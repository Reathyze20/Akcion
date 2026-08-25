/**
 * Co mluví pro a co proti — a jak si to příště ověřím sám.
 *
 * Každý bod nese čipy s fakty, o která se opírá. Není to ozdoba: bod bez
 * ověřené citace backend neuloží, a čip je jediný způsob, jak si to majitel
 * může na obrazovce zkontrolovat, aniž by nám musel věřit.
 *
 * Když se nějaký bod zahodil, řekne se to nahlas. Tiché zahazování je způsob,
 * jak pojistka přestane být vidět — a nikdo si nevšimne, že model začal
 * vymýšlet.
 *
 * Totéž platí o citaci, kterou se ve spisu nepodařilo dohledat. Dřív se mlčky
 * vynechala, a když se stůl rozešel se spisem, ke kterému bylo vysvětlení
 * napsané, zmizely čtyři z osmi čipů a nikdo se to nedozvěděl. Chybějící
 * doklad je teď vidět — je to horší zpráva než žádný doklad, protože znamená,
 * že se rozešly dvě verze spisu.
 *
 * Prázdná strana se nevycpává. „Nic pro to nemluví" je poctivá odpověď a musí
 * být napsaná jako věta, ne jako prázdné místo.
 */

import { Sparkles } from 'lucide-react';

import type { FindAssessment, FindDossier, FindPoint } from '../../api/client';
import { citations, directionTone, splitSides, weightLabel } from '../../lib/finds';

interface Props {
  assessment: FindAssessment | undefined;
  dossier: FindDossier;
  note: string;
  busy: boolean;
  onExplain: () => void;
}

export default function VerdictColumns({ assessment, dossier, note, busy, onExplain }: Props) {
  const explanation = assessment?.explanation ?? null;

  if (!explanation) {
    return (
      <div className="sheet p-4">
        <p className="eyebrow mb-2">Vysvětlení</p>
        <p className="mb-3 max-w-2xl text-xs text-text-secondary">
          Aplikace projde podklady výš a napíše, co mluví pro a co proti — ke
          každému bodu pravidlo z metodiky a větu, jak si ten údaj příště
          ověříš sám.
        </p>
        <button
          type="button"
          className="btn-primary flex items-center gap-2"
          onClick={onExplain}
          disabled={busy}
        >
          <Sparkles className={`h-3.5 w-3.5 ${busy ? 'animate-pulse' : ''}`} aria-hidden />
          {busy ? 'Píšu vysvětlení…' : 'Nechat vysvětlit'}
        </button>
        <p className="mt-1.5 text-[11px] text-text-muted">
          Jediné placené volání v Nálezech. Jedno kliknutí, jedna odpověď.
        </p>
      </div>
    );
  }

  const { pro, proti } = splitSides(explanation.points);
  const dropped = assessment?.points_dropped ?? 0;

  return (
    <div className="sheet p-4">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <p className="eyebrow">Vysvětlení</p>
          <p className="mt-1 max-w-3xl text-sm text-text-primary">
            {explanation.one_line_cs}
          </p>
        </div>
        <button
          type="button"
          className="btn-ghost shrink-0 text-xs"
          onClick={onExplain}
          disabled={busy}
        >
          {busy ? 'Píšu…' : 'Znovu'}
        </button>
      </div>

      {dropped > 0 && (
        <p className="mb-3 rounded-sm bg-warning-bg px-2 py-1.5 text-xs text-warning">
          {dropped === 1
            ? 'Jeden bod se zahodil, protože se opíral o fakt, který v podkladech není.'
            : `${dropped} body se zahodily, protože se opíraly o fakta, která v podkladech nejsou.`}
        </p>
      )}

      <div className="grid gap-4 md:grid-cols-2">
        <Column
          title="Co mluví pro"
          points={pro}
          dossier={dossier}
          empty="Zatím nic, co by mluvilo pro. To není verdikt — je to stav podkladů."
        />
        <Column
          title="Co mluví proti"
          points={proti}
          dossier={dossier}
          empty="Zatím nic, co by mluvilo proti. To není doporučení — je to stav podkladů."
        />
      </div>

      {/* Tvoje úvaha — kvůli tomuhle to celé je: majitel vysloví domněnku
          a vidí, kde se trefil. */}
      <div className="mt-4 border-t border-border-subtle pt-3">
        <p className="eyebrow mb-1.5">Tvoje úvaha</p>
        <p className="mb-2 text-xs italic text-text-muted">„{note}"</p>
        <div className="flex items-start gap-2">
          <span
            className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${
              explanation.own_reason_verdict === 'DRZI'
                ? 'bg-positive'
                : explanation.own_reason_verdict === 'NEDRZI'
                  ? 'bg-negative'
                  : 'bg-text-muted'
            }`}
            aria-hidden
          />
          <p className="text-sm text-text-secondary">{explanation.own_reason_cs}</p>
        </div>
      </div>

      {explanation.lesson_cs && (
        <div className="mt-3 border-t border-border-subtle pt-3">
          <p className="eyebrow mb-1.5">Co si z toho odnést</p>
          <p className="text-sm text-text-secondary">{explanation.lesson_cs}</p>
        </div>
      )}
    </div>
  );
}

/**
 * Čipy s doklady. Nedohledané se ukazují, ne zahazují.
 *
 * Čip odkazující do prázdna vypadá jako doklad — proto se nedohledané id
 * nekreslí jako čip, ale jako pojmenovaná chyba. Když tohle vidíš, rozešel se
 * spis na obrazovce se spisem, ke kterému model psal, a body pod ním se nedají
 * ověřit.
 */
function FactChips({ point, dossier }: { point: FindPoint; dossier: FindDossier }) {
  const { found, missing } = citations(point, dossier);
  return (
    <div className="mt-2 flex flex-wrap items-center gap-1">
      {found.map((fact) => (
        <span
          key={fact.id}
          title={fact.text_cs}
          className={`rounded-sm border border-border-subtle bg-surface-active px-1.5 py-0.5 font-mono text-[10px] ${directionTone(
            fact.direction,
          )}`}
        >
          {fact.id}
        </span>
      ))}
      {missing.length > 0 && (
        <span
          className="rounded-sm border border-negative/40 bg-negative-bg px-1.5 py-0.5 text-[10px] text-negative"
          title={`Vysvětlení se opírá o ${missing.join(', ')}, ale ve spisu na obrazovce to není. Ten bod si nejde ověřit.`}
        >
          {missing.length === 1
            ? `doklad ${missing[0]} v tomhle spisu není`
            : `${missing.length} dokladů v tomhle spisu není`}
        </span>
      )}
    </div>
  );
}

function Column({
  title,
  points,
  dossier,
  empty,
}: {
  title: string;
  points: FindPoint[];
  dossier: FindDossier;
  empty: string;
}) {
  return (
    <div>
      <p className="eyebrow mb-2">{title}</p>
      {points.length === 0 ? (
        <p className="text-xs text-text-muted">{empty}</p>
      ) : (
        <ul className="space-y-3">
          {points.map((point, index) => (
            <li key={`${point.headline_cs}-${index}`} className="panel-inset p-2.5">
              <div className="flex items-baseline justify-between gap-2">
                <p className="text-sm font-medium text-text-primary">{point.headline_cs}</p>
                {weightLabel(point.weight) && (
                  <span className="shrink-0 text-[10px] text-text-muted">
                    {weightLabel(point.weight)}
                  </span>
                )}
              </div>

              <p className="mt-1 text-xs text-text-secondary">{point.body_cs}</p>

              {point.canon_text_cs && (
                <p className="mt-1.5 text-[11px] text-text-muted">
                  Metodika {point.canon_ref}: {point.canon_text_cs}
                </p>
              )}

              <p className="mt-1.5 text-[11px] text-text-secondary">
                <span className="text-text-muted">Jak si to ověřím sám: </span>
                {point.check_yourself_cs}
              </p>

              <FactChips point={point} dossier={dossier} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
