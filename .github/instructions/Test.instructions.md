---
applyTo: "backend/app/trading/**"
---

# Gomes Trading Strategy Implementation Guide

## Role
Jsi **Senior Algo-Trading Developer**. Tvým úkolem je převést nestrukturovaný transcript pravidel Marka Gomese (Money Mark) do robustního Python kódu.

## Cíl
Vytvořit soubor `backend/app/trading/gomes_logic.py`, který bude obsahovat třídu `GomesStrategy`. Tato třída bude fungovat jako **"Gatekeeper"** – schválí obchod jen tehdy, pokud splňuje přísná pravidla z transcriptu.

## Vstupní data
Máš k dispozici transcript videa *"How I Make Money On Stocks"*, kde Mark definuje své principy.

---

## Požadavky na implementaci (Step-by-Step)

### 1. Implementuj `MarketAlertSystem` (Semafor)

Z transcriptu víme, že existují **4 stavy trhu**. Vytvoř Enum a logiku pro alokaci aktiv:

| Alert Level | Popis | Alokace |
|-------------|-------|---------|
| 🟢 **GREEN** | Všechny systémy jedou | 100% Stocks, 0% Hedge |
| 🟡 **YELLOW** | "Market is expensive" | Prodat spekulativní + "Wait Time" akcie. Cash + Hedge (RWM) cca 20-30% |
| 🟠 **ORANGE** | "Worse than yellow" | Prodat většinu akcií. Zbytek plně hedgovat pomocí RWM (Russell 2000 Short) |
| 🔴 **RED** | "Extreme Risk" | Téměř 100% Cash nebo Hedge |

**Funkce:** `get_portfolio_allocation(alert_level: str) -> dict` (vrátí % cash, % stocks, % hedge)

---

### 2. Implementuj `StockLifecycleClassifier` (Fáze Života)

Mark definuje **3 fáze**. Toto je kritický filtr:

| Fáze | Popis | Akce |
|------|-------|------|
| **GREAT FIND** | "Dream phase." Neznámá, začíná růst | Riskantní, ale povolené |
| **WAIT TIME (KILLER)** | "Hype dies, price drops." | ⚠️ **Neinvestovat!** (Return signal=AVOID) |
| **GOLD MINE** | "Proven execution." Firma je zisková nebo má silné objednávky | ✅ Safe Buy |

**Detekce WAIT TIME:**
- Transcript obsahuje: `"delays"`, `"no orders yet"`, `"waiting for approval"`

**Detekce GOLD MINE:**
- Transcript obsahuje: `"Firing on all cylinders"`, `"Record revenue"`, `"Profitable"`

**Funkce:** `is_investable(phase: str) -> bool` (False pro WAIT_TIME)

---

### 3. Implementuj `RiskRewardCalculator` (Lines Logic)

Vytvoř logiku pro výpočet nákupních zón:

- **Green Line (BUY):** Podhodnocená úroveň
- **Red Line (SELL):** Plně ohodnocená úroveň
- **3-Point Rule:** Pokud se skóre akcie (1-10) zhorší o 3 body (např. cena vyrostla příliš rychle), doporuč "Take Profit"
- **Doubling Rule:** *"If you doubled your money, sell half."* (House Money)

---

### 4. Implementuj `PositionSizingEngine` (Velikost Pozice)

Podle minuty **50:00** v transcriptu:

| Tier | Typ pozice | Max % portfolia |
|------|------------|-----------------|
| **Primary (Core)** | Proven Gold Mine | 10% |
| **Secondary (Unofficial)** | Great Find, dating phase | Menší pozice |
| **Tertiary (FOMO/Speculative)** | Spekulativní | Max 1-2% |

> ⚠️ **Yellow Alert Constraint:** V Yellow Alertu nesmí být žádné spekulativní pozice!

---

## Výstupní Kód

Napiš kompletní Python modul `gomes_logic.py`, který bude obsahovat tyto třídy a funkce:

- Kód musí být **type-safe** (použij Pydantic)
- Musí obsahovat komentáře odkazující na konkrétní části transcriptu
  - Např.: `# Ref: Minute 31:28 - Wait Time Rule`