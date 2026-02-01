"""
Investment Decision Engine - Long-Term Intelligence

Combines all data sources to generate investment recommendations:
- ML price predictions (fused with Gomes)
- News sentiment and catalysts
- Entry zone analysis
- Portfolio position context

Philosophy: BUY when thesis is intact and price is right
"""
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum

from sqlalchemy.orm import Session
from loguru import logger

from app.models.trading import ActiveWatchlist, OHLCVData, MLPrediction
from app.models.stock import Stock
from app.services.news_monitor import NewsMonitorService, NewsItem, PriceAlert, NewsUrgency


# =============================================================================
# INVESTMENT DECISION TYPES
# =============================================================================

class InvestmentAction(str, Enum):
    """Long-term investment actions (not trading!)"""
    STRONG_BUY = "STRONG_BUY"      # Entry zone + thesis strong + catalyst imminent
    ACCUMULATE = "ACCUMULATE"       # Good price, add to position gradually
    HOLD = "HOLD"                   # Keep position, no action needed
    WATCH = "WATCH"                 # On watchlist, waiting for entry
    REDUCE = "REDUCE"               # Consider trimming (target reached or thesis weakening)
    EXIT = "EXIT"                   # Thesis broken, exit position
    AVOID = "AVOID"                 # Do not buy


class ThesisStatus(str, Enum):
    """Status of the investment thesis"""
    STRONG = "STRONG"               # Thesis intact, catalysts on track
    INTACT = "INTACT"               # No changes, continue holding
    WEAKENING = "WEAKENING"         # Some concerns, monitor closely
    BROKEN = "BROKEN"               # Thesis invalidated, consider exit


@dataclass
class InvestmentDecision:
    """Complete investment decision with reasoning"""
    ticker: str
    company_name: str
    action: InvestmentAction
    confidence: float  # 0-1
    thesis_status: ThesisStatus
    
    # Price context
    current_price: float
    entry_zone: Optional[str]
    in_entry_zone: bool
    price_vs_target: Optional[str]  # "50% to target", "At target"
    
    # Gomes context
    conviction_score: Optional[int]
    gomes_sentiment: Optional[str]
    edge: Optional[str]
    catalysts: Optional[str]
    risks: Optional[str]
    
    # ML context
    ml_prediction: Optional[str]
    ml_confidence: Optional[float]
    ml_price_target: Optional[float]
    
    # News context
    recent_news_sentiment: Optional[str]
    important_news: List[str]
    catalyst_matches: List[str]
    risk_matches: List[str]
    
    # Reasoning
    reasoning: List[str]
    action_detail: str
    
    # Timestamps
    created_at: datetime
    valid_until: datetime


# =============================================================================
# INVESTMENT DECISION ENGINE
# =============================================================================

class InvestmentDecisionEngine:
    """
    Generates investment decisions by combining all data sources.
    
    This is NOT a trading engine. It answers:
    - Should I buy more of this stock?
    - Is my thesis still valid?
    - Has the risk profile changed?
    - Is now a good entry point?
    """
    
    def __init__(self, db: Session):
        self.db = db
        self.news_service = NewsMonitorService(db)
        
        logger.info("Investment Decision Engine initialized")
    
    async def analyze_stock(self, ticker: str) -> Optional[InvestmentDecision]:
        """
        Generate a complete investment decision for a stock.
        
        Combines:
        1. Gomes analysis (edge, catalysts, risks, score)
        2. ML predictions (direction, confidence)
        3. Current price vs entry zone
        4. Recent news and sentiment
        """
        try:
            logger.info(f"Analyzing {ticker} for investment decision...")
            
            # Get watchlist and stock data
            watchlist = self.db.query(ActiveWatchlist).filter(
                ActiveWatchlist.ticker == ticker.upper(),
                ActiveWatchlist.is_active == True
            ).first()
            
            if not watchlist:
                logger.warning(f"{ticker} not in active watchlist")
                return None
            
            # Get Gomes analysis
            stock = None
            if watchlist.stock_id:
                stock = self.db.query(Stock).filter(Stock.id == watchlist.stock_id).first()
            
            # Get current price
            latest_ohlcv = self.db.query(OHLCVData).filter(
                OHLCVData.ticker == ticker.upper()
            ).order_by(OHLCVData.time.desc()).first()
            
            current_price = float(latest_ohlcv.close) if latest_ohlcv else 0.0
            
            # Get ML prediction
            ml_pred = self.db.query(MLPrediction).filter(
                MLPrediction.ticker == ticker.upper(),
                MLPrediction.valid_until > datetime.utcnow()
            ).order_by(MLPrediction.created_at.desc()).first()
            
            # Fetch recent news
            news_articles = await self.news_service.fetch_news_polygon(ticker, limit=5)
            classified_news = []
            gomes_context = None
            
            if stock:
                gomes_context = {
                    'edge': stock.edge,
                    'catalysts': stock.catalysts,
                    'risks': stock.risks
                }
            
            for article in news_articles:
                classified = self.news_service.classify_news(article, ticker, gomes_context)
                if classified.urgency != NewsUrgency.NOISE:
                    classified_news.append(classified)
            
            # Build decision
            decision = self._build_decision(
                ticker=ticker,
                stock=stock,
                current_price=current_price,
                ml_prediction=ml_pred,
                news=classified_news,
                watchlist=watchlist
            )
            
            logger.info(
                f"{ticker}: {decision.action.value} "
                f"(confidence: {decision.confidence:.0%}, thesis: {decision.thesis_status.value})"
            )
            
            return decision
            
        except Exception as e:
            logger.error(f"Failed to analyze {ticker}: {e}", exc_info=True)
            return None
    
    def _build_decision(
        self,
        ticker: str,
        stock: Optional[Stock],
        current_price: float,
        ml_prediction: Optional[MLPrediction],
        news: List[NewsItem],
        watchlist: ActiveWatchlist
    ) -> InvestmentDecision:
        """Build investment decision from all data sources."""
        
        reasoning = []
        catalyst_matches = []
        risk_matches = []
        important_news = []
        
        # =================================================================
        # 1. GOMES ANALYSIS SCORING
        # =================================================================
        conviction_score = stock.conviction_score if stock else None
        gomes_sentiment = stock.sentiment if stock else None
        gomes_action = stock.action_verdict if stock else None
        
        thesis_points = 0
        max_thesis_points = 10
        
        if conviction_score:
            thesis_points += min(conviction_score, 10) / 2  # Max 5 points from Conviction Score
            reasoning.append(f"Conviction Score: {conviction_score}/10")
        
        if gomes_sentiment == 'Bullish':
            thesis_points += 1
            reasoning.append("Gomes sentiment: Bullish")
        elif gomes_sentiment == 'Bearish':
            thesis_points -= 2
            reasoning.append("Gomes sentiment: Bearish")
        
        # =================================================================
        # 2. ENTRY ZONE ANALYSIS
        # =================================================================
        entry_zone = stock.entry_zone if stock else None
        in_entry_zone = False
        
        if entry_zone and current_price > 0:
            entry_price = self.news_service._parse_entry_zone(entry_zone, current_price)
            if entry_price and current_price <= entry_price:
                in_entry_zone = True
                thesis_points += 2
                reasoning.append(f"IN ENTRY ZONE: ${current_price:.2f} <= ${entry_price:.2f}")
            elif entry_price:
                pct_above = ((current_price - entry_price) / entry_price) * 100
                reasoning.append(f"Price {pct_above:.1f}% above entry zone")
        
        # =================================================================
        # 3. ML PREDICTION INTEGRATION
        # =================================================================
        ml_pred_type = None
        ml_confidence = None
        ml_price_target = None
        
        if ml_prediction:
            ml_pred_type = ml_prediction.prediction_type
            ml_confidence = float(ml_prediction.confidence)
            ml_price_target = float(ml_prediction.predicted_price)
            
            if ml_pred_type == 'UP' and ml_confidence > 0.5:
                thesis_points += 1
                reasoning.append(f"ML prediction: UP ({ml_confidence:.0%} confidence)")
            elif ml_pred_type == 'DOWN' and ml_confidence > 0.5:
                thesis_points -= 1
                reasoning.append(f"ML prediction: DOWN ({ml_confidence:.0%} confidence)")
        
        # =================================================================
        # 4. NEWS SENTIMENT ANALYSIS
        # =================================================================
        bullish_news = sum(1 for n in news if n.sentiment.value == 'BULLISH')
        bearish_news = sum(1 for n in news if n.sentiment.value == 'BEARISH')
        
        for n in news:
            catalyst_matches.extend(n.matched_catalysts)
            risk_matches.extend(n.matched_risks)
            if n.urgency in [NewsUrgency.ACTION_REQUIRED, NewsUrgency.IMPORTANT]:
                important_news.append(f"[{n.sentiment.value}] {n.title[:80]}")
        
        news_sentiment = None
        if bullish_news > bearish_news:
            news_sentiment = 'BULLISH'
            thesis_points += 0.5
            reasoning.append(f"Recent news: {bullish_news} bullish vs {bearish_news} bearish")
        elif bearish_news > bullish_news:
            news_sentiment = 'BEARISH'
            thesis_points -= 0.5
            reasoning.append(f"Recent news: {bearish_news} bearish vs {bullish_news} bullish")
        
        if catalyst_matches:
            thesis_points += 0.5
            reasoning.append(f"Catalyst keywords in news: {', '.join(set(catalyst_matches)[:3])}")
        
        if risk_matches:
            thesis_points -= 0.5
            reasoning.append(f"Risk keywords in news: {', '.join(set(risk_matches)[:3])}")
        
        # =================================================================
        # 5. DETERMINE THESIS STATUS
        # =================================================================
        thesis_score = thesis_points / max_thesis_points
        
        if thesis_score >= 0.7:
            thesis_status = ThesisStatus.STRONG
        elif thesis_score >= 0.4:
            thesis_status = ThesisStatus.INTACT
        elif thesis_score >= 0.2:
            thesis_status = ThesisStatus.WEAKENING
        else:
            thesis_status = ThesisStatus.BROKEN
        
        # =================================================================
        # 6. DETERMINE ACTION
        # =================================================================
        action, action_detail = self._determine_action(
            thesis_status=thesis_status,
            thesis_score=thesis_score,
            in_entry_zone=in_entry_zone,
            gomes_action=gomes_action,
            ml_pred_type=ml_pred_type,
            ml_confidence=ml_confidence or 0,
            current_price=current_price
        )
        
        # Calculate overall confidence
        confidence = min(0.95, max(0.1, thesis_score))
        
        # Price vs target calculation
        price_vs_target = None
        if stock and stock.price_target_long:
            try:
                target = float(stock.price_target_long.replace('$', '').split()[0])
                if target > current_price:
                    upside = ((target - current_price) / current_price) * 100
                    price_vs_target = f"{upside:.0f}% upside to ${target:.2f}"
            except:
                pass
        
        return InvestmentDecision(
            ticker=ticker,
            company_name=stock.company_name if stock else ticker,
            action=action,
            confidence=confidence,
            thesis_status=thesis_status,
            current_price=current_price,
            entry_zone=entry_zone,
            in_entry_zone=in_entry_zone,
            price_vs_target=price_vs_target,
            conviction_score=conviction_score,
            gomes_sentiment=gomes_sentiment,
            edge=stock.edge if stock else None,
            catalysts=stock.catalysts if stock else None,
            risks=stock.risks if stock else None,
            ml_prediction=ml_pred_type,
            ml_confidence=ml_confidence,
            ml_price_target=ml_price_target,
            recent_news_sentiment=news_sentiment,
            important_news=important_news[:5],
            catalyst_matches=list(set(catalyst_matches))[:5],
            risk_matches=list(set(risk_matches))[:5],
            reasoning=reasoning,
            action_detail=action_detail,
            created_at=datetime.utcnow(),
            valid_until=datetime.utcnow() + timedelta(days=1)
        )
    
    def _determine_action(
        self,
        thesis_status: ThesisStatus,
        thesis_score: float,
        in_entry_zone: bool,
        gomes_action: Optional[str],
        ml_pred_type: Optional[str],
        ml_confidence: float,
        current_price: float
    ) -> Tuple[InvestmentAction, str]:
        """Determine the investment action based on all factors."""
        
        # BROKEN THESIS = EXIT or AVOID
        if thesis_status == ThesisStatus.BROKEN:
            return InvestmentAction.EXIT, "Thesis appears broken - consider exiting position"
        
        # WEAKENING = REDUCE or HOLD carefully
        if thesis_status == ThesisStatus.WEAKENING:
            if gomes_action and 'SELL' in gomes_action.upper():
                return InvestmentAction.EXIT, "Gomes recommends selling + thesis weakening"
            return InvestmentAction.HOLD, "Thesis weakening - monitor closely, no new buys"
        
        # STRONG/INTACT THESIS
        if thesis_status in [ThesisStatus.STRONG, ThesisStatus.INTACT]:
            
            # In entry zone = opportunity
            if in_entry_zone:
                if thesis_status == ThesisStatus.STRONG and thesis_score >= 0.7:
                    return InvestmentAction.STRONG_BUY, \
                        "Strong thesis + price in entry zone = excellent accumulation opportunity"
                return InvestmentAction.ACCUMULATE, \
                    "Thesis intact + price in entry zone = good time to add"
            
            # Above entry zone
            if gomes_action:
                action_upper = gomes_action.upper()
                if 'BUY' in action_upper or 'ACCUMULATE' in action_upper:
                    if ml_pred_type == 'UP' and ml_confidence > 0.5:
                        return InvestmentAction.ACCUMULATE, \
                            "Gomes bullish + ML confirms = accumulate on pullbacks"
                    return InvestmentAction.WATCH, \
                        "Gomes bullish but wait for better entry"
                elif 'TRIM' in action_upper:
                    return InvestmentAction.REDUCE, "Gomes recommends trimming position"
                elif 'AVOID' in action_upper:
                    return InvestmentAction.AVOID, "Gomes recommends avoiding"
            
            # Default for intact thesis
            return InvestmentAction.HOLD, "Thesis intact - hold position, wait for entry"
        
        return InvestmentAction.WATCH, "Monitoring - no clear action"
    
    async def analyze_watchlist(self) -> List[InvestmentDecision]:
        """Analyze all stocks in active watchlist."""
        
        decisions = []
        
        watchlist = self.db.query(ActiveWatchlist).filter(
            ActiveWatchlist.is_active == True
        ).all()
        
        logger.info(f"Analyzing {len(watchlist)} watchlist stocks...")
        
        for item in watchlist:
            decision = await self.analyze_stock(item.ticker)
            if decision:
                decisions.append(decision)
        
        # Sort by action priority
        action_priority = {
            InvestmentAction.STRONG_BUY: 0,
            InvestmentAction.ACCUMULATE: 1,
            InvestmentAction.EXIT: 2,
            InvestmentAction.REDUCE: 3,
            InvestmentAction.WATCH: 4,
            InvestmentAction.HOLD: 5,
            InvestmentAction.AVOID: 6
        }
        
        decisions.sort(key=lambda d: (action_priority.get(d.action, 99), -d.confidence))
        
        return decisions
    
    def decision_to_dict(self, decision: InvestmentDecision) -> Dict:
        """Convert decision to JSON-serializable dict."""
        return {
            'ticker': decision.ticker,
            'company_name': decision.company_name,
            'action': decision.action.value,
            'confidence': decision.confidence,
            'thesis_status': decision.thesis_status.value,
            'current_price': decision.current_price,
            'entry_zone': decision.entry_zone,
            'in_entry_zone': decision.in_entry_zone,
            'price_vs_target': decision.price_vs_target,
            'conviction_score': decision.conviction_score,
            'gomes_sentiment': decision.gomes_sentiment,
            'edge': decision.edge,
            'catalysts': decision.catalysts,
            'risks': decision.risks,
            'ml_prediction': decision.ml_prediction,
            'ml_confidence': decision.ml_confidence,
            'ml_price_target': decision.ml_price_target,
            'recent_news_sentiment': decision.recent_news_sentiment,
            'important_news': decision.important_news,
            'catalyst_matches': decision.catalyst_matches,
            'risk_matches': decision.risk_matches,
            'reasoning': decision.reasoning,
            'action_detail': decision.action_detail,
            'created_at': decision.created_at.isoformat(),
            'valid_until': decision.valid_until.isoformat()
        }
