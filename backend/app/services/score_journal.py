"""
Deník skóre — every conviction score the app has issued, with the date it fell.

Why this exists
---------------
The app scores companies 0–10 and builds the semafor, the Kelly sizing and its
whole advice on that number. Until 2026-08-23 it never wrote down *when* a
score was issued, so the one question that judges the entire method — did the
nines earn more than the fives? — had nothing behind it. `stocks` holds the
current score and overwrites the previous one; `conviction_score_history`
existed, and held zero rows.

It held zero rows for a reason worth remembering: three code paths did write to
it (`gomes_deep_dd`, `knowledge_synthesis`, one branch of `routes/gomes`) and
two did not — and the two that did not are the ones actually in use, the manual
score endpoint and the ticker analysis in `routes/intelligence_gomes`. Coverage
that depends on every future author remembering is not coverage.

The journal is append-only. A row is a claim the app made at a moment, and it
is never rewritten. `app/services/score_outcomes.py` reads these rows back
later and measures them against what the price actually did.

Two ways in, on purpose
-----------------------
`record_score()` is the sanctioned path: the caller knows what produced the
score and can afford a quote. `backfill_unattributed()` runs from a
`before_flush` hook and catches every score write that did not come through it.
The second exists because a journal with holes cannot be told apart from a
method that only works sometimes — and rows marked `unattributed` are
themselves the measurement of how leaky the sanctioned path is.

The two are not redundant. The hook only journals a score that actually
*changed*, because it cannot tell a reaffirmation from an incidental re-assign
of the same number. `record_score()` journals every scoring event including an
unchanged one, because a reaffirmed nine is a fresh prediction and leaving it
out would bias the sample toward volatile tickers.

Prices
------
`price_at_analysis` is a convenience, not a requirement. It is written only
when the quote is known good — `YahooFinanceCache` reports it not stale — and
NULL when the refresh failed, rather than a number nobody can stand behind.
Nothing is lost by that: the evaluator resolves a missing baseline from the
historical close on `recorded_at`, which is the more accurate figure anyway. A
stale snapshot, by contrast, would quietly corrupt every return computed from
it, and staleness that makes the app *more* confident is the failure mode this
codebase keeps producing.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Final

from loguru import logger
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import get_history

from app.models.score_history import ConvictionScoreHistory
from app.models.stock import Stock


# ==============================================================================
# Sources
# ==============================================================================
# Written to `analysis_source`. Anything not in this list is still accepted —
# the column is free text and a new caller should not be blocked by a constant
# nobody updated — but these are the ones the calibration report groups by.

SOURCE_DEEP_DD: Final[str] = "deep_dd"
SOURCE_AI_ANALYST: Final[str] = "ai_analyst"
SOURCE_TICKER_ANALYSIS: Final[str] = "ticker_analysis"
SOURCE_SYNTHESIS: Final[str] = "synthesis"
SOURCE_MANUAL: Final[str] = "manual"
SOURCE_SEED: Final[str] = "seed"

#: Written by the safety net below, never by a caller. A rising count of these
#: means a new write path was added without journaling it.
SOURCE_UNATTRIBUTED: Final[str] = "unattributed"


# ==============================================================================
# The sanctioned path
# ==============================================================================

def record_score(
    db: Session,
    *,
    ticker: str,
    score: int | None,
    source: str,
    stock: Stock | None = None,
    stock_id: int | None = None,
    price: Any = None,
    thesis_status: str | None = None,
    action_signal: str | None = None,
    rr_score: Any = None,
    deserved_score: Any = None,
    cylinders: int | None = None,
    green_line: Any = None,
    red_line: Any = None,
    line_currency: str | None = None,
    band: str | None = None,
    market_alert: str | None = None,
    source_key: str | None = None,
) -> ConvictionScoreHistory | None:
    """
    Write one scoring event to the journal.

    Adds to the session; the caller's transaction owns the commit, so a score
    and its journal row land together or not at all.

    Call it *before* the flush that writes the score. The safety net below
    checks the session for a pending row on the same ticker, so recording
    first is what stops the same event being journaled twice.

    Args:
        ticker: Stock ticker. Upper-cased here so callers cannot split the
                history of one company across two spellings.
        score: The conviction score 0–10. `None` means no score was produced,
               which is not a claim and so is not journaled — the function
               returns None rather than inventing a neutral 5.
        source: One of the SOURCE_* constants; what produced this score.
        stock: The Stock this score belongs to. Preferred over `stock_id`:
               passing the object resolves the FK at flush time, so it works
               for a stock created in the same transaction.
        stock_id: FK to `stocks`, when the caller has the id but not the row.
        price: The price this score was formed against. Pass only a quote you
               trust — `trusted_price()` is the way to get one. Anything
               unparseable is stored as NULL, never as zero.
        thesis_status: IMPROVED / STABLE / DETERIORATED / BROKEN, if known.
        action_signal: BUY / ACCUMULATE / HOLD / TRIM / SELL, if known.
        rr_score: the logarithmic R/R score (canon §4a) behind the decision.
        deserved_score: 10 − cylinders (canon §4b) — the level the company's
                operational quality entitled it to.
        cylinders: operational health 0–10. `None` is meaningful and gets
                stored: a row with no cylinders is a row where no buy could
                have been authorised, and that is worth being able to see.
        green_line, red_line, line_currency: the band the score was computed
                against, and the currency it is quoted in. Kept so the score
                can be re-derived after the analyst moves the lines.
        band: which band the price sat in.
        market_alert: the alert in force. It gates every buy, so an outcome
                measured without it cannot be read.
        source_key: GOMES / BREAKOUT_INVESTORS / OTHER.

    The block from `rr_score` down is the *decision*, as distinct from the
    score. It is optional because most callers only produce a score — but
    without it, calibration in 2027 can only ever report whether the nines beat
    the fives, never whether the band engine was right. None of it can be
    added retroactively: this journal starts on 2026-08-23 because nothing
    before that was written down.

    Returns:
        The pending row, or None when there was no score to record.
    """
    if score is None:
        return None

    normalized = (ticker or "").strip().upper()
    if not normalized:
        logger.warning("Skóre bez tickeru se nezapisuje do deníku (source={})", source)
        return None

    row = ConvictionScoreHistory(
        ticker=normalized,
        stock_id=stock_id,
        conviction_score=int(score),
        thesis_status=thesis_status,
        action_signal=action_signal,
        price_at_analysis=_as_price(price),
        analysis_source=source,
        # The decision behind the score. Absent values stay NULL — an unknown
        # cylinder count is itself the record of why no buy was possible.
        rr_score=_as_price(rr_score),
        deserved_score=_as_price(deserved_score),
        cylinders=cylinders,
        green_line=_as_price(green_line),
        red_line=_as_price(red_line),
        line_currency=line_currency,
        band=band,
        market_alert=market_alert,
        source_key=source_key,
    )
    if stock is not None:
        row.stock = stock
    db.add(row)
    return row


def trusted_price(db: Session, ticker: str) -> Decimal | None:
    """
    The current quote for `ticker`, but only if it is genuinely current.

    `YahooFinanceCache` sets `is_stale` when a refresh failed and it fell back
    to whatever it had. Such a price is fine to show on screen next to its
    warning; it is not fine as the baseline of a return measurement, where it
    would silently become the denominator of a number presented as fact.

    **Call this before modifying anything in the session.** The cache commits
    `db` on success and rolls it back on failure, so a quote taken in the
    middle of a write either commits half of it or throws it away.

    Never raises: a scoring event must be journaled even when the network is
    down. A missing baseline is recoverable later from historical bars, a
    missing row is not.
    """
    normalized = (ticker or "").strip().upper()
    if not normalized:
        return None

    try:
        from app.services.yahoo_cache import YahooFinanceCache

        data = YahooFinanceCache(db).get_stock_data(normalized)
    except Exception:  # noqa: BLE001 — any failure means "no trusted price"
        logger.exception("Cena pro deník skóre ({}) se nepodařila načíst", normalized)
        return None

    if not data or data.get("is_stale"):
        return None

    return _as_price(data.get("current_price"))


# ==============================================================================
# The safety net
# ==============================================================================

def backfill_unattributed(session: Session) -> None:
    """
    Journal any conviction score written without going through `record_score()`.

    Called from a `before_flush` hook, which is the one place that sees every
    write regardless of which route made it. Adding objects to the session here
    is supported: SQLAlchemy processes them in the same flush.

    Only *changes* are journaled. A re-assignment of the same number carries no
    information the hook can read — it may be a reaffirmed thesis or an
    unrelated update touching the field — and guessing would fill the journal
    with rows that mean nothing. The sanctioned path knows the difference and
    records reaffirmations itself.
    """
    pending = {
        row.ticker
        for row in session.new
        if isinstance(row, ConvictionScoreHistory) and row.ticker
    }

    for stock in _stocks_in_flight(session):
        ticker = (stock.ticker or "").strip().upper()
        if not ticker or ticker in pending:
            continue

        score = _changed_score(stock, is_new=stock in session.new)
        if score is None:
            continue

        session.add(
            ConvictionScoreHistory(
                ticker=ticker,
                stock_id=stock.id,
                conviction_score=score,
                price_at_analysis=None,
                analysis_source=SOURCE_UNATTRIBUTED,
            )
        )
        pending.add(ticker)
        logger.warning(
            "Skóre {} = {} zapsáno mimo record_score() — deník doplněn jako "
            "'{}'. Volající by měl použít score_journal.record_score().",
            ticker,
            score,
            SOURCE_UNATTRIBUTED,
        )


def _stocks_in_flight(session: Session) -> list[Stock]:
    """Every Stock this flush is about to write, new or modified."""
    return [
        obj
        for obj in list(session.new) + list(session.dirty)
        if isinstance(obj, Stock)
    ]


def _changed_score(stock: Stock, *, is_new: bool) -> int | None:
    """
    The new conviction score, if this flush actually changes it.

    `Session.dirty` is optimistic — an object lands there for being touched,
    not for differing — so the attribute's own history is what decides.
    """
    history = get_history(stock, "conviction_score")
    if not history.added:
        return None

    value = history.added[0]
    if value is None:
        return None

    try:
        new_score = int(value)
    except (TypeError, ValueError):
        return None

    if is_new:
        return new_score

    previous = history.deleted[0] if history.deleted else None
    if previous is not None:
        try:
            if int(previous) == new_score:
                return None
        except (TypeError, ValueError):
            pass

    return new_score


# ==============================================================================
# Helpers
# ==============================================================================

def _as_price(value: Any) -> Decimal | None:
    """
    A price or score as Decimal, or None. Never zero standing in for "unknown".

    Zero is a real value on both scales — a delisted shell really can trade at
    zero, and an R/R score of 0 means the price is at or above the Red Line —
    so a genuine 0 is kept and only unparseable input becomes None.
    """
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        logger.warning("Hodnota {!r} pro deník skóre není číslo — ukládám NULL", value)
        return None
