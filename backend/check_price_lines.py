"""Quick script to check if green_line and red_line data exists in stocks table."""

from sqlalchemy import create_engine, text
from app.config.settings import Settings

settings = Settings()
engine = create_engine(settings.database_url)

with engine.connect() as conn:
    result = conn.execute(text("""
        SELECT ticker, current_price, green_line, red_line 
        FROM stocks 
        WHERE ticker IN ('KUYA.V', 'TSLY', 'NVDY', 'MSTY', 'XMMO.V')
        LIMIT 10
    """))
    
    print("\n=== Price Lines Data ===")
    for row in result:
        print(f"{row[0]}: current={row[1]}, green={row[2]}, red={row[3]}")
    
    # Check total count
    count_result = conn.execute(text("""
        SELECT 
            COUNT(*) as total,
            COUNT(green_line) as has_green,
            COUNT(red_line) as has_red
        FROM stocks
    """))
    
    stats = count_result.fetchone()
    print(f"\n=== Statistics ===")
    print(f"Total stocks: {stats[0]}")
    print(f"Has green_line: {stats[1]}")
    print(f"Has red_line: {stats[2]}")
