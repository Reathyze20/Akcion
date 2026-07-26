# Akcion — App Specification & Context Pack

**Purpose of this document:** a single, self-contained brief you can paste into any AI conversation to discuss *what to build or do next*. An AI reading only this file (no repo access) has enough context to give useful, grounded advice. Verified against the codebase on **2026-07-26**, branch `feature/gomes-fidelity`.

---

## 1. Mission, user, constraints (read this first)

Akcion is a **fiduciary investment terminal for one family's real money**, run by a solo developer-investor. It is not a hobby project and not a product for other users.

- **Goal:** ~20% yearly return. The goal is high and the app must **never promise it**. The app's actual job: zero avoidable errors, rule enforcement, minimal time cost. That gives a *shot* at the goal, not a guarantee.
- **User constraints:** chronic health condition with variable energy; periods of weeks without checking the app are normal. Time budget per decision: **≤2 minutes, ≤3 actions, one screen**. The app decides; the user confirms.
- **Priority rubric for any new work:** rank by `(risk to capital reduced) × (user effort reduced)`, not by feature appeal. Correctness IS the feature: a broken save, a fake UI value, or wrong math costs real money and is P0, always.
- **"Nic. Drž."** ("Nothing. Hold.") is a first-class product state, the correct answer most days.
- **Must survive absence:** stale data must be labeled stale, never silently filled with fake numbers. Default under uncertainty: protect capital.

History note: the app went dormant ~3.5 months (2026-04 to 2026-07). A trust audit on return found 5 trust-breaking bugs (all fixed, see §4). The lesson that now drives priorities: "looks like it works" ≠ "can be trusted with money."

## 2. The methodology the app enforces

Akcion encodes the investing method of **Mark Gomes** ("Money Mark", equity analyst). Canonical source: his article *"Get Rich On Stocks"*, distilled to `docs/GOMES_METHODOLOGY_CANON.md` (in Czech). When code and canon disagree, canon wins. Core rules:

**a) Market Alert (traffic light), portfolio-level timing.** Derived (per canon) from a 40-year S&P valuation chart:
- 🟢 GREEN: own stocks without fear; position size via R/R charts; 0% hedge.
- 🟡 YELLOW: sell all speculative + "Wait Time" stocks; raise cash (don't redeploy profits); 20-30% in RWM hedge.
- 🟠 ORANGE: between Yellow and Red; all cash in RWM.
- 🔴 RED (twice-in-a-lifetime): sell almost everything, bet against the market.
- Instruments: **BOXX** (cash parking), **RWM** (inverse Russell 2000 hedge).

**b) Stock lifecycle (3 stages):** Great Find (unknown, early, risky, OK in Green) → Wait Time (hype died, **do not be invested**) → Gold Mine (momentum + profits, safe to hold long).

**c) Risk/Reward score, the core mechanic. LOGARITHMIC, not linear:**
```
R/R score       = 10 × log(High/price) / log(High/Low)    # 10 at Low (green line, buy), 0 at High (red line, sell)
deserved_score  = 10 − cylinders                          # cylinders 0-10 = company operational health
BUY  when score > deserved_score   (cheap relative to quality)
SELL when score < deserved_score   (expensive relative to quality)
```
Math verified against the live fan tracker riskrewardcharts.com (e.g. CXDO low 3.25 / high 15.50 / price 6.62 → score 5.45). Refuse BUY when cylinders unknown (avoids Wait-Time value traps).

**d) Sell rules:** take profits at R/R highs (that's where cash for the next downturn comes from); **Doubling rule** (doubled → sell half, "house money"); **3-point rule**: a 3-point move on the 10-point log scale, exact trigger `price × (High/Low)^(3/(10−topScore))`.

**e) Position sizing tiers:** Primary/Core (proven Gold Mine) max 10%, Secondary smaller, Tertiary/speculative 1-2%. Yellow blocks Tertiary entirely. App-level cap: 15% per position.

**f) Prohibitions:** no options; never buy all picks at once; buy only when market is Green AND price is attractive on the R/R chart; never deploy cash just because it's there (excess goes to BOXX).

**Second source:** the user also follows **Breakout Investors** (a trader Discord community). It has no written canon; its "signal" is community consensus/disagreement. Since commit `4d87346` (2026-07-26) the app preserves both sources per ticker side by side (`source_key` GOMES / BREAKOUT_INVESTORS / OTHER) with agreement states AGREE / MIXED / CONFLICT / SINGLE, instead of one source overwriting the other.

## 3. What the app is today

**Stack:** React 19 + TypeScript + Vite + Tailwind (frontend, SPA) · FastAPI + Python 3.12 + SQLAlchemy 2.0 (backend) · PostgreSQL on Neon.tech · Google Gemini for AI analysis · Yahoo Finance (cached) + Massive + Finnhub for market data · email (SMTP) notifications.

**Primary workflow:** paste a YouTube URL / transcript / text from Gomes or Breakout Investors → Gemini extracts tickers, thesis, price lines (green/red), cylinders, catalysts → app stores a versioned analysis per ticker per source → rule engine (not the AI) produces verdicts → user sees portfolio/watchlist cards, detail modal with Trading Deck, signals, and notifications.

**Frontend:** single-page terminal, 4 tabs: **Portfolio**, **Watchlist**, **Freedom** (goal tracking), **Splácení** (family debt payments). 27 components; the shell `InvestmentTerminal.tsx` is a 5,660-line monolith (known code-health issue). Dark Bloomberg-terminal aesthetic.

**Backend:** 14 route modules (portfolio, stocks, analysis, gap_analysis, trading, intelligence, gomes, intelligence_gomes, master_signal, notifications, investment, currency, yahoo_finance, dev_utils). Dev SQL endpoint is gated behind `settings.debug`. 17 SQL migrations (applied manually, no migration runner). 7 pytest files in `backend/tests/`.

**Rule engines (important nuance, two exist):**
- `backend/app/trading/gomes_logic.py` (1,146 lines): THE canonical engine. MarketAlertSystem (alert → allocation/blocked tiers), StockLifecycleClassifier, RiskRewardCalculator (log score, deserved score, 3-point triggers, doubling rule), PositionSizingEngine, GomesGatekeeper (final verdict synthesis).
- `backend/app/core/gomes_logic.py` (399 lines): an older conviction-score-driven `GomesLogicEngine` still used by `services/gomes_ai_analyst.py` and one route. Duplication risk: two "Gomes logic" sources of truth.
- `backend/app/trading/master_signal.py`: Master Signal v2.1 — fundamentals-only score: Thesis Tracker 60%, Valuation & Cash 40%, Weinstein 30WMA at **0% weight** (informational `technical_overlay_warning` badge only; it no longer blocks or penalizes, resolving gap #3).
- `backend/app/services/daily_actions.py` + `routes/daily_actions.py`: Daily Action engine (Path 1) — `GET /api/trading/daily-actions` returns max 3 ranked actions with exact CZK amounts or `HOLD_HOLD_HOLD` ("Nic. Drž."); de-risk > doubling-rule trims > R/R trims > guarded BUYs; missing/stale data surfaces as Czech warnings, never numbers.

**Data model (main tables):** `stocks` (versioned AI analyses per ticker+source: conviction score, price lines, cylinders, lifecycle, catalysts, `source_key`, `is_latest`), `portfolios` + `positions` (multi-portfolio, multi-broker: Degiro / Trading212 / XTB CSV import), `analyzed_stocks`, score history, trading signals/zones, ticker mentions, thesis monitor, yahoo cache, investment logs.

## 4. Verified current state (what actually works)

Fixed and committed on this branch (verified 2026-07-26):

1. **Trust triage (commit `c21462b`):** Trim/Sell persists to DB (was a `console.log` no-op); real test suite un-gitignored and in CI; CI repaired (was compiling deleted files since ~Feb); dev SQL endpoint gated; fake hardcoded UI values removed (isLargeCap, currentAge, deposits bar).
2. **R/R scoring corrected (commit `dc145a0`):** logarithmic formula + cylinders wired in (`BUY when score > 10 − cylinders`), 3-point price triggers, fails safe to None on invalid input. 25 test assertions, tracker-verified fixtures.
3. **Dual-source attribution (commit `4d87346`):** Gomes and Breakout Investors coexist per ticker; version retention scoped per source; `GET /api/stocks/{ticker}/sources` comparison endpoint. 20 test assertions. Migration `add_source_key.sql` **applied to Neon 2026-07-26** (22 rows backfilled: 9 GOMES / 13 OTHER, 0 NULL, index created).
4. **Infra verified alive (2026-07-26):** Neon awake (PostgreSQL 17), Gemini + Massive + Finnhub keys valid; Yahoo repaired by upgrading yfinance 0.2.49 → 0.2.66 (old version broke on Yahoo API change).
5. **Buy Guard + dual-source matrix (this branch):** `GomesGatekeeper.evaluate_buy_guard()` hard-blocks BUY unless GREEN + known nonzero cylinders + not Wait-Time + R/R score > deserved; `evaluate_dual_source_buy()` sizes by agreement (AGREE≤15% / SINGLE·MIXED≤7% / CONFLICT≤5%+review; Breakout can never override a Gomes block). `tests/test_buy_guard.py`: 29 assertions.
6. **Master Signal reweighted (this branch):** 60/40/0, Weinstein → `technical_overlay_warning` badge; `tests/test_master_signal.py` rewritten for V2 (was failing at collection against the deleted V1 aggregator): 26 assertions.
7. **Daily Action engine + UI (this branch):** pure engine + endpoint + `DailyActionWidget.tsx` mounted at top of Portfolio tab; verified live against real DB (returned GREEN, real cash, `HOLD_HOLD_HOLD`, 6 stale-price warnings) and visually in browser. `tests/test_daily_actions_endpoint.py`: 26 assertions.
8. **Frontend CI gate repaired (this branch):** `npm run build` (`tsc -b && vite build`) had 33 pre-existing strict-TS errors (half-finished gomes→conviction rename, duplicate identifiers, dead type mismatches) — now **0 errors**.
9. **Buy Guard enforced in the verdict path (this branch):** `GomesGatekeeper.evaluate()` Rule 7 downgrades any STRONG_BUY/BUY/ACCUMULATE to HOLD when the guard fails (non-GREEN, unknown cylinders, Wait-Time, or score ≤ deserved) — no buy-side verdict can bypass canon §6. +5 tests.
10. **Price refresh repaired (this branch):** `yahoo_cache.py` read `fast_info` with snake_case keys but yfinance FastInfo uses camelCase — every "successful" fetch stored `None` prices silently. Fixed; forced refresh updated 8/10 positions (KUYA.V + IMP.V fail on Yahoo data gaps for TSX-V; they now carry an explicit "price age unknown" warning).
11. **Broker-import honesty (this branch):** Degiro portfolio CSVs carry no purchase price; the old import silently stored the closing price as `avg_cost` (fabricated cost basis — zero P/L, disarmed doubling rule). Now: `positions.avg_cost` is nullable (migration applied), Degiro imports store the closing price as `current_price` and cost as NULL, the app renders "⚠️ doplň nákupní cenu" everywhere (row, detail, upload toast, daily-action warnings) until the user fills it via Edit, re-imports NEVER overwrite a filled-in cost, and the metadata-skip bug that ate the first position of headerless Degiro files is fixed. T212/XTB CSVs carry genuine costs and are unchanged. Also fixed: the manual Add Position endpoint crashed on computed-property assignment.
12. Test suites: **165 passed**; the 28 failures in old `test_api_*`/`test_yahoo_cache`/`test_phase1_extraction` files are pre-existing (identical set on the base commit) and test obsolete API shapes.

**Unverified / at risk (do not assume these work):**
- **SMSI position record is pre-split:** SMSI did a 1-for-5 reverse split 2026-06-05 (Yahoo splits data). DB holds 611 shares @ $0.60; reality is ~122 shares @ ~$3.00 (cost basis identical). Until reconciled against the broker, the doubling rule fires a FALSE "+317% → TRIM 305.5 shares" action. **User decision needed** — correct via position edit / CSV re-import. No corporate-action handling exists in general (new known gap).
- KUYA.V and IMP.V have no fresh price (Yahoo TSX-V data gaps) and no price timestamp; daily-actions flags them "STÁŘÍ CENY NEZNÁMÉ".
- Uncommitted working-tree files: `backend/migrations/000_clean_schema.sql` (clean-start schema), `backend/test_endpoint.py`, `backend/test_gomes_endpoints.py` (manual localhost scripts, not pytest).
- README stats/versions are stale (says React 18; actual React 19).
- 28 legacy pytest failures (`test_api_*`, `test_yahoo_cache`, `test_phase1_extraction`) test obsolete API shapes — not repaired, not regressions.

## 5. Known gaps (methodology fidelity + product)

From the 14-item gap map in `GOMES_METHODOLOGY_CANON.md` §9, updated to today:

| # | Gap | Status 2026-07-26 |
|---|-----|-------------------|
| 0 | R/R score was linear, must be logarithmic | ✅ **FIXED** (`dc145a0`) |
| 1 | Cylinders ignored by scoring | ✅ **FIXED** (`dc145a0`) |
| 2 | Market Alert is a manually set field, not gauged from the 40y S&P chart | ❌ OPEN |
| 3 | Weinstein 30WMA pillar was 15% of Master Signal (technical analysis vs canon) | ✅ **FIXED** — reweighted 60/40/0; 30WMA is now an informational `technical_overlay_warning` badge, never scores or blocks |
| 4 | Yellow/Orange/Red allocation percentages are interpretation, not canon | 🟡 acceptable drift |
| 6 | BOXX/RWM not modeled as real instruments, only abstract cash % | ❌ OPEN (minor) |
| 9 | Yellow blocks Tertiary tier but did not flag held Wait-Time positions for sale | ✅ **FIXED** — Daily Action engine emits SELL_WAIT_TIME / SELL for Wait-Time + blocked tiers on Yellow/Orange, LIQUIDATE_HEAVY on Red |
| 13 | Doubling rule: in docs, implementation in signal flow unverified | ✅ **FIXED** — wired into Daily Action engine (doubled → TRIM half), tested |
| 14 | No buy guard: nothing warns when buying a pick outside Green or above deserved price | ✅ **FIXED** — `evaluate_buy_guard()` hard-blocks (GREEN + cylinders + not Wait-Time + score > deserved); enforced in the Daily Action BUY scan |

(Gaps 5, 7, 8, 10, 11 are faithful; 12 resolved: 3-point rule now has exact math.)

**Product gaps vs the target UX (§6):** no dedicated one-confirm de-risk flow on alert change (the sell list itself now exists in Daily Actions), no monthly-deposit deployment path, no Away mode, notifications are email-only (no Telegram/push).

**Code health gaps:** 5,660-line frontend monolith; two parallel Gomes engines; migrations applied by hand with no tracking of what's applied where.

## 6. Target UX: the 7 user paths (from `docs/EFFICIENT_INVESTING_PLAYBOOK.md`)

Each path has a hard time budget. Build status today:

| Path | Time budget | Status |
|------|-------------|--------|
| 1. "What should I do today?" — alert semafor + ranked action list (max 3 items, exact amounts) or "Nic. Drž." | ≤2 min | ✅ **built** — `GET /api/trading/daily-actions` + `DailyActionWidget` at top of Portfolio tab, verified live + visually |
| 2. Process a new pick/video → verdict BUY now / WAIT / Watchlist | ≤5 min | ✅ gating done in the canonical engine (`evaluate()` Rule 7 — no buy-side verdict bypasses the guard); 🟡 legacy `core/gomes_logic.py` engine still ungated |
| 3. Record a trade the app told me to make | ≤1 min | ✅ works (was broken, fixed + tested) |
| 4. Alert flipped Yellow/Orange/Red → one-confirm de-risk sell list | ≤3 min | 🟡 partial (Daily Actions generates the ranked sell list on non-green alerts; a dedicated one-confirm batch flow is not built) |
| 5. Monthly deposit → where to put it, or "hold in BOXX" | ≤3 min | 🟡 partial (gap analysis exists; no deposit-flow UX) |
| 6. Weekly/monthly portfolio health audit (exceptions only) | ≤5 min | 🟡 partial (widgets exist: drift alerts, family audit) |
| 7. Away mode: tighter stops, raise-cash default, single most-urgent push alert | set once | ❌ not built |

Acceptance style used across paths: the app never shows a fake number (missing data renders as "⚠️ missing data", not a value), never says BUY when market ≠ Green or price above deserved, and every failure is shown as an error, never a silent success.

## 7. Prioritized backlog (as of 2026-07-26)

~~Shipped 2026-07-26:~~ migration + infra check, Path 1 Daily Action screen, gap #14 buy guard (incl. verdict-path enforcement), gap #3 Weinstein reweight, de-risk sell list generation, price-refresh repair. Remaining:

1. **Reconcile positions against broker statements** (user decision): SMSI needs its 1:5 reverse-split correction (a false TRIM fires until then), and every Degiro-imported position's `avg_cost` predating 2026-07-26 is suspect — the old import fabricated it from the closing price. Fill real purchase costs via Edit; the new import flow will never overwrite them.
1b. **Trading212 official API sync** (next transport step): free read-only key, returns positions incl. genuine average price + cash; wire into the reconciliation flow for automatic, split-proof position sync.
2. **Path 4 completion: one-confirm batch de-risk flow** (the sell list exists in Daily Actions; add the single-confirmation execution UX).
3. **Gap #2: Market-alert gauge**, assisted computation from long-term S&P valuation instead of a purely manual field.
4. **Path 7: Away mode** + single-alert push channel (Telegram or email digest).
5. Code health when it blocks the above: split `InvestmentTerminal.tsx` (incl. deleting the dead exported `StockDetailModal`), retire or merge `core/gomes_logic.py` into the trading engine (it still bypasses the Buy Guard), repair or delete the 28 legacy failing tests.

## 8. How to evaluate any proposed "next thing" (rubric for AI discussions)

When discussing what to do next, test every idea against these, in order:

1. Does it reduce risk of losing money to an app error? (correctness > features)
2. Does it cut the user's time/energy per decision toward the 2-minute budget?
3. Does it enforce a canon rule the user could otherwise break under stress? ("selective signal following destroys the statistics")
4. Does it keep working when the user disappears for 3 weeks?
5. Is it honest? (no fake data, no implied return promises, stale = labeled stale)

Reject anything that: adds daily monitoring burden, adds a number the app can't back with real data, optimizes returns by adding user decisions, or grows the untested surface faster than the tested one.

## 9. Open strategic questions (good AI discussion topics)

1. What does a trustworthy **market-alert gauge** look like when the canon source is a chart-reading habit, not a formula? (40y S&P valuation vs trend lines)
2. How should **Breakout Investors signals** influence decisions, given no written rules? (e.g., use only as confirmation/conflict flag on Gomes picks vs independent watchlist source)
3. Weinstein pillar: is a 15% technical-trend guard a useful safety net worth keeping against canon, or drift to cut?
4. What is the minimal **Away mode** that actually protects capital: alert-based auto-suggestions queued for one-tap approval, hard stop-loss orders at the broker, or pure notification escalation?
5. Is ~20%/yr even the right dashboard framing, or should the Freedom tab track "rules followed / errors avoided" as the honest leading metric?
6. When to trust automation with real orders (broker API) vs keeping the app decision-support only? (today: decision-support only, trades executed manually at broker)

## 10. Reference: repo facts

- Repo: `github.com/Reathyze20/Akcion`, main branch `main`, work happens on feature branches. CI: `.github/workflows/ci.yml` (pytest + compile checks).
- Run: backend `cd backend && python start.py` (localhost:8000, docs at /docs); frontend `cd frontend && npm run dev` (localhost:5173).
- Key files: `backend/app/trading/gomes_logic.py` (canonical rule engine), `backend/app/trading/master_signal.py` (3-pillar signal), `backend/app/core/sources.py` (dual-source), `backend/app/core/analysis.py` + `prompts*.py` (Gemini), `backend/app/database/repositories.py`, `frontend/src/components/InvestmentTerminal.tsx` (SPA shell).
- Docs in repo: `GOMES_METHODOLOGY_CANON.md` (canon + full gap map, Czech), `EFFICIENT_INVESTING_PLAYBOOK.md` (7 paths + ~40 Given/When/Then test cases, Czech), `AKCION_PRODUCT_OVERVIEW.md` (v2.0, partly stale), plus per-feature docs (MASTER_SIGNAL, NOTIFICATIONS, YAHOO_CACHE, etc.).
- Env (backend/.env): `DATABASE_URL`, `GEMINI_API_KEY`, `MASSIVE_API_KEY`, `FINNHUB_API_KEY`, `CORS_ORIGINS`, `DEBUG`, SMTP_* + `EMAIL_RECIPIENT`.
- Language note: UI and docs are Czech-first; code and commits mix Czech/English.

---

*Maintenance: update §4-§7 whenever a backlog item ships; update §2 only when the canon doc changes. This file intentionally duplicates key canon facts so it can travel alone.*
