/**
 * Složené úročení — projekce portfolia.
 *
 * Tenhle modul počítá jediné, co v aplikaci nelze ověřit proti realitě:
 * budoucnost. O to přísněji se musí chovat.
 *
 * Tři pravidla, která z toho plynou:
 *
 *  1. Nedosažitelný cíl se hlásí jako nedosažitelný. Starý kód počítal
 *     do stropu 360 měsíců a vracel 360 i tam, kde se cíl nedal splnit
 *     nikdy — z „to nevyjde" se stalo „za 30 let".
 *
 *  2. Projekce je rozpětí, ne číslo. Jediná křivka při 15 % ročně je
 *     fikce; trh takhle nechodí. Vracíme pesimistickou, očekávanou
 *     a optimistickou dráhu a vykresluje se pás mezi nimi.
 *
 *  3. Vložené a vydělané se nesčítá do jedné hromady. Kolik jsi vložil
 *     je fakt, kolik přidal trh je odhad, a v grafu to musí být vidět
 *     odděleně.
 *
 * Zaokrouhlování na haléře sem nepatří vůbec. O tom rozhoduje vrstva
 * zobrazení, ne výpočet — ale žádná projekce se nesmí vysázet
 * s přesností, kterou nemá.
 */

export interface ProjectionInput {
  /** Dnešní hodnota portfolia v Kč. */
  presentValue: number;
  /** Měsíční vklad v Kč. */
  monthlyContribution: number;
  /** Očekávaný roční výnos jako desetinné číslo (0.15 = 15 %). */
  annualReturn: number;
  /** Délka projekce v letech. */
  years: number;
}

export interface YearPoint {
  /** Rok od dneška; 0 je dnešek. */
  year: number;
  /** Hodnota portfolia při očekávaném výnosu. */
  value: number;
  /** Hodnota při pesimistické dráze. */
  low: number;
  /** Hodnota při optimistické dráze. */
  high: number;
  /**
   * Vložený kapitál: dnešní hodnota plus všechny vklady do tohoto roku.
   * Není to projekce — je to součet toho, co člověk odloží.
   */
  contributed: number;
  /** Rozdíl mezi očekávanou hodnotou a vloženým kapitálem. */
  growth: number;
}

/**
 * O kolik se pesimistická a optimistická dráha liší od očekávané.
 *
 * Není to statistický interval spolehlivosti a netváří se tak. Je to
 * přiznání, že očekávaný výnos je odhad: horní dráha počítá s výnosem
 * o třetinu vyšším, spodní s výnosem o třetinu nižším.
 */
export const RETURN_SPREAD = 1 / 3;

/** Dlouhodobý inflační cíl ČNB. Používá se k přepočtu na dnešní kupní sílu. */
export const DEFAULT_INFLATION = 0.02;

const MONTHS = 12;

/**
 * Budoucí hodnota při měsíčním připisování a vkladu na konci měsíce.
 *
 * Uzavřený tvar; iterace přes měsíce dává totéž, ale u dlouhých období
 * nasčítá zaokrouhlovací chybu.
 */
export function futureValue(
  presentValue: number,
  monthlyContribution: number,
  annualReturn: number,
  months: number,
): number {
  if (months <= 0) return presentValue;

  const i = annualReturn / MONTHS;

  // Nulový výnos není okrajový případ k ignorování: je to volba, kterou
  // si člověk v kalkulačce zadá, aby viděl, kolik z výsledku dělá jen
  // odkládání. Uzavřený tvar by tady dělil nulou.
  if (i === 0) {
    return presentValue + monthlyContribution * months;
  }

  const growth = Math.pow(1 + i, months);
  return presentValue * growth + monthlyContribution * ((growth - 1) / i);
}

/**
 * Za kolik měsíců projekce dosáhne cíle.
 *
 * Vrací `null`, když cíl při zadaných parametrech nedosáhne nikdy —
 * typicky při nulovém vkladu i výnosu, nebo při záporném výnosu, který
 * portfolio umazává rychleji, než vklady přibývají.
 *
 * `limitMonths` je pojistka proti nekonečné smyčce, ne odpověď. Když se
 * na ni narazí, výsledek je `null`.
 */
export function monthsToTarget(
  presentValue: number,
  monthlyContribution: number,
  annualReturn: number,
  target: number,
  limitMonths = 100 * MONTHS,
): number | null {
  if (presentValue >= target) return 0;

  const i = annualReturn / MONTHS;
  let value = presentValue;

  for (let month = 1; month <= limitMonths; month += 1) {
    const before = value;
    value = value * (1 + i) + monthlyContribution;

    if (value >= target) return month;

    // Neroste to. Další iterace na tom nic nezmění, ať jich je kolik chce.
    if (value <= before) return null;
  }

  return null;
}

/** Roční body projekce, včetně dnešního stavu jako roku 0. */
export function project(input: ProjectionInput): YearPoint[] {
  const { presentValue, monthlyContribution, annualReturn, years } = input;

  const low = annualReturn * (1 - RETURN_SPREAD);
  const high = annualReturn * (1 + RETURN_SPREAD);

  const points: YearPoint[] = [];

  for (let year = 0; year <= years; year += 1) {
    const months = year * MONTHS;
    const value = futureValue(presentValue, monthlyContribution, annualReturn, months);
    const contributed = presentValue + monthlyContribution * months;

    points.push({
      year,
      value,
      low: futureValue(presentValue, monthlyContribution, low, months),
      high: futureValue(presentValue, monthlyContribution, high, months),
      contributed,
      growth: value - contributed,
    });
  }

  return points;
}

/**
 * Přepočet na dnešní kupní sílu.
 *
 * Třicet milionů za dvacet let nejsou dnešní tři miliony. Aplikace, která
 * ukazuje jen nominální cíl, slibuje víc, než kolik ta částka koupí.
 */
export function realValue(
  nominal: number,
  years: number,
  inflation = DEFAULT_INFLATION,
): number {
  if (years <= 0) return nominal;
  return nominal / Math.pow(1 + inflation, years);
}

/**
 * Kolik z jednoho dnešního vkladu bude v cílovém roce.
 *
 * Tohle je ta motivující pravda o složeném úročení a dá se spočítat
 * poctivě: jde o jeden vklad úročený po celou dobu, ne o rozdíl dvou
 * zaokrouhlených scénářů.
 *
 * Starší verze aplikace hlásila „poslední vklad přiblížil důchod o 30 dní".
 * To číslo bylo vždycky násobkem třiceti, protože vznikalo jako rozdíl
 * dvou celočíselných počtů měsíců krát 30. Přesnost, kterou nemělo.
 */
export function contributionAtHorizon(
  contribution: number,
  annualReturn: number,
  years: number,
): number {
  return futureValue(contribution, 0, annualReturn, years * MONTHS);
}

export interface GoalSummary {
  /** Počet měsíců k cíli, nebo null když je cíl mimo dosah. */
  months: number | null;
  years: number | null;
  monthsRemainder: number | null;
  /** Věk v době dosažení cíle, když je znám dnešní věk. */
  ageAtGoal: number | null;
  /** Podíl dnešní hodnoty na cíli, 0 až 100. */
  progressPct: number;
  /** Cílová částka přepočtená na dnešní kupní sílu. */
  targetInTodaysMoney: number | null;
}

export function summarise(
  input: ProjectionInput,
  target: number,
  currentAge?: number,
  inflation = DEFAULT_INFLATION,
): GoalSummary {
  const months = monthsToTarget(
    input.presentValue,
    input.monthlyContribution,
    input.annualReturn,
    target,
  );

  const years = months === null ? null : Math.floor(months / MONTHS);
  const progressPct = target > 0
    ? Math.min(100, Math.max(0, (input.presentValue / target) * 100))
    : 0;

  return {
    months,
    years,
    monthsRemainder: months === null ? null : months % MONTHS,
    ageAtGoal: months === null || currentAge === undefined
      ? null
      : currentAge + Math.floor(months / MONTHS),
    progressPct,
    targetInTodaysMoney: months === null
      ? null
      : realValue(target, months / MONTHS, inflation),
  };
}
