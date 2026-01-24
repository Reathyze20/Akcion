/**
 * KellyAllocatorWidget Component
 * 
 * Shows recommended allocation based on Kelly Criterion and Gomes scores.
 * "Kolik investovat?" - connects score to actual money amounts.
 */

import React, { useState, useEffect } from 'react';
import { Calculator, DollarSign, TrendingUp, AlertCircle, Wallet, PiggyBank } from 'lucide-react';
import { apiClient } from '../api/client';
import type { AllocationPlanResponse } from '../types';

interface KellyAllocatorWidgetProps {
  portfolioId: number;
  defaultCzk?: number;
  defaultEur?: number;
  onClose?: () => void;
}

// Kelly weights mapping (must match backend)
const KELLY_WEIGHTS: Record<number, number> = {
  10: 20, 9: 15, 8: 12, 7: 10, 6: 8, 5: 5, 4: 3, 3: 2, 2: 1, 1: 0
};

export const KellyAllocatorWidget: React.FC<KellyAllocatorWidgetProps> = ({
  portfolioId,
  defaultCzk = 20000,
  defaultEur = 1393,
  onClose,
}) => {
  const [availableCzk, setAvailableCzk] = useState(defaultCzk);
  const [availableEur, setAvailableEur] = useState(defaultEur);
  const [plan, setPlan] = useState<AllocationPlanResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchPlan = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiClient.getAllocationPlan(portfolioId, availableCzk, availableEur);
      setPlan(data);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Nepodařilo se načíst alokační plán');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (portfolioId) {
      fetchPlan();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [portfolioId]);

  const getRiskColor = (level: string) => {
    switch (level) {
      case 'LOW': return 'text-green-400 bg-green-500/20';
      case 'MEDIUM': return 'text-yellow-400 bg-yellow-500/20';
      case 'HIGH': return 'text-orange-400 bg-orange-500/20';
      case 'EXTREME': return 'text-red-400 bg-red-500/20';
      default: return 'text-slate-400 bg-slate-500/20';
    }
  };

  const formatCurrency = (amount: number, currency: string = 'CZK') => {
    return new Intl.NumberFormat('cs-CZ', { 
      style: 'currency', 
      currency,
      maximumFractionDigits: 0 
    }).format(amount);
  };

  return (
    <div className="bg-gradient-to-br from-slate-800 to-slate-900 rounded-xl border border-indigo-500/30 p-5">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-indigo-500/20 rounded-lg">
            <Calculator className="w-5 h-5 text-indigo-400" />
          </div>
          <div>
            <h3 className="text-lg font-bold text-white">Kelly Alokátor</h3>
            <p className="text-xs text-slate-400">Kolik investovat do každé pozice?</p>
          </div>
        </div>
        {onClose && (
          <button onClick={onClose} className="text-slate-400 hover:text-white">✕</button>
        )}
      </div>

      {/* Capital Inputs */}
      <div className="grid grid-cols-2 gap-3 mb-4">
        <div className="relative">
          <label className="text-xs text-slate-400 mb-1 block">Volný kapitál (CZK)</label>
          <div className="relative">
            <PiggyBank className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
            <input
              type="number"
              value={availableCzk}
              onChange={(e) => setAvailableCzk(Number(e.target.value))}
              className="w-full pl-10 pr-3 py-2 bg-slate-700/50 border border-slate-600 rounded-lg 
                         text-white font-mono text-sm focus:outline-none focus:border-indigo-500"
            />
          </div>
        </div>
        <div className="relative">
          <label className="text-xs text-slate-400 mb-1 block">Volný kapitál (EUR)</label>
          <div className="relative">
            <Wallet className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
            <input
              type="number"
              value={availableEur}
              onChange={(e) => setAvailableEur(Number(e.target.value))}
              className="w-full pl-10 pr-3 py-2 bg-slate-700/50 border border-slate-600 rounded-lg 
                         text-white font-mono text-sm focus:outline-none focus:border-indigo-500"
            />
          </div>
        </div>
      </div>

      {/* Calculate Button */}
      <button
        onClick={fetchPlan}
        disabled={loading}
        className="w-full py-2 mb-4 bg-indigo-600 hover:bg-indigo-500 disabled:bg-slate-600 
                   text-white font-semibold rounded-lg transition-colors flex items-center justify-center gap-2"
      >
        {loading ? (
          <span className="animate-spin">⏳</span>
        ) : (
          <>
            <Calculator className="w-4 h-4" />
            Přepočítat alokaci
          </>
        )}
      </button>

      {/* Error */}
      {error && (
        <div className="mb-4 p-3 bg-red-500/20 border border-red-500/50 rounded-lg flex items-center gap-2 text-red-300 text-sm">
          <AlertCircle className="w-4 h-4" />
          {error}
        </div>
      )}

      {/* Kelly Weight Reference */}
      <div className="mb-4 p-3 bg-slate-700/30 rounded-lg border border-slate-600/50">
        <div className="text-xs text-slate-400 mb-2">Kelly váhy podle skóre:</div>
        <div className="flex flex-wrap gap-1">
          {Object.entries(KELLY_WEIGHTS).map(([score, weight]) => (
            <span 
              key={score}
              className={`px-2 py-0.5 rounded text-xs font-mono ${
                Number(score) >= 8 ? 'bg-green-500/20 text-green-400' :
                Number(score) >= 5 ? 'bg-yellow-500/20 text-yellow-400' :
                'bg-red-500/20 text-red-400'
              }`}
            >
              {score}→{weight}%
            </span>
          ))}
        </div>
      </div>

      {/* Recommendations */}
      {plan && plan.recommendations.length > 0 && (
        <div className="space-y-2">
          <div className="text-xs text-slate-400 uppercase tracking-wider mb-2">
            Doporučené alokace
          </div>
          
          {plan.recommendations.map((rec) => (
            <div 
              key={rec.ticker}
              className="flex items-center justify-between p-3 bg-slate-700/30 rounded-lg 
                         border border-slate-600/50 hover:border-indigo-500/50 transition-colors"
            >
              <div className="flex items-center gap-3">
                <div className={`w-10 h-10 rounded-lg flex items-center justify-center font-bold text-lg
                                 ${rec.gomes_score >= 8 ? 'bg-green-500/20 text-green-400' :
                                   rec.gomes_score >= 5 ? 'bg-yellow-500/20 text-yellow-400' :
                                   'bg-red-500/20 text-red-400'}`}>
                  {rec.gomes_score}
                </div>
                <div>
                  <div className="font-bold text-white">{rec.ticker}</div>
                  <div className="text-xs text-slate-400">
                    Kelly: {rec.kelly_weight_pct}%
                  </div>
                </div>
              </div>
              
              <div className="text-right">
                <div className="flex items-center gap-1 justify-end">
                  <DollarSign className="w-4 h-4 text-emerald-400" />
                  <span className="text-lg font-bold text-emerald-400 font-mono">
                    {formatCurrency(rec.recommended_amount, rec.currency)}
                  </span>
                </div>
                <span className={`text-xs px-2 py-0.5 rounded ${getRiskColor(rec.risk_level)}`}>
                  {rec.risk_level}
                </span>
              </div>
            </div>
          ))}

          {/* Summary */}
          <div className="mt-4 p-3 bg-indigo-500/10 rounded-lg border border-indigo-500/30">
            <div className="flex justify-between items-center">
              <span className="text-slate-300">Celkem alokováno:</span>
              <span className="text-lg font-bold text-indigo-400 font-mono">
                {formatCurrency(plan.total_allocated_czk)}
              </span>
            </div>
            <div className="flex justify-between items-center text-sm">
              <span className="text-slate-400">Zbývá:</span>
              <span className="text-slate-300 font-mono">
                {formatCurrency(plan.remaining_czk)}
              </span>
            </div>
          </div>
        </div>
      )}

      {/* Empty state */}
      {plan && plan.recommendations.length === 0 && (
        <div className="text-center py-6 text-slate-400">
          <TrendingUp className="w-10 h-10 mx-auto mb-2 opacity-50" />
          <p>Žádné pozice k alokaci</p>
          <p className="text-xs">Přidejte akcie s Gomes skóre ≥ 5</p>
        </div>
      )}
    </div>
  );
};

export default KellyAllocatorWidget;
