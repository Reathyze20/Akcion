"""
ML Learning Engine - Self-Improving Prediction System
======================================================

Tracks historical trade outcomes and adjusts ML confidence based on:
- Prediction accuracy (direction correctness)
- Price target accuracy
- Gomes signal correlation
- Win/Loss ratio per ticker

The system LEARNS from every trade and improves over time.

Author: GitHub Copilot with Claude Sonnet 4.5
Date: 2026-01-17
Version: 1.0.0
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.trading import MLPrediction, ModelPerformance, TradingSignal
from app.models.stock import Stock


logger = logging.getLogger(__name__)


# ==============================================================================
# Data Models
# ==============================================================================

@dataclass
class PerformanceMetrics:
    """Performance metrics for a ticker/model combination"""
    ticker: str
    model_version: str
    
    # Accuracy metrics
    total_predictions: int
    correct_direction: int
    direction_accuracy: float  # 0-1
    
    # Price accuracy
    avg_price_error_pct: float  # Average % error
    median_price_error_pct: float
    
    # Gomes correlation
    gomes_agreement_rate: float  # How often ML agrees with Gomes
    gomes_success_rate: float  # When agreeing with Gomes, success rate
    
    # Trade outcomes
    win_count: int
    loss_count: int
    win_rate: float  # 0-1
    avg_return_pct: float
    
    # Confidence calibration
    confidence_calibration: float  # How well confidence predicts success
    
    # Time periods
    lookback_days: int
    last_updated: datetime


@dataclass
class ConfidenceAdjustment:
    """Confidence adjustment based on historical performance"""
    original_confidence: float
    adjusted_confidence: float
    adjustment_factor: float  # Multiplier applied
    reason: str
    metrics_used: PerformanceMetrics


# ==============================================================================
# Learning Engine
# ==============================================================================

class MLLearningEngine:
    """
    Self-Improving ML Engine
    
    Tracks prediction outcomes and adjusts confidence based on:
    1. Historical accuracy for this ticker
    2. Model performance trends
    3. Gomes signal correlation
    4. Win/loss patterns
    
    Usage:
        engine = MLLearningEngine(db)
        
        # Record outcome after trade completes
        engine.record_outcome(
            prediction_id=123,
            actual_price=190.50,
            actual_direction="UP"
        )
        
        # Get adjusted confidence
        adjusted = engine.adjust_confidence(
            ticker="AAPL",
            raw_confidence=0.85,
            prediction_type="UP"
        )
    """
    
    def __init__(
        self,
        db: Session,
        lookback_days: int = 90,
        min_samples: int = 5,
        confidence_boost_threshold: float = 0.75,  # 75% accuracy
        confidence_penalty_threshold: float = 0.45,  # Below 45% accuracy
    ):
        """
        Initialize Learning Engine
        
        Args:
            db: Database session
            lookback_days: Days of history to analyze (default 90)
            min_samples: Minimum predictions needed for adjustment (default 5)
            confidence_boost_threshold: Accuracy needed for confidence boost
            confidence_penalty_threshold: Accuracy below which to penalize
        """
        self.db = db
        self.lookback_days = lookback_days
        self.min_samples = min_samples
        self.boost_threshold = confidence_boost_threshold
        self.penalty_threshold = confidence_penalty_threshold
        
        logger.info(
            f"🧠 ML Learning Engine initialized "
            f"(lookback={lookback_days}d, min_samples={min_samples})"
        )
    
    # ==========================================================================
    # Recording Outcomes
    # ==========================================================================
    
    def record_outcome(
        self,
        prediction_id: int,
        actual_price: float,
        actual_direction: Optional[str] = None,
        evaluation_date: Optional[datetime] = None,
    ) -> ModelPerformance:
        """
        Record actual outcome for a prediction.
        
        Call this after trade completes or prediction horizon expires.
        
        Args:
            prediction_id: ID of the MLPrediction
            actual_price: Actual price at horizon end
            actual_direction: Actual direction ("UP", "DOWN", "NEUTRAL")
            evaluation_date: Date of evaluation (default: now)
            
        Returns:
            ModelPerformance record
            
        Raises:
            ValueError: If prediction not found
        """
        prediction = self.db.query(MLPrediction).get(prediction_id)
        if not prediction:
            raise ValueError(f"Prediction {prediction_id} not found")
        
        # Determine actual direction if not provided
        if actual_direction is None:
            price_change_pct = (
                (actual_price - float(prediction.current_price)) / 
                float(prediction.current_price) * 100
            )
            
            if price_change_pct > 2.0:
                actual_direction = "UP"
            elif price_change_pct < -2.0:
                actual_direction = "DOWN"
            else:
                actual_direction = "NEUTRAL"
        
        # Calculate accuracy
        direction_correct = actual_direction == prediction.prediction_type
        
        predicted_price = float(prediction.predicted_price)
        price_error_pct = abs(
            (actual_price - predicted_price) / predicted_price * 100
        )
        
        # Simple accuracy: 1.0 if direction correct, 0.0 otherwise
        # Could be enhanced to consider price error
        accuracy = 1.0 if direction_correct else 0.0
        
        # Create performance record
        performance = ModelPerformance(
            ticker=prediction.ticker,
            model_version=prediction.model_version or "unknown",
            prediction_id=prediction_id,
            predicted_direction=prediction.prediction_type,
            actual_direction=actual_direction,
            predicted_price=prediction.predicted_price,
            actual_price=Decimal(str(actual_price)),
            accuracy=Decimal(str(accuracy)),
            prediction_date=prediction.created_at,
            evaluation_date=evaluation_date or datetime.utcnow(),
        )
        
        self.db.add(performance)
        self.db.commit()
        self.db.refresh(performance)
        
        logger.info(
            f"📊 Recorded outcome for {prediction.ticker}: "
            f"predicted={prediction.prediction_type}, "
            f"actual={actual_direction}, "
            f"accuracy={accuracy:.0%}"
        )
        
        return performance
    
    def record_signal_outcome(
        self,
        signal_id: int,
        exit_price: float,
        exit_date: Optional[datetime] = None,
    ) -> Optional[ModelPerformance]:
        """
        Record outcome for a trading signal.
        
        Convenience method that finds the related prediction and records outcome.
        
        Args:
            signal_id: TradingSignal ID
            exit_price: Price at exit
            exit_date: Date of exit (default: now)
            
        Returns:
            ModelPerformance record or None if no prediction linked
        """
        signal = self.db.query(TradingSignal).get(signal_id)
        if not signal or not signal.ml_prediction_id:
            logger.warning(f"Signal {signal_id} has no linked ML prediction")
            return None
        
        return self.record_outcome(
            prediction_id=signal.ml_prediction_id,
            actual_price=exit_price,
            evaluation_date=exit_date,
        )
    
    # ==========================================================================
    # Performance Analysis
    # ==========================================================================
    
    def get_performance_metrics(
        self,
        ticker: str,
        model_version: Optional[str] = None,
    ) -> Optional[PerformanceMetrics]:
        """
        Get performance metrics for a ticker.
        
        Args:
            ticker: Stock ticker
            model_version: Specific model version (optional)
            
        Returns:
            PerformanceMetrics or None if insufficient data
        """
        cutoff_date = datetime.utcnow() - timedelta(days=self.lookback_days)
        
        # Query performance records
        query = self.db.query(ModelPerformance).filter(
            ModelPerformance.ticker == ticker,
            ModelPerformance.evaluation_date >= cutoff_date
        )
        
        if model_version:
            query = query.filter(ModelPerformance.model_version == model_version)
        
        records = query.all()
        
        if len(records) < self.min_samples:
            logger.debug(
                f"Insufficient data for {ticker}: "
                f"{len(records)} records < {self.min_samples} minimum"
            )
            return None
        
        # Calculate metrics
        total = len(records)
        correct = sum(1 for r in records if float(r.accuracy) == 1.0)
        direction_accuracy = correct / total
        
        # Price error
        price_errors = [
            abs(
                (float(r.actual_price) - float(r.predicted_price)) /
                float(r.predicted_price) * 100
            )
            for r in records
        ]
        avg_price_error = sum(price_errors) / len(price_errors)
        median_price_error = sorted(price_errors)[len(price_errors) // 2]
        
        # Win/loss (direction correct = win)
        win_count = correct
        loss_count = total - correct
        win_rate = win_count / total
        
        # Average return (if we have actual prices)
        returns = [
            (float(r.actual_price) - float(r.predicted_price)) /
            float(r.predicted_price) * 100
            for r in records
            if r.predicted_direction == "UP"  # Only count UP predictions
        ]
        avg_return = sum(returns) / len(returns) if returns else 0.0
        
        # Gomes correlation (requires looking up Gomes signals)
        gomes_agreement, gomes_success = self._calculate_gomes_correlation(
            ticker, records
        )
        
        # Confidence calibration (TODO: implement)
        confidence_calibration = 0.5  # Placeholder
        
        return PerformanceMetrics(
            ticker=ticker,
            model_version=model_version or "all",
            total_predictions=total,
            correct_direction=correct,
            direction_accuracy=direction_accuracy,
            avg_price_error_pct=avg_price_error,
            median_price_error_pct=median_price_error,
            gomes_agreement_rate=gomes_agreement,
            gomes_success_rate=gomes_success,
            win_count=win_count,
            loss_count=loss_count,
            win_rate=win_rate,
            avg_return_pct=avg_return,
            confidence_calibration=confidence_calibration,
            lookback_days=self.lookback_days,
            last_updated=datetime.utcnow(),
        )
    
    def _calculate_gomes_correlation(
        self,
        ticker: str,
        performance_records: list[ModelPerformance]
    ) -> tuple[float, float]:
        """
        Calculate correlation between ML predictions and Gomes signals.
        
        Returns:
            (agreement_rate, success_rate_when_agreeing)
        """
        # Get Gomes signals for this ticker
        stock = self.db.query(Stock).filter(Stock.ticker == ticker).first()
        if not stock or not stock.mark_gomes_signal:
            return 0.5, 0.5  # No Gomes data
        
        gomes_bullish = stock.mark_gomes_signal in ("BUY_NOW", "ACCUMULATE")
        
        # Count agreements
        agreements = 0
        successes_when_agreeing = 0
        
        for record in performance_records:
            ml_bullish = record.predicted_direction == "UP"
            
            if ml_bullish == gomes_bullish:
                agreements += 1
                if float(record.accuracy) == 1.0:
                    successes_when_agreeing += 1
        
        agreement_rate = agreements / len(performance_records) if performance_records else 0.5
        success_rate = (
            successes_when_agreeing / agreements if agreements > 0 else 0.5
        )
        
        return agreement_rate, success_rate
    
    # ==========================================================================
    # Confidence Adjustment
    # ==========================================================================
    
    def adjust_confidence(
        self,
        ticker: str,
        raw_confidence: float,
        prediction_type: str,
        model_version: Optional[str] = None,
    ) -> ConfidenceAdjustment:
        """
        Adjust ML confidence based on historical performance.
        
        This is the KEY method - it makes the AI learn from mistakes.
        
        Args:
            ticker: Stock ticker
            raw_confidence: Raw ML confidence (0-1)
            prediction_type: "UP", "DOWN", "NEUTRAL"
            model_version: Model version (optional)
            
        Returns:
            ConfidenceAdjustment with adjusted confidence
        """
        # Get performance metrics
        metrics = self.get_performance_metrics(ticker, model_version)
        
        if metrics is None:
            # No historical data - return unadjusted
            return ConfidenceAdjustment(
                original_confidence=raw_confidence,
                adjusted_confidence=raw_confidence,
                adjustment_factor=1.0,
                reason="Insufficient historical data for adjustment",
                metrics_used=None,
            )
        
        # Calculate adjustment factor based on metrics
        adjustment_factor = 1.0
        reasons = []
        
        # 1. Direction accuracy adjustment
        if metrics.direction_accuracy >= self.boost_threshold:
            boost = 0.1 * (metrics.direction_accuracy - self.boost_threshold) / 0.25
            adjustment_factor += boost
            reasons.append(
                f"High accuracy ({metrics.direction_accuracy:.1%}): +{boost:.1%}"
            )
        elif metrics.direction_accuracy <= self.penalty_threshold:
            penalty = 0.2 * (self.penalty_threshold - metrics.direction_accuracy) / 0.45
            adjustment_factor -= penalty
            reasons.append(
                f"Low accuracy ({metrics.direction_accuracy:.1%}): -{penalty:.1%}"
            )
        
        # 2. Gomes correlation adjustment
        if metrics.gomes_agreement_rate >= 0.7 and metrics.gomes_success_rate >= 0.7:
            adjustment_factor += 0.05
            reasons.append(
                f"Strong Gomes correlation "
                f"({metrics.gomes_agreement_rate:.1%} agreement, "
                f"{metrics.gomes_success_rate:.1%} success)"
            )
        elif metrics.gomes_agreement_rate <= 0.3:
            adjustment_factor -= 0.05
            reasons.append(f"Poor Gomes correlation ({metrics.gomes_agreement_rate:.1%})")
        
        # 3. Win rate adjustment (for UP predictions)
        if prediction_type == "UP":
            if metrics.win_rate >= 0.70:
                adjustment_factor += 0.05
                reasons.append(f"Strong win rate ({metrics.win_rate:.1%})")
            elif metrics.win_rate <= 0.40:
                adjustment_factor -= 0.1
                reasons.append(f"Weak win rate ({metrics.win_rate:.1%})")
        
        # Clamp adjustment factor
        adjustment_factor = max(0.5, min(1.3, adjustment_factor))
        
        # Apply adjustment
        adjusted_confidence = raw_confidence * adjustment_factor
        adjusted_confidence = max(0.0, min(1.0, adjusted_confidence))
        
        reason_str = "; ".join(reasons) if reasons else "No significant adjustments"
        
        logger.info(
            f"🎯 Adjusted confidence for {ticker}: "
            f"{raw_confidence:.1%} → {adjusted_confidence:.1%} "
            f"(factor: {adjustment_factor:.2f}) - {reason_str}"
        )
        
        return ConfidenceAdjustment(
            original_confidence=raw_confidence,
            adjusted_confidence=adjusted_confidence,
            adjustment_factor=adjustment_factor,
            reason=reason_str,
            metrics_used=metrics,
        )
    
    # ==========================================================================
    # Batch Operations
    # ==========================================================================
    
    def evaluate_all_pending_predictions(self) -> int:
        """
        Evaluate all predictions whose horizon has passed.
        
        Automatically fetches current prices and records outcomes.
        
        Returns:
            Number of predictions evaluated
        """
        # Find predictions past their valid_until date
        cutoff = datetime.utcnow()
        
        pending = self.db.query(MLPrediction).filter(
            MLPrediction.valid_until < cutoff,
            ~MLPrediction.performance_records.any()  # No performance record yet
        ).all()
        
        evaluated = 0
        
        for prediction in pending:
            try:
                # Fetch current price (you'll need to implement this)
                current_price = self._fetch_current_price(prediction.ticker)
                
                if current_price:
                    self.record_outcome(
                        prediction_id=prediction.id,
                        actual_price=current_price
                    )
                    evaluated += 1
                    
            except Exception as e:
                logger.warning(
                    f"Failed to evaluate prediction {prediction.id}: {e}"
                )
                continue
        
        logger.info(f"✅ Evaluated {evaluated} pending predictions")
        return evaluated
    
    def _fetch_current_price(self, ticker: str) -> Optional[float]:
        """
        Fetch current price for ticker.
        
        TODO: Implement actual price fetching (from OHLCV or market data service)
        """
        from app.models.trading import OHLCVData
        
        latest = self.db.query(OHLCVData).filter(
            OHLCVData.ticker == ticker
        ).order_by(OHLCVData.time.desc()).first()
        
        return float(latest.close) if latest else None
    
    # ==========================================================================
    # Reporting
    # ==========================================================================
    
    def get_overall_performance(self) -> dict:
        """
        Get overall ML engine performance across all tickers.
        
        Returns:
            Dict with aggregate metrics
        """
        cutoff_date = datetime.utcnow() - timedelta(days=self.lookback_days)
        
        records = self.db.query(ModelPerformance).filter(
            ModelPerformance.evaluation_date >= cutoff_date
        ).all()
        
        if not records:
            return {
                "total_predictions": 0,
                "overall_accuracy": 0.0,
                "win_rate": 0.0,
                "avg_return": 0.0,
            }
        
        total = len(records)
        correct = sum(1 for r in records if float(r.accuracy) == 1.0)
        
        # Group by ticker for per-ticker stats
        ticker_stats = {}
        for record in records:
            if record.ticker not in ticker_stats:
                ticker_stats[record.ticker] = {"correct": 0, "total": 0}
            
            ticker_stats[record.ticker]["total"] += 1
            if float(record.accuracy) == 1.0:
                ticker_stats[record.ticker]["correct"] += 1
        
        return {
            "total_predictions": total,
            "overall_accuracy": correct / total,
            "win_rate": correct / total,
            "tickers_tracked": len(ticker_stats),
            "best_ticker": max(
                ticker_stats.items(),
                key=lambda x: x[1]["correct"] / x[1]["total"] if x[1]["total"] > 0 else 0
            )[0] if ticker_stats else None,
            "lookback_days": self.lookback_days,
        }


# ==============================================================================
# Convenience Functions
# ==============================================================================

def adjust_ml_confidence(
    db: Session,
    ticker: str,
    raw_confidence: float,
    prediction_type: str,
) -> float:
    """
    Convenience function to get adjusted confidence.
    
    Usage:
        adjusted = adjust_ml_confidence(db, "AAPL", 0.85, "UP")
    """
    engine = MLLearningEngine(db)
    result = engine.adjust_confidence(ticker, raw_confidence, prediction_type)
    return result.adjusted_confidence
