/**
 * DailyActionWidget — Path 1: "Co mám dnes udělat?"
 *
 * One glance, ≤2 minutes: either the first-class rest state "Nic. Drž."
 * or at most 3 ranked actions with exact amounts from the backend rule
 * engine (GET /api/trading/daily-actions).
 *
 * Honesty rules: backend warnings (⚠️ CHYBÍ ÚDAJE / stará cena) are always
 * rendered; a fetch error shows as an error, never as a quiet "all good".
 */

import React, { useCallback, useEffect, useState } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  ChevronRight,
  RefreshCw,
  ShieldCheck,
  Wallet,
} from 'lucide-react';
import { apiClient } from '../api/client';
import type { DailyAction, DailyActionsResponse } from '../api/client';

interface DailyActionWidgetProps {
  /**
   * Called when the user hits "Provést". Return true if the app opened a
   * pre-filled trade flow; false falls back to a "execute at broker" note.
   */
  onExecuteAction?: (action: DailyAction) => boolean;
  /** Bump to force a refetch (e.g. after a recorded trade). */
  refreshKey?: number;
}

/*
 * Stupeň semaforu nese barevný bod, ne emoji. Emoji se vykresluje písmem
 * systému, takže na každém stroji vypadá jinak a v tištěné podobě zmizí
 * úplně; navíc se nedá přebarvit s tématem.
 */
const ALERT_STYLE: Record<string, { dot: string; label: string; pill: string }> = {
  GREEN: {
    dot: 'bg-signal-green',
    label: 'Trh je v pořádku',
    pill: 'bg-positive-bg text-positive border-positive-border',
  },
  YELLOW: {
    dot: 'bg-signal-amber',
    label: 'Žlutá — jen nejlepší příležitosti',
    pill: 'bg-warning-bg text-warning border-warning-border',
  },
  ORANGE: {
    dot: 'bg-signal-orange',
    label: 'Oranžová — obranné držení',
    pill: 'bg-warning-bg text-warning border-warning-border',
  },
  RED: {
    dot: 'bg-signal-red',
    label: 'Červená — přednost má hotovost',
    pill: 'bg-negative-bg text-negative border-negative-border',
  },
  UNKNOWN: {
    dot: 'bg-text-muted',
    label: 'Semafor není nastaven',
    pill: 'bg-warning-bg text-warning border-warning-border',
  },
};

const ALERT_NAME: Record<string, string> = {
  GREEN: 'zelená',
  YELLOW: 'žlutá',
  ORANGE: 'oranžová',
  RED: 'červená',
};

// Semantic tokens only — the emoji + label carry the alert level, color stays quiet.
const ACTION_STYLE: Record<string, { border: string; badge: string; label: string }> = {
  BUY: { border: 'border-positive-border', badge: 'bg-positive-bg text-positive', label: 'Koupit' },
  TRIM: { border: 'border-warning-border', badge: 'bg-warning-bg text-warning', label: 'Odebrat — vybrat zisk' },
  SELL: { border: 'border-negative-border', badge: 'bg-negative-bg text-negative', label: 'Prodat — snížit riziko' },
  SELL_WAIT_TIME: { border: 'border-negative-border', badge: 'bg-negative-bg text-negative', label: 'Prodat — kapitál nepracuje' },
  LIQUIDATE_HEAVY: { border: 'border-negative-border', badge: 'bg-negative-bg text-negative', label: 'Zlikvidovat pozici' },
};

const SOURCE_LABEL: Record<string, string> = {
  GOMES: 'Gomes',
  BREAKOUT_INVESTORS: 'Breakout',
  COMBINED: 'Gomes + Breakout',
};

const formatCzk = (value: number): string =>
  value.toLocaleString('cs-CZ', { style: 'currency', currency: 'CZK', maximumFractionDigits: 0 });

export const DailyActionWidget: React.FC<DailyActionWidgetProps> = ({
  onExecuteAction,
  refreshKey = 0,
}) => {
  const [data, setData] = useState<DailyActionsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [manualNote, setManualNote] = useState<string | null>(null);

  const fetchActions = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await apiClient.getDailyActions();
      setData(response);
    } catch (err) {
      // Honest failure: no cached pretend-success.
      setData(null);
      setError(err instanceof Error ? err.message : 'Načtení denních akcí selhalo');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchActions();
  }, [fetchActions, refreshKey]);

  const handleExecute = (action: DailyAction) => {
    const handled = onExecuteAction?.(action) ?? false;
    setManualNote(
      handled
        ? null
        : `${action.ticker}: proveď obchod ručně u brokera (${action.action_type} ${action.quantity} ks), pak ho zaznamenej v detailu pozice.`
    );
  };

  if (loading) {
    return (
      <div className="mb-4 bg-surface-raised/50 rounded-xl border border-border p-5 animate-pulse">
        <div className="h-7 bg-surface-hover rounded w-1/3 mb-3" />
        <div className="h-16 bg-surface-hover rounded" />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="mb-4 bg-negative/10 rounded-xl border border-negative/40 p-5">
        <div className="flex items-center gap-3">
          <AlertTriangle className="w-6 h-6 text-negative shrink-0" />
          <div className="flex-1">
            <h3 className="font-bold text-negative">Denní akce nelze načíst</h3>
            <p className="text-sm text-text-secondary mt-0.5">
              {error ?? 'Neznámá chyba'} — bez dat žádné doporučení, nejednej naslepo.
            </p>
          </div>
          <button
            onClick={fetchActions}
            className="px-3 py-2 bg-negative/20 hover:bg-negative/30 text-negative rounded-lg text-sm font-medium flex items-center gap-2 transition-colors"
          >
            <RefreshCw className="w-4 h-4" />
            Zkusit znovu
          </button>
        </div>
      </div>
    );
  }

  const alertStyle = ALERT_STYLE[data.market_alert] ?? ALERT_STYLE.UNKNOWN;
  const isHold = data.status === 'HOLD_HOLD_HOLD';

  return (
    <div className="mb-4 bg-surface-raised rounded-xl border border-border overflow-hidden">
      {/* Header row: alert pill + cash pill + refresh */}
      <div className="flex items-center justify-between px-5 pt-4">
        <div className="flex items-center gap-2 flex-wrap">
          <span
            className={`flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-semibold ${alertStyle.pill}`}
          >
            <span className={`h-2 w-2 rounded-full ${alertStyle.dot}`} aria-hidden="true" />
            Semafor: {ALERT_NAME[data.market_alert] ?? data.market_alert}
          </span>
          <span className="flex items-center gap-1.5 rounded-full border border-accent/40 bg-accent/10 px-3 py-1 text-xs font-semibold text-accent">
            <Wallet className="w-3.5 h-3.5" />
            Volná hotovost: {formatCzk(data.available_cash_czk)}
          </span>
        </div>
        <button
          onClick={fetchActions}
          title="Obnovit"
          className="p-2 hover:bg-surface-hover rounded-lg text-text-secondary hover:text-text-primary transition-colors"
        >
          <RefreshCw className="w-4 h-4" />
        </button>
      </div>

      {isHold ? (
        /* State A: Nic. Drž. — the correct answer most days */
        <div className="px-5 py-8 text-center">
          <ShieldCheck className="w-12 h-12 mx-auto mb-3 text-positive/80" />
          <h2 className="font-display text-3xl font-bold tracking-tight text-text-primary">
            Dnes není co dělat.
          </h2>
          <p className="mt-2 text-sm text-text-secondary">
            {alertStyle.label}. Žádné pravidlo nebylo porušeno, kapitál je chráněn.
          </p>
        </div>
      ) : (
        /* State B: 1-3 ranked actions */
        <div className="px-5 py-4">
          <h2 className="text-lg font-black text-text-primary mb-3 flex items-center gap-2">
            <CheckCircle2 className="w-5 h-5 text-accent" />
            CO MÁM DNES UDĚLAT ({data.actions.length})
          </h2>
          <div className="space-y-3">
            {data.actions.map((action, index) => {
              const style = ACTION_STYLE[action.action_type] ?? ACTION_STYLE.SELL;
              return (
                <div
                  key={action.id}
                  className={`p-4 rounded-lg border bg-surface-raised/40 ${style.border}`}
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2 flex-wrap mb-1">
                        <span className="text-text-muted font-mono text-sm">{index + 1}.</span>
                        <span className={`text-xs font-bold px-2 py-0.5 rounded ${style.badge}`}>
                          {style.label}
                        </span>
                        <span className="font-black text-lg text-text-primary">{action.ticker}</span>
                        <span className="text-[10px] uppercase tracking-wider px-2 py-0.5 rounded bg-surface-hover text-text-secondary">
                          {SOURCE_LABEL[action.source_key] ?? action.source_key}
                        </span>
                        {action.review_required && (
                          <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-warning/20 text-warning">
                            ⚠️ ZKONTROLUJ — zdroje v konfliktu
                          </span>
                        )}
                      </div>
                      <div className="text-sm text-text-primary font-mono">
                        {action.quantity.toLocaleString('cs-CZ')} ks × {action.current_price.toLocaleString('cs-CZ')} {action.currency}
                        <span className="mx-2 text-text-muted">≈</span>
                        <span className="font-bold">{formatCzk(action.estimated_czk_value)}</span>
                      </div>
                      <p className="text-xs text-text-secondary mt-1">{action.reason}</p>
                    </div>
                    <button
                      onClick={() => handleExecute(action)}
                      className="shrink-0 px-4 py-2 bg-accent hover:bg-accent/80 text-text-primary rounded-lg text-sm font-bold flex items-center gap-1.5 transition-colors"
                    >
                      Provést
                      <ChevronRight className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
          {manualNote && (
            <p className="mt-3 text-xs text-accent bg-accent/10 border border-accent/30 rounded-lg px-3 py-2">
              {manualNote}
            </p>
          )}
        </div>
      )}

      {/* Data-honesty warnings — always visible, both states */}
      {data.warnings.length > 0 && (
        <div className="mx-5 mb-4 p-3 rounded-lg bg-warning-bg border border-warning-border">
          {data.warnings.map((warning) => (
            <p key={warning} className="text-xs text-warning py-0.5">
              {warning}
            </p>
          ))}
        </div>
      )}
    </div>
  );
};

export default DailyActionWidget;
