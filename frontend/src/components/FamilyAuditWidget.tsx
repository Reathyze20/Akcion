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

  // Backend posílá `priority` (HIGH/MEDIUM), ne pokyn ke koupi. Widget dřív
  // četl `action`, což je pole, které API nikdy neposlalo.
  const getPriorityColor = (priority: string) =>
    priority === 'HIGH'
      ? 'text-warning bg-warning/20'
      : 'text-text-secondary bg-surface-active/20';

  const getScoreColor = (score: number | null) => {
    if (score === null) return 'text-text-muted';
    if (score >= 8) return 'text-positive';
    if (score >= 5) return 'text-warning';
    return 'text-negative';
  };

  return (
    <div className="bg-gradient-to-br from-surface-raised to-surface-base rounded-xl border border-accent/30 p-5">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-accent/20 rounded-lg">
            <Users className="w-5 h-5 text-accent" />
          </div>
          <div>
            <h3 className="text-lg font-bold text-text-primary">Rodinný Audit</h3>
            <p className="text-xs text-text-secondary">Synchronizace portfolií</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button 
            onClick={fetchAudit}
            disabled={loading}
            className="p-2 hover:bg-surface-hover rounded-lg transition-colors"
          >
            <RefreshCw className={`w-4 h-4 text-text-secondary ${loading ? 'animate-spin' : ''}`} />
          </button>
          {onClose && (
            <button onClick={onClose} className="text-text-secondary hover:text-text-primary">✕</button>
          )}
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="mb-4 p-3 bg-negative/20 border border-negative/50 rounded-lg flex items-center gap-2 text-negative text-sm">
          <AlertTriangle className="w-4 h-4" />
          {error}
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="py-8 text-center text-text-secondary">
          <RefreshCw className="w-8 h-8 mx-auto mb-2 animate-spin" />
          <p>Porovnávám portfolia...</p>
        </div>
      )}

      {/* Portfolios compared */}
      {audit && !loading && (
        <>
          <div className="flex items-center justify-center gap-2 mb-4 text-sm text-text-secondary">
            {(audit.owners_analyzed ?? []).map((name: string, i: number) => (
              <React.Fragment key={name}>
                <span className="px-3 py-1 bg-surface-hover rounded-lg text-text-primary">{name}</span>
                {i < (audit.owners_analyzed ?? []).length - 1 && (
                  <ArrowRight className="w-4 h-4" />
                )}
              </React.Fragment>
            ))}
          </div>

          {/* Gaps List */}
          {audit.gaps.length > 0 ? (
            <div className="space-y-2">
              <div className="text-xs text-text-secondary uppercase tracking-wider mb-2 flex items-center gap-2">
                <AlertTriangle className="w-3 h-3 text-warning" />
                Nalezené mezery ({audit.gaps.length})
              </div>
              
              {audit.gaps.map((gap, index) => (
                <div 
                  key={`${gap.ticker}-${index}`}
                  className="flex items-center justify-between p-3 bg-surface-hover/30 rounded-lg 
                             border border-warning/30 hover:border-warning/50 transition-colors"
                >
                  <div className="flex items-center gap-3">
                    <div className={`w-10 h-10 rounded-lg flex items-center justify-center font-bold text-lg
                                     ${getScoreColor(gap.conviction_score)} bg-surface-raised`}>
                      {gap.conviction_score ?? '—'}
                    </div>
                    <div>
                      <div className="font-bold text-text-primary">{gap.ticker}</div>
                      <div className="text-xs text-text-secondary">
                        <span className="text-accent">{gap.owner_with_position}</span> má,
                        <span className="text-warning"> {gap.missing_owner}</span> nemá
                      </div>
                    </div>
                  </div>
                  
                  <span className={`px-3 py-1 rounded-lg text-sm font-semibold ${getPriorityColor(gap.priority)}`}>
                    {gap.priority === 'HIGH' ? 'přednostně' : 'k zvážení'}
                  </span>
                </div>
              ))}

              {/* Summary */}
              {audit.message && (
                <div className="mt-4 p-3 bg-accent/10 rounded-lg border border-accent/30 text-sm text-text-secondary">
                  {audit.message}
                </div>
              )}
            </div>
          ) : (
            <div className="text-center py-8">
              <CheckCircle className="w-12 h-12 mx-auto mb-3 text-positive" />
              <p className="text-lg font-semibold text-positive">Portfolia jsou synchronizovaná!</p>
              <p className="text-sm text-text-secondary mt-1">Žádné mezery k řešení</p>
            </div>
          )}
        </>
      )}
    </div>
  );
};

export default FamilyAuditWidget;


