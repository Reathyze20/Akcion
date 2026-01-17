# 🚀 Akcion - Průvodce instalací pro začátečníky

Tento návod tě provede krok za krokem, jak si rozjet Akcion projekt na tvém počítači.

---

## 📋 Co budeš potřebovat

### 1. Nainstaluj tyto programy:

| Program | Odkaz ke stažení | Proč to potřebuješ |
|---------|------------------|-------------------|
| **VS Code** | https://code.visualstudio.com/ | Editor kódu |
| **Python 3.12** | https://www.python.org/downloads/ | Backend server |
| **Node.js 20+** | https://nodejs.org/ | Frontend server |
| **Git** | https://git-scm.com/downloads | Verzování kódu |

### ⚠️ Důležité při instalaci Pythonu:
Při instalaci **ZAŠKRTNI** políčko **"Add Python to PATH"**!

![Python PATH](https://docs.python.org/3/_images/win_installer.png)

---

## 🔧 Instalace krok za krokem

### Krok 1: Otevři VS Code
1. Spusť VS Code
2. Otevři složku projektu: `File` → `Open Folder` → vyber `C:\Users\reath\Projects\Akcion`

### Krok 2: Otevři Terminál
1. V VS Code stiskni `` Ctrl+` `` (klávesa pod Escape)
2. Nebo: `Terminal` → `New Terminal`

### Krok 3: Nainstaluj Python knihovny (Backend)
Zkopíruj tyto příkazy do terminálu a stiskni Enter:

```powershell
cd backend
pip install -r requirements.txt
```

Počkej než se vše nainstaluje (může to trvat 2-5 minut).

### Krok 4: Nainstaluj Node.js balíčky (Frontend)
```powershell
cd ../frontend
npm install
```

Počkej než se vše nainstaluje (může to trvat 1-3 minuty).

---

## ▶️ Spuštění aplikace

### Možnost A: Pomocí VS Code Tasks (doporučeno) 🌟

1. Stiskni `Ctrl+Shift+B`
2. Vyber **"⚡ Start All (BE + FE)"**
3. Hotovo! Oba servery běží.

### Možnost B: Ručně (pokud nefunguje Možnost A)

**Terminál 1 - Backend:**
```powershell
cd C:\Users\reath\Projects\Akcion\backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8002 --reload
```

**Terminál 2 - Frontend:** (otevři nový terminál: `Ctrl+Shift+``)
```powershell
cd C:\Users\reath\Projects\Akcion\frontend
npm run dev
```

---

## 🌐 Otevři aplikaci v prohlížeči

Po spuštění otevři v prohlížeči:

| Služba | URL | Co tam najdeš |
|--------|-----|---------------|
| **Frontend** | http://localhost:5173 | Hlavní aplikace |
| **Backend API** | http://localhost:8002/api/docs | API dokumentace |

---

## ✅ Jak poznat, že vše funguje?

### Backend běží správně, když vidíš:
```
INFO:     Uvicorn running on http://127.0.0.1:8002
INFO:     Application startup complete.
```

### Frontend běží správně, když vidíš:
```
VITE v7.2.5  ready in 285 ms
➜  Local:   http://localhost:5173/
```

---

## 🛑 Jak zastavit servery?

### Možnost 1: V terminálu
Stiskni `Ctrl+C` v každém terminálu kde běží server.

### Možnost 2: Pomocí VS Code Task
1. `Ctrl+Shift+P`
2. Napiš "Tasks: Run Task"
3. Vyber **"🛑 Stop All Servers"**

---

## 🐛 Řešení běžných problémů

### Problém: "python is not recognized"
**Řešení:** Python nebyl přidán do PATH. Přeinstaluj Python a zaškrtni "Add to PATH".

### Problém: "npm is not recognized"
**Řešení:** Restartuj VS Code po instalaci Node.js.

### Problém: "Port 8002 already in use"
**Řešení:** Spusť tento příkaz:
```powershell
Get-Process -Name python | Stop-Process -Force
```

### Problém: "Port 5173 already in use"
**Řešení:** Spusť tento příkaz:
```powershell
Get-Process -Name node | Stop-Process -Force
```

### Problém: Backend hází chyby o databázi
**Řešení:** Databáze je v cloudu (Neon), takže se připojí automaticky. Pokud ne, zkontroluj internetové připojení.

---

## 📁 Struktura projektu (co je kde)

```
Akcion/
├── backend/           ← Python server (FastAPI)
│   ├── app/
│   │   ├── core/      ← AI prompty, analýza
│   │   ├── routes/    ← API endpointy
│   │   └── models/    ← Databázové modely
│   └── requirements.txt
│
├── frontend/          ← React aplikace
│   ├── src/
│   │   ├── components/ ← UI komponenty
│   │   └── api/        ← API klient
│   └── package.json
│
└── docs/              ← Dokumentace (jsi tady!)
```

---

## 🧪 Testování (pro QA)

### Jak otestovat API:
1. Otevři http://localhost:8002/api/docs
2. Klikni na endpoint (např. `GET /api/stocks`)
3. Klikni "Try it out"
4. Klikni "Execute"
5. Zkontroluj odpověď

### Klíčové endpointy k testování:

| Endpoint | Metoda | Co dělá |
|----------|--------|---------|
| `/api/stocks` | GET | Vrátí seznam akcií |
| `/api/stocks/enriched` | GET | Akcie s aktuálními cenami |
| `/api/portfolio` | GET | Portfolio data |
| `/api/intelligence/market-alert` | GET | Stav trhu |

---

## 💡 Užitečné klávesové zkratky VS Code

| Zkratka | Co dělá |
|---------|---------|
| `Ctrl+Shift+B` | Spustí build task (Start All) |
| `` Ctrl+` `` | Otevře/zavře terminál |
| `Ctrl+Shift+P` | Command Palette |
| `Ctrl+S` | Uloží soubor |
| `Ctrl+Shift+F` | Hledání v celém projektu |

---

## 📞 Potřebuješ pomoc?

Pokud něco nefunguje:
1. Zkus restartovat VS Code
2. Zkus restartovat počítač
3. Zavolej mi! 📱

---

*Vytvořeno s ❤️ pro nejlepší QA testerku na světě!*
