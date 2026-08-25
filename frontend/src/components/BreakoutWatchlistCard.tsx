/**
 * BreakoutWatchlistCard — co si o našich jménech myslí druhý zdroj.
 *
 * Breakout Investors zveřejňují u každého jména dvě čísla: kolik členů ho
 * podepsalo a jaký růst od něj čekají. To druhé je jejich cílová cena řečená
 * jinak, a tahle karta ji dopočítává zpátky, aby šla položit vedle Gomesovy
 * červené čáry a porovnat.
 *
 * Karta nic nedoporučuje, a to je záměr, ne opomenutí. Kdyby se jejich
 * watchlist zapsal jako druhý názor do `stocks`, dvacet osm jmen by rázem
 * mělo souhlas dvou zdrojů a strop pozice by u nich vyskočil ze 7 % na 15 %
 * — na základě staženého seznamu, který nikdo nečetl. Čísla se ukazují vedle
 * sebe, rozhoduje se u nich pořád ručně.
 *
 * Naše jména jsou nahoře a v plné barvě, jejich zbytek pod čarou a potlačený.
 * Celá otázka zní „co říkají o tom, co držím", ne „co mají na seznamu".
 *
 * Chybějící číslo se nekreslí. Cíl bez kurzu neexistuje — ani jako nula, ani
 * jako ten včerejší — a prázdné místo je čitelnější než sloupec pomlček.
 */

import React, { useCallback, useEffect, useState } from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';
import { apiClient } from '../api/client';
import { day, percent, price } from '../lib/format';
import Term from './ui/Term';
import type {
  BreakoutChange,
  BreakoutEntry,
  BreakoutWatchlist,
} from '../api/client';

interface Props {
  className?: string;
}

/** Prázdné místo, ne pomlčka. Stejná konvence jako v ostatních listech. */
const EMPTY = <span className="text-sheet-faint">·</span>;

const RELATION_LABEL: Record<string, string> = {
  OWNED: 'držíme',
  WATCHED: 'sledujeme',
};

export const BreakoutWatchlistCard: React.FC<Props> = ({ className = '' }) => {
  const [data, setData] = useState<BreakoutWatchlist | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reading, setReading] = useState(false);

  useEffect(() => {
    let alive = true;
    apiClient
      .getBreakoutWatchlist()
      .then((result) => alive && setData(result))
      .catch(
        () =>
          alive &&
          setError('Watchlist se nepodařilo načíst. Běží backend?'),
      );
    return () => {
      alive = false;
    };
  }, []);

  /* Tlačítko čte zdroj mimo denní interval. Je to stisk člověka, ne smyčka —
     proto smí obejít limit, který drží automatické čtení na jednom za den. */
  const readNow = useCallback(async () => {
    setReading(true);
    setError(null);
    try {
      setData(await apiClient.refreshBreakoutWatchlist());
    } catch {
      setError('Zdroj neodpověděl. Čísla níž jsou z minulého čtení.');
    } finally {
      setReading(false);
    }
  }, []);

  const ours = (data?.entries ?? []).filter((e) => e.relation !== 'THEIRS');
  const theirs = (data?.entries ?? []).filter((e) => e.relation === 'THEIRS');

  return (
    <div className={`rounded-card border border-sheet-rule bg-sheet p-3 ${className}`}>
      <header className="mb-2.5 flex items-center gap-2">
        <h3 className="text-[13px] font-semibold text-sheet-text">
          <Term id="breakoutInvestors">Breakout Investors</Term>
        </h3>
        {data && !data.never_read && (
          <span className="text-[11px] text-sheet-muted">
            {data.ours_total} z {data.entries_total} jmen je našich
          </span>
        )}
        <button
          onClick={readNow}
          disabled={reading}
          className="ml-auto rounded-button p-1 text-sheet-muted transition-colors hover:bg-sheet-alt hover:text-sheet-text disabled:opacity-40"
          title="Přečíst zdroj teď"
          aria-label="Přečíst zdroj teď"
        >
          <RefreshCw size={12} className={reading ? 'animate-spin' : ''} />
        </button>
      </header>

      {!data && !error && (
        <p className="py-4 text-center text-[12px] text-sheet-muted">Načítám…</p>
      )}

      {error && (
        <p className="mb-2.5 flex items-center gap-2 rounded-input border border-warning-border bg-warning-bg px-2.5 py-2 text-[12px] text-warning">
          <AlertTriangle size={13} className="shrink-0" />
          {error}
        </p>
      )}

      {data && <Freshness data={data} />}

      {data && !data.never_read && (
        <>
          {ours.length > 0 ? (
            <EntryTable entries={ours} />
          ) : (
            <p className="py-3 text-[12px] leading-relaxed text-sheet-muted">
              Z jejich {data.entries_total} jmen nedržíme ani nesledujeme
              žádné. Seznam níž je jen jejich.
            </p>
          )}

          {theirs.length > 0 && <Rest entries={theirs} />}
          {data.changes.length > 0 && <Changes changes={data.changes} />}
        </>
      )}
    </div>
  );
};

/**
 * Kdy se zdroj naposled povedlo přečíst.
 *
 * Watchlist, který se dva týdny nezměnil, a watchlist, který se dva týdny
 * nepodařilo přečíst, vypadají na obrazovce stejně. Rozdíl musí být napsaný.
 */
const Freshness: React.FC<{ data: BreakoutWatchlist }> = ({ data }) => {
  if (data.never_read) {
    return (
      <p className="rounded-input border border-sheet-rule bg-sheet-alt px-2.5 py-2 text-[12px] leading-relaxed text-sheet-muted">
        Zdroj zatím nebyl přečtený, takže prázdno neznamená prázdný seznam.
        Tlačítkem nahoře se načte poprvé; dál se čte sám jednou denně.
        {data.last_error && (
          <>
            {' '}Poslední pokus skončil chybou: {data.last_error}
          </>
        )}
      </p>
    );
  }

  if (!data.stale && !data.last_error) return null;

  return (
    <p className="mb-2.5 flex items-start gap-2 rounded-input border border-warning-border bg-warning-bg px-2.5 py-2 text-[12px] leading-relaxed text-warning">
      <AlertTriangle size={13} className="mt-0.5 shrink-0" />
      <span>
        {data.last_success_at
          ? `Naposledy přečteno ${day(data.last_success_at)}. Čísla níž jsou z toho dne.`
          : 'Zdroj se dosud nepodařilo přečíst.'}
        {data.last_error && <> Poslední pokus: {data.last_error}</>}
      </span>
    </p>
  );
};

const EntryTable: React.FC<{ entries: BreakoutEntry[]; muted?: boolean }> = ({
  entries,
  muted = false,
}) => (
  <table className="w-full text-[12px]">
    <thead>
      <tr className="border-b border-sheet-rule text-left text-[11px] text-sheet-muted">
        <th className="pb-1 font-normal">Ticker</th>
        <th className="pb-1 text-right font-normal">
          <Term id="podpisy">Podpisy</Term>
        </th>
        <th className="pb-1 text-right font-normal">Jejich cíl</th>
        <th className="pb-1 text-right font-normal">
          <Term id="ocekavanyRust">Růst</Term>
        </th>
        <th className="pb-1 pl-2 font-normal">Proti Gomesovi</th>
      </tr>
    </thead>
    <tbody>
      {entries.map((entry) => (
        <Row key={entry.symbol} entry={entry} muted={muted} />
      ))}
    </tbody>
  </table>
);

const Row: React.FC<{ entry: BreakoutEntry; muted: boolean }> = ({ entry, muted }) => {
  const tone = muted ? 'text-sheet-muted' : 'text-sheet-text';

  return (
    <tr className="border-b border-sheet-faint last:border-0">
      <td className={`py-1.5 font-mono ${tone}`}>
        {entry.symbol}
        {RELATION_LABEL[entry.relation] && (
          <span className="ml-1.5 font-sans text-[10px] uppercase tracking-wide text-sheet-faint">
            {RELATION_LABEL[entry.relation]}
          </span>
        )}
      </td>
      <td className={`py-1.5 text-right font-mono ${tone}`}>{entry.endorsements}</td>
      <td className={`py-1.5 text-right font-mono ${tone}`}>
        {entry.implied_target == null ? EMPTY : price(entry.implied_target, 'USD')}
      </td>
      <td className="py-1.5 text-right font-mono text-sheet-muted">
        {entry.upside_pct == null
          ? EMPTY
          : percent(entry.upside_pct, { sign: true, digits: 0 })}
      </td>
      <td className="py-1.5 pl-2">
        <VsGomes entry={entry} />
      </td>
    </tr>
  );
};

/**
 * Kam jejich cíl padne v Gomesově pásmu.
 *
 * Popis, ne verdikt. „Nad červenou" znamená, že čekají cenu, kterou Gomes
 * považuje za nadhodnocenou — to je zajímavý nesoulad dvou čísel a není to
 * pokyn ani k jednomu.
 */
const VsGomes: React.FC<{ entry: BreakoutEntry }> = ({ entry }) => {
  if (!entry.vs_gomes) {
    return (
      <span className="text-[11px] text-sheet-faint">
        {entry.implied_target == null ? '' : 'čáry nezadané'}
      </span>
    );
  }

  if (entry.vs_gomes === 'ABOVE_RED') {
    return (
      <span className="flex items-center gap-1.5 text-[11px] text-warning">
        <span className="h-[6px] w-[6px] shrink-0 rounded-full bg-warning" aria-hidden />
        nad <Term id="cervenaLinka">červenou</Term>
        {entry.gomes_red_line != null && (
          <span className="font-mono text-sheet-faint">
            {price(entry.gomes_red_line, 'USD')}
          </span>
        )}
      </span>
    );
  }

  if (entry.vs_gomes === 'BELOW_GREEN') {
    return (
      <span className="flex items-center gap-1.5 text-[11px] text-negative">
        <span className="h-[6px] w-[6px] shrink-0 rounded-full bg-negative" aria-hidden />
        pod <Term id="zelenaLinka">zelenou</Term>
      </span>
    );
  }

  return <span className="text-[11px] text-sheet-muted">v pásmu</span>;
};

/** Jejich zbytek. Sbalený, protože o něm se nerozhoduje. */
const Rest: React.FC<{ entries: BreakoutEntry[] }> = ({ entries }) => {
  const [open, setOpen] = useState(false);

  return (
    <div className="mt-3 border-t border-sheet-rule pt-2">
      <button
        onClick={() => setOpen((v) => !v)}
        className="text-[11px] text-sheet-muted transition-colors hover:text-sheet-text"
      >
        {open ? 'Skrýt' : 'Zobrazit'} zbytek jejich watchlistu ({entries.length})
      </button>
      {open && (
        <div className="mt-2">
          <EntryTable entries={entries} muted />
        </div>
      )}
    </div>
  );
};

/**
 * Co se pohnulo od minulého čtení.
 *
 * Tohle je jediný důvod, proč se zdroj vůbec čte opakovaně — denní seznam
 * dvaceti osmi nezměněných jmen nikdo neotevírá dvakrát.
 */
const Changes: React.FC<{ changes: BreakoutChange[] }> = ({ changes }) => (
  <div className="mt-3 border-t border-sheet-rule pt-2">
    <h4 className="mb-1.5 text-[11px] uppercase tracking-wide text-sheet-muted">
      Co se změnilo
    </h4>
    <ul className="space-y-1">
      {changes.slice(0, 12).map((change) => (
        <li
          key={`${change.symbol}-${change.kind}-${change.detected_at}`}
          className="flex items-baseline gap-2 text-[12px] leading-relaxed"
        >
          <span className="shrink-0 font-mono text-[11px] text-sheet-faint">
            {day(change.detected_at)}
          </span>
          <span
            className={
              change.relation === 'THEIRS' ? 'text-sheet-muted' : 'text-sheet-text'
            }
          >
            {change.detail_cs}
          </span>
        </li>
      ))}
    </ul>
  </div>
);

export default BreakoutWatchlistCard;
