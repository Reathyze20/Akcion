# Logical Validation System

**Automatic Detection of Investment Logic Errors**

---

## 📋 Overview

Logical Validation System je bezpečnostní mechanismus, který detekuje **logické rozpory** v investiční analýze a upozorňuje uživatele na nekompletní data.

### Primary Rule

> **Score 9+ vyžaduje konkrétní Catalyst**

Pokud AI přidělí vysoké skóre (9 nebo 10) ale nezaregistruje **konkrétní katalyzátor s datem**, aplikace zobrazí **žluté varování**.

---

## 🎯 Why It Matters

### Problem: AI Blind Spots

AI je skvělá na **čtení textu**, ale špatná na **domýšlení kontextu**:

```
❌ AI nemůže odvodit:
"Po Těžbě následuje Prodej a po Prodeji následuje Report"

✅ AI umí extrahovat:
"Q1 2026 Mining Complete" → Catalyst detected
```

### Real Example: KUYA

**Scénář:**
```
AI analýza transkriptu:
- Gomes Score: 9/10
- Těžba dokončena: ✅ Q1 2026
- Next Catalyst: ❌ (prázdné)
```

**Logical Error:**
```
⚠️ Score 9 není obhajitelné bez konkrétního katalyzátoru!

Bez katalyzátoru → Cena stagnuje nebo padá (Dead Money)
```

**Solution:**
```
Uživatel ručně doplní:
Next Catalyst: "Q1 2026 High-Grade Silver Sales Report"

→ Žluté varování zmizí ✅
→ Score 9 je nyní obhajitelný ✅
```

---

## 🛡️ Validation Rules

### Rule 1: High Score Requires Catalyst

```python
IF gomes_score >= 9:
    IF next_catalyst is empty OR contains "NO CATALYST":
        → TRIGGER WARNING: "LOGICAL ERROR"
        → Display yellow alert box
        → Log warning to backend
```

### Rule 2: Score Justification

```
Score 1-4: Low conviction → Catalyst optional
Score 5-6: Moderate → Catalyst recommended
Score 7-8: High → Catalyst strongly recommended
Score 9-10: Premium → Catalyst REQUIRED ⚠️
```

---

## 📡 Implementation

### Backend Validation

**File:** `backend/app/routes/intelligence_gomes.py`

```python
# Universal Mode
if gomes_score >= 9 and ("NO CATALYST" in next_catalyst.upper() or not next_catalyst.strip()):
    warning_msgs.append(
        "⚠️ LOGICAL ERROR: High Score (9+) but No Catalyst. "
        "Score není obhajitelné bez konkrétního katalyzátoru. "
        "Doplň ručně (např. 'Q1 High-Grade Sales')."
    )
    logger.warning(f"Logical error detected for {request.ticker}: Score {gomes_score} but catalyst: {next_catalyst}")

# Legacy Mode
if gomes_score >= 9 and ("NO CATALYST" in next_catalyst.upper() or not next_catalyst.strip()):
    warning_msgs.append(
        "⚠️ LOGICAL ERROR: High Score (9+) but No Catalyst. "
        "Score není obhajitelné bez konkrétního katalyzátoru. "
        "Doplň ručně (např. 'Q1 High-Grade Sales')."
    )
    logger.warning(f"Logical error detected for {request.ticker}: Score {gomes_score} but catalyst: {next_catalyst}")
```

### Frontend Warning Display

**File:** `frontend/src/components/StockDetailModalGomes.tsx`

```tsx
{/* LOGICAL ERROR WARNING: High Score but No Catalyst */}
{position.gomes_score >= 9 && 
 (!position.next_catalyst || position.next_catalyst.toUpperCase().includes('NO CATALYST')) && (
  <div className="mt-2 bg-yellow-500/20 border border-yellow-500/60 rounded-lg p-2">
    <div className="flex items-start gap-2">
      <AlertTriangle className="w-4 h-4 text-yellow-400 flex-shrink-0 mt-0.5" />
      <div className="text-[10px] text-yellow-200 leading-tight">
        <strong className="text-yellow-300 font-bold">⚠️ LOGICAL ERROR:</strong> 
        High Score ({position.gomes_score}/10) but No Catalyst.
        <br />
        <span className="text-yellow-300/80">
          Score není obhajitelné bez konkrétního katalyzátoru. 
          Doplň ručně (např. "Q1 High-Grade Sales").
        </span>
      </div>
    </div>
  </div>
)}
```

---

## 🎨 UI/UX Design

### Yellow Warning Box

**Position:** Directly below "Next Catalyst" section in Inflection Engine

**Visual:**
```
┌────────────────────────────────────────────┐
│ NEXT CATALYST                               │
│ ┌─────────────────────────────────────────┐│
│ │ ❌ No catalyst - position questionable  ││
│ └─────────────────────────────────────────┘│
│                                             │
│ ⚠️ LOGICAL ERROR:                          │
│ High Score (9/10) but No Catalyst.         │
│                                             │
│ Score není obhajitelné bez konkrétního     │
│ katalyzátoru. Doplň ručně (např.           │
│ "Q1 High-Grade Sales").                    │
└────────────────────────────────────────────┘
```

**Colors:**
- Background: `bg-yellow-500/20`
- Border: `border-yellow-500/60`
- Text: `text-yellow-200`
- Strong Text: `text-yellow-300 font-bold`

---

## 📊 Validation Matrix

| Score | Catalyst Status | Validation Result |
|-------|-----------------|-------------------|
| 1-4 | Empty | ✅ OK (Low conviction) |
| 1-4 | Present | ✅ OK |
| 5-6 | Empty | ⚠️ Warning (Recommended) |
| 5-6 | Present | ✅ OK |
| 7-8 | Empty | ⚠️ Warning (Strongly recommended) |
| 7-8 | Present | ✅ OK |
| 9-10 | Empty | 🚨 **LOGICAL ERROR** |
| 9-10 | "NO CATALYST" | 🚨 **LOGICAL ERROR** |
| 9-10 | Present | ✅ OK |

---

## 🔧 How to Fix

### Step-by-Step Fix for KUYA Example

**1. Zobrazení chyby:**
```
Dashboard → KUYA.V
- Gomes Score: 9/10
- Next Catalyst: (prázdné)
→ Žluté varování: "LOGICAL ERROR"
```

**2. Otevření editace:**
```
Klik na KUYA → Stock Detail Modal
Klik na "Edit" nebo "+ ANALÝZA"
```

**3. Doplnění katalyzátoru:**
```
Textové pole: Next Catalyst
Zadej: "Q1 2026 High-Grade Silver Sales Report"
```

**4. Uložení:**
```
Klik na "Save"
→ Žluté varování zmizí ✅
→ Score 9 je nyní validní ✅
```

---

## 💡 Use Cases

### Use Case 1: AI Miss (KUYA)

**Input:**
```
Transkript: "Těžba dokončena Q1 2026, očekáváme strong revenue..."
```

**AI Output:**
```
Gomes Score: 9
Next Catalyst: (prázdné)  ← AI nezaregistrovala "Sales Report"
```

**System Response:**
```
⚠️ LOGICAL ERROR displayed
Backend log: "Logical error detected for KUYA.V: Score 9 but catalyst: "
```

**User Action:**
```
Manually add: "Q1 2026 High-Grade Silver Sales Report"
→ Warning disappears
```

### Use Case 2: Vague Catalyst

**Input:**
```
Next Catalyst: "Soon"
```

**AI Output:**
```
Gomes Score: 9
Next Catalyst: "Soon"
```

**System Response:**
```
⚠️ Still triggers warning (too vague)
```

**User Action:**
```
Replace with: "Q2 2026 FDA Approval Expected"
→ Warning disappears
```

### Use Case 3: Multiple Catalysts

**Input:**
```
Next Catalyst: "Q1 2026 Sales + Q2 2026 Expansion"
```

**AI Output:**
```
Gomes Score: 9
Next Catalyst: "Q1 2026 Sales + Q2 2026 Expansion"
```

**System Response:**
```
✅ Valid - specific dates provided
No warning
```

---

## ⚠️ Edge Cases

### Edge Case 1: Score 8.5 (not 9)

```
Score: 8.5
Catalyst: (empty)
→ No warning triggered (threshold is >= 9)
```

**Rationale:** Score 8 is strong but not premium, catalyst recommended but not required.

### Edge Case 2: Catalyst = "TBD"

```
Score: 9
Catalyst: "TBD"
→ Warning NOT triggered (catalyst field has text)
```

**Note:** System checks for empty or "NO CATALYST", not vague values.

**Recommendation:** Consider adding validation for vague terms like "TBD", "Soon", "Upcoming" in future versions.

### Edge Case 3: Negative Catalyst

```
Score: 9
Catalyst: "Risk: Q2 Earnings Miss"
→ No warning (catalyst exists, even if negative)
```

**Rationale:** System validates presence, not sentiment of catalyst.

---

## 🎯 Best Practices

### DO:
✅ Always provide specific dates (Q1 2026, March 15th, etc.)  
✅ Include event type (Sales Report, FDA Approval, Earnings)  
✅ Update catalyst as new info arrives  
✅ Use clear language (avoid "TBD", "Soon")  

### DON'T:
❌ Leave catalyst empty for Score 9-10  
❌ Use vague terms like "Upcoming" or "Expected"  
❌ Ignore yellow warnings  
❌ Assume AI will infer calendar events  

---

## 📚 Related Documentation

- [Universal Intelligence](./UNIVERSAL_INTELLIGENCE.md) - Multi-source analysis system
- [Gomes Rules](./GOMES_RULES.md) - Core investment principles
- [API Reference](./README.md) - Complete API documentation

---

## 🔮 Future Enhancements

### Planned Features

1. **Vague Term Detection**
   - Flag: "TBD", "Soon", "Upcoming", "Expected"
   - Suggest: More specific alternatives

2. **Catalyst Type Validation**
   - Verify: Earnings, Sales, FDA, Production match company lifecycle
   - Warn: If catalyst doesn't fit company type

3. **Date Validation**
   - Check: Catalyst date is in future (not past)
   - Alert: If catalyst date already passed

4. **AI Auto-Suggestions**
   - Analyze: Company lifecycle and past patterns
   - Suggest: "Based on Q1 mining, next catalyst likely Q2 Sales"

---

**Author:** Akcion Development Team  
**Last Updated:** January 25, 2026  
**Version:** 1.0
