"""
One away-mode cycle, from outside the app.

The scheduler that exists today lives inside the manually started localhost
process: close the app and everything stops. That is precisely backwards for a
feature whose whole purpose is the weeks the app is not opened.

This script needs nothing running. Point Windows Task Scheduler at it:

    python C:\\Users\\reath\\Projects\\Akcion\\backend\\scripts\\away_check.py

every few hours, and away mode works with the app shut. It still needs the
machine on and a working SMTP credential — neither of which code can arrange.

    --dry-run   decide and print, send nothing
    --now ISO   pretend it is a different moment (for checking the rules)
"""

from __future__ import annotations

import argparse
import asyncio
import os
import pathlib
import sys
from datetime import datetime

BACKEND = pathlib.Path(__file__).resolve().parent.parent
os.chdir(BACKEND)  # Settings reads .env relative to the working directory
sys.path.insert(0, str(BACKEND))

from app.config.settings import get_settings  # noqa: E402
from app.database.connection import initialize_database, session_scope  # noqa: E402
import app.models.trading  # noqa: F401,E402  — SQLAlchemy needs every mapper
import app.models.away  # noqa: F401,E402
from app.routes.away import _cycle  # noqa: E402
from app.services.away_runner import summarize  # noqa: E402


def _send(subject: str, body: str) -> bool:
    """
    Deliver one away-mode message. Returns whether it actually left.

    False, not an exception: a failed send must leave the quiet period unstarted
    so the next cycle tries again, rather than swallowing the message.
    """
    from app.services.notifications import Alert, NotificationService

    service = NotificationService.from_env()
    if not service.channels:
        print("Žádný kanál není nastavený — zpráva nemá kudy odejít.")
        return False

    alert = Alert(
        ticker=subject,
        buy_confidence=0.0,
        signal_strength="AWAY",
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="rozhodnout a vypsat, nic neposílat")
    parser.add_argument("--now", help="ISO čas místo teď, pro ověření pravidel")
    args = parser.parse_args()

    moment = datetime.fromisoformat(args.now) if args.now else None
    initialize_database(get_settings().database_url)

    with session_scope() as db:
        result = _cycle(db, send=not args.dry_run, notify=_send, now=moment)
        if args.dry_run:
            db.rollback()
        else:
            db.commit()

    print(summarize(result))
    if result.subject:
        print(f"\n--- {result.subject} ---\n{result.body}")
    for line in (result.held or []):
        print(f"  zadrženo: {line}")

    # 0 whether or not anything was sent — staying quiet is a success.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
