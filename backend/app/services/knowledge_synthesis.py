"""
Knowledge Synthesis Service
============================

Implements the "Brain Logic" for incremental knowledge synthesis.
NEVER overwrites - always MERGES & REFINES existing data.

Core Principles:
- Context Match: Compare new info with existing Thesis Tracker
- Conflict Resolution: Detect contradictions, adjust scores, trigger alerts
- Price Context: Correlate mentions with stored Green/Red Lines
- Preserve History: All changes tracked in score_history

Author: Akcion Lead Architect
Date: 2026-01-31
Version: 2.0.0
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Optional, Tuple, List

from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.config.settings import Settings
from app.models.stock import Stock
from app.models.score_history import ConvictionScoreHistory, ThesisDriftAlert
from app.models.trading import ActiveWatchlist


logger = logging.getLogger(__name__)


class ConflictType(str, Enum):
    """Types of thesis conflicts detected."""
    NONE = "NONE"
    MINOR = "MINOR"           # Small adjustment needed
    SIGNIFICANT = "SIGNIFICANT"  # Score adjustment 2-3 points
    CRITICAL = "CRITICAL"     # Thesis breaking, score drop 4+


class MergeAction(str, Enum):
    """Result of knowledge merge."""
    CREATED = "CREATED"       # New stock created
    UPDATED = "UPDATED"       # Existing data refined
    CONFLICT = "CONFLICT"     # Conflicting info detected
    NO_CHANGE = "NO_CHANGE"   # Info already known


@dataclass
class ConflictAnalysis:
    """Result of conflict detection between old and new data."""
    conflict_type: ConflictType
    conflicts: List[str]
    score_adjustment: int  # Negative = downgrade
    confidence_change: float
    explanation: str


@dataclass
class MergeResult:
    """Result of knowledge synthesis operation."""
    action: MergeAction
    ticker: str
    old_score: Optional[int]
    new_score: Optional[int]
    conflicts: List[str]
    merged_fields: List[str]
    alert_generated: bool
    explanation: str


@dataclass
class PriceContextMatch:
    """Result of price context analysis."""
    has_price_mention: bool
    mentioned_price: Optional[float]
    relation_to_green_line: Optional[str]  # BELOW, AT, ABOVE
    relation_to_red_line: Optional[str]
    is_bullish_signal: bool
    explanation: str


class KnowledgeSynthesisService:
    """
    Service for intelligent knowledge synthesis.
    
    Implements:
    - Incremental learning (merge, don't overwrite)
    - Conflict detection and resolution
    - Price line correlation
    - Thesis drift tracking
    
    Usage:
        service = KnowledgeSynthesisService(db)
        result = await service.synthesize_knowledge(
            ticker="AAPL",
            new_info="Management reported delay...",
            source="Breakout Investors Chat"
        )
    """
    
    def __init__(self, db: Session):
        self.db = db
        self.settings = Settings()
        self._init_gemini()
        
    def _init_gemini(self) -> None:
        """Initialize Gemini AI for intelligent merging."""
        try:
            import google.generativeai as genai
            genai.configure(api_key=self.settings.gemini_api_key)
            self.model = genai.GenerativeModel('gemini-2.0-flash')
            self.gemini_available = True
            logger.info("Gemini initialized for Knowledge Synthesis")
        except Exception as e:
            logger.warning(f"Gemini not available for synthesis: {e}")
            self.gemini_available = False
            self.model = None
    
    # =========================================================================
    # MAIN SYNTHESIS METHODS
    # =========================================================================
    
    async def synthesize_knowledge(
        self,
        ticker: str,
        new_info: str,
        source: str = "Unknown",
        force_score: Optional[int] = None,
    ) -> MergeResult:
        """
        Main entry point for knowledge synthesis.
        
        Steps:
        1. Get existing stock data
        2. Analyze for conflicts with new info
        3. Check price context
        4. Merge data intelligently
        5. Update database
        6. Generate alerts if needed
        
        Args:
            ticker: Stock ticker symbol
            new_info: New information text (chat message, news, etc.)
            source: Source of the information
            force_score: Override score (for manual adjustments)
            
        Returns:
            MergeResult with details of what was done
        """
        ticker = ticker.upper()
        logger.info(f"Synthesizing knowledge for {ticker} from {source}")
        
        # Get existing stock
        existing = self._get_existing_stock(ticker)
        
        if not existing:
            # Create new stock from info
            return await self._create_new_from_info(ticker, new_info, source)
        
        # Analyze conflicts
        conflict_analysis = await self._analyze_conflicts(existing, new_info)
        
        # Check price context
        price_context = self._analyze_price_context(existing, new_info)
        
        # Calculate new score
        old_score = existing.conviction_score
        new_score = self._calculate_merged_score(
            old_score, 
            conflict_analysis, 
            price_context,
            force_score
        )
        
        # Merge the data
        merged_fields = await self._merge_stock_data(
            existing, 
            new_info, 
            source,
            conflict_analysis,
            new_score
        )
        
        # Generate alert if significant change
        alert_generated = False
        if conflict_analysis.conflict_type in [ConflictType.SIGNIFICANT, ConflictType.CRITICAL]:
            self._generate_conflict_alert(
                ticker, 
                old_score, 
                new_score, 
                conflict_analysis
            )
            alert_generated = True
        
        # Record score history
        self._record_score_history(
            ticker,
            existing.id,
            new_score,
            conflict_analysis.conflict_type.value,
            source
        )
        
        # Commit changes
        self.db.commit()
        
        return MergeResult(
            action=MergeAction.CONFLICT if conflict_analysis.conflicts else MergeAction.UPDATED,
            ticker=ticker,
            old_score=old_score,
            new_score=new_score,
            conflicts=conflict_analysis.conflicts,
            merged_fields=merged_fields,
            alert_generated=alert_generated,
            explanation=conflict_analysis.explanation
        )
    
    # =========================================================================
    # CONFLICT DETECTION
    # =========================================================================
    
    async def _analyze_conflicts(
        self, 
        existing: Stock, 
        new_info: str
    ) -> ConflictAnalysis:
        """
        Analyze new information for conflicts with existing thesis.
        
        Uses AI to detect:
        - Contradictions with stored catalysts/edge
        - Delays vs "on track" statements
        - Management changes
        - Guidance revisions
        """
        if not self.gemini_available:
            return self._rule_based_conflict_check(existing, new_info)
        
        prompt = f"""Analyze if this new information conflicts with the existing investment thesis.

EXISTING THESIS:
- Ticker: {existing.ticker}
- Company: {existing.company_name or 'Unknown'}
- Current Score: {existing.conviction_score}/10
- Edge (Why we own it): {existing.edge or 'Not specified'}
- Catalysts: {existing.catalysts or 'Not specified'}
- Risks: {existing.risks or 'Not specified'}
- Action Verdict: {existing.action_verdict or 'Not specified'}

NEW INFORMATION:
{new_info[:5000]}

Analyze for conflicts:
1. Does new info CONTRADICT any existing thesis points?
2. Are there DELAYS to expected catalysts?
3. Any NEGATIVE management/guidance changes?
4. Any POSITIVE developments that strengthen thesis?

Respond in JSON:
{{
    "conflict_type": "NONE|MINOR|SIGNIFICANT|CRITICAL",
    "conflicts": ["list of specific conflicts"],
    "positive_developments": ["list of positive news"],
    "score_adjustment": -3 to +2 (integer),
    "explanation": "Brief summary"
}}
"""
        try:
            response = self.model.generate_content(prompt)
            result = self._parse_json_response(response.text)
            
            return ConflictAnalysis(
                conflict_type=ConflictType(result.get("conflict_type", "NONE")),
                conflicts=result.get("conflicts", []),
                score_adjustment=int(result.get("score_adjustment", 0)),
                confidence_change=0.0,
                explanation=result.get("explanation", "")
            )
        except Exception as e:
            logger.error(f"AI conflict analysis failed: {e}")
            return self._rule_based_conflict_check(existing, new_info)
    
    def _rule_based_conflict_check(
        self, 
        existing: Stock, 
        new_info: str
    ) -> ConflictAnalysis:
        """Fallback rule-based conflict detection."""
        conflicts = []
        score_adj = 0
        info_lower = new_info.lower()
        
        # Check for negative keywords
        negative_keywords = [
            ("delay", -1, "Delay mentioned"),
            ("postponed", -1, "Postponement mentioned"),
            ("missed", -2, "Missed target/deadline"),
            ("downgrade", -2, "Downgrade mentioned"),
            ("cut guidance", -2, "Guidance cut"),
            ("lowered guidance", -2, "Guidance lowered"),
            ("disappointing", -1, "Disappointing results"),
            ("lawsuit", -1, "Legal issues"),
            ("sec investigation", -2, "SEC investigation"),
            ("fraud", -3, "Fraud allegation"),
            ("bankruptcy", -4, "Bankruptcy risk"),
            ("dilution", -1, "Share dilution"),
        ]
        
        for keyword, adjustment, description in negative_keywords:
            if keyword in info_lower:
                conflicts.append(description)
                score_adj += adjustment
        
        # Check for positive keywords (can offset)
        positive_keywords = [
            ("beat expectations", 1),
            ("raised guidance", 1),
            ("ahead of schedule", 1),
            ("major contract", 1),
            ("fda approval", 2),
        ]
        
        for keyword, adjustment in positive_keywords:
            if keyword in info_lower:
                score_adj += adjustment
        
        # Determine conflict type
        if score_adj <= -4:
            conflict_type = ConflictType.CRITICAL
        elif score_adj <= -2:
            conflict_type = ConflictType.SIGNIFICANT
        elif score_adj < 0:
            conflict_type = ConflictType.MINOR
        else:
            conflict_type = ConflictType.NONE
        
        return ConflictAnalysis(
            conflict_type=conflict_type,
            conflicts=conflicts,
            score_adjustment=score_adj,
            confidence_change=0.0,
            explanation=f"Rule-based analysis: {len(conflicts)} issues found"
        )
    
    # =========================================================================
    # PRICE CONTEXT ANALYSIS
    # =========================================================================
    
    def _analyze_price_context(
        self, 
        stock: Stock, 
        new_info: str
    ) -> PriceContextMatch:
        """
        Analyze price mentions in new info and correlate with price lines.
        
        Detects:
        - Price mentions ($XX, XX dollars)
        - Relation to Green Line (buy zone)
        - Relation to Red Line (sell zone)
        - Support/resistance mentions
        """
        # Extract price mentions
        price_patterns = [
            r'\$(\d+(?:\.\d{1,2})?)',
            r'(\d+(?:\.\d{1,2})?)\s*dollars?',
            r'price[d]?\s+(?:at|to|of)\s+\$?(\d+(?:\.\d{1,2})?)',
        ]
        
        mentioned_price = None
        for pattern in price_patterns:
            match = re.search(pattern, new_info, re.IGNORECASE)
            if match:
                try:
                    mentioned_price = float(match.group(1))
                    break
                except ValueError:
                    continue
        
        if not mentioned_price:
            return PriceContextMatch(
                has_price_mention=False,
                mentioned_price=None,
                relation_to_green_line=None,
                relation_to_red_line=None,
                is_bullish_signal=False,
                explanation="No price mentioned"
            )
        
        # Compare with price lines
        green_line = float(stock.green_line) if stock.green_line else None
        red_line = float(stock.red_line) if stock.red_line else None
        
        relation_green = None
        relation_red = None
        is_bullish = False
        
        if green_line:
            if mentioned_price < green_line * 0.95:
                relation_green = "BELOW"
                is_bullish = True  # Below buy zone = opportunity
            elif mentioned_price < green_line * 1.05:
                relation_green = "AT"
                is_bullish = True
            else:
                relation_green = "ABOVE"
        
        if red_line:
            if mentioned_price > red_line * 0.95:
                relation_red = "AT_OR_ABOVE"
            else:
                relation_red = "BELOW"
        
        # Check for bullish language
        bullish_terms = ["support", "bounce", "breakout", "accumulating", "buying"]
        info_lower = new_info.lower()
        for term in bullish_terms:
            if term in info_lower:
                is_bullish = True
                break
        
        explanation = f"Price ${mentioned_price} mentioned"
        if green_line:
            explanation += f" (Green Line: ${green_line})"
        
        return PriceContextMatch(
            has_price_mention=True,
            mentioned_price=mentioned_price,
            relation_to_green_line=relation_green,
            relation_to_red_line=relation_red,
            is_bullish_signal=is_bullish,
            explanation=explanation
        )
    
    # =========================================================================
    # SCORE CALCULATION
    # =========================================================================
    
    def _calculate_merged_score(
        self,
        old_score: Optional[int],
        conflict_analysis: ConflictAnalysis,
        price_context: PriceContextMatch,
        force_score: Optional[int] = None
    ) -> int:
        """
        Calculate new score based on all factors.
        
        Rules:
        - Start with old score (or 5 if none)
        - Apply conflict adjustment
        - Bonus for bullish price context at green line
        - Clamp to 1-10 range
        """
        if force_score is not None:
            return max(1, min(10, force_score))
        
        base_score = old_score or 5
        
        # Apply conflict adjustment
        new_score = base_score + conflict_analysis.score_adjustment
        
        # Bullish price context bonus
        if price_context.is_bullish_signal and price_context.relation_to_green_line == "AT":
            new_score += 1  # At green line with bullish signal
        
        # Clamp to valid range
        return max(1, min(10, new_score))
    
    # =========================================================================
    # DATA MERGING
    # =========================================================================
    
    async def _merge_stock_data(
        self,
        stock: Stock,
        new_info: str,
        source: str,
        conflict_analysis: ConflictAnalysis,
        new_score: int
    ) -> List[str]:
        """
        Merge new information into existing stock data.
        
        Updates:
        - conviction_score
        - analysis_summary (appends, doesn't overwrite)
        - updated_at
        - source attribution
        """
        merged_fields = []
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M")
        
        # Update score
        if stock.conviction_score != new_score:
            stock.conviction_score = new_score
            merged_fields.append("conviction_score")
        
        # Append to analysis summary (not overwrite!)
        new_summary_entry = f"\n\n---\n[{timestamp}] {source}:\n{new_info[:500]}"
        
        if conflict_analysis.conflicts:
            new_summary_entry += f"\n⚠️ CONFLICTS: {', '.join(conflict_analysis.conflicts)}"
        
        if stock.analysis_summary:
            # Append new info to existing
            stock.analysis_summary = stock.analysis_summary + new_summary_entry
        else:
            stock.analysis_summary = new_summary_entry
        merged_fields.append("analysis_summary")
        
        # Update timestamp
        stock.updated_at = datetime.utcnow()
        merged_fields.append("updated_at")
        
        # Update source attribution
        if source and source != "Unknown":
            existing_sources = stock.source_type or ""
            if source not in existing_sources:
                stock.source_type = f"{existing_sources}, {source}".strip(", ")
                merged_fields.append("source_type")
        
        return merged_fields
    
    async def _create_new_from_info(
        self,
        ticker: str,
        new_info: str,
        source: str
    ) -> MergeResult:
        """Create new stock entry from information."""
        new_stock = Stock(
            ticker=ticker,
            source_type=source,
            raw_notes=new_info[:2000],
            analysis_summary=f"[{datetime.utcnow().strftime('%Y-%m-%d')}] {source}:\n{new_info[:1000]}",
            conviction_score=5,  # Neutral starting score
            is_latest=True,
            created_at=datetime.utcnow(),
        )
        
        self.db.add(new_stock)
        self.db.commit()
        self.db.refresh(new_stock)
        
        return MergeResult(
            action=MergeAction.CREATED,
            ticker=ticker,
            old_score=None,
            new_score=5,
            conflicts=[],
            merged_fields=["all"],
            alert_generated=False,
            explanation=f"New stock created from {source}"
        )
    
    # =========================================================================
    # ALERTS AND HISTORY
    # =========================================================================
    
    def _generate_conflict_alert(
        self,
        ticker: str,
        old_score: Optional[int],
        new_score: int,
        conflict_analysis: ConflictAnalysis
    ) -> None:
        """Generate alert for significant thesis conflict."""
        severity = "CRITICAL" if conflict_analysis.conflict_type == ConflictType.CRITICAL else "WARNING"
        
        alert = ThesisDriftAlert(
            ticker=ticker,
            alert_type=f"CONFLICT_{conflict_analysis.conflict_type.value}",
            severity=severity,
            old_score=old_score,
            new_score=new_score,
            message=f"Thesis conflict detected: {', '.join(conflict_analysis.conflicts[:3])}. {conflict_analysis.explanation}",
            is_acknowledged=False,
        )
        
        self.db.add(alert)
        logger.warning(f"Alert generated for {ticker}: {alert.message}")
    
    def _record_score_history(
        self,
        ticker: str,
        stock_id: int,
        score: int,
        thesis_status: str,
        source: str
    ) -> None:
        """Record score change in history."""
        history = ConvictionScoreHistory(
            ticker=ticker,
            stock_id=stock_id,
            conviction_score=score,
            thesis_status=thesis_status,
            analysis_source=source,
            recorded_at=datetime.utcnow(),
        )
        
        self.db.add(history)
    
    # =========================================================================
    # HELPER METHODS
    # =========================================================================
    
    def _get_existing_stock(self, ticker: str) -> Optional[Stock]:
        """Get latest stock record for ticker."""
        return (
            self.db.query(Stock)
            .filter(Stock.ticker == ticker.upper())
            .order_by(desc(Stock.created_at))
            .first()
        )
    
    def _parse_json_response(self, text: str) -> dict:
        """Extract and parse JSON from AI response."""
        # Try to find JSON in markdown code block
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
        if json_match:
            return json.loads(json_match.group(1))
        
        # Try to find raw JSON
        start = text.find('{')
        end = text.rfind('}') + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end])
        
        return {}
