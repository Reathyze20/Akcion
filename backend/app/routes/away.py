"""
Away mode API — the switch, and one dry run of what it would send.

`GET /api/away` answers three questions the UI has to be able to ask apart:
is away mode on, when did anything last leave, and what did the last cycle
decide to hold back. The third one matters most: while away the app is
deliberately quiet, and quiet has to be legible as a decision rather than as
the app having stopped working.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.routes.daily_actions import load_daily_action_inputs
from app.services.away_mode import (
    MAX_ACTIONABLE_AGE,
    MIN_PUSH_INTERVAL,
    AwayState,
    escalated_alert,
    escalation_note,
)
from app.services.away_runner import _naive, get_state, run_cycle
from app.services.currency import CurrencyService
from app.services.daily_actions import generate_daily_actions

router = APIRouter(prefix="/api/away", tags=["away"])


# ==============================================================================
# Schemas
# ==============================================================================

class AwayStatus(BaseModel):
    """The switch and everything the UI needs to explain the silence."""

    is_away: bool
    active: bool = Field(
        description="On *and* inside its window — an `until` in the past is off."
    )
    since: datetime | None = None
    until: datetime | None = None
    reason: str | None = None
    days_away: int | None = None

    last_push_at: datetime | None = None
    last_push_subject: str | None = None
    last_digest_reason: str | None = Field(
        default=None,
        description=(
            "Why the last cycle did or did not send. Away mode is quiet on "
            "purpose; this is what makes the quiet readable."
        ),
    )

    max_data_age_hours: int = int(MAX_ACTIONABLE_AGE.total_seconds() // 3600)
    quiet_period_hours: int = int(MIN_PUSH_INTERVAL.total_seconds() // 3600)


class AwayUpdate(BaseModel):
    is_away: bool
    until: datetime | None = None
    reason: str | None = None


class AwayPreview(BaseModel):
    """What a cycle would do right now, without sending anything."""

    away: bool
    would_send: bool
    decision: str
    subject: str | None = None
    body: str | None = None
    held: list[str] = Field(default_factory=list)


# ==============================================================================
# Endpoints
# ==============================================================================

def _status(row, now: datetime) -> AwayStatus:
    # Postgres returns tz-aware datetimes and `now` here is naive UTC.
    # Comparing the two raises, so everything is flattened to naive first.
    state = AwayState(
        is_away=bool(row.is_away),
        since=_naive(row.since),
        until=_naive(row.until),
    )
    return AwayStatus(
        is_away=bool(row.is_away),
        active=state.active_at(now),
        since=row.since,
        until=row.until,
        reason=row.reason,
        days_away=state.days_away(now),
        last_push_at=row.last_push_at,
        last_push_subject=row.last_push_subject,
        last_digest_reason=row.last_digest_reason,
    )


@router.get("", response_model=AwayStatus)
def get_away(db: Session = Depends(get_db)) -> AwayStatus:
    """Is away mode on, and what did it last decide?"""
    row = get_state(db)
    db.commit()
    return _status(row, datetime.utcnow())


@router.put("", response_model=AwayStatus)
def set_away(update: AwayUpdate, db: Session = Depends(get_db)) -> AwayStatus:
    """
    Turn away mode on or off.

    Switching it on stamps `since` now; switching it off clears the window but
    leaves `last_push_*` alone, so turning it on again the same day does not
    reopen the channel for a message that already went out.
    """
    now = datetime.utcnow()
    row = get_state(db)

    if update.is_away and not row.is_away:
        row.since = now
    if not update.is_away:
        row.since = None
        row.until = None

    row.is_away = update.is_away
    if update.is_away:
        row.until = update.until
        row.reason = update.reason
    else:
        row.reason = None

    db.commit()
    return _status(row, now)


@router.post("/preview", response_model=AwayPreview)
def preview(db: Session = Depends(get_db)) -> AwayPreview:
    """
    Run one cycle without sending, and show what it decided.

    The point is to be able to check the rules against the real portfolio
    before trusting them with a week of silence.
    """
    try:
        result = _cycle(db, send=False)
    except Exception as e:
        logger.exception("Away preview failed")
        raise HTTPException(status_code=500, detail=f"Away preview failed: {e}")

    db.rollback()  # a preview writes nothing, not even the digest reason
    return AwayPreview(
        away=result.away,
        would_send=result.sent or bool(result.subject),
        decision=result.reason,
        subject=result.subject,
        body=result.body,
        held=result.held or [],
    )


def _cycle(db: Session, *, send: bool, notify=None, now: datetime | None = None):
    """Build today's actions, add away stops, and run one away-mode pass."""
    (
        market_alert,
        alert_updated_at,
        positions,
        analyses,
        cash_czk,
    ) = load_daily_action_inputs(db)

    now = now or datetime.utcnow()

    # The escalation happens here, not in the engine: the canon's blocked-tier
    # table is used unchanged, just against a semafor one step further toward
    # defence. The normal daily list must not quietly acquire it.
    daily = generate_daily_actions(
        market_alert=escalated_alert(market_alert),
        market_alert_updated_at=alert_updated_at,
        positions=positions,
        analyses=analyses,
        cash_czk=cash_czk,
        fx_rate_to_czk=CurrencyService.get_rate_to_czk,
        now=now,
    )

    note = escalation_note(market_alert)
    actions = list(daily.actions)
    for action in actions:
        if note and action.action_type in ("SELL", "SELL_WAIT_TIME"):
            action.reason = f"{action.reason}\n\n{note}"

    return run_cycle(
        db,
        actions=actions,
        positions=positions,
        now=now,
        send=send,
        notify=notify,
        notes=_blind_spots(daily.warnings),
    )


#: Warnings that explain why away mode had nothing to say, most explanatory
#: first. The order is the point: "NEZNÁMÁ KVALITA u 15 pozic" is *the* reason
#: the de-risking rules cannot fire — without a phase or a conviction score the
#: engine refuses to judge a holding at all — while three missing purchase
#: prices only disarm the doubling rule. An unranked list truncated to three
#: showed the second and dropped the first.
_BLIND_SPOT_MARKERS: tuple[str, ...] = (
    "NEZNÁMÁ KVALITA",   # nothing can be judged — the whole of away mode idles
    "SEMAFOR",           # the semafor gates every de-risking rule
    "NESEDÍ",            # a wrong currency mis-sizes everything downstream
    "CHYBÍ",             # a missing input disarms one rule
)

#: Three lines is a note; ten is a wall nobody reads on returning from a
#: hospital stay.
MAX_BLIND_SPOTS = 3


def _blind_spots(warnings: list[str]) -> list[str]:
    """
    The gaps that make silence mean less than it looks like it means.

    Away mode staying quiet because nothing needs doing and away mode staying
    quiet because it could not read a single holding produce the same empty
    inbox. Only the second one is a problem, and it has to be findable when you
    come back — so the most explanatory gaps are the ones that survive the cap.
    """
    ranked: list[tuple[int, str]] = []
    for warning in warnings:
        upper = warning.upper()
        for rank, marker in enumerate(_BLIND_SPOT_MARKERS):
            if marker in upper:
                ranked.append((rank, warning))
                break
    ranked.sort(key=lambda pair: pair[0])
    return [warning for _, warning in ranked[:MAX_BLIND_SPOTS]]
