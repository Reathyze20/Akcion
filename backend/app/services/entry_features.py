"""
What a stock looked like on the day somebody decided to buy it.

Seven numbers, computed from daily bars and nothing else. They exist so that a
candidate today can be placed against the distribution of Mark Gomes' actual
entries over 2021-2026 — see `research/profile.py` and
`app/services/gomes_fit.py`.

This module lives in `app/` and not in `research/` for one reason: the reference
distribution and the candidate being compared against it MUST be computed by the
same code. Two implementations that agree today drift apart the first time
either is touched, and the comparison silently starts meaning nothing. So the
pure computation is here, `research/` imports it, and `app/` never imports
`research/`.

No lookahead, by construction
-----------------------------
Every window ends at the entry bar. Nothing dated after it can reach any output.
That is not a convention to be careful about, it is what makes the whole
comparison honest: features that can see the future would place every one of
Mark's entries beautifully and tell you nothing about a candidate today.

Which price
-----------
Split-adjusted close (`Bar.close`), not the dividend-adjusted one. These are
chart-shaped questions — how far below the year's high, where in the year's
range — and a chart shows split-adjusted prices. `score_outcomes.py` uses the
dividend-adjusted series for the different job of measuring what a holder
earned, and that difference is deliberate rather than an inconsistency: the
cohort is micro-caps that pay no dividend, where the two series coincide, and
for the handful that do (NVDA, CALM) "20 % below the high" should mean what the
chart says.

Missing is missing
------------------
Each window needs `MIN_COVERAGE` of its expected sessions or the feature is
`None` and its name goes in `missing`. Never zero, never forward-filled, never
"use whatever history exists" — a twelve-month return computed from three months
is a different quantity wearing the same name. Missingness is per feature, so a
recently listed company still contributes everything it can support.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from datetime import date
from typing import Final, Iterable, Sequence

#: Trading sessions in the windows, as the market counts them.
SESSIONS_1M: Final[int] = 21
SESSIONS_3M: Final[int] = 63
SESSIONS_6M: Final[int] = 126
SESSIONS_12M: Final[int] = 252
SESSIONS_VOL: Final[int] = 60
SESSIONS_VOLUME: Final[int] = 20
SESSIONS_MA: Final[int] = 200

#: How much of a window has to be present for the feature to be computed.
#:
#: Eighty percent, not a hundred. Micro-caps genuinely halt and go no-bid, and
#: demanding completeness would drop names that traded perfectly normally. Below
#: this the answer is a named absence, because the alternative — quietly
#: computing a "twelve-month return" from seven months — produces a number that
#: looks like every other number in the column.
MIN_COVERAGE: Final[float] = 0.8

#: Sessions per year, for annualising volatility.
SESSIONS_PER_YEAR: Final[int] = 252

#: The seven features the profile is built from, in reading order. Short on
#: purpose: each one has to be explainable in a sentence to somebody deciding
#: whether to buy something. `gauge_z_at_entry` is the seventh and is not
#: computed here — it is a fact about the market, not about the company, and it
#: needs the index series rather than this one.
PROFILE_FEATURES: Final[tuple[str, ...]] = (
    "drawdown_from_52w_high_pct",
    "pct_of_52w_range",
    "ret_6m_pct",
    "vol_60d_annualised_pct",
    "median_dollar_volume_20d",
    "price_level",
)

#: Czech labels, so no screen has to invent its own wording for these.
FEATURE_LABELS_CS: Final[dict[str, str]] = {
    "drawdown_from_52w_high_pct": "Pokles od ročního maxima",
    "pct_of_52w_range": "Pozice v ročním rozpětí",
    "ret_6m_pct": "Výnos za 6 měsíců",
    "vol_60d_annualised_pct": "Volatilita (60 d, roční)",
    "median_dollar_volume_20d": "Medián denního obratu",
    "price_level": "Cena",
    "gauge_z_at_entry": "Semafor (z-skóre S&P)",
}


@dataclass(frozen=True)
class Bar:
    """One session. Split-adjusted prices, as-reported volume."""

    day: date
    open: float
    high: float
    low: float
    close: float
    #: Split- AND dividend-adjusted. Kept for outcome measurement, not used by
    #: the chart-shaped features here.
    adj_close: float
    volume: int
    #: The split ratio reported for this session, 0.0 when there is none.
    #: A 1-for-10 reverse split reports 0.1.
    split: float = 0.0


@dataclass(frozen=True)
class Bars:
    """Sessions for one ticker, oldest first."""

    ticker: str
    rows: tuple[Bar, ...] = ()

    def __len__(self) -> int:
        return len(self.rows)

    @property
    def is_empty(self) -> bool:
        return not self.rows

    @property
    def first_day(self) -> date | None:
        return self.rows[0].day if self.rows else None

    @property
    def last_day(self) -> date | None:
        return self.rows[-1].day if self.rows else None

    def on_or_after(self, when: date) -> Bar | None:
        """
        The first session at or after `when`.

        The dates in the sheet are days somebody wrote something down; the
        market may have been shut. Same rule as `score_outcomes._first_bar_from`,
        and a test pins that the two agree.
        """
        for row in self.rows:
            if row.day >= when:
                return row
        return None

    def on_or_before(self, when: date) -> Bar | None:
        found = None
        for row in self.rows:
            if row.day > when:
                break
            found = row
        return found

    def through(self, when: date) -> tuple[Bar, ...]:
        """Every session up to and including `when`. The no-lookahead cut."""
        return tuple(row for row in self.rows if row.day <= when)

    def between(self, start: date, end: date) -> tuple[Bar, ...]:
        return tuple(row for row in self.rows if start <= row.day <= end)

    def splits_between(self, start: date, end: date) -> tuple[Bar, ...]:
        return tuple(row for row in self.between(start, end) if row.split)

    def cumulative_split(self, start: date, end: date) -> float:
        """
        The product of every split ratio in the window, 1.0 when there are none.

        What a suspected price factor has to be corroborated by: a factor of 10
        with a reported 0.1 split is the sheet agreeing with the tape once a
        reverse split is undone; the same factor with no split event is a wrong
        price.
        """
        product = 1.0
        for row in self.splits_between(start, end):
            product *= row.split
        return product


@dataclass(frozen=True)
class EntryFeatures:
    """
    One entry, described by what its chart looked like that day.

    Any field may be `None`; the name of every absent one is in `missing`, so a
    caller counting features has a denominator it can trust rather than one that
    silently shrank.
    """

    ticker: str
    #: The date asked about.
    as_of: date
    #: The session the numbers actually come from — the first at or after
    #: `as_of`, because the market may have been shut.
    bar_date: date
    close: float

    drawdown_from_52w_high_pct: float | None = None
    pct_of_52w_range: float | None = None
    ret_6m_pct: float | None = None
    vol_60d_annualised_pct: float | None = None
    median_dollar_volume_20d: float | None = None
    price_level: float | None = None

    #: Computed but not part of the profile: context for the findings document
    #: and the neighbours, where a fuller picture is wanted and no distribution
    #: is being fitted.
    ret_1m_pct: float | None = None
    ret_3m_pct: float | None = None
    ret_12m_pct: float | None = None
    dist_from_200d_ma_pct: float | None = None

    missing: tuple[str, ...] = ()

    def get(self, name: str) -> float | None:
        return getattr(self, name, None)

    @property
    def available_profile_features(self) -> tuple[str, ...]:
        return tuple(f for f in PROFILE_FEATURES if self.get(f) is not None)


class FeatureError(Exception):
    """No features can be computed at all — not even a partial answer."""


def _window(rows: Sequence[Bar], sessions: int) -> tuple[Bar, ...] | None:
    """
    The last `sessions` bars, or None if too few of them are there.

    `rows` is already cut at the entry bar by the caller, so this can only ever
    look backwards.
    """
    needed = int(sessions * MIN_COVERAGE)
    if len(rows) < needed:
        return None
    return tuple(rows[-sessions:])


def _pct(new: float, old: float) -> float | None:
    if old <= 0:
        return None
    return (new / old - 1.0) * 100.0


def compute(bars: Bars, as_of: date) -> EntryFeatures:
    """
    What `bars.ticker` looked like on the first session at or after `as_of`.

    Raises `FeatureError` when there is no such session at all. Everything
    weaker than that — a short history, a halted stretch — produces a partial
    answer with the gaps named, because a company that listed six months ago
    still has a real six-month return and dropping it would bias the sample
    towards whatever has been around longest.
    """
    if bars.is_empty:
        raise FeatureError(f"{bars.ticker}: žádné kurzy, vlastnosti nepočítám")

    bar = bars.on_or_after(as_of)
    if bar is None:
        raise FeatureError(
            f"{bars.ticker}: po {as_of} už žádná seance není — pod tímhle "
            f"symbolem se přestalo obchodovat"
        )

    history = bars.through(bar.day)  # the no-lookahead cut, once, here
    closes = [row.close for row in history]
    price = bar.close
    missing: list[str] = []

    def absent(name: str) -> None:
        missing.append(name)

    year = _window(history, SESSIONS_12M)
    if year is None:
        absent("drawdown_from_52w_high_pct")
        absent("pct_of_52w_range")
        drawdown = position = None
    else:
        high = max(row.high for row in year)
        low = min(row.low for row in year)
        drawdown = _pct(price, high)
        span = high - low
        position = ((price - low) / span * 100.0) if span > 0 else None
        if drawdown is None:
            absent("drawdown_from_52w_high_pct")
        if position is None:
            absent("pct_of_52w_range")

    returns: dict[str, float | None] = {}
    for name, sessions in (
        ("ret_1m_pct", SESSIONS_1M),
        ("ret_3m_pct", SESSIONS_3M),
        ("ret_6m_pct", SESSIONS_6M),
        ("ret_12m_pct", SESSIONS_12M),
    ):
        window = _window(history, sessions + 1)
        value = _pct(price, window[0].close) if window else None
        returns[name] = value
        if value is None:
            absent(name)

    vol_window = _window(history, SESSIONS_VOL + 1)
    volatility: float | None = None
    if vol_window:
        steps = [
            math.log(b.close / a.close)
            for a, b in zip(vol_window, vol_window[1:])
            if a.close > 0 and b.close > 0
        ]
        if len(steps) >= 2:
            volatility = (
                statistics.stdev(steps) * math.sqrt(SESSIONS_PER_YEAR) * 100.0
            )
    if volatility is None:
        absent("vol_60d_annualised_pct")

    volume_window = _window(history, SESSIONS_VOLUME)
    dollar_volume: float | None = None
    if volume_window:
        # Median, not mean. One halted session's print wrecks a mean on a
        # micro-cap, and liquidity is exactly what you are trying to read.
        turnover = [row.close * row.volume for row in volume_window]
        dollar_volume = statistics.median(turnover) if turnover else None
    if dollar_volume is None:
        absent("median_dollar_volume_20d")

    ma_window = _window(history, SESSIONS_MA)
    distance_from_ma: float | None = None
    if ma_window:
        average = statistics.fmean(row.close for row in ma_window)
        distance_from_ma = _pct(price, average)
    if distance_from_ma is None:
        absent("dist_from_200d_ma_pct")

    return EntryFeatures(
        ticker=bars.ticker,
        as_of=as_of,
        bar_date=bar.day,
        close=price,
        drawdown_from_52w_high_pct=drawdown,
        pct_of_52w_range=position,
        ret_6m_pct=returns["ret_6m_pct"],
        vol_60d_annualised_pct=volatility,
        median_dollar_volume_20d=dollar_volume,
        price_level=price if price > 0 else None,
        ret_1m_pct=returns["ret_1m_pct"],
        ret_3m_pct=returns["ret_3m_pct"],
        ret_12m_pct=returns["ret_12m_pct"],
        dist_from_200d_ma_pct=distance_from_ma,
        missing=tuple(missing),
    )


# ==============================================================================
# Outcomes — what happened after, for the record rather than for the profile
# ==============================================================================

@dataclass(frozen=True)
class Outcome:
    """
    What the position did between entry and exit, from bars rather than the sheet.

    The honest replacement for the sheet's "Peak Return While Live" column,
    which is split-contaminated past repair (MRIN reads 22394 %). Computed on
    the DIVIDEND-adjusted series, because this one is about what a holder
    earned rather than what a chart showed.
    """

    ret_to_exit_pct: float | None
    max_drawup_pct: float | None
    max_drawdown_pct: float | None
    sessions: int


def outcome(bars: Bars, entered: date, exited: date | None) -> Outcome | None:
    """What happened while the position was live. None when it cannot be read."""
    start = bars.on_or_after(entered)
    if start is None:
        return None
    end_day = exited or (bars.last_day or start.day)
    live = bars.between(start.day, end_day)
    if len(live) < 2:
        return None

    base = start.adj_close
    if base <= 0:
        return None

    highs = [row.adj_close for row in live]
    return Outcome(
        ret_to_exit_pct=_pct(live[-1].adj_close, base),
        max_drawup_pct=_pct(max(highs), base),
        max_drawdown_pct=_pct(min(highs), base),
        sessions=len(live),
    )


def to_bars(ticker: str, rows: Iterable[Bar]) -> Bars:
    """Sort into a `Bars`, oldest first, without trusting the caller's order."""
    return Bars(ticker=ticker, rows=tuple(sorted(rows, key=lambda r: r.day)))
