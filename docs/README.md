# Akcion Documentation Index

> ⚠️ **This file replaces an earlier "Complete System Documentation" index that
> described a January 2026 version of the app (React 18, a 6-component Master
> Signal, ML/PatchTST, Docker deployment) — none of which reflects the current
> codebase. That old content has been preserved as `README.legacy-2026-01.md` in
> this folder. Nothing was deleted; this file was rewritten as of 2026-08-28 to be
> the real, current index.**

This is the entry point into Akcion's documentation. If you are an AI or a new
contributor given access to this repository, **read in this order**:

1. [`INVARIANTS.md`](specification/INVARIANTS.md) — the rules that must never break, and why
2. [`ARCHITECTURE.md`](specification/ARCHITECTURE.md) — how the system is put together
3. [`DOMAIN_MODEL.md`](specification/DOMAIN_MODEL.md) — what the app is actually deciding, and why
4. [`KNOWN_ISSUES.md`](specification/KNOWN_ISSUES.md) — what is currently broken, prioritised

Then the four detailed references, read as needed:

5. [`API_REFERENCE.md`](specification/API_REFERENCE.md) — the full backend HTTP surface
6. [`DATA_MODEL.md`](specification/DATA_MODEL.md) — every table, and the traps in each
7. [`FRONTEND.md`](specification/FRONTEND.md) — the React app, screen by screen
8. [`OPERATIONS.md`](specification/OPERATIONS.md) — external data sources, scheduled jobs, config

Before starting **any** task, also read `../CLAUDE.md` (verification commands and
hard invariants) and `../IMPLEMENTATION_PLAN.md` in full — the latter is the running
engineering log and is frequently ahead of everything below it, including this index.

---

## Why this documentation exists

Akcion is a decision-support tool for one person's real family investment portfolio.
The owner has multiple sclerosis and limited time — correctness and honest handling
of missing data matter more than any feature. This documentation set was generated
2026-08-28 specifically so an AI given access to this GitHub repository could
understand the architecture, the domain, and the current defects quickly enough to
propose useful next steps. See `INVARIANTS.md` §0 for the full framing.

---

## The eight core documents — `docs/specification/`

| Document | Type | Covers |
|---|---|---|
| [`INVARIANTS.md`](specification/INVARIANTS.md) | Explanation | The cardinal rule (missing data ≠ a verdict), the Buy Guard, propose-then-confirm, secrets, language/design rules, verification commands |
| [`ARCHITECTURE.md`](specification/ARCHITECTURE.md) | Explanation | System diagram, the decision-request lifecycle end to end, why migrations are hand-written, the duplicate-engine risk |
| [`DOMAIN_MODEL.md`](specification/DOMAIN_MODEL.md) | Explanation | Gomes' methodology as code: market alert, lifecycle ratchet, R/R log-scale scoring, cylinders, position sizing, the Buy Guard's exact gate order, calibration status |
| [`KNOWN_ISSUES.md`](specification/KNOWN_ISSUES.md) | Reference | Every verified defect, P0 (money-affecting) to P4 (process), plus open decisions only the owner can make |
| [`API_REFERENCE.md`](specification/API_REFERENCE.md) | Reference | All 21 routers, every endpoint, duplicate/competing endpoints, dead code, schema notes |
| [`DATA_MODEL.md`](specification/DATA_MODEL.md) | Reference | All 47+ tables by domain, migration history and its known breaks, column-level traps (`is_current`, currency, `avg_cost`, price lines) |
| [`FRONTEND.md`](specification/FRONTEND.md) | Reference | Stack, every screen, the API client, state management, design system, dead components, client-side verdict duplication |
| [`OPERATIONS.md`](specification/OPERATIONS.md) | Reference | Every external integration (SEC, Yahoo, Firecrawl, LLM providers, brokers, WhatsApp), config, scheduled jobs, CI |

These eight are the **canonical, current** documentation. Everything below this line
is either domain source material that remains authoritative for its narrow topic, or
historical material kept for the record.

---

## Domain source material (still canonical, narrower scope)

These are not superseded — they are the primary sources `DOMAIN_MODEL.md`
summarizes and links back to. Read them directly for exact quotes and citations.

| File | Covers |
|---|---|
| [`GOMES_METHODOLOGY_CANON.md`](GOMES_METHODOLOGY_CANON.md) | The written source of truth for the investing method, distilled from Gomes' own article. When code and this doc disagree, **this doc wins** |
| [`GOMES_VIDEO_ADDENDUM.md`](GOMES_VIDEO_ADDENDUM.md) | Amendments from Gomes' own video, covering topics the article is silent on (V1–V14) |
| [`GOMES_TACTICAL_PANELS.md`](GOMES_TACTICAL_PANELS.md) | ⚠️ Describes the "Gomes Guardian" AI-analyst implementation that was later found to be a fabricating stub and disabled — see `INVARIANTS.md` §1. Historical design intent only; do not treat as current |
| [`KANADSKE_VYKAZY.md`](KANADSKE_VYKAZY.md) | The Firecrawl-sourced Canadian/foreign-filer cylinder layer — why it exists, what it costs, per-company findings |
| [`INVESTING_LITERATURE_CONTEXT.md`](INVESTING_LITERATURE_CONTEXT.md) | Secondary context (Lynch, Mayer, O'Neil, Marks, Dorsey, Graham) explaining *why* the canon's rules make sense — never itself a source of a rule |
| [`EFFICIENT_INVESTING_PLAYBOOK.md`](EFFICIENT_INVESTING_PLAYBOOK.md) | User paths and acceptance-test scenarios, with real tracker fixtures. Paths still valid; the sizing table (15%) predates and contradicts the current 10% Primary tier cap — trust `DOMAIN_MODEL.md` for the number |
| [`DESKTOP_DESIGN_PROMPT.md`](DESKTOP_DESIGN_PROMPT.md) | The approved visual direction ("signální skříň") — exact colour tokens and copy rules. Canonical; summarized in `INVARIANTS.md` §7 and `FRONTEND.md` |
| [`whatsapp/README.md`](whatsapp/README.md) | The WhatsApp grooming convention (author slots, no phone numbers, provenance) and index of archived extracts |
| [`AUDIT_2026-08-22.md`](AUDIT_2026-08-22.md) | The original 106-finding full audit. Useful-but-stale reference — most of its top findings are fixed; its unverified section (~25% of raw findings) was refuted and should not be treated as fact |
| [`AUDIT_2026-08-22_AKCNI_PLAN.md`](AUDIT_2026-08-22_AKCNI_PLAN.md) | The action-plan summary of the above |
| [`BACKLOG.md`](BACKLOG.md) | Live backlog drawn from the audit — covers only its top slice; see `KNOWN_ISSUES.md` for the fuller current list |
| [`REDESIGN_BACKLOG.md`](REDESIGN_BACKLOG.md) | Outstanding frontend rebuild tasks (A–I). Section A's palette is superseded by `DESKTOP_DESIGN_PROMPT.md`; the rest is current |
| [`SETUP_GUIDE.md`](SETUP_GUIDE.md) | A beginner install walkthrough written for a non-technical tester. Ports and paths correct; harmless to keep |
| [`AKCION_PROVOZ.md`](AKCION_PROVOZ.md) | Day-to-day operations how-to — migrations, scheduling, verification, troubleshooting. Mostly folded into `OPERATIONS.md` now; kept as the Czech-language original |

---

## Superseded — historical only, do not treat as current

These describe an earlier version of the application (roughly January–February
2026: React 18, Google Gemini 2.0 Flash as the primary model, a 6-component Master
Signal, an ML/PatchTST prediction engine, Docker/systemd deployment) that no longer
exists in this codebase. **Kept for the historical record per project convention —
nothing in this repository's docs gets deleted — but every fact in them should be
assumed wrong until cross-checked against the eight core documents above.**

| File | What it claimed that is no longer true |
|---|---|
| `README.legacy-2026-01.md` | The old version of this very index |
| [`COMPLETE_SYSTEM_DOCUMENTATION.md`](COMPLETE_SYSTEM_DOCUMENTATION.md) | React 18, Gemini 2.0 Flash, 6-component Master Signal, ML/backtesting, Docker/systemd/`docs.akcion.com` — none of this is real |
| [`AKCION_PRODUCT_OVERVIEW.md`](AKCION_PRODUCT_OVERVIEW.md) | A 5-phase lifecycle (canon has 3) and a 15% conviction-based allocation cap (canon has a 10% Primary tier cap) |
| [`MASTER_SIGNAL.md`](MASTER_SIGNAL.md) | The 3-pillar Master Signal with a 15% Weinstein-guard weight — Weinstein is 0% weight by explicit decision (informational badge only) |
| [`LOGICAL_VALIDATION.md`](LOGICAL_VALIDATION.md) | Anchored on `gomes_score` and a component (`StockDetailModalGomes.tsx`) that no longer exists |
| [`UNIVERSAL_INTELLIGENCE.md`](UNIVERSAL_INTELLIGENCE.md) | The specific reliability percentages (Filing 100%/Analyst 60%/Chat 30%) are Gemini-era; the underlying idea (source reliability tiering) survives in `source_key` and the dual-source cap matrix — see `DOMAIN_MODEL.md` |
| [`YAHOO_CACHE.md`](YAHOO_CACHE.md) | The cache mechanism exists but its staleness-honesty semantics were rewritten after the audit found failed fetches were logged as fresh — see `OPERATIONS.md` |
| [`PORTFOLIO_PL_CALCULATION.md`](PORTFOLIO_PL_CALCULATION.md) | Predates nullable `avg_cost`, FX conflict warnings, and the currency-honesty fixes — see `DATA_MODEL.md` §"avg_cost" |
| [`NOTIFICATIONS.md`](NOTIFICATIONS.md) | Documents phantom env vars (`SMTP_FROM_EMAIL`/`SMTP_TO_EMAIL`) that were found to permanently break the notification service, a port-8000 setup, and a systemd unit that was never used — see `OPERATIONS.md` |
| [`QUICKSTART.md`](QUICKSTART.md) | Wrong port (8000, not 8002), wrong API key name, wrong entrypoints |
| `../README.md` (repo root) | Same era as the above — React 18, Gemini, port 8000, wrong file/line counts |
| `../backend/README.md` | Port 8000, `/docs` instead of `/api/docs` |
| `../frontend/README.md` | Claims React 18; still contains Vite template boilerplate |
| `../backend/README_YAHOO_CACHE.md` | Same era as `YAHOO_CACHE.md` above |

---

## Scratch / not documentation

`../.github/instructions/*.md` are historical AI-assistant persona prompts from
January 2026, describing work already completed. Not documentation of current
behaviour.

---

## See also

- `../CLAUDE.md` — skill routing and verification commands, loaded automatically by
  coding agents
- `../IMPLEMENTATION_PLAN.md` — the running engineering log; always read this in full
  before starting non-trivial work
