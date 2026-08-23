"""
Market gauge API — where the S&P sits on the 40-year chart, and nothing more.

There is deliberately no endpoint that applies the reading to the semafor. The
gauge finds one of the canon's two RED calls and misses the other; a field it
could set on its own would turn that half-blindness into an instruction. It
reports, the user decides.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.models.portfolio import MarketStatus
from app.services.market_gauge import (
    INDEX_TICKER,
    GaugeError,
    agreement_cs,
    current_reading,
)

router = APIRouter(prefix="/api/market-gauge", tags=["market-gauge"])


class GaugeOut(BaseModel):
    """A reading, everything behind it, and what it cannot see."""

    index: str = INDEX_TICKER
    as_of: date
    close: float

    z_score: float = Field(description="Standard deviations from the log trend")
    percentile: float = Field(description="Where this sits in the whole window")
    position: str
    position_cs: str

    suggested_alert: str = Field(
        description="A suggestion. Nothing in the app acts on it by itself."
    )
    current_alert: str | None = None
    agreement_cs: str

    trend_value: float
    upper_line: float
    grey_line: float
    lower_line: float
    trend_pct_per_year: float
    years: float

    blind_spot_cs: str = Field(
        description=(
            "What this measure cannot see, stated in every reading — it finds "
            "the 1999 top and misses the 2007 one entirely."
        )
    )


@router.get("", response_model=GaugeOut)
def get_gauge(
    refresh: bool = Query(False, description="Přepočítat, i když je čerstvý"),
    db: Session = Depends(get_db),
) -> GaugeOut:
    """
    Where the S&P sits on its 40-year chart, and what the canon does there.

    Returns 503 rather than a default reading when the index cannot be read:
    the whole reason this exists is that GREEN must never mean "nobody looked".
    """
    try:
        reading = current_reading(refresh=refresh)
    except GaugeError as e:
        logger.warning("Market gauge nedostupný: {}", e)
        raise HTTPException(status_code=503, detail=str(e))

    status_row = db.query(MarketStatus).first()
    current = status_row.status.value if status_row else None

    return GaugeOut(
        as_of=reading.as_of,
        close=reading.close,
        z_score=round(reading.z_score, 3),
        percentile=round(reading.percentile, 1),
        position=reading.position.value,
        position_cs=reading.note_cs,
        suggested_alert=reading.suggested_alert,
        current_alert=current,
        agreement_cs=agreement_cs(reading, current),
        trend_value=round(reading.trend_value, 2),
        upper_line=round(reading.upper_line, 2),
        grey_line=round(reading.grey_line, 2),
        lower_line=round(reading.lower_line, 2),
        trend_pct_per_year=round(reading.trend_pct_per_year, 2),
        years=round(reading.years, 1),
        blind_spot_cs=reading.blind_spot_cs,
    )
