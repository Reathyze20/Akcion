"""
The earnings countdown as both tables show it.

The holdings view and the watchlist ask the same question about different
objects, so the answer is built once. What has to hold is that the cell never
loses the distinction the calendar exists to keep: an announced date and a
pattern this app worked out are both actionable and are not the same claim.

And that the countdown stays a nicety. A calendar that cannot be read must not
take the holdings table down with it — the money is the point, the badge next
to it is not.
"""

from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401
import app.models.trading  # noqa: F401
from app.models.base import Base
from app.models.earnings import (
    SOURCE_RELEASE_CADENCE,
    SOURCE_YAHOO,
    EarningsDate,
)
from app.services.earnings_lookup import BLACKOUT_DAYS, badge, badges

TODAY = date(2026, 8, 25)


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[EarningsDate.__table__])
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


def _row(**over):
    base = dict(
        ticker="DBOXF",
        next_date=date(2026, 11, 11),
        window_end=None,
        confirmed=True,
        source=SOURCE_YAHOO,
        note=None,
    )
    base.update(over)
    return EarningsDate(**base)


# ==============================================================================
# The cell says which kind of date it is
# ==============================================================================

def test_an_announced_date_counts_down_plainly():
    made = badge(_row(), today=TODAY)

    assert made.label_cs == "za 78 dní"
    assert made.confirmed is True


def test_an_estimate_says_it_is_one_in_the_cell_itself():
    """
    Not only in the tooltip. A column of bare day counts is read as a column of
    facts, and two of the twelve holdings have a date nobody announced —
    Gatekeeper and Kuya, worked out from their own publishing history.
    """
    made = badge(
        _row(
            ticker="GKPRF",
            next_date=date(2026, 12, 1),
            window_end=date(2026, 12, 31),
            confirmed=False,
            source=SOURCE_RELEASE_CADENCE,
        ),
        today=TODAY,
    )

    assert made.label_cs.startswith("asi za ")
    assert made.confirmed is False


def test_the_detail_carries_the_date_and_the_reason():
    made = badge(
        _row(confirmed=False, note="Odhad z vlastní historie zveřejňování firmy"),
        today=TODAY,
    )

    assert "11.11.2026" in made.detail_cs
    assert "odhad" in made.detail_cs
    assert "historie" in made.detail_cs


def test_czech_counts_a_day_a_few_days_and_many_days_differently():
    one = badge(_row(next_date=date(2026, 8, 28)), today=TODAY)
    few = badge(_row(next_date=date(2026, 8, 27)), today=TODAY)

    assert one.label_cs == "za 3 dny"
    assert few.label_cs == "za 2 dny"
    assert badge(_row(next_date=TODAY), today=TODAY).label_cs == "dnes"
    assert badge(_row(next_date=date(2026, 8, 26)), today=TODAY).label_cs == "zítra"


def test_a_date_that_has_slipped_into_the_past_says_so(db):
    """Counting backwards would read as "reported already", which is a guess."""
    made = badge(_row(next_date=date(2026, 8, 1)), today=TODAY)

    assert made.label_cs == "termín prošel"


# ==============================================================================
# The blackout the Buy Guard actually enforces
# ==============================================================================

def test_a_print_inside_the_guard_window_is_flagged():
    """
    The same fourteen days `GomesGatekeeper` refuses purchases in. Sent rather
    than recomputed in the browser, so the table and the guard cannot disagree
    about what is imminent.
    """
    inside = badge(_row(next_date=date(2026, 9, 5)), today=TODAY)   # 11 days
    outside = badge(_row(next_date=date(2026, 9, 30)), today=TODAY)  # 36 days

    assert inside.days <= BLACKOUT_DAYS and inside.blackout is True
    assert outside.blackout is False


# ==============================================================================
# One company, whatever it is held as
# ==============================================================================

def test_a_position_held_under_another_listing_still_finds_its_date(db):
    """The calendar keeps one row per company under KUYAF; the broker says KUYA.V."""
    db.add(_row(ticker="KUYAF", next_date=date(2026, 11, 21), confirmed=False))
    db.flush()

    found = badges(db, ["KUYA.V"], today=TODAY)

    assert "KUYA.V" in found
    assert found["KUYA.V"].next_date == date(2026, 11, 21)


def test_a_company_with_no_row_is_absent_rather_than_zero(db):
    """
    A missing key lets the table draw a dash. A zero would read as "reports
    today", which is the defect this app keeps finding in another costume.
    """
    assert badges(db, ["NOSUCHCO"], today=TODAY) == {}


def test_no_tickers_asks_nothing(db):
    assert badges(db, [], today=TODAY) == {}


# ==============================================================================
# The badge is a nicety; the table is not
# ==============================================================================

def test_an_unreadable_calendar_does_not_take_the_holdings_table_down():
    """
    Found by a test, not in production: the holdings endpoint raised
    OperationalError for every position because one auxiliary table was
    missing. The money must survive the loss of the note beside it.
    """
    engine = create_engine("sqlite://")  # deliberately no tables created
    session = sessionmaker(bind=engine)()
    try:
        assert badges(session, ["DBOXF"], today=TODAY) == {}
    finally:
        session.close()


# ==============================================================================
# A date that has already happened is not an answer
# ==============================================================================

def test_a_provider_date_in_the_past_is_refused_like_any_other(db, monkeypatch):
    """
    The module's own rule — "a date from three months ago is worse than none,
    because it looks like an answer" — was applied only to the cadence tier.
    The provider broke it for four watchlist names, still returning last
    quarter's print weeks after the fact.
    """
    from app.services import earnings_calendar as ec

    monkeypatch.setattr(
        ec, "fetch_from_provider",
        lambda ticker: ec.Guess(
            next_date=date(2026, 8, 7), confirmed=True, source=SOURCE_YAHOO
        ),
    )
    monkeypatch.setattr(ec, "estimate_from_filings", lambda *a, **k: None)
    monkeypatch.setattr(ec, "estimate_from_release_history", lambda *a, **k: None)

    from datetime import datetime, timezone
    [row] = ec.refresh(db, ["CELH"], now=datetime(2026, 8, 25, tzinfo=timezone.utc))
    db.flush()

    assert row.next_date is None
    assert "nezná" in row.note


def test_a_window_still_open_counts_as_future(db, monkeypatch):
    """The window started yesterday; the company has not reported yet."""
    from datetime import datetime, timezone

    from app.services import earnings_calendar as ec

    monkeypatch.setattr(
        ec, "fetch_from_provider",
        lambda ticker: ec.Guess(
            next_date=date(2026, 8, 20), window_end=date(2026, 9, 3),
            confirmed=False, source=SOURCE_YAHOO,
        ),
    )
    [row] = ec.refresh(db, ["GKPRF"], now=datetime(2026, 8, 25, tzinfo=timezone.utc))
    db.flush()

    assert row.next_date == date(2026, 8, 20)
