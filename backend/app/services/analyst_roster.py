"""
Reading and maintaining the list of people whose word counts.

`app/core/sources.py` stays free of the database so the attribution rules can
be exercised without one; this module is what fetches the list and hands it in.

Nobody is on the list by default. That is the design, not an oversight: the
WhatsApp group has around a hundred and thirty members and the app has no way
to tell which of them writes research. Their messages are stored with their
names intact and count toward nothing until somebody says otherwise, which is
the correct treatment for a crowd.
"""

from __future__ import annotations

from datetime import datetime, timezone

from loguru import logger
from sqlalchemy.orm import Session

from app.core.sources import InvestmentSource
from app.models.analyst_roster import RosterEntry

#: The only two sources a roster row may point at. OTHER is what an ABSENCE
#: from the list means, so listing somebody as OTHER would be a contradiction.
ALLOWED_SOURCES = (
    InvestmentSource.GOMES.value,
    InvestmentSource.BREAKOUT_INVESTORS.value,
)


def load(db: Session) -> dict[str, str]:
    """
    The active roster as `{lower-cased name: source key}`.

    Never raises: attribution has a keyword fallback, so a roster that cannot
    be read degrades to the behaviour the app had before it existed rather than
    taking a paste down with it.
    """
    try:
        rows = db.query(RosterEntry).filter(RosterEntry.active.is_(True)).all()
    except Exception:  # noqa: BLE001 — see docstring
        logger.exception("Seznam analytiků se nepodařilo načíst")
        return {}
    return {row.name_key: row.source_key for row in rows}


def add(
    db: Session,
    display_name: str,
    source_key: str,
    *,
    note: str | None = None,
    now: datetime | None = None,
) -> RosterEntry:
    """
    Put somebody on the list, or move them to another source.

    Adds to the session without committing. Raises on an unusable name or an
    unknown source rather than storing a row that will never match anything.
    """
    name = (display_name or "").strip()
    if not name:
        raise ValueError("Jméno nesmí být prázdné")

    key = name.lower()
    source = (source_key or "").strip().upper()
    if source not in ALLOWED_SOURCES:
        raise ValueError(
            f"Zdroj musí být jeden z {', '.join(ALLOWED_SOURCES)} — "
            f"nepřítomnost na seznamu už znamená OTHER"
        )

    row = db.query(RosterEntry).filter(RosterEntry.name_key == key).first()
    if row is None:
        row = RosterEntry(
            name_key=key,
            display_name=name,
            source_key=source,
            note=note,
            active=True,
            added_at=now or datetime.now(timezone.utc),
        )
        db.add(row)
    else:
        row.display_name = name
        row.source_key = source
        row.active = True
        if note:
            row.note = note

    logger.info("Na seznamu analytiků: {} -> {}", name, source)
    return row


def deactivate(db: Session, display_name: str) -> RosterEntry | None:
    """
    Stop counting somebody, without erasing what they already said.

    Deactivated rather than deleted: claims recorded while they were listed
    keep their attribution, because rewriting the past to match a present
    opinion would make the record useless for judging either.
    """
    key = (display_name or "").strip().lower()
    row = db.query(RosterEntry).filter(RosterEntry.name_key == key).first()
    if row is None:
        return None
    row.active = False
    logger.info("Ze seznamu analytiků odebrán: {}", row.display_name)
    return row


def listed(db: Session) -> list[RosterEntry]:
    """Everyone on the list, active first, for a screen or a report."""
    return (
        db.query(RosterEntry)
        .order_by(RosterEntry.active.desc(), RosterEntry.source_key, RosterEntry.name_key)
        .all()
    )
