/**
 * StockCard Component - TRADING SIGNAL FOCUSED
 * 
 * Redesigned to show actionable trading information, not just analysis.
 */

import React from 'react';
import { TrendingUp, TrendingDown, Minus, Target, AlertTriangle, Zap, Star } from 'lucide-react';
import type { Stock } from '../types';

interface StockCardProps {
  stock: Stock;
  onClick?: () => void;
}

export const StockCard: React.FC<StockCardProps> = ({ stock, onClick }) => {
  
  // Action verdict badge styling
  const getActionBadge = () => {
    const verdict = stock.action_verdict?.toUpperCase();
    switch (verdict) {
      case 'BUY_NOW':
        return { bg: 'bg-green-500/20', text: 'text-green-400', border: 'border-green-500/50', label: '🟢 BUY NOW' };
      case 'ACCUMULATE':
        return { bg: 'bg-emerald-500/20', text: 'text-emerald-400', border: 'border-emerald-500/50', label: '📈 ACCUMULATE' };
      case 'WATCH_LIST':
        return { bg: 'bg-yellow-500/20', text: 'text-yellow-400', border: 'border-yellow-500/50', label: '👀 WATCH' };
      case 'TRIM':
        return { bg: 'bg-orange-500/20', text: 'text-orange-400', border: 'border-orange-500/50', label: '⚠️ TRIM' };
      case 'SELL':
        return { bg: 'bg-red-500/20', text: 'text-red-400', border: 'border-red-500/50', label: '🔴 SELL' };
      case 'AVOID':
        return { bg: 'bg-gray-500/20', text: 'text-gray-400', border: 'border-gray-500/50', label: '❌ AVOID' };
      default:
        return { bg: 'bg-slate-500/20', text: 'text-slate-400', border: 'border-slate-500/50', label: '📊 ANALYZE' };
    }
  };

  const getSentiment = (sentiment: string | null) => {
    const s = sentiment?.toUpperCase();
    if (s === 'BULLISH') return { icon: TrendingUp, color: 'text-green-500' };
    if (s === 'BEARISH') return { icon: TrendingDown, color: 'text-red-500' };
    return { icon: Minus, color: 'text-gray-500' };
  };

  // Moat rating as stars
  const renderMoatRating = (rating: number | null) => {
    if (!rating) return null;
    return (
      <div className="flex items-center gap-1">
        {[...Array(5)].map((_, i) => (
          <Star
            key={i}
            className={`w-3 h-3 ${i < rating ? 'text-amber-400 fill-amber-400' : 'text-gray-600'}`}
          />
        ))}
      </div>
    );
  };

  const actionBadge = getActionBadge();
  const sentiment = getSentiment(stock.sentiment);
  const SentimentIcon = sentiment.icon;

  return (
    <div
      onClick={onClick}
      className={`relative overflow-hidden rounded-xl border-2 ${actionBadge.border} ${actionBadge.bg} 
                  backdrop-blur-sm p-5 cursor-pointer transition-all duration-300 
                  hover:scale-105 hover:shadow-2xl hover:shadow-${actionBadge.text}/20 group`}
    >
      {/* Action Verdict Banner */}
      <div className={`absolute top-0 right-0 px-4 py-1 ${actionBadge.bg} ${actionBadge.text} 
                       text-xs font-bold border-l-2 border-b-2 ${actionBadge.border} 
                       rounded-bl-lg`}>
        {actionBadge.label}
      </div>

      {/* Header: Ticker & Gomes Score */}
      <div className="flex items-start justify-between mb-4 mt-2">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <h3 className="text-3xl font-black text-white font-mono tracking-tight">
              {stock.ticker}
            </h3>
            <div className={sentiment.color}>
              <SentimentIcon className="w-5 h-5" strokeWidth={2.5} />
            </div>
          </div>
          {stock.company_name && (
            <p className="text-xs text-slate-400 max-w-[200px] truncate">
              {stock.company_name}
            </p>
          )}
        </div>
        
        {/* Gomes Score */}
        {stock.gomes_score && (
          <div className="text-right">
            <div className={`text-4xl font-black font-mono ${
              stock.gomes_score >= 8 ? 'text-green-400' : 
              stock.gomes_score >= 6 ? 'text-yellow-400' : 
              'text-gray-400'
            }`}>
              {stock.gomes_score}
            </div>
            <div className="text-[10px] text-slate-500 font-semibold">SCORE</div>
          </div>
        )}
      </div>

      {/* Trading Levels Grid */}
      <div className="grid grid-cols-3 gap-2 mb-4 text-xs">
        {stock.entry_zone && (
          <div className="bg-slate-900/50 rounded-lg p-2 border border-blue-500/30">
            <div className="text-blue-400 font-semibold mb-0.5">ENTRY</div>
            <div className="text-white text-xs font-mono">{stock.entry_zone}</div>
          </div>
        )}
        {stock.price_target_short && (
          <div className="bg-slate-900/50 rounded-lg p-2 border border-green-500/30">
            <div className="text-green-400 font-semibold mb-0.5">TARGET</div>
            <div className="text-white text-xs font-mono">{stock.price_target_short}</div>
          </div>
        )}
        {stock.stop_loss_risk && (
          <div className="bg-slate-900/50 rounded-lg p-2 border border-red-500/30">
            <div className="text-red-400 font-semibold mb-0.5">STOP</div>
            <div className="text-white text-xs font-mono truncate">{stock.stop_loss_risk.split(' ').slice(0, 3).join(' ')}</div>
          </div>
        )}
      </div>

      {/* Moat Rating */}
      {stock.moat_rating && (
        <div className="mb-3">
          <div className="flex items-center justify-between">
            <span className="text-[10px] text-slate-500 font-semibold uppercase">Competitive Moat</span>
            {renderMoatRating(stock.moat_rating)}
          </div>
        </div>
      )}

      {/* Catalysts */}
      {stock.catalysts && (
        <div className="mb-3">
          <div className="flex items-center gap-1.5 mb-1.5">
            <Zap className="w-3.5 h-3.5 text-amber-400" />
            <span className="text-[10px] text-slate-500 font-semibold uppercase">Catalysts</span>
          </div>
          <p className="text-xs text-slate-300 leading-relaxed line-clamp-2">
            {stock.catalysts}
          </p>
        </div>
      )}

      {/* Trade Rationale */}
      {stock.trade_rationale && (
        <div className="mb-3">
          <div className="flex items-center gap-1.5 mb-1.5">
            <Target className="w-3.5 h-3.5 text-indigo-400" />
            <span className="text-[10px] text-slate-500 font-semibold uppercase">Why Now</span>
          </div>
          <p className="text-xs text-slate-300 leading-relaxed line-clamp-2">
            {stock.trade_rationale}
          </p>
        </div>
      )}

      {/* Footer: Time Horizon & Risk Warning */}
      <div className="flex items-center justify-between pt-3 border-t border-slate-700/50 text-[10px]">
        <div className="text-slate-500">
          {stock.time_horizon || 'No timeframe'}
        </div>
        {stock.risks && (
          <div className="flex items-center gap-1 text-orange-400">
            <AlertTriangle className="w-3 h-3" />
            <span>Risks present</span>
          </div>
        )}
      </div>
    </div>
  );
};
