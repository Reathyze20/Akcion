"""
One read of the Gomes tracker, from outside the app.

Why this job matters more than the Breakout one
-----------------------------------------------
riskrewardcharts.com is where the Green and Red Lines live, and those two
numbers are the input every band, every deserved comparison, every 3-point
trigger and every outstanding instruction is computed from
(docs/GOMES_METHODOLOGY_CANON.md §4a). `tracker_sync` existed and was tested
from 2026-07-26 and nothing ever called it, so the columns it fills stayed
empty and the whole decision engine ran over nothing.

The canon says these lines are NOT real-time and change rarely. That is
precisely why a change is worth a message: when a line moves, the analyst has
revalued the company, and everything the app said about it until that moment
was measured against a band that no longer exists. A pick flipping
OFFICIAL <-> NOT OFFICIAL is bigger still — it means he moved real money.

Scheduling
----------
Windows Task Scheduler, pointed at `scripts/tracker_poll.cmd` (which adds a
log), daily. Same shape as the other two jobs:

    Get-ScheduledTaskInfo    -TaskName "Akcion - tracker Gomes"  # last result
    Start-ScheduledTask      -TaskName "Akcion - tracker Gomes"  # run it now
    Unregister-ScheduledTask -TaskName "Akcion - tracker Gomes"  # remove it

Log: backend/logs/tracker_poll.log

The hour does not matter: the lines move on the order of weeks and a missed day
costs nothing, because the diff is against whatever was last stored rather than
against yesterday specifically. Running it twice in a day is harmless and does
nothing — `MIN_POLL_INTERVAL` (12 h) is enforced in code, not by the schedule.

    --dry-run   read, diff, print; write nothing and send nothing
    --force     read even if the interval has not elapsed
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
from app.models.tracker import TrackerLineChange  # noqa: E402
from app.services.tracker_sync import (  # noqa: E402
    STATUS_SYNCED,
    STATUS_TOO_SOON,
    sync_tracker,
)

#: How urgent each kind of change is, in plain Czech. The order is the order
#: they are listed in: a pick entering or leaving the real portfolio outranks a
#: revaluation, which outranks a name appearing on the watch side.
_KIND_LABEL = {
    "PICK_TYPE": "portfolio",
    "LINE_MOVED": "přecenění",
    "NEW_PICK": "nový",
    "REMOVED": "zmizel",
}
_KIND_ORDER = {"PICK_TYPE": 0, "LINE_MOVED": 1, "REMOVED": 2, "NEW_PICK": 3}


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
        signal_strength="TRACKER",
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


def _compose(rows: list[TrackerLineChange]) -> tuple[str, str]:
    """
    Subject and body for the changes worth sending.

    The body is the stored Czech sentence per change — written once in
    `diff_tracker`, so the mail and the screen say the same thing rather than
    two paraphrases of it.
    """
    ordered = sorted(rows, key=lambda r: (_KIND_ORDER.get(r.kind, 9), r.ticker))
    moved = [r for r in ordered if r.kind in ("LINE_MOVED", "PICK_TYPE")]

    subject = (
        f"Gomes tracker: {len(moved)} přeceněno"
        if moved
        else f"Gomes tracker: {len(ordered)} změn"
    )

    lines = ["Změny na Gomesových Risk/Reward grafech:", ""]
    for row in ordered:
        lines.append(f"  [{_KIND_LABEL.get(row.kind, row.kind)}] {row.detail_cs}")
    lines += [
        "",
        "Posunutá čára znamená, že analytik firmu přecenil — každé skóre",
        "spočítané do téhle chvíle stálo na starém pásmu. Zkontroluj v aplikaci,",
        "jestli se tím nezměnil pokyn.",
    ]
    return subject, "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true", help="přečíst a vypsat, nic nezapsat"
    )
    parser.add_argument(
        "--force", action="store_true", help="číst i před uplynutím intervalu"
    )
    parser.add_argument(
        "--quiet", action="store_true", help="změny zapsat, zprávu neposílat"
    )
    args = parser.parse_args()

    initialize_database(get_settings().database_url)

    # Before the tracker read, not after: the tracker has several early exits
    # (nothing changed, read too recently, source down) and the semafor check
    # is independent of all of them. Behind the last one it simply never ran.
    if not args.dry_run:
        _tighten_semafor()
        _refresh_earnings()

    with session_scope() as db:
        report = sync_tracker(db, force=args.force or args.dry_run)

        if report.status == STATUS_TOO_SOON:
            print("Tracker byl čten před méně než 12 hodinami — nečte se znovu.")
            db.rollback()
            return 0

        if report.status != STATUS_SYNCED:
            print(f"Tracker nedostupný: {report.error}")
            # The attempt itself IS recorded, so an outage does not turn into a
            # retry loop against someone else's server.
            if args.dry_run:
                db.rollback()
            else:
                db.commit()
            return 0

        print(report.summary_cs())
        for change in report.changes:
            print(f"  {change.detail}")

        if args.dry_run:
            db.rollback()
            return 0

        db.flush()
        unsent = (
            db.query(TrackerLineChange)
            .filter(TrackerLineChange.notified_at.is_(None))
            .order_by(TrackerLineChange.detected_at)
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

        subject, body = _compose(unsent)
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


def _tighten_semafor() -> None:
    """
    Let the long-term chart make the app more careful, if it says to.

    Runs on the same daily heartbeat as the tracker read because it answers the
    same kind of question — has the ground moved since we last looked — and
    because a third scheduled task is a third thing that can quietly stop
    running.

    Only ever tightens. See `app/services/market_watch.py`: this measure misses
    the 2007 top entirely, so it has not earned the right to sound an
    all-clear, but a semafor left stale for a fortnight disarms every purchase
    rule in the app exactly during the weeks nobody is at the keyboard.
    """
    from app.services.market_watch import APPLIED, apply_gauge

    try:
        with session_scope() as db:
            result = apply_gauge(db)
            if result.status == APPLIED:
                print(result.message_cs)
            else:
                print(f"Semafor beze změny: {result.message_cs}")
    except Exception as e:  # noqa: BLE001 — the tracker read already succeeded
        print(f"Kontrola semaforu selhala: {type(e).__name__}: {e}")


def _refresh_earnings() -> None:
    """
    Find out when each held company reports next.

    On the daily heartbeat because the canon's blackout rule needs a date and
    has never had one, and because the dates themselves move on the order of
    weeks — `REFRESH_AFTER` skips anything read in the last few days, so this
    is one network call per company every third run rather than every night.

    Never raises: the tracker read has already succeeded by this point and a
    missing earnings date must not undo it.
    """
    from app.models.portfolio import Position
    from app.services.earnings_calendar import describe, refresh

    try:
        with session_scope() as db:
            tickers = [
                t for (t,) in db.query(Position.ticker)
                .filter(Position.shares_count > 0)
                .distinct()
            ]
            touched = refresh(db, tickers)
            db.commit()
            if touched:
                print(f"Data výsledků: {len(touched)} firem aktualizováno")
                for row in touched:
                    print(f"  {row.ticker}: {describe(row)}")
            else:
                print("Data výsledků jsou čerstvá, nečtu znovu.")
    except Exception as e:  # noqa: BLE001 — see docstring
        print(f"Data výsledků selhala: {type(e).__name__}: {e}")


if __name__ == "__main__":
    raise SystemExit(main())
