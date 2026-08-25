/**
 * Testy projekce.
 *
 * Projekce je jediná část aplikace, kterou nelze porovnat se skutečností,
 * takže je jediná, kde se chyba nikdy neprozradí sama. Testy tu proto
 * hlídají hlavně to, aby výsledek nepředstíral jistotu, kterou nemá:
 * nedosažitelný cíl musí vyjít jako nedosažitelný a vložený kapitál se
 * nesmí smíchat s odhadovaným výnosem.
 */

import { describe, expect, it } from 'vitest';
import {
  contributedAt,
  contributionAtHorizon,
  DEFAULT_INFLATION,
  futureValue,
  futureValueStaged,
  monthsToTarget,
  project,
  realValue,
  retirementOutlook,
  RETURN_SPREAD_PP,
  SAFE_WITHDRAWAL_RATE,
  summarise,
  sustainableMonthlyIncome,
} from './compound';

describe('futureValue', () => {
  it('bez času vrací dnešní hodnotu', () => {
    expect(futureValue(100_000, 20_000, 0.15, 0)).toBe(100_000);
    expect(futureValue(100_000, 20_000, 0.15, -12)).toBe(100_000);
  });

  it('při nulovém výnosu jen sečte vklady', () => {
    // Nulový výnos není okrajový případ — je to volba v kalkulačce,
    // která ukazuje, kolik z výsledku dělá samotné odkládání.
    expect(futureValue(100_000, 20_000, 0, 12)).toBe(100_000 + 240_000);
  });

  it('nedělí nulou při nulovém výnosu', () => {
    expect(Number.isFinite(futureValue(0, 1_000, 0, 120))).toBe(true);
  });

  it('odpovídá ručně dopočítané anuitě', () => {
    // PV 100 000, vklad 10 000/měs, 12 % p.a., 24 měsíců.
    // i = 0.01; (1.01)^24 = 1.26973...
    const i = 0.12 / 12;
    const g = Math.pow(1 + i, 24);
    const expected = 100_000 * g + 10_000 * ((g - 1) / i);
    expect(futureValue(100_000, 10_000, 0.12, 24)).toBeCloseTo(expected, 6);
  });

  it('roste s delším obdobím rychleji než lineárně', () => {
    // Podstata složeného úročení: druhých deset let přidá víc než prvních.
    const first = futureValue(1_000_000, 0, 0.10, 120) - 1_000_000;
    const second = futureValue(1_000_000, 0, 0.10, 240)
      - futureValue(1_000_000, 0, 0.10, 120);
    expect(second).toBeGreaterThan(first);
  });

  it('zvládne záporný výnos', () => {
    expect(futureValue(1_000_000, 0, -0.10, 12)).toBeLessThan(1_000_000);
  });
});

describe('monthsToTarget', () => {
  it('vrací nulu, když je cíl už splněný', () => {
    expect(monthsToTarget(300_000, 20_000, 0.15, 250_000)).toBe(0);
  });

  it('najde počet měsíců, po kterých projekce cíl překročí', () => {
    const months = monthsToTarget(0, 10_000, 0, 100_000);
    expect(months).toBe(10);
  });

  it('vrátí null, když se cíl nedá splnit nikdy', () => {
    // Žádný vklad, žádný výnos. Starý kód by dopočítal do stropu
    // a vrátil ho, takže „nikdy" vypadalo jako „za 30 let".
    expect(monthsToTarget(100_000, 0, 0, 30_000_000)).toBeNull();
  });

  it('vrátí null, když portfolio klesá rychleji, než přibývají vklady', () => {
    expect(monthsToTarget(1_000_000, 100, -0.30, 30_000_000)).toBeNull();
  });

  it('nevrátí strop jako odpověď', () => {
    // Cíl je dosažitelný, ale až daleko za limitem. Odpověď musí být
    // „nevím", ne limit vydávaný za výsledek.
    const limit = 24;
    expect(monthsToTarget(0, 1_000, 0, 1_000_000, limit)).toBeNull();
  });

  it('nezacyklí se při nulovém růstu i nulovém vkladu', () => {
    expect(monthsToTarget(0, 0, 0, 1)).toBeNull();
  });
});

describe('project', () => {
  const input = {
    presentValue: 233_294,
    monthlyContribution: 20_000,
    annualReturn: 0.15,
    years: 15,
  };

  it('začíná dneškem a končí zadaným rokem', () => {
    const points = project(input);
    expect(points).toHaveLength(16);
    expect(points[0].year).toBe(0);
    expect(points[0].value).toBe(input.presentValue);
    expect(points[15].year).toBe(15);
  });

  it('drží vložený kapitál oddělený od výnosu', () => {
    const points = project(input);
    const last = points[15];
    // Vložené je fakt: dnešek plus 180 vkladů. Nic víc do něj nepatří.
    expect(last.contributed).toBe(233_294 + 20_000 * 180);
    expect(last.growth).toBeCloseTo(last.value - last.contributed, 6);
  });

  it('v roce nula nemá žádný výnos', () => {
    expect(project(input)[0].growth).toBe(0);
  });

  it('pás rozpětí obklopuje očekávanou dráhu', () => {
    const points = project(input);
    for (const point of points) {
      expect(point.low).toBeLessThanOrEqual(point.value + 1e-6);
      expect(point.high).toBeGreaterThanOrEqual(point.value - 1e-6);
    }
  });

  it('rozpětí se s časem rozevírá', () => {
    // Čím dál do budoucna, tím míň se dá tvrdit. Pás to musí ukázat.
    const points = project(input);
    const early = points[1].high - points[1].low;
    const late = points[15].high - points[15].low;
    expect(late).toBeGreaterThan(early);
  });

  it('pesimistická dráha ubírá tři procentní body', () => {
    const points = project({ ...input, years: 1 });
    const expected = futureValue(
      input.presentValue,
      input.monthlyContribution,
      input.annualReturn - RETURN_SPREAD_PP,
      12,
    );
    expect(points[1].low).toBeCloseTo(expected, 6);
  });

  it('spodní dráha se nepropadne do záporného výnosu', () => {
    // Při očekávání 1 % by odečtení tří bodů dalo −2 %. Klesající pás
    // kolem rostoucího očekávání je jiný scénář, ne „vyšlo to hůř".
    const points = project({ ...input, annualReturn: 0.01, years: 10 });
    for (const point of points) {
      expect(point.low).toBeGreaterThanOrEqual(point.contributed - 1e-6);
    }
  });
});

describe('realValue', () => {
  it('při nulovém čase nic nemění', () => {
    expect(realValue(1_000_000, 0)).toBe(1_000_000);
  });

  it('kupní síla částky v budoucnu klesá', () => {
    const real = realValue(30_000_000, 20, DEFAULT_INFLATION);
    expect(real).toBeLessThan(30_000_000);
    // Při dvou procentech ročně po dvaceti letech zbyde zhruba dvě třetiny.
    expect(real).toBeCloseTo(30_000_000 / Math.pow(1.02, 20), 6);
  });

  it('při nulové inflaci nic nemění', () => {
    expect(realValue(1_000_000, 30, 0)).toBe(1_000_000);
  });
});

describe('contributionAtHorizon', () => {
  it('jeden vklad se úročí po celou dobu', () => {
    const value = contributionAtHorizon(20_000, 0.15, 19);
    expect(value).toBeCloseTo(futureValue(20_000, 0, 0.15, 19 * 12), 6);
    expect(value).toBeGreaterThan(20_000);
  });

  it('bez výnosu zůstane vklad vkladem', () => {
    expect(contributionAtHorizon(20_000, 0, 19)).toBe(20_000);
  });
});

describe('summarise', () => {
  const input = {
    presentValue: 233_294,
    monthlyContribution: 20_000,
    annualReturn: 0.15,
    years: 30,
  };

  it('rozpadne dobu na roky a měsíce', () => {
    const summary = summarise(input, 30_000_000, 35);
    expect(summary.months).not.toBeNull();
    expect(summary.years! * 12 + summary.monthsRemainder!).toBe(summary.months);
  });

  it('spočítá věk v době dosažení cíle', () => {
    const summary = summarise(input, 30_000_000, 35);
    expect(summary.ageAtGoal).toBe(35 + summary.years!);
  });

  it('bez zadaného věku věk nevymýšlí', () => {
    expect(summarise(input, 30_000_000).ageAtGoal).toBeNull();
  });

  it('u nedosažitelného cíle nevrací ani dobu, ani reálnou hodnotu', () => {
    const summary = summarise(
      { ...input, monthlyContribution: 0, annualReturn: 0 },
      30_000_000,
      35,
    );
    expect(summary.months).toBeNull();
    expect(summary.years).toBeNull();
    expect(summary.ageAtGoal).toBeNull();
    expect(summary.targetInTodaysMoney).toBeNull();
  });

  it('postup drží v mezích nula až sto', () => {
    expect(summarise(input, 30_000_000).progressPct).toBeGreaterThan(0);
    expect(summarise(input, 30_000_000).progressPct).toBeLessThan(1);
    expect(summarise({ ...input, presentValue: 40_000_000 }, 30_000_000).progressPct)
      .toBe(100);
  });

  it('nulový cíl nevyrobí dělení nulou', () => {
    expect(summarise(input, 0).progressPct).toBe(0);
  });

  it('cíl přepočítá na dnešní kupní sílu', () => {
    // Třicet milionů za devatenáct let není dnešních třicet milionů,
    // a aplikace to nesmí zamlčet.
    const summary = summarise(input, 30_000_000, 35);
    expect(summary.targetInTodaysMoney).toBeLessThan(30_000_000);
  });
});

describe('futureValueStaged', () => {
  const change = { afterYears: 5, monthlyContribution: 8_000 };

  it('bez zlomu se chová jako futureValue', () => {
    expect(futureValueStaged(260_000, 20_000, 0.15, 204)).toBe(
      futureValue(260_000, 20_000, 0.15, 204),
    );
  });

  it('před zlomem se chová jako futureValue', () => {
    // Zlom v pátém roce nesmí ovlivnit nic, co je před ním.
    expect(futureValueStaged(260_000, 20_000, 0.15, 48, change)).toBe(
      futureValue(260_000, 20_000, 0.15, 48),
    );
  });

  it('po zlomu je výsledek nižší, když vklad klesne', () => {
    const bez = futureValueStaged(260_000, 20_000, 0.15, 204);
    const se = futureValueStaged(260_000, 20_000, 0.15, 204, change);
    expect(se).toBeLessThan(bez);
  });

  it('navazuje spojitě — dva úseky dají totéž co jeden při stejném vkladu', () => {
    const jeden = futureValue(260_000, 20_000, 0.15, 204);
    const dva = futureValueStaged(260_000, 20_000, 0.15, 204, {
      afterYears: 5,
      monthlyContribution: 20_000,
    });
    expect(dva).toBeCloseTo(jeden, 6);
  });
});

describe('contributedAt', () => {
  it('sčítá oba úseky, ne jen ten první', () => {
    // 5 let po 20 000 a 12 let po 8 000, k tomu dnešní hodnota.
    const change = { afterYears: 5, monthlyContribution: 8_000 };
    expect(contributedAt(260_000, 20_000, 204, change)).toBe(
      260_000 + 20_000 * 60 + 8_000 * 144,
    );
  });

  it('bez zlomu je to prostý součet', () => {
    expect(contributedAt(260_000, 20_000, 204)).toBe(260_000 + 20_000 * 204);
  });
});

describe('sustainableMonthlyIncome', () => {
  it('dělí roční výběr na měsíce', () => {
    expect(sustainableMonthlyIncome(12_000_000, 0.04)).toBeCloseTo(40_000, 6);
  });

  it('výchozí sazba je nižší než slavná čtyři procenta', () => {
    // Odchod v padesáti = čtyřicet let výběru, ne třicet.
    expect(SAFE_WITHDRAWAL_RATE).toBeLessThan(0.04);
  });

  it('ze záporného nebo nulového jmění nerentuje', () => {
    expect(sustainableMonthlyIncome(0)).toBe(0);
    expect(sustainableMonthlyIncome(-1)).toBe(0);
  });
});

describe('retirementOutlook', () => {
  const vstup = { presentValue: 260_000, monthlyContribution: 20_000, annualReturn: 0.15 };

  it('vrací null, když je odchod dnes nebo v minulosti', () => {
    // Nula by byla odpověď. Tohle není odpověď.
    expect(retirementOutlook(vstup, 50, 50)).toBeNull();
    expect(retirementOutlook(vstup, 55, 50)).toBeNull();
  });

  it('reálná hodnota je nižší než nominální', () => {
    const v = retirementOutlook(vstup, 33, 50)!;
    expect(v.years).toBe(17);
    expect(v.real).toBeLessThan(v.nominal);
    expect(v.real).toBeCloseTo(realValue(v.nominal, 17, DEFAULT_INFLATION), 6);
  });

  it('renta se počítá z dnešní kupní síly, ne z nominálu', () => {
    // Míchat nominální jmění s dnešními výdaji je nejběžnější
    // způsob, jak si o důchodu lhát.
    const v = retirementOutlook(vstup, 33, 50)!;
    expect(v.monthlyIncome).toBeCloseTo(sustainableMonthlyIncome(v.real), 6);
    expect(v.monthlyIncome).toBeLessThan(sustainableMonthlyIncome(v.nominal));
  });

  it('hypotéka sníží rentu', () => {
    const bez = retirementOutlook(vstup, 33, 50)!;
    const se = retirementOutlook(
      { ...vstup, contributionChange: { afterYears: 3, monthlyContribution: 8_000 } },
      33,
      50,
    )!;
    expect(se.monthlyIncome).toBeLessThan(bez.monthlyIncome);
    expect(se.contributed).toBeLessThan(bez.contributed);
  });
});

describe('skutečný scénář domácnosti', () => {
  /*
   * Regresní pojistka na číslo, které stojí v hlavičce záložky Cíl.
   *
   * Rozsah, ne přesná hodnota: přesnou by rozbila každá záměrná změna
   * inflace nebo sazby výběru, a test by pak hlídal zaokrouhlení místo
   * smyslu. Rozsah zachytí to, na čem záleží — že se řádově nepohnulo
   * něco, co lidem říká, kolik budou mít v důchodu.
   */
  const vstup = {
    presentValue: 260_000,      // dnešní portfolio
    monthlyContribution: 20_000,
    annualReturn: 0.15,
  };

  it('při 15 % vyjde renta v desítkách tisíc, ne ve stovkách', () => {
    const v = retirementOutlook(vstup, 33, 50)!;
    expect(v.nominal).toBeGreaterThan(20_000_000);
    expect(v.nominal).toBeLessThan(23_000_000);
    expect(v.monthlyIncome).toBeGreaterThan(38_000);
    expect(v.monthlyIncome).toBeLessThan(46_000);
  });

  it('při 10 % je renta zhruba poloviční — proto ta druhá karta', () => {
    const strizlivy = retirementOutlook({ ...vstup, annualReturn: 0.10 }, 33, 50)!;
    const cilovy = retirementOutlook(vstup, 33, 50)!;
    expect(strizlivy.monthlyIncome).toBeLessThan(cilovy.monthlyIncome * 0.6);
  });
});
