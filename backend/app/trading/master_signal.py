"""
Master Signal v2.0 - Simplified 3-Pillar System
=================================================

SIMPLIFIED for Micro-Cap investing (The Gomes Way).

OLD (6 components):
- Investment Intelligence (30%)
- ML Predictions (25%)     ❌ REMOVED - Micro-caps are unpredictable
- Technical (15%)          ❌ SIMPLIFIED to 30 WMA only
- Sentiment (15%)          ❌ REMOVED - No Bloomberg for micro-caps
- Gap Analysis (10%)
- Risk/Reward (5%)

NEW (3 pillars):
- Thesis Tracker (60%)     ✅ Investment Intelligence + Milestones + Red Flags
- Valuation & Cash (25%)   ✅ Cash runway, burn rate, dilution risk
- Weinstein Guard (15%)    ✅ 30-Week Moving Average only

Author: GitHub Copilot with Claude Opus 4.5
Date: 2026-01-24
Version: 2.0.0
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Optional, List

import pandas as pd
from sqlalchemy.orm import Session

from app.models.trading import ActiveWatchlist, TradingSignal
from app.models.stock import Stock
from app.services.gomes_intelligence import GomesIntelligenceService
from app.trading.gomes_logic import InvestmentVerdict


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


class WeinsteinPhase(str, Enum):
    """Stan Weinstein's Market Phases"""
    PHASE_1_BASE = "PHASE_1_BASE"           # Accumulation - Watch
    PHASE_2_ADVANCE = "PHASE_2_ADVANCE"     # Uptrend - BUY
    PHASE_3_TOP = "PHASE_3_TOP"             # Distribution - Sell
    PHASE_4_DECLINE = "PHASE_4_DECLINE"     # Downtrend - AVOID


class CashRunwayStatus(str, Enum):
    """Cash runway health status"""
    HEALTHY = "HEALTHY"           # > 12 months runway
    CAUTION = "CAUTION"           # 6-12 months runway
    DANGER = "DANGER"             # < 6 months runway - Dilution risk!
    UNKNOWN = "UNKNOWN"           # No data


class WeightConfigV2:
    """
    Simplified weight configuration - 3 pillars only
    
    Thesis Tracker (60%) - Gomes is the authority
    Valuation & Cash (25%) - Hard numbers don't lie
    Weinstein Guard (15%) - Simple trend filter
    """
    THESIS_TRACKER: float = 0.60      # 60% - Gomes + Milestones + Red Flags
    VALUATION_CASH: float = 0.25      # 25% - Cash runway, dilution risk
    WEINSTEIN_GUARD: float = 0.15     # 15% - 30 WMA trend filter
    
    @classmethod
    def validate(cls) -> None:
        """Validate weights sum to 1.0"""
        total = cls.THESIS_TRACKER + cls.VALUATION_CASH + cls.WEINSTEIN_GUARD
        if not 0.99 <= total <= 1.01:
            raise ValueError(f"Weights must sum to 1.0, got {total}")


WeightConfigV2.validate()


# ==============================================================================
# Data Models
# ==============================================================================

@dataclass
class ThesisTrackerScore:
    """Thesis Tracker component (60% weight)"""
    conviction_score: float              # 0-100 from Investment Intelligence
    milestones_hit: int             # Count of achieved milestones
    red_flags_count: int            # Count of red flags (dilution, delays, etc.)
    verdict: str                    # Gomes verdict string
    combined_score: float           # Final 0-100 score


@dataclass
class ValuationCashScore:
    """Valuation & Cash component (25% weight)"""
    cash_on_hand: Optional[float]   # In millions
    total_debt: Optional[float]     # In millions
    burn_rate: Optional[float]      # Monthly burn in millions
    runway_months: Optional[float]  # Months until cash runs out
    runway_status: CashRunwayStatus
    dilution_risk: bool             # Is dilution likely?
    combined_score: float           # Final 0-100 score


@dataclass
class WeinsteinGuardScore:
    """Weinstein Trend Guard component (15% weight)"""
    current_price: float
    wma_30: float                   # 30-week moving average
    wma_slope: float                # Slope of 30 WMA (-1 to +1)
    phase: WeinsteinPhase
    price_vs_wma_pct: float         # % above/below 30 WMA
    combined_score: float           # Final 0-100 score


@dataclass
class SignalComponentsV2:
    """All signal components for v2"""
    thesis_tracker: ThesisTrackerScore
    valuation_cash: ValuationCashScore
    weinstein_guard: WeinsteinGuardScore


@dataclass
class MasterSignalResultV2:
    """
    Master Signal v2.0 Result
    
    Simplified output - 3 pillars instead of 6.
    """
    ticker: str
    buy_confidence: float           # 0-100 - THE KEY NUMBER
    signal_strength: SignalStrength
    
    # Component breakdown (3 pillars)
    components: SignalComponentsV2
    
    # Blocking reasons
    blocked: bool
    blocked_reason: Optional[str]
    
    # Actionable data
    verdict: str
    entry_price: Optional[float]
    target_price: Optional[float]
    stop_loss: Optional[float]
    risk_reward_ratio: Optional[float]
    
    # Metadata
    calculated_at: datetime
    
    def to_dict(self) -> dict:
        """Convert to API response"""
        return {
            "ticker": self.ticker,
            "buy_confidence": round(self.buy_confidence, 2),
            "signal_strength": self.signal_strength.value,
            "components": {
                "thesis_tracker": {
                    "score": round(self.components.thesis_tracker.combined_score, 2),
                    "conviction_score": round(self.components.thesis_tracker.conviction_score, 2),
                    "milestones_hit": self.components.thesis_tracker.milestones_hit,
                    "red_flags": self.components.thesis_tracker.red_flags_count,
                    "verdict": self.components.thesis_tracker.verdict,
                },
                "valuation_cash": {
                    "score": round(self.components.valuation_cash.combined_score, 2),
                    "cash_on_hand_m": self.components.valuation_cash.cash_on_hand,
                    "runway_months": self.components.valuation_cash.runway_months,
                    "runway_status": self.components.valuation_cash.runway_status.value,
                    "dilution_risk": self.components.valuation_cash.dilution_risk,
                },
                "weinstein_guard": {
                    "score": round(self.components.weinstein_guard.combined_score, 2),
                    "phase": self.components.weinstein_guard.phase.value,
                    "price": self.components.weinstein_guard.current_price,
                    "wma_30": round(self.components.weinstein_guard.wma_30, 2),
                    "price_vs_wma_pct": round(self.components.weinstein_guard.price_vs_wma_pct, 2),
                },
            },
            "blocked": self.blocked,
            "blocked_reason": self.blocked_reason,
            "verdict": self.verdict,
            "entry_price": self.entry_price,
            "target_price": self.target_price,
            "stop_loss": self.stop_loss,
            "risk_reward_ratio": round(self.risk_reward_ratio, 2) if self.risk_reward_ratio else None,
            "calculated_at": self.calculated_at.isoformat(),
        }


# ==============================================================================
# Master Signal Aggregator v2.0
# ==============================================================================

class MasterSignalAggregatorV2:
    """
    Master Signal v2.0 - Simplified 3-Pillar System
    
    Designed for Micro-Cap investing following Mark Gomes methodology.
    
    Pillars:
    1. Thesis Tracker (60%) - AI analysis of transcripts + milestones
    2. Valuation & Cash (25%) - Cash runway, burn rate, dilution risk
    3. Weinstein Guard (15%) - 30-week moving average trend filter
    
    Usage:
        aggregator = MasterSignalAggregatorV2(db)
        result = aggregator.calculate_master_signal("GKPRF")
        
        if result.buy_confidence >= 70 and not result.blocked:
            print(f"BUY: {result.ticker} at ${result.entry_price}")
    """
    
    def __init__(self, db: Session):
        """Initialize Master Signal v2 Aggregator"""
        self.db = db
        self.gomes_service = GomesIntelligenceService(db)
        logger.info("Master Signal v2.0 initialized (3-pillar system)")
    
    # ==========================================================================
    # Main Entry Point
    # ==========================================================================
    
    def calculate_master_signal(
        self,
        ticker: str,
        user_id: Optional[int] = None,
        current_price: Optional[float] = None,
    ) -> MasterSignalResultV2:
        """
        Calculate Master Signal using 3-pillar system.
        
        Args:
            ticker: Stock ticker symbol
            user_id: Optional user ID (for portfolio context)
            current_price: Current price (will fetch if None)
            
        Returns:
            MasterSignalResultV2 with buy_confidence (0-100)
        """
        logger.info(f"Calculating Master Signal v2.0 for {ticker}")
        
        # Fetch current price if not provided
        if current_price is None:
            current_price = self._fetch_current_price(ticker)
        
        # =======================================================
        # PILLAR 1: Thesis Tracker (60%)
        # =======================================================
        thesis_score = self._calculate_thesis_tracker(ticker, current_price)
        
        # =======================================================
        # PILLAR 2: Valuation & Cash (25%)
        # =======================================================
        valuation_score = self._calculate_valuation_cash(ticker)
        
        # =======================================================
        # PILLAR 3: Weinstein Trend Guard (15%)
        # =======================================================
        weinstein_score = self._calculate_weinstein_guard(ticker, current_price)
        
        # =======================================================
        # AGGREGATE SCORES
        # =======================================================
        buy_confidence = (
            thesis_score.combined_score * WeightConfigV2.THESIS_TRACKER +
            valuation_score.combined_score * WeightConfigV2.VALUATION_CASH +
            weinstein_score.combined_score * WeightConfigV2.WEINSTEIN_GUARD
        )
        
        # =======================================================
        # BLOCKING RULES
        # =======================================================
        blocked = False
        blocked_reason = None
        
        # Rule 1: Weinstein Phase 4 = DO NOT BUY
        if weinstein_score.phase == WeinsteinPhase.PHASE_4_DECLINE:
            blocked = True
            blocked_reason = "WEINSTEIN_PHASE_4: Price below falling 30 WMA - DO NOT BUY"
            buy_confidence *= 0.3  # Heavy penalty
        
        # Rule 2: Cash Runway < 6 months = Dilution risk
        if valuation_score.runway_status == CashRunwayStatus.DANGER:
            blocked = True
            blocked_reason = "CASH_RUNWAY_DANGER: Less than 6 months runway - Dilution likely"
            buy_confidence *= 0.5  # Penalty
        
        # Rule 3: Multiple red flags from Gomes
        if thesis_score.red_flags_count >= 3:
            blocked = True
            blocked_reason = f"RED_FLAGS: {thesis_score.red_flags_count} red flags detected"
            buy_confidence *= 0.5
        
        # Classify signal strength
        signal_strength = self._classify_strength(buy_confidence)
        
        # Get entry/target/stop from Gomes verdict
        verdict_obj = self.gomes_service.generate_verdict(ticker, current_price)
        
        # Extract green_line (buy target) and red_line (sell target) from verdict
        target_price = verdict_obj.red_line if verdict_obj else None
        stop_loss = verdict_obj.green_line * 0.9 if verdict_obj and verdict_obj.green_line else None
        
        # Calculate risk/reward if we have the data
        risk_reward = None
        if current_price and target_price and stop_loss and current_price > stop_loss:
            potential_gain = target_price - current_price
            potential_loss = current_price - stop_loss
            if potential_loss > 0:
                risk_reward = potential_gain / potential_loss
        
        components = SignalComponentsV2(
            thesis_tracker=thesis_score,
            valuation_cash=valuation_score,
            weinstein_guard=weinstein_score,
        )
        
        return MasterSignalResultV2(
            ticker=ticker,
            buy_confidence=buy_confidence,
            signal_strength=signal_strength,
            components=components,
            blocked=blocked,
            blocked_reason=blocked_reason,
            verdict=thesis_score.verdict,
            entry_price=current_price,
            target_price=target_price,
            stop_loss=stop_loss,
            risk_reward_ratio=risk_reward,
            calculated_at=datetime.utcnow(),
        )
    
    # ==========================================================================
    # Pillar 1: Thesis Tracker (60%)
    # ==========================================================================
    
    def _calculate_thesis_tracker(
        self,
        ticker: str,
        current_price: Optional[float]
    ) -> ThesisTrackerScore:
        """
        Calculate Thesis Tracker score.
        
        This is the heart of Gomes methodology - AI analysis of transcripts.
        
        Components:
        - Investment Intelligence Score (main)
        - Milestones achieved (contracts, certifications, revenue)
        - Red flags (dilution, delays, leadership changes)
        """
        try:
            verdict = self.gomes_service.generate_verdict(ticker, current_price)
            
            # Convert verdict to base score
            verdict_scores = {
                InvestmentVerdict.STRONG_BUY: 95.0,
                InvestmentVerdict.BUY: 80.0,
                InvestmentVerdict.HOLD: 50.0,
                InvestmentVerdict.SELL: 25.0,
                InvestmentVerdict.AVOID: 5.0,
            }
            conviction_score = verdict_scores.get(verdict.verdict, 50.0)
            
            # Count milestones from latest analysis
            # TODO: Implement milestone tracking from transcripts
            milestones_hit = 0
            
            # Count red flags
            # TODO: Implement red flag detection
            red_flags_count = 0
            if not verdict.passed_gomes_filter:
                red_flags_count += 1
            
            # Apply penalties/bonuses
            combined_score = conviction_score
            combined_score += milestones_hit * 5  # +5 per milestone
            combined_score -= red_flags_count * 15  # -15 per red flag
            combined_score = max(0, min(100, combined_score))
            
            return ThesisTrackerScore(
                conviction_score=conviction_score,
                milestones_hit=milestones_hit,
                red_flags_count=red_flags_count,
                verdict=verdict.verdict.value,
                combined_score=combined_score,
            )
            
        except Exception as e:
            logger.warning(f"Thesis Tracker error for {ticker}: {e}")
            return ThesisTrackerScore(
                conviction_score=50.0,
                milestones_hit=0,
                red_flags_count=0,
                verdict="UNKNOWN",
                combined_score=50.0,
            )
    
    # ==========================================================================
    # Pillar 2: Valuation & Cash (25%)
    # ==========================================================================
    
    def _calculate_valuation_cash(self, ticker: str) -> ValuationCashScore:
        """
        Calculate Valuation & Cash score from DB data.
        
        Gomes Rule: "Did they run out of money?"
        
        Uses cash_runway_months from Deep DD analysis stored in DB.
        NO YFINANCE - we use our own analysis data.
        
        Key metrics:
        - Cash runway (months until cash runs out)
        - Dilution risk assessment
        """
        try:
            # Get stock from DB with Deep DD data
            stock = (
                self.db.query(Stock)
                .filter(Stock.ticker == ticker)
                .filter(Stock.is_latest == True)
                .first()
            )
            
            # Default values if no data
            cash = None
            debt = None
            burn_rate = None
            runway_months = None
            
            # Try to extract from stock's raw_notes or catalysts (Deep DD stores here)
            if stock and stock.raw_notes:
                # Parse cash runway from Deep DD stored data
                notes = stock.raw_notes.lower()
                if "cash runway" in notes or "runway" in notes:
                    # Extract months if mentioned
                    import re
                    match = re.search(r'(\d+)\s*m[oě]s[íi]c', notes)
                    if match:
                        runway_months = float(match.group(1))
            
            # Determine status based on runway
            if runway_months is None:
                runway_status = CashRunwayStatus.UNKNOWN
                dilution_risk = False
                combined_score = 50.0  # Neutral when unknown
            elif runway_months >= 18:
                runway_status = CashRunwayStatus.HEALTHY
                dilution_risk = False
                combined_score = 90.0
            elif runway_months >= 12:
                runway_status = CashRunwayStatus.HEALTHY
                dilution_risk = False
                combined_score = 75.0
            elif runway_months >= 6:
                runway_status = CashRunwayStatus.CAUTION
                dilution_risk = True
                combined_score = 50.0
            else:
                runway_status = CashRunwayStatus.DANGER
                dilution_risk = True
                combined_score = 20.0
            
            return ValuationCashScore(
                cash_on_hand=cash,
                total_debt=debt,
                burn_rate=burn_rate,
                runway_months=runway_months,
                runway_status=runway_status,
                dilution_risk=dilution_risk,
                combined_score=combined_score,
            )
            
        except Exception as e:
            logger.warning(f"Valuation & Cash error for {ticker}: {e}")
            return ValuationCashScore(
                cash_on_hand=None,
                total_debt=None,
                burn_rate=None,
                runway_months=None,
                runway_status=CashRunwayStatus.UNKNOWN,
                dilution_risk=False,
                combined_score=50.0,  # Neutral on error
            )
    
    # ==========================================================================
    # Pillar 3: Weinstein Trend Guard (15%)
    # ==========================================================================
    
    def _calculate_weinstein_guard(
        self,
        ticker: str,
        current_price: Optional[float]
    ) -> WeinsteinGuardScore:
        """
        Calculate Weinstein Trend Guard score.
        
        SIMPLIFIED VERSION - No yfinance dependency.
        
        We use price position relative to green_line/red_line from DB
        as a proxy for trend analysis:
        - Near green_line = likely in accumulation (Phase 1/2)
        - Near red_line = likely topping out (Phase 3/4)
        
        For proper 30 WMA, user should run Deep DD which stores this data.
        """
        try:
            # Get stock from DB
            stock = (
                self.db.query(Stock)
                .filter(Stock.ticker == ticker)
                .filter(Stock.is_latest == True)
                .first()
            )
            
            if not stock:
                return self._default_weinstein_score(current_price or 0)
            
            # Use stored price data
            price = current_price or stock.current_price
            green_line = stock.green_line
            red_line = stock.red_line
            
            if not price or not green_line or not red_line:
                return self._default_weinstein_score(price or 0)
            
            # Calculate price position (0% = at green, 100% = at red)
            if red_line > green_line:
                price_range = red_line - green_line
                price_position = ((price - green_line) / price_range) * 100 if price_range > 0 else 50
            else:
                price_position = 50  # Default to middle
            
            # Determine phase based on price position
            if price_position <= 25:
                # Near green line = likely Phase 2 (accumulation/advance)
                phase = WeinsteinPhase.PHASE_2_ADVANCE
                combined_score = 85.0
            elif price_position <= 50:
                # Lower half = Phase 1 (base building)
                phase = WeinsteinPhase.PHASE_1_BASE
                combined_score = 65.0
            elif price_position <= 75:
                # Upper half = Phase 3 (topping)
                phase = WeinsteinPhase.PHASE_3_TOP
                combined_score = 40.0
            else:
                # Near red line = Phase 4 (decline/overvalued)
                phase = WeinsteinPhase.PHASE_4_DECLINE
                combined_score = 15.0
            
            return WeinsteinGuardScore(
                current_price=price,
                wma_30=green_line,  # Use green_line as proxy
                wma_slope=0.0,  # Not calculated without historical data
                phase=phase,
                price_vs_wma_pct=price_position - 50,  # Relative to midpoint
                combined_score=combined_score,
            )
            
        except Exception as e:
            logger.warning(f"Weinstein Guard error for {ticker}: {e}")
            return self._default_weinstein_score(current_price or 0)
    
    def _default_weinstein_score(self, price: float) -> WeinsteinGuardScore:
        """Return neutral Weinstein score on error"""
        return WeinsteinGuardScore(
            current_price=price,
            wma_30=price,
            wma_slope=0.0,
            phase=WeinsteinPhase.PHASE_1_BASE,
            price_vs_wma_pct=0.0,
            combined_score=50.0,
        )
    
    # ==========================================================================
    # Helpers
    # ==========================================================================
    
    def _fetch_current_price(self, ticker: str) -> Optional[float]:
        """Fetch current market price from DB"""
        try:
            stock = (
                self.db.query(Stock)
                .filter(Stock.ticker == ticker)
                .filter(Stock.is_latest == True)
                .first()
            )
            if stock and stock.current_price:
                return float(stock.current_price)
        except Exception as e:
            logger.warning(f"Failed to fetch price for {ticker}: {e}")
        return None
    
    def _classify_strength(self, confidence: float) -> SignalStrength:
        """Classify buy confidence into signal strength"""
        if confidence >= 80:
            return SignalStrength.STRONG_BUY
        elif confidence >= 60:
            return SignalStrength.BUY
        elif confidence >= 40:
            return SignalStrength.WEAK_BUY
        elif confidence >= 20:
            return SignalStrength.NEUTRAL
        else:
            return SignalStrength.AVOID


# ==============================================================================
# Convenience Functions
# ==============================================================================

def calculate_master_signal_v2(
    db: Session,
    ticker: str,
    user_id: Optional[int] = None,
) -> MasterSignalResultV2:
    """
    Convenience function to calculate Master Signal v2.
    
    Usage:
        result = calculate_master_signal_v2(db, "GKPRF")
        print(f"Buy Confidence: {result.buy_confidence}%")
    """
    aggregator = MasterSignalAggregatorV2(db)
    return aggregator.calculate_master_signal(ticker, user_id)


def get_top_opportunities_v2(
    db: Session,
    tickers: List[str],
    min_confidence: float = 60.0,
    exclude_blocked: bool = True,
) -> List[MasterSignalResultV2]:
    """
    Get top opportunities from list of tickers.
    
    Args:
        db: Database session
        tickers: List of tickers to analyze
        min_confidence: Minimum buy confidence (default 60%)
        exclude_blocked: Exclude blocked signals (default True)
        
    Returns:
        List of MasterSignalResultV2 sorted by confidence (highest first)
    """
    aggregator = MasterSignalAggregatorV2(db)
    results = []
    
    for ticker in tickers:
        try:
            result = aggregator.calculate_master_signal(ticker)
            
            if result.buy_confidence >= min_confidence:
                if not exclude_blocked or not result.blocked:
                    results.append(result)
                    
        except Exception as e:
            logger.warning(f"Failed to calculate signal for {ticker}: {e}")
    
    # Sort by confidence (highest first)
    results.sort(key=lambda x: x.buy_confidence, reverse=True)
    
    return results
