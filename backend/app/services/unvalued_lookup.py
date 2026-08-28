"""
Gathering what can be said about the holdings the method cannot value.

`outside_method` holds the rules and is deliberately pure. This is the part
that goes and finds the facts they read: how long the cash lasts, how much of
the portfolio rests on the company, and whether anyone can see its filings at
all.

The runway comes from the cylinder rubric
-----------------------------------------
It is computed there anyway, out of the same XBRL, and stored as a number
alongside the confirmed cylinder count. Recomputing it here would mean an HTTP
call to EDGAR inside a request, and reading it out of the sentence the rubric
wrote would be parsing prose — the thing this codebase refuses to do.

A company confirmed before the rubric started keeping that number simply has
none, and then the survival rule stays quiet rather than guessing.
"""

from __future__ import annotations

from app.core.czech import n as cz

from datetime import date, datetime

from loguru import logger
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.core.sources import InvestmentSource
from app.core.tickers import canonical_ticker, variants_of
from app.models.gomes import StockLifecycleModel
from app.models.sec import SecCoverage
from app.models.stock import Stock
from app.services.breakout_band import headroom_to_target
from app.services.breakout_lookup import breakout_views
from app.services.currency import CurrencyService
from app.services.daily_actions import convert_price
from app.services.outside_method import (
    SEVERITY_NOTE,
    Finding,
    UnvaluedPosition,
    assess,
)


def unvalued_findings(db: Session, positions: list) -> dict[str, list[Finding]]:
    """
    Findings per ticker, for every held position with no valuation band.

    Positions that HAVE a band are skipped entirely: the ladder already speaks
    for them, and adding a second voice about the same holding is how a screen
    starts contradicting itself.

    Never raises. These rules are what the app says about the money it cannot
    judge; failing to compute them must not take down the money it can.
    """
    try:
        return _gather(db, positions)
    except Exception:  # noqa: BLE001 — see docstring
        logger.exception("Pravidla pro pozice bez ocenění se nepodařilo spočítat")
        return {}


def _gather(db: Session, positions: list) -> dict[str, list[Finding]]:
    total = _portfolio_total(positions)
    out: dict[str, list[Finding]] = {}

    # The other people who cover these companies. Six of the eight holdings the
    # method cannot value are on Breakout's list, so for most of the silence
    # there is at least a number from somebody — not a valuation, and said as
    # such, but better than the nothing that was here before.
    views = breakout_views(db)

    for pos in positions:
        ticker = (pos.ticker or "").upper()
        if not ticker or _has_band(db, ticker):
            continue

        value = _value(pos)
        findings = assess(
            UnvaluedPosition(
                ticker=ticker,
                weight_pct=(value / total * 100.0) if total and value else None,
                sec_covered=_sec_covered(db, ticker),
                **_runway(db, ticker),
            )
        )
        findings.extend(_breakout_note(pos, ticker, views))
        if findings:
            out[ticker] = findings
    return out


def _breakout_note(pos, ticker: str, views: dict) -> list[Finding]:
    """
    What Breakout thinks a company worth, for a company the method cannot value.

    Deliberately a NOTE and never a REVIEW or an EXIT. Their number is a target
    derived from a downloaded ratio, not a valuation of the business, and it has
    no floor — so it cannot say "cheap" and must not be allowed to sound like it.
    What it can say is how far today's price sits from what that community
    expects, which for six of these eight holdings is the only outside opinion
    the app has.

    The conversion is the point of doing this here rather than inline. Their
    targets quote the US listing in dollars while `DBO.TO` and `GSI.V` trade in
    Canadian dollars and `IMP.V` and `KUYA.V` are held in euros. Comparing those
    raw is wrong by the whole exchange rate, which is the defect that already
    produced one wrong recommendation on GSI.V.
    """
    view = views.get(canonical_ticker(ticker))
    if view is None or view.red_line is None:
        return []

    def convert(price: float, frm: str, to: str) -> float | None:
        return convert_price(price, frm, to, CurrencyService.get_rate_to_czk)

    headroom, warning = headroom_to_target(
        view, _price(pos), (pos.currency or "").upper() or None, convert
    )
    if warning:
        return [Finding(ticker, SEVERITY_NOTE, warning)]
    if headroom is None:
        return []

    backing = f"{view.endorsements} {_podpisy(view.endorsements)}"
    direction = (
        f"{cz(headroom, 0)} % nad dnešní cenou"
        if headroom >= 0
        else f"{cz(abs(headroom), 0)} % POD dnešní cenou"
    )
    return [
        Finding(
            ticker, SEVERITY_NOTE,
            f"Breakout u téhle firmy čeká {cz(view.red_line, 2)} USD — {direction} "
            f"({backing}). Je to cíl odvozený z jejich staženého seznamu, ne "
            f"ocenění firmy: spodní hranici nemají, takže z toho pásmo ani "
            f"nákup nedělám",
        )
    ]


def _price(pos) -> float | None:
    value = getattr(pos, "current_price", None)
    return float(value) if value else None


def _podpisy(n: int) -> str:
    """Czech counts one, a few, and many differently, and a screen that gets it
    wrong reads as machine output rather than as something written for you."""
    if n == 1:
        return "podpis"
    if 2 <= n <= 4:
        return "podpisy"
    return "podpisů"


def _has_band(db: Session, ticker: str) -> bool:
    """Whether the ladder can speak for this holding, in which case this does not."""
    symbols = variants_of(ticker) or (ticker.upper(),)
    return (
        db.query(Stock)
        .filter(Stock.ticker.in_(symbols))
        .filter(Stock.source_key == InvestmentSource.GOMES.value)
        .filter(Stock.green_line.isnot(None))
        .filter(Stock.red_line.isnot(None))
        .first()
    ) is not None


def _sec_covered(db: Session, ticker: str) -> bool:
    row = (
        db.query(SecCoverage)
        .filter(SecCoverage.ticker.in_(variants_of(ticker) or (ticker.upper(),)))
        .first()
    )
    return bool(row and row.status == "COVERED" and row.cik)


def _runway(db: Session, ticker: str) -> dict:
    """
    Months of cash, as the cylinder rubric measured them when confirmed.

    Absent for anything confirmed before the rubric kept that figure as a
    number, and then the survival rule stays quiet — which is right, because
    the alternative is reading it back out of a Czech sentence.
    """
    row = (
        db.query(StockLifecycleModel)
        .filter(StockLifecycleModel.ticker == (canonical_ticker(ticker) or ticker.upper()))
        .filter(StockLifecycleModel.valid_until.is_(None))
        .order_by(desc(StockLifecycleModel.detected_at))
        .first()
    )
    signals = (row.phase_signals if row is not None else None) or {}
    months = signals.get("runway_months")
    as_of_raw = signals.get("runway_as_of")

    as_of: date | None = None
    if isinstance(as_of_raw, str):
        try:
            as_of = datetime.fromisoformat(as_of_raw).date()
        except ValueError:
            as_of = None

    return {
        "runway_months": float(months) if months is not None else None,
        "runway_as_of": as_of,
    }


def _value(pos) -> float | None:
    if pos.current_price is None or not pos.shares:
        return None
    return pos.current_price * pos.shares


def _portfolio_total(positions: list) -> float:
    """
    In each position's own quoted currency, deliberately.

    A weight is a ratio, and mixing currencies only distorts it when the mix
    changes — which is a smaller error than skipping the rule entirely for a
    portfolio spread across three currencies. The result is used to ask "is
    this a big part of the money", never to price anything.
    """
    return sum(v for v in (_value(p) for p in positions) if v)
