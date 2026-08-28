/**
 * Seznam nálezů. Jediná věc na téhle obrazovce, která scrolluje.
 *
 * Řádek nese jen to, podle čeho se vybírá: symbol, skóre pozornosti a
 * jednořádkové shrnutí, když už vysvětlení existuje. Čísla, pro a proti a celý
 * spis jsou ve stole vpravo — vypisovat je i tady by znamenalo říct tutéž věc
 * dvakrát.
 *
 * **Řadí se podle podílu ze stropu, ne podle data.** Pásmo tu dřív bylo hlavní
 * značka a bylo k ničemu: u vlastního nálezu vyjde `MIMO METODIKU` skoro
 * vždycky, protože pásmo se počítá z Gomesových čar a vlastní nález je
 * z definice firma, kterou Gomes nepokrývá. Dvanáct řádků se stejnou značkou
 * není podle čeho seřadit — a přesně kvůli tomu skóre vzniklo.
 *
 * Skóre se píše VŽDY jako dvojice `body / strop`. Samotné body by se četly
 * jako známka ze sta a neprozkoumaná firma by vypadala jako špatná.
 */


import type { Find } from '../../api/client';
import { day } from '../../lib/format';
import { attentionLabel, attentionRatio, attentionTone, sortByAttention } from '../../lib/finds';

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
        {sortByAttention(finds).map((find) => {
          const active = find.id === selectedId;
          const ratio = attentionRatio(find.attention_points, find.attention_ceiling);
          const label = attentionLabel(find.attention_points, find.attention_ceiling);
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
                {label ? (
                  <>
                    <span className={`font-mono text-[11px] ${attentionTone(ratio)}`}>
                      {label}
                    </span>
                    {find.attention_verdict_cs && (
                      <span className="truncate text-[10px] text-text-muted">
                        {find.attention_verdict_cs}
                      </span>
                    )}
                  </>
                ) : (
                  <span className="text-[10px] text-text-muted">bez skóre</span>
                )}
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
