"""
Gomes AI Analyst Service
========================

AI Integration Layer for analyzing financial reports and updating stock metrics.

This service:
1. Parses quarterly reports, news, earnings calls
2. Extracts hard metrics (cash, burn rate, revenue)
3. Generates soft metrics (Gomes Score, thesis narrative)
4. Detects inflection points and catalysts

The AI follows strict prompts to maintain consistency with Gomes philosophy.

Author: GitHub Copilot with Claude Sonnet 4.5
Date: 2026-01-25
"""

import json
import logging
from typing import Optional
from datetime import datetime, date
from pydantic import BaseModel, Field

from app.core.gomes_logic import (
    AssetClass, InflectionStatus, ValuationStage,
    calculate_valuation_stage
)

logger = logging.getLogger(__name__)


# ============================================================================
# AI OUTPUT MODELS
# ============================================================================

class GomesAnalystOutput(BaseModel):
    """
    Structured output from AI analyst.
    This is what the LLM must return in JSON format.
    """
    
    # Financial Fortress Updates
    total_cash: Optional[float] = Field(None, description="Cash & equivalents in USD")
    quarterly_burn_rate: Optional[float] = Field(None, description="Quarterly cash burn (negative number)")
    cash_runway_months: Optional[int] = Field(None, description="Months of cash remaining")
    
    # Inflection Detection
    inflection_status: Optional[InflectionStatus] = Field(None, description="Business stage")
    inflection_reasoning: Optional[str] = Field(None, description="Why this stage was chosen")
    
    # Scoring (0-10)
    gomes_score: Optional[int] = Field(None, ge=0, le=10, description="Conviction score")
    score_reasoning: str = Field(..., description="Detailed scoring rationale")
    
    # Score deltas (what changed)
    score_deltas: dict[str, int] = Field(
        default_factory=dict,
        description="Point changes: {'dilution': -1, 'insider_buying': +2}"
    )
    
    # Catalysts
    primary_catalyst: Optional[str] = Field(None, description="Next major event")
    catalyst_date: Optional[date] = Field(None, description="Estimated catalyst date")
    
    # Thesis Update
    thesis_narrative: Optional[str] = Field(None, description="One-sentence investment thesis")
    thesis_changed: bool = Field(False, description="Did thesis fundamentally change?")
    
    # Insider Activity
    insider_activity: Optional[str] = Field(None, description="BUYING, HOLDING, or SELLING")
    
    # Risk Flags
    red_flags: list[str] = Field(default_factory=list, description="Negative developments")
    green_flags: list[str] = Field(default_factory=list, description="Positive developments")


# ============================================================================
# AI PROMPT TEMPLATES
# ============================================================================

GOMES_ANALYST_SYSTEM_PROMPT = """
Role: You are an expert Micro-Cap Investment Analyst following Mark Gomes' philosophy.

Philosophy:
- Focus on CASH FLOW INFLECTION (transition from burning to generating cash)
- Emphasize OPERATING LEVERAGE (revenue growing faster than expenses)
- Demand DOWNSIDE PROTECTION (cash runway, insider ownership)
- Hate corporate fluff and generic PR without hard numbers
- Binary thinking: Either a company has a path to profitability or it doesn't

Scoring Framework (0-10):
- START at 5/10 (neutral)
- DEDUCT points for:
  - Dilution (-1 to -2 points depending on severity)
  - Missed timelines or guidance cuts (-1 point)
  - Insider selling (-2 points)
  - Generic PR without metrics (-1 point)
  - Deteriorating margins (-1 to -2 points)
  - Legal issues or regulatory problems (-2 to -3 points)

- ADD points for:
  - Record backlog or growing pipeline (+1 to +2)
  - Insider buying (+2 points, strong signal)
  - Strategic partnerships with hard numbers (+1 to +2)
  - Improving margins or operating leverage (+1 to +2)
  - Path to profitability becoming clear (+2 to +3)
  - Institutional investment (+1 point)

Inflection Status Rules:
- WAIT_TIME: Company is pre-revenue, or past peak, or burning cash with no clear path
- UPCOMING: Revenue growing, approaching breakeven, or major catalyst within 6 months
- ACTIVE_GOLD_MINE: Cash flow positive, margins expanding, operational

Cash Runway Calculation:
- Extract "Cash & Equivalents" from balance sheet
- Calculate quarterly burn: Net Loss + Stock Compensation - Revenue Growth
- Runway = Cash / (Quarterly Burn / 3) months

Output Requirements:
- You MUST respond ONLY in valid JSON matching GomesAnalystOutput schema
- Be specific with numbers (e.g., "Cash: $25.5M" not "good cash position")
- Identify exact dates for catalysts when possible
- One-sentence thesis must be actionable and specific
"""

ANALYSIS_USER_PROMPT_TEMPLATE = """
Ticker: {ticker}
Current Gomes Score: {current_score}/10
Previous Thesis: {previous_thesis}

New Information (Source: {source_type}):
{document_text}

Task:
1. UPDATE CASH RUNWAY:
   - Extract latest cash balance
   - Calculate burn rate from this report
   - Compute months remaining

2. DETECT INFLECTION:
   - Is revenue accelerating?
   - Are they closer to profitability?
   - What stage are they in?

3. SCORE UPDATE:
   - Start from current score: {current_score}
   - Apply deltas based on new information
   - Explain each delta

4. EXTRACT CATALYSTS:
   - Find specific future events with dates
   - Identify the MOST important one

5. UPDATE THESIS:
   - One sentence describing current setup
   - Flag if thesis fundamentally changed

OUTPUT: JSON only, no markdown, no explanations outside JSON.
"""


# ============================================================================
# AI INTEGRATION SERVICE
# ============================================================================

class GomesAIAnalyst:
    """
    Service for AI-powered stock analysis.
    
    This wraps calls to OpenAI API (or other LLM) with Gomes-specific prompts.
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize AI analyst.
        
        Args:
            api_key: OpenAI API key (or load from settings)
        """
        self.api_key = api_key
        # TODO: Initialize OpenAI client when implementing
        # from openai import OpenAI
        # self.client = OpenAI(api_key=api_key)
    
    async def analyze_document(
        self,
        ticker: str,
        document_text: str,
        source_type: str = "quarterly_report",
        current_score: Optional[int] = 5,
        previous_thesis: Optional[str] = None
    ) -> GomesAnalystOutput:
        """
        Analyze financial document and extract Gomes metrics.
        
        Args:
            ticker: Stock ticker symbol
            document_text: Full text of earnings report, news, etc.
            source_type: Type of document (quarterly_report, news, earnings_call)
            current_score: Existing Gomes score to update from
            previous_thesis: Previous investment thesis
        
        Returns:
            Structured analysis output
        """
        
        # Build user prompt
        user_prompt = ANALYSIS_USER_PROMPT_TEMPLATE.format(
            ticker=ticker,
            current_score=current_score or 5,
            previous_thesis=previous_thesis or "Not yet established",
            source_type=source_type,
            document_text=document_text[:8000]  # Truncate to avoid token limits
        )
        
        # TODO: Actual LLM call when implementing
        # For now, return mock data
        logger.info(f"AI Analysis requested for {ticker} ({source_type})")
        
        # Mock response (replace with actual OpenAI call)
        mock_output = self._generate_mock_analysis(ticker, document_text)
        
        return mock_output
    
    def _generate_mock_analysis(self, ticker: str, text: str) -> GomesAnalystOutput:
        """
        Generate mock analysis for testing.
        
        TODO: Replace with actual LLM integration.
        """
        
        # Simple heuristics for demo
        has_revenue_growth = "revenue" in text.lower() and ("growth" in text.lower() or "increase" in text.lower())
        has_cash_mention = "cash" in text.lower()
        
        score = 7 if has_revenue_growth else 5
        
        return GomesAnalystOutput(
            total_cash=25_500_000.0 if has_cash_mention else None,
            quarterly_burn_rate=-2_100_000.0,
            cash_runway_months=12,
            inflection_status=InflectionStatus.UPCOMING if has_revenue_growth else InflectionStatus.WAIT_TIME,
            inflection_reasoning="Revenue growing, approaching commercial production" if has_revenue_growth else "Pre-revenue development stage",
            gomes_score=score,
            score_reasoning=f"Mock analysis: {'Strong fundamentals' if has_revenue_growth else 'Neutral position'}",
            score_deltas={"revenue_growth": 2} if has_revenue_growth else {},
            primary_catalyst="Q2 2026 Production Ramp",
            catalyst_date=date(2026, 6, 30),
            thesis_narrative=f"{ticker}: Transitioning to commercial production with operational leverage to commodity prices",
            thesis_changed=False,
            insider_activity="HOLDING",
            red_flags=[],
            green_flags=["Revenue growing" if has_revenue_growth else ""]
        )
    
    async def update_stock_from_analysis(
        self,
        stock,  # SQLAlchemy Stock model
        analysis: GomesAnalystOutput
    ):
        """
        Apply AI analysis results to stock model.
        
        This updates the database with new metrics.
        """
        
        # Update financial metrics
        if analysis.total_cash is not None:
            stock.total_cash = analysis.total_cash
        
        if analysis.quarterly_burn_rate is not None:
            stock.quarterly_burn_rate = analysis.quarterly_burn_rate
        
        if analysis.cash_runway_months is not None:
            stock.cash_runway_months = analysis.cash_runway_months
        
        # Update inflection status
        if analysis.inflection_status is not None:
            stock.inflection_status = analysis.inflection_status.value
        
        # Update score
        if analysis.gomes_score is not None:
            stock.gomes_score = analysis.gomes_score
        
        # Update thesis
        if analysis.thesis_narrative:
            stock.thesis_narrative = analysis.thesis_narrative
        
        # Update catalyst
        if analysis.primary_catalyst:
            stock.primary_catalyst = analysis.primary_catalyst
        
        if analysis.catalyst_date:
            stock.catalyst_date = analysis.catalyst_date
        
        # Update insider activity
        if analysis.insider_activity:
            stock.insider_activity = analysis.insider_activity
        
        # Log significant changes
        if analysis.thesis_changed:
            logger.warning(f"{stock.ticker}: THESIS CHANGED - {analysis.thesis_narrative}")
        
        if analysis.red_flags:
            logger.warning(f"{stock.ticker}: RED FLAGS - {', '.join(analysis.red_flags)}")
        
        return stock


# ============================================================================
# EXAMPLE USAGE
# ============================================================================

if __name__ == "__main__":
    import asyncio
    
    async def demo():
        analyst = GomesAIAnalyst()
        
        # Simulate Q4 earnings report
        mock_report = """
        Q4 2025 Results:
        - Revenue: $12.5M (up 45% YoY)
        - Cash & Equivalents: $25.5M
        - Operating Loss: $2.1M (down from $3.8M in Q3)
        - New backlog: $45M in signed contracts
        - Mill commissioning on track for Q2 2026
        
        Management Commentary:
        "We're approaching breakeven with improving operational efficiency.
        Expect full capacity by June 2026."
        """
        
        result = await analyst.analyze_document(
            ticker="KUYA.V",
            document_text=mock_report,
            source_type="quarterly_report",
            current_score=8
        )
        
        print("="*60)
        print("AI Analyst Output:")
        print("="*60)
        print(result.model_dump_json(indent=2))
    
    asyncio.run(demo())
