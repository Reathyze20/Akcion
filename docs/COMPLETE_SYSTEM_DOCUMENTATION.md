# 📚 AKCION - Complete System Documentation

## Trading Intelligence Module for Critical Investment Decisions

**Verze:** 2.0.0  
**Poslední aktualizace:** Leden 2026  
**Autor:** GitHub Copilot s Claude Opus 4.5

---

## 📋 Obsah

1. [Úvod a Mise](#1-úvod-a-mise)
2. [Architektura Systému](#2-architektura-systému)
3. [Tech Stack](#3-tech-stack)
4. [Backend - Detailní Popis](#4-backend---detailní-popis)
5. [Frontend - Komponenty](#5-frontend---komponenty)
6. [Gomes Metodologie](#6-gomes-metodologie)
7. [Master Signal v2.0](#7-master-signal-v20)
8. [AI Analýza](#8-ai-analýza)
9. [Databázové Modely](#9-databázové-modely)
10. [API Reference](#10-api-reference)
11. [Services Layer](#11-services-layer)
12. [Konfigurace a Deployment](#12-konfigurace-a-deployment)
13. [Testování](#13-testování)
14. [Bezpečnostní Pravidla](#14-bezpečnostní-pravidla)
15. [Slovník Pojmů](#15-slovník-pojmů)

---

## 1. Úvod a Mise

### 1.1 Co je Akcion?

**Akcion** je fiduciární investiční platforma navržená pro kritická rodinná finanční rozhodnutí. Kombinuje:

- 🧠 **Lidskou analýzu** - Transkripty z videí investorů (Mark Gomes / Money Mark)
- 🤖 **AI predikce** - Google Gemini 2.0 Flash s Deep Due Diligence
- 📊 **Tvrdá data** - Fundamentální a technické ukazatele

### 1.2 Klíčová Mise

> **CRITICAL MISSION**: Family financial security depends on accurate analysis.

Systém je navržen s vědomím, že každá chyba může mít reálné finanční dopady. Proto je kladen důraz na:

- ✅ **Robustnost** - Maximální odolnost vůči chybám
- ✅ **Transparentnost** - Jasné zdůvodnění každého doporučení
- ✅ **Konzervativnost** - Raději zmeškat příležitost než ztratit kapitál
- ✅ **Auditovatelnost** - Kompletní historie rozhodnutí

### 1.3 Filozofie "The Gomes Way"

Systém je postaven na investiční filozofii Marka Gomese (Money Mark):

1. **Information Arbitrage** - Co ví člověk, co trh neví?
2. **Catalyst Focus** - Žádná investice bez jasného katalyzátoru
3. **Risk Management** - Green/Red line systém + position sizing
4. **Lifecycle Awareness** - Rozpoznání fáze životního cyklu akcie

---

## 2. Architektura Systému

### 2.1 High-Level Architektura

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           FRONTEND (React 18)                                │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐          │
│  │ Gomes Guardian   │  │ Portfolio View   │  │ Action Center    │          │
│  │ Dashboard        │  │                  │  │                  │          │
│  └──────────────────┘  └──────────────────┘  └──────────────────┘          │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                              FastAPI REST API
                                      │
┌─────────────────────────────────────────────────────────────────────────────┐
│                           BACKEND (Python 3.12)                              │
│                                                                              │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                      MASTER SIGNAL v2.0 (3 Pillars)                   │  │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐       │  │
│  │  │ Thesis Tracker  │  │ Valuation &     │  │ Weinstein       │       │  │
│  │  │     (60%)       │  │ Cash (25%)      │  │ Guard (15%)     │       │  │
│  │  └─────────────────┘  └─────────────────┘  └─────────────────┘       │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐                │
│  │ Gomes Intel    │  │ Investment     │  │ Kelly          │                │
│  │ Service        │  │ Engine         │  │ Allocator      │                │
│  └────────────────┘  └────────────────┘  └────────────────┘                │
│                                                                              │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐                │
│  │ AI Analysis    │  │ Gap Analysis   │  │ Notifications  │                │
│  │ (Gemini)       │  │ Service        │  │ Service        │                │
│  └────────────────┘  └────────────────┘  └────────────────┘                │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
┌─────────────────────────────────────────────────────────────────────────────┐
│                    DATABASE (PostgreSQL + Neon.tech)                         │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐                │
│  │ Stocks         │  │ Portfolios     │  │ Trading        │                │
│  │ + Analysis     │  │ + Positions    │  │ Signals        │                │
│  └────────────────┘  └────────────────┘  └────────────────┘                │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Tok Dat

```
1. INPUT (Zdroje dat)
   ├── YouTube Transkripty → Extractor
   ├── Google Docs → Extractor  
   ├── Manual Input → Direct
   └── Yahoo Finance → Cache Service

2. PROCESSING (Zpracování)
   ├── Gemini AI → Stock Extraction + Scoring
   ├── Gomes Logic → Validation + Rules
   └── Master Signal → Aggregation

3. OUTPUT (Výstupy)
   ├── API Response → Frontend
   ├── Notifications → Telegram/Email
   └── Database → Persistence
```

---

## 3. Tech Stack

### 3.1 Backend

| Technologie | Verze | Účel |
|-------------|-------|------|
| **Python** | 3.12 | Hlavní jazyk |
| **FastAPI** | Latest | REST API framework |
| **SQLAlchemy** | 2.0 | ORM |
| **Pydantic** | 2.x | Validace dat |
| **Google Generative AI** | Latest | Gemini AI |
| **Uvicorn** | Latest | ASGI server |
| **PostgreSQL** | 15+ | Databáze (Neon.tech) |

### 3.2 Frontend

| Technologie | Verze | Účel |
|-------------|-------|------|
| **React** | 18 | UI framework |
| **TypeScript** | 5.x | Type safety |
| **Vite** | Latest | Build tool |
| **Tailwind CSS** | 3.x | Styling |
| **Lucide Icons** | Latest | Ikony |

### 3.3 Infrastruktura

| Služba | Účel |
|--------|------|
| **Neon.tech** | Managed PostgreSQL (cloud) |
| **Google Cloud** | Gemini API |
| **Telegram** | Notifikace |
| **Gmail SMTP** | Email alerty |

---

## 4. Backend - Detailní Popis

### 4.1 Struktura Projektu

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI entry point
│   ├── schemas.py           # Pydantic schemas (legacy)
│   │
│   ├── config/
│   │   ├── __init__.py
│   │   └── settings.py      # Environment configuration
│   │
│   ├── core/
│   │   ├── __init__.py
│   │   ├── analysis.py      # StockAnalyzer (Gemini AI)
│   │   ├── constants.py     # Magic strings, enums
│   │   ├── extractors.py    # YouTube, Google Docs extractors
│   │   ├── gomes_logic.py   # Core Gomes business rules
│   │   ├── market_hours.py  # Trading hours utilities
│   │   ├── prompts.py       # AI system prompts
│   │   ├── prompts_ticker_analysis.py
│   │   └── prompts_universal_intelligence.py
│   │
│   ├── database/
│   │   ├── __init__.py
│   │   ├── connection.py    # SQLAlchemy engine management
│   │   └── repositories.py  # Repository pattern for CRUD
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── base.py          # SQLAlchemy Base
│   │   ├── stock.py         # Stock model (core entity)
│   │   ├── portfolio.py     # Portfolio + Position models
│   │   ├── trading.py       # Trading signals, ML predictions
│   │   ├── gomes.py         # Gomes-specific models
│   │   ├── analysis.py      # AnalyzedStock, SWOT
│   │   └── score_history.py # Score tracking over time
│   │
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── analysis.py      # /api/analyze/*
│   │   ├── stocks.py        # /api/stocks/*
│   │   ├── portfolio.py     # /api/portfolio/*
│   │   ├── trading.py       # /api/trading/*
│   │   ├── master_signal.py # /api/master-signal/*
│   │   ├── gomes.py         # /api/gomes/*
│   │   ├── intelligence.py  # /api/intelligence/*
│   │   ├── gap_analysis.py  # /api/gap-analysis/*
│   │   ├── notifications.py # /api/notifications/*
│   │   ├── investment.py    # /api/investment/*
│   │   ├── yahoo_finance.py # /api/yahoo/*
│   │   └── dev_utils.py     # /api/dev/* (DISABLE IN PROD!)
│   │
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── requests.py      # Request DTOs
│   │   └── responses.py     # Response DTOs
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── alert_scheduler.py     # Background alert monitoring
│   │   ├── currency.py            # Exchange rates
│   │   ├── gap_analysis.py        # Portfolio gap detection
│   │   ├── gomes_ai_analyst.py    # AI-powered Gomes analysis
│   │   ├── gomes_deep_dd.py       # Deep Due Diligence
│   │   ├── gomes_intelligence.py  # Gomes business logic service
│   │   ├── importer.py            # Broker CSV import
│   │   ├── investment_engine.py   # Investment decision engine
│   │   ├── kelly_allocator.py     # Kelly Criterion position sizing
│   │   ├── market_data.py         # Real-time market data
│   │   ├── news_monitor.py        # News and sentiment
│   │   ├── notification_service.py
│   │   ├── notifications.py
│   │   ├── trading_zones.py
│   │   ├── weekly_summary.py
│   │   └── yahoo_cache.py         # Smart Yahoo Finance cache
│   │
│   └── trading/
│       ├── __init__.py
│       ├── master_signal.py       # Master Signal v2.0 aggregator
│       ├── gomes_logic.py         # Gomes Gatekeeper rules
│       ├── gomes_analyzer.py
│       ├── gomes_signals.py
│       ├── kelly.py               # Kelly Criterion calculator
│       ├── signals.py
│       ├── watchlist.py
│       ├── data_fetcher.py
│       └── price_lines_data.py    # Hardcoded price lines from images
│
├── migrations/                    # SQL migration scripts
├── tests/                         # Test suite
├── requirements.txt
└── start.py                       # Startup script
```

### 4.2 Entry Point (main.py)

```python
# Klíčové části main.py

app = FastAPI(
    title="Akcion Investment Analysis API",
    version="2.0.0",
    description="Family financial security depends on accurate analysis."
)

# Startup event - inicializace DB a scheduleru
@app.on_event("startup")
async def startup_event():
    initialize_database(settings.database_url)
    await start_scheduler()  # Background alert monitoring

# Registrace routerů
app.include_router(portfolio.router)
app.include_router(stocks.router)
app.include_router(master_signal.router)
app.include_router(gomes.router)
# ... další routery
```

### 4.3 Configuration (settings.py)

Systém používá Pydantic Settings pro type-safe konfiguraci:

```python
class Settings(BaseSettings):
    # Database
    database_url: str = Field(..., alias="DATABASE_URL")
    
    # AI
    gemini_api_key: str = Field(..., alias="GEMINI_API_KEY")
    
    # Market Data
    massive_api_key: str | None = Field(None, alias="MASSIVE_API_KEY")
    finnhub_api_key: str | None = Field(None, alias="FINNHUB_API_KEY")
    
    # Notifications
    TELEGRAM_BOT_TOKEN: str | None = Field(None)
    TELEGRAM_CHAT_ID: str | None = Field(None)
    EMAIL_RECIPIENT: str | None = Field(None)
```

**Environment Variables (.env):**
```env
DATABASE_URL=postgresql://user:pass@host/db
GEMINI_API_KEY=your_gemini_key
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

---

## 5. Frontend - Komponenty

### 5.1 Hlavní Komponenty

| Komponenta | Soubor | Popis |
|------------|--------|-------|
| **GomesGuardianDashboard** | `GomesGuardianDashboard.tsx` | Hlavní dashboard (~3800 řádků) |
| **StockDetailModalGomes** | `StockDetailModalGomes.tsx` | Detail akcie s 4-panel layoutem |
| **ActionCenter** | `ActionCenter.tsx` | Centrum akcí a signálů |
| **PortfolioView** | `PortfolioView.tsx` | Přehled portfolia |
| **TranscriptImporter** | `TranscriptImporter.tsx` | Import transkriptů |
| **KellyAllocatorWidget** | `KellyAllocatorWidget.tsx` | Position sizing |
| **TrafficLightWidget** | `TrafficLightWidget.tsx` | Market Alert semafor |
| **FamilyAuditWidget** | `FamilyAuditWidget.tsx` | Rodinný audit portfolií |
| **WatchlistRankingTable** | `WatchlistRankingTable.tsx` | Ranking watchlistu |

### 5.2 Gomes Guardian Dashboard

Hlavní dashboard zobrazuje:

1. **Portfolio Summary** - Celková hodnota, P/L, počet pozic
2. **Position Cards** - Každá pozice s:
   - Gomes Score (1-10)
   - Action Signal (BUY/HOLD/SELL/SNIPER)
   - Current Weight vs Target Weight
   - Gap Analysis (kolik dokoupit/prodat)
   - Next Catalyst
3. **Traffic Light** - Celkový stav trhu (GREEN/YELLOW/ORANGE/RED)
4. **Top Picks** - Nejlepší příležitosti k nákupu

### 5.3 Target Weight Systém

```typescript
// Cílové váhy podle Gomes Score
const TARGET_WEIGHTS: Record<number, number> = {
  10: 15,   // CORE - Highest conviction (12-15%)
  9: 15,    // CORE - High conviction  
  8: 12,    // STRONG - Solid position (10-12%)
  7: 10,    // GROWTH - Growth position (7-10%)
  6: 5,     // WATCH - Monitor closely (3-5%)
  5: 3,     // WATCH - Small position
  4: 0,     // EXIT - Should not hold
  3: 0,     // EXIT - Sell signal
  2: 0,     // EXIT - Strong sell
  1: 0,     // EXIT - Avoid completely
};
```

### 5.4 Action Commands

```typescript
// Dynamické akční příkazy
const getActionCommand = (score, currentWeight, targetWeight, profitPct) => {
  // Priority 1: Free Ride at 150%+
  if (profitPct >= 150) return 'FREE RIDE';
  
  // Priority 2: Hard Exit for score < 4
  if (score < 4) return 'HARD EXIT';
  
  // Priority 3: Strong Buy for score >= 8 and underweight
  if (score >= 8 && currentWeight < targetWeight) return 'STRONG BUY';
  
  // Priority 4: Hold if at or above target weight
  if (score >= 5 && currentWeight >= targetWeight) return 'HOLD';
  
  // Default: BUY signal
  if (score >= 5 && currentWeight < targetWeight) return 'BUY';
  
  return 'ANALYZE';
};
```

---

## 6. Gomes Metodologie

### 6.1 The Gomes Rules

Mark Gomes (Money Mark) definuje přísná pravidla pro investování do micro-cap akcií:

#### 6.1.1 Market Alert System (Semafor)

| Alert Level | Popis | Alokace |
|-------------|-------|---------|
| 🟢 **GREEN** | Offense mode - agresivně nasazovat kapitál | 100% Stocks |
| 🟡 **YELLOW** | Selective - pouze nejlepší setupy | 70-80% Stocks, 20-30% Cash/Hedge |
| 🟠 **ORANGE** | Defense - redukovat expozici | 40-50% Stocks, 50-60% Cash/Hedge |
| 🔴 **RED** | Cash is King - chránit kapitál | 0-20% Stocks, 80-100% Cash |

#### 6.1.2 Stock Lifecycle Phases

| Fáze | Popis | Akce |
|------|-------|------|
| **GREAT FIND** | Dream phase - neznámá, začíná růst | ✅ Riskantní, ale povolené |
| **WAIT TIME** | Hype umřel, cena klesá, čekání | ⚠️ **NEINVESTOVAT!** |
| **GOLD MINE** | Proven execution - zisková, silné objednávky | ✅ Safe Buy |

**Detekce WAIT TIME:**
- Transcript obsahuje: "delays", "no orders yet", "waiting for approval"

**Detekce GOLD MINE:**
- Transcript obsahuje: "Firing on all cylinders", "Record revenue", "Profitable"

#### 6.1.3 Position Sizing Tiers

| Tier | Typ pozice | Max % portfolia |
|------|------------|-----------------|
| **PRIMARY (Core)** | Proven Gold Mine | 10-15% |
| **SECONDARY** | Great Find, dating phase | 5-8% |
| **TERTIARY** | Spekulativní/FOMO | 1-2% |

> ⚠️ **Yellow Alert Constraint:** V Yellow Alertu nesmí být žádné spekulativní pozice!

### 6.2 Price Lines System

```
┌─────────────────────────────────────────────┐
│                 RED LINE                     │  ← SELL ZONE (overvalued)
│                    ▲                         │
│                    │                         │
│             Current Price                    │
│                    │                         │
│                    ▼                         │
│                GREEN LINE                    │  ← BUY ZONE (undervalued)
└─────────────────────────────────────────────┘
```

- **Green Line**: Podhodnocená úroveň - ideální pro nákup
- **Red Line**: Plně ohodnocená úroveň - zvážit prodej
- **3-Point Rule**: Pokud se skóre zhorší o 3 body → Take Profit
- **Doubling Rule**: Pokud zdvojnásobíš peníze → prodej polovinu (House Money)

### 6.3 Gomes Gatekeeper

```python
# Implementace v gomes_logic.py

class GomesGatekeeper:
    """
    Final verdict synthesizer - no investment passes without approval.
    """
    
    def evaluate(self, ticker: str) -> GomesVerdict:
        # 1. Check market alert level
        if self.market_alert == MarketAlert.RED:
            return GomesVerdict.BLOCKED
        
        # 2. Check lifecycle phase
        if self.lifecycle_phase == LifecyclePhase.WAIT_TIME:
            return GomesVerdict.AVOID
        
        # 3. Check position sizing
        if self.current_allocation > self.max_allocation:
            return GomesVerdict.TRIM
        
        # 4. Check price vs lines
        if self.current_price < self.green_line:
            return GomesVerdict.STRONG_BUY
        
        # ... další logika
```

---

## 7. Master Signal v2.0

### 7.1 Přehled

**Master Signal v2.0** je zjednodušený 3-pilířový systém navržený pro micro-cap investování.

### 7.2 Co bylo odstraněno (a proč)

| Komponenta | Důvod odstranění |
|------------|------------------|
| **ML/PatchTST** | Micro-capy jsou nepředvídatelné - GSI udělá +100% za den po oznámení kontraktu |
| **Sentiment Analysis** | O GKPRF nepíše Bloomberg - sentiment = placené PR zprávy |
| **RSI/MACD** | 10k shares/day volume = šum, ne signál |
| **Backtesting** | Spread 5-10% u micro-capů zkresluje simulaci |

### 7.3 Nový 3-Pilířový Systém

```
┌───────────────────────────────────────────────────────────────────┐
│                     MASTER SIGNAL v2.0                             │
│                                                                    │
│  ┌───────────────────────────────────────────────────────────┐    │
│  │ 1. THESIS TRACKER (60%)                                   │    │
│  │    • Gemini Pro + Transkripty → Gomes Score               │    │
│  │    • Milníky (Contracts, Certifications, Revenue)         │    │
│  │    • Červené vlajky (Dilution, Delays, Leadership)        │    │
│  └───────────────────────────────────────────────────────────┘    │
│                                                                    │
│  ┌───────────────────────────────────────────────────────────┐    │
│  │ 2. VALUATION & CASH (25%)                                 │    │
│  │    • Cash on Hand                                         │    │
│  │    • Total Debt                                           │    │
│  │    • Burn Rate → Runway < 6 měsíců = RED FLAG             │    │
│  └───────────────────────────────────────────────────────────┘    │
│                                                                    │
│  ┌───────────────────────────────────────────────────────────┐    │
│  │ 3. WEINSTEIN TREND GUARD (15%)                            │    │
│  │    • 30 WMA (Weekly Moving Average)                       │    │
│  │    • Pod klesající 30 WMA? → NEKUPOVAT                    │    │
│  │    • Nad rostoucí 30 WMA? → KUPOVAT                       │    │
│  └───────────────────────────────────────────────────────────┘    │
└───────────────────────────────────────────────────────────────────┘
```

### 7.4 Weinstein Phases

Stan Weinstein's Market Phases:

| Phase | Popis | Akce |
|-------|-------|------|
| **Phase 1 (Base)** | Cena pod WMA, ale WMA se zvedá | WATCH |
| **Phase 2 (Advance)** | Cena nad rostoucí WMA | **BUY** ✅ |
| **Phase 3 (Top)** | Cena nad WMA, ale WMA klesá | SELL |
| **Phase 4 (Decline)** | Cena pod klesající WMA | **AVOID** ❌ |

### 7.5 Cash Runway Status

| Status | Runway | Riziko ředění |
|--------|--------|---------------|
| **HEALTHY** | > 12 měsíců | Nízké |
| **CAUTION** | 6-12 měsíců | Střední |
| **DANGER** | < 6 měsíců | **Vysoké** ⚠️ |

### 7.6 Blocking Rules

Systém automaticky blokuje nákup v těchto situacích:

1. **Weinstein Phase 4**: Cena pod klesající 30 WMA → DO NOT BUY
2. **Cash Runway < 6 měsíců**: Vysoké riziko ředění → AVOID
3. **3+ Red Flags**: Příliš mnoho varovných signálů → AVOID

### 7.7 API Usage

```http
GET /api/master-signal/{ticker}
```

**Response:**
```json
{
  "ticker": "GKPRF",
  "buy_confidence": 72.5,
  "signal_strength": "BUY",
  "components": {
    "thesis_tracker": {
      "score": 85.0,
      "gomes_score": 80.0,
      "milestones_hit": 2,
      "red_flags": 0,
      "verdict": "BUY"
    },
    "valuation_cash": {
      "score": 70.0,
      "cash_on_hand_m": 15.2,
      "runway_months": 18,
      "runway_status": "HEALTHY"
    },
    "weinstein_guard": {
      "score": 55.0,
      "phase": "PHASE_2_ADVANCE",
      "price": 0.45,
      "wma_30": 0.42
    }
  },
  "blocked": false,
  "verdict": "BUY"
}
```

---

## 8. AI Analýza

### 8.1 Gemini Integration

Systém používá **Google Gemini 2.0 Flash** pro:

1. **Stock Extraction** - Extrakce akciových zmínek z transkriptů
2. **Scoring** - Přidělení Gomes Score (1-10)
3. **Deep Due Diligence** - Hloubková analýza s Google Search

### 8.2 System Prompt

```python
ROLE: You are a HEDGE FUND PORTFOLIO MANAGER with 20+ years experience.
Your mandate is to generate ACTIONABLE TRADING SIGNALS, not just research reports.

CRITICAL MINDSET:
- Do NOT just analyze text - look for TRADING SETUPS
- Distinguish between "I like the company" vs "I like the chart"
- If speaker doesn't state exact price, INFER the context

ACTION VERDICT (choose ONE):
- BUY_NOW: Strong conviction, catalysts imminent
- ACCUMULATE: Building position, favorable R/R
- WATCH_LIST: Interesting but needs trigger
- TRIM: Reduce exposure
- SELL: Exit completely
- AVOID: Stay away

OUTPUT: Pure JSON with stocks array
```

### 8.3 Universal Intelligence Unit

Multi-source context-aware analysis system:

| Source Type | Reliability | Extraction Strategy |
|------------|-------------|---------------------|
| **Official Filing** | 100% | Tvrdá čísla (cash, revenue, dates) |
| **Press Release** | 100% | Skeptický k vágním prohlášením |
| **Analyst Report** | 60% | Price targets, porovnání s tezí |
| **Chat Discussion** | 30% | Key voices, ignorovat hype |
| **Article/Manual** | 50% | Balanced approach |

### 8.4 Extraction Flow

```
1. INPUT: Raw transcript/document
      ↓
2. SOURCE DETECTION: AI determines source type
      ↓
3. EXTRACTION: Context-aware extraction based on source
      ↓
4. SCORING: Gomes Score assignment (1-10)
      ↓
5. VALIDATION: Cross-check with hard data
      ↓
6. OUTPUT: Structured JSON with stocks
```

---

## 9. Databázové Modely

### 9.1 Core Models

#### Stock Model

```python
class Stock(Base):
    """Stock analysis record following Gomes Investment Methodology."""
    
    __tablename__ = "stocks"
    
    # Primary Key & Timestamps
    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())
    
    # Stock Identification
    ticker = Column(String(20), nullable=False, index=True)
    company_name = Column(String(200))
    
    # Source Attribution
    source_type = Column(String(50))  # YouTube, Google Docs, etc.
    speaker = Column(String(100))     # e.g., Mark Gomes
    
    # Analysis Metadata
    sentiment = Column(String(50))    # Bullish, Bearish, Neutral
    gomes_score = Column(Integer)     # 1-10
    
    # The Gomes Rules (Core Analysis)
    edge = Column(Text)               # Information Arbitrage
    catalysts = Column(Text)          # Upcoming events
    next_catalyst = Column(String(100))  # "Q1 EARNINGS / MAY 26"
    risks = Column(Text)              # Risk assessment
    
    # Trading Action Fields
    action_verdict = Column(String(50))   # BUY_NOW, ACCUMULATE, etc.
    entry_zone = Column(String(200))      # "Under $15"
    price_target_short = Column(String(50))
    price_target_long = Column(String(50))
    stop_loss_risk = Column(Text)
    moat_rating = Column(Integer)         # 1-5
    
    # Gomes Tactical Fields
    asset_class = Column(String)          # ANCHOR, HIGH_BETA_ROCKET, etc.
    cash_runway_months = Column(Integer)
    total_cash = Column(Float)
    quarterly_burn_rate = Column(Float)
    inflection_status = Column(String)    # WAIT_TIME, UPCOMING, GOLD_MINE
    
    # Price Lines
    green_line = Column(Float)            # Buy zone
    red_line = Column(Float)              # Sell zone
    
    # Versioning
    version = Column(Integer, default=1)
    is_latest = Column(Boolean, default=True)
```

#### Portfolio Model

```python
class Portfolio(Base):
    """Portfolio representing a user's investment account."""
    
    __tablename__ = "portfolios"
    
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    owner = Column(String(100), nullable=False)  # "Já", "Přítelkyně"
    broker = Column(SQLEnum(BrokerType))         # T212, DEGIRO, XTB
    cash_balance = Column(Float, default=0.0)
    monthly_contribution = Column(Float, default=20000.0)
    
    # Relationships
    positions = relationship("Position", back_populates="portfolio")
```

#### Position Model

```python
class Position(Base):
    """Position representing a stock holding in a portfolio."""
    
    __tablename__ = "positions"
    
    id = Column(Integer, primary_key=True)
    portfolio_id = Column(Integer, ForeignKey("portfolios.id"))
    ticker = Column(String, nullable=False, index=True)
    company_name = Column(String(255))
    shares_count = Column(Float, nullable=False)
    avg_cost = Column(Float, nullable=False)
    currency = Column(String(3), default="USD")
    current_price = Column(Float)
    
    # Computed properties
    @property
    def cost_basis(self) -> float:
        return self.shares_count * self.avg_cost
    
    @property
    def market_value(self) -> float:
        return self.shares_count * (self.current_price or self.avg_cost)
    
    @property
    def unrealized_pnl(self) -> float:
        return self.market_value - self.cost_basis
```

### 9.2 Trading Models

```python
class ActiveWatchlist(Base):
    """Analyst-recommended tickers for active monitoring."""
    
    __tablename__ = "active_watchlist"
    
    id = Column(Integer, primary_key=True)
    ticker = Column(String(10), unique=True, nullable=False)
    stock_id = Column(Integer, ForeignKey('stocks.id'))
    action_verdict = Column(String(20))
    confidence_score = Column(Numeric(3, 2))
    gomes_score = Column(Numeric(4, 2))
    investment_thesis = Column(Text)
    risks = Column(Text)
    is_active = Column(Boolean, default=True)


class MLPrediction(Base):
    """ML model predictions (legacy - reduced scope in v2.0)."""
    
    __tablename__ = "ml_predictions"
    
    id = Column(Integer, primary_key=True)
    ticker = Column(String(10), nullable=False)
    prediction_type = Column(String(10))  # UP, DOWN, NEUTRAL
    confidence = Column(Numeric(5, 4))
    predicted_price = Column(Numeric(12, 4))
    current_price = Column(Numeric(12, 4))
    model_version = Column(String(50))
    horizon_days = Column(Integer, default=5)
```

### 9.3 Gomes-Specific Models

```python
class MarketAlertModel(Base):
    """Market alert level (Traffic Light)."""
    
    __tablename__ = "market_alerts"
    
    id = Column(Integer, primary_key=True)
    alert_level = Column(String(10))  # GREEN, YELLOW, ORANGE, RED
    stocks_pct = Column(Numeric)
    cash_pct = Column(Numeric)
    hedge_pct = Column(Numeric)
    reason = Column(Text)
    effective_from = Column(DateTime)
    effective_until = Column(DateTime)


class PriceLinesModel(Base):
    """Price lines for stocks (Green/Red lines)."""
    
    __tablename__ = "price_lines"
    
    id = Column(Integer, primary_key=True)
    ticker = Column(String(10), unique=True)
    green_line = Column(Float)
    red_line = Column(Float)
    grey_line = Column(Float)
    source = Column(String(50))  # transcript, image, manual
```

---

## 10. API Reference

### 10.1 Analysis Endpoints

#### POST /api/analyze/text
Analyzuje text transkriptu pro akciové zmínky.

```json
// Request
{
  "transcript": "I'm very bullish on NVDA...",
  "speaker": "Mark Gomes",
  "source_type": "manual_input"
}

// Response
{
  "stocks": [
    {
      "ticker": "NVDA",
      "company_name": "NVIDIA Corporation",
      "sentiment": "Bullish",
      "gomes_score": 8,
      "action_verdict": "BUY_NOW",
      "entry_zone": "Under $500"
    }
  ]
}
```

#### POST /api/analyze/youtube
Analyzuje YouTube video transcript.

```json
// Request
{
  "url": "https://www.youtube.com/watch?v=VIDEO_ID",
  "speaker": "Mark Gomes"
}
```

#### POST /api/analyze/google-docs
Analyzuje Google Docs obsah.

```json
// Request
{
  "url": "https://docs.google.com/document/d/DOC_ID/edit",
  "speaker": "Mark Gomes"
}
```

### 10.2 Portfolio Endpoints

#### GET /api/portfolio
Vrátí seznam všech portfolií.

#### GET /api/portfolio/{id}
Vrátí detail portfolia s pozicemi.

#### POST /api/portfolio/import
Importuje pozice z broker CSV.

```json
// Request (multipart/form-data)
{
  "file": "portfolio.csv",
  "broker": "T212",
  "portfolio_id": 1
}
```

### 10.3 Master Signal Endpoints

#### GET /api/master-signal/{ticker}
Vrátí Master Signal pro ticker.

#### GET /api/action-center
Vrátí akční centrum se všemi signály.

### 10.4 Gomes Endpoints

#### GET /api/gomes/market-alert
Vrátí aktuální stav trhu (Traffic Light).

#### POST /api/gomes/market-alert
Nastaví nový stav trhu.

```json
// Request
{
  "alert_level": "YELLOW",
  "reason": "Market is expensive, being selective"
}
```

#### GET /api/gomes/price-lines/{ticker}
Vrátí price lines pro ticker.

### 10.5 Intelligence Endpoints

#### POST /api/intelligence/analyze-ticker
Analyzuje ticker s Universal Intelligence.

```json
// Request
{
  "ticker": "KUYA.V",
  "source_type": "transcript",
  "input_text": "Full text...",
  "investor_name": "Mark Gomes"
}
```

---

## 11. Services Layer

### 11.1 GomesIntelligenceService

Hlavní služba pro Gomes business logiku:

```python
class GomesIntelligenceService:
    """Main service for Gomes Intelligence Module."""
    
    def get_current_market_alert(self) -> MarketAlert:
        """Get current market alert level."""
    
    def get_market_allocation(self) -> MarketAllocation:
        """Get portfolio allocation based on market alert."""
    
    def set_market_alert(self, alert_level: str, reason: str) -> MarketAlertModel:
        """Set new market alert level."""
    
    def get_lifecycle_phase(self, ticker: str) -> LifecyclePhase:
        """Determine stock lifecycle phase."""
    
    def get_price_lines(self, ticker: str) -> PriceLines:
        """Get green/red lines for ticker."""
    
    def get_verdict(self, ticker: str) -> GomesVerdict:
        """Get final investment verdict."""
```

### 11.2 KellyAllocatorService

Position sizing podle Kelly Criterion:

```python
class KellyAllocatorService:
    """Gomes Gap Analysis Allocation Service."""
    
    # Target weights by Gomes score
    TARGET_WEIGHTS = {
        10: 0.15,  # CORE - highest conviction
        9: 0.15,
        8: 0.12,
        7: 0.10,
        6: 0.05,
        5: 0.03,
        4: 0.00,  # EXIT
        3: 0.00,
        2: 0.00,
        1: 0.00,
    }
    
    MAX_POSITION_WEIGHT = 0.15  # Max 15% in single stock
    MIN_INVESTMENT_CZK = 1000   # Min investment
    
    def calculate_allocation(
        self,
        portfolio_id: int,
        available_cash_eur: float
    ) -> AllocationPlan:
        """Calculate optimal allocation for available capital."""
```

### 11.3 GapAnalysisService

Detekce mezer mezi analýzou a pozicemi:

```python
class GapAnalysisService:
    """Gap analysis between stock signals and portfolio positions."""
    
    @staticmethod
    def calculate_match_signal(
        stock: Stock,
        user_position: Position | None,
        market_status: MarketStatusEnum
    ) -> MatchSignal:
        """
        Returns:
        - OPPORTUNITY: BUY signal, don't own
        - ACCUMULATE: BUY signal, already own
        - DANGER_EXIT: SELL signal, currently own
        - WAIT_MARKET_BAD: BUY signal but market is RED
        - HOLD: Own but no strong signal
        - NO_ACTION: Don't own, no strong signal
        """
```

### 11.4 InvestmentDecisionEngine

Generuje investiční rozhodnutí kombinací všech zdrojů:

```python
class InvestmentDecisionEngine:
    """
    Generates investment decisions by combining:
    - Gomes analysis (edge, catalysts, risks, score)
    - ML predictions (direction, confidence)
    - Current price vs entry zone
    - Recent news and sentiment
    """
    
    async def analyze_stock(self, ticker: str) -> InvestmentDecision:
        """Generate complete investment decision for a stock."""
```

### 11.5 YahooCache Service

Smart cache pro Yahoo Finance data:

```python
class YahooSmartCache:
    """
    Intelligent caching for Yahoo Finance data.
    
    - Caches quotes for 1 hour during market hours
    - Caches quotes for 24 hours after market close
    - Handles rate limiting
    - Fallback to cached data on API failure
    """
```

---

## 12. Konfigurace a Deployment

### 12.1 Lokální Vývoj

```powershell
# Backend
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python start.py

# Frontend
cd frontend
npm install
npm run dev
```

### 12.2 Environment Variables

```env
# Database (Neon.tech)
DATABASE_URL=postgresql://user:password@ep-xxx.eu-central-1.aws.neon.tech/akcion

# AI
GEMINI_API_KEY=AIzaSy...

# Market Data (optional)
MASSIVE_API_KEY=...
FINNHUB_API_KEY=...

# Notifications
TELEGRAM_BOT_TOKEN=123456:ABC...
TELEGRAM_CHAT_ID=123456789
EMAIL_RECIPIENT=your@email.com
SMTP_USERNAME=smtp@gmail.com
SMTP_PASSWORD=app_password
```

### 12.3 VS Code Tasks

```json
{
  "label": "🚀 Start Backend",
  "command": "python -m uvicorn app.main:app --host 127.0.0.1 --port 8002 --reload",
  "options": { "cwd": "${workspaceFolder}/backend" }
},
{
  "label": "🎨 Start Frontend",
  "command": "npm run dev",
  "options": { "cwd": "${workspaceFolder}/frontend" }
},
{
  "label": "⚡ Start All (BE + FE)",
  "dependsOn": ["🚀 Start Backend", "🎨 Start Frontend"]
}
```

### 12.4 Database Migrations

```bash
# Apply migration
psql $DATABASE_URL -f migrations/add_gomes_tactical_fields.sql

# Or use apply script
python apply_migration.py
```

---

## 13. Testování

### 13.1 Test Structure

```
backend/tests/
├── conftest.py              # Shared fixtures
├── test_api_endpoints.py    # API integration tests
├── test_api_integration.py  # Full integration tests
├── test_backtest.py         # Backtesting tests
├── test_master_signal.py    # Master Signal tests
├── test_ml_learning.py      # ML tests (legacy)
├── test_phase1_extraction.py # Extraction tests
└── test_yahoo_cache.py      # Yahoo cache tests
```

### 13.2 Running Tests

```powershell
cd backend
pytest tests/ -v

# Specific test
pytest tests/test_master_signal.py -v

# With coverage
pytest tests/ --cov=app --cov-report=html
```

### 13.3 Test Instructions

Viz `.github/instructions/Test.instructions.md`:

- Testy musí validovat proti známým transkriptům
- Očekávaný výstup: 100% capture rate akciových zmínek
- Gomes scoring musí být konzistentní s manuální analýzou

---

## 14. Bezpečnostní Pravidla

### 14.1 Production Checklist

- [ ] **Disable dev_utils.py** v produkci
- [ ] Nastavit `DEBUG=False`
- [ ] Použít silná hesla v .env
- [ ] Rotovat API klíče pravidelně
- [ ] Monitoring error rates
- [ ] Backup databáze

### 14.2 Fiduciary Standards

Systém dodržuje fiduciární standardy:

1. **Transparentnost** - Každé doporučení má zdůvodnění
2. **Konzervativnost** - Raději zmeškat příležitost než ztratit kapitál
3. **Auditovatelnost** - Kompletní historie rozhodnutí
4. **No Conflicts** - Systém nemá vlastní zájmy

### 14.3 Data Protection

- Citlivá data (API klíče) pouze v .env
- .env nikdy v git repozitáři
- Database credentials šifrované
- Telegram notifikace pouze autorizovaným uživatelům

---

## 15. Slovník Pojmů

| Pojem | Definice |
|-------|----------|
| **Gomes Score** | Skóre 1-10 přidělené akcii podle metodologie Marka Gomese |
| **Edge** | Information Arbitrage - co investor ví, co trh neví |
| **Catalyst** | Konkrétní událost, která pohne cenou (earnings, contract, FDA approval) |
| **Green Line** | Cenová úroveň pro nákup (podhodnoceno) |
| **Red Line** | Cenová úroveň pro prodej (plně ohodnoceno) |
| **WAIT TIME** | Fáze životního cyklu kdy se nemá investovat |
| **GOLD MINE** | Fáze životního cyklu - osvědčená firma, safe buy |
| **Traffic Light** | Market Alert systém (GREEN/YELLOW/ORANGE/RED) |
| **Kelly Criterion** | Matematický vzorec pro optimální velikost pozice |
| **30 WMA** | 30-Week Moving Average (Weinstein trend guard) |
| **Dilution Risk** | Riziko ředění akcií při nízké cash runway |
| **Free Ride** | Pozice s 150%+ ziskem - prodej poloviny |
| **House Money** | Pravidlo zdvojnásobení - prodat polovinu pro jistotu |
| **Fiduciary** | Povinnost jednat v nejlepším zájmu klienta |

---

## 📞 Podpora

Pro dotazy a podporu kontaktujte vlastníka projektu nebo otevřete issue na GitHub.

---

*Tato dokumentace byla vygenerována pro Akcion Trading Intelligence Module v2.0.0*
