"""
Whose word counts, and what happens to everyone else's.

Two opposite bugs met in the same place. `normalize_source` decided
attribution by substring, so an analyst writing under his own name landed in
OTHER — and OTHER does not enter `evaluate_dual_source_buy` at all, so their
research was stored and silently unused. Meanwhile
`claim_extraction.resolve_source_key` mapped EVERY speaker in the WhatsApp
group to BREAKOUT_INVESTORS: around a hundred and thirty people, any one of
whom then carried the authority of the research desk.

That key sets the position cap. Agreement between two sources allows 15 % of a
portfolio where a single source allows 7 %, so getting attribution wrong in
either direction is a sizing error on real money.
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401
import app.models.trading  # noqa: F401
from app.core.sources import normalize_source
from app.models.analyst_roster import RosterEntry
from app.models.base import Base
from app.services.analyst_roster import add, deactivate, listed, load

NOW = datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[RosterEntry.__table__])
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


# ==============================================================================
# Attribution, with and without a list
# ==============================================================================

def test_without_a_roster_nothing_changes():
    """The keyword fallback is what the app had, and it still works."""
    assert normalize_source("Mark Gomes") == "GOMES"
    assert normalize_source("Breakout Investors") == "BREAKOUT_INVESTORS"
    assert normalize_source("Brad Steveson") == "OTHER"


def test_a_listed_name_is_attributed_to_its_source():
    """
    The bug in one line. An analyst under his own name used to be OTHER, and
    OTHER never reaches the agreement matrix.
    """
    roster = {"brad steveson": "BREAKOUT_INVESTORS"}
    assert normalize_source("Brad Steveson", roster) == "BREAKOUT_INVESTORS"


def test_matching_ignores_case_and_padding():
    roster = {"brad steveson": "BREAKOUT_INVESTORS"}
    assert normalize_source("  BRAD STEVESON ", roster) == "BREAKOUT_INVESTORS"


def test_the_roster_wins_over_the_substring():
    """
    Substring matching is the thing being replaced, so it must not override the
    owner's own assignment.
    """
    roster = {"breakout bob": "GOMES"}
    assert normalize_source("Breakout Bob", roster) == "GOMES"


def test_an_unlisted_stranger_stays_other():
    """
    A hundred and thirty people in a group chat. Counting them all as the
    research desk is what this replaces, and the absence of a name is the
    answer rather than a gap to fill.
    """
    roster = {"brad steveson": "BREAKOUT_INVESTORS"}
    assert normalize_source("Someone Else", roster) == "OTHER"


def test_nobody_is_listed_by_default(db):
    assert load(db) == {}


# ==============================================================================
# Maintaining the list
# ==============================================================================

def test_adding_somebody_makes_them_count(db):
    add(db, "Brad Steveson", "BREAKOUT_INVESTORS", note="píše analýzy", now=NOW)
    db.flush()

    roster = load(db)
    assert roster == {"brad steveson": "BREAKOUT_INVESTORS"}
    assert normalize_source("Brad Steveson", roster) == "BREAKOUT_INVESTORS"


def test_adding_the_same_person_twice_moves_them(db):
    add(db, "Brad Steveson", "BREAKOUT_INVESTORS", now=NOW)
    db.flush()
    add(db, "Brad Steveson", "GOMES", now=NOW)
    db.flush()

    assert db.query(RosterEntry).count() == 1
    assert load(db)["brad steveson"] == "GOMES"


def test_a_row_may_not_point_at_other(db):
    """
    Absence from the list already means OTHER. A row saying so would be a
    contradiction, and one that reads as "considered and included".
    """
    with pytest.raises(ValueError):
        add(db, "Somebody", "OTHER", now=NOW)


def test_an_empty_name_is_refused(db):
    with pytest.raises(ValueError):
        add(db, "   ", "GOMES", now=NOW)


def test_deactivating_stops_the_counting_without_erasing_the_past(db):
    """
    Claims recorded while somebody was listed keep their attribution. Rewriting
    the past to match a present opinion would make the record useless for
    judging either.
    """
    add(db, "Brad Steveson", "BREAKOUT_INVESTORS", now=NOW)
    db.flush()

    deactivate(db, "Brad Steveson")
    db.flush()

    assert load(db) == {}
    assert db.query(RosterEntry).count() == 1
    assert db.query(RosterEntry).one().active is False


def test_deactivating_somebody_absent_is_not_an_error(db):
    assert deactivate(db, "Nikdo") is None


def test_every_row_can_say_why_it_is_there(db):
    """A roster without reasons cannot be audited a year later."""
    add(db, "Brad Steveson", "BREAKOUT_INVESTORS", note="píše jejich analýzy", now=NOW)
    db.flush()

    [row] = listed(db)
    assert row.note == "píše jejich analýzy"
    assert row.display_name == "Brad Steveson"     # as written, for the screen


def test_an_unreadable_roster_degrades_rather_than_raises():
    """
    Attribution has a keyword fallback. A roster that cannot be read should
    behave like the app did before it existed, not take a paste down.
    """
    assert load(None) == {}
