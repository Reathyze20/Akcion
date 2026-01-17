"""
Gomes Investment Gatekeeper Logic
===================================

Core implementation of Mark Gomes (Money Mark) investment methodology.
This module acts as the GATEKEEPER - no investment passes without Gomes approval.

Key Components:
1. MarketAlertSystem - Traffic light for overall market (GREEN/YELLOW/ORANGE/RED)
2. StockLifecycleClassifier - Phase detection (GREAT_FIND/WAIT_TIME/GOLD_MINE)
3. RiskRewardCalculator - Green/Red line analysis
4. PositionSizingEngine - Tier-based position limits
5. GomesGatekeeper - Final verdict synthesizer

Author: GitHub Copilot with Claude Opus 4.5
Date: 2026-01-17

Reference: Mark Gomes "How I Make Money On Stocks" transcript
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ============================================================================
# ENUMS - Core Gomes Categories
# ============================================================================

class MarketAlert(str, Enum):
    """
    Market Alert Levels (Mark Gomes style)
    
    Ref: Minute 15:00 - Market Alert System
    """
    GREEN = "GREEN"    # OFFENSE - Aggressively deploying capital - Good time to buy
    YELLOW = "YELLOW"  # SELECTIVE - Only best setups
    ORANGE = "ORANGE"  # DEFENSE - Reducing exposure
    RED = "RED"        # CASH IS KING - Preserve capital


class LifecyclePhase(str, Enum):
    """
    Stock Lifecycle Phases
    
    Ref: Minute 25:00 - Stock Life Phases
    """
    GREAT_FIND = "GREAT_FIND"  # Dream phase - unknown, starting to grow
    WAIT_TIME = "WAIT_TIME"    # Hype died, dead money - AVOID!
    GOLD_MINE = "GOLD_MINE"    # Proven execution - safe buy
    UNKNOWN = "UNKNOWN"        # Cannot determine phase


class PositionTier(str, Enum):
    """
    Position Sizing Tiers
    
    Ref: Minute 50:00 - Position Sizing
    """
    PRIMARY = "PRIMARY"      # Core position - 10% max (proven Gold Mine)
    SECONDARY = "SECONDARY"  # Unofficial - 5% max (Great Find, dating)
    TERTIARY = "TERTIARY"    # FOMO/Speculative - 1-2% max


class InvestmentVerdict(str, Enum):
    """Final investment decision"""
    STRONG_BUY = "STRONG_BUY"  # Gomes score 9-10, all filters pass
    BUY = "BUY"                # Gomes score 7-8
    ACCUMULATE = "ACCUMULATE"  # Buy on dips, add slowly
    HOLD = "HOLD"              # Keep position, don't add
    TRIM = "TRIM"              # Reduce position (3-point rule)
    SELL = "SELL"              # Exit position
    AVOID = "AVOID"            # Don't enter
    BLOCKED = "BLOCKED"        # Failed Gomes filter - HARD NO


# ============================================================================
# DATA CLASSES - Structured Results
# ============================================================================

@dataclass
class MarketAllocation:
    """Portfolio allocation based on market alert level"""
    alert_level: MarketAlert
    stocks_pct: float  # 0-100
    cash_pct: float    # 0-100
    hedge_pct: float   # 0-100
    hedge_ticker: str = "RWM"  # Russell 2000 Short ETF
    
    def __post_init__(self):
        """Validate allocation sums to 100%"""
        total = self.stocks_pct + self.cash_pct + self.hedge_pct
        if abs(total - 100.0) > 0.01:
            raise ValueError(f"Allocation must sum to 100%, got {total}%")


@dataclass
class LifecycleAssessment:
    """Stock lifecycle phase assessment"""
    ticker: str
    phase: LifecyclePhase
    is_investable: bool
    firing_on_all_cylinders: bool | None  # None = unknown
    cylinders_count: int | None  # 0-10
    signals: dict[str, bool] = field(default_factory=dict)
    reasoning: str = ""
    confidence: str = "MEDIUM"  # HIGH/MEDIUM/LOW


@dataclass
class PriceLines:
    """Green/Red/Grey line price targets"""
    ticker: str
    green_line: float | None  # Buy zone
    red_line: float | None    # Sell zone
    grey_line: float | None   # Neutral (optional)
    current_price: float | None
    source: str = "unknown"  # transcript, image, manual
    
    @property
    def is_undervalued(self) -> bool | None:
        """Check if current price is below green line"""
        if self.current_price is None or self.green_line is None:
            return None
        return self.current_price < self.green_line
    
    @property
    def is_overvalued(self) -> bool | None:
        """Check if current price is above red line"""
        if self.current_price is None or self.red_line is None:
            return None
        return self.current_price > self.red_line
    
    @property
    def price_vs_green_pct(self) -> float | None:
        """Percentage above/below green line"""
        if self.current_price is None or self.green_line is None:
            return None
        if self.green_line == 0:
            return None
        return ((self.current_price - self.green_line) / self.green_line) * 100


@dataclass
class PositionLimit:
    """Position sizing constraints"""
    ticker: str
    tier: PositionTier
    max_portfolio_pct: float
    recommended_pct: float
    allowed_in_yellow: bool
    allowed_in_orange: bool
    allowed_in_red: bool
    reasoning: str = ""


@dataclass
class GomesVerdict:
    """
    Final investment verdict - the Gatekeeper's decision.
    
    This is the output that tells you whether to invest or not.
    """
    ticker: str
    verdict: InvestmentVerdict
    passed_gomes_filter: bool
    blocked_reason: str | None = None
    
    # Scores
    gomes_score: int = 0  # 0-10
    ml_prediction_score: float | None = None  # 0-100%
    ml_direction: str | None = None  # UP/DOWN/NEUTRAL
    
    # Context
    lifecycle_phase: LifecyclePhase = LifecyclePhase.UNKNOWN
    market_alert: MarketAlert = MarketAlert.GREEN
    position_tier: PositionTier | None = None
    max_position_pct: float = 0.0
    
    # Price context
    current_price: float | None = None
    green_line: float | None = None
    red_line: float | None = None
    
    # Risk
    risk_factors: list[str] = field(default_factory=list)
    days_to_earnings: int | None = None
    
    # Catalyst
    has_catalyst: bool = False
    catalyst_type: str | None = None
    catalyst_description: str | None = None
    
    # Cases
    bull_case: str | None = None
    bear_case: str | None = None
    
    # Confidence
    confidence: str = "MEDIUM"
    reasoning: str = ""
    
    # Timestamps
    created_at: datetime = field(default_factory=datetime.now)


# ============================================================================
# 1. MARKET ALERT SYSTEM (Semafor)
# ============================================================================

class MarketAlertSystem:
    """
    Market Alert System (Mark Gomes style)
    
    Ref: Minute 15:00 - "When I see the market is expensive, I raise cash..."
    
    GREEN ALERT: OFFENSE - Aggressively deploying capital - Good time to buy
    YELLOW ALERT: SELECTIVE - Only best setups
    ORANGE ALERT: DEFENSE - Reducing exposure
    RED ALERT: CASH IS KING - Preserve capital
    """
    
    # Alert descriptions (displayed in UI)
    ALERT_DESCRIPTIONS: dict[MarketAlert, tuple[str, str]] = {
        MarketAlert.GREEN: ("OFFENSE", "Aggressively deploying capital - Good time to buy"),
        MarketAlert.YELLOW: ("SELECTIVE", "Only best setups"),
        MarketAlert.ORANGE: ("DEFENSE", "Reducing exposure"),
        MarketAlert.RED: ("CASH IS KING", "Preserve capital"),
    }
    
    # Default allocations per alert level
    ALLOCATIONS: dict[MarketAlert, tuple[float, float, float]] = {
        MarketAlert.GREEN: (100.0, 0.0, 0.0),    # stocks, cash, hedge
        MarketAlert.YELLOW: (75.0, 15.0, 10.0),
        MarketAlert.ORANGE: (25.0, 35.0, 40.0),
        MarketAlert.RED: (5.0, 45.0, 50.0),
    }
    
    @classmethod
    def get_description(cls, alert_level: MarketAlert | str) -> tuple[str, str]:
        """Get mode name and description for alert level"""
        if isinstance(alert_level, str):
            alert_level = MarketAlert(alert_level.upper())
        return cls.ALERT_DESCRIPTIONS[alert_level]
    
    @classmethod
    def get_allocation(cls, alert_level: MarketAlert | str) -> MarketAllocation:
        """
        Get portfolio allocation for given alert level.
        
        Args:
            alert_level: Market alert level (enum or string)
            
        Returns:
            MarketAllocation with percentages
            
        Ref: Minute 16:30 - "In Yellow, I'm 20-30% in cash and hedge"
        """
        if isinstance(alert_level, str):
            alert_level = MarketAlert(alert_level.upper())
        
        stocks, cash, hedge = cls.ALLOCATIONS[alert_level]
        
        return MarketAllocation(
            alert_level=alert_level,
            stocks_pct=stocks,
            cash_pct=cash,
            hedge_pct=hedge,
            hedge_ticker="RWM"  # Russell 2000 Short
        )
    
    @classmethod
    def is_speculative_allowed(cls, alert_level: MarketAlert | str) -> bool:
        """
        Check if speculative (TERTIARY) positions are allowed.
        
        Ref: Minute 18:00 - "In YELLOW ALERT, I sell all speculative positions"
        """
        if isinstance(alert_level, str):
            alert_level = MarketAlert(alert_level.upper())
        
        # Only GREEN allows speculative
        return alert_level == MarketAlert.GREEN
    
    @classmethod
    def get_blocked_tiers(cls, alert_level: MarketAlert | str) -> list[PositionTier]:
        """Get position tiers that are blocked at this alert level"""
        if isinstance(alert_level, str):
            alert_level = MarketAlert(alert_level.upper())
        
        blocked = []
        
        if alert_level == MarketAlert.YELLOW:
            blocked.append(PositionTier.TERTIARY)
        elif alert_level == MarketAlert.ORANGE:
            blocked.extend([PositionTier.TERTIARY, PositionTier.SECONDARY])
        elif alert_level == MarketAlert.RED:
            blocked.extend([PositionTier.TERTIARY, PositionTier.SECONDARY, PositionTier.PRIMARY])
        
        return blocked


# ============================================================================
# 2. STOCK LIFECYCLE CLASSIFIER
# ============================================================================

class StockLifecycleClassifier:
    """
    Stock Lifecycle Phase Detection
    
    Ref: Minute 25:00 - 31:28 - Stock Life Phases
    
    GREAT FIND: Dream phase - unknown small-cap, starting to grow
    WAIT TIME: Hype died - DEAD MONEY - DO NOT INVEST
    GOLD MINE: Proven execution - profitable or strong orders
    """
    
    # Keywords that indicate WAIT_TIME phase (AVOID!)
    WAIT_TIME_SIGNALS = [
        "delays", "delayed", "waiting for approval", "no orders yet",
        "waiting for fda", "clinical trial failed", "missed guidance",
        "execution problems", "management issues", "cfo left", "ceo left",
        "lawsuit", "sec investigation", "accounting issues", "restatement",
        "dead money", "going nowhere", "stuck", "stalled"
    ]
    
    # Keywords that indicate GOLD_MINE phase (SAFE BUY)
    GOLD_MINE_SIGNALS = [
        "firing on all cylinders", "profitable", "record revenue",
        "beat earnings", "raised guidance", "strong orders", "backlog",
        "growing revenue", "cash flow positive", "execution excellent",
        "management delivers", "institutional buying", "upgrading"
    ]
    
    # Keywords that indicate GREAT_FIND phase
    GREAT_FIND_SIGNALS = [
        "new discovery", "under the radar", "nobody knows",
        "early stage", "first mover", "disruptive", "revolutionary",
        "undiscovered", "hidden gem", "before the crowd"
    ]
    
    @classmethod
    def classify(cls, ticker: str, text: str | None = None) -> LifecycleAssessment:
        """
        Classify stock into lifecycle phase.
        
        Args:
            ticker: Stock ticker
            text: Optional transcript/analysis text
            
        Returns:
            LifecycleAssessment with phase and investability
            
        Ref: Minute 31:28 - "Wait Time is the KILLER. Don't invest."
        """
        signals: dict[str, bool] = {}
        text_lower = (text or "").lower()
        
        # Check for WAIT_TIME signals first (highest priority for rejection)
        wait_time_count = 0
        for signal in cls.WAIT_TIME_SIGNALS:
            if signal in text_lower:
                signals[f"wait_time:{signal}"] = True
                wait_time_count += 1
        
        # Check for GOLD_MINE signals
        gold_mine_count = 0
        for signal in cls.GOLD_MINE_SIGNALS:
            if signal in text_lower:
                signals[f"gold_mine:{signal}"] = True
                gold_mine_count += 1
        
        # Check for GREAT_FIND signals
        great_find_count = 0
        for signal in cls.GREAT_FIND_SIGNALS:
            if signal in text_lower:
                signals[f"great_find:{signal}"] = True
                great_find_count += 1
        
        # Determine phase based on signal counts
        phase = LifecyclePhase.UNKNOWN
        is_investable = True
        reasoning = ""
        confidence = "LOW"
        
        # WAIT_TIME takes priority (it's the killer)
        if wait_time_count >= 2:
            phase = LifecyclePhase.WAIT_TIME
            is_investable = False
            reasoning = f"Detected {wait_time_count} Wait Time signals - DEAD MONEY"
            confidence = "HIGH" if wait_time_count >= 3 else "MEDIUM"
        
        elif gold_mine_count >= 2:
            phase = LifecyclePhase.GOLD_MINE
            is_investable = True
            reasoning = f"Detected {gold_mine_count} Gold Mine signals - proven execution"
            confidence = "HIGH" if gold_mine_count >= 3 else "MEDIUM"
        
        elif great_find_count >= 2:
            phase = LifecyclePhase.GREAT_FIND
            is_investable = True
            reasoning = f"Detected {great_find_count} Great Find signals - early opportunity"
            confidence = "MEDIUM"
        
        elif text:
            # Text provided but no clear signals
            reasoning = "Insufficient signals to determine phase"
        else:
            reasoning = "No text provided for analysis"
        
        # Check for "firing on all cylinders"
        firing = None
        cylinders = None
        if "firing on all cylinders" in text_lower or "10 cylinders" in text_lower:
            firing = True
            cylinders = 10
        elif "not firing" in text_lower or "problems" in text_lower:
            firing = False
            cylinders = 5  # Default partial
        
        return LifecycleAssessment(
            ticker=ticker,
            phase=phase,
            is_investable=is_investable,
            firing_on_all_cylinders=firing,
            cylinders_count=cylinders,
            signals=signals,
            reasoning=reasoning,
            confidence=confidence
        )
    
    @classmethod
    def is_investable(cls, phase: LifecyclePhase | str) -> bool:
        """
        Quick check if phase is investable.
        
        Ref: Minute 31:28 - "Wait Time is the KILLER"
        """
        if isinstance(phase, str):
            phase = LifecyclePhase(phase.upper())
        
        return phase != LifecyclePhase.WAIT_TIME


# ============================================================================
# 3. RISK/REWARD CALCULATOR (Lines Logic)
# ============================================================================

class RiskRewardCalculator:
    """
    Green Line / Red Line Analysis
    
    Ref: Minute 35:00 - Price Target Lines
    
    Green Line: Undervalued - BUY ZONE
    Red Line: Fair/Overvalued - SELL ZONE
    3-Point Rule: If score drops 3 points, take profit
    Doubling Rule: Doubled money? Sell half (House Money)
    """
    
    @classmethod
    def analyze_lines(
        cls,
        ticker: str,
        current_price: float | None,
        green_line: float | None,
        red_line: float | None,
        grey_line: float | None = None,
        source: str = "manual"
    ) -> PriceLines:
        """
        Create price lines analysis.
        
        Args:
            ticker: Stock ticker
            current_price: Current market price
            green_line: Buy zone price
            red_line: Sell zone price
            grey_line: Optional neutral zone
            source: Data source
            
        Returns:
            PriceLines with analysis
        """
        return PriceLines(
            ticker=ticker,
            green_line=green_line,
            red_line=red_line,
            grey_line=grey_line,
            current_price=current_price,
            source=source
        )
    
    @classmethod
    def should_take_profit(
        cls,
        current_score: int,
        previous_score: int
    ) -> bool:
        """
        3-Point Rule: Score dropped 3+ points = Take Profit
        
        Ref: Minute 40:00 - "If score drops 3 points, I'm out"
        """
        return previous_score - current_score >= 3
    
    @classmethod
    def apply_doubling_rule(
        cls,
        entry_price: float,
        current_price: float
    ) -> tuple[bool, str]:
        """
        Doubling Rule: Doubled money = Sell half
        
        Ref: Minute 42:00 - "House Money Rule"
        
        Returns:
            (should_sell_half, recommendation)
        """
        if entry_price <= 0:
            return False, "Invalid entry price"
        
        gain_pct = ((current_price - entry_price) / entry_price) * 100
        
        if gain_pct >= 100:
            return True, f"DOUBLING RULE: +{gain_pct:.1f}% gain. Sell half, play with house money."
        elif gain_pct >= 75:
            return False, f"Approaching double: +{gain_pct:.1f}%. Consider partial profit."
        else:
            return False, f"Current gain: +{gain_pct:.1f}%"
    
    @classmethod
    def get_action_zone(
        cls,
        current_price: float | None,
        green_line: float | None,
        red_line: float | None
    ) -> tuple[str, str]:
        """
        Determine action zone based on price vs lines.
        
        Returns:
            (zone: "BUY"/"HOLD"/"SELL", reason)
        """
        if current_price is None:
            return "UNKNOWN", "Current price not available"
        
        if green_line is not None and current_price < green_line:
            pct_below = ((green_line - current_price) / green_line) * 100
            return "BUY", f"Price {pct_below:.1f}% below Green Line (undervalued)"
        
        if red_line is not None and current_price > red_line:
            pct_above = ((current_price - red_line) / red_line) * 100
            return "SELL", f"Price {pct_above:.1f}% above Red Line (overvalued)"
        
        if green_line is not None and red_line is not None:
            # Between green and red
            range_total = red_line - green_line
            position = current_price - green_line
            pct_in_range = (position / range_total) * 100 if range_total > 0 else 50
            
            if pct_in_range < 30:
                return "BUY", f"Near Green Line ({pct_in_range:.0f}% of range)"
            elif pct_in_range > 70:
                return "SELL", f"Near Red Line ({pct_in_range:.0f}% of range)"
            else:
                return "HOLD", f"Middle of range ({pct_in_range:.0f}%)"
        
        return "HOLD", "Insufficient line data"


# ============================================================================
# 4. POSITION SIZING ENGINE
# ============================================================================

class PositionSizingEngine:
    """
    Position Sizing Based on Tier
    
    Ref: Minute 50:00 - Position Sizing Rules
    
    PRIMARY (Core): 10% max - Proven Gold Mine stocks
    SECONDARY: 5% max - Great Find, dating phase
    TERTIARY: 1-2% max - FOMO/Speculative
    """
    
    TIER_LIMITS: dict[PositionTier, dict[str, Any]] = {
        PositionTier.PRIMARY: {
            "max_pct": 10.0,
            "recommended_pct": 8.0,
            "yellow_allowed": True,
            "orange_allowed": True,  # But reduced
            "red_allowed": False,
            "description": "Core position - proven Gold Mine"
        },
        PositionTier.SECONDARY: {
            "max_pct": 5.0,
            "recommended_pct": 3.0,
            "yellow_allowed": True,
            "orange_allowed": False,
            "red_allowed": False,
            "description": "Unofficial - Great Find, dating"
        },
        PositionTier.TERTIARY: {
            "max_pct": 2.0,
            "recommended_pct": 1.0,
            "yellow_allowed": False,  # Ref: Minute 52:00
            "orange_allowed": False,
            "red_allowed": False,
            "description": "FOMO/Speculative - small bet"
        },
    }
    
    @classmethod
    def get_position_limit(
        cls,
        tier: PositionTier | str,
        ticker: str = ""
    ) -> PositionLimit:
        """
        Get position size limit for tier.
        
        Args:
            tier: Position tier
            ticker: Stock ticker
            
        Returns:
            PositionLimit with constraints
        """
        if isinstance(tier, str):
            tier = PositionTier(tier.upper())
        
        config = cls.TIER_LIMITS[tier]
        
        return PositionLimit(
            ticker=ticker,
            tier=tier,
            max_portfolio_pct=config["max_pct"],
            recommended_pct=config["recommended_pct"],
            allowed_in_yellow=config["yellow_allowed"],
            allowed_in_orange=config["orange_allowed"],
            allowed_in_red=config["red_allowed"],
            reasoning=config["description"]
        )
    
    @classmethod
    def determine_tier(
        cls,
        lifecycle_phase: LifecyclePhase,
        gomes_score: int,
        has_catalyst: bool = False
    ) -> PositionTier:
        """
        Determine appropriate tier based on stock characteristics.
        
        Ref: Minute 50:00 - How to size positions
        """
        # Gold Mine with high score = PRIMARY
        if lifecycle_phase == LifecyclePhase.GOLD_MINE and gomes_score >= 8:
            return PositionTier.PRIMARY
        
        # Great Find or decent Gold Mine = SECONDARY
        if lifecycle_phase == LifecyclePhase.GREAT_FIND:
            return PositionTier.SECONDARY
        if lifecycle_phase == LifecyclePhase.GOLD_MINE and gomes_score >= 6:
            return PositionTier.SECONDARY
        
        # Everything else = TERTIARY
        return PositionTier.TERTIARY
    
    @classmethod
    def adjust_for_market_alert(
        cls,
        limit: PositionLimit,
        market_alert: MarketAlert
    ) -> PositionLimit:
        """
        Adjust position limit based on market alert level.
        
        Ref: Minute 52:00 - "In Yellow, no speculative positions"
        """
        # Check if tier is allowed at this alert level
        if market_alert == MarketAlert.YELLOW and not limit.allowed_in_yellow:
            limit.max_portfolio_pct = 0.0
            limit.recommended_pct = 0.0
            limit.reasoning += " | BLOCKED: Yellow Alert - speculative not allowed"
        
        elif market_alert == MarketAlert.ORANGE and not limit.allowed_in_orange:
            limit.max_portfolio_pct = 0.0
            limit.recommended_pct = 0.0
            limit.reasoning += " | BLOCKED: Orange Alert - tier not allowed"
        
        elif market_alert == MarketAlert.RED:
            limit.max_portfolio_pct = 0.0
            limit.recommended_pct = 0.0
            limit.reasoning += " | BLOCKED: Red Alert - no new positions"
        
        elif market_alert == MarketAlert.ORANGE and limit.allowed_in_orange:
            # Reduce position size in orange
            limit.max_portfolio_pct *= 0.5
            limit.recommended_pct *= 0.5
            limit.reasoning += " | REDUCED: Orange Alert - 50% size"
        
        return limit


# ============================================================================
# 5. GOMES GATEKEEPER - Final Verdict Synthesizer
# ============================================================================

class GomesGatekeeper:
    """
    The GATEKEEPER - Final Investment Decision
    
    This class synthesizes all Gomes rules and returns a final verdict.
    If the Gatekeeper says NO, you don't invest. Period.
    
    Rules Applied:
    1. Market Alert constraints
    2. Lifecycle phase filter (WAIT_TIME = BLOCKED)
    3. Earnings 14-day rule
    4. Position tier + alert level constraints
    5. Price line analysis
    6. ML prediction integration
    7. Final Gomes score synthesis
    """
    
    EARNINGS_DANGER_DAYS = 14  # Ref: Minute 45:00 - "14 days before earnings = EXIT"
    
    def __init__(
        self,
        market_alert: MarketAlert = MarketAlert.GREEN,
        current_date: datetime | None = None
    ):
        self.market_alert = market_alert
        self.current_date = current_date or datetime.now()
    
    def evaluate(
        self,
        ticker: str,
        gomes_score: int,
        lifecycle_phase: LifecyclePhase | None = None,
        current_price: float | None = None,
        green_line: float | None = None,
        red_line: float | None = None,
        earnings_date: datetime | None = None,
        ml_prediction: dict[str, Any] | None = None,
        transcript_text: str | None = None,
        catalyst_info: dict[str, Any] | None = None
    ) -> GomesVerdict:
        """
        Evaluate investment and return final verdict.
        
        This is THE GATEKEEPER function. All rules are applied here.
        
        Args:
            ticker: Stock ticker
            gomes_score: Base Gomes score (0-10)
            lifecycle_phase: Stock lifecycle phase (or auto-detect)
            current_price: Current market price
            green_line: Buy zone price
            red_line: Sell zone price
            earnings_date: Next earnings date
            ml_prediction: ML prediction dict {"direction": "UP", "confidence": 0.85}
            transcript_text: Transcript for lifecycle detection
            catalyst_info: Catalyst info dict
            
        Returns:
            GomesVerdict with final decision
        """
        risk_factors: list[str] = []
        blocked_reason: str | None = None
        passed_filter = True
        adjusted_score = gomes_score
        
        # =====================================================================
        # RULE 1: Lifecycle Phase Filter (WAIT_TIME = BLOCKED)
        # Ref: Minute 31:28 - "Wait Time is the KILLER"
        # =====================================================================
        
        if lifecycle_phase is None and transcript_text:
            assessment = StockLifecycleClassifier.classify(ticker, transcript_text)
            lifecycle_phase = assessment.phase
        
        lifecycle_phase = lifecycle_phase or LifecyclePhase.UNKNOWN
        
        if lifecycle_phase == LifecyclePhase.WAIT_TIME:
            passed_filter = False
            blocked_reason = "WAIT_TIME phase - Dead Money (Gomes Rule)"
            risk_factors.append("🚫 BLOCKED: Wait Time phase - do not invest")
        
        # =====================================================================
        # RULE 2: Earnings 14-Day Rule
        # Ref: Minute 45:00 - "Never hold through earnings"
        # =====================================================================
        
        days_to_earnings: int | None = None
        
        if earnings_date:
            days_to_earnings = (earnings_date - self.current_date).days
            
            if days_to_earnings <= self.EARNINGS_DANGER_DAYS:
                if days_to_earnings <= 0:
                    passed_filter = False
                    blocked_reason = f"Earnings TODAY or PASSED - DO NOT ENTER"
                    risk_factors.append(f"🚫 BLOCKED: Earnings in {days_to_earnings} days")
                else:
                    # Penalty but not blocked (unless < 7 days)
                    adjusted_score = max(0, adjusted_score - 3)
                    risk_factors.append(f"⚠️ Earnings in {days_to_earnings} days - HIGH RISK")
                    
                    if days_to_earnings < 7:
                        passed_filter = False
                        blocked_reason = f"Earnings too close ({days_to_earnings} days)"
        
        # =====================================================================
        # RULE 3: Market Alert Constraints
        # Ref: Minute 15:00-18:00 - Market Alert System
        # =====================================================================
        
        if self.market_alert == MarketAlert.RED:
            passed_filter = False
            blocked_reason = "RED ALERT - No new positions allowed"
            risk_factors.append("🔴 BLOCKED: Red Alert - full defensive mode")
        
        # =====================================================================
        # RULE 4: Position Tier + Market Alert
        # =====================================================================
        
        position_tier = PositionSizingEngine.determine_tier(
            lifecycle_phase=lifecycle_phase,
            gomes_score=adjusted_score,
            has_catalyst=bool(catalyst_info and catalyst_info.get("has_catalyst"))
        )
        
        position_limit = PositionSizingEngine.get_position_limit(position_tier, ticker)
        position_limit = PositionSizingEngine.adjust_for_market_alert(
            position_limit, self.market_alert
        )
        
        if position_limit.max_portfolio_pct == 0:
            # Position not allowed at this alert level
            if passed_filter:  # Don't override stronger blocks
                passed_filter = False
                blocked_reason = f"{position_tier.value} tier blocked at {self.market_alert.value} alert"
            risk_factors.append(f"⚠️ {position_tier.value} positions not allowed in {self.market_alert.value}")
        
        # =====================================================================
        # RULE 5: Price Line Analysis
        # =====================================================================
        
        price_zone = "UNKNOWN"
        if current_price is not None:
            zone, zone_reason = RiskRewardCalculator.get_action_zone(
                current_price, green_line, red_line
            )
            price_zone = zone
            
            if zone == "SELL" and passed_filter:
                # Price above red line - don't buy
                adjusted_score = max(0, adjusted_score - 2)
                risk_factors.append(f"📈 {zone_reason}")
            elif zone == "BUY":
                adjusted_score = min(10, adjusted_score + 1)
        
        # =====================================================================
        # RULE 6: ML Prediction Integration
        # =====================================================================
        
        ml_direction: str | None = None
        ml_confidence: float | None = None
        
        if ml_prediction:
            ml_direction = ml_prediction.get("direction", ml_prediction.get("prediction_type"))
            ml_confidence = ml_prediction.get("confidence", ml_prediction.get("score"))
            
            if ml_direction == "DOWN" and ml_confidence and ml_confidence > 0.7:
                risk_factors.append(f"📉 ML predicts DOWN with {ml_confidence*100:.0f}% confidence")
                adjusted_score = max(0, adjusted_score - 1)
            elif ml_direction == "UP" and ml_confidence and ml_confidence > 0.7:
                adjusted_score = min(10, adjusted_score + 1)
        
        # =====================================================================
        # FINAL VERDICT DETERMINATION
        # =====================================================================
        
        if not passed_filter:
            verdict = InvestmentVerdict.BLOCKED
        elif adjusted_score >= 9:
            verdict = InvestmentVerdict.STRONG_BUY
        elif adjusted_score >= 7:
            verdict = InvestmentVerdict.BUY
        elif adjusted_score >= 5:
            if price_zone == "BUY":
                verdict = InvestmentVerdict.ACCUMULATE
            else:
                verdict = InvestmentVerdict.HOLD
        elif adjusted_score >= 3:
            verdict = InvestmentVerdict.AVOID
        else:
            verdict = InvestmentVerdict.AVOID
        
        # Catalyst info
        has_catalyst = bool(catalyst_info and catalyst_info.get("has_catalyst"))
        catalyst_type = catalyst_info.get("type") if catalyst_info else None
        catalyst_desc = catalyst_info.get("description") if catalyst_info else None
        
        # Build reasoning
        reasoning_parts = []
        reasoning_parts.append(f"Gomes Score: {adjusted_score}/10 (original: {gomes_score})")
        reasoning_parts.append(f"Phase: {lifecycle_phase.value}")
        reasoning_parts.append(f"Market: {self.market_alert.value}")
        reasoning_parts.append(f"Tier: {position_tier.value} (max {position_limit.max_portfolio_pct}%)")
        
        if green_line:
            reasoning_parts.append(f"Green Line: ${green_line:.2f}")
        if red_line:
            reasoning_parts.append(f"Red Line: ${red_line:.2f}")
        if current_price:
            reasoning_parts.append(f"Current: ${current_price:.2f} ({price_zone})")
        
        reasoning = " | ".join(reasoning_parts)
        
        # Confidence based on data availability
        confidence = "HIGH" if all([
            lifecycle_phase != LifecyclePhase.UNKNOWN,
            green_line is not None,
            ml_prediction is not None
        ]) else "MEDIUM" if ml_prediction or green_line else "LOW"
        
        return GomesVerdict(
            ticker=ticker,
            verdict=verdict,
            passed_gomes_filter=passed_filter,
            blocked_reason=blocked_reason,
            gomes_score=adjusted_score,
            ml_prediction_score=ml_confidence * 100 if ml_confidence else None,
            ml_direction=ml_direction,
            lifecycle_phase=lifecycle_phase,
            market_alert=self.market_alert,
            position_tier=position_tier,
            max_position_pct=position_limit.max_portfolio_pct,
            current_price=current_price,
            green_line=green_line,
            red_line=red_line,
            risk_factors=risk_factors,
            days_to_earnings=days_to_earnings,
            has_catalyst=has_catalyst,
            catalyst_type=catalyst_type,
            catalyst_description=catalyst_desc,
            confidence=confidence,
            reasoning=reasoning
        )


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

def quick_gomes_check(
    ticker: str,
    gomes_score: int,
    lifecycle_phase: str | None = None,
    market_alert: str = "GREEN",
    days_to_earnings: int | None = None
) -> tuple[bool, str]:
    """
    Quick pass/fail Gomes check.
    
    Returns:
        (passed: bool, reason: str)
    """
    gatekeeper = GomesGatekeeper(
        market_alert=MarketAlert(market_alert.upper())
    )
    
    earnings_date = None
    if days_to_earnings is not None:
        earnings_date = datetime.now() + timedelta(days=days_to_earnings)
    
    phase = LifecyclePhase(lifecycle_phase.upper()) if lifecycle_phase else None
    
    verdict = gatekeeper.evaluate(
        ticker=ticker,
        gomes_score=gomes_score,
        lifecycle_phase=phase,
        earnings_date=earnings_date
    )
    
    return verdict.passed_gomes_filter, verdict.blocked_reason or verdict.verdict.value
