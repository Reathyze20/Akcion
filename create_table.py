"""Quick script to create the stocks table in your Neon database"""
from sqlalchemy import create_engine, Column, Integer, String, Text, TIMESTAMP
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func

# Your Neon connection string
DATABASE_URL = "postgresql://neondb_owner:npg_YoV4K0xCmpOX@ep-silent-hat-agvd3kf5-pooler.c-2.eu-central-1.aws.neon.tech/neondb?sslmode=require"

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

try:
    print("Connecting to Neon database...")
    engine = create_engine(DATABASE_URL)
    
    print("Creating stocks table...")
    Base.metadata.create_all(engine)
    
    print("✅ SUCCESS! Table created in your Neon database.")
    print("\nYou can now refresh your Streamlit app!")
    
except Exception as e:
    print(f"❌ ERROR: {e}")
