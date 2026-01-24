/**
 * FamilyAuditWidget Component
 * 
 * Shows gaps between family portfolios.
 * "Co mám já, ale přítelkyně ne?" - portfolio synchronization.
 */

import React, { useState, useEffect } from 'react';
import { Users, AlertTriangle, CheckCircle, ArrowRight, RefreshCw } from 'lucide-react';
import { apiClient } from '../api/client';
import type { FamilyAuditResponse } from '../types';

interface FamilyAuditWidgetProps {
  onClose?: () => void;
}

export const FamilyAuditWidget: React.FC<FamilyAuditWidgetProps> = ({ onClose }) => {
  const [audit, setAudit] = useState<FamilyAuditResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchAudit = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiClient.getFamilyAudit();
      setAudit(data);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Nepodařilo se načíst rodinný audit');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAudit();
  }, []);

  const getActionColor = (action: string) => {
    switch (action) {
      case 'KOUPIT': return 'text-green-400 bg-green-500/20';
      case 'PRODAT': return 'text-red-400 bg-red-500/20';
      case 'PŘIDAT': return 'text-emerald-400 bg-emerald-500/20';
      default: return 'text-slate-400 bg-slate-500/20';
    }
  };

  const getScoreColor = (score: number) => {
    if (score >= 8) return 'text-green-400';
    if (score >= 5) return 'text-yellow-400';
    return 'text-red-400';
  };

  return (
    <div className="bg-gradient-to-br from-slate-800 to-slate-900 rounded-xl border border-purple-500/30 p-5">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-purple-500/20 rounded-lg">
            <Users className="w-5 h-5 text-purple-400" />
          </div>
          <div>
            <h3 className="text-lg font-bold text-white">Rodinný Audit</h3>
            <p className="text-xs text-slate-400">Synchronizace portfolií</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button 
            onClick={fetchAudit}
            disabled={loading}
            className="p-2 hover:bg-slate-700 rounded-lg transition-colors"
          >
            <RefreshCw className={`w-4 h-4 text-slate-400 ${loading ? 'animate-spin' : ''}`} />
          </button>
          {onClose && (
            <button onClick={onClose} className="text-slate-400 hover:text-white">✕</button>
          )}
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="mb-4 p-3 bg-red-500/20 border border-red-500/50 rounded-lg flex items-center gap-2 text-red-300 text-sm">
          <AlertTriangle className="w-4 h-4" />
          {error}
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="py-8 text-center text-slate-400">
          <RefreshCw className="w-8 h-8 mx-auto mb-2 animate-spin" />
          <p>Porovnávám portfolia...</p>
        </div>
      )}

      {/* Portfolios compared */}
      {audit && !loading && (
        <>
          <div className="flex items-center justify-center gap-2 mb-4 text-sm text-slate-400">
            {audit.portfolios_compared.map((name, i) => (
              <React.Fragment key={name}>
                <span className="px-3 py-1 bg-slate-700 rounded-lg text-white">{name}</span>
                {i < audit.portfolios_compared.length - 1 && (
                  <ArrowRight className="w-4 h-4" />
                )}
              </React.Fragment>
            ))}
          </div>

          {/* Gaps List */}
          {audit.gaps.length > 0 ? (
            <div className="space-y-2">
              <div className="text-xs text-slate-400 uppercase tracking-wider mb-2 flex items-center gap-2">
                <AlertTriangle className="w-3 h-3 text-amber-400" />
                Nalezené mezery ({audit.gaps.length})
              </div>
              
              {audit.gaps.map((gap, index) => (
                <div 
                  key={`${gap.ticker}-${index}`}
                  className="flex items-center justify-between p-3 bg-slate-700/30 rounded-lg 
                             border border-amber-500/30 hover:border-amber-500/50 transition-colors"
                >
                  <div className="flex items-center gap-3">
                    <div className={`w-10 h-10 rounded-lg flex items-center justify-center font-bold text-lg
                                     ${getScoreColor(gap.gomes_score)} bg-slate-800`}>
                      {gap.gomes_score}
                    </div>
                    <div>
                      <div className="font-bold text-white">{gap.ticker}</div>
                      <div className="text-xs text-slate-400">
                        <span className="text-purple-400">{gap.holder}</span> má, 
                        <span className="text-amber-400"> {gap.missing_from}</span> nemá
                      </div>
                    </div>
                  </div>
                  
                  <span className={`px-3 py-1 rounded-lg text-sm font-semibold ${getActionColor(gap.action)}`}>
                    {gap.action}
                  </span>
                </div>
              ))}

              {/* Summary */}
              <div className="mt-4 p-3 bg-purple-500/10 rounded-lg border border-purple-500/30 text-sm text-slate-300">
                {audit.summary}
              </div>
            </div>
          ) : (
            <div className="text-center py-8">
              <CheckCircle className="w-12 h-12 mx-auto mb-3 text-green-400" />
              <p className="text-lg font-semibold text-green-400">Portfolia jsou synchronizovaná!</p>
              <p className="text-sm text-slate-400 mt-1">Žádné mezery k řešení</p>
            </div>
          )}
        </>
      )}
    </div>
  );
};

export default FamilyAuditWidget;
