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
} from 'lucide-react';
import { apiClient } from '../api/client';
import type { DailyAction, DailyActionsResponse } from '../api/client';
import { groupWarnings } from '../lib/warnings';
import { plural } from '../lib/format';

interface DailyActionWidgetProps {
  /**
   * Called when the user hits "Provést". Return true if the app opened a
   * pre-filled trade flow; false falls back to a "execute at broker" note.
   */
  onExecuteAction?: (action: DailyAction) => boolean;
  /**
   * Called when the user wants to resolve a ROZPOR. Rozpory ukazujeme tady
   * jen jako jednořádkovou připomínku — celé odůvodnění (fáze cyklu vs.
   * ocenění) už jednou stojí na záložce „Co s tím", a psát ho sem znovu by
   * bylo doslovné opakování téže věty ze stejného zdroje dat.
   */
  onOpenRozpor?: () => void;
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

// Semantic tokens only — the emoji + label carry the alert level, color stays quiet.
const ACTION_STYLE: Record<string, { border: string; badge: string; label: string }> = {
  BUY: { border: 'border-positive-border', badge: 'bg-positive-bg text-positive', label: 'Koupit' },
  TRIM: { border: 'border-warning-border', badge: 'bg-warning-bg text-warning', label: 'Odebrat — vybrat zisk' },
  SELL: { border: 'border-negative-border', badge: 'bg-negative-bg text-negative', label: 'Prodat — snížit riziko' },
  SELL_WAIT_TIME: { border: 'border-negative-border', badge: 'bg-negative-bg text-negative', label: 'Prodat — kapitál nepracuje' },
  LIQUIDATE_HEAVY: { border: 'border-negative-border', badge: 'bg-negative-bg text-negative', label: 'Zlikvidovat pozici' },
  /*
   * Rozpor není pokyn. Nese varovný tón a níž se u něj nevykresluje
   * tlačítko — provést se nedá něco, co aplikace sama nerozhodla.
   */
  ROZPOR: { border: 'border-warning-border', badge: 'bg-warning-bg text-warning', label: 'Rozpor — rozhodni ty' },
};

/** Pokyny, které se dají provést. Cokoli jinde je otázka, ne příkaz. */
const EXECUTABLE = (actionType: string): boolean => actionType !== 'ROZPOR';

const SOURCE_LABEL: Record<string, string> = {
  GOMES: 'Gomes',
  BREAKOUT_INVESTORS: 'Breakout',
  COMBINED: 'Gomes + Breakout',
};

const formatCzk = (value: number): string =>
  value.toLocaleString('cs-CZ', { style: 'currency', currency: 'CZK', maximumFractionDigits: 0 });

export const DailyActionWidget: React.FC<DailyActionWidgetProps> = ({
  onExecuteAction,
  onOpenRozpor,
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

  const toDo = (data?.actions ?? []).filter((a) => EXECUTABLE(a.action_type)).length;
  const questions = (data?.actions ?? []).length - toDo;

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
    <div className="bg-surface-raised rounded-card border border-border overflow-hidden">
      {/*
        Semafor a volná hotovost se dřív opakovaly i tady — semafor už trvale
        stojí v levém sloupci (SideRail) a hotovost v horní liště appky
        (HOTOVOST pill). Stejný fakt na obrazovce dvakrát není důraz, je to
        šum; zůstává jen tlačítko na obnovení téhle karty.
      */}
      <div className="flex items-center justify-end px-5 pt-4">
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
        /* Klid je správná odpověď většinu dní, ale nezaslouží si třetinu
           obrazovky. Dřív tu byl vycentrovaný štít 48 px a nadpis 30 px
           na jednu větu. */
        <div className="flex items-baseline gap-2.5 px-5 py-3.5">
          <ShieldCheck className="w-4 h-4 shrink-0 translate-y-0.5 text-positive/80" aria-hidden="true" />
          <h2 className="font-display text-lg font-bold tracking-tight text-text-primary">
            Dnes není co dělat.
          </h2>
          <p className="text-[13px] text-text-secondary">
            {alertStyle.label}. Žádné pravidlo nebylo porušeno, kapitál je chráněn.
          </p>
        </div>
      ) : (
        /* State B: 1-3 ranked actions */
        <div className="px-5 py-4">
          {/*
            * Nadpis počítá jen to, co se dá provést. Rozpory jsou otázky a
            * počítat je mezi úkoly by znamenalo tvrdit, že aplikace ví, co
            * dělat — přesně to, co u nich netvrdí.
            */}
          <h2 className="text-lg font-black text-text-primary mb-3 flex items-center gap-2">
            <CheckCircle2 className="w-5 h-5 text-accent" />
            {toDo > 0 ? `CO MÁM DNES UDĚLAT (${toDo})` : 'DNES NIC K PROVEDENÍ'}
            {questions > 0 && (
              <span className="text-[11px] font-bold uppercase tracking-wider text-warning">
                · {questions} {plural(questions, 'rozpor', 'rozpory', 'rozporů')} k rozhodnutí
              </span>
            )}
          </h2>
          <div className="space-y-3">
            {data.actions.map((action, index) => {
              const style = ACTION_STYLE[action.action_type] ?? ACTION_STYLE.SELL;

              /*
               * Rozpor je otázka, ne pokyn — odůvodnění (fáze cyklu vs.
               * ocenění) se nezopakuje, žije na záložce „Co s tím". Tady
               * zůstává jen tolik, aby bylo vidět, že existuje a u koho.
               */
              if (action.action_type === 'ROZPOR') {
                return (
                  <button
                    key={action.id}
                    type="button"
                    onClick={onOpenRozpor}
                    disabled={!onOpenRozpor}
                    className={`flex w-full items-center justify-between gap-3 rounded-lg border bg-surface-raised/40 px-4 py-2.5 text-left transition-colors ${style.border} ${
                      onOpenRozpor ? 'hover:bg-surface-hover' : ''
                    }`}
                  >
                    <span className="flex items-center gap-2 min-w-0">
                      <span className="text-text-muted font-mono text-sm">{index + 1}.</span>
                      <span className={`text-xs font-bold px-2 py-0.5 rounded ${style.badge}`}>
                        {style.label}
                      </span>
                      <span className="font-black text-base text-text-primary">{action.ticker}</span>
                    </span>
                    {onOpenRozpor && (
                      <span className="shrink-0 flex items-center gap-1 text-[11px] font-semibold text-accent">
                        Co s tím
                        <ChevronRight className="w-3.5 h-3.5" />
                      </span>
                    )}
                  </button>
                );
              }

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
        /* Devět skoro stejných vět podle tickeru se čte jako spam. Tři až
           čtyři skupiny podle problému se čtou za dvě vteřiny — a u každé
           stojí, co kvůli ní aplikace nemůže. Nic se nezahazuje: varování,
           kterému skládání nerozumí, se ukáže samo za sebe. */
        <div className="mx-5 mb-4 divide-y divide-warning-border rounded-lg border border-warning-border bg-warning-bg">
          {groupWarnings(data.warnings).map((group, index) => (
            <div key={`${group.kind}-${index}`} className="px-3 py-2">
              <div className="flex items-baseline gap-2">
                <AlertTriangle
                  className="w-3 h-3 shrink-0 translate-y-0.5 text-warning"
                  aria-hidden="true"
                />
                <span className="font-mono text-[12px] font-medium text-warning">
                  {group.kind === 'JINE'
                    ? group.label
                    : `${group.count} ${plural(group.count, 'pozice', 'pozice', 'pozic')} — ${group.label}`}
                </span>
              </div>
              {group.consequence && (
                <p className="mt-0.5 pl-5 text-[11.5px] leading-relaxed text-text-secondary">
                  {group.consequence}
                </p>
              )}
              {group.tickers.length > 0 && group.tickers.length <= 6 && (
                <p className="mt-0.5 pl-5 font-mono text-[10.5px] text-text-muted">
                  {group.tickers.join(' · ')}
                </p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default DailyActionWidget;
