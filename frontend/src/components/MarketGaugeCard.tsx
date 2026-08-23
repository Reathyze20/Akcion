/**
 * MarketGaugeCard — where the S&P sits on its 40-year chart.
 *
 * Canon §2 derives the semafor from this chart. The app has never had it: the
 * alert was a field someone remembers to switch, and GREEN has meant "nobody
 * touched this".
 *
 * Two rules govern how this renders:
 *
 * 1. **It suggests; it never sets.** There is no button here that writes the
 *    semafor. The measure finds one of the canon's two RED calls and misses
 *    the other, and a field it could set on its own would turn that
 *    half-blindness into an instruction.
 * 2. **The blind spot is shown, not buried.** It is the single most important
 *    thing to know before acting on the number, so it is on the card rather
 *    than behind a tooltip.
 */

import React, { useCallback, useEffect, useState } from 'react';
import { AlertTriangle, Check, Info, RefreshCw, TrendingUp } from 'lucide-react';
import { apiClient } from '../api/client';
import { alertDot, alertName, day, decimal, percent } from '../lib/format';
import Term from './ui/Term';
import type { ChannelPosition, MarketGauge } from '../api/client';

interface MarketGaugeCardProps {
  className?: string;
}

const POSITION_STYLE: Record<
  ChannelPosition,
  { label: string; pill: string; marker: string }
> = {
  AT_UPPER_LINE: {
    label: 'U HORNÍ LINIE',
    pill: 'bg-negative-bg text-negative border-negative-border',
    marker: 'bg-negative',
  },
  EXPENSIVE: {
    label: 'DRAHÝ TRH',
    pill: 'bg-warning-bg text-warning border-warning-border',
    marker: 'bg-warning',
  },
  ABOVE_TREND: {
    label: 'NAD TRENDEM',
    pill: 'bg-surface-active text-text-secondary border-border',
    marker: 'bg-text-muted',
  },
  BELOW_GREY: {
    label: 'POD ŠEDOU LINIÍ',
    pill: 'bg-positive-bg text-positive border-positive-border',
    marker: 'bg-positive',
  },
  AT_LOWER_LINE: {
    label: 'U SPODNÍ LINIE',
    pill: 'bg-positive-bg text-positive border-positive-border',
    marker: 'bg-positive',
  },
};

const formatIndex = (value: number): string =>
  value.toLocaleString('cs-CZ', { maximumFractionDigits: 0 });

export const MarketGaugeCard: React.FC<MarketGaugeCardProps> = ({ className = '' }) => {
  const [gauge, setGauge] = useState<MarketGauge | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (refresh = false) => {
    setLoading(true);
    setError(null);
    try {
      setGauge(await apiClient.getMarketGauge(refresh));
    } catch (err) {
      // A gauge that cannot be computed shows as unavailable. Rendering a
      // stale or default reading is the failure this whole feature exists to
      // remove.
      setGauge(null);
      setError(err instanceof Error ? err.message : 'Ukazatel se nepodařilo načíst');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading && !gauge) {
    return (
      <div className={`bg-surface-raised border border-border rounded-lg p-4 ${className}`}>
        <div className="h-4 w-40 bg-surface-active rounded animate-pulse" />
        <div className="h-8 w-24 bg-surface-active rounded animate-pulse mt-3" />
      </div>
    );
  }

  if (error || !gauge) {
    return (
      <div
        className={`bg-surface-raised border border-warning-border rounded-lg p-4 ${className}`}
      >
        <div className="flex items-center gap-2 text-warning text-sm font-medium">
          <AlertTriangle size={16} />
          40letý graf S&amp;P se nepodařilo spočítat
        </div>
        <p className="text-text-muted text-xs mt-2">{error}</p>
        <p className="text-text-muted text-xs mt-2">
          Semafor z toho neodvozuju — raději nic než číslo, které si vymyslím.
        </p>
      </div>
    );
  }

  const style = POSITION_STYLE[gauge.position];
  const agrees =
    gauge.current_alert != null &&
    gauge.current_alert.toUpperCase() === gauge.suggested_alert;

  // Where the marker sits between the bottom and top lines, in percent.
  const span = gauge.upper_line - gauge.lower_line;
  const offset = span > 0
    ? Math.min(100, Math.max(0, ((gauge.close - gauge.lower_line) / span) * 100))
    : 50;

  return (
    <div className={`bg-surface-raised border border-border rounded-lg p-4 ${className}`}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <TrendingUp size={16} className="text-text-muted" />
            <h3 className="text-text-primary text-sm font-semibold">
              {gauge.index} na dlouhodobém grafu
            </h3>
          </div>
          <p className="text-text-muted text-xs mt-1">
            Kánon §2 z tohohle odvozuje semafor. Data k {day(gauge.as_of)}.
          </p>
        </div>
        <button
          onClick={() => void load(true)}
          disabled={loading}
          className="text-text-muted hover:text-text-primary transition-colors disabled:opacity-40"
          title="Přepočítat"
        >
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
        </button>
      </div>

      <div className="flex items-baseline gap-3 mt-4">
        <span className="text-text-primary text-2xl font-semibold tabular-nums">
          {gauge.z_score > 0 ? '+' : ''}
          {decimal(gauge.z_score, 2)}
          <Term id="sigma">σ</Term>
        </span>
        <span
          className={`px-2 py-0.5 rounded border text-[11px] font-medium ${style.pill}`}
        >
          {style.label}
        </span>
        <span className="text-text-muted text-xs">
          {Math.round(gauge.percentile)}. percentil za {decimal(gauge.years)} let
        </span>
      </div>

      {/* The three lines, and where the index sits between them. */}
      <div className="mt-4">
        <div className="relative h-2 rounded-full bg-surface-active overflow-hidden">
          <div
            className={`absolute top-0 h-full w-1 rounded-full ${style.marker}`}
            style={{ left: `calc(${offset}% - 2px)` }}
          />
        </div>
        <div className="flex justify-between text-[10px] text-text-muted mt-1 tabular-nums">
          <span>spodní {formatIndex(gauge.lower_line)}</span>
          <span>trend {formatIndex(gauge.grey_line)}</span>
          <span>horní {formatIndex(gauge.upper_line)}</span>
        </div>
        <p className="text-text-secondary text-xs mt-2">{gauge.position_cs}</p>
      </div>

      {/* The suggestion, and whether it argues with the field. */}
      <div
        className={`mt-4 rounded border p-3 ${
          agrees
            ? 'bg-surface-base border-border-subtle'
            : 'bg-warning-bg border-warning-border'
        }`}
      >
        <div className="flex items-center gap-2 text-xs">
          {agrees ? (
            <Check size={14} className="text-positive shrink-0" />
          ) : (
            <AlertTriangle size={14} className="text-warning shrink-0" />
          )}
          <span className="text-text-primary">
            Graf odpovídá stupni{' '}
            <span
              className={`inline-block h-2 w-2 rounded-full align-middle ${alertDot(gauge.suggested_alert)}`}
              aria-hidden="true"
            />{' '}
            <strong>{alertName(gauge.suggested_alert)}</strong>
          </span>
        </div>
        <p className="text-text-secondary text-xs mt-2">{gauge.agreement_cs}</p>
      </div>

      {/* Not a footnote: this is what to know before trusting the number. */}
      <div className="mt-3 flex gap-2 text-[11px] text-text-muted leading-relaxed">
        <Info size={13} className="shrink-0 mt-0.5" />
        <p>{gauge.blind_spot_cs}</p>
      </div>

      <p className="text-[10px] text-text-muted mt-3">
        Dlouhodobý trend {percent(gauge.trend_pct_per_year)} ročně. Semafor
        se z tohohle nepřepíná automaticky — je to podklad, ne verdikt.
      </p>
    </div>
  );
};

export default MarketGaugeCard;
