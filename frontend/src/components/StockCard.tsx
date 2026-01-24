/**
 * StockCard Component - TRADING SIGNAL FOCUSED WITH GAP ANALYSIS
 * 
 * Shows actionable trading information + portfolio position status
 */

import React from 'react';
import { TrendingUp, TrendingDown, Minus, Target, AlertTriangle, Zap, Star, Briefcase, DollarSign } from 'lucide-react';
import type { Stock, EnrichedStock, MatchSignal } from '../types';
import { ScoreHistoryMiniChart } from './ScoreHistoryMiniChart';

interface StockCardProps {
  stock: Stock | EnrichedStock;
  onClick?: () => void;
}

// Type guard to check if stock is enriched
function isEnrichedStock(stock: Stock | EnrichedStock): stock is EnrichedStock {
  return 'match_signal' in stock;
}

// Format price with $ and 2 decimals
const formatPrice = (price: number | null | undefined): string => {
  if (price === null || price === undefined) return 'N/A';
  return `$${price.toFixed(2)}`;
};

// Get color based on price zone
const getPriceZoneColor = (zone: string | null | undefined): string => {
  switch (zone) {
    case 'DEEP_VALUE':
      return 'text-emerald-400';
    case 'BUY_ZONE':
      return 'text-green-400';
    case 'ACCUMULATE':
      return 'text-lime-400';
    case 'FAIR_VALUE':
      return 'text-yellow-400';
    case 'SELL_ZONE':
      return 'text-orange-400';
    case 'OVERVALUED':
      return 'text-red-400';
    default:
      return 'text-slate-400';
  }
};

// Get zone label for display
const getPriceZoneLabel = (zone: string | null | undefined): string => {
  switch (zone) {
    case 'DEEP_VALUE':
      return 'HLUBOKÁ HODNOTA';
    case 'BUY_ZONE':
      return 'NÁKUPNÍ PÁSMO';
    case 'ACCUMULATE':
      return 'AKUMULOVAT';
    case 'FAIR_VALUE':
      return 'FÉR. HODNOTA';
    case 'SELL_ZONE':
      return 'PRODEJNÍ PÁSMO';
    case 'OVERVALUED':
      return 'NADHODNOCENO';
    default:
      return zone || '';
  }
};

export const StockCard: React.FC<StockCardProps> = ({ stock, onClick }) => {
  const enriched = isEnrichedStock(stock) ? stock : null;
  
  // Match signal styling (for gap analysis)
  const getMatchSignalStyle = (signal?: MatchSignal) => {
    switch (signal) {
      case 'OPPORTUNITY':
        return 'animate-pulse shadow-lg shadow-green-500/30 ring-2 ring-green-500/50';
      case 'DANGER_EXIT':
        return 'animate-pulse shadow-lg shadow-red-500/30 ring-2 ring-red-500/50';
      case 'ACCUMULATE':
        return 'shadow-lg shadow-emerald-500/20 ring-1 ring-emerald-500/30';
      case 'WAIT_MARKET_BAD':
        return 'opacity-60 ring-1 ring-yellow-500/30';
      default:
        return '';
    }
  };
  
  // Action verdict badge styling
  const getActionBadge = () => {
    const verdict = stock.action_verdict?.toUpperCase();
    switch (verdict) {
      case 'BUY_NOW':
        return { bg: 'bg-green-500/20', text: 'text-green-400', border: 'border-green-500/50', label: 'KOUPIT' };
      case 'ACCUMULATE':
        return { bg: 'bg-emerald-500/20', text: 'text-emerald-400', border: 'border-emerald-500/50', label: 'AKUMULOVAT' };
      case 'WATCH_LIST':
        return { bg: 'bg-yellow-500/20', text: 'text-yellow-400', border: 'border-yellow-500/50', label: 'SLEDOVAT' };
      case 'TRIM':
        return { bg: 'bg-orange-500/20', text: 'text-orange-400', border: 'border-orange-500/50', label: 'REDUKOVAT' };
      case 'SELL':
        return { bg: 'bg-red-500/20', text: 'text-red-400', border: 'border-red-500/50', label: 'PRODAT' };
      case 'AVOID':
        return { bg: 'bg-gray-500/20', text: 'text-gray-400', border: 'border-gray-500/50', label: 'VYHNOUT SE' };
      default:
        return { bg: 'bg-slate-500/20', text: 'text-slate-400', border: 'border-slate-500/50', label: 'ANALYZOVAT' };
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
  const matchSignalStyle = enriched ? getMatchSignalStyle(enriched.match_signal) : '';

  return (
    <div
      onClick={onClick}
      className={`relative overflow-hidden rounded-xl border-2 ${actionBadge.border} ${actionBadge.bg} 
                  backdrop-blur-sm p-5 cursor-pointer transition-all duration-300 
                  hover:scale-105 hover:shadow-2xl hover:shadow-${actionBadge.text}/20 group
                  ${matchSignalStyle}`}
    >
      {/* Holdings Badge (if owned) */}
      {enriched?.user_holding && (
        <div className="absolute top-0 left-0 px-3 py-1 bg-indigo-500/20 text-indigo-400 
                        text-xs font-bold border-r-2 border-b-2 border-indigo-500/50 
                        rounded-br-lg flex items-center gap-1">
          <Briefcase size={12} />
          V PORTFOLIU: {enriched.holding_quantity?.toFixed(0)} akcií
        </div>
      )}

      {/* Action Verdict Banner */}
      <div className={`absolute top-0 right-0 px-4 py-1 ${actionBadge.bg} ${actionBadge.text} 
                       text-xs font-bold border-l-2 border-b-2 ${actionBadge.border} 
                       rounded-bl-lg ${enriched?.user_holding ? 'mt-8' : ''}`}>
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
        
        {/* Gomes Score with History */}
        {stock.gomes_score && (
          <div className="text-right flex flex-col items-end gap-1">
            <div className="flex items-center gap-2">
              <ScoreHistoryMiniChart 
                ticker={stock.ticker} 
                currentScore={stock.gomes_score}
                height={30}
                width={60}
              />
              <div>
                <div className={`text-4xl font-black font-mono ${
                  stock.gomes_score >= 8 ? 'text-green-400' : 
                  stock.gomes_score >= 6 ? 'text-yellow-400' : 
                  'text-gray-400'
                }`}>
                  {stock.gomes_score}
                </div>
                <div className="text-[10px] text-slate-500 font-semibold">SCORE</div>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Current Price & Price Position */}
      {stock.current_price && (
        <div className="mb-4 p-3 bg-slate-900/70 rounded-lg border border-slate-700/50">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <DollarSign className="w-4 h-4 text-slate-400" />
              <span className="text-lg font-bold text-white font-mono">
                {formatPrice(stock.current_price)}
              </span>
            </div>
            {stock.price_zone && (
              <span className={`text-xs font-bold px-2 py-1 rounded ${getPriceZoneColor(stock.price_zone)} bg-slate-800/80`}>
                {getPriceZoneLabel(stock.price_zone)}
              </span>
            )}
          </div>
          
          {/* Price Range Bar */}
          {stock.green_line && stock.red_line && (
            <div className="relative">
              <div className="flex justify-between text-[10px] mb-1">
                <span className="text-green-400 font-mono">${stock.green_line.toFixed(2)}</span>
                <span className="text-red-400 font-mono">${stock.red_line.toFixed(2)}</span>
              </div>
              <div className="h-2 rounded-full bg-gradient-to-r from-green-500 via-yellow-500 to-red-500 relative overflow-hidden">
                {stock.price_position_pct !== null && stock.price_position_pct !== undefined && (
                  <div 
                    className="absolute top-0 w-1 h-full bg-white shadow-lg shadow-white/50 rounded"
                    style={{ 
                      left: `${Math.max(0, Math.min(100, stock.price_position_pct))}%`,
                      transform: 'translateX(-50%)'
                    }}
                  />
                )}
              </div>
              <div className="flex justify-between text-[9px] mt-0.5 text-slate-500">
                <span>NÁKUP</span>
                <span>FÉR. HODNOTA</span>
                <span>PRODEJ</span>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Trading Levels Grid */}
      <div className="grid grid-cols-3 gap-2 mb-4 text-xs">
        {stock.entry_zone && (
          <div className="bg-slate-900/50 rounded-lg p-2 border border-blue-500/30">
            <div className="text-blue-400 font-semibold mb-0.5">VSTUP</div>
            <div className="text-white text-xs font-mono">{stock.entry_zone}</div>
          </div>
        )}
        {stock.price_target_short && (
          <div className="bg-slate-900/50 rounded-lg p-2 border border-green-500/30">
            <div className="text-green-400 font-semibold mb-0.5">CÍL</div>
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
            <span className="text-[10px] text-slate-500 font-semibold uppercase">Konkurenční příkop</span>
            {renderMoatRating(stock.moat_rating)}
          </div>
        </div>
      )}

      {/* Catalysts */}
      {stock.catalysts && (
        <div className="mb-3">
          <div className="flex items-center gap-1.5 mb-1.5">
            <Zap className="w-3.5 h-3.5 text-amber-400" />
            <span className="text-[10px] text-slate-500 font-semibold uppercase">Katalyzátory</span>
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
            <span className="text-[10px] text-slate-500 font-semibold uppercase">Proč nyní</span>
          </div>
          <p className="text-xs text-slate-300 leading-relaxed line-clamp-2">
            {stock.trade_rationale}
          </p>
        </div>
      )}

      {/* Position P/L (if owned) */}
      {enriched?.user_holding && enriched.holding_unrealized_pl !== null && (
        <div className="mb-3 p-2 bg-slate-900/70 rounded-lg border border-slate-700/50">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-[10px] text-slate-500 font-semibold uppercase mb-0.5">Vaše pozice</div>
              <div className="text-xs text-slate-400">
                Prům: ${enriched.holding_avg_cost?.toFixed(2)} × {enriched.holding_quantity?.toFixed(0)} akcií
              </div>
            </div>
            <div className="text-right">
              <div className={`text-sm font-bold ${
                enriched.holding_unrealized_pl >= 0 ? 'text-green-400' : 'text-red-400'
              }`}>
                {enriched.holding_unrealized_pl >= 0 ? '+' : ''}
                ${enriched.holding_unrealized_pl.toFixed(2)}
              </div>
              <div className={`text-xs ${
                enriched.holding_unrealized_pl_percent! >= 0 ? 'text-green-400' : 'text-red-400'
              }`}>
                {enriched.holding_unrealized_pl_percent! >= 0 ? '+' : ''}
                {enriched.holding_unrealized_pl_percent?.toFixed(2)}%
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Match Signal Badge (if enriched) */}
      {enriched?.match_signal && enriched.match_signal !== 'NO_ACTION' && enriched.match_signal !== 'HOLD' && (
        <div className="mb-3">
          <div className={`px-3 py-2 rounded-lg text-center font-bold text-sm ${
            enriched.match_signal === 'OPPORTUNITY' ? 'bg-green-500/20 text-green-400 border border-green-500/50' :
            enriched.match_signal === 'ACCUMULATE' ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/50' :
            enriched.match_signal === 'DANGER_EXIT' ? 'bg-red-500/20 text-red-400 border border-red-500/50 animate-pulse' :
            enriched.match_signal === 'WAIT_MARKET_BAD' ? 'bg-yellow-500/20 text-yellow-400 border border-yellow-500/50' :
            'bg-slate-500/20 text-slate-400 border border-slate-500/50'
          }`}>
            {enriched.match_signal === 'OPPORTUNITY' && 'PŘÍLEŽITOST - Nevlastním'}
            {enriched.match_signal === 'ACCUMULATE' && 'Přidat další akcie'}
            {enriched.match_signal === 'DANGER_EXIT' && 'SIGNAL K PRODEJI'}
            {enriched.match_signal === 'WAIT_MARKET_BAD' && 'Čekat - Trh je červený'}
          </div>
        </div>
      )}

      {/* Footer: Time Horizon & Risk Warning */}
      <div className="flex items-center justify-between pt-3 border-t border-slate-700/50 text-[10px]">
        <div className="text-slate-500">
          {stock.time_horizon || 'Bez časového horizontu'}
        </div>
        {stock.risks && (
          <div className="flex items-center gap-1 text-orange-400">
            <AlertTriangle className="w-3 h-3" />
            <span>Rizika přítomna</span>
          </div>
        )}
      </div>
    </div>
  );
};
