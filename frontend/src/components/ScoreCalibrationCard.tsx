/**
 * ScoreCalibrationCard — jak dopadla skóre, která aplikace vydala.
 *
 * Aplikace rozdává skóre 0–10 a staví na nich semafor, velikost pozice
 * i doporučení. Do 23. 8. 2026 si nikdy nezapsala, kdy které skóre padlo,
 * takže na jedinou otázku, která tu metodu soudí — vydělávaly devítky víc
 * než pětky? — neexistovala odpověď. Tahle karta je ta odpověď, až dozraje.
 *
 * Většinu prvního roku bude prázdná, a to je správně. Medián ze tří vzorků
 * není zjištění, je to náhoda s desetinnou čárkou. O tom, jestli je vzorek
 * dost velký, rozhoduje backend (`sufficient`) — ne tahle komponenta, aby
 * číslo nešlo nakreslit tím, že se někdo prostě nezeptal.
 *
 * Proto se místo prázdna píše, kolik měření už běží a kdy dozraje první.
 * „Zatím nic" a „první odpověď přijde 22. září" jsou dvě různé zprávy pro
 * někoho, kdo čeká půl roku.
 *
 * Povrch je list (`bg-sheet`), ne panel: je to evidence, ne verdikt.
 */

import React, { useEffect, useState } from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';
import { apiClient } from '../api/client';
import { day, decimal, percent } from '../lib/format';
import Term from './ui/Term';
import type { CalibrationBand, ScoreCalibration } from '../api/client';

/** Horizonty, které vyhodnocovač měří. Musí odpovídat HORIZONS v backendu. */
const HORIZONS = [30, 90, 180, 365] as const;

/** Výsledek jednoho načtení, označkovaný tím, co si vyžádal. */
interface Fetched {
  horizon: number;
  attempt: number;
  data?: ScoreCalibration;
  error?: string;
}

interface Props {
  className?: string;
}

export const ScoreCalibrationCard: React.FC<Props> = ({ className = '' }) => {
  const [horizon, setHorizon] = useState<number>(90);
  const [attempt, setAttempt] = useState(0);
  const [fetched, setFetched] = useState<Fetched | null>(null);

  /* Stav „načítám" se neukládá, odvozuje se: uložený výsledek buď patří
     k tomu, co je právě vybrané, nebo se ještě čeká. Tím v efektu nezůstane
     žádné synchronní setState a zároveň nemůže dojet odpověď na horizont,
     který už nikoho nezajímá. */
  useEffect(() => {
    let alive = true;
    apiClient
      .getScoreCalibration(horizon)
      .then((data) => {
        if (alive) setFetched({ horizon, attempt, data });
      })
      .catch(() => {
        /* Rozlišeno od prázdna schválně: nenačtený přehled a přehled bez
           dat vypadají jinak, protože znamenají něco jiného. */
        if (alive) {
          setFetched({
            horizon,
            attempt,
            error: 'Přehled se nepodařilo načíst. Běží backend?',
          });
        }
      });
    return () => {
      alive = false;
    };
  }, [horizon, attempt]);

  const current =
    fetched && fetched.horizon === horizon && fetched.attempt === attempt
      ? fetched
      : null;

  return (
    <div className={`rounded-card border border-sheet-rule bg-sheet p-3 ${className}`}>
      <header className="mb-2.5 flex items-center gap-2">
        <h3 className="text-[13px] font-semibold text-sheet-text">
          Jak vycházejí naše skóre
        </h3>
        <div className="ml-auto flex items-center gap-1">
          {HORIZONS.map((days) => (
            <button
              key={days}
              onClick={() => setHorizon(days)}
              className={`rounded-button px-2 py-0.5 font-mono text-[11px] transition-colors ${
                days === horizon
                  ? 'bg-accent-bg text-accent'
                  : 'text-sheet-muted hover:bg-sheet-alt hover:text-sheet-text'
              }`}
              title={`Výsledek ${days} dní po vydání skóre`}
            >
              {days} d
            </button>
          ))}
          <button
            onClick={() => setAttempt((n) => n + 1)}
            className="ml-1 rounded-button p-1 text-sheet-muted transition-colors hover:bg-sheet-alt hover:text-sheet-text"
            title="Načíst znovu"
            aria-label="Načíst znovu"
          >
            <RefreshCw size={12} />
          </button>
        </div>
      </header>

      {current === null && (
        <p className="py-4 text-center text-[12px] text-sheet-muted">Načítám…</p>
      )}

      {current?.error && (
        <p className="flex items-center gap-2 rounded-input border border-warning-border bg-warning-bg px-2.5 py-2 text-[12px] text-warning">
          <AlertTriangle size={13} className="shrink-0" />
          {current.error}
        </p>
      )}

      {current?.data && <Report data={current.data} />}
    </div>
  );
};

const Report: React.FC<{ data: ScoreCalibration }> = ({ data }) => {
  const nothingAtAll = data.n_evaluated === 0 && data.n_pending === 0;

  if (nothingAtAll) {
    return (
      <p className="py-3 text-[12px] leading-relaxed text-sheet-muted">
        Deník skóre je zatím prázdný. Naplní se sám, jakmile aplikace vydá
        první hodnocení.
      </p>
    );
  }

  return (
    <>
      {!data.sufficient && <Waiting data={data} />}

      <table className="w-full text-[12px]">
        <thead>
          <tr className="border-b border-sheet-rule text-left text-[11px] text-sheet-muted">
            <th className="pb-1 font-normal">Skóre</th>
            <th className="pb-1 text-right font-normal">Změřeno</th>
            <th className="pb-1 text-right font-normal">
              <Term id="nadvynos">Nadvýnos</Term>
            </th>
            <th className="pb-1 text-right font-normal">Výnos</th>
            <th className="pb-1 text-right font-normal">Úspěšnost</th>
          </tr>
        </thead>
        <tbody>
          {data.bands.map((band) => (
            <BandRow key={band.label} band={band} />
          ))}
        </tbody>
      </table>

      <Footnote data={data} />
    </>
  );
};

const Waiting: React.FC<{ data: ScoreCalibration }> = ({ data }) => (
  <p className="mb-2.5 rounded-input border border-sheet-rule bg-sheet-alt px-2.5 py-2 text-[12px] leading-relaxed text-sheet-muted">
    {data.n_evaluated === 0 ? (
      <>
        Zatím není změřené žádné skóre — čeká jich{' '}
        <span className="font-mono text-sheet-text">{data.n_pending}</span>.
      </>
    ) : (
      <>
        Změřeno{' '}
        <span className="font-mono text-sheet-text">{data.n_evaluated}</span>,
        čeká <span className="font-mono text-sheet-text">{data.n_pending}</span>.
        Na medián je potřeba{' '}
        <span className="font-mono text-sheet-text">{data.min_sample}</span> v
        jednom pásmu.
      </>
    )}
    {data.first_result_expected && (
      <> První dozraje {day(data.first_result_expected)}.</>
    )}
  </p>
);

const BandRow: React.FC<{ band: CalibrationBand }> = ({ band }) => {
  const empty = <span className="text-sheet-faint">·</span>;

  return (
    <tr className="border-b border-sheet-faint last:border-0">
      <td className="py-1.5 font-mono text-sheet-text">{band.label}</td>
      <td className="py-1.5 text-right font-mono text-sheet-muted">
        {band.n_evaluated > 0 ? band.n_evaluated : empty}
        {band.n_pending > 0 && (
          <span className="text-sheet-faint"> / {band.n_pending}</span>
        )}
      </td>
      <td className="py-1.5 text-right font-mono">
        {band.median_excess_pct === null ? (
          empty
        ) : (
          <Signed value={band.median_excess_pct} />
        )}
      </td>
      <td className="py-1.5 text-right font-mono text-sheet-muted">
        {band.median_return_pct === null ? (
          empty
        ) : (
          percent(band.median_return_pct, { sign: true })
        )}
      </td>
      <td className="py-1.5 text-right font-mono text-sheet-muted">
        {band.share_positive_excess === null
          ? empty
          : `${decimal(band.share_positive_excess * 100, 0)} %`}
      </td>
    </tr>
  );
};

/** Nadvýnos je to hlavní číslo, tak je jediné barevné. */
const Signed: React.FC<{ value: number }> = ({ value }) => (
  <span className={value >= 0 ? 'text-positive' : 'text-negative'}>
    {percent(value, { sign: true })}
  </span>
);

const Footnote: React.FC<{ data: ScoreCalibration }> = ({ data }) => (
  <p className="mt-2 text-[11px] leading-relaxed text-sheet-muted">
    Výsledek {data.horizon_days} dní po vydání skóre, proti{' '}
    <Term id="sp500">S&amp;P 500</Term>.
    {data.n_unable > 0 && (
      <>
        {' '}Nezměřitelných:{' '}
        <span className="font-mono">{data.n_unable}</span> — chybí cena, nebo je
        titul stažený z burzy.
      </>
    )}
  </p>
);

export default ScoreCalibrationCard;
