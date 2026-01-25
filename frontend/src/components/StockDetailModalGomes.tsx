/**
 * Stock Detail Modal - Gomes Edition
 * ==================================
 * Redesigned according to Mark Gomes investing philosophy:
 * - Focus on CATALYSTS (future), not P/L (past)  
 * - Cash runway & survival metrics
 * - 4 tactical panels for decision-making
 * 
 * Author: GitHub Copilot with Claude Sonnet 4.5
 * Date: 2026-01-25
 */

import React, { useState } from 'react';
import { 
  X, TrendingDown, AlertTriangle, 
  Zap, DollarSign, Target, Calendar,
  Clock, Rocket, ArrowUpCircle, ArrowDownCircle, Scale,
  Banknote, Briefcase, Globe, BookOpen, CalendarClock, 
  Scissors, ShieldCheck, Info, FileText, Plus
} from 'lucide-react';
import type { Stock } from '../types';

// Types - Extend base types with Gomes fields
interface EnrichedPosition {
  id: number;
  ticker: string;
  company_name?: string | null;
  shares_count: number;
  avg_cost: number;
  current_price: number | null;
  currency?: string;
  unrealized_pl: number;
  unrealized_pl_percent: number;
  stock?: Stock;
  gomes_score: number | null;
  trend_status: 'BULLISH' | 'BEARISH' | 'NEUTRAL';
  is_deteriorated: boolean;
  target_weight_pct: number;
  weight_in_portfolio: number;
  gap_czk: number;
  optimal_size: number;
  action_signal: 'BUY' | 'HOLD' | 'SELL' | 'SNIPER';
  next_catalyst?: string;
}

interface EnrichedPosition {
  id: number;
  ticker: string;
  company_name?: string | null;
  shares_count: number;
  avg_cost: number;
  current_price: number | null;
  currency?: string;
  unrealized_pl: number;
  unrealized_pl_percent: number;
  stock?: Stock;
  gomes_score: number | null;
  trend_status: 'BULLISH' | 'BEARISH' | 'NEUTRAL';
  is_deteriorated: boolean;
  target_weight_pct: number;
  weight_in_portfolio: number;
  gap_czk: number;
  optimal_size: number;
  action_signal: 'BUY' | 'HOLD' | 'SELL' | 'SNIPER';
  next_catalyst?: string;
}

interface Props {
  position: EnrichedPosition;
  onClose: () => void;
  onUpdate?: () => void;
}

const StockDetailModalGomes: React.FC<Props> = ({ position, onClose }) => {
  const stock = position.stock;
  const currentPrice = stock?.current_price ?? position.current_price ?? 0;
  
  // State for Trim Modal
  const [showTrimModal, setShowTrimModal] = useState(false);
  const [trimShares, setTrimShares] = useState('');
  const [trimPrice, setTrimPrice] = useState('');
  
  // State for Transcript Analysis Modal
  const [showTranscriptModal, setShowTranscriptModal] = useState(false);
  const [sourceType, setSourceType] = useState<'youtube' | 'transcript' | 'manual'>('youtube');
  const [inputText, setInputText] = useState<string>('');
  const [investorName, setInvestorName] = useState<string>('Mark Gomes');
  const [analysisDate, setAnalysisDate] = useState<string>(new Date().toISOString().split('T')[0]);
  const [isAnalyzing, setIsAnalyzing] = useState<boolean>(false);
  
  // Temporary calculations (should come from backend)
  const cashRunwayMonths = stock?.cash_runway_months ?? null;
  const insiderActivity = stock?.insider_activity ?? 'HOLDING';
  const thesisNarrative = stock?.thesis_narrative ?? 
    'High-grade producer entering commercial stage. Operational leverage to commodity prices.';
  const inflectionStage = (stock?.inflection_status ?? 'UPCOMING') as 'WAIT_TIME' | 'UPCOMING' | 'ACTIVE_GOLD_MINE';
  
  // Valuation metrics
  const priceFloor = stock?.price_floor ?? currentPrice * 0.6;
  const priceBase = stock?.price_base ?? currentPrice * 2.0;
  const priceMoon = stock?.price_moon ?? currentPrice * 4.0;
  
  // Position discipline
  const maxAllocationPct = stock?.max_allocation_cap ?? 8.0;
  const isOverAllocated = position.weight_in_portfolio > maxAllocationPct;
  
  // Calculate price position on slider (FIX #2: Linear from Floor to Base, not Moon)
  // Floor $0.90 → Current $1.50 → Base $3.00
  // Position = (Current - Floor) / (Base - Floor) * 100
  const sliderRange = priceBase - priceFloor;
  const pricePosition = sliderRange > 0 ? ((currentPrice - priceFloor) / sliderRange) * 100 : 50;
  
  // Stage colors
  const stageConfig: Record<'WAIT_TIME' | 'UPCOMING' | 'ACTIVE_GOLD_MINE', { color: string; label: string; icon: typeof Clock }> = {
    WAIT_TIME: { color: 'red', label: 'The Wait Time', icon: Clock },
    UPCOMING: { color: 'yellow', label: 'Inflection Upcoming', icon: Zap },
    ACTIVE_GOLD_MINE: { color: 'green', label: 'The Gold Mine', icon: Rocket }
  };
  const stage = stageConfig[inflectionStage];
  
  // Cash runway status
  const getCashRunwayStatus = (months: number | null) => {
    if (months === null) return { color: 'slate', label: 'Unknown', severity: 'neutral' };
    if (months < 6) return { color: 'red', label: 'Critical', severity: 'danger' };
    if (months < 12) return { color: 'yellow', label: 'Watch', severity: 'warning' };
    return { color: 'green', label: 'Healthy', severity: 'safe' };
  };
  const runwayStatus = getCashRunwayStatus(cashRunwayMonths);
  
  // Insider activity color
  const insiderColor = insiderActivity === 'BUYING' ? 'green' : 
                       insiderActivity === 'SELLING' ? 'red' : 'slate';
  
  return (
    <div className="fixed inset-0 bg-black/90 backdrop-blur-sm z-50 flex items-center justify-center p-2">
      <div className="bg-slate-950 border border-slate-700 rounded-xl w-full max-w-7xl h-[95vh] flex flex-col overflow-hidden">
        
        {/* ======================================================================
            ROW 1: ULTRA-DENSE HEADER (Bloomberg Style)
            ====================================================================== */}
        <div className="bg-gradient-to-r from-slate-900 to-slate-800 border-b border-slate-700 px-4 py-2 flex items-center justify-between">
          {/* LEFT: Ticker + Price + Change */}
          <div className="flex items-center gap-4">
            <h2 className="text-3xl font-black text-white tracking-tight">{position.ticker}</h2>
            <div className="text-sm text-slate-400">{stock?.company_name || position.company_name || 'Unknown'}</div>
            <div className="h-8 w-px bg-slate-600" />
            <div className="flex items-baseline gap-2">
              <span className="text-2xl font-mono font-bold text-white">${currentPrice.toFixed(2)}</span>
              <span className={`text-sm font-mono ${position.unrealized_pl_percent >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                {position.unrealized_pl_percent >= 0 ? '+' : ''}{position.unrealized_pl_percent.toFixed(1)}%
              </span>
            </div>
          </div>
          
          {/* RIGHT: Status Badges + Score */}
          <div className="flex items-center gap-2">
            {/* Cash Runway Badge */}
            <div className={`px-2 py-1 rounded text-xs font-bold flex items-center gap-1.5 
              bg-${runwayStatus.color}-500/20 border border-${runwayStatus.color}-500/50 text-${runwayStatus.color}-400`}>
              <Banknote className="w-3 h-3" />
              Cash {cashRunwayMonths !== null ? `${cashRunwayMonths}m` : '?'} {runwayStatus.label}
            </div>
            
            {/* Insider Activity Badge */}
            <div className={`px-2 py-1 rounded text-xs font-bold flex items-center gap-1.5
              bg-${insiderColor}-500/20 border border-${insiderColor}-500/50 text-${insiderColor}-400`}>
              <Briefcase className="w-3 h-3" />
              {insiderActivity}
            </div>
            
            {/* Market Cap Badge */}
            {stock?.market_cap && (
              <div className="px-2 py-1 rounded text-xs font-bold flex items-center gap-1.5 bg-slate-700/50 border border-slate-600 text-slate-300">
                <Globe className="w-3 h-3" />
                ${(stock.market_cap / 1_000_000).toFixed(0)}M
              </div>
            )}
            
            <div className="h-8 w-px bg-slate-600 mx-1" />
            
            {/* Gomes Score */}
            <div className={`px-3 py-1 rounded-lg flex items-center gap-2 font-black text-lg border-2
              ${position.gomes_score && position.gomes_score >= 7 
                ? 'bg-green-500/30 text-green-400 border-green-500' :
                position.gomes_score && position.gomes_score >= 5 
                ? 'bg-yellow-500/30 text-yellow-400 border-yellow-500' :
                'bg-red-500/30 text-red-400 border-red-500'}`}>
              <Target className="w-4 h-4" />
              {position.gomes_score ?? '?'}/10
            </div>
            
            {/* Add Analysis Button */}
            <button
              onClick={() => setShowTranscriptModal(true)}
              className="px-3 py-2 bg-indigo-500 hover:bg-indigo-600 border border-indigo-400 rounded-lg text-sm text-white font-bold transition-colors flex items-center gap-2"
              title="Přidat analýzu z transkriptů"
            >
              <Plus className="w-4 h-4" />
              ANALÝZA
            </button>
            
            {/* Close Button */}
            <button onClick={onClose} className="ml-2 p-1.5 hover:bg-slate-700 rounded transition-colors">
              <X className="w-5 h-5 text-slate-400" />
            </button>
          </div>
        </div>

        {/* ======================================================================
            ROW 2: NARRATIVE & POSITION (2-Column Grid: 2/3 + 1/3)
            Height: ~35% of viewport
            ====================================================================== */}
        <div className="grid grid-cols-3 gap-3 p-3 h-[35vh] border-b border-slate-800">
          {/* LEFT COLUMN: INFLECTION ENGINE (2/3 width) */}
          <div className="col-span-2 bg-gradient-to-br from-slate-800/80 to-indigo-900/20 rounded-lg p-3 border border-indigo-500/20 flex flex-col">
            <h3 className="text-[10px] font-bold text-indigo-400 uppercase tracking-wider mb-2 flex items-center gap-1.5">
              <Zap className="w-3 h-3" /> INFLECTION ENGINE
            </h3>
            
            {/* The Thesis (2 lines max) */}
            <div className="mb-3">
              <div className="text-[10px] text-slate-500 mb-1 flex items-center gap-1">
                <BookOpen className="w-3 h-3 opacity-70" />
                THE SETUP
              </div>
              <p className="text-xs text-white leading-tight line-clamp-2">{thesisNarrative}</p>
            </div>
            
            {/* Stage */}
            <div className="mb-3">
              <div className="text-[10px] text-slate-500 mb-1">STAGE</div>
              <div className={`inline-flex items-center gap-1.5 px-2 py-1 rounded border text-[10px]
                bg-${stage.color}-500/20 border-${stage.color}-500/50 text-${stage.color}-400`}>
                <stage.icon className="w-3 h-3" />
                <span className="font-bold">{stage.label}</span>
              </div>
            </div>
            
            {/* Next Catalyst (Highlighted) */}
            <div className="flex-1">
              <div className="text-[10px] text-slate-500 mb-1.5 flex items-center gap-1">
                <CalendarClock className="w-3 h-3 opacity-70" />
                NEXT CATALYST
              </div>
              {position.next_catalyst ? (
                <div className="bg-indigo-500/20 border border-indigo-500/40 rounded-lg p-2 h-full flex items-center">
                  <div className="flex items-start gap-2">
                    <Calendar className="w-3 h-3 text-indigo-400 mt-0.5 flex-shrink-0" />
                    <div className="text-xs text-white leading-tight">{position.next_catalyst}</div>
                  </div>
                </div>
              ) : (
                <div className="bg-red-500/20 border border-red-500/40 rounded-lg p-2 h-full flex items-center justify-center">
                  <div className="flex items-center gap-2">
                    <AlertTriangle className="w-4 h-4 text-red-400" />
                    <span className="text-xs text-red-300 font-semibold">No catalyst - position questionable</span>
                  </div>
                </div>
              )}
              
              {/* LOGICAL ERROR WARNING: High Score but No Catalyst */}
              {position.gomes_score >= 9 && (!position.next_catalyst || position.next_catalyst.toUpperCase().includes('NO CATALYST')) && (
                <div className="mt-2 bg-yellow-500/20 border border-yellow-500/60 rounded-lg p-2">
                  <div className="flex items-start gap-2">
                    <AlertTriangle className="w-4 h-4 text-yellow-400 flex-shrink-0 mt-0.5" />
                    <div className="text-[10px] text-yellow-200 leading-tight">
                      <strong className="text-yellow-300 font-bold">⚠️ LOGICAL ERROR:</strong> High Score ({position.gomes_score}/10) but No Catalyst.
                      <br />
                      <span className="text-yellow-300/80">Score není obhajitelné bez konkrétního katalyzátoru. Doplň ručně (např. "Q1 High-Grade Sales").</span>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* RIGHT COLUMN: POSITION COMMAND (1/3 width) */}
          <div className="bg-gradient-to-br from-slate-800/80 to-purple-900/20 rounded-lg p-3 border border-purple-500/20 flex flex-col">
            <h3 className="text-[10px] font-bold text-purple-400 uppercase tracking-wider mb-2 flex items-center gap-1.5">
              <DollarSign className="w-3 h-3" /> POSITION COMMAND
            </h3>
            
            {/* Compact Risk Alert (if over-allocated) */}
            {isOverAllocated && (
              <div className="mb-2 p-2 bg-red-500/20 border border-red-500 rounded flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 text-red-400 flex-shrink-0" />
                <div className="text-[10px] text-red-300 font-bold">RISK: OVER-ALLOCATED</div>
              </div>
            )}
            
            {/* Trend Warning (if bearish) */}
            {position.trend_status === 'BEARISH' && (
              <div className="mb-2 p-2 bg-red-500/20 border border-red-500 rounded flex items-center gap-2">
                <TrendingDown className="w-4 h-4 text-red-400 flex-shrink-0" />
                <div className="text-[10px] text-red-300 font-bold">TREND BROKEN</div>
              </div>
            )}
            
            {/* Current vs Max Allocation */}
            <div className="mb-3">
              <div className="text-[10px] text-slate-500 mb-1">ALLOCATION</div>
              <div className="flex items-baseline gap-1">
                <span className="text-2xl font-black text-white">{position.weight_in_portfolio.toFixed(1)}%</span>
                <span className="text-xs text-slate-400">/ {maxAllocationPct}%</span>
              </div>
              <div className="h-1.5 bg-slate-700 rounded-full overflow-hidden mt-1.5">
                <div 
                  className={`h-full ${isOverAllocated ? 'bg-red-500' : 'bg-green-500'}`}
                  style={{ width: `${Math.min(100, (position.weight_in_portfolio / maxAllocationPct) * 100)}%` }}
                />
              </div>
            </div>
            
            {/* Action Button (TRIM or ACCUMULATE) */}
            <div className="flex-1 flex flex-col justify-center">
              {isOverAllocated ? (
                <button 
                  onClick={() => setShowTrimModal(true)}
                  className="w-full py-3 bg-red-500 hover:bg-red-600 text-white font-black text-sm rounded-lg border-2 border-red-400 transition-colors flex items-center justify-center gap-2"
                >
                  <Scissors className="w-4 h-4" />
                  TRIM POSITION
                </button>
              ) : position.optimal_size > 0 ? (
                <button className="w-full py-3 bg-green-500 hover:bg-green-600 text-white font-black text-sm rounded-lg border-2 border-green-400 transition-colors">
                  ACCUMULATE
                </button>
              ) : (
                <button className="w-full py-3 bg-slate-600 text-slate-300 font-black text-sm rounded-lg border-2 border-slate-500 cursor-not-allowed flex items-center justify-center gap-2">
                  <ShieldCheck className="w-4 h-4" />
                  HOLD
                </button>
              )}
              
              {/* Gap Display */}
              <div className="mt-2 text-center">
                <div className="text-[10px] text-slate-500">OPTIMAL SIZE</div>
                <div className={`text-lg font-bold font-mono ${position.optimal_size < 0 ? 'text-red-400' : 'text-white'}`}>
                  {position.optimal_size < 0 ? '-' : '+'}{Math.abs(position.optimal_size).toLocaleString('cs-CZ')} Kč
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* ======================================================================
            ROW 3: THE TRADING DECK (Compact Table Layout)
            Height: ~40% of viewport
            ====================================================================== */}
        <div className="px-3 pb-3 pt-2 bg-slate-900/50">
          <h3 className="text-xs font-bold text-amber-400 uppercase tracking-wider mb-2 flex items-center gap-2">
            <Target className="w-4 h-4" /> THE TRADING DECK
          </h3>
          
          <div className="grid grid-cols-3 gap-2">
            {/* BLOCK 1: DOWNSIDE REALITY - Table Format */}
            <div className="bg-gradient-to-br from-red-900/20 to-slate-800 rounded-lg border border-red-500/30 overflow-hidden">
              <div className="bg-red-500/10 px-2 py-1.5 border-b border-red-500/30 flex items-center justify-between">
                <div className="flex items-center gap-1.5">
                  <ArrowDownCircle className="w-3 h-3 text-red-400" />
                  <span className="text-[10px] font-bold text-red-400 uppercase">DOWNSIDE</span>
                </div>
                <div className="group relative">
                  <Info className="w-3 h-3 text-slate-500 cursor-help" />
                  <div className="absolute right-0 top-full mt-1 w-48 p-2 bg-slate-950 border border-slate-700 rounded text-[9px] text-slate-300 hidden group-hover:block z-10">
                    Hodnocení rizika: Likvidační hodnota vs technická podpora
                  </div>
                </div>
              </div>
              <div className="p-2 space-y-1">
                <div className="grid grid-cols-2 text-xs">
                  <span className="text-slate-500">Liquidation Floor</span>
                  <span className="text-red-400 font-mono font-bold text-right">${priceFloor.toFixed(2)}</span>
                </div>
                {position.stock?.green_line && (
                  <div className="grid grid-cols-2 text-xs">
                    <span className="text-slate-500">Tech. Support</span>
                    <span className="text-green-400 font-mono font-bold text-right">${position.stock.green_line.toFixed(2)}</span>
                  </div>
                )}
                {position.stock?.max_buy_price && (
                  <div className="grid grid-cols-2 text-xs">
                    <span className="text-slate-500">Buy Limit</span>
                    <span className="text-green-300 font-mono text-right">${position.stock.max_buy_price.toFixed(2)}</span>
                  </div>
                )}
                <div className="grid grid-cols-2 text-xs pt-1 border-t border-slate-700">
                  <span className="text-slate-500 font-bold">Risk to Floor</span>
                  <span className="text-red-400 font-bold text-right">
                    {position.stock?.risk_to_floor_pct 
                      ? `${position.stock.risk_to_floor_pct.toFixed(0)}%`
                      : `${((priceFloor / currentPrice - 1) * 100).toFixed(0)}%`}
                  </span>
                </div>
              </div>
            </div>

            {/* BLOCK 2: CURRENT PRICE - Compact */}
            <div className="bg-gradient-to-br from-slate-800 to-slate-900 rounded-lg border border-slate-600 overflow-hidden">
              <div className="bg-slate-700/30 px-2 py-1.5 border-b border-slate-600 flex items-center justify-between">
                <div className="flex items-center gap-1.5">
                  <Scale className="w-3 h-3 text-blue-400" />
                  <span className="text-[10px] font-bold text-blue-400 uppercase">CURRENT</span>
                </div>
              </div>
              <div className="p-2">
                <div className="text-center mb-2">
                  <div className="text-3xl font-black font-mono text-blue-400">${currentPrice.toFixed(2)}</div>
                </div>
                
                {/* Compact Slider */}
                <div className="mb-2">
                  <div className="relative h-3 bg-slate-700 rounded-full mb-1">
                    <div className="absolute inset-0 bg-gradient-to-r from-red-500 via-yellow-500 to-green-500 rounded-full opacity-40" />
                    <div 
                      className="absolute top-1/2 -translate-y-1/2 w-4 h-4 bg-white border-2 border-blue-500 rounded-full shadow-lg"
                      style={{ left: `${pricePosition}%`, transform: 'translate(-50%, -50%)' }}
                    />
                  </div>
                  <div className="grid grid-cols-3 text-[8px]">
                    <span className="text-red-400 font-bold">Floor</span>
                    <span className="text-yellow-400 font-bold text-center">Base</span>
                    <span className="text-green-400 font-bold text-right">Moon</span>
                  </div>
                </div>
                
                {/* Signal Badge */}
                {position.stock?.trading_zone_signal && (
                  <div className="text-center">
                    <div className={`inline-flex items-center gap-1 px-2 py-1 rounded text-xs font-bold border\n                      ${isOverAllocated ? 'bg-red-500/20 text-red-400 border-red-500' :
                        position.stock.trading_zone_signal.includes('BUY') ? 'bg-green-500/20 text-green-400 border-green-500' :
                        position.stock.trading_zone_signal.includes('SELL') ? 'bg-red-500/20 text-red-400 border-red-500' :
                        'bg-slate-600/20 text-slate-400 border-slate-600'}`}>
                      {isOverAllocated ? (
                        <>
                          <Scissors className="w-2.5 h-2.5" />
                          TRIM (RISK)
                        </>
                      ) : (
                        position.stock.trading_zone_signal
                      )}
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* BLOCK 3: UPSIDE POTENTIAL - Table Format */}
            <div className="bg-gradient-to-br from-green-900/20 to-slate-800 rounded-lg border border-green-500/30 overflow-hidden">
              <div className="bg-green-500/10 px-2 py-1.5 border-b border-green-500/30 flex items-center justify-between">
                <div className="flex items-center gap-1.5">
                  <ArrowUpCircle className="w-3 h-3 text-green-400" />
                  <span className="text-[10px] font-bold text-green-400 uppercase">UPSIDE</span>
                </div>
                <div className="group relative">
                  <Info className="w-3 h-3 text-slate-500 cursor-help" />
                  <div className="absolute right-0 top-full mt-1 w-48 p-2 bg-slate-950 border border-slate-700 rounded text-[9px] text-slate-300 hidden group-hover:block z-10">
                    Potenciál růstu: Technický odpor vs fundamentální cíl
                  </div>
                </div>
              </div>
              <div className="p-2 space-y-1">
                {position.stock?.red_line && (
                  <div className="grid grid-cols-2 text-xs">
                    <span className="text-slate-500">Tech. Resistance</span>
                    <span className="text-red-400 font-mono font-bold text-right">${position.stock.red_line.toFixed(2)}</span>
                  </div>
                )}
                {position.stock?.start_sell_price && (
                  <div className="grid grid-cols-2 text-xs">
                    <span className="text-slate-500">Sell Alert</span>
                    <span className="text-red-300 font-mono text-right">${position.stock.start_sell_price.toFixed(2)}</span>
                  </div>
                )}
                <div className="grid grid-cols-2 text-xs">
                  <span className="text-slate-500">Moon Target</span>
                  <span className="text-green-400 font-mono font-bold text-right">${priceMoon.toFixed(2)}</span>
                </div>
                <div className="grid grid-cols-2 text-xs pt-1 border-t border-slate-700">
                  <span className="text-slate-500 font-bold">R/R Ratio</span>
                  <span className={`font-bold text-right ${
                    ((position.stock?.upside_to_ceiling_pct || 0) / Math.abs(position.stock?.risk_to_floor_pct || 1)) >= 3 ? 'text-green-400' :
                    ((position.stock?.upside_to_ceiling_pct || 0) / Math.abs(position.stock?.risk_to_floor_pct || 1)) >= 2 ? 'text-yellow-400' :
                    'text-red-400'
                  }`}>
                    {position.stock?.upside_to_ceiling_pct && position.stock?.risk_to_floor_pct
                      ? `${(position.stock.upside_to_ceiling_pct / Math.abs(position.stock.risk_to_floor_pct)).toFixed(1)}:1`
                      : `${((priceMoon / currentPrice - 1) * 100 / Math.abs((priceFloor / currentPrice - 1) * 100)).toFixed(1)}:1`}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* ======================================================================
            TRADING DECK LEGEND: Vysvětlivky
            ====================================================================== */}
        <div className="px-3 py-2 bg-slate-900/50 border-t border-slate-800">
          <div className="grid grid-cols-3 gap-4 text-[10px]">
            {/* Downside Legend */}
            <div className="space-y-1">
              <div className="text-red-400 font-bold mb-1.5 flex items-center gap-1">
                <ArrowDownCircle className="w-3 h-3" />
                DOWNSIDE VYSVĚTLIVKY
              </div>
              <div className="text-slate-400 leading-tight">
                <strong className="text-green-400">Liquidation Floor:</strong> Minimální hodnota podle zůstatkové ceny aktiv
              </div>
              <div className="text-slate-400 leading-tight">
                <strong className="text-green-300">Tech. Support:</strong> Technická podpora z grafu (kde kupují velcí)
              </div>
              <div className="text-slate-400 leading-tight">
                <strong className="text-slate-300">Buy Limit:</strong> Tvůj maximální nákup (pokud klesne až sem)
              </div>
              <div className="text-slate-400 leading-tight">
                <strong className="text-red-400">Risk to Floor:</strong> Kolik můžeš ztratit při pádu na dno
              </div>
            </div>

            {/* Current Legend */}
            <div className="space-y-1">
              <div className="text-blue-400 font-bold mb-1.5 flex items-center gap-1">
                <Scale className="w-3 h-3" />
                CURRENT VYSVĚTLIVKY
              </div>
              <div className="text-slate-400 leading-tight">
                <strong className="text-blue-400">Slider:</strong> Kde je cena vzhledem k Floor (červená) → Base (žlutá) → Moon (zelená)
              </div>
              <div className="text-slate-400 leading-tight">
                <strong className="text-green-400">BUY Zone:</strong> Cena je blízko dna → bezpečná koupě
              </div>
              <div className="text-slate-400 leading-tight">
                <strong className="text-red-400">SELL Zone:</strong> Cena je vysoko → riskantní držet
              </div>
            </div>

            {/* Upside Legend */}
            <div className="space-y-1">
              <div className="text-green-400 font-bold mb-1.5 flex items-center gap-1">
                <ArrowUpCircle className="w-3 h-3" />
                UPSIDE VYSVĚTLIVKY
              </div>
              <div className="text-slate-400 leading-tight">
                <strong className="text-red-400">Tech. Resistance:</strong> Kde prodávají velcí (technický odpor)
              </div>
              <div className="text-slate-400 leading-tight">
                <strong className="text-red-300">Sell Alert:</strong> Kde začneš brát zisky (první výstup)
              </div>
              <div className="text-slate-400 leading-tight">
                <strong className="text-green-400">Moon Target:</strong> Maximální cíl podle fundamentů
              </div>
              <div className="text-slate-400 leading-tight">
                <strong className="text-yellow-400">R/R Ratio:</strong> Risk/Reward poměr (3:1 = super, 1:1 = riskantní)
              </div>
            </div>
          </div>
        </div>

        {/* ======================================================================
            FOOTER: Historical P/L (De-emphasized)
            ====================================================================== */}
        <div className="px-3 pb-2 mt-auto">
          <div className="bg-slate-800/30 rounded px-3 py-1.5 border border-slate-700/50 flex items-center justify-between">
            <span className="text-[10px] text-slate-500">Historical P/L (reference only)</span>
            <div className="flex items-center gap-3 text-xs">
              <span className={`font-mono ${position.unrealized_pl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                {position.unrealized_pl >= 0 ? '+' : ''}{position.unrealized_pl.toFixed(2)} {position.currency || 'USD'}
              </span>
              <span className={`font-bold ${position.unrealized_pl_percent >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                ({position.unrealized_pl_percent >= 0 ? '+' : ''}{position.unrealized_pl_percent.toFixed(1)}%)
              </span>
            </div>
          </div>
        </div>

      </div>
      
      {/* ======================================================================
          TRIM MODAL: Log Transaction
          ====================================================================== */}
      {showTrimModal && (
        <div className="fixed inset-0 bg-black/90 backdrop-blur-sm z-[60] flex items-center justify-center p-4">
          <div className="bg-slate-900 border-2 border-red-500 rounded-xl w-full max-w-md">
            {/* Header */}
            <div className="bg-gradient-to-r from-red-900/50 to-slate-800 border-b border-red-500/30 p-4 flex items-center justify-between">
              <div>
                <h3 className="text-lg font-black text-white flex items-center gap-2">
                  <Scissors className="w-5 h-5 text-red-400" />
                  Exekuce strategie: Ořezání pozice
                </h3>
                <p className="text-xs text-slate-400 mt-1">{position.ticker}</p>
              </div>
              <button 
                onClick={() => setShowTrimModal(false)}
                className="p-1.5 hover:bg-slate-700 rounded transition-colors"
              >
                <X className="w-5 h-5 text-slate-400" />
              </button>
            </div>

            {/* Body */}
            <div className="p-6 space-y-6">
              {/* Doporučení */}
              <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-4">
                <div className="flex items-start gap-3">
                  <AlertTriangle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
                  <div>
                    <div className="text-sm font-bold text-red-400 mb-1">Doporučení aplikace</div>
                    <div className="text-sm text-white">
                      Abyste se dostali na limit <span className="font-bold text-red-400">{maxAllocationPct}%</span>, 
                      prodejte akcie v hodnotě <span className="font-bold text-red-400">{Math.abs(position.optimal_size).toLocaleString('cs-CZ')} Kč</span>.
                    </div>
                  </div>
                </div>
              </div>

              {/* Info: Current Holdings */}
              <div className="bg-slate-800/50 rounded-lg p-3 text-xs">
                <div className="flex justify-between mb-1">
                  <span className="text-slate-400">Aktuální počet kusů:</span>
                  <span className="text-white font-bold">{position.shares_count}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Průměrná cena:</span>
                  <span className="text-white font-bold">${position.avg_cost.toFixed(2)}</span>
                </div>
              </div>

              {/* Form */}
              <div className="space-y-4">
                <div>
                  <label className="block text-xs text-slate-400 mb-2">Počet prodaných kusů</label>
                  <input
                    type="number"
                    value={trimShares}
                    onChange={(e) => setTrimShares(e.target.value)}
                    placeholder="Zadejte počet kusů"
                    className="w-full px-4 py-3 bg-slate-800 border border-slate-600 rounded-lg text-white placeholder-slate-500 focus:border-red-500 focus:outline-none focus:ring-2 focus:ring-red-500/20"
                    min="1"
                    max={position.shares_count}
                  />
                </div>

                <div>
                  <label className="block text-xs text-slate-400 mb-2">Prodejní cena (za kus)</label>
                  <input
                    type="number"
                    value={trimPrice}
                    onChange={(e) => setTrimPrice(e.target.value)}
                    placeholder="Zadejte prodejní cenu"
                    step="0.01"
                    className="w-full px-4 py-3 bg-slate-800 border border-slate-600 rounded-lg text-white placeholder-slate-500 focus:border-red-500 focus:outline-none focus:ring-2 focus:ring-red-500/20"
                  />
                </div>

                {/* Preview Calculation */}
                {trimShares && trimPrice && (
                  <div className="bg-slate-800/50 border border-slate-600 rounded-lg p-3 text-xs space-y-1">
                    <div className="flex justify-between">
                      <span className="text-slate-400">Hodnota transakce:</span>
                      <span className="text-white font-bold">
                        ${(parseFloat(trimShares) * parseFloat(trimPrice)).toFixed(2)}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-400">Zbývající kusy:</span>
                      <span className="text-white font-bold">
                        {position.shares_count - parseFloat(trimShares)}
                      </span>
                    </div>
                  </div>
                )}
              </div>

              {/* Actions */}
              <div className="flex gap-3">
                <button
                  onClick={() => setShowTrimModal(false)}
                  className="flex-1 py-3 bg-slate-700 hover:bg-slate-600 text-white font-bold rounded-lg transition-colors"
                >
                  Zrušit
                </button>
                <button
                  onClick={() => {
                    // TODO: Call API to save transaction
                    console.log('Saving trim transaction:', {
                      ticker: position.ticker,
                      shares: parseFloat(trimShares),
                      price: parseFloat(trimPrice)
                    });
                    setShowTrimModal(false);
                    setTrimShares('');
                    setTrimPrice('');
                  }}
                  disabled={!trimShares || !trimPrice || parseFloat(trimShares) <= 0 || parseFloat(trimPrice) <= 0}
                  className="flex-1 py-3 bg-red-500 hover:bg-red-600 text-white font-black rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  Uložit transakci
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
      
      {/* ======================================================================
          TRANSCRIPT ANALYSIS MODAL: Add Analysis from Transcripts
          ====================================================================== */}
      {showTranscriptModal && (
        <div className="fixed inset-0 bg-black/90 backdrop-blur-sm z-[60] flex items-center justify-center p-4">
          <div className="bg-slate-900 border-2 border-indigo-500 rounded-xl w-full max-w-2xl">
            {/* Header */}
            <div className="bg-gradient-to-r from-indigo-900/50 to-slate-800 border-b border-indigo-500/30 p-4 flex items-center justify-between">
              <div>
                <h3 className="text-lg font-black text-white flex items-center gap-2">
                  <FileText className="w-5 h-5 text-indigo-400" />
                  Přidat analýzu z transkriptů
                </h3>
                <p className="text-xs text-slate-400 mt-1">{position.ticker} - {stock?.company_name}</p>
              </div>
              <button 
                onClick={() => setShowTranscriptModal(false)}
                className="p-1.5 hover:bg-slate-700 rounded transition-colors"
              >
                <X className="w-5 h-5 text-slate-400" />
              </button>
            </div>

            {/* Body */}
            <div className="p-6 space-y-6">
              {/* Info Box */}
              <div className="bg-indigo-500/10 border border-indigo-500/30 rounded-lg p-4">
                <div className="flex items-start gap-3">
                  <Info className="w-5 h-5 text-indigo-400 flex-shrink-0 mt-0.5" />
                  <div className="text-sm text-white">
                    <div className="font-bold mb-2">Gomes Guardian Intelligence Unit</div>
                    <div className="text-xs space-y-1">
                      <div>• AI <strong>auto-detektuje typ zdroje</strong> (Official Filing, Chat, Analyst Report)</div>
                      <div>• <strong>Různá logika pro každý typ</strong>: 100% spolehlivost (filings) vs 30% (chat)</div>
                      <div>• Chat: Extrahuje sentiment, rumory, key voices (Florian, Gomes)</div>
                      <div>• Official: Tvrdá čísla, penalty za chybějící cash</div>
                    </div>
                  </div>
                </div>
              </div>

              {/* Source Type Selector */}
              <div className="bg-slate-800/50 border border-slate-700 rounded-lg p-4">
                <div className="flex items-center gap-2 mb-3">
                  <FileText className="w-4 h-4 text-slate-400" />
                  <span className="text-sm font-bold text-white">Typ zdroje</span>
                  <span className="text-xs text-slate-500 ml-auto">AI detekuje automaticky</span>
                </div>
                <select
                  value={sourceType}
                  onChange={(e) => setSourceType(e.target.value as 'youtube' | 'transcript' | 'manual')}
                  className="w-full px-4 py-3 bg-slate-800 border border-slate-600 rounded-lg text-white focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/20"
                >
                  <option value="youtube">📹 YouTube URL (Auto-transcript)</option>
                  <option value="transcript">📄 Transkript / Text (Official/Chat/Article)</option>
                  <option value="manual">✍️ Manuální poznámky</option>
                </select>
              </div>

              {/* Input Field */}
              <div>
                <label className="block text-xs text-slate-400 mb-2">
                  {sourceType === 'youtube' ? 'YouTube URL' : sourceType === 'transcript' ? 'Transkript / Text zdroje' : 'Poznámky / Analýza'}
                </label>
                <textarea
                  value={inputText}
                  onChange={(e) => setInputText(e.target.value)}
                    placeholder={
                      sourceType === 'youtube' 
                        ? 'https://youtube.com/watch?v=...' 
                        : sourceType === 'transcript'
                        ? 'Příklady:\n• Official Filing: "Q3 2025 Results: Revenue $2.1M, Cash $8.2M..."\n• Chat: "Florian: Nejsem si jist managementem... Josh: Solid business..."\n• Analyst Report: "Substack analýza od X, price target $5..."'
                        : 'Vložte vlastní poznámky z výzkumu...'
                    }
                    rows={10}
                    className="w-full px-4 py-3 bg-slate-800 border border-slate-600 rounded-lg text-white placeholder-slate-500 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 font-mono text-sm"
                  ></textarea>
                  <div className="mt-2 text-xs text-slate-500">
                    {sourceType === 'transcript' && (
                      <div>
                        💡 <strong>Tip:</strong> AI automaticky rozpozná, zda jde o official filing (100% spolehlivost), 
                        chat diskuzi (sentiment + rumory), nebo analyst report
                      </div>
                    )}
                  </div>
                </div>

              {/* Quick Fields */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs text-slate-400 mb-2">Investor / Zdroj</label>
                  <input
                    type="text"
                    placeholder="Mark Gomes"
                    value={investorName}
                    onChange={(e) => setInvestorName(e.target.value)}
                    className="w-full px-4 py-2 bg-slate-800 border border-slate-600 rounded-lg text-white placeholder-slate-500 focus:border-indigo-500 focus:outline-none"
                  />
                </div>
                <div>
                  <label className="block text-xs text-slate-400 mb-2">Datum videa/analýzy</label>
                  <input
                    type="date"
                    value={analysisDate}
                    onChange={(e) => setAnalysisDate(e.target.value)}
                    className="w-full px-4 py-2 bg-slate-800 border border-slate-600 rounded-lg text-white focus:border-indigo-500 focus:outline-none"
                  />
                </div>
              </div>

              {/* Actions */}
              <div className="flex gap-3">
                <button
                  onClick={() => setShowTranscriptModal(false)}
                  className="flex-1 py-3 bg-slate-700 hover:bg-slate-600 text-white font-bold rounded-lg transition-colors"
                >
                  Zrušit
                </button>
                <button
                  onClick={async () => {
                    if (inputText.length < 50) {
                      alert('Text je příliš krátký - vložte alespoň 50 znaků');
                      return;
                    }
                    
                    setIsAnalyzing(true);
                    try {
                      const response = await fetch('http://127.0.0.1:8002/api/intelligence/analyze-ticker', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                          ticker: position.ticker,
                          source_type: sourceType,
                          input_text: inputText,
                          investor_name: investorName,
                          analysis_date: analysisDate
                        })
                      });
                      
                      if (!response.ok) {
                        const error = await response.json();
                        throw new Error(error.detail || 'Analýza selhala');
                      }
                      
                      const result = await response.json();
                      
                      // Build detailed alert message
                      let alertMsg = '';
                      
                      // Show warnings if any
                      if (result.warning_messages && result.warning_messages.length > 0) {
                        alertMsg += `⚠️ VAROVÁNÍ:\n\n${result.warning_messages.join('\n\n')}`;
                      } else {
                        alertMsg += `✅ Analýza dokončena!\n\n`;
                      }
                      
                      alertMsg += `\nGomes Score: ${result.gomes_score}/10`;
                      alertMsg += `\nStage: ${result.inflection_status}`;
                      alertMsg += `\nDoporučení: ${result.recommendation}`;
                      
                      // Display result
                      alert(alertMsg);
                      
                      // Refresh page to show updated data
                      window.location.reload();
                      
                    } catch (error) {
                      console.error('Analýza selhala:', error);
                      alert(`❌ Chyba při analýze: ${error instanceof Error ? error.message : 'Neznámá chyba'}`);
                    } finally {
                      setIsAnalyzing(false);
                    }
                  }}
                  disabled={isAnalyzing || inputText.length < 50}
                  className="flex-1 py-3 bg-indigo-500 hover:bg-indigo-600 disabled:bg-slate-700 disabled:cursor-not-allowed text-white font-black rounded-lg transition-colors flex items-center justify-center gap-2"
                >
                  {isAnalyzing ? (
                    <>
                      <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin"></div>
                      Analyzuji...
                    </>
                  ) : (
                    <>
                      <FileText className="w-4 h-4" />
                      Analyzovat a uložit
                    </>
                  )}
                </button>
              </div>

              {/* Helper Text */}
              <div className="text-xs text-slate-500 text-center">
                AI extrahuje: thesis, catalyst, stage, insider activity, risk faktory
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default StockDetailModalGomes;
