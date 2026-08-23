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
  contributionAtHorizon,
  DEFAULT_INFLATION,
  project,
  RETURN_SPREAD_PP,
  summarise,
} from '../../lib/compound';
import { czk, duration, estimate, percent, plural } from '../../lib/format';
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
const DEFAULT_AGE = 35;
const DEFAULT_CONTRIBUTION = 20_000;

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
  }), [form, portfolioValue, liveContribution]);

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
      },
      state.target,
      state.currentAge,
    ),
    [state, annualReturn],
  );

  // Graf sahá rok za cíl — jen tolik, aby bylo vidět, že křivka pokračuje.
  // Víc ne: při patnácti procentech ročně by přestřelení osu roztáhlo
  // natolik, že by se meta zmáčkla ke dnu grafu.
  const horizon = summary.years !== null
    ? Math.min(60, Math.max(5, summary.years + 1))
    : FALLBACK_HORIZON;

  const points = useMemo(
    () => project({
      presentValue: state.presentValue,
      monthlyContribution: state.monthlyContribution,
      annualReturn,
      years: horizon,
    }),
    [state, annualReturn, horizon],
  );

  const atGoal = summary.years !== null
    ? points[Math.min(points.length - 1, summary.years)]
    : points[points.length - 1];

  const oneDeposit = contributionAtHorizon(
    state.monthlyContribution,
    annualReturn,
    summary.years ?? horizon,
  );

  const reachable = summary.months !== null;

  return (
    <div className="flex flex-col gap-4">

      {/* ---- panel: kde jsme, kam míříme ------------------------------- */}

      <section className="panel rounded-card px-5 py-5">
        <div className="flex items-center gap-2">
          <Target size={15} className="text-frame-muted" aria-hidden="true" />
          <h2 className="eyebrow text-frame-muted">Cíl</h2>
        </div>

        <div className="mt-3 flex flex-wrap items-baseline gap-x-4 gap-y-1">
          <span className="font-display text-2xl font-semibold tabular-nums tracking-tight text-frame-text">
            {czk(state.presentValue)}
          </span>
          <span className="text-frame-muted" aria-hidden="true">→</span>
          <span className="font-display text-2xl font-bold tracking-tight text-frame-text">
            {estimate(state.target)}
          </span>
        </div>

        <p className="mt-2 max-w-[68ch] text-[14px] leading-relaxed text-frame-muted">
          {reachable ? (
            <>
              Při vkladu {czk(state.monthlyContribution)} měsíčně a výnosu{' '}
              {percent(state.annualReturnPct)} <Term id="pa">p.&nbsp;a.</Term> za{' '}
              <strong className="font-medium text-frame-text">
                {duration(summary.months)}
              </strong>
              {summary.ageAtGoal !== null && <> — ve věku {summary.ageAtGoal} let</>}.
            </>
          ) : (
            <>
              Při vkladu {czk(state.monthlyContribution)} měsíčně a výnosu{' '}
              {percent(state.annualReturnPct)} <Term id="pa">p.&nbsp;a.</Term>{' '}
              <strong className="font-medium text-frame-text">
                se tenhle cíl nedá splnit
              </strong>
              . Není to chyba výpočtu — vklady rostou pomaleji, než by bylo třeba.
              Zkus vyšší vklad, delší dobu, nebo nižší cíl.
            </>
          )}
        </p>
      </section>

      {/* ---- list: graf + kalkulačka ----------------------------------- */}

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1fr_340px]">

        <section className="sheet">
          <div className="sheet-head">
            <h3 className="sheet-title">Dráha portfolia</h3>
            <span className="ml-auto font-mono text-[11px] text-sheet-muted">
              {horizon} {plural(horizon, 'rok', 'roky', 'let')} dopředu
            </span>
          </div>

          <div className="px-2 pt-4">
            <ProjectionChart
              points={points}
              target={state.target}
              goalYear={summary.years}
            />
          </div>

          {/* Legenda vysvětluje, které vrstvě se dá věřit. */}
          <div className="flex flex-wrap items-center gap-x-5 gap-y-2 border-t border-sheet-rule px-4 py-3">
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

          <div className="border-t border-sheet-rule px-4 py-3">
            <MilestoneLadder current={state.presentValue} target={state.target} />
          </div>
        </section>

        <section className="sheet self-start">
          <div className="sheet-head">
            <h3 className="sheet-title">Kalkulačka</h3>
          </div>
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
            })}
          />
        </section>
      </div>

      {/* ---- list: co z toho plyne ------------------------------------- */}

      <section className="sheet">
        <div className="sheet-head">
          <h3 className="sheet-title">Co z toho plyne</h3>
        </div>

        <dl className="grid grid-cols-1 divide-y divide-sheet-rule sm:grid-cols-3 sm:divide-x sm:divide-y-0">

          <div className="px-4 py-4">
            <dt className="text-[12.5px] text-sheet-muted">
              Kolik vložíš a kolik přidá trh
            </dt>
            <dd className="mt-2">
              <div className="flex items-baseline justify-between gap-3">
                <span className="text-[12.5px] text-sheet-muted">vložíš</span>
                <span className="font-mono text-[15px] text-sheet-text">
                  {estimate(atGoal.contributed)}
                </span>
              </div>
              <div className="mt-1 flex items-baseline justify-between gap-3">
                <span className="text-[12.5px] text-sheet-muted">přidá trh</span>
                <span className="font-mono text-[15px] text-signal-green">
                  {atGoal.growth > 0 ? estimate(atGoal.growth) : '—'}
                </span>
              </div>
              <p className="mt-2 text-[12px] leading-relaxed text-sheet-faint">
                {atGoal.growth > atGoal.contributed
                  ? 'Po téhle době přidá trh víc, než kolik sám odložíš. To je celý smysl toho čekat.'
                  : 'Zatím převažuje to, co odložíš. Zlom přijde později — čím delší doba, tím větší podíl výnosu.'}
              </p>
            </dd>
          </div>

          <div className="px-4 py-4">
            <dt className="text-[12.5px] text-sheet-muted">
              Co za to bude ke koupi
            </dt>
            <dd className="mt-2">
              <span className="font-mono text-[17px] text-sheet-text">
                {summary.targetInTodaysMoney !== null
                  ? estimate(summary.targetInTodaysMoney)
                  : '—'}
              </span>
              <p className="mt-2 text-[12px] leading-relaxed text-sheet-faint">
                {summary.targetInTodaysMoney !== null ? (
                  <>
                    Tolik je {estimate(state.target)} v cílovém roce v dnešní{' '}
                    <Term id="realnaHodnota">kupní síle</Term> při inflaci{' '}
                    {percent(DEFAULT_INFLATION * 100)} ročně. Nominální cíl slibuje víc,
                    než kolik ta částka koupí.
                  </>
                ) : (
                  <>Dokud není cíl dosažitelný, není co přepočítávat.</>
                )}
              </p>
            </dd>
          </div>

          <div className="px-4 py-4">
            <dt className="text-[12.5px] text-sheet-muted">
              Co udělá jeden dnešní vklad
            </dt>
            <dd className="mt-2">
              <span className="font-mono text-[17px] text-sheet-text">
                {estimate(oneDeposit)}
              </span>
              <p className="mt-2 text-[12px] leading-relaxed text-sheet-faint">
                Tolik bude z dnešních {czk(state.monthlyContribution)} v cíli, když
                se jich nikdo nedotkne. Jeden vklad, úročený celou dobu —
                ne rozdíl dvou scénářů.
              </p>
            </dd>
          </div>
        </dl>

        <p className="flex gap-2 border-t border-sheet-rule px-4 py-3 text-[12px] leading-relaxed text-sheet-muted">
          <Info size={13} className="mt-0.5 shrink-0" aria-hidden="true" />
          <span>
            Všechna čísla na téhle stránce kromě dnešní hodnoty portfolia jsou
            projekce, ne předpověď. Vycházejí z jediného předpokladu — konstantního
            výnosu — a ten trh nikdy nedodrží. Skutečná dráha bude hrbolatější
            v obou směrech; proto je v grafu pás a ne čára.
          </span>
        </p>
      </section>
    </div>
  );
};

export default GoalPage;
