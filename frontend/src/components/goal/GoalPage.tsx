/**
 * GoalPage — kde jsme a kam míříme.
 *
 * Sloučená záložka: dřívější Freedom a Platby. Freedom byla z poloviny
 * gamifikace (odznaky, duchové, hrady) a Platby pětkrát prázdný stav
 * s velkou zelenou fajfkou. Zůstalo z toho jedno: kalkulačka a graf.
 *
 * Motivace tu nestojí na oslavných hláškách, ale na jednom skutečném
 * faktu — po dost dlouhé době přidá trh víc, než kolik člověk vloží.
 * To se dá ukázat poctivě a je to silnější než konfety.
 *
 * Co se sem naopak vědomě nevrátilo: „Za 15 let budeš mít
 * 15 552 907,74 Kč". Projekce se vysází nahrubo, protože nahrubo je
 * všechno, co se o ní dá tvrdit.
 */

import React, { useEffect, useMemo, useState } from 'react';
import { Info, Target } from 'lucide-react';
import { apiClient } from '../../api/client';
import {
  type ContributionChange,
  contributionAtHorizon,
  DEFAULT_INFLATION,
  project,
  retirementOutlook,
  RETURN_SPREAD_PP,
  SAFE_WITHDRAWAL_RATE,
  summarise,
} from '../../lib/compound';
import { czk, estimate, percent, plural } from '../../lib/format';
import Term from '../ui/Term';
import CalculatorControls, { type CalculatorState } from './CalculatorControls';
import MilestoneLadder from './MilestoneLadder';
import ProjectionChart from './ProjectionChart';

interface GoalPageProps {
  /** Skutečná hodnota portfolia včetně hotovosti. */
  portfolioValue: number;
  /** Měsíční vklad nastavený v portfoliu. */
  monthlyContribution: number;
}

const DEFAULT_TARGET = 30_000_000;
const DEFAULT_RETURN_PCT = 15;
const DEFAULT_AGE = 33;
const DEFAULT_RETIREMENT_AGE = 50;
const DEFAULT_CONTRIBUTION = 20_000;

/**
 * Střízlivý scénář: dlouhodobý průměr širokého akciového trhu.
 *
 * Nestojí tu jako předpověď, ale jako protiváha. Patnáct procent
 * sedmnáct let v řadě je horní hranice toho, co se komu povedlo —
 * plánovat na ně je v pořádku, stavět na nich jediné číslo na obrazovce
 * není. Karta se vykreslí jen tehdy, když je zadaný výnos vyšší; jinak
 * by opakovala totéž podruhé.
 */
const SOBER_RETURN_PCT = 10;

/**
 * Stav formuláře. `null` u prvních dvou polí znamená „ber skutečnou
 * hodnotu z portfolia"; číslo znamená, že si ji člověk přepsal.
 */
interface FormState {
  presentValue: number | null;
  monthlyContribution: number | null;
  annualReturnPct: number;
  target: number;
  currentAge: number;
  retirementAge: number;
  changeAfterYears: number;
  changeContribution: number;
}

/** O kolik let dopředu graf kreslí, když cíl leží dál nebo vůbec. */
const FALLBACK_HORIZON = 25;

export const GoalPage: React.FC<GoalPageProps> = ({
  portfolioValue,
  monthlyContribution,
}) => {
  /*
   * Dvě pole kalkulačky mají skutečnou předlohu v portfoliu: dnešní hodnota
   * a měsíční vklad. Ta se navíc načítá až po prvním vykreslení.
   *
   * `null` znamená „drž se skutečnosti". Jakmile člověk posuvníkem hodnotu
   * změní, uloží se jako přepis a živá data ji už nepřebijí.
   *
   * Dřív se to řešilo efektem, který skutečnou hodnotu kopíroval do stavu.
   * To spouští další vykreslení kvůli údaji, který nikdy nebyl stavem —
   * je odvozený. Takhle žádný efekt není potřeba.
   */
  const [form, setForm] = useState<FormState>({
    presentValue: null,
    monthlyContribution: null,
    annualReturnPct: DEFAULT_RETURN_PCT,
    target: DEFAULT_TARGET,
    currentAge: DEFAULT_AGE,
    retirementAge: DEFAULT_RETIREMENT_AGE,
    // Nula = s hypotékou se nepočítá. Zapnutí přepínačem nastaví oboje.
    changeAfterYears: 0,
    changeContribution: 8_000,
  });

  const [indexTrendPct, setIndexTrendPct] = useState<number | null>(null);

  const liveContribution = monthlyContribution || DEFAULT_CONTRIBUTION;

  // Musí to být useMemo, ne prostý objekt: nová reference při každém
  // vykreslení by zneplatnila projekci níž, takže by se počítala pořád
  // dokola, i když se nic nezměnilo.
  const state: CalculatorState = useMemo(() => ({
    presentValue: form.presentValue ?? portfolioValue,
    monthlyContribution: form.monthlyContribution ?? liveContribution,
    annualReturnPct: form.annualReturnPct,
    target: form.target,
    currentAge: form.currentAge,
    retirementAge: form.retirementAge,
    changeAfterYears: form.changeAfterYears,
    changeContribution: form.changeContribution,
  }), [form, portfolioValue, liveContribution]);

  // Zlom vzniká, jen když je přepínač zapnutý. Objekt se musí memoizovat
  // ze stejného důvodu jako `state`: nová reference by přepočítala projekci
  // při každém vykreslení.
  const contributionChange: ContributionChange | undefined = useMemo(
    () => (state.changeAfterYears > 0
      ? { afterYears: state.changeAfterYears, monthlyContribution: state.changeContribution }
      : undefined),
    [state.changeAfterYears, state.changeContribution],
  );

  // Dlouhodobý trend indexu jako opora u pole s očekávaným výnosem.
  // Když se nenačte, pole funguje dál — jen bez opory.
  useEffect(() => {
    let alive = true;
    apiClient
      .getMarketGauge()
      .then((gauge) => {
        if (alive) setIndexTrendPct(gauge.trend_pct_per_year);
      })
      .catch(() => {
        /* Ukazatel není povinný. Kalkulačka na něm nestojí. */
      });
    return () => {
      alive = false;
    };
  }, []);

  const annualReturn = state.annualReturnPct / 100;

  const summary = useMemo(
    () => summarise(
      {
        presentValue: state.presentValue,
        monthlyContribution: state.monthlyContribution,
        annualReturn,
        years: FALLBACK_HORIZON,
        contributionChange,
      },
      state.target,
      state.currentAge,
    ),
    [state, annualReturn, contributionChange],
  );

  /*
   * Výhled k důchodu odpovídá na jinou otázku než `summary`.
   *
   * `summary` řeší „za jak dlouho na částku". Když má člověk pevné datum
   * odchodu, je správná otázka opačná: částka není vstup, ale výsledek —
   * a to, co z ní opravdu plyne, není číslo na účtu, ale kolik z něj
   * půjde měsíčně brát, aniž by došlo.
   */
  const outlook = useMemo(
    () => retirementOutlook(
      {
        presentValue: state.presentValue,
        monthlyContribution: state.monthlyContribution,
        annualReturn,
        contributionChange,
      },
      state.currentAge,
      state.retirementAge,
    ),
    [state, annualReturn, contributionChange],
  );

  // Střízlivá varianta nikdy neleze nad zadaný výnos. Kdyby si člověk
  // zadal osm procent, „střízlivých deset" by byl optimismus navíc.
  const soberReturnPct = Math.min(state.annualReturnPct, SOBER_RETURN_PCT);

  const soberOutlook = useMemo(
    () => retirementOutlook(
      {
        presentValue: state.presentValue,
        monthlyContribution: state.monthlyContribution,
        annualReturn: soberReturnPct / 100,
        contributionChange,
      },
      state.currentAge,
      state.retirementAge,
    ),
    [state, soberReturnPct, contributionChange],
  );

  // Graf sahá rok za cíl — jen tolik, aby bylo vidět, že křivka pokračuje.
  // Víc ne: při patnácti procentech ročně by přestřelení osu roztáhlo
  // natolik, že by se meta zmáčkla ke dnu grafu.
  /*
   * Graf sahá po odchod do důchodu, ne po dosažení částky.
   *
   * Dřív se osa řídila cílem, takže při nedosažitelném cíli spadla na
   * náhradních dvacet pět let a datum odchodu na ní nebylo vidět vůbec.
   * Když je odchod ta rozhodující chvíle, musí být na ose vždycky —
   * i (a hlavně) když se do ní cíl nestihne.
   */
  const horizon = outlook !== null
    ? Math.min(60, Math.max(5, outlook.years))
    : FALLBACK_HORIZON;

  const points = useMemo(
    () => project({
      presentValue: state.presentValue,
      monthlyContribution: state.monthlyContribution,
      annualReturn,
      years: horizon,
      contributionChange,
    }),
    [state, annualReturn, horizon, contributionChange],
  );

  // Poslední bod dráhy JE den odchodu — osa se od něj odvíjí (viz `horizon`).
  const atRetirement = points[points.length - 1];

  const oneDeposit = contributionAtHorizon(
    state.monthlyContribution,
    annualReturn,
    horizon,
  );

  const reachable = summary.months !== null;

  return (
    /* Rozestupy jsou o stupeň těsnější, než by byly na samostatné
       stránce: Cíl je jedna z obrazovek aplikace, která nescrolluje,
       a devadesát pixelů vzduchu mezi bloky stálo přesně to, kvůli
       čemu se muselo rolovat k „Co z toho plyne". */
    <div className="flex h-full min-h-0 flex-col gap-2">

      {/* ---- panel: kde jsme, kam míříme ------------------------------- */}

      <section className="panel shrink-0 rounded-card px-5 py-2.5">
        {/* Nadpis „CÍL" tu stál nad číslem, které je pod položkou Cíl
            v levém menu, na které se právě stojí. Ikona zůstala, řádek ne. */}
        {/* Vede renta, ne cílová částka. Jmění je mezivýsledek —
            otázka „na co nám to bude stačit" je ta, kvůli které se
            odkládá. */}
        <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
          <Target size={15} className="self-center text-frame-muted" aria-hidden="true" />
          <span className="font-display text-2xl font-semibold tabular-nums tracking-tight text-frame-text">
            {czk(state.presentValue)}
          </span>
          <span className="text-frame-muted" aria-hidden="true">→</span>
          {outlook !== null ? (
            <>
              <span className="font-display text-2xl font-bold tracking-tight text-frame-text">
                {estimate(outlook.real)}
              </span>
              <span className="text-[12.5px] text-frame-muted">
                v {state.retirementAge} letech, v dnešní{' '}
                <Term id="realnaHodnota">kupní síle</Term>
              </span>

              <span
                className="ml-auto flex items-baseline gap-2"
                title={`Udržitelný roční výběr ${percent(SAFE_WITHDRAWAL_RATE * 100)} z portfolia. Slavná čtyři procenta jsou spočítaná na třicet let důchodu; odchod v ${state.retirementAge} znamená spíš čtyřicet, a na tom horizontu čtyři procenta historicky selhávala.`}
              >
                <span className="text-[12.5px] text-frame-muted">renta</span>
                <span className="font-display text-2xl font-bold tabular-nums tracking-tight text-signal-green">
                  {czk(outlook.monthlyIncome)}
                </span>
                <span className="text-[12.5px] text-frame-muted">měsíčně</span>
              </span>
            </>
          ) : (
            <span className="text-[13px] text-frame-muted">
              Odchod je zadaný dřív než dnešek — není co promítat.
            </span>
          )}
        </div>

        <p className="mt-1.5 max-w-[74ch] text-[13.5px] leading-snug text-frame-muted">
          Při vkladu {czk(state.monthlyContribution)} měsíčně
          {contributionChange && (
            <> — a {czk(contributionChange.monthlyContribution)} od{' '}
              {contributionChange.afterYears}. roku, až začne splátka</>
          )}
          {' '}a výnosu {percent(state.annualReturnPct)} <Term id="pa">p.&nbsp;a.</Term>{' '}
          {reachable && summary.ageAtGoal !== null ? (
            <>
              Cílových {estimate(state.target)} padne{' '}
              <strong className="font-medium text-frame-text">
                ve věku {summary.ageAtGoal} let
              </strong>
              {summary.ageAtGoal > state.retirementAge && (
                <>, tedy {summary.ageAtGoal - state.retirementAge}{' '}
                  {plural(summary.ageAtGoal - state.retirementAge, 'rok', 'roky', 'let')} po
                  odchodu</>
              )}.
            </>
          ) : (
            <>
              Cílových {estimate(state.target)}{' '}
              <strong className="font-medium text-frame-text">
                se při tomhle plánu nedosáhne
              </strong>
              . Není to chyba výpočtu — vklady rostou pomaleji, než by bylo třeba.
            </>
          )}
        </p>
      </section>

      {/* ---- list: graf + kalkulačka ----------------------------------- */}

      <div className="grid min-h-0 flex-1 grid-cols-1 gap-3 xl:grid-cols-[1fr_340px]">

        <section className="sheet flex min-h-0 flex-col">
          <div className="sheet-head shrink-0 py-2">
            <h3 className="sheet-title">Dráha portfolia</h3>
            <span className="ml-auto font-mono text-[11px] text-sheet-muted">
              {horizon} {plural(horizon, 'rok', 'roky', 'let')} dopředu
            </span>
          </div>

          {/* Graf bere zbylou výšku. Legenda a mezníky pod ním mají
              pevný obsah, takže se nesmí smrsknout. */}
          <div className="min-h-[140px] flex-1 px-2 pt-2">
            <ProjectionChart
              points={points}
              target={state.target}
              goalYear={summary.years}
            />
          </div>

          {/* Legenda vysvětluje, které vrstvě se dá věřit. */}
          <div className="flex shrink-0 flex-wrap items-center gap-x-5 gap-y-2 border-t border-sheet-rule px-4 py-2">
            <span className="flex items-center gap-2 text-[11.5px] text-sheet-muted">
              <span className="h-0.5 w-5 bg-signal-green" aria-hidden="true" />
              očekávaná dráha
            </span>
            <span className="flex items-center gap-2 text-[11.5px] text-sheet-muted">
              <span
                className="h-3 w-5 bg-signal-green/20"
                aria-hidden="true"
              />
              rozpětí {percent(Math.max(0, state.annualReturnPct - RETURN_SPREAD_PP * 100), { digits: 0 })} až {percent(state.annualReturnPct + RETURN_SPREAD_PP * 100, { digits: 0 })} ročně
            </span>
            <span className="flex items-center gap-2 text-[11.5px] text-sheet-muted">
              <span
                className="h-3 w-5 border-y border-dashed border-sheet-faint bg-sheet-faint/20"
                aria-hidden="true"
              />
              vložený kapitál — jediná vrstva, která není odhad
            </span>
          </div>

          <div className="shrink-0 border-t border-sheet-rule px-4 py-2">
            <MilestoneLadder current={state.presentValue} target={state.target} />
          </div>
        </section>

        <section className="sheet flex min-h-0 flex-col self-stretch overflow-hidden">
          <div className="sheet-head shrink-0 py-2">
            <h3 className="sheet-title">Kalkulačka</h3>
          </div>
          {/* Na nízkém okně roluje kalkulačka sama v sobě. Stránka ne. */}
          <div className="min-h-0 flex-1 overflow-y-auto">
          <CalculatorControls
            value={state}
            actualValue={portfolioValue}
            indexTrendPct={indexTrendPct}
            onChange={(next) => setForm({
              // Vrátí-li se hodnota na skutečnou, přepis se zruší a pole
              // zase sleduje portfolio.
              presentValue: Math.round(next.presentValue) === Math.round(portfolioValue)
                ? null
                : next.presentValue,
              monthlyContribution: next.monthlyContribution === liveContribution
                ? null
                : next.monthlyContribution,
              annualReturnPct: next.annualReturnPct,
              target: next.target,
              currentAge: next.currentAge,
              retirementAge: next.retirementAge,
              changeAfterYears: next.changeAfterYears,
              changeContribution: next.changeContribution,
            })}
          />
          </div>
        </section>
      </div>

      {/* ---- list: co z toho plyne ------------------------------------- */}

      <section className="sheet shrink-0">
        {/* Upozornění, že jde o projekce, stálo pod pruhem jako čtyřřádkový
            odstavec — a bralo tolik výšky, že kalkulačka vedle grafu musela
            rolovat. Patří k nadpisu, ne za čísla, tak je u něj. */}
        <div className="sheet-head py-2">
          <h3 className="sheet-title">Co z toho plyne</h3>
          <span className="ml-auto flex items-center gap-1.5 text-[11.5px] text-sheet-muted">
            <Info size={12} className="shrink-0" aria-hidden="true" />
            <span title="Vycházejí z jediného předpokladu — konstantního výnosu — a ten trh nikdy nedodrží. Skutečná dráha bude hrbolatější v obou směrech; proto je v grafu pás a ne čára.">
              kromě dnešní hodnoty portfolia jsou všechna čísla projekce, ne předpověď
            </span>
          </span>
        </div>

        <dl className="grid grid-cols-1 divide-y divide-sheet-rule sm:grid-cols-3 sm:divide-x sm:divide-y-0">

          <div className="px-4 py-2">
            <dt className="text-[12.5px] text-sheet-muted">
              Kolik vložíš a kolik přidá trh
            </dt>
            <dd className="mt-1">
              <div className="flex items-baseline justify-between gap-3">
                <span className="text-[12.5px] text-sheet-muted">vložíš</span>
                <span className="font-mono text-[15px] text-sheet-text">
                  {estimate(atRetirement.contributed)}
                </span>
              </div>
              <div className="mt-1 flex items-baseline justify-between gap-3">
                <span className="text-[12.5px] text-sheet-muted">přidá trh</span>
                <span className="font-mono text-[15px] text-signal-green">
                  {atRetirement.growth > 0 ? estimate(atRetirement.growth) : '—'}
                </span>
              </div>
              <p className="mt-1.5 text-[12px] leading-snug text-sheet-faint">
                {atRetirement.growth > atRetirement.contributed
                  ? 'Po téhle době přidá trh víc, než kolik sám odložíš. To je celý smysl toho čekat.'
                  : 'Zatím převažuje to, co odložíš. Zlom přijde později — čím delší doba, tím větší podíl výnosu.'}
              </p>
            </dd>
          </div>

          {/* Protiváha k jedinému číslu v hlavičce. Patnáct procent je cíl,
              ne příslib — a plán, který se rozsype při deseti, je křehký
              způsob, jak si stavět důchod. */}
          <div className="px-4 py-2">
            <dt className="text-[12.5px] text-sheet-muted">
              Když to nevyjde na {percent(state.annualReturnPct)}
            </dt>
            <dd className="mt-1">
              {soberOutlook !== null && soberReturnPct < state.annualReturnPct ? (
                <>
                  <div className="flex items-baseline justify-between gap-3">
                    <span className="text-[12.5px] text-sheet-muted">
                      při {percent(soberReturnPct)}
                    </span>
                    <span className="font-mono text-[15px] text-sheet-text">
                      {estimate(soberOutlook.real)}
                    </span>
                  </div>
                  <div className="mt-1 flex items-baseline justify-between gap-3">
                    <span className="text-[12.5px] text-sheet-muted">renta</span>
                    <span className="font-mono text-[15px] text-sheet-text">
                      {czk(soberOutlook.monthlyIncome)}
                    </span>
                  </div>
                  <p className="mt-1.5 text-[12px] leading-snug text-sheet-faint">
                    Dlouhodobý průměr širokého trhu, v dnešní{' '}
                    <Term id="realnaHodnota">kupní síle</Term> při inflaci{' '}
                    {percent(DEFAULT_INFLATION * 100)}. Není to předpověď, ale
                    protiváha — {percent(state.annualReturnPct)} po celých{' '}
                    {horizon} {plural(horizon, 'rok', 'roky', 'let')} je horní
                    hranice toho, co se komu kdy povedlo.
                  </p>
                </>
              ) : (
                <p className="text-[12px] leading-snug text-sheet-faint">
                  Zadaný výnos {percent(state.annualReturnPct)} je sám o sobě
                  střízlivý — druhý scénář by opakoval totéž.
                </p>
              )}
            </dd>
          </div>

          <div className="px-4 py-2">
            <dt className="text-[12.5px] text-sheet-muted">
              Co udělá jeden dnešní vklad
            </dt>
            <dd className="mt-1">
              <span className="font-mono text-[17px] text-sheet-text">
                {estimate(oneDeposit)}
              </span>
              <p className="mt-1.5 text-[12px] leading-snug text-sheet-faint">
                Tolik bude z dnešních {czk(state.monthlyContribution)} v den
                odchodu, když se jich nikdo nedotkne. Jeden vklad, úročený celou
                dobu — ne rozdíl dvou scénářů.
              </p>
            </dd>
          </div>
        </dl>

      </section>
    </div>
  );
};

export default GoalPage;
