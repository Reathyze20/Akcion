# AKCION - Investment Analysis Platform

**Trading Intelligence pro kritická investiční rozhodnutí**

---

## 📋 Přehled

Akcion je fiduciární investiční platforma využívající AI (Google Gemini) k extrakci akciových zmínek z transkriptů podle pravidel "The Gomes Rules". Aplikace podporuje kritická rodinná finanční rozhodnutí.

### Klíčové funkce

- **Universal Intelligence Unit** - Multi-source analýza (Official Filings 100%, Chat Discussion 30%, Analyst Reports 60%)
- **AI Analýza** - Gemini 2.0 Flash s Deep Due Diligence
- **Logical Validation** - Automatická detekce chyb (Score 9+ vyžaduje Catalyst)
- **The Gomes Rules** - Information Arbitrage, Catalysts, Risk Assessment
- **Fiduciární standard** - Agresivní extrakce se scoring systémem 1-10
- **Multi-Portfolio** - Správa portfolií pro více majitelů
- **Multi-Broker** - Import z Degiro, Trading212, XTB
- **Kelly Allocator** - Doporučení velikosti pozice podle skóre

### Technologie

| Vrstva | Technologie |
|--------|-------------|
| Frontend | React 18, TypeScript, Vite, Tailwind CSS |
| Backend | FastAPI, Python 3.12, SQLAlchemy 2.0 |
| Databáze | PostgreSQL (Neon.tech) |
| AI | Google Gemini 2.0 Flash Exp |
| Market Data | DB + Deep DD Analysis |

---

## 🚀 Quick Start

### Požadavky

- Python 3.12+
- Node.js 18+
- PostgreSQL účet (Neon.tech)
- Gemini API Key

### 1. Backend

```powershell
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Konfigurace (.env)
copy .env.example .env
# Upravte .env s vašimi credentials

# Spuštění
python start.py
```

Backend: **http://localhost:8000**  
API Docs: **http://localhost:8000/docs**

### 2. Frontend

```powershell
cd frontend
npm install
npm run dev
```

Frontend: **http://localhost:5173**

---

## 📁 Struktura projektu

```
Akcion/
├── backend/
│   ├── app/
│   │   ├── config/        # Nastavení (settings.py)
│   │   ├── core/          # Business logika
│   │   │   ├── analysis.py    # StockAnalyzer (Gemini AI)
│   │   │   ├── extractors.py  # YouTube, Google Docs
│   │   │   ├── prompts.py     # Fiduciary Analyst prompt
│   │   │   └── constants.py   # Konstanty
│   │   ├── database/      # DB vrstva
│   │   │   ├── connection.py  # Engine, session factory
│   │   │   └── repositories.py # CRUD operace
│   │   ├── models/        # SQLAlchemy modely
│   │   │   ├── stock.py       # Stock model
│   │   │   ├── portfolio.py   # Portfolio, Position
│   │   │   ├── analysis.py    # AnalyzedStock
│   │   │   └── trading.py     # Trading signals
│   │   ├── routes/        # API endpointy
│   │   │   ├── analysis.py    # /api/analyze/*
│   │   │   ├── stocks.py      # /api/stocks/*
│   │   │   ├── portfolio.py   # /api/portfolio/*
│   │   │   └── gap_analysis.py
│   │   ├── schemas/       # Pydantic modely
│   │   │   ├── requests.py
│   │   │   └── responses.py
│   │   ├── services/      # Business services
│   │   └── main.py        # FastAPI app
│   ├── tests/             # Testy
│   ├── .env               # Konfigurace
│   └── requirements.txt
│
├── frontend/
│   ├── src/
│   │   ├── api/           # API klient (Axios)
│   │   ├── components/    # React komponenty
│   │   │   ├── Sidebar.tsx
│   │   │   ├── AnalysisView.tsx
│   │   │   ├── PortfolioView.tsx
│   │   │   ├── StockCard.tsx
│   │   │   └── StockDetail.tsx
│   │   ├── context/       # State management
│   │   ├── types/         # TypeScript typy
│   │   └── App.tsx
│   └── package.json
│
└── README.md              # Tento soubor
```

---

## 🔌 API Endpointy

### Analýza

| Endpoint | Popis |
|----------|-------|
| `POST /api/analyze/text` | Analyzuj raw transkript |
| `POST /api/analyze/youtube` | Analyzuj YouTube video |
| `POST /api/analyze/google-docs` | Analyzuj Google Doc |

### Portfolio

| Endpoint | Popis |
|----------|-------|
| `GET /api/stocks` | Všechny akcie (s filtry) |
| `GET /api/stocks/high-conviction` | High-conviction (score ≥7) |
| `GET /api/stocks/{ticker}` | Konkrétní akcie |
| `GET /api/stocks/{ticker}/history` | Historie tickeru |

### Portfolio Management

| Endpoint | Popis |
|----------|-------|
| `POST /api/portfolio/create` | Vytvořit portfolio |
| `GET /api/portfolio/list` | Seznam portfolií |
| `POST /api/portfolio/upload-csv` | Import CSV |
| `POST /api/portfolio/refresh` | Refresh cen |

---

## 🏗️ Architektura

```
┌─────────────────────────────────────────┐
│         Frontend (React)                │
│  - UI Components, State Management      │
└──────────────┬──────────────────────────┘
               │ HTTP REST API
┌──────────────▼──────────────────────────┐
│         Backend (FastAPI)               │
│  - Routes, Schemas, Validation          │
└──────────────┬──────────────────────────┘
               │ Function Calls
┌──────────────▼──────────────────────────┐
│         Core (Pure Python)              │
│  - AI Prompts, Analysis, Extractors     │
│  - Database Models & Repositories       │
└──────────────┬──────────────────────────┘
               │ SQL
┌──────────────▼──────────────────────────┘
│         PostgreSQL (Neon.tech)          │
└─────────────────────────────────────────┘
```

### Principy

- **Separation of Concerns** - UI, API, business logika izolované
- **Repository Pattern** - Čistá data access vrstva
- **Type Safety** - TypeScript + Pydantic + Python type hints
- **Clean Code** - SRP, meaningful names, logging

---

## 🎨 UI Design

**Bloomberg Terminal Aesthetic:**
- Dark theme: `#0E1117` background, `#2962FF` accent
- Sentiment barvy: 🟢 Bullish (#00E676), 🔴 Bearish (#FF5252)
- Grid layout s kompaktními kartami

**Views:**
1. **Analysis** - Input form pro transkripty
2. **Portfolio** - Grid akcií s filtry
3. **Stock Detail** - Modal s plnou analýzou

---

## 📊 Datový model

```sql
-- Hlavní tabulky
stocks          -- AI analýzy z transkriptů
portfolios      -- Portfolia (majitel, broker)
positions       -- Akciové pozice
analyzed_stocks -- Detailní analýzy

-- Klíčová pole v stocks
ticker, company_name, sentiment, gomes_score,
conviction_score, action_verdict, entry_zone,
price_target, stop_loss, edge, catalysts, risks
```

---

## ⚙️ Konfigurace

### Backend (.env)

```env
DATABASE_URL=postgresql://user:pass@host/db
GEMINI_API_KEY=your_key
MASSIVE_API_KEY=your_key
CORS_ORIGINS=http://localhost:5173
DEBUG=True
```

### Frontend (.env)

```env
VITE_API_URL=http://localhost:8000
```

---

## 🔧 Vývoj

### Spuštění testů

```powershell
cd backend
python -m pytest tests/
```

### Kontrola kódu

```powershell
# Backend
python -c "from app.core import *; from app.models import *; print('OK')"

# Frontend
cd frontend
npm run build
```

### Databázové migrace

SQL skripty v `backend/migrations/`:
- `add_analysis_tables.sql`
- `add_trading_tables.sql`

---

## 📈 Statistiky projektu

| Metrika | Hodnota |
|---------|---------|
| Backend souborů | 45 |
| Frontend souborů | 24 |
| Celkem řádků | ~15,000 |
| API endpointů | 15+ |

---

## 📝 Changelog

### Leden 2026

#### 🆕 Universal Intelligence Unit (25.1.2026)
- ✅ Multi-source prompt s auto-detekci typu vstupu
- ✅ Source-specific logic: Official (100%), Chat (30%), Analyst (60%)
- ✅ Nested JSON structure s meta_info, inflection_updates, financial_updates
- ✅ Context-aware extraction (Chat → sentiment/rumors, Official → hard numbers)

#### 🛡️ Logical Validation System (25.1.2026)
- ✅ Backend validace: Score 9+ vyžaduje konkrétní Catalyst
- ✅ Žluté varování ve frontendu při logické chybě
- ✅ Ochrana před AI blind spots (domýšlení burzovního kalendáře)

#### 🎨 UI Improvements
- ✅ Trading Deck větší fonty (text-xs místo text-[9px])
- ✅ + ANALÝZA tlačítko přesunuto do header
- ✅ Trading Deck Legend (3-column vysvětlivky)
- ✅ Gomes Guardian Intelligence Unit modal

#### 🧹 Clean Code Refactoring
- ✅ Přechod na `from __future__ import annotations`
- ✅ Type hints: `str | None` místo `Optional[str]`
- ✅ Logging místo print()
- ✅ Centralizované konstanty
- ✅ Čištění projektové struktury

---

## 📄 Licence

Proprietární - pouze pro interní použití.
