/**
 * RiskMeter — kolik portfolia stojí na růstových sázkách.
 *
 * Původní verze měla vadu, kterou tahle aplikace jinak celou dobu
 * odstraňuje: když nebyla ohodnocená ani jedna pozice, součet vyšel
 * nula, nula prošla prahem „pod 60 %" a vykreslila se zeleně jako
 * `0 %`. Nad portfoliem, které je −42 % a nemá jediné použitelné
 * hodnocení, to bylo jediné velké barevné číslo v hlavičce — a hlásilo
 * klid.
 *
 * Nula a „nemám z čeho počítat" jsou dva různé stavy. Bez ohodnocených
 * pozic se tedy ukáže pomlčka a důvod, ne zelená nula.
 */

import React from 'react';
import { AlertCircle, Anchor, Clock, Rocket } from 'lucide-react';
import Term from './ui/Term';
import { plural } from '../lib/format';

interface RiskMeterProps {
  rocketCount: number;
  anchorCount: number;
  waitTimeCount: number;
  unanalyzedCount: number;
  riskScore: number;
}

interface CategoryProps {
  Icon: typeof Rocket;
  count: number;
  label: string;
  tone: string;
}

const Category: React.FC<CategoryProps> = ({ Icon, count, label, tone }) => (
  <div className="flex flex-col items-center">
    <Icon
      size={15}
      className={`mb-1 ${count > 0 ? tone : 'text-text-muted'}`}
      aria-hidden="true"
    />
    <span className={`font-mono text-sm font-semibold ${count > 0 ? tone : 'text-text-muted'}`}>
      {count}
    </span>
    <span className="mt-0.5 text-[9px] uppercase tracking-wider text-text-muted">
      {label}
    </span>
  </div>
);

export const RiskMeter: React.FC<RiskMeterProps> = ({
  rocketCount,
  anchorCount,
  waitTimeCount,
  unanalyzedCount,
  riskScore,
}) => {
  const judged = rocketCount + anchorCount + waitTimeCount;

  // Bez ohodnocené pozice není z čeho počítat podíl. Prahy se na takový
  // stav vůbec nemají uplatňovat — jinak „nevím" propadne do „v pořádku".
  const measurable = judged > 0;
  const overexposed = measurable && riskScore > 60;
  const dangerous = measurable && riskScore > 70;

  const scoreTone = !measurable
    ? 'text-text-muted'
    : dangerous
      ? 'text-signal-red'
      : overexposed
        ? 'text-signal-amber'
        : 'text-signal-green';

  const edge = dangerous
    ? 'border-negative-border'
    : overexposed
      ? 'border-warning-border'
      : 'border-border';

  return (
    <div className={`rounded-card border bg-surface-raised p-4 ${edge}`}>
      <div className="mb-3 flex items-center justify-between gap-2">
        <div className="eyebrow text-text-muted">Podíl růstových pozic</div>

        {!measurable && (
          <span className="rounded-input bg-surface-active px-2 py-0.5 text-[10px] font-medium text-text-secondary">
            chybí hodnocení
          </span>
        )}
        {overexposed && (
          <span
            className={`rounded-input px-2 py-0.5 text-[10px] font-semibold ${
              dangerous ? 'bg-negative-bg text-negative' : 'bg-warning-bg text-warning'
            }`}
          >
            {dangerous ? 'PŘEVÁŽIT' : 'HLÍDAT'}
          </span>
        )}
      </div>

      <div className={`mb-1 text-center font-display text-3xl font-bold ${scoreTone}`}>
        {measurable ? `${riskScore} %` : '—'}
      </div>

      {/*
        Základ se píše vždy, když není z čeho počítat celý. Podíl spočítaný
        ze dvou pozic z patnácti je pravdivé číslo o dvou pozicích a
        zavádějící číslo o portfoliu — a bez uvedeného základu vypadá
        jako druhé.
      */}
      {!measurable ? (
        <p className="mb-3 text-center text-[11px] leading-snug text-text-muted">
          {unanalyzedCount > 0 ? (
            <>
              {unanalyzedCount}{' '}
              {plural(unanalyzedCount, 'pozice nemá', 'pozice nemají', 'pozic nemá')}{' '}
              <Term id="konvikcniSkore">konvikční skóre</Term>. Dokud ho nemají,
              nejde spočítat, na čem portfolio stojí.
            </>
          ) : (
            <>Není z čeho počítat.</>
          )}
        </p>
      ) : unanalyzedCount > 0 ? (
        <p className="mb-3 text-center text-[11px] leading-snug text-text-muted">
          Počítáno z {judged} {plural(judged, 'pozice', 'pozic', 'pozic')} z{' '}
          {judged + unanalyzedCount}. Zbytek nemá{' '}
          <Term id="konvikcniSkore">konvikční skóre</Term>.
        </p>
      ) : (
        <p className="mb-3 text-center text-[11px] text-text-muted">
          Počítáno ze všech pozic.
        </p>
      )}

      <div className="grid grid-cols-4 gap-1 text-center">
        <Category Icon={Rocket} count={rocketCount} label="Růst" tone="text-accent" />
        <Category Icon={Anchor} count={anchorCount} label="Jádro" tone="text-accent" />
        <Category Icon={Clock} count={waitTimeCount} label="Čekání" tone="text-signal-amber" />
        <Category
          Icon={AlertCircle}
          count={unanalyzedCount}
          label="Nové"
          tone="text-text-secondary"
        />
      </div>

      {overexposed && (
        <p
          className={`mt-2 text-center text-[10.5px] ${
            dangerous ? 'text-negative' : 'text-warning'
          }`}
        >
          {dangerous
            ? 'Růstová část je přes 70 % — portfolio potřebuje převážit.'
            : 'Růstová část je přes 60 % — hlídej, ať dál neroste.'}
        </p>
      )}
    </div>
  );
};

export default RiskMeter;
