"""
Trading Zones Calculator - Gomes Methodology

Calculates BUY/HOLD/SELL zones based on green and red price lines.

Clean Code Principles:
- Single Responsibility: Zone calculation only
- Type-safe with explicit return types
- No side effects - pure calculation
"""

from typing import TypedDict


class TradingZones(TypedDict):
    """Trading zones calculation result."""
    max_buy_price: float | None
    start_sell_price: float | None
    risk_to_floor_pct: float | None
    upside_to_ceiling_pct: float | None
    trading_zone_signal: str | None


def calculate_trading_zones(
    current_price: float | None,
    green_line: float | None,
    red_line: float | None
) -> TradingZones:
    """
    Calculate Gomes Trading Zones from price lines.
    
    Logic:
    - BUY LIMIT: green_line + 5% (Above this: HOLD only)
    - SELL LIMIT: red_line - 5% (Sell into strength, before top)
    - Risk: % distance to green (downside)
    - Upside: % distance to red (potential gain)
    - Signal: Based on where current price sits
    
    Args:
        current_price: Current market price
        green_line: Support/Buy zone price (Gomes undervalued)
        red_line: Resistance/Sell zone price (Gomes fair/overvalued)
    
    Returns:
        TradingZones dict with calculated metrics
    """
    # Default empty response
    if not all([current_price, green_line, red_line]):
        return {
            "max_buy_price": None,
            "start_sell_price": None,
            "risk_to_floor_pct": None,
            "upside_to_ceiling_pct": None,
            "trading_zone_signal": None
        }
    
    # Convert to float (in case of Decimal from database)
    current_price = float(current_price)
    green_line = float(green_line)
    red_line = float(red_line)
    
    # Calculate zone boundaries
    max_buy_price = green_line * 1.05  # Green + 5%
    start_sell_price = red_line * 0.95  # Red - 5%
    
    # Calculate risk/reward percentages
    risk_to_floor_pct = ((current_price - green_line) / current_price) * 100
    upside_to_ceiling_pct = ((red_line - current_price) / current_price) * 100
    
    # Determine trading signal
    if current_price <= max_buy_price:
        # Price is at or below green + 5%
        if current_price < green_line:
            signal = "AGGRESSIVE_BUY"  # Below green line (steal)
        else:
            signal = "BUY"  # Between green and green+5%
    elif current_price >= start_sell_price:
        # Price is at or above red - 5%
        if current_price > red_line:
            signal = "STRONG_SELL"  # Above red line (overvalued)
        else:
            signal = "SELL"  # Between red-5% and red
    else:
        # Price is in neutral zone (green+5% to red-5%)
        signal = "HOLD"
    
    return {
        "max_buy_price": round(max_buy_price, 2),
        "start_sell_price": round(start_sell_price, 2),
        "risk_to_floor_pct": round(risk_to_floor_pct, 2),
        "upside_to_ceiling_pct": round(upside_to_ceiling_pct, 2),
        "trading_zone_signal": signal
    }


def update_stock_trading_zones(stock) -> None:
    """
    Update Stock model instance with calculated trading zones.
    
    Modifies stock object in-place (does NOT commit to database).
    
    Args:
        stock: Stock SQLAlchemy model instance
    """
    zones = calculate_trading_zones(
        stock.current_price,
        stock.green_line,
        stock.red_line
    )
    
    stock.max_buy_price = zones["max_buy_price"]
    stock.start_sell_price = zones["start_sell_price"]
    stock.risk_to_floor_pct = zones["risk_to_floor_pct"]
    stock.upside_to_ceiling_pct = zones["upside_to_ceiling_pct"]
    stock.trading_zone_signal = zones["trading_zone_signal"]
