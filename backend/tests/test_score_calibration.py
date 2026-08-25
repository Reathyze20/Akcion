"""
Tests for the calibration report.

The arithmetic here is a median. What is worth testing is the restraint: for
the first six months of this feature's life every band is empty, and the way
it reports that emptiness is the whole difference between a useful report and
a misleading one.

The sample threshold is tested hardest because it is the only thing standing
between the user and a median of three numbers presented as evidence that the
method works.
"""

from datetime import date
from decimal import Decimal

import app.models  # noqa: F401  — register every mapper
import app.models.trading  # noqa: F401
from app.models.score_outcome import (
    STATUS_EVALUATED,
    STATUS_PENDING,
    STATUS_UNABLE,
)
from app.services.score_calibration import (
    BANDS,
    MIN_SAMPLE,
    Measurement,
    calibrate,
)


def measured(score, excess, ret=None):
    return Measurement(
        conviction_score=score,
        eval_status=STATUS_EVALUATED,
        return_pct=Decimal(str(ret if ret is not None else excess)),
        excess_return_pct=Decimal(str(excess)),
    )


def pending(score, on=date(2026, 9, 22)):
    return Measurement(
        conviction_score=score, eval_status=STATUS_PENDING, expected_on=on
    )


def band(report, label):
    return next(b for b in report.bands if b.label == label)


def enough(score, excess):
    """A band's worth of identical outcomes, so medians are predictable."""
    return [measured(score, excess) for _ in range(MIN_SAMPLE)]


# ==============================================================================
# The restraint
# ==============================================================================

class TestSufficiency:
    def test_an_empty_journal_reports_every_band_as_insufficient(self):
        report = calibrate([], horizon_days=90)

        assert report.sufficient is False
        assert len(report.bands) == len(BANDS)
        assert all(b.median_excess_pct is None for b in report.bands)

    def test_bands_are_present_even_when_empty(self):
        """
        A band that disappears for having no data reads as a band that does not
        exist — and the reader cannot tell which scores were never measured.
        """
        report = calibrate([measured(9, 5)], horizon_days=90)

        assert [b.label for b in report.bands] == [label for _, _, label in BANDS]

    def test_below_the_threshold_no_median_is_reported(self):
        rows = [measured(9, 12) for _ in range(MIN_SAMPLE - 1)]

        report = calibrate(rows, horizon_days=90)

        top = band(report, "9–10")
        assert top.n_evaluated == MIN_SAMPLE - 1
        assert top.sufficient is False
        assert top.median_excess_pct is None
        assert report.sufficient is False

    def test_at_the_threshold_the_median_appears(self):
        report = calibrate(enough(9, 12), horizon_days=90)

        top = band(report, "9–10")
        assert top.sufficient is True
        assert top.median_excess_pct == Decimal("12.0000")
        assert report.sufficient is True

    def test_one_sufficient_band_is_enough_for_the_report(self):
        rows = enough(9, 12) + [measured(4, -3)]

        report = calibrate(rows, horizon_days=90)

        assert report.sufficient is True
        assert band(report, "4–6").sufficient is False
        assert band(report, "4–6").median_excess_pct is None


# ==============================================================================
# What the report says while it waits
# ==============================================================================

class TestPending:
    def test_counts_pending_separately_from_measured(self):
        report = calibrate([pending(9), pending(9), measured(9, 4)], horizon_days=30)

        top = band(report, "9–10")
        assert top.n_pending == 2
        assert top.n_evaluated == 1

    def test_reports_when_the_first_answer_arrives(self):
        """
        "Nothing yet" and "the first answer is due on this date" are different
        things to tell someone who is waiting six months.
        """
        report = calibrate(
            [pending(9, date(2026, 11, 21)), pending(5, date(2026, 9, 22))],
            horizon_days=90,
        )

        assert report.first_result_expected == date(2026, 9, 22)

    def test_no_pending_rows_means_no_expected_date(self):
        report = calibrate([measured(9, 4)], horizon_days=90)

        assert report.first_result_expected is None

    def test_unable_rows_are_counted_and_never_averaged_in(self):
        rows = enough(9, 10) + [
            Measurement(conviction_score=9, eval_status=STATUS_UNABLE)
        ]

        report = calibrate(rows, horizon_days=90)

        top = band(report, "9–10")
        assert top.n_unable == 1
        assert top.n_evaluated == MIN_SAMPLE
        assert top.median_excess_pct == Decimal("10.0000")


# ==============================================================================
# The finding the report exists to surface
# ==============================================================================

class TestBands:
    def test_bands_can_come_out_in_the_wrong_order(self):
        """
        The report has to be able to say the method is not working. If nines
        underperform fives, nothing here should smooth that over.
        """
        rows = enough(9, -8) + enough(5, 6)

        report = calibrate(rows, horizon_days=365)

        assert band(report, "9–10").median_excess_pct == Decimal("-8.0000")
        assert band(report, "4–6").median_excess_pct == Decimal("6.0000")

    def test_scores_land_in_the_right_band(self):
        rows = enough(10, 1) + enough(8, 2) + enough(6, 3) + enough(0, 4)

        report = calibrate(rows, horizon_days=90)

        assert band(report, "9–10").median_excess_pct == Decimal("1.0000")
        assert band(report, "7–8").median_excess_pct == Decimal("2.0000")
        assert band(report, "4–6").median_excess_pct == Decimal("3.0000")
        assert band(report, "0–3").median_excess_pct == Decimal("4.0000")

    def test_share_positive_counts_only_wins(self):
        rows = [measured(9, 5) for _ in range(6)] + [
            measured(9, -5) for _ in range(4)
        ]

        report = calibrate(rows, horizon_days=90)

        assert band(report, "9–10").share_positive_excess == Decimal("0.6000")

    def test_absolute_and_excess_are_both_reported(self):
        rows = [measured(9, excess=2, ret=11) for _ in range(MIN_SAMPLE)]

        report = calibrate(rows, horizon_days=90)

        top = band(report, "9–10")
        assert top.median_excess_pct == Decimal("2.0000")
        assert top.median_return_pct == Decimal("11.0000")

    def test_outcomes_without_a_benchmark_keep_their_absolute_median(self):
        """
        A missing ^GSPC window empties the excess but not the return. The band
        says how many of its rows actually carry a benchmark.
        """
        rows = [
            Measurement(
                conviction_score=9,
                eval_status=STATUS_EVALUATED,
                return_pct=Decimal("7"),
                excess_return_pct=None,
            )
            for _ in range(MIN_SAMPLE)
        ]

        report = calibrate(rows, horizon_days=90)

        top = band(report, "9–10")
        assert top.n_with_benchmark == 0
        assert top.median_excess_pct is None
        assert top.median_return_pct == Decimal("7.0000")


# ==============================================================================
# Serialisation
# ==============================================================================

class TestAsDict:
    def test_decimals_become_floats_and_nulls_survive(self):
        report = calibrate(enough(9, 3), horizon_days=90).as_dict()

        assert report["horizon_days"] == 90
        assert report["min_sample"] == MIN_SAMPLE
        top = report["bands"][0]
        assert top["median_excess_pct"] == 3.0
        assert top["median_return_pct"] == 3.0
        assert report["bands"][1]["median_excess_pct"] is None
        assert report["first_result_expected"] is None
