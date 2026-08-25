/**
 * Jedna firma, víc tickerů.
 *
 * Čtyři pozice se drží na kanadské burze, ale každá analýza — Gomesova
 * i watchlist Breakout Investors — mluví o americkém OTC listingu. Aplikace
 * je brala jako dvě různé firmy: KUYA.V mělo skóre 7 a KUYAF skóre 10,
 * KUYAF se ukazovalo mezi „Sledovanými", i když KUYA.V se drží.
 *
 * Tabulka aliasů žije v backendu (`backend/app/core/tickers.py`) a chodí
 * s daty jako `canonical_ticker`. Tady se schválně nekopíruje: dva seznamy
 * dvojic by se dřív nebo později rozešly a rozdíl by nikdo nenašel.
 *
 * Aliasy slouží jen k párování. Zobrazuje se pořád `ticker` z výpisu od
 * brokera, protože to je ten, který má člověk na papíře.
 */

/** Cokoli, co nese ticker a případně jeho kanonickou podobu. */
export interface HasTicker {
  ticker: string;
  canonical_ticker?: string | null;
}

/**
 * Klíč pro párování.
 *
 * `canonical_ticker` z API, jinak samotný ticker. Fallback není pojistka na
 * chybějící data — většina tickerů má jediný listing a je sama sobě
 * kanonická.
 */
export function canonicalOf(item: HasTicker | null | undefined): string {
  if (!item) return '';
  const canonical = item.canonical_ticker?.trim().toUpperCase();
  if (canonical) return canonical;
  return item.ticker?.trim().toUpperCase() ?? '';
}

/** Sada kanonických tickerů — pro „držíme tuhle firmu?". */
export function canonicalSet(items: HasTicker[]): Set<string> {
  const out = new Set<string>();
  for (const item of items) {
    const key = canonicalOf(item);
    if (key) out.add(key);
  }
  return out;
}

interface AnalysisRow extends HasTicker {
  source_key?: string | null;
  conviction_score?: number | null;
}

/**
 * Která analýza patří k tomuhle papíru.
 *
 * Na jednu firmu můžou být dva řádky — jeden pod kanadským tickerem, druhý
 * pod OTC — a každý s jiným skóre. Pořadí je rozhodnuté, ne náhodné:
 *
 *   1. řádek od Gomese, který má skóre — valuační autorita je jeho (kánon),
 *   2. jinak jakýkoli řádek se skóre,
 *   3. jinak řádek od Gomese,
 *   4. jinak první, co je.
 *
 * Proč „od Gomese SE SKÓRE" a ne prostě „od Gomese": GSI.V má skóre 5 pod
 * kanadským tickerem a řádek GKPRF od Gomese žádné skóre nemá. Slepá
 * přednost zdroje by pozici o pětku připravila a aplikace by hlásila, že
 * hodnocení chybí, i když ho má. Vybírá se vždycky JEDEN řádek celý; čísla
 * ze dvou se nemíchají, jinak by vznikla analýza, kterou nikdo nenapsal.
 *
 * `undefined` znamená, že k tomu tickeru žádná analýza není. To je odpověď,
 * ne chyba — pět z dvanácti pozic ji 23. 8. 2026 nemělo.
 */
export function pickAnalysis<T extends AnalysisRow>(
  rows: T[],
  target: HasTicker | null | undefined
): T | undefined {
  const key = canonicalOf(target);
  if (!key) return undefined;

  const candidates = rows.filter((row) => canonicalOf(row) === key);
  if (candidates.length <= 1) return candidates[0];

  const scored = (row: T) => row.conviction_score != null;
  const gomes = (row: T) => row.source_key === 'GOMES';

  const base = (
    candidates.find((row) => gomes(row) && scored(row)) ??
    candidates.find(scored) ??
    candidates.find(gomes) ??
    candidates[0]
  );

  // Pokud vybranému řádku chybí cenové linie, doplnit je z Gomesova řádku téže firmy
  const gomesWithLines = candidates.find(
    (row: any) => gomes(row) && (row.green_line != null || row.red_line != null)
  ) as any;

  if (gomesWithLines && (base as any).green_line == null) {
    return {
      ...base,
      green_line: gomesWithLines.green_line,
      red_line: gomesWithLines.red_line,
      grey_line: gomesWithLines.grey_line,
      price_zone: (base as any).price_zone ?? gomesWithLines.price_zone,
      price_position_pct: (base as any).price_position_pct ?? gomesWithLines.price_position_pct,
    };
  }

  return base;
}
