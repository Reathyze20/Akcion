"""
Wiring the Green and Red Lines into the database.

`tracker_sync` was written and tested on 2026-07-26 and had no caller: not a
route, not a script, not a scheduled task. The two lines it fetches are what
every band, every deserved comparison and every 3-point trigger is computed
from, so the whole decision engine was running over empty columns while its
unit tests passed.

What is asserted here is therefore the wiring, not the arithmetic — the
arithmetic already has `test_gomes_tracker.py`. Specifically the three ways
this job can go wrong quietly:

  * reading too often, against somebody else's server;
  * announcing sixteen picks as "new" on the very first read, which teaches
    the owner to ignore the next message;
  * turning an outage into silence that looks like "nothing changed".
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401
import app.models.trading  # noqa: F401
from app.models.base import Base
from app.models.stock import Stock
from app.models.tracker import TrackerLineChange, TrackerPollState
from app.services.gomes_tracker import TrackerPick, TrackerUnavailable
from app.services.tracker_sync import (
    STATUS_SYNCED,
    STATUS_TOO_SOON,
    STATUS_UNAVAILABLE,
    recent_line_notes,
    sync_tracker,
)

NOW = datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc)

#: Two real picks from the tracker snapshot in canon 8a.
CXDO = TrackerPick(ticker="CXDO", low=3.25, high=15.50, pick_type="OFFICIAL", price=6.62)
TPCS = TrackerPick(ticker="TPCS", low=3.25, high=14.00, pick_type="OFFICIAL", price=4.56)


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(
        engine,
        tables=[
            Stock.__table__,
            TrackerPollState.__table__,
            TrackerLineChange.__table__,
        ],
    )
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


def _feed(picks, monkeypatch, fail=None):
    """Stand in for the network. The HTTP layer has its own tests."""
    def fake_fetch(*, session=None):
        if fail is not None:
            raise TrackerUnavailable(fail)
        return picks

    monkeypatch.setattr("app.services.tracker_sync.fetch_tracker", fake_fetch)


# ==============================================================================
# The lines actually land
# ==============================================================================

def test_a_sync_writes_the_band_onto_a_gomes_row(db, monkeypatch):
    """The point of the whole exercise: `stocks.green_line` stops being NULL."""
    _feed([CXDO], monkeypatch)

    report = sync_tracker(db, now=NOW)
    db.flush()

    assert report.status == STATUS_SYNCED
    row = db.query(Stock).filter(Stock.ticker == "CXDO").one()
    assert float(row.green_line) == 3.25
    assert float(row.red_line) == 15.50
    assert row.source_key == "GOMES"
    # OFFICIAL means the Money Mark Portfolio — the app's portfolio/watchlist
    # split reads this, and it is not derivable from anything else (canon 8a).
    assert row.source_type == "OFFICIAL"


def test_the_first_read_is_a_baseline_not_sixteen_news_items(db, monkeypatch):
    """
    Diffing a first read against an empty table would report every pick as new
    and mail the lot — the one message guaranteed to teach the owner to ignore
    the next one. The rows are still written; only the news is suppressed.
    """
    _feed([CXDO, TPCS], monkeypatch)

    report = sync_tracker(db, now=NOW)
    db.flush()

    assert report.picks_read == 2
    assert report.changes == []
    assert db.query(TrackerLineChange).count() == 0
    assert db.query(Stock).count() == 2       # the bands landed regardless


def test_a_moved_line_is_recorded_as_news(db, monkeypatch):
    """
    The event that matters most. When the analyst moves a band he has revalued
    the company, and every score computed until that moment stood on the old
    one.
    """
    _feed([CXDO], monkeypatch)
    sync_tracker(db, now=NOW)
    db.flush()

    rebanded = TrackerPick(
        ticker="CXDO", low=4.00, high=18.00, pick_type="OFFICIAL", price=6.62
    )
    _feed([rebanded], monkeypatch)
    report = sync_tracker(db, force=True, now=NOW + timedelta(days=1))
    db.flush()

    assert report.band_updated == ["CXDO"]
    change = db.query(TrackerLineChange).one()
    assert change.kind == "LINE_MOVED"
    assert "CXDO" in change.detail_cs
    assert change.notified_at is None          # nobody has been told yet


def test_a_pick_leaving_the_real_portfolio_is_recorded(db, monkeypatch):
    """OFFICIAL -> NOT OFFICIAL means he moved real money out. Bigger than a re-band."""
    _feed([CXDO], monkeypatch)
    sync_tracker(db, now=NOW)
    db.flush()

    demoted = TrackerPick(
        ticker="CXDO", low=3.25, high=15.50, pick_type="NOT OFFICIAL", price=6.62
    )
    _feed([demoted], monkeypatch)
    sync_tracker(db, force=True, now=NOW + timedelta(days=1))
    db.flush()

    change = db.query(TrackerLineChange).filter_by(kind="PICK_TYPE").one()
    assert "OFFICIAL" in change.detail_cs


# ==============================================================================
# Reading politely, and failing honestly
# ==============================================================================

def test_a_second_read_within_twelve_hours_does_not_happen(db, monkeypatch):
    """
    The canon says these lines move on the order of weeks. The limit lives in
    code rather than in the scheduler, so clicking the button twice cannot
    hammer somebody else's server.
    """
    _feed([CXDO], monkeypatch)
    sync_tracker(db, now=NOW)
    db.flush()

    report = sync_tracker(db, now=NOW + timedelta(hours=6))
    assert report.status == STATUS_TOO_SOON
    assert report.picks_read == 0


def test_force_overrides_the_interval(db, monkeypatch):
    """For a first run and for checking an announced change — never for a loop."""
    _feed([CXDO], monkeypatch)
    sync_tracker(db, now=NOW)
    db.flush()

    report = sync_tracker(db, force=True, now=NOW + timedelta(hours=1))
    assert report.status == STATUS_SYNCED


def test_an_unreachable_source_is_reported_not_raised(db, monkeypatch):
    """
    "We could not see" must stay distinguishable from "there was nothing to
    see". An exception here would take down the caller; a silent empty result
    would read as good news.
    """
    _feed(None, monkeypatch, fail="connection refused")

    report = sync_tracker(db, now=NOW)
    db.flush()

    assert report.status == STATUS_UNAVAILABLE
    assert "connection refused" in report.error
    assert "nedostupný" in report.summary_cs()


def test_a_failed_read_still_counts_as_an_attempt(db, monkeypatch):
    """Otherwise an outage becomes a retry loop against a server that is already struggling."""
    _feed(None, monkeypatch, fail="timeout")
    sync_tracker(db, now=NOW)
    db.flush()

    state = db.query(TrackerPollState).one()
    assert state.last_attempt_at is not None
    assert state.last_success_at is None       # and it was not a success

    report = sync_tracker(db, now=NOW + timedelta(hours=1))
    assert report.status == STATUS_TOO_SOON


def test_a_pick_without_a_band_never_overwrites_a_good_one(db, monkeypatch):
    """A pick carrying no lines has no decision value and must not null one out."""
    _feed([CXDO], monkeypatch)
    sync_tracker(db, now=NOW)
    db.flush()

    bandless = TrackerPick(
        ticker="CXDO", low=None, high=None, pick_type="OFFICIAL", price=6.62
    )
    _feed([bandless], monkeypatch)
    sync_tracker(db, force=True, now=NOW + timedelta(days=1))
    db.flush()

    assert float(db.query(Stock).filter_by(ticker="CXDO").one().green_line) == 3.25


# ==============================================================================
# The re-banding reaches the place decisions are made
# ==============================================================================

def test_a_recent_reband_leads_the_daily_warnings(db, monkeypatch):
    """
    A moved band has to be read BEFORE the actions under it, because it changes
    what those numbers mean. A note filed after them would be read too late.
    """
    _feed([CXDO], monkeypatch)
    sync_tracker(db, now=NOW)
    db.flush()

    _feed(
        [TrackerPick(ticker="CXDO", low=4.00, high=18.00, pick_type="OFFICIAL", price=6.62)],
        monkeypatch,
    )
    sync_tracker(db, force=True, now=NOW + timedelta(days=1))
    db.flush()

    notes = recent_line_notes(db, now=NOW + timedelta(days=2))
    assert len(notes) == 1
    assert "PŘECENĚNO" in notes[0]
    assert "CXDO" in notes[0]


def test_an_old_reband_stops_being_shown(db, monkeypatch):
    """
    Two weeks is long enough to survive a fortnight away and short enough that
    the note does not become wallpaper the owner stops reading.
    """
    _feed([CXDO], monkeypatch)
    sync_tracker(db, now=NOW)
    db.flush()

    _feed(
        [TrackerPick(ticker="CXDO", low=4.00, high=18.00, pick_type="OFFICIAL", price=6.62)],
        monkeypatch,
    )
    sync_tracker(db, force=True, now=NOW + timedelta(days=1))
    db.flush()

    assert recent_line_notes(db, now=NOW + timedelta(days=40)) == []


def test_a_new_watchlist_name_is_not_a_daily_warning(db, monkeypatch):
    """
    It is news, but it does not make yesterday's score wrong. Only the two
    kinds that change what a number MEANS lead the list.
    """
    _feed([CXDO], monkeypatch)
    sync_tracker(db, now=NOW)
    db.flush()

    _feed([CXDO, TPCS], monkeypatch)
    sync_tracker(db, force=True, now=NOW + timedelta(days=1))
    db.flush()

    assert db.query(TrackerLineChange).filter_by(kind="NEW_PICK").count() == 1
    assert recent_line_notes(db, now=NOW + timedelta(days=2)) == []


def test_notes_never_take_the_daily_list_down(db):
    """A table that cannot be read costs a note, not the morning."""
    assert recent_line_notes(None) == []


def test_a_dry_run_writes_nothing(db, monkeypatch):
    """
    The contract `--dry-run` promises. It was broken: `apply_picks` committed
    mid-way, so the script's rollback had nothing left to undo and a dry run
    stamped `last_attempt_at` — which then silently blocked the next real read
    for twelve hours. The caller owns the transaction; this is what proves it.
    """
    _feed([CXDO], monkeypatch)

    sync_tracker(db, now=NOW)
    db.rollback()

    assert db.query(Stock).count() == 0
    assert db.query(TrackerPollState).count() == 0
