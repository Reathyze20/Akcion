"""
Market Hours Helper - NYSE Trading Hours Detection

Detekuje jestli jsou trhy otevřené nebo zavřené podle NYSE pravidel.
Respektuje časové pásmo US Eastern Time a státní svátky.

CRITICAL: Část Gomes Guardian aplikace pro finanční zabezpečení rodiny.
Přesnost market hours je klíčová pro správné cachování Yahoo Finance dat.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Final
from zoneinfo import ZoneInfo

import logging

logger = logging.getLogger(__name__)


# ==============================================================================
# Constants
# ==============================================================================

# NYSE časové pásmo
MARKET_TIMEZONE: Final = ZoneInfo("America/New_York")

# Obchodní hodiny (NYSE regular hours)
MARKET_OPEN_TIME: Final = time(9, 30)   # 9:30 AM EST
MARKET_CLOSE_TIME: Final = time(16, 0)  # 4:00 PM EST

# Pre-market a After-hours (pro budoucí rozšíření)
PRE_MARKET_OPEN: Final = time(4, 0)     # 4:00 AM EST
AFTER_HOURS_CLOSE: Final = time(20, 0)  # 8:00 PM EST

# NYSE státní svátky 2026 (pevně dané dny)
NYSE_HOLIDAYS_2026: Final[set[tuple[int, int]]] = {
    (1, 1),    # New Year's Day
    (1, 20),   # Martin Luther King Jr. Day
    (2, 17),   # Presidents' Day
    (4, 3),    # Good Friday
    (5, 25),   # Memorial Day
    (7, 3),    # Independence Day (observed)
    (9, 7),    # Labor Day
    (11, 26),  # Thanksgiving Day
    (12, 25),  # Christmas Day
}


# ==============================================================================
# Market Hours Logic
# ==============================================================================

def get_current_market_time() -> datetime:
    """
    Vrátí aktuální čas v NYSE timezone (America/New_York).
    
    Returns:
        datetime: Aktuální čas v Eastern Time
    """
    return datetime.now(MARKET_TIMEZONE)


def is_weekend(dt: datetime | None = None) -> bool:
    """
    Zkontroluje jestli je víkend (sobota nebo neděle).
    
    Args:
        dt: Datetime k testování (default: now)
        
    Returns:
        bool: True pokud je sobota (5) nebo neděle (6)
    """
    if dt is None:
        dt = get_current_market_time()
    
    # Convert to market timezone if not already
    if dt.tzinfo != MARKET_TIMEZONE:
        dt = dt.astimezone(MARKET_TIMEZONE)
    
    return dt.weekday() in (5, 6)  # Saturday = 5, Sunday = 6


def is_nyse_holiday(dt: datetime | None = None) -> bool:
    """
    Zkontroluje jestli je NYSE státní svátek.
    
    Args:
        dt: Datetime k testování (default: now)
        
    Returns:
        bool: True pokud je NYSE zavřená kvůli svátku
    """
    if dt is None:
        dt = get_current_market_time()
    
    # Convert to market timezone if not already
    if dt.tzinfo != MARKET_TIMEZONE:
        dt = dt.astimezone(MARKET_TIMEZONE)
    
    return (dt.month, dt.day) in NYSE_HOLIDAYS_2026


def is_market_open(dt: datetime | None = None, include_extended_hours: bool = False) -> bool:
    """
    Zkontroluje jestli je NYSE otevřená (regular hours nebo extended hours).
    
    GOMES PRAVIDLO: Během market hours aktualizujeme data každých 15 minut.
    Mimo market hours neaktualizujeme (šetříme API calls).
    
    Args:
        dt: Datetime k testování (default: now)
        include_extended_hours: Pokud True, počítá i pre-market a after-hours
        
    Returns:
        bool: True pokud jsou trhy otevřené
        
    Examples:
        >>> # Úterý 10:00 EST
        >>> is_market_open(datetime(2026, 1, 27, 10, 0, tzinfo=MARKET_TIMEZONE))
        True
        
        >>> # Sobota
        >>> is_market_open(datetime(2026, 1, 25, 10, 0, tzinfo=MARKET_TIMEZONE))
        False
        
        >>> # Úterý 17:00 EST (po zavíračce)
        >>> is_market_open(datetime(2026, 1, 27, 17, 0, tzinfo=MARKET_TIMEZONE))
        False
    """
    if dt is None:
        dt = get_current_market_time()
    
    # Convert to market timezone if not already
    if dt.tzinfo != MARKET_TIMEZONE:
        dt = dt.astimezone(MARKET_TIMEZONE)
    
    # Kontrola víkendu
    if is_weekend(dt):
        logger.debug(f"Market closed: Weekend ({dt.strftime('%A')})")
        return False
    
    # Kontrola státního svátku
    if is_nyse_holiday(dt):
        logger.debug(f"Market closed: NYSE Holiday ({dt.month}/{dt.day})")
        return False
    
    # Kontrola časů
    current_time = dt.time()
    
    if include_extended_hours:
        # Pre-market + Regular + After-hours
        is_open = PRE_MARKET_OPEN <= current_time <= AFTER_HOURS_CLOSE
    else:
        # Pouze regular hours (9:30 - 16:00)
        is_open = MARKET_OPEN_TIME <= current_time <= MARKET_CLOSE_TIME
    
    if not is_open:
        logger.debug(f"Market closed: Outside trading hours ({current_time})")
    
    return is_open


def should_refresh_market_data(
    last_updated: datetime | None,
    force: bool = False
) -> tuple[bool, str]:
    """
    Rozhodne jestli by se měla aktualizovat market data podle Gomes pravidel.
    
    GOMES PRAVIDLA:
    1. Force refresh = vždy aktualizovat (manual button)
    2. Market zavřený + data mladší než 12h = neaktualizovat (cache)
    3. Market otevřený + data starší než 15 min = aktualizovat
    4. Žádná data = aktualizovat
    
    Args:
        last_updated: Timestamp posledního update
        force: Force refresh flag (manual button)
        
    Returns:
        tuple[bool, str]: (should_refresh, reason)
        
    Examples:
        >>> # Force refresh
        >>> should_refresh_market_data(None, force=True)
        (True, 'Manual refresh requested')
        
        >>> # Žádná data
        >>> should_refresh_market_data(None)
        (True, 'No cached data available')
        
        >>> # Market zavřený, data stará 1 hodinu
        >>> should_refresh_market_data(datetime.now() - timedelta(hours=1))
        (False, 'Market closed - using cache (age: 1.0h)')
    """
    # Rule 1: Force refresh
    if force:
        return True, "Manual refresh requested"
    
    # Rule 2: Žádná data
    if last_updated is None:
        return True, "No cached data available"
    
    # Spočítej stáří dat
    current_time = get_current_market_time()
    
    # Ensure last_updated is timezone-aware
    if last_updated.tzinfo is None:
        # Assume UTC if naive
        last_updated = last_updated.replace(tzinfo=ZoneInfo("UTC"))
    
    age = current_time - last_updated
    age_minutes = age.total_seconds() / 60
    age_hours = age_minutes / 60
    
    # Rule 3: Market zavřený
    if not is_market_open():
        # O víkendu/po zavíračce nerefreshujeme pokud data nejsou starší než 12h
        if age_hours < 12:
            return False, f"Market closed - using cache (age: {age_hours:.1f}h)"
        else:
            return True, f"Market closed but data stale (age: {age_hours:.1f}h)"
    
    # Rule 4: Market otevřený
    if age_minutes > 15:
        return True, f"Market open - data stale (age: {age_minutes:.1f} min)"
    else:
        return False, f"Market open - cache fresh (age: {age_minutes:.1f} min)"


def get_market_status() -> dict[str, any]:
    """
    Vrátí kompletní status trhů pro debug/monitoring.
    
    Returns:
        dict s informacemi o market status
        
    Example:
        {
            "is_open": True,
            "current_time_est": "2026-01-27 10:30:00 EST",
            "is_weekend": False,
            "is_holiday": False,
            "next_open": "2026-01-27 09:30:00 EST",
            "next_close": "2026-01-27 16:00:00 EST"
        }
    """
    now = get_current_market_time()
    
    return {
        "is_open": is_market_open(),
        "current_time_est": now.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "is_weekend": is_weekend(now),
        "is_holiday": is_nyse_holiday(now),
        "weekday": now.strftime("%A"),
        "regular_hours": f"{MARKET_OPEN_TIME} - {MARKET_CLOSE_TIME} EST",
    }


# ==============================================================================
# Utility Functions
# ==============================================================================

def minutes_until_market_open() -> int | None:
    """
    Vrátí počet minut do otevření trhu.
    
    Returns:
        int | None: Počet minut nebo None pokud trh už je otevřený
    """
    if is_market_open():
        return None
    
    now = get_current_market_time()
    
    # Spočítej další otevírací čas
    next_open = now.replace(hour=MARKET_OPEN_TIME.hour, minute=MARKET_OPEN_TIME.minute, second=0)
    
    # Pokud jsme po zavíračce, přidej den
    if now.time() > MARKET_CLOSE_TIME:
        next_open += timedelta(days=1)
    
    # Přeskoč víkendy
    while is_weekend(next_open) or is_nyse_holiday(next_open):
        next_open += timedelta(days=1)
    
    delta = next_open - now
    return int(delta.total_seconds() / 60)


def format_market_time(dt: datetime) -> str:
    """
    Formátuj datetime do lidsky čitelného formátu s EST timezone.
    
    Args:
        dt: Datetime k formátování
        
    Returns:
        str: Formatted string
        
    Example:
        "Mon 27 Jan 2026 10:30 EST"
    """
    if dt.tzinfo != MARKET_TIMEZONE:
        dt = dt.astimezone(MARKET_TIMEZONE)
    
    return dt.strftime("%a %d %b %Y %H:%M %Z")
