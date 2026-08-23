"""
Analyse SEC filings without spending API credit.

The backend reads a newly filed report on its own, through the Anthropic API,
because a server has no other way to do it — a Claude subscription authenticates
a person in a client, not a process on a box. That path is deliberately small:
one call per ticker for the newest filing nobody has read yet.

A *backfill* is the opposite shape. Re-reading every holding after a prompt
change is dozens of long documents at once, and there is no reason to buy that
through the API when a Claude Code session is already open and covered by the
subscription. So this splits the job in two:

    python scripts/sec_backfill.py export [TICKER ...]

writes each unanalysed filing to `.sec_backfill/<TICKER>_<FORM>_<DATE>.txt`,
exactly the text the model would have been sent — exhibits included, so a 6-K
carries its EX-99 rather than its cover page.

    python scripts/sec_backfill.py import

reads `<same name>.summary.md` back and stores it as that filing's analysis.
A filing whose summary file is missing is left NULL, not blanked: "nobody has
read this yet" and "read, nothing notable" have to stay distinguishable, and
this script is not allowed to blur them either.

    python scripts/sec_backfill.py status

lists what is analysed, what is waiting, and what has been exported but not
yet written back.
"""

from __future__ import annotations

import argparse
import os
import pathlib
import re
import sys
from datetime import datetime, timezone

BACKEND = pathlib.Path(__file__).resolve().parent.parent
os.chdir(BACKEND)  # Settings reads .env relative to the working directory
sys.path.insert(0, str(BACKEND))

from app.config.settings import get_settings  # noqa: E402
from app.database.connection import initialize_database, session_scope  # noqa: E402
import app.models.trading  # noqa: F401,E402  — SQLAlchemy needs every mapper
from app.models.sec import SecFiling  # noqa: E402
from app.services.sec_edgar import SecEdgarClient  # noqa: E402
from app.services.sec_sync import read_filing  # noqa: E402

#: Kept out of the repo — these are megabytes of regulator prose, and they are
#: reproducible from EDGAR at any time.
EXPORT_DIR = BACKEND / ".sec_backfill"

#: What the session is being asked to produce. Deliberately the same shape
#: `format_outlook` renders, so exported and API-written summaries read alike.
INSTRUCTIONS = """<!--
Přečti text podání v souboru .txt vedle tohoto a napiš sem souhrn v češtině.
Struktura (vynech sekci, pro kterou v podání nic není — a napiš to):

**Varovné signály:**
  🔴 / 🟠 / 🟡 fakt, doslovně podložený textem

**Výhled (zvýšen|snížen|potvrzen|neuveden):** ...
**Objednávky / backlog:** ...
**Provozní fakta (válce):**
  - ...
**Nová/zhoršená rizika:**
  - ...

Poslední odstavec: souvislé shrnutí bez odrážek.

Nic nedomýšlej. Když podání číslo neuvádí, napiš, že ho neuvádí.
-->
"""


def summary_body(text: str) -> str:
    """
    The written part of a summary file, with the instruction block removed.

    Empty means nobody has written anything yet. Storing the template back
    would turn "not read" into "read, nothing to report" — the exact confusion
    every other part of this integration exists to prevent.

    Only a comment *at the top* is removed. Splitting on the first `-->`
    anywhere would eat the opening of any summary whose prose contains an
    arrow, and "Tržby 2Q --> 3Q rostou" is an ordinary thing to write.
    """
    return re.sub(r"\A\s*<!--.*?-->", "", text, count=1, flags=re.S).strip()


def _slug(filing: SecFiling) -> str:
    form = filing.form.replace("/", "-")
    return f"{filing.ticker}_{form}_{filing.filed_date}"


def _pending(db, tickers: list[str]) -> list[SecFiling]:
    query = db.query(SecFiling).filter(SecFiling.analysis.is_(None))
    if tickers:
        query = query.filter(SecFiling.ticker.in_([t.upper() for t in tickers]))
    return query.order_by(SecFiling.ticker, SecFiling.filed_date.desc()).all()


def do_export(tickers: list[str], *, newest_only: bool) -> int:
    """Fetch each unanalysed filing's full text to a file. No model involved."""
    EXPORT_DIR.mkdir(exist_ok=True)
    client = SecEdgarClient()
    written = 0

    with session_scope() as db:
        filings = _pending(db, tickers)
        if newest_only:
            seen: set[str] = set()
            filings = [
                f for f in filings
                if f.ticker not in seen and not seen.add(f.ticker)
            ]

        if not filings:
            print("Nic k exportu — všechna podání už mají analýzu.")
            return 0

        for filing in filings:
            source = read_filing(
                client,
                url=filing.url,
                form=filing.form,
                cik=filing.cik,
                accession=filing.accession,
            )
            if source is None:
                print(f"{_slug(filing)}: nelze stáhnout, přeskakuji")
                continue

            body = EXPORT_DIR / f"{_slug(filing)}.txt"
            header = (
                f"# {filing.ticker} {filing.form} podáno {filing.filed_date}\n"
                f"# období: {filing.period_date or 'neuvedeno'}\n"
                f"# zdroje: {', '.join(source.sources)}\n"
                f"# {filing.url}\n"
            )
            if source.thin_note:
                header += f"# POZOR: {source.thin_note}\n"
            if source.truncated:
                header += "# POZOR: text byl zkrácen, konec podání chybí\n"
            body.write_text(header + "\n" + source.text, encoding="utf-8")

            summary = EXPORT_DIR / f"{_slug(filing)}.summary.md"
            if not summary.exists():
                summary.write_text(INSTRUCTIONS, encoding="utf-8")

            print(f"{_slug(filing)}: {len(source.text):>7} znaků  "
                  f"({', '.join(source.sources)})")
            written += 1

    print(f"\nHotovo: {written} podání v {EXPORT_DIR}")
    print("Napiš souhrny do souborů .summary.md, pak spusť: "
          "python scripts/sec_backfill.py import")
    return written


def do_import() -> int:
    """Store hand-written summaries. A missing one leaves the filing NULL."""
    if not EXPORT_DIR.exists():
        print(f"{EXPORT_DIR} neexistuje — nejdřív spusť export.")
        return 0

    stored = 0
    with session_scope() as db:
        for filing in _pending(db, []):
            summary_file = EXPORT_DIR / f"{_slug(filing)}.summary.md"
            if not summary_file.exists():
                continue

            without_comment = summary_body(
                summary_file.read_text(encoding="utf-8")
            )
            if not without_comment:
                print(f"{_slug(filing)}: souhrn je prázdný, nechávám neanalyzované")
                continue

            filing.analysis = without_comment
            filing.analyzed_at = datetime.now(timezone.utc)
            stored += 1
            print(f"{_slug(filing)}: uloženo ({len(without_comment)} znaků)")
        db.commit()

    print(f"\nUloženo {stored} souhrnů.")
    return stored


def do_status() -> None:
    by_ticker: dict[str, list[tuple[str, bool]]] = {}

    # Read everything inside the session: a row read after it closes raises
    # DetachedInstanceError on the first lazy attribute.
    with session_scope() as db:
        for row in (db.query(SecFiling)
                      .order_by(SecFiling.ticker, SecFiling.filed_date.desc())):
            by_ticker.setdefault(row.ticker, []).append(
                (_slug(row), bool(row.analysis))
            )

    for ticker, filings in sorted(by_ticker.items()):
        done = sum(1 for _, analysed in filings if analysed)
        waiting = [slug for slug, analysed in filings if not analysed]
        exported = sum(
            1 for slug in waiting if (EXPORT_DIR / f"{slug}.txt").exists()
        )
        note = f"{done}/{len(filings)} analyzováno"
        if waiting:
            note += f", čeká {len(waiting)}"
        if exported:
            note += f" (z toho {exported} vyexportováno)"
        print(f"{ticker:12} {note}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    export = sub.add_parser("export", help="stáhnout texty nepřečtených podání")
    export.add_argument("tickers", nargs="*", help="omezit na tyto tickery")
    export.add_argument("--newest-only", action="store_true",
                        help="jen nejnovější nepřečtené podání na ticker")

    sub.add_parser("import", help="uložit ručně napsané souhrny do DB")
    sub.add_parser("status", help="co je analyzované a co čeká")

    args = parser.parse_args()
    initialize_database(get_settings().database_url)

    if args.command == "export":
        do_export(args.tickers, newest_only=args.newest_only)
    elif args.command == "import":
        do_import()
    else:
        do_status()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
