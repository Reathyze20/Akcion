/**
 * SecFilingsCard
 *
 * What the company told the regulator: reported results, its own outlook, and
 * — last, and much smaller — insider trades.
 *
 * That order is the point. Results come from XBRL as exact audited figures;
 * outlook is the company's own words about what comes next; insider activity
 * is a footnote, because the canon is a fundamental method and who bought
 * stock last week is not what it values.
 *
 * The card's other job is to never let an absence read as a finding. There are
 * four separate reasons this card can be empty — a foreign listing, an ISIN
 * stored where a symbol belongs, a foreign private issuer on the 20-F
 * schedule, and EDGAR being unreachable — and not one of them means the
 * company reported nothing. Each gets its own sentence.
 */

import React from 'react';
import {
  AlertTriangle,
  ExternalLink,
  FileText,
  Info,
  Loader2,
  RefreshCw,
  TrendingDown,
  TrendingUp,
} from 'lucide-react';

import { apiClient } from '../../api/client';
import type { SecTickerData, SecCoverageStatus } from '../../api/client';

export interface SecFilingsCardProps {
  ticker: string;
}

/** How each non-COVERED state should read to someone looking for numbers. */
const STATUS_COPY: Record<
  Exclude<SecCoverageStatus, 'COVERED'>,
  { title: string; tone: 'neutral' | 'warning' }
> = {
  NOT_AN_SEC_FILER: {
    title: 'Nepodává u SEC',
    tone: 'neutral',
  },
  FOREIGN_PRIVATE_ISSUER: {
    title: 'Zahraniční emitent — jiné formuláře',
    tone: 'neutral',
  },
  NOT_A_TICKER: {
    title: 'Uloženo jako ISIN, ne ticker',
    tone: 'warning',
  },
  LOOKUP_FAILED: {
    title: 'SEC se nepodařilo přečíst',
    tone: 'warning',
  },
};

const formatDate = (iso: string | null): string =>
  iso ? new Date(iso).toLocaleDateString('cs-CZ') : '—';

export const SecFilingsCard: React.FC<SecFilingsCardProps> = ({ ticker }) => {
  const [data, setData] = React.useState<SecTickerData | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [syncing, setSyncing] = React.useState(false);
  // Distinguished from `data === null`: one means we failed, the other means
  // this ticker has never been checked.
  const [error, setError] = React.useState<string | null>(null);
  const [neverChecked, setNeverChecked] = React.useState(false);

  const load = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await apiClient.getSecData(ticker));
      setNeverChecked(false);
    } catch (e: unknown) {
      const status = (e as { response?: { status?: number } })?.response?.status;
      if (status === 404) {
        setNeverChecked(true);
        setData(null);
      } else {
        setError('Data ze SEC se nepodařilo načíst.');
      }
    } finally {
      setLoading(false);
    }
  }, [ticker]);

  React.useEffect(() => {
    void load();
  }, [load]);

  const sync = async () => {
    setSyncing(true);
    setError(null);
    try {
      await apiClient.syncSecTicker(ticker, true);
      await load();
    } catch {
      setError('Stažení ze SEC selhalo.');
    } finally {
      setSyncing(false);
    }
  };

  // ---------------------------------------------------------------- loading
  if (loading) {
    return (
      <div className="card p-4 flex items-center gap-2 text-text-muted">
        <Loader2 className="w-4 h-4 animate-spin" />
        <span className="text-sm">Načítám data ze SEC…</span>
      </div>
    );
  }

  // ------------------------------------------------------------ not checked
  if (neverChecked) {
    return (
      <div className="card p-4 border-l-4 border-text-muted">
        <div className="flex items-start gap-3">
          <FileText className="w-5 h-5 text-text-muted flex-shrink-0 mt-0.5" />
          <div className="flex-1">
            <h3 className="text-sm font-semibold text-text-secondary mb-1">
              SEC EDGAR
            </h3>
            {/* Not "no filings" — we have not looked. */}
            <p className="text-sm text-text-muted mb-3">
              {ticker} jsme u SEC zatím neověřovali.
            </p>
            <button onClick={sync} disabled={syncing} className="btn-secondary text-xs">
              {syncing ? (
                <>
                  <Loader2 className="w-3 h-3 animate-spin inline mr-1" />
                  Stahuji…
                </>
              ) : (
                'Stáhnout ze SEC'
              )}
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="card p-4 border-l-4 border-warning">
        <div className="flex items-center gap-2 text-warning">
          <AlertTriangle className="w-4 h-4" />
          <span className="text-sm">{error ?? 'Data nejsou k dispozici.'}</span>
        </div>
      </div>
    );
  }

  // ----------------------------------------------- files somewhere, not here
  if (data.status !== 'COVERED' && data.status !== 'FOREIGN_PRIVATE_ISSUER') {
    const copy = STATUS_COPY[data.status];
    return (
      <div
        className={`card p-4 border-l-4 ${
          copy.tone === 'warning' ? 'border-warning' : 'border-text-muted'
        }`}
      >
        <div className="flex items-start gap-3">
          <Info
            className={`w-5 h-5 flex-shrink-0 mt-0.5 ${
              copy.tone === 'warning' ? 'text-warning' : 'text-text-muted'
            }`}
          />
          <div>
            <h3 className="text-sm font-semibold text-text-secondary mb-1">
              {copy.title}
            </h3>
            <p className="text-sm text-text-muted">{data.note}</p>
          </div>
        </div>
      </div>
    );
  }

  const analysed = data.filings.filter((f) => f.analyzed);
  const latestAnalysis = analysed[0] ?? null;

  return (
    <div className="card p-0 overflow-hidden">
      {/* Header */}
      <div className="px-4 py-3 border-b border-border flex items-center justify-between">
        <div className="flex items-center gap-2">
          <FileText className="w-4 h-4 text-accent" />
          <h3 className="text-sm font-semibold text-accent">
            SEC EDGAR
            {data.company_name && (
              <span className="text-text-muted font-normal ml-2">
                {data.company_name}
              </span>
            )}
          </h3>
        </div>
        <button
          onClick={sync}
          disabled={syncing}
          title="Stáhnout nejnovější podání a znovu analyzovat"
          className="text-text-muted hover:text-text-primary transition-colors"
        >
          <RefreshCw className={`w-4 h-4 ${syncing ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {/* Foreign private issuers file 20-F, not 10-Q — say so before the gap
          below is read as the company going quiet. */}
      {data.status === 'FOREIGN_PRIVATE_ISSUER' && data.note && (
        <div className="px-4 py-2 bg-surface-hover border-b border-border">
          <p className="text-xs text-text-muted">{data.note}</p>
        </div>
      )}

      {/* Results — exact figures, the part that matters most */}
      <div className="p-4 border-l-4 border-accent bg-gradient-to-r from-accent/5 to-transparent">
        <h4 className="text-xs font-semibold text-accent uppercase tracking-wider mb-2">
          Výsledky
        </h4>
        {data.findings.length > 0 ? (
          <ul className="space-y-1.5">
            {data.findings.map((finding, i) => (
              <li key={i} className="text-sm text-text-primary leading-relaxed">
                {finding}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-text-muted italic">
            Čísla z výkazů se nepodařilo načíst.
          </p>
        )}

        {/* A line item the company does not tag is a gap in our reading, not a
            zero in theirs. */}
        {data.gaps.length > 0 && (
          <ul className="mt-3 space-y-1">
            {data.gaps.map((gap, i) => (
              <li key={i} className="text-xs text-text-muted">
                ○ {gap}
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Outlook — the company's own words */}
      <div className="p-4 border-t border-border">
        <h4 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-2">
          Výhled
          {latestAnalysis && (
            <span className="text-text-muted font-normal normal-case ml-2">
              {latestAnalysis.form} podáno {formatDate(latestAnalysis.filed_date)}
            </span>
          )}
        </h4>
        {latestAnalysis?.analysis ? (
          <div className="text-sm text-text-primary leading-relaxed whitespace-pre-line">
            {latestAnalysis.analysis}
          </div>
        ) : (
          // Never "nothing notable" — we simply have not read it yet.
          <p className="text-sm text-text-muted italic">
            Zprávu jsme zatím nečetli. Klikni na ↻ pro analýzu.
          </p>
        )}
      </div>

      {/* Filings */}
      {data.filings.length > 0 && (
        <div className="px-4 py-3 border-t border-border">
          <h4 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-2">
            Podání
          </h4>
          <div className="space-y-1">
            {data.filings.slice(0, 6).map((filing, i) => (
              <div key={i} className="flex items-center gap-2 text-xs">
                <span className="font-mono text-text-primary w-14">{filing.form}</span>
                <span className="text-text-muted">
                  {formatDate(filing.filed_date)}
                </span>
                {filing.url && (
                  <a
                    href={filing.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-accent hover:underline flex items-center gap-1"
                  >
                    otevřít <ExternalLink className="w-3 h-3" />
                  </a>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Insiders — deliberately last and deliberately small */}
      <div className="px-4 py-3 border-t border-border bg-surface-hover/50">
        <h4 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-2">
          Insideři
        </h4>
        {data.insider_trades.length > 0 ? (
          <div className="space-y-1">
            {data.insider_trades.slice(0, 5).map((trade, i) => (
              <div key={i} className="flex items-center gap-2 text-xs">
                {trade.signal === 'BUY' ? (
                  <TrendingUp className="w-3 h-3 text-positive flex-shrink-0" />
                ) : (
                  <TrendingDown className="w-3 h-3 text-negative flex-shrink-0" />
                )}
                <span className="text-text-muted">
                  {formatDate(trade.transaction_date)}
                </span>
                <span className="text-text-primary truncate max-w-[140px]">
                  {trade.insider_name}
                </span>
                <span
                  className={
                    trade.signal === 'BUY' ? 'text-positive' : 'text-negative'
                  }
                >
                  {trade.code_label}
                </span>
                {trade.shares != null && (
                  <span className="text-text-muted font-mono">
                    {trade.shares.toLocaleString('cs-CZ')} ks
                  </span>
                )}
              </div>
            ))}
          </div>
        ) : (
          <p className="text-xs text-text-muted">
            Žádný nákup ani prodej na trhu.
          </p>
        )}

        {/* The count that stops a gift being read as a sale. */}
        {data.insider_non_signal_count > 0 && (
          <p className="text-[11px] text-text-muted mt-2">
            + {data.insider_non_signal_count}{' '}
            {data.insider_non_signal_count === 1 ? 'transakce' : 'transakcí'} bez
            signálu (granty, dary, akcie zadržené na daň) — administrativa, ne
            rozhodnutí o penězích.
          </p>
        )}
      </div>

      {data.last_checked_at && (
        <div className="px-4 py-2 border-t border-border">
          <p className="text-[10px] text-text-muted">
            Naposledy ověřeno u SEC: {formatDate(data.last_checked_at)}
          </p>
        </div>
      )}
    </div>
  );
};

export default SecFilingsCard;
