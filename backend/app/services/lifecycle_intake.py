"""
Gathering the facts the lifecycle rubric reads, and writing the confirmation.

`lifecycle_rubric.py` holds the rules and knows nothing about the database. This
is the part that goes and finds what they read, and the part that turns an
agreed proposal into the `phase` every tier and de-risking rule depends on.

The high-water mark, and why it is the 52-week high
---------------------------------------------------
The canon describes Wait Time as retracing "a large part of the Great Find move"
— a fall from the peak, not from what you paid. The app has no price history to
find that peak with: `ohlcv_data` is empty and the score journal only opened on
2026-08-23.

Yahoo publishes `fiftyTwoWeekHigh` and the quote cache already stores the raw
payload, so it is used — and labelled as what it is. A 52-week high is not an
all-time high, and a company that peaked two years ago will read as less
retraced than it is. That is a stated limitation, not a silent approximation.

The runway comes from the cylinder confirmation
-----------------------------------------------
It is computed there from the same XBRL and stored as a **number** beside the
confirmed count. Reading it back out of the Czech sentence the rubric wrote
would be parsing prose, which this codebase refuses to do.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Final

from loguru import logger
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.core.sources import InvestmentSource, normalize_source
from app.core.tickers import canonical_ticker, variants_of
from app.models.gomes import StockLifecycleModel
from app.models.portfolio import Position
from app.services.analyst_roster import load as load_roster
from app.services.currency import CurrencyService
from app.services.daily_actions import convert_price
from app.services.price_history import peak_since
from app.services.finnhub_metrics import fetch as fetch_finnhub
from app.core.sources import lifecycle_source_rank
from app.services.lifecycle_rubric import (
    GOLD_MINE,
    GREAT_FIND,
    PHASE_RANK,
    LAYER_FINNHUB,
    LAYER_NONE,
    LAYER_XBRL,
    LAYER_YAHOO,
    WAIT_TIME,
    LifecycleInputs,
    LifecycleProposal,
    apply_ratchet,
    propose_phase,
)

#: How `stock_lifecycle.phase` is spelled for a confirmed reading, and the
#: marker that says a human agreed rather than a rubric proposed.
SOURCE_RUBRIC = "lifecycle_rubric"

#: Words an analyst might use, mapped to the canon's stages. Deliberately short
#: and explicit — the same reasoning as the analyst roster: matching by
#: similarity is the quiet mistake that costs money.
_ANALYST_WORDS: dict[str, str] = {
    "gold mine": GOLD_MINE,
    "goldmine": GOLD_MINE,
    "zlatý důl": GOLD_MINE,
    "wait time": WAIT_TIME,
    "waittime": WAIT_TIME,
    "čekání": WAIT_TIME,
    "great find": GREAT_FIND,
    "greatfind": GREAT_FIND,
    "objev": GREAT_FIND,
}


def gather(
    db: Session,
    ticker: str,
    *,
    fundamentals: Any | None = None,
    as_of: date | None = None,
) -> LifecycleInputs:
    """
    Everything the rubric reads for one company, out of what is already stored.

    `fundamentals` is passed in rather than fetched, for the same reason the
    cylinder intake does it: reading XBRL is an HTTP call per company and the
    caller decides whether to pay for it.
    """
    day = as_of or datetime.now(timezone.utc).date()
    symbols = variants_of(ticker) or (ticker.upper(),)

    price, high, peak_label = _price_and_high(db, symbols, ticker)
    numbers, layer = _numbers(db, symbols, fundamentals)
    analyst, name, when = _analyst_stance(db, symbols)

    return LifecycleInputs(
        ticker=ticker.upper(),
        layer=layer,
        as_of=day,
        current_price=price,
        high_water=high,
        high_water_on_cs=peak_label,
        runway_months=_runway_months(db, ticker),
        analyst_says=analyst,
        analyst_name=name,
        analyst_on=when,
        **numbers,
    )


#: A price and a high measured this far apart do not describe the same moment,
#: and dividing one by the other reports a drawdown that is partly just time.
MAX_PRICE_GAP_DAYS: Final[int] = 7


def _price_and_high(
    db: Session, symbols: tuple[str, ...], ticker: str
) -> tuple[float | None, float | None, str | None]:
    """
    Today's price and the peak of the last two years, in the same currency.

    Returns `(price, peak, peak_label_cs)`. The label carries the peak's DATE,
    because "63 % pod maximem" and "63 % pod maximem z listopadu 2024" are
    different claims: only the second lets a person judge whether that peak was
    the Great Find move the canon is talking about.

    Three things this gets right that the first version did not
    -----------------------------------------------------------
    **The price comes from the position.** `yahoo_finance_cache.current_price`
    for ECOR was 6,19 from 26 July while the position carried 10,52 from
    21 August. The rubric read the month-old figure, computed a 41 % drawdown
    that was really 4 %, and that flipped ECOR from Gold Mine to Wait Time.
    Stale is the same defect as missing, one floor up.

    **The peak comes from stored history, not a 52-week high.** A thesis that
    topped eighteen months ago reads as un-retraced through a one-year window.

    **The currencies are reconciled, not assumed.** `IMP.V` is held in euros
    and its history is `ITMSF` in dollars. The peak is converted into the
    position's currency through the same rate the rest of the engine uses; with
    no rate, no peak is returned and the gap is named.
    """
    pos = (
        db.query(Position)
        .filter(Position.ticker.in_(symbols))
        .filter(Position.shares_count > 0)
        .first()
    )
    if pos is None or not pos.current_price:
        return None, None, None

    price = float(pos.current_price)
    peak = peak_since(db, ticker)
    if peak is None:
        return price, None, None

    held_ccy = (pos.currency or "").upper()
    peak_ccy = _currency_of(db, peak.symbol)

    value = peak.value
    if held_ccy and peak_ccy and held_ccy != peak_ccy:
        converted = convert_price(
            value, peak_ccy, held_ccy, CurrencyService.get_rate_to_czk
        )
        if converted is None:
            return price, None, None
        value = converted

    return price, value, peak.label_cs


def _currency_of(db: Session, symbol: str) -> str | None:
    """
    Which money a listing quotes in, as the quote cache recorded it.

    None when nobody wrote it down — and then the caller compares without
    converting, which is right: an unknown currency is not a licence to invent
    an exchange rate, and the two symbols are usually the same listing anyway.
    """
    if not symbol:
        return None
    from sqlalchemy import text

    row = db.execute(
        text("SELECT currency FROM yahoo_finance_cache WHERE ticker = :s LIMIT 1"),
        {"s": symbol.upper()},
    ).first()
    return (row.currency or "").upper() if row and row.currency else None


def _numbers(
    db: Session, symbols: tuple[str, ...], fundamentals: Any | None
) -> tuple[dict[str, Any], str]:
    """
    Revenue trajectory, cash generation and margin move, plus where they came
    from.

    Three layers in order of how directly the app saw the numbers:

      1. **SEC XBRL** — the app reads the tagged filings and knows which period
         each figure covers. Seven of the twelve holdings.
      2. **Finnhub** — a vendor's year-on-year computation over filings the app
         never read. It reaches the Canadian listings through their US OTC
         symbols and closes most of the 60 % that had nothing.
      3. **Yahoo trailing aggregates** — a rolling annual total, from which no
         year-on-year growth is derivable and none is invented.

    The layer is always returned with the numbers, never inferred later.
    """
    if fundamentals is not None:
        found = _from_filings(fundamentals)
        if found:
            return found, LAYER_XBRL

    vendor = _from_finnhub(symbols)
    if vendor:
        return vendor, LAYER_FINNHUB

    aggregates = _from_aggregates(db, symbols)
    if aggregates:
        return aggregates, LAYER_YAHOO
    return {}, LAYER_NONE


def _from_finnhub(symbols: tuple[str, ...]) -> dict[str, Any]:
    """
    Year-on-year revenue and margins for the companies EDGAR cannot see.

    The quarterly comparison is preferred over the trailing one where both
    exist: a rolling twelve months still carries three quarters of the old
    story, and the canon's question — has the story caught traction — is about
    the newest one.
    """
    metrics = fetch_finnhub(symbols[0] if symbols else "")
    if metrics is None:
        return {}

    out: dict[str, Any] = {}
    growth = (
        metrics.revenue_quarter_yoy_pct
        if metrics.revenue_quarter_yoy_pct is not None
        else metrics.revenue_yoy_pct
    )
    if growth is not None:
        out["revenue_yoy_pct"] = growth
    if metrics.net_margin_pct is not None:
        out["margin_pct"] = metrics.net_margin_pct
        # The sign of the net margin stands in for cash generation. Not the
        # same thing, and the layer says so — but without it a Canadian
        # listing has no profitability reading at all.
        out["operating_cash_flow"] = metrics.net_margin_pct
    return out


def _from_filings(fundamentals: Any) -> dict[str, Any]:
    """Year-on-year revenue and cash flow out of the tagged filings."""
    out: dict[str, Any] = {}

    revenue = fundamentals.get("revenue")
    if revenue is not None:
        pair = _year_on_year(revenue)
        if pair is not None:
            now, then = pair
            if then:
                out["revenue_yoy_pct"] = (now - then) / abs(then) * 100.0

    ocf = fundamentals.get("operating_cash_flow")
    if ocf is not None and getattr(ocf, "latest_quarter", None):
        out["operating_cash_flow"] = float(ocf.latest_quarter.value)

    gross = fundamentals.get("gross_profit")
    if gross is not None and revenue is not None:
        move = _margin_move(revenue, gross)
        if move is not None:
            out["margin_move_pp"] = move
    return out


def _year_on_year(series: Any) -> tuple[float, float] | None:
    """
    The latest quarter and the same quarter a year earlier.

    `year_ago_quarter()` returns the matching point on its own, not a pair —
    `latest_quarter` is the other half. It already refuses to pair a
    three-month period with a twelve-month one, which is the trap this
    comparison usually falls into.
    """
    try:
        latest = series.latest_quarter
        ago = series.year_ago_quarter()
    except Exception:  # noqa: BLE001 — an unusable series is not a crash
        return None
    if latest is None or ago is None:
        return None
    return float(latest.value), float(ago.value)


def _margin_move(revenue: Any, gross: Any) -> float | None:
    """Gross margin now against a year ago, in percentage points."""
    rev = _year_on_year(revenue)
    gro = _year_on_year(gross)
    if not rev or not gro or not rev[0] or not rev[1]:
        return None
    now = gro[0] / rev[0] * 100.0
    then = gro[1] / rev[1] * 100.0
    return now - then


def _from_aggregates(db: Session, symbols: tuple[str, ...]) -> dict[str, Any]:
    """
    Trailing-twelve-month figures for the companies EDGAR cannot see.

    No year-on-year growth is derivable here and none is invented: a rolling
    annual total is not a series. What it does give is the sign of the margin,
    which is half of "firma profituje".
    """
    from sqlalchemy import text

    row = db.execute(
        text(
            """
            SELECT operating_margin, profit_margin, revenue_ttm, net_income_ttm
            FROM yahoo_finance_cache
            WHERE ticker = ANY(:symbols)
            ORDER BY last_updated DESC NULLS LAST
            LIMIT 1
            """
        ),
        {"symbols": list(symbols)},
    ).first()
    if row is None:
        return {}

    out: dict[str, Any] = {}
    if row.operating_margin is not None:
        out["margin_pct"] = float(row.operating_margin) * 100.0
        # The sign of operating margin stands in for cash generation. It is not
        # the same thing and the layer says so; without it a Canadian listing
        # has no profitability reading at all.
        out["operating_cash_flow"] = float(row.operating_margin)
    elif row.net_income_ttm is not None:
        out["operating_cash_flow"] = float(row.net_income_ttm)
    return out


def _runway_months(db: Session, ticker: str) -> float | None:
    """
    Months of cash, as the cylinder rubric measured them when confirmed.

    A number, not a sentence — stored that way on purpose, because reading it
    back out of Czech prose is the thing this codebase refuses to do.
    """
    row = (
        db.query(StockLifecycleModel)
        .filter(
            StockLifecycleModel.ticker == (canonical_ticker(ticker) or ticker.upper())
        )
        .filter(StockLifecycleModel.valid_until.is_(None))
        .order_by(desc(StockLifecycleModel.detected_at))
        .first()
    )
    signals = (row.phase_signals if row is not None else None) or {}
    months = signals.get("runway_months")
    return float(months) if months is not None else None


def _analyst_stance(
    db: Session, symbols: tuple[str, ...]
) -> tuple[str | None, str | None, date | None]:
    """
    Whether a named analyst has placed this company in a stage.

    Only somebody on today's roster counts. The stored `source_key` is not
    trusted on its own: the roster can change afterwards, and a deactivated
    analyst must stop voting rather than keep voting forever.
    """
    from sqlalchemy import text

    roster = load_roster(db)
    rows = db.execute(
        text(
            """
            SELECT speaker, mention_date, context_snippet, key_points
            FROM ticker_mentions
            WHERE ticker = ANY(:symbols) AND is_current IS TRUE
            ORDER BY mention_date DESC
            LIMIT 40
            """
        ),
        {"symbols": list(symbols)},
    ).all()

    for row in rows:
        source = normalize_source(row.speaker, roster=roster)
        if source == InvestmentSource.OTHER.value:
            continue
        haystack = " ".join(
            filter(None, [row.context_snippet, str(row.key_points or "")])
        ).lower()
        for word, phase in _ANALYST_WORDS.items():
            if word in haystack:
                return phase, row.speaker, row.mention_date
    return None, None, None


def _row(db: Session, ticker: str) -> StockLifecycleModel | None:
    """The live lifecycle row for a company, or None when it has never had one."""
    key = canonical_ticker(ticker) or ticker.upper()
    return (
        db.query(StockLifecycleModel)
        .filter(StockLifecycleModel.ticker == key)
        .filter(StockLifecycleModel.valid_until.is_(None))
        .order_by(desc(StockLifecycleModel.detected_at))
        .first()
    )


def reached(db: Session, ticker: str) -> str | None:
    """
    The furthest stage this company has ever reached, or None.

    Falls back to `phase` for rows written before the ratchet existed and never
    re-confirmed since. A company recorded as GOLD_MINE has, by definition,
    reached GOLD_MINE; reading it any other way would re-open exactly the
    demotion §V1 closes. UNKNOWN is not a rung and never becomes a floor.
    """
    row = _row(db, ticker)
    if row is None:
        return None
    mark = (row.phase_reached or row.phase or "").upper()
    return mark if mark in PHASE_RANK else None


def propose(
    db: Session,
    ticker: str,
    *,
    fundamentals: Any | None = None,
    as_of: date | None = None,
) -> LifecycleProposal:
    """
    One company's stage, proposed. Never raises; a failure is no proposal.

    The rubric's vote is left on `proposal.phase` and the ratchet's answer on
    `proposal.effective_phase`. Both are kept because the screen has to be able
    to say *why* a Wait Time reading did not become a Wait Time stage — hiding
    the vote would make the rough-patch flag look like it came from nowhere.
    """
    try:
        proposal = propose_phase(
            gather(db, ticker, fundamentals=fundamentals, as_of=as_of)
        )
    except Exception:  # noqa: BLE001
        logger.exception("Návrh fáze cyklu pro {} selhal", ticker)
        return LifecycleProposal(
            ticker=ticker.upper(),
            unknowns=["návrh se nepodařilo spočítat — chyba je v logu"],
        )

    if proposal.phase is None:
        return proposal

    result = apply_ratchet(proposal.phase, reached(db, ticker))
    proposal.ratcheted_to = result.phase
    proposal.rough_patch = result.rough_patch
    proposal.ratchet_note_cs = result.held_back_cs
    if result.held_back_cs:
        proposal.unknowns.append(result.held_back_cs)
    return proposal


def confirm(
    db: Session,
    ticker: str,
    phase: str,
    *,
    confirmed_by: str,
    proposal: LifecycleProposal | None = None,
    now: datetime | None = None,
) -> StockLifecycleModel:
    """
    Write an agreed stage onto the company, where every tier rule reads it.

    Adds to the session without committing; the caller owns the transaction —
    the same discipline the tracker sync had to learn after a `--dry-run`
    committed halfway and blocked the next real read for twelve hours.

    The stage is deliberately NOT given an expiry. Cylinders expire at the next
    earnings because quality is a quarterly reading; a lifecycle stage changes
    when the business changes, which no date predicts. What replaces it is
    another confirmation.
    """
    moment = now or datetime.now(timezone.utc)
    key = canonical_ticker(ticker) or ticker.upper()

    row = _row(db, ticker)
    if row is None:
        row = StockLifecycleModel(ticker=key, detected_at=moment)
        db.add(row)

    # The ratchet is enforced HERE, not only in `propose`, because this is the
    # only door onto `phase` and a caller may pass a stage that came from
    # somewhere else entirely. §V1: a reading never moves the stage backwards,
    # and a Wait Time reading on a proven company becomes a rough patch instead
    # of being thrown away.
    prior = (row.phase_reached or row.phase or "").upper()
    result = apply_ratchet(phase, prior if prior in PHASE_RANK else None)
    if result.changed:
        logger.info(
            "Fáze cyklu {}: návrh {} se nezapisuje — {}", key, phase, result.held_back_cs
        )

    row.phase = result.phase

    # `source` describes where the row's CYLINDER reading came from, and this
    # function writes a phase. Stamping it `rubric` erased that provenance —
    # and with it the guard in `cylinder_intake` that stops an estimate from
    # closing out an analyst on record, because after this line the row no
    # longer looked like an analyst row. The phase's own provenance is recorded
    # in `phase_signals` below, where it belongs and where it costs nothing.
    if lifecycle_source_rank(row.source) <= lifecycle_source_rank(SOURCE_RUBRIC):
        row.source = SOURCE_RUBRIC

    # The high-water mark only ever rises.
    if PHASE_RANK.get(result.phase, 0) > PHASE_RANK.get(
        (row.phase_reached or "").upper(), 0
    ):
        row.phase_reached = result.phase

    if result.rough_patch:
        # `since` is set once and left alone. A slowdown that keeps being
        # re-detected is the same slowdown, and restamping it every run would
        # keep moving it past the cylinder confirmation it is meant to
        # invalidate — quietly re-authorising the buy this flag exists to stop.
        if not row.rough_patch:
            row.rough_patch_since = moment
        row.rough_patch = True
        row.rough_patch_note = result.held_back_cs
    elif result.phase == GOLD_MINE and row.rough_patch and phase.upper() == GOLD_MINE:
        # The numbers argue for Gold Mine on their own again: the slowdown is
        # over. Cleared only on a positive reading, never by silence.
        row.rough_patch = False
        row.rough_patch_since = None
        row.rough_patch_until = None
        row.rough_patch_note = None

    signals = dict(row.phase_signals or {})
    signals["phase_confirmed_at"] = moment.isoformat()
    signals["phase_confirmed_by"] = confirmed_by
    if proposal is not None:
        signals["phase_proposed"] = proposal.phase
        signals["phase_confidence"] = proposal.confidence
        signals["phase_layer"] = proposal.layer
        signals["phase_evidence"] = [
            {
                "towards": s.towards,
                "weight": s.weight,
                "fact_cs": s.fact_cs,
                "source": s.source,
                "as_of": s.as_of.isoformat() if s.as_of else None,
            }
            for s in proposal.signals
        ]
        signals["phase_unknowns"] = list(proposal.unknowns)
        # Recorded when the owner disagreed with the rubric. A year from now
        # this is the only way to tell whether the rubric was worth having.
        signals["phase_overridden"] = bool(
            proposal.phase and proposal.phase != phase
        )
    if result.changed:
        signals["phase_ratcheted_from"] = phase.upper()
        signals["phase_ratchet_note"] = result.held_back_cs
    row.phase_signals = signals

    logger.info("Fáze cyklu {} = {} (potvrdil {})", key, row.phase, confirmed_by)
    return row
