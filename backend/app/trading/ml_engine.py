"""
ML Prediction Engine - Neural Forecasting with PatchTST
Uses NeuralForecast library for robust time-series predictions

CRITICAL: This module handles financial predictions for family security.
All predictions include confidence intervals and quality assessment.
Never allow uncertain predictions to be acted upon.
"""
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import text
import numpy as np
import pandas as pd

from app.models.trading import OHLCVData, MLPrediction, ActiveWatchlist
from loguru import logger

# NeuralForecast imports with graceful fallback
try:
    from neuralforecast import NeuralForecast
    from neuralforecast.models import PatchTST
    from neuralforecast.losses.pytorch import MAE
    NEURALFORECAST_AVAILABLE = True
except ImportError:
    NEURALFORECAST_AVAILABLE = False
    logger.warning("NeuralForecast not available. Install: pip install neuralforecast")


class MLEngineError(Exception):
    """Custom exception for ML Engine errors"""
    pass


class InsufficientDataError(MLEngineError):
    """Raised when there's not enough data for training"""
    pass


class PredictionQuality:
    """Confidence assessment levels"""
    HIGH = "HIGH_CONFIDENCE"      # CI width < 10% of price - Safe to trade
    MEDIUM = "MEDIUM_CONFIDENCE"  # CI width 10-20% - Trade with caution
    LOW = "LOW_CONFIDENCE"        # CI width > 20% - DO NOT TRADE
    FAILED = "PREDICTION_FAILED"  # Model failed - DO NOT TRADE


class MLPredictionEngine:
    """
    Neural Forecasting Engine using PatchTST Transformer
    
    Provides stock price predictions with confidence intervals and quality assessment.
    Automatically marks low-quality predictions to prevent risky trades.
    
    Key Features:
    - PatchTST model for time-series forecasting
    - 80% and 90% confidence intervals
    - Automatic quality assessment
    - Robust error handling
    - Database persistence
    """
    
    def __init__(
        self,
        db: Session,
        horizon: int = 5,
        input_size: int = 60,
        confidence_levels: List[int] = [80, 90],
        quality_threshold_pct: float = 10.0,
        min_data_points: int = 60
    ):
        """
        Initialize ML Prediction Engine
        
        Args:
            db: Database session
            horizon: Days to predict ahead (default 5)
            input_size: Historical window size (default 60 days)
            confidence_levels: CI levels to compute (default [80, 90])
            quality_threshold_pct: Max acceptable 90% CI width as % of price (default 10%)
            min_data_points: Minimum required data points (default 60)
        """
        if not NEURALFORECAST_AVAILABLE:
            logger.error("❌ NeuralForecast not installed - ML predictions disabled")
            logger.info("Install with: pip install neuralforecast torch")
        
        self.db = db
        self.horizon = horizon
        self.input_size = input_size
        self.confidence_levels = confidence_levels
        self.quality_threshold_pct = quality_threshold_pct
        self.min_data_points = min_data_points
        self.model_version = "PatchTST-v1.0"
        self.lookback_days = input_size  # Alias for compatibility
        
        # PatchTST model configuration
        self.model_config = {
            'h': horizon,                    # Forecast horizon
            'input_size': input_size,        # Lookback window
            'patch_len': 16,                 # Patch length for transformer
            'stride': 8,                     # Stride between patches
            'hidden_size': 128,              # Hidden layer size
            'n_heads': 4,                    # Attention heads
            'max_steps': 500,                # Training steps
            'val_check_steps': 50,           # Validation frequency
            'early_stop_patience_steps': 3,  # Early stopping patience
            'learning_rate': 1e-3,           # Learning rate
            'scaler_type': 'standard',       # Data normalization
            'loss': MAE() if NEURALFORECAST_AVAILABLE else None,
            'random_seed': 42,
            'alias': 'PatchTST'
        }
        
        logger.info(
            f"✅ ML Engine initialized: horizon={horizon}d, "
            f"input_size={input_size}d, quality_threshold={quality_threshold_pct}%"
        )
    
    def predict(self, ticker: str, save_to_db: bool = True) -> Optional[Dict]:
        """
        Generate ML prediction for a ticker with confidence intervals
        
        Args:
            ticker: Stock ticker symbol
            save_to_db: Whether to persist prediction (default True)
        
        Returns:
            Dict with prediction, confidence intervals, and quality assessment
            Returns None if insufficient data or model unavailable
        """
        if not NEURALFORECAST_AVAILABLE:
            logger.warning(f"⚠️  Skipping {ticker} - NeuralForecast not available")
            return self._fallback_prediction(ticker)
        
        try:
            logger.info(f"🔮 Generating prediction for {ticker}...")
            
            # Step 1: Fetch historical data
            df = self._get_historical_data(ticker)
            if df is None or len(df) < self.min_data_points:
                raise InsufficientDataError(
                    f"Need {self.min_data_points} days, got {len(df) if df is not None else 0}"
                )
            
            current_price = float(df['close'].iloc[-1])
            logger.info(f"  Current price: ${current_price:.2f}, Data points: {len(df)}")
            
            # Step 2: Prepare data for NeuralForecast
            nf_df = self._prepare_neuralforecast_data(df, ticker)
            
            # Step 3: Train model and generate predictions
            predictions_df = self._train_and_predict(nf_df)
            
            if predictions_df is None:
                raise MLEngineError("Model training failed")
            
            # Step 4: Extract confidence intervals
            pred_dict = self._extract_predictions(predictions_df)
            
            # Step 5: Assess prediction quality
            quality, metrics = self._assess_quality(pred_dict, current_price)
            
            # Step 6: Determine trading direction
            predicted_price = pred_dict['point_prediction']
            price_change_pct = ((predicted_price - current_price) / current_price) * 100
            
            prediction_type, confidence = self._determine_direction(
                price_change_pct, quality
            )
            
            # Step 7: Prepare result
            result = {
                'ticker': ticker,
                'prediction_type': prediction_type,
                'confidence': confidence,
                'current_price': current_price,
                'predicted_price': predicted_price,
                'price_change_pct': price_change_pct,
                'horizon_days': self.horizon,
                'quality': quality,
                'ci_80_lower': pred_dict['ci_80_lower'],
                'ci_80_upper': pred_dict['ci_80_upper'],
                'ci_90_lower': pred_dict['ci_90_lower'],
                'ci_90_upper': pred_dict['ci_90_upper'],
                'ci_90_width_pct': metrics['ci_90_width_pct'],
                'quality_reason': metrics['reason'],
                'model_version': self.model_version,
                'data_points_used': len(nf_df),
                'created_at': datetime.utcnow()
            }
            
            # Step 8: Save to database
            if save_to_db:
                self._save_to_database(result)
            
            # Log result with quality indicator
            quality_emoji = "✅" if quality == PredictionQuality.HIGH else \
                           "⚠️" if quality == PredictionQuality.MEDIUM else "❌"
            
            logger.info(
                f"{quality_emoji} {ticker}: {prediction_type} ({confidence:.0%}), "
                f"${current_price:.2f} → ${predicted_price:.2f} ({price_change_pct:+.1f}%), "
                f"Quality: {quality}"
            )
            
            return result
            
        except InsufficientDataError as e:
            logger.warning(f"⚠️  {ticker}: Insufficient data - {e}")
            return None
            
        except Exception as e:
            logger.error(f"❌ {ticker}: Prediction failed - {e}", exc_info=True)
            return None
    
    def predict_batch(self, tickers: List[str]) -> Dict[str, Optional[Dict]]:
        """
        Generate predictions for multiple tickers
        
        Args:
            tickers: List of stock ticker symbols
        
        Returns:
            Dict mapping ticker to prediction result (or None if failed)
        """
        results = {}
        total = len(tickers)
        
        logger.info(f"📊 Starting batch prediction for {total} tickers...")
        
        for idx, ticker in enumerate(tickers, 1):
            logger.info(f"  [{idx}/{total}] Processing {ticker}...")
            try:
                result = self.predict(ticker, save_to_db=True)
                results[ticker] = result
            except Exception as e:
                logger.error(f"  ❌ {ticker} failed: {e}")
                results[ticker] = None
        
        # Summary statistics
        successful = sum(1 for r in results.values() if r is not None)
        high_quality = sum(
            1 for r in results.values()
            if r and r.get('quality') == PredictionQuality.HIGH
        )
        low_quality = sum(
            1 for r in results.values()
            if r and r.get('quality') == PredictionQuality.LOW
        )
        
        logger.info(
            f"✅ Batch complete: {successful}/{total} successful, "
            f"{high_quality} high quality, {low_quality} low quality"
        )
        
        return results
    
    def _get_historical_data(self, ticker: str) -> Optional[pd.DataFrame]:
        """
        Fetch historical OHLCV data from database
        
        Args:
            ticker: Stock ticker
        
        Returns:
            DataFrame with time, close columns or None if no data
        """
        try:
            # Use raw SQL for better performance
            query = text("""
                SELECT time, close
                FROM ohlcv_data
                WHERE ticker = :ticker
                ORDER BY time DESC
                LIMIT :limit
            """)
            
            result = self.db.execute(
                query,
                {"ticker": ticker, "limit": self.input_size + 30}  # Extra buffer
            )
            
            rows = result.fetchall()
            
            if not rows:
                logger.warning(f"  No OHLCV data found for {ticker}")
                return None
            
            # Convert to DataFrame and reverse to chronological order
            df = pd.DataFrame(rows, columns=['time', 'close'])
            df = df.sort_values('time').reset_index(drop=True)
            df['close'] = df['close'].astype(float)
            
            return df
            
        except Exception as e:
            logger.error(f"  Failed to fetch data for {ticker}: {e}")
            return None
    
    def _prepare_neuralforecast_data(
        self,
        df: pd.DataFrame,
        ticker: str
    ) -> pd.DataFrame:
        """
        Prepare data in NeuralForecast format
        
        Args:
            df: Raw OHLCV DataFrame
            ticker: Stock ticker (for unique_id)
        
        Returns:
            DataFrame with columns: unique_id, ds, y
        """
        nf_df = pd.DataFrame({
            'unique_id': ticker,
            'ds': pd.to_datetime(df['time']),
            'y': df['close']
        })
        
        # Remove NaN values
        nf_df = nf_df.dropna()
        
        # Ensure chronological order
        nf_df = nf_df.sort_values('ds').reset_index(drop=True)
        
        return nf_df
    
    def _train_and_predict(self, df: pd.DataFrame) -> Optional[pd.DataFrame]:
        """
        Train PatchTST model and generate predictions with confidence intervals
        
        Args:
            df: Prepared NeuralForecast DataFrame
        
        Returns:
            DataFrame with predictions and confidence intervals, or None if failed
        """
        try:
            # Initialize PatchTST model
            model = PatchTST(**self.model_config)
            
            # Create NeuralForecast instance
            nf = NeuralForecast(
                models=[model],
                freq='D'  # Daily frequency
            )
            
            # Train and generate predictions with cross-validation
            logger.debug("  Training PatchTST model...")
            
            predictions = nf.cross_validation(
                df=df,
                val_size=self.horizon,
                test_size=self.horizon,
                n_windows=None,
                level=self.confidence_levels  # [80, 90] confidence intervals
            )
            
            # Get latest forecast
            predictions = predictions.reset_index()
            predictions = predictions.sort_values('ds', ascending=False).head(1)
            
            return predictions
            
        except Exception as e:
            logger.error(f"  Model training failed: {e}", exc_info=True)
            return None
    
    def _extract_predictions(self, pred_df: pd.DataFrame) -> Dict:
        """
        Extract prediction values from NeuralForecast output
        
        Args:
            pred_df: Predictions DataFrame
        
        Returns:
            Dict with point prediction and confidence intervals
        """
        return {
            'point_prediction': float(pred_df['PatchTST'].iloc[0]),
            'ci_80_lower': float(pred_df['PatchTST-lo-80'].iloc[0]),
            'ci_80_upper': float(pred_df['PatchTST-hi-80'].iloc[0]),
            'ci_90_lower': float(pred_df['PatchTST-lo-90'].iloc[0]),
            'ci_90_upper': float(pred_df['PatchTST-hi-90'].iloc[0])
        }
    
    def _assess_quality(
        self,
        pred: Dict,
        current_price: float
    ) -> Tuple[str, Dict]:
        """
        Assess prediction quality based on confidence interval width
        
        Args:
            pred: Prediction dictionary with CIs
            current_price: Current stock price
        
        Returns:
            Tuple of (quality_level, metrics_dict)
        """
        try:
            # Calculate CI widths
            ci_90_width = pred['ci_90_upper'] - pred['ci_90_lower']
            ci_80_width = pred['ci_80_upper'] - pred['ci_80_lower']
            
            # Width as percentage of current price
            ci_90_width_pct = (ci_90_width / current_price) * 100
            ci_80_width_pct = (ci_80_width / current_price) * 100
            
            # Assess quality - BE CONSERVATIVE
            if ci_90_width_pct > self.quality_threshold_pct * 2:
                quality = PredictionQuality.LOW
                reason = f"90% CI extremely wide: {ci_90_width_pct:.1f}% of price - DO NOT TRADE"
            elif ci_90_width_pct > self.quality_threshold_pct:
                quality = PredictionQuality.MEDIUM
                reason = f"90% CI moderate: {ci_90_width_pct:.1f}% of price - Trade with caution"
            else:
                quality = PredictionQuality.HIGH
                reason = f"90% CI tight: {ci_90_width_pct:.1f}% of price - Safe to trade"
            
            metrics = {
                'ci_90_width_pct': ci_90_width_pct,
                'ci_80_width_pct': ci_80_width_pct,
                'reason': reason
            }
            
            return quality, metrics
            
        except Exception as e:
            logger.error(f"  Quality assessment failed: {e}")
            return PredictionQuality.LOW, {'reason': f'Assessment error: {str(e)}'}
    
    def _determine_direction(
        self,
        price_change_pct: float,
        quality: str
    ) -> Tuple[str, float]:
        """
        Determine prediction direction and confidence
        
        Args:
            price_change_pct: Predicted price change percentage
            quality: Prediction quality level
        
        Returns:
            Tuple of (prediction_type, confidence)
        """
        # DO NOT TRADE on low quality predictions
        if quality == PredictionQuality.LOW:
            return 'NEUTRAL', 0.3
        
        # Determine direction based on price change
        if price_change_pct > 2.0:
            prediction_type = 'UP'
            base_confidence = 0.75 if quality == PredictionQuality.HIGH else 0.55
        elif price_change_pct < -2.0:
            prediction_type = 'DOWN'
            base_confidence = 0.75 if quality == PredictionQuality.HIGH else 0.55
        else:
            prediction_type = 'NEUTRAL'
            base_confidence = 0.5
        
        # Scale confidence by magnitude of change (more change = more confidence)
        magnitude_factor = min(abs(price_change_pct) / 10.0, 1.0)
        confidence = base_confidence * (0.7 + 0.3 * magnitude_factor)
        
        return prediction_type, round(confidence, 4)
    
    def _save_to_database(self, result: Dict) -> None:
        """
        Save prediction to ml_predictions table
        
        Args:
            result: Prediction result dictionary
        """
        try:
            # Calculate Kelly position size
            kelly_size = self._calculate_kelly(
                result['confidence'],
                result['prediction_type']
            )
            
            # Get watchlist entry
            watchlist = self.db.query(ActiveWatchlist).filter(
                ActiveWatchlist.ticker == result['ticker'],
                ActiveWatchlist.is_active == True
            ).first()
            
            # Create MLPrediction record
            prediction = MLPrediction(
                ticker=result['ticker'],
                prediction_type=result['prediction_type'],
                confidence=result['confidence'],
                predicted_price=result['predicted_price'],
                current_price=result['current_price'],
                kelly_position_size=kelly_size,
                model_version=result['model_version'],
                horizon_days=result['horizon_days'],
                created_at=result['created_at'],
                valid_until=result['created_at'] + timedelta(days=result['horizon_days']),
                watchlist_id=watchlist.id if watchlist else None
            )
            
            self.db.add(prediction)
            self.db.commit()
            
            logger.debug(f"  Saved prediction to database (Kelly: {kelly_size:.2%})")
            
        except Exception as e:
            logger.error(f"  Failed to save prediction: {e}")
            self.db.rollback()
            # Don't raise - prediction is still valid even if save fails
    
    def _calculate_kelly(self, confidence: float, prediction_type: str) -> float:
        """
        Calculate Kelly Criterion position size
        
        Args:
            confidence: Prediction confidence (0-1)
            prediction_type: UP, DOWN, or NEUTRAL
        
        Returns:
            Kelly position size (0-0.25)
        """
        if prediction_type == 'NEUTRAL' or confidence < 0.5:
            return 0.0
        
        # Conservative Kelly: half-Kelly with cap
        win_loss_ratio = 1.5  # Assume 1.5:1 win/loss ratio for stocks
        win_probability = confidence
        
        kelly = (win_loss_ratio * win_probability - (1 - win_probability)) / win_loss_ratio
        kelly = max(0, kelly)  # No negative
        kelly = kelly * 0.5    # Half-Kelly for safety
        kelly = min(kelly, 0.25)  # Cap at 25% position
        
        return round(kelly, 4)
    
    def _fallback_prediction(self, ticker: str) -> Optional[Dict]:
        """
        Simple fallback prediction when NeuralForecast unavailable
        
        Args:
            ticker: Stock ticker
        
        Returns:
            Basic prediction dict or None
        """
        try:
            df = self._get_historical_data(ticker)
            if df is None or len(df) < 30:
                return None
            
            current_price = float(df['close'].iloc[-1])
            
            # Simple trend analysis
            recent_avg = df['close'].iloc[-5:].mean()
            older_avg = df['close'].iloc[-20:-5].mean()
            trend = (recent_avg - older_avg) / older_avg
            
            predicted_price = current_price * (1 + trend * 0.5)
            
            return {
                'ticker': ticker,
                'prediction_type': 'NEUTRAL',
                'confidence': 0.4,
                'current_price': current_price,
                'predicted_price': predicted_price,
                'price_change_pct': ((predicted_price - current_price) / current_price) * 100,
                'horizon_days': self.horizon,
                'quality': PredictionQuality.LOW,
                'quality_reason': 'Fallback prediction - NeuralForecast unavailable',
                'model_version': 'fallback-v1',
                'data_points_used': len(df)
            }
            
        except Exception as e:
            logger.error(f"  Fallback prediction failed: {e}")
            return None
    
    def get_latest_prediction(self, ticker: str) -> Optional[MLPrediction]:
        """
        Get most recent valid prediction for a ticker
        
        Args:
            ticker: Stock ticker
        
        Returns:
            MLPrediction object or None
        """
        return self.db.query(MLPrediction).filter(
            MLPrediction.ticker == ticker,
            MLPrediction.valid_until > datetime.utcnow()
        ).order_by(MLPrediction.created_at.desc()).first()


# ==========================================
# Convenience Functions
# ==========================================

def create_ml_engine(
    db: Session,
    horizon: int = 5,
    quality_threshold: float = 10.0
) -> MLPredictionEngine:
    """
    Factory function to create ML Engine
    
    Args:
        db: Database session
        horizon: Prediction horizon in days
        quality_threshold: Max CI width as % of price
    
    Returns:
        Configured MLPredictionEngine instance
    """
    return MLPredictionEngine(
        db=db,
        horizon=horizon,
        quality_threshold_pct=quality_threshold
    )

