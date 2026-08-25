/**
 * RemovePositionDialog — „už tuhle akcii nedržím".
 *
 * Za tou jednou větou se schovávají dvě úplně různé věci a aplikace je nesmí
 * splést:
 *
 *  1. **Prodal jsem to.** Pak se zapisuje obchod, ne mazání. Prodejní cena je
 *     jediné místo, odkud se dá spočítat realizovaný zisk — a taky jediné,
 *     z čeho Kalibrace pozná, jestli naše skóre skutečně vydělávala.
 *     `record_trade` v backendu vznikl přesně proto, že se dřív odchody
 *     zapisovaly přepsáním `shares_count`, čímž se prodejní cena zahodila.
 *     Smazat prodanou pozici znamená totéž ještě jednou.
 *
 *  2. **Ten řádek tam nikdy neměl být.** Import z brokera občas přinese
 *     nesmysl — v portfoliu leží `CA00654B1040` a `US90138A1034`, tedy ISINy
 *     místo tickerů, bez nákupní ceny. Tyhle se opravdu mažou, protože o nich
 *     není co zaznamenat.
 *
 * Dialog proto nenabízí jedno tlačítko „smazat", ale ptá se, která z těch dvou
 * věcí nastala. Mazání je schválně to druhé, oddělené a s varováním: je to
 * jediná cesta v aplikaci, která nenávratně zahodí historii.
 */

import React, { useState } from 'react';
import { AlertTriangle, Loader2, Trash2, TrendingDown, X } from 'lucide-react';
import { apiClient } from '../api/client';
import { TradeForm } from './stock-detail/TradeForm';
import type { Position } from '../types';

interface Props {
  position: Position;
  /** Zavolá se po úspěšném zápisu i po smazání — volající přenačte data. */
  onDone: () => void | Promise<void>;
  onCancel: () => void;
}

type Mode = 'volba' | 'prodej' | 'mazani';

export const RemovePositionDialog: React.FC<Props> = ({ position, onDone, onCancel }) => {
  const [mode, setMode] = useState<Mode>('volba');
  const [mazu, setMazu] = useState(false);
  const [chyba, setChyba] = useState<string | null>(null);

  const smazat = async () => {
    setMazu(true);
    setChyba(null);
    try {
      await apiClient.deletePosition(position.id);
      await onDone();
    } catch (err: unknown) {
      // Nezavírat. Když se smazání nepovede, člověk to musí vidět —
      // zavřené okno vypadá jako úspěch.
      setChyba(err instanceof Error ? err.message : 'Smazání se nepovedlo.');
      setMazu(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="w-full max-w-lg rounded-card border border-border bg-surface-overlay p-5 shadow-xl">
        <div className="mb-4 flex items-baseline gap-2">
          <h3 className="text-[15px] font-semibold text-text-primary">
            {position.ticker}
          </h3>
          <span className="text-[12px] text-text-muted">
            {position.shares_count} ks
            {position.company_name ? ` · ${position.company_name}` : ''}
          </span>
          <button
            onClick={onCancel}
            className="ml-auto rounded p-1 text-text-muted transition-colors hover:text-text-primary"
            aria-label="Zavřít"
          >
            <X size={16} />
          </button>
        </div>

        {mode === 'volba' && (
          <>
            <p className="mb-4 text-[13px] leading-relaxed text-text-secondary">
              Co se s tou pozicí stalo? Na tom záleží víc, než to vypadá —
              prodej se zapisuje, aby zůstala historie. Smazat jde jen řádek,
              který v evidenci nikdy neměl být.
            </p>

            <button
              onClick={() => setMode('prodej')}
              className="mb-2 flex w-full items-start gap-3 rounded-button border border-border bg-surface-raised px-4 py-3 text-left transition-colors hover:border-accent hover:bg-surface-hover"
            >
              <TrendingDown size={17} className="mt-0.5 shrink-0 text-accent" aria-hidden="true" />
              <span>
                <span className="block text-[13.5px] font-medium text-text-primary">
                  Prodal jsem to
                </span>
                <span className="block text-[12px] leading-snug text-text-muted">
                  Zapíše prodejní cenu a realizovaný zisk. Pozice zmizí z přehledu,
                  ale zůstane v historii a v Kalibraci.
                </span>
              </span>
            </button>

            <button
              onClick={() => setMode('mazani')}
              className="flex w-full items-start gap-3 rounded-button border border-border px-4 py-3 text-left transition-colors hover:border-negative hover:bg-negative/10"
            >
              <Trash2 size={17} className="mt-0.5 shrink-0 text-text-muted" aria-hidden="true" />
              <span>
                <span className="block text-[13.5px] font-medium text-text-primary">
                  Tenhle řádek sem nepatří
                </span>
                <span className="block text-[12px] leading-snug text-text-muted">
                  Chyba z importu — nikdy jsem to nedržel. Smaže se bez záznamu.
                </span>
              </span>
            </button>
          </>
        )}

        {mode === 'prodej' && (
          <TradeForm
            positionId={position.id}
            ticker={position.ticker}
            side="SELL"
            currentPrice={position.current_price}
            sharesHeld={position.shares_count}
            avgCost={position.avg_cost}
            currency={position.currency ?? null}
            onRecorded={() => { void onDone(); }}
            onCancel={() => setMode('volba')}
          />
        )}

        {mode === 'mazani' && (
          <>
            <div className="mb-4 flex items-start gap-2.5 rounded-input border border-negative/40 bg-negative/10 px-3 py-2.5">
              <AlertTriangle size={15} className="mt-0.5 shrink-0 text-negative" aria-hidden="true" />
              <p className="text-[12.5px] leading-relaxed text-text-secondary">
                Smazání je nevratné a nezanechá stopu. Pokud jsi{' '}
                <strong className="text-text-primary">{position.ticker}</strong> skutečně
                držel a prodal, vrať se a zapiš prodej — jinak přijdeš o realizovaný
                zisk i o to, jak se tahle pozice počítá do Kalibrace.
              </p>
            </div>

            {chyba && (
              <p className="mb-3 rounded-input border border-negative/40 bg-negative/10 px-3 py-2 text-[12px] text-negative">
                {chyba}
              </p>
            )}

            <div className="flex justify-end gap-2">
              <button
                onClick={() => setMode('volba')}
                disabled={mazu}
                className="rounded-button border border-border px-3 py-1.5 text-[13px] text-text-secondary transition-colors hover:text-text-primary disabled:opacity-40"
              >
                Zpět
              </button>
              <button
                onClick={smazat}
                disabled={mazu}
                className="flex items-center gap-2 rounded-button border border-negative bg-negative/20 px-3 py-1.5 text-[13px] font-medium text-negative transition-colors hover:bg-negative/30 disabled:opacity-40"
              >
                {mazu && <Loader2 size={13} className="animate-spin" />}
                Smazat řádek
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
};

export default RemovePositionDialog;
