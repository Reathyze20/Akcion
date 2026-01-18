"""
Master Signal Aggregator
=========================

Combines ALL signals into one actionable "Buy Confidence" score (0-100%).

This is the BRAIN of the trading system - it weighs:
- Gomes Intelligence Score
- ML Prediction Confidence
- Technical Indicators (RSI, MACD)
- Gap Analysis (opportunity matching)
- Risk/Reward Ratio

Author: GitHub Copilot with Claude Sonnet 4.5
Date: 2026-01-17
Version: 1.0.0
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy.orm import Session

from app.models.trading import ActiveWatchlist, MLPrediction, TradingSignal
from app.services.gap_analysis import GapAnalysisService, MatchSignal
from app.services.gomes_intelligence import GomesIntelligenceService
from app.trading.gomes_logic import InvestmentVerdict

# Optional sentiment analysis
try:
    from app.trading.sentiment import SentimentAnalyzer
    SENTIMENT_AVAILABLE = True
except ImportError:
    SENTIMENT_AVAILABLE = False
    logger.warning("Sentiment analysis not available")


logger = logging.getLogger(__name__)


# ==============================================================================
# Enums & Constants
# ==============================================================================

class SignalStrength(str, Enum):
    """Signal strength classification"""
    STRONG_BUY = "STRONG_BUY"      # 80-100%
    BUY = "BUY"                    # 60-79%
    WEAK_BUY = "WEAK_BUY"          # 40-59%
    NEUTRAL = "NEUTRAL"            # 20-39%
    AVOID = "AVOID"                # 0-19%


class WeightConfig:
    """Weight configuration for signal components"""
    
    # Default weights (must sum to 1.0)
    GOMES_SCORE: float = 0.30       # 30% - Gomes je hlavní autorita
    ML_CONFIDENCE: float = 0.25     # 25% - ML predikce
    TECHNICAL: float = 0.15         # 15% - RSI/MACD
    SENTIMENT: float = 0.15         # 15% - News sentiment
    GAP_ANALYSIS: float = 0.10      # 10% - Portfolio match
    RISK_REWARD: float = 0.05       # 5% - R/R ratio
    
    @classmethod
    def validate(cls) -> None:
        """Validate that weights sum to 1.0"""
        total = (
            cls.GOMES_SCORE + 
            cls.ML_CONFIDENCE + 
            cls.TECHNICAL +
            cls.SENTIMENT +
            cls.GAP_ANALYSIS + 
            cls.RISK_REWARD
        )
        if not 0.99 <= total <= 1.01:  # Allow small float rounding
            raise ValueError(f"Weights must sum to 1.0, got {total}")


# Validate on import
WeightConfig.validate()


# ==============================================================================
# Data Models
# ==============================================================================

@dataclass
class TechnicalScore:
    """Technical indicator scores"""
    rsi: float  # 0-100
    macd_signal: float  # -1 to +1 (normalized)
    trend_strength: float  # 0-100
    combined_score: float  # 0-100 (weighted average)


@dataclass
class SignalComponents:
    """Individual signal component scores"""
    gomes_score: float  # 0-100
    ml_confidence: float  # 0-100
    technical_score: float  # 0-100
    sentiment_score: float  # 0-100
    gap_score: float  # 0-100
    risk_reward_score: float  # 0-100


@dataclass
class MasterSignalResult:
    """
    Master Signal Aggregation Result
    
    This is the FINAL OUTPUT - the single number that tells you:
    "How confident should I be in buying this stock RIGHT NOW?"
    """
    ticker: str
    buy_confidence: float  # 0-100 - THE KEY NUMBER
    signal_strength: SignalStrength
    
    # Component breakdown
    components: SignalComponents
    
    # Supporting data
    verdict: str  # Gomes verdict
    blocked_reason: Optional[str]
    entry_price: Optional[float]
    target_price: Optional[float]
    stop_loss: Optional[float]
    risk_reward_ratio: Optional[float]
    kelly_size: Optional[float]
    
    # Metadata
    calculated_at: datetime
    expires_at: Optional[datetime]
    
    def to_dict(self) -> dict:
        """Convert to dictionary for API response"""
        return {
            "ticker": self.ticker,
            "buy_confidence": round(self.buy_confidence, 2),
            "signal_strength": self.signal_strength.value,
            "components": {
                "gomes_score": round(self.components.gomes_score, 2),
                "ml_confidence": round(self.components.ml_confidence, 2),
                "technical_score": round(self.components.technical_score, 2),
                "sentiment_score": round(self.components.sentiment_score, 2),
                "gap_score": round(self.components.gap_score, 2),
                "risk_reward_score": round(self.components.risk_reward_score, 2),
            },
            "verdict": self.verdict,
            "blocked_reason": self.blocked_reason,
            "entry_price": self.entry_price,
            "target_price": self.target_price,
            "stop_loss": self.stop_loss,
            "risk_reward_ratio": round(self.risk_reward_ratio, 2) if self.risk_reward_ratio else None,
            "kelly_size": round(self.kelly_size, 4) if self.kelly_size else None,
            "calculated_at": self.calculated_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }


# ==============================================================================
# Master Signal Aggregator
# ==============================================================================

class MasterSignalAggregator:
    """
    Master Signal Aggregator - The Brain of Trading System
    
    Combines all signal sources into one actionable "Buy Confidence" score.
    
    Usage:
        aggregator = MasterSignalAggregator(db)
        result = aggregator.calculate_master_signal(ticker="AAPL")
        
        if result.buy_confidence > 80:
            print(f"STRONG BUY: {result.buy_confidence}%")
    """
    
    def __init__(self, db: Session, weights: Optional[WeightConfig] = None):
        """
        Initialize Master Signal Aggregator
        
        Args:
            db: Database session
            weights: Custom weight configuration (optional)
        """
        self.db = db
        self.weights = weights or WeightConfig()
        self.gomes_service = GomesIntelligenceService(db)
        self.gap_service = GapAnalysisService()
        
        # Initialize sentiment analyzer if available
        if SENTIMENT_AVAILABLE:
            self.sentiment_analyzer = SentimentAnalyzer(lookback_days=7)
            logger.info("📰 Sentiment analysis ENABLED")
        else:
            self.sentiment_analyzer = None
            logger.warning("⚠️  Sentiment analysis DISABLED")
        
        logger.info("🧠 Master Signal Aggregator initialized")
    
    # ==========================================================================
    # Main Entry Point
    # ==========================================================================
    
    def calculate_master_signal(
        self,
        ticker: str,
        user_id: Optional[int] = None,
        current_price: Optional[float] = None,
    ) -> MasterSignalResult:
        """
        Calculate Master Signal for a ticker.
        
        This is THE method - it produces the final "Buy Confidence" score.
        
        Args:
            ticker: Stock ticker symbol
            user_id: User ID for gap analysis (optional)
            current_price: Current market price (optional, will fetch if None)
            
        Returns:
            MasterSignalResult with buy_confidence (0-100)
            
        Raises:
            ValueError: If ticker not found or insufficient data
        """
        logger.info(f"🎯 Calculating Master Signal for {ticker}")
        
        # ======================================================================
        # 1. FETCH DATA
        # ======================================================================
        watchlist = self._get_watchlist(ticker)
        prediction = self._get_latest_prediction(ticker)
        signal = self._get_latest_signal(ticker)
        
        if current_price is None:
            current_price = float(prediction.current_price) if prediction else None
        
        # ======================================================================
        # 2. GOMES SCORE (35%)
        # ======================================================================
        gomes_score = self._calculate_gomes_score(ticker, current_price)
        
        # ======================================================================
        # 3. ML CONFIDENCE (25%)
        # ======================================================================
        ml_confidence = self._calculate_ml_confidence(prediction)
        
        # ======================================================================
        # 4. TECHNICAL SCORE (15%)
        # ======================================================================
        technical_score = self._calculate_technical_score(ticker)
        
        # ======================================================================
        # 5. SENTIMENT SCORE (15%)
        # ======================================================================
        sentiment_score = self._calculate_sentiment_score(ticker)
        
        # ======================================================================
        # 6. GAP ANALYSIS (10%)
        # ======================================================================
        gap_score = self._calculate_gap_score(ticker, user_id)
        
        # ======================================================================
        # 7. RISK/REWARD SCORE (5%)
        # ======================================================================
        risk_reward_score = self._calculate_risk_reward_score(signal, prediction)
        
        # ======================================================================
        # 8. AGGREGATE SCORES
        # ======================================================================
        components = SignalComponents(
            gomes_score=gomes_score,
            ml_confidence=ml_confidence,
            technical_score=technical_score,
            sentiment_score=sentiment_score,
            gap_score=gap_score,
            risk_reward_score=risk_reward_score,
        )
        
        buy_confidence = self._aggregate_scores(components)
        signal_strength = self._classify_strength(buy_confidence)
        
        # ======================================================================
        # 8. GET VERDICT & SUPPORTING DATA
        # ======================================================================
        verdict_obj = self.gomes_service.generate_verdict(ticker, current_price)
        
        return MasterSignalResult(
            ticker=ticker,
            buy_confidence=buy_confidence,
            signal_strength=signal_strength,
            components=components,
            verdict=verdict_obj.verdict.value,
            blocked_reason=verdict_obj.blocked_reason if not verdict_obj.passed_gomes_filter else None,
            entry_price=float(signal.entry_price) if signal else current_price,
            target_price=float(signal.target_price) if signal else None,
            stop_loss=float(signal.stop_loss) if signal else None,
            risk_reward_ratio=float(signal.risk_reward_ratio) if signal else None,
            kelly_size=float(signal.kelly_size) if signal else None,
            calculated_at=datetime.utcnow(),
            expires_at=signal.expires_at if signal else None,
        )
    
    # ==========================================================================
    # Component Calculators
    # ==========================================================================
    
    def _calculate_gomes_score(self, ticker: str, current_price: Optional[float]) -> float:
        """
        Calculate Gomes Intelligence Score (0-100)
        
        Returns:
            0-100 score based on Gomes verdict
        """
        try:
            verdict = self.gomes_service.generate_verdict(ticker, current_price)
            
            # Convert verdict to score
            if verdict.verdict == InvestmentVerdict.STRONG_BUY:
                base_score = 90.0
            elif verdict.verdict == InvestmentVerdict.BUY:
                base_score = 75.0
            elif verdict.verdict == InvestmentVerdict.HOLD:
                base_score = 50.0
            elif verdict.verdict == InvestmentVerdict.SELL:
                base_score = 25.0
            elif verdict.verdict == InvestmentVerdict.AVOID:
                base_score = 0.0
            else:
                base_score = 50.0  # Neutral
            
            # Apply Gomes filter penalty
            if not verdict.passed_gomes_filter:
                base_score *= 0.3  # 70% penalty if blocked
            
            # Boost for Kelly sizing confidence
            if verdict.kelly_position_size:
                kelly_boost = min(verdict.kelly_position_size * 20, 10)  # Max +10
                base_score = min(base_score + kelly_boost, 100)
            
            logger.debug(f"Gomes score for {ticker}: {base_score:.2f}")
            return base_score
            
        except Exception as e:
            logger.warning(f"Failed to get Gomes score for {ticker}: {e}")
            return 50.0  # Neutral on error
    
    def _calculate_ml_confidence(self, prediction: Optional[MLPrediction]) -> float:
        """
        Calculate ML Prediction Confidence (0-100)
        
        Returns:
            0-100 score based on ML prediction confidence
        """
        if not prediction:
            logger.debug("No ML prediction available")
            return 50.0  # Neutral
        
        # Only UP predictions get positive scores
        if prediction.prediction_type != 'UP':
            logger.debug(f"ML prediction type is {prediction.prediction_type}, not UP")
            return 30.0  # Penalty for non-UP
        
        # Use confidence directly (already 0-100)
        confidence = float(prediction.confidence)
        
        # Penalize low-quality predictions
        if prediction.quality_assessment == "LOW_CONFIDENCE":
            confidence *= 0.5
        elif prediction.quality_assessment == "PREDICTION_FAILED":
            confidence = 0.0
        
        logger.debug(f"ML confidence: {confidence:.2f}")
        return confidence
    
    def _calculate_technical_score(self, ticker: str) -> float:
        """
        Calculate Technical Indicators Score (0-100)
        
        TODO: Implement RSI/MACD calculation from OHLCV data
        
        For now, returns neutral score.
        """
        # TODO: Query OHLCVData and calculate:
        # - RSI (Relative Strength Index)
        # - MACD (Moving Average Convergence Divergence)
        # - Trend strength
        
        logger.debug(f"Technical score for {ticker}: 50.0 (placeholder)")
        return 50.0  # Neutral until implemented
    
    def _calculate_sentiment_score(self, ticker: str) -> float:
        """
        Calculate News Sentiment Score (0-100)
        
        Analyzes recent news headlines and returns sentiment.
        
        Returns:
            0-100 score (0=very bearish, 50=neutral, 100=very bullish)
        """
        if not self.sentiment_analyzer:
            logger.debug("Sentiment analysis disabled")
            return 50.0  # Neutral
        
        try:
            result = self.sentiment_analyzer.analyze_ticker(ticker)
            
            # Apply confidence penalty for low article count
            score = result.sentiment_score * result.confidence + 50.0 * (1 - result.confidence)
            
            logger.debug(
                f"Sentiment score for {ticker}: {score:.2f} "
                f"(raw: {result.sentiment_score:.2f}, confidence: {result.confidence:.2f})"
            )
            return score
            
        except Exception as e:
            logger.warning(f"Failed to get sentiment for {ticker}: {e}")
            return 50.0  # Neutral on error
    
    def _calculate_gap_score(self, ticker: str, user_id: Optional[int]) -> float:
        """
        Calculate Gap Analysis Score (0-100)
        
        Scores based on position matching:
        - OPPORTUNITY: 100 (BUY signal, don't own)
        - ACCUMULATE: 80 (BUY signal, already own)
        - HOLD: 50 (Own but no strong signal)
        - WAIT_MARKET_BAD: 30 (BUY signal but bad market)
        - DANGER_EXIT: 10 (SELL signal, own)
        - NO_ACTION: 40 (Don't own, no signal)
        """
        if not user_id:
            logger.debug("No user_id provided for gap analysis")
            return 50.0  # Neutral
        
        try:
            # Get stock with signal
            from app.models.stock import Stock
            stock = self.db.query(Stock).filter(Stock.ticker == ticker).first()
            
            if not stock:
                return 50.0
            
            # Get match signal
            match_signal = self.gap_service.get_match_signal(
                stock_signal=stock.mark_gomes_signal,
                user_owns_position=self._user_owns_ticker(ticker, user_id)
            )
            
            # Score mapping
            score_map = {
                MatchSignal.OPPORTUNITY: 100.0,
                MatchSignal.ACCUMULATE: 80.0,
                MatchSignal.HOLD: 50.0,
                MatchSignal.WAIT_MARKET_BAD: 30.0,
                MatchSignal.DANGER_EXIT: 10.0,
                MatchSignal.NO_ACTION: 40.0,
            }
            
            score = score_map.get(match_signal, 50.0)
            logger.debug(f"Gap score for {ticker}: {score:.2f} (match: {match_signal})")
            return score
            
        except Exception as e:
            logger.warning(f"Failed to calculate gap score for {ticker}: {e}")
            return 50.0
    
    def _calculate_risk_reward_score(
        self,
        signal: Optional[TradingSignal],
        prediction: Optional[MLPrediction]
    ) -> float:
        """
        Calculate Risk/Reward Score (0-100)
        
        Scores based on R/R ratio:
        - R/R >= 3.0: 100
        - R/R >= 2.0: 80
        - R/R >= 1.5: 60
        - R/R >= 1.0: 40
        - R/R < 1.0: 20
        """
        risk_reward = None
        
        if signal and signal.risk_reward_ratio:
            risk_reward = float(signal.risk_reward_ratio)
        elif prediction:
            # Calculate R/R from prediction
            current = float(prediction.current_price)
            target = float(prediction.predicted_price)
            stop_loss = current * 0.9  # Assume 10% stop loss
            
            potential_gain = target - current
            potential_loss = current - stop_loss
            
            if potential_loss > 0:
                risk_reward = potential_gain / potential_loss
        
        if risk_reward is None:
            logger.debug("No R/R ratio available")
            return 50.0
        
        # Score mapping
        if risk_reward >= 3.0:
            score = 100.0
        elif risk_reward >= 2.0:
            score = 80.0
        elif risk_reward >= 1.5:
            score = 60.0
        elif risk_reward >= 1.0:
            score = 40.0
        else:
            score = 20.0
        
        logger.debug(f"R/R score: {score:.2f} (ratio: {risk_reward:.2f})")
        return score
    
    # ==========================================================================
    # Aggregation
    # ==========================================================================
    
    def _aggregate_scores(self, components: SignalComponents) -> float:
        """
        Aggregate component scores into final Buy Confidence (0-100)
        
        Uses weighted average based on WeightConfig.
        """
        buy_confidence = (
            components.gomes_score * self.weights.GOMES_SCORE +
            components.ml_confidence * self.weights.ML_CONFIDENCE +
            components.technical_score * self.weights.TECHNICAL +
            components.sentiment_score * self.weights.SENTIMENT +
            components.gap_score * self.weights.GAP_ANALYSIS +
            components.risk_reward_score * self.weights.RISK_REWARD
        )
        
        # Clamp to 0-100
        buy_confidence = max(0.0, min(100.0, buy_confidence))
        
        logger.info(f"📊 Buy Confidence: {buy_confidence:.2f}%")
        return buy_confidence
    
    def _classify_strength(self, buy_confidence: float) -> SignalStrength:
        """Classify signal strength based on buy confidence"""
        if buy_confidence >= 80:
            return SignalStrength.STRONG_BUY
        elif buy_confidence >= 60:
            return SignalStrength.BUY
        elif buy_confidence >= 40:
            return SignalStrength.WEAK_BUY
        elif buy_confidence >= 20:
            return SignalStrength.NEUTRAL
        else:
            return SignalStrength.AVOID
    
    # ==========================================================================
    # Helper Methods
    # ==========================================================================
    
    def _get_watchlist(self, ticker: str) -> Optional[ActiveWatchlist]:
        """Get active watchlist entry for ticker"""
        return self.db.query(ActiveWatchlist).filter(
            ActiveWatchlist.ticker == ticker,
            ActiveWatchlist.is_active == True
        ).first()
    
    def _get_latest_prediction(self, ticker: str) -> Optional[MLPrediction]:
        """Get latest ML prediction for ticker"""
        return self.db.query(MLPrediction).filter(
            MLPrediction.ticker == ticker
        ).order_by(MLPrediction.created_at.desc()).first()
    
    def _get_latest_signal(self, ticker: str) -> Optional[TradingSignal]:
        """Get latest trading signal for ticker"""
        return self.db.query(TradingSignal).filter(
            TradingSignal.ticker == ticker
        ).order_by(TradingSignal.created_at.desc()).first()
    
    def _user_owns_ticker(self, ticker: str, user_id: int) -> bool:
        """Check if user owns position in ticker"""
        from app.models.portfolio import Position
        
        position = self.db.query(Position).filter(
            Position.ticker == ticker,
            Position.user_id == user_id,
            Position.quantity > 0
        ).first()
        
        return position is not None


# ==============================================================================
# Convenience Functions
# ==============================================================================

def calculate_buy_confidence(
    db: Session,
    ticker: str,
    user_id: Optional[int] = None,
    current_price: Optional[float] = None,
) -> MasterSignalResult:
    """
    Convenience function to calculate Buy Confidence for a ticker.
    
    Usage:
        result = calculate_buy_confidence(db, "AAPL", user_id=1)
        print(f"Buy Confidence: {result.buy_confidence}%")
    """
    aggregator = MasterSignalAggregator(db)
    return aggregator.calculate_master_signal(ticker, user_id, current_price)


def get_top_opportunities(
    db: Session,
    user_id: Optional[int] = None,
    min_confidence: float = 60.0,
    limit: int = 10,
) -> list[MasterSignalResult]:
    """
    Get top trading opportunities sorted by Buy Confidence.
    
    Args:
        db: Database session
        user_id: User ID for personalized gap analysis
        min_confidence: Minimum buy confidence threshold (default 60%)
        limit: Max number of results (default 10)
        
    Returns:
        List of MasterSignalResult sorted by buy_confidence (descending)
    """
    aggregator = MasterSignalAggregator(db)
    
    # Get all active watchlist tickers
    watchlist_items = db.query(ActiveWatchlist).filter(
        ActiveWatchlist.is_active == True
    ).all()
    
    results = []
    for item in watchlist_items:
        try:
            result = aggregator.calculate_master_signal(
                ticker=item.ticker,
                user_id=user_id
            )
            
            if result.buy_confidence >= min_confidence:
                results.append(result)
                
        except Exception as e:
            logger.warning(f"Failed to calculate signal for {item.ticker}: {e}")
            continue
    
    # Sort by confidence descending
    results.sort(key=lambda x: x.buy_confidence, reverse=True)
    
    return results[:limit]
