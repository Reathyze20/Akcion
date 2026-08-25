"""
An estimate does not close out a statement by being newer.

`stock_lifecycle` holds readings from two very different places. One is Mark
Gomes saying a number out loud on a dated video; the other is this app's rubric
inferring one from filings. Both are worth storing. They were not worth the
same, and the writer did not know it — it superseded whatever was live, so the
newest row won.

What that cost, on the live database:

    2026-08-21  GKPRF  10 válců  source=gomes_video_2026-08-21  confidence=HIGH
                „gatekeeper is operating on ten cylinders right now
                 I don't think anybody can deny they are operating
                 on all ten cylinders"
    2026-08-23  GKPRF   5 válců  source=rubric                  confidence=MEDIUM

Because `zasloužené = 10 − válce`, the bar the price is judged against moved
from 0 to 5. The R/R score of 4,26 turned from cheap into „PŘEPLACENO", and the
engine ordered half of a 13,9 % position sold — on the strength of the app's
own guess, over the analyst's statement.

The owner keeps the last word. What he no longer has is the accidental path to
it: overruling a stronger source now takes `override=True`, and the override is
stamped onto the row so a year from now it is still visible that it happened.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401
import app.models.trading  # noqa: F401
from app.core.sources import (
    RANK_ANALYST,
    RANK_RUBRIC,
    RANK_UNKNOWN,
    lifecycle_source_rank,
)
from app.models.base import Base
from app.models.gomes import StockLifecycleModel
from app.services.cylinder_intake import confirm

NOW = datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc)
SAID_ON = datetime(2026, 8, 21, 12, 0, tzinfo=timezone.utc)


@compiles(JSONB, "sqlite")
def _jsonb(type_, compiler, **kw):  # noqa: ARG001
    return "JSON"


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[StockLifecycleModel.__table__])
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def gomes_row(db, ticker="GKPRF", cylinders=10, detected_at=SAID_ON, valid_until=None):
    """The live row as it stood on 2026-08-22, before the rubric reached it."""
    row = StockLifecycleModel(
        ticker=ticker,
        phase="UNKNOWN",
        is_investable=True,
        cylinders_count=cylinders,
        firing_on_all_cylinders=cylinders >= 10,
        confidence="HIGH",
        source=f"gomes_video_{detected_at.date()}",
        detected_at=detected_at,
        cylinders_valid_until=valid_until,
    )
    db.add(row)
    db.flush()
    return row


# ==============================================================================
# The ranking itself
# ==============================================================================

class TestTheRanking:
    def test_an_analyst_on_record_outranks_the_rubric(self):
        assert lifecycle_source_rank("gomes_video_2026-08-21") == RANK_ANALYST
        assert lifecycle_source_rank("OFFICIAL") == RANK_ANALYST

    def test_both_rubric_writers_rank_the_same(self):
        """Two modules write phases and cylinders; neither outranks the other."""
        assert lifecycle_source_rank("rubric") == RANK_RUBRIC
        assert lifecycle_source_rank("lifecycle_rubric") == RANK_RUBRIC

    def test_a_row_that_cannot_say_where_it_came_from_ranks_lowest(self):
        """Below the rubric on purpose — unprovenanced is the weakest thing here."""
        assert lifecycle_source_rank(None) == RANK_UNKNOWN
        assert lifecycle_source_rank("") == RANK_UNKNOWN
        assert RANK_UNKNOWN < RANK_RUBRIC < RANK_ANALYST


# ==============================================================================
# What the writer does with it
# ==============================================================================

class TestTheRubricCannotOverwriteAStatement:
    def test_the_write_is_refused(self, db):
        gomes_row(db)
        with pytest.raises(ValueError):
            confirm(db, "GKPRF", 5, confirmed_by="Tomas", now=NOW)

    def test_the_statement_stays_live(self, db):
        gomes_row(db)
        with pytest.raises(ValueError):
            confirm(db, "GKPRF", 5, confirmed_by="Tomas", now=NOW)
        live = (
            db.query(StockLifecycleModel)
            .filter(StockLifecycleModel.valid_until.is_(None))
            .one()
        )
        assert live.cylinders_count == 10

    def test_the_refusal_says_what_stands_and_why(self, db):
        """
        „Nelze zapsat" with no reason is a wall. The message names the number,
        the date and the source, because the screen has to show him what he
        would be overwriting before he can sensibly agree to it.
        """
        gomes_row(db)
        with pytest.raises(ValueError) as raised:
            confirm(db, "GKPRF", 5, confirmed_by="Tomas", now=NOW)
        message = str(raised.value)
        assert "10 válců" in message
        assert "gomes_video_2026-08-21" in message
        assert "override" in message

    def test_a_stale_statement_no_longer_blocks(self, db):
        """
        A cylinder count describes how a company is operating, and the next
        report is what can contradict it. Past that, the rubric is the better
        of two imperfect readings and proceeds without asking.
        """
        gomes_row(db, detected_at=NOW - timedelta(days=200))
        row = confirm(db, "GKPRF", 5, confirmed_by="Tomas", now=NOW)
        db.flush()
        assert row.cylinders_count == 5

    def test_an_explicit_expiry_in_the_future_still_blocks(self, db):
        gomes_row(db, detected_at=NOW - timedelta(days=200),
                  valid_until=NOW + timedelta(days=30))
        with pytest.raises(ValueError):
            confirm(db, "GKPRF", 5, confirmed_by="Tomas", now=NOW)

    def test_one_rubric_row_still_supersedes_another(self, db):
        """The guard is about rank, not about refusing to move at all."""
        confirm(db, "CXDO", 7, confirmed_by="Tomas", now=NOW)
        db.flush()
        confirm(db, "CXDO", 8, confirmed_by="Tomas", now=NOW + timedelta(days=1))
        db.flush()
        live = (
            db.query(StockLifecycleModel)
            .filter(StockLifecycleModel.valid_until.is_(None))
            .one()
        )
        assert live.cylinders_count == 8


class TestTheOwnerKeepsTheLastWord:
    def test_override_writes_it(self, db):
        gomes_row(db)
        row = confirm(db, "GKPRF", 5, confirmed_by="Tomas", now=NOW, override=True)
        db.flush()
        assert row.cylinders_count == 5

    def test_override_leaves_a_mark(self, db):
        """
        Without this the new row looks like any other rubric confirmation, and
        nobody can later tell that Gomes had said something else.
        """
        gomes_row(db)
        row = confirm(db, "GKPRF", 5, confirmed_by="Tomas", now=NOW, override=True)
        db.flush()
        assert row.phase_signals["overrode_source"] == "gomes_video_2026-08-21"
        assert row.phase_signals["overrode_cylinders"] == 10

    def test_an_ordinary_confirmation_carries_no_such_mark(self, db):
        confirm(db, "CXDO", 7, confirmed_by="Tomas", now=NOW)
        db.flush()
        confirm(db, "CXDO", 8, confirmed_by="Tomas",
                now=NOW + timedelta(days=1), override=True)
        db.flush()
        live = (
            db.query(StockLifecycleModel)
            .filter(StockLifecycleModel.valid_until.is_(None))
            .one()
        )
        assert "overrode_source" not in (live.phase_signals or {})


class TestProvenanceSurvivesAPhaseWrite:
    def test_writing_a_phase_does_not_restamp_the_source(self, db):
        """
        `lifecycle_intake.confirm` mutates the live row in place and used to set
        `source = lifecycle_rubric` unconditionally. After that line the row no
        longer looked like an analyst row, which defeated the guard above — the
        next rubric write would sail straight through.
        """
        from app.services.lifecycle_intake import confirm as confirm_phase

        gomes_row(db)
        confirm_phase(db, "GKPRF", "GOLD_MINE", confirmed_by="Tomas", now=NOW)
        db.flush()

        live = (
            db.query(StockLifecycleModel)
            .filter(StockLifecycleModel.valid_until.is_(None))
            .one()
        )
        assert live.phase == "GOLD_MINE"
        assert live.source == "gomes_video_2026-08-21"
        assert lifecycle_source_rank(live.source) == RANK_ANALYST
