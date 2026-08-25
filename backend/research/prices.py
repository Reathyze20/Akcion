"""
Daily bars for the tickers in the sheet, both adjusted and as-quoted.

Why both. The sheet's prices are what was quoted on the day; yfinance's default
`auto_adjust=True` gives prices rewritten backwards through every split and
dividend since. For a name that has split, those two disagree by a factor, and
the disagreement is exactly what `reconcile.py` has to tell apart from a
transcription error. So this module fetches once with `auto_adjust=False,
actions=True`, which returns the as-quoted OHLC, the adjusted close, AND the
split events — so a factor can be checked against a split the data itself
reports rather than inferred from the factor's own plausibility.

Where the types live
--------------------
`Bar` and `Bars` are imported from `app/services/entry_features.py`, not defined
here. The reference distribution and the candidate compared against it have to
be computed by the same code, so the pure container and the feature maths live
in the app and this module only does the I/O the app has no business doing —
fetching from an unofficial endpoint and caching to a gitignored directory.

Relationship to `app/services/score_outcomes.py`
------------------------------------------------
The adjusted close here must mean the same thing it means in the live
evaluator, or comparing the app against the sheet compares nothing. The
session-lookup rule is pinned against `score_outcomes._first_bar_from` in
`tests/test_research_prices.py` rather than left as an intention.

What is NOT reused is its error handling. `fetch_bars` swallows every failure
into an empty list (score_outcomes.py:326-333), which is right for a daily job
that must not die on one dead ticker and useless here, where "no rows" has to be
told apart from "the network failed" — one is a fact about the company, the
other is a fact about this afternoon.

Caching
-------
`out/bars/{TICKER}.csv`, gitignored, with the fetch date in a `#` header. One
call per ticker, not per row: SMSI appears eight times in the sheet and there is
no reason to ask eight times. The cache is a courtesy for repeated local runs,
not a store: adjusted history is rewritten backwards on every corporate action,
so a stale cache silently drifts from the source. Delete `out/bars/` whenever
that matters and pay for the refetch.
"""

from __future__ import annotations

import csv
import time
from datetime import date, timedelta
from typing import Final, Iterable

from app.services.entry_features import Bar, Bars
from research._bootstrap import out_dir

#: Politeness between calls to an unofficial, unauthenticated endpoint. 156
#: tickers at this rate is under a minute, and it is not our data source to
#: hammer.
REQUEST_PAUSE_SECONDS: Final[float] = 0.4

#: How long a cached file is trusted before it is refetched. A day: adjusted
#: history is rewritten backwards on every split, and a research run that spans
#: a corporate action should notice.
CACHE_MAX_AGE_DAYS: Final[int] = 1

_HEADER: Final[tuple[str, ...]] = (
    "date", "open", "high", "low", "close", "adj_close", "volume", "split",
)


class PriceError(Exception):
    """
    The bars could not be fetched, and it is not a fact about the company.

    Distinct from an empty result on purpose. An empty frame for a delisted
    ticker is an answer; a timeout is not, and treating them alike would let a
    bad afternoon look like a coverage limit.
    """


# ==============================================================================
# Cache
# ==============================================================================

def _cache_path(ticker: str):
    safe = ticker.replace("/", "_").replace("\\", "_").replace(" ", "_")
    return out_dir("bars") / f"{safe}.csv"


def _read_cache(ticker: str, today: date) -> Bars | None:
    path = _cache_path(ticker)
    if not path.exists():
        return None

    with path.open(encoding="utf-8", newline="") as handle:
        lines = handle.read().splitlines()

    fetched: date | None = None
    for line in lines:
        if line.startswith("# fetched:"):
            try:
                fetched = date.fromisoformat(line.split(":", 1)[1].strip())
            except ValueError:
                return None
            break
    if fetched is None or (today - fetched).days > CACHE_MAX_AGE_DAYS:
        return None

    rows: list[Bar] = []
    for row in csv.DictReader(l for l in lines if not l.startswith("#")):
        rows.append(
            Bar(
                day=date.fromisoformat(row["date"]),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                adj_close=float(row["adj_close"]),
                volume=int(float(row["volume"])),
                split=float(row["split"]),
            )
        )
    return Bars(ticker=ticker, rows=tuple(rows))


def _write_cache(bars: Bars, start: date, end: date, today: date) -> None:
    path = _cache_path(bars.ticker)
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(f"# {bars.ticker} daily, yfinance auto_adjust=False actions=True\n")
        handle.write(f"# requested: {start} .. {end}\n")
        handle.write(f"# fetched: {today}\n")
        writer = csv.writer(handle)
        writer.writerow(_HEADER)
        for row in bars.rows:
            writer.writerow(
                [
                    row.day.isoformat(),
                    f"{row.open:.6f}", f"{row.high:.6f}", f"{row.low:.6f}",
                    f"{row.close:.6f}", f"{row.adj_close:.6f}",
                    row.volume, f"{row.split:.6f}",
                ]
            )


# ==============================================================================
# Fetch
# ==============================================================================

def fetch(
    ticker: str,
    start: date,
    end: date,
    *,
    today: date | None = None,
    use_cache: bool = True,
) -> Bars:
    """
    Daily bars for one ticker, as quoted and adjusted, with split events.

    An empty `Bars` is a legitimate answer — the ticker is dead, or was never
    covered. `PriceError` is not: it means the fetch itself failed and the
    question is unanswered.
    """
    now = today or date.today()
    if use_cache:
        cached = _read_cache(ticker, now)
        if cached is not None:
            return cached

    try:
        import yfinance as yf

        frame = yf.Ticker(ticker).history(
            start=start.isoformat(),
            end=(end + timedelta(days=1)).isoformat(),  # yfinance end is exclusive
            interval="1d",
            auto_adjust=False,
            actions=True,
        )
    except Exception as exc:  # noqa: BLE001 — every failure is the same absence
        raise PriceError(f"{ticker}: stažení historie selhalo — {exc}") from exc

    if frame is None:
        raise PriceError(f"{ticker}: yfinance nevrátil nic")

    if frame.empty:
        bars = Bars(ticker=ticker, rows=())
        if use_cache:
            _write_cache(bars, start, end, now)
        return bars

    missing = [c for c in ("Open", "High", "Low", "Close") if c not in frame]
    if missing:
        raise PriceError(
            f"{ticker}: v odpovědi chybí sloupce {missing} — tvar dat se změnil, "
            f"nedopočítávám to"
        )

    # `Adj Close` disappears when a future yfinance changes its default. Falling
    # back to `Close` would silently make the adjusted series the raw one and
    # every reconciliation verdict would flip, so it is an error, not a default.
    if "Adj Close" not in frame:
        raise PriceError(
            f"{ticker}: chybí sloupec 'Adj Close' — bez něj nejde odlišit "
            f"kurz z toho dne od zpětně přepočteného"
        )

    rows: list[Bar] = []
    for stamp, row in frame.iterrows():
        close = row["Close"]
        if close != close:  # NaN rows exist at the edges
            continue
        rows.append(
            Bar(
                day=stamp.date(),
                open=float(row["Open"]),
                high=float(row["High"]),
                low=float(row["Low"]),
                close=float(close),
                adj_close=float(row["Adj Close"]),
                volume=int(row["Volume"]) if row["Volume"] == row["Volume"] else 0,
                split=float(row.get("Stock Splits", 0.0) or 0.0),
            )
        )

    bars = Bars(ticker=ticker, rows=tuple(rows))
    if use_cache:
        _write_cache(bars, start, end, now)
    return bars


def fetch_many(
    tickers: Iterable[str],
    start: date,
    end: date,
    *,
    today: date | None = None,
    use_cache: bool = True,
    on_progress=None,
) -> dict[str, Bars | PriceError]:
    """
    One call per distinct ticker, in order, with a pause between live calls.

    Failures are returned, not raised: a run over 156 tickers must not lose 155
    results to one bad symbol. The caller decides what an unfetchable ticker
    means, because `reconcile.py` needs that distinction and this module does
    not get to make it.
    """
    results: dict[str, Bars | PriceError] = {}
    for index, ticker in enumerate(sorted(set(tickers))):
        cached = _read_cache(ticker, today or date.today()) if use_cache else None
        try:
            results[ticker] = cached or fetch(
                ticker, start, end, today=today, use_cache=use_cache
            )
        except PriceError as exc:
            results[ticker] = exc
        if on_progress:
            on_progress(index + 1, ticker, results[ticker])
        if cached is None and use_cache:
            time.sleep(REQUEST_PAUSE_SECONDS)
    return results
