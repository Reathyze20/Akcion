"""
Running one away-mode cycle: read the state, build the digest, send at most one.

`away_mode` is the policy and stays pure. This is the part that touches the
database and the notification channel, kept separate so the rules above can be
tested without either.

The semafor escalation is applied by the caller rather than inside
`generate_daily_actions`, because it is not a rule of the method — the canon's
blocked-tier table is used unchanged, just against a semafor one step further
toward defence. The normal daily list must not quietly acquire it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.away import AwayModeState
from app.schemas.daily_actions import ActionItem
from app.services.away_mode import AwayState, build_digest


@dataclass
class CycleResult:
    """What one cycle did, ready to render or log."""

    away: bool
    sent: bool
    reason: str
    subject: str | None = None
    body: str | None = None
    held: list[str] | None = None


def get_state(db: Session) -> AwayModeState:
    """The single away-mode row, created on first use."""
    row = db.query(AwayModeState).order_by(AwayModeState.id).first()
    if row is None:
        row = AwayModeState(is_away=False, last_push_urgency=0)
        db.add(row)
        db.flush()
    return row


def _naive(value: datetime | None) -> datetime | None:
    """
    Postgres hands back tz-aware datetimes; the action engine works in naive
    UTC. Comparing the two raises, and a raise here means no message at all.
    """
    if value is None:
        return None
    return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value


def oldest_price_update(positions: list, tickers: set[str]) -> datetime | None:
    """
    The stalest price behind the given tickers.

    The oldest, not the newest: a digest is only as current as its weakest
    input, and one refreshed position does not make a week-old one usable.
    None when any of them has no timestamp at all — that is "we do not know",
    which away mode treats as too old.
    """
    stamps: list[datetime] = []
    for pos in positions:
        if pos.ticker.upper() not in tickers:
            continue
        stamp = _naive(pos.last_price_update)
        if stamp is None:
            return None
        stamps.append(stamp)
    return min(stamps) if stamps else None


def run_cycle(
    db: Session,
    *,
    actions: list[ActionItem],
    positions: list,
    now: datetime | None = None,
    send: bool = True,
    notify=None,
    notes: list[str] | None = None,
) -> CycleResult:
    """
    One away-mode pass.

    `actions` are the ranked daily actions, ranked as the engine produced them.
    `notify` is called with (subject, body) and returns True when the message
    left; the default sends nothing, which is what tests and dry runs want.

    `notes` are the reasons away mode may have had *nothing* to say — chiefly
    that it could not judge the positions at all. They are stored with the
    decision rather than pushed, because after a week of silence "there was
    nothing to send" and "I could not read any of your holdings" are very
    different things to come back to, and only one of them is good news.
    """
    now = now or datetime.utcnow()
    row = get_state(db)

    state = AwayState(
        is_away=bool(row.is_away),
        since=_naive(row.since),
        until=_naive(row.until),
    )
    if not state.active_at(now):
        return CycleResult(
            away=False, sent=False,
            reason="Away mode je vypnutý — běží normální denní seznam.",
        )

    tickers = {a.ticker.upper() for a in actions}
    digest = build_digest(
        actions,
        price_as_of=oldest_price_update(positions, tickers),
        now=now,
        last_push_at=_naive(row.last_push_at),
        last_push_urgency=row.last_push_urgency or 0,
    )

    if not digest.send:
        reason = _with_notes(digest.reason, notes)
        row.last_digest_reason = reason
        return CycleResult(
            away=True, sent=False, reason=reason, held=digest.held,
        )

    delivered = True
    if send:
        delivered = bool(notify and notify(digest.subject, digest.body))

    # The quiet period only starts when something actually left. A failed send
    # that still marked the channel quiet would swallow the message entirely.
    if delivered:
        row.last_push_at = now
        row.last_push_urgency = digest.urgency
        row.last_push_subject = digest.subject
    row.last_digest_reason = digest.reason if delivered else (
        f"{digest.reason} — odeslání selhalo, zkusí se znovu."
    )

    return CycleResult(
        away=True,
        sent=delivered,
        reason=row.last_digest_reason,
        subject=digest.subject,
        body=digest.body,
        held=digest.held,
    )


def _with_notes(reason: str, notes: list[str] | None) -> str:
    """Append the blind spots to a decision, so silence stays legible."""
    if not notes:
        return reason
    return reason + " " + " ".join(notes)


def summarize(result: CycleResult) -> str:
    """One line for a log or a console."""
    if not result.away:
        return "away mode vypnutý"
    if result.sent:
        return f"odesláno: {result.subject}"
    return f"neodesláno: {result.reason}"


__all__ = [
    "CycleResult",
    "get_state",
    "oldest_price_update",
    "run_cycle",
    "summarize",
]
