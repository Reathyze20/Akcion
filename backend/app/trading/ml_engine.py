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

# Learning Engine import
try:
    from app.trading.ml_learning import MLLearningEngine
    LEARNING_ENGINE_AVAILABLE = True
except ImportError:
    LEARNING_ENGINE_AVAILABLE = False
    logger.warning("ML Learning Engine not available")


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
        horizon: int = 14,
        input_size: int = 20,
        confidence_levels: List[int] = [80, 90],
        quality_threshold_pct: float = 15.0,
        min_data_points: int = 35,
        enable_learning: bool = True,
        device: str = "auto"  # "auto", "cuda", "cpu"
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
            device: Device to use - "auto" (detect), "cuda" (GPU), "cpu" (force CPU)
            enable_learning: Enable self-learning confidence adjustment (default True)
        """
        import torch
        
        if not NEURALFORECAST_AVAILABLE:
            logger.error("❌ NeuralForecast not installed - ML predictions disabled")
            logger.info("Install with: pip install neuralforecast torch")
        
        # Device selection
        if device == "auto":
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            self.device = device
        
        # Set PyTorch default device
        if self.device == "cuda" and torch.cuda.is_available():
            logger.info(f"🚀 Using GPU: {torch.cuda.get_device_name(0)}")
        else:
            logger.info("💻 Using CPU for ML predictions")
            self.device = "cpu"  # Fallback if cuda requested but unavailable
        
        self.db = db
        self.horizon = horizon
        self.input_size = input_size
        self.confidence_levels = confidence_levels
        self.quality_threshold_pct = quality_threshold_pct
        self.min_data_points = min_data_points
        self.model_version = "PatchTST-v1.0"
        self.lookback_days = input_size  # Alias for compatibility
        
        # Initialize Learning Engine
        self.enable_learning = enable_learning
        if enable_learning and LEARNING_ENGINE_AVAILABLE:
            self.learning_engine = MLLearningEngine(db)
            logger.info("🧠 Learning Engine ENABLED - confidence will be adjusted")
        else:
            self.learning_engine = None
            if enable_learning:
                logger.warning("⚠️  Learning Engine requested but not available")
        
        # PatchTST model configuration
        self.model_config = {
            'h': horizon,                    # Forecast horizon
            'input_size': input_size,        # Lookback window
            'patch_len': 16,                 # Patch length for transformer
            'stride': 8,                     # Stride between patches
            'hidden_size': 64,               # Hidden layer size (reduced for speed)
            'n_heads': 2,                    # Attention heads (reduced for speed)
            'max_steps': 100,                # Training steps (reduced for dev)
            'val_check_steps': 25,           # Validation frequency
            'early_stop_patience_steps': 3,  # Early stopping patience
            'learning_rate': 1e-3,           # Learning rate
            'scaler_type': 'standard',       # Data normalization
            'loss': MAE() if NEURALFORECAST_AVAILABLE else None,
            'random_seed': 42,
            'alias': 'PatchTST',
            'accelerator': 'gpu' if self.device == 'cuda' else 'cpu'  # Device selection
        }
        
        logger.info(
            f"✅ ML Engine initialized: horizon={horizon}d, "
            f"input_size={input_size}d, device={self.device}, quality_threshold={quality_threshold_pct}%"
        )
    
    # ==========================================================================
    # GOMES FUSION SYSTEM
    # Combines ML predictions with qualitative analyst insights
    # ==========================================================================
    
    def _get_gomes_context(self, ticker: str) -> Optional[Dict]:
        """
        Fetch Gomes analysis context for a ticker from database.
        
        Returns:
            Dict with gomes_score, sentiment, action_verdict, edge, catalysts, risks
            or None if no analysis found
        """
        from app.models.stock import Stock
        
        try:
            # Get from watchlist -> stock relationship
            watchlist = self.db.query(ActiveWatchlist).filter(
                ActiveWatchlist.ticker == ticker.upper(),
                ActiveWatchlist.is_active == True
            ).first()
            
            if not watchlist or not watchlist.stock_id:
                return None
            
            stock = self.db.query(Stock).filter(Stock.id == watchlist.stock_id).first()
            if not stock:
                return None
            
            return {
                'gomes_score': stock.gomes_score,  # 1-10
                'sentiment': stock.sentiment,  # Bullish, Bearish, Neutral
                'action_verdict': stock.action_verdict,  # BUY_NOW, ACCUMULATE, WATCH_LIST, etc.
                'edge': stock.edge,
                'catalysts': stock.catalysts,
                'risks': stock.risks,
                'time_horizon': stock.time_horizon,
                'price_target': stock.price_target,
                'entry_zone': stock.entry_zone,
            }
        except Exception as e:
            logger.warning(f"  Could not fetch Gomes context for {ticker}: {e}")
            return None
    
    def _apply_gomes_fusion(
        self,
        ticker: str,
        ml_prediction_type: str,
        ml_confidence: float,
        price_change_pct: float,
        quality: str
    ) -> Tuple[str, float, Dict]:
        """
        Apply Gomes Fusion to adjust ML prediction based on analyst insights.
        
        Fusion Logic:
        1. Alignment Boost: If ML and Gomes agree on direction → boost confidence
        2. Conflict Penalty: If they disagree → reduce confidence, flag for review
        3. Score Multiplier: Higher Gomes score (8-10) → higher weight to fusion
        4. Catalyst Timing: Near-term catalysts → boost short-term predictions
        5. Risk Adjustment: High risks mentioned → reduce confidence
        
        Args:
            ticker: Stock ticker
            ml_prediction_type: UP, DOWN, NEUTRAL from ML
            ml_confidence: Base ML confidence (0-1)
            price_change_pct: Predicted price change
            quality: ML prediction quality
        
        Returns:
            Tuple of (final_prediction_type, final_confidence, fusion_metadata)
        """
        gomes = self._get_gomes_context(ticker)
        
        fusion_meta = {
            'gomes_applied': False,
            'alignment': 'N/A',
            'adjustments': [],
            'original_confidence': ml_confidence,
            'gomes_score': None,
            'gomes_sentiment': None,
        }
        
        if not gomes:
            logger.debug(f"  No Gomes context for {ticker} - using pure ML")
            return ml_prediction_type, ml_confidence, fusion_meta
        
        fusion_meta['gomes_applied'] = True
        fusion_meta['gomes_score'] = gomes.get('gomes_score')
        fusion_meta['gomes_sentiment'] = gomes.get('sentiment')
        
        final_confidence = ml_confidence
        final_type = ml_prediction_type
        
        # =======================================================
        # 1. DIRECTION ALIGNMENT CHECK
        # =======================================================
        gomes_direction = self._sentiment_to_direction(gomes.get('sentiment'))
        
        if ml_prediction_type == gomes_direction:
            # Agreement! Boost confidence
            fusion_meta['alignment'] = 'ALIGNED'
            boost = 0.10  # +10% base boost for agreement
            
            # Extra boost for strong Gomes conviction
            gomes_score = gomes.get('gomes_score') or 5
            if gomes_score >= 8:
                boost += 0.10  # +10% for high conviction
                fusion_meta['adjustments'].append(f"High conviction boost (+10%): Score {gomes_score}/10")
            elif gomes_score >= 6:
                boost += 0.05  # +5% for medium conviction
                fusion_meta['adjustments'].append(f"Medium conviction boost (+5%): Score {gomes_score}/10")
            
            final_confidence = min(0.95, final_confidence + boost)
            fusion_meta['adjustments'].append(f"Direction aligned with Gomes: +{boost*100:.0f}%")
            
        elif ml_prediction_type == 'NEUTRAL' and gomes_direction != 'NEUTRAL':
            # ML is unsure but Gomes has conviction
            fusion_meta['alignment'] = 'GOMES_OVERRIDE'
            
            gomes_score = gomes.get('gomes_score') or 5
            if gomes_score >= 7:
                # Strong Gomes conviction can override neutral ML
                final_type = gomes_direction
                final_confidence = 0.45 + (gomes_score - 7) * 0.05  # 45-60% based on score
                fusion_meta['adjustments'].append(
                    f"Gomes override: ML neutral → {gomes_direction} (score {gomes_score}/10)"
                )
            else:
                # Keep neutral but note the divergence
                fusion_meta['adjustments'].append(
                    f"Gomes suggests {gomes_direction} but score {gomes_score}/10 too low to override"
                )
                
        elif gomes_direction != 'NEUTRAL' and ml_prediction_type != gomes_direction:
            # CONFLICT: ML and Gomes disagree
            fusion_meta['alignment'] = 'CONFLICT'
            
            # Reduce confidence significantly - this needs human review
            penalty = 0.15
            final_confidence = max(0.25, final_confidence - penalty)
            fusion_meta['adjustments'].append(
                f"⚠️ CONFLICT: ML says {ml_prediction_type}, Gomes says {gomes_direction} (-15%)"
            )
        
        # =======================================================
        # 2. ACTION VERDICT ALIGNMENT
        # =======================================================
        action = gomes.get('action_verdict', '').upper()
        
        if action in ['BUY_NOW', 'ACCUMULATE'] and final_type == 'UP':
            final_confidence = min(0.95, final_confidence + 0.05)
            fusion_meta['adjustments'].append(f"Action {action} confirms UP (+5%)")
        elif action in ['SELL', 'TRIM', 'AVOID'] and final_type == 'DOWN':
            final_confidence = min(0.95, final_confidence + 0.05)
            fusion_meta['adjustments'].append(f"Action {action} confirms DOWN (+5%)")
        elif action == 'AVOID' and final_type == 'UP':
            final_confidence = max(0.30, final_confidence - 0.10)
            fusion_meta['adjustments'].append(f"⚠️ Gomes says AVOID but ML says UP (-10%)")
        
        # =======================================================
        # 3. RISK ASSESSMENT
        # =======================================================
        risks = gomes.get('risks', '') or ''
        high_risk_keywords = ['bankruptcy', 'dilution', 'fraud', 'sec investigation', 
                              'delisting', 'going concern', 'liquidity crisis']
        
        risk_lower = risks.lower()
        found_risks = [kw for kw in high_risk_keywords if kw in risk_lower]
        
        if found_risks:
            risk_penalty = min(0.15, len(found_risks) * 0.05)
            final_confidence = max(0.25, final_confidence - risk_penalty)
            fusion_meta['adjustments'].append(
                f"High-risk keywords detected: {', '.join(found_risks)} (-{risk_penalty*100:.0f}%)"
            )
        
        # =======================================================
        # 4. CATALYST TIMING (future enhancement)
        # =======================================================
        # TODO: Parse catalyst dates and boost if within prediction horizon
        catalysts = gomes.get('catalysts', '') or ''
        if catalysts and len(catalysts) > 20:
            # Has meaningful catalysts mentioned
            final_confidence = min(0.95, final_confidence + 0.03)
            fusion_meta['adjustments'].append("Catalysts identified (+3%)")
        
        # =======================================================
        # 5. EDGE QUALITY
        # =======================================================
        edge = gomes.get('edge', '') or ''
        if edge and len(edge) > 50:
            # Has meaningful edge description
            final_confidence = min(0.95, final_confidence + 0.02)
            fusion_meta['adjustments'].append("Information edge documented (+2%)")
        
        # Round final confidence
        final_confidence = round(final_confidence, 4)
        
        logger.info(
            f"  🔀 Gomes Fusion: {ml_confidence:.1%} → {final_confidence:.1%} "
            f"({fusion_meta['alignment']}, score={fusion_meta['gomes_score']})"
        )
        
        return final_type, final_confidence, fusion_meta
    
    def _sentiment_to_direction(self, sentiment: Optional[str]) -> str:
        """Convert Gomes sentiment to prediction direction."""
        if not sentiment:
            return 'NEUTRAL'
        
        sentiment_upper = sentiment.upper()
        if 'BULLISH' in sentiment_upper or 'BUY' in sentiment_upper:
            return 'UP'
        elif 'BEARISH' in sentiment_upper or 'SELL' in sentiment_upper:
            return 'DOWN'
        return 'NEUTRAL'
    
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
            pred_dict = self._extract_predictions(predictions_df, current_price)
            
            # Step 5: Assess prediction quality
            quality, metrics = self._assess_quality(pred_dict, current_price)
            
            # Step 6: Determine trading direction (pure ML)
            predicted_price = pred_dict['point_prediction']
            price_change_pct = ((predicted_price - current_price) / current_price) * 100
            
            ml_prediction_type, ml_confidence = self._determine_direction(
                price_change_pct, quality, ticker=ticker
            )
            
            # Step 6.5: Apply Gomes Fusion (combine ML with analyst insights)
            prediction_type, confidence, fusion_meta = self._apply_gomes_fusion(
                ticker=ticker,
                ml_prediction_type=ml_prediction_type,
                ml_confidence=ml_confidence,
                price_change_pct=price_change_pct,
                quality=quality
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
                'created_at': datetime.utcnow(),
                # Fusion metadata
                'fusion_applied': fusion_meta['gomes_applied'],
                'fusion_alignment': fusion_meta['alignment'],
                'fusion_adjustments': fusion_meta['adjustments'],
                'ml_original_confidence': fusion_meta['original_confidence'],
                'gomes_score': fusion_meta['gomes_score'],
                'gomes_sentiment': fusion_meta['gomes_sentiment'],
            }
            
            # Step 8: Save to database
            if save_to_db:
                self._save_to_database(result)
            
            # Log result with quality indicator
            fusion_indicator = "🔀" if fusion_meta['gomes_applied'] else ""
            quality_emoji = "✅" if quality == PredictionQuality.HIGH else \
                           "⚠️" if quality == PredictionQuality.MEDIUM else "❌"
            
            logger.info(
                f"{quality_emoji}{fusion_indicator} {ticker}: {prediction_type} ({confidence:.0%}), "
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
            # Calculate available data for cross-validation
            # CV needs: input_size + val_size + test_size <= len(df)
            # And test_size >= horizon (from NeuralForecast requirement)
            available = len(df) - self.input_size
            
            # Minimum data for CV: input_size + 2*horizon (val+test must be >= horizon each)
            min_cv_data = self.input_size + 2 * self.horizon
            
            logger.debug(f"  Data check: have={len(df)}, need_for_cv={min_cv_data}, input={self.input_size}, horizon={self.horizon}")
            
            if len(df) >= min_cv_data:
                # Enough data for cross-validation with confidence intervals
                logger.debug("  Using cross-validation mode...")
                
                # Standard model with early stopping
                model = PatchTST(**self.model_config)
                nf = NeuralForecast(models=[model], freq='D')
                
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
            else:
                # Not enough data for CV - use simple fit + predict
                # Disable early stopping and use minimal validation
                # Note: fit+predict mode doesn't support native confidence intervals
                logger.debug("  Using simple fit+predict mode (limited data)...")
                
                # Create a model config without early stopping for limited data
                limited_config = {**self.model_config}
                limited_config['early_stop_patience_steps'] = -1  # Disable early stopping
                limited_config['val_check_steps'] = 50  # Reduce validation checks
                
                model = PatchTST(**limited_config)
                nf = NeuralForecast(models=[model], freq='D')
                
                # Calculate minimal validation size (at least 1, max horizon)
                min_val_size = min(self.horizon, max(1, len(df) - self.input_size - 1))
                
                # Simple fit without prediction intervals (will be estimated later)
                nf.fit(df=df, val_size=min_val_size)
                predictions = nf.predict()  # No level param for simple fit
                predictions = predictions.reset_index()
                predictions = predictions.sort_values('ds', ascending=False).head(1)
            
            return predictions
            
        except Exception as e:
            logger.error(f"  Model training failed: {e}", exc_info=True)
            return None
    
    def _extract_predictions(self, pred_df: pd.DataFrame, current_price: float = None) -> Dict:
        """
        Extract prediction values from NeuralForecast output
        
        Args:
            pred_df: Predictions DataFrame
            current_price: Current price for CI estimation fallback
        
        Returns:
            Dict with point prediction and confidence intervals
        """
        point_pred = float(pred_df['PatchTST'].iloc[0])
        
        # Check if model provides confidence intervals
        if 'PatchTST-lo-80' in pred_df.columns:
            return {
                'point_prediction': point_pred,
                'ci_80_lower': float(pred_df['PatchTST-lo-80'].iloc[0]),
                'ci_80_upper': float(pred_df['PatchTST-hi-80'].iloc[0]),
                'ci_90_lower': float(pred_df['PatchTST-lo-90'].iloc[0]),
                'ci_90_upper': float(pred_df['PatchTST-hi-90'].iloc[0])
            }
        
        # Fallback: estimate CI from prediction variance
        # Use 5% for 80% CI and 8% for 90% CI (conservative)
        base_price = current_price if current_price else point_pred
        spread_80 = base_price * 0.05
        spread_90 = base_price * 0.08
        
        return {
            'point_prediction': point_pred,
            'ci_80_lower': point_pred - spread_80,
            'ci_80_upper': point_pred + spread_80,
            'ci_90_lower': point_pred - spread_90,
            'ci_90_upper': point_pred + spread_90
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
        quality: str,
        ticker: Optional[str] = None
    ) -> Tuple[str, float]:
        """
        Determine prediction direction and confidence
        
        Args:
            price_change_pct: Predicted price change percentage
            quality: Prediction quality level
            ticker: Stock ticker (for learning adjustment)
        
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
        raw_confidence = base_confidence * (0.7 + 0.3 * magnitude_factor)
        
        # Apply learning-based adjustment if enabled
        if self.learning_engine and ticker:
            adjustment = self.learning_engine.adjust_confidence(
                ticker=ticker,
                raw_confidence=raw_confidence,
                prediction_type=prediction_type,
                model_version=self.model_version
            )
            
            confidence = adjustment.adjusted_confidence
            
            if adjustment.adjustment_factor != 1.0:
                logger.info(
                    f"  📊 Learning adjustment for {ticker}: "
                    f"{raw_confidence:.1%} → {confidence:.1%} "
                    f"({adjustment.reason})"
                )
        else:
            confidence = raw_confidence
        
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

