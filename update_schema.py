"""Update database columns to handle longer values"""
from sqlalchemy import create_engine, text

# Your Neon connection string
DATABASE_URL = "postgresql://neondb_owner:npg_YoV4K0xCmpOX@ep-silent-hat-agvd3kf5-pooler.c-2.eu-central-1.aws.neon.tech/neondb?sslmode=require"

try:
    print("Connecting to database...")
    engine = create_engine(DATABASE_URL)
    
    with engine.connect() as conn:
        print("Updating column types...")
        
        # Change price_target from VARCHAR(100) to TEXT
        conn.execute(text("ALTER TABLE stocks ALTER COLUMN price_target TYPE TEXT"))
        print("✅ Updated price_target to TEXT")
        
        # Change sentiment from VARCHAR(20) to VARCHAR(50)
        conn.execute(text("ALTER TABLE stocks ALTER COLUMN sentiment TYPE VARCHAR(50)"))
        print("✅ Updated sentiment to VARCHAR(50)")
        
        # Change time_horizon from VARCHAR(50) to VARCHAR(100)
        conn.execute(text("ALTER TABLE stocks ALTER COLUMN time_horizon TYPE VARCHAR(100)"))
        print("✅ Updated time_horizon to VARCHAR(100)")
        
        conn.commit()
    
    print("\n✅ SUCCESS! Database schema updated.")
    print("Refresh your Streamlit app and try analyzing again!")
    
except Exception as e:
    print(f"❌ ERROR: {e}")
