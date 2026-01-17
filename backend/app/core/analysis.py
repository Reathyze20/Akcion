"""
Core AI Analysis Module

Handles all interactions with Gemini AI for stock analysis.
The prompts and analysis flow directly impact investment decisions.

Clean Code Principles Applied:
- Single Responsibility: Each method does one thing well
- Open/Closed: Extensible without modification via composition
- Dependency Injection: Services injected, not hardcoded
- Explicit error handling: No bare except clauses
- Small functions: Each function fits on one screen

TESTING REQUIREMENTS:
- Any changes must be validated against known Mark Gomes transcripts
- Expected output: 100% stock mention capture rate
- Gomes scoring must remain consistent with manual analysis
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Final

import google.generativeai as genai
from google.generativeai.types import GenerateContentResponse

from .constants import ERROR_MESSAGES
from .prompts import (
    FIDUCIARY_ANALYST_PROMPT,
    GOOGLE_SEARCH_CONFIG,
    GEMINI_MODEL_NAME,
    PromptBuilder,
)
from ..services.market_data import MarketDataService


logger = logging.getLogger(__name__)


# ==============================================================================
# Result Types (Explicit data structures)
# ==============================================================================

@dataclass
class AnalysisResult:
    """
    Immutable result container for stock analysis.
    
    Using dataclass instead of dict provides:
    - Type safety
    - IDE autocomplete
    - Immutability guarantee
    """
    stocks: list[dict[str, Any]]
    market_status: dict[str, Any] | None = None
    raw_response: str = ""
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result: dict[str, Any] = {"stocks": self.stocks}
        if self.market_status:
            result["market_status"] = self.market_status
        return result


# ==============================================================================
# JSON Response Cleaner (Separated concern)
# ==============================================================================

class JsonResponseCleaner:
    """
    Utility class for cleaning AI JSON responses.
    
    Single Responsibility: Only handles JSON cleanup logic.
    """
    
    _MARKDOWN_CODE_FENCE_PATTERN: Final[re.Pattern[str]] = re.compile(
        r'^```(?:json)?\n?', re.MULTILINE
    )
    _MARKDOWN_CODE_FENCE_END: Final[re.Pattern[str]] = re.compile(
        r'\n?```$', re.MULTILINE
    )
    
    @classmethod
    def clean(cls, text: str) -> str:
        """
        Remove markdown code fences from AI response.
        
        Gemini sometimes wraps JSON in ```json ... ``` blocks.
        This strips them to get pure JSON.
        
        Args:
            text: Raw AI response text
            
        Returns:
            Cleaned JSON string
        """
        if not text.startswith("```"):
            return text
        
        cleaned = cls._MARKDOWN_CODE_FENCE_PATTERN.sub('', text)
        cleaned = cls._MARKDOWN_CODE_FENCE_END.sub('', cleaned)
        return cleaned.strip()


# ==============================================================================
# Ticker Enrichment Service (Separated concern)
# ==============================================================================

class TickerEnrichmentService:
    """
    Service for validating and enriching stock ticker data.
    
    Single Responsibility: Only handles ticker validation/enrichment.
    """
    
    @staticmethod
    def enrich_stocks(stocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Validate and fix tickers using company names.
        
        Also enriches company_name if missing but ticker is valid.
        
        Args:
            stocks: List of stock dictionaries from AI
            
        Returns:
            List of stocks with validated/fixed tickers
        """
        enriched_stocks: list[dict[str, Any]] = []
        
        for stock in stocks:
            enriched_stock = TickerEnrichmentService._enrich_single_stock(stock)
            enriched_stocks.append(enriched_stock)
        
        return enriched_stocks
    
    @staticmethod
    def _enrich_single_stock(stock: dict[str, Any]) -> dict[str, Any]:
        """
        Enrich a single stock entry with validated ticker and name.
        
        Args:
            stock: Single stock dictionary
            
        Returns:
            Enriched stock dictionary
        """
        ticker = stock.get("ticker")
        company_name = stock.get("company_name")
        
        try:
            fixed_ticker = MarketDataService.fix_ticker(ticker, company_name)
            if fixed_ticker:
                stock["ticker"] = fixed_ticker
                
                # Fill company name if missing
                if not company_name:
                    stock = TickerEnrichmentService._add_company_name(
                        stock, fixed_ticker
                    )
        except Exception as e:
            # Log but don't fail - original data is still valid
            logger.warning(f"Ticker enrichment failed for {ticker}: {e}")
        
        return stock
    
    @staticmethod
    def _add_company_name(
        stock: dict[str, Any], 
        ticker: str
    ) -> dict[str, Any]:
        """
        Add company name from market data service.
        
        Args:
            stock: Stock dictionary to enrich
            ticker: Validated ticker symbol
            
        Returns:
            Stock with company_name added if available
        """
        try:
            info = MarketDataService.get_stock_info(ticker)
            if info and info.get("company_name"):
                stock["company_name"] = info["company_name"]
        except Exception as e:
            logger.debug(f"Could not fetch company name for {ticker}: {e}")
        
        return stock


# ==============================================================================
# Gemini Model Factory (Separated concern)
# ==============================================================================

class GeminiModelFactory:
    """
    Factory for creating configured Gemini model instances.
    
    Single Responsibility: Only handles model instantiation.
    """
    
    @staticmethod
    def create(
        model_name: str = GEMINI_MODEL_NAME,
        system_instruction: str = FIDUCIARY_ANALYST_PROMPT,
        tools: Any | None = GOOGLE_SEARCH_CONFIG,
    ) -> genai.GenerativeModel:
        """
        Create a configured Gemini model instance.
        
        Args:
            model_name: Name of the Gemini model to use
            system_instruction: System prompt for the model
            tools: Optional tools configuration (e.g., Google Search)
            
        Returns:
            Configured GenerativeModel instance
        """
        model_kwargs: dict[str, Any] = {
            "model_name": model_name,
            "system_instruction": system_instruction,
        }
        
        if tools is not None:
            model_kwargs["tools"] = tools
        
        return genai.GenerativeModel(**model_kwargs)


# ==============================================================================
# Stock Analyzer (Main orchestrator)
# ==============================================================================

class StockAnalyzer:
    """
    Orchestrates AI-powered stock analysis using Gemini.
    
    This class coordinates the analysis pipeline:
    1. Configure Gemini with API key
    2. Apply fiduciary system prompt
    3. Parse and validate JSON responses
    4. Enrich ticker data with market information
    
    Clean Code: This class delegates to specialized services
    instead of doing everything itself.
    """
    
    def __init__(self, api_key: str) -> None:
        """
        Initialize the analyzer with Gemini API credentials.
        
        Args:
            api_key: Google Gemini API key
        """
        self._api_key = api_key
        self._configure_api()
    
    def _configure_api(self) -> None:
        """Configure Gemini API with stored credentials."""
        genai.configure(api_key=self._api_key)
    
    def analyze_transcript(self, transcript: str) -> dict[str, Any]:
        """
        Analyze investment transcript and extract all stock mentions.
        
        This is the CORE analysis function orchestrating:
        - Prompt generation
        - AI model invocation
        - Response parsing
        - Ticker enrichment
        
        Args:
            transcript: Investment video/document content
            
        Returns:
            Dictionary with structure:
            {
                "stocks": [...],
                "market_status": {...}
            }
            
        Raises:
            ValueError: If AI returns invalid JSON
            RuntimeError: If analysis fails for other reasons
        """
        try:
            response = self._call_gemini_api(transcript)
            result = self._parse_response(response)
            enriched_result = self._enrich_result(result)
            return enriched_result.to_dict()
            
        except json.JSONDecodeError as e:
            raise ValueError(f"{ERROR_MESSAGES.INVALID_JSON_RESPONSE}: {e}")
        except Exception as e:
            raise RuntimeError(f"{ERROR_MESSAGES.ANALYSIS_FAILED}: {e}")
    
    def _call_gemini_api(self, transcript: str) -> GenerateContentResponse:
        """
        Call Gemini API with the prepared prompt.
        
        Args:
            transcript: Raw transcript text
            
        Returns:
            Gemini API response object
        """
        model = GeminiModelFactory.create()
        prompt = PromptBuilder().with_transcript(transcript).build()
        return model.generate_content(prompt)
    
    def _parse_response(self, response: GenerateContentResponse) -> AnalysisResult:
        """
        Parse Gemini response into structured AnalysisResult.
        
        Args:
            response: Raw Gemini API response
            
        Returns:
            Parsed AnalysisResult object
            
        Raises:
            json.JSONDecodeError: If response is not valid JSON
        """
        raw_text = response.text.strip()
        cleaned_text = JsonResponseCleaner.clean(raw_text)
        parsed_data = json.loads(cleaned_text)
        
        return AnalysisResult(
            stocks=parsed_data.get("stocks", []),
            market_status=parsed_data.get("market_status"),
            raw_response=raw_text,
        )
    
    def _enrich_result(self, result: AnalysisResult) -> AnalysisResult:
        """
        Enrich analysis result with validated ticker data.
        
        Args:
            result: Raw analysis result from AI
            
        Returns:
            Enriched result with validated tickers
        """
        enriched_stocks = TickerEnrichmentService.enrich_stocks(result.stocks)
        
        return AnalysisResult(
            stocks=enriched_stocks,
            market_status=result.market_status,
            raw_response=result.raw_response,
        )


# ==============================================================================
# Legacy Function (Backward Compatibility)
# ==============================================================================

def analyze_with_gemini(transcript: str, api_key: str) -> dict[str, Any] | None:
    """
    Legacy function signature for backward compatibility.
    
    DEPRECATED: Use StockAnalyzer class directly for new code.
    Maintains the same interface as the original Streamlit app.
    
    Args:
        transcript: Investment content to analyze
        api_key: Gemini API key
        
    Returns:
        Analysis results dictionary or None on failure
    """
    try:
        analyzer = StockAnalyzer(api_key)
        return analyzer.analyze_transcript(transcript)
    except Exception as e:
        logger.exception(f"Legacy analysis failed: {e}")
        return None
