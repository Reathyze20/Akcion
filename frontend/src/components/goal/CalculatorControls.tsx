/**
 * Ovládání kalkulačky.
 *
 * Každý vstup má posuvník i pole pro číslo. Posuvník je na hraní —
 * chci vidět, co udělá tisícovka navíc — pole na přesné zadání.
 *
 * U očekávaného výnosu stojí vedle posuvníku dlouhodobý trend indexu,
 * který si aplikace spočítala z vlastních dat. Bez něj je pole
 * s hodnotou 15 % pozvánka k tomu napsat si tam 30 a uvěřit tomu.
 */

import React from 'react';
import { RotateCcw } from 'lucide-react';
import Term from '../ui/Term';
import { amount, percent } from '../../lib/format';

export interface CalculatorState {
  presentValue: number;
  monthlyContribution: number;
  annualReturnPct: number;
  target: number;
  currentAge: number;
  /** Věk, ve kterém se přestává vkládat a začíná vybírat. */
  retirementAge: number;
  /**
   * Hypotéka: po kolika letech klesne vklad. Nula znamená „nepočítat
   * s ní" — pak se ovládání druhého pole vůbec nevykreslí.
   */
  changeAfterYears: number;
  /** Vklad po zlomu. */
  changeContribution: number;
}

interface CalculatorControlsProps {
  value: CalculatorState;
  onChange: (next: CalculatorState) => void;
  /** Skutečná hodnota portfolia — pro tlačítko návratu ke skutečnosti. */
  actualValue: number;
  /** Dlouhodobý trend indexu v procentech ročně, když je znám. */
  indexTrendPct?: number | null;
}

interface FieldProps {
  label: React.ReactNode;
  hint?: React.ReactNode;
  min: number;
  max: number;
  step: number;
  value: number;
  suffix: string;
  onChange: (value: number) => void;
  /** Zobrazení hodnoty v poli i u posuvníku. */
  render?: (value: number) => string;
  action?: React.ReactNode;
}

const Field: React.FC<FieldProps> = ({
  label, hint, min, max, step, value, suffix, onChange, render, action,
}) => {
  const id = React.useId();
  const shown = render ? render(value) : amount(value);

  /*
   * Řádek má dvě patra, ne tři.
   *
   * Třetí patro neslo vlevo hodnotu posuvníku — tedy „233 294" pod polem,
   * ve kterém stálo 233294. Táž číslice dvakrát, o osmnáct pixelů níž.
   * Vysvětlivka z jeho pravé strany se přesunula pod popisek, kam patří,
   * a řádek zhubl z 89 px na necelých šedesát. Pět ovládacích prvků se
   * tak vejde i na okno, kterému panel záložek a lišta oblíbených
   * ukrojily sto padesát pixelů.
   *
   * Údaj `shown` nezmizel: formátovaná hodnota je v `title` pole, takže
   * „30000000" jde ověřit jako „30 000 000" bez počítání nul.
   */
  return (
    <div className="border-b border-sheet-rule px-4 py-1.5 last:border-b-0">
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <label htmlFor={id} className="block truncate text-[13px] font-medium text-sheet-text">
            {label}
          </label>
          {hint && (
            <span className="block text-[11px] leading-tight text-sheet-muted">{hint}</span>
          )}
        </div>
        <div className="flex shrink-0 items-baseline gap-1.5">
          <input
            id={id}
            type="number"
            min={min}
            max={max}
            step={step}
            value={value}
            title={shown}
            onChange={(e) => {
              const next = Number(e.target.value);
              if (Number.isFinite(next)) onChange(Math.min(max, Math.max(min, next)));
            }}
            className="w-24 rounded-input border border-sheet-rule bg-sheet-alt px-2 py-1 text-right font-mono text-[13px] text-sheet-text focus:border-accent focus:outline-none"
          />
          <span className="font-mono text-[11px] text-sheet-muted">{suffix}</span>
          {action}
        </div>
      </div>

      <input
        type="range"
        aria-label={typeof label === 'string' ? label : undefined}
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="mt-1.5 h-1 w-full cursor-pointer appearance-none rounded bg-sheet-rule accent-[rgb(var(--accent))]"
      />
    </div>
  );
};

export const CalculatorControls: React.FC<CalculatorControlsProps> = ({
  value, onChange, actualValue, indexTrendPct,
}) => {
  const set = <K extends keyof CalculatorState>(key: K, next: CalculatorState[K]) =>
    onChange({ ...value, [key]: next });

  const edited = Math.round(value.presentValue) !== Math.round(actualValue);

  return (
    <div>
      <Field
        label="Dnešní hodnota portfolia"
        min={0}
        max={5_000_000}
        step={1_000}
        value={Math.round(value.presentValue)}
        suffix="Kč"
        onChange={(v) => set('presentValue', v)}
        hint={edited ? 'upraveno oproti skutečnosti' : 'skutečný stav'}
        action={edited ? (
          <button
            type="button"
            title="Vrátit skutečnou hodnotu portfolia"
            onClick={() => set('presentValue', actualValue)}
            className="ml-1 rounded-input p-1 text-sheet-muted hover:bg-sheet-alt hover:text-sheet-text"
          >
            <RotateCcw size={12} />
          </button>
        ) : undefined}
      />

      <Field
        label="Měsíční vklad"
        min={0}
        max={100_000}
        step={1_000}
        value={value.monthlyContribution}
        suffix="Kč"
        onChange={(v) => set('monthlyContribution', v)}
        hint={`${amount(value.monthlyContribution * 12)} Kč ročně`}
      />

      <Field
        label={<>Očekávaný roční výnos</>}
        min={0}
        max={25}
        step={0.5}
        value={value.annualReturnPct}
        suffix="% p.a."
        onChange={(v) => set('annualReturnPct', v)}
        render={(v) => percent(v)}
        hint={
          indexTrendPct != null ? (
            <>
              trend indexu {percent(indexTrendPct)}{' '}
              <Term id="pa">p.&nbsp;a.</Term>
            </>
          ) : (
            <Term id="slozeneUroceni">složené úročení</Term>
          )
        }
      />

      <Field
        label="Cílová částka"
        min={500_000}
        max={50_000_000}
        step={500_000}
        value={value.target}
        suffix="Kč"
        onChange={(v) => set('target', v)}
        hint="kdy je hotovo"
      />

      <Field
        label="Dnešní věk"
        min={18}
        max={70}
        step={1}
        value={value.currentAge}
        suffix="let"
        onChange={(v) => set('currentAge', v)}
        render={(v) => `${v} let`}
        hint="pro přepočet na věk v cíli"
      />

      <Field
        label="Odchod do důchodu"
        min={value.currentAge + 1}
        max={75}
        step={1}
        value={value.retirementAge}
        suffix="let"
        onChange={(v) => set('retirementAge', v)}
        render={(v) => `${v} let`}
        hint={`za ${Math.max(0, value.retirementAge - value.currentAge)} let`}
      />

      {/*
        Hypotéka je schovaná za přepínačem schválně. Většinu času je to
        pole navíc, které jen ubírá výšku panelu — a ten je na nízkém okně
        to první, co začne rolovat. Zapnutá odkryje dvě pole, protože bez
        obou je odpověď k ničemu: „kdy" bez „kolik" nic neříká.
      */}
      <div className="border-b border-sheet-rule px-4 py-1.5 last:border-b-0">
        <label className="flex items-center justify-between gap-3">
          <span className="min-w-0">
            <span className="block truncate text-[13px] font-medium text-sheet-text">
              Počítat s hypotékou
            </span>
            <span className="block text-[11px] leading-tight text-sheet-muted">
              splátka sníží vklad, ne výnos
            </span>
          </span>
          <input
            type="checkbox"
            checked={value.changeAfterYears > 0}
            onChange={(e) => set('changeAfterYears', e.target.checked ? 2 : 0)}
            className="size-4 shrink-0 accent-[rgb(var(--accent))]"
          />
        </label>
      </div>

      {value.changeAfterYears > 0 && (
        <>
          <Field
            label="Splátka začne za"
            min={1}
            max={Math.max(1, value.retirementAge - value.currentAge)}
            step={1}
            value={value.changeAfterYears}
            suffix="let"
            onChange={(v) => set('changeAfterYears', v)}
            render={(v) => `${v} let`}
            hint="od té chvíle platí vklad níž"
          />
          <Field
            label="Vklad po splátce"
            min={0}
            max={100_000}
            step={1_000}
            value={value.changeContribution}
            suffix="Kč"
            onChange={(v) => set('changeContribution', v)}
            hint={`${amount(value.changeContribution * 12)} Kč ročně`}
          />
        </>
      )}
    </div>
  );
};

export default CalculatorControls;
