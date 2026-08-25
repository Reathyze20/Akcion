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
  /** Volitelná změna vkladu v čase (typicky start hypotéky). */
  contributionChange?: ContributionChange;
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
 * O kolik procentních bodů se pesimistická a optimistická dráha liší
 * od očekávaného výnosu.
 *
 * Není to statistický interval spolehlivosti a netváří se tak. Je to
 * přiznání, že očekávaný výnos je odhad.
 *
 * Procentní body, ne podíl. Dva důvody:
 *
 *  - Dá se to vyslovit. „Pás ukazuje 12 až 18 % ročně" je věta, které
 *    člověk rozumí. „Rozpětí je třetina očekávaného výnosu" není.
 *  - Relativní rozpětí se přes dvacet let složeného úročení rozevře
 *    tak, že horní okraj vytáhne osu grafu čtyřnásobně nad cíl
 *    a očekávaná dráha se zmáčkne ke dnu. Pás, kvůli kterému není
 *    vidět to hlavní, informaci neubírá — bere ji.
 */
export const RETURN_SPREAD_PP = 0.03;

/** Dlouhodobý inflační cíl ČNB. Používá se k přepočtu na dnešní kupní sílu. */
export const DEFAULT_INFLATION = 0.02;

/**
 * Podíl portfolia, který jde ročně vybírat, aniž by došlo.
 *
 * Slavná čtyři procenta (Bengen 1994) jsou kalibrovaná na **třicet let**
 * důchodu. Odchod v padesáti znamená, že peníze musí vydržet čtyřicet
 * až padesát — a na tom horizontu čtyři procenta historicky selhávala.
 * Proto 3,25 %.
 *
 * Není to opatrnost pro opatrnost. Rozdíl mezi 4 % a 3,25 % je pětina
 * renty; rozdíl mezi „vyšlo to" a „v sedmdesáti pěti došly peníze" je
 * celý zbytek života.
 */
export const SAFE_WITHDRAWAL_RATE = 0.0325;

const MONTHS = 12;

/**
 * Změna měsíčního vkladu v čase.
 *
 * Existuje kvůli hypotéce. Splátka nesníží výnos ani nepohne trhem —
 * sníží vklad, a to je jediná páka, kterou člověk skutečně drží.
 * Projekce s konstantním vkladem po celou dobu kreslí dráhu, po které
 * se ve skutečnosti nejde.
 */
export interface ContributionChange {
  /** Po kolika letech od dneška se vklad mění. */
  afterYears: number;
  /** Nový měsíční vklad od té chvíle dál. */
  monthlyContribution: number;
}

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
 * Budoucí hodnota, když se vklad v půlce cesty změní.
 *
 * Počítá se ve dvou úsecích: hodnota v okamžiku zlomu se stane výchozí
 * hodnotou druhého úseku. Uzavřený tvar platí v obou, takže se nic
 * nenasčítá navíc.
 */
export function futureValueStaged(
  presentValue: number,
  monthlyContribution: number,
  annualReturn: number,
  months: number,
  change?: ContributionChange,
): number {
  const breakMonth = change ? Math.round(change.afterYears * MONTHS) : 0;

  if (!change || breakMonth <= 0 || months <= breakMonth) {
    return futureValue(presentValue, monthlyContribution, annualReturn, months);
  }

  const atBreak = futureValue(presentValue, monthlyContribution, annualReturn, breakMonth);
  return futureValue(atBreak, change.monthlyContribution, annualReturn, months - breakMonth);
}

/**
 * Vložený kapitál k danému měsíci — dnešní hodnota plus všechny vklady.
 *
 * Jediná vrstva projekce, která není odhad, takže musí zlom respektovat
 * stejně jako dráha. Kdyby ho ignorovala, tvrdila by, že jsi vložil víc,
 * než kolik jsi vložil.
 */
export function contributedAt(
  presentValue: number,
  monthlyContribution: number,
  months: number,
  change?: ContributionChange,
): number {
  const breakMonth = change ? Math.round(change.afterYears * MONTHS) : 0;

  if (!change || breakMonth <= 0 || months <= breakMonth) {
    return presentValue + monthlyContribution * months;
  }

  return presentValue
    + monthlyContribution * breakMonth
    + change.monthlyContribution * (months - breakMonth);
}

/**
 * Udržitelná měsíční renta z daného jmění.
 *
 * Vstup patří v dnešní kupní síle, výstup vyjde v téže. Míchat nominální
 * jmění s dnešními výdaji je nejběžnější způsob, jak si o důchodu lhát:
 * dvacet milionů za sedmnáct let zní jako dost, dokud se nezeptáš, co
 * za ně bude k mání.
 */
export function sustainableMonthlyIncome(
  realValue: number,
  rate = SAFE_WITHDRAWAL_RATE,
): number {
  if (realValue <= 0) return 0;
  return (realValue * rate) / MONTHS;
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
  change?: ContributionChange,
): number | null {
  if (presentValue >= target) return 0;

  const i = annualReturn / MONTHS;
  const breakMonth = change ? Math.round(change.afterYears * MONTHS) : 0;
  let value = presentValue;

  for (let month = 1; month <= limitMonths; month += 1) {
    const before = value;
    // Po zlomu se přidává nový vklad. Bez toho by odpověď „za jak dlouho"
    // počítala s penězi, které v té době půjdou na splátku.
    const pmt = change && breakMonth > 0 && month > breakMonth
      ? change.monthlyContribution
      : monthlyContribution;
    value = value * (1 + i) + pmt;

    if (value >= target) return month;

    // Neroste to. Další iterace na tom nic nezmění, ať jich je kolik chce.
    if (value <= before) return null;
  }

  return null;
}

/** Roční body projekce, včetně dnešního stavu jako roku 0. */
export function project(input: ProjectionInput): YearPoint[] {
  const { presentValue, monthlyContribution, annualReturn, years, contributionChange } = input;

  // Spodní dráha se nepropadne pod nulu: záporný výnos je jiný scénář
  // než „vyšlo to hůř", a do pásu kolem kladného očekávání nepatří.
  const low = Math.max(0, annualReturn - RETURN_SPREAD_PP);
  const high = annualReturn + RETURN_SPREAD_PP;

  const points: YearPoint[] = [];

  for (let year = 0; year <= years; year += 1) {
    const months = year * MONTHS;
    const value = futureValueStaged(
      presentValue, monthlyContribution, annualReturn, months, contributionChange,
    );
    const contributed = contributedAt(
      presentValue, monthlyContribution, months, contributionChange,
    );

    points.push({
      year,
      value,
      low: futureValueStaged(presentValue, monthlyContribution, low, months, contributionChange),
      high: futureValueStaged(presentValue, monthlyContribution, high, months, contributionChange),
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
    undefined,
    input.contributionChange,
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

/**
 * Výhled k důchodu.
 *
 * Odpovídá na jinou otázku než `summarise`. Ta řeší „za jak dlouho
 * na částku"; tahle „co budeme mít v den D a co nám to bude vyplácet".
 * Pro někoho, kdo má pevné datum odchodu, je správná ta druhá — částka
 * není vstup, ale výsledek.
 *
 * `null` znamená, že projekce nedává smysl: odchod už nastal, nebo je
 * zadaný dřív než dnešek. Nulu vracet nelze — nula je odpověď, tohle není.
 */
export interface RetirementOutlook {
  /** Let do odchodu. */
  years: number;
  /** Hodnota portfolia v den odchodu, nominálně. */
  nominal: number;
  /** Táž hodnota v dnešní kupní síle. */
  real: number;
  /** Kolik z toho tvoří vklady. Fakt, ne odhad. */
  contributed: number;
  /** Udržitelná měsíční renta, v dnešních penězích. */
  monthlyIncome: number;
}

export function retirementOutlook(
  input: Omit<ProjectionInput, 'years'>,
  currentAge: number,
  retirementAge: number,
  inflation = DEFAULT_INFLATION,
  withdrawalRate = SAFE_WITHDRAWAL_RATE,
): RetirementOutlook | null {
  const years = retirementAge - currentAge;
  if (years <= 0) return null;

  const months = years * MONTHS;
  const nominal = futureValueStaged(
    input.presentValue,
    input.monthlyContribution,
    input.annualReturn,
    months,
    input.contributionChange,
  );
  const real = realValue(nominal, years, inflation);

  return {
    years,
    nominal,
    real,
    contributed: contributedAt(
      input.presentValue, input.monthlyContribution, months, input.contributionChange,
    ),
    monthlyIncome: sustainableMonthlyIncome(real, withdrawalRate),
  };
}
