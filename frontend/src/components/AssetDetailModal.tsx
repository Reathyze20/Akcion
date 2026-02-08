/**
 * Stock Detail Modal - Enterprise Edition
 * ==================================
 * Redesigned according to Investment Committee investment methodology:
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
  Scissors, ShieldCheck, Info, FileText, Plus, HelpCircle
} from 'lucide-react';
import type { Stock } from '../types';
import { GatekeeperShield } from './GatekeeperShield';
import { useGatekeeperStatus } from '../hooks/useGatekeeperStatus';

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
  conviction_score: number | null;
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
  conviction_score: number | null;
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

const AssetDetailModal: React.FC<Props> = ({ position, onClose }) => {
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
  const [investorName, setInvestorName] = useState<string>('Investment Committee');
  const [analysisDate, setAnalysisDate] = useState<string>(new Date().toISOString().split('T')[0]);
  const [isAnalyzing, setIsAnalyzing] = useState<boolean>(false);
  
  // State for Edit Mode
  const [showEditModal, setShowEditModal] = useState(false);
  
  // State for Legend Popup
  const [showLegend, setShowLegend] = useState(false);
  const [editedData, setEditedData] = useState({
    next_catalyst: stock?.next_catalyst ?? '',
    thesis_narrative: stock?.thesis_narrative ?? '',
    conviction_score: stock?.conviction_score ?? 5,
    inflection_status: stock?.inflection_status ?? 'WAIT_TIME',
    price_floor: stock?.price_floor ?? 0,
    price_base: stock?.price_base ?? 0,
    price_moon: stock?.price_moon ?? 0,
    stop_loss_price: stock?.stop_loss_price ?? 0,
    max_allocation_cap: stock?.max_allocation_cap ?? 10,
    cash_runway_months: stock?.cash_runway_months ?? null,
  });
  const [isSaving, setIsSaving] = useState(false);
  
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
  
  // Handle manual edit save
  const handleSaveEdit = async () => {
    setIsSaving(true);
    try {
      const response = await fetch(`http://127.0.0.1:8002/api/stocks/${position.ticker}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(editedData)
      });
      
      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Uložení selhalo');
      }
      
      alert('✅ Údaje úspěšně uloženy!');
      window.location.reload();
      
    } catch (error) {
      console.error('Uložení selhalo:', error);
      alert(`❌ Chyba při ukládání: ${error instanceof Error ? error.message : 'Neznámá chyba'}`);
    } finally {
      setIsSaving(false);
    }
  };

  const handleCancelEdit = () => {
    setShowEditModal(false);
    setEditedData({
      next_catalyst: stock?.next_catalyst ?? '',
      thesis_narrative: stock?.thesis_narrative ?? '',
      conviction_score: stock?.conviction_score ?? 5,
      inflection_status: stock?.inflection_status ?? 'WAIT_TIME',
      price_floor: stock?.price_floor ?? 0,
      price_base: stock?.price_base ?? 0,
      price_moon: stock?.price_moon ?? 0,
      stop_loss_price: stock?.stop_loss_price ?? 0,
      max_allocation_cap: stock?.max_allocation_cap ?? 10,
      cash_runway_months: stock?.cash_runway_months ?? null,
    });
  };
  
  // ============================================================================
  // GATEKEEPER SHIELD - Fiduciary Protection Layer
  // ============================================================================
  // Convert inflection status to Weinstein stage number
  const getWeinsteinStage = (): 1 | 2 | 3 | 4 | null => {
    // If we have explicit stage data from backend, use it
    // Otherwise, infer from trend_status and inflection_status
    if (position.trend_status === 'BEARISH') return 4;
    if (inflectionStage === 'WAIT_TIME') return 1;
    if (inflectionStage === 'UPCOMING') return 2;
    if (inflectionStage === 'ACTIVE_GOLD_MINE') return 3;
    return null;
  };

  const gatekeeperAnalysis = {
    cash_runway_months: cashRunwayMonths,
    stock_price: currentPrice,
    wma_30: stock?.green_line ?? currentPrice * 0.9, // Use green_line as proxy for 30 WMA
    stage_analysis: getWeinsteinStage(),
    gomes_score: position.conviction_score,
  };

  // Get shield status for conditional rendering
  const shieldStatus = useGatekeeperStatus(gatekeeperAnalysis);
  const isBuyBlocked = shieldStatus.hideBuyButton;
  
  return (
    <div className="fixed inset-0 bg-black/90 backdrop-blur-sm z-50 flex items-center justify-center p-2">
      <GatekeeperShield analysis={gatekeeperAnalysis}>
      <div className="bg-surface-base border border-border rounded-xl w-full max-w-7xl h-[95vh] flex flex-col overflow-hidden">
        
        {/* ======================================================================
            ROW 1: ULTRA-DENSE HEADER (Bloomberg Style)
            ====================================================================== */}
        <div className="bg-surface-overlay border-b border-border px-4 py-2 flex items-center justify-between">
          {/* LEFT: Ticker + Price + Change */}
          <div className="flex items-center gap-4">
            <h2 className="text-3xl font-black text-text-primary tracking-tight">{position.ticker}</h2>
            <div className="text-sm text-text-secondary">{stock?.company_name || position.company_name || 'Unknown'}</div>
            <div className="h-8 w-px bg-border" />
            <div className="flex items-baseline gap-2">
              <span className="text-2xl font-mono font-bold text-text-primary">${currentPrice.toFixed(2)}</span>
              <span className={`text-sm font-mono ${position.unrealized_pl_percent >= 0 ? 'text-positive' : 'text-negative'}`}>
                {position.unrealized_pl_percent >= 0 ? '+' : ''}{position.unrealized_pl_percent.toFixed(1)}%
              </span>
            </div>
          </div>
          
          {/* RIGHT: Status Badges + Score */}
          <div className="flex items-center gap-2">
            {/* Cash Runway Badge */}
            <div className={`px-2 py-1 rounded text-xs font-bold flex items-center gap-1.5 
              ${runwayStatus.severity === 'danger' ? 'bg-negative-bg border border-negative-border text-negative' :
                runwayStatus.severity === 'warning' ? 'bg-warning-bg border border-warning-border text-warning' :
                runwayStatus.severity === 'safe' ? 'bg-positive-bg border border-positive-border text-positive' :
                'bg-surface-hover border border-border text-text-secondary'}`}>
              <Banknote className="w-3 h-3" />
              Cash {cashRunwayMonths !== null ? `${cashRunwayMonths}m` : '?'} {runwayStatus.label}
            </div>
            
            {/* Insider Activity Badge */}
            <div className={`px-2 py-1 rounded text-xs font-bold flex items-center gap-1.5
              ${insiderActivity === 'BUYING' ? 'bg-positive-bg border border-positive-border text-positive' :
                insiderActivity === 'SELLING' ? 'bg-negative-bg border border-negative-border text-negative' :
                'bg-surface-hover border border-border text-text-secondary'}`}>
              <Briefcase className="w-3 h-3" />
              {insiderActivity}
            </div>
            
            {/* Market Cap Badge */}
            {stock?.market_cap && (
              <div className="px-2 py-1 rounded text-xs font-bold flex items-center gap-1.5 bg-surface-hover border border-border text-text-secondary">
                <Globe className="w-3 h-3" />
                ${(stock.market_cap / 1_000_000).toFixed(0)}M
              </div>
            )}
            
            <div className="h-8 w-px bg-border mx-1" />
            
            {/* Conviction Score */}
            <div className={`px-3 py-1 rounded-lg flex items-center gap-2 font-black text-lg border-2
              ${position.conviction_score && position.conviction_score >= 7 
                ? 'bg-positive-bg text-positive border-positive' :
                position.conviction_score && position.conviction_score >= 5 
                ? 'bg-warning-bg text-warning border-warning' :
                'bg-negative-bg text-negative border-negative'}`}>
              <Target className="w-4 h-4" />
              {position.conviction_score ?? '?'}/10
            </div>
            
            {/* Add Analysis Button */}
            <button
              onClick={() => setShowTranscriptModal(true)}
              className="px-3 py-2 bg-surface-active hover:bg-surface-hover border border-border rounded-lg text-sm text-text-primary font-bold transition-colors flex items-center gap-2"
              title="Přidat analýzu z transkriptů"
            >
              <Plus className="w-4 h-4" />
              ANALÝZA
            </button>
            
            {/* Edit/Save Buttons */}
            {!showEditModal ? (
              <button
                onClick={() => setShowEditModal(true)}
                className="px-3 py-2 bg-surface-active hover:bg-surface-hover border border-border rounded-lg text-sm text-text-primary font-bold transition-colors flex items-center gap-2"
                title="Ručně upravit údaje"
              >
                <FileText className="w-4 h-4" />
                UPRAVIT
              </button>
            ) : null}
            
            {/* Close Button */}
            <button onClick={onClose} className="ml-2 p-1.5 hover:bg-surface-hover rounded transition-colors">
              <X className="w-5 h-5 text-text-muted" />
            </button>
          </div>
        </div>

        {/* ======================================================================
            ROW 2: NARRATIVE & POSITION (2-Column Grid: 2/3 + 1/3)
            Height: ~35% of viewport
            ====================================================================== */}
        <div className="grid grid-cols-3 gap-3 p-3 h-[35vh] border-b border-border">
          {/* LEFT COLUMN: INFLECTION ENGINE (2/3 width) */}
          <div className="col-span-2 bg-surface-raised rounded-lg p-3 border border-border flex flex-col">
            <h3 className="text-[10px] font-bold text-text-secondary uppercase tracking-wider mb-2 flex items-center gap-1.5">
              <Zap className="w-3 h-3" /> INFLECTION ENGINE
            </h3>
            
            {/* The Thesis (2 lines max) */}
            <div className="mb-3">
              <div className="text-[10px] text-text-muted mb-1 flex items-center gap-1">
                <BookOpen className="w-3 h-3 opacity-70" />
                THE SETUP
              </div>
              <p className="text-xs text-text-primary leading-tight line-clamp-2">{thesisNarrative}</p>
            </div>
            
            {/* Stage */}
            <div className="mb-3">
              <div className="text-[10px] text-text-muted mb-1">STAGE</div>
              <div className={`inline-flex items-center gap-1.5 px-2 py-1 rounded border text-[10px]
                ${stage.color === 'red' ? 'bg-negative-bg border-negative-border text-negative' :
                  stage.color === 'yellow' ? 'bg-warning-bg border-warning-border text-warning' :
                  'bg-positive-bg border-positive-border text-positive'}`}>
                <stage.icon className="w-3 h-3" />
                <span className="font-bold">{stage.label}</span>
              </div>
            </div>
            
            {/* Next Catalyst (Highlighted) */}
            <div className="flex-1">
              <div className="text-[10px] text-text-muted mb-1.5 flex items-center gap-1">
                <CalendarClock className="w-3 h-3 opacity-70" />
                NEXT CATALYST
              </div>
              {position.next_catalyst ? (
                <div className="bg-surface-hover border border-border rounded-lg p-2 h-full flex items-center">
                  <div className="flex items-start gap-2">
                    <Calendar className="w-3 h-3 text-text-secondary mt-0.5 flex-shrink-0" />
                    <div className="text-xs text-text-primary leading-tight">{position.next_catalyst}</div>
                  </div>
                </div>
              ) : (
                <div className="bg-warning-bg border border-warning-border rounded-lg p-2 h-full flex items-center justify-center">
                  <div className="flex items-center gap-2">
                    <AlertTriangle className="w-4 h-4 text-warning" />
                    <span className="text-xs text-warning font-semibold">No catalyst - position questionable</span>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* RIGHT COLUMN: POSITION COMMAND (1/3 width) */}
          <div className="bg-surface-raised rounded-lg p-3 border border-border flex flex-col">
            <h3 className="text-[10px] font-bold text-text-secondary uppercase tracking-wider mb-2 flex items-center gap-1.5">
              <DollarSign className="w-3 h-3" /> POSITION COMMAND
            </h3>
            
            {/* Compact Risk Alert (if over-allocated) */}
            {isOverAllocated && (
              <div className="mb-2 p-2 bg-negative-bg border border-negative rounded flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 text-negative flex-shrink-0" />
                <div className="text-[10px] text-negative font-bold">RISK: OVER-ALLOCATED</div>
              </div>
            )}
            
            {/* Trend Warning (if bearish) */}
            {position.trend_status === 'BEARISH' && (
              <div className="mb-2 p-2 bg-negative-bg border border-negative rounded flex items-center gap-2">
                <TrendingDown className="w-4 h-4 text-negative flex-shrink-0" />
                <div className="text-[10px] text-negative font-bold">TREND BROKEN</div>
              </div>
            )}
            
            {/* Current vs Max Allocation */}
            <div className="mb-3">
              <div className="text-[10px] text-text-muted mb-1">ALLOCATION</div>
              <div className="flex items-baseline gap-1">
                <span className="text-2xl font-black text-text-primary">{position.weight_in_portfolio.toFixed(1)}%</span>
                <span className="text-xs text-text-secondary">/ {maxAllocationPct}%</span>
              </div>
              <div className="h-1.5 bg-surface-active rounded-full overflow-hidden mt-1.5">
                <div 
                  className={`h-full ${isOverAllocated ? 'bg-negative' : 'bg-positive'}`}
                  style={{ width: `${Math.min(100, (position.weight_in_portfolio / maxAllocationPct) * 100)}%` }}
                />
              </div>
            </div>
            
            {/* Action Button (TRIM or ACCUMULATE) */}
            <div className="flex-1 flex flex-col justify-center">
              {isOverAllocated ? (
                <button 
                  onClick={() => setShowTrimModal(true)}
                  className="w-full py-3 bg-negative hover:bg-negative-muted text-text-primary font-black text-sm rounded-lg border-2 border-negative transition-colors flex items-center justify-center gap-2"
                >
                  <Scissors className="w-4 h-4" />
                  TRIM POSITION
                </button>
              ) : position.optimal_size > 0 ? (
                <button className="w-full py-3 bg-positive hover:bg-positive-muted text-text-primary font-black text-sm rounded-lg border-2 border-positive transition-colors">
                  ACCUMULATE
                </button>
              ) : (
                <button className="w-full py-3 bg-surface-active text-text-secondary font-black text-sm rounded-lg border-2 border-border cursor-not-allowed flex items-center justify-center gap-2">
                  <ShieldCheck className="w-4 h-4" />
                  HOLD
                </button>
              )}
              
              {/* Gap Display */}
              <div className="mt-2 text-center">
                <div className="text-[10px] text-text-muted">OPTIMAL SIZE</div>
                <div className={`text-lg font-bold font-mono ${position.optimal_size < 0 ? 'text-negative' : 'text-text-primary'}`}>
                  {position.optimal_size < 0 ? '-' : '+'}{Math.abs(position.optimal_size).toLocaleString('cs-CZ')} Kč
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* ======================================================================
            LOGICAL ERROR WARNING: High Score but No Catalyst
            ====================================================================== */}
        {position.conviction_score && position.conviction_score >= 9 && (!position.next_catalyst || position.next_catalyst.toUpperCase().includes('NO CATALYST')) && (
          <div className="mx-3 mb-3 bg-warning-bg border-2 border-warning rounded-lg p-4 shadow-lg">
            <div className="flex items-start gap-3">
              <div className="flex-shrink-0 mt-1">
                <AlertTriangle className="w-6 h-6 text-warning animate-pulse" />
              </div>
              <div className="flex-1">
                <div className="text-base text-warning font-bold mb-2 flex items-center gap-2">
                  ⚠️ LOGICAL ERROR: High Score ({position.conviction_score}/10) but No Catalyst
                </div>
                <div className="text-sm text-text-secondary leading-relaxed space-y-1">
                  <p>
                    <strong className="text-warning">Problém:</strong> Score není obhajitelné bez konkrétního katalyzátoru. 
                    Bez katalyzátoru cena padá dolů (dead money).
                  </p>
                  <p className="mt-2">
                    <strong className="text-warning">Řešení:</strong> Klikni na <span className="px-2 py-0.5 bg-surface-hover rounded text-xs font-bold text-text-secondary">UPRAVIT</span> v headeru 
                    a doplň konkrétní catalyst (např. "Q1 2026 High-Grade Silver Sales Report").
                  </p>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ======================================================================
            ROW 3: THE TRADING DECK (Compact Table Layout)
            Height: ~40% of viewport
            ====================================================================== */}
        <div className="px-3 pb-3 pt-2 bg-surface-raised">
          <h3 className="text-xs font-bold text-warning uppercase tracking-wider mb-2 flex items-center gap-2">
            <Target className="w-4 h-4" /> THE TRADING DECK
          </h3>
          
          <div className="grid grid-cols-3 gap-2">
            {/* BLOCK 1: DOWNSIDE REALITY - Table Format */}
            <div className="bg-surface-overlay rounded-lg border border-negative-border overflow-hidden">
              <div className="bg-negative-bg px-2 py-1.5 border-b border-negative-border flex items-center justify-between">
                <div className="flex items-center gap-1.5">
                  <ArrowDownCircle className="w-3 h-3 text-negative" />
                  <span className="text-[10px] font-bold text-negative uppercase">DOWNSIDE</span>
                </div>
                <div className="group relative">
                  <Info className="w-3 h-3 text-text-muted cursor-help" />
                  <div className="absolute right-0 top-full mt-1 w-48 p-2 bg-surface-base border border-border rounded text-[9px] text-text-secondary hidden group-hover:block z-10">
                    Hodnocení rizika: Likvidační hodnota vs technická podpora
                  </div>
                </div>
              </div>
              <div className="p-2 space-y-1">
                <div className="grid grid-cols-2 text-xs">
                  <span className="text-text-muted">Liquidation Floor</span>
                  <span className="text-negative font-mono font-bold text-right">${priceFloor.toFixed(2)}</span>
                </div>
                {position.stock?.green_line && (
                  <div className="grid grid-cols-2 text-xs">
                    <span className="text-text-muted">Tech. Support</span>
                    <span className="text-positive font-mono font-bold text-right">${position.stock.green_line.toFixed(2)}</span>
                  </div>
                )}
                {position.stock?.max_buy_price && (
                  <div className="grid grid-cols-2 text-xs">
                    <span className="text-text-muted">Buy Limit</span>
                    <span className="text-positive font-mono text-right">${position.stock.max_buy_price.toFixed(2)}</span>
                  </div>
                )}
                <div className="grid grid-cols-2 text-xs pt-1 border-t border-border">
                  <span className="text-text-muted font-bold">Risk to Floor</span>
                  <span className="text-negative font-bold text-right">
                    {position.stock?.risk_to_floor_pct 
                      ? `${position.stock.risk_to_floor_pct.toFixed(0)}%`
                      : `${((priceFloor / currentPrice - 1) * 100).toFixed(0)}%`}
                  </span>
                </div>
              </div>
            </div>

            {/* BLOCK 2: CURRENT PRICE - Compact */}
            <div className="bg-surface-overlay rounded-lg border border-border overflow-hidden">
              <div className="bg-surface-hover px-2 py-1.5 border-b border-border flex items-center justify-between">
                <div className="flex items-center gap-1.5">
                  <Scale className="w-3 h-3 text-text-secondary" />
                  <span className="text-[10px] font-bold text-text-secondary uppercase">CURRENT</span>
                </div>
              </div>
              <div className="p-2">
                <div className="text-center mb-2">
                  <div className="text-3xl font-black font-mono text-text-secondary">${currentPrice.toFixed(2)}</div>
                </div>
                
                {/* Compact Slider */}
                <div className="mb-2">
                  <div className="relative h-3 bg-surface-active rounded-full mb-1">
                    <div className="absolute inset-0 bg-gradient-to-r from-negative via-warning to-positive rounded-full opacity-40" />
                    <div 
                      className="absolute top-1/2 -translate-y-1/2 w-4 h-4 bg-white border border-border rounded-full shadow-lg"
                      style={{ left: `${pricePosition}%`, transform: 'translate(-50%, -50%)' }}
                    />
                  </div>
                  <div className="grid grid-cols-3 text-[8px]">
                    <span className="text-negative font-bold">Floor</span>
                    <span className="text-warning font-bold text-center">Base</span>
                    <span className="text-positive font-bold text-right">Moon</span>
                  </div>
                </div>
                
                {/* Signal Badge */}
                {position.stock?.trading_zone_signal && (
                  <div className="text-center">
                    <div className={`inline-flex items-center gap-1 px-2 py-1 rounded text-xs font-bold border
                      ${isOverAllocated ? 'bg-negative-bg text-negative border-negative' :
                        position.stock.trading_zone_signal.includes('BUY') ? 'bg-positive-bg text-positive border-positive' :
                        position.stock.trading_zone_signal.includes('SELL') ? 'bg-negative-bg text-negative border-negative' :
                        'bg-surface-hover text-text-secondary border-border'}`}>
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
            <div className="bg-surface-overlay rounded-lg border border-positive-border overflow-hidden">
              <div className="bg-positive-bg px-2 py-1.5 border-b border-positive-border flex items-center justify-between">
                <div className="flex items-center gap-1.5">
                  <ArrowUpCircle className="w-3 h-3 text-positive" />
                  <span className="text-[10px] font-bold text-positive uppercase">UPSIDE</span>
                </div>
                <div className="group relative">
                  <Info className="w-3 h-3 text-text-muted cursor-help" />
                  <div className="absolute right-0 top-full mt-1 w-48 p-2 bg-surface-base border border-border rounded text-[9px] text-text-secondary hidden group-hover:block z-10">
                    Potenciál růstu: Technický odpor vs fundamentální cíl
                  </div>
                </div>
              </div>
              <div className="p-2 space-y-1">
                {position.stock?.red_line && (
                  <div className="grid grid-cols-2 text-xs">
                    <span className="text-text-muted">Tech. Resistance</span>
                    <span className="text-negative font-mono font-bold text-right">${position.stock.red_line.toFixed(2)}</span>
                  </div>
                )}
                {position.stock?.start_sell_price && (
                  <div className="grid grid-cols-2 text-xs">
                    <span className="text-text-muted">Sell Alert</span>
                    <span className="text-negative font-mono text-right">${position.stock.start_sell_price.toFixed(2)}</span>
                  </div>
                )}
                <div className="grid grid-cols-2 text-xs">
                  <span className="text-text-muted">Moon Target</span>
                  <span className="text-positive font-mono font-bold text-right">${priceMoon.toFixed(2)}</span>
                </div>
                <div className="grid grid-cols-2 text-xs pt-1 border-t border-border">
                  <span className="text-text-muted font-bold">R/R Ratio</span>
                  <span className={`font-bold text-right ${
                    ((position.stock?.upside_to_ceiling_pct || 0) / Math.abs(position.stock?.risk_to_floor_pct || 1)) >= 3 ? 'text-positive' :
                    ((position.stock?.upside_to_ceiling_pct || 0) / Math.abs(position.stock?.risk_to_floor_pct || 1)) >= 2 ? 'text-warning' :
                    'text-negative'
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
            FOOTER: Historical P/L (De-emphasized) + Legend Icon
            ====================================================================== */}
        <div className="px-3 pb-2 mt-auto relative">
          <div className="bg-surface-hover rounded px-3 py-1.5 border border-border flex items-center justify-between">
            <span className="text-[10px] text-text-muted">Historical P/L (reference only)</span>
            <div className="flex items-center gap-3 text-xs">
              <span className={`font-mono ${position.unrealized_pl >= 0 ? 'text-positive' : 'text-negative'}`}>
                {position.unrealized_pl >= 0 ? '+' : ''}{position.unrealized_pl.toFixed(2)} {position.currency || 'USD'}
              </span>
              <span className={`font-bold ${position.unrealized_pl_percent >= 0 ? 'text-positive' : 'text-negative'}`}>
                ({position.unrealized_pl_percent >= 0 ? '+' : ''}{position.unrealized_pl_percent.toFixed(1)}%)
              </span>
            </div>
          </div>
          
          {/* Legend Icon - Bottom Right */}
          <button
            onClick={() => setShowLegend(true)}
            className="absolute bottom-4 right-5 w-7 h-7 bg-surface-overlay border border-border-strong rounded-full flex items-center justify-center hover:bg-surface-active hover:border-accent transition-all shadow-lg"
            title="Vysvětlivky pojmů"
          >
            <HelpCircle className="w-4 h-4 text-text-muted" />
          </button>
        </div>
        
        {/* Legend Popup Modal */}
        {showLegend && (
          <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-[70] flex items-center justify-center p-4" onClick={() => setShowLegend(false)}>
            <div className="bg-surface-base border border-border-strong rounded-xl w-full max-w-lg shadow-2xl" onClick={(e) => e.stopPropagation()}>
              {/* Header */}
              <div className="px-5 py-4 border-b border-border flex items-center justify-between">
                <h3 className="text-base font-bold text-text-primary flex items-center gap-2">
                  <HelpCircle className="w-5 h-5 text-accent" />
                  Vysvětlivky Trading Decku
                </h3>
                <button 
                  onClick={() => setShowLegend(false)}
                  className="p-1.5 hover:bg-surface-hover rounded transition-colors"
                >
                  <X className="w-5 h-5 text-text-muted" />
                </button>
              </div>
              
              {/* Body */}
              <div className="p-5 grid grid-cols-1 md:grid-cols-3 gap-6">
                {/* Downside Column */}
                <div className="space-y-3">
                  <h4 className="text-sm font-semibold text-negative border-b border-negative-border pb-1">⬇️ Downside</h4>
                  <div className="space-y-2 text-xs text-text-secondary">
                    <div><span className="font-medium text-text-primary">Liquidation Floor:</span> Minimální hodnota aktiv při nejhorším scénáři</div>
                    <div><span className="font-medium text-text-primary">Tech. Support:</span> Technická úroveň podpory z grafu</div>
                    <div><span className="font-medium text-text-primary">Buy Limit:</span> Maximální rozumná nákupní cena</div>
                    <div><span className="font-medium text-text-primary">Risk to Floor:</span> Potenciální ztráta k nejnižší ceně</div>
                  </div>
                </div>
                
                {/* Current Column */}
                <div className="space-y-3">
                  <h4 className="text-sm font-semibold text-text-primary border-b border-border pb-1">📍 Aktuální pozice</h4>
                  <div className="space-y-2 text-xs text-text-secondary">
                    <div><span className="font-medium text-text-primary">Slider:</span> Vizuální pozice ceny mezi Floor → Base → Moon</div>
                    <div><span className="font-medium text-text-primary">BUY Zone:</span> Cena je blízko dna – výhodná k nákupu</div>
                    <div><span className="font-medium text-text-primary">SELL Zone:</span> Cena je vysoko – zvážit prodej</div>
                  </div>
                </div>
                
                {/* Upside Column */}
                <div className="space-y-3">
                  <h4 className="text-sm font-semibold text-positive border-b border-positive-border pb-1">⬆️ Upside</h4>
                  <div className="space-y-2 text-xs text-text-secondary">
                    <div><span className="font-medium text-text-primary">Tech. Resistance:</span> Technická úroveň odporu z grafu</div>
                    <div><span className="font-medium text-text-primary">Moon Target:</span> Fundamentální cílová cena</div>
                    <div><span className="font-medium text-text-primary">R/R Ratio:</span> Risk/Reward poměr (3:1+ je dobré)</div>
                  </div>
                </div>
              </div>
              
              {/* Footer */}
              <div className="px-5 py-3 border-t border-border bg-surface-hover rounded-b-xl">
                <p className="text-[10px] text-text-muted text-center">
                  Klikněte kamkoliv mimo okno nebo na × pro zavření
                </p>
              </div>
            </div>
          </div>
        )}

      </div>
      
      {/* ======================================================================
          TRIM MODAL: Log Transaction
          ====================================================================== */}
      {showTrimModal && (
        <div className="fixed inset-0 bg-black/90 backdrop-blur-sm z-[60] flex items-center justify-center p-4">
          <div className="bg-surface-base border-2 border-negative rounded-xl w-full max-w-md">
            {/* Header */}
            <div className="bg-negative-bg border-b border-negative-border p-4 flex items-center justify-between">
              <div>
                <h3 className="text-lg font-black text-text-primary flex items-center gap-2">
                  <Scissors className="w-5 h-5 text-negative" />
                  Exekuce strategie: Ořezání pozice
                </h3>
                <p className="text-xs text-text-muted mt-1">{position.ticker}</p>
              </div>
              <button 
                onClick={() => setShowTrimModal(false)}
                className="p-1.5 hover:bg-surface-hover rounded transition-colors"
              >
                <X className="w-5 h-5 text-text-muted" />
              </button>
            </div>

            {/* Body */}
            <div className="p-6 space-y-6">
              {/* Doporučení */}
              <div className="bg-negative-bg border border-negative-border rounded-lg p-4">
                <div className="flex items-start gap-3">
                  <AlertTriangle className="w-5 h-5 text-negative flex-shrink-0 mt-0.5" />
                  <div>
                    <div className="text-sm font-bold text-negative mb-1">Doporučení aplikace</div>
                    <div className="text-sm text-text-primary">
                      Abyste se dostali na limit <span className="font-bold text-negative">{maxAllocationPct}%</span>, 
                      prodejte akcie v hodnotě <span className="font-bold text-negative">{Math.abs(position.optimal_size).toLocaleString('cs-CZ')} Kč</span>.
                    </div>
                  </div>
                </div>
              </div>

              {/* Info: Current Holdings */}
              <div className="bg-surface-hover rounded-lg p-3 text-xs">
                <div className="flex justify-between mb-1">
                  <span className="text-text-muted">Aktuální počet kusů:</span>
                  <span className="text-text-primary font-bold">{position.shares_count}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-text-muted">Průměrná cena:</span>
                  <span className="text-text-primary font-bold">${position.avg_cost.toFixed(2)}</span>
                </div>
              </div>

              {/* Form */}
              <div className="space-y-4">
                <div>
                  <label className="block text-xs text-text-muted mb-2">Počet prodaných kusů</label>
                  <input
                    type="number"
                    value={trimShares}
                    onChange={(e) => setTrimShares(e.target.value)}
                    placeholder="Zadejte počet kusů"
                    className="w-full px-4 py-3 bg-surface-overlay border border-border rounded-lg text-text-primary placeholder-text-muted focus:border-negative focus:outline-none focus:ring-2 focus:ring-negative/20"
                    min="1"
                    max={position.shares_count}
                  />
                </div>

                <div>
                  <label className="block text-xs text-text-muted mb-2">Prodejní cena (za kus)</label>
                  <input
                    type="number"
                    value={trimPrice}
                    onChange={(e) => setTrimPrice(e.target.value)}
                    placeholder="Zadejte prodejní cenu"
                    step="0.01"
                    className="w-full px-4 py-3 bg-surface-overlay border border-border rounded-lg text-text-primary placeholder-text-muted focus:border-negative focus:outline-none focus:ring-2 focus:ring-negative/20"
                  />
                </div>

                {/* Preview Calculation */}
                {trimShares && trimPrice && (
                  <div className="bg-surface-hover border border-border rounded-lg p-3 text-xs space-y-1">
                    <div className="flex justify-between">
                      <span className="text-text-muted">Hodnota transakce:</span>
                      <span className="text-text-primary font-bold">
                        ${(parseFloat(trimShares) * parseFloat(trimPrice)).toFixed(2)}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-text-muted">Zbývající kusy:</span>
                      <span className="text-text-primary font-bold">
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
                  className="flex-1 py-3 bg-surface-hover hover:bg-surface-active text-text-primary font-bold rounded-lg transition-colors"
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
                  className="flex-1 py-3 bg-negative hover:bg-negative-muted text-text-primary font-black rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
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
          <div className="bg-surface-base border border-border rounded-xl w-full max-w-2xl">
            {/* Header */}
            <div className="bg-surface-hover border-b border-border p-4 flex items-center justify-between">
              <div>
                <h3 className="text-lg font-black text-text-primary flex items-center gap-2">
                  <FileText className="w-5 h-5 text-text-secondary" />
                  Přidat analýzu z transkriptů
                </h3>
                <p className="text-xs text-text-muted mt-1">{position.ticker} - {stock?.company_name}</p>
              </div>
              <button 
                onClick={() => setShowTranscriptModal(false)}
                className="p-1.5 hover:bg-surface-hover rounded transition-colors"
              >
                <X className="w-5 h-5 text-text-muted" />
              </button>
            </div>

            {/* Body */}
            <div className="p-6 space-y-6">
              {/* Info Box */}
              <div className="bg-surface-hover border border-border rounded-lg p-4">
                <div className="flex items-start gap-3">
                  <Info className="w-5 h-5 text-text-secondary flex-shrink-0 mt-0.5" />
                  <div className="text-sm text-text-primary">
                    <div className="font-bold mb-2">Investment Intelligence Engine</div>
                    <div className="text-xs space-y-1 text-text-secondary">
                      <div>• AI <strong>auto-detektuje typ zdroje</strong> (Official Filing, Chat, Analyst Report)</div>
                      <div>• <strong>Různá logika pro každý typ</strong>: 100% spolehlivost (filings) vs 30% (chat)</div>
                      <div>• Chat: Extrahuje sentiment, rumory, key voices (key analysts)</div>
                      <div>• Official: Tvrdá čísla, penalty za chybějící cash</div>
                    </div>
                  </div>
                </div>
              </div>

              {/* Source Type Selector */}
              <div className="bg-surface-hover border border-border rounded-lg p-4">
                <div className="flex items-center gap-2 mb-3">
                  <FileText className="w-4 h-4 text-text-muted" />
                  <span className="text-sm font-bold text-text-primary">Typ zdroje</span>
                  <span className="text-xs text-text-muted ml-auto">AI detekuje automaticky</span>
                </div>
                <select
                  value={sourceType}
                  onChange={(e) => setSourceType(e.target.value as 'youtube' | 'transcript' | 'manual')}
                  className="w-full px-4 py-3 bg-surface-overlay border border-border rounded-lg text-text-primary focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/20"
                >
                  <option value="youtube">📹 YouTube URL (Auto-transcript)</option>
                  <option value="transcript">📄 Transkript / Text (Official/Chat/Article)</option>
                  <option value="manual">✍️ Manuální poznámky</option>
                </select>
              </div>

              {/* Input Field */}
              <div>
                <label className="block text-xs text-text-muted mb-2">
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
                    className="w-full px-4 py-3 bg-surface-overlay border border-border rounded-lg text-text-primary placeholder-text-muted focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/20 font-mono text-sm"
                  ></textarea>
                  <div className="mt-2 text-xs text-text-muted">
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
                  <label className="block text-xs text-text-muted mb-2">Investor / Zdroj</label>
                  <input
                    type="text"
                    placeholder="Investment Committee"
                    value={investorName}
                    onChange={(e) => setInvestorName(e.target.value)}
                    className="w-full px-4 py-2 bg-surface-overlay border border-border rounded-lg text-text-primary placeholder-text-muted focus:border-accent focus:outline-none"
                  />
                </div>
                <div>
                  <label className="block text-xs text-text-muted mb-2">Datum videa/analýzy</label>
                  <input
                    type="date"
                    value={analysisDate}
                    onChange={(e) => setAnalysisDate(e.target.value)}
                    className="w-full px-4 py-2 bg-surface-overlay border border-border rounded-lg text-text-primary focus:border-accent focus:outline-none"
                  />
                </div>
              </div>

              {/* Actions */}
              <div className="flex gap-3">
                <button
                  onClick={() => setShowTranscriptModal(false)}
                  className="flex-1 py-3 bg-surface-hover hover:bg-surface-active text-text-primary font-bold rounded-lg transition-colors"
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
                      
                      alertMsg += `\nConviction Score: ${result.conviction_score}/10`;
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
                  className="flex-1 py-3 bg-surface-active hover:bg-surface-hover disabled:bg-surface-hover disabled:cursor-not-allowed text-text-primary font-black rounded-lg transition-colors flex items-center justify-center gap-2"
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
              <div className="text-xs text-text-muted text-center">
                AI extrahuje: thesis, catalyst, stage, insider activity, risk faktory
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ======================================================================
          EDIT MODAL: Manual Stock Data Edit
          ====================================================================== */}
      {showEditModal && (
        <div className="fixed inset-0 bg-black/90 backdrop-blur-sm z-[60] flex items-center justify-center p-4">
          <div className="bg-surface-base border border-border rounded-xl w-full max-w-3xl max-h-[90vh] flex flex-col">
            {/* Header */}
            <div className="bg-surface-hover border-b border-border p-4 flex items-center justify-between flex-shrink-0">
              <div>
                <h3 className="text-lg font-black text-text-primary flex items-center gap-2">
                  <FileText className="w-5 h-5 text-text-secondary" />
                  Ruční úprava údajů – {position.ticker}
                </h3>
                <p className="text-xs text-text-muted mt-1">Uprav klíčové hodnoty pro stock analysis</p>
              </div>
              <button 
                onClick={handleCancelEdit}
                className="p-1.5 hover:bg-surface-hover rounded transition-colors"
              >
                <X className="w-5 h-5 text-text-muted" />
              </button>
            </div>

            {/* Body - Scrollable */}
            <div className="p-6 space-y-4 overflow-y-auto flex-1">
              <div className="grid grid-cols-2 gap-4">
                {/* Conviction Score */}
                <div>
                  <label className="block text-sm text-text-secondary mb-2 font-semibold">Conviction Score (1-10)</label>
                  <input
                    type="number"
                    min="1"
                    max="10"
                    value={editedData.conviction_score}
                    onChange={(e) => setEditedData({...editedData, conviction_score: parseInt(e.target.value) || 5})}
                    className="w-full px-4 py-3 bg-surface-overlay border border-border rounded-lg text-text-primary focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/20"
                  />
                </div>

                {/* Inflection Status */}
                <div>
                  <label className="block text-sm text-text-secondary mb-2 font-semibold">Inflection Stage</label>
                  <select
                    value={editedData.inflection_status}
                    onChange={(e) => setEditedData({...editedData, inflection_status: e.target.value as 'WAIT_TIME' | 'UPCOMING' | 'ACTIVE_GOLD_MINE'})}
                    className="w-full px-4 py-3 bg-surface-overlay border border-border rounded-lg text-text-primary focus:border-accent focus:outline-none"
                  >
                    <option value="WAIT_TIME">🔴 The Wait Time</option>
                    <option value="UPCOMING">🟡 Inflection Upcoming</option>
                    <option value="ACTIVE_GOLD_MINE">🟢 The Gold Mine</option>
                  </select>
                </div>

                {/* Max Allocation Cap */}
                <div>
                  <label className="block text-sm text-text-secondary mb-2 font-semibold">Max Allocation Cap (%)</label>
                  <input
                    type="number"
                    step="0.5"
                    value={editedData.max_allocation_cap}
                    onChange={(e) => setEditedData({...editedData, max_allocation_cap: parseFloat(e.target.value) || 10})}
                    className="w-full px-4 py-3 bg-surface-overlay border border-border rounded-lg text-text-primary focus:border-accent focus:outline-none"
                  />
                </div>

                {/* Cash Runway Months */}
                <div>
                  <label className="block text-sm text-text-secondary mb-2 font-semibold">Cash Runway (měsíce)</label>
                  <input
                    type="number"
                    value={editedData.cash_runway_months ?? ''}
                    onChange={(e) => setEditedData({...editedData, cash_runway_months: e.target.value ? parseInt(e.target.value) : null})}
                    placeholder="prázdné = neznámé"
                    className="w-full px-4 py-3 bg-surface-overlay border border-border rounded-lg text-text-primary placeholder-text-muted focus:border-accent focus:outline-none"
                  />
                </div>

                {/* Price Floor */}
                <div>
                  <label className="block text-sm text-text-secondary mb-2 font-semibold">Price Floor (Liquidation)</label>
                  <input
                    type="number"
                    step="0.01"
                    value={editedData.price_floor}
                    onChange={(e) => setEditedData({...editedData, price_floor: parseFloat(e.target.value) || 0})}
                    className="w-full px-4 py-3 bg-surface-overlay border border-border rounded-lg text-text-primary focus:border-accent focus:outline-none"
                  />
                </div>

                {/* Price Base */}
                <div>
                  <label className="block text-sm text-text-secondary mb-2 font-semibold">Price Base (Fair Value)</label>
                  <input
                    type="number"
                    step="0.01"
                    value={editedData.price_base}
                    onChange={(e) => setEditedData({...editedData, price_base: parseFloat(e.target.value) || 0})}
                    className="w-full px-4 py-3 bg-surface-overlay border border-border rounded-lg text-text-primary focus:border-accent focus:outline-none"
                  />
                </div>

                {/* Price Moon */}
                <div>
                  <label className="block text-sm text-text-secondary mb-2 font-semibold">Price Moon (Bull Case)</label>
                  <input
                    type="number"
                    step="0.01"
                    value={editedData.price_moon}
                    onChange={(e) => setEditedData({...editedData, price_moon: parseFloat(e.target.value) || 0})}
                    className="w-full px-4 py-3 bg-surface-overlay border border-border rounded-lg text-text-primary focus:border-accent focus:outline-none"
                  />
                </div>

                {/* Stop Loss */}
                <div>
                  <label className="block text-sm text-text-secondary mb-2 font-semibold">Stop Loss (Kill Switch)</label>
                  <input
                    type="number"
                    step="0.01"
                    value={editedData.stop_loss_price}
                    onChange={(e) => setEditedData({...editedData, stop_loss_price: parseFloat(e.target.value) || 0})}
                    className="w-full px-4 py-3 bg-surface-overlay border border-border rounded-lg text-text-primary focus:border-accent focus:outline-none"
                  />
                </div>
              </div>

              {/* Next Catalyst */}
              <div>
                <label className="block text-sm text-text-secondary mb-2 font-semibold">Next Catalyst</label>
                <input
                  type="text"
                  value={editedData.next_catalyst}
                  onChange={(e) => setEditedData({...editedData, next_catalyst: e.target.value})}
                  placeholder="např. Q1 2026 High-Grade Silver Sales Report"
                  className="w-full px-4 py-3 bg-surface-overlay border border-border rounded-lg text-text-primary placeholder-text-muted focus:border-accent focus:outline-none"
                />
              </div>

              {/* Thesis Narrative */}
              <div>
                <label className="block text-sm text-text-secondary mb-2 font-semibold">Thesis (The Setup)</label>
                <textarea
                  value={editedData.thesis_narrative}
                  onChange={(e) => setEditedData({...editedData, thesis_narrative: e.target.value})}
                  rows={4}
                  placeholder="2-3 věty popisující investiční tezi..."
                  className="w-full px-4 py-3 bg-surface-overlay border border-border rounded-lg text-text-primary placeholder-text-muted focus:border-accent focus:outline-none resize-none"
                />
              </div>
            </div>

            {/* Footer - Actions */}
            <div className="border-t border-border p-4 flex gap-3 flex-shrink-0">
              <button
                onClick={handleCancelEdit}
                className="flex-1 py-3 bg-surface-hover hover:bg-surface-active text-text-primary font-bold rounded-lg transition-colors"
              >
                Zrušit
              </button>
              <button
                onClick={handleSaveEdit}
                disabled={isSaving}
                className="flex-1 py-3 bg-surface-active hover:bg-surface-hover disabled:bg-surface-hover disabled:cursor-not-allowed text-text-primary font-black rounded-lg transition-colors flex items-center justify-center gap-2"
              >
                {isSaving ? (
                  <>
                    <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin"></div>
                    Ukládám...
                  </>
                ) : (
                  <>
                    <ShieldCheck className="w-4 h-4" />
                    ULOŽIT ZMĚNY
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
      </GatekeeperShield>
    </div>
  );
};

export default AssetDetailModal;


