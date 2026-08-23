/**
 * CashHedgeCard — the semafor in instruments, not percentages.
 *
 * Canon §2 names BOXX and RWM. The app modelled both as abstract percentages,
 * which is a plan you cannot execute.
 *
 * The card leads with the blocker rather than the target, because both
 * instruments are US-domiciled and this portfolio is held through EU retail
 * brokers, which under PRIIPs generally cannot sell them. Showing "put 93,317
 * CZK into RWM" as the headline would be a plan for a button that is not
 * there. The canon's own fallback — hold the cash, be more selective — is what
 * gets the emphasis instead.
 *
 * Percentages the canon did not give are labelled as the app's reading. Gomes
 * gives a number for GREEN and YELLOW; ORANGE gets a sentence and RED a
 * description, and rendering 25/35/40 as scripture would put words in his
 * mouth.
 */

import React, { useCallback, useEffect, useState } from 'react';
import { AlertTriangle, Ban, Info, Quote, Wallet } from 'lucide-react';
import { apiClient } from '../api/client';
import { alertName } from '../lib/format';
import type { CashHedgeLeg, CashHedgePlan } from '../api/client';

interface CashHedgeCardProps {
  /** Override the stored semafor — used to preview a level you are not in. */
  alert?: string;
  className?: string;
}

const ROLE_LABEL: Record<string, string> = {
  CASH_PARK: 'Parkoviště hotovosti',
  HEDGE: 'Hedge',
};

const formatCzk = (value: number): string =>
  value.toLocaleString('cs-CZ', {
    style: 'currency',
    currency: 'CZK',
    maximumFractionDigits: 0,
  });

const Leg: React.FC<{ leg: CashHedgeLeg }> = ({ leg }) => {
  const blocked = leg.availability === 'LIKELY_BLOCKED_EU_RETAIL';

  return (
    <div
      className={`rounded border p-3 ${
        blocked ? 'border-warning-border bg-warning-bg/30' : 'border-border-subtle bg-surface-base'
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-text-primary text-sm font-semibold">{leg.ticker}</span>
            <span className="text-[10px] uppercase tracking-wide text-text-muted">
              {ROLE_LABEL[leg.role] ?? leg.role}
            </span>
          </div>
          <p className="text-text-muted text-[11px] mt-0.5">
            {leg.name} · {leg.exchange}
          </p>
        </div>
        <div className="text-right shrink-0">
          <div className="text-text-primary text-sm font-medium tabular-nums">
            {formatCzk(leg.target_czk)}
          </div>
          <div className="text-text-muted text-[11px] tabular-nums">
            {leg.shares != null && leg.price != null
              ? `${leg.shares.toLocaleString('cs-CZ', { maximumFractionDigits: 1 })} ks à ${leg.price.toFixed(2)} ${leg.currency}`
              : 'počet kusů neznám'}
          </div>
        </div>
      </div>

      <p className="text-text-secondary text-[11px] mt-2 leading-relaxed">{leg.note_cs}</p>

      {leg.blocker_cs && (
        <div className="flex gap-2 mt-2 text-[11px] text-warning leading-relaxed">
          <Ban size={13} className="shrink-0 mt-0.5" />
          <p>{leg.blocker_cs}</p>
        </div>
      )}
    </div>
  );
};

export const CashHedgeCard: React.FC<CashHedgeCardProps> = ({ alert, className = '' }) => {
  const [plan, setPlan] = useState<CashHedgePlan | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setPlan(await apiClient.getCashHedgePlan(alert));
    } catch (err) {
      // Includes the deliberate 400 for an unset semafor. Planning for GREEN
      // because nobody touched the field is how a portfolio ends up unhedged
      // by accident, so that refusal is shown as itself.
      setPlan(null);
      setError(err instanceof Error ? err.message : 'Plán se nepodařilo sestavit');
    } finally {
      setLoading(false);
    }
  }, [alert]);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading && !plan) {
    return (
      <div className={`bg-surface-raised border border-border rounded-lg p-4 ${className}`}>
        <div className="h-4 w-40 bg-surface-active rounded animate-pulse" />
        <div className="h-16 w-full bg-surface-active rounded animate-pulse mt-3" />
      </div>
    );
  }

  if (!plan) {
    return (
      <div
        className={`bg-surface-raised border border-warning-border rounded-lg p-4 ${className}`}
      >
        <div className="flex items-center gap-2 text-warning text-sm font-medium">
          <AlertTriangle size={16} />
          Hotovost a hedge nelze spočítat
        </div>
        <p className="text-text-muted text-xs mt-2">{error}</p>
      </div>
    );
  }

  return (
    <div className={`bg-surface-raised border border-border rounded-lg p-4 ${className}`}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <Wallet size={16} className="text-text-muted" />
            <h3 className="text-text-primary text-sm font-semibold">
              Hotovost a hedge při stupni {alertName(plan.alert)}
            </h3>
          </div>
          <p className="text-text-muted text-xs mt-1">
            Ze základu {formatCzk(plan.portfolio_czk)}
          </p>
        </div>
        <div className="text-right text-[11px] text-text-muted tabular-nums shrink-0">
          <div>akcie {plan.stocks_pct.toFixed(0)} %</div>
          <div>hotovost {plan.cash_pct.toFixed(0)} %</div>
          <div>hedge {plan.hedge_pct.toFixed(0)} %</div>
        </div>
      </div>

      {/* Whose number is it. */}
      <div className="flex gap-2 mt-3 text-[11px] text-text-secondary leading-relaxed">
        <Quote size={13} className="shrink-0 mt-0.5 text-text-muted" />
        <p>
          {plan.canon_text}
          {plan.interpreted && (
            <span className="text-warning">
              {' '}
              Procenta výše jsou čtení aplikace, ne Gomesova slova.
            </span>
          )}
        </p>
      </div>

      {/* The fallback outranks the targets when the targets cannot be filled. */}
      {plan.fallback_cs && (
        <div className="mt-3 rounded border border-warning-border bg-warning-bg p-3">
          <p className="text-[10px] uppercase tracking-wide text-warning">
            Co s tím doopravdy
          </p>
          <p className="text-text-primary text-xs mt-1 leading-relaxed">
            {plan.fallback_cs}
          </p>
        </div>
      )}

      <div className="space-y-2 mt-3">
        {plan.legs.map((leg) => (
          <Leg key={leg.ticker} leg={leg} />
        ))}
      </div>

      {plan.ucits_example && (
        <div className="mt-3 flex gap-2 text-[11px] text-text-muted leading-relaxed">
          <Info size={13} className="shrink-0 mt-0.5" />
          <p>
            <span className="text-text-secondary">{plan.ucits_example.ticker}</span> —{' '}
            {plan.ucits_example.note_cs}
          </p>
        </div>
      )}

      {plan.gaps.length > 0 && (
        <ul className="mt-3 pt-3 border-t border-border-subtle space-y-1">
          {plan.gaps.map((gap, index) => (
            <li key={index} className="text-text-muted text-[11px] leading-relaxed">
              ⚠️ {gap}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};

export default CashHedgeCard;
