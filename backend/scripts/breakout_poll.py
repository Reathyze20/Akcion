"""
One read of the Breakout Investors watchlist, from outside the app.

Reads the source at most once a day, records what moved, and sends a message
only when something actually did. A daily list of twenty-eight unchanged names
trains you to stop opening the mail; a line saying a name you own gained two
endorsements does not.

Scheduling
----------
Windows Task Scheduler, pointed at `scripts/breakout_poll.cmd` (which adds a
log), daily. Same shape as the score evaluation job:

    Get-ScheduledTaskInfo    -TaskName "Akcion - watchlist Breakout"  # last result
    Start-ScheduledTask      -TaskName "Akcion - watchlist Breakout"  # run it now
    Unregister-ScheduledTask -TaskName "Akcion - watchlist Breakout"  # remove it

Log: backend/logs/breakout_poll.log

The hour does not matter much — their list moves on the order of weeks — but
an evening run pairs the message with the day's other mail rather than waking
you with it. A missed day costs nothing: the diff is against whatever was last
stored, not against yesterday specifically.

Running it twice in one day is harmless and does nothing: `MIN_POLL_INTERVAL`
(20 h) is enforced in code, not by the schedule. `--force` overrides it, and
exists for the first run and for checking a change by hand — not for a loop.

    --dry-run   read, diff, print; write nothing and send nothing
    --force     read even if the daily interval has not elapsed
    --quiet     record changes but send no message
"""

from __future__ import annotations

import argparse
import asyncio
import os
import pathlib
import sys

BACKEND = pathlib.Path(__file__).resolve().parent.parent
os.chdir(BACKEND)  # Settings reads .env relative to the working directory
sys.path.insert(0, str(BACKEND))

# The Windows console this runs on is cp1250. Anything outside that page takes
# the whole run down with UnicodeEncodeError, which is a poor way for a
# scheduled job to fail.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

from datetime import datetime, timezone  # noqa: E402

from app.config.settings import get_settings  # noqa: E402
from app.database.connection import initialize_database, session_scope  # noqa: E402
import app.models  # noqa: F401,E402  — SQLAlchemy needs every mapper
import app.models.trading  # noqa: F401,E402
from app.models.breakout import BreakoutWatchChange  # noqa: E402
from app.services.breakout_sync import (  # noqa: E402
    RELATION_OWNED,
    RELATION_THEIRS,
    RELATION_WATCHED,
    STATUS_SYNCED,
    STATUS_TOO_SOON,
    our_symbols,
    sync_watchlist,
)

#: Prefix per relation. A change to a name you hold is not the same news as a
#: change to one of their twenty-eight, and the message has to say which.
_RELATION_LABEL = {
    RELATION_OWNED: "držíme",
    RELATION_WATCHED: "sledujeme",
    RELATION_THEIRS: "jejich",
}


def _send(subject: str, body: str) -> bool:
    """
    Deliver one message. Returns whether it actually left.

    False rather than an exception: a failed send must leave the changes
    unmarked so the next run tries again, instead of losing them silently.
    """
    from app.services.notifications import Alert, NotificationService

    service = NotificationService.from_env()
    if not service.channels:
        print("Žádný kanál není nastavený — zpráva nemá kudy odejít.")
        return False

    alert = Alert(
        ticker=subject,
        buy_confidence=0.0,
        signal_strength="BREAKOUT",
        entry_price=None,
        target_price=None,
        stop_loss=None,
        kelly_size=None,
        message=body,
    )
    try:
        results = asyncio.run(service.send_alert(alert))
    except Exception as e:  # noqa: BLE001 — a channel failing is not a crash
        print(f"Odeslání selhalo: {type(e).__name__}: {e}")
        return False
    return any(results.values())


def _compose(rows: list[BreakoutWatchChange], relations: dict[str, str]) -> tuple[str, str]:
    """
    Subject and body for the changes worth sending.

    Ours first, then theirs. The body is the stored Czech sentence per change —
    written once in `diff_watchlist`, so the mail and the screen say the same
    thing rather than two paraphrases of it.
    """
    ordered = sorted(
        rows,
        key=lambda r: (
            {RELATION_OWNED: 0, RELATION_WATCHED: 1}.get(
                relations.get(r.symbol, RELATION_THEIRS), 2
            ),
            r.symbol,
        ),
    )

    ours = [r for r in ordered if relations.get(r.symbol, RELATION_THEIRS) != RELATION_THEIRS]
    subject = (
        f"Breakout Investors: {len(ours)} změn u našich jmen"
        if ours
        else f"Breakout Investors: {len(ordered)} změn na jejich watchlistu"
    )

    lines = ["Změny na watchlistu Breakout Investors:", ""]
    for row in ordered:
        label = _RELATION_LABEL[relations.get(row.symbol, RELATION_THEIRS)]
        lines.append(f"  [{label}] {row.detail_cs}")
    lines += [
        "",
        "Jsou to jejich čísla, ne pokyn. Strop pozice se tím nemění —",
        "porovnání s Gomesovými čárami je v aplikaci v odrážce Breakout.",
    ]
    return subject, "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true", help="přečíst a vypsat, nic nezapsat"
    )
    parser.add_argument(
        "--force", action="store_true", help="číst i před uplynutím denního intervalu"
    )
    parser.add_argument(
        "--quiet", action="store_true", help="změny zapsat, zprávu neposílat"
    )
    args = parser.parse_args()

    initialize_database(get_settings().database_url)

    with session_scope() as db:
        result = sync_watchlist(db, force=args.force or args.dry_run)

        if result.status == STATUS_TOO_SOON:
            print("Zdroj byl čten před méně než 20 hodinami — nečte se znovu.")
            db.rollback()
            return 0

        if result.status != STATUS_SYNCED:
            print(f"Zdroj nedostupný: {result.error}")
            # The attempt itself IS recorded, so an outage does not turn into a
            # retry loop against someone else's server.
            if args.dry_run:
                db.rollback()
            else:
                db.commit()
            return 0

        print(f"Načteno {result.entries_read} jmen, {len(result.changes)} změn.")
        for change in result.changes:
            print(f"  {change.detail_cs}")

        if args.dry_run:
            db.rollback()
            return 0

        db.flush()
        relations = our_symbols(db)
        unsent = (
            db.query(BreakoutWatchChange)
            .filter(BreakoutWatchChange.notified_at.is_(None))
            .order_by(BreakoutWatchChange.detected_at)
            .all()
        )

        if not unsent:
            print("Nic nového k odeslání.")
            db.commit()
            return 0

        if args.quiet:
            print(f"{len(unsent)} změn zapsáno, zpráva se neposílá (--quiet).")
            db.commit()
            return 0

        subject, body = _compose(unsent, relations)
        if _send(subject, body):
            stamp = datetime.now(timezone.utc)
            for row in unsent:
                row.notified_at = stamp
            print(f"Odesláno: {subject}")
        else:
            # Left unmarked on purpose — the next run picks them up again.
            print("Zpráva neodešla, změny zůstávají neoznámené.")

        db.commit()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
