"""
Cash and hedge as real instruments, not percentages.

Canon §2 does not say "hold 15 % cash". It says BOXX — a money-market ETF where
cash is parked and stays liquid — and RWM, an inverse Russell 2000 ETF, which
is the hedge. In ORANGE it is quoted directly: *"I have ALL of my cash in RWM."*
The app modelled both as abstract percentages, which is a plan you cannot
execute.

Modelling them properly turns out to surface the thing that actually matters
here, and it is not the arithmetic.

**Both instruments are US-domiciled, and this portfolio is not.**

Verified against live data 2026-08-23: RWM is ProShares Short Russell2000 on
NYSE Arca, BOXX is Alpha Architect 1-3 Month Box on Cboe US. Both are US funds
priced in USD. EU retail brokers generally cannot offer a US-domiciled ETF to
an EU retail client, because PRIIPs requires a key information document that US
funds do not publish. A plan that says "put 40 % into RWM" to someone holding
Degiro and Trading 212 accounts in Czechia is a plan for a button that is not
there.

The canon anticipates this in one line — *"Mimo USA: RWM nemusí být dostupné →
buď extra vybíravý, drž víc cashe místo hedge"* — and that line is the fallback
this module returns, rather than a target it knows cannot be filled.

Nothing here checks a specific broker's product list, so availability is stated
as a likelihood with its reason, never as a fact. "Your broker probably cannot
sell you this, here is why, check it" is honest. "Unavailable" would be a claim
about an account this code has never seen.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Final

from loguru import logger

CACHE_TTL: Final[timedelta] = timedelta(hours=6)


class Role(str, Enum):
    CASH_PARK = "CASH_PARK"
    HEDGE = "HEDGE"


class Availability(str, Enum):
    """How likely the holder can actually buy this. Never a claim of fact."""

    LIKELY_AVAILABLE = "LIKELY_AVAILABLE"
    LIKELY_BLOCKED_EU_RETAIL = "LIKELY_BLOCKED_EU_RETAIL"
    UNKNOWN = "UNKNOWN"


class HedgeError(Exception):
    """A price could not be read. Never replaced with a made-up one."""


@dataclass(frozen=True)
class Instrument:
    """One real, buyable thing — or one the canon names that may not be."""

    ticker: str
    name: str
    role: Role
    currency: str
    domicile: str
    exchange: str
    ucits: bool
    note_cs: str

    @property
    def availability(self) -> Availability:
        """
        US domicile is what blocks an EU retail purchase, so it is what this
        keys on. A UCITS fund is the case that is likely fine.
        """
        if self.ucits:
            return Availability.LIKELY_AVAILABLE
        if self.domicile == "US":
            return Availability.LIKELY_BLOCKED_EU_RETAIL
        return Availability.UNKNOWN


#: The two instruments the canon names, as they actually exist. Verified
#: against live quote data on 2026-08-23.
BOXX: Final[Instrument] = Instrument(
    ticker="BOXX",
    name="Alpha Architect 1-3 Month Box ETF",
    role=Role.CASH_PARK,
    currency="USD",
    domicile="US",
    exchange="Cboe US",
    ucits=False,
    note_cs=(
        "Sem kánon parkuje hotovost — má být rychle likvidní. Je to americký "
        "fond bez KID podle PRIIPs, takže ho evropský retailový broker "
        "pravděpodobně neprodá."
    ),
)

RWM: Final[Instrument] = Instrument(
    ticker="RWM",
    name="ProShares Short Russell2000",
    role=Role.HEDGE,
    currency="USD",
    domicile="US",
    exchange="NYSE Arca",
    ucits=False,
    note_cs=(
        "Inverzní Russell 2000 — roste, když trh padá. Kánon sám varuje, že "
        "při rostoucím trhu padá, takže se ho nemá kupovat moc. Americký fond, "
        "evropský retail ho pravděpodobně nekoupí."
    ),
)

CANON_INSTRUMENTS: Final[tuple[Instrument, ...]] = (BOXX, RWM)

#: Named because it exists, not because it is a substitute. A UCITS inverse ETF
#: an EU retail account can normally buy — but it shorts the S&P 500, not the
#: Russell 2000, and it resets daily, so in a choppy sideways market it bleeds
#: even when the index ends where it started. Different instrument, different
#: risk. The canon's own fallback is cash, and that is what `plan` returns.
UCITS_INVERSE_EXAMPLE: Final[Instrument] = Instrument(
    ticker="XSPS.L",
    name="Xtrackers S&P 500 Inverse Daily Swap UCITS ETF",
    role=Role.HEDGE,
    currency="GBp",
    domicile="IE",
    exchange="LSE",
    ucits=True,
    note_cs=(
        "UCITS, takže koupitelné — ale shortuje S&P 500, ne Russell 2000, a "
        "resetuje se denně. V rozkolísaném bočním trhu ztrácí, i když index "
        "skončí tam, kde začal. Není to náhrada RWM, jen důkaz, že evropská "
        "inverzní ETF existují."
    ),
)

#: The canon's own words, and what is the app's interpretation. Only YELLOW is
#: quoted: *"20-30 % v RWM je víc než dost."* The ORANGE line is a quote about
#: cash, not a percentage. GREEN is explicit. RED is described, not numbered.
CANON_HEDGE_TEXT: Final[dict[str, str]] = {
    "GREEN": "0 % hedge — „own stocks without fear\".",
    "YELLOW": "„20-30 % v RWM je víc než dost.\" (doslovný údaj z kánonu)",
    "ORANGE": "„I have ALL of my cash in RWM.\" — kánon nedává procento, dává větu.",
    "RED": "Většina peněz v RWM. Kánon nedává číslo.",
}

#: Where the app's numbers stop being the canon's. Flagged so a percentage
#: nobody said out loud cannot be read as scripture.
CANON_GIVES_A_NUMBER: Final[frozenset[str]] = frozenset({"GREEN", "YELLOW"})


@dataclass(frozen=True)
class Leg:
    """One line of an executable plan."""

    instrument: Instrument
    target_czk: float
    price: float | None
    shares: float | None
    #: Set when this leg cannot be executed as written.
    blocker_cs: str | None = None


@dataclass(frozen=True)
class Plan:
    """What the semafor implies, in instruments and amounts."""

    alert: str
    portfolio_czk: float
    stocks_pct: float
    cash_pct: float
    hedge_pct: float
    legs: list[Leg]
    canon_text: str
    #: True when the percentages are the app's reading rather than the canon's.
    interpreted: bool
    fallback_cs: str | None = None
    gaps: list[str] = None  # type: ignore[assignment]


# ==============================================================================
# Prices
# ==============================================================================

_lock = threading.Lock()
_prices: dict[str, tuple[float, datetime]] = {}


def reset_cache() -> None:
    with _lock:
        _prices.clear()


def price_of(ticker: str) -> float | None:
    """
    Last close for one instrument, cached.

    None — not a guess — when it cannot be read. A share count computed from an
    invented price is worse than no share count.
    """
    with _lock:
        cached = _prices.get(ticker)
        if cached and datetime.now() - cached[1] < CACHE_TTL:
            return cached[0]

    try:
        import yfinance as yf

        history = yf.Ticker(ticker).history(period="5d")
        if history.empty:
            logger.warning("{}: prázdná historie, cenu nemám", ticker)
            return None
        value = float(history["Close"].iloc[-1])
    except Exception as e:  # noqa: BLE001
        logger.warning("{}: cenu nelze načíst: {}", ticker, e)
        return None

    with _lock:
        _prices[ticker] = (value, datetime.now())
    return value


# ==============================================================================
# The plan
# ==============================================================================

def build_plan(
    alert: str | None,
    portfolio_czk: float,
    *,
    fx_rate_to_czk,
    allocations: dict[str, tuple[float, float, float]] | None = None,
) -> Plan:
    """
    Turn the semafor into instruments and amounts.

    `fx_rate_to_czk` converts an instrument's currency; it may raise, and a leg
    whose currency cannot be converted comes back with a stated gap rather than
    a koruna figure built on a guess.

    Raises HedgeError only for an unusable semafor — an absent one is a gap the
    caller has to see, not a reason to plan for GREEN.
    """
    if not alert:
        raise HedgeError(
            "Semafor není nastavený — kolik držet v hotovosti a v hedgi z "
            "ničeho neodvodím."
        )

    level = alert.upper()
    table = allocations or _default_allocations()
    if level not in table:
        raise HedgeError(f"Neznámý semafor {level}.")

    stocks_pct, cash_pct, hedge_pct = table[level]
    gaps: list[str] = []
    legs = [
        _leg(BOXX, portfolio_czk * cash_pct / 100, fx_rate_to_czk, gaps),
        _leg(RWM, portfolio_czk * hedge_pct / 100, fx_rate_to_czk, gaps),
    ]

    blocked = [leg for leg in legs if leg.blocker_cs and leg.target_czk > 0]
    fallback = _fallback_text(blocked, cash_pct + hedge_pct) if blocked else None

    return Plan(
        alert=level,
        portfolio_czk=portfolio_czk,
        stocks_pct=stocks_pct,
        cash_pct=cash_pct,
        hedge_pct=hedge_pct,
        legs=legs,
        canon_text=CANON_HEDGE_TEXT.get(level, ""),
        interpreted=level not in CANON_GIVES_A_NUMBER,
        fallback_cs=fallback,
        gaps=gaps,
    )


def _leg(
    instrument: Instrument, target_czk: float, fx_rate_to_czk, gaps: list[str],
) -> Leg:
    price = price_of(instrument.ticker)
    shares: float | None = None

    if price is None:
        gaps.append(
            f"{instrument.ticker}: cenu se nepodařilo načíst, počet kusů "
            f"nespočítám."
        )
    else:
        try:
            rate = fx_rate_to_czk(instrument.currency)
            shares = target_czk / (price * rate) if price > 0 else None
        except Exception as e:  # noqa: BLE001 — CurrencyError and anything else
            gaps.append(f"{instrument.ticker}: {e}")

    blocker = None
    if instrument.availability is Availability.LIKELY_BLOCKED_EU_RETAIL:
        blocker = (
            f"{instrument.ticker} je americký fond bez KID podle PRIIPs. "
            f"Evropský retailový broker (Degiro, Trading 212) ho "
            f"pravděpodobně neprodá — ověř si to u svého."
        )

    return Leg(
        instrument=instrument,
        target_czk=target_czk,
        price=price,
        shares=shares,
        blocker_cs=blocker,
    )


def _fallback_text(blocked: list[Leg], defensive_pct: float) -> str:
    """The canon's own answer for an investor outside the US."""
    names = ", ".join(leg.instrument.ticker for leg in blocked)
    return (
        f"{names} si nejspíš koupit nemůžeš. Kánon na to má vlastní odpověď: "
        f"„Mimo USA drž víc cashe místo hedge a buď extra vybíravý.\" "
        f"Prakticky: těch {defensive_pct:.0f} % nech v hotovosti na účtu a "
        f"zpřísni, co vůbec pustíš do portfolia — hedge, který nekoupíš, "
        f"nenahradíš tím, že ho budeš mít v plánu."
    )


def _default_allocations() -> dict[str, tuple[float, float, float]]:
    from app.trading.gomes_logic import MarketAlertSystem

    return {
        alert.value: values
        for alert, values in MarketAlertSystem.ALLOCATIONS.items()
    }
