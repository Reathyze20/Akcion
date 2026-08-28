# API Reference

**Type:** Reference · **Source:** `backend/app/main.py` + `backend/app/routes/*.py`
· **Verified:** 2026-08-28 against a runtime dump of `app.routes` (170 unique
`(METHOD, path)` pairs; 8 are FastAPI's own docs routes, 6 are dead shadowed
duplicates)

There is **no authentication anywhere in this API**. It is a single-user app bound to
`0.0.0.0`. Do not expose it to a network you do not control.

---

## Application setup

```python
app = FastAPI(
    title=settings.app_name,        # "Akcion"
    version=settings.app_version,   # "1.0.0"
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)
```

| Concern | Reality |
|---|---|
| CORS | Single `CORSMiddleware` with a **hardcoded** origin list: `localhost` and `127.0.0.1` on ports 3000, 5173, 5174. `allow_credentials=True`, all methods, all headers |
| Other middleware | **None.** No auth, no rate limiting, no request logging |
| Startup | `@app.on_event("startup")` (deprecated style): `initialize_database()` then `await start_scheduler()`. **Both failures are printed, not fatal** — the app boots with a broken DB |
| Shutdown | `await stop_scheduler()` |
| Global exception handling | **None.** Every handler does its own `except Exception → HTTPException(500, str(e))`, which leaks raw exception text into responses |

> **Config drift:** `Settings.cors_origins` exists with a validator but is never read.
> Editing `CORS_ORIGINS` in `.env` has no effect.

### Background scheduler — `app/services/alert_scheduler.py`

A plain `asyncio.Task`, not APScheduler.

- Loop: if local time is 08:00–21:00 (`is_waking_hours()`) → `run_alert_check()`;
  then sleep `ALERT_CHECK_INTERVAL` minutes (default **30**).
- `run_alert_check()` calls `app.routes.away.run_away_cycle(send=True, notify=_deliver)`.
  **This is the only outbound push path in the app**, and it no-ops unless away mode is on.
- `_deliver()` uses `NotificationService.from_env()` and returns `bool` instead of
  raising, so a failed send leaves the quiet period unstarted.

### Root-level endpoints

| METHOD | Path | Notes |
|---|---|---|
| GET | `/api/health` | `HealthCheckResponse`. **Does not actually check the DB**, despite its docstring |
| GET | `/` | `{message, version, docs, health}` |

Six further handlers are declared directly on `app` and are **dead — shadowed by
routers registered later**: `POST /api/analyze/{text,youtube,google-docs}`,
`GET /api/stocks`, `GET /api/stocks/{ticker}`, `GET /api/stocks/{ticker}/history`.
They are also broken (they read request fields that no longer exist on the imported
schemas). See [Dead code](#dead-code).

---

## Router registry

Registration order matters — later routers shadow earlier paths.

| # | Module | Prefix | Tag |
|---|---|---|---|
| 1 | `portfolio` | `/api/portfolio` | portfolio |
| 2 | `stocks` | `/api/stocks` | Portfolio |
| 3 | `gap_analysis` | `/api/analysis` | analysis |
| 4 | `analysis` | `/api/analyze` | Analysis |
| 5 | `trading` | `/api/trading` | trading |
| 6 | `intelligence` | `/api/intelligence` | Intelligence |
| 7 | `gomes` | `/api/gomes` | Gomes Analysis |
| 8 | `intelligence_gomes` | `/api/intelligence` | Gomes Intelligence |
| 9 | `notifications` | `/api/notifications` | notifications |
| 10 | `daily_actions` | `/api/trading` | Daily Actions |
| 11 | `currency` | `/api/currency` | currency |
| 12 | `yahoo_finance` | `/api/yahoo` | Yahoo Finance |
| 13 | `sec` | `/api/sec` | sec |
| 14 | `away` | `/api/away` | away |
| 15 | `market_gauge` | `/api/market-gauge` | market-gauge |
| 16 | `cash_hedge` | `/api/cash-hedge` | cash-hedge |
| 17 | `breakout` | `/api/breakout` | breakout |
| 18 | `finds` | `/api/finds` | Nálezy |
| 19 | `revenue_models` | `/api/revenue-models` | Analytikovy modely tržeb |
| 20 | `intake` | `/api/intake` | Intake |
| 21 | `dev_utils` | `/api/dev` | Development — **only when `settings.debug`** |

Two prefixes are deliberately shared: `/api/intelligence` (`intelligence` +
`intelligence_gomes`) and `/api/trading` (`trading` + `daily_actions`). No path
actually collides, but OpenAPI splits each across two tags.

**Never registered:** `routes/investment.py` and `routes/master_signal.py`.

---

## Endpoints by router

### `/api/portfolio` — portfolio, positions, trades, semafor

| METHOD | Path | Purpose |
|---|---|---|
| GET | `/portfolios` | List portfolios with computed totals (`?owner`) |
| POST | `/portfolios` | Create |
| GET | `/portfolios/{portfolio_id}` | Portfolio + positions + CZK totals → `PortfolioSummaryResponse` (incl. `unconvertible_positions[]`) |
| DELETE | `/portfolios/{portfolio_id}` | Delete + cascade positions |
| POST | `/portfolios/{id}/positions` | Add or average into a position |
| DELETE | `/portfolios/{id}/positions/{ticker}` | Delete one; auto-adds to `ActiveWatchlist` |
| DELETE | `/portfolios/{id}/positions` | Delete **all** positions |
| PUT | `/portfolios/{id}/cash-balance` | Set cash (**query param**, not body) |
| PUT | `/portfolios/{id}/monthly-contribution` | Set contribution (**query param**) |
| POST | `/upload-csv` | Broker CSV import (upsert) → `CSVUploadResponse` |
| POST | `/upload-csv-smart` | CSV import **with sale reconciliation** |
| POST | `/refresh` | Refresh prices → `PriceRefreshResponse` |
| GET/POST | `/positions` | List / create |
| PUT | `/positions/{position_id}` | Patch-style update (`exclude_unset`) |
| POST | `/positions/{position_id}/trade` | **Record an already-executed BUY/SELL** into the immutable ledger |
| DELETE | `/positions/{position_id}` | Delete |
| GET | `/market-status` | Semafor + catalyst freshness verdict |
| PUT | `/market-status` | Set semafor. **422 if ORANGE/RED without a `catalyst_description`** |
| GET | `/owners` | Distinct owner names |
| POST | `/allocate/{portfolio_id}` | Kelly allocation plan (`?available_eur`, `?additional_czk`) |
| GET | `/family-audit` | Positions one owner holds and the other does not |
| POST/GET | `/logs` | Journal entries (POST takes **all params as query string**) |
| GET | `/logs/monthly-summary` | Monthly aggregate (requires `year`, `month`) |

`TradeResponse` returns `realized_pl = null` when cost basis is unknown, plus an
explicit `avg_cost_known` flag — an instance of the "name the gap" rule.

`_band_at_trade()` stamps the green/red line and cylinder count onto the trade at
execution time so the canon's 3-point rule stays computable afterwards.

**Known problems.** `upload_csv` and `upload_csv_with_reconciliation` use
`db = next(get_db())` instead of `Depends(get_db)`, so the session is never closed by
the dependency system; `upload_csv` also appends to a **relative** file
`csv_upload.log` five times per request. Two different functions are named
`delete_position` in one module.

---

### `/api/stocks` — analyses and manual overrides

| METHOD | Path | Purpose |
|---|---|---|
| GET | `/` | All analyses + earnings badges + fallback price lines (`?sentiment`, `?min_conviction_score`, `?min_conviction`, `?speaker`) |
| GET | `/enriched` | Same plus live prices, `price_position_pct`, `price_zone` |
| GET | `/high-conviction` | Score ≥ 7 |
| GET | `/{ticker}` | Latest analysis |
| GET | `/{ticker}/history` | All historical analyses |
| GET | `/{ticker}/sources` | Gomes vs Breakout side by side → `agreement: AGREE\|MIXED\|CONFLICT\|SINGLE\|NONE` |
| GET | `/stats/summary` | Counts, sentiment breakdown, average score |
| PUT | `/{ticker}/price` | Manual price / line override |
| PUT | `/{ticker}/score` | Manual conviction score (creates the stock if absent) — **journals via `record_score`** |
| PATCH | `/{ticker}` | Partial manual edit of ~10 fields — **does *not* journal the score** |

**Known problems.** The Gomes valuation-zone classification (`DEEP_VALUE`,
`BUY_ZONE`, `ACCUMULATE`, `FAIR_VALUE`, `SELL_ZONE`, `OVERVALUED`) is implemented
*inside this route module*, and `portfolio.py`, `intelligence_gomes.py` and
`services/ladder_view.py` each carry their own variant. `PATCH /{ticker}` is an
untracked scoring path. Ticker matching is inconsistent: `PUT /{ticker}/price` uses
`ilike`, the other two use `== ticker.upper()`. Two copy-paste bugs produce duplicate
dict keys in `/high-conviction` and `/stats/summary`.

---

### `/api/analyze` — transcript ingestion

| METHOD | Path | Purpose |
|---|---|---|
| POST | `/text` | Analyze a raw transcript (201) |
| POST | `/youtube` | Fetch YouTube transcript, then analyze (201) |
| POST | `/google-docs` | Fetch a Google Doc, then analyze (201) |
| GET | `/health` | Config-only health of the analysis path |

**Known problems.** The three handlers are ~90 % duplicated — the market-status
detection block is copy-pasted verbatim three times. All three **write the market
semafor as a side effect of a transcript analysis**, bypassing the catalyst guard that
`PUT /api/portfolio/market-status` enforces. `_refresh_verdicts_async()` is not async
and blocks the request. `/health` reports on `anthropic_api_key` while the handlers
construct `StockAnalyzer(api_key=settings.gemini_api_key)` — the health check and the
code path check different credentials.

---

### `/api/analysis` — gap analysis

| METHOD | Path | Purpose |
|---|---|---|
| GET | `/match` | Every analysis enriched with position data + match signal |
| GET | `/opportunities` | BUY signals on stocks not held |
| GET | `/danger-exits` | SELL signals on stocks held |

`/match` runs `db.query(Stock).all()` — unbounded, with no `is_latest` filter, so
every historical revision of every ticker is enriched.

---

### `/api/trading` — orders, watchlist sync, alerts

| METHOD | Path | Purpose |
|---|---|---|
| POST | `/validate-order` | Pre-flight Gomes compliance check. 403 = market RED; 422 = runway < 6 mo or Stage 4 |
| POST | `/order` | Validate + "place". **No broker execution exists** — `# TODO: Integrate with actual broker API` |
| POST | `/sync/watchlist` | Rebuild `ActiveWatchlist` from verdicts |
| POST | `/sync/data` | Background OHLCV fetch |
| GET | `/ohlcv/{ticker}` | Historical OHLCV (`?days=60`) |
| DELETE | `/signals/expire` | Mark expired signals inactive |
| GET | `/watchlist` | Active tickers |
| GET | `/alerts` | `GomesAlert` list |
| GET | `/alerts/count` | Badge counts |
| POST | `/alerts/{id}/read` | Mark read |
| POST | `/alerts/{id}/action` | acknowledged / dismissed / acted_upon |
| GET | `/stocks-needing-review` | `Stock.needs_review == True` |

`GET /api/trading/signals` was **deliberately deleted** — a tombstone comment at
lines 140–144 records that it was a sixth competing answer to the daily-action
question, built on ML predictions that no longer exist. `MLPredictionEngine` imports
fall back permanently to `ML_ENGINE_AVAILABLE = False`.

This module calls `Settings()` at import time (line 53), so it crashes when `.env` is
missing — unlike `gomes.py`, which deliberately uses the cached `get_settings()`.

---

### `/api/trading` (daily_actions) — the decision surface

| METHOD | Path | Purpose |
|---|---|---|
| GET | `/daily-actions` | **"Co mám dnes udělat?"** — at most 3 ranked actions, or `HOLD_HOLD_HOLD` |
| GET | `/daily-actions/by-owner` | Every account answered **separately**, never merged |
| GET | `/board` | One card per company, with per-owner instructions |

`ActionItem`: `id, ticker, source_key, action_type (TRIM|SELL_WAIT_TIME|SELL|BUY|
LIQUIDATE_HEAVY|ROZPOR), current_price, currency, target_price, quantity,
estimated_czk_value, reason, urgency_score, review_required, portfolio_id, owner,
limit_price, limit_currency, valid_until, invalidated_if`.

**This is the well-factored router** and the model to copy. All rule logic lives in
`services/daily_actions.py`; the route only assembles the DB snapshot.
`load_daily_action_inputs()` is the shared snapshot loader and is the app's only
cross-route import (`away.py` uses it). Refusals commit separately so a failed
measurement write never costs the owner their morning list. Merging across accounts is
presentation-only — caps are always computed per account.

---

### `/api/intelligence` (intelligence.py) — transcripts, SWOT, synthesis, calibration

| METHOD | Path | Purpose |
|---|---|---|
| POST/GET | `/transcripts` | Create (201) / list (`?source_name, ?ticker, ?date_from, ?date_to, ?is_processed, ?limit≤200`) |
| GET/PATCH/DELETE | `/transcripts/{id}` | Read / update / delete (204) |
| POST/GET | `/swot` | Create (deactivates prior active) / list |
| GET | `/swot/ticker/{ticker}` | Latest active SWOT |
| PATCH | `/swot/{swot_id}` | Update |
| POST | `/swot/expire-old` | Expire > 90 days (calls SQL fn `expire_old_swot_analyses()`) |
| GET/PATCH | `/watchlist[/{ticker}]` | Watchlist + analysis (raw SQL over view `v_watchlist_analysis`) |
| GET | `/top-gomes/{limit}` | Top tickers by score (SQL fn `get_top_gomes_tickers`) |
| GET | `/stats` | Counts, average score, top sources |
| POST | `/synthesize` | **"Brain Logic"** — merge new info without overwriting; reports `conflicts[]` |
| POST | `/quick-note/{ticker}` | Fast synthesize (**query params**, not a body) |
| GET | `/alerts` | Thesis drift alerts |
| POST | `/alerts/{id}/acknowledge`, `/alerts/acknowledge-all` | Acknowledge |
| GET | `/score-calibration` | **Do high scores actually outperform?** `?horizon=90`. **Read `sufficient` first** |
| GET | `/score-history/{ticker}` | Score journal |
| POST | `/reconcile/preview`, `/reconcile/{portfolio_id}` | Dry run / execute |
| GET | `/notifications` | Aggregated feed |

`/score-calibration` returning `sufficient: false` is the **correct** state until the
journal matures (opened 2026-08-23; first 30-day measurement 2026-09-22; full
calibration ~Aug 2027). See `DOMAIN_MODEL.md`.

**Known problems.** A second import block sits halfway down the file (lines 366–376).
Several request/response models are defined inline instead of in `schemas/`. A comment
at lines 775–780 warns of a bug in `GET /notifications` that appears already fixed —
the comment is stale and misleading.

---

### `/api/intelligence` (intelligence_gomes.py) — the Gatekeeper

| METHOD | Path | Purpose |
|---|---|---|
| GET/POST | `/market-alert` | Alert level + target allocation. **POST has no catalyst guard** |
| GET/POST | `/lifecycle[/{ticker}]` | AI lifecycle classification — **bypasses the ratchet**; prefer `/api/gomes/lifecycle/{ticker}` |
| GET/POST | `/price-lines[/{ticker}]` | Green/red/grey lines + zone |
| POST | `/verdict` | **The Gatekeeper** — full verdict from supplied inputs |
| GET | `/verdict/{ticker}` | Same, from stored data |
| POST | `/scan` | Scan the watchlist → ranked verdicts + blocked list |
| GET | `/top-opportunities` | Dashboard widget (untyped) |
| GET | `/blocked` | Stocks the filter blocked (untyped) |
| POST | `/position-size` | Tier + max % |
| GET | `/ml-stocks` | Gomes stocks + lines |
| GET | `/dashboard` | Combined dashboard |
| POST | `/analyze-ticker` | LLM ticker analysis from a transcript/video. **429** inside `MIN_ANALYZE_INTERVAL` |

**Known problems.**
- `analyze_ticker_from_transcript` is **~290 lines of business logic inline in the
  route** — the largest handler in the app and the clearest extraction candidate.
- `calculate_position_size` references `LifecyclePhase.UNKNOWN` on line 564 while
  `LifecyclePhase` is only imported inside the `if lifecycle:` branch on line 550 →
  **`NameError` whenever the ticker has no lifecycle row**, swallowed into a 500.
- `get_dashboard` returns `top_opportunities=[]` with `# Would need conversion` — a
  permanently empty documented field.
- `CalculatePositionRequest.portfolio_value` is required and never used.
- `MarketAlertResponse.reason` is hardcoded to `"Current market state"` on GET.

---

### `/api/gomes` — the largest router (83 KB)

| METHOD | Path | Purpose |
|---|---|---|
| POST/GET | `/analyze[/{ticker}]` | Score a ticker via `GomesAnalyzer` |
| POST | `/analyze/batch` | Batch |
| POST | `/scan-watchlist` | Rank stored scores |
| GET | `/top-picks` | Filter the scan by rating |
| GET | `/stats` | **STUB — returns hardcoded zeros** |
| GET | `/ticker/{ticker}/price-lines-history` | Line history |
| POST | `/transcripts/import` | Import a transcript with a historical date |
| GET | `/transcripts` | List |
| POST | `/transcripts/{id}/process` | AI-extract sentiment / actions / lines |
| GET | `/ticker/{ticker}/timeline` | Weighted mention history (−1…+1) |
| POST | `/deep-dd`, `/deep-dd/batch` | 6-pillar deep due diligence |
| POST | `/update-stock/{ticker}` | Update a stock from new information |
| POST | `/update-stock-ai/{ticker}` | **501 `AnalystNotImplemented`** — see `INVARIANTS.md` §1 |
| GET | `/score-history/{ticker}` | Journal only; no fabricated past |
| GET/POST | `/drift-alerts[/{id}/acknowledge]` | Thesis drift |
| POST | `/refresh-all-verdicts` | Re-run the gatekeeper over the watchlist |
| GET/POST | `/weekly-summary[/send-email]` | Weekly digest |
| POST | `/tracker/sync` | Read the Gomes tracker → write bands |
| **GET/POST** | **`/cylinders/{ticker}`** | **Rubric proposal → human confirmation. This is what unlocks buying** |
| **GET/POST** | **`/lifecycle/{ticker}`** | **Phase proposal → human confirmation. The ratchet is unconditional; no override** |
| GET | `/owner-intent/{ticker}` | Standing instruction (read-only) |
| GET | `/ladder` | Whole portfolio: band + two limit prices per company |
| POST | `/whatsapp/paste` | Parse a WhatsApp export; optionally extract claims |

The **cylinders and lifecycle endpoints are the architectural centre of the Buy
Guard** — they are the only two that implement the propose→human-confirm gate. See
`INVARIANTS.md` §3.

`GET /api/gomes/analyze-position/{ticker}` was deliberately removed (tombstone at
lines 1705–1710): it published a second competing verdict set whose rule 5 was
unreachable and whose rule 4 always fired first.

**Known problems.**
- `POST /deep-dd` takes a >100-character transcript as a **URL query parameter**;
  `/deep-dd/batch` takes a whole list that way. Both will hit URL length limits.
- `POST /update-stock/{ticker}`: when a body is supplied, `source_type` is still read
  from the query default (lines 1249, 1268); the body's value lands in
  `final_source_type` (line 1231) which is never used. **Real bug.**
- Line 1278 computes `previous_score = score_change + conviction_score` — inverted.
- `GET /drift-alerts` swallows every exception into
  `{"count":0,"alerts":[],"note":"Alerts table not initialized yet"}` — a DB error is
  reported as "no alerts". This is the `INVARIANTS.md` §1 defect class.
- `get_top_gomes_picks` calls `scan_watchlist_gomes(...)` directly as a Python
  function, passing `db=db` — a route calling another route handler.
- `analyze_ticker_gomes` passes `llm_api_key=getattr(settings, "openai_api_key", None)`
  — that attribute does not exist on `Settings`, so it is always `None`.

---

### `/api/finds` — Nálezy (the owner's own ideas)

| METHOD | Path | Purpose |
|---|---|---|
| GET | `/` | List finds, newest first (`?include_closed=false`) |
| POST | `/` | Create, fetch public data, build the dossier (201). **409** if an open find already exists for the canonical ticker |
| GET | `/{find_id}` | Find + **stored** dossier + all assessments |
| POST | `/{find_id}/refresh` | Re-fetch, append a new assessment (free) |
| POST | `/{find_id}/explain` | **The only paid LLM call in this router.** 409 if already explained (unless `?force`), 502 on `FindExplainError` |
| PATCH | `/{find_id}` | Edit note / status. Finds are **closed, never deleted** |

`GET /{find_id}` carries a load-bearing docstring explaining why it must **not**
rebuild the dossier: rebuilding without `enrich()` yields fewer facts, and because
fact IDs are sequential (`FUND-1`, `FUND-2`…), a shorter layer renumbers everything
after it — so stored citations would point at the wrong facts. The same reasoning
governs `/explain`, which explains the *stored* dossier.

`AttentionOut` always carries `ceiling` alongside `points`, so a low score cannot be
misread as a verdict (a low ceiling means "this much cannot be known about this
company", not "this company is bad").

The module docstring says "Sedm endpointů" — there are six. Stale.

---

### `/api/away` — away mode

| METHOD | Path | Purpose |
|---|---|---|
| GET | `/` | Is away mode on; what the last cycle decided |
| PUT | `/` | Turn on/off |
| POST | `/preview` | Dry-run one cycle, send nothing, then `db.rollback()` |

`run_away_cycle()` is a module-level function in a route file that the **scheduler
imports**. It is the shared push pipeline, not a handler.

Away mode **escalates the semafor one step** before generating actions and appends
`escalation_note` to SELL reasons — deliberately, and deliberately not applied to the
normal daily list. `_blind_spots()` ranks warnings by `_BLIND_SPOT_MARKERS`
("NEZNÁMÁ KVALITA" > "SEMAFOR" > "NESEDÍ" > "CHYBÍ") and caps at 3; the ordering is
documented as load-bearing.

---

### `/api/breakout` — Breakout Investors watchlist

| METHOD | Path | Purpose |
|---|---|---|
| GET | `/watchlist` | Everything stored, ours first. **Never touches the network** |
| POST | `/refresh` | Read the source now, then return the same shape |

`WatchlistOut` carries `stale` (> 48 h), `never_read` and `last_error` as first-class
fields precisely so "not read for a week" cannot be misread as "unchanged for a week".
`ScorecardOut` refuses to emit a hit rate below `min_horizon_days` (180) — not zero,
not "40 % so far", but no number at all.

---

### `/api/sec` — SEC EDGAR

| METHOD | Path | Purpose |
|---|---|---|
| GET | `/held` | Tickers with `shares_count > 0` |
| GET | `/{ticker}` | Everything stored for one ticker. **404 with a Czech instruction** when never checked |
| POST | `/sync/{ticker}` | Refresh one (`?with_outlook=true`) |
| POST | `/sync` | Refresh all held; one failure does not abort. `?with_outlook=false` **by default** — it costs one model call per filing |

Only insider codes `P` and `S` count as signal; everything else is collapsed into
`insider_non_signal_count`. A fundamentals failure becomes a named `gaps` entry, never
silence. `/held` must stay declared **before** `/{ticker}`.

---

### `/api/market-gauge`

| METHOD | Path | Purpose |
|---|---|---|
| GET | `/` | Where the S&P sits on its 40-year log trend (`?refresh=false`). **503 rather than a default reading** |

The module docstring states there is **deliberately no endpoint that applies the
reading to the semafor** — the gauge catches one of the canon's two RED calls and
misses the other, so it reports and the owner decides. `blind_spot_cs` is mandatory in
every response.

---

### `/api/cash-hedge`

| METHOD | Path | Purpose |
|---|---|---|
| GET | `/` | Semafor → instruments and share counts. **400 when the semafor is unset** |

`_portfolio_value()` names every position it had to exclude (no price, unconvertible
currency) rather than folding it in at zero. `interpreted=true` flags percentages the
app inferred rather than read from the canon.

---

### `/api/revenue-models` — analyst revenue models vs. reality

| METHOD | Path | Purpose |
|---|---|---|
| GET | `/` | List model summaries (`?ticker`) |
| GET | `/{model_id}` | Summary + lines |
| POST | `/` | Create a model with ≥1 line (201) |
| POST | `/{model_id}/compare` | Fetch SEC actuals, compare period by period |
| DELETE | `/{model_id}` | Delete (204) |

The module docstring states explicitly that **no LLM is called anywhere here** and
that nothing writes to `stock_lifecycle`, `stocks` or `positions`. `/compare` is a
separate POST so the network hit never happens on page load — the same pattern as
`POST /api/finds/{id}/refresh`.

---

### `/api/intake` — Gemini Flash intake

| METHOD | Path | Purpose |
|---|---|---|
| POST | `/analyze` | Structured proposal from text or a YouTube URL |
| POST | `/commit` | Persist the human-reviewed result |

Disabled 2026-08-24 and re-enabled 2026-08-25 (see the comment block at
`main.py:149–155`): `/commit` used to write `lifecycle_phase` directly onto columns
that do not exist on the model, bypassing `lifecycle_intake.confirm()` and therefore
the ratchet.

**Ordering inside `/commit` is load-bearing and commented:** `record_score` must run
before any query that would trigger SQLAlchemy autoflush, or the `before_flush` safety
net writes a duplicate `unattributed` journal row.

`CONFIRMED_BY = "Tomas"` is hardcoded.

---

### `/api/currency`, `/api/yahoo`, `/api/notifications`, `/api/dev`

| METHOD | Path | Purpose |
|---|---|---|
| GET | `/api/currency/rates` | All CNB rates to CZK |
| GET | `/api/currency/rate/{currency}` | One rate + liveness |
| POST | `/api/currency/convert` | Convert. **`to_currency` is accepted and silently ignored** — everything converts to CZK |
| POST | `/api/yahoo/stock` | Smart-cached quote |
| POST | `/api/yahoo/bulk-refresh` | 1–50 tickers |
| GET | `/api/yahoo/cache-status/{ticker}` | Cache age debugging |
| GET | `/api/yahoo/market-status` | Is NYSE open (**not** the semafor) |
| POST | `/api/yahoo/manual-refresh/{ticker}` | Force refresh — calls `get_stock_data()` directly |
| POST | `/api/notifications/test-alert` | **Actually sends a real message.** 400 if no channel configured |
| GET | `/api/notifications/status` | Which channels are configured (reads `os.getenv` directly — the only place that bypasses `Settings`) |
| POST | `/api/dev/execute-sql` | **Arbitrary raw SQL, semicolon-split, auto-committed.** Gated only by `DEBUG` |

`StockDataResponse.from_cache` is derived as `not request.force_refresh` — it reports
the *request's intent*, not whether the data actually came from cache.

`POST /api/dev/execute-sql` is full remote code execution against the production
database with no auth. It is correctly absent when `DEBUG=false`.

---

## Schemas

The live definitions are in the **`app/schemas/` package**.

| File | Contents |
|---|---|
| `requests.py` | `AnalyzeTextRequest`, `AnalyzeYouTubeRequest`, `AnalyzeGoogleDocsRequest` |
| `responses.py` | `StockResponse` (~55 fields), `EarningsInfo`, `AnalysisResponse`, `StockPortfolioResponse`, `HealthCheckResponse`, `ErrorResponse` |
| `portfolio.py` | Portfolio / position / trade / CSV / price-refresh / market-status models, `PortfolioSummaryResponse`, `UnconvertiblePosition` |
| `gomes.py` | Market alert, lifecycle, price lines, verdict, scan, dashboard, position size, deep DD |
| `analysis.py` | Transcript, SWOT, watchlist-analysis, stats. Last four models unused |
| `trading.py` | `DataSyncRequest/Response`, `WatchlistSyncResponse` used; the rest are leftovers from the removed ML/backtesting engines |
| `daily_actions.py` | `ActionItem`, `DailyActionResponse`, `BoardCardOut`, `BoardResponse`, … (imported directly, not re-exported) |

Two field-level decisions carry comments worth preserving:

- `StockResponse.catalyst_date` is typed `date` after typing it `str` turned
  `GET /api/stocks` into a 500 and made the app claim no analysis existed.
- `DeepDueDiligenceResult.conviction_score` is `Optional` **on purpose** — a previous
  default of 5 turned model silence into a middling conviction that drove position
  sizing. This is `INVARIANTS.md` §1 in a type annotation.

### `app/schemas.py` is dead and should be deleted

`app/schemas.py` and `app/schemas/` coexist. Python resolves **packages before
modules**, so `app.schemas` always binds to the package and the `.py` file is never
imported. It contains **nine duplicated, divergent models** (`HealthCheckResponse`,
`StocksListResponse`, `StockResponse`, the three `Analyze*Request`s, …) whose request
models still carry a required `api_key` field and use `video_url` instead of `url` —
which is exactly what the dead `main.py` handlers were written against.

Both files share the same latent bug: `conviction_score` is declared **twice** in
`StockAnalysisResult`, the second declaration silently relaxing the first's `ge=1`
constraint to optional.

---

## Run entrypoints

| File | Host | Port | Notes |
|---|---|---|---|
| `backend/run_server.py` | `0.0.0.0` | **8002** | `uvicorn.run("app.main:app", reload=True)`. **The canonical dev entrypoint** |
| `backend/start.py` | `0.0.0.0` | **8002** | `pip install -r requirements.txt`, then uvicorn. Refuses to run unless CWD has `app/` and `.env` |
| `start.ps1` (root) | — | 8002 + 5173 | Opens two PowerShell windows: backend `run_server.py`, frontend `npm run dev` |
| `start.py` (root) | `0.0.0.0` | **8000** ⚠ | Interactive launcher. Prints `/docs` and `/health` — **both wrong**; the real paths are `/api/docs` and `/api/health` |
| `backend/start_background.ps1` | — | **8000** ⚠ | Kills whatever holds port 8000, then starts `run_server.py` — which binds **8002**. The kill targets the wrong port |

`Settings.api_port` defaults to 8002 but **no entrypoint reads it**; every one
hardcodes its port.

---

## Duplicate and competing endpoints

Multiple endpoints answer the same question with different logic. This is the single
biggest source of confusion in the API.

| Question | Endpoints |
|---|---|
| "What should I do about X?" | `/api/trading/daily-actions`, `/api/trading/board`, `/api/gomes/ladder`, `/api/intelligence/verdict/{ticker}`, `/api/intelligence/scan`, `/api/analysis/match`, `/api/gomes/top-picks` |
| Market alert / semafor | `PUT /api/portfolio/market-status` (**guarded**) vs `POST /api/intelligence/market-alert` (unguarded) vs a side effect of `POST /api/analyze/*` |
| Lifecycle phase | `/api/intelligence/lifecycle*` (AI, **no ratchet**) vs `/api/gomes/lifecycle/{ticker}` (rubric + human confirm + ratchet — **the canon**) |
| Price lines | `/api/intelligence/price-lines*`, `PUT /api/stocks/{ticker}/price`, `/api/gomes/ticker/{t}/price-lines-history`, plus side-effect writes from `/deep-dd`, `/update-stock/{t}`, `/transcripts/{id}/process`, `/tracker/sync` |
| Score history | `/api/gomes/score-history/{t}` vs `/api/intelligence/score-history/{t}` |
| Alerts | `/api/trading/alerts` (`GomesAlert`) vs `/api/intelligence/alerts` + `/api/gomes/drift-alerts` (`ThesisDriftAlert`) vs `/api/intelligence/notifications` (aggregator) |
| Reconciliation | `POST /api/intelligence/reconcile/{id}` vs `POST /api/portfolio/upload-csv-smart` |
| Top picks | `/api/gomes/top-picks`, `/api/intelligence/top-opportunities`, `/api/intelligence/top-gomes/{n}`, `/api/analysis/opportunities` |
| Name collision | `/api/portfolio/market-status` (semafor) vs `/api/yahoo/market-status` (exchange hours) |

---

## Dead code

| What | Detail |
|---|---|
| `backend/app/schemas.py` | Unreachable; 9 duplicated divergent models |
| `backend/app/routes/investment.py` | `/api/invest/*`, 9 endpoints, never registered |
| `backend/app/routes/master_signal.py` | `/api/master-signal/*`, `/api/action-center/*`, 5 endpoints, never registered. Documented as removed 2026-08-24 ("a rival engine whose 'Weinstein phase' read a Green Line as a moving average"). Contains a hard `NameError` and a shadowed route |
| Six handlers in `main.py` | Shadowed by routers and broken against current schemas |
| `GET /api/gomes/stats` | Live route returning hardcoded zeros |
| Most of `schemas/trading.py` | Leftovers from the removed ML/backtest engines |
| `NotificationConfig`, `MatchAnalysisRequest`, `BatchTranscriptCreate`, `BatchSWOTCreate`, `*SearchParams` | Defined, never used |

---

## Convention inconsistencies

- **Query params used as request bodies:** `POST /api/gomes/deep-dd` (a >100-char
  transcript in the URL), `/deep-dd/batch`, `/weekly-summary/send-email`,
  `/api/intelligence/quick-note/{ticker}`, `POST /api/portfolio/logs`,
  `PUT /api/portfolio/portfolios/{id}/cash-balance`, `.../monthly-contribution`.
- **Status codes:** `analysis.py` returns 201 where `main.py` returned 200; most POSTs
  return 200; `finds`, `revenue-models` and `intelligence` use proper 201/204.
- **Response typing:** `finds`, `sec`, `daily_actions` and `breakout` are fully typed;
  `revenue_models`, much of `gomes`, `trading` and `portfolio` return bare `dict`.
- **Pydantic v1 and v2 syntax are mixed** (`class Config` + `validator` in
  `schemas/trading.py` and `schemas/gomes.py`; `model_config` elsewhere).
- **Local imports inside function bodies** are pervasive in `gomes.py`, `trading.py`,
  `portfolio.py`, `intelligence_gomes.py`.

---

## See also

- `ARCHITECTURE.md` — how the layers fit together
- `DOMAIN_MODEL.md` — what the verdicts mean
- `DATA_MODEL.md` — the tables behind these responses
- `KNOWN_ISSUES.md` — the bugs listed above, prioritised
