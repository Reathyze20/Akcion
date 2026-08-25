"""
Gathering what the portfolio-level risk check reads.

`concentration.py` holds the arithmetic and is pure. This finds the facts: what
each holding is worth, whether its filings raised anything material, how long
its cash lasts, and whether anyone can read it at all.

The last one is the point. Sixty percent of this portfolio by value files where
EDGAR cannot see, and for those companies every question this check asks comes
back empty. Counting an empty answer as a clean one is the defect this codebase
keeps finding, so coverage is looked up explicitly rather than inferred from an
absence of findings.
"""

from __future__ import annotations

from loguru import logger
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.core.tickers import canonical_ticker, variants_of
from app.models.gomes import StockLifecycleModel
from app.models.sec import SecCoverage, SecFiling
from app.models.sec_finding import SEVERITY_CRITICAL, SEVERITY_HIGH, SecFinding
from app.services.concentration import Holding, Reading, assess
from app.services.currency import CurrencyError, CurrencyService


def portfolio_concentration(db: Session, positions: list) -> Reading | None:
    """
    One reading of the portfolio's exposure to trouble and to not knowing.

    Never raises: this colours the day's list and must not be able to take it
    down. None means the check could not be made, and the caller then says
    nothing rather than reporting a reassuring zero.
    """
    try:
        return assess([h for h in (_holding(db, p) for p in positions) if h])
    except Exception:  # noqa: BLE001 — see docstring
        logger.exception("Koncentraci rizika se nepodařilo spočítat")
        return None


def _holding(db: Session, pos) -> Holding | None:
    ticker = (pos.ticker or "").upper()
    if not ticker or pos.current_price is None or not pos.shares:
        return None

    try:
        rate = CurrencyService.get_rate_to_czk(pos.currency or "USD")
    except CurrencyError:
        # No rate, no CZK value, no share of anything. Left out rather than
        # priced in somebody else's money.
        return None

    symbols = variants_of(ticker) or (ticker,)
    return Holding(
        ticker=ticker,
        value_czk=pos.current_price * pos.shares * rate,
        has_material_finding=_has_material_finding(db, symbols),
        runway_months=_runway(db, ticker),
        assessed=_assessed(db, symbols),
    )


def _has_material_finding(db: Session, symbols: tuple[str, ...]) -> bool:
    return (
        db.query(SecFinding)
        .filter(SecFinding.ticker.in_(symbols))
        .filter(SecFinding.severity.in_((SEVERITY_CRITICAL, SEVERITY_HIGH)))
        .first()
    ) is not None


def _assessed(db: Session, symbols: tuple[str, ...]) -> bool:
    """
    Whether anyone can read this company's filings at all.

    Coverage AND an actual analysis: a company EDGAR serves but nobody has
    opened is no more assessed than one it cannot serve, and treating the two
    alike is what would turn a blind spot into a clean bill.
    """
    covered = (
        db.query(SecCoverage)
        .filter(SecCoverage.ticker.in_(symbols))
        .filter(SecCoverage.status == "COVERED")
        .filter(SecCoverage.cik.isnot(None))
        .first()
    )
    if covered is None:
        return False

    return (
        db.query(SecFiling)
        .filter(SecFiling.ticker.in_(symbols))
        .filter(SecFiling.analysis.isnot(None))
        .first()
    ) is not None


def _runway(db: Session, ticker: str) -> float | None:
    """Months of cash, as the cylinder rubric measured them when confirmed."""
    row = (
        db.query(StockLifecycleModel)
        .filter(StockLifecycleModel.ticker == (canonical_ticker(ticker) or ticker))
        .filter(StockLifecycleModel.valid_until.is_(None))
        .order_by(desc(StockLifecycleModel.detected_at))
        .first()
    )
    months = ((row.phase_signals if row is not None else None) or {}).get("runway_months")
    return float(months) if months is not None else None
