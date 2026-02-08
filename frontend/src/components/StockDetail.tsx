/**
 * StockDetail Component - "Decision Cockpit" Design
 * 
 * Transformed from "Information Panel" to "Decision Cockpit"
 * following the Gomes methodology: "Verdict First, Data Second"
 * 
 * Visual Hierarchy:
 * 1. GomesHeader - Verdict at a glance (Score, Action, Price)
 * 2. SafetyGaugeRow - Pre-flight safety checks
 * 3. ThesisCard - WHY we hold this (fundament before price)
 * 4. TradingDeck - Execution panel (locked unless safe)
 * 5. Details Tabs - Additional data (charts, metadata)
 * 
 * @fiduciary This component prioritizes capital protection over information density.
 */

import React, { useState } from 'react';
import type { Stock } from '../types';
import { 
  GomesHeader, 
  SafetyGaugeRow, 
  ThesisCard, 
  TradingDeck 
} from './stock-detail';
import {
  BarChart3,
  FileText,
  Clock,
  Info,
  Briefcase
} from 'lucide-react';

// Extended position type - loosely typed to accept various position formats
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
  conviction_score?: number | null;
  target_weight_pct?: number;
  weight_in_portfolio?: number;
  gap_czk?: number;
  optimal_size?: number;
  action_signal?: 'BUY' | 'HOLD' | 'SELL' | 'SNIPER';
  next_catalyst?: string;
  max_allocation_cap?: number;
  trend_status?: 'BULLISH' | 'BEARISH' | 'NEUTRAL';
  is_deteriorated?: boolean;
  [key: string]: unknown; // Allow additional properties
}

interface StockDetailProps {
  // Either stock OR position must be provided
  stock?: Stock;
  position?: EnrichedPosition;
  onClose: () => void;
  onUpdate?: () => void;
  marketAlert?: 'RED' | 'YELLOW' | 'GREEN';
}

type TabId = 'overview' | 'trading' | 'analysis' | 'metadata' | 'position';

interface Tab {
  id: TabId;
  label: string;
  icon: React.ReactNode;
}

export const StockDetail: React.FC<StockDetailProps> = ({ 
  stock: stockProp, 
  position,
  onClose,
  onUpdate: _onUpdate, // Reserved for future use
  marketAlert = 'GREEN' 
}) => {
  // Derive stock from either prop or position
  const stock = stockProp ?? position?.stock;
  const hasPosition = !!position;
  
  // Silence unused variable warning
  void _onUpdate;
  
  // Build tabs dynamically based on whether we have position data
  const tabs: Tab[] = [
    { id: 'overview', label: 'Přehled', icon: <Info className="w-4 h-4" /> },
    ...(hasPosition ? [{ id: 'position' as TabId, label: 'Pozice', icon: <Briefcase className="w-4 h-4" /> }] : []),
    { id: 'trading', label: 'Trading', icon: <BarChart3 className="w-4 h-4" /> },
    { id: 'analysis', label: 'Analýza', icon: <FileText className="w-4 h-4" /> },
    { id: 'metadata', label: 'Metadata', icon: <Clock className="w-4 h-4" /> },
  ];
  
  const [activeTab, setActiveTab] = useState<TabId>('overview');

  // If no stock data available, show error state
  if (!stock) {
    return (
      <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
        <div className="bg-primary-surface border border-border rounded-lg p-8 text-center">
          <p className="text-negative mb-4">Chybí data akcie</p>
          <button onClick={onClose} className="btn btn-secondary">Zavřít</button>
        </div>
      </div>
    );
  }

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleString('cs-CZ', {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };
  
  const formatCurrency = (value: number, currency = 'CZK') => {
    return new Intl.NumberFormat('cs-CZ', { 
      style: 'currency', 
      currency,
      maximumFractionDigits: 0 
    }).format(value);
  };

  const handleBuyClick = () => {
    console.log(`Buy clicked for ${stock.ticker}`);
  };

  const handleSellClick = () => {
    console.log(`Sell clicked for ${stock.ticker}`);
  };

  // Use position's current_price if available, otherwise stock's
  const currentPrice = position?.current_price ?? stock.current_price;

  return (
    <div className="fixed inset-0 bg-black/90 flex items-center justify-center z-50 p-4">
      <div className="bg-[#0d1117] border border-slate-700 rounded-xl max-w-4xl w-full max-h-[90vh] overflow-hidden flex flex-col shadow-2xl">
        
        {/* ============================================ */}
        {/* LAYER 1: THE VERDICT HEADER                 */}
        {/* Shows Score, Action, Price at a glance      */}
        {/* ============================================ */}
        <GomesHeader
          ticker={stock.ticker}
          companyName={stock.company_name}
          currentPrice={currentPrice}
          gomesScore={stock.conviction_score}
          actionVerdict={stock.action_verdict}
          onClose={onClose}
        />
        
        {/* ============================================ */}
        {/* LAYER 2: TABS - Navigation at top           */}
        {/* ============================================ */}
        <div className="bg-[#161b22] border-b border-slate-700">
          <div className="flex">
            {tabs.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`
                  flex items-center gap-2 px-5 py-3 text-sm font-medium
                  transition-all border-b-2 -mb-px
                  ${activeTab === tab.id 
                    ? 'text-emerald-400 border-emerald-400 bg-emerald-400/10' 
                    : 'text-slate-400 border-transparent hover:text-slate-200 hover:bg-slate-800/50'}
                `}
              >
                {tab.icon}
                <span>{tab.label}</span>
              </button>
            ))}
          </div>
        </div>
        
        {/* Scrollable Content */}
        <div className="flex-1 overflow-y-auto custom-scrollbar bg-[#0d1117]">
          <div className="p-5 space-y-5">
            
            {/* ============================================ */}
            {/* LAYER 3: SAFETY GAUGE ROW                   */}
            {/* Pre-flight checks before any trading        */}
            {/* ============================================ */}
            <SafetyGaugeRow
              cashRunwayMonths={stock.cash_runway_months ?? null}
              inflectionStatus={stock.inflection_status ?? null}
              priceZone={stock.price_zone}
              marketAlert={marketAlert}
            />
            
            {/* ============================================ */}
            {/* TAB CONTENT                                 */}
            {/* ============================================ */}
            
            {/* Overview Tab */}
            {activeTab === 'overview' && (
              <div className="space-y-5">
                {/* Thesis Card */}
                <ThesisCard
                  thesisNarrative={stock.thesis_narrative ?? null}
                  edge={stock.edge}
                  catalysts={stock.catalysts}
                  nextCatalyst={stock.next_catalyst ?? null}
                  risks={stock.risks}
                  primaryCatalyst={stock.primary_catalyst ?? null}
                  catalystDate={stock.catalyst_date ?? null}
                />
                
                {/* Price Targets */}
                {(stock.price_target || stock.price_target_short || stock.price_target_long) && (
                  <div className="bg-[#161b22] rounded-lg p-4 border border-slate-700">
                    <h4 className="text-sm font-semibold text-emerald-400 mb-3">Cenové cíle</h4>
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                      {stock.price_target && (
                        <div className="bg-[#0d1117] rounded-lg p-3 border border-slate-600">
                          <p className="text-xs text-slate-500 mb-1">Obecný cíl</p>
                          <p className="text-lg font-bold text-emerald-400">{stock.price_target}</p>
                          {stock.time_horizon && (
                            <p className="text-xs text-slate-400 mt-1">{stock.time_horizon}</p>
                          )}
                        </div>
                      )}
                      {stock.price_target_short && (
                        <div className="bg-[#0d1117] rounded-lg p-3 border border-green-800">
                          <p className="text-xs text-slate-500 mb-1">Krátkodobý</p>
                          <p className="text-lg font-bold text-green-400">{stock.price_target_short}</p>
                        </div>
                      )}
                      {stock.price_target_long && (
                        <div className="bg-[#0d1117] rounded-lg p-3 border border-blue-800">
                          <p className="text-xs text-slate-500 mb-1">Dlouhodobý</p>
                          <p className="text-lg font-bold text-blue-400">{stock.price_target_long}</p>
                        </div>
                      )}
                    </div>
                  </div>
                )}
                
                {/* Key Metrics */}
                <div className="bg-[#161b22] rounded-lg p-4 border border-slate-700">
                  <h4 className="text-sm font-semibold text-emerald-400 mb-3">Klíčové metriky</h4>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                    <MetricCard 
                      label="Moat Rating" 
                      value={stock.moat_rating ? `${stock.moat_rating}/5` : null}
                    />
                    <MetricCard 
                      label="Max Alokace" 
                      value={stock.max_allocation_cap ? `${stock.max_allocation_cap}%` : null}
                    />
                    <MetricCard 
                      label="Insider Activity" 
                      value={stock.insider_activity}
                    />
                    <MetricCard 
                      label="Valuation Stage" 
                      value={stock.current_valuation_stage?.replace('_', ' ')}
                    />
                  </div>
                </div>
              </div>
            )}
            
            {/* Trading Tab */}
            {activeTab === 'trading' && (
              <div className="space-y-5">
                {/* Trading Deck */}
                <TradingDeck
                  ticker={stock.ticker}
                  currentPrice={currentPrice}
                  marketAlert={marketAlert}
                  cashRunwayMonths={stock.cash_runway_months ?? null}
                  inflectionStatus={stock.inflection_status ?? null}
                  priceZone={stock.price_zone}
                  greenLine={stock.green_line}
                  redLine={stock.red_line}
                  maxBuyPrice={stock.max_buy_price ?? null}
                  stopLossPrice={stock.stop_loss_price ?? null}
                  actionVerdict={stock.action_verdict}
                  onBuyClick={handleBuyClick}
                  onSellClick={handleSellClick}
                />
                
                {/* Entry/Exit Zones */}
                <div className="grid grid-cols-2 gap-4">
                  {stock.entry_zone && (
                    <div className="bg-green-900/30 border border-green-700 rounded-lg p-4">
                      <p className="text-xs text-green-400 font-medium mb-1">Vstupní zóna</p>
                      <p className="text-lg font-bold text-green-400">{stock.entry_zone}</p>
                    </div>
                  )}
                  {stock.stop_loss_risk && (
                    <div className="bg-red-900/30 border border-red-700 rounded-lg p-4">
                      <p className="text-xs text-red-400 font-medium mb-1">Stop Loss / Riziko</p>
                      <p className="text-sm font-medium text-red-400">{stock.stop_loss_risk}</p>
                    </div>
                  )}
                </div>
                
                {/* Trade Rationale */}
                {stock.trade_rationale && (
                  <div className="bg-[#161b22] rounded-lg p-4 border border-slate-700">
                    <h4 className="text-sm font-semibold text-emerald-400 mb-2">Trade Rationale</h4>
                    <p className="text-sm text-slate-300">{stock.trade_rationale}</p>
                  </div>
                )}
                
                {/* Chart Setup */}
                {stock.chart_setup && (
                  <div className="bg-[#161b22] rounded-lg p-4 border border-slate-700">
                    <h4 className="text-sm font-semibold text-emerald-400 mb-2">Chart Setup</h4>
                    <p className="text-sm text-slate-300">{stock.chart_setup}</p>
                  </div>
                )}
                
                {/* Risk/Reward Metrics */}
                {(stock.risk_to_floor_pct != null || stock.upside_to_ceiling_pct != null) && (
                  <div className="grid grid-cols-2 gap-4">
                    {stock.risk_to_floor_pct != null && (
                      <MetricCard 
                        label="Risk to Floor" 
                        value={`${stock.risk_to_floor_pct!.toFixed(1)}%`}
                        variant="negative"
                      />
                    )}
                    {stock.upside_to_ceiling_pct != null && (
                      <MetricCard 
                        label="Upside to Ceiling" 
                        value={`${stock.upside_to_ceiling_pct!.toFixed(1)}%`}
                        variant="positive"
                      />
                    )}
                  </div>
                )}
              </div>
            )}
            
            {/* Analysis Tab */}
            {activeTab === 'analysis' && (
              <div className="space-y-4">
                {stock.raw_notes && (
                  <div className="bg-[#161b22] rounded-lg p-4 border border-slate-700">
                    <h4 className="text-sm font-semibold text-slate-400 mb-2">Plná analýza</h4>
                    <pre className="text-sm text-slate-300 whitespace-pre-wrap font-mono 
                                    bg-[#0d1117] p-4 rounded-lg max-h-96 overflow-y-auto custom-scrollbar">
                      {stock.raw_notes}
                    </pre>
                  </div>
                )}
                
                {!stock.raw_notes && (
                  <p className="text-slate-500 text-center py-8">
                    Žádná detailní analýza není k dispozici.
                  </p>
                )}
              </div>
            )}
            
            {/* Metadata Tab */}
            {activeTab === 'metadata' && (
              <div className="bg-[#161b22] rounded-lg p-4 border border-slate-700">
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <MetricCard label="ID" value={`#${stock.id}`} />
                  <MetricCard label="Řečník" value={stock.speaker} />
                  <MetricCard label="Zdroj" value={stock.source_type} />
                  <MetricCard label="Analyzováno" value={formatDate(stock.created_at)} />
                  <MetricCard label="Sentiment" value={stock.sentiment} />
                  <MetricCard label="Time Horizon" value={stock.time_horizon} />
                  <MetricCard label="Asset Class" value={stock.asset_class} />
                  <MetricCard 
                    label="Market Cap" 
                    value={stock.market_cap ? `$${(stock.market_cap / 1e6).toFixed(0)}M` : null} 
                  />
                </div>
              </div>
            )}
            
            {/* Position Tab - Only shows when position data is available */}
            {activeTab === 'position' && position && (
              <div className="space-y-5">
                {/* Position Summary */}
                <div className="bg-[#161b22] rounded-lg p-4 border border-slate-700">
                  <h4 className="text-sm font-semibold text-emerald-400 mb-3">Pozice</h4>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                    <MetricCard 
                      label="Počet akcií" 
                      value={position.shares_count}
                    />
                    <MetricCard 
                      label="Průměrná cena" 
                      value={formatCurrency(position.avg_cost, position.currency)}
                    />
                    <MetricCard 
                      label="Aktuální cena" 
                      value={currentPrice ? formatCurrency(currentPrice, position.currency) : null}
                    />
                    <MetricCard 
                      label="Hodnota pozice" 
                      value={currentPrice ? formatCurrency(position.shares_count * currentPrice, position.currency) : null}
                    />
                  </div>
                </div>
                
                {/* P/L Section */}
                <div className="grid grid-cols-2 gap-4">
                  <div className={`p-4 rounded-lg border ${position.unrealized_pl >= 0 ? 'bg-green-900/20 border-green-700' : 'bg-red-900/20 border-red-700'}`}>
                    <p className="text-xs text-slate-500 mb-1">Nerealizovaný P/L</p>
                    <p className={`text-xl font-bold ${position.unrealized_pl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                      {formatCurrency(position.unrealized_pl, position.currency)}
                    </p>
                    <p className={`text-sm ${position.unrealized_pl_percent >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                      {position.unrealized_pl_percent >= 0 ? '+' : ''}{position.unrealized_pl_percent.toFixed(2)}%
                    </p>
                  </div>
                  
                  {/* Allocation */}
                  <div className="p-4 rounded-lg border border-slate-700 bg-[#161b22]">
                    <p className="text-xs text-slate-500 mb-1">Alokace v portfoliu</p>
                    <p className="text-xl font-bold text-slate-200">
                      {position.weight_in_portfolio?.toFixed(1) ?? 0}%
                    </p>
                    <p className="text-xs text-slate-400">
                      Max: {position.target_weight_pct?.toFixed(0) ?? stock.max_allocation_cap ?? 10}%
                    </p>
                  </div>
                </div>
                
                {/* Gap Analysis */}
                {position.gap_czk !== undefined && (
                  <div className={`p-4 rounded-lg border ${position.gap_czk > 0 ? 'bg-green-900/20 border-green-700' : position.gap_czk < 0 ? 'bg-yellow-900/20 border-yellow-700' : 'border-slate-700 bg-[#161b22]'}`}>
                    <p className="text-xs text-slate-500 mb-1">Gomes Gap Analýza</p>
                    <div className="flex items-center justify-between">
                      <p className={`text-lg font-bold ${position.gap_czk > 0 ? 'text-green-400' : position.gap_czk < 0 ? 'text-yellow-400' : 'text-slate-200'}`}>
                        {position.gap_czk > 0 ? '+' : ''}{formatCurrency(position.gap_czk)}
                      </p>
                      <span className={`px-3 py-1 rounded-full text-sm font-medium ${
                        position.action_signal === 'BUY' ? 'bg-green-900/50 text-green-400' :
                        position.action_signal === 'SELL' ? 'bg-red-900/50 text-red-400' :
                        position.action_signal === 'SNIPER' ? 'bg-emerald-900/50 text-emerald-400' :
                        'bg-slate-800 text-slate-400'
                      }`}>
                        {position.action_signal ?? 'HOLD'}
                      </span>
                    </div>
                    {position.optimal_size !== undefined && position.optimal_size > 0 && (
                      <p className="text-sm text-slate-400 mt-2">
                        Optimální nákup tento měsíc: {formatCurrency(position.optimal_size)}
                      </p>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
        
        {/* Footer */}
        <div className="bg-[#161b22] border-t border-slate-700 p-4 flex justify-end">
          <button 
            onClick={onClose} 
            className="px-6 py-2 bg-slate-700 hover:bg-slate-600 text-slate-200 rounded-lg font-medium transition-colors"
          >
            Zavřít
          </button>
        </div>
      </div>
    </div>
  );
};

// Helper Component: Metric Card
interface MetricCardProps {
  label: string;
  value: string | number | null | undefined;
  variant?: 'default' | 'positive' | 'negative';
}

const MetricCard: React.FC<MetricCardProps> = ({ label, value, variant = 'default' }) => {
  const colorClass = 
    variant === 'positive' ? 'text-green-400' :
    variant === 'negative' ? 'text-red-400' : 'text-slate-200';
  
  return (
    <div className="bg-[#0d1117] rounded-lg p-3 border border-slate-700">
      <p className="text-xs text-slate-500 mb-1">{label}</p>
      <p className={`text-sm font-medium ${colorClass}`}>
        {value ?? 'N/A'}
      </p>
    </div>
  );
};

export default StockDetail;
