"""
Gomes Logic Core - The Algorithm Layer
======================================

This module contains HARD-CODED business logic for Mark Gomes' investment framework.
AI must NEVER override these rules - they are safety constraints.

Key Principles:
1. Max allocation is dynamically calculated based on risk
2. Action signals are deterministic (no AI interpretation)
3. Cash runway is the primary survival metric
4. Gomes Score is AI-generated but rules are code-enforced

Author: GitHub Copilot with Claude Sonnet 4.5
Date: 2026-01-25
"""

from enum import Enum
from typing import Optional
from pydantic import BaseModel


# ============================================================================
# ENUMS - Type Definitions
# ============================================================================

class AssetClass(str, Enum):
    """Asset classification per Gomes framework"""
    ANCHOR = "ANCHOR"  # Stable grower (GSI) - Compounders
    HIGH_BETA_ROCKET = "HIGH_BETA_ROCKET"  # Miners, leveraged plays (KUYA)
    BIOTECH_BINARY = "BIOTECH_BINARY"  # Binary outcomes (IMP)
    TURNAROUND = "TURNAROUND"  # Recovery plays
    VALUE_TRAP = "VALUE_TRAP"  # Avoid these


class InflectionStatus(str, Enum):
    """Business lifecycle stage"""
    WAIT_TIME = "WAIT_TIME"  # 🔴 Past peak or pre-inflection
    UPCOMING = "UPCOMING"  # 🟡 Catalyst approaching
    ACTIVE_GOLD_MINE = "ACTIVE_GOLD_MINE"  # 🟢 Generating cash


class ValuationStage(str, Enum):
    """Price relative to target"""
    UNDERVALUED = "UNDERVALUED"  # <50% of target
    FAIR = "FAIR"  # 50-100% of target
    OVERVALUED = "OVERVALUED"  # 100-150% of target
    BUBBLE = "BUBBLE"  # >150% of target


class ActionSignal(str, Enum):
    """Investment action recommendation"""
    HARD_EXIT = "HARD_EXIT"  # Thesis broken, sell immediately
    SELL = "SELL"  # Overvalued or risk too high
    TRIM = "TRIM"  # Reduce position (over-allocated)
    HOLD = "HOLD"  # Fair value, maintain position
    ACCUMULATE = "ACCUMULATE"  # Undervalued, high quality
    SNIPER = "SNIPER"  # Perfect setup, load the boat


# ============================================================================
# DATA MODELS
# ============================================================================

class StockMetrics(BaseModel):
    """Input metrics for Gomes Logic calculations"""
    
    # Identity
    ticker: str
    asset_class: AssetClass
    
    # Quality Score (AI-generated)
    gomes_score: Optional[int] = None  # 0-10
    
    # Financial Fortress
    cash_runway_months: Optional[int] = None
    insider_ownership_pct: Optional[float] = None
    
    # Inflection
    inflection_status: Optional[InflectionStatus] = None
    
    # Valuation
    current_price: float
    price_floor: Optional[float] = None
    price_target_24m: Optional[float] = None
    
    # Position
    current_weight_pct: float  # Current % in portfolio


class GomesDecision(BaseModel):
    """Output from Gomes Logic"""
    
    # Allocation Control
    max_allocation_cap: float  # Dynamically calculated max %
    recommended_weight_pct: float  # Where position should be
    
    # Action
    action_signal: ActionSignal
    action_reason: str
    
    # Warnings
    warnings: list[str]
    is_safe_to_buy: bool


# ============================================================================
# CORE ALGORITHMS
# ============================================================================

class GomesLogicEngine:
    """
    The brain of Gomes Guardian.
    
    These rules are FIXED and tested. AI provides inputs (scores, metrics)
    but cannot override the logic.
    """
    
    @staticmethod
    def calculate_max_allocation(
        asset_class: AssetClass,
        gomes_score: Optional[int],
        cash_runway_months: Optional[int],
        inflection_status: Optional[InflectionStatus]
    ) -> float:
        """
        Calculate maximum safe allocation for a stock.
        
        Formula:
        1. Base cap from asset class (risk profile)
        2. Safety multiplier from quality metrics
        3. Final cap = Base × Safety
        
        Returns:
            Maximum portfolio allocation percentage (0-100)
        """
        
        # Step 1: Base cap by asset class
        BASE_CAPS = {
            AssetClass.ANCHOR: 12.0,  # Stable compounders
            AssetClass.HIGH_BETA_ROCKET: 8.0,  # Miners, leveraged
            AssetClass.BIOTECH_BINARY: 3.0,  # Binary outcomes
            AssetClass.TURNAROUND: 2.0,  # Recovery plays
            AssetClass.VALUE_TRAP: 0.0,  # Never buy
        }
        
        base_cap = BASE_CAPS.get(asset_class, 5.0)  # Default 5%
        
        # Step 2: Safety multiplier (quality penalties)
        safety_multiplier = 1.0
        
        # Quality penalty
        if gomes_score is not None and gomes_score < 7:
            safety_multiplier *= 0.5  # Cut allocation in half for low quality
        
        # Survival penalty (CRITICAL)
        if cash_runway_months is not None:
            if cash_runway_months < 6:
                # Company may not survive - STOP BUYING
                safety_multiplier = 0.0
            elif cash_runway_months < 12:
                # Risky - reduce allocation
                safety_multiplier *= 0.7
        
        # Inflection bonus (reward active producers)
        if inflection_status == InflectionStatus.ACTIVE_GOLD_MINE:
            safety_multiplier *= 1.2  # Can hold slightly more of cash generators
        
        # Step 3: Final calculation
        final_cap = base_cap * safety_multiplier
        
        return round(final_cap, 2)
    
    @staticmethod
    def determine_action_signal(
        current_price: float,
        price_target_24m: Optional[float],
        price_floor: Optional[float],
        gomes_score: Optional[int],
        cash_runway_months: Optional[int],
        inflection_status: Optional[InflectionStatus],
        current_weight_pct: float,
        max_allocation_cap: float
    ) -> tuple[ActionSignal, str]:
        """
        Determine investment action recommendation.
        
        Logic flows from most critical (exit) to opportunistic (buy).
        
        Returns:
            (ActionSignal, reason_string)
        """
        
        # Rule 1: HARD EXIT - Thesis Broken
        if gomes_score is not None and gomes_score < 4:
            return ActionSignal.HARD_EXIT, "Thesis Broken (Score < 4/10)"
        
        # Rule 2: SELL - Insolvency Risk
        if (cash_runway_months is not None and 
            cash_runway_months < 6 and 
            inflection_status != InflectionStatus.ACTIVE_GOLD_MINE):
            return ActionSignal.SELL, "Insolvency Risk (Cash runway < 6 months)"
        
        # Rule 3: TRIM - Over-Allocated
        if current_weight_pct > max_allocation_cap:
            return ActionSignal.TRIM, f"Overweight ({current_weight_pct:.1f}% > {max_allocation_cap:.1f}% limit)"
        
        # Rule 4: HOLD/SELL - Upside Realized
        if price_target_24m is not None and current_price > price_target_24m:
            return ActionSignal.HOLD, "Target Price Achieved - Consider Profits"
        
        # Rule 5: SELL - Bubble Territory
        if price_target_24m is not None and current_price > price_target_24m * 1.5:
            return ActionSignal.SELL, "Bubble Territory (>150% of target)"
        
        # Rule 6: SNIPER - Perfect Setup
        if (gomes_score is not None and gomes_score >= 9 and
            cash_runway_months is not None and cash_runway_months >= 18 and
            price_floor is not None and current_price <= price_floor * 1.2):
            return ActionSignal.SNIPER, "Perfect Setup: High quality + Safe + Cheap"
        
        # Rule 7: ACCUMULATE - Quality at Discount
        if (gomes_score is not None and gomes_score >= 7 and
            price_target_24m is not None and current_price < price_target_24m * 0.7):
            return ActionSignal.ACCUMULATE, "Quality at Discount (>30% upside)"
        
        # Default: HOLD
        return ActionSignal.HOLD, "Fair Value - Maintain Position"
    
    @staticmethod
    def generate_warnings(
        gomes_score: Optional[int],
        cash_runway_months: Optional[int],
        insider_ownership_pct: Optional[float],
        current_weight_pct: float,
        max_allocation_cap: float
    ) -> list[str]:
        """Generate risk warnings for UI display"""
        
        warnings = []
        
        # Quality warnings
        if gomes_score is not None:
            if gomes_score < 5:
                warnings.append("⚠️ Low Quality Score - High Risk")
            elif gomes_score < 7:
                warnings.append("⚠️ Below Target Quality (< 7/10)")
        
        # Survival warnings
        if cash_runway_months is not None:
            if cash_runway_months < 6:
                warnings.append("🔴 CRITICAL: Cash runway < 6 months - Bankruptcy risk!")
            elif cash_runway_months < 12:
                warnings.append("🟡 WARNING: Cash runway < 12 months - Dilution likely")
        
        # Insider alignment
        if insider_ownership_pct is not None and insider_ownership_pct < 5.0:
            warnings.append("⚠️ Low Insider Ownership (< 5%) - Weak skin in game")
        
        # Position size
        if current_weight_pct > max_allocation_cap:
            warnings.append(f"🔴 Over-Allocated: {current_weight_pct:.1f}% > {max_allocation_cap:.1f}% limit")
        
        return warnings
    
    @classmethod
    def execute(cls, metrics: StockMetrics) -> GomesDecision:
        """
        Main entry point - execute full Gomes Logic analysis.
        
        This is what gets called from API endpoints.
        """
        
        # Step 1: Calculate max safe allocation
        max_allocation_cap = cls.calculate_max_allocation(
            asset_class=metrics.asset_class,
            gomes_score=metrics.gomes_score,
            cash_runway_months=metrics.cash_runway_months,
            inflection_status=metrics.inflection_status
        )
        
        # Step 2: Determine action signal
        action_signal, action_reason = cls.determine_action_signal(
            current_price=metrics.current_price,
            price_target_24m=metrics.price_target_24m,
            price_floor=metrics.price_floor,
            gomes_score=metrics.gomes_score,
            cash_runway_months=metrics.cash_runway_months,
            inflection_status=metrics.inflection_status,
            current_weight_pct=metrics.current_weight_pct,
            max_allocation_cap=max_allocation_cap
        )
        
        # Step 3: Generate warnings
        warnings = cls.generate_warnings(
            gomes_score=metrics.gomes_score,
            cash_runway_months=metrics.cash_runway_months,
            insider_ownership_pct=metrics.insider_ownership_pct,
            current_weight_pct=metrics.current_weight_pct,
            max_allocation_cap=max_allocation_cap
        )
        
        # Step 4: Calculate recommended weight
        if action_signal in [ActionSignal.HARD_EXIT, ActionSignal.SELL]:
            recommended_weight = 0.0
        elif action_signal == ActionSignal.TRIM:
            recommended_weight = max_allocation_cap
        elif action_signal in [ActionSignal.ACCUMULATE, ActionSignal.SNIPER]:
            recommended_weight = max_allocation_cap  # Fill to cap
        else:
            recommended_weight = metrics.current_weight_pct  # Hold current
        
        # Step 5: Safety check
        is_safe_to_buy = (
            action_signal not in [ActionSignal.HARD_EXIT, ActionSignal.SELL, ActionSignal.TRIM] and
            max_allocation_cap > 0 and
            (metrics.cash_runway_months is None or metrics.cash_runway_months >= 6)
        )
        
        return GomesDecision(
            max_allocation_cap=max_allocation_cap,
            recommended_weight_pct=recommended_weight,
            action_signal=action_signal,
            action_reason=action_reason,
            warnings=warnings,
            is_safe_to_buy=is_safe_to_buy
        )


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def calculate_valuation_stage(
    current_price: float,
    price_target_24m: Optional[float]
) -> ValuationStage:
    """Determine valuation stage based on price vs target"""
    
    if price_target_24m is None:
        return ValuationStage.FAIR  # Unknown
    
    ratio = current_price / price_target_24m
    
    if ratio < 0.5:
        return ValuationStage.UNDERVALUED
    elif ratio < 1.0:
        return ValuationStage.FAIR
    elif ratio < 1.5:
        return ValuationStage.OVERVALUED
    else:
        return ValuationStage.BUBBLE


def calculate_upside_potential(
    current_price: float,
    price_target: Optional[float]
) -> Optional[float]:
    """Calculate upside percentage to target"""
    
    if price_target is None or price_target <= 0:
        return None
    
    return ((price_target / current_price) - 1) * 100


# ============================================================================
# EXAMPLE USAGE
# ============================================================================

if __name__ == "__main__":
    # Test case: KUYA Silver
    kuya_metrics = StockMetrics(
        ticker="KUYA.V",
        asset_class=AssetClass.HIGH_BETA_ROCKET,
        gomes_score=9,
        cash_runway_months=24,
        insider_ownership_pct=15.0,
        inflection_status=InflectionStatus.ACTIVE_GOLD_MINE,
        current_price=0.65,
        price_floor=0.45,
        price_target_24m=1.80,
        current_weight_pct=11.2
    )
    
    decision = GomesLogicEngine.execute(kuya_metrics)
    
    print("="*60)
    print(f"Gomes Logic Decision for {kuya_metrics.ticker}")
    print("="*60)
    print(f"Max Allocation Cap: {decision.max_allocation_cap}%")
    print(f"Recommended Weight: {decision.recommended_weight_pct}%")
    print(f"Action: {decision.action_signal.value}")
    print(f"Reason: {decision.action_reason}")
    print(f"Safe to Buy: {decision.is_safe_to_buy}")
    if decision.warnings:
        print("\nWarnings:")
        for warning in decision.warnings:
            print(f"  {warning}")
