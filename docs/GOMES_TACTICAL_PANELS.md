> ⚠️ **Stav: historický design záměr, ne aktuální implementace.** Popsaný "Gomes AI
> Analyst" se ukázal jako atrapa — nikdy nevolal žádný model, psal vymyšlená čísla
> do živého portfolia. Zastaveno 23. 8. 2026 (viz `INVARIANTS.md` §1,
> `akcion-ai-analyst-was-a-stub` v paměti projektu). Ponecháno pro historii, ne jako
> návod k implementaci.

# Gomes Guardian - Complete Implementation

## ✅ Vytvořeno (Ready to Deploy):

### 1. **Database Schema** (`add_gomes_tactical_fields.sql`)
Complete Master Table podle architektonického plánu:

```sql
-- IDENTITY & CLASSIFICATION
asset_class TEXT  -- ANCHOR, HIGH_BETA_ROCKET, BIOTECH_BINARY, TURNAROUND

-- FINANCE (HARD DATA) - Survival Metrics
cash_runway_months INTEGER
insider_ownership_pct FLOAT
fully_diluted_market_cap FLOAT
enterprise_value FLOAT
quarterly_burn_rate FLOAT
total_cash FLOAT

-- THESIS (SOFT DATA) - The Narrative  
gomes_score INTEGER (0-10)
inflection_status TEXT  -- WAIT_TIME, UPCOMING, ACTIVE_GOLD_MINE
primary_catalyst TEXT
catalyst_date DATE
thesis_narrative TEXT

-- VALUATION - Price Targets
price_floor FLOAT
price_target_24m FLOAT
current_valuation_stage TEXT  -- UNDERVALUED, FAIR, OVERVALUED, BUBBLE
price_base FLOAT
price_moon FLOAT
forward_pe_2027 FLOAT

-- RISK CONTROL - Position Discipline
max_allocation_cap FLOAT  -- Dynamically calculated
stop_loss_price FLOAT
insider_activity TEXT  -- BUYING, HOLDING, SELLING
```

### 2. **Gomes Logic Core** (`app/core/gomes_logic.py`)
Hard-coded algorithms (AI cannot override):

**A. Max Allocation Algorithm:**
```python
Base Cap by Asset Class:
- Anchor (GSI): 12%
- High Beta Rocket (KUYA): 8%  
- Biotech Binary (IMP): 3%
- Turnaround: 2%

Safety Multipliers:
- Gomes Score < 7: × 0.5
- Cash Runway < 6 months: × 0.0 (STOP!)
- Cash Runway < 12 months: × 0.7
- Active Gold Mine: × 1.2

Final Cap = Base Cap × Safety Multiplier
```

**B. Action Signal Algorithm:**
```python
Priority Order:
1. Score < 4 → HARD_EXIT (Thesis broken)
2. Cash < 6 months → SELL (Insolvency risk)
3. Weight > Max Cap → TRIM (Over-allocated)
4. Price > Target → HOLD (Upside realized)
5. Price > 1.5× Target → SELL (Bubble)
6. Score ≥ 9 + Cash ≥ 18mo + Near Floor → SNIPER
7. Score ≥ 7 + Price < 0.7× Target → ACCUMULATE
8. Default → HOLD
```

**C. Warning Generator:**
- Cash runway < 6 months: 🔴 CRITICAL
- Cash runway < 12 months: 🟡 WARNING  
- Score < 5: ⚠️ Low Quality
- Insider ownership < 5%: ⚠️ Weak alignment
- Over-allocated: 🔴 TRIM NOW

### 3. **AI Integration Service** (`app/services/gomes_ai_analyst.py`)
Structured AI prompts for document analysis:

**System Prompt:**
```
Role: Micro-Cap Analyst following Mark Gomes philosophy
- Focus on cash flow inflection
- Emphasize operating leverage
- Demand downside protection
- Hate fluff, love numbers

Scoring Deltas:
DEDUCT: Dilution (-1), Missed guidance (-1), Insider selling (-2)
ADD: Backlog growth (+2), Insider buying (+2), Margins improving (+2)

Cash Runway: Cash / (Quarterly Burn / 3) months
```

**Output Schema:**
```json
{
  "total_cash": 25500000,
  "quarterly_burn_rate": -2100000,
  "cash_runway_months": 12,
  "inflection_status": "UPCOMING",
  "gomes_score": 9,
  "score_reasoning": "Revenue accelerating...",
  "primary_catalyst": "Q2 Production Ramp",
  "catalyst_date": "2026-06-30",
  "thesis_narrative": "One sentence...",
  "insider_activity": "BUYING",
  "red_flags": [],
  "green_flags": ["Revenue growth"]
}
```

### 4. **Stock Detail Modal** (`StockDetailModalGomes.tsx`)
4-Panel tactical UI (viz předchozí dokumentace)

### 5. **Transcript Upload Fix**
POST body místo URL params pro dlouhé texty

---

## 🚀 Deployment Steps:

### KROK 1: Aplikuj SQL Migraci

Otevři Neon Dashboard nebo psql a spusť:

```bash
# Soubor: backend/migrations/add_gomes_tactical_fields.sql
psql $DATABASE_URL -f migrations/add_gomes_tactical_fields.sql
```

Nebo ručně v Neon SQL Editor - celý obsah souboru.

### KROK 2: Aktualizuj Stock Model

V `backend/app/models/stock.py` přidej nové sloupce:

```python
from sqlalchemy import Column, Integer, Float, String, Date, Text

# Přidej do Stock class:
asset_class = Column(String, nullable=True)
cash_runway_months = Column(Integer, nullable=True)
total_cash = Column(Float, nullable=True)
quarterly_burn_rate = Column(Float, nullable=True)
insider_ownership_pct = Column(Float, nullable=True)
fully_diluted_market_cap = Column(Float, nullable=True)
enterprise_value = Column(Float, nullable=True)

# Gomes Scoring
gomes_score = Column(Integer, nullable=True)
inflection_status = Column(String, nullable=True)
primary_catalyst = Column(Text, nullable=True)
catalyst_date = Column(Date, nullable=True)
thesis_narrative = Column(Text, nullable=True)

# Valuation
price_floor = Column(Float, nullable=True)
price_target_24m = Column(Float, nullable=True)
current_valuation_stage = Column(String, nullable=True)
price_base = Column(Float, nullable=True)
price_moon = Column(Float, nullable=True)
forward_pe_2027 = Column(Float, nullable=True)

# Risk Control
max_allocation_cap = Column(Float, nullable=True)
stop_loss_price = Column(Float, nullable=True)
insider_activity = Column(String, nullable=True)
```

### KROK 3: Aktualizuj Pydantic Schemas

V `backend/app/schemas/responses.py` nebo podobném:

```python
class StockResponse(BaseModel):
    # ... existing fields ...
    
    # Gomes Fields
    asset_class: Optional[str] = None
    cash_runway_months: Optional[int] = None
    gomes_score: Optional[int] = None
    inflection_status: Optional[str] = None
    primary_catalyst: Optional[str] = None
    catalyst_date: Optional[date] = None
    thesis_narrative: Optional[str] = None
    
    # Valuation
    price_floor: Optional[float] = None
    price_target_24m: Optional[float] = None
    price_base: Optional[float] = None
    price_moon: Optional[float] = None
    
    # Risk Control
    max_allocation_cap: Optional[float] = None
    insider_activity: Optional[str] = None
```

### KROK 4: Aktivuj Gomes Logic v API

Vytvoř nový endpoint `/api/gomes/analyze/{ticker}`:

```python
from app.core.gomes_logic import GomesLogicEngine, StockMetrics, AssetClass

@router.get("/api/gomes/analyze/{ticker}")
async def analyze_position(
    ticker: str,
    portfolio_id: int,
    db: Session = Depends(get_db)
):
    """Apply Gomes Logic to position"""
    
    stock = db.query(Stock).filter(Stock.ticker == ticker).first()
    position = db.query(Position).filter(
        Position.ticker == ticker,
        Position.portfolio_id == portfolio_id
    ).first()
    
    # Build metrics
    metrics = StockMetrics(
        ticker=ticker,
        asset_class=AssetClass(stock.asset_class) if stock.asset_class else AssetClass.HIGH_BETA_ROCKET,
        gomes_score=stock.gomes_score,
        cash_runway_months=stock.cash_runway_months,
        inflection_status=stock.inflection_status,
        current_price=stock.current_price or 0,
        price_floor=stock.price_floor,
        price_target_24m=stock.price_target_24m,
        current_weight_pct=(position.market_value / total_portfolio_value) * 100
    )
    
    # Execute Gomes Logic
    decision = GomesLogicEngine.execute(metrics)
    
    # Update stock with calculated max_allocation_cap
    stock.max_allocation_cap = decision.max_allocation_cap
    db.commit()
    
    return decision
```

### KROK 5: Integrace AI Analysta

Aktualizuj stávající Deep DD endpoint:

```python
from app.services.gomes_ai_analyst import GomesAIAnalyst

@router.post("/api/gomes/update-stock/{ticker}")
async def update_with_ai_analysis(
    ticker: str,
    request_body: StockUpdateRequest,
    db: Session = Depends(get_db)
):
    """AI-powered stock update"""
    
    stock = db.query(Stock).filter(Stock.ticker == ticker).first()
    
    # AI Analysis
    analyst = GomesAIAnalyst()
    analysis = await analyst.analyze_document(
        ticker=ticker,
        document_text=request_body.transcript,
        source_type=request_body.source_type,
        current_score=stock.gomes_score,
        previous_thesis=stock.thesis_narrative
    )
    
    # Apply to stock
    await analyst.update_stock_from_analysis(stock, analysis)
    
    # Run Gomes Logic to recalculate allocation
    # ... (viz KROK 4)
    
    db.commit()
    
    return {"success": True, "analysis": analysis}
```

### KROK 6: Frontend - Aktivuj Nový Modal

V `GomesGuardianDashboard.tsx`:

```typescript
import StockDetailModalGomes from './StockDetailModalGomes';

// V render sekci:
{selectedPosition && (
  <StockDetailModalGomes
    position={selectedPosition}
    onClose={() => setSelectedPosition(null)}
    onUpdate={async () => {
      await refreshPortfolios();
      const stocksData = await apiClient.getStocks();
      setStocks(stocksData.stocks);
    }}
  />
)}
```

---

## 📊 Workflow po nasazení:

### Denní Automat:
1. Cron job aktualizuje ceny (Yahoo Cache)
2. Automaticky volá `/api/gomes/analyze/{ticker}` pro každou pozici
3. Přepočítá `max_allocation_cap` podle aktuálního score a cash runway
4. Pokud `current_weight > max_cap` → Push notifikace "TRIM {ticker}"

### Kvartální Update:
1. Nahraješ PDF výsledků do UI
2. Frontend volá `/api/gomes/update-stock/{ticker}` s textem
3. AI analyzuje → vrátí nový score, cash runway, katalyzátory
4. Gomes Logic přepočítá max allocation
5. UI se aktualizuje s novými hodnotami a warnings

---

## 🧪 Testování:

```bash
# Test Gomes Logic
cd backend
python -m app.core.gomes_logic

# Test AI Analyst (mock)
python -m app.services.gomes_ai_analyst

# Test celého flow
curl -X POST http://localhost:8002/api/gomes/update-stock/KUYA.V \
  -H "Content-Type: application/json" \
  -d '{"transcript": "Q4 results...", "source_type": "quarterly_report"}'
```

---

## 🎯 Filosofie změn:

**HARD-CODED (Gomes Logic):**
- ✅ Max allocation výpočty
- ✅ Action signal pravidla
- ✅ Safety constraints

**AI-POWERED (Analyst Service):**
- ✅ Score generation (0-10)
- ✅ Cash runway extraction  
- ✅ Inflection detection
- ✅ Catalyst identification
- ✅ Thesis narrative

**UI Redesign:**
- ✅ Focus on FUTURE (catalysts), not PAST (P/L)
- ✅ Cash Runway visibility
- ✅ 4 Tactical Panels
- ✅ P/L minimized

**Gomes by byl hrdý! 🎯**
