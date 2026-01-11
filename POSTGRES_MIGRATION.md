# AKCION - PostgreSQL Migration Guide

## Overview
This app has been migrated from SQLite to PostgreSQL using SQLAlchemy ORM for production deployment.

## ✅ What Was Changed

### Database Layer
- **Old**: `sqlite3` library with `invest_data.db` local file
- **New**: SQLAlchemy ORM with PostgreSQL connection via `st.secrets["postgres"]["url"]`

### Schema Changes
- **Old**: Two tables (`videos`, `stock_mentions`)
- **New**: Single `stocks` table with all Gomes methodology fields

### Columns Mapping
```
Old Column Name     →  New Column Name
-------------------------------------------
edge_summary       →  edge
risk_factors       →  risks
key_note           →  raw_notes (aliased as key_note in queries)
```

### Database Functions Updated
1. `init_database()` - Now uses SQLAlchemy engine and creates tables via `Base.metadata.create_all()`
2. `save_analysis()` - Now uses SQLAlchemy Session to insert Stock objects
3. `get_portfolio_master()` - Uses `pd.read_sql_query()` with SQLAlchemy engine
4. `get_ticker_history()` - Uses parameterized queries with SQLAlchemy

## ⚠️ What Was NOT Changed (AI Logic Preserved)

### Analysis System - COMPLETELY UNCHANGED
- ✅ Gemini API integration (`analyze_with_gemini()`)
- ✅ Aggressive fiduciary system prompt for client with MS
- ✅ The Gomes Rules methodology (Information Arbitrage, Catalysts, Risks)
- ✅ Speaker identification ("Mark Gomes")
- ✅ Gomes scoring system (1-10 scale)
- ✅ Stock extraction logic ("AGGRESSIVE EXTRACTION")

### UI System - COMPLETELY UNCHANGED
- ✅ Premium dark fintech CSS (960+ lines)
- ✅ Bloomberg terminal-style aesthetic
- ✅ All display functions (`display_stock_card`, `display_portfolio_dataframe`)
- ✅ Streamlit page layout and navigation
- ✅ Input methods (YouTube, Google Docs, Paste Transcript, Upload File)

## 🚀 Setup Instructions

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure PostgreSQL Connection

Create `.streamlit/secrets.toml`:
```toml
[postgres]
url = "postgresql://username:password@hostname:port/database_name"
```

**Example connection strings:**
```toml
# Local PostgreSQL
url = "postgresql://postgres:mypassword@localhost:5432/akcion_db"

# Heroku Postgres
url = "postgresql://user:pass@ec2-xxx.compute-1.amazonaws.com:5432/dbname"

# Railway
url = "postgresql://postgres:pass@containers-us-west-xxx.railway.app:6543/railway"

# Neon.tech
url = "postgresql://user:pass@ep-xxx-xxx.us-east-2.aws.neon.tech/neondb"
```

### 3. Create PostgreSQL Database

```sql
CREATE DATABASE akcion_db;
```

The app will automatically create the `stocks` table on first run.

### 4. Run the App
```bash
streamlit run app.py
```

## 📊 Database Schema

### Stocks Table
```sql
CREATE TABLE stocks (
    id SERIAL PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ticker VARCHAR(20) NOT NULL,
    company_name VARCHAR(255),
    source_type VARCHAR(50),
    speaker VARCHAR(100),
    sentiment VARCHAR(20),
    gomes_score INTEGER,
    price_target VARCHAR(50),
    edge TEXT,
    catalysts TEXT,
    risks TEXT,
    raw_notes TEXT,
    time_horizon VARCHAR(50),
    conviction_score INTEGER
);
```

## 🔍 Error Handling

The app displays database connection status in the sidebar:
- ✅ Green "PostgreSQL Connected" - Successfully connected
- ⚠️ Red error message - Connection issue with details

If connection fails:
1. Check your `.streamlit/secrets.toml` connection string
2. Verify PostgreSQL server is running
3. Ensure database exists and credentials are correct
4. Check network/firewall settings for cloud databases

## 🧪 Testing Checklist

After migration, verify:
- [ ] Database connects successfully (green status in sidebar)
- [ ] Can analyze YouTube videos
- [ ] Can analyze pasted transcripts
- [ ] Stocks are saved to PostgreSQL
- [ ] Portfolio View displays saved stocks
- [ ] Ticker history works
- [ ] Gomes scores display correctly
- [ ] All 11 stocks from Mark Gomes transcript are preserved (if migrating existing data)

## 📦 Migrating Existing SQLite Data

If you have an existing `invest_data.db` file, you can migrate data:

```python
import sqlite3
import psycopg2
from sqlalchemy import create_engine

# Read from SQLite
sqlite_conn = sqlite3.connect('invest_data.db')
df = pd.read_sql_query("SELECT * FROM stock_mentions", sqlite_conn)

# Write to PostgreSQL
postgres_url = "postgresql://user:pass@host:port/dbname"
engine = create_engine(postgres_url)
df.to_sql('stocks', engine, if_exists='append', index=False)
```

## 🔒 Security Notes

- Never commit `.streamlit/secrets.toml` to version control
- Add to `.gitignore`:
  ```
  .streamlit/secrets.toml
  *.db
  ```
- Use environment variables for production deployments

## 📝 Deployment

For Streamlit Cloud:
1. Push code to GitHub (excluding secrets.toml)
2. In Streamlit Cloud dashboard, go to app settings
3. Add secrets in the "Secrets" section:
   ```toml
   [postgres]
   url = "your-production-postgres-url"
   ```

For other platforms (Heroku, Railway, etc.):
Set environment variable or use their secrets management.

## 🆘 Support

If you encounter issues:
1. Check database connection status in sidebar
2. Verify `.streamlit/secrets.toml` format
3. Test PostgreSQL connection independently
4. Check Streamlit logs for detailed errors

---

**Migration completed by**: Senior Python Backend Developer
**Date**: 2024
**Critical requirement met**: ✅ All AI analysis logic and UI completely preserved
