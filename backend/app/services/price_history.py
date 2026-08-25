"""
Daily prices, and the peak that the drawdown rule is actually about.

Why this exists
---------------
The lifecycle rubric's Wait Time signal is "retraces a large part of the Great
Find move" (§3) — a fall from a peak. It was reading Yahoo's `fiftyTwoWeekHigh`,
which is the wrong peak twice over: a thesis that topped eighteen months ago
reads as not retraced at all, and the figure sits in a cache whose price field
goes stale (ECOR held a July price into late August and turned a 4 % drawdown
into 41 %, which flipped the verdict from "hold" to "sell").

Full daily history is free from the source the app already uses and
`ohlcv_data` was empty. This fills it.

Why not the all-time high
-------------------------
Because split adjustment makes it meaningless for these companies. SMSI's
adjusted history peaks at 5 120 USD, IZEA at 2 720, ECOR at 304 — every one of
them a reverse split, and against them every holding reads as 99 % retraced.
The adjustment is not wrong; reaching back through it is. A drawdown measured
across a decade is not a statement about the current thesis.

Why a stated window, and why the peak's date is reported
--------------------------------------------------------
The app's own dates cannot anchor the thesis: `investment_logs` has no entries
and `stocks.created_at` is 2026-01-24 for half the portfolio, which is the day
of the initial import rather than the day anybody formed a view.

So the window is a stated constant — and the peak's **date** is carried with the
number and printed. "63 % pod maximem z března 2025" lets a person see whether
that peak was the Great Find move or something older that happens to fall inside
the window; "63 % pod maximem" alone does not. The window is a judgement the app
makes and shows its working for, not one it hides.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Final

from loguru import logger
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.tickers import variants_of

#: How far back a drawdown is measured. Two years covers the cycle these
#: theses run on — "trvá dýl než čekáš" (§3) — without reaching into a
#: different era of the company through a reverse split.
LOOKBACK_YEARS: Final[int] = 2

#: How much history is kept. More than the window, so the window can be
#: widened later without re-fetching, and bounded so the table stays small.
STORE_YEARS: Final[int] = 5

#: Rows older than this are pruned on refresh; anything newer is upserted.
_STORE_DAYS: Final[int] = STORE_YEARS * 366
_LOOKBACK_DAYS: Final[int] = LOOKBACK_YEARS * 366


@dataclass(frozen=True)
class Peak:
    """The highest close in the window, and when it happened."""

    value: float
    on: date
    #: The window the search ran over, so the caller can say it out loud.
    since: date
    #: The listing the bars came from. Carried because it decides the currency:
    #: `ITMSF` peaks in dollars while the `IMP.V` position is priced in euros,
    #: and the caller must not divide one by the other.
    symbol: str = ""

    @property
    def label_cs(self) -> str:
        return f"{self.on.day}. {self.on.month}. {self.on.year}"


def refresh(
    db: Session,
    ticker: str,
    *,
    fetch=None,
) -> int:
    """
    Pull daily history for one company and store it. Returns rows written.

    `fetch` is injected so the rules can be exercised without a network call.
    It takes a symbol and returns rows of `(date, open, high, low, close,
    volume)`.

    Never raises: one company Yahoo cannot serve must not stop the rest.
    """
    fetcher = fetch or _fetch_from_yahoo
    symbols = variants_of(ticker) or (ticker.upper(),)

    for symbol in symbols:
        try:
            rows = fetcher(symbol)
        except Exception:  # noqa: BLE001 — see docstring
            logger.exception("Historii {} se nepodařilo stáhnout", symbol)
            continue
        if not rows:
            continue
        # Stored under the symbol that ANSWERED, not under the one asked for.
        # `IMP.V` is held in euros and its history comes from `ITMSF` in
        # dollars; filing those bars as "IMP.V" would let a later comparison
        # divide a euro price by a dollar peak and report a drawdown that is
        # really an exchange rate — the defect that already produced one wrong
        # recommendation on GSI.V.
        return _store(db, symbol.upper(), rows)

    logger.warning("Historie pro {} není nikde — zkusil jsem {}", ticker, symbols)
    return 0


def _fetch_from_yahoo(symbol: str) -> list[tuple]:
    """
    Daily bars, split- and dividend-adjusted.

    Adjusted on purpose: an unadjusted series would show a reverse split as a
    price jump and report it as a gain nobody made. The adjustment is what
    makes the drawdown a real return — the reason not to reach back a decade is
    the window, not the adjustment.
    """
    import yfinance as yf

    frame = yf.Ticker(symbol).history(period=f"{STORE_YEARS}y", interval="1d")
    if frame is None or frame.empty:
        return []

    out: list[tuple] = []
    for stamp, row in frame.iterrows():
        out.append(
            (
                stamp.date(),
                float(row["Open"]),
                float(row["High"]),
                float(row["Low"]),
                float(row["Close"]),
                int(row["Volume"] or 0),
            )
        )
    return out


def _store(db: Session, ticker: str, rows: list[tuple]) -> int:
    """
    Upsert the bars, then drop anything older than the retention window.

    Adds to the session without committing — the caller owns the transaction,
    the discipline the tracker sync had to learn after a `--dry-run` committed
    halfway and blocked the next real read for twelve hours.
    """
    payload = [
        {
            "time": datetime(d.year, d.month, d.day, tzinfo=timezone.utc),
            "ticker": ticker,
            "open": o,
            "high": h,
            "low": low,
            "close": c,
            "volume": v,
        }
        for d, o, h, low, c, v in rows
    ]
    if not payload:
        return 0

    db.execute(
        text(
            """
            INSERT INTO ohlcv_data (time, ticker, open, high, low, close, volume)
            VALUES (:time, :ticker, :open, :high, :low, :close, :volume)
            ON CONFLICT (time, ticker) DO UPDATE SET
                open = EXCLUDED.open, high = EXCLUDED.high,
                low = EXCLUDED.low, close = EXCLUDED.close,
                volume = EXCLUDED.volume
            """
        ),
        payload,
    )
    db.execute(
        text("DELETE FROM ohlcv_data WHERE ticker = :t AND time < :cutoff"),
        {
            "t": ticker,
            "cutoff": datetime.now(timezone.utc) - timedelta(days=_STORE_DAYS),
        },
    )
    return len(payload)


def peak_since(
    db: Session,
    ticker: str,
    *,
    years: int = LOOKBACK_YEARS,
    now: datetime | None = None,
) -> Peak | None:
    """
    The highest daily close in the window, with the day it happened.

    The CLOSE rather than the intraday high, deliberately: a one-minute spike
    that nobody could have sold into is not a peak the position ever had, and
    measuring a drawdown against it overstates every fall.

    None means the app has no history for this company — which is different
    from a drawdown of zero, and the caller has to say so.
    """
    moment = now or datetime.now(timezone.utc)
    since = moment - timedelta(days=years * 366)

    row = db.execute(
        text(
            """
            SELECT close, ticker, time::date AS on_day
            FROM ohlcv_data
            WHERE ticker = ANY(:symbols) AND time >= :since
            ORDER BY close DESC
            LIMIT 1
            """
        ),
        {
            "symbols": list(variants_of(ticker) or (ticker.upper(),))
            + [ticker.upper()],
            "since": since,
        },
    ).first()

    if row is None or row.close is None:
        return None
    return Peak(
        value=float(row.close),
        on=row.on_day,
        since=since.date(),
        symbol=row.ticker,
    )


def latest_close(db: Session, ticker: str) -> tuple[float, date] | None:
    """
    The most recent close the app has stored, and its day.

    Used to check that a price and a peak describe the same series before they
    are divided by each other — the guard that a stale quote and a fresh peak
    would otherwise slip past.
    """
    row = db.execute(
        text(
            """
            SELECT close, time::date AS on_day
            FROM ohlcv_data
            WHERE ticker = ANY(:symbols)
            ORDER BY time DESC
            LIMIT 1
            """
        ),
        {
            "symbols": list(variants_of(ticker) or (ticker.upper(),))
            + [ticker.upper()],
        },
    ).first()
    if row is None or row.close is None:
        return None
    return float(row.close), row.on_day
