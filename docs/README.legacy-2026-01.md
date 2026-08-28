> ⚠️ **Stav: historické, nahrazeno 2026-08-28.** Toto byl dřívější `docs/README.md`
> (rejstřík appky ze stavu leden 2026 — React 18, Gemini 2.0 Flash, Master Signal
> se 6 komponentami). Nic z toho už neplatí. Aktuální rejstřík:
> [`README.md`](README.md). Zachováno pro historii, nikoli jako platný popis appky.

# Complete System Documentation

# ==============================

Kompletní přehled **Akcion Trading Intelligence** systému.

---

## 📚 Table of Contents

1. [System Overview](#system-overview)
2. [Architecture](#architecture)
3. [Module Documentation](#module-documentation)
4. [New Features (January 2026)](#new-features)
5. [API Reference](#api-reference)
6. [Deployment](#deployment)
7. [Testing](#testing)
8. [Troubleshooting](#troubleshooting)

---

## System Overview

**Akcion Trading Intelligence** je kompletní trading systém, který kombinuje:

- 🧠 **AI Analýzu** (Gomes transkripty + ML predikce)
- 📊 **Technical Indicators** (RSI, MACD, Moving Averages)
- 📰 **Sentiment Analysis** (News headlines)
- 📈 **Fundamentální Analýzu** (Gap Analysis)
- 🎯 **Master Signal** (6-component aggregation → Buy Confidence 0-100%)
- 🔔 **Alerty** (Telegram + Email)
- 📉 **Backtesting** (1-year simulations)
- 🧪 **ML Learning** (Self-improving AI)

### Tech Stack

| Layer          | Technology                         |
| -------------- | ---------------------------------- |
| **Backend**    | Python 3.12, FastAPI, SQLAlchemy   |
| **Database**   | PostgreSQL (Neon), TimescaleDB     |
| **ML**         | PyTorch, NeuralForecast (PatchTST) |
| **Frontend**   | React 18, TypeScript, Recharts     |
| **Deployment** | Docker, systemd, GitHub Actions CI |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      FRONTEND (React)                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ Action Center│  │ ML Charts    │  │ Portfolio    │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└─────────────────────────────────────────────────────────────┘
                            │
                    FastAPI REST API
                            │
┌─────────────────────────────────────────────────────────────┐
│                      BACKEND (Python)                        │
│                                                              │
│  ┌───────────────────────────────────────────────────────┐  │
│  │                  MASTER SIGNAL                        │  │
│  │  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌───┐ │  │
│  │  │Gomes │ │  ML  │ │Tech  │ │Sent  │ │ Gap  │ │R/R│ │  │
│  │  │ 30% │ │ 25% │ │ 15% │ │ 15% │ │ 10% │ │5% │ │  │
│  │  └──────┘ └──────┘ └──────┘ └──────┘ └──────┘ └───┘ │  │
│  └───────────────────────────────────────────────────────┘  │
│                            │                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ ML Learning  │  │ Backtesting  │  │ Notifications│      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└─────────────────────────────────────────────────────────────┘
                            │
┌─────────────────────────────────────────────────────────────┐
│              DATABASE (PostgreSQL + TimescaleDB)            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ OHLCV Data   │  │ Gomes Intel  │  │ ML Perform.  │      │
│  │ (TimeSeries) │  │              │  │              │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└─────────────────────────────────────────────────────────────┘
```

---

## Module Documentation

### 1. Master Signal Aggregator

**File**: `backend/app/trading/master_signal.py`

**Purpose**: Kombinuje 6 signálů do Buy Confidence score (0-100%)

**Components**:

- Gomes Intelligence (30%)
- ML Predictions (25%)
- Technical Analysis (15%)
- Sentiment Analysis (15%)
- Gap Analysis (10%)
- Risk/Reward Ratio (5%)

📖 **Detailed docs**: [MASTER_SIGNAL.md](./MASTER_SIGNAL.md)

---

### 2. ML Learning Engine

**File**: `backend/app/trading/ml_learning.py`

**Purpose**: Sleduje historical performance a adjustuje confidence

**Features**:

- ✅ Win rate tracking
- ✅ Prediction error analysis
- ✅ Gomes correlation
- ✅ Automatic confidence adjustment
- ✅ Leaderboard

📖 **Detailed docs**: [ML_LEARNING.md](./ML_LEARNING.md)

---

### 3. Sentiment Analysis

**File**: `backend/app/trading/sentiment.py`

**Purpose**: Stahuje news headlines a počítá sentiment score

**Sources**:

- Yahoo Finance
- RSS feeds (extensible)

**Algorithm**:

- Keyword-based NLP
- Negation handling
- Amplifier detection
- Returns 0-100 score

---

## New Features

### 🆕 January 2026 Updates

#### 1. Universal Intelligence Unit

**File**: `backend/app/core/prompts_universal_intelligence.py`

**Purpose**: Multi-source context-aware analysis with automatic source detection

**Features**:

- ✅ Auto-detects source type (Official Filing, Chat Discussion, Analyst Report)
- ✅ Source-specific reliability (100% for Filings, 30% for Chat, 60% for Analysts)
- ✅ Context-aware extraction (Chat → sentiment/rumors, Official → hard numbers)
- ✅ Nested JSON output with meta_info, inflection_updates, financial_updates
- ✅ Decision tree with source-specific scoring penalties

**API Endpoint**:
```
POST /api/intelligence/analyze-ticker?use_universal_prompt=true
```

📖 **Detailed docs**: [UNIVERSAL_INTELLIGENCE.md](./UNIVERSAL_INTELLIGENCE.md)

---

#### 2. Logical Validation System

**Files**: 
- `backend/app/routes/intelligence_gomes.py`
- `frontend/src/components/StockDetailModalGomes.tsx`

**Purpose**: Automatic detection of investment logic errors

**Features**:

- ✅ Validates: Score 9+ requires specific Catalyst
- ✅ Yellow warning box in frontend when logic error detected
- ✅ Backend logging for monitoring
- ✅ Protects against AI blind spots (missing market calendar context)

**Validation Rule**:
```python
IF gomes_score >= 9 AND next_catalyst is empty:
    → Display: "⚠️ LOGICAL ERROR: High Score but No Catalyst"
```

📖 **Detailed docs**: [LOGICAL_VALIDATION.md](./LOGICAL_VALIDATION.md)

---

#### 3. UI/UX Improvements

**File**: `frontend/src/components/StockDetailModalGomes.tsx`

**Changes**:

- ✅ Trading Deck larger fonts (text-xs instead of text-[9px])
- ✅ "+ ANALÝZA" button moved to header (right side)
- ✅ Trading Deck Legend added (3-column explanations in Czech)
- ✅ Gomes Guardian Intelligence Unit modal with source type selector

---

### 4. Backtesting Engine

**File**: `backend/app/trading/backtest.py`

**Purpose**: Simuluje trading strategii na historical data

**Features**:

- ✅ OHLCV-based simulation
- ✅ Stop loss / Take profit
- ✅ Kelly position sizing
- ✅ Performance metrics (win rate, Sharpe, drawdown)

---

### 5. Notification System

**Files**:

- `backend/app/services/notifications.py`
- `backend/app/services/alert_scheduler.py`

**Purpose**: Posílá real-time alerts když Master Signal > 80%

**Channels**:

- Telegram bot
- Email (SMTP)

📖 **Detailed docs**: [NOTIFICATIONS.md](./NOTIFICATIONS.md)

---

## API Reference

### Base URL

```
Development: http://localhost:8000
Production: https://api.akcion.com
```

### Authentication

❌ **Zatím není implementováno**  
✅ **TODO**: JWT tokens v příští verzi

### Endpoints

#### Master Signal

| Method | Endpoint                           | Description                  |
| ------ | ---------------------------------- | ---------------------------- |
| GET    | `/api/master-signal/{ticker}`      | Get Master Signal for ticker |
| GET    | `/api/action-center/opportunities` | Get top opportunities        |
| GET    | `/api/action-center/summary`       | Get summary stats            |

#### ML Learning

| Method | Endpoint                       | Description                |
| ------ | ------------------------------ | -------------------------- |
| GET    | `/api/ml/performance/{ticker}` | Get performance metrics    |
| POST   | `/api/ml/outcome`              | Record prediction outcome  |
| GET    | `/api/ml/leaderboard`          | Get top performing tickers |

#### Backtesting

| Method | Endpoint                       | Description     |
| ------ | ------------------------------ | --------------- |
| POST   | `/api/backtest/run/{ticker}`   | Run backtest    |
| GET    | `/api/backtest/stats/{ticker}` | Get quick stats |

#### Notifications

| Method | Endpoint                                 | Description        |
| ------ | ---------------------------------------- | ------------------ |
| POST   | `/api/notifications/test-alert`          | Send test alert    |
| POST   | `/api/notifications/check-opportunities` | Manual alert check |
| GET    | `/api/notifications/status`              | Get channel status |

📖 **Full API docs**: http://localhost:8000/api/docs (Swagger UI)

---

## Deployment

### Local Development

```bash
# Backend
cd backend
pip install -r requirements.txt
pip install -r requirements_trading.txt
python run_server.py

# Frontend
cd frontend
npm install
npm run dev
```

### Production (Docker)

```dockerfile
# Dockerfile
FROM python:3.12-slim

WORKDIR /app
COPY backend/ .

RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir -r requirements_trading.txt

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

```bash
docker build -t akcion-backend .
docker run -p 8000:8000 \
  -e DATABASE_URL="postgresql://..." \
  -e TELEGRAM_BOT_TOKEN="..." \
  akcion-backend
```

### systemd Service

```ini
# /etc/systemd/system/akcion-api.service
[Unit]
Description=Akcion Trading API
After=network.target postgresql.service

[Service]
Type=simple
User=akcion
WorkingDirectory=/opt/akcion/backend
Environment="PATH=/opt/akcion/venv/bin"
EnvironmentFile=/opt/akcion/.env
ExecStart=/opt/akcion/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
```

---

## Testing

### Run All Tests

```bash
cd backend
pip install -r requirements_test.txt
pytest tests/ -v --cov=app
```

### Test Coverage

```bash
pytest tests/ --cov=app --cov-report=html
open htmlcov/index.html
```

### CI/CD Pipeline

GitHub Actions workflow: `.github/workflows/ci.yml`

**Stages**:

1. ✅ Backend tests (Python 3.12)
2. ✅ Frontend tests (Node 18)
3. ✅ Code quality (ruff)
4. ✅ Coverage upload (Codecov)

---

## Configuration

### Environment Variables

```bash
# Database
DATABASE_URL=postgresql://user:pass@host:5432/akcion

# OpenAI (for Gomes analysis)
OPENAI_API_KEY=sk-...

# Telegram
TELEGRAM_BOT_TOKEN=123456:ABC...
TELEGRAM_CHAT_ID=123456789

# Email
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-email@gmail.com
SMTP_PASSWORD=app-password-16-chars
SMTP_FROM_EMAIL=your-email@gmail.com
SMTP_TO_EMAIL=alerts@yourdomain.com

# Alert Settings
ALERT_CHECK_INTERVAL=30
ALERT_MIN_CONFIDENCE=80

# ML Learning
ML_LEARNING_ENABLED=true
ML_MIN_SAMPLES=20
ML_ADJUSTMENT_STRENGTH=0.15
```

---

## Troubleshooting

### Backend neběží

```bash
# Check logs
tail -f /var/log/akcion/api.log

# Check dependencies
pip list | grep -E "fastapi|sqlalchemy|torch"

# Test DB connection
python -c "from app.database.connection import is_connected; print(is_connected())"
```

### Master Signal vrací nízkou confidence

1. **Zkontrolujte komponenty**:

```bash
curl http://localhost:8000/api/master-signal/AAPL | jq .components
```

2. **Možné příčiny**:
   - ❌ Chybí ML predikce → retrain model
   - ❌ Chybí Gomes data → import transcript
   - ❌ Negativní sentiment → normal, market bearish
   - ❌ Špatný R/R ratio → adjust targets

### Tests failují

```bash
# Reinstall dependencies
pip install --force-reinstall -r requirements_test.txt

# Run specific test
pytest tests/test_master_signal.py::test_weights_sum_to_one -v

# Skip slow tests
pytest tests/ -v -m "not slow"
```

### Alerty se neposílají

1. **Test manuálně**:

```bash
curl -X POST http://localhost:8000/api/notifications/test-alert \
  -H "Content-Type: application/json" \
  -d '{"ticker":"AAPL","buy_confidence":85}'
```

2. **Zkontrolujte scheduler**:

```bash
ps aux | grep alert_scheduler
```

3. **Zkontrolujte credentials**:

```bash
curl http://localhost:8000/api/notifications/status
```

---

## Performance Optimization

### Database Indexing

```sql
-- OHLCV queries
CREATE INDEX idx_ohlcv_ticker_timestamp ON ohlcv_data(ticker, timestamp DESC);

-- Master Signal cache
CREATE INDEX idx_master_signal_ticker ON master_signals(ticker, created_at DESC);

-- ML Performance
CREATE INDEX idx_ml_perf_ticker_eval ON model_performance(ticker, evaluation_date DESC);
```

### Caching Strategy

```python
from functools import lru_cache

@lru_cache(maxsize=128)
def get_master_signal_cached(ticker: str) -> MasterSignal:
    # Cache pro 5 minut
    return get_master_signal(db, ticker)
```

### Async Optimization

```python
import asyncio

async def fetch_all_signals(tickers: list[str]):
    tasks = [get_master_signal_async(ticker) for ticker in tickers]
    return await asyncio.gather(*tasks)
```

---

## Security

### ⚠️ CRITICAL

1. **NIKDY** necommitujte `.env` soubor
2. **VŽDY** používejte environment variables pro credentials
3. **ROTUJTE** API keys pravidelně
4. **LIMITUJTE** API rate limits (10 req/sec per IP)

### Best Practices

```bash
# .env example (NEVER commit!)
# Use .env.example for templates

# Strong passwords
DATABASE_PASSWORD=$(openssl rand -base64 32)

# Restrict file permissions
chmod 600 .env
```

---

## Changelog

### January 25, 2026

**🆕 Universal Intelligence Unit**
- Multi-source prompt with automatic source type detection
- Context-aware extraction logic per source reliability
- Nested JSON structure with meta_info, inflection_updates, financial_updates
- Decision tree with source-specific penalties

**🛡️ Logical Validation System**
- Backend validation: Score 9+ requires Catalyst
- Yellow warning display in frontend
- Protection against AI blind spots

**🎨 UI/UX Improvements**
- Trading Deck larger fonts (text-xs)
- "+ ANALÝZA" button relocated to header
- Trading Deck Legend with 3-column Czech explanations
- Enhanced Intelligence Unit modal

---

## Documentation Index

| Document | Description |
|----------|-------------|
| [README.md](./README.md) | Complete system documentation (this file) |
| [QUICKSTART.md](./QUICKSTART.md) | Quick setup guide |
| [SETUP_GUIDE.md](./SETUP_GUIDE.md) | Detailed setup instructions |
| [MASTER_SIGNAL.md](./MASTER_SIGNAL.md) | Master Signal aggregator docs |
| [NOTIFICATIONS.md](./NOTIFICATIONS.md) | Alert system configuration |
| [UNIVERSAL_INTELLIGENCE.md](./UNIVERSAL_INTELLIGENCE.md) | Multi-source analysis system |
| [LOGICAL_VALIDATION.md](./LOGICAL_VALIDATION.md) | Investment logic validation |
| [GOMES_TACTICAL_PANELS.md](./GOMES_TACTICAL_PANELS.md) | Gomes methodology panels |
| [PORTFOLIO_PL_CALCULATION.md](./PORTFOLIO_PL_CALCULATION.md) | P&L calculation logic |
| [YAHOO_CACHE.md](./YAHOO_CACHE.md) | Yahoo Finance caching |

---

### v1.0.0 (2025-01-17)

**Features**:

- ✅ Master Signal Aggregator (6 components)
- ✅ ML Learning Engine (self-improving)
- ✅ Sentiment Analysis (news scraping)
- ✅ Backtesting Engine (1-year sims)
- ✅ Notification System (Telegram + Email)
- ✅ Action Center (frontend widget)
- ✅ ML Prediction Charts (interactive)

**Tests**:

- ✅ 50+ unit tests
- ✅ API integration tests
- ✅ GitHub Actions CI

**Documentation**:

- ✅ Complete module docs
- ✅ API reference
- ✅ Deployment guide

---

## Future Roadmap

### v1.1.0 (Q1 2025)

- [ ] Short position support
- [ ] Multi-timeframe analysis (1h, 4h, 1d)
- [ ] Discord notifications
- [ ] Mobile app (React Native)

### v1.2.0 (Q2 2025)

- [ ] Options trading signals
- [ ] Portfolio optimization
- [ ] Risk management dashboard
- [ ] Advanced backtesting (Monte Carlo)

### v2.0.0 (Q3 2025)

- [ ] Real-time WebSocket feeds
- [ ] AI chatbot assistant
- [ ] Social sentiment (Twitter, Reddit)
- [ ] Auto-trading execution

---

## Support

**Documentation**: https://docs.akcion.com  
**Issues**: https://github.com/akcion/trading-intelligence/issues  
**Email**: support@akcion.com

---

## License

Proprietary - All Rights Reserved

© 2025 Akcion Trading Intelligence
