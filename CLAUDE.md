
## Skill routing

When the user's request matches an available skill, invoke it via the Skill tool. When in doubt, invoke the skill.

Key routing rules:
- Product ideas/brainstorming → invoke /office-hours
- Strategy/scope → invoke /plan-ceo-review
- Architecture → invoke /plan-eng-review
- Design system/plan review → invoke /design-consultation or /plan-design-review
- Full review pipeline → invoke /autoplan
- Bugs/errors → invoke /investigate
- QA/testing site behavior → invoke /qa or /qa-only
- Code review/diff check → invoke /review
- Visual polish → invoke /design-review
- Ship/deploy/PR → invoke /ship or /land-and-deploy
- Save progress → invoke /context-save
- Resume context → invoke /context-restore
- Author a backlog-ready spec/issue → invoke /spec

## Verification commands

Every LongHorizon-Harness role starts with an empty context and reads this file,
so the auditor knows no command that is not written down here.

- Backend tests: `python -m pytest` from `backend/`. Use the **system** Python —
  pytest is not installed in `.venv` and is not in `requirements.txt`.
- Frontend build: `npm run build` from `frontend/` (runs `tsc -b` first, so it
  is also the type check).
- Frontend lint: `npm run lint` from `frontend/`.

A subtask counts as done only when the relevant command above exits 0. An
executor's claim that something works is not evidence.

## Invariants

- `backend/.env` holds live brokerage and SMTP credentials. Never read it into
  output, never copy it, never commit it.
- Never send a real notification or place a real order to verify a change. Use
  `--dry-run` (see `backend/scripts/away_check.py`) or a test double.
