"""
Tests for the measurement of past conviction scores.

The arithmetic is trivial; what is worth testing is everything the arithmetic
must refuse to do. A missing baseline, a delisted ticker, a horizon that has
not elapsed and a zero price all have to come out as a named absence, because
each of them would otherwise come out as 0 % — a number indistinguishable from
"the score was exactly right about nothing happening".

The immutability test matters for a different reason: an outcome is a record
of a prediction that was already judged. If a later run could rewrite it, the
app's history of being wrong would quietly improve over time.
"""

from datetime import date
from decimal import Decimal

import pytest

import app.models  # noqa: F401  — register every mapper before the models load
import app.models.trading  # noqa: F401
from app.models.score_outcome import (
    STATUS_EVALUATED,
    STATUS_PENDING,
    STATUS_UNABLE,
)
from app.services.score_outcomes import (
    BASELINE_CLOSE,
    BASELINE_JOURNAL,
    HORIZONS,
    REASON_NO_BASELINE,
    REASON_NO_FORWARD_BAR,
    REASON_ZERO_BASELINE,
    Evaluation,
    evaluate,
    span_for,
    to_bars,
)


RECORDED = date(2026, 1, 5)


def bars(*pairs):
    return [(when, Decimal(str(close))) for when, close in pairs]


#: A stock that went 100 -> 110 over the first 30 days, and the index 100 -> 104.
TICKER_BARS = bars(
    (date(2026, 1, 5), 100),
    (date(2026, 2, 4), 110),
    (date(2026, 4, 6), 130),
)
BENCH_BARS = bars(
    (date(2026, 1, 5), 100),
    (date(2026, 2, 4), 104),
    (date(2026, 4, 6), 108),
)


def evaluate_30d(**overrides) -> Evaluation:
    kwargs = dict(
        recorded_on=RECORDED,
        horizon_days=30,
        journal_price=Decimal("100"),
        ticker_bars=TICKER_BARS,
        benchmark_bars=BENCH_BARS,
        today=date(2026, 8, 23),
    )
    kwargs.update(overrides)
    return evaluate(**kwargs)


# ==============================================================================
# The measurement itself
# ==============================================================================

class TestMeasurement:
    def test_return_and_excess_on_known_numbers(self):
        """100 -> 110 is +10 %, against an index that did +4 %, so +6 % excess."""
        result = evaluate_30d()

        assert result.eval_status == STATUS_EVALUATED
        assert result.return_pct == Decimal("10.0000")
        assert result.benchmark_return_pct == Decimal("4.0000")
        assert result.excess_return_pct == Decimal("6.0000")
        assert result.end_date == date(2026, 2, 4)

    def test_a_loss_that_still_beats_the_index(self):
        """
        The reason excess is the headline. Down 10 % is not automatically bad
        advice, and up 5 % is not automatically good — only the gap says which.
        """
        falling = bars((date(2026, 1, 5), 100), (date(2026, 2, 4), 90))
        crashing = bars((date(2026, 1, 5), 100), (date(2026, 2, 4), 80))

        result = evaluate_30d(ticker_bars=falling, benchmark_bars=crashing)

        assert result.return_pct == Decimal("-10.0000")
        assert result.excess_return_pct == Decimal("10.0000")

    def test_the_horizon_lands_on_the_next_available_bar(self):
        """Horizons fall on weekends; the first bar at or after the target wins."""
        result = evaluate_30d(
            ticker_bars=bars((date(2026, 1, 5), 100), (date(2026, 2, 9), 110))
        )

        assert result.end_date == date(2026, 2, 9)

    def test_every_horizon_is_supported(self):
        for horizon in HORIZONS:
            result = evaluate_30d(horizon_days=horizon, today=date(2027, 12, 31))
            assert result.eval_status in {STATUS_EVALUATED, STATUS_UNABLE}


# ==============================================================================
# Baselines
# ==============================================================================

class TestBaseline:
    def test_the_journal_price_is_preferred(self):
        result = evaluate_30d(journal_price=Decimal("50"))

        assert result.baseline_source == BASELINE_JOURNAL
        assert result.baseline_price == Decimal("50")
        assert result.return_pct == Decimal("120.0000")

    def test_a_missing_journal_price_is_recovered_from_the_close(self):
        """
        Why a NULL price in the journal is not a lost measurement — most of
        them come back, and from a better number than the snapshot would have
        been.
        """
        result = evaluate_30d(journal_price=None)

        assert result.eval_status == STATUS_EVALUATED
        assert result.baseline_source == BASELINE_CLOSE
        assert result.baseline_price == Decimal("100")

    def test_no_baseline_anywhere_is_unable_not_zero(self):
        result = evaluate_30d(
            journal_price=None,
            ticker_bars=bars((date(2026, 2, 4), 110)),  # nothing on or before
        )

        assert result.eval_status == STATUS_UNABLE
        assert result.unable_reason == REASON_NO_BASELINE
        assert result.return_pct is None

    def test_a_zero_baseline_is_unable_not_minus_one_hundred(self):
        """
        Dividing by zero is not a total loss, it is an unusable denominator.
        The distinction decides whether the app reports a catastrophe it never
        measured.
        """
        result = evaluate_30d(journal_price=Decimal("0"))

        assert result.eval_status == STATUS_UNABLE
        assert result.unable_reason == REASON_ZERO_BASELINE
        assert result.return_pct is None


# ==============================================================================
# Absences
# ==============================================================================

class TestAbsences:
    def test_an_unelapsed_horizon_is_pending(self):
        """The state of almost every row for the first year. Not a failure."""
        result = evaluate_30d(today=date(2026, 1, 20))

        assert result.eval_status == STATUS_PENDING
        assert result.return_pct is None
        assert result.unable_reason is None

    def test_pending_is_decided_before_anything_else(self):
        """A horizon in the future cannot be 'unable' — nothing was tried yet."""
        result = evaluate_30d(today=date(2026, 1, 20), journal_price=None, ticker_bars=[])

        assert result.eval_status == STATUS_PENDING

    def test_a_delisted_ticker_is_unable(self):
        result = evaluate_30d(
            ticker_bars=bars((date(2026, 1, 5), 100)),  # nothing after the target
        )

        assert result.eval_status == STATUS_UNABLE
        assert result.unable_reason == REASON_NO_FORWARD_BAR
        assert result.baseline_price == Decimal("100")  # what was known is kept

    def test_a_horizon_maturing_today_waits_for_the_close(self):
        """
        Today's bar is a partial session while the market is open. Measuring
        against it would freeze an intraday price into an outcome that is never
        recomputed — so the horizon waits one more day instead.
        """
        result = evaluate_30d(today=date(2026, 2, 4))  # target is exactly today

        assert result.eval_status == STATUS_PENDING

    def test_todays_bar_is_never_the_end_price(self):
        """
        Target has passed, but the only bar at or after it is today's — still
        open, so still not usable. Waiting, not failure.
        """
        result = evaluate_30d(
            today=date(2026, 2, 5),
            ticker_bars=bars((date(2026, 1, 5), 100), (date(2026, 2, 5), 999)),
        )

        assert result.eval_status == STATUS_PENDING

    def test_the_same_bar_is_used_once_it_has_closed(self):
        """The day after, that bar is a completed session and gets measured."""
        result = evaluate_30d(
            today=date(2026, 2, 6),
            ticker_bars=bars((date(2026, 1, 5), 100), (date(2026, 2, 5), 999)),
        )

        assert result.eval_status == STATUS_EVALUATED
        assert result.end_date == date(2026, 2, 5)

    def test_a_weekend_target_waits_rather_than_failing(self):
        """
        A horizon landing on a Saturday has no bar for days. That is the market
        being shut, not the ticker being gone, and retiring the measurement as
        `unable` would throw away one that is about to arrive.
        """
        result = evaluate_30d(
            today=date(2026, 2, 6),
            ticker_bars=bars((date(2026, 1, 5), 100)),
        )

        assert result.eval_status == STATUS_PENDING

    def test_after_the_settle_window_a_silent_ticker_is_unable(self):
        """Past the grace window, no bar means delisted — and it says so."""
        result = evaluate_30d(
            today=date(2026, 3, 1),
            ticker_bars=bars((date(2026, 1, 5), 100)),
        )

        assert result.eval_status == STATUS_UNABLE
        assert result.unable_reason == REASON_NO_FORWARD_BAR

    def test_the_run_time_of_day_does_not_change_the_answer(self):
        """
        The whole point of excluding open sessions: the scheduled job can fire
        at any hour and produce the same measurement.
        """
        settled = evaluate_30d(today=date(2026, 2, 6))

        assert settled.eval_status == STATUS_EVALUATED
        assert settled.end_date == date(2026, 2, 4)

    def test_a_missing_benchmark_keeps_the_absolute_return(self):
        """
        The stock's own return is a real measurement and is not thrown away
        because the index could not be read. Only the excess goes empty.
        """
        result = evaluate_30d(benchmark_bars=[])

        assert result.eval_status == STATUS_EVALUATED
        assert result.return_pct == Decimal("10.0000")
        assert result.benchmark_return_pct is None
        assert result.excess_return_pct is None


# ==============================================================================
# Bar handling
# ==============================================================================

class TestBars:
    def test_unreadable_rows_are_dropped_not_defaulted(self):
        """A fabricated bar would land straight in a return calculation."""
        result = to_bars(
            [
                (date(2026, 1, 5), 100),
                (date(2026, 1, 6), None),
                (None, 105),
                (date(2026, 1, 7), "nonsense"),
            ]
        )

        assert result == [(date(2026, 1, 5), Decimal("100"))]

    def test_bars_come_back_sorted(self):
        result = to_bars([(date(2026, 2, 4), 110), (date(2026, 1, 5), 100)])

        assert [bar[0] for bar in result] == [date(2026, 1, 5), date(2026, 2, 4)]

    def test_span_covers_the_longest_horizon_with_lead_in(self):
        start, end = span_for(date(2026, 1, 5), today=date(2027, 12, 31))

        assert start < date(2026, 1, 5)
        assert (end - date(2026, 1, 5)).days >= max(HORIZONS)

    def test_span_never_asks_for_bars_from_the_future(self):
        start, end = span_for(date(2026, 8, 1), today=date(2026, 8, 23))

        assert end == date(2026, 8, 23)


# ==============================================================================
# The run
# ==============================================================================

class TestEvaluateAll:
    """
    Exercised against a real sqlite session: the run is mostly about which rows
    it decides to touch, which a mock would not tell us anything about.
    """

    @pytest.fixture
    def db(self):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        from app.models.base import Base
        from app.models.score_history import ConvictionScoreHistory
        from app.models.score_outcome import ScoreOutcome
        from app.models.stock import Stock

        engine = create_engine("sqlite://")
        Base.metadata.create_all(
            engine,
            tables=[
                Stock.__table__,
                ConvictionScoreHistory.__table__,
                ScoreOutcome.__table__,
            ],
        )
        session = sessionmaker(bind=engine)()
        try:
            yield session
        finally:
            session.close()

    def _journal(self, db, price="100"):
        from app.models.score_history import ConvictionScoreHistory

        entry = ConvictionScoreHistory(
            ticker="TEST",
            conviction_score=9,
            price_at_analysis=Decimal(price) if price else None,
            analysis_source="seed",
            recorded_at=RECORDED,
        )
        db.add(entry)
        db.commit()
        return entry

    def _fetch(self, ticker, start, end):
        return BENCH_BARS if ticker.startswith("^") else TICKER_BARS

    def test_writes_one_row_per_horizon(self, db):
        from app.models.score_outcome import ScoreOutcome
        from app.services.score_outcomes import evaluate_all

        self._journal(db)
        summary = evaluate_all(db, today=date(2026, 8, 23), fetch=self._fetch)
        db.commit()

        assert db.query(ScoreOutcome).count() == len(HORIZONS)
        assert summary.written == len(HORIZONS)

    def test_a_measured_outcome_is_never_recomputed(self, db):
        """
        An outcome is a record of a prediction that was already judged. If a
        rerun could rewrite it, the app's history of being wrong would improve
        on its own.
        """
        from app.models.score_outcome import ScoreOutcome
        from app.services.score_outcomes import evaluate_all

        self._journal(db)
        evaluate_all(db, today=date(2026, 8, 23), fetch=self._fetch)
        db.commit()

        measured = (
            db.query(ScoreOutcome)
            .filter(ScoreOutcome.eval_status == STATUS_EVALUATED)
            .first()
        )
        assert measured is not None
        original = measured.return_pct

        def different_history(ticker, start, end):
            if ticker.startswith("^"):
                return BENCH_BARS
            return bars((date(2026, 1, 5), 100), (date(2026, 2, 4), 999))

        evaluate_all(db, today=date(2026, 8, 23), fetch=different_history)
        db.commit()

        db.refresh(measured)
        assert measured.return_pct == original

    def test_pending_rows_are_recomputed_as_horizons_elapse(self, db):
        from app.models.score_outcome import ScoreOutcome
        from app.services.score_outcomes import evaluate_all

        self._journal(db)
        evaluate_all(db, today=date(2026, 1, 10), fetch=self._fetch)
        db.commit()

        assert db.query(ScoreOutcome).filter(
            ScoreOutcome.eval_status == STATUS_PENDING
        ).count() == len(HORIZONS)

        evaluate_all(db, today=date(2026, 8, 23), fetch=self._fetch)
        db.commit()

        assert db.query(ScoreOutcome).filter(
            ScoreOutcome.eval_status == STATUS_EVALUATED
        ).count() >= 1
        assert db.query(ScoreOutcome).count() == len(HORIZONS)

    def test_a_ticker_with_no_bars_is_reported_not_silently_skipped(self, db):
        from app.services.score_outcomes import evaluate_all

        self._journal(db, price=None)
        summary = evaluate_all(
            db, today=date(2026, 8, 23), fetch=lambda t, s, e: []
        )
        db.commit()

        assert "TEST" in summary.tickers_without_bars
        assert summary.unable >= 1
        assert summary.evaluated == 0

    def test_an_empty_journal_does_nothing(self, db):
        from app.services.score_outcomes import evaluate_all

        summary = evaluate_all(db, today=date(2026, 8, 23), fetch=self._fetch)

        assert summary.scanned == 0
        assert summary.written == 0
