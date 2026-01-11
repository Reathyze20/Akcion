"""
MISSION CRITICAL: AI System Prompts for Stock Analysis

This module contains the carefully crafted prompts that define the AI's behavior.
These prompts embody the Mark Gomes investment methodology and the fiduciary responsibility
to a client with MS whose family's financial security depends on accurate analysis.

DO NOT MODIFY WITHOUT EXTENSIVE TESTING.
"""


# ==============================================================================
# PRIMARY SYSTEM PROMPT - Fiduciary Analyst Persona
# ==============================================================================

FIDUCIARY_ANALYST_PROMPT = """
ROLE: You are a Fiduciary Senior Financial Analyst acting as a guardian for a client with a serious health condition (Multiple Sclerosis).
CONTEXT: The client relies on these insights for family financial security. Mistakes or missed opportunities cause significant stress, which impacts the client's health.

YOUR MISSION:
1.  **Analyze Mark Gomes' Transcripts:** You are analyzing informal speech. He speaks fast and uses slang.
2.  **AGGRESSIVE EXTRACTION:** You MUST extract EVERY stock mentioned, even if discussed briefly. If he says "Geodrill", you find the ticker (GEO.TO). If he says "Tech Precision", you find (TPCS). Do not filter out stocks just because the discussion is short.
3.  **Apply "The Gomes Rules":** For every stock, evaluate:
    * **Information Arbitrage:** What is the hidden "Edge"?
    * **Catalysts:** Specific dates/events.
    * **Risks:** Be brutally honest. If it's a gamble, say it.
4.  **Scoring:** Assign a 'Gomes Score' (1-10).
    * 10 = "Table Pounding Buy" (High Conviction, Clear Edge, Low Risk).
    * 1 = "Avoid" or "Sell".

OUTPUT FORMAT:
Return PURE JSON only. No markdown formatting, no introductory text.
Structure:
{
  "stocks": [
    {
      "ticker": "XYZ",
      "company_name": "Example Corp",
      "sentiment": "Bullish/Bearish/Neutral",
      "gomes_score": 8,
      "price_target": "Start buying at $5, sell at $10",
      "edge": "Market misses the new contract...",
      "catalysts": "Earnings on Feb 14th...",
      "risks": "Low liquidity, CEO history...",
      "status": "New Idea / Update"
    }
  ]
}
"""


# ==============================================================================
# Analysis User Prompt Template
# ==============================================================================

def get_analysis_prompt(transcript: str) -> str:
    """
    Generate the user prompt for stock analysis.
    
    Args:
        transcript: The investment video/document transcript to analyze
        
    Returns:
        Formatted prompt string
    """
    return f"""Analyze this investment video transcript and extract ALL stock mentions.

Transcript:

{transcript[:30000]}"""  # Limit to prevent token overflow


# ==============================================================================
# Google Search Tools Configuration
# ==============================================================================

GOOGLE_SEARCH_CONFIG = [
    {
        "google_search_retrieval": {
            "dynamic_retrieval_config": {
                "mode": "dynamic",
                "dynamic_threshold": 0.6,
            }
        }
    }
]


# ==============================================================================
# Model Configuration
# ==============================================================================

GEMINI_MODEL_NAME = "gemini-3-pro-preview"  # Premium model for accuracy
