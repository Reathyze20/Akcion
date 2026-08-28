/**
 * PortfolioDiffCard — v čem se dvě portfolia liší.
 *
 * Odpovídá na jedinou otázku: co drží jeden a druhý ne. Dřív to viselo
 * jako pruh pod tabulkou portfolia, anglicky a s prázdnými jmény, protože
 * backend posílal `owner_with_position` a frontend četl `holder`. Panel se
 * navíc nikdy nezobrazil, dokud existovalo jediné portfolio, takže si té
 * rozbité smlouvy nikdo nevšiml.
 *
 * Dvě věci, na kterých tahle karta stojí:
 *
 *  1. **Rozdíl není doporučení.** Pozice bez konvikčního skóre se ukáže,
 *     protože „Tom drží DAIO 8,3 %, Míša ne" je pravda i bez hodnocení.
 *     Nesmí z ní ale vzniknout pokyn — takové řádky proto stojí zvlášť pod
 *     čarou a nikde u nich nestojí, že se má něco koupit.
 *
 *  2. **Prázdné portfolio není nález.** Když jeden z účtů nemá ani jednu
 *     pozici, je rozdílem celé portfolio toho druhého. Vysypat na to
 *     člověka devět „zjištění" znamená tvářit se, že aplikace něco našla.
 *     Píše se to proto rovnou jednou větou nahoře.
 *
 * Povrch je list (`bg-sheet`), ne panel: je to evidence, ne verdikt.
 */

import React, { useEffect, useState } from 'react';
import { AlertTriangle, RefreshCw, Users } from 'lucide-react';
import { apiClient } from '../api/client';
import { percent } from '../lib/format';
import type { FamilyAuditResponse, FamilyGap } from '../types';

interface Props {
  className?: string;
}

/** Výsledek jednoho načtení, označkovaný tím, co si ho vyžádalo. */
interface Fetched {
  attempt: number;
  audit?: FamilyAuditResponse;
  /** Vlastníci účtů a kdo z nich nemá ani jednu pozici. */
  owners?: string[];
  empty?: string[];
  error?: string;
}

export const PortfolioDiffCard: React.FC<Props> = ({ className = '' }) => {
  const [attempt, setAttempt] = useState(0);
  const [fetched, setFetched] = useState<Fetched | null>(null);

  /*
   * Načítají se dvě věci najednou: rozdíly a stav účtů. Bez toho druhého by
   * karta neuměla rozeznat „portfolia se liší v devíti pozicích" od
   * „druhý účet je zatím prázdný", což jsou úplně jiné zprávy.
   *
   * Stav „načítám" se neukládá, odvozuje se — stejně jako v ScoreCalibrationCard.
   * Uložený výsledek buď patří k aktuálnímu pokusu, nebo se ještě čeká. Tím
   * v efektu nezůstane synchronní setState a zároveň nemůže dojet odpověď,
   * o kterou už nikdo nestojí.
   */
  useEffect(() => {
    let alive = true;

    Promise.all([apiClient.getFamilyAudit(), apiClient.getPortfolios()])
      .then(([audit, portfolios]) => {
        if (!alive) return;
        setFetched({
          attempt,
          audit,
          owners: portfolios.map((p) => p.owner),
          empty: portfolios
            .filter((p) => (p.position_count ?? 0) === 0)
            .map((p) => p.owner),
        });
      })
      .catch((err: unknown) => {
        if (!alive) return;
        setFetched({
          attempt,
          error: err instanceof Error ? err.message : 'Rozdíly se nepodařilo načíst.',
        });
      });

    return () => {
      alive = false;
    };
  }, [attempt]);

  const loading = fetched?.attempt !== attempt;
  const error = fetched?.error ?? null;
  const owners = fetched?.owners ?? [];
  const empty = fetched?.empty ?? [];
  const gaps = fetched?.audit?.gaps ?? [];
  const doporuceni = gaps.filter((g) => g.priority !== 'UNKNOWN');
  const bezSkore = gaps.filter((g) => g.priority === 'UNKNOWN');

  return (
    <div className={`rounded-card border border-sheet-rule bg-sheet p-3 ${className}`}>
      <div className="mb-2 flex items-center gap-2">
        <Users size={14} className="shrink-0 text-sheet-muted" aria-hidden="true" />
        <h3 className="text-[13px] font-semibold text-sheet-text">Rozdíly portfolií</h3>
        {owners.length > 0 && (
          <span className="text-[11.5px] text-sheet-muted">{owners.join(' × ')}</span>
        )}
        <button
          onClick={() => setAttempt((a) => a + 1)}
          disabled={loading}
          className="ml-auto rounded-button p-1 text-sheet-muted transition-colors hover:bg-sheet-alt hover:text-sheet-text disabled:opacity-40"
          title="Načíst znovu"
          aria-label="Načíst znovu"
        >
          <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
        </button>
      </div>

      {loading && <p className="py-4 text-center text-[12px] text-sheet-muted">Porovnávám…</p>}

      {error && !loading && (
        <p className="flex items-center gap-2 rounded-input border border-negative/40 bg-negative/10 px-2.5 py-2 text-[12px] text-negative">
          <AlertTriangle size={13} className="shrink-0" aria-hidden="true" />
          {error}
        </p>
      )}

      {!loading && !error && (
        <>
          {/* Prázdný účet přebíjí všechno ostatní: dokud tam nic není,
              není co porovnávat a seznam níž jen vypisuje jedno portfolio. */}
          {empty.length > 0 && (
            <p className="mb-2.5 rounded-input border border-sheet-rule bg-sheet-alt px-2.5 py-2 text-[12px] leading-relaxed text-sheet-muted">
              {empty.join(' a ')}{' '}
              {empty.length > 1 ? 'nemají' : 'nemá'} zatím žádnou pozici, takže rozdílem
              je celé portfolio toho druhého. Až proběhne import, začne mít tenhle
              seznam smysl.
            </p>
          )}

          {gaps.length === 0 ? (
            <p className="py-3 text-center text-[12px] text-sheet-muted">
              {owners.length < 2
                ? 'Porovnávat jde až dvě portfolia. Zatím je tu jedno.'
                : 'Žádný rozdíl — oba účty drží totéž.'}
            </p>
          ) : (
            <>
              {doporuceni.length > 0 && (
                <>
                  <p className="eyebrow mb-1.5 text-sheet-muted">Stojí za dorovnání</p>
                  <ul className="mb-3 space-y-1">
                    {doporuceni.map((g) => (
                      <GapRow key={`${g.owner_with_position}-${g.ticker}`} gap={g} />
                    ))}
                  </ul>
                </>
              )}

              {bezSkore.length > 0 && (
                <>
                  <p className="eyebrow mb-1.5 text-sheet-muted">
                    Rozdíl, ale posoudit ho neumíme ({bezSkore.length})
                  </p>
                  <ul className="space-y-1">
                    {bezSkore.map((g) => (
                      <GapRow key={`${g.owner_with_position}-${g.ticker}`} gap={g} />
                    ))}
                  </ul>
                  <p className="mt-2 text-[11.5px] leading-relaxed text-sheet-faint">
                    Tyhle pozice nemají konvikční skóre, takže aplikace neumí říct,
                    jestli je má druhý účet dorovnat. Je to zjištěný rozdíl, ne pokyn.
                  </p>
                </>
              )}
            </>
          )}
        </>
      )}
    </div>
  );
};

/** Jeden řádek rozdílu. Vždycky říká čí, kolik a u koho chybí. */
const GapRow: React.FC<{ gap: FamilyGap }> = ({ gap }) => (
  <li className="flex items-baseline gap-2 rounded-input border border-sheet-rule bg-sheet-alt px-2.5 py-1.5">
    <span className="w-24 shrink-0 truncate font-mono text-[12.5px] text-sheet-text" title={gap.company_name ?? undefined}>
      {gap.ticker}
    </span>
    <span className="min-w-0 flex-1 text-[12px] text-sheet-muted">
      <span className="text-sheet-text">{gap.owner_with_position}</span> má{' '}
      <span className="font-mono tabular-nums">{percent(gap.owner_weight_pct)}</span>,{' '}
      <span className="text-sheet-text">{gap.missing_owner}</span> ne
    </span>
    <span className="shrink-0 font-mono text-[11px] text-sheet-faint">
      {gap.conviction_score != null ? `${gap.conviction_score}/10` : 'bez skóre'}
    </span>
  </li>
);

export default PortfolioDiffCard;
