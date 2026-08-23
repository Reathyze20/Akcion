/**
 * Skládání varování do skupin.
 *
 * Backend posílá jedno varování na pozici. U patnácti pozic to znamená devět
 * skoro stejných žlutých vět pod sebou — třikrát „CHYBÍ NÁKUPNÍ CENA",
 * třikrát „STARÁ CENA", dvakrát „MĚNA NESEDÍ". Nejcennější obsah aplikace
 * vypadá jako spam a čte se přesně tak: nijak.
 *
 * Tři skupiny podle **problému** místo devíti řádků podle tickeru se dají
 * přečíst za dvě vteřiny a každá může mít tlačítko, které vede k opravě.
 *
 * Dvě pravidla, na kterých to celé stojí:
 *
 *  1. **Nic se nezahodí.** Varování, které sem nepasuje, se ukáže samo za
 *     sebe. Aplikace je postavená na tom, že absence se pojmenuje — tichý
 *     filtr by tenhle princip obrátil naruby.
 *  2. **Pořadí je podle toho, co blokuje.** Chybějící hodnocení umlčí celý
 *     denní seznam, špatná měna zkresluje hodnotu portfolia, chybějící
 *     nákupní cena odzbrojí jedno pravidlo. Stará cena je poznámka.
 */

export type WarningKind =
  | 'BEZ_HODNOCENI'
  | 'MENA'
  | 'BEZ_NAKUPNI_CENY'
  | 'STARA_CENA'
  | 'JINE';

export interface WarningGroup {
  kind: WarningKind;
  /** Krátký nadpis skupiny. Počet doplňuje volající. */
  label: string;
  /** Co kvůli tomu aplikace nemůže. Tohle je ta důležitá věta. */
  consequence: string;
  /** Tickery, kterých se to týká. Prázdné, když je varování souhrnné. */
  tickers: string[];
  /** Kolik pozic je dotčeno. */
  count: number;
  /** Původní věty — nic se neztrácí. */
  raw: string[];
}

interface Rule {
  kind: WarningKind;
  /** Podle čeho se varování pozná. */
  match: RegExp;
  label: string;
  consequence: string;
  /** Souhrnné varování nese počet v textu, ne jeden ticker. */
  aggregate?: boolean;
}

/* Pořadí v poli = pořadí zobrazení. Nejvíc blokující nahoře. */
const RULES: Rule[] = [
  {
    kind: 'BEZ_HODNOCENI',
    match: /NEZNÁMÁ KVALITA/i,
    label: 'bez konvikčního skóre',
    consequence:
      'Aplikace nespočítá cílové váhy ani nevydá pokyn. Dokud to trvá, denní seznam mlčí.',
    aggregate: true,
  },
  {
    kind: 'MENA',
    match: /MĚNA NESEDÍ/i,
    label: 'měna neodpovídá burze',
    consequence:
      'Hodnota v korunách je přepočtená špatným kurzem, takže celé portfolio ukazuje jinou částku, než jakou má.',
  },
  {
    kind: 'BEZ_NAKUPNI_CENY',
    match: /CHYBÍ NÁKUPNÍ CENA/i,
    label: 'chybí nákupní cena',
    consequence:
      'Bez ní nejde spočítat zisk ani ztráta a pravidlo zdvojnásobení je u těchhle pozic odzbrojené.',
  },
  {
    kind: 'STARA_CENA',
    match: /STARÁ CENA/i,
    label: 'zastaralá cena',
    consequence: 'Před obchodem si cenu ověř u brokera — tahle je starší, než by měla být.',
  },
];

/**
 * Vytáhne tickery z věty.
 *
 * Souhrnné varování je nese v závorce oddělené čárkami, jednotlivé je má
 * hned za dvojtečkou. Pozor na tvary jako `IMP.V (EUR→CAD?)` a na ISINy,
 * které jsou dlouhé a obsahují číslice.
 */
export function extractTickers(warning: string): string[] {
  const inParens = warning.match(/\(([A-Z0-9., ]+)\)/);
  if (inParens && inParens[1].includes(',')) {
    return inParens[1]
      .split(',')
      .map((t) => t.trim())
      .filter(Boolean);
  }

  const afterColon = warning.match(/:\s*([A-Z0-9.]{2,20})/);
  if (afterColon) return [afterColon[1]];

  return [];
}

/** Počet dotčených pozic. U souhrnného varování je v textu („u 15 pozic"). */
function countFrom(warning: string, tickers: string[]): number {
  const explicit = warning.match(/u\s+(\d+)\s+pozic/i);
  if (explicit) return Number(explicit[1]);
  return tickers.length || 1;
}

export function groupWarnings(warnings: string[]): WarningGroup[] {
  const groups = new Map<WarningKind, WarningGroup>();
  const other: WarningGroup[] = [];

  for (const warning of warnings) {
    const rule = RULES.find((r) => r.match.test(warning));

    if (!rule) {
      // Nezařazené varování se ukáže samo za sebe. Zahodit ho by znamenalo
      // ztratit přesně tu informaci, kvůli které varování existují.
      other.push({
        kind: 'JINE',
        label: warning,
        consequence: '',
        tickers: [],
        count: 1,
        raw: [warning],
      });
      continue;
    }

    const tickers = extractTickers(warning);
    const existing = groups.get(rule.kind);

    if (existing) {
      existing.raw.push(warning);
      for (const t of tickers) {
        if (!existing.tickers.includes(t)) existing.tickers.push(t);
      }
      existing.count = rule.aggregate
        ? Math.max(existing.count, countFrom(warning, tickers))
        : existing.tickers.length || existing.raw.length;
    } else {
      groups.set(rule.kind, {
        kind: rule.kind,
        label: rule.label,
        consequence: rule.consequence,
        tickers,
        count: countFrom(warning, tickers),
        raw: [warning],
      });
    }
  }

  // Pořadí podle RULES, nezařazená na konec.
  const ordered = RULES.map((r) => groups.get(r.kind)).filter(
    (g): g is WarningGroup => g !== undefined,
  );

  return [...ordered, ...other];
}
