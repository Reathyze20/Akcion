"""
Record a standing owner instruction for one ticker — the override that
suppresses BUY/ACCUMULATE suggestions independently of the phase gate.

Why this exists
----------------
ECOR is GREAT_FIND (confirmed 23.8.2026) and would pass the Buy Guard, but
it is queued for exit: waiting for enough market interest to sell into, not
for the thesis to fail. SMSI is WAIT_TIME and already blocked, but for the
wrong reason — it is held only for a tax-loss harvest, and that block would
silently lift the moment a future reading moves it off WAIT_TIME. Neither
belongs on `stock_lifecycle`, which a rubric re-read can quietly overwrite;
see app/models/owner_intent.py.

No UI exists to set this — today it is two tickers on a single-user app, the
same reasoning `propose_lifecycle.py` uses for staying a script. **Writes
nothing unless asked.**

    --ticker ECOR --intent EXIT_PENDING --note "..." [--by Tomas]
"""

from __future__ import annotations

import argparse
import os
import pathlib
import sys

BACKEND = pathlib.Path(__file__).resolve().parent.parent
os.chdir(BACKEND)
sys.path.insert(0, str(BACKEND))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

from app.config.settings import get_settings  # noqa: E402
from app.database.connection import initialize_database, session_scope  # noqa: E402
import app.models  # noqa: F401,E402
import app.models.trading  # noqa: F401,E402
from app.services import owner_intent  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ticker", required=True)
    parser.add_argument(
        "--intent", required=True,
        choices=[owner_intent.EXIT_PENDING, owner_intent.TAX_LOSS_HOLD],
    )
    parser.add_argument("--note", required=True, help="proč, v jedné větě")
    parser.add_argument("--by", default="Tomas", help="kdo to zapisuje")
    parser.add_argument(
        "--commit", action="store_true",
        help="skutečně zapsat — bez tohohle jen ukáže, co by se stalo",
    )
    args = parser.parse_args()

    initialize_database(get_settings().database_url)

    with session_scope() as db:
        ticker = args.ticker.upper()
        existing = owner_intent.get(db, ticker)
        if existing is not None:
            print(f"{ticker}: dnes {existing.intent} ({existing.note!r}, zapsal {existing.set_by})")

        owner_intent.record(
            db, ticker, args.intent, note=args.note, set_by=args.by,
        )

        if args.commit:
            db.commit()
            print(f"{ticker}: zapsáno {args.intent} — {args.note}")
        else:
            db.rollback()
            print(f"{ticker}: NEzapsáno (chybí --commit) — bylo by {args.intent}: {args.note}")


if __name__ == "__main__":
    main()
