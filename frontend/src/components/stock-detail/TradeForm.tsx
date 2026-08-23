/**
 * TradeForm — record a BUY/SELL that already happened at the broker.
 *
 * This app does not place orders. The Buy/Sell buttons in TradingDeck used to
 * be `console.log` no-ops, which is the worst possible failure: the owner
 * clicks, sees nothing wrong, and believes the trade was recorded. Every
 * submit here goes through apiClient.recordTrade(), which writes the ledger
 * row and moves the position in one server-side transaction.
 *
 * @fiduciary Two rules this form must never break:
 *   1. A missing purchase price is reported as missing, never as 0.
 *   2. An off-plan trade (one the safety deck blocked) cannot be recorded
 *      without the owner writing down why — that sentence is the whole
 *      point of the emotion_tag column.
 */

import React, { useState } from 'react';
import { AlertTriangle, Check, Loader2, X } from 'lucide-react';
import { apiClient } from '../../api/client';
import type { TradeResponse, TradeSide } from '../../types';

export interface TradeFormProps {
  positionId: number;
  ticker: string;
  side: TradeSide;
  /** Prefills the price field. The owner overwrites it with what he actually got. */
  currentPrice: number | null;
  sharesHeld: number;
  avgCost: number | null;
  currency: string | null;
  /** True when the safety deck raised a critical blocker — forces a written reason. */
  requireReason?: boolean;
  onRecorded: (result: TradeResponse) => void;
  onCancel: () => void;
}

const fmt = (v: number, currency: string | null) =>
  new Intl.NumberFormat('cs-CZ', {
    style: currency ? 'currency' : 'decimal',
    currency: currency ?? undefined,
    maximumFractionDigits: 2,
  }).format(v);

export const TradeForm: React.FC<TradeFormProps> = ({
  positionId,
  ticker,
  side,
  currentPrice,
  sharesHeld,
  avgCost,
  currency,
  requireReason = false,
  onRecorded,
  onCancel,
}) => {
  const [shares, setShares] = useState('');
  const [price, setPrice] = useState(currentPrice != null ? String(currentPrice) : '');
  const [reason, setReason] = useState('');
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<TradeResponse | null>(null);

  const isBuy = side === 'BUY';
  const sharesNum = parseFloat(shares);
  const priceNum = parseFloat(price);

  // Mirrors the server's rules so the owner gets the objection immediately.
  const validate = (): string | null => {
    if (isNaN(sharesNum) || sharesNum <= 0) return 'Počet akcií musí být kladné číslo.';
    if (isNaN(priceNum) || priceNum <= 0) return 'Cena musí být kladné číslo.';
    if (!isBuy && sharesNum > sharesHeld)
      return `Nemůžeš prodat ${sharesNum} akcií, držíš jen ${sharesHeld}.`;
    if (requireReason && reason.trim().length < 3)
      return 'Tenhle obchod jde proti pravidlům. Napiš proč ho děláš.';
    return null;
  };

  const handleSubmit = async () => {
    const problem = validate();
    if (problem) {
      setError(problem);
      return;
    }
    setIsSaving(true);
    setError(null);
    try {
      const res = await apiClient.recordTrade(positionId, {
        side,
        shares: sharesNum,
        price: priceNum,
        emotion_tag: reason.trim() || null,
      });
      setResult(res);
      onRecorded(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Zápis obchodu selhal. Zkus to znovu.');
    } finally {
      setIsSaving(false);
    }
  };

  // ---------------------------------------------------------------- result
  if (result) {
    return (
      <div className="card p-4 space-y-3 border border-positive/40">
        <div className="flex items-center gap-2 text-positive">
          <Check className="w-5 h-5" />
          <span className="font-semibold">
            Zapsáno: {result.side === 'BUY' ? 'nákup' : 'prodej'} {result.shares}× {result.ticker}
          </span>
        </div>

        <dl className="text-sm space-y-1">
          <div className="flex justify-between">
            <dt className="text-secondary">Cena za kus</dt>
            <dd>{fmt(result.price, result.currency)}</dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-secondary">Celkem</dt>
            <dd>{fmt(result.gross_amount, result.currency)}</dd>
          </div>

          {result.side === 'SELL' && (
            <div className="flex justify-between">
              <dt className="text-secondary">Realizovaný zisk</dt>
              <dd>
                {result.realized_pl === null ? (
                  // Never render this as 0 — unknown and break-even are different facts.
                  <span className="text-warning">⚠️ nelze spočítat — chybí nákupní cena</span>
                ) : (
                  <span className={result.realized_pl >= 0 ? 'text-positive' : 'text-negative'}>
                    {result.realized_pl >= 0 ? '+' : ''}
                    {fmt(result.realized_pl, result.currency)}
                  </span>
                )}
              </dd>
            </div>
          )}

          <div className="flex justify-between">
            <dt className="text-secondary">Zbývá akcií</dt>
            <dd>{result.new_shares_count}</dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-secondary">Průměrná nákupní cena</dt>
            <dd>
              {result.new_avg_cost === null ? (
                <span className="text-warning">⚠️ neznámá</span>
              ) : (
                fmt(result.new_avg_cost, result.currency)
              )}
            </dd>
          </div>
        </dl>

        {result.position_closed && (
          <p className="text-sm text-secondary">Pozice je uzavřená (0 akcií).</p>
        )}

        <button onClick={onCancel} className="btn btn-secondary w-full">
          Zavřít
        </button>
      </div>
    );
  }

  // ------------------------------------------------------------------ form
  return (
    <div className="card p-4 space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="font-semibold">
          Zapsat {isBuy ? 'nákup' : 'prodej'} — {ticker}
        </h3>
        <button
          onClick={onCancel}
          className="text-secondary hover:text-primary"
          aria-label="Zrušit"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      <p className="text-xs text-secondary">
        Appka neobchoduje za tebe. Tohle zapisuje obchod, který jsi už udělal u brokera.
      </p>

      {requireReason && (
        <div className="flex gap-2 p-3 rounded-lg bg-warning/10 border border-warning/40 text-sm">
          <AlertTriangle className="w-4 h-4 text-warning shrink-0 mt-0.5" />
          <span>
            Tenhle obchod jde proti pravidlům, která sis nastavil. Zapsat ho můžeš,
            ale musíš napsat proč.
          </span>
        </div>
      )}

      <div className="grid grid-cols-2 gap-3">
        <label className="space-y-1">
          <span className="text-sm text-secondary">Počet akcií</span>
          <input
            type="number"
            inputMode="decimal"
            min="0"
            step="any"
            value={shares}
            onChange={(e) => setShares(e.target.value)}
            className="input w-full"
            placeholder="0"
            autoFocus
          />
          {!isBuy && (
            <span className="text-xs text-secondary">držíš {sharesHeld}</span>
          )}
        </label>

        <label className="space-y-1">
          <span className="text-sm text-secondary">
            Cena za kus{currency ? ` (${currency})` : ''}
          </span>
          <input
            type="number"
            inputMode="decimal"
            min="0"
            step="any"
            value={price}
            onChange={(e) => setPrice(e.target.value)}
            className="input w-full"
            placeholder="0.00"
          />
          {avgCost !== null && !isBuy && (
            <span className="text-xs text-secondary">
              nákup byl {fmt(avgCost, currency)}
            </span>
          )}
          {avgCost === null && !isBuy && (
            <span className="text-xs text-warning">nákupní cena neznámá</span>
          )}
        </label>
      </div>

      <label className="block space-y-1">
        <span className="text-sm text-secondary">
          Proč {requireReason ? '' : '(nepovinné)'}
        </span>
        <input
          type="text"
          maxLength={100}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          className="input w-full"
          placeholder="např. bál jsem se, ale koupil jsem dip"
        />
      </label>

      {!isNaN(sharesNum) && !isNaN(priceNum) && sharesNum > 0 && priceNum > 0 && (
        <p className="text-sm text-secondary">
          Celkem: <span className="text-primary">{fmt(sharesNum * priceNum, currency)}</span>
        </p>
      )}

      {error && (
        <p className="text-sm text-negative" role="alert">
          {error}
        </p>
      )}

      <div className="flex gap-2">
        <button onClick={onCancel} className="btn btn-secondary flex-1" disabled={isSaving}>
          Zrušit
        </button>
        <button
          onClick={handleSubmit}
          className={`btn flex-1 ${isBuy ? 'btn-primary' : 'btn-danger'}`}
          disabled={isSaving}
        >
          {isSaving ? (
            <span className="flex items-center justify-center gap-2">
              <Loader2 className="w-4 h-4 animate-spin" />
              Zapisuju…
            </span>
          ) : (
            `Zapsat ${isBuy ? 'nákup' : 'prodej'}`
          )}
        </button>
      </div>
    </div>
  );
};
