> ⚠️ **Stav: historické k únoru 2026, neaktuální.** Popisuje 5fázový lifecycle
> (kánon má 3) a 15% strop podle conviction skóre (aktuální je 10% strop Primary
> tieru). Aktuální metodika: [`DOMAIN_MODEL.md`](DOMAIN_MODEL.md).

# 🎯 AKCION - Product Overview

**Verze:** 2.0.0 | **Datum:** Únor 2026

---

## 📋 Executive Summary

**Akcion** je fiduciární investiční platforma pro správu rodinného portfolia small-cap akcií. Kombinuje AI-powered analýzu s metodologií profesionálního investora Marka Gomese ("Money Mark").

### Klíčová hodnota
> *"Family financial security depends on accurate analysis"*

Platforma pomáhá investorům:
- ✅ Sledovat a analyzovat small-cap akcie s vysokým potenciálem růstu
- ✅ Rozhodovat kdy KOUPIT, DRŽET nebo PRODAT na základě dat, ne emocí
- ✅ Řídit riziko pomocí price lines a position sizing
- ✅ Automaticky monitorovat změny v investičních tezích

---

## 🏗️ Architektura systému

```
┌─────────────────────────────────────────────────────────────┐
│                    FRONTEND (React 18 + TypeScript)         │
│  • Portfolio Dashboard    • Stock Detail Modal              │
│  • Watchlist             • Analysis Terminal                │
│  • Notifications         • Family Audit                     │
└─────────────────────────────────────────────────────────────┘
                              ↓ REST API
┌─────────────────────────────────────────────────────────────┐
│                    BACKEND (Python 3.12 + FastAPI)          │
│  • Master Signal Engine   • AI Analysis (Gemini 2.0)        │
│  • Gomes Intelligence     • Yahoo Finance Integration       │
│  • Position Sizing        • Notification Service            │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                    DATABASE (PostgreSQL / Neon.tech)        │
│  • Stocks & Watchlist    • Portfolios & Positions           │
│  • Score History         • Analysis Logs                    │
└─────────────────────────────────────────────────────────────┘
```

---

## 🎨 Hlavní obrazovky a funkce

### 1. Portfolio Dashboard
**Účel:** Přehled celého portfolia na první pohled

| Komponenta | Funkce |
|------------|--------|
| Portfolio Cards | Karty jednotlivých portfolií (Family Office, Speculative, atd.) |
| Family Audit | Agregovaný přehled napříč všemi portfolii |
| Quick Stats | Celková hodnota, P/L, distribuce |

### 2. Stock Detail Modal (Trading Deck)
**Účel:** Kompletní analýza jedné akcie pro rozhodnutí

| Sekce | Data |
|-------|------|
| **Inflection Engine** | Lifecycle fáze, conviction score, next catalyst |
| **Trading Deck** | Price lines (Floor/Base/Moon), visual slider, R/R ratio |
| **Position Command** | Doporučená alokace, trim/add signals |
| **Legend (ℹ️)** | Vysvětlivky pojmů (collapsible popup) |

### 3. Watchlist
**Účel:** Sledování potenciálních nákupů

| Funkce | Popis |
|--------|-------|
| Stock Cards | Rychlý přehled: ticker, score, verdict, price zone |
| Add Analysis | Vložení transkriptu/YouTube pro AI analýzu |
| Quick Actions | Přesunutí do portfolia, update analysis |

### 4. Investment Terminal
**Účel:** Hromadná analýza transkriptů

| Funkce | Popis |
|--------|-------|
| Multi-source input | YouTube URL, manuální transkript, Google Docs |
| Batch extraction | AI extrahuje všechny tickery z textu |
| Auto-categorization | Zařazení do portfolia nebo watchlistu |

### 5. Notification Bell
**Účel:** Upozornění na důležité události

| Typ notifikace | Trigger |
|----------------|---------|
| Entry Zone Alert | Cena vstoupila do buy zóny |
| Thesis Drift | Změna v investiční tezi |
| Catalyst Alert | Blížící se katalyzátor |
| Risk Warning | Cash runway < 6 měsíců |

---

## 🧠 Gomes Investment Methodology

### Master Signal v2.0 (3 Pillars)

| Pilíř | Váha | Popis |
|-------|------|-------|
| **Thesis Tracker** | 60% | Milníky vs Red Flags, progrese příběhu |
| **Valuation & Cash** | 25% | Cash runway, valuace, dilution risk |
| **Weinstein Guard** | 15% | Technická fáze (Phase 1-4), 30 WMA |

### Lifecycle Phases

| Fáze | Popis | Akce |
|------|-------|------|
| **WAIT_TIME** | Thesis nepotvrzena, čekáme na katalyzátor | WATCH pouze |
| **APPROACHING** | Katalyzátor blízko, připravit pozici | ACCUMULATE |
| **GOLD_MINE** | Thesis potvrzena, monetizace běží | BUY/ADD agresivně |
| **MATURE** | Růst zpomaluje, valuace plná | HOLD/TRIM |
| **DECLINING** | Thesis zlomená nebo vyčerpaná | SELL/AVOID |

### Price Lines (Traffic Light System)

| Linie | Význam | Akce |
|-------|--------|------|
| 🟢 **Green Line** | Undervalued, buy zone | Agresivní nákup |
| ⚪ **Base Price** | Fair value | Hold |
| 🔴 **Red Line** | Overvalued, sell zone | Trim/Sell |
| ⚫ **Grey Line** | Danger zone, thesis broken | Stop-loss |

### Conviction Score (1-10)

| Skóre | Interpretace | Maximální alokace |
|-------|--------------|-------------------|
| 9-10 | Exceptional, table-pounding buy | 15% |
| 7-8 | Strong conviction | 10% |
| 5-6 | Speculative, binary outcome | 5% |
| 3-4 | High risk, weak fundamentals | 2% |
| 1-2 | Broken thesis, avoid | 0% |

---

## 🤖 AI Intelligence Engine

### Gemini 2.0 Flash Integration

| Funkce | Popis |
|--------|-------|
| **Transcript Analysis** | Extrakce tickerů, sentimentu, price targets z videa/textu |
| **Deep Due Diligence** | 6-pilířová Gomes analýza pro jednotlivý ticker |
| **Thesis Drift Detection** | Porovnání nových dat s původní tezí |
| **Price Line Estimation** | Odhad green/red lines pokud nejsou explicitní |

### Universal Intelligence Unit

| Typ zdroje | Spolehlivost | Logika |
|------------|--------------|--------|
| Official Filing (10-K, 10-Q) | 100% | Tvrdá data, bez interpretace |
| Analyst Report | 70% | Kvalifikovaný názor |
| Chat/Discussion | 30% | Rumors, sentiment only |
| YouTube Transcript | 50% | Závisí na speakerovi |

---

## 📊 Datový model (klíčové entity)

### Stock
```
ticker, company_name, conviction_score, action_verdict,
green_line, red_line, price_zone, inflection_status,
cash_runway_months, insider_activity, next_catalyst,
thesis_narrative, edge, catalysts, risks
```

### Position
```
ticker, shares_count, avg_cost, current_price, market_value,
unrealized_pl, unrealized_pl_percent, portfolio_id
```

### Portfolio
```
name, owner, type (FAMILY_OFFICE | SPECULATIVE | LONG_TERM),
total_value, monthly_contribution
```

---

## 🔧 Současný stav a známé limitace

### ✅ Funguje
- Portfolio management (CRUD)
- Stock analysis via AI
- Price lines visualization (Trading Deck)
- Watchlist management
- Notifications system
- Yahoo Finance price updates

### ⚠️ Částečně funguje
- Automatické price line estimation (nově přidáno)
- Multi-portfolio family audit
- Historical P/L tracking

### ❌ Chybí / TODO
- Mobile responsive design (částečně)
- Automatické alertsy na email/Telegram (backend ready, frontend chybí)
- Backtesting modul
- Export do Excel/PDF
- Dark/Light theme switch

---

## 🚀 Typický user flow

### 1. Nový uživatel
```
1. Vytvoří portfolio (Family Office)
2. Importuje pozice z brokera (CSV) nebo ručně přidá
3. Systém načte ceny z Yahoo Finance
```

### 2. Analýza nové akcie
```
1. Najde video Marka Gomese o tickeru
2. Vloží YouTube URL do Investment Terminal
3. AI extrahuje: ticker, score, price targets, catalysts, risks
4. Akcie se přidá do Watchlistu nebo Portfolia
```

### 3. Denní rutina
```
1. Otevře dashboard → vidí přehled portfolia
2. Zkontroluje Notification Bell → nové alerty?
3. Klikne na akcii → Trading Deck ukazuje aktuální zónu
4. Rozhodne: HOLD / ADD / TRIM
```

### 4. Update analýzy
```
1. Vyjde nové video/earnings call
2. Otevře stock detail → "Přidat analýzu z transkriptů"
3. Vloží text → AI porovná s původní tezí
4. Systém updatuje score a detekuje thesis drift
```

---

## 📈 Metriky úspěchu

| Metrika | Cíl | Měření |
|---------|-----|--------|
| Přesnost AI skóre | >80% shoda s manuální analýzou | A/B test |
| Rychlost rozhodnutí | <5 min per stock | UX tracking |
| False positive rate (alerts) | <10% | User feedback |
| Portfolio outperformance | >S&P 500 | Backtest |

---

## 🎯 Další kroky pro zjednodušení

### Priority 1 (Quick Wins)
1. **Zjednodušit Trading Deck** - méně čísel, více vizuálu
2. **Onboarding wizard** - průvodce pro nové uživatele
3. **Keyboard shortcuts** - rychlá navigace pro power users

### Priority 2 (Medium Effort)
1. **Mobile view** - responsive design pro telefon
2. **Bulk actions** - hromadné operace na watchlistu
3. **Export** - PDF report pro jednotlivou akcii

### Priority 3 (Long Term)
1. **Telegram bot** - notifikace do mobilu
2. **Backtesting** - historická analýza signálů
3. **API pro 3rd party** - integrace s brokery

---

## 📞 Kontakt

**Vývojový tým:** GitHub Copilot + Claude Opus 4.5  
**Product Owner:** [Vaše jméno]  
**Repository:** `c:\Users\reath\Projects\Akcion`

---

*Dokument vytvořen: 1. února 2026*
