# 🏗️ Akcion Architecture Diagram

## Three-Tier Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                         USER BROWSER                                 │
│                     http://localhost:5173                            │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
                                │ HTTP (REST API)
                                │ JSON Requests/Responses
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         TIER 1: FRONTEND                             │
│                      React + TypeScript + Tailwind                   │
│                                                                      │
│  ┌────────────────┐  ┌────────────────┐  ┌─────────────────────┐  │
│  │  Sidebar.tsx   │  │ AnalysisView   │  │  PortfolioView      │  │
│  │  - Navigation  │  │ - Welcome      │  │  - Stock Grid       │  │
│  │  - Input Form  │  │ - Instructions │  │  - Filters          │  │
│  └────────────────┘  └────────────────┘  └─────────────────────┘  │
│                                                                      │
│  ┌────────────────┐  ┌────────────────┐  ┌─────────────────────┐  │
│  │ StockCard.tsx  │  │ StockDetail    │  │  API Client         │  │
│  │ - Compact Card │  │ - Full Modal   │  │  - Axios HTTP       │  │
│  │ - Bloomberg    │  │ - Gomes Rules  │  │  - Type Safety      │  │
│  └────────────────┘  └────────────────┘  └─────────────────────┘  │
│                                                                      │
│  State: React Context (currentView, stocks, filters, loading)       │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
                                │ axios.post('/api/analyze/text')
                                │ axios.get('/api/stocks')
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         TIER 2: BACKEND                              │
│                        FastAPI + Uvicorn                             │
│                     http://localhost:8000                            │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────┐    │
│  │                        main.py                              │    │
│  │  - FastAPI App Instance                                     │    │
│  │  - CORS Middleware (allow React dev server)                │    │
│  │  - Error Handlers (validation, global)                     │    │
│  │  - Lifecycle (startup: DB init, shutdown: cleanup)         │    │
│  └────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────┐    │
│  │                    routes/analysis.py                       │    │
│  │  POST /api/analyze/text        - Analyze raw transcript    │    │
│  │  POST /api/analyze/youtube     - YouTube video analysis    │    │
│  │  POST /api/analyze/google-docs - Google Docs analysis      │    │
│  │  GET  /api/analyze/health      - Service health check      │    │
│  └────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────┐    │
│  │                     routes/stocks.py                        │    │
│  │  GET /api/stocks                    - Get all with filters │    │
│  │  GET /api/stocks/high-conviction    - High conviction (7+) │    │
│  │  GET /api/stocks/{ticker}           - Get specific stock   │    │
│  │  GET /api/stocks/{ticker}/history   - Ticker history       │    │
│  │  GET /api/stocks/stats/summary      - Portfolio stats      │    │
│  └────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  ┌──────────────────┐  ┌──────────────────┐  ┌─────────────────┐  │
│  │ schemas/         │  │ config/          │  │ Dependency      │  │
│  │ - requests.py    │  │ - settings.py    │  │ Injection:      │  │
│  │ - responses.py   │  │ - Pydantic       │  │ - get_db()      │  │
│  └──────────────────┘  └──────────────────┘  └─────────────────┘  │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
                                │ analyzer.analyze_transcript()
                                │ repository.create_stocks()
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         TIER 3: CORE                                 │
│                      Pure Python Business Logic                      │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────┐    │
│  │                    core/prompts.py                          │    │
│  │  - FIDUCIARY_ANALYST_PROMPT (MS client context)            │    │
│  │  - AGGRESSIVE EXTRACTION rules                             │    │
│  │  - The Gomes Rules (Information Arbitrage, Catalysts)      │    │
│  │  - GOOGLE_SEARCH_CONFIG                                    │    │
│  │  - GEMINI_MODEL_NAME (gemini-3-pro-preview)               │    │
│  └────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────┐    │
│  │                    core/analysis.py                         │    │
│  │  Class: StockAnalyzer                                       │    │
│  │    - analyze_transcript(transcript, speaker, source)       │    │
│  │    - Gemini AI integration                                 │    │
│  │    - JSON response parsing & cleaning                      │    │
│  │    - Error handling                                        │    │
│  └────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────┐    │
│  │                   core/extractors.py                        │    │
│  │  - extract_video_id(url)        - YouTube URL parser       │    │
│  │  - get_youtube_transcript(id)   - Fetch transcript         │    │
│  │  - extract_google_doc_id(url)   - Google Docs parser       │    │
│  │  - get_google_doc_content(id)   - Fetch document          │    │
│  └────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────┐    │
│  │                    models/stock.py                          │    │
│  │  SQLAlchemy Model: Stock                                    │    │
│  │    - 15 fields (id, ticker, sentiment, gomes_score, etc.)  │    │
│  │    - to_dict() method for API responses                    │    │
│  └────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────┐    │
│  │                  database/connection.py                     │    │
│  │  - initialize_database() - Create engine/session factory   │    │
│  │  - get_engine() - Singleton engine                         │    │
│  │  - get_session() - Session factory                         │    │
│  │  - get_db() - FastAPI dependency for sessions              │    │
│  │  - is_connected() - Health check                           │    │
│  └────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────┐    │
│  │                 database/repositories.py                    │    │
│  │  Class: StockRepository                                     │    │
│  │    - create_stocks(stocks_data) - Bulk insert              │    │
│  │    - get_all_stocks() - Retrieve all                       │    │
│  │    - get_stock_by_ticker(ticker) - Get most recent         │    │
│  │    - get_ticker_history(ticker) - Historical analyses      │    │
│  │    - get_stocks_by_sentiment(sentiment) - Filter           │    │
│  │    - get_high_conviction_stocks() - Score >= 7             │    │
│  └────────────────────────────────────────────────────────────┘    │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
                                │ SQL Queries
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         DATABASE LAYER                               │
│                   PostgreSQL on Neon.tech                            │
│                                                                      │
│  Table: stocks                                                       │
│  ┌──────────────────────────────────────────────────────────┐      │
│  │ id               INTEGER PRIMARY KEY                      │      │
│  │ created_at       TIMESTAMP DEFAULT NOW()                 │      │
│  │ ticker           VARCHAR(20) NOT NULL                    │      │
│  │ company_name     VARCHAR(200)                            │      │
│  │ source_type      VARCHAR(50)                             │      │
│  │ speaker          VARCHAR(200)                            │      │
│  │ sentiment        VARCHAR(50)                             │      │
│  │ gomes_score      INTEGER                                 │      │
│  │ conviction_score INTEGER                                 │      │
│  │ price_target     TEXT                                    │      │
│  │ time_horizon     VARCHAR(100)                            │      │
│  │ edge             TEXT  -- Information Arbitrage          │      │
│  │ catalysts        TEXT                                    │      │
│  │ risks            TEXT                                    │      │
│  │ raw_notes        TEXT                                    │      │
│  └──────────────────────────────────────────────────────────┘      │
│                                                                      │
│  Current Data: 10 stocks from Mark Gomes analysis                   │
└─────────────────────────────────────────────────────────────────────┘
                                │
                                │ API Calls
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      EXTERNAL SERVICES                               │
│                                                                      │
│  ┌──────────────────┐  ┌──────────────────┐  ┌─────────────────┐  │
│  │ Google Gemini    │  │ YouTube          │  │ Google Docs     │  │
│  │ - gemini-3-pro   │  │ - Transcript API │  │ - Docs API      │  │
│  │ - Google Search  │  │                  │  │                 │  │
│  └──────────────────┘  └──────────────────┘  └─────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Data Flow Example: Analyzing a YouTube Video

```
1. USER ACTION
   ↓
   User enters YouTube URL in Sidebar
   Clicks "Analyze" button

2. FRONTEND (React)
   ↓
   Sidebar.tsx calls: apiClient.analyzeYouTube({ url, speaker })
   Sets loading state: setIsLoading(true)

3. API REQUEST
   ↓
   Axios POST http://localhost:8000/api/analyze/youtube
   Body: { "url": "https://...", "speaker": "Mark Gomes" }

4. BACKEND (FastAPI)
   ↓
   routes/analysis.py → analyze_youtube() endpoint
   Validates request with AnalyzeYouTubeRequest schema
   Injects database session via get_db()

5. CORE LOGIC - EXTRACTION
   ↓
   core/extractors.py → extract_video_id(url)
   Returns: "dQw4w9WgXcQ"
   
   core/extractors.py → get_youtube_transcript(video_id)
   Calls: youtube_transcript_api
   Returns: Full transcript text

6. CORE LOGIC - AI ANALYSIS
   ↓
   core/analysis.py → StockAnalyzer.analyze_transcript()
   
   Uses: FIDUCIARY_ANALYST_PROMPT from core/prompts.py
   Calls: Gemini API with gemini-3-pro-preview model
   Includes: Google Search tool for real-time data
   
   AI extracts stocks with:
   - Ticker, company name, sentiment
   - Gomes Score (1-10), Conviction Score (1-10)
   - Information Arbitrage (Edge)
   - Catalysts, Risks, Price Target
   
   Returns: List of stock dictionaries

7. DATABASE PERSISTENCE
   ↓
   database/repositories.py → StockRepository.create_stocks()
   
   Converts dictionaries to Stock SQLAlchemy models
   Bulk inserts to PostgreSQL via session.add_all()
   Commits transaction
   
   Returns: List of saved Stock models

8. API RESPONSE
   ↓
   routes/analysis.py wraps result in AnalysisResponse schema
   Returns JSON: {
     "success": true,
     "message": "Found 3 stock mentions",
     "stocks_found": 3,
     "stocks": [{ ...StockResponse... }]
   }

9. FRONTEND UPDATE
   ↓
   apiClient receives response
   Sidebar.tsx updates state: setStocks([...newStocks, ...existing])
   Sets loading: setIsLoading(false)
   Shows alert: "✅ Successfully analyzed"
   Navigates to: Portfolio view

10. UI RENDER
    ↓
    PortfolioView.tsx renders stock grid
    Each StockCard.tsx displays:
    - Ticker, sentiment badge
    - Gomes Score, Conviction Score
    - Catalysts preview
    
    User clicks card → StockDetail.tsx modal opens
    Shows full analysis with Gomes Rules breakdown
```

---

## Key Design Principles

### 1. Separation of Concerns
- **Frontend**: UI/UX only, no business logic
- **Backend**: API orchestration, validation, error handling
- **Core**: Pure business logic, framework-agnostic

### 2. Dependency Direction
```
Frontend → Backend → Core → Database
         → External APIs (Gemini, YouTube, Docs)
```

Core never depends on Backend or Frontend.
Backend never depends on Frontend.

### 3. Type Safety
- **Frontend**: TypeScript interfaces match backend schemas
- **Backend**: Pydantic models enforce request/response structure
- **Core**: Python type hints throughout

### 4. Error Propagation
```
Core raises Exception
  ↓
Backend catches, wraps in HTTPException
  ↓
FastAPI returns JSON error response
  ↓
Frontend axios interceptor catches
  ↓
React state updates with error
  ↓
UI shows error toast
```

### 5. State Management
- **Frontend State**: React Context (global)
  - Current view, stock list, filters, loading
- **Backend State**: Stateless (REST principles)
  - Each request is independent
- **Database State**: PostgreSQL (persistent)
  - Historical stock analyses

---

## Scalability Considerations

### Horizontal Scaling
- **Frontend**: Static files → CDN (Vercel, Netlify)
- **Backend**: Multiple FastAPI instances → Load balancer
- **Database**: PostgreSQL read replicas

### Caching
- **API responses**: Redis cache for stock portfolio
- **Static assets**: Browser cache + CDN
- **AI responses**: Cache common queries

### Performance
- **Frontend**: Code splitting, lazy loading
- **Backend**: Async operations, connection pooling
- **Database**: Indexes on ticker, created_at, sentiment

---

## Security Architecture

### Frontend
- **Environment variables**: API URL only
- **No secrets**: All auth handled by backend
- **HTTPS**: Required in production

### Backend
- **API key**: Gemini key in environment variable
- **CORS**: Restricted to frontend domain
- **Input validation**: Pydantic schemas
- **Error handling**: No sensitive data in errors

### Database
- **Connection string**: In environment variable
- **SSL mode**: Required for Neon.tech
- **No direct access**: Only through backend

---

## Monitoring & Observability

### Health Checks
- **Frontend**: Dev server status
- **Backend**: `/health` endpoint checks DB + Gemini
- **Database**: `is_connected()` function

### Logging
- **Frontend**: Console logs + error boundaries
- **Backend**: Uvicorn access logs + app logs
- **Database**: PostgreSQL logs on Neon dashboard

### Metrics (Future)
- API response times
- Success/error rates
- Stock analysis volume
- User engagement

---

**This architecture ensures reliability, maintainability, and scalability while preserving the critical business logic that supports family financial security.**
