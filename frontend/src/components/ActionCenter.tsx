/**
 * Action Center Component
 *
 * Displays today's top trading opportunities with Buy Confidence scores.
 * Shows Master Signal aggregation results in an actionable format.
 * 
 * Now includes THESIS_BROKEN alerts at the top (Phase 3 of Gomes Enforcement Protocol).
 */

import React, { useEffect, useState } from "react";
import { GomesAlertPanel } from "./GomesAlertPanel";

interface MasterSignalResult {
  ticker: string;
  buy_confidence: number;
  signal_strength: "STRONG_BUY" | "BUY" | "WEAK_BUY" | "NEUTRAL" | "AVOID";
  components: {
    conviction_score: number;
    ml_confidence: number;
    technical_score: number;
    sentiment_score: number;
    gap_score: number;
    risk_reward_score: number;
  };
  verdict: string;
  entry_price: number | null;
  target_price: number | null;
  stop_loss: number | null;
  risk_reward_ratio: number | null;
  kelly_size: number | null;
}

interface ActionCenterProps {
  minConfidence?: number;
  limit?: number;
  userId?: number;
}

const ActionCenter: React.FC<ActionCenterProps> = ({ minConfidence = 60, limit = 10, userId }) => {
  const [opportunities, setOpportunities] = useState<MasterSignalResult[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<string>("");

  useEffect(() => {
    fetchOpportunities();
    const interval = setInterval(fetchOpportunities, 60000); // Refresh every minute
    return () => clearInterval(interval);
  }, [minConfidence, limit, userId]);

  const fetchOpportunities = async () => {
    try {
      setLoading(true);
      const params = new URLSearchParams({
        min_confidence: minConfidence.toString(),
        limit: limit.toString(),
      });
      if (userId) params.append("user_id", userId.toString());

      const response = await fetch(`/api/action-center/opportunities?${params}`);
      if (!response.ok) throw new Error("Failed to fetch opportunities");

      const data = await response.json();
      setOpportunities(data.opportunities || []);
      setLastUpdated(data.last_updated || new Date().toISOString());
      setError(null);
    } catch (err: any) {
      setError(err.message);
      console.error("Failed to fetch opportunities:", err);
    } finally {
      setLoading(false);
    }
  };

  const getConfidenceColor = (confidence: number): string => {
    if (confidence >= 80) return "text-positive";
    if (confidence >= 60) return "text-accent";
    if (confidence >= 40) return "text-warning";
    return "text-text-muted";
  };

  const getConfidenceBarColor = (confidence: number): string => {
    if (confidence >= 80) return "bg-positive";
    if (confidence >= 60) return "bg-accent";
    if (confidence >= 40) return "bg-warning";
    return "bg-surface-active";
  };

  const getStrengthBadge = (strength: string): React.JSX.Element => {
    const colors: Record<string, string> = {
      STRONG_BUY: "bg-positive text-positive border-positive",
      BUY: "bg-accent text-accent border-accent",
      WEAK_BUY: "bg-warning text-warning border-warning",
      NEUTRAL: "bg-surface-active text-text-muted border-border-strong",
      AVOID: "bg-negative text-negative border-negative",
    };

    return <span className={`px-2 py-1 text-xs font-semibold rounded border ${colors[strength] || colors.NEUTRAL}`}>{strength.replace("_", " ")}</span>;
  };

  if (loading && opportunities.length === 0) {
    return (
      <div className="bg-surface-overlay rounded-lg shadow p-6">
        <div className="animate-pulse">
          <div className="h-6 bg-surface-active rounded w-1/3 mb-4"></div>
          <div className="space-y-3">
            {[...Array(3)].map((_, i) => (
              <div key={i} className="h-24 bg-surface-active rounded"></div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-surface-overlay rounded-lg shadow p-6">
        <div className="text-center text-negative">
          <p className="font-semibold">Chyba při načítání příležitostí</p>
          <p className="text-sm mt-2">{error}</p>
          <button onClick={fetchOpportunities} className="mt-4 px-4 py-2 bg-accent text-text-primary rounded hover:bg-accent">
            Zkusit znovu
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-surface-overlay rounded-lg shadow">
      {/* THESIS DRIFT ALERTS - Priority Display */}
      <div className="px-6 pt-4">
        <GomesAlertPanel 
          showAllAlerts={true}
          maxAlerts={5}
          onTakeAction={() => {
            // Refresh opportunities when action is taken
            fetchOpportunities();
          }}
        />
      </div>
      
      {/* Header */}
      <div className="px-6 py-4 border-b border-border-strong flex justify-between items-center">
        <div>
          <h2 className="text-xl font-bold text-text-muted">Dnešní příležitosti</h2>
          <p className="text-sm text-text-muted mt-1">
            {opportunities.length} {opportunities.length === 1 ? "příležitost" : "příležitostí"} nad {minConfidence}% spolehlivost
          </p>
        </div>
        <div className="text-right">
          <button onClick={fetchOpportunities} disabled={loading} className="text-sm text-accent hover:text-accent disabled:text-text-secondary">
            {loading ? "Aktualizuji..." : "Obnovit"}
          </button>
          <p className="text-xs text-text-secondary mt-1">Aktualizováno: {new Date(lastUpdated).toLocaleTimeString()}</p>
        </div>
      </div>

      {/* Opportunities List */}
      <div className="divide-y divide-border-strong">
        {opportunities.length === 0 ? (
          <div className="px-6 py-12 text-center text-text-muted">
            <p className="text-lg">Žádné příležitosti nenalezeny</p>
            <p className="text-sm mt-2">Zkuste snížit minimální hranici spolehlivosti</p>
          </div>
        ) : (
          opportunities.map((opp) => (
            <div key={opp.ticker} className="px-6 py-4 hover:bg-surface-active transition-colors">
              {/* Ticker Row */}
              <div className="flex items-start justify-between mb-3">
                <div className="flex items-center gap-3">
                  <h3 className="text-lg font-bold text-text-muted">{opp.ticker}</h3>
                  {getStrengthBadge(opp.signal_strength)}
                </div>
                <div className="text-right">
                  <div className={`text-2xl font-bold ${getConfidenceColor(opp.buy_confidence)}`}>{opp.buy_confidence.toFixed(1)}%</div>
                  <div className="text-xs text-text-muted">Spolehlivost nákupu</div>
                </div>
              </div>

              {/* Confidence Bar */}
              <div className="mb-3">
                <div className="w-full bg-surface-active rounded-full h-2.5">
                  <div className={`h-2.5 rounded-full ${getConfidenceBarColor(opp.buy_confidence)}`} style={{ width: `${opp.buy_confidence}%` }}></div>
                </div>
              </div>

              {/* Price Info */}
              {opp.entry_price && (
                <div className="grid grid-cols-3 gap-4 mb-3 text-sm">
                  <div>
                    <div className="text-text-muted">Vstup</div>
                    <div className="font-semibold text-text-muted">${opp.entry_price.toFixed(2)}</div>
                  </div>
                  <div>
                    <div className="text-text-muted">Cíl</div>
                    <div className="font-semibold text-positive">{opp.target_price ? `$${opp.target_price.toFixed(2)}` : "—"}</div>
                  </div>
                  <div>
                    <div className="text-text-muted">Stop Loss</div>
                    <div className="font-semibold text-negative">{opp.stop_loss ? `$${opp.stop_loss.toFixed(2)}` : "—"}</div>
                  </div>
                </div>
              )}

              {/* Metrics */}
              <div className="flex gap-4 text-xs text-text-muted">
                {opp.risk_reward_ratio && (
                  <div>
                    <span className="text-text-muted">R/R:</span> <span className="font-semibold">{opp.risk_reward_ratio.toFixed(2)}:1</span>
                  </div>
                )}
                {opp.kelly_size && (
                  <div>
                    <span className="text-text-muted">Velikost:</span> <span className="font-semibold">{(opp.kelly_size * 100).toFixed(1)}%</span>
                  </div>
                )}
                <div>
                  <span className="text-text-muted">Verdikt:</span> <span className="font-semibold">{opp.verdict}</span>
                </div>
              </div>

              {/* Component Breakdown (Collapsible) */}
              <details className="mt-3">
                <summary className="cursor-pointer text-xs text-accent hover:text-accent">Zobrazit rozklad signálu</summary>
                <div className="mt-2 grid grid-cols-2 gap-2 text-xs">
                  <div className="flex justify-between">
                    <span className="text-text-muted">Score:</span>
                    <span className="font-semibold">{opp.components.conviction_score.toFixed(1)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-text-muted">ML:</span>
                    <span className="font-semibold">{opp.components.ml_confidence.toFixed(1)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-text-muted">Technical:</span>
                    <span className="font-semibold">{opp.components.technical_score.toFixed(1)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-text-muted">Sentiment:</span>
                    <span className="font-semibold">{opp.components.sentiment_score.toFixed(1)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-text-muted">Gap:</span>
                    <span className="font-semibold">{opp.components.gap_score.toFixed(1)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-text-muted">R/R:</span>
                    <span className="font-semibold">{opp.components.risk_reward_score.toFixed(1)}</span>
                  </div>
                </div>
              </details>
            </div>
          ))
        )}
      </div>
    </div>
  );
};

export default ActionCenter;


