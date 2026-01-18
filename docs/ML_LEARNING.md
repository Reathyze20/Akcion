# ML Learning Engine - Documentation

# ====================================

## Přehled

**ML Learning Engine** sleduje historickou úspěšnost predikcí a automaticky upravuje confidence score na základě skutečných výsledků.

**Klíčová idea:** Pokud Gomes řekl "Koupit" a cena klesla, AI by se to měla naučit a příště snížit confidence.

---

## Jak to Funguje

### 1. Recording Outcomes

Každá predikce se zaloguje do databáze s výsledkem:

```python
from app.trading.ml_learning import MLLearningEngine

engine = MLLearningEngine(db)

engine.record_outcome(
    ticker="AAPL",
    predicted_price=155.0,
    actual_price=156.5,  # Úspěch!
    confidence=0.85,
    prediction_date=datetime(2024, 1, 1),
    evaluation_date=datetime(2024, 1, 8)
)
```

### 2. Performance Tracking

Engine počítá metriky:

- **Win Rate**: % úspěšných predikcí
- **Average Error**: průměrná chyba v ceně
- **Sharpe Ratio**: risk-adjusted výkon
- **Gomes Correlation**: korelace s Gomes signály

```python
metrics = engine.get_performance_metrics("AAPL")

print(f"Win Rate: {metrics.win_rate:.1%}")
print(f"Avg Error: ${metrics.avg_error:.2f}")
print(f"Sharpe: {metrics.sharpe_ratio:.2f}")
```

### 3. Confidence Adjustment

Engine upravuje confidence na základě historical performance:

```python
original_confidence = 0.75
adjusted = engine.adjust_confidence("AAPL", original_confidence)

# Pokud AAPL má 85% win rate → confidence ↑
# Pokud AAPL má 40% win rate → confidence ↓
```

**Adjustment logic:**

- Win rate > 70% → boost +5-15%
- Win rate < 50% → penalize -5-20%
- High Gomes correlation → boost +5%
- Low Sharpe ratio → penalize -10%

---

## API Endpoints

### 1. Get Performance Metrics

```http
GET /api/ml/performance/{ticker}
```

**Response:**

```json
{
  "ticker": "AAPL",
  "total_predictions": 120,
  "win_rate": 0.675,
  "avg_error": 2.34,
  "sharpe_ratio": 1.45,
  "gomes_correlation": 0.82,
  "last_30_days": {
    "predictions": 15,
    "win_rate": 0.73
  }
}
```

### 2. Record Outcome

```http
POST /api/ml/outcome
```

**Request:**

```json
{
  "ticker": "AAPL",
  "predicted_price": 155.0,
  "actual_price": 156.5,
  "confidence": 0.85,
  "prediction_date": "2024-01-01T00:00:00",
  "evaluation_date": "2024-01-08T00:00:00"
}
```

### 3. Leaderboard

```http
GET /api/ml/leaderboard?limit=10
```

Top 10 tickerů podle win rate.

### 4. Batch Update

```http
POST /api/ml/batch-update
```

Pro bulk update více outcomes najednou.

---

## Database Schema

```sql
CREATE TABLE model_performance (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(10) NOT NULL,
    predicted_price DECIMAL(10,2),
    actual_price DECIMAL(10,2),
    prediction_error DECIMAL(10,2),
    confidence DECIMAL(3,2),
    prediction_date TIMESTAMP,
    evaluation_date TIMESTAMP,
    gomes_score DECIMAL(3,1),
    created_at TIMESTAMP DEFAULT NOW(),
    INDEX idx_ticker (ticker),
    INDEX idx_evaluation_date (evaluation_date)
);
```

---

## Integrace s ML Engine

```python
from app.trading.ml_engine import MLEngine

ml = MLEngine()

# Při predikci se automaticky aplikuje learning adjustment
prediction = ml.predict_price(
    ticker="AAPL",
    use_learning=True  # Default: True
)

print(f"Raw confidence: {prediction.raw_confidence}")
print(f"Adjusted confidence: {prediction.confidence}")
```

---

## Performance Monitoring

### Dashboard Query

```python
# Top performers
top_tickers = engine.get_leaderboard(limit=10)

for ticker in top_tickers:
    print(f"{ticker.ticker}: {ticker.win_rate:.1%} WR, {ticker.sharpe_ratio:.2f} Sharpe")
```

### Alert on Poor Performance

```python
metrics = engine.get_performance_metrics("AAPL")

if metrics.win_rate < 0.50 and metrics.total_predictions > 20:
    print(f"⚠️ WARNING: {ticker} has poor performance!")
    print(f"   Win Rate: {metrics.win_rate:.1%}")
    print(f"   Consider reducing weight or excluding")
```

---

## Configuration

Environment variables:

```bash
# Learning Engine Settings
ML_LEARNING_ENABLED=true
ML_MIN_SAMPLES=20          # Minimum predictions before adjustment
ML_ADJUSTMENT_STRENGTH=0.15  # Max adjustment ±15%
ML_LOOKBACK_DAYS=90        # Use last 90 days for metrics
```

---

## Best Practices

1. **Minimum Samples**: Neupravujte confidence dokud nemáte 20+ predictions
2. **Regular Evaluation**: Evaluujte predikce každých 7 dní
3. **Outlier Removal**: Odstraňte outliers před výpočtem metrik
4. **Correlation Check**: Sledujte Gomes correlation - pokud je vysoká, Gomes signály jsou užitečné

---

## Troubleshooting

### Win rate je příliš nízká (< 40%)

**Možné příčiny:**

- ML model potřebuje retraining
- Features nejsou dostatečně prediktivní
- Market regime se změnil

**Řešení:**

```bash
# Retrain ML model
python -m app.trading.ml_engine --ticker AAPL --retrain --epochs 100
```

### Confidence adjustment je příliš agresivní

Snižte `ML_ADJUSTMENT_STRENGTH`:

```bash
ML_ADJUSTMENT_STRENGTH=0.10  # Reduce to ±10%
```

### Metriky se nepočítají

Zkontrolujte, že máte dostatek dat:

```python
metrics = engine.get_performance_metrics("AAPL")
print(f"Total predictions: {metrics.total_predictions}")

# Pokud < 20, není dost dat pro učení
```

---

## Example: End-to-End Workflow

```python
from app.trading.ml_engine import MLEngine
from app.trading.ml_learning import MLLearningEngine
from app.database.connection import get_db_session

# 1. Make prediction
ml = MLEngine()
prediction = ml.predict_price("AAPL", horizon=7, use_learning=True)

print(f"Predicted: ${prediction.price:.2f}")
print(f"Confidence: {prediction.confidence:.1%}")

# 2. Wait 7 days...

# 3. Record actual outcome
with get_db_session() as db:
    learning = MLLearningEngine(db)

    learning.record_outcome(
        ticker="AAPL",
        predicted_price=prediction.price,
        actual_price=172.50,  # Real price after 7 days
        confidence=prediction.confidence,
        prediction_date=prediction.timestamp,
        evaluation_date=datetime.now()
    )

# 4. Check updated metrics
metrics = learning.get_performance_metrics("AAPL")
print(f"Updated Win Rate: {metrics.win_rate:.1%}")
```

---

## Changelog

### v1.0.0 (2025-01-17)

- ✅ Initial release
- ✅ Performance tracking
- ✅ Confidence adjustment
- ✅ Gomes correlation
- ✅ Leaderboard API
