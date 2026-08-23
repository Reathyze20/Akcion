/**
 * ProjectionChart — kde jsme a kam míříme.
 *
 * Graf má jednu úlohu: ukázat, že většinu cílové částky nevytvoří vklady,
 * ale čas. Proto se vykresluje ve třech vrstvách, které se dají přečíst
 * odděleně:
 *
 *   vložený kapitál   plná plocha  — co odložíš. Fakt, ne odhad.
 *   pás rozpětí       světlá plocha — kam to může dojít při horším a lepším výnosu
 *   očekávaná dráha   čára         — střed rozpětí
 *
 * Rozdíl mezi plochou a čárou je ta motivace. A pás je tam proto, že
 * jediná čára by tvrdila, že budoucnost známe.
 *
 * Barvy se berou z CSS proměnných, takže graf drží krok s přepínačem
 * tématu bez další logiky.
 */

import React, { useMemo } from 'react';
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Label,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { YearPoint } from '../../lib/compound';
import { axisTick, estimate, plural } from '../../lib/format';

interface ProjectionChartProps {
  points: YearPoint[];
  /** Cílová částka. Vykreslí se jako vodorovná meta. */
  target: number;
  /** Rok, kdy projekce cíl protne. Null, když ho nepotká. */
  goalYear: number | null;
  height?: number;
}

interface ChartRow {
  year: number;
  contributed: number;
  band: [number, number];
  value: number;
}

const GRID = 'rgb(var(--rule) / 0.7)';
const AXIS = 'rgb(var(--ink-3))';

const TooltipBody: React.FC<{
  active?: boolean;
  payload?: { payload: ChartRow }[];
}> = ({ active, payload }) => {
  if (!active || !payload?.length) return null;
  const row = payload[0].payload;
  const growth = row.value - row.contributed;

  return (
    <div className="rounded-card border border-frame-line bg-frame p-3 text-frame-text shadow-card-hover">
      <p className="eyebrow text-frame-muted">
        {row.year === 0 ? 'dnes' : `za ${row.year} ${plural(row.year, 'rok', 'roky', 'let')}`}
      </p>
      <p className="mt-1.5 font-mono text-base font-medium">{estimate(row.value)}</p>

      <dl className="mt-2 space-y-1 text-[12px]">
        <div className="flex items-baseline justify-between gap-6">
          <dt className="text-frame-muted">z toho vloženo</dt>
          <dd className="font-mono">{estimate(row.contributed)}</dd>
        </div>
        <div className="flex items-baseline justify-between gap-6">
          <dt className="text-frame-muted">přidal trh</dt>
          <dd className="font-mono">{growth > 0 ? estimate(growth) : '—'}</dd>
        </div>
        {row.year > 0 && (
          <div className="flex items-baseline justify-between gap-6 border-t border-frame-line pt-1">
            <dt className="text-frame-muted">rozpětí</dt>
            <dd className="font-mono text-frame-muted">
              {estimate(row.band[0])} – {estimate(row.band[1])}
            </dd>
          </div>
        )}
      </dl>
    </div>
  );
};

export const ProjectionChart: React.FC<ProjectionChartProps> = ({
  points,
  target,
  goalYear,
  height = 300,
}) => {
  const data = useMemo<ChartRow[]>(
    () => points.map((p) => ({
      year: p.year,
      contributed: p.contributed,
      band: [p.low, p.high],
      value: p.value,
    })),
    [points],
  );

  // Meta se vejde do osy jen tehdy, když ji projekce potká. Jinak by se
  // graf zbytečně roztáhl kvůli čáře, ke které se nikdy nedojde.
  const peak = Math.max(...points.map((p) => p.high));
  const showTarget = target <= peak * 1.15;

  return (
    <div style={{ height }} className="w-full">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data} margin={{ top: 12, right: 16, bottom: 4, left: 4 }}>
          <CartesianGrid stroke={GRID} strokeDasharray="2 4" vertical={false} />

          <XAxis
            dataKey="year"
            tick={{ fill: AXIS, fontSize: 11, fontFamily: 'IBM Plex Mono' }}
            tickFormatter={(y: number) => (y === 0 ? 'dnes' : `+${y}`)}
            tickLine={false}
            axisLine={{ stroke: GRID }}
            minTickGap={18}
          />
          <YAxis
            tick={{ fill: AXIS, fontSize: 11, fontFamily: 'IBM Plex Mono' }}
            tickFormatter={axisTick}
            tickLine={false}
            axisLine={false}
            width={52}
          />

          <Tooltip content={<TooltipBody />} cursor={{ stroke: GRID, strokeWidth: 1 }} />

          {/* Pás mezi pesimistickou a optimistickou dráhou. */}
          <Area
            type="monotone"
            dataKey="band"
            stroke="none"
            fill="rgb(var(--signal-green) / 0.14)"
            isAnimationActive={false}
          />

          {/* Vložený kapitál — jediná vrstva, která není odhad. */}
          <Area
            type="monotone"
            dataKey="contributed"
            stroke="rgb(var(--ink-3))"
            strokeWidth={1}
            strokeDasharray="3 3"
            fill="rgb(var(--ink-3) / 0.16)"
            isAnimationActive={false}
          />

          {/* Očekávaná dráha. */}
          <Line
            type="monotone"
            dataKey="value"
            stroke="rgb(var(--signal-green))"
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4, strokeWidth: 0, fill: 'rgb(var(--signal-green))' }}
            isAnimationActive={false}
          />

          {showTarget && (
            <ReferenceLine
              y={target}
              stroke="rgb(var(--signal-amber))"
              strokeDasharray="5 4"
              strokeWidth={1.5}
            >
              <Label
                value={`cíl ${estimate(target)}`}
                position="insideTopRight"
                fill="rgb(var(--signal-amber))"
                fontSize={11}
                fontFamily="IBM Plex Mono"
              />
            </ReferenceLine>
          )}

          {goalYear !== null && (
            <ReferenceLine
              x={goalYear}
              stroke="rgb(var(--signal-amber) / 0.5)"
              strokeDasharray="5 4"
            />
          )}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
};

export default ProjectionChart;
