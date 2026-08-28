# Architecture

**Type:** Explanation · **Verified:** 2026-08-28

Read `INVARIANTS.md` first. This document explains how the pieces fit together and
why they are shaped the way they are; it does not repeat what must never break.

---

## What this is

Akcion is a single-user, single-tenant decision-support tool: a Python/FastAPI
backend, a React/TypeScript frontend, and a Postgres (Neon) database, run on a
Windows machine behind no authentication. It is not a SaaS product and should never
be treated as one — see `INVARIANTS.md` §5 for what that implies about exposure.

```
┌──────────────────────────────────────────────────────────────────┐
│  React 19 SPA (Vite, port 5173 dev)                               │
│  No router. One tab-state variable. Seven screens, one shell.     │
└───────────────────────────────┬────────────────────────────────────┘
                                 │ axios, /api/*, no auth
┌───────────────────────────────▼────────────────────────────────────┐
│  FastAPI (uvicorn, port 8002)                                      │
│  21 routers · no global exception handler · no middleware but CORS │
│  ┌────────────────────────────────────────────────────────────┐   │
│  │ asyncio background loop (alert_scheduler) — away-mode push  │   │
│  └────────────────────────────────────────────────────────────┘   │
└───────────────┬──────────────────────────────┬─────────────────────┘
                │ SQLAlchemy                    │ httpx / requests / yfinance
┌───────────────▼──────────────────┐  ┌─────────▼─────────────────────┐
│  Postgres (Neon)                 │  │  External sources               │
│  44 hand-written SQL migrations, │  │  SEC EDGAR, Yahoo, Finnhub,      │
│  no ORM-driven schema changes    │  │  Firecrawl, TranscriptAPI,       │
└───────────────────────────────────┘  │  riskrewardcharts.com,          │
                                        │  breakoutinvestors.com, CNB,    │
                                        │  Trading 212, Anthropic, Gemini │
                                        └──────────────────────────────────┘
        Windows Task Scheduler (external, unversioned)
        4 daily .cmd jobs — tracker/breakout polls, score eval, price history
```

Full detail per box: `API_REFERENCE.md` (backend HTTP surface), `FRONTEND.md` (the
SPA), `DATA_MODEL.md` (the schema), `OPERATIONS.md` (external sources and scheduled
jobs), `DOMAIN_MODEL.md` (what any of this is actually *for*).

---

## The shape of a decision, end to end

This is the path that matters most in the whole codebase — everything else supports
it. Follow one ticker from "an analyst said something" to "the owner sees an
instruction."

1. **Ingestion.** A transcript, a WhatsApp paste, a company press release (via
   Firecrawl), or an SEC filing arrives through one of several intake paths (`gomes.py`,
   `intake.py`, `whatsapp/paste`, `sec/sync`). Each writes *evidence* — a transcript
   row, a ticker mention, a filing, a finding — never a verdict.
2. **Proposal.** A rubric reads that evidence and *proposes* two specific inputs the
   canon needs: cylinders (0–10, operating quality) and lifecycle phase (Great Find /
   Wait Time / Gold Mine). `cylinder_intake.propose()` and `lifecycle_intake.propose()`
   — read-only, never persisted as a decision.
3. **Confirmation.** Only a human action calls `.confirm()`, which writes to
   `stock_lifecycle`, append-only (the previous row is retired with `valid_until`, not
   deleted). This is the one place these two hard-to-automate inputs enter the system.
   See `INVARIANTS.md` §3.
4. **The Buy Guard.** `GomesGatekeeper.evaluate_buy_guard()` reads the confirmed
   inputs plus the market alert, the R/R band (from `riskrewardcharts.com` via
   `tracker_sync`) and the earnings calendar, and evaluates five gates in strict order:
   market alert → cylinders known → not Wait Time → band computable → score > deserved.
   First failure ends it; failure downgrades to HOLD, never to SELL.
5. **The decision surface.** `services/daily_actions.py` assembles the guard's output
   plus concentration, pacing, emotional-brake and refused-buy checks into at most
   three ranked actions — "what do I do today" — served by `GET /api/trading/daily-actions`
   and `GET /api/trading/board`, and rendered verbatim by the frontend's `DecisionBoard`
   and `DailyActionWidget` with no re-derivation.
6. **The record.** Whatever the owner actually does (`POST .../trade`) is written to
   an immutable ledger, and the score at that moment is journalled
   (`score_journal.record_score`) so `score_calibration` can eventually ask whether the
   method's confidence tracked real outcomes.

The single biggest architectural risk in the codebase is that step 5's answer has
been re-derived, differently, in several other places — see
[Duplicate engines](#duplicate-engines-the-central-risk) below.

---

## Backend layout

```
backend/app/
  main.py          FastAPI app, router registration, startup/shutdown, scheduler kickoff
  config/          pydantic-settings — the one place env vars are typed
  routes/          24 modules — HTTP boundary only, ideally thin (not always — see API_REFERENCE.md)
  schemas/         Pydantic request/response models (the package; app/schemas.py is a dead duplicate)
  services/        82 modules — where the domain logic should live (and mostly does)
  trading/         10 modules — the older Gomes engine (gatekeeper, signals, Kelly sizing)
  core/            constants, tickers, Czech formatting, prompts, compliance rules
  models/          23 modules — SQLAlchemy ORM
  database/        connection + repositories
```

**`services/` vs `trading/` is a historical split, not a clean layered boundary.**
`trading/gomes_logic.py` holds `GomesGatekeeper` (the Buy Guard) and
`PositionSizingEngine`; `core/gomes_logic.py` is a **separate, smaller module with an
overlapping name** — check which one a symbol actually comes from before assuming.
Newer domain logic (cylinders, lifecycle, margin of safety, emotional brakes, the
market gauge) lives in `services/` and is generally better factored: one
responsibility per module, explicit "what happens when this input is missing"
handling, and a matching test file.

**Routes that carry real business logic instead of delegating** (see
`API_REFERENCE.md` for specifics): `intelligence_gomes.analyze_ticker_from_transcript`
(~290 lines), the price-zone classification duplicated across `stocks.py`,
`portfolio.py` and `services/ladder_view.py`, and the market-status-detection block
triplicated in `analysis.py`. `daily_actions.py`, `market_gauge.py`, `cash_hedge.py`
and `revenue_models.py` are the counter-examples worth imitating: thin routes, all
logic in a service, typed responses.

---

## Duplicate engines: the central risk

The Buy Guard is the one authoritative answer to "should this be bought." Several
other code paths answer overlapping questions with **different logic**, and nothing
prevents them from disagreeing:

| Question | Authoritative path | Competing path(s) |
|---|---|---|
| Should I buy/sell this today? | `daily_actions.py` → `GET /api/trading/board` | `getActionCommand()` in `InvestmentTerminal.tsx` (frontend re-implementation of the same four gates); `GET /api/intelligence/verdict/{ticker}`; `GET /api/gomes/ladder` |
| What's the market alert? | `PUT /api/portfolio/market-status` (catalyst-guarded) | `POST /api/intelligence/market-alert` (unguarded); a side effect of `POST /api/analyze/*` |
| What lifecycle phase is this? | `GET/POST /api/gomes/lifecycle/{ticker}` (rubric + human confirm + ratchet) | `GET/POST /api/intelligence/lifecycle*` (AI classification, **bypasses the ratchet**) |
| What's the max position size? | Backend `max_allocation_cap` field | `TARGET_WEIGHTS` + `calculateMaxAllocationCap()` hardcoded in the frontend as a fallback |

This pattern — one canonical engine plus one or more shadow copies that can silently
diverge — is the architectural expression of the `INVARIANTS.md` §1 defect class.
When extending any of these questions, extend the authoritative path and delete the
shadow, rather than adding a third.

---

## Frontend architecture in one paragraph

No router, no global state library. One `useState` tab switch in a 4352-line
`InvestmentTerminal.tsx` that also holds the portfolio screen, five payment modals and
the CSV/position/analysis modals. State is per-component `useState` plus one
substantial `useMemo` (`familyData`) that does the entire portfolio roll-up. The
`DecisionBoard` screen is the model to copy: it renders backend verdicts verbatim with
no client-side re-derivation. Full detail, including every place that model is *not*
followed, is in `FRONTEND.md`.

---

## Data flow for a price

Prices have three independent paths into the app, and they disagree on freshness
semantics on purpose:

1. **Yahoo cache** (`yahoo_cache.py`) — 15-minute TTL during market hours, serves
   stale-flagged data otherwise. The default path for the portfolio table.
2. **OHLCV history** (`price_history.py`) — daily bars for charts, refreshed once a
   day by the "historie cen" scheduled job, stored under whichever symbol Yahoo
   actually answered for (relevant for the four Canadian cross-listings).
3. **The R/R tracker** (`gomes_tracker.py` via `tracker_sync`) — not a price at all,
   but the green/red lines the Buy Guard's band computation depends on. Polled once
   every 12 hours, independent of market hours.

None of these three write to each other. A stale price never silently becomes a fresh
one (`_increment_error_count` deliberately does not touch `last_updated`); see
`OPERATIONS.md` for the specific historical bugs this guards against.

---

## Why Postgres migrations are hand-written

`Base.metadata.create_all(checkfirst=True)` runs on every startup and creates missing
**tables only** — it never alters an existing one. Real schema changes are 44
hand-written `.sql` files in `backend/migrations/`, applied manually with
`python apply_migration.py <name>`. Alembic is a listed dependency and is not used.

The consequence, seen more than once: a model class and the live database can drift
(`PriceLinesModel` vs. its actual columns is the worst recorded case — see
`DATA_MODEL.md`), and the failure mode is `UndefinedColumn` at request time, not at
startup. There is no automated check that every model's columns exist in the database
it's pointed at. This is the single most valuable piece of tooling this repo does not
yet have — see `KNOWN_ISSUES.md`.

---

## Why the research pipeline is offline and one-directional

`backend/research/` (see `OPERATIONS.md`) computes Gomes' typical entry profile from
his 12-year track record and publishes exactly one JSON file the live app reads. It
never runs at request time and the live app never imports it directly — enforced by
an AST-walking test. The reason is freshness honesty: `research/out/` depends on
yfinance's adjusted-price history, which yfinance silently rewrites on every split and
dividend, so a cached copy would drift from its source without anyone noticing. This
same "don't cache what silently rewrites itself" reasoning shows up again in
`score_outcomes.py`.

---

## Deliberately absent

Reading what is *not* here matters as much as what is.

- **No authentication, no multi-tenancy.** Single owner, single machine.
- **No broker execution path.** `POST /api/trading/order` validates and stops —
  `# TODO: Integrate with actual broker API`. The app advises; the owner acts.
- **No ML/backtesting engine.** Removed; `schemas/trading.py` and several dead
  imports are its remains. `MASTER_SIGNAL.md`'s "6-component aggregation" describes
  this removed system, not the current one.
- **No client-side router.** A deliberate simplicity choice for a single-owner app,
  though it means no deep links and no browser back-button navigation between tabs.
- **No runtime response validation on the frontend.** Responses are cast, not parsed;
  a backend field rename fails silently rather than loudly. See `FRONTEND.md`.

---

## See also

- `INVARIANTS.md` — the rules this architecture exists to enforce
- `DOMAIN_MODEL.md` — what the Buy Guard's five gates actually mean
- `API_REFERENCE.md`, `FRONTEND.md`, `DATA_MODEL.md`, `OPERATIONS.md` — the four
  detailed references this document summarizes
- `KNOWN_ISSUES.md` — prioritised defects, including the duplicate-engine instances
  above
