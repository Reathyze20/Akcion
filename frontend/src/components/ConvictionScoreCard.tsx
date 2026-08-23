/**
 * ConvictionScoreCard Component
 * 
 * Displays detailed Investment Intelligence analysis for a ticker.
 * Shows lifecycle phase, score breakdown, green/red lines, and risk factors.
 */

import React from 'react';
import type { ConvictionScoreResponse, ConvictionRating, LifecyclePhase, MarketAlert } from '../types';

interface ConvictionScoreCardProps {
  score: ConvictionScoreResponse;
  onAnalyze?: (ticker: string) => void;
}

// Rating colors and icons
const getRatingStyle = (rating: ConvictionRating) => {
  switch (rating) {
    case 'STRONG_BUY':
      return { bg: 'bg-positive/30', border: 'border-positive', text: 'text-positive', icon: '' };
    case 'BUY':
      return { bg: 'bg-positive/20', border: 'border-positive', text: 'text-positive', icon: '' };
    case 'HOLD':
      return { bg: 'bg-warning/20', border: 'border-warning', text: 'text-warning', icon: '' };
    case 'HIGH_RISK':
      return { bg: 'bg-negative/30', border: 'border-negative', text: 'text-negative', icon: '' };
    case 'AVOID':
    default:
      return { bg: 'bg-surface-base/30', border: 'border-border-strong', text: 'text-text-secondary', icon: '' };
  }
};

// Lifecycle phase styling
const getLifecycleStyle = (phase?: LifecyclePhase) => {
  switch (phase) {
    case 'GREAT_FIND':
      return { bg: 'bg-accent/30', text: 'text-accent', icon: '' };
    case 'GOLD_MINE':
      return { bg: 'bg-warning/30', text: 'text-warning', icon: '' };
    case 'WAIT_TIME':
      return { bg: 'bg-warning/30', text: 'text-warning', icon: '' };
    default:
      return { bg: 'bg-surface-base/30', text: 'text-text-secondary', icon: '' };
  }
};

// Market alert styling
const getMarketAlertStyle = (alert?: MarketAlert | null) => {
  switch (alert) {
    case 'GREEN':
      return { bg: 'bg-positive/30', text: 'text-positive', icon: '' };
    case 'YELLOW':
      return { bg: 'bg-warning/30', text: 'text-warning', icon: '' };
    case 'ORANGE':
      return { bg: 'bg-warning/30', text: 'text-warning', icon: '' };
    case 'RED':
      return { bg: 'bg-negative/30', text: 'text-negative', icon: '' };
    default:
      return null;
  }
};

const ConvictionScoreCard: React.FC<ConvictionScoreCardProps> = ({ score, onAnalyze }) => {
  const ratingStyle = getRatingStyle(score.rating);
  const lifecycleStyle = getLifecycleStyle(score.lifecycle_phase);
  const marketAlertStyle = score.market_alert ? getMarketAlertStyle(score.market_alert) : null;

  return (
    <div className={`rounded-lg border-2 ${ratingStyle.border} ${ratingStyle.bg} p-6 space-y-4`}>
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-3">
            <h3 className="text-2xl font-bold text-text-primary">{score.ticker}</h3>
            <span className={`text-3xl font-bold ${ratingStyle.text}`}>
              {score.total_score}/10
            </span>
          </div>
          <div className="flex items-center gap-2 mt-1">
            <span className={`px-3 py-1 rounded-full text-sm font-semibold ${ratingStyle.text} bg-surface-base/30`}>
              {ratingStyle.icon} {score.rating.replace('_', ' ')}
            </span>
            <span className={`px-2 py-1 rounded text-xs ${
              score.confidence === 'HIGH' ? 'bg-positive/50 text-positive' :
              score.confidence === 'MEDIUM' ? 'bg-warning/50 text-warning' :
              'bg-surface-base/50 text-text-primary'
            }`}>
              {score.confidence}
            </span>
          </div>
        </div>

        {/* Lifecycle Phase */}
        {score.lifecycle_phase && score.lifecycle_phase !== 'UNKNOWN' && (
          <div className={`${lifecycleStyle.bg} px-4 py-2 rounded-lg border border-border-strong/10`}>
            <div className="text-xs text-text-secondary mb-1">Životní cyklus</div>
            <div className={`${lifecycleStyle.text} font-semibold flex items-center gap-1`}>
              <span>{lifecycleStyle.icon}</span>
              <span>{score.lifecycle_phase.replace('_', ' ')}</span>
            </div>
          </div>
        )}
      </div>

      {/* Market Alert */}
      {marketAlertStyle && (
        <div className={`${marketAlertStyle.bg} border border-border-strong/10 rounded-lg p-3`}>
          <div className="flex items-center gap-2">
            <span className="text-xl">{marketAlertStyle.icon}</span>
            <div>
              <div className="text-xs text-text-secondary">Stav trhu</div>
              <div className={`${marketAlertStyle.text} font-semibold">`}>
                {score.market_alert}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Score Breakdown */}
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
        <ScoreItem label="Příběh" value={score.story_score} max={2} />
        <ScoreItem label="Breakout" value={score.breakout_score} max={2} />
        <ScoreItem label="Insider" value={score.insider_score} max={2} />
        <ScoreItem label="ML predikce" value={score.ml_score} max={2} />
        <ScoreItem label="Objem" value={score.volume_score} max={1} />
        {score.earnings_penalty < 0 && (
          <ScoreItem label="Výsledky" value={score.earnings_penalty} max={0} negative />
        )}
      </div>

      {/* Green/Red Lines */}
      {(score.green_line || score.red_line || score.is_undervalued) && (
        <div className="bg-surface-base/30 rounded-lg p-4 space-y-2">
          <div className="text-xs text-text-secondary font-semibold mb-2">CENOVÉ CÍLE</div>
          <div className="grid grid-cols-2 gap-4">
            {(score.green_line || score.is_undervalued) && (
              <div>
                <div className="text-xs text-positive mb-1">Zelená linie (NÁKUP)</div>
                <div className="text-lg font-bold text-positive">
                  {score.green_line ? `$${score.green_line.toFixed(2)}` : 'Podhodnoceno'}
                </div>
              </div>
            )}
            {score.red_line && (
              <div>
                <div className="text-xs text-negative mb-1">Červená linie (PRODEJ)</div>
                <div className="text-lg font-bold text-negative">
                  ${score.red_line.toFixed(2)}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* 10 Cylinders Indicator */}
      {score.firing_on_10_cylinders !== undefined && score.firing_on_10_cylinders !== null && (
        <div className={`rounded-lg p-3 border ${
          score.firing_on_10_cylinders 
            ? 'bg-positive/20 border-positive/30' 
            : 'bg-warning/20 border-warning/30'
        }`}>
          <div className="flex items-center gap-2">
            <span className="text-xl">{score.firing_on_10_cylinders ? '' : ''}</span>
            <div>
              <div className="text-xs text-text-secondary">Kvalita exekuce</div>
              <div className={score.firing_on_10_cylinders ? 'text-positive' : 'text-warning'}>
                {score.firing_on_10_cylinders ? 'Všechny motory jedou' : 'NEJEDE na plný plyn'}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Reasoning */}
      <div className="bg-surface-base/30 rounded-lg p-4">
        <div className="text-xs text-text-secondary font-semibold mb-2">ANALÝZA</div>
        <div className="text-sm text-text-primary whitespace-pre-line">
          {score.reasoning}
        </div>
      </div>

      {/* Bull/Bear Cases */}
      {(score.bull_case || score.bear_case) && (
        <div className="grid md:grid-cols-2 gap-4">
          {score.bull_case && (
            <div className="bg-positive/10 border border-positive/20 rounded-lg p-3">
              <div className="text-xs text-positive font-semibold mb-2">BÝČÍ SCÉNÁŘ</div>
              <div className="text-sm text-text-primary">{score.bull_case}</div>
            </div>
          )}
          {score.bear_case && (
            <div className="bg-negative/10 border border-negative/20 rounded-lg p-3">
              <div className="text-xs text-negative font-semibold mb-2">MEDVĚDÍ SCÉNÁŘ</div>
              <div className="text-sm text-text-primary">{score.bear_case}</div>
            </div>
          )}
        </div>
      )}

      {/* Catalysts */}
      {score.catalysts && score.catalysts.length > 0 && (
        <div className="bg-surface-base/30 rounded-lg p-4">
          <div className="text-xs text-positive font-semibold mb-2">KATALYZÁTORY</div>
          <ul className="space-y-1">
            {score.catalysts.map((catalyst, idx) => (
              <li key={idx} className="text-sm text-text-primary flex items-start gap-2">
                <span className="text-positive">•</span>
                <span>{catalyst}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Risk Factors */}
      {score.risk_factors.length > 0 && (
        <div className="bg-negative/10 border border-negative/20 rounded-lg p-4">
          <div className="text-xs text-negative font-semibold mb-2">RIZIKOVÉ FAKTORY</div>
          <ul className="space-y-1">
            {score.risk_factors.map((risk, idx) => (
              <li key={idx} className="text-sm text-text-primary flex items-start gap-2">
                <span className="text-negative">•</span>
                <span>{risk}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Data Sources */}
      <div className="flex items-center gap-4 text-xs text-text-secondary border-t border-border-strong/10 pt-3">
        <span>Data: {score.has_transcript && 'Přepis'} {score.has_swot && 'SWOT'} {score.has_ml_prediction && 'ML'}</span>
        {score.earnings_date && (
          <span>Výsledky: {new Date(score.earnings_date).toLocaleDateString()}</span>
        )}
        <span className="ml-auto">
          {new Date(score.analysis_timestamp).toLocaleString()}
        </span>
      </div>

      {/* Action Button */}
      {onAnalyze && (
        <button
          onClick={() => onAnalyze(score.ticker)}
          className="w-full py-2 bg-accent hover:bg-accent text-text-primary rounded-lg font-semibold transition-colors"
        >
          Obnovit analýzu
        </button>
      )}
    </div>
  );
};

// Helper component for score items
const ScoreItem: React.FC<{ label: string; value: number; max: number; negative?: boolean }> = ({
  label,
  value,
  max,
  negative
}) => {
  const percentage = max > 0 ? (value / max) * 100 : 0;
  const color = negative ? 'bg-negative' : value === max ? 'bg-positive' : value > 0 ? 'bg-warning' : 'bg-surface-active';

  return (
    <div className="bg-surface-base/30 rounded p-2">
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs text-text-secondary">{label}</span>
        <span className={`text-sm font-bold ${negative ? 'text-negative' : 'text-text-primary'}`}>
          {value}/{max}
        </span>
      </div>
      <div className="h-1.5 bg-surface-hover rounded-full overflow-hidden">
        <div
          className={`h-full ${color} transition-all duration-300`}
          style={{ width: negative ? '100%' : `${percentage}%` }}
        />
      </div>
    </div>
  );
};

export default ConvictionScoreCard;


