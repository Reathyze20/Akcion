"""
Gomes-Integrated Signal Generator
===================================

Signal generation with Gomes Gatekeeper integration.
This is the FINAL layer - signals MUST pass Gomes filter.

Author: GitHub Copilot with Claude Opus 4.5
Date: 2026-01-17
"""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.stock import Stock
from app.models.trading import ActiveWatchlist, MLPrediction, TradingSignal
from app.services.gomes_intelligence import GomesIntelligenceService
from app.trading.gomes_logic import (
    GomesGatekeeper,
    GomesVerdict,
    InvestmentVerdict,
    LifecyclePhase,
    MarketAlert,
    PositionSizingEngine,
)
from app.trading.kelly import KellyCriterion
from app.trading.signals import SignalGenerator


logger = logging.getLogger(__name__)


class GomesIntegratedSignalGenerator:
    """
    Signal generator with Gomes Gatekeeper integration.
    
    This wraps the standard SignalGenerator and adds Gomes filtering.
    Signals ONLY pass if the Gatekeeper approves.
    """
    
    def __init__(self, db: Session):
        self.db = db
        self.base_generator = SignalGenerator(db)
        self.gomes_service = GomesIntelligenceService(db)
        self.kelly_calc = KellyCriterion(max_position=0.25, fractional_kelly=0.5)
    
    def generate_signal(
        self,
        prediction: MLPrediction,
        stop_loss_pct: float = 0.10,
        risk_reward_min: float = 2.0,
        current_price: float | None = None,
        earnings_date: datetime | None = None
    ) -> tuple[TradingSignal | None, GomesVerdict]:
        """
        Generate trading signal with Gomes filtering.
        
        CRITICAL: Signal is only generated if Gomes filter passes.
        
        Args:
            prediction: ML prediction object
            stop_loss_pct: Stop loss percentage
            risk_reward_min: Minimum R/R ratio
            current_price: Current market price
            earnings_date: Next earnings date
            
        Returns:
            Tuple of (TradingSignal or None, GomesVerdict)
        """
        ticker = prediction.ticker
        logger.info(f"Gomes-Integrated Signal Generation: {ticker}")
        
        # =====================================================================
        # 1. GET GOMES VERDICT FIRST
        # =====================================================================
        verdict = self.gomes_service.generate_verdict(
            ticker=ticker,
            current_price=current_price or float(prediction.current_price),
            earnings_date=earnings_date
        )
        
        # =====================================================================
        # 2. CHECK IF GOMES APPROVES
        # =====================================================================
        if not verdict.passed_gomes_filter:
            logger.warning(
                f"{ticker} BLOCKED by Gomes: {verdict.blocked_reason}"
            )
            return None, verdict
        
        if verdict.verdict == InvestmentVerdict.AVOID:
            logger.warning(f"{ticker} marked as AVOID by Gomes")
            return None, verdict
        
        if verdict.verdict == InvestmentVerdict.BLOCKED:
            logger.warning(f"{ticker} BLOCKED by Gomes filter")
            return None, verdict
        
        # =====================================================================
        # 3. CHECK ML PREDICTION DIRECTION
        # =====================================================================
        if prediction.prediction_type != 'UP':
            logger.debug(f"{ticker} ML predicts {prediction.prediction_type}, not BUY signal")
            return None, verdict
        
        # =====================================================================
        # 4. ADJUST KELLY SIZE BASED ON GOMES TIER
        # =====================================================================
        base_kelly = self.kelly_calc.calculate_from_prediction(
            confidence=float(prediction.confidence),
            current_price=float(prediction.current_price),
            predicted_price=float(prediction.predicted_price),
            stop_loss_pct=stop_loss_pct
        )
        
        kelly_size = base_kelly['kelly_size']
        risk_reward = base_kelly['risk_reward_ratio']
        
        # Apply Gomes position limit
        max_pct = verdict.max_position_pct / 100  # Convert to decimal
        if kelly_size > max_pct:
            logger.info(
                f"{ticker} Kelly {kelly_size:.1%} capped to Gomes limit {max_pct:.1%}"
            )
            kelly_size = max_pct
        
        # =====================================================================
        # 5. APPLY FILTERS
        # =====================================================================
        if kelly_size < 0.01:  # Less than 1%
            logger.debug(f"{ticker} position too small after Gomes adjustment")
            return None, verdict
        
        if risk_reward < risk_reward_min:
            logger.debug(f"{ticker} R/R ratio {risk_reward:.2f} < minimum {risk_reward_min}")
            return None, verdict
        
        # =====================================================================
        # 6. CREATE SIGNAL
        # =====================================================================
        entry_price = current_price or float(prediction.current_price)
        target_price = float(prediction.predicted_price)
        stop_loss = entry_price * (1 - stop_loss_pct)
        
        # Get analyst source
        watchlist = (
            self.db.query(ActiveWatchlist)
            .filter(ActiveWatchlist.ticker == ticker)
            .filter(ActiveWatchlist.is_active == True)
            .first()
        )
        
        analyst_source_id = watchlist.stock_id if watchlist else None
        
        # Build comprehensive notes
        notes_parts = [
            f"ML: {prediction.prediction_type} ({float(prediction.confidence)*100:.0f}%)",
            f"Gomes: {verdict.verdict.value} (score {verdict.gomes_score}/10)",
            f"Phase: {verdict.lifecycle_phase.value if verdict.lifecycle_phase else 'N/A'}",
            f"Tier: {verdict.position_tier.value if verdict.position_tier else 'N/A'}",
            f"Kelly: {kelly_size:.1%}",
            f"R/R: {risk_reward:.2f}"
        ]
        
        if verdict.risk_factors:
            notes_parts.append(f"Risks: {len(verdict.risk_factors)}")
        
        # Create signal
        signal = TradingSignal(
            ticker=ticker,
            signal_type='BUY',
            ml_prediction_id=prediction.id,
            analyst_source_id=analyst_source_id,
            confidence=Decimal(str(float(prediction.confidence) * verdict.gomes_score / 10)),  # Weighted
            kelly_size=Decimal(str(kelly_size)),
            entry_price=Decimal(str(entry_price)),
            target_price=Decimal(str(target_price)) if target_price else None,
            stop_loss=Decimal(str(stop_loss)),
            risk_reward_ratio=Decimal(str(risk_reward)) if risk_reward else None,
            expires_at=prediction.valid_until,
            notes=" | ".join(notes_parts)
        )
        
        # Update prediction with Kelly size
        prediction.kelly_position_size = Decimal(str(kelly_size))
        
        self.db.add(signal)
        self.db.commit()
        self.db.refresh(signal)
        
        logger.info(
            f"{ticker} SIGNAL GENERATED: "
            f"{verdict.verdict.value} | Kelly {kelly_size:.1%} | R/R {risk_reward:.2f}"
        )
        
        return signal, verdict
    
    def generate_signals_batch(
        self,
        predictions: list[MLPrediction],
        **kwargs
    ) -> list[tuple[TradingSignal, GomesVerdict]]:
        """
        Generate signals for multiple predictions with Gomes filtering.
        
        Returns:
            List of (signal, verdict) tuples for approved signals only
        """
        results = []
        blocked_count = 0
        
        for prediction in predictions:
            try:
                signal, verdict = self.generate_signal(prediction, **kwargs)
                
                if signal:
                    results.append((signal, verdict))
                else:
                    if not verdict.passed_gomes_filter:
                        blocked_count += 1
                        
            except Exception as e:
                logger.error(f"Failed to generate signal for {prediction.ticker}: {e}")
        
        logger.info(
            f"Batch complete: {len(results)} signals generated, "
            f"{blocked_count} blocked by Gomes, "
            f"{len(predictions) - len(results) - blocked_count} filtered by R/R"
        )
        
        return results
    
    def get_active_signals_with_verdicts(self, limit: int = 20) -> list[dict[str, Any]]:
        """
        Get active trading signals enriched with Gomes verdicts.
        
        Returns:
            List of signal dicts with Gomes context
        """
        # Get base signals
        base_signals = self.base_generator.get_active_signals(limit=limit)
        
        enriched = []
        
        for signal in base_signals:
            ticker = signal['ticker']
            
            # Get latest verdict
            from app.models.gomes import InvestmentVerdictModel
            
            verdict = (
                self.db.query(InvestmentVerdictModel)
                .filter(InvestmentVerdictModel.ticker == ticker)
                .filter(InvestmentVerdictModel.valid_until.is_(None))
                .first()
            )
            
            # Enrich with Gomes data
            signal['gomes_context'] = {
                'verdict': verdict.verdict if verdict else None,
                'gomes_score': verdict.gomes_score if verdict else None,
                'passed_filter': verdict.passed_gomes_filter if verdict else True,
                'lifecycle_phase': verdict.lifecycle_phase if verdict else None,
                'position_tier': verdict.position_tier if verdict else None,
                'max_position_pct': float(verdict.max_position_size) if verdict and verdict.max_position_size else None,
                'risk_factors': verdict.risk_factors if verdict else [],
                'has_catalyst': verdict.has_catalyst if verdict else None
            }
            
            # Get price lines
            from app.models.gomes import PriceLinesModel
            
            lines = (
                self.db.query(PriceLinesModel)
                .filter(PriceLinesModel.ticker == ticker)
                .filter(PriceLinesModel.valid_until.is_(None))
                .first()
            )
            
            signal['price_lines'] = {
                'green_line': float(lines.green_line) if lines and lines.green_line else None,
                'red_line': float(lines.red_line) if lines and lines.red_line else None,
                'grey_line': float(lines.grey_line) if lines and lines.grey_line else None,
                'is_undervalued': lines.is_undervalued if lines else None
            }
            
            enriched.append(signal)
        
        return enriched


def create_gomes_signal_generator(db: Session) -> GomesIntegratedSignalGenerator:
    """Factory function for creating Gomes-integrated signal generator"""
    return GomesIntegratedSignalGenerator(db)
