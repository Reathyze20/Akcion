"""
Weekly Summary Service

Generates automated weekly investment summaries based on Mark Gomes transcripts,
score changes, and thesis drift alerts.

Clean Code Principles:
- Single Responsibility: Email generation only
- Type hints throughout
- Minimal dependencies
"""

from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_

from app.models.analysis import AnalystTranscript, TickerMention
from app.models.stock import Stock
from app.models.score_history import GomesScoreHistory, ThesisDriftAlert
from app.models.gomes import InvestmentVerdictModel
from app.models.trading import ActiveWatchlist


class WeeklySummary:
    """Generates weekly investment summary reports"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def generate_summary(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Generate comprehensive weekly summary.
        
        Args:
            start_date: Start of week (default: 7 days ago)
            end_date: End of week (default: today)
            
        Returns:
            Dictionary with summary data
        """
        if not end_date:
            end_date = datetime.utcnow()
        if not start_date:
            start_date = end_date - timedelta(days=7)
        
        return {
            "period": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat()
            },
            "transcripts": self._get_weekly_transcripts(start_date, end_date),
            "score_changes": self._get_score_changes(start_date, end_date),
            "new_signals": self._get_new_signals(start_date, end_date),
            "thesis_alerts": self._get_thesis_alerts(start_date, end_date),
            "watchlist_summary": self._get_watchlist_summary(),
            "top_picks": self._get_top_picks(),
        }
    
    def _get_weekly_transcripts(
        self,
        start_date: datetime,
        end_date: datetime
    ) -> List[Dict[str, Any]]:
        """Get transcripts from this week"""
        transcripts = self.db.query(AnalystTranscript).filter(
            and_(
                AnalystTranscript.date >= start_date.date(),
                AnalystTranscript.date <= end_date.date()
            )
        ).order_by(desc(AnalystTranscript.date)).all()
        
        return [
            {
                "source": t.source_name,
                "date": t.date.isoformat(),
                "tickers": t.detected_tickers,
                "summary": t.processed_summary[:300] if t.processed_summary else None
            }
            for t in transcripts
        ]
    
    def _get_score_changes(
        self,
        start_date: datetime,
        end_date: datetime
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Get stocks where Gomes score changed significantly"""
        
        # Get all score records in period
        recent_scores = self.db.query(GomesScoreHistory).filter(
            and_(
                GomesScoreHistory.recorded_at >= start_date,
                GomesScoreHistory.recorded_at <= end_date
            )
        ).all()
        
        # Group by ticker
        ticker_scores = {}
        for score in recent_scores:
            if score.ticker not in ticker_scores:
                ticker_scores[score.ticker] = []
            ticker_scores[score.ticker].append(score)
        
        # Find significant changes (±2 points or more)
        improved = []
        deteriorated = []
        
        for ticker, scores in ticker_scores.items():
            if len(scores) < 2:
                continue
            
            # Sort by date
            scores.sort(key=lambda x: x.recorded_at)
            old_score = scores[0].gomes_score
            new_score = scores[-1].gomes_score
            change = new_score - old_score
            
            if abs(change) >= 2:
                stock = self.db.query(Stock).filter(
                    Stock.ticker == ticker,
                    Stock.is_latest == True
                ).first()
                
                item = {
                    "ticker": ticker,
                    "old_score": old_score,
                    "new_score": new_score,
                    "change": change,
                    "company_name": stock.company_name if stock else None,
                    "action_verdict": stock.action_verdict if stock else None
                }
                
                if change > 0:
                    improved.append(item)
                else:
                    deteriorated.append(item)
        
        return {
            "improved": sorted(improved, key=lambda x: x["change"], reverse=True),
            "deteriorated": sorted(deteriorated, key=lambda x: x["change"])
        }
    
    def _get_new_signals(
        self,
        start_date: datetime,
        end_date: datetime
    ) -> List[Dict[str, Any]]:
        """Get new BUY/STRONG_BUY signals from this week"""
        verdicts = self.db.query(InvestmentVerdictModel).filter(
            and_(
                InvestmentVerdictModel.created_at >= start_date,
                InvestmentVerdictModel.created_at <= end_date,
                InvestmentVerdictModel.verdict.in_(['STRONG_BUY', 'BUY', 'ACCUMULATE']),
                InvestmentVerdictModel.passed_gomes_filter == True
            )
        ).order_by(desc(InvestmentVerdictModel.gomes_score)).all()
        
        return [
            {
                "ticker": v.ticker,
                "verdict": v.verdict,
                "gomes_score": v.gomes_score,
                "confidence": v.confidence,
                "lifecycle_phase": v.lifecycle_phase,
                "green_line": float(v.green_line) if v.green_line else None,
                "current_price": float(v.current_price) if v.current_price else None,
                "bull_case": v.bull_case,
            }
            for v in verdicts
        ]
    
    def _get_thesis_alerts(
        self,
        start_date: datetime,
        end_date: datetime
    ) -> List[Dict[str, Any]]:
        """Get thesis drift alerts from this week"""
        alerts = self.db.query(ThesisDriftAlert).filter(
            and_(
                ThesisDriftAlert.created_at >= start_date,
                ThesisDriftAlert.created_at <= end_date,
                ThesisDriftAlert.is_acknowledged == False
            )
        ).order_by(desc(ThesisDriftAlert.severity)).all()
        
        return [
            {
                "ticker": a.ticker,
                "alert_type": a.alert_type,
                "severity": a.severity,
                "old_score": a.old_score,
                "new_score": a.new_score,
                "price_change_pct": float(a.price_change_pct) if a.price_change_pct else None,
                "message": a.message,
            }
            for a in alerts
        ]
    
    def _get_watchlist_summary(self) -> Dict[str, Any]:
        """Get current watchlist statistics"""
        watchlist = self.db.query(ActiveWatchlist).filter(
            ActiveWatchlist.is_active == True
        ).all()
        
        if not watchlist:
            return {"total": 0, "by_verdict": {}}
        
        by_verdict = {}
        for item in watchlist:
            verdict = item.action_verdict or "UNKNOWN"
            by_verdict[verdict] = by_verdict.get(verdict, 0) + 1
        
        return {
            "total": len(watchlist),
            "by_verdict": by_verdict
        }
    
    def _get_top_picks(self) -> List[Dict[str, Any]]:
        """Get top 5 stocks by Gomes score"""
        watchlist = self.db.query(ActiveWatchlist).filter(
            ActiveWatchlist.is_active == True,
            ActiveWatchlist.gomes_score != None
        ).order_by(desc(ActiveWatchlist.gomes_score)).limit(5).all()
        
        return [
            {
                "ticker": item.ticker,
                "gomes_score": float(item.gomes_score) if item.gomes_score else None,
                "action_verdict": item.action_verdict,
                "investment_thesis": item.investment_thesis[:200] if item.investment_thesis else None
            }
            for item in watchlist
        ]
    
    def generate_email_body(self, summary: Dict[str, Any]) -> str:
        """
        Generate HTML email body from summary data.
        
        Args:
            summary: Summary dictionary from generate_summary()
            
        Returns:
            HTML email body
        """
        period = summary["period"]
        transcripts = summary["transcripts"]
        score_changes = summary["score_changes"]
        new_signals = summary["new_signals"]
        alerts = summary["thesis_alerts"]
        top_picks = summary["top_picks"]
        
        html = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                h1 {{ color: #2c3e50; border-bottom: 3px solid #3498db; padding-bottom: 10px; }}
                h2 {{ color: #34495e; margin-top: 30px; }}
                .ticker {{ font-weight: bold; color: #2980b9; }}
                .score-up {{ color: #27ae60; font-weight: bold; }}
                .score-down {{ color: #e74c3c; font-weight: bold; }}
                .verdict-buy {{ background-color: #d4edda; padding: 5px 10px; border-radius: 5px; }}
                .verdict-sell {{ background-color: #f8d7da; padding: 5px 10px; border-radius: 5px; }}
                .alert-critical {{ background-color: #f8d7da; padding: 10px; border-left: 4px solid #e74c3c; margin: 10px 0; }}
                .alert-warning {{ background-color: #fff3cd; padding: 10px; border-left: 4px solid #ffc107; margin: 10px 0; }}
                table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
                th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }}
                th {{ background-color: #3498db; color: white; }}
            </style>
        </head>
        <body>
            <h1>📊 Týdenní Investiční Přehled</h1>
            <p><strong>Období:</strong> {period['start'][:10]} - {period['end'][:10]}</p>
        """
        
        # Transcripts section
        if transcripts:
            html += "<h2>🎥 Co říkal Mark Gomes tento týden</h2>"
            for t in transcripts:
                html += f"""
                <div style="margin-bottom: 15px; padding: 10px; background-color: #ecf0f1; border-radius: 5px;">
                    <strong>{t['source']}</strong> - {t['date']}<br>
                    <strong>Zmíněné akcie:</strong> {', '.join(t['tickers'][:10])}<br>
                    {f"<em>{t['summary']}...</em>" if t['summary'] else ''}
                </div>
                """
        
        # Score improvements
        if score_changes["improved"]:
            html += "<h2>📈 Akcie se zlepšujícím skóre (BUY signals)</h2>"
            html += "<table><tr><th>Ticker</th><th>Staré skóre</th><th>Nové skóre</th><th>Změna</th><th>Akce</th></tr>"
            for stock in score_changes["improved"]:
                html += f"""
                <tr>
                    <td class="ticker">{stock['ticker']}</td>
                    <td>{stock['old_score']}</td>
                    <td class="score-up">{stock['new_score']}</td>
                    <td class="score-up">+{stock['change']}</td>
                    <td class="verdict-buy">{stock['action_verdict'] or 'N/A'}</td>
                </tr>
                """
            html += "</table>"
        
        # Score deteriorations
        if score_changes["deteriorated"]:
            html += "<h2>📉 Akcie s klesajícím skóre (REVIEW needed)</h2>"
            html += "<table><tr><th>Ticker</th><th>Staré skóre</th><th>Nové skóre</th><th>Změna</th><th>Akce</th></tr>"
            for stock in score_changes["deteriorated"]:
                html += f"""
                <tr>
                    <td class="ticker">{stock['ticker']}</td>
                    <td>{stock['old_score']}</td>
                    <td class="score-down">{stock['new_score']}</td>
                    <td class="score-down">{stock['change']}</td>
                    <td class="verdict-sell">{stock['action_verdict'] or 'N/A'}</td>
                </tr>
                """
            html += "</table>"
        
        # Thesis drift alerts
        if alerts:
            html += "<h2>🚨 Thesis Drift Alerts</h2>"
            for alert in alerts:
                alert_class = "alert-critical" if alert['severity'] == 'CRITICAL' else "alert-warning"
                html += f"""
                <div class="{alert_class}">
                    <strong class="ticker">{alert['ticker']}</strong> - {alert['alert_type']}<br>
                    Score: {alert['old_score']} → {alert['new_score']}<br>
                    {alert['message']}
                </div>
                """
        
        # Top picks
        if top_picks:
            html += "<h2>⭐ Top 5 High Conviction Stocks</h2>"
            html += "<table><tr><th>Ticker</th><th>Gomes Score</th><th>Verdict</th><th>Thesis</th></tr>"
            for stock in top_picks:
                html += f"""
                <tr>
                    <td class="ticker">{stock['ticker']}</td>
                    <td><strong>{stock['gomes_score']}/10</strong></td>
                    <td class="verdict-buy">{stock['action_verdict'] or 'N/A'}</td>
                    <td>{stock['investment_thesis'] or 'N/A'}</td>
                </tr>
                """
            html += "</table>"
        
        html += """
            <hr style="margin-top: 40px;">
            <p style="color: #7f8c8d; font-size: 12px;">
                Tento email byl automaticky generován systémem Akcion Investment Intelligence.<br>
                Pro více detailů se přihlas do aplikace.
            </p>
        </body>
        </html>
        """
        
        return html


def send_weekly_summary_email(
    db: Session,
    recipient_email: str,
    smtp_settings: Optional[Dict[str, str]] = None
) -> bool:
    """
    Generate and send weekly summary email.
    
    Args:
        db: Database session
        recipient_email: Recipient email address
        smtp_settings: SMTP configuration (host, port, username, password)
        
    Returns:
        True if email sent successfully
    """
    summary_service = WeeklySummary(db)
    summary = summary_service.generate_summary()
    email_body = summary_service.generate_email_body(summary)
    
    # Import email sending functionality
    try:
        from app.services.notifications import send_email
        
        subject = f"📊 Týdenní Investiční Přehled - {summary['period']['end'][:10]}"
        
        return send_email(
            to_email=recipient_email,
            subject=subject,
            body=email_body,
            smtp_settings=smtp_settings
        )
    except Exception as e:
        print(f"Failed to send weekly summary: {e}")
        return False
