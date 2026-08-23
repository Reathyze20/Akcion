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

  return (
    <div className="border-b border-sheet-rule px-4 py-3.5 last:border-b-0">
      <div className="flex items-baseline justify-between gap-3">
        <label htmlFor={id} className="text-[13px] font-medium text-sheet-text">
          {label}
        </label>
        <div className="flex items-baseline gap-1.5">
          <input
            id={id}
            type="number"
            min={min}
            max={max}
            step={step}
            value={value}
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
        className="mt-2.5 h-1 w-full cursor-pointer appearance-none rounded bg-sheet-rule accent-[rgb(var(--accent))]"
      />

      <div className="mt-1 flex items-baseline justify-between">
        <span className="font-mono text-[10.5px] text-sheet-faint">{shown}</span>
        {hint && <span className="text-[11px] text-sheet-muted">{hint}</span>}
      </div>
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
              dlouhodobý trend indexu {percent(indexTrendPct)}{' '}
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
    </div>
  );
};

export default CalculatorControls;
