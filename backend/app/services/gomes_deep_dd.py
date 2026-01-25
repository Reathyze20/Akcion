"""
Gomes Deep Due Diligence Service
=================================

AI-powered deep analysis of stocks using Mark Gomes methodology.
Generates both human-readable analysis (Czech) and structured JSON data.

Author: GitHub Copilot with Claude Opus 4.5
Date: 2026-01-24
Version: 2.0.0
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from app.config.settings import Settings
from app.core.prompts import GOMES_DEEP_DUE_DILIGENCE_PROMPT, THESIS_DRIFT_PROMPT
from app.models.stock import Stock
from app.models.score_history import GomesScoreHistory, ThesisDriftAlert, AlertType
from app.schemas.gomes import (
    DeepDueDiligenceRequest,
    DeepDueDiligenceResponse,
    DeepDueDiligenceResult,
    PriceTargetsSchema,
    ThesisDriftResult,
)


logger = logging.getLogger(__name__)


class GomesDeepDueDiligenceService:
    """
    Service for running deep due diligence analysis using AI.
    
    Implements the "Treasure Hunter" methodology:
    1. Analyzes transcripts/news for investment signals
    2. Generates structured data for database
    3. Compares with existing thesis for drift detection
    4. Outputs both human-readable Czech analysis and JSON
    
    Usage:
        service = GomesDeepDueDiligenceService(db)
        result = await service.analyze(transcript="...")
        
        print(result.analysis_text)  # Czech analysis
        print(result.data.gomes_score)  # Structured data
    """
    
    def __init__(self, db: Session):
        self.db = db
        self.settings = Settings()
        self._init_gemini()
    
    def _init_gemini(self) -> None:
        """Initialize Gemini AI client"""
        try:
            import google.generativeai as genai
            genai.configure(api_key=self.settings.gemini_api_key)
            self.model = genai.GenerativeModel('gemini-2.5-pro')
            self.gemini_available = True
            logger.info("Gemini 2.5 Pro initialized for Deep Due Diligence")
        except Exception as e:
            logger.error(f"Failed to initialize Gemini: {e}")
            self.gemini_available = False
            self.model = None
    
    async def analyze(
        self,
        request: DeepDueDiligenceRequest,
    ) -> DeepDueDiligenceResponse:
        """
        Run deep due diligence analysis on transcript.
        
        Args:
            request: Analysis request with transcript text
            
        Returns:
            DeepDueDiligenceResponse with analysis and structured data
        """
        if not self.gemini_available:
            raise RuntimeError("Gemini AI not available")
        
        # Get existing stock data for thesis drift comparison
        existing_data = ""
        if request.include_existing_data and request.ticker:
            existing_data = self._get_existing_stock_data(request.ticker)
        
        # Build prompt
        prompt = GOMES_DEEP_DUE_DILIGENCE_PROMPT.format(
            existing_stock_data=existing_data or "Žádná stávající data.",
            transcript=request.transcript[:50000]  # Limit transcript length
        )
        
        # Call Gemini
        try:
            response = self.model.generate_content(prompt)
            raw_output = response.text
            logger.info(f"Gemini raw output length: {len(raw_output)}")
        except Exception as e:
            logger.error(f"Gemini API call failed: {e}")
            raise RuntimeError(f"AI analysis failed: {e}")
        
        # Parse response
        try:
            analysis_text, data = self._parse_response(raw_output)
        except ValueError as e:
            logger.error(f"Parse error: {e}")
            logger.error(f"Raw output (first 1000 chars):\n{raw_output[:1000]}")
            raise RuntimeError(f"Analysis failed: {e}")
        
        # Calculate thesis drift if we have existing data
        thesis_drift = None
        score_change = None
        if request.ticker and existing_data:
            drift_result = self._calculate_thesis_drift(request.ticker, data)
            if drift_result:
                thesis_drift = drift_result.thesis_drift
                score_change = drift_result.score_change
        
        return DeepDueDiligenceResponse(
            analysis_text=analysis_text,
            data=data,
            thesis_drift=thesis_drift,
            score_change=score_change,
            analyzed_at=datetime.utcnow(),
            source_length=len(request.transcript),
        )
    
    def _get_existing_stock_data(self, ticker: str) -> str:
        """Get existing stock data from database for comparison"""
        stock = self.db.query(Stock).filter(
            Stock.ticker == ticker.upper()
        ).order_by(Stock.created_at.desc()).first()
        
        if not stock:
            return ""
        
        return f"""
Ticker: {stock.ticker}
Company: {stock.company_name or 'N/A'}
Gomes Score: {stock.gomes_score or 'N/A'}/10
Sentiment: {stock.sentiment or 'N/A'}
Action Verdict: {stock.action_verdict or 'N/A'}
Edge: {stock.edge or 'N/A'}
Catalysts: {stock.catalysts or 'N/A'}
Risks: {stock.risks or 'N/A'}
Price Target: {stock.price_target or 'N/A'}
Entry Zone: {stock.entry_zone or 'N/A'}
Last Updated: {stock.created_at.strftime('%Y-%m-%d') if stock.created_at else 'N/A'}
"""
    
    def _extract_json_object(self, text: str) -> Optional[str]:
        """
        Extract a complete JSON object from text by finding balanced braces.
        
        Args:
            text: Raw text containing JSON somewhere
            
        Returns:
            JSON string or None if not found
        """
        # Find first { that might start our JSON
        start_candidates = [i for i, c in enumerate(text) if c == '{']
        
        for start in start_candidates:
            brace_count = 0
            in_string = False
            escape_next = False
            
            for i, char in enumerate(text[start:], start):
                if escape_next:
                    escape_next = False
                    continue
                    
                if char == '\\':
                    escape_next = True
                    continue
                    
                if char == '"' and not escape_next:
                    in_string = not in_string
                    continue
                    
                if not in_string:
                    if char == '{':
                        brace_count += 1
                    elif char == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            json_str = text[start:i + 1]
                            # Verify it has expected keys
                            if '"ticker"' in json_str:
                                return json_str
                            break
        
        return None

    def _parse_response(self, raw_output: str) -> Tuple[str, DeepDueDiligenceResult]:
        """
        Parse AI response into analysis text and structured data.
        
        Args:
            raw_output: Raw AI response
            
        Returns:
            Tuple of (analysis_text, structured_data)
        """
        logger.info(f"Parsing response of length {len(raw_output)}")
        
        # Extract JSON block from markdown code fence
        json_match = re.search(r'```json\s*([\s\S]*?)\s*```', raw_output)
        
        if json_match:
            json_str = json_match.group(1).strip()
            logger.info(f"Found JSON in markdown block, length: {len(json_str)}")
        else:
            # Try to extract JSON by finding balanced braces
            logger.info("No markdown JSON block found, trying to extract raw JSON")
            json_str = self._extract_json_object(raw_output)
            if not json_str:
                logger.error(f"No JSON found in response. First 1000 chars: {raw_output[:1000]}")
                raise ValueError("No JSON data found in AI response")
            logger.info(f"Extracted JSON of length: {len(json_str)}")
        
        # Parse JSON
        try:
            data_dict = json.loads(json_str)
            logger.info(f"Successfully parsed JSON with keys: {list(data_dict.keys())}")
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON: {e}")
            logger.error(f"JSON string (first 500 chars): {repr(json_str[:500])}")
            raise ValueError(f"Invalid JSON in AI response: {e}")
        
        # Convert to Pydantic model
        price_targets = PriceTargetsSchema(
            pessimistic=data_dict.get("price_targets", {}).get("pessimistic"),
            realistic=data_dict.get("price_targets", {}).get("realistic"),
            optimistic=data_dict.get("price_targets", {}).get("optimistic"),
        )
        
        data = DeepDueDiligenceResult(
            ticker=data_dict.get("ticker", "UNKNOWN"),
            company_name=data_dict.get("company_name"),
            gomes_score=int(data_dict.get("gomes_score", 5)),
            thesis_status=data_dict.get("thesis_status", "STABLE"),
            inflection_point_status=data_dict.get("inflection_point_status", "UPCOMING"),
            upside_potential=str(data_dict.get("upside_potential", "N/A")),
            risk_level=data_dict.get("risk_level", "MEDIUM"),
            cash_runway_months=data_dict.get("cash_runway_months"),
            action_signal=data_dict.get("action_signal", "HOLD"),
            kelly_criterion_hint=float(data_dict.get("kelly_criterion_hint", 5)),
            price_targets=price_targets,
            green_line=data_dict.get("green_line"),
            red_line=data_dict.get("red_line"),
            key_milestones=data_dict.get("key_milestones", []),
            red_flags=data_dict.get("red_flags", []),
            edge=data_dict.get("edge"),
            catalysts=data_dict.get("catalysts"),
            risks=data_dict.get("risks"),
        )
        
        # Extract analysis text (everything before JSON)
        if json_match:
            analysis_text = raw_output[:json_match.start()].strip()
        else:
            analysis_text = raw_output
        
        # Clean up analysis text
        analysis_text = re.sub(r'=== ČÁST 2.*$', '', analysis_text, flags=re.DOTALL).strip()
        
        return analysis_text, data
    
    def _calculate_thesis_drift(
        self,
        ticker: str,
        new_data: DeepDueDiligenceResult,
    ) -> Optional[ThesisDriftResult]:
        """
        Calculate thesis drift by comparing with existing data.
        
        Args:
            ticker: Stock ticker
            new_data: New analysis data
            
        Returns:
            ThesisDriftResult or None if no existing data
        """
        stock = self.db.query(Stock).filter(
            Stock.ticker == ticker.upper()
        ).order_by(Stock.created_at.desc()).first()
        
        if not stock or not stock.gomes_score:
            return None
        
        # Simple drift calculation
        old_score = stock.gomes_score
        new_score = new_data.gomes_score
        score_change = new_score - old_score
        
        # Determine drift status
        if score_change >= 2:
            thesis_drift = "IMPROVED"
            alert_level = "INFO"
        elif score_change >= 0:
            thesis_drift = "STABLE"
            alert_level = "INFO"
        elif score_change >= -2:
            thesis_drift = "DETERIORATED"
            alert_level = "WARNING"
        else:
            thesis_drift = "BROKEN"
            alert_level = "CRITICAL"
        
        # Collect key changes
        key_changes = []
        if new_data.thesis_status != "STABLE":
            key_changes.append(f"Thesis status: {new_data.thesis_status}")
        if new_data.red_flags:
            key_changes.append(f"Red flags: {', '.join(new_data.red_flags[:3])}")
        if new_data.key_milestones:
            key_changes.append(f"Milestones: {', '.join(new_data.key_milestones[:3])}")
        
        return ThesisDriftResult(
            ticker=ticker,
            thesis_drift=thesis_drift,
            score_change=score_change,
            new_gomes_score=new_score,
            reasoning=f"Score changed from {old_score} to {new_score}",
            key_changes=key_changes,
            action_update=new_data.action_signal,
            alert_level=alert_level,
        )
    
    async def update_stock_from_analysis(
        self,
        result: DeepDueDiligenceResponse,
        analysis_source: str = "deep_dd",
    ) -> Stock:
        """
        Update or create stock record from analysis result.
        Also saves to score history for thesis drift tracking.
        
        Args:
            result: Analysis result
            analysis_source: Source of analysis (deep_dd, transcript, earnings, manual)
            
        Returns:
            Updated/created Stock model
        """
        data = result.data
        
        # Find or create stock
        stock = self.db.query(Stock).filter(
            Stock.ticker == data.ticker.upper()
        ).first()
        
        old_score = stock.gomes_score if stock else None
        
        if not stock:
            stock = Stock(ticker=data.ticker.upper())
            self.db.add(stock)
        
        # Update fields
        stock.company_name = data.company_name or stock.company_name
        stock.gomes_score = data.gomes_score
        stock.action_verdict = data.action_signal
        stock.edge = data.edge
        stock.catalysts = data.catalysts
        stock.risks = data.risks
        stock.entry_zone = f"Green: ${data.green_line}" if data.green_line else None
        
        # Map action to sentiment
        sentiment_map = {
            "BUY": "BULLISH",
            "ACCUMULATE": "BULLISH",
            "HOLD": "NEUTRAL",
            "TRIM": "BEARISH",
            "SELL": "BEARISH",
        }
        stock.sentiment = sentiment_map.get(data.action_signal, "NEUTRAL")
        
        # Set price targets
        if data.price_targets.realistic:
            stock.price_target = str(data.price_targets.realistic)
        
        self.db.commit()
        self.db.refresh(stock)
        
        # === SAVE TO SCORE HISTORY ===
        score_history = GomesScoreHistory(
            ticker=data.ticker.upper(),
            stock_id=stock.id,
            gomes_score=data.gomes_score,
            thesis_status=result.thesis_drift or "STABLE",
            action_signal=data.action_signal,
            price_at_analysis=data.current_price,
            analysis_source=analysis_source,
        )
        self.db.add(score_history)
        
        # === CREATE DRIFT ALERT IF NEEDED ===
        if old_score is not None and result.thesis_drift:
            score_change = data.gomes_score - old_score
            
            if result.thesis_drift == "BROKEN" or score_change <= -3:
                alert = ThesisDriftAlert(
                    ticker=data.ticker.upper(),
                    alert_type=AlertType.THESIS_BREAKING,
                    severity="CRITICAL",
                    old_score=old_score,
                    new_score=data.gomes_score,
                    message=f"THESIS BREAKING: {data.ticker} spadl z {old_score} na {data.gomes_score}/10. Zvazte prodej!",
                )
                self.db.add(alert)
            elif result.thesis_drift == "DETERIORATED":
                alert = ThesisDriftAlert(
                    ticker=data.ticker.upper(),
                    alert_type=AlertType.THESIS_DETERIORATING,
                    severity="WARNING",
                    old_score=old_score,
                    new_score=data.gomes_score,
                    message=f"Thesis deteriorating: {data.ticker} klesl z {old_score} na {data.gomes_score}/10.",
                )
                self.db.add(alert)
            elif result.thesis_drift == "IMPROVED" and score_change >= 2:
                alert = ThesisDriftAlert(
                    ticker=data.ticker.upper(),
                    alert_type=AlertType.THESIS_IMPROVING,
                    severity="INFO",
                    old_score=old_score,
                    new_score=data.gomes_score,
                    message=f"Thesis improving: {data.ticker} vzrostl z {old_score} na {data.gomes_score}/10!",
                )
                self.db.add(alert)
        
        self.db.commit()
        
        return stock
