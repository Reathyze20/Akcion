# Data Model

**Type:** Reference · **Source:** `backend/app/database/`, `backend/app/models/*`,
`backend/migrations/*` · **Verified:** 2026-08-28

**Engine: PostgreSQL only** (Neon), via `DATABASE_URL`. SQLAlchemy 2.0.36,
`pool_size=5`, `max_overflow=10`, `pool_pre_ping=True`. Tests use
`sqlite:///:memory:` and build tables from the ORM models — a column that exists
only in a `.sql` migration will pass in production and fail tests with
"no such column".

There are **47 ORM-mapped tables**, **4 raw-SQL-only tables**, and **44 migration
files with no runner, no ledger, and no ordering manifest**. Read the last section
of this document before touching schema.

---

## Session access — three patterns

| Function | Behaviour |
|---|---|
| `get_session()` | raw `Session` or `None`; caller closes |
| `get_db()` | FastAPI dependency generator; closes in `finally`; **never commits** |
| `session_scope()` | `@contextmanager`; commits on success, rolls back on exception, closes in `finally` |

### A global write hook

```python
@event.listens_for(Session, "before_flush")
def _journal_score_writes(session, flush_context, instances):
    from ..services.score_journal import backfill_unattributed
    backfill_unattributed(session)
```

Registered on the `Session` **class**, so it fires for every session in the process —
routes, scripts, the away runner. This is why `Stock.conviction_score` is a
`column_property(..., active_history=True)`: the journal needs the previous value at
set time to tell a real change from a no-op re-assignment, and without
`active_history` a score set on an expired instance (which happens whenever anything
committed earlier in the same request) looks like a change and journals a spurious
`unattributed` row. Consequence documented in `routes/intake.py`: `record_score()`
**must** run before any query that would trigger autoflush.

Exceptions in this hook are logged and swallowed — a broken journal can never break
the write it's journalling.

### Repositories

Only **one** repository class exists: `StockRepository`. Everything else queries the
ORM (or raw `text()`) directly from routes and services.

`StockRepository._handle_existing_versions` demotes the single `is_latest=True` row
**for the ticker across all sources**, then computes a per-source version number.
This means a Breakout Investors analysis inserted for a ticker becomes "latest" and
hides the Gomes row from every reader filtering `Stock.is_latest == True` — which is
most of them. The newer, correct pattern is Postgres
`DISTINCT ON (ticker, source_key)`, used in `daily_actions.py` and
`get_current_by_source()`. See [Traps](#traps-and-column-level-semantics) below.

---

## Table inventory by domain

### Core analysis — `models/stock.py`

**`stocks`** — one analysis of one ticker by one source, versioned.

Identity: `ticker` (indexed), `company_name`. Attribution: `source_type`, `speaker`,
`source_key` (indexed — `GOMES` / `BREAKOUT_INVESTORS` / `OTHER`). Verdict:
`sentiment`, `conviction_score` (a `column_property`, see above), `action_verdict`.
Price lines: `line_currency`, `current_price`, `green_line`, `red_line`, `grey_line`,
`price_position_pct`, `price_zone`. Trading zones: `max_buy_price`,
`start_sell_price`, `risk_to_floor_pct`, `upside_to_ceiling_pct`. Guardian block
(~20 more columns): `cash_runway_months`, `inflection_status`, `thesis_narrative`,
`price_floor`, `max_allocation_cap`, `stop_loss_price`, etc. Versioning: `is_latest`
(indexed), `version`.

**No unique constraints, no foreign keys.** `to_dict()` has a duplicated
`"conviction_score"` key.

### Transcripts and claims — `models/analysis.py`

**`analyst_transcripts`** — `source_name`, `raw_text`, `detected_tickers`
(`ARRAY(String)`), `date`, `is_processed`. CHECK: `date <= CURRENT_DATE`.

**`ticker_mentions`** — one claim about one ticker in one transcript. `ticker`
(indexed), FK to `analyst_transcripts` (cascade delete), `mention_date`,
`sentiment` (default `NEUTRAL`), `context_snippet`, `key_points` (JSONB),
`price_target`. **`is_current` BOOL default True** — see
[the trap below](#is_current-is-written-backwards). Attribution columns added
2026-08: `speaker`, `source_key`, `claim_type`, `thesis_impact`. Python property
`weight` decays with `exp(-0.023 * age_days)`, ~30-day half-life.

> **Not exported from `models/__init__.py`.** Import it directly:
> `from app.models.analysis import TickerMention`.

**`swot_analysis`** — `swot_data` (JSONB), CHECK requires keys `strengths`,
`weaknesses`, `opportunities`, `threats`. Unique index on `ticker WHERE is_active`.

### Portfolio — `models/portfolio.py`

**`portfolios`** — `owner` (indexed, default `"Default User"`), `broker`
(`T212|DEGIRO|XTB`), `cash_balance`, `monthly_contribution` (default **0.0** — see
`INVARIANTS.md`, the app never invents a budget). No `UNIQUE(name, owner)` in the
model (only in the stale `000_clean_schema.sql`).

**`positions`** — `ticker` (indexed), `shares_count`, **`avg_cost` nullable** (NULL =
unknown; DeGiro exports carry no buy price), `currency` (default `USD`),
**`currency_confirmed`** (default False). Properties `cost_basis`,
`unrealized_pl`, `unrealized_pl_percent` return `None` — never 0 — when `avg_cost` is
NULL; `market_value` returns 0.0 when price is missing. No
`UNIQUE(portfolio_id, ticker)` in the model.

> **Contract mismatch:** `routes/portfolio.py`'s add-position request declares
> `avg_cost: float = Field(..., gt=0)` — required, strictly positive — while
> `schemas/portfolio.py`'s `PositionBase` has `avg_cost: float | None = None`. Two
> request schemas disagree on whether cost is required.

**`market_status`** — the live semafor (conceptually one row). `status`
(`GREEN|YELLOW|ORANGE|RED`, default GREEN), plus the catalyst block:
`catalyst_description`, `catalyst_identified_at`, `catalyst_severity_known` (default
**False** — "nobody named the cause", not "it's fine"). Nothing in the app ever
lowers the alert automatically; only a dated catalyst can de-escalate.

**`investment_logs`** — the trade ledger and gamification journal. `log_type`
(`DEPOSIT|BUY|SELL|DIVIDEND|MILESTONE|BADGE`), `trade_date` nullable (readers fall
back to `created_at` when unknown), `amount`, `shares`, `price`, `cost_basis`,
**`realized_pl` nullable — never 0** when cost basis is unknown. Entry-valuation
snapshot: `rr_score_at_entry`, `green_line_at_entry`, `red_line_at_entry`,
`cylinders_at_entry`, `line_currency`.

### Gomes intelligence — `models/gomes.py`

**`market_alerts`** — the **older** semafor table, still read by
`core/gomes_compliance.py` and `services/gomes_intelligence.py`. CHECK enforces
`stocks_pct + cash_pct + hedge_pct = 100.00`. See
[the two-semafor trap](#two-semafor-tables-both-written) below.

**`stock_lifecycle`** — the single most semantically loaded table in the schema.
`ticker` (indexed), `phase` (`GREAT_FIND|WAIT_TIME|GOLD_MINE|UNKNOWN`). **The
ratchet:** `phase_reached` (a high-water mark, monotone, never lowered),
`rough_patch` (an orthogonal temporary flag, never a phase demotion by itself),
`rough_patch_since`/`_until`/`_note`. Investability: `is_investable`,
`cylinders_count` (0–10). **The confirmation gate:**
`cylinders_confirmed_at` (NULL = proposal only, authorises nothing),
`cylinders_confirmed_by`, `cylinders_valid_until`. Rows are versioned via
`valid_until` (NULL = the active row). See [§3](#confirm-vs-propose) for the write
discipline, which is inconsistent between cylinders and phase.

**`price_lines`** — a **second, separate** band store from `stocks.green_line` — see
[the trap below](#two-price-line-stores).

**`position_tiers`** — `tier` (`PRIMARY|SECONDARY|TERTIARY`), `max_portfolio_pct`
(CHECK 0–20).

**`investment_verdicts`** — the gatekeeper's recorded decision: `verdict`
(`STRONG_BUY|BUY|ACCUMULATE|HOLD|TRIM|SELL|AVOID|BLOCKED`), `passed_gomes_filter`,
`blocked_reason`, full context snapshot (lifecycle, market alert, tier, price vs.
lines). **`days_to_earnings` is NULL on every row ever written** — the field exists
but nothing populates it.

**`gomes_alerts`** — read by `routes/trading.py`. A separate alert system from
`thesis_drift_alerts` (below) — see `API_REFERENCE.md`'s duplicate-endpoints table.

**`gomes_score_history`** — **deprecated. Do not write to it.** The model docstring
says so explicitly. Dropped by `rename_to_enterprise.sql`; `create_all` silently
recreates it empty on every startup, and nothing outside `models/` references it.

### Scoring, journal, calibration

**`conviction_score_history`** (`models/score_history.py`) — **the canonical score
journal**, opened 2026-08-23 (see `DOMAIN_MODEL.md`). Score layer: `conviction_score`,
`thesis_status`, `action_signal`, `price_at_analysis`, `analysis_source` (vocabulary:
`deep_dd`, `ai_analyst`, `ticker_analysis`, `synthesis`, `manual`, `seed`,
`unattributed`). **Decision layer**, all nullable and deliberately so — NULL means
"the app did not know", which is itself the measurement: `rr_score`,
`deserved_score`, `cylinders`, `green_line`/`red_line`, `band`, `market_alert`,
`source_key`.

**`score_outcomes`** — one score, one horizon.
`UniqueConstraint(history_id, horizon_days)`. `eval_status`
(`evaluated|pending|unable`) — CHECK enforces `unable` names a `unable_reason`.
`baseline_price`, `end_price`, `return_pct`, `benchmark_return_pct` (vs `^GSPC`),
`excess_return_pct`.

**`refused_buys`** — the negative record: what the Buy Guard refused, and why.
`failed_gate` is a `GomesGatekeeper.BuyGate` code, **never free text**.
`UniqueConstraint(ticker, refused_on, failed_gate)` — one row per ticker per day per
gate.

### SEC — `models/sec.py`, `models/sec_finding.py`

**`sec_coverage`** — `ticker` **UNIQUE**, `status`
(`COVERED|NOT_AN_SEC_FILER|LOOKUP_FAILED|FOREIGN_PRIVATE_ISSUER|NOT_A_TICKER`,
widened to VARCHAR(32) because `FOREIGN_PRIVATE_ISSUER` is 22 chars),
`last_checked_at` (NULL = never checked ≠ nothing found).

**`sec_filings`** — `analysis` nullable (NULL = not analysed — must not render as
"nothing found"). `UniqueConstraint(accession, document)`.

**`insider_transactions`** — `signal` (`BUY|SELL|NO_SIGNAL`, **derived from the SEC
transaction code, never from acquired/disposed**), `price_per_share` nullable (NULL
for grants and gifts). `UniqueConstraint(accession, insider_name, transaction_date,
code, shares)`.

**`sec_findings`** — `severity` (`CRITICAL|HIGH|MEDIUM`), `fact_cs`, `quote`.
`UniqueConstraint(accession, fact_cs)`. Only filings analysed **from 2026-08-23
forward** are structured here; older analyses stay as prose in `sec_filings.analysis`.

### Fundamentals and calendar

**`fundamental_snapshots`** — append-only TTM series. `ticker` is deliberately **the
provider's symbol, not canonicalised** — see [§5.10 below](#canonical-ticker).
Dedup is **by value**, not by day: a row means something actually changed.

**`earnings_dates`** — one row per **canonical** company. `confirmed` (default
False — True only for a single announced day), `window_end` (set only when the
provider gave a range, not a day), `source`
(`YAHOO|SEC_CADENCE|RELEASE_CADENCE`).

### External source sync

**`tracker_poll_state`** / **`breakout_poll_state`** — single-row state (`id=1`),
written on **every attempt**, so a down source is not retried faster than a live one.

**`tracker_line_changes`** / **`breakout_watchlist_changes`** — `notified_at` NULL
until the owner was actually told (see `OPERATIONS.md` for the send-confirms-notify
invariant these support).

**`breakout_watchlist`** — `price_at_read`/`implied_target` are overwritten every
poll; **`price_at_first_seen`/`target_at_first_seen` are written on insert only** —
this is what lets `breakout_scorecard.py` measure whether a call panned out from its
*original* reading, not a moving target.

**`analyst_roster`** — `name_key` **UNIQUE** (lower-cased, exact match only — no
fuzzy matching), `active` (deactivated, never deleted). See `INVARIANTS.md` §6.

**`analyze_ticker_state`** — `ticker` is the **primary key** (no surrogate id).
Exists because a throttle bug once let `/analyze-ticker` fire 143 times in 24 hours
on one ticker.

**`gomes_fit_cache`** — `ticker` is the primary key. Caches the output of the offline
research pipeline (see `OPERATIONS.md`).

### Own finds and analyst models

**`own_finds`** — `ticker` (canonical, indexed) vs. `display_ticker` (as the owner
typed it — this is what renders on screen). `status`
(`OTEVRENY|ODLOZENY|ZAHOZENY` — finds are closed, never deleted).

**`own_find_assessments`** — append-only, one reading per row. `dossier` (JSONB, the
whole fact set, so `fact_id` citations stay resolvable — see `INVARIANTS.md`'s note
on `GET /api/finds/{id}` never rebuilding the dossier). `price_is_stale` **defaults
to True**. `gate_passed` is nullable — NULL means the gate could not be evaluated,
distinct from `False` meaning it was evaluated and refused. Nine CHECK constraints,
including `deserved_has_its_cylinders` (a deserved score requires *confirmed*
cylinders, not proposed ones) and `attention_points_have_a_ceiling`.

**`analyst_revenue_models`** / **`analyst_revenue_model_lines`** — the owner's saved
copies of an analyst's bottom-up model, compared against SEC actuals. CHECK
`amount_or_unit_math` enforces a line has either a direct amount or both quantity and
price.

### Owner controls and ops

**`stock_owner_intent`** — `ticker` is the primary key. `intent`
(`EXIT_PENDING`/`TAX_LOSS_HOLD` today — free text, not an enum). Absence = no
override.

**`away_mode_state`** — `is_away`, `since`/`until` (a past `until` self-disables), and
the throttle bookkeeping (`last_push_at`, `last_push_urgency`, `last_digest_reason`).
**Not exported from `models/__init__.py`.**

### Trading / ML (mostly legacy)

`ohlcv_data` (composite PK `time, ticker`, documented as a TimescaleDB hypertable),
`active_watchlist`, `ml_predictions`, `trading_signals`, `model_performance`,
`data_sync_log` — all in `models/trading.py`, whose `models/__init__.py` import is
**commented out** ("to avoid circular imports"). They still register with
`Base.metadata` because routes import the module at app startup, but a script
importing only `app.models` will not create these tables.

### Tables with no ORM model

| Table | Lives in | Status |
|---|---|---|
| `yahoo_finance_cache` | `migrations/add_yahoo_cache.sql`, raw SQL in `yahoo_cache.py` | **Live.** One row per ticker, overwritten |
| `yahoo_refresh_log` | same migration | **Live** audit log |
| `yahoo_cache` | `000_clean_schema.sql` only | **Dead** — a differently-named duplicate concept, nothing reads it |
| `notifications` | `000_clean_schema.sql` only | **Dead** — the real notification channels are stateless (Telegram/SMTP) |

---

## Traps and column-level semantics

Read this section before writing any new query against these tables.

### `is_current` is written backwards

`ticker_mentions.is_current` defaults `TRUE`. The `update_current_mention()` trigger
only **demotes others** on insert — it keys on insertion order, not `mention_date`,
and never promotes the new row. Two writers disagree on what to set:

- `scripts/backfill_transcripts.py` writes real Gomes statements with verbatim quotes
  as **`is_current=False`**.
- `routes/gomes.py` writes bare, content-less ticker hits as **`is_current=True`**.

**Net effect: a reader filtering `WHERE is_current IS TRUE` gets empty rows instead
of the 355 real statements.** Correct readers filter on *content presence* instead,
and say so in comments: `services/find_dossier.py::_gomes_mentions`,
`services/breakout_lookup.py`, `services/lifecycle_intake.py::_analyst_stance`.
Regression test: `tests/test_ticker_mentions_is_current_fix.py`. **Never write a new
query with `is_current IS TRUE`.**

### Currency columns are inconsistent, and two are hardcoded rather than read

Column widths vary (`VARCHAR(3)` to `VARCHAR(10)`) across a dozen tables with no
single convention. Two call sites **hardcode `"USD"` instead of reading the actual
column**:

- `routes/portfolio.py::_band_at_trade()` — `"line_currency": "USD" if stock else
  None`, with a comment explaining the tracker quotes the US OTC listing even for a
  Canadian-exchange position. This value is then persisted into
  `investment_logs.line_currency` on every recorded trade.
- `routes/daily_actions.py` — Breakout rows get `line_currency="USD"`
  unconditionally, while the same file reads the *real* `stock.line_currency` for
  Gomes rows a few lines away.

`positions.currency_confirmed` exists because a ticker suffix can imply the wrong
currency (`IMP.V`/`KUYA.V` are genuinely held in EUR despite the Canadian-looking
symbol). `currency_conflict` (a computed Pydantic field) deliberately collapses
"matches" and "cannot be determined" into `None` — "we don't know" must never render
as "it's fine".

### `avg_cost` nullable — but `000_clean_schema.sql` reintroduces the old bug

The model correctly allows `NULL`. But `000_clean_schema.sql` still declares
`avg_cost FLOAT NOT NULL DEFAULT 0` — **rebuilding a database from that file alone
reintroduces the exact defect** the nullable column was created to fix (a missing
cost silently becoming a confident zero P/L). Never use `000_clean_schema.sql` as a
from-scratch baseline; see [Migrations](#migrations) below.

### Two price-line stores, never reconciled

- **`stocks.green_line`/`red_line`/`grey_line`** is what the decision engine
  actually reads (`daily_actions.py`, `tracker_sync.py`, `decision_board.py`,
  `find_dossier.py`). This is the operative one.
- **`price_lines`** is a separately versioned table with `conviction_score_at_green`,
  `source_reference`, `image_path` — written by `routes/gomes.py` and
  `gomes_intelligence.py`, read back only by the history endpoint. It also has **no
  `line_currency` column at all.**

Nothing keeps them in sync. Treat `stocks.*_line` as the source of truth; treat
`price_lines` as an audit trail the engine never consults.

### `is_latest` is per-ticker, but rows are conceptually per-(ticker, source)

Because `StockRepository._handle_existing_versions` demotes the single
`is_latest=True` row **for the ticker regardless of source**, inserting a Breakout
Investors analysis silently hides the Gomes row from any of the ~15 call sites that
filter `Stock.is_latest == True`. The newer, correct pattern — Postgres
`DISTINCT ON (ticker, source_key)` — is used in `daily_actions.py` and
`StockRepository.get_current_by_source()`. Prefer that pattern in new code.

### Confirm vs. propose — two write disciplines on `stock_lifecycle`

`cylinder_intake.confirm()` **versions**: retires the previous row
(`valid_until = now`), inserts a fresh one. `lifecycle_intake.confirm()` **mutates in
place**: updates the active row's `phase`, `phase_reached`, `rough_patch*` directly,
deliberately, because the stage is not given an expiry the way cylinders are. Know
which discipline you're extending before writing to this table.

The Buy Guard requires `cylinders_confirmed_at IS NOT NULL` **and** an unexpired
`cylinders_valid_until`. An expired confirmation is kept, never deleted — this is the
asymmetric staleness rule from `INVARIANTS.md` §1: stale data may make the app more
cautious, never less.

### Two semafor tables, both written

`market_status` (new, catalyst-aware, what the app actually reads) and
`market_alerts` (older, still read by `core/gomes_compliance.py` and
`gomes_intelligence.py`). `routes/analysis.py` writes **both** on every transcript
analysis, with a comment acknowledging it's updating "the legacy table" too. Singleton
access is also inconsistent: `market_watch.py` orders by `id`; `daily_actions.py` and
`cash_hedge.py` call a bare `.first()`, which is non-deterministic if more than one
row exists — and `000_clean_schema.sql`'s seed insert can create a duplicate on every
re-run (its `ON CONFLICT DO NOTHING` has no unique key to conflict on other than the
PK).

### Canonical ticker — which tables key on which form

`app/core/tickers.py` maps dual listings to a canonical (US OTC) symbol —
`DBOXF↔DBO.TO`, `GKPRF↔GSI.V`, `ITMSF↔IMP.V`, `KUYAF↔KUYA.V`, and others. **Aliasing
is for matching only** — the broker's own symbol always stays on screen.

| Uses the canonical form | Uses the provider's own symbol (deliberately not canonicalised) |
|---|---|
| `earnings_dates.ticker` (unique) | `fundamental_snapshots.ticker` — two listings can report different currencies and share counts; merging would fabricate a trend out of a units change |
| `own_finds.ticker` | `positions.ticker`, `own_finds.display_ticker` — the broker's symbol |
| `gomes_fit_cache.ticker` | `stocks.ticker`, `ticker_mentions.ticker`, `breakout_watchlist.symbol` — whatever the source used |

### Absence semantics — the pattern applied consistently across the schema

A missing input is stored as `NULL` and never substituted with a neutral value. This
is `INVARIANTS.md` §1 expressed as schema design:

- `realized_pl`, `rr_score` — NULL, never 0, when the underlying number is unknown.
- `deserved_score` requires *confirmed* cylinders (CHECK).
- `own_find_assessments.gate_passed` — NULL ("could not evaluate") ≠ `False`
  ("evaluated and refused").
- `score_outcomes.eval_status = 'unable'` must name a reason (CHECK).
- `sec_coverage.last_checked_at` NULL — never checked ≠ nothing found.
- `sec_filings.analysis` NULL — not analysed, must not render as "clean".
- `insider_transactions.price_per_share` NULL for grants/gifts — a gift's price is
  absent, not zero.
- `own_find_assessments.price_is_stale` defaults to **True**.
- `market_status.catalyst_severity_known` defaults to **False**.
- `attention_points` is meaningless without `attention_ceiling` (CHECK enforces
  both-or-neither).
- `investment_logs.trade_date` NULL → readers fall back to `created_at`, never to
  "today".

### A silent write to a column that does not exist

`routes/intake.py` does `stock.thesis = data.summary_cz`. `Stock` has **no `thesis`
column** — only `thesis_narrative`. SQLAlchemy accepts the attribute assignment on
the Python instance and discards it on flush; the Czech summary is silently lost on
every intake. One of the model's own comments names this defect class precisely:
*"the hardest kind of missing input: the data isn't missing, the awareness of it
is."*

---

## Migrations

**44 `.sql` files in `backend/migrations/`. No runner, no ledger, no
`schema_migrations` table, no ordering manifest.** Alembic is a listed dependency
and is entirely unused (no `alembic.ini`, no `versions/`).

| Mechanism | What it does |
|---|---|
| `python backend/apply_migration.py <name>` | Reads `migrations/<name>.sql`, strips lines containing `"""` (a hack for one file that opens with a Python docstring), executes the whole file as one statement. **Keeps no record of what ran.** |
| `apply_gomes_migration.py` | Hardcoded to one specific file; broken against its own target |
| `fix_constraint.py` | A schema change that exists **only in Python**, no `.sql` file — rebuilding from `migrations/` alone loses it |
| `Base.metadata.create_all(checkfirst=True)` | Runs on every startup; creates missing **tables**, never adds missing **columns** |
| `POST /api/dev/execute-sql` | Arbitrary SQL, gated on `DEBUG` (see `INVARIANTS.md` §5) |

### `000_clean_schema.sql` is **not** a usable from-scratch baseline

Despite the name, it creates only **9 of the ~47 tables** and predates the entire
August 2026 feature wave. It also actively reintroduces defects the later migrations
fixed: `avg_cost NOT NULL DEFAULT 0`, `monthly_contribution DEFAULT 0` (vs. the real
`20000.0`), the dead `yahoo_cache` and `notifications` tables instead of the live
ones, narrower VARCHAR widths, and a `market_status` seed insert with no real unique
key to conflict on. **Never use it to build a new database.** The only reliable path
today is `create_all()` (tables) followed by manually replaying every migration in
the order listed in this document — and even that has known breaks:

- `add_gomes_intelligence.sql` contains **invalid PostgreSQL** (a table CHECK with a
  `WHERE` clause) — `stock_lifecycle`'s "one active phase per ticker" rule almost
  certainly does not exist in any real database built from this file, only via
  `create_all`.
- `add_ticker_mentions.sql` cannot replay after `rename_to_enterprise.sql` — a view it
  creates selects a column that migration renames away.
- The `gomes_score` → `conviction_score` rename is **half-done**: several tables
  (`active_watchlist`, `investment_verdicts`, `price_lines`) carry both names side by
  side, and several views/functions (`gomes_investable_stocks`,
  `get_top_gomes_tickers()`) still reference the old name.
- `gomes_score_history` is created **twice** with two different schemas across two
  files, both `IF NOT EXISTS` — the winner depends on apply order, which nothing
  records.
- `thesis_drift_alerts` is created in **three** files with three different shapes.

**Before starting any schema work:** read the full migration list and the specific
traps above — they are the reason `sync_model_drift.sql` exists at all (twelve model
columns went missing from the live DB, and every ORM query against them aborted its
transaction until that file ran).

---

## Data files — `backend/app/data/`

Committed, derived artefacts — reviewable in a diff, so the app never depends on
anyone having run a research script at the right time.

| File | Written by | Read by | Purpose |
|---|---|---|---|
| `company_releases.json` | Curated by hand | `services/release_fundamentals.py` | The Canadian press-release cylinder layer (see `OPERATIONS.md` — Firecrawl). A reading without a verbatim `quote` or `basis_months` is discarded on load |
| `gomes_entry_profile.json` | `research/publish.py` | `services/gomes_fit.py` | Gomes' typical entry shape, from his 12-year track record (see `DOMAIN_MODEL.md`) |
| `gomes_registry.csv` | `research/publish.py` | **nothing in `app/`** | Dead — its stated purpose ("the per-company history line on the decision board") was never wired up |

---

## See also

- `ARCHITECTURE.md` — why the migration system is shaped this way
- `DOMAIN_MODEL.md` — what `stock_lifecycle`, `conviction_score_history` and the
  cylinder/phase confirmation actually mean
- `INVARIANTS.md` §1, §3 — the missing-data and propose-then-confirm rules this
  schema encodes
- `KNOWN_ISSUES.md` — every trap above, prioritised
