"""
The assisted semafor, read as of a past date and scored against Mark's own calls.

A separate file from `test_market_gauge.py` on purpose. That one fails when the
fit breaks. This one fails when the gauge's measured agreement with the person
whose method it reproduces changes — a different fact, and mixing them would
make one regression look like the other.

The scorecard is pinned as a characterisation, not as a bar. `assert accuracy >=
0.6` on eleven events is a number somebody made up: it would either always pass
or block a real improvement. What is worth pinning is that we know exactly how
good this is, which is the same thing the sibling file does by pinning mid-2007
as a documented failure.

No network. Uses the committed ^GSPC fixture.
"""

import csv
import pathlib
from datetime import date

import pytest

from app.services.market_gauge import EXPENSIVE_Z, MIN_YEARS, GaugeError, fit
from research.gauge_events import load_events, score

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "gspc_monthly.csv"


@pytest.fixture(scope="module")
def series() -> list[tuple[date, float]]:
    """The real ^GSPC monthly closes, pinned 2026-08-23."""
    points = []
    with FIXTURE.open(encoding="utf-8") as handle:
        for row in csv.reader(line for line in handle if not line.startswith("#")):
            if row[0] == "date":
                continue
            points.append((date.fromisoformat(row[0]), float(row[1])))
    return points


@pytest.fixture(scope="module")
def scored(series):
    return score(series, load_events())


# ==============================================================================
# That as_of means what it says
# ==============================================================================

class TestAsOfDoesNotPeek:
    """
    The one assertion in this file worth more than the rest together.

    An as-of reading that can see the future is not wrong by a little; it is a
    machine for producing hindsight and calling it calibration.
    """

    def test_future_points_cannot_change_a_past_reading(self, series):
        cut = date(2016, 4, 28)
        before = fit(series, as_of=cut)

        tampered = [
            (when, close * 3 if when > cut else close) for when, close in series
        ]
        after = fit(tampered, as_of=cut)

        assert after.z_score == before.z_score
        assert after.percentile == before.percentile
        assert after.trend_value == before.trend_value
        assert after.as_of == before.as_of

    def test_the_trend_is_refitted_not_sliced_out_of_the_full_fit(self, series):
        """
        A 2016 reading must not carry 2026's slope.

        Ten more years of a rising market lift the fitted slope, so the two must
        differ. If they ever matched, the truncation would be cosmetic.
        """
        early = fit(series, as_of=date(2016, 4, 28))
        today = fit(series)
        assert early.trend_pct_per_year != today.trend_pct_per_year

    def test_without_as_of_nothing_changed(self, series):
        assert fit(series).as_of == series[-1][0]


class TestMinYearsStillApplies:

    def test_too_early_raises_rather_than_answering(self, series):
        """
        The fixture starts 1985-01, so thirty years land in early 2015.

        Softening `MIN_YEARS` to reach further back is the obvious way to get
        more events, and it is wrong for the reason the module already gives:
        a trend through one regime says nothing about where the market sits in
        its history.
        """
        with pytest.raises(GaugeError) as caught:
            fit(series, as_of=date(2013, 1, 1))
        assert str(int(MIN_YEARS)) in str(caught.value)

    def test_just_past_the_boundary_answers(self, series):
        assert fit(series, as_of=date(2016, 1, 1)).months >= MIN_YEARS * 12


class TestMonthlyResolutionIsReported:

    def test_as_of_lands_on_the_monthly_bar_not_the_requested_day(self, series):
        """
        A query for 14 February 2020 reads the 1 February close.

        The reading cannot be more precise than its input, and saying otherwise
        would let a mid-month crash look like something the gauge saw.
        """
        reading = fit(series, as_of=date(2020, 2, 14))
        assert reading.as_of == date(2020, 2, 1)

    def test_every_scored_event_reports_its_lag(self, scored):
        assert all(0 <= s.lag_days <= 31 for s in scored)


# ==============================================================================
# The scorecard
# ==============================================================================

class TestAgainstMarksOwnCalls:

    def test_all_eleven_events_are_reachable(self, scored):
        """None of them falls before thirty years of history."""
        assert len(scored) == 11

    def test_the_measured_agreement(self, scored):
        """
        Three out of eleven, as of the fixture pinned 2026-08-23.

        Not a bar. A change to this number means the fit changed, and whoever
        changed it should say which way and why.
        """
        assert sum(1 for s in scored if s.agrees) == 3

    def test_the_gauge_finds_none_of_the_six_hedge_openings(self, scored):
        """
        The finding that matters, and it is a failure.

        Every one of the six dates Mark opened an index hedge, the gauge reads
        below `EXPENSIVE_Z` and would have suggested GREEN. Not one near-misses
        into a YELLOW. Whatever made him hedge, it was not this measure.
        """
        opens = [s for s in scored if s.event.label == "HEDGE_OPEN"]
        assert len(opens) == 6
        assert all(s.z_score < EXPENSIVE_Z for s in opens)
        assert all(s.suggested_alert == "GREEN" for s in opens)

    def test_the_failures_split_into_two_different_kinds(self, scored):
        """
        Near-misses and outright disagreements, and the difference is the point.

        The 2021 and 2022 hedges sit in the top fifth of the channel — the gauge
        is reading the same market he is and stopping just short of saying so.
        The 2016 and 2020 hedges sit around the middle: there the gauge is not
        near-missing, it disagrees. February 2020 is the clearest case, and it
        is the same failure as mid-2007 — a top built on something other than
        price against trend, which this measure cannot see by construction.
        """
        opens = {s.event.event_date: s for s in scored if s.event.label == "HEDGE_OPEN"}

        near = [date(2021, 1, 5), date(2022, 2, 3), date(2022, 3, 16)]
        assert all(opens[d].percentile > 80 for d in near)

        disagreed = [date(2016, 4, 28), date(2020, 2, 14), date(2020, 4, 13)]
        assert all(opens[d].percentile < 60 for d in disagreed)

    def test_the_agreements_are_all_on_the_calm_side(self, scored):
        """
        Worth stating plainly: the gauge scores its three hits by saying "not
        expensive" at moments Mark was standing down. It says "not expensive"
        at ten of the eleven events, so agreeing on those three costs it
        nothing. The scorecard is three out of eleven and the three are cheap.
        """
        agreed = [s for s in scored if s.agrees]
        assert all(not s.event.claims_danger for s in agreed)

    def test_the_two_events_that_name_a_level_carry_their_quote(self):
        """Every label is checkable by eye against the sheet it came from."""
        named = [e for e in load_events() if e.claimed_level]
        assert {e.claimed_level for e in named} == {"GREEN", "YELLOW"}
        assert all(e.evidence_quote for e in named)
        assert all(e.evidence_row_id > 0 for e in named)

    def test_this_says_nothing_about_the_upper_line(self, scored):
        """
        `UPPER_LINE_Z = 2.5` selects 1999-2000 and nothing else. No event here
        comes within a mile of it, so this harness carries zero information
        about that constant — and it is exactly the constant somebody with a new
        measuring stick will want to "improve".
        """
        assert max(s.z_score for s in scored) < 2.0
