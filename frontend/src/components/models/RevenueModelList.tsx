/**
 * Seznam analytikových modelů tržeb. Jediná věc na téhle obrazovce, která
 * scrolluje.
 *
 * Řádek nese ticker, jméno modelu a poslední období — čísla a porovnání
 * s realitou jsou v detailu vpravo.
 */

import type { RevenueModelSummary } from '../../api/client';
import { day } from '../../lib/format';

interface Props {
  models: RevenueModelSummary[];
  selectedId: number | null;
  onSelect: (id: number) => void;
}

export default function RevenueModelList({ models, selectedId, onSelect }: Props) {
  if (models.length === 0) {
    return (
      <div className="sheet flex-1 p-3">
        <p className="text-xs text-text-muted">
          Zatím žádný model. Přibude, až se stáhne další od Marka nebo jiného analytika.
        </p>
      </div>
    );
  }

  return (
    <div className="sheet flex min-h-0 flex-1 flex-col">
      <div className="sheet-head">
        <span className="sheet-title">Modely</span>
        <span className="text-[11px] text-sheet-faint">{models.length}</span>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        {models.map((model) => {
          const active = model.id === selectedId;
          const lastPeriod = model.period_totals[model.period_totals.length - 1] ?? null;
          return (
            <button
              key={model.id}
              type="button"
              onClick={() => onSelect(model.id)}
              aria-current={active ? 'true' : undefined}
              className={`flex w-full flex-col gap-1 border-b border-border-subtle px-3 py-2 text-left ${
                active ? 'bg-accent-bg' : 'hover:bg-surface-hover'
              }`}
            >
              <div className="flex items-baseline justify-between gap-2">
                <span className="font-mono text-sm font-medium text-text-primary">
                  {model.ticker}
                </span>
                <span className="text-[10px] text-text-muted">{day(model.document_date)}</span>
              </div>

              <span className="truncate text-[11px] text-text-secondary">{model.model_name}</span>

              <div className="flex items-center justify-between gap-2">
                <span className="text-[10px] text-text-muted">{model.source_name}</span>
                {lastPeriod && (
                  <span className="text-[10px] text-text-muted">
                    {lastPeriod.period_label} · {model.line_count}{' '}
                    {model.line_count === 1 ? 'řádek' : 'řádků'}
                  </span>
                )}
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
