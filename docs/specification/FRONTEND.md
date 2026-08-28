# Frontend Reference

**Type:** Reference · **Source:** `frontend/` · **Verified:** 2026-08-28

---

## Stack

| Concern | Value |
|---|---|
| Framework | React **19.2**, StrictMode |
| Language | TypeScript ~5.9.3, `strict: true`, `noUnusedLocals`, `noUnusedParameters`, `erasableSyntaxOnly`, `verbatimModuleSyntax` |
| Build | Vite 7.2.5 **via `npm:rolldown-vite`** (an `overrides` entry), `@vitejs/plugin-react` |
| Styling | Tailwind 3.4 + PostCSS + Autoprefixer. **Tailwind holds no literal colours** — every value is a CSS variable |
| HTTP | axios 1.13, one singleton client |
| Charts | recharts 3.6 (used in exactly 2 files) |
| Icons | lucide-react (46 files) |
| Fonts | `@fontsource-variable/archivo`, `@fontsource/ibm-plex-sans`, `@fontsource/ibm-plex-mono` — **self-hosted**, deliberately: works offline and covers Czech diacritics |
| Toasts | custom `ToastContext`. `sonner` is a dependency but imported only by a dead file |
| Tests | vitest 4.1.11. **No jsdom, no testing-library** |
| Unused deps | `clsx` (imported nowhere), `sonner` (dead file only) |

### Scripts

| Command | Does | Status 2026-08-28 |
|---|---|---|
| `npm run dev` | Vite on 5173, proxies `/api` → `http://127.0.0.1:8002` | — |
| `npm run build` | `tsc -b && vite build` — **also the typecheck** | passes |
| `npm test` | `vitest run` | **124 tests, 5 files, all pass (~0.3 s)** |
| `npm run lint` | `eslint .` | **FAILS: 23 errors, 2 warnings** |

### Environment

- `.env.example` → `VITE_API_URL=http://localhost:8000`
- `.env` (live) → `VITE_API_URL=http://localhost:8002`, `VITE_APP_NAME=AKCION`
- `src/vite-env.d.ts` declares **only** `VITE_API_URL`. `VITE_APP_NAME` is declared nowhere and used nowhere.
- Code fallback: `import.meta.env.VITE_API_URL || 'http://localhost:8002'`
  ([client.ts:62](../../frontend/src/api/client.ts#L62)).

> **Three sources disagree on the port:** the code fallback says 8002,
> `.env.example` says 8000, `frontend/README.md` says 8000. Only `.env` is right.
> `frontend/README.md` is stale in general — it claims React 18 and still contains
> Vite template boilerplate.

`index.html` carries an inline pre-paint script that reads
`localStorage['akcion.theme']` and stamps `data-theme` on `<html>` before React
mounts, to prevent a flash. Its keys must stay in sync with `src/design/theme.ts`.

---

## Directory map

```
src/
  main.tsx                    createRoot + StrictMode
  App.tsx                     ToastProvider > InvestmentTerminal + ToastContainer
  index.css                   fonts, tokens, @tailwind, @layer components
  App.css                     Vite starter leftovers — IMPORTED NOWHERE (dead)
  api/client.ts               1776 lines — the whole API surface + ~40 response types
  types/index.ts              858 lines — domain types mirroring backend Pydantic
  context/
    AppContext.tsx            DEAD (AppProvider never mounted)
    ToastContext.tsx          live toast store
  hooks/
    useAppState.ts            DEAD
    useGatekeeperStatus.tsx   DEAD
  design/
    tokens.css                light + dark CSS custom properties
    theme.ts                  3-state theme store, no library
    useTheme.ts               useSyncExternalStore wrapper
  lib/
    format.ts    (330)  czk / percent / price / plural / day + band, zone, verdict names
    compound.ts  (409)  goal math: futureValue, project, retirementOutlook
    finds.ts     (365)  Finds helpers: citations, pillars, attention scoring
    tickers.ts   (109)  canonicalOf / canonicalSet / pickAnalysis
    warnings.ts  (184)  groupWarnings + stripSeverityEmoji
    glossary.ts  (368)  42 terms for <Term>
    *.test.ts    5 files, 124 tests
  utils/errorHandling.ts      handleApiError, retryRequest, checkBackendConnection
  components/
    InvestmentTerminal.tsx    4352 lines — shell, portfolio tab, 8 inline modals
    StockDetail.tsx           920 — position modal ("Decision Cockpit")
    DecisionBoard.tsx         843 — the "Co s tím" board
    DailyActionWidget.tsx     403 — "Co mám dnes udělat"
    shell/SideRail.tsx        223 — left nav + market traffic light
    shell/ContextPanel.tsx    213 — bottom accordion, 7 context cards
    MarketGaugeCard, CashHedgeCard, AwayModeCard, ScoreCalibrationCard,
      PortfolioDiffCard, BreakoutWatchlistCard, RiskMeter
    stock-detail/  GomesHeader, SafetyBadge, ThesisCard, TradingDeck, TradeForm,
                   SecFilingsCard
    finds/         FindsPage, FindList, FindDesk, FindForm, AttentionPanel,
                   VerdictColumns, FindEvidenceStrip
    goal/          GoalPage, CalculatorControls, MilestoneLadder, ProjectionChart
    models/        RevenueModelsPage, RevenueModelList, RevenueModelDesk
    payments/      PaymentsPage (presentational only)
    ui/            Term.tsx (portal tooltip), ThemeToggle.tsx
```

---

## Shell and navigation

`main.tsx` → `App.tsx` → `<ToastProvider><InvestmentTerminal/><ToastContainer/></ToastProvider>`.
That is the entire app composition.

**There is no router.** No `react-router`, no URL state, no deep links. Navigation is
one `useState` at [InvestmentTerminal.tsx:1829](../../frontend/src/components/InvestmentTerminal.tsx#L1829):

```ts
const [activeTab, setActiveTab] = useState<
  'rozhodnuti'|'portfolio'|'watchlist'|'nalezy'|'modely'|'cil'|'splaceni'
>('rozhodnuti')
```

The same union is re-declared as `TabId` in
[SideRail.tsx:21](../../frontend/src/components/shell/SideRail.tsx#L21) — duplicated,
not imported.

**Layout contract** (documented in comments at `InvestmentTerminal.tsx:2447`):
`h-screen` + `overflow-hidden` at the root, `min-h-0` down every flex link. *Only
lists scroll; the window never does.*

### App-level fetch on mount

Runs once regardless of tab ([InvestmentTerminal.tsx:2026](../../frontend/src/components/InvestmentTerminal.tsx#L2026)),
each call in its own try/catch so one failure does not kill the page:

| Call | Endpoint | Behaviour on failure |
|---|---|---|
| `getExchangeRates()` | `GET /api/currency/rates` | keeps a hardcoded fallback `{EUR: 25, USD: 24}` ⚠ |
| `getLadder()` | `GET /api/gomes/ladder` | Pásmo column stays empty — never computed client-side |
| `getMarketStatus()` | `GET /api/portfolio/market-status` | `marketAlert` stays `null`, which is read as a **veto**, never as GREEN ✅ |
| `getPortfolios()` + N× `getPortfolioSummary(id)` | `/api/portfolio/portfolios[/{id}]` | failing summaries **silently skipped** ⚠ |
| `getEnrichedStocks()` | `GET /api/stocks/enriched` | throws to the outer catch |

`SideRail` calls `getMarketStatus()` again independently, so the traffic light is
fetched twice on load.

---

## Screen map

### 1. "Co s tím" / `rozhodnuti` (default) — `DecisionBoard.tsx`

Master–detail. A filterable list of cards (one per company) on the left, the full
thesis on the right. Each card carries: band pill + `BandScale` (R/R score against
"deserved" = 10 − cylinders), `band_reason_cs`, the two limit prices
(`buy_below` / `sell_above`), a 180-day price chart with the limits drawn as
`ReferenceLine`s, `SafetyLine` (downside to the tangible-book or net-cash floor), the
Breakout second opinion, per-company notes, then one `OwnerRow` per portfolio owner
with instruction, quantity and limit price.

Endpoints: `GET /api/trading/board`, `GET /api/trading/ohlcv/{ticker}?days=180`.

**This is the only screen that renders backend verdicts verbatim** — no client-side
verdict maths. It is the model the rest of the app should follow.

### 2. "Portfolio" / `portfolio` — `InvestmentTerminal.tsx:2777–3009`

- **Left:** `DailyActionWidget` (`GET /api/trading/daily-actions`) — either "Dnes není
  co dělat" or ≤3 ranked actions (BUY / TRIM / SELL / SELL_WAIT_TIME /
  LIQUIDATE_HEAVY, plus the non-executable `ROZPOR` which links to tab 1), a
  concentration strip, and always-visible grouped warnings.
- **Right:** monthly allocation strip (editing the contribution issues
  `PUT .../monthly-contribution` for **every** portfolio, split evenly), search, sort
  (`score` / `weight` / `pl`), and the positions table.
- **Columns:** Symbol (+ `REVIEW` and `⚠ SEC` badges), **Pokyn**, Váha (now/target),
  Skóre, Cena, Pásmo, P/L, remove. Optional columns render only when ≥1/5 of rows have
  data (`columns` memo at `:2358`) — the anti-redundancy rule in code.
- Row click → `StockDetail` modal. X → `RemovePositionDialog`.
- **Below:** `ContextPanel` — 7 collapsible bullets, only one open at a time,
  persisted:

| Bullet | Component | Endpoint |
|---|---|---|
| Trh | `MarketGaugeCard` | `GET /api/market-gauge` |
| Hotovost a hedge | `CashHedgeCard` | `GET /api/cash-hedge` |
| Nepřítomnost | `AwayModeCard` | `GET/PUT /api/away`, `POST /api/away/preview` |
| Kalibrace | `ScoreCalibrationCard` | `GET /api/intelligence/score-calibration` |
| Rozdíly portfolií | `PortfolioDiffCard` | `GET /api/portfolio/family-audit` |
| Breakout | `BreakoutWatchlistCard` | `GET /api/breakout/watchlist`, `POST /api/breakout/refresh` |
| Skladba | `RiskMeter` | none — props from `familyData` |

### 3. "Sledované" / `watchlist` — `InvestmentTerminal.tsx:3012–3091`

Stocks with a conviction score that are **not** held (via `canonicalSet` /
`canonicalOf` from `lib/tickers.ts`, which handles cross-exchange listings). Columns:
Symbol, Firma, Skóre, Verdikt, Cenové pásmo, Výsledky (`EarningsCell`), Detail. Row
click opens `WatchlistDetailModal` (defined inline at `:772`), which can post new
intelligence via `POST /api/gomes/update-stock/{ticker}`.

### 4. "Nálezy" / `nalezy` — `finds/FindsPage.tsx`

List left, desk right. Four render states (loading / error+retry / empty / content)
are explicitly kept apart.

Endpoints: `GET /api/finds`, `GET /api/finds/{id}`, `POST /api/finds` (120 s timeout —
it hits Yahoo, EDGAR and Finnhub), `POST /api/finds/{id}/refresh` (free),
`POST /api/finds/{id}/explain` (**paid**, 300 s timeout, labelled as paid on the
button), `PATCH /api/finds/{id}`.

`FindDesk` ordering is load-bearing: header → buy-gate sentence → `AttentionPanel`
(points **always** with ceiling) → gaps → `VerdictColumns` (PRO/PROTI with fact-id
chips, dropping uncited points loudly) → `FindEvidenceStrip` → assessment history.

### 5. "Modely" / `modely` — `models/RevenueModelsPage.tsx`

Analyst revenue models against reality. `GET /api/revenue-models`,
`GET /api/revenue-models/{id}`, `POST /api/revenue-models/{id}/compare` (SEC read, on
button only, 60 s).

### 6. "Cíl" / `cil` — `goal/GoalPage.tsx`

Compounding calculator fed by `portfolioValue` / `monthlyContribution` from
`familyData`. `CalculatorControls` (slider + field per input), `ProjectionChart`
(recharts, three layers: contributed capital / expected / ±3 pp band),
`MilestoneLadder` (log scale), retirement outlook from `lib/compound.ts`. Its only
network call is `GET /api/market-gauge`, for `trend_pct_per_year` shown beside the
expected-return field as a sanity anchor.

### 7. "Platby" / `splaceni` — `payments/PaymentsPage.tsx`

Five ledgers (debts, shared, Míša, savings, Tom) as bullets plus one table.
**Presentational only** — all state, forms and the five near-identical modals live in
`InvestmentTerminal.tsx:3312–4338`.

> **Data is `localStorage`-only** (`akcion_debts`, `akcion_savings`,
> `akcion_shared_payments`, `akcion_tom_payments`, `akcion_misa_payments`). No
> backend, no backup. This tab was contributed by another person; see
> `INVARIANTS.md` — do not delete it, and check `git log --format='%an' -- <file>`
> before removing anything here.

### Header (all tabs)

Brand, portfolio value + unrealized P/L + EUR equivalent + progress bar to 500k, cash
pill (editable **only when exactly one portfolio exists** — otherwise a tooltip
explains why), position count, `ThemeToggle`, `NotificationBell`
(`GET /api/intelligence/notifications`), `ClearPortfolioButton`, Import (CSV modal),
Pozice (add position), Nová analýza (`/api/analyze/youtube` | `/api/analyze/google-docs`
| `/api/gomes/deep-dd`). `SideRail` also has "Nový intake" → `GomesIntakeModal`
(`POST /api/intake/analyze`, `POST /api/intake/commit`).

### `StockDetail` modal

Tabs: Přehled / Pozice / Trading / Analýza / Metadata. Fetches
`GET /api/portfolio/market-status` itself (null ≠ GREEN) and
`GET /api/gomes/owner-intent/{ticker}`. Sub-components: `GomesHeader`,
`SafetyGaugeRow`, `ThesisCard`, `TradingDeck` (client-side blocker rules), `TradeForm`
(`POST /api/portfolio/positions/{id}/trade`), `SecFilingsCard` (`GET /api/sec/{ticker}`,
`POST /api/sec/sync/{ticker}`). Position editing via `PUT /api/portfolio/positions/{id}`
is the **only reachable way** to fill a missing `avg_cost` or fix a currency. It has an
explicit "no analysis exists" branch that still shows the bare position rather than an
error dead-end.

---

## API client layer

`src/api/client.ts` — one `ApiClient` class exported as the `apiClient` singleton.

- `axios.create({ baseURL, timeout: 60000 })`.
- One response interceptor → `handleApiError()` in `utils/errorHandling.ts`, which
  classifies into `network | rate-limit | server | client | unknown` with Czech
  messages and **throws a structured `ApiError`** — so `catch` blocks receive
  `ApiError`, not `AxiosError`.
- ~70 methods grouped by comment banners.
- Per-call timeout overrides where the backend is slow: `createFind` / `refreshFind`
  120 s, `explainFind` 300 s, `compareRevenueModel` 60 s.

**Types are split across two files:** `src/types/index.ts` holds the domain model;
`client.ts:1119–1772` holds ~40 more exported interfaces. There is **no runtime
validation anywhere** — responses are cast, so a backend field rename fails silently.
Two such incidents are documented in code comments (`types/index.ts:556 FamilyGap`,
`client.ts:1181 ScoreHistoryItem.recorded_at`).

**~40 client methods are dead** (defined, never called from a live component),
including `analyzeText`, `getStocks`, `refreshPrices`, `syncSecAll`,
`getMatchAnalysis`, `getOpportunities`, `gomesAnalyze`, `getTickerTimeline`,
`synthesizeKnowledge`, `getAllocationPlan`, `healthCheck`.

---

## State management

There is **no state library and no global store in use**.

- `context/AppContext.tsx` + `hooks/useAppState.ts` exist but `AppProvider` is
  **never mounted**. Dead layer.
- `context/ToastContext.tsx` is the one live context — but `useToast` is currently
  called by **no live component**. Toasts are provided and effectively unused;
  components show inline errors instead.
- `design/theme.ts` is a hand-rolled module store (`subscribe` / `getSnapshot` /
  `setChoice`) consumed through `useSyncExternalStore`. The snapshot is the string
  `"choice|resolved"` so a system dark-mode flip re-renders even when the choice stays
  `"system"`.
- Everything else is local `useState` in `InvestmentTerminal` (~30 pieces) plus
  per-card fetch state.
- `familyData` (`useMemo`, `:2088`) does the entire portfolio roll-up: FX conversion,
  weights, gap analysis, priority allocation of the monthly budget, risk counts.

**localStorage keys:** `akcion.theme`, `akcion.rail.collapsed`, `akcion.panel.open`,
`akcion.panel.tab`, `akcion_debts`, `akcion_savings`, `akcion_shared_payments`,
`akcion_tom_payments`, `akcion_misa_payments`, plus `<key>__poskozeno` quarantine
copies written by `readStoredList` (`:1764`).

---

## Design system

**Colours.** Tailwind holds no literal colours; every one is
`rgb(var(--token) / <alpha-value>)`, so themes swap at runtime
(`tailwind.config.js:10`). Tokens live in `src/design/tokens.css`.

- Three surface *meanings*: `page` (ground), `frame` (**where the app speaks** — dark
  in both themes), `sheet` (records, a ruled ledger).
- `signal.{green,amber,orange,red}` — the traffic light. The only place colour carries
  state, and it is **always accompanied by a word**, never colour alone.
- `accent` = coral (`#D2401C` light / `#FF5A36` dark). **Saturated = interactive
  only**; muted colours (`positive` / `negative` / `warning`) are facts about money.
  This split is the documented core rule.
- Legacy compatibility aliases (`surface.*`, `border.*`, `text.*`) exist so 44 files
  did not have to change.
- `safelist` in `tailwind.config.js:19` covers runtime-composed class names.

**Typography.** `font-display` Archivo Variable (uses the width axis; verdicts and
brand only), `font-sans` IBM Plex Sans (Czech prose), `font-mono` IBM Plex Mono (all
numbers, tabular figures forced globally on `.font-mono`, `table`, `[data-numeric]`).

**Radii.** Deliberately near-square: `rounded-card` 3px, `rounded-button` 3px,
`rounded-input` 2px.

**Shared primitives.** `@layer components` in `index.css`: `.panel`, `.panel-inset`,
`.sheet`, `.sheet-head/-title/-row`, `.eyebrow`, `.data-label`, `.data-value`,
`.pro-card`, `.badge-*`, `.btn-primary/-secondary/-danger/-ghost`, `.table-pro`,
`.score-*`, `.input-pro`. React primitives: `ui/Term.tsx` (glossary tooltip rendered
through a **portal into `<body>`** so it is not clipped by `overflow: hidden`; hover,
keyboard focus and tap) and `ui/ThemeToggle.tsx`.

**Themes.** Three states (light / dark / system). `:root` carries the complete light
palette; dark is defined twice — under
`@media (prefers-color-scheme: dark) :root:not([data-theme="light"])` and under
`:root[data-theme="dark"]`.

**Accessibility.** `:focus-visible` outline in accent;
`@media (prefers-reduced-motion: reduce)` genuinely disables animations (with an
explicit comment noting the owner has MS); status is never carried by colour alone;
emoji are stripped from backend strings by `stripSeverityEmoji` because they cannot be
themed.

---

## Tests

5 files, 124 tests, all passing. **All are pure-logic unit tests on `src/lib`.** No
jsdom is installed and `vite.config.ts` has no `test` block, so the environment is
`node` — component testing is not currently possible without adding a dependency.

| File | Covers |
|---|---|
| `compound.test.ts` (372 l) | `futureValue`, `futureValueStaged`, `contributedAt`, `monthsToTarget` (including "never returns the 240-month cap as an answer"), `project` (band widening, no negative-return floor), `realValue`, `summarise`, `sustainableMonthlyIncome`, `retirementOutlook`, plus two real-household scenarios |
| `finds.test.ts` (407 l) | `citedFacts` (drops ids missing from the dossier, preserves order), layer labels, attention scoring |
| `warnings.test.ts` (151 l) | `extractTickers` (ISINs, parenthesised lists, currency notes), `groupWarnings` (9 sentences → 4 groups, blocking-first ordering, dedupe, **never discards an unrecognised warning**) |
| `tickers.test.ts` (110 l) | `canonicalOf`, `canonicalSet`, `pickAnalysis` precedence |
| `glossary.test.ts` (100 l) | Every entry has an explanation ≤2 sentences, no self-referencing terms, and — by reading `.tsx` sources off disk — **every `<Term id="…">` points at an existing term** (21 usages, 42 terms) |

> **The coverage is inverted relative to risk.** The pure maths is well tested; the
> business logic most likely to produce a wrong money decision —
> `getActionCommand`, `getActionSignal`, `getTargetWeight`,
> `calculateMaxAllocationCap`, `getAnalysisState`,
> `TradingDeck.evaluateTradeBlockers` — has **zero** test coverage, as do all React
> components, the API client and `lib/format.ts`.

---

## Problems

### Dead components

Directly unimported: `ActionCenter`, `AnalysisView`, `AnalyticsDashboard`,
`ConfirmDialog`, `DriftAlertsWidget`, `FamilyAuditWidget`, `GatekeeperShield`,
`GomesAlertPanel`, `KellyAllocatorWidget`, `QuickNoteInput`, `Sidebar`, `SkeletonCard`,
`TrafficLightWidget`, `hooks/useGatekeeperStatus.tsx`.

Transitively dead: `StockCard` → `ScoreHistoryMiniChart`; `ConvictionScoreCard`,
`TickerTimeline`, `TopPicksWidget`, `WatchlistRankingTable`, `TranscriptImporter` (all
via `AnalyticsDashboard`).

Also dead: `context/AppContext.tsx` + `hooks/useAppState.ts`, `src/App.css`.

Two dead components still call endpoints by raw `fetch` rather than the client:
`ActionCenter` → `/api/action-center/opportunities` and `GomesAlertPanel` →
`/api/trading/alerts/*`. Those are the only two endpoints not represented in
`api/client.ts` — and `/api/action-center/*` is served by a router that
**`main.py` never registers**.

### Broken CSS classes in *live* code

`.card`, `.skeleton`, `.btn`, the `info` colour family and `primary-card` do not exist
in `tailwind.config.js` or `index.css` (`.card` is defined only in the unimported
`App.css`):

| File | Lines | Class |
|---|---|---|
| `InvestmentTerminal.tsx` (`WatchlistDetailModal`, live) | 819–899 | `border-info/50`, `bg-info`, `text-info`, `focus:border-info` — renders with no border, background or accent |
| `stock-detail/SecFilingsCard.tsx` | 112, 122, 151, 165, 190 | `card p-4` → an unstyled div |
| `stock-detail/TradingDeck.tsx` | 168, 198, 320 | `card p-0`, `bg-primary-card/50` |
| `GomesHeader`, `SafetyBadge`, `ThesisCard` | — | `primary-card` |
| `DecisionBoard.tsx` | 815 | `bg-surface` (no DEFAULT on the `surface` scale) |
| `StockDetail.tsx` | 285 | `btn btn-secondary` (`.btn` undefined) |
| `TradingDeck.tsx` | 277, 297 | hardcoded `text-white` instead of a token |

All of these render inside the live "Decision Cockpit".

### Business verdicts computed client-side

This is the frontend's version of `INVARIANTS.md` §2. The engine is disciplined; the
presentation layer sometimes gets its own simpler copy.

| Where | What it recomputes |
|---|---|
| `InvestmentTerminal.tsx:194 getActionCommand` | The Pokyn column. Re-implements the backend's four Buy Guard gates in the browser (band presence, market alert, Wait Time, earnings blackout). The comments admit it is "the presentation layer's half of the same rule". It can drift from `GET /api/trading/board`, which answers the same question authoritatively on tab 1 — **two screens, two engines, one question** |
| `:92 TARGET_WEIGHTS`, `:157 getTargetWeight`, `:1670 calculateMaxAllocationCap` | Position-sizing policy (asset-class caps 12/8/3/2/0 %, ×0.5 for score <7, ×0 for runway <6 m, ×0.7 for <12 m, ×1.2 for ACTIVE_GOLD_MINE) hardcoded in the browser as a fallback when the backend omits `max_allocation_cap` |
| `:166 getActionSignal`, `:2221` budget loop | Ranks positions and allocates the monthly contribution entirely client-side (`MIN_INVESTMENT_CZK = 1000`) |
| `:294 ANALYSIS_STALE_AFTER_DAYS = 30`, `getAnalysisState` | The "is this analysis still current" rule exists **only** in the frontend |
| `:134 calculateMonthsToTarget` | A second, untested time-to-goal implementation duplicating `lib/compound.ts`'s tested `monthsToTarget`. The Goal tab uses the tested one; the header tooltip uses this copy |
| `stock-detail/TradingDeck.tsx:70 evaluateTradeBlockers` | Six trading rules evaluated in the browser to lock/unlock the Buy button |
| `hooks/useGatekeeperStatus.tsx:46` | A third copy of runway/stage/score gating (dead, but present) |
| `:994` `WatchlistDetailModal` | Prints a "Strong Buy Signal" panel from `score>=7 && price_zone ∈ {DEEP_VALUE, BUY_ZONE, ACCUMULATE}` — **with no gate at all** |

**The counter-example done right:** `bandToTrend` (`:361`) explicitly refuses to
recompute the band client-side and maps a missing band to `UNKNOWN`, not to a neutral
middle.

### Duplicated view logic

- **Five near-identical payment modals**, ~1030 lines (`:3312–4338`) — same 8 fields,
  same handlers, copy-pasted, each with its own duplicated `useState` block and
  persistence `useEffect` (`:1843–2005`).
- **Score → colour ternary** reimplemented in `PortfolioRow` (`:493`),
  `WatchlistDetailModal` (`:779`), the watchlist table (`:3033`) and `StockCard:190`
  (with *different* thresholds) — while `index.css` already defines `.score-high`,
  `.score-medium`, `.score-low`.
- **Currency formatting duplicated:** `formatCurrency` / `formatPercent` /
  `formatPrice` + a `CURRENCY_SYMBOL` map at `:113–343` duplicate `lib/format.ts`.
  The two maps have **different entries** (local has `ILS`; `format.ts` has
  `GBX`/`CHF`/`PLN`).
- `BAND_LABELS_CS` (`:379`) duplicates `bandName()` in `lib/format.ts:201`.
- Warning-group rendering duplicated between `DailyActionWidget:372` and
  `DecisionBoard:648`.
- The portfolio refetch block is written out four times (`:2013`, `:2057`, `:3266`,
  `:3297`).

### Missing-data hazards

Unguarded array access on fields the types declare required but the backend may omit.
The precedent is documented in code at `:2297` — a missing `unconvertible_positions`
crashed the Portfolio tab to a blank screen and had to be fixed with `?? []`. The same
pattern is **still unguarded** at:

`InvestmentTerminal.tsx:2121` (`portfolio.positions`), `ClearPortfolioButton.tsx:28,89`,
`DailyActionWidget.tsx:280,366` and `:339` (`action.current_price.toLocaleString()` on
a typed-non-null field — a null price crashes the widget),
`DecisionBoard.tsx:464,607` (`card.owners`), `SecFilingsCard.tsx:186,229,243,277,310`,
`CashHedgeCard.tsx:185,200`, `ScoreCalibrationCard.tsx:157`,
`BreakoutWatchlistCard.tsx:131,339`, `RevenueModelDesk.tsx:81`,
`FindEvidenceStrip.tsx:61,74`.

**There is no `ErrorBoundary` anywhere in the tree**, so any of these takes the whole
app to a white screen.

Other hazards:

- **Unwrapped `localStorage.setItem`** in the five payment persistence effects
  (`:1900, 1905, 1938, 1971, 2004`) — throws in private mode or with site data
  blocked, unlike the carefully guarded `readStoredList` directly above it.
- **The FX fallback invents rates.** `exchangeRates` defaults to `{EUR: 25, USD: 24}`
  (`:1803`) and `exchangeRates[positionCurrency] || 1` (`:2134`) values an unknown
  currency 1:1 with CZK and folds it silently into the portfolio total. This is exactly
  the class of bug the `unconvertible_positions` warning strip exists to surface.
- `WatchlistDetailModal` **hardcodes `$`** for `current_price`, `green_line` and
  `red_line` (`:958–968`) while the rest of the app is careful about CAD and EUR.
- `refreshPortfolios` swallows per-portfolio failures (`catch { /* skip */ }`), so a
  failing account silently vanishes from every total on screen.

### Lint

23 errors + 2 warnings across 12 files. 17× `@typescript-eslint/no-explicit-any`,
1× `no-misleading-character-class` (`lib/warnings.ts:183`, the emoji-strip regex),
1× unused binding (`errorHandling.ts:189`), `react-refresh/only-export-components`
(`ToastContext.tsx:24`), 2× `react-hooks/exhaustive-deps`.

Most are in dead files, but `lib/tickers.ts`, `lib/warnings.ts` and
`utils/errorHandling.ts` are live. `REDESIGN_BACKLOG.md` item **H0 says lint passing
blocks closing everything else**.

### Size

`InvestmentTerminal.tsx` is **4352 lines** and contains the shell, the portfolio
screen, five payment modals, the CSV import modal, the add-position modal, the
new-analysis modal, the watchlist detail modal, and the portfolio maths. It is the
single biggest maintenance risk in the frontend. The file also starts with a UTF-8 BOM.

---

## See also

- `API_REFERENCE.md` — the endpoints these screens call
- `INVARIANTS.md` §7 — the language, colour and density rules
- `DESKTOP_DESIGN_PROMPT.md` — the approved visual direction, in full
- `REDESIGN_BACKLOG.md` — the outstanding rebuild tasks
- `KNOWN_ISSUES.md` — the problems above, prioritised
