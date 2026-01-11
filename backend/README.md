# Akcion Backend - FastAPI Server

## Overview
This is the FastAPI backend for the Akcion Investment Analysis application. It provides REST API endpoints that wrap the core business logic extracted from the original Streamlit application.

## Architecture

```
backend/
├── app/
│   ├── core/           # Core business logic (AI, extractors)
│   ├── models/         # SQLAlchemy database models
│   ├── database/       # Database connection & repositories
│   ├── routes/         # FastAPI route handlers
│   ├── schemas/        # Pydantic request/response models
│   ├── config/         # Configuration management
│   └── main.py         # FastAPI application entry point
├── tests/              # Test suite
├── requirements.txt    # Python dependencies
├── .env               # Environment configuration
└── start.py           # Startup script
```

## Quick Start

### 1. Install Dependencies

```bash
cd backend
pip install -r requirements.txt
```

### 2. Configure Environment

Copy `.env.example` to `.env` and configure:

```bash
copy .env.example .env
```

Edit `.env` with your credentials:
- `DATABASE_URL`: PostgreSQL connection string
- `GEMINI_API_KEY`: Google Gemini API key
- `CORS_ORIGINS`: Allowed frontend origins

### 3. Start Server

**Option A: Using startup script**
```bash
python start.py
```

**Option B: Direct uvicorn**
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The API will be available at:
- **API**: http://localhost:8000
- **Docs**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## API Endpoints

### Analysis Endpoints

#### POST /api/analyze/text
Analyze raw transcript text for stock mentions.

**Request:**
```json
{
  "transcript": "I'm very bullish on NVDA. The AI revolution is just beginning...",
  "speaker": "Mark Gomes",
  "source_type": "manual_input"
}
```

#### POST /api/analyze/youtube
Analyze YouTube video transcript.

**Request:**
```json
{
  "url": "https://www.youtube.com/watch?v=VIDEO_ID",
  "speaker": "Mark Gomes"
}
```

#### POST /api/analyze/google-docs
Analyze Google Docs content.

**Request:**
```json
{
  "url": "https://docs.google.com/document/d/DOC_ID/edit",
  "speaker": "Mark Gomes"
}
```

### Portfolio Endpoints

#### GET /api/stocks
Get all stocks with optional filters.

**Query Parameters:**
- `sentiment`: Filter by BULLISH, BEARISH, or NEUTRAL
- `min_gomes_score`: Minimum Gomes Score (1-10)
- `min_conviction`: Minimum Conviction Score (1-10)
- `speaker`: Filter by speaker name

#### GET /api/stocks/high-conviction
Get high-conviction picks (Gomes Score >= 7, Conviction >= 7).

#### GET /api/stocks/{ticker}
Get most recent analysis for a specific ticker.

#### GET /api/stocks/{ticker}/history
Get all historical analyses for a ticker.

#### GET /api/stocks/stats/summary
Get portfolio summary statistics.

### Health Check

#### GET /health
Comprehensive health check for all services.

## Core Features Preserved

This backend maintains 100% of the original Streamlit application's functionality:

1. **FIDUCIARY_ANALYST_PROMPT**: MS client context for family financial security
2. **Aggressive Extraction**: Extracts EVERY stock mentioned in transcripts
3. **The Gomes Rules**:
   - Information Arbitrage (Edge)
   - Catalysts
   - Risk Assessment
4. **Scoring System**: Gomes Score (1-10), Conviction Score (1-10)
5. **Database Schema**: All 15 Stock model fields preserved
6. **AI Model**: gemini-3-pro-preview with Google Search enabled

## Testing

Run the verification test suite:

```bash
cd backend
python tests/test_phase1_extraction.py
```

Test API endpoints:
```bash
pytest tests/
```

## Database

The application uses PostgreSQL (Neon.tech) with the following schema:

**Stock Model:**
- `id`: Primary key
- `created_at`: Timestamp
- `ticker`: Stock symbol
- `company_name`: Company name
- `source_type`: youtube, google_docs, manual_input
- `speaker`: Speaker/analyst name
- `sentiment`: BULLISH, BEARISH, NEUTRAL
- `gomes_score`: 1-10 opportunity score
- `conviction_score`: 1-10 conviction level
- `price_target`: Target price and timeframe
- `time_horizon`: Investment horizon
- `edge`: Information Arbitrage explanation
- `catalysts`: Positive catalysts
- `risks`: Risk factors
- `raw_notes`: Full AI response

## Development

### Running in Development Mode

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The `--reload` flag enables auto-reload on code changes.

### CORS Configuration

The backend is configured to accept requests from:
- `http://localhost:5173` (Vite default)
- `http://localhost:3000` (Create React App default)
- `http://127.0.0.1:5173`
- `http://127.0.0.1:3000`

Modify `CORS_ORIGINS` in `.env` to add more origins.

## Production Deployment

For production deployment:

1. Set `DEBUG=False` in `.env`
2. Use a production ASGI server:
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
   ```
3. Use a reverse proxy (nginx, Caddy)
4. Enable HTTPS
5. Restrict CORS origins to your frontend domain

## Migration from Streamlit

The original Streamlit app (`app.py`) can continue running while you migrate to the new architecture. The backend modules can be imported into the Streamlit app for incremental migration:

```python
# In app.py (Streamlit)
from backend.app.core.analysis import StockAnalyzer
from backend.app.database.repositories import StockRepository

# Use the new modules
analyzer = StockAnalyzer(api_key=st.secrets["GEMINI_API_KEY"])
stocks = analyzer.analyze_transcript(transcript, speaker, source_type)
```

This allows zero-downtime migration.

## Support

For issues or questions about the architecture migration, refer to:
- `PHASE1_COMPLETE.md`: Core extraction documentation
- API Documentation: http://localhost:8000/docs
- Source code comments (all modules heavily documented)

## Critical Note

This application is vital for family financial security (client has MS). All analysis logic has been preserved exactly from the original Streamlit application to prevent regressions. The FIDUCIARY_ANALYST_PROMPT, Gomes Rules framework, and database models remain identical in behavior.
