/**
 * AwayModeCard — the switch for the weeks you cannot open the app.
 *
 * The hard part of this screen is not the toggle. It is that away mode is
 * *deliberately quiet*, and quiet has to read as a decision rather than as the
 * app having stopped working. So the card always shows the last cycle's
 * reasoning, whether or not anything was sent, and the preview button exists
 * so the rules can be checked against the real portfolio before a week of
 * silence is trusted to them.
 *
 * What the backend promises, restated here because the user has to know it
 * before switching this on:
 *   - buys are never pushed while away
 *   - nothing actionable is built on prices older than two days
 *   - one message a day unless something is materially more urgent
 */

import React, { useCallback, useEffect, useState } from 'react';
import {
  AlertTriangle,
  Clock,
  Eye,
  MailX,
  Moon,
  Sun,
} from 'lucide-react';
import { apiClient } from '../api/client';
import type { AwayPreview, AwayStatus } from '../api/client';

interface AwayModeCardProps {
  className?: string;
}

const formatMoment = (iso?: string | null): string => {
  if (!iso) return '—';
  const parsed = new Date(iso);
  return Number.isNaN(parsed.getTime())
    ? '—'
    : parsed.toLocaleString('cs-CZ', {
        day: 'numeric',
        month: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      });
};

export const AwayModeCard: React.FC<AwayModeCardProps> = ({ className = '' }) => {
  const [status, setStatus] = useState<AwayStatus | null>(null);
  const [preview, setPreview] = useState<AwayPreview | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setStatus(await apiClient.getAwayStatus());
    } catch (err) {
      setStatus(null);
      setError(err instanceof Error ? err.message : 'Stav away mode se nenačetl');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const toggle = async () => {
    if (!status) return;
    setBusy(true);
    setError(null);
    try {
      setStatus(await apiClient.setAwayMode({ is_away: !status.is_away }));
      setPreview(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Přepnutí se nepovedlo');
    } finally {
      setBusy(false);
    }
  };

  const runPreview = async () => {
    setBusy(true);
    setError(null);
    try {
      setPreview(await apiClient.previewAway());
    } catch (err) {
      setPreview(null);
      setError(err instanceof Error ? err.message : 'Náhled se nepovedl');
    } finally {
      setBusy(false);
    }
  };

  if (loading && !status) {
    return (
      <div className={`bg-surface-raised border border-border rounded-lg p-4 ${className}`}>
        <div className="h-4 w-32 bg-surface-active rounded animate-pulse" />
        <div className="h-6 w-48 bg-surface-active rounded animate-pulse mt-3" />
      </div>
    );
  }

  if (!status) {
    return (
      <div
        className={`bg-surface-raised border border-warning-border rounded-lg p-4 ${className}`}
      >
        <div className="flex items-center gap-2 text-warning text-sm font-medium">
          <AlertTriangle size={16} />
          Away mode se nenačetl
        </div>
        <p className="text-text-muted text-xs mt-2">{error}</p>
      </div>
    );
  }

  const on = status.active;

  return (
    <div
      className={`bg-surface-raised border rounded-lg p-4 ${
        on ? 'border-accent-border' : 'border-border'
      } ${className}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            {on ? (
              <Moon size={16} className="text-accent" />
            ) : (
              <Sun size={16} className="text-text-muted" />
            )}
            <h3 className="text-text-primary text-sm font-semibold">
              Away mode {on ? 'je zapnutý' : 'je vypnutý'}
            </h3>
          </div>
          <p className="text-text-muted text-xs mt-1">
            {on
              ? 'Aplikace posílá nejvýš jednu zprávu denně a jen to, co chrání kapitál.'
              : 'Pro období, kdy se appce nemůžeš věnovat.'}
          </p>
        </div>
        <button
          onClick={() => void toggle()}
          disabled={busy}
          className={`px-3 py-1.5 rounded text-xs font-medium border transition-colors disabled:opacity-40 ${
            on
              ? 'bg-surface-active text-text-primary border-border hover:bg-surface-hover'
              : 'bg-accent-bg text-accent border-accent-border hover:bg-accent-hover'
          }`}
        >
          {on ? 'Vypnout' : 'Zapnout'}
        </button>
      </div>

      {on && (
        <div className="flex flex-wrap gap-x-4 gap-y-1 mt-3 text-[11px] text-text-muted">
          {status.days_away != null && (
            <span className="inline-flex items-center gap-1">
              <Clock size={12} /> {status.days_away} dní
            </span>
          )}
          <span className="inline-flex items-center gap-1">
            <MailX size={12} /> poslední zpráva {formatMoment(status.last_push_at)}
          </span>
          <span>data max. {status.max_data_age_hours} h stará</span>
          <span>klid {status.quiet_period_hours} h mezi zprávami</span>
        </div>
      )}

      {/* The rules, stated before the switch is trusted with a week. */}
      <ul className="mt-3 space-y-1 text-[11px] text-text-secondary">
        <li>• Nákupy se neposílají — promeškaný nákup stojí příležitost, prodej peníze.</li>
        <li>• Na datech starších než dva dny nedostaneš pokyn, jen „otevři aplikaci".</li>
        <li>• Semafor se pro odlehčování bere o stupeň opatrněji (rozšíření aplikace, ne kánon).</li>
      </ul>

      {/* Silence has to be legible. */}
      {status.last_digest_reason && (
        <div className="mt-3 rounded border border-border-subtle bg-surface-base p-3">
          <p className="text-[10px] uppercase tracking-wide text-text-muted">
            Co appka naposled rozhodla
          </p>
          <p className="text-text-secondary text-xs mt-1 leading-relaxed">
            {status.last_digest_reason}
          </p>
        </div>
      )}

      <div className="flex items-center gap-2 mt-3">
        <button
          onClick={() => void runPreview()}
          disabled={busy}
          className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded text-xs border border-border text-text-secondary hover:bg-surface-hover transition-colors disabled:opacity-40"
        >
          <Eye size={13} />
          Co by se poslalo teď
        </button>
        {error && <span className="text-negative text-xs">{error}</span>}
      </div>

      {preview && (
        <div className="mt-3 rounded border border-border-subtle bg-surface-base p-3">
          {!preview.away ? (
            <p className="text-text-secondary text-xs">
              Away mode je vypnutý — běží normální denní seznam.
            </p>
          ) : preview.would_send ? (
            <>
              <p className="text-[10px] uppercase tracking-wide text-text-muted">
                Odešlo by
              </p>
              <p className="text-text-primary text-xs font-medium mt-1">
                {preview.subject}
              </p>
              <pre className="text-text-secondary text-[11px] mt-2 whitespace-pre-wrap font-sans leading-relaxed">
                {preview.body}
              </pre>
            </>
          ) : (
            <>
              <p className="text-[10px] uppercase tracking-wide text-text-muted">
                Neodešlo by nic
              </p>
              <p className="text-text-secondary text-xs mt-1 leading-relaxed">
                {preview.decision}
              </p>
            </>
          )}

          {preview.held.length > 0 && (
            <div className="mt-3 pt-3 border-t border-border-subtle">
              <p className="text-[10px] uppercase tracking-wide text-text-muted">
                Zadrženo ({preview.held.length})
              </p>
              <ul className="mt-1 space-y-1">
                {preview.held.map((line, index) => (
                  <li key={index} className="text-text-muted text-[11px] leading-relaxed">
                    • {line}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      <p className="text-[10px] text-text-muted mt-3">
        Aby to fungovalo se zavřenou aplikací, pověs{' '}
        <code className="text-text-secondary">backend/scripts/away_check.py</code> na
        Plánovač úloh Windows. Pořád to potřebuje zapnutý počítač a funkční SMTP.
      </p>
    </div>
  );
};

export default AwayModeCard;
