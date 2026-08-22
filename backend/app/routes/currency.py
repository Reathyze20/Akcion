"""
Currency Exchange Rates API

Provides live exchange rates from Czech National Bank (CNB).
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.currency import CurrencyError, CurrencyService


router = APIRouter(prefix="/api/currency", tags=["currency"])


class ExchangeRatesResponse(BaseModel):
    """All exchange rates to CZK"""
    rates: dict[str, float]
    base: str = "CZK"


class ConvertRequest(BaseModel):
    """Currency conversion request"""
    amount: float
    from_currency: str
    to_currency: str = "CZK"


class ConvertResponse(BaseModel):
    """Currency conversion result"""
    original_amount: float
    from_currency: str
    converted_amount: float
    to_currency: str
    rate: float


@router.get("/rates", response_model=ExchangeRatesResponse)
async def get_exchange_rates() -> ExchangeRatesResponse:
    """
    Get all available exchange rates to CZK.
    
    Uses Czech National Bank (CNB) live rates with fallback.
    """
    rates = CurrencyService.get_all_rates()
    return ExchangeRatesResponse(rates=rates)


@router.get("/rate/{currency}")
async def get_rate(currency: str) -> dict:
    """
    Get exchange rate for specific currency to CZK.
    
    Args:
        currency: Currency code (USD, EUR, GBP, etc.)
    """
    try:
        detail = CurrencyService.get_rate(currency.upper())
    except CurrencyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {
        "currency": currency.upper(),
        "rate_to_czk": detail.value,
        "base": "CZK",
        # Whether this is today's fixing or the snapshot we fall back on.
        "is_live": detail.is_live,
        "as_of": detail.as_of.isoformat() if detail.as_of else None,
    }


@router.post("/convert", response_model=ConvertResponse)
async def convert_currency(request: ConvertRequest) -> ConvertResponse:
    """
    Convert amount between currencies.
    
    Currently only supports conversion TO CZK.
    """
    try:
        rate = CurrencyService.get_rate_to_czk(request.from_currency.upper())
    except CurrencyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    converted = request.amount * rate
    
    return ConvertResponse(
        original_amount=request.amount,
        from_currency=request.from_currency.upper(),
        converted_amount=converted,
        to_currency="CZK",
        rate=rate
    )
