"""
Day zero for the score journal.

`stocks` holds a current conviction score for twelve companies and no record
of when any of them was issued — eight have no `updated_at` at all, two were
last touched on 2026-02-01. That history cannot be reconstructed; it was never
written. What *can* be done is start the clock, so that measurement begins
today instead of whenever each company next happens to be re-analysed, which
for a stale ticker could be never.

This writes one journal row per already-scored stock, sourced `seed`. The row
claims only what is true: this was the app's score for this company on the day
the journal opened. It does not claim the score was formed that day, and
`source='seed'` is what keeps the two apart — a calibration report can exclude
these rows if their unknown provenance ever matters.

Run once:

    python scripts/seed_score_journal.py --dry-run    # decide and print
    python scripts/seed_score_journal.py              # write

Idempotent: a ticker that already has any journal row is left alone, so a
second run does nothing.
"""

from __future__ import annotations

import argparse
import os
import pathlib
import sys

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
from app.models.score_history import ConvictionScoreHistory  # noqa: E402
from app.models.stock import Stock  # noqa: E402
from app.services.score_journal import SOURCE_SEED, record_score, trusted_price  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="decide and print, write nothing",
    )
    args = parser.parse_args()

    ok, error = initialize_database(get_settings().database_url)
    if not ok:
        print(f"Databáze není dostupná: {error}")
        return 1

    with session_scope() as db:
        already = {
            ticker
            for (ticker,) in db.query(ConvictionScoreHistory.ticker).distinct().all()
        }

        candidates = (
            db.query(Stock)
            .filter(Stock.conviction_score.isnot(None))
            .order_by(Stock.conviction_score.desc())
            .all()
        )
        todo = [s for s in candidates if (s.ticker or "").upper() not in already]

        if not todo:
            print(
                f"Deník už pokrývá všech {len(candidates)} oskórovaných akcií — "
                "není co zakládat."
            )
            return 0

        # Every quote first, before a single row is added: YahooFinanceCache
        # commits this session, and a commit in the middle of the write would
        # persist rows that --dry-run promised not to write.
        prices = {
            stock.ticker.upper(): trusted_price(db, stock.ticker) for stock in todo
        }

        print(f"{'TICKER':<10} {'SKÓRE':>6}  CENA")
        for stock in todo:
            ticker = stock.ticker.upper()
            price = prices[ticker]
            shown = f"{price}" if price is not None else "—  (baseline dopočte evaluátor)"
            print(f"{ticker:<10} {stock.conviction_score:>6}  {shown}")

            record_score(
                db,
                ticker=ticker,
                score=stock.conviction_score,
                source=SOURCE_SEED,
                stock=stock,
                price=price,
                action_signal=stock.action_verdict,
            )

        skipped = len(candidates) - len(todo)
        print()
        print(
            f"{len(todo)} nových záznamů"
            + (f", {skipped} už v deníku bylo" if skipped else "")
        )

        if args.dry_run:
            db.rollback()
            print("--dry-run: nic se nezapsalo.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
