"""Apply Gomes Tactical Fields migration"""
import sys
sys.path.append('.')

from app.database.connection import initialize_database, get_db
from app.config.settings import Settings
from sqlalchemy import text

def apply_migration():
    # Initialize database first
    settings = Settings()
    initialize_database(settings.database_url)
    
    with open('migrations/add_gomes_tactical_fields.sql', 'r', encoding='utf-8') as f:
        sql = f.read()
    
    db = next(get_db())
    try:
        # Split by semicolons and execute each statement
        statements = [s.strip() for s in sql.split(';') if s.strip() and not s.strip().startswith('--')]
        
        for stmt in statements:
            if stmt:
                print(f"Executing: {stmt[:100]}...")
                db.execute(text(stmt))
        
        db.commit()
        print("\n✅ Gomes Tactical Fields migration applied successfully!")
    except Exception as e:
        db.rollback()
        print(f"\n❌ Migration failed: {e}")
        raise
    finally:
        db.close()

if __name__ == '__main__':
    apply_migration()
