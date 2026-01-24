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
        border: 'border-red-500/50',
        bg: 'bg-red-500/10',
        icon: 'text-red-400',
        badge: 'bg-red-500/20 text-red-400'
      };
      case 'WARNING': return {
        border: 'border-amber-500/50',
        bg: 'bg-amber-500/10',
        icon: 'text-amber-400',
        badge: 'bg-amber-500/20 text-amber-400'
      };
      default: return {
        border: 'border-blue-500/50',
        bg: 'bg-blue-500/10',
        icon: 'text-blue-400',
        badge: 'bg-blue-500/20 text-blue-400'
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
      <div className="bg-slate-800/50 rounded-lg p-4 animate-pulse">
        <div className="h-6 bg-slate-700 rounded w-1/3 mb-4" />
        <div className="space-y-2">
          <div className="h-16 bg-slate-700 rounded" />
          <div className="h-16 bg-slate-700 rounded" />
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
            <div className="p-2 bg-amber-500/20 rounded-lg">
              <Bell className="w-5 h-5 text-amber-400" />
            </div>
            {unacknowledgedCount > 0 && (
              <span className="absolute -top-1 -right-1 w-5 h-5 bg-red-500 rounded-full 
                               text-xs font-bold text-white flex items-center justify-center animate-pulse">
                {unacknowledgedCount}
              </span>
            )}
          </div>
          <div>
            <h3 className="text-lg font-bold text-white">Thesis Drift Alerty</h3>
            <p className="text-xs text-slate-400">Když cena a fundament jdou proti sobě</p>
          </div>
        </div>
        {onClose && (
          <button onClick={onClose} className="text-slate-400 hover:text-white">
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
                        <span className="font-bold text-white text-lg">{alert.ticker}</span>
                        <span className={`text-xs px-2 py-0.5 rounded ${style.badge}`}>
                          {alert.severity}
                        </span>
                      </div>
                      
                      {/* Alert Type */}
                      <div className="text-sm font-semibold text-white mb-1">
                        {getAlertTypeLabel(alert.alert_type)}
                      </div>
                      
                      {/* Message */}
                      <p className="text-sm text-slate-300">{alert.message}</p>
                      
                      {/* Score Change & Price */}
                      <div className="flex items-center gap-4 mt-2 text-xs">
                        {alert.old_score !== null && alert.new_score !== null && (
                          <div className="flex items-center gap-1">
                            <span className="text-slate-400">Skóre:</span>
                            <span className={alert.new_score < alert.old_score ? 'text-red-400' : 'text-green-400'}>
                              {alert.old_score} → {alert.new_score}
                            </span>
                            {alert.new_score < alert.old_score ? 
                              <TrendingDown className="w-3 h-3 text-red-400" /> :
                              <TrendingUp className="w-3 h-3 text-green-400" />
                            }
                          </div>
                        )}
                        {alert.price_change_pct !== null && (
                          <div className="flex items-center gap-1">
                            <span className="text-slate-400">Cena:</span>
                            <span className={alert.price_change_pct > 0 ? 'text-green-400' : 'text-red-400'}>
                              {alert.price_change_pct > 0 ? '+' : ''}{alert.price_change_pct.toFixed(1)}%
                            </span>
                          </div>
                        )}
                        <span className="text-slate-500">{formatTimeAgo(alert.created_at)}</span>
                      </div>
                    </div>
                  </div>
                  
                  {/* Acknowledge Button */}
                  <button
                    onClick={() => acknowledgeAlert(alert.id)}
                    className="p-2 hover:bg-slate-700/50 rounded-lg transition-colors group"
                    title="Potvrdit alert"
                  >
                    <Check className="w-4 h-4 text-slate-400 group-hover:text-green-400" />
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="text-center py-8">
          <Bell className="w-12 h-12 mx-auto mb-3 text-slate-600" />
          <p className="text-slate-400">Žádné aktivní alerty</p>
          <p className="text-xs text-slate-500 mt-1">Vše je v pořádku</p>
        </div>
      )}
    </div>
  );
};

export default DriftAlertsWidget;
