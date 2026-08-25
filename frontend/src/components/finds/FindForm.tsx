/**
 * Zadání nálezu: symbol a jedna věta proč.
 *
 * Poznámka není popisek. Vstupuje do posudku jako fakt a vysvětlovač se k ní
 * musí postavit — proto má minimum délky a proto se u ní říká, k čemu je.
 * Za rok je to navíc jediná věc, která připomene, proč si toho člověk všiml.
 *
 * Zakládání sáhne na síť (Yahoo, EDGAR, Finnhub) a u neznámého tickeru trvá
 * pár sekund. Placené API se nevolá — a je to na tlačítku napsané, aby si
 * toho nikdo nemusel všímat až z faktury.
 */

import { useState } from 'react';
import { Plus, RefreshCw } from 'lucide-react';

import { apiClient } from '../../api/client';
import type { FindDetail } from '../../api/client';

const MIN_NOTE = 10;

interface Props {
  onCreated: (detail: FindDetail) => void;
}

export default function FindForm({ onCreated }: Props) {
  const [symbol, setSymbol] = useState('');
  const [note, setNote] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const ready = symbol.trim().length > 0 && note.trim().length >= MIN_NOTE;

  const submit = async () => {
    if (!ready || saving) return;
    setSaving(true);
    setError(null);
    try {
      const detail = await apiClient.createFind({
        symbol: symbol.trim().toUpperCase(),
        note: note.trim(),
      });
      setSymbol('');
      setNote('');
      onCreated(detail);
    } catch (e) {
      const detail = (e as { detail?: string })?.detail;
      setError(detail ?? (e instanceof Error ? e.message : 'Nález se nepodařilo založit'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="panel p-3">
      <p className="eyebrow mb-2">Nový nález</p>

      <input
        className="input-pro w-full"
        placeholder="Symbol, např. CVV"
        value={symbol}
        maxLength={20}
        onChange={(e) => setSymbol(e.target.value.toUpperCase())}
        disabled={saving}
        aria-label="Burzovní symbol"
      />

      <textarea
        className="input-pro mt-2 h-20 w-full resize-none"
        placeholder="Proč sis jí všiml? Jedna věta stačí."
        value={note}
        maxLength={4000}
        onChange={(e) => setNote(e.target.value)}
        disabled={saving}
        aria-label="Proč sis jí všiml"
      />

      <p className="mt-1 text-[11px] text-text-muted">
        Tvoje věta jde do posudku jako podklad — aplikace k ní řekne, jestli
        podle dat obstojí.
      </p>

      {error && (
        <p className="mt-2 rounded-sm bg-negative-bg px-2 py-1.5 text-xs text-negative">
          {error}
        </p>
      )}

      <button
        type="button"
        className="btn-primary mt-2 flex w-full items-center justify-center gap-2"
        onClick={() => void submit()}
        disabled={!ready || saving}
      >
        {saving ? (
          <>
            <RefreshCw className="h-3.5 w-3.5 animate-spin" aria-hidden />
            Sbírám data…
          </>
        ) : (
          <>
            <Plus className="h-3.5 w-3.5" aria-hidden />
            Přidat nález
          </>
        )}
      </button>

      {saving && (
        <p className="mt-1 text-[11px] text-text-muted">
          U neznámé firmy to trvá pár sekund — čtou se výkazy a kurzy. Nic to
          nestojí.
        </p>
      )}
    </div>
  );
}
