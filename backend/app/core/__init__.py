"""
Core Business Logic Package

This package contains the core AI analysis and data extraction logic.
All modules follow Clean Code principles:
- Single Responsibility
- Open/Closed for extension
- Explicit typing
- No magic numbers/strings

Modules:
- constants: Centralized configuration and enums
- prompts: AI prompt templates and builders
- analysis: Gemini AI integration and stock analysis
- extractors: YouTube/Google Docs content extraction
"""

# Constants and Enums (use these for type-safe code)
from .constants import (
    ActionVerdict,
    MarketStatus,
    MoatRating,
    Sentiment,
    StockStatus,
    GEMINI_CONFIG,
    MAX_TRANSCRIPT_LENGTH,
    REQUEST_TIMEOUT_SECONDS,
    ERROR_MESSAGES,
)

# Analysis Classes and Functions
from .analysis import (
    StockAnalyzer,
    AnalysisResult,
    JsonResponseCleaner,
    TickerEnrichmentService,
    GeminiModelFactory,
    analyze_with_gemini,
)

# Prompt Building
from .prompts import (
    FIDUCIARY_ANALYST_PROMPT,
    GOOGLE_SEARCH_CONFIG,
    GEMINI_MODEL_NAME,
    PromptBuilder,
    get_analysis_prompt,  # Deprecated, use PromptBuilder
    # V2.0 Enhanced Prompts
    ENTERPRISE_ANALYST_PROMPT_V2,
    QUICK_ANALYSIS_PROMPT,
    DEEP_DD_PROMPT_V2,
    THESIS_DRIFT_PROMPT_V2,
    MARKET_CONTEXT_PROMPT,
)

# Content Extraction
from .extractors import (
    extract_video_id,
    get_youtube_transcript,
    extract_google_doc_id,
    get_google_doc_content,
)


__all__ = [
    # Constants and Enums
    "ActionVerdict",
    "MarketStatus",
    "MoatRating",
    "Sentiment",
    "StockStatus",
    "GEMINI_CONFIG",
    "MAX_TRANSCRIPT_LENGTH",
    "REQUEST_TIMEOUT_SECONDS",
    "ERROR_MESSAGES",
    # Analysis
    "StockAnalyzer",
    "AnalysisResult",
    "JsonResponseCleaner",
    "TickerEnrichmentService",
    "GeminiModelFactory",
    "analyze_with_gemini",
    # Prompts
    "FIDUCIARY_ANALYST_PROMPT",
    "GOOGLE_SEARCH_CONFIG",
    "GEMINI_MODEL_NAME",
    "PromptBuilder",
    "get_analysis_prompt",
    # V2.0 Enhanced Prompts
    "ENTERPRISE_ANALYST_PROMPT_V2",
    "QUICK_ANALYSIS_PROMPT",
    "DEEP_DD_PROMPT_V2",
    "THESIS_DRIFT_PROMPT_V2",
    "MARKET_CONTEXT_PROMPT",
    # Extractors
    "extract_video_id",
    "get_youtube_transcript",
    "extract_google_doc_id",
    "get_google_doc_content",
]
