"""
An assisted reading of the semafor from the long-term S&P chart.

Canon §2 derives the market alert from where the S&P sits on a 40-year chart
against three lines — an upper line where you take profits, a grey line below
which buying is safe, and a bottom white line that marks a generational
opportunity. The app has never had any of that: the semafor is a field someone
remembers to switch, and GREEN has meant "nobody has touched this".

This computes a proxy for that chart position: monthly ^GSPC closes over the
whole available window (1985 to now — 41.6 years, which is the 40-year chart),
a log-linear trend fitted through them, and the current price expressed as
standard deviations from that trend.

**What it gets right, and what it does not.**

Checked against the canon's own two RED calls, the only two Gomes says he has
made in a lifetime:

* **End of 1999 — found.** December 1999 scores +2.74 and March 2000 +2.75,
  the two highest readings in the entire 41-year series. Nothing else comes
  close.
* **Middle of 2007 — missed completely.** June 2007 scores +0.58: the 78th
  percentile, an unremarkable month. The 2007 top was built on credit and
  earnings that were about to evaporate, not on price running away from its
  own trend, and a price-versus-trend channel is structurally blind to it.

So this is one input, not the answer, and it says so in every response it
produces. It never writes the semafor itself — `suggested_alert` is what
`app/services/market_watch.py` reads, and that module may only ever tighten the
setting, never loosen it: this measure misses the 2007 top entirely, so it has
not earned the right to sound an all-clear. What follows is a suggestion the
user accepts or ignores, because a gauge that silently sets the field would be
the same manufactured confidence in a new place. It also refuses to answer at
all rather than guess: too little history, or no history, returns a stated gap.

The z-score is in-sample — today's price is one of the points the trend is
fitted through. On a 500-month series one point moves the line very little, but
it is worth knowing that the measure is not out-of-sample.
"""

from __future__ import annotations

import math
import statistics
import threading
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import Enum
from typing import Final

from loguru import logger

#: The index the canon's chart is of.
INDEX_TICKER: Final[str] = "^GSPC"

#: Below this the channel is not a 40-year chart and the reading is refused.
#: A trend fitted through fifteen years of one regime says nothing about where
#: the market sits in its history.
MIN_YEARS: Final[float] = 30.0

#: Monthly closes are what the canon's chart shows, and they keep the series
#: small enough to fit and cache cheaply.
MONTHS_PER_YEAR: Final[int] = 12

#: One reading per day is plenty — the input is a monthly close.
CACHE_TTL: Final[timedelta] = timedelta(hours=24)

#: The three lines, as standard deviations from the fitted log trend.
#: Calibrated against the series itself, not chosen freehand: +2.5 selects the
#: 1999-2000 cluster and nothing else, and -2.0 selects the early-2009 bottom
#: and nothing else. Those are precisely the two extremes the canon names.
UPPER_LINE_Z: Final[float] = 2.5
EXPENSIVE_Z: Final[float] = 1.0
GREY_LINE_Z: Final[float] = 0.0
LOWER_LINE_Z: Final[float] = -2.0


class ChannelPosition(str, Enum):
    """Where the index sits on the long-term chart, in the canon's own terms."""

    AT_UPPER_LINE = "AT_UPPER_LINE"      # "u horní linie" — take profits
    EXPENSIVE = "EXPENSIVE"              # above trend, not at the line
    ABOVE_TREND = "ABOVE_TREND"
    BELOW_GREY = "BELOW_GREY"            # "pod šedou linií" — safe buying zone
    AT_LOWER_LINE = "AT_LOWER_LINE"      # generational opportunity


#: What the canon does at each chart position.
#:
#: The range is {GREEN, YELLOW} and cannot be anything else. This used to map
#: `AT_UPPER_LINE` to ORANGE, and GOMES_VIDEO_ADDENDUM.md §V3 says why that was
#: wrong at the level of what the three grades MEAN. Gomes separates them by
#: what he KNOWS, not by how dear the market is:
#:
#:   YELLOW  "I don't know what's going to cause the market to drop, but
#:            something's going to, because the market's too expensive right
#:            now. Most of my alerts are going to be yellow."
#:   ORANGE  COVID. "I knew it was bad. I just didn't know HOW bad, because
#:            frankly I'm not a biologist."  -> a named cause, unknown size.
#:   RED     "when I know exactly what's happening, why it's happening, and how
#:            severe it is."  -> a named cause, known to be severe. Twice in
#:            thirty years.
#:
#: A z-score does not know what is happening in the world. It can only ever
#: report the YELLOW condition — expensive, cause unknown — so that is the most
#: it is allowed to say. ORANGE and RED are reached through
#: `app/services/market_catalyst.py`, which requires somebody to name the cause.
#:
#: This is a tightening of what the gauge may claim, not a loosening of the
#: semafor: an expensive market still raises the alert to YELLOW on its own,
#: which is exactly the grade Gomes says most of his alerts are.
POSITION_ALERT: Final[dict[ChannelPosition, str]] = {
    ChannelPosition.AT_UPPER_LINE: "YELLOW",
    ChannelPosition.EXPENSIVE: "YELLOW",
    ChannelPosition.ABOVE_TREND: "GREEN",
    ChannelPosition.BELOW_GREY: "GREEN",
    ChannelPosition.AT_LOWER_LINE: "GREEN",
}

#: The most the valuation measure may ever propose. Asserted rather than
#: trusted: a future edit to the table above must not quietly hand the gauge
#: back the power to declare a catastrophe it cannot see.
GAUGE_MAX_ALERT: Final[str] = "YELLOW"
assert set(POSITION_ALERT.values()) <= {"GREEN", GAUGE_MAX_ALERT}

POSITION_CS: Final[dict[ChannelPosition, str]] = {
    ChannelPosition.AT_UPPER_LINE: (
        "U horní linie 40letého grafu — podle kánonu výborný čas brát zisky. "
        "Samotná drahota je žlutá: oranžovou a červenou nedělá cena, ale "
        "pojmenovaná příčina (§V3)."
    ),
    ChannelPosition.EXPENSIVE: (
        "Nad trendem, ale ne u horní linie — drahý trh, ne extrém."
    ),
    ChannelPosition.ABOVE_TREND: "Mírně nad dlouhodobým trendem.",
    ChannelPosition.BELOW_GREY: (
        "Pod šedou linií — podle kánonu bezpečná nákupní zóna."
    ),
    ChannelPosition.AT_LOWER_LINE: (
        "U spodní bílé linie — generační příležitost, jednou za život."
    ),
}

#: The gauge's own failure, stated in every reading. Not a caveat added for
#: politeness: it is the single most important thing to know before acting on
#: this number.
BLIND_SPOT_CS: Final[str] = (
    "Tenhle ukazatel měří jen cenu proti vlastnímu trendu. Z obou RED alertů, "
    "které Gomes za život vyhlásil, najde jen konec roku 1999 (prosinec 1999 a "
    "březen 2000 jsou dvě nejvyšší hodnoty za celých 41 let). Polovinu roku "
    "2007 nevidí vůbec — červen 2007 vychází na +0,58, tedy 78. percentil, "
    "úplně obyčejný měsíc. Vrchol 2007 stál na úvěrech a ziscích, které se "
    "chystaly zmizet, a to z ceny proti trendu poznat nejde. "
    "Proti jedenácti datovaným Gomesovým zásahům do trhu z let 2016-2022 "
    "souhlasí ve třech, a ve všech třech jen tím, že řekne „není draho“ ve "
    "chvíli, kdy hedge zavíral. Ani jedno z šesti otevření hedge nenajde: tři "
    "z nich (2021 a 2022) leží v horní pětině kanálu, těsně pod hranicí, ale "
    "zbylá tři kolem středu — a mezi nimi 14. 2. 2020, dva týdny před covidovým "
    "propadem. Tam ukazatel netrefuje o kousek, tam nesouhlasí."
)


class GaugeError(Exception):
    """The gauge cannot be computed. Never downgraded to a default GREEN."""


@dataclass(frozen=True)
class Reading:
    """One reading of the long-term chart, with everything behind it."""

    as_of: date
    close: float
    z_score: float
    percentile: float
    position: ChannelPosition
    suggested_alert: str
    trend_value: float
    #: Prices the three lines currently sit at, so the chart can be drawn.
    upper_line: float
    grey_line: float
    lower_line: float
    #: Annualised log slope of the fitted trend, in percent.
    trend_pct_per_year: float
    months: int
    note_cs: str = ""
    blind_spot_cs: str = BLIND_SPOT_CS

    @property
    def years(self) -> float:
        return self.months / MONTHS_PER_YEAR


@dataclass(frozen=True)
class Series:
    """Monthly closes, oldest first."""

    points: list[tuple[date, float]] = field(default_factory=list)


# ==============================================================================
# The channel
# ==============================================================================

def fit(
    points: list[tuple[date, float]], *, as_of: date | None = None
) -> Reading:
    """
    Fit the long-term log trend and place the newest point on it.

    Raises GaugeError when there is not enough history, or when a close is
    non-positive — a log of zero is not a valuation, it is a data fault, and
    silently dropping it would move the trend without saying so.

    `as_of` reads the chart as it stood on a past date: the series is truncated
    to points dated on or before it, and everything below then operates on the
    truncated series. Two properties of that, because both are easy to break in
    the direction that flatters the answer:

    * The trend is REFITTED on the shorter series, never sliced out of the full
      fit. A reading dated 2016 must not know 2026's slope.
    * `MIN_YEARS` still applies and must not be softened for it. Against a
      series starting in 1985 that means any `as_of` before roughly 2015 raises
      instead of answering, which is the correct answer: thirty years is what
      makes this a long-term chart rather than one regime's trend.

    The returned `Reading.as_of` is the last MONTHLY close at or before the
    requested date, not the date requested. The input is a monthly series and
    the reading cannot be more precise than its input.

    Without `as_of` the behaviour is exactly what it was: fit everything, report
    the newest point.
    """
    if as_of is not None:
        points = [point for point in points if point[0] <= as_of]

    if len(points) < MIN_YEARS * MONTHS_PER_YEAR:
        raise GaugeError(
            f"Mám jen {len(points) / MONTHS_PER_YEAR:.1f} roku historie "
            f"{INDEX_TICKER}, na dlouhodobý graf je potřeba aspoň {MIN_YEARS:.0f} let. "
            f"Semafor z tohohle neodvozuju."
        )

    bad = [d for d, close in points if close <= 0]
    if bad:
        raise GaugeError(
            f"{INDEX_TICKER} má nulovou nebo zápornou cenu k {bad[0]} — to je "
            f"chyba dat, ne ocenění. Ukazatel nepočítám."
        )

    xs = list(range(len(points)))
    ys = [math.log(close) for _, close in points]
    n = len(xs)

    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    variance_x = sum((x - mean_x) ** 2 for x in xs)
    slope = sum(
        (x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)
    ) / variance_x
    intercept = mean_y - slope * mean_x

    residuals = [y - (intercept + slope * x) for x, y in zip(xs, ys)]
    sigma = statistics.pstdev(residuals)
    if sigma <= 0:
        raise GaugeError(
            f"{INDEX_TICKER} nemá kolem trendu žádný rozptyl — z takové řady "
            f"se pozice na grafu spočítat nedá."
        )

    z = residuals[-1] / sigma
    percentile = sum(1 for r in residuals if r <= residuals[-1]) / n * 100
    position = classify(z)
    trend_log = intercept + slope * xs[-1]

    return Reading(
        as_of=points[-1][0],
        close=points[-1][1],
        z_score=z,
        percentile=percentile,
        position=position,
        suggested_alert=POSITION_ALERT[position],
        trend_value=math.exp(trend_log),
        upper_line=math.exp(trend_log + UPPER_LINE_Z * sigma),
        grey_line=math.exp(trend_log + GREY_LINE_Z * sigma),
        lower_line=math.exp(trend_log + LOWER_LINE_Z * sigma),
        trend_pct_per_year=(math.exp(slope * MONTHS_PER_YEAR) - 1) * 100,
        months=n,
        note_cs=POSITION_CS[position],
    )


def classify(z: float) -> ChannelPosition:
    """Where a z-score puts the index on the chart."""
    if z >= UPPER_LINE_Z:
        return ChannelPosition.AT_UPPER_LINE
    if z >= EXPENSIVE_Z:
        return ChannelPosition.EXPENSIVE
    if z >= GREY_LINE_Z:
        return ChannelPosition.ABOVE_TREND
    if z > LOWER_LINE_Z:
        return ChannelPosition.BELOW_GREY
    return ChannelPosition.AT_LOWER_LINE


# Stupně semaforu jsou v kódu anglicky, protože tak je pojmenovává kánon
# i databáze. Do české věty ale nepatří — čtenář nemá číst hodnotu z pole.
ALERT_CS: Final[dict[str, str]] = {
    "GREEN": "zelená",
    "YELLOW": "žlutá",
    "ORANGE": "oranžová",
    "RED": "červená",
}


def alert_cs(alert: str) -> str:
    return ALERT_CS.get(alert.upper(), alert)


def agreement_cs(reading: Reading, current_alert: str | None) -> str:
    """
    Whether the gauge and the semafor currently on the field agree.

    Disagreement is not an error and is never resolved automatically. It is
    the one thing worth reading here: a manual GREEN that the long-term chart
    argues with has been sitting unexamined, and that is exactly how a stale
    semafor authorises purchases.
    """
    # Délka řady se hlásí skutečná, ne zaokrouhlená na „40 let". Graf je
    # kalibrovaný na tom, co se opravdu stáhlo, a tvrdit jinak by znamenalo
    # nadsadit rozsah, na kterém ta čísla stojí.
    span = f"{reading.years:.0f}letý".replace(".", ",")

    if not current_alert:
        return (
            f"Semafor v aplikaci není nastavený. Graf by odpovídal stupni "
            f"{alert_cs(reading.suggested_alert)}."
        )
    current = current_alert.upper()
    if current == reading.suggested_alert:
        return (
            f"Semafor {alert_cs(current)} sedí s tím, co ukazuje "
            f"{span} graf."
        )
    return (
        f"Semafor je nastavený na {alert_cs(current)}, ale {span} graf "
        f"odpovídá stupni {alert_cs(reading.suggested_alert)}. Zvolnit ho může "
        f"jen člověk; přitvrdit si aplikace smí sama."
    )


# ==============================================================================
# Data
# ==============================================================================

_lock = threading.Lock()
_cached: Reading | None = None
_cached_at: datetime | None = None


def reset_cache() -> None:
    """Drop the cached reading. For tests and for a manual refresh."""
    global _cached, _cached_at
    with _lock:
        _cached = None
        _cached_at = None


def fetch_series() -> list[tuple[date, float]]:
    """
    Monthly ^GSPC closes, oldest first, over the whole available window.

    Raises GaugeError on any transport failure. Deliberately not an empty list:
    "we could not read the index" and "the index has no history" would both
    end in a refusal, but only one of them is worth retrying.
    """
    try:
        import yfinance as yf

        history = yf.Ticker(INDEX_TICKER).history(
            period="max", interval="1mo", auto_adjust=False,
        )
    except Exception as e:  # noqa: BLE001 — any failure is the same refusal
        raise GaugeError(f"{INDEX_TICKER} se nepodařilo stáhnout: {e}") from e

    points = [
        (stamp.date(), float(close))
        for stamp, close in history["Close"].items()
        if close == close  # NaN months exist at the edges
    ]
    if not points:
        raise GaugeError(f"{INDEX_TICKER} vrátil prázdnou historii.")
    return points


def current_reading(*, refresh: bool = False) -> Reading:
    """
    Today's reading, computed at most once a day.

    Raises GaugeError rather than returning a stale or default reading — the
    whole point of this module is that GREEN must never mean "nobody looked".
    """
    global _cached, _cached_at

    with _lock:
        fresh = (
            _cached is not None
            and _cached_at is not None
            and datetime.now() - _cached_at < CACHE_TTL
        )
        if fresh and not refresh:
            return _cached

        reading = fit(fetch_series())
        _cached = reading
        _cached_at = datetime.now()
        logger.info(
            "Market gauge: {} k {}, z={:+.2f}, {} → návrh {}",
            INDEX_TICKER, reading.as_of, reading.z_score,
            reading.position.value, reading.suggested_alert,
        )
        return reading
