/**
 * ClearPortfolioButton — one-button portfolio wipe with an explicit guard.
 *
 * Deletes ALL positions from the given portfolios (for a clean broker
 * re-import). Deliberately scoped: cash balance, stock analyses, and the
 * watchlist survive. Destructive, so it always asks once, states exactly
 * what will be deleted, and shows errors inline — never a silent failure.
 */

import React, { useState } from 'react';
import { AlertTriangle, Trash2, X } from 'lucide-react';
import { apiClient } from '../api/client';
import type { PortfolioSummary } from '../types';

interface ClearPortfolioButtonProps {
  portfolios: PortfolioSummary[];
  onCleared: () => void | Promise<void>;
}

export const ClearPortfolioButton: React.FC<ClearPortfolioButtonProps> = ({
  portfolios,
  onCleared,
}) => {
  const [open, setOpen] = useState(false);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const totalPositions = portfolios.reduce((n, p) => n + p.positions.length, 0);

  const handleClear = async () => {
    setWorking(true);
    setError(null);
    try {
      let deleted = 0;
      for (const p of portfolios) {
        const result = await apiClient.deleteAllPositions(p.portfolio.id);
        deleted += result.deleted_count;
      }
      await onCleared();
      setOpen(false);
      if (deleted === 0) {
        setError(null);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Smazání selhalo — pozice zůstaly beze změny.');
    } finally {
      setWorking(false);
    }
  };

  return (
    <>
      {/* Neutral chrome — the danger color lives in the confirm dialog,
          not permanently in the header. */}
      <button
        onClick={() => { setError(null); setOpen(true); }}
        className="btn-secondary text-sm text-text-secondary hover:text-negative"
        title="Smazat všechny pozice (hotovost, analýzy a watchlist zůstanou)"
      >
        <Trash2 className="w-4 h-4" />
        Vyčistit
      </button>

      {open && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-surface-base border border-negative/40 rounded-2xl w-full max-w-md p-6">
            <div className="flex items-start justify-between mb-4">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-negative/15 rounded-lg">
                  <AlertTriangle className="w-6 h-6 text-negative" />
                </div>
                <h2 className="text-xl font-black text-text-primary">Vyčistit portfolio</h2>
              </div>
              <button
                onClick={() => setOpen(false)}
                className="p-1 hover:bg-surface-raised rounded-lg"
                disabled={working}
              >
                <X className="w-5 h-5 text-text-secondary" />
              </button>
            </div>

            <p className="text-sm text-text-secondary mb-3">
              Smaže <span className="font-bold text-negative">{totalPositions} pozic</span> z:
            </p>
            <ul className="mb-4 space-y-1">
              {portfolios.map((p) => (
                <li key={p.portfolio.id} className="text-sm text-text-primary font-mono bg-surface-raised/60 rounded px-3 py-1.5">
                  {p.portfolio.name} — {p.positions.length} pozic
                </li>
              ))}
            </ul>
            <p className="text-xs text-text-muted mb-5">
              Zůstane: hotovost, analýzy akcií i watchlist. Pozice pak nahraješ
              znovu přes Import CSV (nový import už nefabuluje nákupní ceny).
              Akci nelze vrátit zpět.
            </p>

            {error && (
              <p className="mb-4 text-xs text-negative bg-negative/10 border border-negative/30 rounded-lg px-3 py-2">
                {error}
              </p>
            )}

            <div className="flex justify-end gap-3">
              <button
                onClick={() => setOpen(false)}
                disabled={working}
                className="px-4 py-2 bg-surface-raised hover:bg-surface-hover text-text-secondary rounded-lg text-sm font-medium transition-colors"
              >
                Zrušit
              </button>
              <button
                onClick={handleClear}
                disabled={working || totalPositions === 0}
                className="px-4 py-2 bg-negative hover:bg-negative/80 disabled:opacity-50 text-text-primary rounded-lg text-sm font-bold flex items-center gap-2 transition-colors"
              >
                <Trash2 className="w-4 h-4" />
                {working ? 'Mažu…' : `Smazat ${totalPositions} pozic`}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
};

export default ClearPortfolioButton;
