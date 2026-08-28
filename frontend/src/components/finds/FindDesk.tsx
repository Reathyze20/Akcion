/**
 * Stůl jednoho nálezu.
 *
 * Pevné pořadí shora dolů, a to pořadí je celé sdělení:
 *
 *   1. hlavička — firma a kurz
 *   2. co říká metodika (`bg-frame`, tmavý pruh — tady mluví aplikace):
 *      věta nákupní brány je NADPIS, pásmo je podpora pod ní
 *   3. kolik si zaslouží pozornosti — POD bránou a menším písmem, protože
 *      odpovídá na jinou otázku („mám tomu věnovat čas", ne „smím koupit")
 *   4. co nevíme — vypsané doslova, deterministicky, NAD textem od modelu
 *   5. vysvětlení — dva sloupce, nebo tlačítko s cenovkou
 *   6. podklady — všechna fakta, v odrážkách, jedna otevřená
 *   7. historie posudků
 *
 * Proč brána nad pásmem: pásmo hlásí NÁKUP už při skóre o půl bodu nad
 * zaslouženým, kdežto brána propustí i těsnější rozdíl — a hlavně se zastaví
 * na semaforu nebo na chybějících válcích. Ty dvě věty se můžou lišit a
 * rozhoduje ta, která umí říct proč ne.
 *
 * Nic z toho nescrolluje kromě otevřené odrážky a historie.
 *
 * **Spis na téhle obrazovce je zapsaný snímek, ne čerstvé sestavení.** Backend
 * ho posílá z posudku a `dossier_from_assessment_id` říká z kterého. Skládat
 * ho znovu při každém otevření vypadalo nevinně a nebylo: sestavení bez
 * `enrich()` nemá výkazy, vydá míň faktů a přečísluje jim id — takže čipy
 * s doklady pod body od AI ukazovaly na jiná fakta, než o která se bod
 * opíral. Datum spisu se proto píše do hlavičky; spis bez data se čte jako
 * dnešní.
 */

import { useCallback, useState } from 'react';
import { RefreshCw } from 'lucide-react';

import { apiClient } from '../../api/client';
import type { FindAssessment, FindDetail } from '../../api/client';
import { bandName, bandTone, decimal, price as fmtPrice, day } from '../../lib/format';
import Term from '../ui/Term';
import { conditionalCylinderSentence, evolution, priceChangePct, splitGaps } from '../../lib/finds';
import AttentionPanel from './AttentionPanel';
import FindEvidenceStrip from './FindEvidenceStrip';
import VerdictColumns from './VerdictColumns';

interface Props {
  detail: FindDetail;
  onChanged: (next: FindDetail) => void;
}

export default function FindDesk({ detail, onChanged }: Props) {
  const { find, dossier, assessments } = detail;
  const newest: FindAssessment | undefined = assessments[0];

  const [busy, setBusy] = useState<'refresh' | 'explain' | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setBusy('refresh');
    setError(null);
    try {
      onChanged(await apiClient.refreshFind(find.id));
    } catch (e) {
      const d = (e as { detail?: string })?.detail;
      setError(d ?? (e instanceof Error ? e.message : 'Data se nepodařilo dotáhnout'));
    } finally {
      setBusy(null);
    }
  }, [find.id, onChanged]);

  const explain = useCallback(async () => {
    setBusy('explain');
    setError(null);
    try {
      await apiClient.explainFind(find.id);
      onChanged(await apiClient.getFind(find.id));
    } catch (e) {
      const d = (e as { detail?: string })?.detail;
      setError(d ?? (e instanceof Error ? e.message : 'Vysvětlení se nepodařilo získat'));
    } finally {
      setBusy(null);
    }
  }, [find.id, onChanged]);

  const m = dossier.method;
  const tone = bandTone(m.band);
  const conditional = conditionalCylinderSentence(dossier);
  const history = evolution(assessments);
  const gaps = splitGaps(dossier);

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3">
      {/* 1. hlavička */}
      <div className="flex items-baseline justify-between gap-3">
        <div className="flex items-baseline gap-2">
          <h2 className="font-display text-lg text-text-primary [font-stretch:78%]">
            {find.symbol}
          </h2>
          {find.company_name && (
            <span className="text-sm text-text-secondary">{find.company_name}</span>
          )}
        </div>
        <div className="flex items-center gap-3">
          {dossier.price != null && (
            <span className="font-mono text-sm text-text-primary">
              {fmtPrice(dossier.price, dossier.price_currency ?? undefined)}
            </span>
          )}
          {dossier.price_is_stale && (
            <span className="flex items-center gap-1 text-[11px] text-text-muted">
              <span className="h-1.5 w-1.5 rounded-full bg-warning" aria-hidden />
              kurz není čerstvý
            </span>
          )}
          {/* Spis je snímek, ne dnešek. Bez data by se četl jako dnešní —
              a přesně to tvrzení bylo dřív nepravdivé. */}
          <span className="text-[11px] text-text-muted">
            spis z {day(dossier.as_of)}
          </span>
          <button
            type="button"
            className="btn-ghost flex items-center gap-1.5 text-xs"
            onClick={() => void refresh()}
            disabled={busy !== null}
          >
            <RefreshCw
              className={`h-3.5 w-3.5 ${busy === 'refresh' ? 'animate-spin' : ''}`}
              aria-hidden
            />
            Dotáhnout data
          </button>
        </div>
      </div>

      {/* 2. co říká metodika — tady mluví aplikace */}
      <div className="rounded-card bg-frame p-4">
        <p className="eyebrow text-frame-muted">Co říká metodika</p>

        {/* `text-frame-text`, not `text-inverse` — `text-inverse` flips with
            the PAGE's theme (white on light, near-black on dark), but this
            box (`bg-frame`) stays dark in both themes. In dark mode the two
            near-black tones sat 6-8 RGB steps apart — the gate sentence, the
            single most important line on the screen, was functionally blank. */}
        <p className="mt-1.5 text-sm text-frame-text">{m.gate_reason_cs}</p>

        <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-frame-muted">
          <span className="flex items-center gap-1.5">
            <Term id="pasmo">Pásmo</Term>
            <span className={`rounded-sm border px-1.5 py-0.5 ${tone.pill}`}>
              {bandName(m.band)}
            </span>
          </span>

          {m.rr_score != null && (
            <span>
              <Term id="rr">R/R</Term> {decimal(m.rr_score, 2)}
              {m.deserved != null && (
                <>
                  {' '}proti <Term id="zaslouzeneSkore">zaslouženému</Term>{' '}
                  {decimal(m.deserved, 1)}
                </>
              )}
            </span>
          )}

          <span>
            <Term id="valce">Válce</Term>{' '}
            {m.cylinders_confirmed != null
              ? `${m.cylinders_confirmed}/10 potvrzeno`
              : 'nikdo nepotvrdil'}
          </span>

          {m.buy_below != null && (
            <span>kupovat pod {decimal(m.buy_below, 2)} {m.line_currency ?? ''}</span>
          )}
          {m.sell_above != null && (
            <span>prodávat nad {decimal(m.sell_above, 2)} {m.line_currency ?? ''}</span>
          )}
        </div>

        {conditional && (
          <p className="mt-2 border-t border-frame-muted/20 pt-2 text-xs text-frame-muted">
            {conditional}
          </p>
        )}
      </div>

      {error && (
        <p className="rounded-sm bg-negative-bg px-3 py-2 text-xs text-negative">{error}</p>
      )}

      <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto pr-0.5">
        {/* 3. kolik si zaslouží pozornosti — pod bránou, menším písmem */}
        <AttentionPanel
          attention={newest?.attention}
          onRefresh={() => void refresh()}
          onExplain={() => void explain()}
          busy={busy !== null}
        />

        {/* 4. co nevíme — deterministické, nad textem od modelu.
            Rozdělené na dva seznamy: jeden seznam třinácti položek se čte jako
            třináct selhání, přitom většina z nich je „takhle to prostě je".

            Vedle sebe, ne pod sebou, když existují oba — stejný vzor jako pro
            a proti níž. Stůl je široký (desk, ne úzký sloupec) a dva krátké
            seznamy pod sebou zabíraly dvojnásobek výšky, který nikdo nečetl
            zprava doprázdna. */}
        {(gaps.fixable.length > 0 || gaps.permanent.length > 0) && (
          <div className="sheet p-3">
            <div
              className={
                gaps.fixable.length > 0 && gaps.permanent.length > 0
                  ? 'grid gap-x-6 gap-y-3 md:grid-cols-2'
                  : undefined
              }
            >
              {gaps.fixable.length > 0 && (
                <div>
                  <p className="eyebrow mb-2">Co chybí a jde doplnit</p>
                  <ul className="space-y-1.5">
                    {gaps.fixable.map((gap) => (
                      <li
                        key={gap.id}
                        className="flex items-start gap-2 text-xs text-text-secondary"
                      >
                        <span
                          className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-warning"
                          aria-hidden
                        />
                        <span>
                          {gap.text_cs}
                          <button
                            type="button"
                            className="ml-2 text-accent underline underline-offset-2"
                            onClick={() => void refresh()}
                            disabled={busy !== null}
                          >
                            {gap.fixable_cs}
                          </button>
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {gaps.permanent.length > 0 && (
                <div>
                  <p className="eyebrow mb-2">Co se nedozvíme</p>
                  <ul className="space-y-1.5">
                    {gaps.permanent.map((gap) => (
                      <li
                        key={gap.id}
                        className="flex items-start gap-2 text-xs text-text-secondary"
                      >
                        <span
                          className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-text-muted"
                          aria-hidden
                        />
                        <span>{gap.text_cs}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </div>
        )}

        {/* 5. vysvětlení */}
        <VerdictColumns
          assessment={newest}
          dossier={dossier}
          note={find.note}
          busy={busy === 'explain'}
          onExplain={() => void explain()}
        />

        {/* 6. podklady */}
        <FindEvidenceStrip dossier={dossier} />

        {/* 7. historie */}
        {assessments.length > 1 && (
          <div className="sheet p-3">
            <p className="eyebrow mb-2">Historie posudků</p>
            <p className="mb-2 text-xs text-text-secondary">{history.summary_cs}</p>
            <table className="table-pro w-full">
              <thead>
                <tr>
                  <th className="text-left">Kdy</th>
                  <th className="text-left">Pásmo</th>
                  <th className="text-right">Kurz tehdy</th>
                  <th className="text-right">Od té doby</th>
                </tr>
              </thead>
              <tbody>
                {assessments.map((a) => {
                  const moved = priceChangePct(a, dossier.price, dossier.price_currency);
                  return (
                    <tr key={a.id}>
                      <td>{day(a.assessed_at)}</td>
                      <td className={bandTone(a.band).text}>{bandName(a.band)}</td>
                      <td className="text-right font-mono">
                        {a.price_at_assessment != null
                          ? fmtPrice(a.price_at_assessment, a.price_currency ?? undefined)
                          : ''}
                      </td>
                      <td
                        className={`text-right font-mono ${
                          moved == null
                            ? 'text-text-muted'
                            : moved >= 0
                              ? 'text-positive'
                              : 'text-negative'
                        }`}
                      >
                        {moved == null ? '' : `${moved >= 0 ? '+' : ''}${decimal(moved, 1)} %`}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
