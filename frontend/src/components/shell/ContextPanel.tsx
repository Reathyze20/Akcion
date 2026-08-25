/**
 * ContextPanel — spodní pruh s odrážkami.
 *
 * Tři karty (graf trhu, hotovost a hedge, nepřítomnost) stály pod tabulkou
 * vedle sebe. Každá je dlouhá — hotovost a hedge má přes sedm set pixelů,
 * protože vysvětluje, proč se dva americké fondy z kánonu přes evropského
 * brokera nekoupí. Tři takové karty pod portfoliem znamenaly, že stránka
 * měřila 1 791 px při obrazovce vysoké 1 000.
 *
 * Jsou to přitom podklady, ne denní čtení: člověk se na ně podívá, když se
 * ptá „proč" — ne pokaždé, když otevře aplikaci. Proto z nich jsou odrážky.
 * Zavřený pruh zabírá 38 px a je z něj vidět, že tam ty tři věci jsou;
 * kliknutím se rozbalí ta jedna, o kterou jde, a scrolluje sama v sobě.
 *
 * Volba i to, jestli je pruh otevřený, přežije zavření okna. Kdo se dívá
 * hlavně na trh, najde ho příště otevřený.
 */

import React, { useState } from 'react';
import { ChevronDown, LineChart, Moon, Target, Users, Users2, Wallet } from 'lucide-react';
import MarketGaugeCard from '../MarketGaugeCard';
import CashHedgeCard from '../CashHedgeCard';
import AwayModeCard from '../AwayModeCard';
import ScoreCalibrationCard from '../ScoreCalibrationCard';
import PortfolioDiffCard from '../PortfolioDiffCard';
import BreakoutWatchlistCard from '../BreakoutWatchlistCard';

type PanelId = 'trh' | 'hotovost' | 'nepritomnost' | 'kalibrace' | 'rozdily' | 'breakout';

interface Bullet {
  id: PanelId;
  label: string;
  hint: string;
  Icon: typeof Wallet;
}

const BULLETS: Bullet[] = [
  {
    id: 'trh',
    label: 'Trh',
    hint: 'kde stojí index na dlouhodobém grafu',
    Icon: LineChart,
  },
  {
    id: 'hotovost',
    label: 'Hotovost a hedge',
    hint: 'kolik držet stranou při dnešním stupni',
    Icon: Wallet,
  },
  {
    id: 'nepritomnost',
    label: 'Nepřítomnost',
    hint: 'co se posílá, když se aplikaci nevěnuješ',
    Icon: Moon,
  },
  {
    id: 'kalibrace',
    label: 'Kalibrace',
    hint: 'jestli naše skóre skutečně vydělávala',
    Icon: Target,
  },
  {
    id: 'rozdily',
    label: 'Rozdíly portfolií',
    hint: 'co drží jeden a druhý ne',
    Icon: Users,
  },
  {
    id: 'breakout',
    label: 'Breakout',
    hint: 'kolik podpisů a jaký cíl dává našim jménům druhý zdroj',
    Icon: Users2,
  },
];

const OPEN_KEY = 'akcion.panel.open';
const TAB_KEY = 'akcion.panel.tab';

function readOpen(): boolean {
  try {
    return window.localStorage.getItem(OPEN_KEY) === '1';
  } catch {
    return false;
  }
}

function readTab(): PanelId {
  try {
    const stored = window.localStorage.getItem(TAB_KEY);
    if (stored && BULLETS.some((b) => b.id === stored)) return stored as PanelId;
  } catch {
    /* Zakázaná data webu. Začne se trhem. */
  }
  return 'trh';
}

function remember(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    /* Volba nepřežije zavření okna. Nevadí — nejsou to data. */
  }
}

export const ContextPanel: React.FC = () => {
  const [open, setOpen] = useState(readOpen);
  const [active, setActive] = useState<PanelId>(readTab);

  const select = (id: PanelId) => {
    /* Klik na už otevřenou odrážku ji zavře. Druhá cesta ven než šipka —
       zavírá se tam, kde se otevíralo. */
    const nextOpen = !(open && active === id);
    setActive(id);
    setOpen(nextOpen);
    remember(TAB_KEY, id);
    remember(OPEN_KEY, nextOpen ? '1' : '0');
  };

  return (
    <section
      className="shrink-0 overflow-hidden rounded-card border border-border bg-surface-raised"
      aria-label="Podklady"
    >
      <div className="flex items-center gap-1 px-1.5 py-1.5">
        {BULLETS.map(({ id, label, hint, Icon }) => {
          const on = open && active === id;
          return (
            <button
              key={id}
              onClick={() => select(id)}
              aria-expanded={on}
              title={hint}
              className={`flex items-center gap-2 rounded-button px-2.5 py-1 text-[12.5px] transition-colors ${
                on
                  ? 'bg-accent-bg text-accent'
                  : 'text-text-secondary hover:bg-surface-hover hover:text-text-primary'
              }`}
            >
              <span
                className={`h-[6px] w-[6px] shrink-0 rounded-full ${on ? 'bg-accent' : 'bg-text-muted'}`}
                aria-hidden="true"
              />
              <Icon size={13} strokeWidth={2} aria-hidden="true" className="shrink-0" />
              {label}
            </button>
          );
        })}

        <span className="ml-auto pr-1 text-[11px] text-text-muted">
          {open ? '' : 'podklady k rozhodování'}
        </span>

        {open && (
          <button
            onClick={() => {
              setOpen(false);
              remember(OPEN_KEY, '0');
            }}
            className="rounded p-1 text-text-muted transition-colors hover:text-text-primary"
            title="Zavřít podklady"
            aria-label="Zavřít podklady"
          >
            <ChevronDown size={15} />
          </button>
        )}
      </div>

      {/* Otevřená odrážka. Pevná výška a vlastní scrollování — pruh nikdy
          neroztáhne stránku, ať je v kartě čehokoli. */}
      {open && (
        <div className="max-h-[42vh] min-h-[220px] overflow-y-auto border-t border-border-subtle p-2.5">
          {active === 'trh' && <MarketGaugeCard />}
          {active === 'hotovost' && <CashHedgeCard />}
          {active === 'nepritomnost' && <AwayModeCard />}
          {active === 'kalibrace' && <ScoreCalibrationCard />}
          {active === 'rozdily' && <PortfolioDiffCard />}
          {active === 'breakout' && <BreakoutWatchlistCard />}
        </div>
      )}
    </section>
  );
};

export default ContextPanel;
