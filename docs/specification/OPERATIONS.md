# Operations & Data Sources

**Type:** Reference · **Source:** `backend/app/config`, `backend/app/services/*`,
`backend/scripts/*`, `backend/research/*`, `.github/workflows/ci.yml` ·
**Verified:** 2026-08-28

`backend/.env` was never read while researching this document. Env var **names**
below, never values.

---

## External integrations

| Source | Module | Auth env var | Cost | Throttle | On failure |
|---|---|---|---|---|---|
| Yahoo Finance | `yahoo_cache.py`, `price_history.py` | none (yfinance) | free | market-hours-aware TTL | serves cache flagged `is_stale` |
| Finnhub | `market_data.py`, `finnhub_metrics.py` | `FINNHUB_API_KEY` | free tier (60/min) | none in code | returns `None` |
| Massive/Polygon | `market_data.py`, `data_fetcher.py`, `news_monitor.py` | `MASSIVE_API_KEY` | paid tier | none | returns `None` |
| SEC EDGAR | `sec_edgar.py`, `sec_fundamentals.py`, `sec_sync.py` | none (hardcoded User-Agent) | **free** | `MIN_REQUEST_INTERVAL = 0.12s` (~8.3/s) | raises `SecError`; `CoverageStatus` enum |
| Firecrawl | `firecrawl.py` | `FIRECRAWL_API_KEY` | **metered — 1000 credits total, not monthly** | ledger + disk cache | `ok=False` + Czech reason |
| TranscriptAPI | `scripts/gomes_transcripts.py` | `TRANSCRIPTAPI_KEY` | **paid, 1000 credits/mo** | `sleep(0.3)` | prints failure, continues |
| Anthropic | `services/llm.py` | `ANTHROPIC_API_KEY` | **paid per token** | `MIN_ANALYZE_INTERVAL = 6h` per ticker | raises `LLMError` |
| Gemini | `gomes_intake_flash.py` | `GEMINI_API_KEY` | paid | none | `RuntimeError` after fallback |
| riskrewardcharts.com | `gomes_tracker.py` | none (unauth'd) | free | `MIN_POLL_INTERVAL = 12h` | `TrackerUnavailable` |
| breakoutinvestors.com | `breakout_watchlist.py` | none (unauth'd) | free | `MIN_POLL_INTERVAL = 20h` | `WatchlistUnavailable` |
| Czech National Bank | `currency.py` | none | free | `CACHE_TTL = 6h` | dated fallback, `is_live=False` |
| Trading 212 | `trading212.py` | `T212_API_KEY_ID`, `T212_API_KEY` | free | per-endpoint spacing table | typed exceptions |
| DeGiro | `degiro_transactions.py`, `importer.py` | none (CSV export) | free | n/a | `DegiroImportError` |
| Telegram | `notifications.py` | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | free | none | returns `False` |
| SMTP | `notifications.py` | `SMTP_*`, `EMAIL_RECIPIENT` | free | none | returns `False`, keeps `last_error` |

### Market data

`services/market_data.py` — `MarketDataService`, all static methods.
`get_current_price()` resolves in a deliberate order: fresh Yahoo cache → Finnhub
`/quote` (live) → Massive `/v2/aggs/.../prev` (**yesterday's close, explicitly not
live**) → stale cache as a last resort, logged as stale.

Two anti-fabrication guards worth preserving: Finnhub's `pc` (previous-close)
fallback was **removed** so a missing quote stays missing; `refresh_portfolio_prices()`
returns `stale_count` separately from `updated_count` and does **not** stamp
`last_price_update` on a stale row — stamping it once permanently disabled the
staleness alarm in `daily_actions`.

`services/yahoo_cache.py` — `YahooFinanceCache`, tables `yahoo_finance_cache` +
`yahoo_refresh_log`. TTLs: market data 15 min, fundamentals 7 days, financials 90
days. Refresh decisions come from `core/market_hours.should_refresh_market_data()`
(NYSE hours, `America/New_York`). `NYSE_HOLIDAYS_2026` is **hardcoded as `(month,
day)` tuples with no year check — this set needs updating for 2027.**

Two documented fixes: `fast_info` keys are camelCase (`lastPrice`, not `last_price`)
— the snake_case read once cached empty prices while logging success; and
`_increment_error_count` deliberately does **not** touch `last_updated`, because it
used to, which made frequently-failing tickers look freshest.

`services/price_history.py` fills `ohlcv_data` via
`yf.Ticker(symbol).history(period="5y", interval="1d")`. Bars are stored under **the
symbol that answered**, not the one asked for — `IMP.V` (EUR) gets its history from
`ITMSF` (USD); filing them together would report an FX move as a price drawdown.

`services/finnhub_metrics.py` tries **US OTC symbols first** because Finnhub answers
for `GKPRF` and returns `{}` for `GSI.V`. `_safe_reason()` strips the API key and
query string from exception text — `requests` puts `token=<key>` into `HTTPError`
messages, and a live credential was written to a log once before this fix. **Apply
this pattern to every API added from now on** (see `INVARIANTS.md` §5).

### SEC EDGAR (free)

- `USER_AGENT` is **hardcoded** with a personal email, no env override.
- Throttle `0.12s` between requests, **per-instance, not process-global** — concurrent
  clients can exceed SEC's 10/s cap.
- CIK mapping is exact-ticker only; suffix-stripping was removed after `DBO.TO`
  matched "Invesco DB Oil Fund" and attached an ETF's numbers to a Toronto holding.
  Foreign suffixes route through a curated cross-listing table in `app/core/tickers.py`.
- `CoverageStatus` = `COVERED | NOT_AN_SEC_FILER | LOOKUP_FAILED |
  FOREIGN_PRIVATE_ISSUER | NOT_A_TICKER`. `GET /api/sec/{ticker}` returns **404**
  when never checked — "we have not looked" is a different answer from "there is
  nothing".
- Only Form 4 codes `P`/`S` map to BUY/SELL; the other 17 codes are `NO_SIGNAL` with
  price nulled, so a gift cannot average in as "bought for nothing".
- The only paid call is `analyze_outlook()` (Anthropic). `POST /api/sec/sync`
  defaults `with_outlook=False` for this reason.

`scripts/sec_backfill.py` (`export | import | status`) exists specifically so a bulk
re-analysis runs from the owner's **subscription**, not the API — see
`INVARIANTS.md` §5 / the API-vs-subscription split.

### Firecrawl — the one hard budget

`DEFAULT_BUDGET = 1000` credits, **total, not monthly**. Key travels only in
`Authorization: Bearer`. `Ledger` persists to `backend/data/firecrawl/ledger.json`
(gitignored); a corrupt ledger loads as `budget=0` — refusing to spend is
recoverable, double-spending is not. Pages cache to `backend/data/firecrawl/pages/`.

Purpose: the four Canadian filers invisible to SEC — see `DOMAIN_MODEL.md` §"data
provenance layers". A response under `MIN_USEFUL_CHARS = 200` returns `ok=False`
(cookie wall / JS shell), never an empty string treated as a clean read.

**Deliberately not used:** Firecrawl's own LLM extraction (several times the cost of
a scrape) — numbers are read out of the returned markdown in-session instead.

### Brokers — two unconnected stacks

`services/trading212.py` and `services/degiro_transactions.py` are careful and
well-tested but **imported by nothing but their own tests**. The live import path is
`services/importer.py` → `routes/portfolio.py` (CSV upload).

- **Trading 212** is read-only, enforced structurally (no write method exists) *and*
  by AST tests that assert no `post`/`put`/`patch`/`delete` call exists anywhere in
  the module. See `INVARIANTS.md` §5 — a key with `orders` permission is a
  configuration error, not a feature.
- **DeGiro** transaction CSV (not the positions export — that export has no cost
  basis). Parsed **positionally**, Czech locale (`DD-MM-YYYY`, `"1.234,56"`). Dedup
  counts identical `(order_id, executed_at, isin, quantity, price)` tuples — keying on
  `order_id` alone would have deleted 500 real shares of a 7-fill sell.
- **`importer.py`** (the live path): DeGiro rows return `avg_cost = None` deliberately
  — the export's closing price becomes `current_price`, never cost basis — and a
  re-import never overwrites a known cost with nothing. Pinned by
  `tests/test_csv_import_honesty.py`.

### Transcripts / YouTube

`scripts/gomes_transcripts.py` → TranscriptAPI, `channel/latest` free,
`transcript` 1 credit. Preferred over the free `youtube-transcript-api` library
because YouTube IP-blocks a home address periodically — fine for a one-off, not for
a scheduled job. Dedup by filesystem glob, so a re-run never re-spends.

`scripts/verify_gomes_claims.py` is explicitly **non-LLM**: it checks that each
`verbatim_quote` actually occurs in the raw transcript. Writes nothing to the DB.
`apply_gomes_cleanup.py` applies the verdicts and refuses to act unless exactly one
DB row matches. See `INVARIANTS.md` §1 for why this gate exists.

### WhatsApp — no API, entirely manual paste

`POST /api/gomes/whatsapp/paste`. `extract: bool = False` by default — reading who
wrote something costs nothing; claim extraction costs money and is opt-in.

`strip_phone_numbers()` runs first, unconditionally, in both parsers. For
WhatsApp's own export format, the author field **is** the phone number, so each
author gets a slot letter (A, B, C…) and a human supplies names afterward. Guessing
an author from message text was considered and rejected — a reply thread can name
someone other than its author. See `INVARIANTS.md` §6 and
`akcion-breakout-analysts` / `akcion-whatsapp-archiv` in project memory.

`whatsapp_contacts.local.json` (repo root, gitignored) is a human/agent lookup —
**no Python code reads it.**

### LLM

`services/llm.py` is the single place a model name appears — written after
`gemini-2.0-flash` was retired 2026-06-01 while hardcoded in five other files,
silently killing analysis for ~12 weeks.

```
MODEL       = "claude-opus-5"
MODEL_CHEAP = "claude-haiku-4-5-20251001"   # only where output is schema-bound AND mechanically verified
MODEL_MID   = "claude-sonnet-5"
DEFAULT_MAX_TOKENS = 16000
MAX_RETRIES = 5
```

`complete_json()` raises rather than returning `{}` — an empty dict would read
downstream as "the model found nothing" (see `INVARIANTS.md` §1). Cost controls:
`MIN_ANALYZE_INTERVAL = 6h` per ticker (a 10-minute gate once produced 143 calls in
24h on one ticker); `with_outlook=False` by default on bulk SEC sync;
`backfill_transcripts.py --use-api` defaults to `False`.

**Gemini is separately live** in `services/gomes_intake_flash.py` (raw REST to
`gemini-2.5-flash`, fallback `gemini-1.5-flash`), reachable via the registered
`intake` router. `AKCION_PROVOZ.md §7` calling `GEMINI_API_KEY` "vestigial" is only
half right — the `google-generativeai` *package* is dead, but this key is genuinely
in use.

### Currency

CNB daily fixing, `CACHE_TTL = 6h`. An unknown currency **raises `CurrencyError`**
rather than defaulting to USD (see `INVARIANTS.md` §1 — an ILS position was once
valued at the USD rate, a 3.3× overstatement). Every rate carries `is_live` and
`as_of` so a stale snapshot can never be silently folded into a total.

---

## Configuration — `backend/app/config/settings.py`

pydantic-settings, `env_file=".env"`, singleton via `get_settings()`.

| Env var | Default | If unset |
|---|---|---|
| `DATABASE_URL` | **required** | app won't start |
| `GEMINI_API_KEY` | **required** | app won't start; used only by the intake route |
| `ANTHROPIC_API_KEY` | `None` | narrative layer dead; numeric layer fine |
| `T212_API_KEY_ID` / `T212_API_KEY` | `None` | nothing — client is unwired |
| `MASSIVE_API_KEY` | `None` | no US prev-close, no Polygon news/OHLCV |
| `FINNHUB_API_KEY` | `None` | no live quotes, no YoY metrics layer |
| `TRANSCRIPTAPI_KEY` | `None` | transcripts script exits |
| `FIRECRAWL_API_KEY` | `None` | `ok=False` |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | `None` | Telegram channel not built |
| `EMAIL_RECIPIENT` | `None` | email channel not built |
| `SMTP_SERVER` / `PORT` / `USERNAME` / `PASSWORD` | Gmail defaults / `None` | email channel not built |
| `DEBUG` | `False` | `True` registers `POST /api/dev/execute-sql` — **arbitrary SQL** |
| `API_HOST` / `API_PORT` | `0.0.0.0` / `8002` | **dead — nothing reads them** |
| `CORS_ORIGINS` | localhost list | **dead — `main.py` hardcodes the origin list** |

**Cross-check against `.env.example` files:**

- Present in `settings.py`, **missing from both examples**: `API_HOST`, `API_PORT`,
  `DEBUG`, `EMAIL_RECIPIENT`, `FIRECRAWL_API_KEY`, `TRANSCRIPTAPI_KEY`.
  `EMAIL_RECIPIENT` is the notable one — it is the only working recipient variable
  and is documented in neither example.
- In `.env.notifications.example` but not a real setting: `SMTP_FROM_EMAIL`,
  `SMTP_TO_EMAIL` (**phantom names** — a comment in `notifications.py` documents that
  these previously made `from_env()` always fail), `ALERT_MIN_CONFIDENCE` (read by
  nothing).

**`ALERT_CHECK_INTERVAL` trap:** `alert_scheduler.py` reads it with `os.getenv`, but
pydantic-settings loads `.env` **without exporting to `os.environ`**. Putting it in
`backend/.env` does nothing — the interval is locked at 30 minutes unless set in the
real process environment. The same mechanism makes `GET /api/notifications/status`
report `configured: false` on a working setup (it checks `os.getenv` on names that
exist in neither `Settings` nor a working `.env`).

**Database:** `pool_size=5`, `max_overflow=10`, `pool_pre_ping=True`.
`Base.metadata.create_all(checkfirst=True)` on startup creates missing **tables**,
never adds a missing **column** — real schema changes are hand-written SQL in
`backend/migrations/` (44 files), applied by `python apply_migration.py <name>`.
Alembic is a dependency but unused.

---

## Background and scheduled work

### In-process scheduler

APScheduler is a pinned dependency but **imported nowhere**. The real scheduler is a
hand-rolled asyncio loop in `services/alert_scheduler.py`, started from the
deprecated `@app.on_event("startup")`. `WAKING_START_HOUR/END_HOUR = 8/21` is **local
machine time, not market time**. It only runs while the FastAPI process is up, and
`run_server.py` uses `reload=True`, so the reloader restarts the loop on every code
change during development.

### Windows Task Scheduler (external, no `.xml` in the repo)

Four tasks registered by hand in the GUI. Names appear only in script docstrings and
`AKCION_PROVOZ.md`.

| Task name | Wrapper | Time | Throttle |
|---|---|---|---|
| Akcion - vyhodnoceni skore | `scripts/evaluate_scores.cmd` | daily 18:00 | none (settle-based) |
| Akcion - historie cen | `scripts/refresh_price_history.cmd` | daily 18:05 | none (upsert) |
| Akcion - Gomes tracker | `scripts/tracker_poll.cmd` | daily 18:15 | 12 h |
| Akcion - Breakout watchlist | `scripts/breakout_poll.cmd` | daily 18:30 | 20 h |

All four wrappers share one shape: a hardcoded interpreter path with a `py.exe -3`
fallback (the first `python.exe` on `PATH` is often the Microsoft Store stub, which
would silently do nothing), a `BACKEND` path derived relative to the script so moving
the project doesn't break the task, logging to `backend\logs\<name>.log` rotated at
1 MB, and `[CHYBA] navratovy kod %RC%` appended on a non-zero exit (Task Scheduler
only stores a return code, so "ran" and "ran but the source was down" would otherwise
be indistinguishable).

**`scripts/away_check.py` is NOT scheduled.** There is no wrapper for it.
`AKCION_PROVOZ.md` states this explicitly, and the consequence is direct: **away mode
has never sent anything.**

### What each job does

- **`tracker_poll.py`** — reads riskrewardcharts.com. Before the tracker read it also
  runs `_tighten_semafor()` (may only make the market alert stricter, never looser)
  and `_refresh_earnings()`, deliberately ordered ahead of early-exit paths.
- **`breakout_poll.py`** — reads breakoutinvestors.com. Writes only to
  `breakout_watchlist*` tables; deliberately writes nothing into `stocks`.
- **`evaluate_scores.py`** — measures `conviction_score_history` against
  `HORIZONS = (30, 90, 180, 365)` days vs `^GSPC`. The only script returning non-zero
  on DB failure.
- **`refresh_price_history.py`** — fills `ohlcv_data`.
- **`away_check.py`** — one away cycle. Always returns 0 ("staying quiet is a
  success").
- **`news_monitor.py`** — writes nothing to the DB, and its only route file
  (`routes/investment.py`) is never registered in `main.py`. All its endpoints are
  dead.
- **`weekly_summary.py`** — **not scheduled and broken.**
  `send_weekly_summary_email()` imports a `send_email` function that does not exist;
  the `except Exception` swallows the `ImportError` and returns `False`. It can never
  send.

### 🔴 Live bug: the breakout poll has crashed every night since 2026-08-24

`scripts/breakout_poll.py:182` reads `change.detail_cs`, but `SyncResult.changes`
holds dataclasses whose field is `detail` (`detail_cs` exists only on the ORM row).
`tracker_poll.py` correctly uses `.detail`. The crash lands inside the transaction
scope, which rolls back — so the watchlist snapshot, the change rows, and the
poll-state timestamp are all discarded every time. The job re-reads and re-diffs
everything as new on every run, the 20-hour throttle is defeated, and **no Breakout
notification has ever successfully been sent.** One-line fix: `change.detail`.

---

## Notifications

**Two `NotificationService` classes exist.** `services/notifications.py` is live;
`services/notification_service.py` is reachable only through the unregistered
`routes/investment.py` and is dead code.

**Channels: SMTP email + Telegram only.** No push, no webhooks, no in-app table.

**Live triggers:** away-mode digest, tracker line changes, breakout changes
(currently unreachable — see the bug above), and the manual
`POST /api/notifications/test-alert`. A former confidence-threshold trigger was
deleted; a tombstone comment explains it bypassed every gate (Buy Guard, cylinders,
semafor, caps, pacing, concentration) and had never once executed successfully due to
a signature mismatch.

**Throttling** (`services/away_mode.py`):

```
MIN_PUSH_INTERVAL  = 24 h
MAX_ACTIONABLE_AGE = 2 days
PUSHABLE_ACTIONS   = {LIQUIDATE_HEAVY, SELL_WAIT_TIME, SELL, TRIM}   # BUY deliberately excluded
```

**Dedup, all in Postgres, no files:** `away_mode_state` (singleton row),
`tracker_line_changes.notified_at`, `breakout_watchlist_changes.notified_at`. The
critical invariant, implemented identically everywhere it applies: **the notified
timestamp is stamped only if the send actually returned `True`.** Every sender
returns `False` rather than raising, so a failed delivery leaves the item unmarked
and the next run retries it.

**`scripts/away_check.py --dry-run`** — the safe way to test any change touching this
path (see `INVARIANTS.md` §5). Two suppression layers: `send=False` means the notify
callable is never invoked (no SMTP connection, no Telegram call), and an explicit
`db.rollback()` discards bookkeeping. It does **not** suppress computation or console
output — it prints the would-be subject, body and every held-back reason.
**`--now ISO` alone will send for real** — only `--dry-run` is safe.

**Away mode has never delivered a message.** `away_check.py` isn't scheduled, the
in-process scheduler only runs while the localhost app is open, and see
`DOMAIN_MODEL.md` for why most positions currently lack the lifecycle/cylinder data
the engine needs before it will judge them at all.

---

## Testing and CI

| Check | Command | Directory | Requires |
|---|---|---|---|
| Backend tests | `python -m pytest` | `backend/` | **system Python** — pytest is not in `.venv` |
| Frontend build+typecheck | `npm run build` | `frontend/` | — |
| Frontend tests | `npm test` | `frontend/` | — |
| Frontend lint | `npm run lint` | `frontend/` | — |

`tests/conftest.py` sets `DATABASE_URL=sqlite:///:memory:` and dummy API keys at
**module level, not inside a fixture** — several modules instantiate `Settings()` at
import time (during collection, before any fixture runs), so without this the test
suite would fail to even collect on a machine with no `.env`. No real DB is required
for the suite; `MagicMock` sessions stand in.

**CI (`.github/workflows/ci.yml`)** runs three jobs on push/PR to `main`/`develop`:

- `backend-tests` — installs `requirements.txt` + `requirements_test.txt`,
  `py_compile`s four modules, then `pytest tests/ -v --cov=app`.
- `frontend-tests` — `npm ci`, `npm run type-check || npx tsc --noEmit`,
  `npm run lint || echo`, `npm run build`.
- `code-quality` — `ruff check --select E,F,W || echo`, `ruff format --check || echo`.

**Gaps in CI, worth fixing:**

- No Postgres service container — everything runs on sqlite/mock defaults, so a
  Postgres-specific defect (a real migration, a real constraint) cannot be caught here.
- **`npm test` (vitest) is never run in CI**, despite `CLAUDE.md` naming it the
  default frontend gate.
- `npm run type-check` **does not exist** in `package.json`; it always falls through
  to the `|| npx tsc --noEmit` branch.
- Lint and format checks are **`|| echo`-suppressed — non-blocking.** Only
  `py_compile`, `pytest`, and `npm run build` can fail the pipeline. `npm run lint`
  currently fails locally with 23 errors and CI would not catch that.

**Dependency audit:** `apscheduler`, `numpy`, `alembic`, `python-docx`,
`google-generativeai` are declared in `requirements.txt` and imported nowhere.

---

## `backend/research/` — offline research lab

Not part of the running service. Purpose: derive Mark Gomes' typical entry shape from
his 12-year "Priority Ideas" track record (see `DOMAIN_MODEL.md` and the
`akcion-gomes-track-record` project memory), so a candidate idea can be compared
against it.

**The one hard invariant, enforced by `tests/test_research_layout.py`:**
`backend/app/` never imports `backend/research/`. The reverse is intentional — shared
math lives in `app/services/entry_features.py`, and research imports it, so the
candidate and the reference are computed by identical code. The test walks the full
AST of every file under `app/` (catching lazy in-function imports too) and asserts
`research/out/` is gitignored.

**Flow:** committed CSVs in `research/data/` → yfinance (cached in `research/out/bars/`)
→ `research/out/reconciliation.csv`, `features.csv` → `research/publish.py` writes the
two files the live app actually reads: `app/data/gomes_entry_profile.json` and
`gomes_registry.csv`.

**Why `research/out/` is gitignored:** everything in it is a function of (committed
inputs + yfinance on a given day), and yfinance rewrites adjusted history backwards on
every split and dividend — a stored copy would silently drift from its source.
`services/score_outcomes.py` refuses to cache adjusted prices for the same reason.

**What the app consumes:** exactly `gomes_entry_profile.json`, read by
`services/gomes_fit.py`, cached into the `gomes_fit_cache` table, and read from that
cache by `find_dossier._gomes_fit_layer` — never over the network at request time.

---

## Known operational defects (see `KNOWN_ISSUES.md` for the full list)

1. **`breakout_poll.py:182`** — wrong field name, crashes and rolls back every night
   since 2026-08-24. No Breakout notification has ever sent.
2. **`portfolio_reconciliation.py` cannot execute** — references enum members that
   don't exist and assigns to read-only `@property` fields. Wired to two live routes
   but unreachable from the UI, which is why the crash hasn't surfaced.
3. **WhatsApp claims are never persisted** despite a docstring claiming they land in
   `ticker_mentions` — the paste route returns claims over HTTP and writes nothing.
4. **`GET /api/notifications/status` lies** about configuration state (see
   `ALERT_CHECK_INTERVAL` trap above).
5. **`start_background.ps1` targets the wrong port** (8000; the server binds 8002) —
   it cannot stop a running backend.
6. **`routes/investment.py` is never registered**, so `news_monitor.py` and the dead
   `notification_service.py` stack are unreachable.
7. **`weekly_summary.send_weekly_summary_email()` can never send** — imports a
   function that doesn't exist.
8. **`NYSE_HOLIDAYS_2026` needs a 2027 update** or it will treat holidays as trading
   days from 2027.

---

## See also

- `INVARIANTS.md` §5 — secrets, dry-run and key-in-log rules that apply to every
  integration above
- `DOMAIN_MODEL.md` — what the data these jobs fetch is used to decide
- `API_REFERENCE.md` — the HTTP surface these services back
- `KNOWN_ISSUES.md` — full triaged list
