"""Calculate and update trading zones for all stocks with price lines."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.database.connection import get_engine, initialize_database
from app.config.settings import Settings
from app.services.trading_zones import calculate_trading_zones
from sqlalchemy import text

settings = Settings()

# Initialize database
success, error = initialize_database(settings.database_url)
if not success:
    print(f"❌ Database connection failed: {error}")
    sys.exit(1)

engine = get_engine()

print("🎯 Calculating Trading Zones...")
print()

with engine.begin() as conn:
    # Get all stocks with price lines
    result = conn.execute(text("""
        SELECT id, ticker, current_price, green_line, red_line
        FROM stocks
        WHERE current_price IS NOT NULL 
          AND green_line IS NOT NULL 
          AND red_line IS NOT NULL
    """))
    
    stocks = result.fetchall()
    
    if not stocks:
        print("❌ No stocks with price lines data found")
        sys.exit(1)
    
    for stock in stocks:
        stock_id, ticker, current_price, green_line, red_line = stock
        
        # Calculate zones
        zones = calculate_trading_zones(current_price, green_line, red_line)
        
        # Update database
        conn.execute(text("""
            UPDATE stocks 
            SET 
                max_buy_price = :max_buy,
                start_sell_price = :start_sell,
                risk_to_floor_pct = :risk,
                upside_to_ceiling_pct = :upside,
                trading_zone_signal = :signal
            WHERE id = :id
        """), {
            'id': stock_id,
            'max_buy': zones['max_buy_price'],
            'start_sell': zones['start_sell_price'],
            'risk': zones['risk_to_floor_pct'],
            'upside': zones['upside_to_ceiling_pct'],
            'signal': zones['trading_zone_signal']
        })
        
        print(f"✅ {ticker:8s} | ${current_price:6.2f} | Signal: {zones['trading_zone_signal']:15s} | Upside: {zones['upside_to_ceiling_pct']:6.1f}% | Risk: {zones['risk_to_floor_pct']:6.1f}%")

print()
print(f"🎉 Updated {len(stocks)} stocks with trading zones!")
