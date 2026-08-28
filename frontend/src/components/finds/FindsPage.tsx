/**
 * Nálezy — vlastní nápady, posouzené podle metodiky.
 *
 * Vlevo seznam nálezů (jediná věc, která tu scrolluje), vpravo stůl s jedním
 * vybraným. Zakládání a čtení je zdarma; jediné placené volání je tlačítko
 * „Nechat vysvětlit" ve stole, a nese to napsané.
 *
 * Čtyři stavy vykreslení se nesmí slít do jednoho: načítání, chyba s možností
 * zkusit znovu, prázdno a obsah. Prázdná obrazovka místo chyby by se četla
 * jako „nic tu není", což je jiné tvrzení než „nepodařilo se to načíst".
 */

import { useCallback, useEffect, useState } from 'react';
import { Lightbulb, RefreshCw } from 'lucide-react';

import { apiClient } from '../../api/client';
import type { Find, FindDetail } from '../../api/client';
import FindForm from './FindForm';
import FindList from './FindList';
import FindDesk from './FindDesk';

export default function FindsPage() {
  const [finds, setFinds] = useState<Find[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [detail, setDetail] = useState<FindDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  const loadList = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const rows = await apiClient.getFinds();
      setFinds(rows);
      setSelectedId((current) => {
        if (current !== null && rows.some((r) => r.id === current)) return current;
        return rows.length > 0 ? rows[0].id : null;
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Nálezy se nepodařilo načíst');
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
      setDetail(await apiClient.getFind(id));
    } catch (e) {
      setDetailError(e instanceof Error ? e.message : 'Nález se nepodařilo načíst');
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

  const handleCreated = useCallback((created: FindDetail) => {
    setDetail(created);
    setSelectedId(created.find.id);
    void loadList();
  }, [loadList]);

  const handleChanged = useCallback((next: FindDetail) => {
    setDetail(next);
    void loadList();
  }, [loadList]);

  if (loading && finds === null) {
    return (
      <div className="flex h-full items-center justify-center text-text-muted">
        <RefreshCw className="h-4 w-4 animate-spin" aria-hidden />
        <span className="ml-2 text-sm">Načítám nálezy…</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="panel m-4 p-4">
        <p className="text-sm text-negative">{error}</p>
        <button type="button" className="btn-secondary mt-3" onClick={() => void loadList()}>
          Zkusit znovu
        </button>
      </div>
    );
  }

  return (
    <div className="flex min-h-0 flex-1 gap-3 p-3">
      <div className="flex min-h-0 w-80 shrink-0 flex-col gap-3">
        <FindForm onCreated={handleCreated} />
        <FindList
          finds={finds ?? []}
          selectedId={selectedId}
          onSelect={setSelectedId}
        />
      </div>

      <div className="flex min-h-0 flex-1 flex-col">
        {selectedId === null ? (
          <EmptyDesk />
        ) : detailError ? (
          <div className="panel p-4">
            <p className="text-sm text-negative">{detailError}</p>
            <button
              type="button"
              className="btn-secondary mt-3"
              onClick={() => void loadDetail(selectedId)}
            >
              Zkusit znovu
            </button>
          </div>
        ) : detail === null || (detailLoading && detail === null) ? (
          <div className="flex h-full items-center justify-center text-sm text-text-muted">
            Načítám spis…
          </div>
        ) : (
          <FindDesk detail={detail} onChanged={handleChanged} />
        )}
      </div>
    </div>
  );
}

function EmptyDesk() {
  return (
    <div className="panel flex h-full flex-col items-center justify-center gap-3 p-8 text-center">
      <Lightbulb className="h-6 w-6 text-text-muted" aria-hidden />
      <p className="max-w-md text-sm text-text-secondary">
        Sem patří akcie, na které narazíš sám. Napiš symbol a jednu větu, proč
        sis jí všiml — zbytek si aplikace posbírá od Marka Gomese, z Breakout
        Investors a z výkazů.
      </p>
      <p className="max-w-md text-xs text-text-muted">
        Nálezy nikam nezasahují. Nic z nich nezvětší pozici ani neodemkne nákup.
      </p>
    </div>
  );
}
