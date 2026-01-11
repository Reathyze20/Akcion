"""
Database Setup Script for AKCION
Creates the PostgreSQL database and tables if they don't exist.
"""

import sys
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

def create_database(admin_url: str, db_name: str):
    """Create database if it doesn't exist"""
    try:
        # Connect to postgres database (default)
        engine = create_engine(admin_url)
        conn = engine.connect()
        
        # Don't use a transaction for CREATE DATABASE
        conn.execute(text("COMMIT"))
        
        # Check if database exists
        result = conn.execute(text(
            f"SELECT 1 FROM pg_database WHERE datname = '{db_name}'"
        ))
        
        if not result.fetchone():
            print(f"Creating database '{db_name}'...")
            conn.execute(text(f"CREATE DATABASE {db_name}"))
            print(f"✅ Database '{db_name}' created successfully!")
        else:
            print(f"ℹ️  Database '{db_name}' already exists.")
        
        conn.close()
        return True
        
    except SQLAlchemyError as e:
        print(f"❌ Error creating database: {e}")
        return False

def setup_tables(db_url: str):
    """Create tables using SQLAlchemy models"""
    try:
        from sqlalchemy import Column, Integer, String, Text, TIMESTAMP
        from sqlalchemy.ext.declarative import declarative_base
        from sqlalchemy.sql import func
        
        Base = declarative_base()
        
        class Stock(Base):
            __tablename__ = 'stocks'
            
            id = Column(Integer, primary_key=True, autoincrement=True)
            created_at = Column(TIMESTAMP, server_default=func.now())
            ticker = Column(String(20), nullable=False)
            company_name = Column(String(255))
            source_type = Column(String(50))
            speaker = Column(String(100))
            sentiment = Column(String(20))
            gomes_score = Column(Integer)
            price_target = Column(String(50))
            edge = Column(Text)
            catalysts = Column(Text)
            risks = Column(Text)
            raw_notes = Column(Text)
            time_horizon = Column(String(50))
            conviction_score = Column(Integer)
        
        engine = create_engine(db_url)
        Base.metadata.create_all(engine)
        
        print("✅ Tables created successfully!")
        return True
        
    except SQLAlchemyError as e:
        print(f"❌ Error creating tables: {e}")
        return False

def main():
    print("=" * 60)
    print("AKCION Database Setup")
    print("=" * 60)
    print()
    
    # Get connection details
    print("Enter PostgreSQL connection details:")
    host = input("Host (e.g., localhost): ").strip() or "localhost"
    port = input("Port (default: 5432): ").strip() or "5432"
    username = input("Username (e.g., postgres): ").strip() or "postgres"
    password = input("Password: ").strip()
    db_name = input("Database name (e.g., akcion_db): ").strip() or "akcion_db"
    
    print()
    print("-" * 60)
    
    # Admin URL (connects to default 'postgres' database)
    admin_url = f"postgresql://{username}:{password}@{host}:{port}/postgres"
    
    # Target database URL
    db_url = f"postgresql://{username}:{password}@{host}:{port}/{db_name}"
    
    # Step 1: Create database
    print(f"\n1. Creating database '{db_name}'...")
    if not create_database(admin_url, db_name):
        print("\n❌ Setup failed at database creation step.")
        sys.exit(1)
    
    # Step 2: Create tables
    print(f"\n2. Creating tables in '{db_name}'...")
    if not setup_tables(db_url):
        print("\n❌ Setup failed at table creation step.")
        sys.exit(1)
    
    # Success!
    print()
    print("=" * 60)
    print("✅ Setup completed successfully!")
    print("=" * 60)
    print()
    print("Add this to your .streamlit/secrets.toml:")
    print()
    print("[postgres]")
    print(f'url = "{db_url}"')
    print()
    print("Then run: streamlit run app.py")
    print()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n❌ Setup cancelled by user.")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        sys.exit(1)
