"""
The ratchet has to survive being written to the database.

`app/services/lifecycle_rubric.py` decides what the stage is; its own tests
cover that. This is about the other half — `classify_stock_lifecycle` does not
UPDATE the live row, it retires it and inserts a new one, so anything the
ratchet depends on has to be copied across by hand or it is gone.

That is not a hypothetical. `stock_lifecycle.phase_reached` is the entire memory
behind §V1: without it a proven Gold Mine drops back to Wait Time the first time
a stream says "delays" or "lawsuit" — the vocabulary of a rough patch is exactly
`WAIT_TIME_SIGNALS` — and `GomesGatekeeper` then refuses to buy it at the moment
it is cheapest. A high-water mark silently reset by a routine transcript run
gives back precisely the failure the column was added to close.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.gomes import StockLifecycleModel
from app.models.stock import Stock
from app.services.gomes_intelligence import GomesIntelligenceService

#: Two Gold Mine phrases: enough for the keyword vote to carry (>= 2).
PROVEN = "TPCS is profitable and posted record revenue this quarter."

#: Two Wait Time phrases — and both are rough-patch vocabulary, which is the
#: whole point. Gomes: a proven company having a bad run has NOT gone back.
BAD_RUN = "TPCS missed guidance and there are execution problems at TPCS."

#: The same two phrases about a company that never proved anything. The
#: classifier scopes evidence to sentences naming the company, so the ticker has
#: to be in the text — a phrase said about somebody else is not evidence here.
BAD_RUN_XXXX = "XXXX missed guidance and there are execution problems at XXXX."


@compiles(JSONB, "sqlite")
def _jsonb(type_, compiler, **kw):  # noqa: ARG001
    """The signals column is JSONB; sqlite calls the same thing JSON."""
    return "JSON"


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(
        engine, tables=[Stock.__table__, StockLifecycleModel.__table__]
    )
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


def live(db) -> StockLifecycleModel:
    """The row the rest of the app reads."""
    return (
        db.query(StockLifecycleModel)
        .filter(StockLifecycleModel.valid_until.is_(None))
        .one()
    )


class TestTheHighWaterMarkSurvivesAReclassification:
    def test_a_first_reading_records_what_it_reached(self, db):
        GomesIntelligenceService(db).classify_stock_lifecycle("TPCS", PROVEN)

        row = live(db)
        assert row.phase == "GOLD_MINE"
        assert row.phase_reached == "GOLD_MINE"

    def test_a_bad_quarter_does_not_demote_a_proven_company(self, db):
        service = GomesIntelligenceService(db)
        service.classify_stock_lifecycle("TPCS", PROVEN)

        service.classify_stock_lifecycle("TPCS", BAD_RUN)

        row = live(db)
        assert row.phase == "GOLD_MINE"
        assert row.phase_reached == "GOLD_MINE"

    def test_the_blocked_reading_is_kept_as_a_rough_patch(self, db):
        """
        The Wait Time reading is a real observation that the business slowed. It
        stops being a stage and becomes a flag — nothing is thrown away.
        """
        service = GomesIntelligenceService(db)
        service.classify_stock_lifecycle("TPCS", PROVEN)

        service.classify_stock_lifecycle("TPCS", BAD_RUN)

        row = live(db)
        assert row.rough_patch is True
        assert row.rough_patch_since is not None
        assert row.rough_patch_note

    def test_the_slowdown_keeps_its_original_date(self, db):
        """
        Set once. A slowdown re-detected on the next transcript is the same
        slowdown, and restamping it would keep moving it past the cylinder
        confirmation it exists to invalidate — quietly re-authorising the very
        purchase the flag is there to stop.
        """
        service = GomesIntelligenceService(db)
        service.classify_stock_lifecycle("TPCS", PROVEN)
        service.classify_stock_lifecycle("TPCS", BAD_RUN)
        first = live(db).rough_patch_since

        service.classify_stock_lifecycle("TPCS", BAD_RUN)

        assert live(db).rough_patch_since == first

    def test_a_transcript_that_says_nothing_does_not_erase_the_stage(self, db):
        """
        Silence is not a demotion. A stream that never mentions the company
        votes UNKNOWN, and writing that over a recorded stage would lose what is
        known because nobody happened to bring it up.
        """
        service = GomesIntelligenceService(db)
        service.classify_stock_lifecycle("TPCS", PROVEN)

        service.classify_stock_lifecycle("TPCS", "Nothing about this company.")

        row = live(db)
        assert row.phase == "GOLD_MINE"
        assert row.phase_reached == "GOLD_MINE"

    def test_a_rough_patch_is_not_cleared_by_this_path(self, db):
        """
        Clearing it declares a slowdown over, and the evidence here is keyword
        votes over a transcript — the weakest the app has. It is cleared in
        `lifecycle_intake.confirm`, on filed numbers the owner confirmed. Weak
        data may make this app more careful, never less.
        """
        service = GomesIntelligenceService(db)
        service.classify_stock_lifecycle("TPCS", PROVEN)
        service.classify_stock_lifecycle("TPCS", BAD_RUN)

        service.classify_stock_lifecycle("TPCS", "Nothing about this company.")

        assert live(db).rough_patch is True


class TestTheStageStillMovesForward:
    def test_an_unproven_company_may_become_wait_time(self, db):
        GomesIntelligenceService(db).classify_stock_lifecycle("XXXX", BAD_RUN_XXXX)

        row = live(db)
        assert row.phase == "WAIT_TIME"
        assert row.phase_reached == "WAIT_TIME"
        assert row.rough_patch is False

    def test_wait_time_is_promoted_when_the_story_catches(self, db):
        service = GomesIntelligenceService(db)
        service.classify_stock_lifecycle("XXXX", BAD_RUN_XXXX)

        service.classify_stock_lifecycle(
            "XXXX", "XXXX is profitable with record revenue."
        )

        row = live(db)
        assert row.phase == "GOLD_MINE"
        assert row.phase_reached == "GOLD_MINE"

    def test_an_unreadable_first_reading_sets_no_floor(self, db):
        """
        UNKNOWN is the absence of a reading, not a rung. Recorded as a
        high-water mark it would be a floor made out of ignorance.
        """
        GomesIntelligenceService(db).classify_stock_lifecycle("XXXX", "")

        row = live(db)
        assert row.phase == "UNKNOWN"
        assert row.phase_reached is None


class TestOnlyOneRowIsLive:
    def test_the_previous_reading_is_retired_not_deleted(self, db):
        service = GomesIntelligenceService(db)
        service.classify_stock_lifecycle("TPCS", PROVEN)
        service.classify_stock_lifecycle("TPCS", BAD_RUN)

        rows = db.query(StockLifecycleModel).all()
        assert len(rows) == 2
        assert sum(1 for row in rows if row.valid_until is None) == 1
