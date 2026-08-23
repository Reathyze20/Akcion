/**
 * MilestoneLadder — žebřík mezníků.
 *
 * Lineární pruh od nuly k třiceti milionům by dnešní stav vykreslil jako
 * 0,78 % šířky, tedy jako nic. To je sice pravda, ale k ničemu: člověk
 * z toho nevyčte, jak daleko je k dalšímu kroku.
 *
 * Žebřík je proto v logaritmickém měřítku. Nezkresluje — jen říká, že
 * cesta z 233 tisíc na půl milionu a z 15 na 30 milionů je stejný krok:
 * v obou případech zdvojnásobení. Tak složené úročení opravdu funguje.
 */

import React from 'react';
import { amount, czk, estimate } from '../../lib/format';

interface Milestone {
  value: number;
  label: string;
}

const MILESTONES: Milestone[] = [
  { value: 500_000, label: '500 tis.' },
  { value: 1_000_000, label: '1 mil.' },
  { value: 5_000_000, label: '5 mil.' },
  { value: 10_000_000, label: '10 mil.' },
  { value: 30_000_000, label: '30 mil.' },
];

interface MilestoneLadderProps {
  current: number;
  target: number;
}

export const MilestoneLadder: React.FC<MilestoneLadderProps> = ({ current, target }) => {
  // Žebřík vede od dnešního stavu (nebo prvního mezníku, když je stav vyšší)
  // až k cíli. Zahrnou se jen mezníky, které do rozsahu spadají.
  const steps = MILESTONES.filter((m) => m.value <= target);
  const floor = Math.max(1, Math.min(current, steps[0]?.value ?? target) * 0.8);
  const ceiling = Math.max(target, current);

  const logFloor = Math.log10(floor);
  const logSpan = Math.log10(ceiling) - logFloor;

  const pos = (value: number) =>
    logSpan <= 0 ? 0 : ((Math.log10(Math.max(floor, value)) - logFloor) / logSpan) * 100;

  const currentPos = pos(current);
  const next = steps.find((m) => m.value > current);

  return (
    <div>
      <div className="flex items-baseline justify-between">
        <p className="eyebrow text-sheet-muted">Mezníky</p>
        {next && (
          <p className="text-[12px] text-sheet-muted">
            do {next.label} chybí{' '}
            <span className="font-mono text-sheet-text">{czk(next.value - current)}</span>
          </p>
        )}
      </div>

      <div className="relative mt-3 h-9">
        {/* Dráha */}
        <div className="absolute left-0 right-0 top-1.5 h-px bg-sheet-rule" />

        {/* Ušlá část */}
        <div
          className="absolute left-0 top-1.5 h-px bg-signal-green"
          style={{ width: `${currentPos}%` }}
        />

        {/* Mezníky */}
        {steps.map((m) => {
          const reached = current >= m.value;
          return (
            <div
              key={m.value}
              className="absolute top-0 flex -translate-x-1/2 flex-col items-center"
              style={{ left: `${pos(m.value)}%` }}
            >
              <span
                className={`h-3 w-px ${reached ? 'bg-signal-green' : 'bg-sheet-rule'}`}
                aria-hidden="true"
              />
              <span
                className={`mt-1 whitespace-nowrap font-mono text-[10px] ${
                  reached ? 'text-signal-green' : 'text-sheet-faint'
                }`}
              >
                {m.label}
              </span>
            </div>
          );
        })}

        {/* Dnešek */}
        <div
          className="absolute top-0 -translate-x-1/2"
          style={{ left: `${currentPos}%` }}
        >
          <span
            className="block h-3 w-[3px] rounded-sm bg-signal-green"
            aria-hidden="true"
          />
        </div>
      </div>

      <p className="mt-1 text-[11px] text-sheet-faint">
        Měřítko je logaritmické: stejná vzdálenost znamená stejný násobek, ne stejnou
        částku. Dnes {amount(current)} Kč, cíl {estimate(target)}.
      </p>
    </div>
  );
};

export default MilestoneLadder;
