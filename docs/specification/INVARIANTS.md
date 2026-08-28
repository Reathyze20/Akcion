# Invariants

**Type:** Explanation · **Audience:** anyone (human or AI) about to change this code
· **Last verified:** 2026-08-28

Read this before `ARCHITECTURE.md`. Akcion is not a demo. It allocates one family's
real savings. The rules below are not style preferences — several of them exist
because breaking them already cost money or nearly did.

---

## 0. What the app is for, and why that reorders everything

Akcion is a decision-support tool for a single owner who:

- manages **real family money** with it,
- has **multiple sclerosis**, so has limited time and energy and can be away for
  weeks at a time,
- targets roughly **20 % a year** — a high bar the app must never present as a promise.

Three consequences that outrank every feature request:

| Consequence | What it means in code |
|---|---|
| **Correctness is the feature** | A save that silently no-ops, a hardcoded UI value, or wrong math is a P0, not polish |
| **A decision must fit ~2 minutes, ≤3 actions, one screen** | The app proposes, the owner confirms. "Nothing to do today" is a first-class, well-designed state |
| **It must survive absence** | Stale data is labelled as stale, never filled in. Away mode sends **one** most-urgent message, not a stream |

Rank work by **(risk to capital × reduction in owner effort)**, not by feature appeal.

---

## 1. The cardinal rule: missing data must never become a verdict

This is the single recurring defect class in this codebase. It has been found and
fixed at least **six separate times** in different modules. It will happen again if
you are not looking for it.

**The shape of the bug:** a value is absent or ambiguous, and some branch converts
that absence into a confident, actionable output.

Documented instances:

| Where | What absence became |
|---|---|
| `StockLifecycleClassifier.classify()` | A whole transcript was searched for "10 cylinders" and credited to whichever ticker the caller passed — one 2-hour stream made every company a 10-cylinder GOLD_MINE. 10 cylinders ⇒ deserved score 0 ⇒ almost any price clears the Buy Guard |
| `market_status` | One row, `GREEN`, dated 2026-01-31, unflagged. Seven months of buys authorised against a stale reading |
| `determine_tier()` | Ended in "everything else = TERTIARY", and YELLOW blocks TERTIARY — so 14 *unanalysed* positions produced **SELL** orders precisely *because* nothing was known about them |
| `verify_claims()` | Rejected true claims whose quote spanned a `(1:35:22)` transcript marker — the same class pointing the other way: real evidence silently discarded |
| `GomesAIAnalyst.analyze_document` | Never called a model at all. Returned invented cash, burn, runway and a conviction score, and wrote them into the live `stocks` row with `"success": true` |
| An external AI backfill | 395 transcript claims written straight into the live DB unverified. Independent audit: 39.5 % confirmed, 50.4 % overstated, 9.9 % misattributed |

**The rule.** When you touch any branch that reads `cylinders`, `lifecycle_phase`,
`conviction_score`, `green_line` / `red_line`, `market_status`, or a price:

> Ask what the code does when that value is absent.
> The answer must be a named gap in Czech, never a default that happens to be actionable.

**The staleness corollary (asymmetric).** Stale data may make the app *more*
cautious, never less. A stale ORANGE still de-risks. A stale GREEN stops
authorising buys.

**The stub corollary.** Any not-yet-implemented path must **raise**, never return
something plausible. `analyze_document` now raises `AnalystNotImplemented` and the
route answers 501 and rolls back.

**The bulk-import corollary.** No mass AI extraction (transcripts, PDFs, anything)
may be written to the production DB without independent adversarial verification as a
**gate before the write**, not an audit after it. Mechanical citation checking
("that sentence really is in the transcript") catches only ~40 % of the problem —
attribution and overstatement need semantic judgement.

---

## 2. The Buy Guard may not be bypassed

`GomesGatekeeper.evaluate_buy_guard()` (`backend/app/trading/gomes_logic.py:1183`,
class at `:1015`) is the one place a buy-side verdict is authorised. It evaluates in
order: **market alert → cylinders (0–10) → lifecycle phase → R/R band → score >
deserved**.

- It is enforced on **both** backend paths: the daily-action engine
  (`services/daily_actions.py`) and the verdict path (`trading/gomes_logic.py`,
  "RULE 7 — no buy-side verdict may bypass it"). Failing the guard downgrades to
  **HOLD**, never to SELL.
- **The presentation layer counts too.** A table cell reading "STRONG BUY" is a
  verdict whether or not the backend agrees. `getActionCommand()` in
  `frontend/src/components/InvestmentTerminal.tsx:194` carries the same four gates
  (Wait Time, missing band, unknown market alert, earnings blackout) for exactly this
  reason — it previously computed a verdict from score and weight alone. Do not
  reintroduce a second, simpler copy of the rule anywhere in the UI.
- Margin of safety **informs and warns; it never permits or blocks.** It is
  deliberately *not* a sixth gate. A purchase already passes band, cylinders, Buy
  Guard, tier cap, source matrix, pacing and concentration; adding a veto from a
  different method is what caused five competing engines to be deleted once already.

---

## 3. Propose, then confirm — the app never authorises its own inputs

Cylinders and lifecycle phase are the two inputs the Buy Guard leans on hardest, and
neither can be derived from public data. They are Gomes' own judgement.

- `cylinder_intake.propose()` / `lifecycle_intake.propose()` may **suggest**.
- Only `…​.confirm()`, called on a human action, writes to `stock_lifecycle`.
- Writes are **append-only**: the previous reading is retired, not deleted.
- A rubric run may never silently overwrite a number a human confirmed —
  `_outranks_rubric` recognises the analyst only by the `source` field, so when you
  write a number from a non-rubric source (a Gomes video, a manual judgement), you
  **must** correct `source` before commit. `cylinder_intake.confirm()` hardcodes
  `"rubric"`; leaving it loses provenance *and* lets the next rubric run overwrite it.

**The Nálezy (own finds) sandbox has the same rule, harder:** nothing in
`services/find_dossier.py`, `find_explainer.py` or `routes/finds.py` writes to
`stock_lifecycle`, `stocks` or `positions`. It reads only.

---

## 4. Provenance: never merge audited numbers with model interpretation

| Layer | Source | May a model touch it? |
|---|---|---|
| Results | SEC XBRL, company release, Yahoo, Finnhub | **No.** Plain code, no key required |
| Outlook / red flags | Filing text through an LLM | Yes, and it is **labelled as an interpretation** |

Everything numeric — XBRL fundamentals, burn, runway, Form 4 classification, coverage
status, FX, R/R scoring, the market gauge — is deterministic code and runs with no API
key. Only the *narrative* layer calls a model.

Related rules that fall out of this:

- A reading from a company press release is discarded unless it carries a **verbatim
  quote, a period length, and a `source_url`** (`services/release_fundamentals.py`).
- A price target is only called a target if the number appears **literally in the
  speaker's own quote**. `find_dossier._quoted_target` strikes 27 of 61 stored
  targets on this rule alone; even what survives is phrased as "a price was
  mentioned", not "target".
- Anything a person did not confirm may be shown only as a conditional sentence
  ("if cylinders were N (unconfirmed)…"), never as a fact.

---

## 5. Secrets and live systems

- **`backend/.env` holds live brokerage and SMTP credentials.** Never read it into
  output, never copy it, never commit it. Use `backend/.env.example`.
- **Never send a real notification or place a real order to verify a change.** Use
  `--dry-run` (see `backend/scripts/away_check.py`) or a test double.
- **The key-in-log trap.** `requests` puts the full URL — including `?token=` — into
  the text of an `HTTPError`, so `logger.exception` writes a live key into the log
  file. `_safe_reason` in `services/finnhub_metrics.py` is the fix. **This applies to
  every API added from now on.** Send keys in an `Authorization: Bearer` header, never
  as a query parameter.
- `whatsapp_contacts.local.json` (phone number → name) is gitignored and must stay
  that way. No phone number belongs in `docs/`, not even in a format example.

---

## 6. Two sources, and they are not equal

The owner follows **Mark Gomes** (a structured single analyst, with a written
methodology — see `GOMES_METHODOLOGY_CANON.md`) and **Breakout Investors** (a
crowd-sourced community with no written rules).

Both coexist per ticker via `source_key`. The dual-source matrix caps position size
by agreement:

| Agreement | Cap |
|---|---|
| Both sources agree | ≤ 15 % |
| Single source | ≤ 7 % |
| Sources conflict | ≤ 5 % + review |

**Breakout can never override a Gomes block.** Anyone not on the analyst roster stays
`OTHER` and does not enter the matrix at all — writing the whole ~130-person group in
would silently double allowed position sizes on the opinions of unvetted people.

Add names only through `analyst_roster.add(db, name, 'BREAKOUT_INVESTORS', note=…)`,
always with a note recording when and on whose instruction.

---

## 7. Language and presentation rules

These come from the approved design direction ("signální skříň") and are enforced by
tests, not convention.

- **Czech everywhere in the UI**, in a professional register. No jargon-Czech, no
  telegram style.
- `GREEN` / `YELLOW` / `ORANGE` / `RED` are **database values** and must never appear
  in a sentence. Use `alertName()` (`frontend/src/lib/format.ts`) and `alert_cs()`
  (`backend/app/services/market_gauge.py`).
- Every abbreviation gets a tooltip via `<Term id="…">` against
  `frontend/src/lib/glossary.ts`. **A test walks every `.tsx` and fails if an id has
  no glossary entry.**
- No emoji as UI. A coloured dot instead.
- Czech decimal comma and Czech dates go through `frontend/src/lib/format.ts` — never
  `toFixed()` straight into JSX.
- **Never hardcode a Tailwind palette class** (`slate-800`, `text-green-400`) or a
  hex. Colours are RGB triples in `frontend/src/design/tokens.css` reaching Tailwind
  as `rgb(var(--x) / <alpha-value>)`. A codemod removed 711 hardcoded classes; they
  silently break light mode.
- **Nothing scrolls but lists.** The shell is `h-screen` + `overflow-hidden`; every
  layout chain carries `min-h-0`. Long-form context is reached through a bullet strip
  (`shell/ContextPanel.tsx`), not by stacking down the page.
- **Say each fact once.** What is true of every row is a fact about the portfolio, not
  the row. An optional column is drawn only once at least a fifth of the rows fill it.
  **Empty cell, never a dash** — a column of dashes is a vertical stripe with no
  information in it.

---

## 8. Verification is the only evidence

Every role that touches this repo starts with an empty context, so the commands are
written down here and in `CLAUDE.md`. **A claim that something works is not
evidence — an exit code is.**

| Check | Command | Directory | Status 2026-08-28 |
|---|---|---|---|
| Backend tests | `python -m pytest` (use **system** Python — pytest is not in `.venv` and not in `requirements.txt`) | `backend/` | 1583 passed, 1 failed, 54 skipped |
| Frontend build + typecheck | `npm run build` (runs `tsc -b` first) | `frontend/` | passes |
| Frontend tests | `npm test` (vitest, ~0.3 s) | `frontend/` | 124 passed |
| Frontend lint | `npm run lint` | `frontend/` | **23 errors, 2 warnings** |

The one failing backend test,
`test_unvalued_breakout_note.py::test_a_euro_holding_is_converted_before_the_percentage`,
is a **known defect in the test itself** (it depends on a live EUR rate), not a
regression. Do not "fix" it by changing the code it tests.

**A green unit suite is not enough.** Three real defects in the Nálezy feature passed
the complete green suite and were only found by running against real tickers, because
the fixtures return nothing from Yahoo and Finnhub. Test on real stocks before calling
a data-path change done.

---

## 9. Before you start any task

1. `git status` — how much is uncommitted? This repo has carried 200+ uncommitted
   files at once.
2. Read `IMPLEMENTATION_PLAN.md` in the repo root, in full. It is the running
   engineering log and is frequently *ahead* of both the docs and your assumptions.
   Skipping it has already caused expensive duplicated analysis.
3. Read `KNOWN_ISSUES.md` (this directory) for what is currently broken on purpose.

---

## See also

- `ARCHITECTURE.md` — how the system is put together
- `DOMAIN_MODEL.md` — cylinders, lifecycle, bands, the Buy Guard
- `KNOWN_ISSUES.md` — open defects and traps
- `../GOMES_METHODOLOGY_CANON.md` — the methodology source of truth
- `../../CLAUDE.md` — the short version of this file, loaded automatically by agents
