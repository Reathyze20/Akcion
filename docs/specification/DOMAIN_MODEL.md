# Domain Model

**Type:** Explanation · **Source:** `backend/app/trading/gomes_logic.py`,
`backend/app/services/*`, `docs/GOMES_METHODOLOGY_CANON.md`,
`docs/GOMES_VIDEO_ADDENDUM.md` · **Verified:** 2026-08-28

Read `INVARIANTS.md` first. This document explains *what the app is deciding* and
*why the engine is shaped the way it is*. For the Czech-language canon itself —
Gomes' own words, with citations — read `GOMES_METHODOLOGY_CANON.md` and
`GOMES_VIDEO_ADDENDUM.md` directly; they remain the primary source. This document is
the map of how that method became code.

---

## Who and what this encodes

Akcion encodes the investing methodology of **Mark Gomes** ("Money Mark"), an equity
analyst who publishes his research free, with the stated goal of attracting domain
experts who can confirm or kill his theses. His doctrine, in his own words: *"WE
INVEST. WE'RE NOT HERE TO TRADE."* About 20 moves a year. Not technical analysis — a
stock is a piece of a company, and a company has an estimable value from a forward
operating model plus investigative journalism.

A second source, **Breakout Investors** (a Discord community with no written canon),
is tracked in parallel. It can never authorize a buy on its own — see
[Two sources](#two-sources-and-why-one-can-only-veto) below.

**One canonical engine, several ancestors still executing.** The domain logic is not
one clean layer — it is roughly four generations of the same idea:

| Generation | Where | Status |
|---|---|---|
| Canon (current) | `trading/gomes_logic.py` (`GomesGatekeeper`, `RiskRewardCalculator`, `ZoneLadder`, `PositionSizingEngine`) + `services/{daily_actions,ladder_view,decision_board,cylinders,lifecycle_rubric}.py` | Live, tested, canon-faithful |
| Second source | `breakout_watchlist.py` → `breakout_sync.py` → `breakout_lookup.py` → `breakout_band.py` | Live, deliberately veto-only |
| Legacy linear bands | `trading_zones.py`, price-zone logic duplicated in `routes/stocks.py` and `gomes_deep_dd.py` | Live, untested, **mathematically contradicts the canon** |
| Legacy "circuit breaker" | `core/gomes_compliance.py` + `routes/trading.py` | Live endpoints, no frontend caller, **fails open** |
| Legacy ML/Kelly stack | `trading/{kelly,signals,gomes_signals,data_fetcher,watchlist}.py`, `investment_engine.py`, `master_signal.py` | Dead or unregistered |

When code and `GOMES_METHODOLOGY_CANON.md` disagree, the doc wins — it is the
primary author source, not a transcript.

---

## Layer 1 — the market Alert (portfolio-level timing)

Derived from the S&P's position on a 40-year valuation trend.

| Alert | Rule | Cash / hedge |
|---|---|---|
| 🟢 GREEN | Own stocks without fear; R/R charts size the positions | 0 % hedge |
| 🟡 YELLOW | Sell **all** speculative + Wait Time. Forget the 10-point rule. Raise cash — don't redeploy sale proceeds | 20–30 % RWM |
| 🟠 ORANGE | Between yellow and red; the cause is known, severity unclear | Most cash in RWM |
| 🔴 RED | Sell almost everything, bet against the market. Twice in 30+ years (end 1999, mid 2007) | Most of the money in RWM |

**The addendum sharpens this** (`GOMES_VIDEO_ADDENDUM.md` V3): the grade is
**valuation × knowledge of cause**. Yellow means "it's expensive and I don't know
what will break it" — *"most of my alerts are going to be yellow"* — so **yellow is
the base rate, not green.** Orange means the catalyst is known but not its severity
(COVID). Red means both are known and bad.

**Consequently, a valuation-only gauge can only ever emit GREEN or YELLOW.**
`services/market_gauge.py` enforces this with a module-load assertion —
`POSITION_ALERT` maps only to those two values. ORANGE and RED require a written,
dated `MarketCatalyst` (`services/market_catalyst.py`); a description with no date
counts as no cause at all. `grade_for()` returns `RED if severity_known else ORANGE`
— a **boolean, not a scale**, deliberately: a five-point severity scale would invite
a middling "3," and that middling judgement is exactly what Gomes refuses to make.

**The gauge is honest about its own blind spot.** It correctly identifies the 1999
top (z-score +2.74/+2.75, the two highest readings in 41.7 years) and **completely
misses mid-2007** (z = +0.58, an unremarkable month) — and finds none of Gomes' six
documented real hedge openings, including two weeks before COVID. Every reading
carries a `blind_spot_cs` field naming this. It is a valuation-only signal reporting
on a world it cannot see; the owner decides.

**Nothing in the app ever lowers the alert automatically.** `market_watch.py` is the
only writer with no human in the loop, and it may only *tighten* — GREEN→YELLOW,
never the reverse — because the gauge missed 2007 entirely and "has not earned the
right to sound an all-clear." The only de-escalation handle is a dated catalyst
expiring or being explicitly retired.

**Instruments:** BOXX (money-market parking) and RWM (inverse Russell 2000 — matched
to the *size* of companies actually owned, which is why TLT is rejected: it tracks
interest rates, not equities). The hedge is a **source of buying power**, not a
static allocation — it gets unwound near the bottom specifically to buy what's cheap.
Both are US-listed funds with no PRIIPs KID, so a European retail broker will likely
refuse to sell them to this account; the plan says so (`interpreted: true` on
percentages the app inferred rather than read verbatim from the canon).

---

## Layer 2 — the lifecycle (which stocks are eligible at all)

Three phases, and it is a **ratchet, not a classification**:

1. **Great Find** — nobody's heard of it, it's starting to do great things. Risky,
   allowed in GREEN.
2. **Wait Time** — the hype died, the story hasn't caught traction, it retraces most
   of the Great Find move and takes longer than expected. **Do not be invested.**
3. **Gold Mine** — momentum started, the company is profitable or has a strong order
   book. Safe to hold long — and **absorbing**: once reached, it does not slide back.

The addendum's critical correction (V1): a rough patch (fewer orders, a slow quarter)
is an **orthogonal, temporary flag**, never a phase demotion. Demoting a proven Gold
Mine on bad-quarter vocabulary blocks the buy precisely when the stock is cheapest —
which is where Gomes' whole career's money was made (his own example: CTLP $3 → $11).

`services/lifecycle_rubric.py::apply_ratchet` implements this: `PHASE_RANK =
{GREAT_FIND: 1, WAIT_TIME: 2, GOLD_MINE: 3}`, monotone, and `UNKNOWN` is deliberately
excluded from the rank so it can never act as a floor. A demotion from Gold Mine
becomes `rough_patch=True` with a dated note, not a phase change. The counterweight
lives in the Buy Guard: a rough patch with no date, or a cylinder confirmation that
predates the slowdown, is refused (`ROUGH_PATCH_STALE_QUALITY`) — otherwise a
purchase could run on quality agreed *before* the business actually slowed.

**Classification refuses more often than it decides.** `propose_phase()` requires
≥2 hard readings, refuses on a non-positive best score, refuses on a tie ("picking
one would be a coin toss that sells a position"), and explicitly vetoes
self-contradiction — WAIT_TIME is refused if revenue is growing ≥10 %, GOLD_MINE is
refused with no momentum evidence at all. `GREAT_FIND` confidence is always LOW, with
an appended caveat that a great find, by definition, means the market hasn't noticed
yet — which the app has no way to measure.

---

## Layer 3 — R/R charts, the core mechanic

Despite looking like technical-analysis lines, these are fundamental: DCF-based
("New DCF"/"Prior DCF"), anchored in a forward revenue estimate and a peer-comparable
multiple — not price history.

- **Green Line** ("Low") = undervalued = buy zone = **R/R score 10**
- **Red Line** ("High") = full valuation = sell zone = **R/R score 0**

**The scale is logarithmic, recovered from the live fan tracker riskrewardcharts.com
and verified against Gomes' real picks:**

```
R/R score      = 10 × log(High / price) / log(High / Low)
deserved_score = 10 − cylinders
BUY  when  R/R score > deserved_score       (cheap relative to quality)
SELL when  R/R score < deserved_score       (expensive relative to quality)
```

Implemented in `RiskRewardCalculator.calculate_rr_score`
(`trading/gomes_logic.py`), clamped to [0, 10] for parity with the public tracker. The
addendum (V8) wants an unclamped `rr_extension` alongside it purely for ranking ties
— two stocks 36 % and 4.7 % below their green line both currently read "10.00" — with
the explicit rule that it **may never touch the band enum** used for the buy/sell
decision itself.

**How the lines are actually built** (measured across 16 known line pairs plus 61
transcripts, project memory `akcion-jak-vznikaji-cary`): both lines anchor in
*revenue*, not price. Median EV-at-green ≈ 1.7–1.2× trailing revenue (varies by
whether current or one-year-forward revenue is used); median EV-at-red ≈ 8–9×. The
red line's multiple applies to a **future** revenue figure the model itself
forecasts, which is why it can look wild (up to 100×+ trailing) without being
arbitrary — it is a normal multiple (2.75–9.2×) applied to a revenue that hasn't
happened yet. This is Gomes' own stated method: *"look at what they can do with those
earnings... if they can double or quadruple those earnings, then the P/E they're
paying is only 15 or maybe seven."* What the app cannot reconstruct is the judgement
behind that future-revenue estimate — it requires a bottom-up model per company
(orders, backlog, management calls), which is exactly what the "Modely"
(analyst-revenue-models) feature exists to store and compare against reality, never
to compute.

### Cylinders — the input that exists on no website

Operating health, 0–10. Delays, lawsuits, a departing CFO push it down;
*"firing on all cylinders"* is 10. Gomes' own calibration: 5 cylinders means the
stock deserves to sit only halfway between green and red; 1 cylinder means it
deserves to be near the green line. So **quality sets the bar**: `deserved = 10 −
cylinders`. Ten cylinders deserve to run all the way to the red line (bar 0); one
cylinder deserves only the green line (bar ~9).

**Cylinders are his words on the stream — there is no API for them.** This is why
they are the app's binding gate, and why every path to a number is a *proposal*, not
an automatic write (`INVARIANTS.md` §3).

`services/cylinders.py::propose_cylinders` is a scored delta walk from a base of 5,
combining up to four layers, best available first:

| Layer | Range | Max confidence |
|---|---|---|
| SEC XBRL | 0–10 | HIGH at ≥4 hard readings |
| Company release (Firecrawl, Canadian filers) | 2–8 | MEDIUM |
| Yahoo TTM | 3–7 | MEDIUM |
| (fallback) | uncapped | — |

Below `MIN_HARD_READINGS = 2`, cylinders stay `None` — not a neutral 5. Analyst
opinion (Gomes' own stated number) can contribute a **soft** signal capped at ±2, but
can never satisfy the hard-reading minimum by itself, and can never be closed out by
a lower-ranked rubric proposal (`_outranks_rubric` — see the write discipline below).

### Confirmation: the gate that actually matters

`stock_lifecycle.cylinders_confirmed_at` is `NULL` until a human confirms —
`cylinder_intake.confirm()`, append-only versioning (the previous row retires with
`valid_until`, nothing is overwritten). Source precedence matters: an analyst-sourced
number outranks a rubric-computed one, and cannot be silently closed out by a later
rubric run.

**The asymmetry, applied consistently:** the buy side requires the confirmation to be
both present *and* unexpired; the sell side reads the raw count regardless of
expiry. Stale cylinders may make the app more cautious, never less.

---

## Position sizing

**Tier is a ceiling, not a target.** Primary/Core (proven Gold Mine) 10 %,
Secondary (Great Find — "the dating phase") smaller, Tertiary (speculative/FOMO)
1–2 %. **The score is the lever**:

```
target_pct = tier_cap × (rr_score / 10)
```

*"When a stock is a 10 on the scale, I'm liable to own 10 % of it; up here [near the
red line], zero or 1 %."* Equal weighting is explicitly rejected. In a YELLOW alert,
a fully-valued position's target drops to **zero**, not 1 %.

A separate, orthogonal cap layer — `services/asset_class_caps.py` — sizes by *what
kind of bet it is* (Anchor 12 %, High-Beta 8 %, Biotech 3 %, Turnaround 2 %, Value
Trap 0 %), independent of tier. Multiple caps apply and the tightest one wins.

**Dual-source cap.** Both sources coexist per ticker via `source_key`
(`GOMES` / `BREAKOUT_INVESTORS` / `OTHER`):

| Agreement | Cap |
|---|---|
| Both sources agree (`AGREE`) | ≤ 15 % |
| One source (`SINGLE`) | ≤ 7 % |
| Sources conflict (`CONFLICT`) | **0 %** |

Breakout can never authorize a buy alone; it can only reduce the cap or block one.

---

## The buy gate — evaluation order

`GomesGatekeeper.evaluate_buy_guard()` (`trading/gomes_logic.py`) evaluates
strictly in order; the **first** failure ends it and is the reason recorded:

1. Market alert is parseable and known
2. Market alert is GREEN
3. Cylinders are known and non-zero
4. Not Wait Time (and if a rough patch exists, it is dated and the cylinder
   confirmation postdates it)
5. R/R score and deserved score are both computable (needs green line, red line,
   current price)
6. R/R score > deserved score
7. Not inside the 14-day earnings blackout

Failure downgrades to **HOLD, never SELL** — a refused buy is not the same claim as
a sell signal. Every refusal is journalled (`refused_buys`, one row per ticker per
day per gate) so a year of refusals can be reviewed by cause.

**This gate has exactly three legitimate callers** in the current code:
`daily_actions.py` (both the buy and add paths) and `find_dossier.py` (advisory
only, in the Nálezy sandbox — it can never authorize a write there). `ladder_view.py`
and `decision_board.py`, which render the band shown on every board card, **do not
call it** — the displayed band is a fact about price vs. quality, not a purchase
authorization; the instruction text is what carries the guard's verdict.

**A weaker, older gate still runs in parallel and fails open.**
`core/gomes_compliance.py` blocks only on RED (not GREEN-required — YELLOW and
ORANGE pass), checks runway and a single conviction threshold, and knows nothing of
cylinders, R/R, bands, rough patches, or dual sources. It reads a *different*,
older semafor table (`market_alerts`, not `market_status`). It is mounted at
`POST /api/trading/{validate-order,order}`, which has **no frontend caller** —
harmless today only because nothing calls it.

---

## Selling

Two independent triggers, either one is enough:

1. **The 3-point rule** — a 3-point move on the 10-point log scale, in either
   direction, with exact trigger prices derived from the same log formula
   (`price × (High/Low)^(3/(10−topScore))`).
2. **The doubling rule** — *"if you doubled your money, sell half"* — computed
   purely from the owner's entry price, independent of where the stock sits on the
   chart.

Profits taken at R/R highs fund the cash reserve for the next downturn. Exits are a
ladder of partial sells; a full exit returns the name to the watchlist with a
re-entry price, it is not simply forgotten.

**Empirical grounding, from Gomes' own 12-year "Priority Ideas" track record** (208
ideas, 200 closed, parsed and analyzed — project memory `akcion-gomes-track-record`):
68 % overall hit rate, median +15 % return. The number that justifies the sell
discipline: **median long-position peak return was +64 %, but the median actual exit
was +13 %** — a median 28-percentage-point round trip given back between the top and
the actual sale, sometimes far worse (one position went from +22,394 % to −29 %). Even
the analyst whose rules these are gives most of the profit back without them. This is
the empirical case for the ratchet and the sell discipline, not a theoretical one.

---

## Two sources, and why one can only veto

The owner follows Gomes (structured, single analyst, written methodology) and
Breakout Investors (crowd-sourced Discord, no written canon). Coverage is genuinely
asymmetric: measured against the live database, only 3 of 15 held positions have any
Gomes mention at all, and 12 of 28 Breakout-watched names Gomes never mentions.

**Value in the Breakout data is not in the opinion — it's in two things that are
independently falsifiable:**

1. **A dated, priced prediction.** Gomes' lines carry no expiry — they cannot be
   proven wrong by a clock. Breakout entries carry `implied_target` and
   `price_at_first_seen`, so `breakout_scorecard.py` can measure a hit rate — but
   only after `MIN_HORIZON_DAYS = 180` have passed; below that it reports "too early"
   rather than a misleadingly small sample.
2. **Cadence, not sentiment.** Measured across 366 stored mentions:
   `conviction_level` is 361/366 HIGH (a constant, carries no information),
   `sentiment` is 311/366 BULLISH and mislabels several genuinely bearish quotes as
   neutral WhatsApp Q&A. The one field that actually varies is **how often** an
   analyst returns to a name — a company an analyst covered weekly and has now gone
   silent on for 100+ days is a signal; a company nobody ever covered is not the same
   as one that's being watched and found wanting.

Both are computed by code, never asserted by a model, and both feed the cap matrix
above — never a buy authorization on their own.

---

## The decision surface — "what do I do today"

`services/daily_actions.py` assembles everything above into at most **three ranked
actions** per account, or the explicit state `HOLD_HOLD_HOLD` ("nothing to do today"
— a first-class, deliberately well-designed empty state per `INVARIANTS.md` §0).

Priority order (de-risking always outranks profit-taking, which outranks buying):
`LIQUIDATE_HEAVY` (market RED) → `ROZPOR` (phase says sell but the band disagrees —
handed back to the owner with no verb, no limit price) → `SELL_WAIT_TIME` →
blocked-tier `SELL` → doubling `TRIM` → R/R `TRIM` → `ADD` → `BUY`.

`decision_board.py` renders **one card per company** (a fact about the company,
computed once) and **one row per owner** underneath it (an instruction, computed per
account against that account's own cost basis, weight and cash — never against
summed accounts). An owner with no action still gets a row; silence is a state, not
an absence.

`owner_intent.py` is the one standing human override the engine cannot derive:
`EXIT_PENDING` (queued for exit, waiting for buyer interest) and `TAX_LOSS_HOLD`
(held only to harvest a tax loss). A non-null intent suppresses buy-side actions with
no warning text at all — the decision has already been made by a human and does not
need re-litigating daily. It never suppresses a sell.

---

## Nálezy (own finds) — the owner's ideas, judged by the same method

A separate, closed sandbox where the owner enters a ticker and a sentence ("why I
noticed it"). The app assembles a dossier from four layers (Gomes, Breakout,
fundamentals, the method engine) and can, on request, translate it into a paid
AI-generated for/against column where every point cites a specific fact from the
dossier by id.

**Five hard invariants** (see `INVARIANTS.md` §3 for the general rule this
specializes):

1. Nothing here writes to `stock_lifecycle`, `stocks`, or `positions` — only
   `cylinder_intake.confirm()` / `lifecycle_intake.confirm()` change buy-gate inputs,
   and finds never call them.
2. The band is computed from **confirmed** cylinders only; an unconfirmed rubric
   proposal appears only as a conditional sentence ("if cylinders were N
   (unconfirmed)…").
3. "What we don't know" is rendered from the dossier's own gap list — the model never
   writes about gaps. Facts carry a layer prefix; gaps carry a `MEZ-` prefix, and this
   split is what a mechanical check verifies.
4. The paid AI call happens only on explicit click — no cron, no loop, no call on
   page load.
5. Any AI point whose citation doesn't resolve to a real fact is dropped, and the
   **count of dropped points is shown on screen**, not hidden.

`find_attention.py` is the one place a *score* is deliberately allowed in this
sandbox, because a Nálezy find is `MIMO_METODIKU` by definition (it has no Gomes
band) and without some ordering, twelve ideas are indistinguishable. It answers a
different question than the buy gate — "is this worth more of my time?" not "may I
buy this?" — and its central rule is the sharpest expression of the missing-data
principle in the whole codebase: **a missing input lowers the ceiling, not the
score**, and **a known absence scores zero at full ceiling** ("we have 61 transcripts
and none mention this company" is a real zero) while **a genuine gap** ("we have no
transcripts at all") lowers the ceiling instead of guessing.

---

## Calibration — why the app cannot yet claim to work

`services/score_journal.py` opened 2026-08-23. Before that date the app issued scores
but never recorded *when* a given score was assigned — `conviction_score_history` and
its predecessor were empty. There is no way to honestly reconstruct that history, and
the code deliberately does not try (the old fallback that back-dated scores to
`created_at` was found and deleted).

`services/score_outcomes.py` measures each journalled score's *excess* return over
`^GSPC` at four horizons (30/90/180/365 days), with a `MIN_SAMPLE = 10` floor below
which no median is computed at all — the threshold lives in the backend precisely so
a UI cannot draw a false median by skipping the check.

**The correct current state is `sufficient: false`.** The first 30-day measurement
matures 2026-09-22; full calibration across all four horizons is not possible before
roughly August 2027. Until then, the honest self-description of this system is "an
informed, rule-enforced estimate with a full audit trail," not "a verified method" —
and the app should say exactly that on screen, not imply more.

---

## Prohibitions, stated once because they're stated repeatedly by Gomes himself

- **No options**, said three times in the source material.
- Never buy all active picks at once.
- Buy only when the market is GREEN **and** the price is attractive on the R/R chart
  — both conditions, never either alone.
- Never deploy cash just because it exists; a genuine surplus goes to BOXX, not into
  a marginal idea.
- Selective signal-following ("I'll follow this pick but skip that one") is called
  out explicitly as destroying the statistics that make the method work at all — the
  app enforces the gate rather than merely suggesting it for exactly this reason.

---

## What the method cannot do — stated honestly, on purpose

- It doesn't guarantee timing, and the app must never imply that it does
  (`INVARIANTS.md` §0).
- It doesn't see macro risk (tariffs, the Fed, geopolitics) directly — the market
  gauge is the nearest proxy, and it is deliberately slow and honest about its blind
  spot.
- It doesn't derive cylinders from the web — every path to a cylinder number is a
  proposal a human must confirm.
- It doesn't explain the DCF assumptions behind the lines — those live inside PNG
  chart images, and reading them is Gomes' own unautomatable research.
- As of this writing, most of the actual portfolio has no Gomes coverage at all, and
  two positions (ECOR, SMSI) have no coverage from either source. For those, "outside
  the method" is the correct and honest output — never a manufactured neutral score.

---

## See also

- `GOMES_METHODOLOGY_CANON.md`, `GOMES_VIDEO_ADDENDUM.md` — the primary Czech-language
  source this document summarizes; read these for exact quotes and citations
- `INVARIANTS.md` — the rules this domain model exists to protect
- `ARCHITECTURE.md` §"The shape of a decision" — how this maps to the actual request
  flow
- `API_REFERENCE.md` — the endpoints that expose this engine
- `DATA_MODEL.md` — `stock_lifecycle`, `conviction_score_history`, and the other
  tables this document's concepts are stored in
- `KNOWN_ISSUES.md` — the specific places this document's rules are currently
  violated in code
