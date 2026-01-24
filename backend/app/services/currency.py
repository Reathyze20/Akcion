"""
Currency Conversion Service

Converts various currencies to CZK for portfolio summary.
Uses Czech National Bank (CNB) for live rates with fallback to hardcoded rates.

Clean Code Principles Applied:
- Single Responsibility: Currency conversion only
- Explicit logging instead of print statements
- Type hints throughout
- Constants extracted to class level
"""

from __future__ import annotations

import logging
from typing import Dict, Final

import requests


logger = logging.getLogger(__name__)


# ==============================================================================
# Constants
# ==============================================================================

CNB_API_URL: Final[str] = (
    "https://www.cnb.cz/en/financial-markets/foreign-exchange-market/"
    "central-bank-exchange-rate-fixing/central-bank-exchange-rate-fixing/daily.txt"
)
REQUEST_TIMEOUT_SECONDS: Final[int] = 5


class CurrencyService:
    """
    Service for currency conversions to CZK.
    
    Uses CNB (Czech National Bank) API for live rates with hardcoded fallback.
    """
    
    # Fallback rates (updated 2025-01-11)
    FALLBACK_RATES: dict[str, float] = {
        "CZK": 1.00,
        "USD": 22.50,
        "EUR": 24.80,
        "GBP": 28.50,
        "CHF": 25.20,
        "HKD": 2.88,
        "JPY": 0.15,
        "CAD": 16.50,  # Canadian Dollar
        "AUD": 14.50,  # Australian Dollar
        "SGD": 16.00,  # Singapore Dollar
        "NOK": 2.10,   # Norwegian Krone
        "SEK": 2.10,   # Swedish Krona
    }
    
    # ==========================================================================
    # Public Methods
    # ==========================================================================
    
    @classmethod
    def get_rate_to_czk(cls, currency: str) -> float:
        """
        Get exchange rate from currency to CZK.
        
        Tries CNB API first, falls back to hardcoded rates.
        
        Args:
            currency: Currency code (USD, EUR, etc.)
            
        Returns:
            Exchange rate (how many CZK per 1 unit of currency)
        """
        currency = currency.upper()
        
        if currency == "CZK":
            return 1.0
        
        # Try live rates from CNB
        try:
            rate = cls._fetch_cnb_rate(currency)
            if rate is not None:
                logger.debug(f"Got live CNB rate for {currency}: {rate:.4f}")
                return rate
        except Exception as e:
            logger.warning(f"Failed to fetch live rate for {currency}, using fallback: {e}")
        
        # Use fallback rates
        fallback = cls.FALLBACK_RATES.get(currency, cls.FALLBACK_RATES["USD"])
        logger.debug(f"Using fallback rate for {currency}: {fallback:.4f}")
        return fallback
    
    @classmethod
    def convert_to_czk(cls, amount: float, from_currency: str) -> float:
        """
        Convert amount from given currency to CZK.
        
        Args:
            amount: Amount in original currency
            from_currency: Source currency code
            
        Returns:
            Amount in CZK
        """
        rate = cls.get_rate_to_czk(from_currency)
        return amount * rate
    
    # ==========================================================================
    # Private Methods
    # ==========================================================================
    
    @classmethod
    def _fetch_cnb_rate(cls, currency: str) -> float | None:
        """
        Fetch current exchange rate from Czech National Bank API.
        
        CNB format: Country|Currency|Amount|Code|Rate
        Example: USA|dollar|1|USD|22.500
        
        Args:
            currency: Currency code
            
        Returns:
            Exchange rate per 1 unit, or None if failed
        """
        try:
            response = requests.get(CNB_API_URL, timeout=REQUEST_TIMEOUT_SECONDS)
            
            if response.status_code != 200:
                return None
            
            for line in response.text.split("\n"):
                parts = line.split("|")
                if len(parts) >= 5 and parts[3] == currency:
                    amount = float(parts[2])  # How many units
                    rate = float(parts[4])    # Rate for that many units
                    return rate / amount      # Rate per 1 unit
            
            return None
            
        except Exception as e:
            logger.debug(f"CNB API error for {currency}: {e}")
            return None
    
    @classmethod
    def get_all_rates(cls) -> Dict[str, float]:
        """Get all available exchange rates to CZK"""
        rates = {}
        for currency in cls.FALLBACK_RATES.keys():
            rates[currency] = cls.get_rate_to_czk(currency)
        return rates
