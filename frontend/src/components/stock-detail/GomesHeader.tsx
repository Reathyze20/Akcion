/**
 * GomesHeader Component
 * 
 * The "Verdict First" header for StockDetail.
 * Shows Ticker, Price, and prominent Gomes Score with color coding.
 * 
 * Design Philosophy: User sees the VERDICT before any chart or data.
 */

import React from 'react';
import { 
  TrendingUp, 
  TrendingDown, 
  Minus,
  Star,
  Target,
  X
} from 'lucide-react';

export interface GomesHeaderProps {
  ticker: string;
  companyName: string | null;
  currentPrice: number | null;
  gomesScore: number | null;
  actionVerdict: string | null;
  priceChange?: number | null; // Percentage change
  onClose: () => void;
}

/**
 * Get score color based on Gomes methodology
 * 8-10: Gold Mine (Green)
 * 6-7: Speculative (Yellow)
 * 4-5: Watchlist (Gray)
 * 1-3: Avoid (Red)
 */
const getScoreColor = (score: number | null): string => {
  if (score === null) return 'text-text-muted bg-text-muted/20';
  if (score >= 8) return 'text-positive bg-positive/20 border-positive';
  if (score >= 6) return 'text-warning bg-warning/20 border-warning';
  if (score >= 4) return 'text-text-secondary bg-text-secondary/20 border-text-secondary';
  return 'text-negative bg-negative/20 border-negative';
};

const getScoreLabel = (score: number | null): string => {
  if (score === null) return 'N/A';
  if (score >= 8) return 'GOLD MINE';
  if (score >= 6) return 'SPECULATIVE';
  if (score >= 4) return 'WATCHLIST';
  return 'AVOID';
};

const getVerdictStyle = (verdict: string | null): { color: string; icon: React.ReactNode } => {
  switch (verdict) {
    case 'BUY_NOW':
      return { color: 'text-positive', icon: <TrendingUp className="w-5 h-5" /> };
    case 'ACCUMULATE':
      return { color: 'text-positive', icon: <TrendingUp className="w-4 h-4" /> };
    case 'WATCH_LIST':
      return { color: 'text-warning', icon: <Target className="w-4 h-4" /> };
    case 'TRIM':
      return { color: 'text-warning', icon: <TrendingDown className="w-4 h-4" /> };
    case 'SELL':
      return { color: 'text-negative', icon: <TrendingDown className="w-5 h-5" /> };
    case 'AVOID':
      return { color: 'text-gray-400', icon: <Minus className="w-4 h-4" /> };
    default:
      return { color: 'text-text-muted', icon: <Minus className="w-4 h-4" /> };
  }
};

export const GomesHeader: React.FC<GomesHeaderProps> = ({
  ticker,
  companyName,
  currentPrice,
  gomesScore,
  actionVerdict,
  priceChange,
  onClose,
}) => {
  const scoreColor = getScoreColor(gomesScore);
  const scoreLabel = getScoreLabel(gomesScore);
  const verdict = getVerdictStyle(actionVerdict);
  
  return (
    <div className="sticky top-0 bg-gradient-to-r from-primary-surface to-primary-card border-b border-border p-6 z-10">
      <div className="flex items-start justify-between">
        {/* Left: Ticker & Company */}
        <div className="flex-1">
          <div className="flex items-center gap-3 mb-2">
            <h2 className="text-3xl font-bold text-accent">
              {ticker}
            </h2>
            
            {/* Action Verdict Badge */}
            <div className={`
              flex items-center gap-1 px-3 py-1 rounded-full
              ${verdict.color} bg-current/10 border border-current/30
            `}>
              {verdict.icon}
              <span className="text-sm font-bold">
                {actionVerdict?.replace('_', ' ') || 'ANALYZE'}
              </span>
            </div>
          </div>
          
          {companyName && (
            <p className="text-lg text-text-secondary mb-2">{companyName}</p>
          )}
          
          {/* Current Price */}
          {currentPrice !== null && (
            <div className="flex items-center gap-3">
              <span className="text-2xl font-mono font-bold text-text-primary">
                ${currentPrice.toFixed(2)}
              </span>
              {priceChange !== null && priceChange !== undefined && (
                <span className={`
                  flex items-center gap-1 text-sm font-medium
                  ${priceChange >= 0 ? 'text-positive' : 'text-negative'}
                `}>
                  {priceChange >= 0 ? <TrendingUp className="w-4 h-4" /> : <TrendingDown className="w-4 h-4" />}
                  {priceChange >= 0 ? '+' : ''}{priceChange.toFixed(2)}%
                </span>
              )}
            </div>
          )}
        </div>
        
        {/* Right: Gomes Score (The Main Verdict) */}
        <div className="flex items-start gap-4">
          {/* Big Score Display */}
          <div className={`
            flex flex-col items-center justify-center
            w-24 h-24 rounded-xl border-2
            ${scoreColor}
          `}>
            <div className="flex items-center gap-1">
              <Star className="w-4 h-4" />
              <span className="text-xs font-medium uppercase">Gomes</span>
            </div>
            <span className="text-3xl font-bold">
              {gomesScore ?? '—'}
            </span>
            <span className="text-xs font-medium opacity-80">
              {scoreLabel}
            </span>
          </div>
          
          {/* Close Button */}
          <button
            onClick={onClose}
            className="p-2 text-text-muted hover:text-text-primary hover:bg-white/10 
                       rounded-lg transition-colors"
            aria-label="Zavřít"
          >
            <X className="w-6 h-6" />
          </button>
        </div>
      </div>
    </div>
  );
};

export default GomesHeader;
