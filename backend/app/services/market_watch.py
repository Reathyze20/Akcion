"""
Letting the long-term chart tighten the semafor, but never loosen it.

The problem this solves
-----------------------
The market alert gates every purchase in the app, and it is a hand-set field.
`daily_actions` refuses to authorise buys once it is fourteen days old, which is
correct and also means the one thing the owner must do by hand is the one thing
that stops everything else working — precisely during the weeks he cannot do it.

`market_gauge` already computes what the 41-year chart says. Until now it only
suggested, and its own docstring said it would never switch anything
automatically. That was the right default while nothing else had been built;
it is the wrong one now that a stale semafor silently disarms the whole engine.

The asymmetry is the whole design
---------------------------------
The gauge may make the app MORE careful on its own. It may never make it bolder.

That is not timidity, it is what the measure has earned. The gauge admits its
own blind spot: of the two RED alerts Gomes has called in his life it finds the
end of 1999 and misses the middle of 2007 entirely, because the 2007 top rested
on credit and earnings that were about to vanish and price-against-trend cannot
see that. A measure that can miss a top must never be allowed to declare the
all-clear — but a measure that says "expensive" is worth listening to even when
nobody is at the keyboard.

So: a suggestion stricter than the current setting is applied and announced. A
suggestion looser than it is shown and ignored. The owner can always lower the
level himself; the app cannot.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Final

from loguru import logger
from sqlalchemy.orm import Session

from app.models.portfolio import MarketStatus, MarketStatusEnum
from app.services import market_catalyst
from app.services.market_gauge import GaugeError, Reading, alert_cs, current_reading

#: How careful each level is. Comparison is on this, never on the string.
CAUTION: Final[dict[str, int]] = {"GREEN": 0, "YELLOW": 1, "ORANGE": 2, "RED": 3}

APPLIED = "APPLIED"          # the gauge tightened the semafor
SUGGESTED_ONLY = "SUGGESTED"  # the gauge would loosen it; shown, not applied
UNCHANGED = "UNCHANGED"       # they already agree
UNAVAILABLE = "UNAVAILABLE"   # the gauge could not be computed


@dataclass(frozen=True)
class WatchResult:
    """What one look at the long-term chart did."""

    status: str
    previous: str | None = None
    suggested: str | None = None
    message_cs: str = ""

    @property
    def changed(self) -> bool:
        return self.status == APPLIED


def is_more_cautious(candidate: str | None, than: str | None) -> bool:
    """
    Whether `candidate` would make the app more careful than `than`.

    Unknown counts as least cautious: a semafor nobody has set is not a reason
    to refuse a tightening, it is a reason to accept one.
    """
    if not candidate:
        return False
    if not than:
        return True
    return CAUTION.get(candidate.upper(), -1) > CAUTION.get(than.upper(), -1)


def apply_gauge(
    db: Session,
    *,
    reading: Reading | None = None,
    now: datetime | None = None,
    refresh: bool = False,
) -> WatchResult:
    """
    Read the long-term chart and tighten the semafor if it says to.

    Adds to the session without committing; the caller owns the transaction.

    Never raises on an unreachable data source: a gauge that cannot be computed
    leaves the semafor exactly as it was, which is the safe direction — the
    stale-alert rule in `daily_actions` then stops authorising purchases on its
    own, and that is the behaviour we want when nothing can be measured.
    """
    moment = now or datetime.utcnow()

    if reading is None:
        try:
            reading = current_reading(refresh=refresh)
        except (GaugeError, Exception) as exc:  # noqa: BLE001 — see docstring
            logger.warning("Měřidlo trhu nešlo spočítat: {}", exc)
            return WatchResult(
                status=UNAVAILABLE,
                message_cs=f"Dlouhodobý graf se nepodařilo spočítat: {exc}",
            )

    row = db.query(MarketStatus).order_by(MarketStatus.id).first()
    current = row.status.value if row and row.status else None
    suggested = reading.suggested_alert

    # A second lock on the same door as `market_gauge.GAUGE_MAX_ALERT`, and it
    # is here because this is the only place in the app that writes the semafor
    # without a person. §V3: ORANGE and RED are claims about an identified
    # cause, and this path has none to offer — `market_catalyst` is what records
    # one, through the endpoint a human uses. An escalation applied here would
    # also be the one thing nothing can undo, since this module never loosens.
    # Unreachable today; kept so that re-pointing the gauge's table at ORANGE
    # cannot quietly re-open it.
    if suggested in market_catalyst.NEEDS_CAUSE:
        logger.warning(
            "Měřidlo navrhlo {} — stupeň, který potřebuje pojmenovanou příčinu. "
            "Nepoužito.", suggested
        )
        return WatchResult(
            status=SUGGESTED_ONLY, previous=current, suggested=suggested,
            message_cs=(
                f"Dlouhodobý graf by odpovídal stupni {alert_cs(suggested)}, "
                f"ale ten podle metodiky znamená pojmenovanou příčinu, ne "
                f"drahotu. Sám ho nenastavím — zapiš, co se děje."
            ),
        )

    if not is_more_cautious(suggested, current):
        if current == suggested:
            # Agreement is an independent confirmation that the level is still
            # right, so it may refresh the timestamp the staleness rule reads —
            # but only for a cautious level. A stale ORANGE goes on de-risking
            # and costs nothing; a stale GREEN authorises purchases, and the
            # gauge that misses the 2007 top must not be what keeps that alive.
            # Buying stays gated on a human having looked.
            refreshed = False
            if row is not None and CAUTION.get(current or "", 0) > 0:
                row.last_updated = moment
                refreshed = True
            return WatchResult(
                status=UNCHANGED, previous=current, suggested=suggested,
                message_cs=(
                    f"Semafor {alert_cs(current)} sedí s dlouhodobým grafem"
                    + (
                        " — potvrzeno k dnešku."
                        if refreshed
                        else ". Nákupy zůstávají na tvém potvrzení."
                    )
                ),
            )
        return WatchResult(
            status=SUGGESTED_ONLY, previous=current, suggested=suggested,
            message_cs=(
                f"Dlouhodobý graf by odpovídal stupni {alert_cs(suggested)}, "
                f"tedy méně opatrnému než nastavený {alert_cs(current)}. "
                f"Sám ho nezvolním — povolit smíš jen ty."
            ),
        )

    if row is None:
        row = MarketStatus(status=MarketStatusEnum(suggested))
        db.add(row)
    else:
        row.status = MarketStatusEnum(suggested)
    row.last_updated = moment
    if hasattr(row, "note"):
        row.note = (
            f"Automaticky přitvrzeno podle dlouhodobého grafu "
            f"({reading.as_of:%d.%m.%Y}, z-skóre {reading.z_score:+.2f})."
        )

    logger.info("Semafor přitvrzen {} -> {}", current, suggested)
    return WatchResult(
        status=APPLIED, previous=current, suggested=suggested,
        message_cs=(
            f"Semafor přitvrzen z {alert_cs(current) if current else 'nenastaveno'} "
            f"na {alert_cs(suggested)} — dlouhodobý graf k {reading.as_of:%d.%m.%Y} "
            f"stojí na z-skóre {reading.z_score:+.2f}. "
            f"Zvolnit ho může jen člověk."
        ),
    )
