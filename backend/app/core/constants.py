"""
Core Constants Module

Centralized configuration for the AI analysis system.
All magic numbers and strings are defined here for maintainability.

Clean Code Principles Applied:
- No magic numbers/strings scattered in code
- Single source of truth for configuration
- Easy to modify and test
"""

from enum import Enum, auto
from dataclasses import dataclass
from typing import Final


# ==============================================================================
# Transcript Processing Limits
# ==============================================================================

MAX_TRANSCRIPT_LENGTH: Final[int] = 30_000
"""Maximum characters to send to AI to prevent token overflow."""

REQUEST_TIMEOUT_SECONDS: Final[int] = 10
"""HTTP request timeout for external API calls."""


# ==============================================================================
# Action Verdicts (Trading Signals)
# ==============================================================================

class ActionVerdict(str, Enum):
    """
    Trading action signals following Mark Gomes methodology.
    
    Each verdict represents a clear, actionable decision:
    - Not ambiguous "maybe" signals
    - Each has specific meaning for position management
    """
    BUY_NOW = "BUY_NOW"
    """Strong conviction, catalysts imminent, setup confirmed."""
    
    ACCUMULATE = "ACCUMULATE"
    """Building position, favorable R/R but no urgency."""
    
    WATCH_LIST = "WATCH_LIST"
    """Interesting but needs trigger (price level, news, technical break)."""
    
    TRIM = "TRIM"
    """Reduce exposure, take profits, risk increasing."""
    
    SELL = "SELL"
    """Exit completely."""
    
    AVOID = "AVOID"
    """Stay away, broken thesis or better opportunities elsewhere."""


# ==============================================================================
# Market Status (Traffic Light System)
# ==============================================================================

class MarketStatus(str, Enum):
    """
    Mark Gomes 4-state market condition system.
    
    Determines overall portfolio stance and risk appetite.
    """
    GREEN = "GREEN"
    """Offense mode - aggressively deploying capital, good time to buy."""
    
    YELLOW = "YELLOW"
    """Selective mode - be cautious, only best setups."""
    
    ORANGE = "ORANGE"
    """Defense mode - reducing exposure, protecting gains."""
    
    RED = "RED"
    """Cash is King - maximum defensive, preserve capital."""


# ==============================================================================
# Moat Rating Scale
# ==============================================================================

class MoatRating(int, Enum):
    """
    Competitive advantage rating on 1-5 scale.
    
    Based on Warren Buffett's economic moat concept.
    """
    NONE = 1
    """Pure speculation/trade, no competitive advantage."""
    
    WEAK = 2
    """Commodity business, price competition."""
    
    MODERATE = 3
    """Some competitive advantage."""
    
    STRONG = 4
    """High switching costs, network effects."""
    
    UNASSAILABLE = 5
    """Dominant position (e.g., MSFT, GOOGL in their domains)."""


# ==============================================================================
# Sentiment Categories
# ==============================================================================

class Sentiment(str, Enum):
    """Stock sentiment classification."""
    BULLISH = "Bullish"
    NEUTRAL = "Neutral"
    BEARISH = "Bearish"


# ==============================================================================
# Stock Status Categories
# ==============================================================================

class StockStatus(str, Enum):
    """Tracking status for portfolio management."""
    NEW_IDEA = "New Idea"
    ACTIVE_POSITION = "Active Position"
    WATCHING = "Watching"
    CLOSED = "Closed"


# ==============================================================================
# AI Model Configuration
# ==============================================================================

@dataclass(frozen=True)
class GeminiConfig:
    """
    Immutable configuration for Gemini AI model.
    
    Frozen dataclass ensures these values cannot be accidentally modified.
    """
    model_name: str = "gemini-3-pro-preview"
    """Most intelligent Gemini model for financial analysis."""
    
    max_output_tokens: int = 8192
    """Maximum response length."""
    
    temperature: float = 0.1
    """Low temperature for consistent, factual responses."""


GEMINI_CONFIG: Final[GeminiConfig] = GeminiConfig()


# ==============================================================================
# URL Patterns for Content Extraction
# ==============================================================================

@dataclass(frozen=True)
class URLPatterns:
    """Regex patterns for extracting IDs from URLs."""
    
    youtube_watch: str = r'(?:youtube\.com\/watch\?v=|youtu\.be\/)([\w-]+)'
    youtube_embed: str = r'youtube\.com\/embed\/([\w-]+)'
    google_docs: str = r'docs\.google\.com/document/d/([a-zA-Z0-9-_]+)'


URL_PATTERNS: Final[URLPatterns] = URLPatterns()


# ==============================================================================
# Supported Languages for YouTube Transcripts
# ==============================================================================

TRANSCRIPT_LANGUAGES: Final[tuple[str, ...]] = ('en', 'en-US', 'en-GB')
"""Priority order for fetching YouTube transcripts."""


# ==============================================================================
# Error Messages (Centralized for i18n readiness)
# ==============================================================================

@dataclass(frozen=True)
class ErrorMessages:
    """
    Centralized error messages for consistent user communication.
    
    Keeping messages in one place allows:
    - Easy internationalization (i18n)
    - Consistent tone and formatting
    - Easy testing of error conditions
    """
    INVALID_GOOGLE_DOCS_URL: str = "Invalid Google Docs URL format"
    EMPTY_DOCUMENT: str = "Document is empty"
    DOCUMENT_ACCESS_DENIED: str = (
        "Cannot access document. Ensure it's shared as 'Anyone with the link can view'"
    )
    REQUEST_TIMEOUT: str = "Request timeout - check internet connection"
    INVALID_JSON_RESPONSE: str = "AI returned invalid JSON"
    ANALYSIS_FAILED: str = "Analysis failed"


ERROR_MESSAGES: Final[ErrorMessages] = ErrorMessages()
