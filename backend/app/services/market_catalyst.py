"""
What has to be true for the semafor to stand at ORANGE or RED.

The distinction this module exists for
--------------------------------------
GOMES_VIDEO_ADDENDUM.md §V3. The four grades are not four levels of expensive.
Gomes separates them by what he KNOWS:

    YELLOW  "I don't know what's going to cause the market to drop, but
             something's going to, because the market's too expensive right
             now. Most of my alerts are going to be yellow."
    ORANGE  COVID. "I knew it was bad. I just didn't know HOW bad, because
             frankly I'm not a biologist."
    RED     "That is when I know exactly what's happening, why it's happening,
             and how severe it is. And it's bad."  Twice in thirty years:
             the end of 1999 and the middle of 2007.

So YELLOW is a statement about valuation, and ORANGE and RED are statements
about a CAUSE somebody has identified. `market_gauge` measures price against a
41-year trend; it cannot know what is happening in the world, so its range is
capped at YELLOW and the rest is reached only through here.

Why this is worth code rather than a note
-----------------------------------------
Two failures, and the second is the one that costs money.

The first is escalation nobody can justify: ORANGE moves the target allocation
to 25/35/40, which sells most of a portfolio. Doing that off a z-score means
selling on arithmetic that admits it missed the 2007 top entirely.

The second is that **nothing in this app has ever de-escalated the semafor.**
`market_watch` may tighten and may never loosen, by design, and the owner is a
person with no time who returned to this app after three and a half months of
dormancy. An ORANGE set during a scare and then forgotten keeps the Buy Guard
refusing every purchase, in every market, forever — the failure is silent
because a refusal looks exactly like caution working.

Requiring a written cause fixes both. An escalation has to name what is
happening, and a cause with no end in sight can be shown as stale and
questioned. This module never lowers the semafor by itself — the canon's
asymmetry stands, and only a person lowers it — but it makes the case visible
instead of leaving it to be noticed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Final

from app.core.czech import d as cz_date
from app.core.czech import plural as cz_plural

#: Grades that are claims about a cause rather than about valuation.
NEEDS_CAUSE: Final[frozenset[str]] = frozenset({"ORANGE", "RED"})

#: After this long without a review, a recorded cause is shown as stale. Not an
#: expiry: a real crisis lasts longer than a quarter and the semafor must not
#: fall off it on a timer. It is a prompt to look, which is the thing that never
#: happens on its own.
STALE_AFTER_DAYS: Final[int] = 90


@dataclass(frozen=True)
class Catalyst:
    """
    The identified cause behind an ORANGE or RED, as recorded.

    `severity_known` is the axis that separates the two grades, and it is a
    deliberate boolean rather than a scale. Gomes' own distinction is binary:
    either he knows how bad it is or he does not. A five-point severity scale
    would invite a 3, and a 3 is exactly the judgement he refuses to make.
    """

    description: str
    identified_at: datetime
    severity_known: bool = False

    def age_days(self, now: datetime) -> int:
        return max(0, (_naive(now) - _naive(self.identified_at)).days)

    def is_stale(self, now: datetime) -> bool:
        return self.age_days(now) >= STALE_AFTER_DAYS


@dataclass(frozen=True)
class Verdict:
    """Whether the semafor as set is supported by what is on record."""

    #: The grade currently set on the field.
    alert: str
    #: True when the grade is one this module has nothing to say about
    #: (GREEN/YELLOW), or when a cause is on record and matches it.
    supported: bool
    #: The grade the evidence actually supports. Never applied automatically;
    #: only a person lowers the semafor.
    supported_alert: str
    #: Whether the recorded cause has gone unreviewed long enough to ask about.
    stale: bool = False
    message_cs: str = ""

    @property
    def needs_review(self) -> bool:
        return not self.supported or self.stale


def _naive(value: datetime) -> datetime:
    """Comparable regardless of whether the column carried a timezone."""
    return value.replace(tzinfo=None)


def of_row(row: Any | None) -> Catalyst | None:
    """
    The cause recorded on a `market_status` row, or None when none is.

    Duck-typed on the three columns rather than importing the model, so this
    module stays a pure function of what it is given and can be tested without
    a database. A description with no date is treated as no cause at all: the
    age is the only thing that makes a forgotten escalation visible, and a
    cause that cannot be aged cannot be questioned.
    """
    if row is None:
        return None
    description = getattr(row, "catalyst_description", None)
    identified_at = getattr(row, "catalyst_identified_at", None)
    if not description or identified_at is None:
        return None
    return Catalyst(
        description=description,
        identified_at=identified_at,
        severity_known=bool(getattr(row, "catalyst_severity_known", False)),
    )


def note_for(
    alert: str | None, row: Any | None, *, now: datetime | None = None
) -> str | None:
    """
    One sentence for the daily list when the semafor needs a second look.

    Silent whenever the grade stands on something — the daily list is read in
    two minutes and a line that appears every day stops being read at all. It
    speaks in exactly the two cases nothing else in this app can catch: an
    escalation with no cause written down, and a cause old enough that nobody
    can say whether it still holds.
    """
    verdict = check(alert, of_row(row), now=now)
    if not verdict.needs_review:
        return None
    return verdict.message_cs or None


def grade_for(catalyst: Catalyst | None) -> str | None:
    """
    The grade a recorded cause justifies, or None when there is no cause.

    A cause whose size is not yet understood is ORANGE; a cause known to be
    severe is RED. There is no third answer, because there is no third state of
    knowledge in the method.
    """
    if catalyst is None:
        return None
    return "RED" if catalyst.severity_known else "ORANGE"


def check(
    alert: str | None,
    catalyst: Catalyst | None,
    *,
    valuation_alert: str = "YELLOW",
    now: datetime | None = None,
) -> Verdict:
    """
    Whether the semafor standing on the field is backed by what is on record.

    Args:
        alert: The grade currently set.
        catalyst: The cause recorded behind it, if any.
        valuation_alert: What the long-term chart says on its own — the floor
            the semafor falls back to when an escalation has nothing behind it.
            Defaults to YELLOW rather than GREEN: this function must never be
            the reason an all-clear appears, and Gomes says most of his alerts
            are yellow anyway.
        now: Clock, injectable for tests.

    Returns a `Verdict`. It is a finding, never an action — nothing here writes
    the semafor, because lowering it is a person's decision.
    """
    moment = now or datetime.now(timezone.utc)
    level = (alert or "").upper()

    if level not in NEEDS_CAUSE:
        return Verdict(
            alert=level,
            supported=True,
            supported_alert=level,
            message_cs="",
        )

    if catalyst is None:
        return Verdict(
            alert=level,
            supported=False,
            supported_alert=valuation_alert,
            message_cs=(
                f"Semafor stojí na {_CS[level]}, ale není zapsané proč. "
                f"{_CS[level].capitalize()} podle metodiky neznamená „draho“ — "
                f"znamená pojmenovanou příčinu. Bez ní odpovídá stavu trhu "
                f"stupeň {_CS.get(valuation_alert, valuation_alert.lower())}."
            ),
        )

    justified = grade_for(catalyst)
    stale = catalyst.is_stale(moment)

    if justified != level:
        return Verdict(
            alert=level,
            supported=False,
            supported_alert=justified or valuation_alert,
            stale=stale,
            message_cs=(
                f"Zapsaná příčina („{catalyst.description}“) "
                + (
                    "má známý rozsah, což je červená."
                    if catalyst.severity_known
                    else "má neznámý rozsah, což je oranžová."
                )
                + f" Semafor ale stojí na {_CS[level]}."
            ),
        )

    if stale:
        days = catalyst.age_days(moment)
        return Verdict(
            alert=level,
            supported=True,
            supported_alert=level,
            stale=True,
            message_cs=(
                f"Příčina („{catalyst.description}“) je zapsaná od "
                f"{cz_date(catalyst.identified_at)}, tedy {days} "
                f"{cz_plural(days, 'den', 'dny', 'dnů')}. "
                f"Platí pořád? Dokud na {_CS[level]} stojí semafor, aplikace "
                f"nepovolí žádný nákup."
            ),
        )

    return Verdict(
        alert=level,
        supported=True,
        supported_alert=level,
        message_cs=(
            f"{_CS[level].capitalize()} stojí na příčině zapsané "
            f"{cz_date(catalyst.identified_at)}: „{catalyst.description}“."
        ),
    )


#: Grades in Czech. The screen never shows the enum value.
_CS: Final[dict[str, str]] = {
    "GREEN": "zelené",
    "YELLOW": "žluté",
    "ORANGE": "oranžové",
    "RED": "červené",
}
