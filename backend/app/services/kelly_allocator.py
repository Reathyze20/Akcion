"""
Kelly Allocator Service

Calculates optimal position sizing using Kelly Criterion methodology
adapted for Mark Gomes' investment approach.

The service provides:
- Allocation recommendations based on Conviction Score and portfolio weight
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
from app.services.currency import CurrencyError, CurrencyService

logger = logging.getLogger(__name__)


@dataclass
class AllocationRecommendation:
    """Single allocation recommendation"""
    ticker: str
    company_name: Optional[str]
    conviction_score: int
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
    conviction_score: Optional[int]
    owner_with_position: str
    owner_weight_pct: float
    missing_owner: str
    priority: str  # HIGH / MEDIUM = doporučení, UNKNOWN = jen rozdíl bez skóre
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
    Gomes Gap Analysis Allocation Service.
    
    Calculates optimal position sizing based on:
    1. Target weight from Conviction Score (conviction mapping)
    2. Gap analysis (target value - current value)
    3. Priority-based distribution of monthly contribution
    
    Hard caps:
    - MAX_POSITION_WEIGHT: 15% of portfolio
    - MIN_INVESTMENT: 1000 CZK (to avoid fee overhead)
    """
    
    # Target weights by Conviction Score (% of total portfolio)
    TARGET_WEIGHTS = {
        10: 0.15,  # CORE - highest conviction (12-15%)
        9: 0.15,   # CORE - high conviction
        8: 0.12,   # STRONG - solid position (10-12%)
        7: 0.10,   # GROWTH - growth position (7-10%)
        6: 0.05,   # WATCH - monitor closely (3-5%)
        5: 0.03,   # WATCH - small position
        4: 0.00,   # EXIT - should not hold
        3: 0.00,   # EXIT - sell signal
        2: 0.00,   # EXIT - strong sell
        1: 0.00,   # EXIT - avoid completely
        0: 0.00,
    }
    
    # Hard caps (Gomesova pojistka)
    MAX_POSITION_WEIGHT = 0.15  # Max 15% of portfolio in single stock
    MIN_INVESTMENT_CZK = 1000  # Min investment (fee overhead)
    
    #: Only ever a last resort, and never for valuing a position.
    #:
    #: Until 2026-08-23 this rate was applied to EVERY currency when computing
    #: the portfolio total — so a US holding was valued at the euro rate and a
    #: Canadian one at nearly double its worth. Every weight, every gap and
    #: every cap in this file was measured against that number, while
    #: `detect_family_gaps` a few hundred lines below used the real rates. The
    #: same portfolio had two different totals depending on which function you
    #: asked.
    #:
    #: What is left is the presentation of an amount in the account's own
    #: currency, where a missing rate would otherwise mean showing nothing.
    CZK_EUR_RATE = 25.0

    def _eur_rate(self) -> float:
        """The live CZK/EUR rate, falling back to the stale constant."""
        try:
            return CurrencyService.get_rate_to_czk("EUR")
        except CurrencyError:
            logger.warning("Kurz EUR není k dispozici — počítám se starým %s", self.CZK_EUR_RATE)
            return self.CZK_EUR_RATE

    def _position_value_czk(self, position) -> float | None:
        """
        One position in CZK, at its own currency's rate.

        None when the rate is unknown, and the caller must then leave the
        position out rather than price it in somebody else's money — the same
        rule `detect_family_gaps` has always followed.
        """
        price = position.current_price or position.avg_cost
        if price is None or not position.shares_count:
            return None
        currency = getattr(position, "currency", None) or "USD"
        try:
            rate = CurrencyService.get_rate_to_czk(currency)
        except CurrencyError:
            return None
        return price * position.shares_count * rate
    
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
        
        eur_rate = self._eur_rate()
        additional_eur = additional_cash_czk / eur_rate
        total_available_czk = (available_cash_eur * eur_rate) + additional_cash_czk
        
        # Get current positions — held ones only. A closed position has
        # weight zero, which reads as "far below target" and would produce a
        # recommendation to buy back what was just sold.
        positions = self.db.query(Position).filter(
            Position.portfolio_id == portfolio_id,
            Position.shares_count > 0,
        ).all()
        
        # Each position at its OWN currency's rate. A position whose rate is
        # unknown is left out entirely rather than priced in somebody else's
        # money: an unknown is not a number, and the total here is what every
        # weight and every cap below is measured against.
        position_values = {}
        unpriced = []
        for p in positions:
            value = self._position_value_czk(p)
            if value is None:
                unpriced.append(p.ticker)
            else:
                position_values[p.ticker] = value

        if unpriced:
            logger.warning(
                "Bez kurzu, mimo součet portfolia: %s", ", ".join(sorted(unpriced))
            )
        portfolio_value_czk = sum(position_values.values())
        
        # Get stocks with Conviction Scores
        tickers = [p.ticker for p in positions]
        stocks = self.db.query(Stock).filter(
            Stock.ticker.in_(tickers),
            Stock.is_latest == True
        ).all()
        
        stock_scores = {s.ticker: s.conviction_score for s in stocks}
        stock_names = {s.ticker: s.company_name for s in stocks}
        
        # ========================================================
        # GOMES GAP ANALYSIS
        # ========================================================
        
        gap_analysis = []
        
        for position in positions:
            ticker = position.ticker
            score = stock_scores.get(ticker)  # None if not analyzed
            
            # Current position value in CZK
            current_value_czk = position_values.get(position.ticker)
            if current_value_czk is None:
                continue  # no rate -> not in the total, so not in a gap either
            current_weight = current_value_czk / portfolio_value_czk if portfolio_value_czk > 0 else 0
            
            # Target weight from score (0 if score < 5 or None)
            if score is None:
                target_weight = 0  # Unanalyzed = don't allocate
            else:
                target_weight = self.TARGET_WEIGHTS.get(int(round(score)), 0)
            
            # Gap = Target Value - Current Value
            target_value_czk = portfolio_value_czk * target_weight
            gap_czk = target_value_czk - current_value_czk
            
            gap_analysis.append({
                'ticker': ticker,
                'company_name': stock_names.get(ticker),
                'score': score,
                'current_weight': current_weight,
                'target_weight': target_weight,
                'current_value_czk': current_value_czk,
                'target_value_czk': target_value_czk,
                'gap_czk': gap_czk,
            })
        
        # ========================================================
        # PRIORITIZATION & ALLOCATION
        # ========================================================
        
        # Filter: Only allocate to score >= 5 with positive gap
        eligible = [
            g for g in gap_analysis 
            if g['score'] is not None and g['score'] >= 5 and g['gap_czk'] > 0
        ]
        
        # Sort by: 1) Score (highest first), 2) Gap (largest first)
        eligible.sort(key=lambda x: (-x['score'], -x['gap_czk']))
        
        # Distribute available capital
        recommendations = []
        remaining_budget = total_available_czk
        
        for i, item in enumerate(eligible):
            if remaining_budget <= 0:
                break
            
            # Calculate allocation (min of gap and remaining budget)
            allocation = min(item['gap_czk'], remaining_budget)
            
            # Apply hard caps
            # 1. Don't exceed MAX_POSITION_WEIGHT (15%)
            max_allowed_value = portfolio_value_czk * self.MAX_POSITION_WEIGHT
            max_allocation = max_allowed_value - item['current_value_czk']
            allocation = min(allocation, max(0, max_allocation))
            
            # 2. Skip if < MIN_INVESTMENT (fee overhead)
            if allocation < self.MIN_INVESTMENT_CZK:
                continue
            
            allocation = round(allocation, 0)
            remaining_budget -= allocation
            
            recommendations.append(AllocationRecommendation(
                ticker=item['ticker'],
                company_name=item['company_name'],
                conviction_score=int(item['score']),
                current_weight_pct=round(item['current_weight'] * 100, 1),
                recommended_weight_pct=round(item['target_weight'] * 100, 1),
                recommended_amount=round(allocation / eur_rate, 2),  # EUR
                recommended_amount_czk=allocation,
                priority=i + 1,
                reasoning=self._get_reasoning(int(item['score']), item['gap_czk'])
            ))
        
        total_allocated = sum(r.recommended_amount_czk for r in recommendations)
        
        return AllocationPlan(
            available_capital=total_available_czk / eur_rate,
            available_capital_czk=total_available_czk,
            recommendations=recommendations[:5],  # Top 5 recommendations
            total_allocated=total_allocated,
            remaining_cash=total_available_czk - total_allocated
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
            
            # Přepočet na koruny, ne holý součet cena x kusy.
            #
            # Tenhle sloupec drží USD, CAD i EUR vedle sebe. Sečíst je bez
            # kurzu znamená, že se váhy počítají z čísla, které neexistuje:
            # kanadská pozice se nafoukne, americká propadne pod tříprocentní
            # práh a tiše zmizí. Zbytek aplikace to dělá správně
            # (routes/portfolio.py:139) — tohle místo na to zapomnělo.
            #
            # Měnu, na kterou není kurz, radši vynecháme, než abychom ji
            # ocenili dolarovým kurzem. Neznámé nemá být číslo.
            values: Dict[str, float] = {}
            for p in positions:
                currency = getattr(p, "currency", None) or "USD"
                try:
                    rate = CurrencyService.get_rate_to_czk(currency)
                except CurrencyError:
                    continue
                values[p.ticker] = (p.current_price or p.avg_cost or 0) * p.shares_count * rate

            portfolio_value = sum(values.values())
            portfolio_values[owner] = portfolio_value

            owner_positions[owner] = {}
            for p in positions:
                if p.ticker not in values:
                    continue
                weight = values[p.ticker] / portfolio_value if portfolio_value > 0 else 0
                owner_positions[owner][p.ticker] = (p, weight)
        
        # Find gaps: position in one portfolio but not another
        all_tickers = set()
        for positions in owner_positions.values():
            all_tickers.update(positions.keys())
        
        # Get Conviction Scores for all tickers
        stocks = self.db.query(Stock).filter(
            Stock.ticker.in_(list(all_tickers)),
            Stock.is_latest == True
        ).all()
        
        stock_info = {s.ticker: (s.conviction_score, s.company_name) for s in stocks}
        
        for ticker in all_tickers:
            score, company = stock_info.get(ticker, (None, None))
            
            # Známé nízké skóre se přeskočí: u pozice, kterou sama metodika
            # nedoporučuje, nemá smysl řešit, že ji druhý nemá.
            #
            # Neznámé skóre se ale NEpřeskakuje. „Tom drží DAIO 7,7 %, Míša ne"
            # je pravda bez ohledu na hodnocení a do přehledu rozdílů patří.
            # Nesmí z ní jen vzniknout pokyn — proto dostane vlastní stupeň
            # UNKNOWN místo MEDIUM. Dřív tudy None propadalo rovnou mezi
            # doporučení, což je ta vada, které se aplikace musí vyhýbat:
            # z chybějícího vstupu sebejistý verdikt.
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
                            if score is None:
                                priority = "UNKNOWN"
                                message = (
                                    f"{owner} drží {ticker} ({weight*100:.1f} %), "
                                    f"{other_owner} ne. Bez konvikčního skóre to "
                                    f"zůstává rozdíl, ne doporučení."
                                )
                            else:
                                priority = "HIGH" if score >= 8 else "MEDIUM"
                                message = (
                                    f"{owner} drží {ticker} ({weight*100:.1f} %), "
                                    f"ale {other_owner} ne. Konvikční skóre {score}/10."
                                )

                            gaps.append(FamilyGap(
                                ticker=ticker,
                                company_name=company,
                                conviction_score=score,
                                owner_with_position=owner,
                                owner_weight_pct=round(weight * 100, 1),
                                missing_owner=other_owner,
                                priority=priority,
                                message=message,
                            ))
        
        # Posouzené napřed, neposouzené na konec — ať se doporučení neztratí
        # mezi rozdíly, o kterých aplikace nic tvrdit neumí.
        rank = {"HIGH": 0, "MEDIUM": 1, "UNKNOWN": 2}
        gaps.sort(key=lambda x: (rank.get(x.priority, 3), -(x.conviction_score or 0), x.ticker))
        
        return gaps
    
    def _get_reasoning(self, score: int, gap_czk: float) -> str:
        """Generate human-readable reasoning for allocation"""
        gap_k = gap_czk / 1000
        
        if score >= 9:
            return f"SNIPER! Score {score}/10. Mezera {gap_k:.1f}k Kc. Prioritni nakup."
        elif score >= 8:
            return f"STRONG. Score {score}/10. Mezera {gap_k:.1f}k Kc. Akumulovat."
        elif score >= 7:
            return f"GROWTH. Score {score}/10. Mezera {gap_k:.1f}k Kc. Pridat."
        elif score >= 5:
            return f"WATCH. Score {score}/10. Mezera {gap_k:.1f}k Kc. Zvazit."
        else:
            return f"EXIT. Score {score}/10. Neposilat penize, zvazit prodej."
