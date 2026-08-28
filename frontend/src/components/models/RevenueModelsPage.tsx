/**
 * Analytikovy modely tržeb — co je pro něj důležité, po řádcích.
 *
 * Vlevo seznam modelů (jediná věc, která tu scrolluje), vpravo stůl s jedním
 * vybraným. Vše je zdarma — jediné volání na síť je tlačítko „Porovnat
 * s realitou" ve stole, a to čte jen veřejné SEC výkazy, žádný jazykový model.
 *
 * Čtyři stavy vykreslení: načítání, chyba s možností zkusit znovu, prázdno,
 * obsah — stejná disciplína jako u Nálezů.
 */

import { useCallback, useEffect, useState } from 'react';
import { RefreshCw, Scale } from 'lucide-react';

import { apiClient } from '../../api/client';
import type { RevenueModelDetail, RevenueModelSummary } from '../../api/client';
import RevenueModelDesk from './RevenueModelDesk';
import RevenueModelList from './RevenueModelList';

export default function RevenueModelsPage() {
  const [models, setModels] = useState<RevenueModelSummary[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [detail, setDetail] = useState<RevenueModelDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  const loadList = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const rows = await apiClient.getRevenueModels();
      setModels(rows);
      setSelectedId((current) => {
        if (current !== null && rows.some((r) => r.id === current)) return current;
        return rows.length > 0 ? rows[0].id : null;
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Modely se nepodařilo načíst');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadList();
  }, [loadList]);

  const loadDetail = useCallback(async (id: number) => {
    setDetailLoading(true);
    setDetailError(null);
    try {
      setDetail(await apiClient.getRevenueModel(id));
    } catch (e) {
      setDetailError(e instanceof Error ? e.message : 'Detail se nepodařilo načíst');
    } finally {
      setDetailLoading(false);
    }
  }, []);

  useEffect(() => {
    if (selectedId === null) {
      setDetail(null);
      return;
    }
    void loadDetail(selectedId);
  }, [selectedId, loadDetail]);

  return (
    <div className="flex min-h-0 flex-1 gap-3 overflow-hidden">
      <div className="flex w-72 shrink-0 flex-col gap-3">
        {loading && models === null && (
          <div className="sheet flex-1 p-3">
            <p className="text-xs text-text-muted">Načítám modely…</p>
          </div>
        )}

        {error && (
          <div className="sheet flex-1 p-3">
            <p className="text-xs text-negative">{error}</p>
            <button
              type="button"
              className="btn-ghost mt-2 flex items-center gap-1.5 text-xs"
              onClick={() => void loadList()}
            >
              <RefreshCw className="h-3.5 w-3.5" aria-hidden />
              Zkusit znovu
            </button>
          </div>
        )}

        {models !== null && !error && (
          <RevenueModelList models={models} selectedId={selectedId} onSelect={setSelectedId} />
        )}
      </div>

      <div className="min-h-0 flex-1 overflow-hidden">
        {detailLoading && (
          <div className="sheet flex h-full items-center justify-center p-6">
            <p className="text-xs text-text-muted">Načítám model…</p>
          </div>
        )}

        {detailError && !detailLoading && (
          <div className="sheet flex h-full flex-col items-center justify-center gap-2 p-6">
            <p className="text-xs text-negative">{detailError}</p>
            <button
              type="button"
              className="btn-ghost flex items-center gap-1.5 text-xs"
              onClick={() => selectedId !== null && void loadDetail(selectedId)}
            >
              <RefreshCw className="h-3.5 w-3.5" aria-hidden />
              Zkusit znovu
            </button>
          </div>
        )}

        {!detailLoading && !detailError && detail && <RevenueModelDesk model={detail} />}

        {!detailLoading && !detailError && !detail && models !== null && models.length === 0 && (
          <div className="sheet flex h-full flex-col items-center justify-center gap-2 p-6 text-center">
            <Scale className="h-8 w-8 text-text-muted" aria-hidden />
            <p className="text-sm text-text-secondary">
              Zatím žádný model. Přibude, až se stáhne další od Marka nebo jiného analytika.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
