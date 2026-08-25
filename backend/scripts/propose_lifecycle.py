"""
Propose a lifecycle stage for every held position, and print the evidence.

Why this exists
---------------
On 2026-08-24 all twelve holdings carried `phase = UNKNOWN`. That capped every
one of them at the strictest tier and left the de-risking branch unable to sell
anything at all in a yellow market — safe, and blind.

The stage cannot be guessed from conviction; that was tried and the app nearly
sold its highest-conviction holding. So it is proposed from dated facts and
confirmed by a person, exactly as the cylinder count is.

Why a script rather than a button
---------------------------------
The proposal needs audited quarterly numbers from SEC XBRL — one HTTP call per
company, rate-limited by regulation — and doing that inside a request would make
the screen wait on somebody else's server. This runs on demand, prints what it
found, and **writes nothing** unless asked.

    --confirm         write the proposals the rubric is confident about
    --ticker XYZ      one company instead of the whole portfolio
    --quiet           the verdicts only, without the evidence behind them
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
from app.services.lifecycle_intake import confirm, propose  # noqa: E402
from app.services.lifecycle_rubric import (  # noqa: E402
    CONFIDENCE_LOW,
    PHASE_MEANING_CS,
    PHASE_NAMES_CS,
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticker", help="jen jedna firma")
    parser.add_argument(
        "--confirm", action="store_true",
        help="zapsat návrhy, u kterých si je rubrika jistá (nikdy ty s nízkou jistotou)",
    )
    parser.add_argument("--quiet", action="store_true", help="jen verdikty")
    parser.add_argument(
        "--by", default="Tomas", help="kdo potvrzuje (zapíše se k záznamu)"
    )
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

        proposed = 0
        written = 0
        for ticker in tickers:
            proposal = propose(db, ticker, fundamentals=_fundamentals(db, ticker))

            if proposal.phase is None:
                print(f"\n{ticker}: bez návrhu")
                for gap in proposal.unknowns:
                    print(f"    ? {gap}")
                continue

            proposed += 1
            name = PHASE_NAMES_CS[proposal.phase]
            print(
                f"\n{ticker}: {name.upper()} "
                f"(jistota {proposal.confidence}, vrstva {proposal.layer})"
            )
            print(f"    {PHASE_MEANING_CS[proposal.phase]}")

            if not args.quiet:
                for signal in proposal.signals:
                    arrow = PHASE_NAMES_CS[signal.towards]
                    print(f"    +{signal.weight} → {arrow}: {signal.fact_cs}")
                for gap in proposal.unknowns:
                    print(f"    ? {gap}")

            # Low confidence is never written without a person looking. That is
            # every Great Find by construction: half its definition is that
            # nobody has heard of the company, and this app measures no such
            # thing.
            if args.confirm and proposal.confidence != CONFIDENCE_LOW:
                confirm(
                    db, ticker, proposal.phase,
                    confirmed_by=args.by, proposal=proposal,
                )
                written += 1
                print("    → zapsáno")
            elif args.confirm:
                print("    → NEzapsáno: nízká jistota, tohle potvrď sám")

        if args.confirm:
            db.commit()
            print(f"\nZapsáno {written} z {proposed} návrhů.")
        else:
            db.rollback()
            print(f"\n{proposed} návrhů z {len(tickers)} pozic. Nic se nezapsalo.")
            print("Zápis: znovu s --confirm")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
