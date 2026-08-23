/**
 * SideRail — levá lišta aplikace.
 *
 * Navigace šla nahoře doprostřed a ujídala výšku: pruh se záložkami plus
 * středový sloupec 1280 px na 1600px monitoru znamenaly 320 px prázdných
 * okrajů a o řádek méně tabulky. Vlevo nestojí nic — svislé místo je
 * v aplikaci vzácné, vodorovné ne.
 *
 * Dole je semafor jako trvalý přístroj. Stav trhu určuje, co se vůbec smí
 * přikupovat, takže patří na každou obrazovku, ne jen na Portfolio. Lišta
 * ho **jen ukazuje** — nikdy nepřepíná. Ukazatel z dlouhodobého grafu najde
 * jeden ze dvou historických RED alertů a druhý mine, a políčko, které by
 * si přepínal sám, by z té poloviční slepoty udělalo pokyn.
 */

import React, { useEffect, useState } from 'react';
import { Coins, Eye, PanelLeftClose, PanelLeftOpen, Target, Wallet } from 'lucide-react';
import { apiClient } from '../../api/client';
import { alertName } from '../../lib/format';

export type TabId = 'portfolio' | 'watchlist' | 'cil' | 'splaceni';

interface SideRailProps {
  active: TabId;
  onSelect: (tab: TabId) => void;
  positionCount: number;
  watchlistCount: number;
}

interface Item {
  id: TabId;
  label: string;
  Icon: typeof Wallet;
  count?: number;
}

/** Stupně v pořadí, v jakém trh přituhuje. */
const STOPS: { key: string; label: string; dot: string; text: string }[] = [
  { key: 'GREEN', label: 'zelená', dot: 'bg-signal-green', text: 'text-signal-green' },
  { key: 'YELLOW', label: 'žlutá', dot: 'bg-signal-amber', text: 'text-signal-amber' },
  { key: 'ORANGE', label: 'oranžová', dot: 'bg-signal-orange', text: 'text-signal-orange' },
  { key: 'RED', label: 'červená', dot: 'bg-signal-red', text: 'text-signal-red' },
];

const STORAGE_KEY = 'akcion.rail.collapsed';

function readCollapsed(): boolean {
  try {
    return window.localStorage.getItem(STORAGE_KEY) === '1';
  } catch {
    return false;
  }
}

export const SideRail: React.FC<SideRailProps> = ({
  active,
  onSelect,
  positionCount,
  watchlistCount,
}) => {
  const [collapsed, setCollapsed] = useState(readCollapsed);
  const [alert, setAlert] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    apiClient
      .getMarketStatus()
      .then((data) => {
        if (alive) setAlert(data.status);
      })
      .catch(() => {
        // Semafor se nenačetl. Lišta funguje dál — jen místo stupně stojí,
        // že se nenačetl. Vymyslet zelenou by bylo horší než nic.
        if (alive) setAlert(null);
      });
    return () => {
      alive = false;
    };
  }, []);

  const toggle = () => {
    const next = !collapsed;
    setCollapsed(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, next ? '1' : '0');
    } catch {
      /* Zakázaná data webu. Sbalení nepřežije zavření okna, nevadí. */
    }
  };

  const items: Item[] = [
    { id: 'portfolio', label: 'Portfolio', Icon: Wallet, count: positionCount },
    { id: 'watchlist', label: 'Sledované', Icon: Eye, count: watchlistCount },
    { id: 'cil', label: 'Cíl', Icon: Target },
    { id: 'splaceni', label: 'Platby', Icon: Coins },
  ];

  const current = STOPS.find((s) => s.key === (alert ?? '').toUpperCase());

  return (
    <aside
      className={`sticky top-0 flex h-screen shrink-0 flex-col border-r border-border-subtle bg-surface-raised transition-[width] duration-150 ${
        collapsed ? 'w-[56px]' : 'w-[188px]'
      }`}
      aria-label="Hlavní navigace"
    >
      <nav className="flex flex-col gap-0.5 p-2 pt-3">
        {items.map(({ id, label, Icon, count }) => {
          const on = active === id;
          return (
            <button
              key={id}
              onClick={() => onSelect(id)}
              aria-current={on ? 'page' : undefined}
              title={collapsed ? label : undefined}
              className={`flex items-center gap-2.5 rounded-button px-2.5 py-2 text-left transition-colors ${
                on
                  ? 'bg-accent-bg text-accent'
                  : 'text-text-secondary hover:bg-surface-hover hover:text-text-primary'
              }`}
            >
              <Icon size={16} strokeWidth={2} className="shrink-0" aria-hidden="true" />
              {!collapsed && (
                <>
                  <span className="text-[13.5px] font-medium">{label}</span>
                  {count !== undefined && (
                    <span className="ml-auto font-mono text-[11px] text-text-muted">
                      {count}
                    </span>
                  )}
                </>
              )}
            </button>
          );
        })}
      </nav>

      {/* Semafor. Dole, aby byl na očích, ale necpal se před navigaci. */}
      <div className="mt-auto border-t border-border-subtle p-3">
        {!collapsed && (
          <p className="eyebrow mb-2.5 text-text-muted">Semafor trhu</p>
        )}

        {alert === null ? (
          collapsed ? (
            <span
              className="mx-auto block h-2 w-2 rounded-full bg-text-muted"
              title="Stupeň semaforu se nenačetl"
            />
          ) : (
            <p className="text-[11px] leading-relaxed text-text-muted">
              Stupeň se nenačetl. Raději nic než zelená, kterou si vymyslím.
            </p>
          )
        ) : collapsed ? (
          <span
            className={`mx-auto block h-2.5 w-2.5 rounded-full ${current?.dot ?? 'bg-text-muted'}`}
            title={`Semafor: ${alertName(alert)}`}
          />
        ) : (
          <ul className="flex flex-col gap-2">
            {STOPS.map((stop) => {
              const on = stop.key === alert.toUpperCase();
              return (
                <li key={stop.key} className="flex items-center gap-2.5">
                  <span
                    className={`h-[7px] w-[7px] shrink-0 rounded-full border ${
                      on
                        ? `${stop.dot} border-transparent`
                        : 'border-text-muted bg-transparent'
                    }`}
                    aria-hidden="true"
                  />
                  <span
                    className={`font-mono text-[10px] uppercase tracking-[0.12em] ${
                      on ? stop.text : 'text-text-muted'
                    }`}
                  >
                    {stop.label}
                  </span>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      <button
        onClick={toggle}
        className="flex items-center justify-center border-t border-border-subtle py-2 text-text-muted transition-colors hover:bg-surface-hover hover:text-text-primary"
        title={collapsed ? 'Rozbalit lištu' : 'Sbalit lištu'}
        aria-label={collapsed ? 'Rozbalit lištu' : 'Sbalit lištu'}
      >
        {collapsed ? <PanelLeftOpen size={15} /> : <PanelLeftClose size={15} />}
      </button>
    </aside>
  );
};

export default SideRail;
