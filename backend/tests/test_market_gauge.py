"""
Tests for the assisted semafor reading.

The module makes two specific claims about its own accuracy, both of which
appear in text the user reads, so both are pinned here against a fixture of the
real series rather than left as prose:

* end of 1999 is the top of the whole 41-year window — the canon's first RED
* middle of 2007 is an unremarkable month — the canon's second RED, missed

If a later change to the fit quietly breaks either, the claim in the docstring
becomes false and these fail. That matters more than usual: a gauge that
overstates its own reliability is precisely the failure this codebase exists to
avoid, and it would do it in the one place the user is deciding whether to
trust it.
"""

import csv
import pathlib
from datetime import date

import pytest

from app.services.market_gauge import (
    EXPENSIVE_Z,
    LOWER_LINE_Z,
    UPPER_LINE_Z,
    ChannelPosition,
    GaugeError,
    agreement_cs,
    classify,
    fit,
)


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


# ==============================================================================
# The two calls the canon names
# ==============================================================================

class TestAgainstTheCanonsTwoRedAlerts:
    """
    Gomes says he has called RED twice: the end of 1999 and the middle of 2007.
    A valuation gauge that cannot find either is useless; one that claims to
    find both when it finds one is worse than useless.
    """

    def _residual_ranking(self, series):
        """Every month's distance from the single 41-year trend, ranked."""
        import math
        import statistics

        xs = list(range(len(series)))
        ys = [math.log(close) for _, close in series]
        n = len(xs)
        mean_x, mean_y = sum(xs) / n, sum(ys) / n
        slope = sum(
            (x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)
        ) / sum((x - mean_x) ** 2 for x in xs)
        intercept = mean_y - slope * mean_x
        residuals = [y - (intercept + slope * x) for x, y in zip(xs, ys)]
        sigma = statistics.pstdev(residuals)
        return {
            month: residual / sigma
            for (month, _), residual in zip(series, residuals)
        }

    def test_the_end_of_1999_is_the_top_of_the_whole_series(self, series):
        """The first RED, and the gauge finds it decisively."""
        z = self._residual_ranking(series)
        top_two = sorted(z, key=lambda m: -z[m])[:2]

        assert all(m.year in (1999, 2000) for m in top_two), top_two
        assert z[date(1999, 12, 1)] > UPPER_LINE_Z

    def test_the_middle_of_2007_is_an_unremarkable_month(self, series):
        """
        The second RED, and the gauge misses it entirely. This is asserted, not
        apologised for: the module's own text says so, and if a later change
        made 2007 light up, that text would be wrong.
        """
        z = self._residual_ranking(series)
        june_2007 = z[date(2007, 6, 1)]

        assert june_2007 < EXPENSIVE_Z, (
            f"2007-06 vyšlo na {june_2007:+.2f} — pokud to teď ukazatel vidí, "
            f"je potřeba přepsat BLIND_SPOT_CS, který tvrdí opak."
        )
        assert classify(june_2007) is not ChannelPosition.AT_UPPER_LINE

    def test_early_2009_is_the_bottom(self, series):
        """The generational buying opportunity, at the other end."""
        z = self._residual_ranking(series)
        bottom = min(z, key=lambda m: z[m])

        assert bottom.year == 2009
        assert z[bottom] < LOWER_LINE_Z

    def test_the_blind_spot_is_stated_in_every_reading(self, series):
        reading = fit(series)

        assert "2007" in reading.blind_spot_cs
        assert "1999" in reading.blind_spot_cs


# ==============================================================================
# The fit
# ==============================================================================

class TestFit:
    def test_the_window_is_the_forty_year_chart(self, series):
        reading = fit(series)
        assert reading.years > 40

    def test_the_lines_are_ordered(self, series):
        reading = fit(series)
        assert reading.lower_line < reading.grey_line < reading.upper_line

    def test_the_grey_line_is_the_trend(self, series):
        reading = fit(series)
        assert reading.grey_line == pytest.approx(reading.trend_value)

    def test_the_long_run_slope_is_plausible(self, series):
        """
        A price-only S&P trend of roughly 7-8 % a year. Far outside that and
        the fit has gone wrong, whatever the z-score says.
        """
        assert 5.0 < fit(series).trend_pct_per_year < 11.0

    def test_todays_reading_is_above_trend_but_not_at_the_line(self, series):
        """Pinned to the fixture: 2026-08 sits at +1.46."""
        reading = fit(series)
        assert reading.z_score == pytest.approx(1.46, abs=0.02)
        assert reading.position is ChannelPosition.EXPENSIVE
        assert reading.suggested_alert == "YELLOW"


class TestRefusals:
    """A gauge that cannot be computed must say so, never default to GREEN."""

    def test_too_little_history_is_refused(self, series):
        with pytest.raises(GaugeError, match="40letý graf"):
            fit(series[-120:])

    def test_an_empty_series_is_refused(self):
        with pytest.raises(GaugeError):
            fit([])

    def test_a_non_positive_close_is_a_data_fault_not_a_valuation(self, series):
        broken = list(series)
        broken[100] = (broken[100][0], 0.0)
        with pytest.raises(GaugeError, match="chyba dat"):
            fit(broken)

    def test_a_flat_series_has_no_channel(self):
        points = [(date(1985 + i // 12, i % 12 + 1, 1), 100.0) for i in range(400)]
        with pytest.raises(GaugeError, match="rozptyl"):
            fit(points)


# ==============================================================================
# It suggests; it never sets
# ==============================================================================

class TestSuggestionNotVerdict:
    def test_the_upper_line_suggests_orange_not_red(self):
        """
        RED is twice in a lifetime and one of those twice this gauge cannot
        see. Proposing it from valuation alone would claim a certainty the
        measure has not earned.
        """
        assert classify(3.0) is ChannelPosition.AT_UPPER_LINE
        from app.services.market_gauge import POSITION_ALERT

        assert POSITION_ALERT[ChannelPosition.AT_UPPER_LINE] == "ORANGE"
        assert "RED" not in set(POSITION_ALERT.values())

    def test_agreement_is_reported_when_they_match(self, series):
        assert "sedí" in agreement_cs(fit(series), "YELLOW")

    def test_disagreement_is_reported_and_left_to_the_user(self, series):
        text = agreement_cs(fit(series), "GREEN")
        assert "GREEN" in text and "YELLOW" in text
        assert "automaticky" in text

    def test_an_unset_semafor_is_not_treated_as_agreement(self, series):
        """
        "Nobody set it" and "it agrees" are the same empty field and must not
        render alike — that is how a default GREEN authorises purchases.
        """
        text = agreement_cs(fit(series), None)
        assert "není nastavený" in text

    def test_case_does_not_create_a_false_disagreement(self, series):
        assert "sedí" in agreement_cs(fit(series), "yellow")


class TestClassification:
    @pytest.mark.parametrize("z,expected", [
        (3.0, ChannelPosition.AT_UPPER_LINE),
        (2.5, ChannelPosition.AT_UPPER_LINE),
        (1.5, ChannelPosition.EXPENSIVE),
        (1.0, ChannelPosition.EXPENSIVE),
        (0.5, ChannelPosition.ABOVE_TREND),
        (0.0, ChannelPosition.ABOVE_TREND),
        (-1.0, ChannelPosition.BELOW_GREY),
        (-2.0, ChannelPosition.AT_LOWER_LINE),
        (-3.0, ChannelPosition.AT_LOWER_LINE),
    ])
    def test_bands(self, z, expected):
        assert classify(z) is expected

    def test_every_position_has_a_czech_note_and_an_alert(self):
        from app.services.market_gauge import POSITION_ALERT, POSITION_CS

        for position in ChannelPosition:
            assert POSITION_CS[position]
            assert POSITION_ALERT[position]
