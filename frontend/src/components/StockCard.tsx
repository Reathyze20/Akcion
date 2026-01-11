/**
 * StockCard Component
 * 
 * Premium Bento-style stock card with high information density.
 */

import React from 'react';
import { TrendingUp, TrendingDown, Minus, Calendar, Target, Zap } from 'lucide-react';
import type { Stock } from '../types';

interface StockCardProps {
  stock: Stock;
  onClick?: () => void;
}

export const StockCard: React.FC<StockCardProps> = ({ stock, onClick }) => {
  const getSentiment = (sentiment: string | null) => {
    const s = sentiment?.toUpperCase();
    if (s === 'BULLISH') return { badge: 'badge-bullish', icon: TrendingUp, color: 'text-semantic-bullish' };
    if (s === 'BEARISH') return { badge: 'badge-bearish', icon: TrendingDown, color: 'text-semantic-bearish' };
    return { badge: 'badge-neutral', icon: Minus, color: 'text-semantic-neutral' };
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const sentiment = getSentiment(stock.sentiment);
  const SentimentIcon = sentiment.icon;

  return (
    <div
      onClick={onClick}
      className="card card-hover p-5 cursor-pointer space-y-4 group"
    >
      {/* Header: Ticker & Sentiment */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <h3 className="text-2xl font-bold text-text-primary font-mono tracking-tight">
              {stock.ticker}
            </h3>
            <div className={`${sentiment.color} transition-transform group-hover:scale-110`}>
              <SentimentIcon className="w-5 h-5" strokeWidth={2.5} />
            </div>
          </div>
          {stock.company_name && (
            <p className="text-sm text-text-secondary line-clamp-1">
              {stock.company_name}
            </p>
          )}
        </div>
        <span className={`badge ${sentiment.badge} flex-shrink-0`}>
          {stock.sentiment || 'NEUTRAL'}
        </span>
      </div>

      {/* Scores Grid */}
      <div className="grid grid-cols-2 gap-3">
        {stock.gomes_score !== null && (
          <div className="bg-terminal-bg rounded-lg p-3 border border-terminal-border">
            <p className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-1.5">
              Gomes Score
            </p>
            <div className="flex items-baseline gap-1.5">
              <span className={`text-3xl font-bold font-mono ${
                stock.gomes_score >= 7 ? 'text-semantic-bullish' : 
                stock.gomes_score >= 5 ? 'text-semantic-neutral' : 
                'text-semantic-bearish'
              }`}>
                {stock.gomes_score}
              </span>
              <span className="text-sm text-text-muted">/10</span>
            </div>
          </div>
        )}
        {stock.conviction_score !== null && (
          <div className="bg-terminal-bg rounded-lg p-3 border border-terminal-border">
            <p className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-1.5">
              Conviction
            </p>
            <div className="flex items-baseline gap-1.5">
              <span className={`text-3xl font-bold font-mono ${
                stock.conviction_score >= 7 ? 'text-accent-purple' : 
                stock.conviction_score >= 5 ? 'text-accent-cyan' : 
                'text-text-muted'
              }`}>
                {stock.conviction_score}
              </span>
              <span className="text-sm text-text-muted">/10</span>
            </div>
          </div>
        )}
      </div>

      {/* Information Grid */}
      <div className="space-y-2.5">
        {stock.edge && (
          <div className="flex gap-2">
            <Zap className="w-4 h-4 text-accent-blue flex-shrink-0 mt-0.5" />
            <div className="flex-1 min-w-0">
              <p className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-0.5">
                Edge
              </p>
              <p className="text-sm text-text-secondary line-clamp-2 leading-relaxed">
                {stock.edge}
              </p>
            </div>
          </div>
        )}
        
        {stock.catalysts && (
          <div className="flex gap-2">
            <Target className="w-4 h-4 text-semantic-bullish flex-shrink-0 mt-0.5" />
            <div className="flex-1 min-w-0">
              <p className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-0.5">
                Catalysts
              </p>
              <p className="text-sm text-text-secondary line-clamp-2 leading-relaxed">
                {stock.catalysts}
              </p>
            </div>
          </div>
        )}
      </div>

      {/* Footer Metadata */}
      <div className="flex items-center justify-between pt-2 border-t border-terminal-border">
        <div className="flex items-center gap-1.5 text-xs text-text-muted">
          <Calendar className="w-3.5 h-3.5" />
          <span>{formatDate(stock.created_at)}</span>
        </div>
        <div className="flex items-center gap-2">
          {stock.price_target && (
            <span className="text-xs font-mono text-accent-cyan px-2 py-0.5 bg-terminal-bg rounded">
              {stock.price_target}
            </span>
          )}
          {stock.speaker && (
            <span className="text-xs text-text-muted">{stock.speaker}</span>
          )}
        </div>
      </div>
    </div>
  );
};
