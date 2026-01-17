"""
Gomes Investment Committee Analyzer
=====================================

Tento modul implementuje investiční filosofii Marka Gomese (Breakout Investors).
Analyzuje tickery podle jeho pravidel a vrací strukturované skóre 0-10.

Mark Gomes Investiční Filosofie:
---------------------------------
1. **Story First**: Každá investice musí mít silný příběh/katalyzátor
2. **Breakout Trading**: Hledáme akcie blízko 52-week high s rostoucím volume
3. **Risk Management**: NIKDY nedržíme přes earnings (14 dní před = exit)
4. **Insider Buying**: Silný bullish signál když insiders nakupují
5. **Multiple Confirmation**: Kombinujeme story + data + AI predikci

Scoring System:
---------------
Base: 0 bodů
+2 body: Insider Buying detected
+2 body: Silný Catalyst v příběhu (AI analýza)
+2 body: PatchTST predikuje růst > 5% (5 dní)
+2 body: Breakout pattern (price near 52w high + volume surge)
+1 bod: Volume trend pozitivní (20d average)
-5 bodů: Earnings za méně než 14 dní (CRITICAL RISK)

Maximum: 10 bodů
Investovatelné: >= 7 bodů

Author: GitHub Copilot with Claude Sonnet 4.5
Date: 2026-01-17
"""

from typing import Dict, Optional, List, Any
from datetime import datetime, timedelta
from decimal import Decimal
import logging
from dataclasses import dataclass
from enum import Enum

from sqlalchemy.orm import Session
from sqlalchemy import desc, func, cast
from sqlalchemy.dialects.postgresql import ARRAY, TEXT

from app.models.analysis import AnalystTranscript, SWOTAnalysis
from app.models.trading import ActiveWatchlist, MLPrediction, OHLCVData
from app.trading.ml_engine import MLPredictionEngine


# ============================================================================
# CONFIGURATION
# ============================================================================

class GomesRating(str, Enum):
    """Investiční rating podle Gomese"""
    STRONG_BUY = "STRONG_BUY"  # 9-10 bodů
    BUY = "BUY"                # 7-8 bodů
    HOLD = "HOLD"              # 5-6 bodů
    AVOID = "AVOID"            # 0-4 bodů
    HIGH_RISK = "HIGH_RISK"    # Earnings < 14 dní


@dataclass
class GomesScore:
    """Výsledek Gomes analýzy"""
    ticker: str
    total_score: int
    rating: GomesRating
    
    # Komponenty skóre
    story_score: int          # 0-2 (catalyst detected)
    breakout_score: int       # 0-2 (near 52w high + volume)
    insider_score: int        # 0-2 (insider buying)
    ml_score: int            # 0-2 (PatchTST > 5%)
    volume_score: int        # 0-1 (volume trend)
    earnings_penalty: int    # 0 or -5
    
    # Metadata
    analysis_timestamp: datetime
    confidence: str          # HIGH/MEDIUM/LOW
    reasoning: str           # Lidsky čitelné zdůvodnění
    risk_factors: List[str]  # Identifikované rizika
    
    # Data sources
    has_transcript: bool
    has_swot: bool
    has_ml_prediction: bool
    earnings_date: Optional[datetime]


# ============================================================================
# MARK GOMES AI SYSTEM PROMPT
# ============================================================================

MARK_GOMES_SYSTEM_PROMPT = """You are Mark Gomes (Money Mark), founder of Breakout Investors and expert momentum trader with 20+ years of experience. You ONLY invest in stocks with strong catalysts and breakout potential.

This is about ensuring the user's financial security, so you MUST NOT hallucinate numbers and you must be CONSERVATIVE.

YOUR CORE INVESTMENT PHILOSOPHY:
================================

1. STORY IS KING
   - Every investment MUST have a compelling story/catalyst
   - No story = No investment, period
   - Catalysts you look for:
     * New contract wins (government, enterprise)
     * FDA approvals or clinical trial success
     * Technological breakthroughs
     * Market expansion into new sectors
     * Insider buying by CEO/CFO
     * Analyst upgrades from major institutions
     * Short squeeze potential (high short interest + catalyst)
     * M&A rumors or strategic partnerships

2. LIFECYCLE PHASES (Stock Life Phases)
   You MUST determine which phase the stock is in:
   
   - **GREAT FIND:** Unknown small-cap stock, starting to grow, strong story, few institutions yet. (BUY SIGNAL)
     * Early momentum building
     * Institutional ownership < 30%
     * Strong narrative forming
     * Volume starting to increase
   
   - **WAIT TIME:** Hype died down, price declining or stagnating. Company trying to deliver results but it's taking too long. This is "DEAD MONEY". (AVOID/SELL SIGNAL)
     * Momentum stalled
     * Consolidation without catalyst
     * Execution delays
     * Investor fatigue setting in
   
   - **GOLD MINE:** Company became profitable, momentum returning, institutions entering. (SAFE BUY SIGNAL)
     * Revenue growth accelerating
     * Profitability achieved or near
     * Institutional accumulation
     * Breaking out to new highs

3. RISK/REWARD LINES (Price Targets)
   - Look for mentions of **"Green Line"** (price where stock is cheap/undervalued) - BUY ZONE
   - Look for mentions of **"Red Line"** (price where stock is expensive/fair value) - SELL ZONE
   - If Mark says "I am buying here", that's the Green Line
   - If he says "It's getting frothy" or "I'm trimming", that's the Red Line
   - Always specify both lines when mentioned

4. 10 CYLINDERS RULE (Execution Quality)
   - Is the company operating at 100%? ("Firing on all cylinders")
   - If problems mentioned (production delays, lawsuits, CFO departure), company is NOT at 10 cylinders
   - When NOT at 10 cylinders, Red Line (target price) must be lowered
   - Execution issues = reduce conviction and price targets

5. MARKET ALERTS (Overall Market State)
   Track mentions of overall market (SPY/IWM):
   - **GREEN:** Market is safe, proceed normally
   - **YELLOW:** Raise cash, sell weak positions
   - **ORANGE:** Move everything to cash/RWM
   - **RED:** Short the market, hold RWM
   
   This affects ALL individual stock decisions.

6. BREAKOUT TRADING RULES
   - Buy stocks near 52-week highs (NOT 52-week lows)
   - Volume must be surging (2x+ average = bullish)
   - Price consolidation followed by breakout = ideal entry
   - Avoid "falling knives" - never catch bottoms

7. RISK MANAGEMENT (SACRED RULES)
   - NEVER hold through earnings (exit 14+ days before)
   - Cut losses quickly (-7% to -8% max loss)
   - Position sizing: Kelly Criterion or max 5% portfolio
   - Diversification: 8-12 positions maximum

8. RED FLAGS (IMMEDIATE DISQUALIFIERS)
   - Earnings in next 14 days = AUTOMATIC SELL
   - Declining revenue trends
   - Insider selling (especially CEO/CFO)
   - Regulatory investigations
   - Accounting irregularities
   - Broken technical support levels
   - NOT firing on all 10 cylinders

9. YOUR ANALYSIS STYLE
   - Be brutally honest about risks
   - If story is weak, say so directly
   - Use specific examples from earnings calls/filings
   - Compare to similar past situations
   - Always mention earnings date risk

YOUR TASK:
==========
Analyze the provided transcript/text and extract key investment information following Mark Gomes methodology.

Return your analysis in this EXACT JSON format:
{
    "has_strong_catalyst": true/false,
    "catalyst_type": "contract_win" | "fda_approval" | "tech_breakthrough" | "insider_buying" | "analyst_upgrade" | "market_expansion" | "short_squeeze" | "ma_rumors" | "none",
    "catalyst_description": "Brief 1-2 sentence description of the catalyst",
    "lifecycle_phase": "GREAT_FIND" | "WAIT_TIME" | "GOLD_MINE" | "UNKNOWN",
    "green_line": null or number (buy price target),
    "red_line": null or number (sell price target),
    "is_undervalued": true/false (if mentioned as "cheap" but no exact Green Line given),
    "firing_on_10_cylinders": true/false/null,
    "market_alert": "GREEN" | "YELLOW" | "ORANGE" | "RED" | null,
    "conviction_level": "HIGH" | "MEDIUM" | "LOW",
    "bull_case": "Why this could work (2-3 sentences)",
    "bear_case": "What could go wrong (2-3 sentences)",
    "catalysts": ["Bullet point list of positive catalysts"],
    "risks": ["Bullet point list of identified risks"],
    "gomes_verdict": "Would Mark Gomes invest? Yes/No and why (1 sentence)"
}

CRITICAL GUIDELINES:
- Be CONSERVATIVE - only mark has_strong_catalyst=true if truly compelling
- If unsure about lifecycle phase, mark as "UNKNOWN"
- If no exact Green Line price mentioned but stock described as "cheap", set is_undervalued=true
- HIGH conviction = you'd bet your own money
- MEDIUM = interesting but needs confirmation
- LOW = weak story, avoid
- If earnings mentioned in text, FLAG IT in bear_case and risks
- If no clear catalyst found, be honest: "No clear catalyst identified"
- List catalysts and risks as bullet points for clarity

Remember: Your reputation is built on finding HIGH-QUALITY setups with REAL catalysts. Don't compromise on quality. This is about the user's family financial security - be precise and conservative.
"""


# ============================================================================
# GOMES ANALYZER
# ============================================================================

class GomesAnalyzer:
    """
    Investiční výbor simulující rozhodování Marka Gomese.
    Kombinuje AI analýzu textu, ML predikce a tvrdá data.
    """
    
    def __init__(
        self,
        db_session: Session,
        ml_engine: Optional[MLPredictionEngine] = None,
        llm_client: Optional[Any] = None,  # OpenAI/Anthropic client
        logger: Optional[logging.Logger] = None
    ):
        """
        Args:
            db_session: SQLAlchemy database session
            ml_engine: ML prediction engine (pro PatchTST predikce)
            llm_client: LLM client pro AI analýzu (OpenAI/Claude)
            logger: Logger instance
        """
        self.db = db_session
        self.ml_engine = ml_engine or MLPredictionEngine(db_session)
        self.llm_client = llm_client
        self.logger = logger or logging.getLogger(__name__)
        
    def analyze_ticker(
        self,
        ticker: str,
        transcript_text: Optional[str] = None,
        market_data: Optional[Dict[str, Any]] = None,
        force_refresh: bool = False
    ) -> GomesScore:
        """
        Hlavní analýza tickeru podle Gomes pravidel.
        
        Args:
            ticker: Stock ticker (e.g., "AAPL")
            transcript_text: Optional transcript text (if not in DB)
            market_data: Optional market data dict (earnings_date, insider_buying, etc.)
            force_refresh: Force new ML prediction
            
        Returns:
            GomesScore object s detailním skóre
            
        Raises:
            ValueError: Invalid ticker
            RuntimeError: Critical error během analýzy
        """
        self.logger.info(f"🎯 Gomes Investment Committee: Analyzing {ticker}")
        
        try:
            # Initialize score components
            story_score = 0
            breakout_score = 0
            insider_score = 0
            ml_score = 0
            volume_score = 0
            earnings_penalty = 0
            
            reasoning_parts = []
            risk_factors = []
            confidence = "MEDIUM"
            
            # ----------------------------------------------------------------
            # 1. STORY CHECK - AI Analysis
            # ----------------------------------------------------------------
            catalyst_analysis = self._analyze_story(ticker, transcript_text)
            
            if catalyst_analysis and catalyst_analysis.get("has_strong_catalyst"):
                story_score = 2
                reasoning_parts.append(
                    f"✅ Strong Catalyst: {catalyst_analysis['catalyst_description']}"
                )
                confidence = catalyst_analysis.get("conviction_level", "MEDIUM")
            else:
                reasoning_parts.append("❌ No compelling catalyst identified")
                risk_factors.append("Weak story - no clear catalyst")
            
            # ----------------------------------------------------------------
            # 2. INSIDER BUYING
            # ----------------------------------------------------------------
            insider_buying = self._check_insider_buying(ticker, market_data)
            
            if insider_buying:
                insider_score = 2
                reasoning_parts.append("✅ Insider Buying detected (Bullish)")
            
            # ----------------------------------------------------------------
            # 3. EARNINGS DATE CHECK (CRITICAL)
            # ----------------------------------------------------------------
            earnings_date = self._get_earnings_date(ticker, market_data)
            days_to_earnings = None
            
            if earnings_date:
                days_to_earnings = (earnings_date - datetime.now()).days
                
                if days_to_earnings < 14:
                    earnings_penalty = -5
                    reasoning_parts.append(
                        f"⚠️ EARNINGS RISK: {days_to_earnings} days until earnings"
                    )
                    risk_factors.append(
                        f"Earnings in {days_to_earnings} days - Gomes rule: EXIT"
                    )
                    confidence = "LOW"
            
            # ----------------------------------------------------------------
            # 4. BREAKOUT PATTERN (Technical Analysis)
            # ----------------------------------------------------------------
            breakout_analysis = self._check_breakout_pattern(ticker)
            
            if breakout_analysis.get("near_52w_high") and breakout_analysis.get("volume_surge"):
                breakout_score = 2
                reasoning_parts.append(
                    f"✅ Breakout Pattern: {breakout_analysis['distance_from_high']:.1f}% from 52w high, "
                    f"Volume +{breakout_analysis['volume_increase']:.0f}%"
                )
            
            # Volume trend bonus
            if breakout_analysis.get("volume_trend_positive"):
                volume_score = 1
                reasoning_parts.append("✅ Volume trend positive (20d)")
            
            # ----------------------------------------------------------------
            # 5. ML PREDICTION (PatchTST)
            # ----------------------------------------------------------------
            ml_prediction = self._get_ml_prediction(ticker, force_refresh)
            
            if ml_prediction:
                predicted_return = ml_prediction.get("predicted_return", 0)
                
                if predicted_return > 5.0:  # > 5% growth
                    ml_score = 2
                    reasoning_parts.append(
                        f"✅ ML Prediction: +{predicted_return:.1f}% (5-day)"
                    )
                elif predicted_return < -5.0:
                    risk_factors.append(f"ML predicts decline: {predicted_return:.1f}%")
            
            # ----------------------------------------------------------------
            # 6. CALCULATE TOTAL SCORE
            # ----------------------------------------------------------------
            total_score = (
                story_score +
                breakout_score +
                insider_score +
                ml_score +
                volume_score +
                earnings_penalty
            )
            
            # Clamp to 0-10 range
            total_score = max(0, min(10, total_score))
            
            # ----------------------------------------------------------------
            # 7. DETERMINE RATING
            # ----------------------------------------------------------------
            if earnings_penalty < 0:
                rating = GomesRating.HIGH_RISK
            elif total_score >= 9:
                rating = GomesRating.STRONG_BUY
            elif total_score >= 7:
                rating = GomesRating.BUY
            elif total_score >= 5:
                rating = GomesRating.HOLD
            else:
                rating = GomesRating.AVOID
            
            # ----------------------------------------------------------------
            # 8. BUILD GOMES SCORE
            # ----------------------------------------------------------------
            reasoning = "\n".join(reasoning_parts)
            
            gomes_score = GomesScore(
                ticker=ticker,
                total_score=total_score,
                rating=rating,
                story_score=story_score,
                breakout_score=breakout_score,
                insider_score=insider_score,
                ml_score=ml_score,
                volume_score=volume_score,
                earnings_penalty=earnings_penalty,
                analysis_timestamp=datetime.now(),
                confidence=confidence,
                reasoning=reasoning,
                risk_factors=risk_factors,
                has_transcript=bool(catalyst_analysis),
                has_swot=self._has_swot_analysis(ticker),
                has_ml_prediction=bool(ml_prediction),
                earnings_date=earnings_date
            )
            
            self.logger.info(
                f"✅ {ticker} Analysis Complete: {total_score}/10 ({rating.value})"
            )
            
            return gomes_score
            
        except Exception as e:
            self.logger.error(f"❌ Error analyzing {ticker}: {str(e)}")
            raise RuntimeError(f"Gomes analysis failed for {ticker}: {str(e)}")
    
    # ========================================================================
    # PRIVATE HELPER METHODS
    # ========================================================================
    
    def _analyze_story(
        self,
        ticker: str,
        transcript_text: Optional[str]
    ) -> Optional[Dict[str, Any]]:
        """
        AI analýza příběhu/katalyzátoru pomocí LLM.
        
        Returns:
            Dict s catalyst analysis nebo None
        """
        # Fetch from database if not provided
        if not transcript_text:
            # Use any() for array containment check - works with text[] in PostgreSQL
            transcript = (
                self.db.query(AnalystTranscript)
                .filter(func.array_position(AnalystTranscript.detected_tickers, ticker).isnot(None))
                .filter(AnalystTranscript.is_processed == True)
                .order_by(desc(AnalystTranscript.date))
                .first()
            )
            
            if transcript:
                transcript_text = transcript.processed_summary or transcript.raw_text
        
        if not transcript_text:
            self.logger.warning(f"No transcript available for {ticker}")
            return None
        
        # Call LLM for analysis
        if not self.llm_client:
            self.logger.warning("No LLM client configured - skipping AI analysis")
            return None
        
        try:
            # TODO: Implement actual LLM call based on client type
            # Example for OpenAI:
            # response = self.llm_client.chat.completions.create(
            #     model="gpt-4-turbo-preview",
            #     messages=[
            #         {"role": "system", "content": MARK_GOMES_SYSTEM_PROMPT},
            #         {"role": "user", "content": f"Analyze this transcript for {ticker}:\n\n{transcript_text}"}
            #     ],
            #     response_format={"type": "json_object"}
            # )
            # return json.loads(response.choices[0].message.content)
            
            self.logger.info("LLM analysis placeholder - implement based on your LLM provider")
            return None
            
        except Exception as e:
            self.logger.error(f"LLM analysis failed: {str(e)}")
            return None
    
    def _check_insider_buying(
        self,
        ticker: str,
        market_data: Optional[Dict[str, Any]]
    ) -> bool:
        """Check for insider buying activity"""
        if market_data and market_data.get("insider_buying"):
            return True
        
        # TODO: Integrate with SEC Edgar API or similar
        # Check Form 4 filings for insider purchases
        
        return False
    
    def _get_earnings_date(
        self,
        ticker: str,
        market_data: Optional[Dict[str, Any]]
    ) -> Optional[datetime]:
        """Get next earnings date"""
        if market_data and market_data.get("earnings_date"):
            return market_data["earnings_date"]
        
        # TODO: Integrate with earnings calendar API (Yahoo Finance, Alpha Vantage)
        
        return None
    
    def _check_breakout_pattern(self, ticker: str) -> Dict[str, Any]:
        """
        Technical analysis - breakout pattern detection.
        
        Returns:
            Dict with breakout indicators
        """
        result = {
            "near_52w_high": False,
            "volume_surge": False,
            "volume_trend_positive": False,
            "distance_from_high": 0.0,
            "volume_increase": 0.0
        }
        
        try:
            # Fetch recent OHLCV data
            ohlcv_data = (
                self.db.query(OHLCVData)
                .filter(OHLCVData.ticker == ticker)
                .order_by(desc(OHLCVData.date))
                .limit(260)  # ~1 year of trading days
                .all()
            )
            
            if len(ohlcv_data) < 20:
                self.logger.warning(f"Insufficient data for {ticker}")
                return result
            
            # Calculate metrics
            latest = ohlcv_data[0]
            recent_20d = ohlcv_data[:20]
            all_data = ohlcv_data
            
            # 52-week high check
            high_52w = max(d.high for d in all_data)
            distance = ((float(latest.close) - float(high_52w)) / float(high_52w)) * 100
            result["distance_from_high"] = distance
            
            if distance > -10:  # Within 10% of 52w high
                result["near_52w_high"] = True
            
            # Volume analysis
            avg_volume_20d = sum(float(d.volume) for d in recent_20d) / 20
            
            if len(all_data) >= 50:
                avg_volume_50d = sum(float(d.volume) for d in all_data[:50]) / 50
                volume_increase = ((avg_volume_20d - avg_volume_50d) / avg_volume_50d) * 100
                result["volume_increase"] = volume_increase
                
                if volume_increase > 50:  # 50% increase
                    result["volume_surge"] = True
                
                if volume_increase > 0:
                    result["volume_trend_positive"] = True
            
            return result
            
        except Exception as e:
            self.logger.error(f"Breakout analysis failed for {ticker}: {str(e)}")
            return result
    
    def _get_ml_prediction(
        self,
        ticker: str,
        force_refresh: bool
    ) -> Optional[Dict[str, Any]]:
        """Get ML prediction from PatchTST"""
        try:
            if force_refresh:
                return self.ml_engine.predict(ticker, save_to_db=True)
            else:
                # Try to get recent prediction from DB
                recent_pred = (
                    self.db.query(MLPrediction)
                    .filter(MLPrediction.ticker == ticker)
                    .filter(
                        MLPrediction.prediction_date >= datetime.now() - timedelta(hours=24)
                    )
                    .order_by(desc(MLPrediction.prediction_date))
                    .first()
                )
                
                if recent_pred:
                    return {
                        "predicted_return": float(recent_pred.predicted_return),
                        "confidence": recent_pred.confidence_score,
                        "quality": recent_pred.prediction_type
                    }
                else:
                    # Generate new prediction
                    return self.ml_engine.predict(ticker, save_to_db=True)
                    
        except Exception as e:
            self.logger.error(f"ML prediction failed for {ticker}: {str(e)}")
            return None
    
    def _has_swot_analysis(self, ticker: str) -> bool:
        """Check if ticker has recent SWOT analysis"""
        swot = (
            self.db.query(SWOTAnalysis)
            .join(ActiveWatchlist)
            .filter(ActiveWatchlist.ticker == ticker)
            .filter(SWOTAnalysis.is_active == True)
            .first()
        )
        return bool(swot)


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

def create_gomes_analyzer(
    db_session: Session,
    llm_api_key: Optional[str] = None,
    llm_provider: str = "openai"  # "openai" or "anthropic"
) -> GomesAnalyzer:
    """
    Factory function pro vytvoření GomesAnalyzer s configured LLM.
    
    Args:
        db_session: Database session
        llm_api_key: API key pro LLM provider
        llm_provider: "openai" nebo "anthropic"
        
    Returns:
        Configured GomesAnalyzer instance
    """
    llm_client = None
    
    if llm_api_key:
        if llm_provider == "openai":
            try:
                from openai import OpenAI
                llm_client = OpenAI(api_key=llm_api_key)
            except ImportError:
                logging.warning("OpenAI library not installed")
        
        elif llm_provider == "anthropic":
            try:
                from anthropic import Anthropic
                llm_client = Anthropic(api_key=llm_api_key)
            except ImportError:
                logging.warning("Anthropic library not installed")
    
    return GomesAnalyzer(
        db_session=db_session,
        llm_client=llm_client
    )
