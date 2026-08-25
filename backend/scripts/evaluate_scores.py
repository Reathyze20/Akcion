"""
Measure the score journal against what the prices did.

Reads every entry in `conviction_score_history`, and for each of the four
horizons (30/90/180/365 days) writes or refreshes a row in `score_outcomes`.
Rows already measured are left alone — an outcome is a record of a prediction
that was judged once.

Scheduling
----------
Already scheduled, as of 2026-08-23. Windows Task Scheduler runs
`scripts/evaluate_scores.cmd` (which adds a log) daily at 18:00 under the task
"Akcion - vyhodnoceni skore", with "run as soon as possible after a missed
start" on — the machine is not always awake at six.

    Get-ScheduledTaskInfo    -TaskName "Akcion - vyhodnoceni skore"  # last result
    Start-ScheduledTask      -TaskName "Akcion - vyhodnoceni skore"  # run it now
    Unregister-ScheduledTask -TaskName "Akcion - vyhodnoceni skore"  # remove it

Log: backend/logs/evaluate_scores.log

The hour does not matter, and is not allowed to. Only completed sessions are
measured (see SETTLE_DAYS in score_outcomes.py), so a run at nine in the
morning and a run at midnight give the same answer. A missed day costs nothing
either — the shortest horizon is a month.

It does still need the machine on and a network: the same limitation as
away_check.py, and the same eventual fix.

    --dry-run   evaluate and print, write nothing
    --today ISO pretend it is a different day (for checking the rules)
"""

from __future__ import annotations

import argparse
import os
import pathlib
import sys
from datetime import date

BACKEND = pathlib.Path(__file__).resolve().parent.parent
os.chdir(BACKEND)  # Settings reads .env relative to the working directory
sys.path.insert(0, str(BACKEND))

# The Windows console this runs on is cp1250. Anything outside that page — an
# arrow, a typographic quote — raises UnicodeEncodeError and takes the whole
# run down, which is a poor way for a scheduled job to fail. Replace rather
# than crash.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

from app.config.settings import get_settings  # noqa: E402
from app.database.connection import initialize_database, session_scope  # noqa: E402
import app.models  # noqa: F401,E402  — SQLAlchemy needs every mapper
import app.models.trading  # noqa: F401,E402
from app.models.score_outcome import ScoreOutcome, STATUS_UNABLE  # noqa: E402
from app.services.score_outcomes import HORIZONS, evaluate_all  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true", help="evaluate and print, write nothing"
    )
    parser.add_argument(
        "--today",
        type=date.fromisoformat,
        default=None,
        help="evaluate as if it were this date (ISO), for checking the rules",
    )
    args = parser.parse_args()

    ok, error = initialize_database(get_settings().database_url)
    if not ok:
        print(f"Databáze není dostupná: {error}")
        return 1

    today = args.today or date.today()
    print(f"Vyhodnocuji k {today}, horizonty {'/'.join(str(h) for h in HORIZONS)} dní")

    with session_scope() as db:
        summary = evaluate_all(db, today=today)
        print(summary.describe())

        if summary.unable:
            print()
            print("Nezměřitelné, podle důvodu:")
            reasons: dict[str, int] = {}
            for row in db.query(ScoreOutcome).filter(
                ScoreOutcome.eval_status == STATUS_UNABLE
            ):
                reasons[row.unable_reason] = reasons.get(row.unable_reason, 0) + 1
            for reason, count in sorted(reasons.items()):
                print(f"  {reason}: {count}")

        if args.dry_run:
            db.rollback()
            print()
            print("--dry-run: nic se nezapsalo.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
