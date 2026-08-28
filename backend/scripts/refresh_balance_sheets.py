"""
Pull balance sheets into `fundamental_snapshots` and print the downside floor.

What this is for
----------------
Everything else the app computes measures upside. The Five Keys framework's
fifth question — the one Gomes recommended the summary of — asks the opposite:
what is holding this price up, and how far can it fall before something real
stops it.

The floor is built from tangible assets only, on purpose. Goodwill and
intangibles are the first entries written down when a thesis breaks, so a floor
that counts them is not a floor.

Why a script
------------
One HTTP call per company to the SEC. Inside a request that would make the
screen wait on twelve round trips to somebody else's server, which is the same
reason the cylinder rubric runs from here.

    --ticker XYZ   one company instead of the whole portfolio
    --dry-run      fetch and print, write nothing
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
from app.core.tickers import variants_of  # noqa: E402
from app.models.portfolio import Position  # noqa: E402
from app.models.sec import SecCoverage  # noqa: E402
from app.services.margin_of_safety import read  # noqa: E402
from app.services.margin_of_safety_lookup import (  # noqa: E402
    balance_from_filings,
    store,
)


def _cik(db, ticker: str) -> str | None:
    row = (
        db.query(SecCoverage)
        .filter(SecCoverage.ticker.in_(variants_of(ticker) or (ticker.upper(),)))
        .filter(SecCoverage.status == "COVERED")
        .first()
    )
    return row.cik if row else None


def _fundamentals(db, ticker: str):
    """Tagged filings, or None with the reason printed. Never raises."""
    cik = _cik(db, ticker)
    if not cik:
        return None
    try:
        from app.services.sec_fundamentals import fetch_fundamentals

        return fetch_fundamentals(ticker, cik)
    except Exception as e:  # noqa: BLE001
        print(f"    (SEC: {type(e).__name__}: {e})")
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticker", help="jen jedna firma")
    parser.add_argument("--dry-run", action="store_true", help="nic nezapisuj")
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

        prices = {
            p.ticker.upper(): (p.current_price, p.currency)
            for p in db.query(Position).filter(Position.shares_count > 0).all()
        }

        written = 0
        for ticker in tickers:
            balance = balance_from_filings(_fundamentals(db, ticker))
            price, _currency = prices.get(ticker, (None, None))
            reading = read(ticker, float(price) if price else None, balance)

            if not reading.support or not reading.support.known:
                gaps = "; ".join(reading.support.unknowns) if reading.support else "bez výkazů"
                print(f"\n{ticker}: podlahu nespočítám — {gaps}")
                continue

            floor = reading.support.floor_per_share or 0.0
            print(f"\n{ticker}: podlaha {floor:.2f} ({reading.support.layer})")
            for note in reading.notes_cs():
                print(f"    {note}")

            if not args.dry_run:
                store(db, ticker, balance)
                written += 1

        if args.dry_run:
            db.rollback()
            print(f"\n--dry-run: nic se nezapsalo ({len(tickers)} firem prošlo).")
        else:
            db.commit()
            print(f"\nUloženo {written} rozvah z {len(tickers)} pozic.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
