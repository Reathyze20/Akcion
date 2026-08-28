"""
Propose a cylinder count for every held position, and print the evidence.

Why a script rather than a button
---------------------------------
The proposal needs two things the app does not keep: audited quarterly numbers
from SEC XBRL (one HTTP call per company, rate-limited to 10/s by regulation)
and Yahoo's trailing aggregates for the companies EDGAR cannot see. Both are
free and neither involves a model, but doing them inside a request would make
the daily list wait on somebody else's server.

So this runs on demand, prints what it found, and writes nothing. Confirming a
number is a separate, deliberate act — `cylinder_intake.confirm()` — because a
cylinder count is what unlocks the Buy Guard, and a number that arrived without
anyone looking at it is the same invented input the app keeps finding.

    --refresh-yahoo   pull trailing financials for names EDGAR cannot see
    --ticker XYZ      one company instead of the whole portfolio
    --quiet           the numbers only, without the evidence behind them
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

from datetime import datetime, timezone  # noqa: E402

from app.config.settings import get_settings  # noqa: E402
from app.database.connection import initialize_database, session_scope  # noqa: E402
import app.models  # noqa: F401,E402
import app.models.trading  # noqa: F401,E402
from app.core.tickers import variants_of  # noqa: E402
from app.models.portfolio import Position  # noqa: E402
from app.models.sec import SecCoverage  # noqa: E402
from app.services.cylinder_intake import is_sec_covered, propose  # noqa: E402


def _cik(db, ticker: str) -> str | None:
    row = (
        db.query(SecCoverage)
        .filter(SecCoverage.ticker.in_(variants_of(ticker) or (ticker.upper(),)))
        .filter(SecCoverage.status == "COVERED")
        .first()
    )
    return row.cik if row else None


def _fundamentals(db, ticker: str):
    """
    Audited quarterly numbers, or None with the reason printed.

    Never raises: a company EDGAR cannot serve must not stop the other eleven
    from being assessed.
    """
    cik = _cik(db, ticker)
    if not cik:
        return None
    try:
        from app.services.sec_fundamentals import fetch_fundamentals

        return fetch_fundamentals(ticker, cik)
    except Exception as e:  # noqa: BLE001
        print(f"    (SEC: {type(e).__name__}: {e})")
        return None


def _refresh_yahoo(db, ticker: str) -> None:
    """
    Fill the trailing financials Yahoo already caches but nothing ever asked for.

    The cache holds a row for most of these tickers with every financial column
    NULL: only market data was ever refreshed. That is why the second layer of
    the rubric — the one that reaches the Canadian and OTC names — had nothing
    to read.

    Tried across every known listing of the company, canonical first. Yahoo
    answers 404 for `KUYA.V` and `IMP.V` and answers properly for `KUYAF` and
    `ITMSF`, which are the same two companies on the US OTC market — asking
    under the broker's symbol alone would leave two of the five largest
    positions unassessable for no reason but the spelling.
    """
    from app.services.yahoo_cache import YahooFinanceCache

    cache = YahooFinanceCache(db)
    for symbol in variants_of(ticker) or (ticker.upper(),):
        try:
            data = cache.get_stock_data(
                symbol, data_types=["fundamental", "financial"], force_refresh=True
            )
        except Exception as e:  # noqa: BLE001
            print(f"    (Yahoo {symbol}: {type(e).__name__}: {e})")
            continue
        if data and data.get("profit_margin") is not None:
            return


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticker", help="jen jedna firma")
    parser.add_argument(
        "--refresh-yahoo", action="store_true",
        help="stáhnout roční souhrny pro firmy mimo dosah SEC",
    )
    parser.add_argument("--quiet", action="store_true", help="bez výpisu důkazů")
    args = parser.parse_args()

    initialize_database(get_settings().database_url)
    today = datetime.now(timezone.utc).date()

    with session_scope() as db:
        if args.ticker:
            tickers = [args.ticker.upper()]
        else:
            tickers = sorted(
                t for (t,) in db.query(Position.ticker)
                .filter(Position.shares_count > 0)
                .distinct()
            )

        proposed = 0
        for ticker in tickers:
            covered = is_sec_covered(db, ticker)
            if args.refresh_yahoo and not covered:
                _refresh_yahoo(db, ticker)

            result = propose(
                db, ticker,
                fundamentals=_fundamentals(db, ticker) if covered else None,
                as_of=today,
            )
            if result.cylinders is not None:
                proposed += 1

            print(f"\n{result.summary_cs()}")
            if args.quiet:
                continue

            for item in result.evidence:
                sign = f"{item.delta:+d}" if item.delta else " 0"
                print(f"    {sign}  {item.fact_cs}  [{item.source}]")
            for gap in result.unknowns:
                print(f"    ??  {gap}")

        print(
            f"\n{proposed} z {len(tickers)} firem má návrh. "
            f"Nic není potvrzené — potvrzení je samostatný krok a teprve to "
            f"odemyká nákupy."
        )
        db.commit()   # only the Yahoo refresh writes anything

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
