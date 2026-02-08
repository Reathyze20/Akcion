"""Populate price lines with sample data for testing."""

from sqlalchemy import create_engine, text
from app.config.settings import Settings

settings = Settings()
engine = create_engine(settings.database_url)

# Sample price data for testing
test_data = {
    'KUYA.V': {'current': 1.50, 'green': 1.20, 'red': 2.00},
    'TSLY': {'current': 45.00, 'green': 40.00, 'red': 50.00},
    'NVDY': {'current': 30.00, 'green': 25.00, 'red': 35.00},
    'MSTY': {'current': 50.00, 'green': 45.00, 'red': 55.00},
    'XMMO.V': {'current': 0.80, 'green': 0.60, 'red': 1.00},
}

with engine.begin() as conn:
    for ticker, prices in test_data.items():
        # First, check if stock exists, if not create it
        result = conn.execute(text("""
            SELECT id FROM stocks WHERE ticker = :ticker
        """), {'ticker': ticker})
        
        stock = result.fetchone()
        
        if not stock:
            # Create new stock entry
            conn.execute(text("""
                INSERT INTO stocks (ticker, company_name, source_type, created_at)
                VALUES (:ticker, :name, 'Manual', NOW())
            """), {
                'ticker': ticker,
                'name': f'{ticker} Test Company'
            })
            print(f"📝 Created stock entry for {ticker}")
        
        # Calculate price position
        price_range = prices['red'] - prices['green']
        position_pct = ((prices['current'] - prices['green']) / price_range) * 100 if price_range > 0 else 50
        
        # Determine zone
        if position_pct <= 20:
            zone = 'DEEP_VALUE'
        elif position_pct <= 40:
            zone = 'BUY_ZONE'
        elif position_pct <= 60:
            zone = 'FAIR_VALUE'
        elif position_pct <= 80:
            zone = 'SELL_ZONE'
        else:
            zone = 'OVERVALUED'
        
        conn.execute(text("""
            UPDATE stocks 
            SET 
                current_price = :current,
                green_line = :green,
                red_line = :red,
                price_position_pct = :position,
                price_zone = :zone
            WHERE ticker = :ticker
        """), {
            'ticker': ticker,
            'current': prices['current'],
            'green': prices['green'],
            'red': prices['red'],
            'position': round(position_pct, 2),
            'zone': zone
        })
        
        print(f"✅ {ticker}: ${prices['current']} (Green: ${prices['green']}, Red: ${prices['red']}) → {zone}")

print("\n🎉 Price lines populated successfully!")
