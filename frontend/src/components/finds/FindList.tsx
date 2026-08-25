/**
 * Seznam nálezů. Jediná věc na téhle obrazovce, která scrolluje.
 *
 * Řádek nese jen to, podle čeho se vybírá: symbol, pásmo a jednořádkové
 * shrnutí, když už vysvětlení existuje. Čísla, pro a proti a celý spis jsou
 * ve stole vpravo — vypisovat je i tady by znamenalo říct tutéž věc dvakrát.
 */


import type { Find } from '../../api/client';
import { bandName, bandTone } from '../../lib/format';
import { day } from '../../lib/format';

interface Props {
  finds: Find[];
  selectedId: number | null;
  onSelect: (id: number) => void;
}

export default function FindList({ finds, selectedId, onSelect }: Props) {
  if (finds.length === 0) {
    return (
      <div className="sheet flex-1 p-3">
        <p className="text-xs text-text-muted">
          Zatím žádný nález. Přidej první nahoře.
        </p>
      </div>
    );
  }

  return (
    <div className="sheet flex min-h-0 flex-1 flex-col">
      <div className="sheet-head">
        <span className="sheet-title">Nálezy</span>
        <span className="text-[11px] text-sheet-faint">{finds.length}</span>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        {finds.map((find) => {
          const active = find.id === selectedId;
          const tone = bandTone(find.last_band);
          return (
            <button
              key={find.id}
              type="button"
              onClick={() => onSelect(find.id)}
              aria-current={active ? 'true' : undefined}
              className={`flex w-full flex-col gap-1 border-b border-border-subtle px-3 py-2 text-left ${
                active ? 'bg-accent-bg' : 'hover:bg-surface-hover'
              }`}
            >
              <div className="flex items-baseline justify-between gap-2">
                <span className="font-mono text-sm font-medium text-text-primary">
                  {find.symbol}
                </span>
                <span className="text-[10px] text-text-muted">{day(find.found_at)}</span>
              </div>

              {find.company_name && (
                <span className="truncate text-[11px] text-text-secondary">
                  {find.company_name}
                </span>
              )}

              <div className="flex items-center gap-1.5">
                <span className={`h-1.5 w-1.5 rounded-full ${tone.marker}`} aria-hidden />
                <span className={`text-[10px] ${tone.text}`}>
                  {find.last_band ? bandName(find.last_band) : 'bez posudku'}
                </span>
              </div>

              {find.last_one_line_cs && (
                <span className="line-clamp-2 text-[11px] text-text-muted">
                  {find.last_one_line_cs}
                </span>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}
