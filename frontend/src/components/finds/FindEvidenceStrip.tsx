/**
 * Podklady v odrážkách — jedna otevřená, ostatní zavřené.
 *
 * Tady a jen tady žijí všechna fakta spisu. Body ve vysvětlení na ně odkazují
 * čipem s id; kdyby se vypisovala i tam, řekla by se tatáž věta dvakrát a
 * majitel si na to výslovně stěžoval.
 *
 * Struktura je opsaná z `shell/ContextPanel.tsx`: zavřený pruh je nízký a je
 * z něj vidět, co tam je; otevřená odrážka scrolluje sama v sobě, takže se
 * stránka nikdy neprotáhne.
 */

import { useState } from 'react';
import { ChevronDown } from 'lucide-react';

import type { FindDossier } from '../../api/client';
import { day } from '../../lib/format';
import { directionTone, factsByLayer } from '../../lib/finds';

interface Props {
  dossier: FindDossier;
}

export default function FindEvidenceStrip({ dossier }: Props) {
  const groups = factsByLayer(dossier);
  const [open, setOpen] = useState<string | null>(null);

  if (groups.length === 0) {
    return (
      <div className="sheet p-3">
        <p className="eyebrow mb-1">Podklady</p>
        <p className="text-xs text-text-muted">
          Zatím žádná fakta. Všechno, co o firmě víme, je v „Co nevíme" —
          a to je taky odpověď.
        </p>
      </div>
    );
  }

  const active = groups.find((g) => g.layer === open) ?? null;

  return (
    <div className="sheet">
      <div className="flex flex-wrap items-center gap-1 border-b border-border-subtle px-2 py-1.5">
        <span className="eyebrow mr-2">Podklady</span>
        {groups.map((group) => {
          const isOpen = group.layer === open;
          return (
            <button
              key={group.layer}
              type="button"
              onClick={() => setOpen(isOpen ? null : group.layer)}
              aria-expanded={isOpen}
              className={`flex items-center gap-1 rounded-sm px-2 py-1 text-[11px] ${
                isOpen
                  ? 'bg-accent-bg text-accent'
                  : 'text-text-secondary hover:bg-surface-hover'
              }`}
            >
              {group.label}
              <span className="text-text-muted">{group.facts.length}</span>
              <ChevronDown
                className={`h-3 w-3 ${isOpen ? 'rotate-180' : ''}`}
                aria-hidden
              />
            </button>
          );
        })}
      </div>

      {active && (
        <div className="max-h-64 overflow-y-auto p-3">
          <ul className="space-y-2">
            {active.facts.map((fact) => (
              <li key={fact.id} className="flex items-start gap-2">
                <span className="mt-0.5 shrink-0 font-mono text-[10px] text-text-muted">
                  {fact.id}
                </span>
                <div className="min-w-0">
                  <p className={`text-xs ${directionTone(fact.direction)}`}>
                    {fact.text_cs}
                  </p>
                  <p className="mt-0.5 text-[10px] text-text-muted">
                    {fact.source}
                    {fact.as_of ? ` · ${day(fact.as_of)}` : ''}
                  </p>
                  {fact.quote && (
                    <p className="mt-1 border-l-2 border-border-subtle pl-2 text-[11px] italic text-text-muted">
                      „{fact.quote}"
                    </p>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
