"""Clear all data from database tables."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from app.database.connection import initialize_database, session_scope
from sqlalchemy import text

def clear_database():
    # Initialize database connection
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("ERROR: DATABASE_URL not set")
        return
    
    success, error = initialize_database(db_url)
    if not success:
        print(f"ERROR: {error}")
        return
    
    with session_scope() as session:
        conn = session.connection()
        
        # Get all tables (exclude views starting with v_)
        result = conn.execute(text("""
            SELECT table_name FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_type = 'BASE TABLE'
            ORDER BY table_name
        """))
        tables = [row[0] for row in result]
        
        print("Tables in database:")
        for t in tables:
            count = conn.execute(text(f'SELECT COUNT(*) FROM "{t}"')).scalar()
            print(f"  {t}: {count} rows")
        
        print("\n" + "="*50)
        confirm = input("Delete ALL data? (yes/no): ")
        
        if confirm.lower() == "yes":
            for table in tables:
                conn.execute(text(f'TRUNCATE TABLE "{table}" CASCADE'))
                print(f"  Cleared: {table}")
            
            session.commit()
            print("\nDatabase cleared!")
        else:
            print("Cancelled.")

if __name__ == "__main__":
    clear_database()
