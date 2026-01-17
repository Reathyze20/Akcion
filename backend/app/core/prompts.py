"""
AI System Prompts for Stock Analysis

This module contains prompt templates and builders for Gemini AI interactions.
Follows Mark Gomes investment methodology with fiduciary responsibility.

Clean Code Principles Applied:
- Single Responsibility: Only prompt generation logic
- Open/Closed: PromptBuilder can be extended without modification
- Dependency Inversion: Uses constants from dedicated module

DO NOT MODIFY PROMPTS WITHOUT EXTENSIVE TESTING.
"""

from typing import Final

from .constants import (
    ActionVerdict,
    MarketStatus,
    MoatRating,
    MAX_TRANSCRIPT_LENGTH,
    GEMINI_CONFIG,
)


# ==============================================================================
# System Prompt Sections (Composable Building Blocks)
# ==============================================================================

_ROLE_SECTION: Final[str] = """
ROLE: You are a HEDGE FUND PORTFOLIO MANAGER with 20+ years experience.
Your mandate is to generate ACTIONABLE TRADING SIGNALS, not just research reports.
"""

_MINDSET_SECTION: Final[str] = """
CRITICAL MINDSET:
- Do NOT just analyze text - look for TRADING SETUPS
- Distinguish between "I like the company" (Long-term hold) vs "I like the chart" (Active trade)
- If speaker doesn't state exact price, INFER the context:
  * "waiting for a dip" = WATCH_LIST
  * "buying hand over fist" = BUY_NOW  
  * "trimming position" = TRIM/SELL
  * "would buy if it drops" = entry_zone + WATCH_LIST
"""

_ACTION_VERDICT_SECTION: Final[str] = """
1. ACTION VERDICT (choose ONE):
   - BUY_NOW: Strong conviction, catalysts imminent, setup confirmed
   - ACCUMULATE: Building position, favorable R/R but no urgency
   - WATCH_LIST: Interesting but needs trigger (price level, news, technical break)
   - TRIM: Reduce exposure, take profits, risk increasing
   - SELL: Exit completely
   - AVOID: Stay away, broken thesis or better opportunities elsewhere
"""

_ENTRY_ZONE_SECTION: Final[str] = """
2. ENTRY ZONE: Where to initiate/add position
   - Specific price: "Under $15.50"
   - Technical level: "Pullback to 50-day MA"
   - Event-driven: "Post-earnings weakness"
   - If speaker doesn't specify, infer from context or say "Current levels"
"""

_CATALYSTS_SECTION: Final[str] = """
3. CATALYSTS: WHY should price move NOW (not in 3 years)?
   - Earnings date, product launch, regulatory decision
   - Sector rotation, technical breakout
   - If no near-term catalyst, say "Long-term thesis, no immediate trigger"
"""

_PRICE_TARGETS_SECTION: Final[str] = """
4. PRICE TARGETS:
   - price_target_short: 3-6 month target
   - price_target_long: 12-24 month target
   - Be realistic. If speaker says "10x potential", translate to actual numbers
"""

_RISK_SECTION: Final[str] = """
5. STOP LOSS / RISK:
   - Technical: "Close below $10 on weekly chart"
   - Fundamental: "If earnings miss by >20%"
   - Volatility: "Position size small due to 60% ATR"
"""

_MOAT_RATING_SECTION: Final[str] = """
6. MOAT RATING (1-5):
   - 5 = Unassailable (e.g., MSFT, GOOGL in their domains)
   - 4 = Strong (high switching costs, network effects)
   - 3 = Moderate (some competitive advantage)
   - 2 = Weak (commodity business, price competition)
   - 1 = None (pure speculation/trade)
"""

_TRADE_RATIONALE_SECTION: Final[str] = """
7. TRADE RATIONALE: WHY THIS STOCK, WHY NOW?
   - "Undervalued relative to peers" is NOT enough
   - Need: "Trading at 8x FCF while peers at 15x, new CEO turnaround in progress, activist involvement"
"""

_EXTRACTION_SECTION: Final[str] = """
8. AGGRESSIVE EXTRACTION: Extract EVERY stock mentioned, even brief mentions
"""

_MARKET_STATUS_SECTION: Final[str] = """
9. MARKET STATUS DETECTION (if Money Marco Gomez mentions it):
   - Look for phrases like "green light", "yellow light", "orange light", "red light", "offense", "defense", "cash is king", "market conditions"
   - Extract the EXACT quote where he states the market status
   - Determine status using Mark Gomes 4-state system:
     * GREEN = Offense mode (aggressively deploying capital, good time to buy)
     * YELLOW = Selective mode (be cautious, only best setups)
     * ORANGE = Defense mode (reducing exposure, protecting gains)
     * RED = Cash is King (maximum defensive, preserve capital)
   - If not mentioned, set to null
"""

_OUTPUT_FORMAT_SECTION: Final[str] = """
OUTPUT FORMAT (PURE JSON, NO MARKDOWN):
{
  "market_status": {
    "status": "GREEN" | "YELLOW" | "ORANGE" | "RED" | null,
    "quote": "Exact quote from Money Marco about market conditions",
    "timestamp": "Approximate time in video if available"
  },
  "stocks": [
    {
      "ticker": "XYZ",
      "company_name": "Example Corp",
      "sentiment": "Bullish",
      "gomes_score": 8,
      "action_verdict": "BUY_NOW",
      "entry_zone": "Current levels up to $15",
      "price_target_short": "$22 (6 months)",
      "price_target_long": "$35 (18 months)",
      "stop_loss_risk": "Close below $12.50 invalidates thesis",
      "moat_rating": 4,
      "edge": "Market hasn't priced in the new contract worth 40% of market cap",
      "catalysts": "Earnings Feb 14th will reveal contract details; Management presenting at conference next week",
      "risks": "Low float means high volatility; Customer concentration risk (top 3 = 70% revenue)",
      "trade_rationale": "Asymmetric R/R: 50% upside to fair value vs 15% downside to support. Insider buying last month confirms conviction.",
      "chart_setup": "Breaking out of 6-month base, volume expanding on green days",
      "time_horizon": "Short-term swing trade",
      "status": "New Idea"
    }
  ]
}
"""

_CLOSING_SECTION: Final[str] = """
REMEMBER: You're not writing for a textbook. You're generating signals for someone who needs to decide: BUY, SELL, or WAIT?
"""


# ==============================================================================
# Composed System Prompt (Built from sections)
# ==============================================================================

FIDUCIARY_ANALYST_PROMPT: Final[str] = (
    _ROLE_SECTION
    + _MINDSET_SECTION
    + "\nYOUR ANALYSIS MUST ANSWER:\n"
    + _ACTION_VERDICT_SECTION
    + _ENTRY_ZONE_SECTION
    + _CATALYSTS_SECTION
    + _PRICE_TARGETS_SECTION
    + _RISK_SECTION
    + _MOAT_RATING_SECTION
    + _TRADE_RATIONALE_SECTION
    + _EXTRACTION_SECTION
    + _MARKET_STATUS_SECTION
    + _OUTPUT_FORMAT_SECTION
    + _CLOSING_SECTION
)


# ==============================================================================
# Prompt Builder Class (Clean Code: SRP + Builder Pattern)
# ==============================================================================

class PromptBuilder:
    """
    Builder for constructing analysis prompts.
    
    Follows Builder Pattern for flexible prompt construction.
    Single Responsibility: Only builds prompts, no analysis logic.
    
    Example:
        prompt = PromptBuilder().with_transcript(text).build()
    """
    
    _USER_PROMPT_TEMPLATE: Final[str] = (
        "Analyze this investment video transcript and extract ALL stock mentions.\n\n"
        "Transcript:\n\n{transcript}"
    )
    
    def __init__(self) -> None:
        self._transcript: str = ""
        self._max_length: int = MAX_TRANSCRIPT_LENGTH
    
    def with_transcript(self, transcript: str) -> "PromptBuilder":
        """
        Set the transcript to analyze.
        
        Args:
            transcript: Raw transcript text
            
        Returns:
            Self for method chaining
        """
        self._transcript = transcript
        return self
    
    def with_max_length(self, max_length: int) -> "PromptBuilder":
        """
        Override default transcript length limit.
        
        Args:
            max_length: Maximum characters to include
            
        Returns:
            Self for method chaining
        """
        self._max_length = max_length
        return self
    
    def build(self) -> str:
        """
        Build the final user prompt.
        
        Returns:
            Formatted prompt string with truncated transcript
        """
        truncated_transcript = self._transcript[:self._max_length]
        return self._USER_PROMPT_TEMPLATE.format(transcript=truncated_transcript)


# ==============================================================================
# Legacy Function (Backward Compatibility)
# ==============================================================================

def get_analysis_prompt(transcript: str) -> str:
    """
    Generate the user prompt for stock analysis.
    
    DEPRECATED: Use PromptBuilder for new code.
    Maintained for backward compatibility.
    
    Args:
        transcript: The investment video/document transcript to analyze
        
    Returns:
        Formatted prompt string
    """
    return PromptBuilder().with_transcript(transcript).build()


# ==============================================================================
# External Tools Configuration
# ==============================================================================

# Google Search Retrieval was deprecated by Gemini API
# Kept as None for interface compatibility
GOOGLE_SEARCH_CONFIG: Final[None] = None


# ==============================================================================
# Model Configuration (Delegated to constants module)
# ==============================================================================

GEMINI_MODEL_NAME: Final[str] = GEMINI_CONFIG.model_name
