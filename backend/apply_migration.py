"""
Quick migration script - applies SQL migrations
Uses existing app database connection
"""
import sys
from pathlib import Path
from sqlalchemy import text

# Add app to path
sys.path.insert(0, str(Path(__file__).parent))

from app.database.connection import get_engine
from app.config.settings import get_settings

def apply_migration(migration_name: str = "add_gomes_tactical_fields"):
    """Apply specified migration"""
    
    migration_file = Path(__file__).parent / "migrations" / f"{migration_name}.sql"
    
    if not migration_file.exists():
        print(f"❌ Migration file not found: {migration_file}")
        return False
    
    # Read SQL
    sql_content = migration_file.read_text(encoding='utf-8')
    
    # Remove docstring comments (triple quotes cause issues)
    lines = sql_content.split('\n')
    cleaned_lines = []
    in_docstring = False
    
    for line in lines:
        if '"""' in line:
            in_docstring = not in_docstring
            continue
        if not in_docstring:
            cleaned_lines.append(line)
    
    sql_content = '\n'.join(cleaned_lines)
    
    # Initialize database connection
    settings = get_settings()
    from app.database.connection import initialize_database
    success, error = initialize_database(settings.database_url)
    
    if not success:
        print(f"❌ Database connection failed: {error}")
        return False
    
    # Get engine
    engine = get_engine()
    
    print("🚀 Applying Gomes Master Table migration...")
    print(f"📄 File: {migration_file.name}")
    print(f"📊 Database: {engine.url.database}")
    print()
    
    try:
        with engine.begin() as conn:
            # Execute SQL
            conn.execute(text(sql_content))
            conn.commit()
        
        print("✅ Migration applied successfully!")
        print()
        print("Added columns:")
        print("  - asset_class (ANCHOR/HIGH_BETA_ROCKET/...)")
        print("  - cash_runway_months")
        print("  - gomes_score (0-10)")
        print("  - inflection_status (WAIT_TIME/UPCOMING/ACTIVE_GOLD_MINE)")
        print("  - primary_catalyst, catalyst_date")
        print("  - price_floor, price_base, price_moon")
        print("  - max_allocation_cap, stop_loss_price")
        print("  - insider_activity (BUYING/HOLDING/SELLING)")
        print("  - thesis_narrative")
        print("  + 10 more fields + 6 indexes")
        print()
        return True
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        return False

if __name__ == "__main__":
    migration_name = sys.argv[1] if len(sys.argv) > 1 else "add_gomes_tactical_fields"
    success = apply_migration(migration_name)
    sys.exit(0 if success else 1)
