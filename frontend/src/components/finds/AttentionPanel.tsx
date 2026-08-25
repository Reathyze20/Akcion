/**
 * Skóre pozornosti — kolik práce si nález zaslouží.
 *
 * Tři pravidla vykreslení, a všechna tři jsou obsahová, ne estetická:
 *
 *  1. **Body nikdy bez stropu.** `38 / 62` říká něco jiného než `38`. Samotné
 *     číslo se čte jako známka ze sta a rubrika se tím mění ve verdikt.
 *  2. **Nedosažitelná část pruhu se kreslí.** Šrafovaný konec je ta pravda,
 *     kvůli které skóre vzniklo: odděluje slabou firmu od neprozkoumané.
 *     Kdyby se jen nekreslila, vypadalo by prázdné místo jako propadlá známka.
 *  3. **Nikdy bez páky.** Skóre bez věty „co by tím nejvíc pohnulo" je známka;
 *     s ní je to úkol.
 *
 * Panel stojí POD větou nákupní brány a menším písmem. Brána odpovídá „smím to
 * koupit" a je kanonická; tohle odpovídá „mám tomu věnovat čas" a je pomocné.
 * Obrátit to pořadí by znamenalo postavit rubriku nad kánon.
 */

import type { FindAttention } from '../../api/client';
import {
  attentionLabel,
  attentionRatio,
  attentionTone,
  orderedPillars,
  pillarWidths,
} from '../../lib/finds';

interface Props {
  attention: FindAttention | null | undefined;
  /** Co udělat, když páka nabízí akci, na kterou tu tlačítko je. */
  onRefresh: () => void;
  onExplain: () => void;
  busy: boolean;
}

export default function AttentionPanel({ attention, onRefresh, onExplain, busy }: Props) {
  if (!attention) return null;

  const ratio = attentionRatio(attention.points, attention.ceiling);
  const label = attentionLabel(attention.points, attention.ceiling);
  const pillars = orderedPillars(attention);

  return (
    <div className="sheet p-3">
      <div className="flex items-baseline justify-between gap-3">
        <p className="eyebrow">Kolik si zaslouží pozornosti</p>
        {label && (
          <span className={`font-mono text-sm ${attentionTone(ratio)}`}>
            {label}
            {attention.ceiling > 0 && (
              <span className="ml-1 text-[10px] text-text-muted">
                z {Math.round(attention.total)} možných
              </span>
            )}
          </span>
        )}
      </div>

      <p className="mt-1 text-sm text-text-primary">{attention.verdict_cs}</p>

      {pillars.length > 0 && (
        <ul className="mt-3 space-y-2">
          {pillars.map((pillar) => {
            const w = pillarWidths(pillar, attention.total);
            return (
              <li key={pillar.key}>
                <div className="flex items-baseline justify-between gap-2">
                  <span className="text-xs text-text-secondary">{pillar.label_cs}</span>
                  <span className="font-mono text-[10px] text-text-muted">
                    {Math.round(pillar.points)}/{Math.round(pillar.ceiling)}
                  </span>
                </div>

                <div
                  className="mt-1 flex h-1.5 w-full overflow-hidden rounded-full bg-surface-active"
                  role="img"
                  aria-label={`${pillar.label_cs}: ${Math.round(pillar.points)} z ${Math.round(
                    pillar.ceiling,
                  )} dosažitelných, ${Math.round(pillar.max_points)} celkem`}
                >
                  <span
                    className="bg-accent"
                    style={{ width: `${w.earned}%` }}
                    aria-hidden
                  />
                  <span
                    className="bg-border-subtle"
                    style={{ width: `${w.open}%` }}
                    aria-hidden
                  />
                  {/* Nedosažitelné: šrafa, ne prázdno. Prázdno by se četlo
                      jako propadlá známka místo jako chybějící vstup. */}
                  <span
                    className="bg-[repeating-linear-gradient(45deg,transparent,transparent_2px,currentColor_2px,currentColor_3px)] text-text-muted/40"
                    style={{ width: `${w.unreachable}%` }}
                    aria-hidden
                  />
                </div>

                <p className="mt-0.5 text-[11px] text-text-muted">{pillar.reason_cs}</p>
                {pillar.missing_cs && (
                  <p className="text-[11px] text-warning">{pillar.missing_cs}</p>
                )}
              </li>
            );
          })}
        </ul>
      )}

      {attention.if_cylinders_cs && (
        <p className="mt-3 border-t border-border-subtle pt-2 text-xs text-text-secondary">
          {attention.if_cylinders_cs}
        </p>
      )}

      {attention.lever_cs && (
        <div className="mt-3 flex items-start gap-2 border-t border-border-subtle pt-2">
          <span className="eyebrow shrink-0 pt-0.5">Nejvíc by pohnulo</span>
          <p className="text-xs text-text-secondary">
            {attention.lever_cs}
            {attention.lever_action === 'DOPLNIT_DATA' && (
              <button
                type="button"
                className="ml-2 text-accent underline underline-offset-2"
                onClick={onRefresh}
                disabled={busy}
              >
                Dotáhnout data
              </button>
            )}
            {attention.lever_action === 'VYSVETLIT' && (
              <button
                type="button"
                className="ml-2 text-accent underline underline-offset-2"
                onClick={onExplain}
                disabled={busy}
              >
                Nechat vysvětlit
              </button>
            )}
            {/* POTVRDIT_VALCE tlačítko záměrně nemá: potvrzení válců je zápis
                do nákupní brány a patří do Portfolia, ne do pískoviště
                Nálezů. Věta říká, co udělat; udělat se to musí tam. */}
          </p>
        </div>
      )}
    </div>
  );
}
