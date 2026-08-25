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

from app.core.czech import d as cz_date
from app.core.czech import n as cz

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field

# The ratchet lives with the rest of the pure stage rules. Importing it here
# rather than re-implementing keeps one definition of "Gold Mine is absorbing";
# `lifecycle_rubric` depends on nothing in this module, so there is no cycle.
from app.services.lifecycle_rubric import apply_ratchet


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
    STRONG_BUY = "STRONG_BUY"  # Conviction Score 9-10, all filters pass
    BUY = "BUY"                # Conviction Score 7-8
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
    #: A Wait Time reading on a company already proven to be a Gold Mine.
    #: Not a phase — see GOMES_VIDEO_ADDENDUM.md §V1.
    rough_patch: bool = False


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
    conviction_score: int = 0  # 0-10
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
    def _sentences_about(
        cls, ticker: str, text: str, aliases: Sequence[str]
    ) -> list[str]:
        """
        The sentences that actually name this company.

        A Gomes stream covers forty tickers in two hours. Searching the whole
        document for a phrase and attributing the hit to whichever ticker the
        caller happened to pass in is not evidence about that company — it is
        evidence that someone said the words. Scope first, then count.
        """
        names = {n.lower() for n in (ticker, *aliases) if n and len(n) >= 2}
        if not names:
            return []
        pattern = re.compile(
            r"\b(" + "|".join(re.escape(n) for n in sorted(names)) + r")\b"
        )
        return [
            sentence
            for sentence in re.split(r"(?<=[.!?])\s+|\n", text)
            if pattern.search(sentence.lower())
        ]

    @classmethod
    def classify(
        cls,
        ticker: str,
        text: str | None = None,
        *,
        aliases: Sequence[str] = (),
        reached: LifecyclePhase | str | None = None,
    ) -> LifecycleAssessment:
        """
        Classify stock into lifecycle phase from text that mentions it.

        Args:
            ticker: Stock ticker.
            text: Transcript or analysis text. May cover many companies.
            aliases: Other ways this company is named in speech — Gomes says
                "gatekeeper", never "GKPRF". Without them a transcript that
                never spells the ticker yields UNKNOWN, which is the safe
                answer, not a wrong one.
            reached: The furthest stage this company has ever reached, from
                `stock_lifecycle.phase_reached`. Without it this method is
                memoryless and will demote a proven Gold Mine to Wait Time the
                first time somebody says "delays" — see below.

        Cylinders are deliberately NOT inferred here; see below.

        Ref: canon §3, GOMES_VIDEO_ADDENDUM.md §V1.
        """
        signals: dict[str, bool] = {}
        scoped = cls._sentences_about(ticker, text or "", aliases)
        haystack = " ".join(scoped).lower()

        def count(kind: str, phrases: list[str]) -> int:
            hits = 0
            for phrase in phrases:
                if phrase in haystack:
                    signals[f"{kind}:{phrase}"] = True
                    hits += 1
            return hits

        # WAIT_TIME first — it is the one that blocks money.
        wait_time_count = count("wait_time", cls.WAIT_TIME_SIGNALS)
        gold_mine_count = count("gold_mine", cls.GOLD_MINE_SIGNALS)
        great_find_count = count("great_find", cls.GREAT_FIND_SIGNALS)

        phase = LifecyclePhase.UNKNOWN
        is_investable = True
        reasoning = ""
        confidence = "LOW"

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

        elif not text:
            reasoning = "No text provided for analysis"
        elif not scoped:
            reasoning = f"Text does not mention {ticker} - nothing to judge it on"
        else:
            reasoning = "Insufficient signals to determine phase"

        # Cylinders (0-10) are NOT derived here, on purpose.
        #
        # This method used to search the whole document for "10 cylinders" and
        # record ten if it appeared, five if the word "problems" did. Run over
        # a real two-hour Gomes stream that produced ten cylinders and
        # GOLD_MINE for ITMSF, because the phrase had been said about WATT's
        # chart and about GateKeeper. Ten cylinders means a deserved score of
        # zero, which lets almost any beaten-down price clear the Buy Guard.
        #
        # Scoping the search to sentences naming the company is necessary but
        # still not sufficient: this very transcript says "I think Watt is
        # executing on MORE THAN one cylinder", and a count lifted out of that
        # is wrong in a way that spends money. A cylinder count is a judgement
        # about a business, not a substring, and it reaches the database only
        # through claim extraction with a verified quote behind it.
        #
        # Unknown cylinders make the Buy Guard refuse to emit BUY. Failing
        # closed is the correct behaviour here.
        #
        # The ratchet (§V1) runs last, over whatever the keywords voted for.
        # It matters most exactly here: WAIT_TIME_SIGNALS above is the
        # vocabulary of a rough patch — "delays", "missed guidance",
        # "lawsuit", "cfo left" — and Gomes is explicit that a proven company
        # saying those things has not gone back to Wait Time. Without a
        # high-water mark to compare against, this method has no way to know
        # the difference, so `reached` is what makes the distinction possible
        # and its absence leaves the old behaviour untouched.
        rough_patch = False
        if reached is not None:
            mark = reached.value if isinstance(reached, LifecyclePhase) else str(reached)
            result = apply_ratchet(phase.value, mark.upper())
            if result.changed:
                phase = LifecyclePhase(result.phase)
                rough_patch = result.rough_patch
                is_investable = cls.is_investable(phase)
                reasoning = f"{reasoning}. {result.held_back_cs}".lstrip(". ")

        return LifecycleAssessment(
            ticker=ticker,
            phase=phase,
            is_investable=is_investable,
            firing_on_all_cylinders=None,
            cylinders_count=None,
            signals=signals,
            reasoning=reasoning,
            confidence=confidence,
            rough_patch=rough_patch,
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
    
    # Score points around the deserved level before flipping BUY/SELL.
    # A deadband avoids flip-flapping when the price sits right at fair value.
    RR_DEADBAND: float = 0.5

    @classmethod
    def calculate_rr_score(
        cls,
        current_price: float | None,
        low: float | None,
        high: float | None,
        top_score: int = 0,
    ) -> float | None:
        """
        Gomes Risk/Reward score — LOGARITHMIC.

        Ref: GOMES_METHODOLOGY_CANON.md §4a. Formula verified against the live
        riskrewardcharts.com tracker (e.g. CXDO 3.25/15.50/6.62 -> 5.45).

            score = top_score + (10 - top_score) * log(high / price) / log(high / low)

        `low` = Green Line (buy zone), `high` = Red Line (sell zone).
        Returns 10 at/below the Green Line (cheapest, best buy) and `top_score`
        (0 or 1) at/above the Red Line (full value / sell). Result is capped to
        [top_score, 10].

        Returns None on invalid input (missing/non-positive prices, or high <= low)
        so callers fail safe instead of rendering a fabricated number.
        """
        if current_price is None or low is None or high is None:
            return None
        if current_price <= 0 or low <= 0 or high <= 0:
            return None
        if high <= low:
            return None  # inverted or degenerate lines -> no meaningful score

        span = math.log(high / low)
        raw = top_score + (10 - top_score) * math.log(high / current_price) / span
        return max(float(top_score), min(10.0, raw))

    @classmethod
    def deserved_score(cls, cylinders: int | float | None) -> float | None:
        """
        Deserved R/R score given operating "cylinders" (0-10 = operational health).

        Ref: canon §4b. Gomes: a stock only deserves the Red Line (full value) when
        the company fires on all 10 cylinders; at 5 cylinders it deserves the
        midpoint, at 1 cylinder it deserves to sit near the Green Line. On the R/R
        scale (10 = Green, 0 = Red) this is simply `10 - cylinders`.

        Returns None when cylinders are unknown.
        """
        if cylinders is None:
            return None
        c = max(0.0, min(10.0, float(cylinders)))
        return 10.0 - c

    @classmethod
    def decide_from_score(
        cls,
        score: float | None,
        cylinders: int | float | None,
    ) -> tuple[str, str]:
        """
        Full Gomes buy/sell decision: compare R/R score to deserved (10 - cylinders).

        BUY  when score > deserved + deadband (cheap for its operational quality)
        SELL when score < deserved - deadband (expensive for its quality)
        HOLD otherwise.

        When cylinders are unknown, refuse to emit BUY (returns WATCH) — buying on
        price alone, without knowing operational quality, is how you fall into a
        Wait-Time value trap.
        """
        if score is None:
            return "UNKNOWN", "Chybí platná data pro R/R skóre"

        if cylinders is None:
            return "WATCH", (
                f"R/R skóre {cz(score, 2)}/10, ale chybí kvalita firmy (válce) "
                f"— nekupovat naslepo"
            )

        deserved = cls.deserved_score(cylinders)
        c = max(0, min(10, int(cylinders)))
        detail = f"zasloužené {cz(deserved, 1)} (10 − {c} válců)"

        if score > deserved + cls.RR_DEADBAND:
            return "BUY", f"R/R skóre {cz(score, 2)} > {detail} — levné vzhledem ke kvalitě"
        if score < deserved - cls.RR_DEADBAND:
            return "SELL", f"R/R skóre {cz(score, 2)} < {detail} — drahé vzhledem ke kvalitě"
        return "HOLD", f"R/R skóre {cz(score, 2)} ≈ {detail}"

    @classmethod
    def decide(
        cls,
        current_price: float | None,
        low: float | None,
        high: float | None,
        cylinders: int | float | None = None,
        top_score: int = 0,
    ) -> tuple[str, str]:
        """Convenience: compute log R/R score from prices, then decide vs cylinders."""
        score = cls.calculate_rr_score(current_price, low, high, top_score)
        return cls.decide_from_score(score, cylinders)

    @classmethod
    def three_point_up(
        cls,
        current_price: float,
        low: float,
        high: float,
        top_score: int = 0,
    ) -> float | None:
        """
        Price at which the R/R score drops 3 points (a take-profit trigger).

        Ref: canon §5.  3pt up = price * (high / low) ** (3 / (10 - top_score))
        """
        if current_price <= 0 or low <= 0 or high <= 0 or high <= low:
            return None
        return current_price * (high / low) ** (3 / (10 - top_score))

    @classmethod
    def three_point_down(
        cls,
        current_price: float,
        low: float,
        high: float,
        top_score: int = 0,
    ) -> float | None:
        """
        Price at which the R/R score rises 3 points (an add / accumulate trigger).

        Ref: canon §5.  3pt down = price / (high / low) ** (3 / (10 - top_score))
        """
        if current_price <= 0 or low <= 0 or high <= 0 or high <= low:
            return None
        return current_price / (high / low) ** (3 / (10 - top_score))

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
            return True, f"DOUBLING RULE: +{cz(gain_pct, 1)}% gain. Sell half, play with house money."
        elif gain_pct >= 75:
            return False, f"Approaching double: +{cz(gain_pct, 1)}%. Consider partial profit."
        else:
            return False, f"Current gain: +{cz(gain_pct, 1)}%"
    
    @classmethod
    def get_action_zone(
        cls,
        current_price: float | None,
        green_line: float | None,
        red_line: float | None
    ) -> tuple[str, str]:
        """
        Determine price-only action zone from the LOGARITHMIC R/R score.

        This is a price-position signal (no operational-quality/cylinders input);
        the Gatekeeper still gates it with market alert, lifecycle, etc. Uses a
        neutral midpoint of 5 (as if the company operates at ~5 cylinders).

        Ref: canon §4a. Replaces the old linear 30/70 band, which was
        mathematically wrong for a log-scaled score.

        Returns:
            (zone: "BUY"/"HOLD"/"SELL"/"UNKNOWN", reason)
        """
        if current_price is None:
            return "UNKNOWN", "Current price not available"

        score = cls.calculate_rr_score(current_price, green_line, red_line)

        if score is None:
            # Lines missing/degenerate: fall back to simple cap checks so we still
            # give a signal when only one line is known, and never fabricate.
            if green_line is not None and current_price < green_line:
                return "BUY", "Below Green Line (undervalued)"
            if red_line is not None and current_price > red_line:
                return "SELL", "Above Red Line (overvalued)"
            return "HOLD", "Insufficient line data"

        # Neutral midpoint 5 +/- deadband on the 0-10 log R/R scale.
        if score >= 5 + cls.RR_DEADBAND:
            return "BUY", f"R/R score {cz(score, 1)}/10 (toward Green Line, undervalued)"
        if score <= 5 - cls.RR_DEADBAND:
            return "SELL", f"R/R score {cz(score, 1)}/10 (toward Red Line, overvalued)"
        return "HOLD", f"R/R score {cz(score, 1)}/10 (near fair value)"


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

    Those are CEILINGS, not targets. What a name is actually worth inside its
    ceiling is `target_pct`, which scales with the R/R score — see §V2. The
    `recommended_pct` values below are kept only for the informational endpoint
    that shows a tier's shape before any company is scored; nothing sizes a
    real purchase from them.
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
    
    #: Below this score, in a market that is not GREEN, a holding is not
    #: trimmed towards a smaller weight — it goes to nothing.
    #:
    #: §V2, and it is Gomes' own number, not a threshold chosen here: "When a
    #: stock is up here, I'm liable to own zero or 1% of it in my portfolio.
    #: Especially in a yellow alert — zero. Why should I own a stock that's
    #: fully valued in a market that's likely to go down? There's no upside in
    #: that. High risk, low reward."
    FULL_VALUE_SCORE: float = 1.0

    @classmethod
    def target_pct(
        cls,
        ceiling_pct: float,
        rr_score: float | None,
        *,
        market_alert: MarketAlert | str | None = None,
    ) -> float:
        """
        How much of the portfolio this name is worth RIGHT NOW, inside its cap.

        GOMES_VIDEO_ADDENDUM.md §V2. The tier is a CEILING; the R/R score is the
        dial. Gomes states both ends of it with numbers:

            "Why would you put the same amount of money in a stock that's here
             as a stock that is way up here? When a stock is up here, I'm liable
             to own zero or 1% of it in my portfolio. When it's here, a 10 on
             the scale, I'm more liable to own 10% of that stock."

        And he rejects the flat alternative outright: "a lot of people say,
        well, I'm just going to put 10,000 in this stock, 10,000 in that stock
        — that defeats the purpose."

        Until this existed, `recommended_pct` was a constant per tier, so a
        PRIMARY at a score of 5 was sized exactly like a PRIMARY at 10. Every
        ceiling the app already applies still applies: pass the SMALLEST one
        (tier ∩ asset class ∩ dual-source agreement) as `ceiling_pct` and this
        only ever scales down from it.

        Args:
            ceiling_pct: The most this name may occupy, after every cap.
            rr_score: Today's log R/R score, 0-10. None means the score could
                not be computed, and an unknown dial is not a full one — the
                answer is zero, the same way every other missing input in this
                module refuses rather than defaults.
            market_alert: When not GREEN, a fully valued name is worth nothing
                rather than a token slice.

        Returns:
            Target weight in percent of the portfolio, 0 <= result <= ceiling.
        """
        if ceiling_pct <= 0 or rr_score is None:
            return 0.0

        score = max(0.0, min(10.0, float(rr_score)))

        if market_alert is not None:
            level = (
                market_alert.value
                if isinstance(market_alert, MarketAlert)
                else str(market_alert).upper()
            )
            if level != MarketAlert.GREEN.value and score <= cls.FULL_VALUE_SCORE:
                return 0.0

        return min(ceiling_pct, ceiling_pct * score / 10.0)

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
        conviction_score: int,
        has_catalyst: bool = False
    ) -> PositionTier:
        """
        Determine appropriate tier based on stock characteristics.
        
        Ref: Minute 50:00 - How to size positions
        """
        # Gold Mine with high score = PRIMARY
        if lifecycle_phase == LifecyclePhase.GOLD_MINE and conviction_score >= 8:
            return PositionTier.PRIMARY
        
        # Great Find or decent Gold Mine = SECONDARY
        if lifecycle_phase == LifecyclePhase.GREAT_FIND:
            return PositionTier.SECONDARY
        if lifecycle_phase == LifecyclePhase.GOLD_MINE and conviction_score >= 6:
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

def _drop_tz(value: datetime) -> datetime:
    """
    A datetime comparable with any other, aware or not.

    The lifecycle columns are `TIMESTAMP WITH TIME ZONE` and the engine clock
    is naive. Comparing the two raises, and the first rough patch ever recorded
    would have taken the guard down with a TypeError — the same way the first
    cylinder confirmation once did in `daily_actions`.
    """
    return value.replace(tzinfo=None)


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
    7. Final Conviction Score synthesis
    """
    
    EARNINGS_DANGER_DAYS = 14  # Ref: Minute 45:00 - "14 days before earnings = EXIT"

    def __init__(
        self,
        market_alert: MarketAlert = MarketAlert.GREEN,
        current_date: datetime | None = None
    ):
        self.market_alert = market_alert
        self.current_date = current_date or datetime.now()

    class BuyGate(str, Enum):
        """
        Which condition refused the buy.

        A code rather than a sentence, because the refusals are recorded and
        read back later (`app/models/refused_buy.py`): grouping a year of them
        by cause has to be a GROUP BY, not a regex over prose that someone
        rewords. `PASSED` is included so the caller never has to test for the
        absence of a gate.
        """

        PASSED = "PASSED"
        ALERT_UNKNOWN = "ALERT_UNKNOWN"
        MARKET_NOT_GREEN = "MARKET_NOT_GREEN"
        CYLINDERS_UNKNOWN = "CYLINDERS_UNKNOWN"
        WAIT_TIME = "WAIT_TIME"
        #: Gold Mine kept its stage through a slowdown (§V1), but the quality
        #: reading behind the purchase was agreed before that slowdown began.
        ROUGH_PATCH_STALE_QUALITY = "ROUGH_PATCH_STALE_QUALITY"
        SCORE_MISSING = "SCORE_MISSING"
        NOT_CHEAP_ENOUGH = "NOT_CHEAP_ENOUGH"
        EARNINGS_SOON = "EARNINGS_SOON"
        #: Not a gate inside the guard — the guard passed and the OTHER
        #: source refused. Recorded with the same vocabulary so a year of
        #: refusals groups by cause in one query.
        SOURCE_CONFLICT = "SOURCE_CONFLICT"

    @classmethod
    def check_buy_guard(
        cls,
        market_alert: MarketAlert | str,
        rr_score: float | None,
        deserved_score: float | None,
        cylinders: int | None,
        lifecycle_stage: LifecyclePhase | str | None,
        days_to_earnings: int | None = None,
        earnings_confirmed: bool = True,
        rough_patch: bool = False,
        rough_patch_since: datetime | None = None,
        cylinders_confirmed_at: datetime | None = None,
    ) -> tuple[bool, "GomesGatekeeper.BuyGate", str]:
        """
        Hard BUY guard — every condition must pass or the buy is refused.

        Canon (GOMES_METHODOLOGY_CANON.md §6): buy only when the market is
        GREEN AND the price is attractive on the R/R chart AND the company's
        operational quality (cylinders) is known. Missing data is a refusal,
        never a default — a BUY built on unknowns is how capital gets lost.

        The rough-patch arguments are the counterweight to §V1. Making Gold
        Mine an absorbing stage stops a proven company being refused as Wait
        Time over one bad quarter — but on its own that would let a purchase
        run on a quality reading agreed BEFORE the business slowed. So the
        slowdown is checked against the confirmation date instead: the caution
        that used to live in the phase now lives here, where it can name what
        is actually wrong.

        The gate order is not arbitrary: it runs cheapest-and-most-decisive
        first, so the recorded reason is the one that actually matters. A stock
        refused for an unknown market alert is a different fact from one
        refused for being expensive, and conflating them would make the
        refusal log unreadable.

        Returns:
            (is_allowed, gate, reason) — `gate` is the machine-readable cause,
            `reason` the sentence with the numbers in it.
        """
        Gate = cls.BuyGate

        if isinstance(market_alert, str):
            try:
                market_alert = MarketAlert(market_alert.upper())
            except ValueError:
                return False, Gate.ALERT_UNKNOWN, (
                    f"Unknown market alert '{market_alert}' (BUY requires GREEN)"
                )

        if market_alert != MarketAlert.GREEN:
            return False, Gate.MARKET_NOT_GREEN, (
                f"Market Alert is {market_alert.value} (BUY requires GREEN)"
            )

        if cylinders is None or cylinders == 0:
            return False, Gate.CYLINDERS_UNKNOWN, (
                "Cylinders unknown or zero (quality unverified)"
            )

        if lifecycle_stage is not None:
            if isinstance(lifecycle_stage, str):
                try:
                    lifecycle_stage = LifecyclePhase(lifecycle_stage.upper())
                except ValueError:
                    lifecycle_stage = LifecyclePhase.UNKNOWN
            if lifecycle_stage == LifecyclePhase.WAIT_TIME:
                return False, Gate.WAIT_TIME, (
                    "Stock is in Wait Time (hype phase / dead period)"
                )

        if rough_patch:
            # An undated slowdown cannot be checked against anything, and an
            # unverifiable flag is treated the same way as a missing number
            # everywhere else in this guard: it refuses.
            if rough_patch_since is None:
                return False, Gate.ROUGH_PATCH_STALE_QUALITY, (
                    "Přechodný útlum je zapsaný bez data — nejde ověřit, "
                    "jestli je posudek válců starší než on"
                )
            if (
                cylinders_confirmed_at is not None
                and _drop_tz(cylinders_confirmed_at) < _drop_tz(rough_patch_since)
            ):
                return False, Gate.ROUGH_PATCH_STALE_QUALITY, (
                    f"Válce potvrzené {cz_date(cylinders_confirmed_at)} jsou "
                    f"starší než útlum od {cz_date(rough_patch_since)} — "
                    f"kvalita se musí posoudit znovu"
                )

        if rr_score is None or deserved_score is None:
            return False, Gate.SCORE_MISSING, "Missing R/R score or deserved score"

        if rr_score <= deserved_score:
            return False, Gate.NOT_CHEAP_ENOUGH, (
                f"Score {cz(rr_score, 2)} <= Deserved {cz(deserved_score, 2)} "
                f"(Not cheap enough)"
            )

        # Last, because it is the only gate that will pass on its own with
        # time. Everything above is a fact about the company or the market;
        # this one is a fact about the calendar, and recording it as the reason
        # when something worse is also true would send the owner waiting for a
        # date instead of looking at the price.
        if days_to_earnings is not None and 0 <= days_to_earnings <= cls.EARNINGS_DANGER_DAYS:
            kind = "oznámeno" if earnings_confirmed else "odhad"
            return False, Gate.EARNINGS_SOON, (
                f"Výsledky za {days_to_earnings} dní ({kind}) — kánon do nich "
                f"nevstupuje. Buy Guard drží {cls.EARNINGS_DANGER_DAYS} dní předem"
            )

        return True, Gate.PASSED, "All Gomes Buy Guard conditions satisfied"

    @classmethod
    def evaluate_buy_guard(
        cls,
        market_alert: MarketAlert | str,
        rr_score: float | None,
        deserved_score: float | None,
        cylinders: int | None,
        lifecycle_stage: LifecyclePhase | str | None,
        days_to_earnings: int | None = None,
        earnings_confirmed: bool = True,
        rough_patch: bool = False,
        rough_patch_since: datetime | None = None,
        cylinders_confirmed_at: datetime | None = None,
    ) -> tuple[bool, str]:
        """
        `check_buy_guard` without the gate code, for callers that only decide.

        Kept as the two-value form because that is what the verdict path and
        the Daily Action engine consume; the gate matters only where a refusal
        is being recorded.
        """
        allowed, _gate, reason = cls.check_buy_guard(
            market_alert=market_alert,
            rr_score=rr_score,
            deserved_score=deserved_score,
            cylinders=cylinders,
            lifecycle_stage=lifecycle_stage,
            days_to_earnings=days_to_earnings,
            earnings_confirmed=earnings_confirmed,
            rough_patch=rough_patch,
            rough_patch_since=rough_patch_since,
            cylinders_confirmed_at=cylinders_confirmed_at,
        )
        return allowed, reason
    
    def evaluate(
        self,
        ticker: str,
        conviction_score: int,
        lifecycle_phase: LifecyclePhase | None = None,
        current_price: float | None = None,
        green_line: float | None = None,
        red_line: float | None = None,
        earnings_date: datetime | None = None,
        ml_prediction: dict[str, Any] | None = None,
        transcript_text: str | None = None,
        catalyst_info: dict[str, Any] | None = None,
        cylinders_count: int | None = None,
        phase_reached: LifecyclePhase | str | None = None,
    ) -> GomesVerdict:
        """
        Evaluate investment and return final verdict.
        
        This is THE GATEKEEPER function. All rules are applied here.
        
        Args:
            ticker: Stock ticker
            conviction_score: Base Conviction Score (0-10)
            lifecycle_phase: Stock lifecycle phase (or auto-detect)
            current_price: Current market price
            green_line: Buy zone price
            red_line: Sell zone price
            earnings_date: Next earnings date
            ml_prediction: ML prediction dict {"direction": "UP", "confidence": 0.85}
            transcript_text: Transcript for lifecycle detection
            catalyst_info: Catalyst info dict
            phase_reached: The furthest stage this company has reached, from
                `stock_lifecycle.phase_reached`. Passed straight to the
                classifier so a transcript full of rough-patch vocabulary
                cannot demote a proven Gold Mine here either (§V1). Without it
                this path stays memoryless.
            
        Returns:
            GomesVerdict with final decision
        """
        risk_factors: list[str] = []
        blocked_reason: str | None = None
        passed_filter = True
        adjusted_score = conviction_score
        
        # =====================================================================
        # RULE 1: Lifecycle Phase Filter (WAIT_TIME = BLOCKED)
        # Ref: Minute 31:28 - "Wait Time is the KILLER"
        # =====================================================================
        
        if lifecycle_phase is None and transcript_text:
            assessment = StockLifecycleClassifier.classify(
                ticker, transcript_text, reached=phase_reached
            )
            lifecycle_phase = assessment.phase
        
        lifecycle_phase = lifecycle_phase or LifecyclePhase.UNKNOWN
        
        if lifecycle_phase == LifecyclePhase.WAIT_TIME:
            passed_filter = False
            blocked_reason = "WAIT_TIME phase - Dead Money (Gomes Rule)"
            risk_factors.append("BLOCKED: Wait Time phase - do not invest")
        
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
                    risk_factors.append(f"BLOCKED: Earnings in {days_to_earnings} days")
                else:
                    # Penalty but not blocked (unless < 7 days)
                    adjusted_score = max(0, adjusted_score - 3)
                    risk_factors.append(f"Earnings in {days_to_earnings} days - HIGH RISK")
                    
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
            risk_factors.append("BLOCKED: Red Alert - full defensive mode")
        
        # =====================================================================
        # RULE 4: Position Tier + Market Alert
        # =====================================================================
        
        position_tier = PositionSizingEngine.determine_tier(
            lifecycle_phase=lifecycle_phase,
            conviction_score=adjusted_score,
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
            risk_factors.append(f"{position_tier.value} positions not allowed in {self.market_alert.value}")
        
        # =====================================================================
        # RULE 5: Price Line Analysis
        # =====================================================================
        
        price_zone = "UNKNOWN"
        if current_price is not None:
            if cylinders_count is not None:
                # Faithful Level-3 decision: R/R score vs deserved (10 - cylinders).
                zone, zone_reason = RiskRewardCalculator.decide(
                    current_price, green_line, red_line, cylinders=cylinders_count
                )
            else:
                # Price-only zone (neutral midpoint) when quality is unknown.
                zone, zone_reason = RiskRewardCalculator.get_action_zone(
                    current_price, green_line, red_line
                )
            price_zone = zone

            if zone == "SELL" and passed_filter:
                # Price above deserved value - don't buy
                adjusted_score = max(0, adjusted_score - 2)
                risk_factors.append(f"{zone_reason}")
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
                risk_factors.append(f"ML predicts DOWN with {cz(ml_confidence*100, 0)}% confidence")
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

        # =====================================================================
        # RULE 7: Hard Buy Guard (canon §6) — no buy-side verdict may bypass it
        # Buy only when GREEN + cylinders known + not Wait-Time + score >
        # deserved. Failing the guard downgrades to HOLD (don't buy ≠ sell).
        # =====================================================================

        if verdict in (
            InvestmentVerdict.STRONG_BUY,
            InvestmentVerdict.BUY,
            InvestmentVerdict.ACCUMULATE,
        ):
            guard_rr_score = RiskRewardCalculator.calculate_rr_score(
                current_price, green_line, red_line
            )
            guard_deserved = RiskRewardCalculator.deserved_score(cylinders_count)
            buy_allowed, guard_reason = self.evaluate_buy_guard(
                market_alert=self.market_alert,
                rr_score=guard_rr_score,
                deserved_score=guard_deserved,
                cylinders=cylinders_count,
                lifecycle_stage=lifecycle_phase,
            )
            if not buy_allowed:
                verdict = InvestmentVerdict.HOLD
                risk_factors.append(f"BUY GUARD: {guard_reason}")

        # Catalyst info
        has_catalyst = bool(catalyst_info and catalyst_info.get("has_catalyst"))
        catalyst_type = catalyst_info.get("type") if catalyst_info else None
        catalyst_desc = catalyst_info.get("description") if catalyst_info else None
        
        # Build reasoning
        reasoning_parts = []
        reasoning_parts.append(f"Conviction Score: {adjusted_score}/10 (original: {conviction_score})")
        reasoning_parts.append(f"Phase: {lifecycle_phase.value}")
        reasoning_parts.append(f"Market: {self.market_alert.value}")
        reasoning_parts.append(f"Tier: {position_tier.value} (max {position_limit.max_portfolio_pct}%)")
        
        if green_line:
            reasoning_parts.append(f"Green Line: ${cz(green_line, 2)}")
        if red_line:
            reasoning_parts.append(f"Red Line: ${cz(red_line, 2)}")
        if current_price:
            reasoning_parts.append(f"Current: ${cz(current_price, 2)} ({price_zone})")
        
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
            conviction_score=adjusted_score,
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
# 6. DUAL-SOURCE BUY POLICY (Gomes × Breakout Investors)
# ============================================================================

@dataclass
class DualSourceBuyDecision:
    """
    Final buy decision after crossing the Gomes Buy Guard with the
    Breakout Investors stance for the same ticker.
    """
    decision: str            # "ALLOW" | "REJECT"
    agreement: str           # "AGREE" | "SINGLE" | "MIXED" | "CONFLICT" | "GOMES_NO_BUY"
    max_position_pct: float  # 0.0 when rejected
    review_required: bool
    reason: str


# Position-size caps (% of portfolio) by cross-source agreement.
# Sources agreeing earns full tier size (app-level cap 15%); a lone Gomes take
# gets standard size; a direct conflict is allowed but tiny + flagged for review.
#: Position cap by how far the two sources agree. CONFLICT no longer sizes
#: anything: since 2026-08-23 a Breakout analyst writing "sell" refuses the
#: purchase outright rather than shrinking it, on the owner's decision that
#: either source may prevent a buy. The key stays so a decision stored before
#: that date still resolves to a number.
AGREEMENT_POSITION_CAPS: dict[str, float] = {
    "AGREE": 15.0,
    "SINGLE": 7.0,
    "MIXED": 7.0,
    "CONFLICT": 0.0,
}


def evaluate_dual_source_buy(
    gomes_allowed: bool,
    gomes_reason: str,
    breakout_stance: str | None,
    tier_max_pct: float,
) -> DualSourceBuyDecision:
    """
    Cross the Gomes Buy Guard verdict with the Breakout Investors stance.

    Both sources may refuse. Neither may authorise alone.
    ------------------------------------------------------
    Changed on 2026-08-23, on the owner's decision that the two sources sit at
    the same level. Equality here is equality in the right to PREVENT, not in
    the right to allow, and the asymmetry is on purpose:

      * Either source saying no stops the purchase. Gomes' valuation guard has
        always had that power; a Breakout analyst writing that he would sell
        now has it too. Two people who follow a company and disagree about
        owning it is not a reason to own a little of it.
      * Neither can authorise a name the method cannot value. Buying still
        requires a real valuation band and a Buy Guard that passes on it, so a
        company nobody has drawn lines for stays unbuyable however enthusiastic
        anyone is about it.

    What that costs, stated plainly: the app will now decline purchases it used
    to make at a fifth of the size. A refusal is recoverable and a bad position
    is not, and a fifth of a position taken against a source you trust was
    always a strange thing to hold.

    Sizes when everyone allows:

      AGREE   (Breakout BULLISH)  -> full tier size, capped at 15%
      SINGLE  (no Breakout take)  -> standard size, capped at 7%
      MIXED   (Breakout NEUTRAL)  -> standard size, capped at 7%

    A stance means somebody wrote something. The scraped watchlist is not one:
    it carries a count of endorsements and no author, and writing all
    twenty-eight names in as BULLISH would double the allowed size of
    twenty-eight positions on the strength of a scrape nobody read. See
    `app/services/breakout_sync.py`.

    Args:
        gomes_allowed/gomes_reason: output of GomesGatekeeper.check_buy_guard.
        breakout_stance: "BULLISH" | "BEARISH" | "NEUTRAL" | None (no take),
            as produced by app.core.sources.verdict_stance — and only ever from
            a named analyst on the roster.
        tier_max_pct: the tier's own max position size (PositionSizingEngine).
    """
    stance = (breakout_stance or "").strip().upper() or None

    if not gomes_allowed:
        if stance == "BULLISH":
            return DualSourceBuyDecision(
                decision="REJECT",
                agreement="GOMES_NO_BUY",
                max_position_pct=0.0,
                review_required=False,
                reason=(
                    f"Breakout je pro, ale Gomes blokuje: {gomes_reason} "
                    f"— na zákaz stačí jeden zdroj"
                ),
            )
        return DualSourceBuyDecision(
            decision="REJECT",
            agreement="GOMES_NO_BUY",
            max_position_pct=0.0,
            review_required=False,
            reason=gomes_reason,
        )

    if stance == "BEARISH":
        # The half that is new. It used to allow a fifth-size position with a
        # review flag — a compromise between two people who disagreed about
        # whether to own the company at all.
        return DualSourceBuyDecision(
            decision="REJECT",
            agreement="CONFLICT",
            max_position_pct=0.0,
            review_required=True,
            reason=(
                "Gomes je pro, ale analytik z Breakoutu píše, že prodávat "
                "— na zákaz stačí jeden zdroj. Rozhodni sám, jestli to přebít"
            ),
        )

    if stance == "BULLISH":
        agreement = "AGREE"
        reason = "Gomes pro + analytik z Breakoutu pro — oba zdroje, plná velikost"
    elif stance is None:
        agreement = "SINGLE"
        reason = "Jen Gomes (Breakout se nevyjádřil) — standardní velikost"
    else:
        agreement = "MIXED"
        reason = f"Gomes pro + Breakout {stance} — bez přímého konfliktu"

    cap = AGREEMENT_POSITION_CAPS[agreement]
    return DualSourceBuyDecision(
        decision="ALLOW",
        agreement=agreement,
        max_position_pct=min(max(tier_max_pct, 0.0), cap),
        review_required=False,
        reason=reason,
    )

def quick_gomes_check(
    ticker: str,
    conviction_score: int,
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
        conviction_score=conviction_score,
        lifecycle_phase=phase,
        earnings_date=earnings_date
    )
    
    return verdict.passed_gomes_filter, verdict.blocked_reason or verdict.verdict.value


# ============================================================================
# 7. ZONE LADDER — the band, and the prices where it changes
# ============================================================================

class Band(str, Enum):
    """
    Where a price sits relative to what the company's quality deserves.

    Named in Czech because these reach the screen. `MIMO_METODIKU` and
    `NEZNAME` are two different absences and are kept apart on purpose: the
    first is a company the method has no valuation for at all, the second is
    one whose valuation is known and whose quality is not.
    """

    POD_ZELENOU = "POD_ZELENOU"        # price at or below the Green Line
    NAKUP = "NAKUP"                    # cheaper than its quality deserves
    DRZET = "DRZET"                    # about what it deserves
    PREPLACENO = "PREPLACENO"          # dearer than its quality deserves
    NAD_CERVENOU = "NAD_CERVENOU"      # price at or above the Red Line
    NEZNAME = "NEZNAME"                # band known, cylinders not
    MIMO_METODIKU = "MIMO_METODIKU"    # no Green/Red Line for this company


class Trigger(str, Enum):
    """A move since entry, which is a different question from where the price sits."""

    VYBRAT_ZISK = "VYBRAT_ZISK"        # 3 points cheaper on the scale than at entry
    DOKOUPIT = "DOKOUPIT"              # 3 points dearer on the scale than at entry
    ZADNY = "ZADNY"


#: Canon section 5. Three points on the ten-point R/R scale, measured FROM ENTRY.
THREE_POINTS: Final[float] = 3.0


@dataclass(frozen=True)
class LadderReading:
    """
    One company's position on the ladder, with the prices where it changes.

    `buy_below` and `sell_above` are the reason this exists. A band tells the
    owner what is true today; two prices let him place an order once and stop
    looking. They are derived from the LINES, not from today's price, so a
    stale quote cannot corrupt them — only the "can this be done now" flag
    depends on a fresh price.
    """

    band: Band
    rr_score: float | None = None
    deserved: float | None = None
    #: Buy at or below this and the score beats what the quality deserves.
    buy_below: float | None = None
    #: At or above this the position is dearer than its quality deserves.
    sell_above: float | None = None
    #: Canon section 5 price triggers, relative to where the position was opened.
    take_profit_above: float | None = None
    add_below: float | None = None
    reason_cs: str = ""

    @property
    def is_tradeable(self) -> bool:
        """Whether this band is a statement about value at all."""
        return self.band not in (Band.NEZNAME, Band.MIMO_METODIKU)


class ZoneLadder:
    """
    The single answer to which band a stock is in, and at what price that changes.

    Two axes, and conflating them is the mistake this class exists to prevent:

      * The BAND compares today's R/R score with `10 - cylinders` (section 4b).
        It answers whether the stock is cheap for its quality right now.
      * The TRIGGERS compare today's score with the score AT ENTRY (section 5).
        They answer whether it has moved three points since it was bought.

    `three_point_up` and `three_point_down` compute a price relative to the
    CURRENT price, which makes them triggers rather than band edges. Used as
    edges they would report "sell" for a stock that is merely dearer than it
    deserves, and "strong buy" where the canon says plain buy.
    """

    @staticmethod
    def price_at_score(
        score: float, low: float, high: float, top_score: int = 0
    ) -> float | None:
        """
        The price at which the R/R score equals `score` — the formula inverted.

            score = top + (10 - top) * log(high/price) / log(high/low)
        =>  price = high * (low/high) ** ((score - top) / (10 - top))

        This is what turns a verdict into an order. Derived from the lines
        alone, so it survives a stale quote; it changes only when the analyst
        moves the band.
        """
        if low is None or high is None or low <= 0 or high <= 0 or high <= low:
            return None
        span = 10 - top_score
        if span <= 0:
            return None
        clamped = max(float(top_score), min(10.0, float(score)))
        return high * (low / high) ** ((clamped - top_score) / span)

    @classmethod
    def read(
        cls,
        current_price: float | None,
        low: float | None,
        high: float | None,
        cylinders: int | float | None,
        *,
        entry_score: float | None = None,
        top_score: int = 0,
    ) -> LadderReading:
        """
        Place one company on the ladder.

        Returns `MIMO_METODIKU` when there is no band at all and `NEZNAME` when
        there is a band but no confirmed quality. Both refuse to name a price
        to act at, because both would be guessing at the half that is missing.
        """
        if low is None or high is None or high <= low:
            return LadderReading(
                band=Band.MIMO_METODIKU,
                reason_cs="Pro tuhle firmu nemám zelenou ani červenou čáru",
            )

        score = RiskRewardCalculator.calculate_rr_score(
            current_price, low, high, top_score
        )
        deserved = RiskRewardCalculator.deserved_score(cylinders)

        if deserved is None:
            return LadderReading(
                band=Band.NEZNAME,
                rr_score=score,
                reason_cs=(
                    f"R/R skóre {cz(score, 2)}/10, ale kvalitu firmy neznám — "
                    f"bez ní nevím, jestli je to levné"
                    if score is not None
                    else "Chybí kvalita firmy i použitelná cena"
                ),
            )

        deadband = RiskRewardCalculator.RR_DEADBAND
        buy_below = cls.price_at_score(deserved + deadband, low, high, top_score)
        sell_above = cls.price_at_score(deserved - deadband, low, high, top_score)

        take_profit_above = add_below = None
        if entry_score is not None:
            take_profit_above = cls.price_at_score(
                entry_score - THREE_POINTS, low, high, top_score
            )
            add_below = cls.price_at_score(
                entry_score + THREE_POINTS, low, high, top_score
            )

        band, reason = cls._classify(
            current_price, low, high, score, deserved, cylinders
        )
        return LadderReading(
            band=band,
            rr_score=score,
            deserved=deserved,
            buy_below=buy_below,
            sell_above=sell_above,
            take_profit_above=take_profit_above,
            add_below=add_below,
            reason_cs=reason,
        )

    @staticmethod
    def _classify(
        price: float | None,
        low: float,
        high: float,
        score: float | None,
        deserved: float,
        cylinders: int | float | None,
    ) -> tuple[Band, str]:
        if price is None or score is None:
            return Band.NEZNAME, "Chybí použitelná cena"

        c = max(0, min(10, int(cylinders)))
        detail = f"zasloužené {cz(deserved, 1)} (10 − {c} válců)"

        # The two ends are separate states, not just extreme scores: at or below
        # the Green Line the analyst says undervalued outright, and at or above
        # the Red Line he says fully valued. Both are worth naming as such.
        if price <= low:
            return Band.POD_ZELENOU, (
                f"Cena {price:g} je na zelené čáře nebo pod ní — nejlevnější "
                f"stav, jaký metodika zná ({detail})"
            )
        if price >= high:
            return Band.NAD_CERVENOU, (
                f"Cena {price:g} je na červené čáře nebo nad ní — plná valuace "
                f"({detail})"
            )

        deadband = RiskRewardCalculator.RR_DEADBAND
        if score > deserved + deadband:
            return Band.NAKUP, (
                f"R/R skóre {cz(score, 2)} > {detail} — levné vzhledem ke kvalitě"
            )
        if score < deserved - deadband:
            return Band.PREPLACENO, (
                f"R/R skóre {cz(score, 2)} < {detail} — drahé vzhledem ke kvalitě"
            )
        return Band.DRZET, f"R/R skóre {cz(score, 2)} ≈ {detail}"

    @staticmethod
    def trigger(
        current_score: float | None, entry_score: float | None
    ) -> tuple[Trigger, str]:
        """
        Canon section 5, measured from where the position was opened.

        Deliberately independent of the band: a stock can be firmly in NAKUP and
        still have moved three points against you since entry, and a stock that
        has moved three points in your favour is worth taking profit on even
        while it still looks fairly priced for its quality. Reading either one
        through the other loses a real signal.

        Silent when the entry score is unknown, which is every position opened
        before it started being recorded. Deriving it from today's band would
        date the move from a starting point that never existed.
        """
        if current_score is None or entry_score is None:
            return Trigger.ZADNY, "Skóre při vstupu neznám — pravidlo tří bodů mlčí"

        moved = current_score - entry_score
        if moved <= -THREE_POINTS:
            return Trigger.VYBRAT_ZISK, (
                f"Od nákupu spadlo skóre o {cz(abs(moved), 1)} bodu "
                f"({cz(entry_score, 1)} → {cz(current_score, 1)}) — vybrat zisk"
            )
        if moved >= THREE_POINTS:
            return Trigger.DOKOUPIT, (
                f"Od nákupu stouplo skóre o {cz(moved, 1)} bodu "
                f"({cz(entry_score, 1)} → {cz(current_score, 1)}) — dokoupit"
            )
        return Trigger.ZADNY, (
            f"Od nákupu se skóre pohnulo o {moved:+.1f} bodu — na pravidlo "
            f"tří bodů to nestačí"
        )
