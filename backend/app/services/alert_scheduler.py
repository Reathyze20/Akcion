"""
The clock behind away mode.

What this used to be
--------------------
A second opinion with a mailing list. Every thirty minutes it asked
`master_signal` for "high-confidence opportunities" and mailed them out with an
entry price, a target and a stop — none of which had passed the Buy Guard, the
cylinder check, the market semafor, the per-account caps, the pacing rules or
the concentration check. It was the rival engine at its most dangerous, because
it was the only one that reached a phone.

It also never worked. `check_and_send_alerts` called
`get_top_opportunities_v2(db=…, min_confidence=…, limit=10)` while that function
required a `tickers` argument and accepted no `limit`, so every single run
raised `TypeError` into the loop's `except Exception` and logged a failure
nobody read. Not one alert was ever sent.

What it is now
--------------
A clock. It runs one away-mode cycle, which is the app's single disciplined push
path: one engine, a 24-hour quiet period, no BUY while nobody is watching, and
silence that is recorded as a decision rather than as nothing happening.

It sends only while away mode is switched on. With away mode off `run_cycle`
returns without touching a channel, which is why this can run every half hour
without becoming noise.
"""

import asyncio
import logging
import os
from datetime import datetime, time

from app.database.connection import session_scope


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ==============================================================================
# Configuration
# ==============================================================================

CHECK_INTERVAL_MINUTES = int(os.getenv('ALERT_CHECK_INTERVAL', '30'))

#: Waking hours, not market hours. Away mode's own 24-hour quiet period decides
#: how often anything leaves; this only decides that it never leaves at four in
#: the morning. The old name said "market" and the numbers said otherwise —
#: 9-16 local time is mostly before the US open.
WAKING_START_HOUR = 8
WAKING_END_HOUR = 21


# ==============================================================================
# Scheduler
# ==============================================================================

def is_waking_hours() -> bool:
    """Whether a message sent now would be read rather than slept through."""
    now = datetime.now().time()
    return time(WAKING_START_HOUR, 0) <= now <= time(WAKING_END_HOUR, 0)


def _deliver(subject: str, body: str) -> bool:
    """
    Put one away-mode message on a channel. Returns whether it actually left.

    False rather than an exception, deliberately: a failed send must leave the
    quiet period unstarted so the next cycle tries again instead of swallowing
    the message. Same contract as `scripts/away_check.py`.
    """
    from app.services.notifications import Alert, NotificationService

    service = NotificationService.from_env()
    if not service.channels:
        logger.warning(
            "Away mode chce něco poslat, ale není nastavený žádný kanál: %s",
            "; ".join(service.unconfigured),
        )
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
        logger.error("Odeslání selhalo: %s: %s", type(e).__name__, e)
        return False
    return any(results.values())


async def run_alert_check():
    """
    One away-mode pass.

    Does nothing at all unless away mode is on: `run_away_cycle` reads the
    switch first and returns without touching a channel when it is off. That is
    the whole reason this can run on a half-hour clock — the decision about
    whether the owner wants to hear from the app is theirs, made once, not
    re-litigated by a confidence threshold every cycle.
    """
    # Imported here, not at module scope: the route pulls in the whole engine
    # and this module is also a __main__ entry point.
    from app.routes.away import run_away_cycle

    try:
        with session_scope() as db:
            result = run_away_cycle(db, send=True, notify=_deliver)

        if not result.away:
            logger.debug("Away mode je vypnutý, neposílám nic")
        elif result.sent:
            logger.info("Odesláno: %s", result.subject)
        else:
            logger.info("Away mode mlčí: %s", result.reason)

    except Exception as e:
        logger.error("Away cyklus selhal: %s", e, exc_info=True)


async def scheduler_loop():
    """The clock. Away mode decides whether anything leaves."""
    logger.info("Away heartbeat spuštěn")
    logger.info("Interval: %d min", CHECK_INTERVAL_MINUTES)
    logger.info("Bdělé hodiny: %d:00 - %d:00", WAKING_START_HOUR, WAKING_END_HOUR)
    
    while True:
        try:
            # Only run during market hours
            if is_waking_hours():
                await run_alert_check()
            else:
                logger.debug("Mimo bdělé hodiny, nekontroluji")
            
            # Wait for next interval
            await asyncio.sleep(CHECK_INTERVAL_MINUTES * 60)
            
        except KeyboardInterrupt:
            logger.info("Scheduler stopped by user")
            break
        except Exception as e:
            logger.error(f"Scheduler error: {e}", exc_info=True)
            await asyncio.sleep(60)  # Wait 1 minute before retrying


# ==============================================================================
# Entry Point
# ==============================================================================

# Global scheduler task
_scheduler_task: asyncio.Task | None = None


async def start_scheduler() -> None:
    """
    Start the background alert scheduler.
    
    Called on application startup to begin monitoring watchlist.
    """
    global _scheduler_task
    
    if _scheduler_task is not None and not _scheduler_task.done():
        logger.warning("Scheduler already running")
        return
    
    _scheduler_task = asyncio.create_task(scheduler_loop())
    logger.info("Alert scheduler started as background task")


async def stop_scheduler() -> None:
    """
    Stop the background alert scheduler.
    
    Called on application shutdown for graceful cleanup.
    """
    global _scheduler_task
    
    if _scheduler_task is None:
        logger.warning("Scheduler not running")
        return
    
    _scheduler_task.cancel()
    try:
        await _scheduler_task
    except asyncio.CancelledError:
        pass
    
    _scheduler_task = None
    logger.info("Alert scheduler stopped")


if __name__ == "__main__":
    asyncio.run(scheduler_loop())
