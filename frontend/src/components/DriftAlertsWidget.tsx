/**
 * DriftAlertsWidget Component
 * 
 * Shows thesis drift alerts - when price is rising but fundamentals deteriorating.
 * "Hype předbíhá fundament!" - early warning system.
 */

import React, { useState, useEffect } from 'react';
import { Bell, AlertTriangle, TrendingUp, TrendingDown, Check, X } from 'lucide-react';
import { apiClient } from '../api/client';
import type { ThesisDriftAlert } from '../types';

interface DriftAlertsWidgetProps {
  onClose?: () => void;
  maxAlerts?: number;
}

export const DriftAlertsWidget: React.FC<DriftAlertsWidgetProps> = ({ 
  onClose,
  maxAlerts = 10 
}) => {
  const [alerts, setAlerts] = useState<ThesisDriftAlert[]>([]);
  const [loading, setLoading] = useState(true);
  const [unacknowledgedCount, setUnacknowledgedCount] = useState(0);

  const fetchAlerts = async () => {
    setLoading(true);
    try {
      const data = await apiClient.getDriftAlerts(true);
      setAlerts(data.alerts.slice(0, maxAlerts));
      setUnacknowledgedCount(data.unacknowledged);
    } catch {
      // Silently fail
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAlerts();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const acknowledgeAlert = async (alertId: number) => {
    try {
      await apiClient.acknowledgeDriftAlert(alertId);
      setAlerts(prev => prev.filter(a => a.id !== alertId));
      setUnacknowledgedCount(prev => prev - 1);
    } catch {
      // Silently fail
    }
  };

  const getSeverityStyle = (severity: string) => {
    switch (severity) {
      case 'CRITICAL': return {
        border: 'border-negative/50',
        bg: 'bg-negative/10',
        icon: 'text-negative',
        badge: 'bg-negative/20 text-negative'
      };
      case 'WARNING': return {
        border: 'border-amber-500/50',
        bg: 'bg-warning/10',
        icon: 'text-warning',
        badge: 'bg-warning/20 text-warning'
      };
      default: return {
        border: 'border-blue-500/50',
        bg: 'bg-blue-500/10',
        icon: 'text-accent',
        badge: 'bg-blue-500/20 text-accent'
      };
    }
  };

  const getAlertTypeLabel = (type: string) => {
    switch (type) {
      case 'HYPE_AHEAD_OF_FUNDAMENTALS': return 'Hype předbíhá fundament';
      case 'THESIS_BREAKING': return 'Teze se rozpadá';
      case 'ACCUMULATE_SIGNAL': return 'Signál k akumulaci';
      default: return type;
    }
  };

  const formatTimeAgo = (dateStr: string) => {
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
    const diffDays = Math.floor(diffHours / 24);
    
    if (diffDays > 0) return `před ${diffDays}d`;
    if (diffHours > 0) return `před ${diffHours}h`;
    return 'právě teď';
  };

  if (loading) {
    return (
      <div className="bg-surface-raised/50 rounded-lg p-4 animate-pulse">
        <div className="h-6 bg-surface-hover rounded w-1/3 mb-4" />
        <div className="space-y-2">
          <div className="h-16 bg-surface-hover rounded" />
          <div className="h-16 bg-surface-hover rounded" />
        </div>
      </div>
    );
  }

  return (
    <div className="bg-gradient-to-br from-slate-800 to-slate-900 rounded-xl border border-amber-500/30 p-5">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className="relative">
            <div className="p-2 bg-warning/20 rounded-lg">
              <Bell className="w-5 h-5 text-warning" />
            </div>
            {unacknowledgedCount > 0 && (
              <span className="absolute -top-1 -right-1 w-5 h-5 bg-negative rounded-full 
                               text-xs font-bold text-text-primary flex items-center justify-center animate-pulse">
                {unacknowledgedCount}
              </span>
            )}
          </div>
          <div>
            <h3 className="text-lg font-bold text-text-primary">Thesis Drift Alerty</h3>
            <p className="text-xs text-text-secondary">Když cena a fundament jdou proti sobě</p>
          </div>
        </div>
        {onClose && (
          <button onClick={onClose} className="text-text-secondary hover:text-text-primary">
            <X className="w-5 h-5" />
          </button>
        )}
      </div>

      {/* Alerts List */}
      {alerts.length > 0 ? (
        <div className="space-y-3">
          {alerts.map((alert) => {
            const style = getSeverityStyle(alert.severity);
            return (
              <div 
                key={alert.id}
                className={`p-4 rounded-lg border ${style.border} ${style.bg} transition-all`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex items-start gap-3">
                    <AlertTriangle className={`w-5 h-5 mt-0.5 ${style.icon}`} />
                    <div>
                      {/* Ticker & Type */}
                      <div className="flex items-center gap-2 mb-1">
                        <span className="font-bold text-text-primary text-lg">{alert.ticker}</span>
                        <span className={`text-xs px-2 py-0.5 rounded ${style.badge}`}>
                          {alert.severity}
                        </span>
                      </div>
                      
                      {/* Alert Type */}
                      <div className="text-sm font-semibold text-text-primary mb-1">
                        {getAlertTypeLabel(alert.alert_type)}
                      </div>
                      
                      {/* Message */}
                      <p className="text-sm text-text-secondary">{alert.message}</p>
                      
                      {/* Score Change & Price */}
                      <div className="flex items-center gap-4 mt-2 text-xs">
                        {alert.old_score !== null && alert.new_score !== null && (
                          <div className="flex items-center gap-1">
                            <span className="text-text-secondary">Skóre:</span>
                            <span className={alert.new_score < alert.old_score ? 'text-negative' : 'text-positive'}>
                              {alert.old_score} → {alert.new_score}
                            </span>
                            {alert.new_score < alert.old_score ? 
                              <TrendingDown className="w-3 h-3 text-negative" /> :
                              <TrendingUp className="w-3 h-3 text-positive" />
                            }
                          </div>
                        )}
                        {alert.price_change_pct !== null && (
                          <div className="flex items-center gap-1">
                            <span className="text-text-secondary">Cena:</span>
                            <span className={alert.price_change_pct > 0 ? 'text-positive' : 'text-negative'}>
                              {alert.price_change_pct > 0 ? '+' : ''}{alert.price_change_pct.toFixed(1)}%
                            </span>
                          </div>
                        )}
                        <span className="text-text-muted">{formatTimeAgo(alert.created_at)}</span>
                      </div>
                    </div>
                  </div>
                  
                  {/* Acknowledge Button */}
                  <button
                    onClick={() => acknowledgeAlert(alert.id)}
                    className="p-2 hover:bg-surface-hover/50 rounded-lg transition-colors group"
                    title="Potvrdit alert"
                  >
                    <Check className="w-4 h-4 text-text-secondary group-hover:text-positive" />
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="text-center py-8">
          <Bell className="w-12 h-12 mx-auto mb-3 text-slate-600" />
          <p className="text-text-secondary">Žádné aktivní alerty</p>
          <p className="text-xs text-text-muted mt-1">Vše je v pořádku</p>
        </div>
      )}
    </div>
  );
};

export default DriftAlertsWidget;


