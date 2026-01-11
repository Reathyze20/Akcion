# 🎯 AKCION - Investment Analysis Platform

**Three-Tier Architecture**  
React Frontend → FastAPI Backend → Core Business Logic

## Overview

Akcion is a fiduciary-grade investment analysis platform that uses AI (Google Gemini) to extract stock mentions and insights from transcripts, applying "The Gomes Rules" framework. This application supports critical family financial decisions.

### Key Features

- **AI-Powered Analysis**: Gemini 3 Pro with Google Search integration
- **The Gomes Rules**: Information Arbitrage, Catalysts, Risk Assessment
- **Fiduciary Standard**: Aggressive extraction with 1-10 scoring system
- **Historical Tracking**: PostgreSQL database for sentiment analysis over time
- **Premium UI**: Bloomberg Terminal-inspired dark fintech aesthetic

---

## 🚀 Quick Start

### Prerequisites

- **Python 3.14+**
- **Node.js 18+**
- **PostgreSQL** (Neon.tech)
- **Gemini API Key**

### 1. Backend Setup

```powershell
cd backend

# Install dependencies
pip install -r requirements.txt

# Configure environment (edit .env with your credentials)
copy .env.example .env

# Start FastAPI server
python start.py
```

Backend runs at: **http://localhost:8000**  
API Docs: **http://localhost:8000/docs**

### 2. Frontend Setup

```powershell
cd frontend

# Install dependencies
npm install

# Configure environment
copy .env.example .env

# Start React dev server
npm run dev
```

Frontend runs at: **http://localhost:5173**

### 3. Use the Application

1. Open **http://localhost:5173**
2. Enter speaker name (e.g., "Mark Gomes")
3. Choose input type:
   - **Text**: Paste transcript directly
   - **YouTube**: Paste video URL
   - **Google Docs**: Paste document URL
4. Click **Analyze** to extract stocks
5. View results in **Portfolio** tab

---

## 📁 Project Structure

```
Akcion/
├── backend/                  # FastAPI Backend
│   ├── app/
│   │   ├── core/            # Business logic (AI, extractors)
│   │   ├── models/          # SQLAlchemy models
│   │   ├── database/        # DB connection, repositories
│   │   ├── routes/          # API endpoints
│   │   ├── schemas/         # Pydantic models
│   │   ├── config/          # Settings management
│   │   └── main.py          # FastAPI app
│   ├── tests/               # Test suite
│   ├── requirements.txt     # Python dependencies
│   ├── .env                 # Environment config
│   ├── start.py             # Startup script
│   └── README.md            # Backend docs
│
├── frontend/                # React Frontend
│   ├── src/
│   │   ├── api/            # API client
│   │   ├── components/     # React components
│   │   ├── context/        # State management
│   │   ├── types/          # TypeScript types
│   │   ├── App.tsx         # Root component
│   │   └── index.css       # Tailwind styles
│   ├── public/             # Static assets
│   ├── .env                # Environment config
│   ├── package.json        # Dependencies
│   └── README.md           # Frontend docs
│
├── app.py                   # Original Streamlit app (still works!)
├── .streamlit/secrets.toml  # Streamlit secrets
├── PHASE1_COMPLETE.md       # Core extraction docs
├── PHASE2_AND_3_COMPLETE.md # Migration completion docs
└── README.md                # This file
```

---

## 🏗️ Architecture

### Three-Tier Design

```
┌─────────────────────────────────────────┐
│         Frontend (React)                │
│  - UI Components                        │
│  - State Management (Context)           │
│  - API Client (Axios)                   │
└──────────────┬──────────────────────────┘
               │ HTTP REST API
┌──────────────▼──────────────────────────┐
│         Backend (FastAPI)               │
│  - REST API Endpoints                   │
│  - Request Validation (Pydantic)        │
│  - Error Handling & CORS                │
└──────────────┬──────────────────────────┘
               │ Function Calls
┌──────────────▼──────────────────────────┐
│         Core (Pure Python)              │
│  - AI Prompts (Fiduciary Analyst)       │
│  - Stock Analysis (Gemini)              │
│  - Data Extractors (YouTube, Docs)      │
│  - Database Models & Repositories       │
└─────────────────────────────────────────┘
```

### Key Benefits

✅ **Separation of Concerns**: UI, API, business logic are isolated  
✅ **Scalability**: Each tier can scale independently  
✅ **Testability**: Core logic testable without UI/API  
✅ **Maintainability**: Changes to one tier don't break others  
✅ **Flexibility**: Can add mobile app, CLI, etc. using same backend

---

## 🎨 UI Design

### Bloomberg Terminal Aesthetic

- **Dark Theme**: `#0E1117` background with `#2962FF` electric blue accents
- **Compact Cards**: Grid layout (3 columns) with key metrics
- **Color-Coded Sentiment**:
  - 🟢 Bullish: `#00E676`
  - 🔴 Bearish: `#FF5252`
  - ⚪ Neutral: `#78909C`
- **Typography**: Inter for UI, JetBrains Mono for code
- **Shadows**: Subtle elevation with blue glow on hover

### Views

1. **Analysis View**: Welcome screen with input form
2. **Portfolio View**: Grid of stock cards with filters
3. **Stock Detail Modal**: Full analysis with Gomes Rules breakdown

---

## 📊 API Endpoints

### Analysis

- `POST /api/analyze/text` - Analyze raw transcript
- `POST /api/analyze/youtube` - Fetch & analyze YouTube video
- `POST /api/analyze/google-docs` - Fetch & analyze Google Doc

### Portfolio

- `GET /api/stocks` - Get all stocks (with filters)
- `GET /api/stocks/high-conviction` - High-conviction picks (score >= 7)
- `GET /api/stocks/{ticker}` - Get specific stock
- `GET /api/stocks/{ticker}/history` - Get ticker history
- `GET /api/stocks/stats/summary` - Portfolio statistics

### Health

- `GET /health` - System health check
- `GET /` - API root with feature list

Full API docs: **http://localhost:8000/docs**

---

## 🔐 Environment Configuration

### Backend `.env`

```bash
DATABASE_URL=postgresql://user:pass@host/db?sslmode=require
GEMINI_API_KEY=your_api_key_here
CORS_ORIGINS=http://localhost:5173,http://localhost:3000
APP_NAME=Akcion Investment Analysis API
DEBUG=True
```

### Frontend `.env`

```bash
VITE_API_URL=http://localhost:8000
```

---

## 🧪 Testing

### Backend Tests

```powershell
cd backend

# Core logic verification
python tests/test_phase1_extraction.py

# API endpoint tests (future)
pytest tests/
```

### Frontend Type Checking

```powershell
cd frontend
npm run type-check
```

---

## 🚢 Production Deployment

### Backend Deployment

**Recommended Platforms:**
- Railway
- Render
- AWS ECS
- Google Cloud Run

**Steps:**
1. Build Docker image or use Python buildpack
2. Set environment variables
3. Deploy with auto-scaling
4. Point domain to backend URL

### Frontend Deployment

**Recommended Platforms:**
- Vercel (recommended for Vite)
- Netlify
- AWS S3 + CloudFront

**Steps:**
```powershell
cd frontend
npm run build
# Deploy dist/ folder
```

Set `VITE_API_URL` to your production backend URL.

### Database

Already on **Neon.tech** (production-ready PostgreSQL).

---

## 🔄 Migration from Streamlit

The original **app.py** (Streamlit) still works! You can:

1. **Run in Parallel**: Keep Streamlit for internal use
2. **Incremental Migration**: Gradually move users to React
3. **Import Backend Modules**: Streamlit can import from `backend/app/`

Example:
```python
# In app.py (Streamlit)
from backend.app.core.analysis import StockAnalyzer

analyzer = StockAnalyzer(api_key=st.secrets["GEMINI_API_KEY"])
stocks = analyzer.analyze_transcript(transcript, speaker, source_type)
```

This allows **zero-downtime migration**.

---

## 📚 Documentation

- **Backend API**: http://localhost:8000/docs
- **Backend README**: [backend/README.md](backend/README.md )
- **Frontend README**: [frontend/README.md](frontend/README.md )
- **Phase 1 Complete**: [backend/PHASE1_COMPLETE.md](backend/PHASE1_COMPLETE.md )
- **Phase 2 & 3 Complete**: [PHASE2_AND_3_COMPLETE.md](PHASE2_AND_3_COMPLETE.md )

---

## 🛠️ Technology Stack

### Backend
- **FastAPI**: Modern async web framework
- **SQLAlchemy**: ORM for PostgreSQL
- **Pydantic**: Data validation
- **Google Generative AI**: Gemini 3 Pro
- **Uvicorn**: ASGI server

### Frontend
- **React 18**: UI library
- **TypeScript**: Type safety
- **Vite 7**: Build tool
- **Tailwind CSS 3**: Utility-first styling
- **Axios**: HTTP client

### Database
- **PostgreSQL**: Relational database (Neon.tech)
- **Psycopg2**: PostgreSQL adapter

---

## 🎯 Critical Business Logic

### FIDUCIARY_ANALYST_PROMPT

The system uses a specialized AI prompt:

> "You are a Fiduciary Senior Financial Analyst acting as a guardian for a client with Multiple Sclerosis. This is not academic - your analysis directly impacts their family's financial security. AGGRESSIVE EXTRACTION: You MUST extract EVERY stock mentioned..."

### The Gomes Rules

1. **Information Arbitrage (Edge)**: What unique insight justifies this position?
2. **Catalysts**: What specific events will drive stock movement?
3. **Risk Assessment**: What could go wrong?

### Scoring System

- **Gomes Score (1-10)**: Overall opportunity quality
- **Conviction Score (1-10)**: Analyst's confidence level

### Data Preservation

All 15 Stock model fields:
- id, created_at, ticker, company_name
- source_type, speaker, sentiment
- gomes_score, conviction_score
- price_target, time_horizon
- edge, catalysts, risks, raw_notes

**100% of original functionality preserved.**

---

## ⚠️ Critical Notes

1. **Family Financial Security**: This application supports critical financial decisions for a client with MS. All features maintain the reliability and accuracy standards of the original system.

2. **Zero Functionality Loss**: The migration preserves the exact AI prompts, scoring system, and Gomes Rules framework from the original Streamlit application.

3. **Backend Dependency**: The frontend requires the FastAPI backend to be running.

---

## 🐛 Troubleshooting

### Backend Won't Start

```powershell
# Check Python version
python --version  # Should be 3.14+

# Verify dependencies
cd backend
pip install -r requirements.txt

# Check environment variables
cat .env  # or type .env on Windows

# Test database connection
python -c "from app.database.connection import is_connected; print(is_connected())"
```

### Frontend Won't Start

```powershell
# Check Node version
node --version  # Should be 18+

# Clear cache and reinstall
cd frontend
rm -rf node_modules package-lock.json
npm install

# Check environment variables
cat .env  # or type .env on Windows
```

### API Connection Issues

1. Verify backend is running: http://localhost:8000/health
2. Check CORS settings in `backend/.env`
3. Check API URL in `frontend/.env`
4. Open browser dev tools → Network tab → Check for errors

---

## 📈 Future Enhancements

- [ ] Authentication & user accounts
- [ ] Real-time stock price data integration
- [ ] Alerts & notifications
- [ ] Export to PDF/Excel
- [ ] Mobile app (React Native)
- [ ] Advanced charting & analytics
- [ ] Multi-language support

---

## 📄 License

Proprietary - Family financial security application

---

## 🙏 Acknowledgments

Built with care for family financial security. This system maintains the fiduciary standard that protects important financial decisions for a client with Multiple Sclerosis.

---

## 📞 Support

For issues or questions:
- Check documentation in `backend/` and `frontend/` folders
- Review API docs: http://localhost:8000/docs
- Check migration docs: PHASE2_AND_3_COMPLETE.md

---

**✨ The Akcion Investment Analysis Platform is now a modern, scalable, three-tier application while maintaining the exact same fiduciary-grade analysis that supports your family's financial security.**

**Status: Phase 1, 2, and 3 Complete** 🎉
