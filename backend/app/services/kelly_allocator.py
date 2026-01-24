"""
Kelly Allocator Service

Calculates optimal position sizing using Kelly Criterion methodology
adapted for Mark Gomes' investment approach.

The service provides:
- Allocation recommendations based on Gomes score and portfolio weight
- Family portfolio gap detection
- Rebalancing suggestions
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.portfolio import Portfolio, Position
from app.models.stock import Stock

logger = logging.getLogger(__name__)


@dataclass
class AllocationRecommendation:
    """Single allocation recommendation"""
    ticker: str
    company_name: Optional[str]
    gomes_score: int
    current_weight_pct: float
    recommended_weight_pct: float
    recommended_amount: float
    recommended_amount_czk: float
    priority: int  # 1 = highest priority
    reasoning: str


@dataclass
class FamilyGap:
    """Gap detected between family portfolios"""
    ticker: str
    company_name: Optional[str]
    gomes_score: Optional[int]
    owner_with_position: str
    owner_weight_pct: float
    missing_owner: str
    priority: str  # HIGH, MEDIUM, LOW
    message: str


@dataclass
class AllocationPlan:
    """Complete allocation plan for available capital"""
    available_capital: float
    available_capital_czk: float
    recommendations: List[AllocationRecommendation]
    total_allocated: float
    remaining_cash: float


class KellyAllocatorService:
    """
    Kelly Criterion based allocation service.
    
    Simplified Kelly for Gomes methodology:
    - Score 9-10: Max 15-20% of portfolio
    - Score 7-8: Max 10-12% of portfolio
    - Score 5-6: Max 5-8% of portfolio
    - Score < 5: Avoid or minimal position
    
    The service adjusts for:
    - Existing positions (don't over-allocate)
    - Portfolio concentration limits
    - Available cash
    """
    
    # Kelly weight limits by Gomes score
    KELLY_WEIGHTS = {
        10: 0.20,  # 20% max
        9: 0.15,   # 15% max
        8: 0.12,   # 12% max
        7: 0.10,   # 10% max
        6: 0.08,   # 8% max
        5: 0.05,   # 5% max
        4: 0.03,   # 3% max - only if already owned
        3: 0.02,   # 2% max - consider selling
        2: 0.01,   # 1% max - sell signal
        1: 0.00,   # 0% - avoid completely
        0: 0.00,
    }
    
    # CZK/EUR exchange rate (should be fetched dynamically in production)
    CZK_EUR_RATE = 25.0
    
    def __init__(self, db: Session):
        self.db = db
    
    def calculate_allocation(
        self,
        portfolio_id: int,
        available_cash_eur: float,
        additional_cash_czk: float = 0,
    ) -> AllocationPlan:
        """
        Calculate optimal allocation for available capital.
        
        Args:
            portfolio_id: Target portfolio ID
            available_cash_eur: Available EUR to invest
            additional_cash_czk: Additional CZK to invest (will be converted)
            
        Returns:
            AllocationPlan with recommendations
        """
        # Get portfolio
        portfolio = self.db.query(Portfolio).filter(
            Portfolio.id == portfolio_id
        ).first()
        
        if not portfolio:
            raise ValueError(f"Portfolio {portfolio_id} not found")
        
        # Convert CZK to EUR
        additional_eur = additional_cash_czk / self.CZK_EUR_RATE
        total_available = available_cash_eur + additional_eur
        total_czk = (available_cash_eur * self.CZK_EUR_RATE) + additional_cash_czk
        
        # Get current positions and their weights
        positions = self.db.query(Position).filter(
            Position.portfolio_id == portfolio_id
        ).all()
        
        portfolio_value = sum(
            (p.current_price or p.avg_cost) * p.shares_count 
            for p in positions
        )
        
        # Get stocks with Gomes scores
        tickers = [p.ticker for p in positions]
        stocks = self.db.query(Stock).filter(
            Stock.ticker.in_(tickers),
            Stock.is_latest == True
        ).all()
        
        stock_scores = {s.ticker: s.gomes_score or 5 for s in stocks}
        stock_names = {s.ticker: s.company_name for s in stocks}
        
        # Calculate current weights and target weights
        recommendations = []
        priority = 1
        
        for position in positions:
            ticker = position.ticker
            score = stock_scores.get(ticker, 5)
            
            current_value = (position.current_price or position.avg_cost) * position.shares_count
            current_weight = current_value / portfolio_value if portfolio_value > 0 else 0
            
            target_weight = self.KELLY_WEIGHTS.get(score, 0.05)
            weight_gap = target_weight - current_weight
            
            # Only recommend if underweight and score >= 5
            if weight_gap > 0.02 and score >= 5:  # At least 2% underweight
                recommended_amount = weight_gap * portfolio_value
                recommended_czk = recommended_amount * self.CZK_EUR_RATE
                
                recommendations.append(AllocationRecommendation(
                    ticker=ticker,
                    company_name=stock_names.get(ticker),
                    gomes_score=score,
                    current_weight_pct=round(current_weight * 100, 1),
                    recommended_weight_pct=round(target_weight * 100, 1),
                    recommended_amount=round(recommended_amount, 2),
                    recommended_amount_czk=round(recommended_czk, 0),
                    priority=priority,
                    reasoning=self._get_reasoning(score, weight_gap)
                ))
                priority += 1
        
        # Sort by score (highest first), then by weight gap
        recommendations.sort(key=lambda x: (-x.gomes_score, -x.recommended_amount))
        
        # Update priorities after sorting
        for i, rec in enumerate(recommendations):
            rec.priority = i + 1
        
        # Calculate how much to allocate (don't exceed available)
        total_recommended = sum(r.recommended_amount for r in recommendations)
        allocated = min(total_recommended, total_available)
        
        # Scale recommendations if not enough cash
        if total_recommended > total_available and total_recommended > 0:
            scale = total_available / total_recommended
            for rec in recommendations:
                rec.recommended_amount = round(rec.recommended_amount * scale, 2)
                rec.recommended_amount_czk = round(rec.recommended_amount_czk * scale, 0)
        
        return AllocationPlan(
            available_capital=total_available,
            available_capital_czk=total_czk,
            recommendations=recommendations[:5],  # Top 5 recommendations
            total_allocated=allocated,
            remaining_cash=total_available - allocated
        )
    
    def detect_family_gaps(
        self,
        owner_portfolios: Dict[str, int]  # e.g., {"Já": 1, "Přítelkyně": 2}
    ) -> List[FamilyGap]:
        """
        Detect gaps between family member portfolios.
        
        If one member owns a high-conviction position that another doesn't,
        generate a FamilyGap alert.
        
        Args:
            owner_portfolios: Dict mapping owner names to portfolio IDs
            
        Returns:
            List of FamilyGap objects
        """
        gaps = []
        
        # Get all positions grouped by owner
        owner_positions: Dict[str, Dict[str, Tuple[Position, float]]] = {}
        portfolio_values: Dict[str, float] = {}
        
        for owner, portfolio_id in owner_portfolios.items():
            positions = self.db.query(Position).filter(
                Position.portfolio_id == portfolio_id
            ).all()
            
            portfolio_value = sum(
                (p.current_price or p.avg_cost) * p.shares_count 
                for p in positions
            )
            portfolio_values[owner] = portfolio_value
            
            owner_positions[owner] = {}
            for p in positions:
                value = (p.current_price or p.avg_cost) * p.shares_count
                weight = value / portfolio_value if portfolio_value > 0 else 0
                owner_positions[owner][p.ticker] = (p, weight)
        
        # Find gaps: position in one portfolio but not another
        all_tickers = set()
        for positions in owner_positions.values():
            all_tickers.update(positions.keys())
        
        # Get Gomes scores for all tickers
        stocks = self.db.query(Stock).filter(
            Stock.ticker.in_(list(all_tickers)),
            Stock.is_latest == True
        ).all()
        
        stock_info = {s.ticker: (s.gomes_score, s.company_name) for s in stocks}
        
        for ticker in all_tickers:
            score, company = stock_info.get(ticker, (None, None))
            
            # Skip low-conviction stocks
            if score is not None and score < 6:
                continue
            
            for owner, positions in owner_positions.items():
                if ticker in positions:
                    position, weight = positions[ticker]
                    
                    # Check if significant position (> 3%)
                    if weight < 0.03:
                        continue
                    
                    # Check other owners
                    for other_owner in owner_portfolios.keys():
                        if other_owner == owner:
                            continue
                        
                        if ticker not in owner_positions.get(other_owner, {}):
                            # Gap detected!
                            priority = "HIGH" if (score or 0) >= 8 else "MEDIUM"
                            
                            gaps.append(FamilyGap(
                                ticker=ticker,
                                company_name=company,
                                gomes_score=score,
                                owner_with_position=owner,
                                owner_weight_pct=round(weight * 100, 1),
                                missing_owner=other_owner,
                                priority=priority,
                                message=f"Family Gap: {owner} vlastní {ticker} ({weight*100:.1f}%), ale {other_owner} ne. Gomes Score: {score}/10"
                            ))
        
        # Sort by priority and score
        gaps.sort(key=lambda x: (0 if x.priority == "HIGH" else 1, -(x.gomes_score or 0)))
        
        return gaps
    
    def _get_reasoning(self, score: int, weight_gap: float) -> str:
        """Generate human-readable reasoning for allocation"""
        gap_pct = weight_gap * 100
        
        if score >= 9:
            return f"High conviction ({score}/10). Podváha {gap_pct:.1f}%. Priority buy."
        elif score >= 7:
            return f"Solid pick ({score}/10). Podváha {gap_pct:.1f}%. Accumulate."
        elif score >= 5:
            return f"Moderate conviction ({score}/10). Podváha {gap_pct:.1f}%. Consider adding."
        else:
            return f"Low conviction ({score}/10). Review position."
