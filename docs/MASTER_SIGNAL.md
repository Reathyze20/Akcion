> ⚠️ **Stav: historické, neaktuální.** Master Signal (`app/trading/master_signal.py`)
> byl 24. 8. 2026 odpojen z appky — soupeřící engine, jehož "Weinstein fáze" četla
> zelenou čáru jako klouzavý průměr. Weinstein je dnes 0% váhy, jen informační
> odznak. Viz [`DOMAIN_MODEL.md`](DOMAIN_MODEL.md) a
> [`KNOWN_ISSUES.md`](KNOWN_ISSUES.md) bod 26.

# Master Signal v2.0 - 3-Pillar System

## 🎯 Přehled

**Master Signal v2.0** je zjednodušený systém pro micro-cap investování podle metodologie Marka Gomese.

### Co bylo odstraněno (a proč)

| Komponenta | Důvod odstranění |
|------------|------------------|
| **ML/PatchTST** | Micro-capy jsou nepředvídatelné. GSI udělá +100% za den po oznámení kontraktu - žádný model tohle z historického grafu nevidí. |
| **Sentiment Analysis** | O GKPRF nepíše Bloomberg. Sentiment = placené PR zprávy. |
| **RSI/MACD** | 10k shares/day volume = šum, ne signál. |
| **Backtesting** | Spread 5-10% u micro-capů zkresluje simulaci. |

---

## 📊 Nový 3-Pilířový Systém

```
┌─────────────────────────────────────────────────────────────┐
│                    MASTER SIGNAL v2.0                        │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ 1. THESIS TRACKER (60%)                             │    │
│  │    • Gemini Pro + Transkripty                       │    │
│  │    • Milníky (Contracts, Certifications, Revenue)   │    │
│  │    • Červené vlajky (Dilution, Delays, Leadership)  │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ 2. VALUATION & CASH (25%)                           │    │
│  │    • Cash on Hand                                   │    │
│  │    • Debt                                           │    │
│  │    • Burn Rate → Runway < 6 měsíců = RED FLAG       │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ 3. WEINSTEIN TREND GUARD (15%)                      │    │
│  │    • 30 WMA (Weekly Moving Average)                 │    │
│  │    • Pod klesající? → NEKUPOVAT                     │    │
│  │    • Nad rostoucí? → KUPOVAT                        │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

---

## 🚀 API Použití

### Get Master Signal

```http
GET /api/master-signal/GKPRF
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
      "runway_status": "HEALTHY",
      "dilution_risk": false
    },
    "weinstein_guard": {
      "score": 55.0,
      "phase": "PHASE_2_ADVANCE",
      "price": 0.45,
      "wma_30": 0.42,
      "price_vs_wma_pct": 7.1
    }
  },
  "blocked": false,
  "verdict": "BUY"
}
```

---

## 🚫 Blocking Rules

Systém automaticky blokuje nákup v těchto situacích:

1. **Weinstein Phase 4**: Cena pod klesající 30 WMA → DO NOT BUY
2. **Cash Runway < 6 měsíců**: Vysoké riziko ředění → AVOID
3. **3+ Red Flags**: Příliš mnoho varovných signálů → AVOID

---

## 📈 Weinstein Phases

| Phase | Popis | Akce |
|-------|-------|------|
| **Phase 1 (Base)** | Cena pod WMA, ale WMA se zvedá | WATCH |
| **Phase 2 (Advance)** | Cena nad rostoucí WMA | **BUY** ✅ |
| **Phase 3 (Top)** | Cena nad WMA, ale WMA klesá | SELL |
| **Phase 4 (Decline)** | Cena pod klesající WMA | **AVOID** ❌ |

---

## 💰 Cash Runway Status

| Status | Runway | Riziko ředění |
|--------|--------|---------------|
| **HEALTHY** | > 12 měsíců | Nízké |
| **CAUTION** | 6-12 měsíců | Střední |
| **DANGER** | < 6 měsíců | **Vysoké** ⚠️ |

---

## 🔧 Python Usage

```python
from app.trading.master_signal import calculate_master_signal_v2

# Calculate for single ticker
result = calculate_master_signal_v2(db, "GKPRF")

print(f"Buy Confidence: {result.buy_confidence}%")
print(f"Signal: {result.signal_strength.value}")
print(f"Blocked: {result.blocked}")
print(f"Runway: {result.components.valuation_cash.runway_months} months")
print(f"Weinstein Phase: {result.components.weinstein_guard.phase.value}")
```

---

## 📋 Dependencies Removed

**Smazáno z requirements.txt:**
- `torch==2.1.2` (~2GB)
- `torchvision==0.16.2`
- `torchaudio==2.1.2`
- `neuralforecast==1.6.4`
- `statsforecast==1.6.0`
- `datasetsforecast==0.0.8`
- `scikit-learn==1.3.2`
- `ta==0.11.0` (technical analysis)
- `redis==5.0.1` (not needed)

**Úspora:** ~2.5 GB dependencies
