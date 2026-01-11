# 🚀 Návod pro vývojáře - AKCION

## ⚡ Quick Start (5 minut do funkční aplikace)

1. `git clone https://github.com/Reathyze20/Akcion.git && cd Akcion`
2. Vytvořte `.env` soubor s klíči (viz sekce Konfigurace)
3. Backend: `cd backend && python -m venv venv && .\venv\Scripts\Activate.ps1 && pip install -r requirements.txt && .\start_background.ps1`
4. Frontend: `cd frontend && npm install && npm run dev`
5. Otevřete http://localhost:5173

## 📋 Přehled projektu

AKCION je platforma pro analýzu obchodních signálů, která transformuje analýzy trhu na praktická obchodní doporučení. Aplikace využívá AI (Google Gemini) k extrakci informací z finančních dokumentů a generování konkrétních obchodních verdiktů (BUY/SELL/WATCH).

### ✅ Aktuální stav (leden 2026)

**Co funguje:**
- ✅ Backend API běží na FastAPI s PostgreSQL databází
- ✅ AI analýza pomocí Google Gemini (Portfolio Manager prompt)
- ✅ Frontend dashboard s třemi sekcemi (Top Picks, Watch List, Other Stocks)
- ✅ Obchodní signály s entry zones, targets, stop loss
- ✅ Databáze obsahuje 10+ akcií s historickými analýzami
- ✅ Real-time Google Docs analýza
- ✅ Background server skripty pro produkci

**Připraveno k vývoji:**
- 🎯 Přidávání nových analytických funkcí
- 🎯 Rozšíření UI komponent
- 🎯 Export obchodních signálů
- 🎯 Notifikace pro nové BUY signály
- 🎯 Historická data a backtesting

### Technologický stack

**Backend:**
- Python 3.12
- FastAPI 0.115.0
- PostgreSQL (Neon Database)
- SQLAlchemy 2.0.36
- Google Gemini API
- Uvicorn (ASGI server)

**Frontend:**
- React 18
- TypeScript
- Vite 7.2.5
- Tailwind CSS v3.4.1
- Lucide React (ikony)

## 🔧 Požadavky před instalací

### Softwarové požadavky
- **Python 3.12** nebo novější
- **Node.js 18+** a **npm/yarn**
- **Git** pro verzování
- **PostgreSQL** (poskytuje Neon cloud)
- **PowerShell** (pro Windows skripty)

### API klíče
- **Google Gemini API klíč** - pro AI analýzu
- **Neon PostgreSQL** - připojovací řetězec k databázi

## 📦 Instalace projektu

### 1. Klonování repozitáře

```bash
git clone https://github.com/Reathyze20/Akcion.git
cd Akcion
```

### 2. Nastavení backendu

```powershell
# Přejděte do složky backend
cd backend

# Vytvořte virtuální prostředí
python -m venv venv

# Aktivujte virtuální prostředí
.\venv\Scripts\Activate.ps1

# Nainstalujte závislosti
pip install -r requirements.txt
```

### 3. Konfigurace prostředí

Vytvořte soubor `.env` v kořenové složce projektu s následujícím obsahem:

```env
# Database
DATABASE_URL=postgresql://neondb_owner:npg_YoV4K0xCmpOX@ep-silent-hat-agvd3kf5-pooler.c-2.eu-central-1.aws.neon.tech/neondb

# Google Gemini API
GEMINI_API_KEY=AIzaSyCKSZ55hHJCkCYt2ugZzLyL-dT43mReR0s

# CORS Origins (pro lokální vývoj)
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```

⚠️ **Poznámka:** Výše uvedené klíče jsou skutečné produkční klíče. Pro vlastní vývoj si vytvořte vlastní.

### 4. Inicializace databáze

```powershell
# Spusťte migrační skript (pokud je potřeba)
python setup_database.py

# Nebo použijte existující migraci pro obchodní pole
python add_trading_fields.py
```

### 5. Nastavení frontendu

```powershell
# Vraťte se do kořenové složky
cd ..

# Přejděte do složky frontend
cd frontend

# Nainstalujte npm balíčky
npm install
```

## 🚀 Spuštění aplikace

### Varianta A: Manuální spuštění (doporučeno pro vývoj)

**Backend (v samostatném terminálu):**
```powershell
cd backend
.\venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**Frontend (v druhém terminálu):**
```powershell
cd frontend
npm run dev
```

### Varianta B: Background skripty (pro produkci)

**Backend:**
```powershell
cd backend
.\start_background.ps1
```

**Frontend:**
```powershell
cd frontend
npm run dev
```

### Přístup k aplikaci

- **Frontend:** http://localhost:5173
- **Backend API:** http://localhost:8000
- **API dokumentace:** http://localhost:8000/docs (Swagger UI)

### ✅ Ověření, že vše funguje

1. **Backend kontrola:**
```powershell
# Zkontrolujte, že backend běží
Get-Process | Where-Object {$_.ProcessName -eq 'python'}

# Otevřete API docs v prohlížeči
start http://localhost:8000/docs

# Test API endpointu
curl http://localhost:8000/api/stocks
```

2. **Frontend kontrola:**
```powershell
# V prohlížeči by měla být viditelná aplikace
start http://localhost:5173

# Konzole by neměla ukazovat žádné chyby
# Měli byste vidět dashboard s akciovými kartami
```

3. **Databáze kontrola:**
```powershell
# V backend složce spusťte Python
cd backend
.\venv\Scripts\Activate.ps1
python
```
```python
from app.database.connection import get_db
from app.models.stock import Stock
from sqlalchemy import select

db = next(get_db())
stocks = db.execute(select(Stock)).scalars().all()
print(f"✅ Databáze obsahuje {len(stocks)} akcií")
for s in stocks[:3]:
    print(f"  - {s.ticker}: {s.action_verdict}")
```

## 🎯 První kroky po instalaci

### 1. Prohlédněte si existující data

- Otevřete http://localhost:5173
- Měli byste vidět dashboard s akciovými kartami
- Klikněte na libovolnou akcii pro detail
- V sekci "Top Picks" jsou akcie s BUY/ACCUMULATE verdiktem

### 2. Vyzkoušejte AI analýzu

- V Sidebar klikněte na "New Analysis"
- Zadejte jméno analytika (např. "Mark Gomes")
- Vložte URL Google Doc nebo text s akciovými zmínkami
- Klikněte "Analyze"
- Sledujte extrakci ticker symbolů a AI analýzu

### 3. Prozkoumejte kód

**Backend - začněte zde:**
1. `backend/app/main.py` - hlavní aplikační soubor, routing
2. `backend/app/core/prompts.py` - AI prompt pro Portfolio Manager
3. `backend/app/models/stock.py` - databázový model s obchodními poli
4. `backend/app/routes/analysis.py` - endpoint pro analýzu dokumentů

**Frontend - začněte zde:**
1. `frontend/src/App.tsx` - hlavní komponenta, state management
2. `frontend/src/components/AnalysisView.tsx` - dashboard s třemi sekcemi
3. `frontend/src/components/StockCard.tsx` - karta obchodního signálu
4. `frontend/src/api/client.ts` - API komunikace

### 4. Proveď první změnu

**Jednoduchý úkol pro začátek:**

Přidejte emoji do názvu sekce v dashboardu:

```typescript
// frontend/src/components/AnalysisView.tsx
// Změňte řádek cca 60:
'🔥 Top Picks This Week'
// na:
'🔥🚀 Top Picks This Week'
```

Uložte → frontend se automaticky reloadne → změna je viditelná!

## 📁 Struktura projektu

```
Akcion/
├── backend/                  # Python FastAPI server
│   ├── app/
│   │   ├── main.py          # Hlavní aplikační soubor
│   │   ├── models/          # SQLAlchemy modely (stock.py)
│   │   ├── schemas/         # Pydantic validační schémata
│   │   ├── routes/          # API endpointy (stocks.py, analysis.py)
│   │   ├── core/            # Byznys logika (prompts.py, extractors.py)
│   │   ├── database/        # DB připojení a repozitáře
│   │   └── config/          # Nastavení aplikace
│   ├── requirements.txt     # Python závislosti
│   └── start_background.ps1 # Spouštěcí skript
│
├── frontend/                 # React TypeScript aplikace
│   ├── src/
│   │   ├── components/      # React komponenty
│   │   │   ├── AnalysisView.tsx    # Hlavní dashboard
│   │   │   ├── StockCard.tsx       # Karta obchodního signálu
│   │   │   ├── StockDetail.tsx     # Detail akcie
│   │   │   └── Sidebar.tsx         # Navigační panel
│   │   ├── api/             # API klient (client.ts)
│   │   ├── types/           # TypeScript definice (index.ts)
│   │   ├── context/         # React Context (AppContext.tsx)
│   │   └── hooks/           # Custom hooks (useAppState.ts)
│   ├── package.json         # npm závislosti
│   └── vite.config.ts       # Vite konfigurace
│
├── .env                      # Proměnné prostředí (NECOMMITOVAT!)
├── README.md                 # Obecná dokumentace
└── NAVOD_PRO_VYVOJARE.md    # Tento soubor
```

## 🔑 Klíčové komponenty

### Backend - Databázový model (models/stock.py)

**Obchodní pole přidaná v poslední migraci:**
- `action_verdict` - Obchodní verdikt (BUY_NOW, ACCUMULATE, WATCH_LIST, TRIM, SELL, AVOID)
- `entry_zone` - Vstupní cenová zóna
- `price_target_short` - Krátkodobý cíl
- `price_target_long` - Dlouhodobý cíl
- `stop_loss_risk` - Stop loss úroveň
- `moat_rating` - Hodnocení konkurenční výhody (1-5)
- `trade_rationale` - Odůvodnění obchodu
- `chart_setup` - Technická analýza

### Frontend - Hlavní komponenty

1. **AnalysisView.tsx** - Dashboard se třemi sekcemi:
   - 🔥 Top Picks (BUY_NOW + ACCUMULATE)
   - 👀 Watch List (WATCH_LIST)
   - 📈 Ostatní akcie (TRIM/SELL/AVOID)

2. **StockCard.tsx** - Karta obchodního signálu:
   - Barevné odlišení podle action_verdict
   - Grid s Entry/Target/Stop Loss
   - 5hvězdičkové hodnocení moat
   - Katalyzátory a trade rationale

### API Endpointy

**GET /api/stocks** - Seznam všech akcií
**GET /api/stocks/{ticker}** - Detail akcie
**POST /api/analysis/google-doc** - Analýza Google Docs URL
**POST /api/analysis/text** - Analýza textového vstupu

## 🛠️ Vývojářský workflow

### 1. Vytvoření nové větve

```bash
git checkout -b feature/nazev-funkce
```

### 2. Přidání nového API endpointu

1. Přidejte model do `backend/app/models/`
2. Vytvořte Pydantic schéma v `backend/app/schemas/`
3. Implementujte endpoint v `backend/app/routes/`
4. Registrujte router v `backend/app/main.py`

### 3. Přidání nové React komponenty

1. Vytvořte komponentu v `frontend/src/components/`
2. Přidejte TypeScript typy do `frontend/src/types/index.ts`
3. Aktualizujte API klient v `frontend/src/api/client.ts`
4. Importujte a použijte v hlavní aplikaci

### 4. Databázové migrace

Pokud měníte databázové schéma:

```python
# Vytvořte migrační skript podobný add_trading_fields.py
import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()
engine = create_engine(os.getenv("DATABASE_URL"))

with engine.connect() as conn:
    conn.execute(text("ALTER TABLE stocks ADD COLUMN nove_pole VARCHAR(255)"))
    conn.commit()
```

### 5. Testování

```powershell
# Backend testy
cd backend
pytest tests/

# Frontend build test
cd frontend
npm run build
```

## 🔍 Debugging

### Backend debug

```powershell
# Spusťte s --reload pro automatický restart při změnách
cd backend
.\venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --log-level debug
```

**Sledování logů:**
```powershell
# Pokud běží background process, logy jsou v:
cat backend\server.log

# Sledování v real-time:
Get-Content backend\server.log -Wait -Tail 20
```

### Frontend debug

- Otevřete Chrome DevTools (F12)
- Network tab: sledujte API požadavky
- Console: kontrolujte chyby
- React DevTools: inspekce komponent

**TypeScript chyby:**
```powershell
cd frontend
npm run build  # Najde všechny TypeScript chyby
```

### Časté problémy a řešení

**1. CORS chyba (Frontend nemůže volat backend):**
```
Access to fetch at 'http://localhost:8000' has been blocked by CORS policy
```
✅ **Řešení:**
- Zkontrolujte `CORS_ORIGINS` v `.env` obsahuje `http://localhost:5173`
- Restartujte backend: `Get-Process python | Stop-Process -Force; .\start_background.ps1`
- Ujistěte se, že backend běží na portu 8000: `curl http://localhost:8000/docs`

**2. Database connection failed:**
```
OperationalError: could not connect to server
```
✅ **Řešení:**
- Ověřte `DATABASE_URL` v `.env` (musí začínat `postgresql://`)
- Zkontrolujte internetové připojení (Neon je cloud databáze)
- Test: `python -c "from app.database.connection import engine; engine.connect()"`

**3. Gemini API error:**
```
400 API key not valid
```
✅ **Řešení:**
- Ověřte platnost `GEMINI_API_KEY` v `.env`
- Zkontrolujte kvótu na https://aistudio.google.com/apikey
- Test: `curl https://generativelanguage.googleapis.com/v1beta/models?key=VÁŠ_KLÍČ`

**4. Frontend 500 error:**
```
AnalysisView.tsx:1 Failed to load resource: the server responded with a status of 500
```
✅ **Řešení:**
- Zkontrolujte TypeScript chyby: `cd frontend && npm run build`
- Podívejte se do konzole prohlížeče (F12)
- Restartujte frontend: Ctrl+C a znovu `npm run dev`

**5. Python process už běží:**
```
Address already in use
```
✅ **Řešení:**
```powershell
# Zastavte všechny Python procesy
Get-Process | Where-Object {$_.ProcessName -eq 'python'} | Stop-Process -Force

# Nebo najděte proces na portu 8000
netstat -ano | findstr :8000
Stop-Process -Id <PID>
```

**6. npm install selhává:**
```
npm ERR! code ERESOLVE
```
✅ **Řešení:**
```powershell
cd frontend
rm -rf node_modules package-lock.json
npm install --legacy-peer-deps
```

**7. Databáze neobsahuje žádné akcie:**
✅ **Řešení:**
```powershell
cd backend
python
```
```python
from app.database.connection import get_db
from app.models.stock import Stock
db = next(get_db())

# Přidejte testovací akcii
test_stock = Stock(
    ticker="TEST",
    company_name="Test Company",
    action_verdict="BUY_NOW",
    entry_zone="$100-$105",
    gomes_score=8
)
db.add(test_stock)
db.commit()
print("✅ Testovací akcie přidána")
```

## 📚 Užitečné příkazy

### Každodenní vývoj

```powershell
# Restart celé aplikace
cd backend
Get-Process | Where-Object {$_.ProcessName -eq 'python'} | Stop-Process -Force
.\start_background.ps1
cd ../frontend
npm run dev

# Sledování logů
Get-Content backend\server.log -Wait -Tail 20  # Backend logy
# Frontend logy jsou v terminálu kde běží npm run dev

# Kontrola běžících procesů
Get-Process | Where-Object {$_.ProcessName -eq 'python'}  # Backend
netstat -ano | findstr :5173  # Frontend
netstat -ano | findstr :8000  # Backend API
```

### Správa závislostí

```powershell
# Backend - aktualizace Python balíčků
cd backend
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt --upgrade
pip list --outdated  # Zjistit co lze aktualizovat

# Frontend - aktualizace npm balíčků
cd frontend
npm update
npm outdated  # Zjistit co lze aktualizovat
npm audit fix  # Opravit bezpečnostní problémy
```

### Čištění a reset

```powershell
# Vyčistit frontend cache
cd frontend
rm -rf node_modules/.vite
rm -rf dist
npm run dev -- --force

# Kompletní reinstalace frontendu
rm -rf node_modules package-lock.json
npm install

# Vyčistit Python cache
cd backend
Get-ChildItem -Recurse -Filter "__pycache__" | Remove-Item -Recurse -Force
Get-ChildItem -Recurse -Filter "*.pyc" | Remove-Item -Force
```

### Databázové operace

```powershell
# Export databáze
pg_dump $env:DATABASE_URL > backup_$(Get-Date -Format "yyyyMMdd_HHmmss").sql

# Import databáze
psql $env:DATABASE_URL < backup.sql

# Spustit migraci
cd backend
python add_trading_fields.py

# Python shell s databázovým připojením
python
```
```python
from app.database.connection import get_db
from app.models.stock import Stock
from sqlalchemy import select
db = next(get_db())

# Ukázka queries
stocks = db.execute(select(Stock)).scalars().all()
buy_stocks = db.execute(select(Stock).where(Stock.action_verdict == "BUY_NOW")).scalars().all()
```

### Git workflow

```powershell
# Před začátkem nové feature
git checkout main
git pull origin main
git checkout -b feature/nazev-funkce

# Pravidelné commitování
git add .
git commit -m "feat: popis změny"
git push origin feature/nazev-funkce

# Před mergem do main
git checkout main
git pull origin main
git checkout feature/nazev-funkce
git rebase main  # Nebo git merge main
```

### Testování a validace

```powershell
# Backend testy
cd backend
pytest tests/ -v
pytest tests/test_api_endpoints.py -k test_get_stocks

# Frontend type check
cd frontend
npm run build  # Najde všechny TypeScript chyby

# Linting
cd frontend
npm run lint
```

## 🤝 Přispívání do projektu

1. **Fork** repozitáře
2. Vytvořte **feature branch** (`git checkout -b feature/amazing-feature`)
3. **Commit** změn (`git commit -m 'Add amazing feature'`)
4. **Push** do branch (`git push origin feature/amazing-feature`)
5. Otevřete **Pull Request**

### Code style

- **Python:** PEP 8 (použijte `black` formatter)
- **TypeScript:** ESLint konfigurace projektu
- **Commity:** Conventional Commits formát

## 📞 Kontakt a podpora

- **GitHub Issues:** https://github.com/Reathyze20/Akcion/issues
- **Dokumentace:** Viz README.md a ARCHITECTURE.md

## 📄 Licence

Informace o licenci naleznete v souboru LICENSE v kořenové složce projektu.

---

**Poslední aktualizace:** 11. ledna 2026  
**Verze:** 2.0 (Trading Platform Upgrade)
