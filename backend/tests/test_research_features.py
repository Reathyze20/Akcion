"""
What a stock looked like on the day it was bought.

One test in this file is worth more than the rest together: features computed
as of a date must not change when the future changes. Features that can see
forward would place every one of Mark's past entries beautifully and tell you
nothing whatsoever about a candidate today, and the failure would look like
success right up until somebody acted on it.

Everything else here is about the second rule: a window that is not there
produces a named absence, never a number. A twelve-month return computed from
three months is a different quantity wearing the same name, and once it is in
the column nobody can tell it apart.
"""

import math
from datetime import date, timedelta

import pytest

from app.services.entry_features import (
    MIN_COVERAGE,
    PROFILE_FEATURES,
    SESSIONS_12M,
    Bar,
    Bars,
    FeatureError,
    compute,
    outcome,
    to_bars,
)


def synthetic(
    n: int = 400,
    *,
    start: date = date(2023, 1, 2),
    price: float = 10.0,
    step: float = 0.0,
    ticker: str = "ACME",
    volume: int = 100_000,
    spread: float = 0.01,
) -> Bars:
    """`n` consecutive weekday sessions, price moving by `step` each day."""
    rows, day, value = [], start, price
    while len(rows) < n:
        if day.weekday() < 5:
            rows.append(
                Bar(
                    day=day, open=value,
                    high=value * (1 + spread), low=value * (1 - spread),
                    close=value, adj_close=value, volume=volume,
                )
            )
            value += step
        day += timedelta(days=1)
    return to_bars(ticker, rows)


# ==============================================================================
# The one that matters
# ==============================================================================

class TestNoLookahead:

    def test_the_future_cannot_reach_a_past_reading(self):
        """
        Recompute with every later session tripled. Nothing may move.

        This is what makes the comparison honest. If it ever fails, the profile
        is a description of hindsight.
        """
        bars = synthetic(400, price=10.0, step=0.01)
        cut = bars.rows[300].day

        before = compute(bars, cut)
        tampered = to_bars(
            bars.ticker,
            [
                Bar(
                    day=b.day, open=b.open * 3, high=b.high * 3, low=b.low * 3,
                    close=b.close * 3, adj_close=b.adj_close * 3,
                    volume=b.volume * 3,
                ) if b.day > cut else b
                for b in bars.rows
            ],
        )
        after = compute(tampered, cut)

        for name in PROFILE_FEATURES:
            assert before.get(name) == after.get(name), name
        assert before.bar_date == after.bar_date
        assert before.close == after.close

    def test_appending_sessions_cannot_move_a_past_reading(self):
        """The other direction: more history after the fact changes nothing."""
        bars = synthetic(300, step=0.02)
        cut = bars.rows[260].day
        before = compute(bars, cut)

        extra = synthetic(340, step=0.02)
        after = compute(extra, cut)

        for name in PROFILE_FEATURES:
            assert before.get(name) == after.get(name), name


# ==============================================================================
# Absence is named, never zero
# ==============================================================================

class TestMissingIsNamed:

    def test_a_short_history_drops_only_the_windows_it_cannot_support(self):
        """
        A company listed six months ago has a real six-month return.

        Dropping the whole row would bias the sample towards whatever has been
        around longest — which is the opposite of what the profile is for.
        """
        bars = synthetic(140, step=0.01)
        features = compute(bars, bars.last_day)

        assert features.ret_6m_pct is not None
        assert features.ret_12m_pct is None
        assert "ret_12m_pct" in features.missing
        assert features.drawdown_from_52w_high_pct is None
        assert "drawdown_from_52w_high_pct" in features.missing

    def test_a_missing_feature_is_none_and_never_zero(self):
        bars = synthetic(30)
        features = compute(bars, bars.last_day)
        for name in features.missing:
            assert features.get(name) is None

    def test_the_denominator_can_be_trusted(self):
        """
        Whatever is not in `missing` is present, and vice versa. A caller saying
        "five of seven" must be able to get that count right.
        """
        for length in (25, 80, 140, 300):
            features = compute(synthetic(length), synthetic(length).last_day)
            available = set(features.available_profile_features)
            named = set(features.missing)
            assert available.isdisjoint(named)
            assert available | (named & set(PROFILE_FEATURES)) == set(PROFILE_FEATURES)

    def test_a_short_halt_still_yields_features(self):
        """
        Micro-caps genuinely halt. Demanding a complete window would drop names
        that traded perfectly normally, which is why the bar is 80 % and not 100 %.
        """
        bars = synthetic(300, step=0.01)
        keep = [b for i, b in enumerate(bars.rows) if not (250 <= i < 255)]
        gapped = to_bars(bars.ticker, keep)
        features = compute(gapped, gapped.last_day)
        assert features.drawdown_from_52w_high_pct is not None

    def test_a_window_thirty_percent_empty_does_not(self):
        needed = int(SESSIONS_12M * MIN_COVERAGE)
        bars = synthetic(needed - 5, step=0.01)
        features = compute(bars, bars.last_day)
        assert features.drawdown_from_52w_high_pct is None

    def test_no_bars_at_all_raises_rather_than_returning_an_empty_row(self):
        with pytest.raises(FeatureError):
            compute(Bars(ticker="GONE"), date(2024, 1, 1))

    def test_a_date_after_the_last_session_raises(self):
        """Asking about a day the symbol no longer traded is not a zero."""
        bars = synthetic(50)
        with pytest.raises(FeatureError, match="přestalo obchodovat"):
            compute(bars, bars.last_day + timedelta(days=30))


# ==============================================================================
# The numbers themselves
# ==============================================================================

class TestTheArithmetic:

    def test_the_session_used_is_the_first_on_or_after(self):
        """The sheet's date is a day somebody wrote something down."""
        bars = synthetic(300, start=date(2023, 1, 2))
        saturday = date(2023, 6, 3)
        assert saturday.weekday() == 5
        assert compute(bars, saturday).bar_date == date(2023, 6, 5)

    def test_drawdown_from_a_known_high(self):
        """Rise to 20, fall to 15: fifteen is 25 % below the high."""
        rising = synthetic(260, price=10.0, step=10.0 / 259, spread=0.0)
        falling = [
            Bar(day=rising.rows[-1].day + timedelta(days=i + 1),
                open=15.0, high=15.0, low=15.0, close=15.0, adj_close=15.0,
                volume=1000)
            for i in range(3)
        ]
        bars = to_bars("ACME", list(rising.rows) + falling)
        features = compute(bars, bars.last_day)
        assert features.drawdown_from_52w_high_pct == pytest.approx(-25.0, abs=0.5)

    def test_range_position_at_the_bottom_and_the_top(self):
        rising = synthetic(300, price=10.0, step=0.05)
        top = compute(rising, rising.last_day)
        assert top.pct_of_52w_range == pytest.approx(100.0, abs=2.0)

        falling = synthetic(300, price=25.0, step=-0.05)
        bottom = compute(falling, falling.last_day)
        assert bottom.pct_of_52w_range == pytest.approx(0.0, abs=2.0)

    def test_a_flat_series_has_no_range_position(self):
        """Zero span is not zero percent — it is a question with no answer."""
        flat = synthetic(300, price=10.0, step=0.0, spread=0.0)
        features = compute(flat, flat.last_day)
        assert features.pct_of_52w_range is None
        assert "pct_of_52w_range" in features.missing

    def test_volatility_is_zero_on_a_flat_series_and_positive_otherwise(self):
        flat = synthetic(200, step=0.0)
        assert compute(flat, flat.last_day).vol_60d_annualised_pct == (
            pytest.approx(0.0)
        )
        moving = synthetic(200, price=10.0, step=0.05)
        assert compute(moving, moving.last_day).vol_60d_annualised_pct > 0

    def test_dollar_volume_uses_the_median_not_the_mean(self):
        """
        One halted session's print wrecks a mean on a micro-cap, and liquidity
        is exactly what the feature is there to read.
        """
        bars = synthetic(100, price=10.0, volume=1000)
        spiked = list(bars.rows)
        spiked[-1] = Bar(
            day=spiked[-1].day, open=10.0, high=10.0, low=10.0, close=10.0,
            adj_close=10.0, volume=100_000_000,
        )
        features = compute(to_bars("ACME", spiked), spiked[-1].day)
        assert features.median_dollar_volume_20d == pytest.approx(10_000.0)


# ==============================================================================
# Outcomes
# ==============================================================================

class TestOutcome:

    def test_drawup_and_drawdown_from_a_known_path(self):
        """
        The honest replacement for the sheet's "Peak Return While Live", which
        is split-contaminated past repair.
        """
        up = synthetic(100, price=10.0, step=0.1)      # 10 -> ~19.9
        down = [
            Bar(day=up.rows[-1].day + timedelta(days=i + 1),
                open=8.0, high=8.0, low=8.0, close=8.0, adj_close=8.0,
                volume=1000)
            for i in range(5)
        ]
        bars = to_bars("ACME", list(up.rows) + down)
        result = outcome(bars, bars.first_day, bars.last_day)

        assert result.max_drawup_pct == pytest.approx(99.0, abs=2.0)
        assert result.max_drawdown_pct == pytest.approx(-20.0, abs=0.5)
        assert result.ret_to_exit_pct == pytest.approx(-20.0, abs=0.5)

    def test_an_open_position_runs_to_the_last_session(self):
        bars = synthetic(100, price=10.0, step=0.1)
        assert outcome(bars, bars.first_day, None) is not None

    def test_a_single_session_is_not_an_outcome(self):
        bars = synthetic(1)
        assert outcome(bars, bars.first_day, bars.last_day) is None


# ==============================================================================
# Against the real cohort
# ==============================================================================

def test_the_reference_cohort_supports_every_profile_feature():
    """
    Pins what the committed data actually yields: forty modern-era entries,
    each with all six chart features and the market one.

    Not a synthetic check. If a rename, a label or a coverage rule change shrinks
    this, the profile shrinks with it and the number that says so should be here
    rather than in a log nobody reads.
    """
    import csv
    import pathlib

    path = pathlib.Path(__file__).parent.parent / "research" / "out" / "features.csv"
    if not path.exists():
        pytest.skip(
            "research/out/features.csv chybí — spusť `python -m research.features`. "
            "Přeskočeno s důvodem, ne tiše."
        )

    rows = [
        row for row in csv.DictReader(path.open(encoding="utf-8"))
        if row["era"] == "MODERN_LONG"
    ]
    assert len(rows) == 40
    for row in rows:
        for name in PROFILE_FEATURES:
            assert row[name] != "", f"{row['ticker']} {row['row_id']}: {name}"
        assert row["gauge_z_at_entry"] != ""
        assert row["missing"] == ""


def test_the_sheet_exits_above_the_close_and_that_is_the_finding():
    """
    Mark's exit prices are decision prices, and the tape cannot confirm them.

    Recomputing each closed modern-era position from adjusted bars gives a
    return that is LOWER than the sheet's own in 25 of 31 cases, median 6 points
    lower. The biggest gaps land exactly on the rows whose notes name an
    intraday price he sold at — AEHR "R/R @ 12-15 (13.50)" is 170 points apart,
    TSSI "R/R rules say get out around $18-20" is 74, VTSI "Profits (R/R) @ 9"
    is 34.

    So he was not selling at the bell. He was selling into intraday strength at
    a level set in advance, and the close on that day is a different, worse
    number.

    Two things follow, and both constrain everything downstream:

    * The ENTRY side is verifiable and verified — `reconcile.py` matched 40 of
      50 modern rows against the tape's own high/low range.
    * The EXIT side is not verifiable at all. `ret_to_exit_pct` from bars is
      what a holder who slept through the day would have got, not what Mark
      got. Anything about what he EARNED has to use the sheet's figure;
      anything about the PATH (drawup, drawdown) has to use the bars. Mixing
      them produces a number belonging to neither.

    Pinned as a characterisation. It will move when the data moves, and whoever
    moves it should say which way.
    """
    import csv
    import pathlib
    import statistics

    path = pathlib.Path(__file__).parent.parent / "research" / "out" / "features.csv"
    if not path.exists():
        pytest.skip(
            "research/out/features.csv chybí — spusť `python -m research.features`. "
            "Přeskočeno s důvodem, ne tiše."
        )

    gaps = []
    for row in csv.DictReader(path.open(encoding="utf-8")):
        if row["era"] != "MODERN_LONG" or not row["pause_interest"]:
            continue
        if not row["ret_to_exit_pct"] or not row["sheet_final_net_change_pct"]:
            continue
        gaps.append(
            float(row["ret_to_exit_pct"]) - float(row["sheet_final_net_change_pct"])
        )

    assert len(gaps) == 31
    assert sum(1 for gap in gaps if gap < -1) == 25
    assert statistics.median(gaps) == pytest.approx(-5.9, abs=1.0)
