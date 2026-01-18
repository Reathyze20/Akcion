"""
Signal Generator - Creates actionable trading signals
"""
from typing import List, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from app.models.trading import TradingSignal, MLPrediction, ActiveWatchlist
from app.models.stock import Stock
from app.trading.kelly import KellyCriterion
from loguru import logger


class SignalGenerator:
    """Generates final trading signals combining ML predictions with Kelly sizing"""
    
    def __init__(self, db: Session):
        self.db = db
        self.kelly_calc = KellyCriterion(max_position=0.25, fractional_kelly=0.5)
    
    def generate_signal(
        self,
        prediction: MLPrediction,
        stop_loss_pct: float = 0.10,
        risk_reward_min: float = 2.0
    ) -> Optional[TradingSignal]:
        """
        Generate trading signal from ML prediction
        
        Args:
            prediction: ML prediction object
            stop_loss_pct: Stop loss percentage (default 10%)
            risk_reward_min: Minimum risk/reward ratio (default 2.0)
        
        Returns:
            TradingSignal or None if signal doesn't meet criteria
        """
        logger.info(f"Generating signal for {prediction.ticker}")
        
        # Only generate BUY signals for UP predictions
        if prediction.prediction_type != 'UP':
            logger.debug(f"Skipping {prediction.ticker} - prediction type is {prediction.prediction_type}")
            return None
        
        # Calculate Kelly position size
        kelly_result = self.kelly_calc.calculate_from_prediction(
            confidence=float(prediction.confidence),
            current_price=float(prediction.current_price),
            predicted_price=float(prediction.predicted_price),
            stop_loss_pct=stop_loss_pct
        )
        
        kelly_size = kelly_result['kelly_size']
        risk_reward = kelly_result['risk_reward_ratio']
        
        # Filter out weak signals
        if kelly_size < 0.05:  # Less than 5% position
            logger.debug(f"Skipping {prediction.ticker} - Kelly size too small ({kelly_size:.2%})")
            return None
        
        if risk_reward < risk_reward_min:
            logger.debug(f"Skipping {prediction.ticker} - R/R ratio too low ({risk_reward:.2f})")
            return None
        
        # Calculate entry/target/stop prices
        entry_price = float(prediction.current_price)
        target_price = float(prediction.predicted_price)
        stop_loss = entry_price * (1 - stop_loss_pct)
        
        # Get analyst source
        watchlist = self.db.query(ActiveWatchlist).filter(
            ActiveWatchlist.ticker == prediction.ticker,
            ActiveWatchlist.is_active == True
        ).first()
        
        analyst_source_id = watchlist.stock_id if watchlist else None
        
        # Create signal
        signal = TradingSignal(
            ticker=prediction.ticker,
            signal_type='BUY',
            ml_prediction_id=prediction.id,
            analyst_source_id=analyst_source_id,
            confidence=prediction.confidence,
            kelly_size=kelly_size,
            entry_price=entry_price,
            target_price=target_price,
            stop_loss=stop_loss,
            risk_reward_ratio=risk_reward,
            expires_at=prediction.valid_until,
            notes=f"ML: {prediction.prediction_type} | Kelly: {kelly_size:.1%} | R/R: {risk_reward:.2f}"
        )
        
        # Update prediction with Kelly size
        prediction.kelly_position_size = kelly_size
        
        self.db.add(signal)
        self.db.commit()
        self.db.refresh(signal)
        
        logger.info(f"Generated BUY signal for {prediction.ticker}: Kelly {kelly_size:.1%}, R/R {risk_reward:.2f}")
        return signal
    
    def generate_signal_from_dict(
        self,
        prediction: dict,
        stop_loss_pct: float = 0.10,
        risk_reward_min: float = 2.0
    ) -> Optional[TradingSignal]:
        """
        Generate trading signal from ML prediction dict (not ORM object)
        
        Args:
            prediction: Dict with prediction data from ml_engine.predict()
            stop_loss_pct: Stop loss percentage (default 10%)
            risk_reward_min: Minimum risk/reward ratio (default 2.0)
        
        Returns:
            TradingSignal or None if signal doesn't meet criteria
        """
        ticker = prediction['ticker']
        logger.info(f"Generating signal for {ticker} from dict")
        
        # Only generate BUY signals for UP predictions
        if prediction['prediction_type'] != 'UP':
            logger.debug(f"Skipping {ticker} - prediction type is {prediction['prediction_type']}")
            return None
        
        # Calculate Kelly position size
        kelly_result = self.kelly_calc.calculate_from_prediction(
            confidence=float(prediction['confidence']),
            current_price=float(prediction['current_price']),
            predicted_price=float(prediction['predicted_price']),
            stop_loss_pct=stop_loss_pct
        )
        
        kelly_size = kelly_result['kelly_size']
        risk_reward = kelly_result['risk_reward_ratio']
        
        # Filter out weak signals
        if kelly_size < 0.05:  # Less than 5% position
            logger.debug(f"Skipping {ticker} - Kelly size too small ({kelly_size:.2%})")
            return None
        
        if risk_reward < risk_reward_min:
            logger.debug(f"Skipping {ticker} - R/R ratio too low ({risk_reward:.2f})")
            return None
        
        # Calculate entry/target/stop prices
        entry_price = float(prediction['current_price'])
        target_price = float(prediction['predicted_price'])
        stop_loss = entry_price * (1 - stop_loss_pct)
        
        # Get watchlist entry for context
        watchlist = self.db.query(ActiveWatchlist).filter(
            ActiveWatchlist.ticker == ticker,
            ActiveWatchlist.is_active == True
        ).first()
        
        analyst_source_id = watchlist.stock_id if watchlist else None
        
        # Get the ML prediction record from DB (if saved)
        ml_prediction = self.db.query(MLPrediction).filter(
            MLPrediction.ticker == ticker
        ).order_by(MLPrediction.created_at.desc()).first()
        
        # Create signal
        valid_until = datetime.utcnow() + timedelta(days=prediction.get('horizon_days', 7))
        
        signal = TradingSignal(
            ticker=ticker,
            signal_type='BUY',
            ml_prediction_id=ml_prediction.id if ml_prediction else None,
            analyst_source_id=analyst_source_id,
            confidence=prediction['confidence'],
            kelly_size=kelly_size,
            entry_price=entry_price,
            target_price=target_price,
            stop_loss=stop_loss,
            risk_reward_ratio=risk_reward,
            expires_at=valid_until,
            notes=f"ML: {prediction['prediction_type']} | Kelly: {kelly_size:.1%} | R/R: {risk_reward:.2f} | Quality: {prediction.get('quality', 'N/A')}"
        )
        
        # Update ML prediction with Kelly size if exists
        if ml_prediction:
            ml_prediction.kelly_position_size = kelly_size
        
        self.db.add(signal)
        self.db.commit()
        self.db.refresh(signal)
        
        logger.info(f"Generated BUY signal for {ticker}: Kelly {kelly_size:.1%}, R/R {risk_reward:.2f}")
        return signal

    def generate_signals_batch(
        self,
        predictions: List[MLPrediction],
        **kwargs
    ) -> List[TradingSignal]:
        """Generate signals for multiple predictions"""
        signals = []
        
        for prediction in predictions:
            try:
                signal = self.generate_signal(prediction, **kwargs)
                if signal:
                    signals.append(signal)
            except Exception as e:
                logger.error(f"Failed to generate signal for {prediction.ticker}: {e}")
        
        logger.info(f"Generated {len(signals)} signals from {len(predictions)} predictions")
        return signals
    
    def get_active_signals(self, limit: int = 20) -> List[dict]:
        """
        Get active trading signals with enriched data
        
        Returns:
            List of dicts with signal + analyst + prediction data
        """
        from sqlalchemy import text
        
        query = text("""
            SELECT 
                ts.id,
                ts.ticker,
                ts.signal_type,
                ts.confidence,
                ts.kelly_size,
                ts.entry_price,
                ts.target_price,
                ts.stop_loss,
                ts.risk_reward_ratio,
                ts.created_at,
                ts.expires_at,
                mp.prediction_type as ml_prediction,
                mp.predicted_price,
                mp.model_version,
                s.action_verdict as analyst_verdict,
                s.sentiment as analyst_sentiment,
                s.company_name
            FROM trading_signals ts
            LEFT JOIN ml_predictions mp ON ts.ml_prediction_id = mp.id
            LEFT JOIN active_watchlist aw ON ts.ticker = aw.ticker
            LEFT JOIN stocks s ON aw.stock_id = s.id
            WHERE ts.is_active = TRUE
            ORDER BY ts.kelly_size DESC, ts.created_at DESC
            LIMIT :limit
        """)
        
        result = self.db.execute(query, {'limit': limit})
        signals = []
        
        for row in result:
            signals.append({
                'id': row.id,
                'ticker': row.ticker,
                'signal_type': row.signal_type,
                'ai_prediction': row.ml_prediction,
                'confidence': float(row.confidence),
                'kelly_position_size': f"{float(row.kelly_size) * 100:.1f}%",
                'entry_price': float(row.entry_price) if row.entry_price else None,
                'target_price': float(row.target_price) if row.target_price else None,
                'stop_loss': float(row.stop_loss) if row.stop_loss else None,
                'risk_reward_ratio': float(row.risk_reward_ratio) if row.risk_reward_ratio else None,
                'analyst_source': {
                    'verdict': row.analyst_verdict,
                    'sentiment': row.analyst_sentiment,
                    'company_name': row.company_name
                },
                'model_version': row.model_version,
                'created_at': row.created_at.isoformat() if row.created_at else None,
                'expires_at': row.expires_at.isoformat() if row.expires_at else None
            })
        
        return signals
    
    def expire_old_signals(self) -> int:
        """Mark expired signals as inactive"""
        from sqlalchemy import text
        
        result = self.db.execute(text("""
            UPDATE trading_signals
            SET is_active = FALSE
            WHERE is_active = TRUE
            AND (
                expires_at < NOW() OR
                created_at < NOW() - INTERVAL '7 days'
            )
        """))
        
        count = result.rowcount
        self.db.commit()
        
        logger.info(f"Expired {count} old signals")
        return count
