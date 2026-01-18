# Master Signal Aggregator - Documentation

## 🎯 Přehled

**Master Signal Aggregator** je "mozek" trading systému. Kombinuje všechny dostupné signály do jednoho actionable čísla: **Buy Confidence (0-100%)**.

## 📊 Komponenty Signálu

Master Signal agreguje 5 komponent s různými vahami:

| Komponenta          | Váha | Popis                                       |
| ------------------- | ---- | ------------------------------------------- |
| **Gomes Score**     | 35%  | Gomes Intelligence verdict                  |
| **ML Confidence**   | 25%  | PatchTST predikce confidence                |
| **Technical Score** | 20%  | RSI/MACD indikátory                         |
| **Gap Analysis**    | 10%  | Match s portfoliem (opportunity/accumulate) |
| **Risk/Reward**     | 10%  | R/R ratio kvalita                           |

## 🚀 Použití

### Backend API

```python
from app.trading.master_signal import calculate_buy_confidence

# Jednoduché použití
result = calculate_buy_confidence(db, ticker="AAPL", user_id=1)

print(f"Buy Confidence: {result.buy_confidence}%")
print(f"Signal Strength: {result.signal_strength}")
print(f"Verdict: {result.verdict}")
print(f"Entry: ${result.entry_price}")
print(f"Target: ${result.target_price}")
print(f"Stop Loss: ${result.stop_loss}")

# Top příležitosti
from app.trading.master_signal import get_top_opportunities

opportunities = get_top_opportunities(
    db=db,
    user_id=1,
    min_confidence=70.0,
    limit=10
)

for opp in opportunities:
    print(f"{opp.ticker}: {opp.buy_confidence}% - {opp.signal_strength}")
```

### REST API Endpoints

#### 1. Master Signal pro jeden ticker

```http
GET /api/master-signal/AAPL?user_id=1
```

**Response:**

```json
{
  "ticker": "AAPL",
  "buy_confidence": 85.5,
  "signal_strength": "STRONG_BUY",
  "components": {
    "gomes_score": 90.0,
    "ml_confidence": 78.5,
    "technical_score": 75.0,
    "gap_score": 100.0,
    "risk_reward_score": 80.0
  },
  "verdict": "STRONG_BUY",
  "entry_price": 185.5,
  "target_price": 205.0,
  "stop_loss": 167.0,
  "risk_reward_ratio": 2.3,
  "kelly_size": 0.15,
  "calculated_at": "2026-01-17T14:30:00Z"
}
```

#### 2. Batch Master Signals

```http
GET /api/master-signal/batch?tickers=AAPL,GOOGL,MSFT&user_id=1
```

**Response:**

```json
{
  "results": [
    {"ticker": "AAPL", "buy_confidence": 85.5, ...},
    {"ticker": "GOOGL", "buy_confidence": 72.0, ...},
    {"ticker": "MSFT", "buy_confidence": 68.0, ...}
  ],
  "count": 3
}
```

#### 3. Action Center - Top Opportunities

```http
GET /api/action-center/opportunities?user_id=1&min_confidence=70&limit=10
```

**Response:**

```json
{
  "opportunities": [
    {
      "ticker": "AAPL",
      "buy_confidence": 85.5,
      "signal_strength": "STRONG_BUY",
      "entry_price": 185.5,
      "target_price": 205.0,
      "stop_loss": 167.0,
      "risk_reward_ratio": 2.3,
      "kelly_size": 0.15
    }
  ],
  "count": 5,
  "last_updated": "2026-01-17T14:30:00Z"
}
```

#### 4. Action Center - Full Watchlist

```http
GET /api/action-center/watchlist?user_id=1&sort_by=confidence
```

#### 5. Action Center - Summary

```http
GET /api/action-center/summary?user_id=1
```

**Response:**

```json
{
  "strong_buy_count": 5,
  "buy_count": 8,
  "weak_buy_count": 3,
  "neutral_count": 9,
  "avoid_count": 2,
  "top_opportunity": {
    "ticker": "AAPL",
    "buy_confidence": 85.5
  },
  "last_updated": "2026-01-17T14:30:00Z"
}
```

## 📈 Signal Strength Classification

| Buy Confidence | Signal Strength | Akce                |
| -------------- | --------------- | ------------------- |
| 80-100%        | **STRONG_BUY**  | ✅ Obchodovat ihned |
| 60-79%         | **BUY**         | ✅ Obchodovat       |
| 40-59%         | **WEAK_BUY**    | ⚠️ Zvážit           |
| 20-39%         | **NEUTRAL**     | 🔍 Sledovat         |
| 0-19%          | **AVOID**       | ❌ Neobchodovat     |

## 🎨 Frontend Integrace

### TypeScript Type Definitions

```typescript
interface MasterSignalResult {
  ticker: string;
  buy_confidence: number; // 0-100
  signal_strength: "STRONG_BUY" | "BUY" | "WEAK_BUY" | "NEUTRAL" | "AVOID";
  components: {
    gomes_score: number;
    ml_confidence: number;
    technical_score: number;
    gap_score: number;
    risk_reward_score: number;
  };
  verdict: string;
  blocked_reason?: string;
  entry_price?: number;
  target_price?: number;
  stop_loss?: number;
  risk_reward_ratio?: number;
  kelly_size?: number;
  calculated_at: string;
  expires_at?: string;
}

interface ActionCenterOpportunities {
  opportunities: MasterSignalResult[];
  count: number;
  last_updated: string;
}
```

### React Component Example

```tsx
import React, { useEffect, useState } from "react";

const ActionCenter: React.FC = () => {
  const [opportunities, setOpportunities] = useState<MasterSignalResult[]>([]);

  useEffect(() => {
    fetch("/api/action-center/opportunities?user_id=1&min_confidence=70")
      .then((res) => res.json())
      .then((data) => setOpportunities(data.opportunities));
  }, []);

  return (
    <div className="action-center">
      <h2>📊 Today's Opportunities</h2>
      {opportunities.map((opp) => (
        <div key={opp.ticker} className={`card ${opp.signal_strength}`}>
          <h3>{opp.ticker}</h3>
          <div className="confidence-bar">
            <div style={{ width: `${opp.buy_confidence}%` }}>{opp.buy_confidence}%</div>
          </div>
          <div className="details">
            <span>Entry: ${opp.entry_price}</span>
            <span>Target: ${opp.target_price}</span>
            <span>Stop: ${opp.stop_loss}</span>
            <span>R/R: {opp.risk_reward_ratio}:1</span>
            <span>Size: {(opp.kelly_size * 100).toFixed(1)}%</span>
          </div>
        </div>
      ))}
    </div>
  );
};
```

## 🔧 Konfigurace

### Úprava Vah

Pokud chcete změnit váhy komponent:

```python
from app.trading.master_signal import MasterSignalAggregator, WeightConfig

# Custom weight configuration
class CustomWeights:
    GOMES_SCORE = 0.40      # 40% Gomes (více váhy)
    ML_CONFIDENCE = 0.30    # 30% ML
    TECHNICAL = 0.15        # 15% Technical
    GAP_ANALYSIS = 0.10     # 10% Gap
    RISK_REWARD = 0.05      # 5% R/R

aggregator = MasterSignalAggregator(db, weights=CustomWeights())
```

## ⚠️ Důležité Poznámky

1. **Gomes Filter Priority**: Pokud ticker neprojde Gomesovým filtrem, automaticky dostává nízké skóre
2. **ML Quality**: Low-confidence ML predikce mají 50% penaltu
3. **Technical Score**: Momentálně vrací 50 (neutral) - TODO: implementovat RSI/MACD
4. **User Context**: Pokud nezadáte `user_id`, gap analysis vrací neutral (50)

## 📝 TODO - Další Vylepšení

- [ ] Implementovat RSI/MACD výpočet pro Technical Score
- [ ] Přidat sentiment analysis komponentu (news/RSS)
- [ ] Implementovat backtesting pro validaci signálů
- [ ] Přidat caching pro rychlejší response
- [ ] WebSocket real-time updates když se změní confidence
- [ ] Historical tracking změn Buy Confidence v čase

## 🧪 Testing

Unit testy jsou v `backend/app/trading/tests/test_master_signal.py`.

```bash
# Spustit testy
pytest backend/app/trading/tests/test_master_signal.py -v

# Pouze jednotkové (bez DB)
pytest backend/app/trading/tests/test_master_signal.py -v -m "not integration"
```

## 📚 Referenční Dokumentace

- [Gomes Logic](../trading/gomes_logic.py)
- [ML Engine](../trading/ml_engine.py)
- [Gap Analysis](../services/gap_analysis.py)
- [Kelly Criterion](../trading/kelly.py)
