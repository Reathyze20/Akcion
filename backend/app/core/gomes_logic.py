"""
Gomes Logic Core - The Algorithm Layer
======================================

This module contains HARD-CODED business logic for Mark Gomes' investment framework.
AI must NEVER override these rules - they are safety constraints.

Key Principles:
1. Max allocation is dynamically calculated based on risk
2. Action signals are deterministic (no AI interpretation)
3. Cash runway is the primary survival metric
4. Conviction Score is AI-generated but rules are code-enforced

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
    conviction_score: Optional[int] = None  # 0-10
    
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
# WHERE THE ENGINE WENT
# ============================================================================
#
# `GomesLogicEngine` stood here: a second set of verdicts (HARD_EXIT / SELL /
# TRIM / HOLD / ACCUMULATE / SNIPER) over the same holdings the band engine
# judges, reached through `GET /api/gomes/analyze-position/{ticker}`. Its rule 5
# was unreachable and rule 4 always fired first, so what it actually published
# was a shorter, older answer competing with the real one.
#
# One thing inside it was real and had no equivalent anywhere else: `BASE_CAPS`,
# which sizes a position by **what kind of bet it is** rather than by how sure
# the thesis is. That axis now lives in `app/services/asset_class_caps.py`,
# where a missing class imposes no ceiling instead of quietly defaulting to
# HIGH_BETA_ROCKET's 8 %.
#
# The enums above stay: `gomes_ai_analyst` types its output with them, and
# `stocks.asset_class` stores their values.


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
