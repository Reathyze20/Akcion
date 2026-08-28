# Known Issues

**Type:** Reference · **Verified:** 2026-08-28 · Consolidated from a full-codebase
audit plus `docs/AUDIT_2026-08-22.md`, `IMPLEMENTATION_PLAN.md`, and project memory.

Ordered by how much money or trust a defect can move, not by how easy it is to fix.
Each item names the file. "Verified" means read directly in the current codebase on
this date; older audit items not re-verified are marked as such.

---

## P0 — an absent input can currently produce a confident BUY

These are direct instances of `INVARIANTS.md` §1 — the app's own cardinal rule,
broken in code today.

1. **`GET /api/portfolio/market-status` silently creates and commits a default
   GREEN row when none exists** (`routes/portfolio.py`), and `gap_analysis.py` does
   the same. This defeats the fail-closed handling elsewhere: `daily_actions.py`
   correctly passes `None` when no row exists (→ refuse), but after *any* page load a
   GREEN row now exists, and it is stamped fresh — so the 14-day staleness alarm
   cannot catch it for a fortnight. **Fix:** never auto-create; return "no reading"
   and let the Buy Guard's `ALERT_UNKNOWN` gate handle it, as designed.
2. **`GomesGatekeeper.__init__` and `GomesVerdict` default `market_alert=GREEN`**;
   `quick_gomes_check` hardcodes `"GREEN"` (`trading/gomes_logic.py`). Any caller that
   forgets to pass a real alert gets the one value that authorizes purchases.
3. **An LLM reading a pasted transcript sets the global semafor**, unguarded —
   `routes/analysis.py`, the same block duplicated across three handlers, writing
   *both* semafor tables. No catalyst requirement, no tighten-only rule, no
   verification. This directly contradicts the careful tighten-only discipline
   `market_watch.py` otherwise enforces, and contradicts the catalyst guard that
   `PUT /api/portfolio/market-status` (the human path) does enforce.
4. **`core/gomes_compliance.get_market_status` defaults to `'YELLOW'` including on a
   database exception**, and its only blocking rule fires on RED. A DB error becomes
   a permission to trade. This module is currently unreachable from the frontend —
   confirm it stays that way before relying on it for anything.
5. **The `LAYER_NONE` cylinder escape hatch** (`services/cylinders.py`): two
   zero-delta "nothing happened" readings (no insider trades, no filing findings) are
   both `is_hard=True` and satisfy `MIN_HARD_READINGS = 2` on their own — so a company
   with **no financial data whatsoever** computes cylinders = 5 (the base), deserved =
   5.0, confidence MEDIUM. A silent-absence company should refuse to propose, not
   propose a neutral middle.
6. **`RiskRewardCalculator.get_action_zone` assumes cylinders = 5 when cylinders are
   unknown** and emits BUY/SELL from that assumption, where the sanctioned path
   (`decide_from_score`) correctly returns `WATCH`. Reaches three
   `/api/intelligence` endpoints and one `GomesGatekeeper` rule.
7. **`MarketDataService.get_current_price` drops its own staleness flag on return** —
   the internal Yahoo-cache helper correctly returns `(price, is_stale)`, but the
   public function returns a bare float, so a stale cached price is indistinguishable
   from a live quote by every caller downstream (the band, the R/R score, the
   verdict). Only a log line records the loss.
8. **`trading_zones.calculate_trading_zones` never checks `red > green`** (unlike the
   canonical `calculate_rr_score`, which does) — an inverted band, from any bad write,
   emits `BUY`/`AGGRESSIVE_BUY` unconditionally, with no cylinders input at all.
9. **`core/gomes_compliance`'s ticker lookup clears any ticker it cannot find** —
   unknown ticker → every rule after the first is skipped → `"✅ ORDER CLEARED"`. Its
   lookup does not use the canonical-ticker resolution the rest of the app relies on,
   so every Canadian cross-listed position takes this path today.
10. **`cylinders = 0` still produces a real, top-ranked band on the ladder.**
    `deserved_score(0) = 10.0`, so `ZoneLadder.read` proceeds past its "no confirmed
    quality" refusal and labels a zero-cylinder company `POD_ZELENOU` (cheapest
    tier — sorted first on screen). The Buy Guard correctly treats `cylinders == 0`
    as unknown and refuses, but `ladder_view.py` never calls the guard, so the ladder
    and the guard disagree about the same position.
11. **`cylinder_intake.confirm()` silently drops `rough_patch`, `rough_patch_since`,
    and `phase_reached` on every new confirmation** — the replacement row doesn't
    copy them forward. This disarms the exact rough-patch staleness gate the
    confirmation flow exists to protect, with no test covering it.
12. **`POST /api/gomes/cylinders/{ticker}` is an undocumented ratchet bypass** —
    it accepts a free-string `phase` and writes it directly to the row without
    calling `apply_ratchet`, while the lifecycle endpoint's own docstring promises
    "there is no escape hatch." Two confirmation endpoints, one enforces the ratchet
    and one doesn't.

---

## P1 — the frontend re-derives a verdict the backend already computed, and can disagree with it

The single largest architectural risk in the app (see `ARCHITECTURE.md`
"Duplicate engines"). All verified in `frontend/src/components/InvestmentTerminal.tsx`.

13. **`getActionCommand()` — the Portfolio tab's "Pokyn" column — never consults
    cylinders at all**, only `conviction_score`. It checks only that a band *exists*
    (`!!position.band`), not its *value* — a position in `PREPLACENO` (overvalued)
    passes the same check as one at the green line. It has no counterpart to the
    backend's `NOT_CHEAP_ENOUGH` gate, no rough-patch check, no asset-class cap, no
    dual-source check, no pacing/concentration check, and — critically — **no
    `owner_intent` check**, so ECOR and SMSI (both under a standing `EXIT_PENDING` /
    `TAX_LOSS_HOLD` instruction) can still render a buy-side word in this one column.
    Concrete failure mode: GOLD_MINE, GREEN, band `PREPLACENO`, conviction 9,
    underweight → renders bold green **"STRONG BUY"**, while the real
    `check_buy_guard` returns `NOT_CHEAP_ENOUGH` for the same position. **The
    authoritative answer already exists and the same component already fetches
    it** — `GET /api/trading/board`'s `BoardCardOut.owners[].instruction_cs`. Replace
    the column with that field.
14. **A second, hardcoded sizing model** (`TARGET_WEIGHTS`,
    `calculateMaxAllocationCap()`) runs in the browser as a fallback whenever the
    backend omits `max_allocation_cap`, duplicating `asset_class_caps.py`'s policy
    with different numbers.
15. **`WatchlistDetailModal` prints a "Strong Buy Signal" panel with no gate at
    all** — triggered purely by `score >= 7 && price_zone ∈ {DEEP_VALUE, BUY_ZONE,
    ACCUMULATE}`.
16. **The market alert, lifecycle phase, and price lines each have two write paths**
    with different guard behaviour — see the duplicate-endpoints table in
    `API_REFERENCE.md`. Extend the guarded path; never add a third path.

---

## P2 — dead or broken machinery that looks live

17. **The nightly Breakout poll has crashed every run since 2026-08-24.**
    `scripts/breakout_poll.py` reads `change.detail_cs` on a dataclass whose field is
    actually `detail`. The crash happens inside the transaction scope, which rolls
    back — so the snapshot, the change rows, *and* the poll-state timestamp are all
    discarded every time, defeating the 20-hour throttle and re-diffing everything as
    new on every run. **No Breakout notification has ever successfully sent.**
    One-line fix: `change.detail`.
18. **`services/portfolio_reconciliation.py` cannot execute at all.** It references
    `InvestmentLogType.SALE`/`.PARTIAL_SALE`/`.PURCHASE`, none of which exist on the
    enum (which has `DEPOSIT/BUY/SELL/DIVIDEND/MILESTONE/BADGE`); it passes
    `price_per_share=`/`total_amount=` to a model whose fields are named
    `amount`/`shares`/`price`; and it assigns to `Position.cost_basis`,
    `.market_value`, `.unrealized_pl*`, which are read-only `@property`. Wired to two
    live routes (`POST /api/intelligence/reconcile/{id}`,
    `POST /api/portfolio/upload-csv-smart`) but unreachable from the UI — which is
    why the crash hasn't surfaced yet. **Also note:** the reconcile endpoint accepts
    an empty position list with no guard, which would delete every position.
19. **`weekly_summary.send_weekly_summary_email()` can never send** — it imports a
    `send_email` function from `services.notifications` that does not exist; the
    catch-all `except Exception` swallows the `ImportError` and returns `False` with
    no trace of why.
20. **`scripts/away_check.py` is not scheduled anywhere.** There is no Windows Task
    Scheduler wrapper for it (all four other daily jobs have one). Combined with
    the in-process scheduler only running while the app is open on a desktop, **away
    mode has never sent a message.**
21. **`GET /api/notifications/status` reports `configured: false` on a genuinely
    working setup.** It reads `os.getenv` on `SMTP_FROM_EMAIL`/`SMTP_TO_EMAIL`, names
    that exist in neither `Settings` nor a correctly filled `.env` — and
    pydantic-settings does not export `.env` values into `os.environ`, so the check
    can never see a real configuration.
22. **`ALERT_CHECK_INTERVAL` in `backend/.env` has no effect**, for the identical
    reason — `alert_scheduler.py` reads it via `os.getenv`. The interval is
    effectively fixed at 30 minutes unless set in the real process environment, not
    the `.env` file.
23. **`app.services.gomes_gatekeeper` does not exist as a module** — `routes/gomes.py`
    imports it unconditionally for `POST /api/gomes/refresh-all-verdicts`, making
    that endpoint permanently 500; `routes/analysis.py` imports the same nonexistent
    module inside a swallowed `try/except ImportError`, silently no-opping instead.
24. **`ml_predictions` has no writer anywhere in the codebase**, yet
    `services/gomes_intelligence.py` and the unregistered `investment_engine.py`
    both read it and feed the (always-empty) result into verdicts. `has_ml_prediction`
    is permanently `False`.
25. **`gomes_alerts` has exactly one writer, `services/thesis_monitor.py`, which is
    itself dead code.** Three live endpoints read the table and always return empty —
    indistinguishable, from the UI, from "nothing is wrong."
26. **`master_signal.py` is unregistered, and for good reason** — every one of its
    failure paths returns a fabricated `combined_score = 50.0` rather than refusing,
    and one branch parses a numeric-looking phrase out of free-text notes with a
    regex to invent a cash-runway figure. Keep it unregistered; it is the textbook
    example of the defect class this app exists to avoid, not a feature to revive.
27. **`GET /api/gomes/stats` is a live route returning hardcoded zeros.**
28. **`app/schemas.py` is dead** — Python resolves the `schemas/` package first, so
    this file (with 9 duplicated, divergent models including a required `api_key`
    field nothing else uses) is never imported. Safe to delete.
29. **`routes/investment.py` and `routes/master_signal.py` are never registered** in
    `main.py`, so `services/news_monitor.py` and a second, entirely unused
    `NotificationService` implementation are unreachable dead weight.

---

## P3 — data traps to know before trusting a number

30. **`ticker_mentions.is_current` is written backwards by both writers** — the
    backfill script marks real, quoted Gomes statements `is_current=False`; the live
    route marks bare content-free ticker hits `is_current=True`. Filtering on
    `is_current IS TRUE` returns empty rows instead of ~355 real statements. **Never
    write a new query against this column with that filter** — filter on content
    presence instead, following `services/find_dossier.py::_gomes_mentions`. The SQL
    view `v_latest_ticker_mentions` still filters on it and should not be trusted
    directly.
31. **`stocks.line_currency` is hardcoded to `"USD"` in two call sites** rather than
    read from the column (`routes/portfolio.py::_band_at_trade`,
    `routes/daily_actions.py` for Breakout rows) — while the same file reads the real
    column for Gomes rows a few lines away. See `DATA_MODEL.md` for the full
    currency-column inconsistency table.
32. **`000_clean_schema.sql` is not a usable from-scratch database baseline.** It
    covers only 9 of ~47 tables, predates the entire August feature set, and actively
    reintroduces two fixed defects if used: `avg_cost NOT NULL DEFAULT 0` and
    `monthly_contribution DEFAULT 0` instead of the real 20000. Never build a new
    database from it alone.
33. **`add_gomes_intelligence.sql` contains invalid PostgreSQL** (a table-level
    `CHECK ... WHERE`, which Postgres does not support) — the "one active phase per
    ticker" uniqueness rule for `stock_lifecycle` almost certainly does not exist in
    any real database, only in the ORM model.
34. **The `gomes_score` → `conviction_score` rename is half-done at the schema
    level** — several tables and at least one SQL view/function still reference the
    old name, while the model layer uses the new one.
35. **`Stock.is_latest` is scoped per-ticker, not per-(ticker, source)** — inserting
    a Breakout analysis for a ticker silently demotes and hides the Gomes row from
    the ~15 call sites that filter `is_latest == True`. Prefer the newer
    `DISTINCT ON (ticker, source_key)` pattern used in `daily_actions.py`.
36. **`routes/intake.py` writes `stock.thesis`, a column that does not exist** on the
    `Stock` model (only `thesis_narrative` does). SQLAlchemy silently discards the
    assignment — the Czech summary is lost on every intake with no error anywhere.
37. **`NYSE_HOLIDAYS_2026` is hardcoded with no year check** and needs a manual
    update for 2027, or the cache will start treating holidays as trading days.
38. **SEC EDGAR's `USER_AGENT` is hardcoded** with a personal email and has no env
    override; the request throttle is per-client-instance, not process-global, so
    concurrent clients can exceed SEC's rate limit.
39. **`populate_price_lines.py`** (backend root) writes fabricated sample green/red
    lines straight into the live `stocks` table for `KUYA.V` and four fictional
    tickers. The existence of `scripts/clean_fake_stock_lines.py` (whose docstring
    names exactly these rows) confirms this already happened once. Do not run this
    script against a live database.
40. **Known-stale fabrication residue:** `KUYA.V` still carries invented cash, burn
    and runway figures from the old `GomesAIAnalyst` stub (see
    `akcion-ai-analyst-was-a-stub` in project memory). The owner decided to leave
    these numbers in place and only stop further writes — do not "fix" them without
    asking first, since that decision was deliberate.

---

## P4 — process and CI gaps

41. **`npm run lint` currently fails** with 23 errors and 2 warnings across 12 files
    (mostly `@typescript-eslint/no-explicit-any`). `REDESIGN_BACKLOG.md` names a
    clean lint run as the item that blocks closing the rest of the frontend rebuild
    backlog.
42. **CI's lint and format checks are non-blocking** (`ruff check ... || echo`,
    `ruff format --check ... || echo`) — only `py_compile`, `pytest`, and
    `npm run build` can actually fail the pipeline. `npm test` (vitest) is **never
    run in CI** at all, despite `CLAUDE.md` naming it the default frontend gate.
43. **No Postgres service container in CI** — the whole suite runs against SQLite/mock
    defaults, so a Postgres-specific defect (a real constraint, a real migration)
    cannot be caught by CI.
44. **The one persistently failing backend test**,
    `test_unvalued_breakout_note.py::test_a_euro_holding_is_converted_before_the_percentage`,
    is a documented defect in the test itself (it hardcodes a percentage against a
    live EUR rate) — not a regression. Do not "fix" the code it tests.
45. **Dependencies declared and never imported:** `apscheduler`, `numpy`, `alembic`,
    `python-docx`, `google-generativeai` (backend); `clsx`, and effectively `sonner`
    (frontend, used only by a dead component).

---

## Frontend-specific defects

46. **Broken CSS classes render in live UI** — `.card`, `.btn`, `border-info`/`bg-info`
    and `primary-card` are used in the live `WatchlistDetailModal` and the
    `StockDetail` "Decision Cockpit" tree but are not defined anywhere reachable
    (only in the unimported `App.css`). These render as unstyled elements.
47. **No `ErrorBoundary` anywhere in the component tree** — any of the several
    documented unguarded-array-access sites (see `FRONTEND.md` "Missing-data
    hazards") takes the whole app to a white screen rather than degrading gracefully.
48. **The FX fallback invents rates**: an unrecognised currency is valued 1:1 against
    CZK and folded silently into the portfolio total — the exact class of bug the
    `unconvertible_positions` warning strip exists to surface, and it bypasses that
    strip entirely.
49. **Five near-identical payment modals** (~1030 lines) — copy-pasted state,
    handlers and persistence effects across debts/shared/savings/Tom/Míša. A change to
    one rarely propagates to the other four. This tab (`Platby`) was contributed by
    another person — check `git log --format='%an' -- <file>` before restructuring.

---

## Open decisions — require the owner, not more code

These are not bugs; they are unresolved questions the audits surfaced that only the
owner can settle. See `IMPLEMENTATION_PLAN.md` §25/§27 for full context.

- **ECOR and SMSI have coverage from neither analyst source.** Continue reporting
  "outside the method" honestly, or find a substitute source? (Current decision:
  both are under `owner_intent` — ECOR `EXIT_PENDING`, SMSI `TAX_LOSS_HOLD` — see
  `akcion-exit-intent-ecor-smsi` in project memory.)
- **Two positions (KUYAF score 10, OPTX score 9) are both `BUY_NOW` with neither a
  band nor cylinders under them.** Trace the source of these scores, or clear them?
- **The four Canadian cross-listed positions (54 % of portfolio value) will likely
  never clear the SEC-coverage cylinder threshold** — worth lowering the threshold for
  them specifically, finding an equivalent to SEDAR+, or leaving them permanently
  manual?
- **`price_lines_data.py` was deleted after being found systematically bullish**
  (average +1.2 R/R points versus the real tracker). After `tracker_sync` is fully
  relied upon, should the deleted fallback concept be permanently forbidden from
  returning, even as an emergency fallback? (Current lean: yes — a silent fallback
  means a silent bullish bias when the real source is briefly unavailable.)

---

## See also

- `INVARIANTS.md` — the rules these issues violate
- `ARCHITECTURE.md` — the duplicate-engine pattern behind items 13–16
- `DOMAIN_MODEL.md`, `DATA_MODEL.md` — full context for the P0/P3 items
- `IMPLEMENTATION_PLAN.md` — the running engineering log; read it in full before
  starting work on any item above, since it is frequently ahead of this document
- `docs/AUDIT_2026-08-22.md` — the original full audit (106 findings); many items
  above trace back to it and are re-verified here as of 2026-08-28
