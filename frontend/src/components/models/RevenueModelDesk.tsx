/**
 * Stůl jednoho modelu tržeb.
 *
 * Pořadí shora dolů:
 *   1. hlavička — ticker, jméno modelu, zdroj a datum
 *   2. poznámky z dokumentu (volný text, když existuje)
 *   3. období po období: co model tvrdí, a tlačítkem po straně co říká realita
 *   4. řádky modelu, seskupené po kategoriích, pro vybrané období
 *
 * Porovnání s realitou je zdarma, ale sahá na SEC — proto je to tlačítko,
 * ne něco, co běží samo při otevření.
 */

import { useCallback, useMemo, useState } from 'react';
import { Scale } from 'lucide-react';

import { apiClient } from '../../api/client';
import type {
  RevenueModelComparison,
  RevenueModelDetail as RevenueModelDetailType,
  RevenueModelPeriodComparison,
} from '../../api/client';
import { bigMoney, day, percent } from '../../lib/format';

interface Props {
  model: RevenueModelDetailType;
}

function confidenceBadge(confidence: string | null | undefined) {
  if (confidence === 'LOCKED') {
    return <span className="badge badge-positive">potvrzená objednávka</span>;
  }
  if (confidence === 'ESTIMATE') {
    return <span className="badge badge-warning">odhad</span>;
  }
  return <span className="badge badge-neutral">nepřečteno z originálu</span>;
}

function varianceBadge(comparison: RevenueModelPeriodComparison | undefined) {
  if (!comparison) return null;
  if (comparison.gap_cs) {
    return <span className="text-[11px] text-text-muted">{comparison.gap_cs}</span>;
  }
  if (comparison.variance_pct == null) return null;
  const over = comparison.variance_pct > 0;
  return (
    <span className={over ? 'data-value-negative' : 'data-value-positive'}>
      model {over ? 'nad' : 'pod'} realitou o {percent(Math.abs(comparison.variance_pct))}
    </span>
  );
}

export default function RevenueModelDesk({ model }: Props) {
  const [selectedPeriod, setSelectedPeriod] = useState<string | null>(
    model.period_totals[0]?.period_label ?? null,
  );
  const [comparison, setComparison] = useState<RevenueModelComparison | null>(null);
  const [comparing, setComparing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const compare = useCallback(async () => {
    setComparing(true);
    setError(null);
    try {
      setComparison(await apiClient.compareRevenueModel(model.id));
    } catch (e) {
      const d = (e as { detail?: string })?.detail;
      setError(d ?? (e instanceof Error ? e.message : 'Porovnání s realitou selhalo'));
    } finally {
      setComparing(false);
    }
  }, [model.id]);

  const comparisonByPeriod = useMemo(() => {
    const map = new Map<string, RevenueModelPeriodComparison>();
    for (const c of comparison?.comparisons ?? []) map.set(c.period_label, c);
    return map;
  }, [comparison]);

  const linesForPeriod = useMemo(
    () => model.lines.filter((l) => l.period_label === selectedPeriod),
    [model.lines, selectedPeriod],
  );

  const categories = useMemo(() => {
    const seen: string[] = [];
    for (const line of linesForPeriod) {
      if (!seen.includes(line.category)) seen.push(line.category);
    }
    return seen;
  }, [linesForPeriod]);

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3">
      {/* 1. hlavička */}
      <div className="flex items-baseline justify-between gap-3">
        <div className="flex items-baseline gap-2">
          <h2 className="font-display text-lg text-text-primary [font-stretch:78%]">
            {model.ticker}
          </h2>
          {model.company_name && (
            <span className="text-sm text-text-secondary">{model.company_name}</span>
          )}
        </div>
        <div className="flex items-center gap-3 text-[11px] text-text-muted">
          <span>{model.source_name}</span>
          {model.document_date && <span>{day(model.document_date)}</span>}
        </div>
      </div>
      <p className="text-sm text-text-secondary">{model.model_name}</p>

      {error && (
        <div className="rounded-card border border-negative-border bg-negative-bg px-3 py-2 text-xs text-negative">
          {error}
        </div>
      )}

      {/* 2. poznámky z dokumentu */}
      {model.notes && (
        <div className="rounded-card bg-frame p-4">
          <p className="eyebrow text-frame-muted">Poznámky z dokumentu</p>
          <p className="mt-1.5 whitespace-pre-line text-sm text-text-inverse">{model.notes}</p>
        </div>
      )}

      {/* 3. období po období */}
      <div className="sheet flex min-h-0 flex-col">
        <div className="sheet-head justify-between">
          <span className="sheet-title">Období</span>
          <button
            type="button"
            className="btn-secondary flex items-center gap-1.5 text-xs"
            onClick={() => void compare()}
            disabled={comparing}
          >
            <Scale className={`h-3.5 w-3.5 ${comparing ? 'animate-pulse' : ''}`} aria-hidden />
            Porovnat s realitou
          </button>
        </div>
        <div className="min-h-0 overflow-y-auto">
          {model.period_totals.map((period) => {
            const active = period.period_label === selectedPeriod;
            const cmp = comparisonByPeriod.get(period.period_label);
            return (
              <button
                key={period.period_label}
                type="button"
                onClick={() => setSelectedPeriod(period.period_label)}
                aria-current={active ? 'true' : undefined}
                className={`sheet-row flex w-full flex-col gap-1 text-left ${
                  active ? 'bg-accent-bg' : ''
                }`}
              >
                <div className="flex items-baseline justify-between gap-2">
                  <span className="font-mono text-sm font-medium text-text-primary">
                    {period.period_label}
                  </span>
                  <span className="data-value">{bigMoney(period.total, period.currency)}</span>
                </div>
                <div className="flex items-baseline justify-between gap-2">
                  <span className="text-[11px] text-text-muted">
                    {period.line_count} {period.line_count === 1 ? 'řádek' : 'řádků'}
                    {period.unrated_lines > 0
                      ? ` · ${period.unrated_lines} bez přečtené barvy`
                      : ''}
                  </span>
                  {varianceBadge(cmp)}
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {/* 4. řádky vybraného období, po kategoriích */}
      {selectedPeriod && (
        <div className="sheet flex min-h-0 flex-1 flex-col">
          <div className="sheet-head">
            <span className="sheet-title">Řádky — {selectedPeriod}</span>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto">
            {categories.map((category) => (
              <div key={category}>
                <div className="bg-sheet-alt px-3 py-1.5">
                  <span className="data-label">{category}</span>
                </div>
                {linesForPeriod
                  .filter((l) => l.category === category)
                  .map((line) => (
                    <div key={line.id} className="sheet-row flex flex-col gap-1">
                      <div className="flex items-baseline justify-between gap-2">
                        <span className="text-sm text-text-primary">{line.item_name}</span>
                        <span className="data-value">
                          {line.resolved_amount != null
                            ? bigMoney(line.resolved_amount, line.currency)
                            : '—'}
                        </span>
                      </div>
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-[11px] text-text-muted">
                          {line.quantity != null && line.price_per_unit != null
                            ? `${line.quantity.toLocaleString('cs-CZ')} ks × ${line.price_per_unit.toLocaleString('cs-CZ')} ${line.currency}`
                            : null}
                        </span>
                        {confidenceBadge(line.confidence)}
                      </div>
                      {line.note && (
                        <span className="text-[11px] text-text-muted">{line.note}</span>
                      )}
                    </div>
                  ))}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
