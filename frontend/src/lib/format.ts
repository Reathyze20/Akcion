/**
 * Formátování čísel.
 *
 * Jedno místo, aby se stejná částka nikde v aplikaci neobjevila dvakrát
 * jinak zaokrouhlená. Ve staré verzi stálo v hlavičce 233 293,56 Kč
 * a o obrazovku níž 233 294 Kč — jedno číslo, dvě podoby, jedna stránka.
 *
 * Hlavní pravidlo: **přesnost zápisu má odpovídat přesnosti údaje.**
 * Zůstatek na účtu se zná na haléře. Patnáctiletá projekce se nezná ani
 * na statisíce, takže se tak ani nesmí vysázet. Proto jsou na projekce
 * samostatné funkce, které zaokrouhlují nahrubo — aby nešlo omylem
 * použít formát pro skutečnou částku.
 */

const CS = 'cs-CZ';

/** Skutečná částka: zůstatek, nákup, hodnota pozice. Zaokrouhlená na koruny. */
export function czk(value: number): string {
  return value.toLocaleString(CS, {
    style: 'currency',
    currency: 'CZK',
    maximumFractionDigits: 0,
  });
}

/** Skutečná částka bez značky měny, když je měna zřejmá z okolí. */
export function amount(value: number): string {
  return value.toLocaleString(CS, { maximumFractionDigits: 0 });
}

/**
 * Odhad. Zaokrouhlí na tři platné číslice a doplní řádovou zkratku.
 *
 * 15 552 907,74 Kč se tímhle stane „15,6 mil. Kč". Rozdíl není kosmetický:
 * první zápis tvrdí, že známe haléře patnáct let dopředu.
 */
export function estimate(value: number): string {
  const abs = Math.abs(value);
  const sign = value < 0 ? '−' : '';

  if (abs >= 1_000_000_000) {
    return `${sign}${(abs / 1_000_000_000).toLocaleString(CS, { maximumFractionDigits: 1 })} mld. Kč`;
  }
  if (abs >= 1_000_000) {
    return `${sign}${(abs / 1_000_000).toLocaleString(CS, { maximumFractionDigits: 1 })} mil. Kč`;
  }
  if (abs >= 10_000) {
    // Na tisíce: u odhadu pod milion jsou stovky pod rozlišovací schopnost.
    return `${sign}${Math.round(abs / 1_000).toLocaleString(CS)} tis. Kč`;
  }
  return `${sign}${Math.round(abs).toLocaleString(CS)} Kč`;
}

/** Krátký popisek osy grafu. Bez měny — ta patří do titulku osy. */
export function axisTick(value: number): string {
  const abs = Math.abs(value);
  if (abs >= 1_000_000) {
    return `${(value / 1_000_000).toLocaleString(CS, { maximumFractionDigits: abs >= 10_000_000 ? 0 : 1 })} M`;
  }
  if (abs >= 1_000) {
    return `${Math.round(value / 1_000).toLocaleString(CS)} tis.`;
  }
  return value.toLocaleString(CS, { maximumFractionDigits: 0 });
}

/** Procento s jedním desetinným místem a znaménkem, když na něm záleží. */
export function percent(value: number, opts: { sign?: boolean; digits?: number } = {}): string {
  const { sign = false, digits = 1 } = opts;
  const text = value.toLocaleString(CS, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
  return `${sign && value > 0 ? '+' : ''}${text} %`;
}

/** Cena v původní měně papíru. Drobné akcie potřebují víc desetinných míst. */
export function price(value: number, currency?: string | null): string {
  const digits = Math.abs(value) < 1 ? 4 : 2;
  const text = value.toLocaleString(CS, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
  const symbol = currency ? CURRENCY_SYMBOL[currency] ?? currency : '';
  return symbol ? `${symbol} ${text}` : text;
}

const CURRENCY_SYMBOL: Record<string, string> = {
  USD: '$',
  EUR: '€',
  CZK: 'Kč',
  CAD: 'CA$',
  GBP: '£',
  GBX: 'p',
  CHF: 'CHF',
  PLN: 'zł',
};

/**
 * Doba v letech a měsících, česky se správným tvarem.
 *
 * `null` znamená, že se cíl při zadaných parametrech nedá splnit.
 * Vrací se text, ne prázdno — nedosažitelnost je odpověď, ne chyba.
 */
export function duration(months: number | null): string {
  if (months === null) return 'nikdy při těchto parametrech';
  if (months <= 0) return 'splněno';

  const years = Math.floor(months / 12);
  const rest = months % 12;

  const parts: string[] = [];
  if (years > 0) parts.push(`${years} ${plural(years, 'rok', 'roky', 'let')}`);
  if (rest > 0) parts.push(`${rest} ${plural(rest, 'měsíc', 'měsíce', 'měsíců')}`);
  return parts.join(' a ');
}

/** České skloňování po číslovce: 1 / 2–4 / 5+. */
export function plural(n: number, one: string, few: string, many: string): string {
  const abs = Math.abs(n);
  if (abs === 1) return one;
  if (abs >= 2 && abs <= 4) return few;
  return many;
}

/** Datum bez času, pro popisky „data k …". */
export function day(iso: string | null | undefined): string {
  if (!iso) return '—';
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return '—';
  return parsed.toLocaleDateString(CS, { day: 'numeric', month: 'numeric', year: 'numeric' });
}
