"""Fix insider_activity constraint in database"""
from sqlalchemy import create_engine, text
from app.config.settings import Settings

settings = Settings()
engine = create_engine(settings.database_url)

with engine.connect() as conn:
    # Drop old constraint
    conn.execute(text('ALTER TABLE stocks DROP CONSTRAINT IF EXISTS stocks_insider_activity_check'))
    # Add new constraint with UNKNOWN and NEUTRAL
    conn.execute(text("ALTER TABLE stocks ADD CONSTRAINT stocks_insider_activity_check CHECK (insider_activity IN ('BUYING', 'HOLDING', 'SELLING', 'NEUTRAL', 'UNKNOWN'))"))
    conn.commit()
    print('Constraint updated successfully!')
