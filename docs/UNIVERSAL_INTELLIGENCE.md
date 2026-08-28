> ⚠️ **Status: historical, stale.** The specific reliability percentages (Filing
> 100% / Analyst 60% / Chat 30%) are from the Gemini era. The underlying idea —
> tiering source reliability — survives as `source_key` and the dual-source cap
> matrix. See [`DOMAIN_MODEL.md`](DOMAIN_MODEL.md) — "Two sources".

# Universal Intelligence Unit

**Multi-Source Context-Aware Analysis System**

---

## 📋 Overview

Universal Intelligence Unit je pokročilý analytický systém, který automaticky detekuje typ vstupního zdroje a aplikuje **odlišnou logiku podle spolehlivosti**:

| Source Type | Reliability | Extraction Strategy |
|------------|-------------|---------------------|
| **Official Filing** | 100% | Extrahuj tvrdá čísla (cash, revenue, dates), penalty za chybějící data |
| **Press Release** | 100% | Stejné jako Filing, ale skeptický k vágním prohlášením |
| **Analyst Report** | 60% | Extrahuj price targets, porovnej s aktuální tezí |
| **Chat Discussion** | 30% | Identifikuj key voices, ignoruj hype, flaguj rumors |
| **Article/Manual** | 50% | Balanced approach |

---

## 🎯 Key Features

### 1. **Automatic Source Detection**

AI analyzuje vstupní text a určí typ zdroje:

```
Input: "Q3 2025 Results: Revenue $2.1M, Cash $8.2M"
→ Detected: OFFICIAL_FILING (100% reliability)

Input: "Florian: Not sure they planned it this way..."
→ Detected: CHAT_DISCUSSION (30% reliability)
```

### 2. **Context-Aware Extraction**

Podle typu zdroje se mění **co a jak** extrahujeme:

**Official Filing:**
- ✅ Priority: Cash, Revenue, Guidance, Dates
- ❌ Penalty: Missing Cash → Score cap at 5
- ❌ Penalty: Missing Catalyst → -2 points

**Chat Discussion:**
- ✅ Priority: Sentiment shifts, Key voices (Florian, Gomes, Josh)
- ✅ Flag: Rumors vs Confirmed info
- ⚠️ Management credibility alerts
- ❌ Ignore: Pure hype without substance

**Analyst Report:**
- ✅ Priority: Price target changes, Thesis shifts
- ⚠️ Skepticism: Verify against hard data
- ❌ Downweight: Upgrades without new data

### 3. **Nested JSON Output**

```json
{
  "ticker": "KUYA.V",
  "meta_info": {
    "detected_source_type": "CHAT_DISCUSSION",
    "confidence_level": "Medium",
    "source_reliability": "30%",
    "key_voices_mentioned": ["Florian", "Josh"]
  },
  "inflection_updates": {
    "thesis_sentiment_shift": "Negative",
    "key_takeaways_bullets": [
      "Key voice Florian doubts management competence",
      "RUMOR: Guidance pushed from 2025 to 2026"
    ],
    "potential_catalyst": "UNCONFIRMED: 2026 timeline mentioned",
    "management_credibility_alert": "Trusted investor questions if success was planned or luck"
  },
  "financial_updates": {
    "cash_runway_status": "UNCHANGED",
    "cash_runway_months": null,
    "revenue_guidance": "DELAYED TO 2026 (Unconfirmed)",
    "insider_activity": "UNKNOWN"
  },
  "score_impact_recommendation": {
    "gomes_score": 6,
    "direction": "Downgrade",
    "reasoning": "Management credibility questioned by lead investors. Timeline delay implies Dead Money risk. Chat source = low reliability but sentiment shift is significant.",
    "suggested_adjustment": -1,
    "confidence": "Medium"
  },
  "thesis_narrative": "Strong assets but execution concerns raised by trusted investors.",
  "inflection_status": "WAIT_TIME",
  "recommendation": "HOLD"
}
```

---

## 🧠 Decision Tree

### Official Filing/Press Release (100%)

```
IF Cash data present:
  → Base score = Evaluate fundamentals objectively
  → Strong results → Can justify score 8-10
ELSE:
  → Score -= 3
  → Cap score at 5
  → Output: "UNKNOWN - DATA GAP"

IF Catalyst present:
  → Base score unchanged
ELSE:
  → Score -= 2
  → Force stage: "WAIT_TIME"
```

### Chat Discussion (30%)

```
IF Negative sentiment from Key Voices:
  → Score -= 1
  → Flag: Management credibility alert

IF Timeline delays rumored:
  → Score -= 1
  → Add: "UNCONFIRMED" flag

IF Pure hype without substance:
  → Ignore, no score change

IF Positive but vague:
  → Do NOT upgrade (insufficient evidence)
```

### Analyst Report (60%)

```
IF Downgrade with logic:
  → Score -= 1 to -2
  → Consider thesis change

IF Upgrade without new data:
  → Score += 1 maximum (skepticism)

IF Contradicts official filing:
  → Prioritize official data
```

---

## 📡 API Usage

### Endpoint

```
POST /api/intelligence/analyze-ticker?use_universal_prompt=true
```

### Request Body

```json
{
  "ticker": "KUYA.V",
  "source_type": "transcript",
  "input_text": "Full text from video/filing/chat...",
  "investor_name": "Mark Gomes",
  "analysis_date": "2026-01-25"
}
```

### Response

```json
{
  "ticker": "KUYA.V",
  "warning_level": "WARNING",
  "gomes_score": 6,
  "inflection_status": "WAIT_TIME",
  "thesis_narrative": "Strong assets but execution concerns...",
  "next_catalyst": "UNCONFIRMED: 2026 timeline",
  "cash_runway_status": "UNCHANGED",
  "recommendation": "HOLD",
  "updated_at": "2026-01-25T10:30:00Z",
  "warning_messages": [
    "📢 CHAT DISKUZE - Spolehlivost 30%",
    "⚠️ Management: Trusted investor questions if success was planned or luck",
    "🔮 RUMOR: Catalyst datum není potvrzený"
  ]
}
```

---

## 🛡️ Safety Mechanisms

### 1. **Data Gap Detection**

```
Official Filing without Cash data:
→ Output: "UNKNOWN - DATA GAP"
→ Score capped at 5
→ Warning: "🚨 CHYBÍ FINANČNÍ DATA - Ochranný mechanismus aktivován"
```

### 2. **Rumor Flagging**

```
Chat Discussion with unconfirmed dates:
→ Catalyst: "UNCONFIRMED: Q1 2026 Production"
→ Warning: "🔮 RUMOR: Catalyst datum není potvrzený"
```

### 3. **Management Credibility**

```
Key voices doubting management:
→ Alert: "management_credibility_alert"
→ Warning: "⚠️ Management: [description]"
→ Score adjustment: -2 points
```

---

## 💡 Use Cases

### Use Case 1: Official Q3 Results

**Input:**
```
Q3 2025 Results: Revenue $2.1M (+40% YoY), 
Cash $8.2M (18 months runway), 
Production target Q1 2026
```

**AI Response:**
- Detected: OFFICIAL_FILING (100%)
- Score: 8 (strong cash + catalyst)
- Catalyst: "Q1 2026 Production Target"
- Cash: 18 months runway (Safe)

### Use Case 2: Chat Discussion with Doubt

**Input:**
```
Florian: Not sure they planned it this way, just got lucky. 
Guidance for 2025 is now 2026.
Josh: Solid business though.
```

**AI Response:**
- Detected: CHAT_DISCUSSION (30%)
- Key Voices: Florian (skeptical), Josh (bullish)
- Score: 6 (downgrade from 7)
- Alert: Management credibility questioned
- Catalyst: UNCONFIRMED: 2026 timeline

### Use Case 3: Vague Press Release

**Input:**
```
Press Release: New marketing campaign launched. 
Exciting growth ahead!
```

**AI Response:**
- Detected: PRESS_RELEASE (100%)
- Score: 5 (capped - no financials)
- Cash: UNKNOWN - DATA GAP
- Warning: "Official source but MISSING FINANCIALS"

---

## 🔧 Implementation

### Backend

**File:** `backend/app/core/prompts_universal_intelligence.py`

**Key Function:**
```python
def get_sentiment_alert_level(sentiment: str, source_type: str) -> str:
    reliability = SOURCE_RELIABILITY.get(source_type, 50)
    
    if sentiment == "Critical Warning":
        return "CRITICAL"
    elif sentiment == "Negative" and reliability >= 60:
        return "WARNING"
    elif sentiment == "Negative" and reliability < 60:
        return "INFO"  # Chat rumors need verification
    else:
        return "OK"
```

### Frontend

**File:** `frontend/src/components/StockDetailModalGomes.tsx`

**Features:**
- Source type selector (YouTube/Transcript/Manual)
- Dynamic placeholder examples per source
- Info box explaining source detection
- Warning display for low-reliability sources

---

## 📊 Reliability Matrix

| Source | Reliability | Trust Level | Score Impact |
|--------|-------------|-------------|--------------|
| Official Filing | 100% | ✅ Full Trust | Can justify 8-10 |
| Press Release | 100% | ✅ Full Trust | But skeptical to vague claims |
| Analyst Report | 60% | ⚠️ Moderate | Max +1 without new data |
| Article | 50% | ⚠️ Moderate | Balanced approach |
| Chat Discussion | 30% | ❌ Low | -1 to -2 on negative sentiment |
| Manual Notes | 50% | ⚠️ Moderate | User-provided context |

---

## ⚠️ Limitations

1. **AI cannot infer market calendar** - You must manually add catalyst dates (e.g., "Q1 High-Grade Sales")
2. **Chat sentiment needs context** - AI flags rumors but cannot verify independently
3. **Analyst bias** - AI cannot detect analyst conflicts of interest
4. **Language barriers** - Best performance with English inputs

---

## 🎯 Best Practices

### DO:
✅ Use Official Filings for score upgrades (8-10)  
✅ Flag rumors from Chat Discussions  
✅ Manually verify catalyst dates  
✅ Cross-reference multiple sources  

### DON'T:
❌ Upgrade score based solely on Chat hype  
❌ Ignore Data Gap warnings  
❌ Trust unconfirmed catalyst dates  
❌ Mix source types in one input  

---

## 📚 Related Documentation

- [Logical Validation](./LOGICAL_VALIDATION.md) - Score 9+ requires Catalyst
- [Gomes Rules](./GOMES_RULES.md) - Core investment principles
- [API Reference](./README.md) - Complete API documentation

---

**Author:** Akcion Development Team  
**Last Updated:** January 25, 2026  
**Version:** 1.0
