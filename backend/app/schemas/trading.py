"""
Pydantic schemas for Trading Intelligence API
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, validator


class WatchlistItemResponse(BaseModel):
    """Watchlist ticker item"""
    id: int
    ticker: str
    action_verdict: Optional[str]
    confidence_score: Optional[float]
    added_at: datetime
    last_updated: datetime
    is_active: bool
    
    class Config:
        from_attributes = True


class MLPredictionResponse(BaseModel):
    """ML prediction output"""
    id: int
    ticker: str
    prediction_type: str
    confidence: float
    predicted_price: float
    current_price: float
    kelly_position_size: Optional[float]
    expected_return_pct: float
    model_version: Optional[str]
    horizon_days: int
    created_at: datetime
    valid_until: Optional[datetime]
    
    class Config:
        from_attributes = True


class TradingSignalResponse(BaseModel):
    """Trading signal with all context"""
    ticker: str = Field(..., description="Stock ticker symbol")
    signal_type: str = Field(..., description="BUY, SELL, or HOLD")
    ai_prediction: str = Field(..., description="ML prediction: UP, DOWN, NEUTRAL")
    confidence: float = Field(..., ge=0, le=1, description="Confidence score 0-1")
    kelly_position_size: str = Field(..., description="Optimal position size as %")
    current_price: float = Field(..., description="Current market price")
    predicted_price: float = Field(..., description="ML predicted price")
    entry_price: Optional[float] = Field(None, description="Suggested entry price")
    target_price: Optional[float] = Field(None, description="Price target")
    stop_loss: Optional[float] = Field(None, description="Stop loss price")
    risk_reward_ratio: Optional[float] = Field(None, description="Risk/reward ratio")
    analyst_source: Optional[int] = Field(None, description="Stock analysis ID")
    analyst_verdict: Optional[str] = Field(None, description="Original analyst recommendation")
    timestamp: datetime = Field(..., description="Signal generation time")
    expires_at: Optional[datetime] = Field(None, description="Signal expiration")
    
    @validator('kelly_position_size', pre=True)
    def format_kelly_size(cls, v):
        """Convert decimal to percentage string"""
        if isinstance(v, (int, float)):
            return f"{v * 100:.2f}%"
        return v
    
    class Config:
        from_attributes = True


class TradingSignalCreate(BaseModel):
    """Create new trading signal"""
    ticker: str
    signal_type: str = Field(..., pattern="^(BUY|SELL|HOLD)$")
    ml_prediction_id: Optional[int]
    analyst_source_id: Optional[int]
    confidence: float = Field(..., ge=0, le=1)
    kelly_size: float = Field(..., ge=0, le=1)
    entry_price: Optional[float]
    target_price: Optional[float]
    stop_loss: Optional[float]
    expires_at: Optional[datetime]
    notes: Optional[str]


class ModelPerformanceResponse(BaseModel):
    """Model accuracy metrics"""
    ticker: str
    model_version: str
    total_predictions: int
    avg_accuracy: float
    min_accuracy: float
    max_accuracy: float
    last_evaluation: datetime
    
    class Config:
        from_attributes = True


class DataSyncRequest(BaseModel):
    """Request to sync historical data"""
    tickers: Optional[list[str]] = Field(None, description="Specific tickers to sync (or all watchlist)")
    days: int = Field(60, ge=1, le=365, description="Days of history to fetch")


class DataSyncResponse(BaseModel):
    """Data sync result"""
    status: str
    message: str
    ticker_count: int


class WatchlistSyncResponse(BaseModel):
    """Watchlist sync result"""
    status: str
    added: int
    updated: int
    removed: int
    total_active: int


class PredictionRequest(BaseModel):
    """Request ML prediction for ticker"""
    ticker: str = Field(..., description="Stock ticker to predict")
    horizon_days: int = Field(5, ge=1, le=30, description="Prediction horizon")
    use_cached: bool = Field(True, description="Use cached prediction if available")


class WatchlistStatsResponse(BaseModel):
    """Watchlist statistics"""
    total_tickers: int
    active_tickers: int
    buy_signals: int
    sell_signals: int
    avg_confidence: float
    top_opportunities: list[TradingSignalResponse]


class BacktestRequest(BaseModel):
    """Backtest model on historical data"""
    ticker: str
    start_date: datetime
    end_date: datetime
    initial_capital: float = Field(10000.0, description="Starting capital")
    kelly_fraction: float = Field(0.25, description="Max Kelly fraction per trade")


class BacktestResult(BaseModel):
    """Backtest performance metrics"""
    ticker: str
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    total_return_pct: float
    sharpe_ratio: float
    max_drawdown_pct: float
    final_capital: float
