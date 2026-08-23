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

import React, { useState, useEffect } from 'react';
import type { Stock } from '../types';
import { apiClient } from '../api/client';
import {
  GomesHeader,
  SafetyGaugeRow,
  ThesisCard,
  TradeForm,
  TradingDeck,
  SecFilingsCard
} from './stock-detail';
import type { MarketAlert, TradeSide } from '../types';
import {
  BarChart3,
  FileText,
  Clock,
  Info,
  Briefcase,
  Pencil,
  Check,
  X,
} from 'lucide-react';

// Extended position type - loosely typed to accept various position formats
interface EnrichedPosition {
  id: number;
  ticker: string;
  company_name?: string | null;
  shares_count: number;
  avg_cost: number | null;  // null = buy price unknown, user must fill in
  current_price: number | null;
  currency?: string;
  unrealized_pl: number | null;
  unrealized_pl_percent: number | null;
  stock?: Stock;
  conviction_score?: number | null;
  target_weight_pct?: number;
  weight_in_portfolio?: number;
  gap_czk?: number;
  optimal_size?: number;
  action_signal?: 'BUY' | 'HOLD' | 'SELL' | 'SNIPER';
  next_catalyst?: string;
  max_allocation_cap?: number;
  trend_status?: 'BULLISH' | 'BEARISH' | 'NEUTRAL' | 'UNKNOWN';
  is_deteriorated?: boolean;
}

interface StockDetailProps {
  // Either stock OR position must be provided
  stock?: Stock;
  position?: EnrichedPosition;
  onClose: () => void;
  onUpdate?: () => void;
  /**
   * Optional override. When omitted the modal fetches the real traffic light
   * itself — it used to default to GREEN, and since neither call site ever
   * passed it, the RED-market buy block was unreachable in the shipped app.
   */
  marketAlert?: MarketAlert;
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
  onUpdate,
  marketAlert: marketAlertOverride,
}) => {
  // Derive stock from either prop or position
  const stock = stockProp ?? position?.stock;
  const hasPosition = !!position;

  // Build tabs dynamically based on whether we have position data
  const tabs: Tab[] = [
    { id: 'overview', label: 'Přehled', icon: <Info className="w-4 h-4" /> },
    ...(hasPosition ? [{ id: 'position' as TabId, label: 'Pozice', icon: <Briefcase className="w-4 h-4" /> }] : []),
    { id: 'trading', label: 'Trading', icon: <BarChart3 className="w-4 h-4" /> },
    { id: 'analysis', label: 'Analýza', icon: <FileText className="w-4 h-4" /> },
    { id: 'metadata', label: 'Metadata', icon: <Clock className="w-4 h-4" /> },
  ];

  const [activeTab, setActiveTab] = useState<TabId>('overview');

  // Real traffic light. Stays null until it actually loads — null means
  // "unknown", which TradingDeck treats as a hard blocker, not as GREEN.
  const [fetchedAlert, setFetchedAlert] = useState<MarketAlert | null>(null);
  const marketAlert: MarketAlert | null = marketAlertOverride ?? fetchedAlert;

  useEffect(() => {
    if (marketAlertOverride) return;
    let cancelled = false;
    apiClient
      .getMarketStatus()
      .then((data) => {
        if (!cancelled) setFetchedAlert(data.status as MarketAlert);
      })
      .catch(() => {
        // Deliberately leave it null: a failed fetch must not read as GREEN.
      });
    return () => {
      cancelled = true;
    };
  }, [marketAlertOverride]);

  // Which trade form is open, if any.
  const [trade, setTrade] = useState<{ side: TradeSide; requireReason: boolean } | null>(null);

  // Position edit — the only reachable way to fill in a purchase price
  // (Degiro imports leave it null; see AKCION_SPEC §4/§7).
  const [isEditingPosition, setIsEditingPosition] = useState(false);
  const [editShares, setEditShares] = useState('');
  const [editAvgCost, setEditAvgCost] = useState('');
  const [isSavingPosition, setIsSavingPosition] = useState(false);
  const [savePositionError, setSavePositionError] = useState<string | null>(null);
  // `position` is a snapshot prop — refreshPortfolios() updates the row
  // behind this modal but not this already-open instance. Without this
  // override the modal would keep showing "chybí nákupní cena" right after
  // a successful save, which reads as "it didn't work" (a trust bug).
  const [savedOverride, setSavedOverride] = useState<{ shares_count: number; avg_cost: number } | null>(null);

  const startEditingPosition = () => {
    if (!position) return;
    setEditShares((savedOverride?.shares_count ?? position.shares_count).toString());
    const cost = savedOverride ? savedOverride.avg_cost : position.avg_cost;
    setEditAvgCost(cost != null ? cost.toString() : '');
    setSavePositionError(null);
    setIsEditingPosition(true);
  };

  const handleSavePosition = async () => {
    if (!position) return;
    const shares = parseFloat(editShares);
    const avgCost = parseFloat(editAvgCost);
    if (isNaN(shares) || shares <= 0) {
      setSavePositionError('Počet akcií musí být kladné číslo.');
      return;
    }
    if (isNaN(avgCost) || avgCost <= 0) {
      setSavePositionError('Nákupní cena musí být kladné číslo.');
      return;
    }
    setIsSavingPosition(true);
    setSavePositionError(null);
    try {
      await apiClient.updatePosition(position.id, {
        shares_count: shares,
        avg_cost: avgCost,
      });
      setIsEditingPosition(false);
      setSavedOverride({ shares_count: shares, avg_cost: avgCost });
      await onUpdate?.();
    } catch (err) {
      setSavePositionError(
        err instanceof Error ? err.message : 'Uložení selhalo, zkus to znovu.'
      );
    } finally {
      setIsSavingPosition(false);
    }
  };

  // If no stock data available, show error state
  if (!stock) {
    return (
      <div className="fixed inset-0 bg-surface-base/70 flex items-center justify-center z-50 p-4">
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

  const handleBuyClick = () => setTrade({ side: 'BUY', requireReason: false });
  const handleSellClick = () => setTrade({ side: 'SELL', requireReason: false });
  // Reached only via "už jsem obchod udělal" — the trade went against the
  // rules, so the reason field becomes mandatory.
  const handleRecordOffPlan = (side: TradeSide) =>
    setTrade({ side, requireReason: true });

  // Use position's current_price if available, otherwise stock's
  const currentPrice = position?.current_price ?? stock.current_price;

  // Post-save display values: prefer what we just saved (see savedOverride
  // above) over the possibly-stale position prop.
  const displayShares = savedOverride?.shares_count ?? position?.shares_count;
  const displayAvgCost = savedOverride ? savedOverride.avg_cost : position?.avg_cost ?? null;
  const displayUnrealizedPl = savedOverride && currentPrice != null && displayShares != null
    ? (currentPrice - savedOverride.avg_cost) * displayShares
    : position?.unrealized_pl ?? null;
  const displayUnrealizedPlPercent = savedOverride
    ? ((currentPrice != null ? currentPrice : savedOverride.avg_cost) - savedOverride.avg_cost) / savedOverride.avg_cost * 100
    : position?.unrealized_pl_percent ?? null;

  return (
    <div className="fixed inset-0 bg-surface-base/90 flex items-center justify-center z-50 p-4">
      <div className="bg-surface-base border border-border rounded-xl max-w-4xl w-full max-h-[90vh] overflow-hidden flex flex-col shadow-2xl">
        
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
        <div className="bg-surface-raised border-b border-border">
          <div className="flex">
            {tabs.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`
                  flex items-center gap-2 px-5 py-3 text-sm font-medium
                  transition-all border-b-2 -mb-px
                  ${activeTab === tab.id 
                    ? 'text-positive border-positive bg-positive/10' 
                    : 'text-text-secondary border-transparent hover:text-text-primary hover:bg-surface-raised/50'}
                `}
              >
                {tab.icon}
                <span>{tab.label}</span>
              </button>
            ))}
          </div>
        </div>
        
        {/* Scrollable Content */}
        <div className="flex-1 overflow-y-auto custom-scrollbar bg-surface-base">
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

                {/* What the company told the regulator. Above the price
                    targets on purpose: reported results outrank anyone's
                    estimate of where the price should go. */}
                <SecFilingsCard ticker={stock.ticker} />

                {/* Price Targets */}
                {(stock.price_target || stock.price_target_short || stock.price_target_long) && (
                  <div className="bg-surface-raised rounded-lg p-4 border border-border">
                    <h4 className="text-sm font-semibold text-positive mb-3">Cenové cíle</h4>
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                      {stock.price_target && (
                        <div className="bg-surface-base rounded-lg p-3 border border-border-strong">
                          <p className="text-xs text-text-muted mb-1">Obecný cíl</p>
                          <p className="text-lg font-bold text-positive">{stock.price_target}</p>
                          {stock.time_horizon && (
                            <p className="text-xs text-text-secondary mt-1">{stock.time_horizon}</p>
                          )}
                        </div>
                      )}
                      {stock.price_target_short && (
                        <div className="bg-surface-base rounded-lg p-3 border border-positive">
                          <p className="text-xs text-text-muted mb-1">Krátkodobý</p>
                          <p className="text-lg font-bold text-positive">{stock.price_target_short}</p>
                        </div>
                      )}
                      {stock.price_target_long && (
                        <div className="bg-surface-base rounded-lg p-3 border border-accent">
                          <p className="text-xs text-text-muted mb-1">Dlouhodobý</p>
                          <p className="text-lg font-bold text-accent">{stock.price_target_long}</p>
                        </div>
                      )}
                    </div>
                  </div>
                )}
                
                {/* Key Metrics */}
                <div className="bg-surface-raised rounded-lg p-4 border border-border">
                  <h4 className="text-sm font-semibold text-positive mb-3">Klíčové metriky</h4>
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
                {/* Recording a trade takes over the panel while it is open. */}
                {trade && position && (
                  <TradeForm
                    positionId={position.id}
                    ticker={stock.ticker}
                    side={trade.side}
                    currentPrice={currentPrice}
                    sharesHeld={displayShares ?? 0}
                    avgCost={displayAvgCost}
                    currency={position.currency ?? null}
                    requireReason={trade.requireReason}
                    onRecorded={() => { void onUpdate?.(); }}
                    onCancel={() => setTrade(null)}
                  />
                )}

                {trade && !position && (
                  <p className="text-sm text-warning">
                    ⚠️ Obchod nelze zapsat — tahle akcie zatím není pozicí v portfoliu.
                  </p>
                )}

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
                  currency={position?.currency ?? null}
                  sharesHeld={displayShares ?? 0}
                  onBuyClick={handleBuyClick}
                  onSellClick={handleSellClick}
                  onRecordOffPlan={handleRecordOffPlan}
                />
                
                {/* Entry/Exit Zones */}
                <div className="grid grid-cols-2 gap-4">
                  {stock.entry_zone && (
                    <div className="bg-positive/30 border border-positive rounded-lg p-4">
                      <p className="text-xs text-positive font-medium mb-1">Vstupní zóna</p>
                      <p className="text-lg font-bold text-positive">{stock.entry_zone}</p>
                    </div>
                  )}
                  {stock.stop_loss_risk && (
                    <div className="bg-negative/30 border border-negative rounded-lg p-4">
                      <p className="text-xs text-negative font-medium mb-1">Stop Loss / Riziko</p>
                      <p className="text-sm font-medium text-negative">{stock.stop_loss_risk}</p>
                    </div>
                  )}
                </div>
                
                {/* Trade Rationale */}
                {stock.trade_rationale && (
                  <div className="bg-surface-raised rounded-lg p-4 border border-border">
                    <h4 className="text-sm font-semibold text-positive mb-2">Trade Rationale</h4>
                    <p className="text-sm text-text-primary">{stock.trade_rationale}</p>
                  </div>
                )}
                
                {/* Chart Setup */}
                {stock.chart_setup && (
                  <div className="bg-surface-raised rounded-lg p-4 border border-border">
                    <h4 className="text-sm font-semibold text-positive mb-2">Chart Setup</h4>
                    <p className="text-sm text-text-primary">{stock.chart_setup}</p>
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
                  <div className="bg-surface-raised rounded-lg p-4 border border-border">
                    <h4 className="text-sm font-semibold text-text-secondary mb-2">Plná analýza</h4>
                    <pre className="text-sm text-text-primary whitespace-pre-wrap font-mono 
                                    bg-surface-base p-4 rounded-lg max-h-96 overflow-y-auto custom-scrollbar">
                      {stock.raw_notes}
                    </pre>
                  </div>
                )}
                
                {!stock.raw_notes && (
                  <p className="text-text-muted text-center py-8">
                    Žádná detailní analýza není k dispozici.
                  </p>
                )}
              </div>
            )}
            
            {/* Metadata Tab */}
            {activeTab === 'metadata' && (
              <div className="bg-surface-raised rounded-lg p-4 border border-border">
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
                {/* Position Summary — editable: this is the only place in the
                    app to fill in shares/purchase price (e.g. after a Degiro
                    import, which never carries a buy price). */}
                <div className="bg-surface-raised rounded-lg p-4 border border-border">
                  <div className="flex items-center justify-between mb-3">
                    <h4 className="text-sm font-semibold text-positive">Pozice</h4>
                    {!isEditingPosition && (
                      <button
                        onClick={startEditingPosition}
                        className="flex items-center gap-1.5 text-xs font-medium text-text-secondary hover:text-text-primary transition-colors"
                      >
                        <Pencil className="w-3.5 h-3.5" />
                        Upravit
                      </button>
                    )}
                  </div>

                  {isEditingPosition ? (
                    <div className="space-y-3">
                      <div className="grid grid-cols-2 gap-3">
                        <div>
                          <label className="block text-xs text-text-muted mb-1">Počet akcií</label>
                          <input
                            type="number"
                            step="any"
                            value={editShares}
                            onChange={(e) => setEditShares(e.target.value)}
                            className="w-full px-3 py-2 bg-surface-base border border-border rounded-lg text-text-primary text-sm focus:outline-none focus:border-positive"
                          />
                        </div>
                        <div>
                          <label className="block text-xs text-text-muted mb-1">
                            Nákupní cena / akcii ({position.currency || 'USD'})
                          </label>
                          <input
                            type="number"
                            step="any"
                            value={editAvgCost}
                            onChange={(e) => setEditAvgCost(e.target.value)}
                            placeholder="např. 27.75"
                            autoFocus
                            className="w-full px-3 py-2 bg-surface-base border border-border rounded-lg text-text-primary text-sm placeholder-text-muted focus:outline-none focus:border-positive"
                          />
                        </div>
                      </div>
                      {savePositionError && (
                        <p className="text-xs text-negative">{savePositionError}</p>
                      )}
                      <div className="flex gap-2">
                        <button
                          onClick={handleSavePosition}
                          disabled={isSavingPosition}
                          className="flex items-center gap-1.5 px-3 py-1.5 bg-positive hover:bg-positive-muted disabled:opacity-50 text-text-inverse text-xs font-semibold rounded-lg transition-colors"
                        >
                          <Check className="w-3.5 h-3.5" />
                          {isSavingPosition ? 'Ukládám…' : 'Uložit'}
                        </button>
                        <button
                          onClick={() => setIsEditingPosition(false)}
                          disabled={isSavingPosition}
                          className="flex items-center gap-1.5 px-3 py-1.5 bg-surface-hover hover:bg-surface-active text-text-primary text-xs font-medium rounded-lg transition-colors"
                        >
                          <X className="w-3.5 h-3.5" />
                          Zrušit
                        </button>
                      </div>
                    </div>
                  ) : (
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                      <MetricCard
                        label="Počet akcií"
                        value={displayShares}
                      />
                      <MetricCard
                        label="Průměrná cena"
                        value={displayAvgCost != null ? formatCurrency(displayAvgCost, position.currency) : '⚠️ doplň nákupní cenu'}
                      />
                      <MetricCard
                        label="Aktuální cena"
                        value={currentPrice ? formatCurrency(currentPrice, position.currency) : null}
                      />
                      <MetricCard
                        label="Hodnota pozice"
                        value={currentPrice && displayShares != null ? formatCurrency(displayShares * currentPrice, position.currency) : null}
                      />
                    </div>
                  )}
                </div>

                {/* P/L Section — unknown cost basis is a prompt, never a number */}
                <div className="grid grid-cols-2 gap-4">
                  {displayUnrealizedPl != null && displayUnrealizedPlPercent != null ? (
                    <div className={`p-4 rounded-lg border ${displayUnrealizedPl >= 0 ? 'bg-positive/20 border-positive' : 'bg-negative/20 border-negative'}`}>
                      <p className="text-xs text-text-muted mb-1">Nerealizovaný P/L</p>
                      <p className={`text-xl font-bold ${displayUnrealizedPl >= 0 ? 'text-positive' : 'text-negative'}`}>
                        {formatCurrency(displayUnrealizedPl, position.currency)}
                      </p>
                      <p className={`text-sm ${displayUnrealizedPlPercent >= 0 ? 'text-positive' : 'text-negative'}`}>
                        {displayUnrealizedPlPercent >= 0 ? '+' : ''}{displayUnrealizedPlPercent.toFixed(2)}%
                      </p>
                    </div>
                  ) : (
                    <button
                      onClick={startEditingPosition}
                      className="text-left p-4 rounded-lg border border-warning bg-warning/20 hover:bg-warning/30 transition-colors"
                    >
                      <p className="text-xs text-text-muted mb-1">Nerealizovaný P/L</p>
                      <p className="text-sm font-bold text-warning">
                        ⚠️ Chybí nákupní cena — klikni pro doplnění, P/L do té doby nelze spočítat
                      </p>
                    </button>
                  )}
                  
                  {/* Allocation */}
                  <div className="p-4 rounded-lg border border-border bg-surface-raised">
                    <p className="text-xs text-text-muted mb-1">Alokace v portfoliu</p>
                    <p className="text-xl font-bold text-text-primary">
                      {position.weight_in_portfolio?.toFixed(1) ?? 0}%
                    </p>
                    <p className="text-xs text-text-secondary">
                      Max: {position.target_weight_pct?.toFixed(0) ?? stock.max_allocation_cap ?? 10}%
                    </p>
                  </div>
                </div>
                
                {/* Gap Analysis */}
                {position.gap_czk !== undefined && (
                  <div className={`p-4 rounded-lg border ${position.gap_czk > 0 ? 'bg-positive/20 border-positive' : position.gap_czk < 0 ? 'bg-warning/20 border-warning' : 'border-border bg-surface-raised'}`}>
                    <p className="text-xs text-text-muted mb-1">Gomes Gap Analýza</p>
                    <div className="flex items-center justify-between">
                      <p className={`text-lg font-bold ${position.gap_czk > 0 ? 'text-positive' : position.gap_czk < 0 ? 'text-warning' : 'text-text-primary'}`}>
                        {position.gap_czk > 0 ? '+' : ''}{formatCurrency(position.gap_czk)}
                      </p>
                      <span className={`px-3 py-1 rounded-full text-sm font-medium ${
                        position.action_signal === 'BUY' ? 'bg-positive/50 text-positive' :
                        position.action_signal === 'SELL' ? 'bg-negative/50 text-negative' :
                        position.action_signal === 'SNIPER' ? 'bg-positive/50 text-positive' :
                        'bg-surface-raised text-text-secondary'
                      }`}>
                        {position.action_signal ?? 'HOLD'}
                      </span>
                    </div>
                    {position.optimal_size !== undefined && position.optimal_size > 0 && (
                      <p className="text-sm text-text-secondary mt-2">
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
        <div className="bg-surface-raised border-t border-border p-4 flex justify-end">
          <button 
            onClick={onClose} 
            className="px-6 py-2 bg-surface-hover hover:bg-surface-active text-text-primary rounded-lg font-medium transition-colors"
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
    variant === 'positive' ? 'text-positive' :
    variant === 'negative' ? 'text-negative' : 'text-text-primary';
  
  return (
    <div className="bg-surface-base rounded-lg p-3 border border-border">
      <p className="text-xs text-text-muted mb-1">{label}</p>
      <p className={`text-sm font-medium ${colorClass}`}>
        {value ?? 'N/A'}
      </p>
    </div>
  );
};

export default StockDetail;
