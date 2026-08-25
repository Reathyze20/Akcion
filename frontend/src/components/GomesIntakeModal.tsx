import React, { useState } from 'react';
import { X, Sparkles, Youtube, FileText, CheckCircle2, AlertTriangle, Loader2 } from 'lucide-react';
import { apiClient } from '../api/client';
import type { IntakeAnalysisResult } from '../types';

interface GomesIntakeModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess?: () => void;
}

export const GomesIntakeModal: React.FC<GomesIntakeModalProps> = ({
  isOpen,
  onClose,
  onSuccess,
}) => {
  const [mode, setMode] = useState<'youtube' | 'text'>('youtube');
  const [youtubeUrl, setYoutubeUrl] = useState('');
  const [rawText, setRawText] = useState('');
  const [sourceType, setSourceType] = useState('GOMES_VIDEO');
  
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [isCommitting, setIsCommitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  
  const [result, setResult] = useState<IntakeAnalysisResult | null>(null);

  if (!isOpen) return null;

  const handleAnalyze = async () => {
    setError(null);
    setSuccessMessage(null);
    setIsAnalyzing(true);

    try {
      const data = await apiClient.analyzeIntake({
        url: mode === 'youtube' ? youtubeUrl : undefined,
        text: mode === 'text' ? rawText : undefined,
        source_type: sourceType,
      });
      setResult(data);
    } catch (err: any) {
      setError(err?.response?.data?.detail || err?.message || 'Analýza selhala.');
    } finally {
      setIsAnalyzing(false);
    }
  };

  const handleCommit = async () => {
    if (!result) return;
    setIsCommitting(true);
    setError(null);

    try {
      const res = await apiClient.commitIntake(result);
      setSuccessMessage(res.message);
      if (onSuccess) {
        onSuccess();
      }
      setTimeout(() => {
        onClose();
      }, 1500);
    } catch (err: any) {
      setError(err?.response?.data?.detail || err?.message || 'Uložení selhalo.');
    } finally {
      setIsCommitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4 animate-in fade-in duration-150">
      <div className="bg-surface-raised border border-border rounded-xl shadow-2xl w-full max-w-2xl overflow-hidden flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border bg-surface-overlay">
          <div className="flex items-center gap-2">
            <div className="p-1.5 bg-accent/15 text-accent rounded-lg">
              <Sparkles className="w-5 h-5" />
            </div>
            <div>
              <h2 className="font-bold text-text-primary text-base">Intake nového obsahu (Gemini 3.7 Flash)</h2>
              <p className="text-xs text-text-secondary">Extrakce Gomes linií, válců a katalyzátorů z videí a zpráv</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1 text-text-muted hover:text-text-primary rounded-lg hover:bg-surface-hover transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <div className="p-6 overflow-y-auto flex-1 space-y-4">
          {error && (
            <div className="p-3 bg-negative/15 border border-negative/30 rounded-lg flex items-start gap-2 text-negative text-xs">
              <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {successMessage && (
            <div className="p-3 bg-positive/15 border border-positive/30 rounded-lg flex items-center gap-2 text-positive text-xs">
              <CheckCircle2 className="w-4 h-4 shrink-0" />
              <span>{successMessage}</span>
            </div>
          )}

          {!result ? (
            <>
              {/* Source Type Toggle */}
              <div className="flex gap-2 p-1 bg-surface-hover rounded-lg border border-border">
                <button
                  type="button"
                  onClick={() => setMode('youtube')}
                  className={`flex-1 flex items-center justify-center gap-2 py-2 px-3 rounded-md text-xs font-semibold transition-all ${
                    mode === 'youtube'
                      ? 'bg-surface-raised text-accent shadow-sm border border-border'
                      : 'text-text-secondary hover:text-text-primary'
                  }`}
                >
                  <Youtube className="w-4 h-4 text-negative" />
                  YouTube Video / Live stream
                </button>
                <button
                  type="button"
                  onClick={() => setMode('text')}
                  className={`flex-1 flex items-center justify-center gap-2 py-2 px-3 rounded-md text-xs font-semibold transition-all ${
                    mode === 'text'
                      ? 'bg-surface-raised text-accent shadow-sm border border-border'
                      : 'text-text-secondary hover:text-text-primary'
                  }`}
                >
                  <FileText className="w-4 h-4 text-accent" />
                  Text zprávy / Breakout Discord
                </button>
              </div>

              {/* Input Area */}
              {mode === 'youtube' ? (
                <div className="space-y-2">
                  <label className="block text-xs font-semibold text-text-secondary">
                    URL adresa videa Marka Gomese:
                  </label>
                  <input
                    type="url"
                    placeholder="https://www.youtube.com/watch?v=... nebo https://youtu.be/..."
                    value={youtubeUrl}
                    onChange={(e) => setYoutubeUrl(e.target.value)}
                    className="w-full px-3 py-2 bg-surface-overlay border border-border rounded-lg text-sm text-text-primary focus:outline-none focus:border-accent"
                  />
                  <p className="text-[11px] text-text-muted">
                    Systém automaticky stáhne transkript z YouTube a vytáhne z něj cenové linie a stádium.
                  </p>
                </div>
              ) : (
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <label className="block text-xs font-semibold text-text-secondary">
                      Vložený text / transkript / příspěvek:
                    </label>
                    <select
                      value={sourceType}
                      onChange={(e) => setSourceType(e.target.value)}
                      className="text-xs bg-surface-overlay border border-border rounded px-2 py-1 text-text-primary"
                    >
                      <option value="GOMES_VIDEO">Mark Gomes (Kánon)</option>
                      <option value="BREAKOUT_INVESTORS">Breakout Investors (Komunita)</option>
                      <option value="EARNINGS_CALL">Earnings Call / Výkazy</option>
                      <option value="OTHER">Ostatní zprávy</option>
                    </select>
                  </div>
                  <textarea
                    rows={6}
                    placeholder="Zkopíruj sem text příspěvku, transkriptu nebo analýzy..."
                    value={rawText}
                    onChange={(e) => setRawText(e.target.value)}
                    className="w-full px-3 py-2 bg-surface-overlay border border-border rounded-lg text-sm text-text-primary focus:outline-none focus:border-accent font-mono"
                  />
                </div>
              )}

              {/* Action Button */}
              <div className="pt-2">
                <button
                  type="button"
                  disabled={isAnalyzing || (mode === 'youtube' ? !youtubeUrl : !rawText.trim())}
                  onClick={handleAnalyze}
                  className="w-full py-2.5 px-4 bg-accent text-accent-fg hover:bg-accent/90 disabled:opacity-50 disabled:cursor-not-allowed font-semibold text-sm rounded-lg flex items-center justify-center gap-2 transition-all shadow-md"
                >
                  {isAnalyzing ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" />
                      Analyzuji přes Gemini Flash (1-2s)...
                    </>
                  ) : (
                    <>
                      <Sparkles className="w-4 h-4" />
                      Analyzovat a extrahovat data
                    </>
                  )}
                </button>
              </div>
            </>
          ) : (
            /* Result Preview Card */
            <div className="space-y-4 animate-in fade-in">
              <div className="p-4 bg-surface-overlay border border-border rounded-xl space-y-3">
                <div className="flex items-start justify-between">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-xl font-bold text-text-primary">{result.ticker}</span>
                      {result.original_ticker && result.original_ticker !== result.ticker && (
                        <span className="text-xs text-text-muted">({result.original_ticker})</span>
                      )}
                      <span className="px-2 py-0.5 bg-accent/15 text-accent text-[10px] font-bold rounded-full uppercase">
                        {result.lifecycle_phase}
                      </span>
                    </div>
                    <div className="text-xs font-semibold text-text-secondary">{result.company_name}</div>
                  </div>
                  <div className="text-right">
                    <span className="text-xs text-text-muted block">Autor: {result.speaker}</span>
                    <span className={`text-xs font-bold ${
                      result.recommended_action === 'BUY' ? 'text-positive' :
                      result.recommended_action === 'SELL' ? 'text-negative' : 'text-warning'
                    }`}>
                      Verdikt: {result.recommended_action}
                    </span>
                  </div>
                </div>

                {/* Price Lines & Cylinders Grid */}
                <div className="grid grid-cols-4 gap-2 pt-2 border-t border-border/50 text-center">
                  <div className="p-2 bg-surface-raised rounded-lg border border-border/50">
                    <span className="text-[10px] text-positive font-bold block">GREEN LINE (Low)</span>
                    <span className="font-mono text-sm font-bold text-text-primary">
                      {result.green_line != null ? `$${result.green_line}` : '—'}
                    </span>
                  </div>
                  <div className="p-2 bg-surface-raised rounded-lg border border-border/50">
                    <span className="text-[10px] text-negative font-bold block">RED LINE (High)</span>
                    <span className="font-mono text-sm font-bold text-text-primary">
                      {result.red_line != null ? `$${result.red_line}` : '—'}
                    </span>
                  </div>
                  <div className="p-2 bg-surface-raised rounded-lg border border-border/50">
                    <span className="text-[10px] text-text-muted font-bold block">VÁLCE</span>
                    <span className="font-mono text-sm font-bold text-text-primary">
                      {result.cylinders != null ? `${result.cylinders}/10` : '—'}
                    </span>
                  </div>
                  <div className="p-2 bg-surface-raised rounded-lg border border-border/50">
                    <span className="text-[10px] text-accent font-bold block">SKÓRE</span>
                    <span className="font-mono text-sm font-bold text-accent">
                      {result.conviction_score != null ? `${result.conviction_score}/10` : '—'}
                    </span>
                  </div>
                </div>

                {/* Summary */}
                <div className="text-xs text-text-primary bg-surface-raised p-2.5 rounded-lg border border-border/50">
                  <span className="font-bold text-text-secondary block mb-1">Shrnutí analýzy:</span>
                  {result.summary_cz}
                </div>

                {/* Catalysts & Risks */}
                {result.primary_catalyst && (
                  <div className="text-xs text-text-secondary">
                    <span className="font-bold text-text-primary">Katalyzátor:</span> {result.primary_catalyst}
                  </div>
                )}
                {result.red_flags && result.red_flags.length > 0 && (
                  <div className="text-xs text-negative bg-negative/10 p-2 rounded-lg border border-negative/20">
                    <span className="font-bold block">Varování / rizika:</span>
                    <ul className="list-disc pl-4 space-y-0.5 mt-0.5">
                      {result.red_flags.map((flag, idx) => (
                        <li key={idx}>{flag}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>

              {/* Action Buttons */}
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => setResult(null)}
                  className="px-4 py-2 bg-surface-overlay hover:bg-surface-hover text-text-secondary text-xs font-semibold rounded-lg border border-border transition-colors"
                >
                  Zpět na zadání
                </button>
                <button
                  type="button"
                  disabled={isCommitting}
                  onClick={handleCommit}
                  className="flex-1 py-2 px-4 bg-positive text-positive-fg hover:bg-positive/90 font-semibold text-xs rounded-lg flex items-center justify-center gap-2 transition-all shadow-md"
                >
                  {isCommitting ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" />
                      Ukládám do databáze...
                    </>
                  ) : (
                    <>
                      <CheckCircle2 className="w-4 h-4" />
                      Potvrdit a uložit do Akcionu
                    </>
                  )}
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
