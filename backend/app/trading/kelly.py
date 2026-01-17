"""
Kelly Criterion Calculator - Position sizing based on win probability
"""
from typing import Optional
import math


class KellyCriterion:
    """
    Calculate optimal position size using Kelly Criterion
    
    Formula: f* = (bp - q) / b
    Where:
        f* = fraction of capital to bet
        b = odds received (win/loss ratio)
        p = probability of winning
        q = probability of losing (1-p)
    """
    
    def __init__(self, max_position: float = 0.25, fractional_kelly: float = 0.5):
        """
        Args:
            max_position: Maximum allowed position size (default 25%)
            fractional_kelly: Use fraction of Kelly (default 0.5 = half-Kelly for safety)
        """
        self.max_position = max_position
        self.fractional_kelly = fractional_kelly
    
    def calculate(
        self,
        win_probability: float,
        expected_return: float,
        expected_loss: float = 0.10
    ) -> float:
        """
        Calculate Kelly position size
        
        Args:
            win_probability: ML prediction confidence (0-1)
            expected_return: Expected % gain if prediction correct (e.g., 0.15 = 15%)
            expected_loss: Expected % loss if prediction wrong (default 10%)
        
        Returns:
            Position size as decimal (0-1), e.g., 0.15 = 15% of portfolio
        """
        if win_probability <= 0.5 or expected_return <= 0:
            return 0.0
        
        # Kelly formula
        # b = win/loss ratio (e.g., gain 15% vs lose 10% = 1.5)
        b = expected_return / expected_loss
        p = win_probability
        q = 1 - p
        
        # Kelly fraction: f* = (bp - q) / b
        kelly = (b * p - q) / b
        
        # Apply fractional Kelly for safety (half-Kelly is common)
        kelly = kelly * self.fractional_kelly
        
        # Clamp to [0, max_position]
        kelly = max(0.0, min(kelly, self.max_position))
        
        return round(kelly, 4)
    
    def calculate_from_prediction(
        self,
        confidence: float,
        current_price: float,
        predicted_price: float,
        stop_loss_pct: float = 0.10
    ) -> dict:
        """
        Calculate Kelly size from ML prediction data
        
        Args:
            confidence: ML prediction confidence (0-1)
            current_price: Current stock price
            predicted_price: ML predicted price
            stop_loss_pct: Stop loss percentage (default 10%)
        
        Returns:
            Dict with kelly_size and calculation details
        """
        # Calculate expected return
        expected_return = abs(predicted_price - current_price) / current_price
        
        # Use confidence as win probability
        win_probability = confidence
        
        # Calculate Kelly position size
        kelly_size = self.calculate(
            win_probability=win_probability,
            expected_return=expected_return,
            expected_loss=stop_loss_pct
        )
        
        return {
            'kelly_size': kelly_size,
            'kelly_pct': round(kelly_size * 100, 2),
            'win_probability': win_probability,
            'expected_return': round(expected_return * 100, 2),
            'expected_loss': round(stop_loss_pct * 100, 2),
            'risk_reward_ratio': round(expected_return / stop_loss_pct, 2)
        }
    
    def adjust_for_volatility(
        self,
        base_kelly: float,
        volatility: float,
        max_volatility: float = 0.05
    ) -> float:
        """
        Reduce Kelly size for high-volatility stocks
        
        Args:
            base_kelly: Original Kelly size
            volatility: Stock volatility (std dev / mean)
            max_volatility: Volatility threshold (default 5%)
        
        Returns:
            Adjusted Kelly size
        """
        if volatility <= max_volatility:
            return base_kelly
        
        # Reduce position size proportionally to excess volatility
        volatility_penalty = math.exp(-(volatility - max_volatility) * 10)
        adjusted_kelly = base_kelly * volatility_penalty
        
        return round(max(0.0, adjusted_kelly), 4)
    
    @staticmethod
    def validate_kelly_size(kelly_size: float) -> bool:
        """Validate Kelly size is within reasonable bounds"""
        return 0.0 <= kelly_size <= 1.0
