"""
Sedi to k Markovi? -- kandidat proti jeho skutecnym vstupum.

Vezme ticker, spocita, jak dnes vypada jeho graf, a rekne, jestli to je tvar,
do ktereho Mark Gomes vstupuje. Nevydava verdikt a nikdy nebude: sedm vlastnosti
tady je vsechno, co je v CENE, a co Marka doopravdy rozhoduje -- mluvil s
vedenim, precetl 10-Q -- v tom listu neni.

    python scripts/gomes_fit.py --ticker CVV
    python scripts/gomes_fit.py --portfolio
    python scripts/gomes_fit.py --scan
    python scripts/gomes_fit.py --ticker CVV --json

--portfolio  kazda drzena pozice: ktera z nich nevypada jako nic, do ceho kdy vstoupil
--scan       jmena z Markova trackeru (NOT OFFICIAL) a watchlistu Breakoutu,
             serazena podle toho, jak moc pripominaji jeho vstup

Referencni profil vyrabi `python -m research.publish` a je commitnuty v
backend/app/data/gomes_entry_profile.json.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
from datetime import date

BACKEND = pathlib.Path(__file__).resolve().parent.parent
os.chdir(BACKEND)  # Settings reads .env relative to the working directory
sys.path.insert(0, str(BACKEND))

# The Windows console this runs on is cp1250. Replace rather than crash.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

from app.services.gomes_fit import (  # noqa: E402
    FitError,
    fit_candidate,
    gauge_z,
    load_profile,
    render_cs,
)


def _held_tickers() -> list[str]:
    from app.config.settings import get_settings
    from app.database.connection import initialize_database, session_scope
    # Both imports, as scripts/evaluate_scores.py does: app.models leaves
    # app.models.trading out (it is commented off in its __init__), and
    # SWOTAnalysis still declares a relationship to ActiveWatchlist, so the
    # mapper configuration fails without the second line.
    import app.models  # noqa: F401 — SQLAlchemy needs every mapper
    import app.models.trading  # noqa: F401
    from app.models.portfolio import Position

    initialize_database(get_settings().database_url)
    with session_scope() as db:
        return sorted({p.ticker for p in db.query(Position).all() if p.ticker})


def _watchlist_tickers() -> list[str]:
    """Names Mark is watching but not holding, plus the Breakout watchlist."""
    from app.config.settings import get_settings
    from app.database.connection import initialize_database, session_scope
    import app.models  # noqa: F401
    import app.models.trading  # noqa: F401
    from app.models.stock import Stock

    initialize_database(get_settings().database_url)
    with session_scope() as db:
        rows = (
            db.query(Stock.ticker)
            .filter(Stock.source_type == "NOT OFFICIAL")
            .distinct()
            .all()
        )
        return sorted({r[0] for r in rows if r[0]})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--ticker", help="jeden kandidat")
    group.add_argument("--portfolio", action="store_true",
                       help="vsechny drzene pozice")
    group.add_argument("--scan", action="store_true",
                       help="sledovana jmena, serazena podle podobnosti")
    parser.add_argument("--json", action="store_true", help="strojovy vystup")
    args = parser.parse_args()

    try:
        profile = load_profile()
    except FitError as exc:
        print(exc)
        return 1

    if args.ticker:
        return _one(args.ticker.upper(), profile, as_json=args.json)

    tickers = _held_tickers() if args.portfolio else _watchlist_tickers()
    if not tickers:
        print("Zadne tickery k proverovani.")
        return 0

    # One index reading for the whole batch: it is the same market for all of
    # them, and asking once is both faster and more consistent.
    market = gauge_z()
    print(f"Prochazim {len(tickers)} symbolu proti {profile.n_rows} Markovym vstupum.\n")

    scored, refused = [], []
    for ticker in tickers:
        try:
            fit = fit_candidate(ticker, profile=profile, market_z=market)
        except FitError as exc:
            refused.append((ticker, str(exc)))
            continue
        scored.append(fit)

    # Fewest features outside his range first. NOT a ranking of quality --
    # it is a ranking of resemblance, and the header says so.
    scored.sort(key=lambda f: (f.count("MIMO"), f.count("NA_OKRAJI")))

    print(f"{'ticker':8s} {'mimo':>5s} {'okraj':>6s} {'typ.':>5s}  nespocitano")
    for fit in scored:
        print(
            f"{fit.ticker:8s} {fit.count('MIMO'):5d} {fit.count('NA_OKRAJI'):6d} "
            f"{fit.count('TYPICKE'):5d}  {len(fit.uncomputable) or ''}"
        )
    if refused:
        print("\nNesly proverit (pojmenovane duvody, ne tise vynechane):")
        for ticker, reason in refused:
            print(f"  {ticker:8s} {reason}")

    print(
        "\nPoradi je podle PODOBNOSTI Markovu vstupu, ne podle kvality firmy."
    )
    return 0


def _one(ticker: str, profile, *, as_json: bool) -> int:
    try:
        fit = fit_candidate(ticker, profile=profile)
    except FitError as exc:
        print(exc)
        return 1

    if as_json:
        print(json.dumps({
            "ticker": fit.ticker,
            "as_of": fit.as_of.isoformat(),
            "profile_n": profile.n_rows,
            "features": [
                {
                    "name": f.name, "value": f.value, "bucket": f.bucket,
                    "median": f.quantiles.median, "below": f.below, "of": f.of,
                }
                for f in fit.fits
            ],
            "uncomputable": list(fit.uncomputable),
            "gauge_cs": fit.gauge_note_cs,
            "neighbours": [
                {
                    "ticker": n.entry.ticker, "entry_date": n.entry.entry_date,
                    "distance": round(n.distance, 4),
                    "sheet_return_pct": n.entry.sheet_return_pct,
                    "note": n.entry.note,
                }
                for n in fit.neighbours
            ],
        }, ensure_ascii=False, indent=2))
        return 0

    print(render_cs(fit))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
