"""
Pull daily price history for every held position into `ohlcv_data`.

Why a script
------------
It is one HTTP call per company and the data changes once a day, so it has no
business inside a request. Run it on a schedule beside the tracker poll.

What it is for
--------------
The lifecycle rubric measures "retraces a large part of the Great Find move"
(§3) against a peak. It was using Yahoo's 52-week high, which misses a thesis
that topped eighteen months ago and which lives in a cache whose price field
goes stale — that combination once turned ECOR's real 4 % drawdown into 41 %
and flipped its verdict from hold to sell.

    --ticker XYZ   one company instead of the whole portfolio
    --quiet        counts only
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
from app.models.portfolio import Position  # noqa: E402
from app.services.price_history import (  # noqa: E402
    LOOKBACK_YEARS,
    peak_since,
    refresh,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticker", help="jen jedna firma")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    initialize_database(get_settings().database_url)

    with session_scope() as db:
        if args.ticker:
            tickers = [args.ticker.upper()]
        else:
            tickers = sorted(
                {
                    p.ticker.upper()
                    for p in db.query(Position).filter(Position.shares_count > 0).all()
                }
            )

        total = 0
        for ticker in tickers:
            written = refresh(db, ticker)
            total += written
            if args.quiet:
                continue

            peak = peak_since(db, ticker)
            if peak is None:
                print(f"  {ticker:9} {written:5} dní  — vrchol neznám")
            else:
                print(
                    f"  {ticker:9} {written:5} dní  vrchol za {LOOKBACK_YEARS} roky "
                    f"{peak.value:8.2f} z {peak.label_cs}"
                )

        db.commit()
        print(f"\nUloženo {total} denních záznamů pro {len(tickers)} firem.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
