# Provoz aplikace — jak ji spustit, naplánovat a ověřit

**Typ dokumentu:** návod (how-to). Ověřeno spuštěním 24. 8. 2026 na větvi `feature/gomes-fidelity`.

Sesterské dokumenty: [`AKCION_JAK_FUNGUJE.md`](AKCION_JAK_FUNGUJE.md) (co appka je),
[`AKCION_ROZHODOVANI.md`](AKCION_ROZHODOVANI.md) (na základě čeho radí),
[`AKCION_HODNOTOVE_INVESTOVANI.md`](AKCION_HODNOTOVE_INVESTOVANI.md) (metodika).

---

## 1. Co je potřeba mít

| Věc | Verze / detail |
|-----|----------------|
| Python | 3.12 (CI běží na 3.12; cesta v `.cmd` obálkách míří na `Python312`) |
| Node.js | 18+ |
| PostgreSQL | vzdálená instance, connection string v `DATABASE_URL` |
| `backend/.env` | živé přístupy k brokerovi a SMTP — **nikdy nečíst do výstupu, nekopírovat, nekomitovat** |

> **pytest není v `.venv` ani v `requirements.txt`.** Testy se pouští **systémovým**
> Pythonem. Tohle je jediné místo, kde na tom záleží.

---

## 2. Spuštění celé aplikace

```powershell
# z kořene projektu — otevře dvě okna, backend + frontend
.\start.ps1
```

Ekvivalentně ručně:

```powershell
cd backend
python run_server.py      # http://localhost:8002, dokumentace na /api/docs

cd frontend
npm run dev               # http://localhost:5173
```

**Ověření, že to jede:** otevři `http://localhost:8002/api/analyze/health`. Endpoint
záměrně **nevolá model** — odpoví jen, který model by zavolal a jestli k němu existuje
klíč:

```json
{ "status": "configured", "model": "claude-opus-5", "api_key_present": true, "web_access": false }
```

`"status": "missing_credentials"` znamená, že v `backend/.env` chybí `ANTHROPIC_API_KEY`
a narativní vrstva (SEC výhledy, deep DD, extrakce tvrzení) nepoběží. Číselná vrstva
poběží dál — ta žádný klíč nepotřebuje.

---

## 3. Migrace databáze

Migrace jsou ruční SQL soubory v `backend/migrations/`, pouštěné jednoduchým runnerem.
Alembic je v závislostech, ale nepoužívá se.

```powershell
cd backend
python apply_migration.py add_lifecycle_ratchet
python apply_migration.py add_market_catalyst
```

**Past:** modely v `app/models/` mohou obsahovat sloupce, které databáze ještě nezná.
Když appka spadne na `UndefinedColumn`, chybí migrace, ne kód. Poslední dvě přidané:

| Migrace | Co přidává |
|---------|-----------|
| `add_lifecycle_ratchet.sql` | `stock_lifecycle.phase_reached`, `rough_patch*` — ráčna fáze cyklu |
| `add_market_catalyst.sql` | `market_status.catalyst_*` — semafor musí mít zapsanou příčinu |

---

## 4. Testy a kontroly (jediné přijatelné důkazy, že něco funguje)

| Co | Příkaz | Stav 24. 8. 2026 |
|----|--------|------------------|
| Backend testy | `python -m pytest` z `backend/` (systémový Python) | **1287 prošlo, 54 přeskočeno**, 23,5 s |
| Frontend typy + build | `npm run build` z `frontend/` (spouští `tsc -b`) | **prošlo**, 944 ms |
| Frontend testy | `npm test` z `frontend/` (vitest) | **81 prošlo** ve 4 souborech, 380 ms |
| Frontend lint | `npm run lint` z `frontend/` | — |

Podúkol je hotový, teprve když příslušný příkaz skončí návratovým kódem 0. Tvrzení
„ověřeno ručně“ důkaz není.

CI (`.github/workflows/ci.yml`) běží na `main` a `develop`: instaluje
`requirements.txt` + `requirements_test.txt`, zkompiluje čtyři klíčové moduly
(`master_signal.py`, `gomes_logic.py`, `kelly.py`, `notifications.py`) a pustí
`pytest` s pokrytím.

`tests/conftest.py` nastavuje `DATABASE_URL=sqlite:///:memory:` a fiktivní klíče
**na úrovni modulu**, ne ve fixtuře — několik modulů (např. `routes/gomes.py`)
instancuje `Settings()` už při importu, tedy během sběru testů, kdy žádná fixtura
ještě neběžela.

---

## 5. Plánované úlohy (Windows Task Scheduler)

Scheduler uvnitř FastAPI procesu funguje jen dokud je appka spuštěná. Úlohy, které
mají běžet i se zavřenou appkou, jsou samostatné skripty s `.cmd` obálkou.

**Proč obálka a ne přímo `python.exe`:** Plánovač si uloží jen návratový kód, takže
„úloha proběhla“ a „úloha proběhla a zdroj byl nedostupný“ jsou bez logu k nerozeznání.
Navíc na `PATH` bývá první zástupce `python.exe` z WindowsApps, který jen otevře
Microsoft Store a úloha by tiše nedělala nic. Obálka proto určuje interpret napevno,
loguje do `backend/logs/*.log` a rotuje log při 1 MB.

| Úloha v Plánovači | Skript | Kadence | Co dělá |
|-------------------|--------|---------|---------|
| Akcion - Gomes tracker | `scripts/tracker_poll.cmd` | denně (v kódu limit 12 h) | čte `riskrewardcharts.com` — zelené a červené čáry, ze kterých se počítá pásmo |
| Akcion - Breakout watchlist | `scripts/breakout_poll.cmd` | denně (v kódu limit 20 h) | čte watchlist Breakout Investors; zprávu pošle jen když se něco změnilo |
| Akcion - historie cen | `scripts/refresh_price_history.cmd` | denně 18:05 | plní `ohlcv_data` denními bary pro měření propadu od vrcholu |
| Akcion - vyhodnoceni skore | `scripts/evaluate_scores.cmd` | denně 18:00, „spustit po zmeškání“ zapnuto | měří deník skóre proti cenám na horizontech 30/90/180/365 dní |

**Nenaplánováno (stav k 23. 8. 2026):** `scripts/away_check.py`. Režim nepřítomnosti
tedy zatím nikdy nic neposlal. Naplánovat lze takto:

```powershell
python C:\Users\reath\Projects\Akcion\backend\scripts\away_check.py
```

Užitečné přepínače:

- `--dry-run` — rozhodne a vypíše, **nepošle nic**
- `--now ISO` — předstírá jiný okamžik, na ověření pravidel

> **Invariant.** Nikdy neposílej skutečné upozornění ani nezadávej skutečný pokyn jen
> proto, abys ověřil změnu. Použij `--dry-run` nebo testovacího dvojníka.

Všechny úlohy potřebují **zapnutý počítač a síť** — to kód zařídit neumí.

---

## 6. Ruční skripty (spouštěné, když je co dělat)

| Skript | K čemu |
|--------|--------|
| `scripts/propose_cylinders.py` | navrhne počet válců pro každou drženou pozici a vypíše důkazy (SEC XBRL + Yahoo) |
| `scripts/propose_lifecycle.py` | navrhne fázi cyklu z datovaných faktů, ne z conviction skóre |
| `scripts/refresh_balance_sheets.py` | natáhne rozvahy do `fundamental_snapshots` a spočítá ochrannou rezervu |
| `scripts/gomes_fit.py --ticker XXX` | porovná tvar grafu kandidáta proti Gomesovým skutečným vstupům |
| `scripts/seed_score_journal.py` | den nula deníku skóre (už proběhlo 23. 8. 2026) |
| `scripts/sec_backfill.py export\|import\|status` | hromadné přečtení podání **z předplatného místo z API** |

**Proč jsou to skripty a ne tlačítka:** návrh válců potřebuje jeden HTTP dotaz na firmu
proti SEC (regulace limituje 10 dotazů/s) a Yahoo agregáty. Uvnitř requestu by denní
seznam čekal na cizí server.

### Hromadné přeanalyzování podání

Server čte **nejnovější nepřečtené podání na ticker** přes placené Anthropic API —
zhruba 8 volání za čtvrtletí. To je záměrně malá cesta, aby se appka aktualizovala
i když u ní nikdo nesedí.

Hromadné přečtení (například po změně promptu) je opačný tvar a patří na předplatné:

```powershell
python scripts/sec_backfill.py export      # vypíše .txt soubory
# přečti je v session, zapiš .summary.md
python scripts/sec_backfill.py import
```

Nikdy nepouštěj `analyze_filing` ve smyčce přes portfolio — utratí API kredit za práci,
kterou předplatné pokrývá.

---

## 7. Konfigurace (`backend/.env`)

| Proměnná | Povinná | K čemu |
|----------|---------|--------|
| `DATABASE_URL` | ano | PostgreSQL connection string |
| `GEMINI_API_KEY` | **ano — ale nic ji nečte** | vestigiální; viz níže |
| `ANTHROPIC_API_KEY` | ne (ale bez ní neběží narativní vrstva) | jediný model, který appka volá |
| `FINNHUB_API_KEY` | ne | růst tržeb a marže, free tier |
| `MASSIVE_API_KEY` | ne | americké ceny (Polygon.io) |
| `T212_API_KEY_ID`, `T212_API_KEY` | ne | Trading 212, **jen pro čtení** — klíč nesmí mít oprávnění `orders` |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | ne | kanál upozornění |
| `EMAIL_RECIPIENT`, `SMTP_*` | ne | kanál upozornění |
| `DEBUG` | ne (default `False`) | **odemyká `POST /api/dev/execute-sql`** (libovolné SQL) — v produkci musí zůstat `False` |
| `CORS_ORIGINS` | ne | default `http://localhost:5173` |
| `API_PORT` | ne | default `8002` |

### Vestigiální `GEMINI_API_KEY`

`settings.gemini_api_key` je stále **povinné** pole (`Field(...)`), takže bez něj appka
nenastartuje — ale `google.generativeai` nemá v `app/` jediné použití. Klíč se předává do
`StockAnalyzer(settings.gemini_api_key)`, kde se uloží do `self._api_key` a **nikdy
nepoužije**: `_call_model` volá `services.llm.complete`, tedy Anthropic (`app/core/analysis.py:259`).
`google-generativeai` v `requirements.txt` je ze stejného důvodu mrtvá závislost.

Historie: `gemini-2.0-flash` byl vyřazen 1. 6. 2026, jméno modelu bylo napsané ručně v pěti
souborech a analýza tiše nefungovala zhruba dvanáct týdnů. Proto dnes jméno modelu existuje
**na jednom místě** — `MODEL` v `app/services/llm.py` — a volající si nesmí říct, s čím mluví.

---

## 8. Řešení problémů

| Příznak | Příčina | Co s tím |
|---------|---------|----------|
| Appka nenastartuje na `ValidationError` | chybí `DATABASE_URL` nebo `GEMINI_API_KEY` | doplň do `.env` (Gemini klíč může být libovolný řetězec, nic ho nečte) |
| `UndefinedColumn` při dotazu | chybí migrace | `python apply_migration.py <jméno>` |
| Analýza vrací chybu, appka jinak jede | chybí `ANTHROPIC_API_KEY` | `/api/analyze/health` to řekne, aniž by utratil kredit |
| Nepřijde e-mail | Gmail app password vypršelo (ověřeno 22. 8. živým odesláním: `535 BadCredentials`) | nové app password na myaccount.google.com → Security → App passwords, přepiš `SMTP_PASSWORD` |
| Úloha v Plánovači „proběhla“, ale nic se nestalo | zástupce `python.exe` z WindowsApps | zkontroluj `backend/logs/<úloha>.log` — obálka tam píše i chybu |
| Pásmo se nepřepočítalo | tracker poll neproběhl | `backend/logs/tracker_poll.log`; v kódu je limit 12 h mezi čteními |
| Skóre pozice chybí | zelená/červená čára pro ticker neexistuje | appka to má pojmenovat jako mezeru, ne dosadit číslo — pokud dosadí, je to chyba třídy „chybějící data se stala verdiktem“ |

---

## 9. Bezpečnostní pravidla, která nejsou konfigurace

1. **`backend/.env` se nikdy nečte do výstupu**, nekopíruje a nekomituje.
2. **Trading 212 klíč je read-only.** Appka nikdy nezadává pokyny. Klíč vytvořený
   s oprávněním `orders` je chyba nastavení, ne funkce.
3. **`POST /api/dev/execute-sql`** je registrovaný jen když `settings.debug` je `True`.
4. **Žádná autentizace.** Backend počítá s tím, že poslouchá na `localhost`.
   Vystavit ho do sítě znamená vystavit celé portfolio bez hesla.
