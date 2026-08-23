"""
SEC EDGAR API — results, outlook and insider activity for held positions.

The response shape follows the same rule as the rest of the app: an absence is
never rendered as a finding. A ticker that does not file with the SEC comes
back with `status: NOT_AN_SEC_FILER` and a Czech note saying so, which is a
different answer from a filer that reported nothing this quarter, which is in
turn different from a filing we have simply not analysed yet.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.models.portfolio import Position
from app.models.sec import InsiderTransaction, SecCoverage, SecFiling
from app.services.sec_edgar import SecEdgarClient
from app.services.sec_fundamentals import fetch_fundamentals
from app.services.sec_sync import sync_held_tickers, sync_ticker

router = APIRouter(prefix="/api/sec", tags=["sec"])


# ==============================================================================
# Schemas
# ==============================================================================

class FilingOut(BaseModel):
    form: str
    filed_date: date
    period_date: date | None
    url: str | None
    analysis: str | None
    analyzed: bool


class InsiderOut(BaseModel):
    insider_name: str
    role: str
    transaction_date: date | None
    code: str
    code_label: str | None
    signal: str
    shares: float | None
    price_per_share: float | None


class TickerSecOut(BaseModel):
    ticker: str
    status: str
    company_name: str | None
    note: str | None
    last_checked_at: str | None
    #: Exact numbers from XBRL. Empty means not fetched, not "no results".
    findings: list[str]
    gaps: list[str]
    filings: list[FilingOut]
    #: Only P and S — a real decision to transact at a market price.
    insider_trades: list[InsiderOut]
    #: Everything else: grants, gifts, tax withholding, option exercises.
    insider_non_signal_count: int


class SyncOut(BaseModel):
    ticker: str
    status: str
    company_name: str | None = None
    filings_stored: int = 0
    insider_stored: int = 0
    findings: list[str] = []
    gaps: list[str] = []
    note: str | None = None
    error: str | None = None


# ==============================================================================
# Helpers
# ==============================================================================

def _role(tx: InsiderTransaction) -> str:
    parts = []
    if tx.is_officer:
        parts.append(tx.officer_title or "vedení")
    if tx.is_director:
        parts.append("člen představenstva")
    if tx.is_ten_percent:
        parts.append("10% vlastník")
    return ", ".join(parts) or "neuvedeno"


def _held_tickers(db: Session) -> list[str]:
    rows = db.query(Position.ticker).filter(Position.shares_count > 0).distinct().all()
    return sorted({r[0].upper() for r in rows if r[0]})


# ==============================================================================
# Endpoints
# ==============================================================================

@router.get("/held", response_model=list[str])
async def held_tickers(db: Session = Depends(get_db)) -> list[str]:
    """Tickers currently held, which is what a refresh covers."""
    return _held_tickers(db)


@router.get("/{ticker}", response_model=TickerSecOut)
async def ticker_sec_data(
    ticker: str,
    with_fundamentals: bool = Query(
        True, description="Fetch exact results from XBRL (one extra SEC call)"
    ),
    db: Session = Depends(get_db),
) -> TickerSecOut:
    """
    Everything stored for one ticker — or a clear statement of why nothing is.
    """
    ticker = ticker.upper().strip()

    coverage = (
        db.query(SecCoverage).filter(SecCoverage.ticker == ticker).first()
    )
    if coverage is None:
        # Never checked. Deliberately not an empty success: "we have not
        # looked" is a different answer from "there is nothing".
        raise HTTPException(
            status_code=404,
            detail=(
                f"{ticker} zatím nebyl u SEC ověřen. Spusť POST /api/sec/sync "
                f"nebo POST /api/sec/sync/{ticker}."
            ),
        )

    filings = (
        db.query(SecFiling)
        .filter(SecFiling.ticker == ticker)
        .order_by(SecFiling.filed_date.desc())
        .limit(8)
        .all()
    )
    transactions = (
        db.query(InsiderTransaction)
        .filter(InsiderTransaction.ticker == ticker)
        .order_by(InsiderTransaction.transaction_date.desc())
        .limit(50)
        .all()
    )

    findings: list[str] = []
    gaps: list[str] = []
    if with_fundamentals and coverage.cik and coverage.status == "COVERED":
        try:
            data = fetch_fundamentals(ticker, coverage.cik, client=SecEdgarClient())
            findings, gaps = data.findings, data.gaps
        except Exception as e:  # noqa: BLE001 — reported, not swallowed
            gaps = [f"Výsledky se nepodařilo načíst: {e}"]

    signal_trades = [t for t in transactions if t.signal != "NO_SIGNAL"]

    return TickerSecOut(
        ticker=ticker,
        status=coverage.status,
        company_name=coverage.company_name,
        note=coverage.note,
        last_checked_at=(
            coverage.last_checked_at.isoformat() if coverage.last_checked_at else None
        ),
        findings=findings,
        gaps=gaps,
        filings=[
            FilingOut(
                form=f.form,
                filed_date=f.filed_date,
                period_date=f.period_date,
                url=f.url,
                analysis=f.analysis,
                analyzed=f.analysis is not None,
            )
            for f in filings
        ],
        insider_trades=[
            InsiderOut(
                insider_name=t.insider_name,
                role=_role(t),
                transaction_date=t.transaction_date,
                code=t.code,
                code_label=t.code_label,
                signal=t.signal,
                shares=t.shares,
                price_per_share=t.price_per_share,
            )
            for t in signal_trades
        ],
        insider_non_signal_count=len(transactions) - len(signal_trades),
    )


@router.post("/sync/{ticker}", response_model=SyncOut)
async def sync_one(
    ticker: str,
    with_outlook: bool = Query(
        True, description="Also read the newest filing's narrative for guidance"
    ),
    db: Session = Depends(get_db),
) -> SyncOut:
    """Refresh one ticker from SEC EDGAR."""
    result = sync_ticker(db, ticker, with_outlook=with_outlook)
    return SyncOut(**result.__dict__)


@router.post("/sync", response_model=list[SyncOut])
async def sync_all(
    with_outlook: bool = Query(
        False,
        description=(
            "Read narratives too. Off by default: it is one model call per "
            "filing, so it costs money on a full portfolio refresh."
        ),
    ),
    db: Session = Depends(get_db),
) -> list[SyncOut]:
    """
    Refresh every held position.

    One ticker failing does not stop the rest — five of fourteen holdings are
    not SEC filers, and a refresh that aborted on the first one would never
    finish.
    """
    tickers = _held_tickers(db)
    if not tickers:
        raise HTTPException(
            status_code=404,
            detail="Portfolio neobsahuje žádné držené pozice.",
        )
    results = sync_held_tickers(db, tickers, with_outlook=with_outlook)
    return [SyncOut(**r.__dict__) for r in results]
