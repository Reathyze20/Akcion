# Quick Start Guide

# ==================

Pro rychlé zprovoznění všech nových modulů.

---

## 1. Install Dependencies

```bash
cd backend
pip install -r requirements.txt
pip install -r requirements_trading.txt
pip install -r requirements_test.txt
```

---

## 2. Configure Environment

Zkopírujte a vyplňte `.env`:

```bash
cp .env.example .env
nano .env
```

**Minimální konfigurace:**

```bash
DATABASE_URL=postgresql://user:pass@localhost:5432/akcion
OPENAI_API_KEY=sk-...

# Optional: Notifications
TELEGRAM_BOT_TOKEN=123456:ABC...
TELEGRAM_CHAT_ID=123456789
```

---

## 3. Run Migrations

```bash
# Apply trading tables
psql $DATABASE_URL -f migrations/add_trading_tables.sql
```

---

## 4. Start Backend

```bash
python run_server.py
```

Otevřete http://localhost:8000/api/docs

---

## 5. Test Master Signal

```bash
# Get signal for AAPL
curl http://localhost:8000/api/master-signal/AAPL | jq

# Get today's opportunities
curl http://localhost:8000/api/action-center/opportunities?min_confidence=75 | jq
```

---

## 6. Start Frontend

```bash
cd frontend
npm install
npm run dev
```

Otevřete http://localhost:5173

---

## 7. Setup Notifications (Optional)

### Telegram:

1. Vytvořte bota: `@BotFather` → `/newbot`
2. Získejte Chat ID: `https://api.telegram.org/bot<TOKEN>/getUpdates`
3. Přidejte do `.env`:

```bash
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```

### Test:

```bash
curl -X POST http://localhost:8000/api/notifications/test-alert \
  -H "Content-Type: application/json" \
  -d '{"ticker":"AAPL","buy_confidence":85}'
```

---

## 8. Start Alert Scheduler

```bash
python -m app.services.alert_scheduler
```

---

## 9. Run Tests

```bash
cd backend
pytest tests/ -v
```

---

## 10. Frontend Components

V React aplikaci použijte nové komponenty:

```tsx
import ActionCenter from "./components/ActionCenter";
import MLPredictionChart from "./components/MLPredictionChart";

function App() {
  return (
    <>
      <ActionCenter />
      <MLPredictionChart ticker="AAPL" />
    </>
  );
}
```

---

## Common Commands

```bash
# Backend
python run_server.py              # Start API
python -m app.services.alert_scheduler  # Start alerts
pytest tests/ -v                  # Run tests

# Frontend
npm run dev                       # Start dev server
npm run build                     # Build production
npm run type-check                # TypeScript check

# Database
psql $DATABASE_URL                # Connect to DB
psql $DATABASE_URL -f migrations/file.sql  # Run migration

# Docker
docker build -t akcion-backend .
docker run -p 8000:8000 akcion-backend
```

---

## Troubleshooting

### Backend neběží

```bash
# Check Python version
python --version  # Should be 3.12+

# Reinstall dependencies
pip install --force-reinstall -r requirements.txt
```

### DB Connection Failed

```bash
# Test connection
psql $DATABASE_URL -c "SELECT 1"

# Check .env
cat .env | grep DATABASE_URL
```

### Tests failují

```bash
# Install test deps
pip install -r requirements_test.txt

# Run with verbose
pytest tests/ -v -s
```

---

## Next Steps

1. 📖 Přečtěte [Complete Documentation](./README.md)
2. 🔧 Nastavte [Notifications](./NOTIFICATIONS.md)
3. 📊 Prostudujte [Master Signal](./MASTER_SIGNAL.md)
4. 🧪 Spusťte [Backtesting](./BACKTESTING.md)

---

**Hotovo! Systém by měl běžet. 🚀**
