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

/** Desetinné číslo s českou čárkou. Pro údaje, které nejsou procenta ani měna. */
export function decimal(value: number, digits = 1): string {
  return value.toLocaleString(CS, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
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

/**
 * Odhad ve svojí vlastní měně (ne v korunách) — pro modely tržeb v USD/CAD.
 * Stejná stupnice jako `estimate()`, jen bez pevné vazby na koruny.
 */
export function bigMoney(value: number, currency: string): string {
  const abs = Math.abs(value);
  const sign = value < 0 ? '−' : '';
  const symbol = CURRENCY_SYMBOL[currency] ?? currency;

  if (abs >= 1_000_000_000) {
    return `${sign}${symbol} ${(abs / 1_000_000_000).toLocaleString(CS, { maximumFractionDigits: 2 })} mld.`;
  }
  if (abs >= 1_000_000) {
    return `${sign}${symbol} ${(abs / 1_000_000).toLocaleString(CS, { maximumFractionDigits: 2 })} mil.`;
  }
  if (abs >= 1_000) {
    return `${sign}${symbol} ${Math.round(abs / 1_000).toLocaleString(CS)} tis.`;
  }
  return `${sign}${symbol} ${Math.round(abs).toLocaleString(CS)}`;
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

/**
 * Stupeň semaforu česky.
 *
 * Backend posílá GREEN / YELLOW / ORANGE / RED. V rozhraní to nemá co
 * dělat — je to hodnota z databáze, ne slovo pro čtenáře. Jedno místo,
 * aby se „YELLOW" neobjevilo uprostřed české věty na jedné kartě
 * a „žlutá" na vedlejší.
 */
const ALERT_CS: Record<string, string> = {
  GREEN: 'zelená',
  YELLOW: 'žlutá',
  ORANGE: 'oranžová',
  RED: 'červená',
};

export function alertName(alert: string | null | undefined): string {
  if (!alert) return 'nenastaveno';
  return ALERT_CS[alert.toUpperCase()] ?? alert;
}

/** Třída plochy pro barevný bod stupně semaforu. */
export function alertDot(alert: string | null | undefined): string {
  switch ((alert ?? '').toUpperCase()) {
    case 'GREEN': return 'bg-signal-green';
    case 'YELLOW': return 'bg-signal-amber';
    case 'ORANGE': return 'bg-signal-orange';
    case 'RED': return 'bg-signal-red';
    default: return 'bg-text-muted';
  }
}

/**
 * České názvy cenových pásem.
 *
 * Jediný překlad, který v aplikaci existoval, seděl v mrtvé komponentě
 * `StockCard.tsx`, zatímco živé obrazovky vypisovaly syrové enumy
 * (`DEEP_VALUE`, `BUY_NOW`). Enum je klíč do kódu, ne slovo pro člověka —
 * a tuhle obrazovku čtou dva lidé, z nichž ani jeden kánon nezná.
 */
const BAND_CS: Record<string, string> = {
  POD_ZELENOU: 'POD ZELENOU',
  NAKUP: 'NÁKUP',
  DRZET: 'DRŽET',
  PREPLACENO: 'PŘEPLACENO',
  NAD_CERVENOU: 'NAD ČERVENOU',
  NEZNAME: 'NEZNÁMÉ',
  MIMO_METODIKU: 'MIMO METODIKU',
};

export function bandName(band: string | null | undefined): string {
  if (!band) return 'NEZNÁMÉ';
  return BAND_CS[band.toUpperCase()] ?? band;
}

/**
 * Barva pásma. Zelená a červená jen tam, kde jde o cenu vůči kvalitě —
 * `MIMO METODIKU` a `NEZNÁMÉ` musí zůstat šedé, protože to nejsou špatné
 * zprávy, ale chybějící údaj, a barva by z chybějícího údaje udělala verdikt.
 */
export function bandTone(band: string | null | undefined): {
  text: string;
  pill: string;
  marker: string;
} {
  switch ((band ?? '').toUpperCase()) {
    case 'POD_ZELENOU':
    case 'NAKUP':
      return {
        text: 'text-positive',
        pill: 'bg-positive-bg text-positive border-positive-border',
        marker: 'bg-positive',
      };
    case 'PREPLACENO':
    case 'NAD_CERVENOU':
      return {
        text: 'text-negative',
        pill: 'bg-negative-bg text-negative border-negative-border',
        marker: 'bg-negative',
      };
    case 'DRZET':
      return {
        text: 'text-text-secondary',
        pill: 'bg-surface-active text-text-secondary border-border-subtle',
        marker: 'bg-text-secondary',
      };
    default:
      return {
        text: 'text-text-muted',
        pill: 'bg-surface-active text-text-muted border-border-subtle',
        marker: 'bg-text-muted',
      };
  }
}

/**
 * České názvy cenových pásem ze Sledovaných (`price_zone`).
 *
 * Jiný enum než `band` — `price_zone` je DEEP_VALUE/BUY_ZONE/ACCUMULATE/
 * FAIR_VALUE/SELL_ZONE/OVERVALUED, `band` je POD_ZELENOU/NAKUP/…. Násilné
 * mapování jednoho na druhý by tvrdilo něco, co appka neměří — proto
 * samostatná dvojice funkcí, ne převod na `bandName`/`bandTone`.
 */
const ZONE_CS: Record<string, string> = {
  DEEP_VALUE: 'HLUBOKÁ HODNOTA',
  BUY_ZONE: 'KUPNÍ PÁSMO',
  ACCUMULATE: 'PŘIKUPOVAT',
  FAIR_VALUE: 'SPRAVEDLIVÁ CENA',
  SELL_ZONE: 'PRODEJNÍ PÁSMO',
  OVERVALUED: 'PŘEHODNOCENO',
};

export function zoneName(zone: string | null | undefined): string {
  if (!zone) return 'MIMO METODIKU';
  return ZONE_CS[zone.toUpperCase()] ?? zone;
}

/** Chybějící/neznámé pásmo zůstává šedé ze stejného důvodu jako u `bandTone()`. */
export function zoneTone(zone: string | null | undefined): { text: string; pill: string } {
  switch ((zone ?? '').toUpperCase()) {
    case 'DEEP_VALUE':
    case 'BUY_ZONE':
      return { text: 'text-positive', pill: 'bg-positive-bg text-positive border-positive-border' };
    case 'ACCUMULATE':
      return { text: 'text-accent', pill: 'bg-accent-bg text-accent border-accent-border' };
    case 'FAIR_VALUE':
    case 'SELL_ZONE':
      return { text: 'text-warning', pill: 'bg-warning-bg text-warning border-warning-border' };
    case 'OVERVALUED':
      return { text: 'text-negative', pill: 'bg-negative-bg text-negative border-negative-border' };
    default:
      return { text: 'text-text-muted', pill: 'bg-surface-active text-text-muted border-border-subtle' };
  }
}

/**
 * České názvy verdiktu ze Sledovaných (`action_verdict`) — třetí, opět jiný
 * enum (BUY_NOW/ACCUMULATE/WATCH_LIST/TRIM/SELL/AVOID), stejný důvod pro
 * samostatnou dvojici funkcí jako u `zoneName`/`zoneTone`.
 */
const VERDICT_CS: Record<string, string> = {
  BUY_NOW: 'KOUPIT TEĎ',
  ACCUMULATE: 'PŘIKUPOVAT',
  WATCH_LIST: 'SLEDOVAT',
  TRIM: 'ODEBRAT',
  SELL: 'PRODAT',
  AVOID: 'VYHNOUT SE',
};

export function verdictName(verdict: string | null | undefined): string {
  if (!verdict) return 'MIMO METODIKU';
  return VERDICT_CS[verdict.toUpperCase()] ?? verdict;
}

export function verdictTone(verdict: string | null | undefined): { text: string; pill: string } {
  switch ((verdict ?? '').toUpperCase()) {
    case 'BUY_NOW':
    case 'ACCUMULATE':
      return { text: 'text-positive', pill: 'bg-positive-bg text-positive border-positive-border' };
    case 'WATCH_LIST':
      return { text: 'text-accent', pill: 'bg-accent-bg text-accent border-accent-border' };
    case 'TRIM':
      return { text: 'text-warning', pill: 'bg-warning-bg text-warning border-warning-border' };
    case 'SELL':
    case 'AVOID':
      return { text: 'text-negative', pill: 'bg-negative-bg text-negative border-negative-border' };
    default:
      return { text: 'text-text-muted', pill: 'bg-surface-active text-text-muted border-border-subtle' };
  }
}
