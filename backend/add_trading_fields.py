"""
Database Migration: Add Trading Action Fields
Run this script once to add new columns to existing stocks table
"""

import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

def migrate():
    """Add new trading-focused columns to stocks table"""
    
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        print("❌ DATABASE_URL not found in environment")
        return
    
    engine = create_engine(database_url)
    
    migrations = [
        "ALTER TABLE stocks ADD COLUMN IF NOT EXISTS action_verdict VARCHAR(50);",
        "ALTER TABLE stocks ADD COLUMN IF NOT EXISTS entry_zone VARCHAR(200);",
        "ALTER TABLE stocks ADD COLUMN IF NOT EXISTS price_target_short VARCHAR(50);",
        "ALTER TABLE stocks ADD COLUMN IF NOT EXISTS price_target_long VARCHAR(50);",
        "ALTER TABLE stocks ADD COLUMN IF NOT EXISTS stop_loss_risk TEXT;",
        "ALTER TABLE stocks ADD COLUMN IF NOT EXISTS moat_rating INTEGER;",
        "ALTER TABLE stocks ADD COLUMN IF NOT EXISTS trade_rationale TEXT;",
        "ALTER TABLE stocks ADD COLUMN IF NOT EXISTS chart_setup TEXT;",
    ]
    
    with engine.connect() as conn:
        for migration in migrations:
            try:
                conn.execute(text(migration))
                conn.commit()
                print(f"✅ Executed: {migration}")
            except Exception as e:
                print(f"⚠️  {migration}\n   Error: {e}")
    
    print("\n🎯 Migration complete! New trading fields added to database.")

if __name__ == "__main__":
    migrate()
