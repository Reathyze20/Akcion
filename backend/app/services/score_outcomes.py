"""
What each conviction score turned out to be worth.

The journal (`app/services/score_journal.py`) records what the app claimed and
when. This module measures those claims against what the price actually did,
so that the one question worth asking about the whole method — did the nines
earn more than the fives? — eventually has an answer made of arithmetic rather
than of impressions.

Horizons
--------
30 / 90 / 180 / 365 days. The reference implementation this idea came from
uses 1/3/5/10 days, which measures a day-trading system; a fundamental method
built on catalysts cannot be judged inside a week. A month gives the earliest
honest signal and a year is the one that decides.

The headline is excess return over ^GSPC
----------------------------------------
A nine that returned +5 % while the index returned +12 % was bad advice, and
an absolute number would hide that. The absolute return is stored beside it,
because the goal it is measured against is a real 20 % a year, not a relative
one — but the number that judges the *score* is the excess.

No model anywhere in here
-------------------------
Two prices and a subtraction. An LLM in this path would make the measurement
exactly as untrustworthy as the thing it is supposed to measure.

What "no data" is allowed to become
-----------------------------------
Nothing. A horizon that has not elapsed is `pending`; a horizon that has
elapsed but cannot be measured is `unable` with a named reason. Neither is
ever a 0 %. This is the app's oldest defect class — absent inputs turning into
confident outputs — and the schema enforces the rule as well as this module
does (see `migrations/add_score_outcomes.sql`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Final, Iterable, Sequence

from loguru import logger

from app.models.score_outcome import (
    STATUS_EVALUATED,
    STATUS_PENDING,
    STATUS_UNABLE,
)


#: Evaluated for every journal entry. Fundamental horizons, not trading ones.
HORIZONS: Final[tuple[int, ...]] = (30, 90, 180, 365)

#: The benchmark every score is judged against.
BENCHMARK_TICKER: Final[str] = "^GSPC"

# Reasons a horizon that has elapsed still cannot be measured.
REASON_NO_BASELINE: Final[str] = "no_baseline_price"
REASON_ZERO_BASELINE: Final[str] = "zero_baseline_price"
REASON_NO_FORWARD_BAR: Final[str] = "no_forward_bar"

#: How long a horizon may sit without a closing bar before it stops being "the
#: market has not gotten there yet" and starts being "this ticker is gone".
#: Covers a long weekend plus a holiday with room to spare.
SETTLE_DAYS: Final[int] = 7

# Where the baseline came from.
BASELINE_JOURNAL: Final[str] = "journal"
BASELINE_CLOSE: Final[str] = "close_on_record_date"

#: A price bar, reduced to the only two fields this module needs.
Bar = tuple[date, Decimal]


@dataclass(frozen=True)
class Evaluation:
    """One score measured at one horizon. Immutable, like the fact it records."""

    eval_status: str
    unable_reason: str | None = None
    baseline_price: Decimal | None = None
    baseline_source: str | None = None
    end_price: Decimal | None = None
    end_date: date | None = None
    return_pct: Decimal | None = None
    benchmark_return_pct: Decimal | None = None
    excess_return_pct: Decimal | None = None

    @property
    def is_measured(self) -> bool:
        return self.eval_status == STATUS_EVALUATED


# ==============================================================================
# The measurement
# ==============================================================================

def evaluate(
    *,
    recorded_on: date,
    horizon_days: int,
    journal_price: Decimal | None,
    ticker_bars: Sequence[Bar],
    benchmark_bars: Sequence[Bar],
    today: date,
) -> Evaluation:
    """
    Measure one journaled score at one horizon.

    Pure: every input is passed in, so the arithmetic can be tested on known
    numbers without a database or a network.

    Args:
        recorded_on: The day the score was issued.
        horizon_days: 30, 90, 180 or 365.
        journal_price: The quote captured at scoring time, if there was a
            trustworthy one. When absent, the baseline is recovered from
            `ticker_bars` — which is in fact the better figure, being the
            market's own close rather than an intraday snapshot.
        ticker_bars: (date, close) ascending. Need not be complete; the
            lookups take the nearest bar on the correct side.
        benchmark_bars: the same for ^GSPC.
        today: the evaluation date, injected so tests are not time-dependent.

    Returns:
        An Evaluation. Never raises on missing data — that is what
        `unable_reason` is for.
    """
    target = recorded_on + timedelta(days=horizon_days)
    if target >= today:
        # `>=`, not `>`: today's bar is a partial session while the market is
        # open, and an outcome measured against an intraday price would be
        # frozen at that price forever, because evaluated rows are never
        # recomputed. One extra day of waiting costs nothing; a permanently
        # wrong number costs the credibility of the whole report.
        return Evaluation(eval_status=STATUS_PENDING)

    # Only completed sessions. This is what makes the run time of the daily job
    # irrelevant — whether it fires at 09:00 or at midnight, it sees the same
    # closed bars and produces the same answer.
    ticker_bars = [bar for bar in ticker_bars if bar[0] < today]
    benchmark_bars = [bar for bar in benchmark_bars if bar[0] < today]

    baseline, baseline_source = _resolve_baseline(journal_price, ticker_bars, recorded_on)
    if baseline is None:
        return Evaluation(eval_status=STATUS_UNABLE, unable_reason=REASON_NO_BASELINE)
    if baseline == 0:
        # A zero baseline is not a 100 % loss, it is an unusable denominator.
        return Evaluation(
            eval_status=STATUS_UNABLE,
            unable_reason=REASON_ZERO_BASELINE,
            baseline_price=baseline,
            baseline_source=baseline_source,
        )

    end_bar = _first_bar_from(ticker_bars, target)
    if end_bar is None:
        if (today - target).days <= SETTLE_DAYS:
            # The horizon has elapsed but no session has closed on or after it
            # yet — a weekend, a holiday, or a run made before the close. That
            # is waiting, not failure, and calling it `unable` would retire a
            # measurement that is about to become available.
            return Evaluation(eval_status=STATUS_PENDING)
        # A week of closed markets with no bar means the ticker is gone:
        # delisted, renamed, or never covered by the data source.
        return Evaluation(
            eval_status=STATUS_UNABLE,
            unable_reason=REASON_NO_FORWARD_BAR,
            baseline_price=baseline,
            baseline_source=baseline_source,
        )

    end_date, end_price = end_bar
    return_pct = _pct_change(baseline, end_price)

    benchmark_pct = _benchmark_change(benchmark_bars, recorded_on, target)
    excess = None if benchmark_pct is None else _round(return_pct - benchmark_pct)

    return Evaluation(
        eval_status=STATUS_EVALUATED,
        baseline_price=baseline,
        baseline_source=baseline_source,
        end_price=end_price,
        end_date=end_date,
        return_pct=return_pct,
        benchmark_return_pct=benchmark_pct,
        excess_return_pct=excess,
    )


def _resolve_baseline(
    journal_price: Decimal | None,
    bars: Sequence[Bar],
    recorded_on: date,
) -> tuple[Decimal | None, str | None]:
    """
    The price the score was formed against.

    Prefers the quote the journal captured, because that is literally what the
    app was looking at. Falls back to the market's close on (or last before)
    the recording day, which is why a journal row with no price is not a lost
    measurement — most of them are recoverable.
    """
    if journal_price is not None:
        return journal_price, BASELINE_JOURNAL

    bar = _last_bar_through(bars, recorded_on)
    if bar is None:
        return None, None
    return bar[1], BASELINE_CLOSE


def _benchmark_change(
    bars: Sequence[Bar], start: date, end: date
) -> Decimal | None:
    """
    ^GSPC over the same window, or None if the index could not be read.

    None is not treated as a failed evaluation: the stock's own return is a
    real measurement and is kept. The calibration report is what has to say
    how many of its rows carry a benchmark.
    """
    start_bar = _last_bar_through(bars, start)
    end_bar = _first_bar_from(bars, end)
    if start_bar is None or end_bar is None or start_bar[1] == 0:
        return None
    return _pct_change(start_bar[1], end_bar[1])


def _last_bar_through(bars: Sequence[Bar], when: date) -> Bar | None:
    """The most recent bar on or before `when` — the market's last word by then."""
    candidates = [bar for bar in bars if bar[0] <= when]
    return max(candidates, key=lambda bar: bar[0]) if candidates else None


def _first_bar_from(bars: Sequence[Bar], when: date) -> Bar | None:
    """The first bar on or after `when` — the horizon lands on a weekend often enough."""
    candidates = [bar for bar in bars if bar[0] >= when]
    return min(candidates, key=lambda bar: bar[0]) if candidates else None


def _pct_change(start: Decimal, end: Decimal) -> Decimal:
    return _round((end - start) / start * Decimal(100))


def _round(value: Decimal) -> Decimal:
    """Four decimal places, matching the column, so nothing is truncated on write."""
    return value.quantize(Decimal("0.0001"))


# ==============================================================================
# Helpers for callers assembling bars
# ==============================================================================

def to_bars(rows: Iterable[tuple]) -> list[Bar]:
    """
    Normalise (date-ish, close-ish) pairs into Bars, dropping anything unusable.

    Rows come from `ohlcv_data` or a yfinance frame and arrive as a mixture of
    datetimes, floats and Decimals. A row that cannot be read is dropped rather
    than defaulted — a fabricated bar would land in a return calculation.
    """
    bars: list[Bar] = []
    for row in rows:
        when, close = row[0], row[1]
        if when is None or close is None:
            continue
        when = when.date() if hasattr(when, "date") else when
        try:
            bars.append((when, Decimal(str(close))))
        except (InvalidOperation, TypeError, ValueError):
            continue
    bars.sort(key=lambda bar: bar[0])
    return bars


def span_for(recorded_on: date, today: date) -> tuple[date, date]:
    """
    The window of bars needed to evaluate every horizon of one journal entry.

    A few days of lead-in so the baseline lookup has a bar to land on when the
    score was recorded over a weekend or a holiday.
    """
    return recorded_on - timedelta(days=7), min(
        today, recorded_on + timedelta(days=max(HORIZONS) + 7)
    )


# ==============================================================================
# Bars
# ==============================================================================

def fetch_bars(ticker: str, start: date, end: date) -> list[Bar]:
    """
    Daily closes for `ticker` between `start` and `end`, adjusted.

    `auto_adjust=True` is not a detail. A two-for-one split in the middle of a
    horizon turns an unadjusted +10 % into a -45 %, and a dividend-paying
    holding looks worse than it was — the app would then report, as measured
    fact, that its own good calls lost money. Adjusted closes are also the
    right basis on principle: what is being judged is the return to a holder,
    dividends included.

    Not cached in `ohlcv_data`, deliberately, though the plan for this work
    said it would be. Adjusted history is rewritten backwards every time a
    dividend or split occurs, so a stored copy silently drifts from the source;
    the alternative saves a few dozen requests in a once-a-day batch, which is
    not a trade worth making. `evaluated` rows are immutable anyway, so each
    one is computed once from the series as it stood.

    Returns an empty list on any failure — a ticker with no bars becomes
    `unable`, never a zero return.
    """
    try:
        import yfinance as yf

        frame = yf.Ticker(ticker).history(
            start=start.isoformat(),
            end=(end + timedelta(days=1)).isoformat(),  # yfinance end is exclusive
            interval="1d",
            auto_adjust=True,
        )
    except Exception:  # noqa: BLE001 — any failure is the same absence
        logger.exception("Historie {} se nepodařila stáhnout", ticker)
        return []

    if frame is None or frame.empty or "Close" not in frame:
        return []

    return to_bars(
        (stamp, close)
        for stamp, close in frame["Close"].items()
        if close == close  # NaN rows exist at the edges
    )


# ==============================================================================
# The run
# ==============================================================================

@dataclass
class RunSummary:
    """What one evaluation pass did."""

    scanned: int = 0
    written: int = 0
    evaluated: int = 0
    pending: int = 0
    unable: int = 0
    tickers_without_bars: list[str] = field(default_factory=list)

    def describe(self) -> str:
        parts = [
            f"{self.scanned} párů (záznam × horizont)",
            f"{self.written} zapsáno",
            f"{self.evaluated} změřeno",
            f"{self.pending} čeká na horizont",
            f"{self.unable} nezměřitelných",
        ]
        line = ", ".join(parts)
        if self.tickers_without_bars:
            line += f"\nBez historie: {', '.join(sorted(self.tickers_without_bars))}"
        return line


def evaluate_all(
    db,
    *,
    today: date | None = None,
    fetch=fetch_bars,
) -> RunSummary:
    """
    Measure every journal entry that is not measured yet.

    Idempotent by design. An `evaluated` row is a fact about a past prediction
    and is never recomputed — only missing and `pending` rows are touched, so
    the run can be repeated as often as anyone likes without the record of
    what the app once claimed drifting underneath it.

    Adds to the session and does not commit; the caller decides, which is what
    lets `scripts/evaluate_scores.py --dry-run` print without writing.

    Args:
        today: injected so tests are not time-dependent.
        fetch: injected so tests do not touch the network.
    """
    from app.models.score_history import ConvictionScoreHistory
    from app.models.score_outcome import ScoreOutcome

    today = today or date.today()
    summary = RunSummary()

    entries = db.query(ConvictionScoreHistory).order_by(
        ConvictionScoreHistory.recorded_at
    ).all()
    if not entries:
        return summary

    existing = {
        (row.history_id, row.horizon_days): row
        for row in db.query(ScoreOutcome).all()
    }

    benchmark_bars = fetch(
        BENCHMARK_TICKER,
        min(_recorded_on(e) for e in entries) - timedelta(days=7),
        today,
    )
    if not benchmark_bars:
        # Not fatal: absolute returns are still real measurements. It does mean
        # the headline excess column will be empty for everything written now.
        logger.warning(
            "{} nevrátil žádnou historii — nadvýnosy tohoto běhu zůstanou prázdné",
            BENCHMARK_TICKER,
        )

    bars_by_ticker: dict[str, list[Bar]] = {}

    for entry in entries:
        recorded_on = _recorded_on(entry)
        ticker = (entry.ticker or "").upper()

        if ticker not in bars_by_ticker:
            start, end = span_for(recorded_on, today)
            bars_by_ticker[ticker] = fetch(ticker, start, end)
            if not bars_by_ticker[ticker]:
                summary.tickers_without_bars.append(ticker)

        for horizon in HORIZONS:
            summary.scanned += 1
            current = existing.get((entry.id, horizon))
            if current is not None and current.eval_status == STATUS_EVALUATED:
                continue  # measured once, kept forever

            result = evaluate(
                recorded_on=recorded_on,
                horizon_days=horizon,
                journal_price=entry.price_at_analysis,
                ticker_bars=bars_by_ticker[ticker],
                benchmark_bars=benchmark_bars,
                today=today,
            )

            if current is None:
                current = ScoreOutcome(history_id=entry.id, horizon_days=horizon)
                db.add(current)
                existing[(entry.id, horizon)] = current

            _apply(current, result)
            summary.written += 1

            if result.eval_status == STATUS_EVALUATED:
                summary.evaluated += 1
            elif result.eval_status == STATUS_PENDING:
                summary.pending += 1
            else:
                summary.unable += 1

    return summary


def _apply(row, result: Evaluation) -> None:
    """Copy an Evaluation onto its row, clearing whatever the last pass left."""
    row.eval_status = result.eval_status
    row.unable_reason = result.unable_reason
    row.baseline_price = result.baseline_price
    row.baseline_source = result.baseline_source
    row.end_price = result.end_price
    row.end_date = result.end_date
    row.return_pct = result.return_pct
    row.benchmark_return_pct = result.benchmark_return_pct
    row.excess_return_pct = result.excess_return_pct


def _recorded_on(entry) -> date:
    """The journal row's date, whatever flavour of datetime it carries."""
    stamp = entry.recorded_at
    return stamp.date() if hasattr(stamp, "date") else stamp
