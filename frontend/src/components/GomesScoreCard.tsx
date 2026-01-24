/**
 * GomesScoreCard Component
 * 
 * Displays detailed Gomes Investment Committee analysis for a ticker.
 * Shows lifecycle phase, score breakdown, green/red lines, and risk factors.
 */

import React from 'react';
import type { GomesScoreResponse, GomesRating, LifecyclePhase, MarketAlert } from '../types';

interface GomesScoreCardProps {
  score: GomesScoreResponse;
  onAnalyze?: (ticker: string) => void;
}

// Rating colors and icons
const getRatingStyle = (rating: GomesRating) => {
  switch (rating) {
    case 'STRONG_BUY':
      return { bg: 'bg-green-900/30', border: 'border-green-500', text: 'text-green-400', icon: '' };
    case 'BUY':
      return { bg: 'bg-green-900/20', border: 'border-green-600', text: 'text-green-500', icon: '' };
    case 'HOLD':
      return { bg: 'bg-yellow-900/20', border: 'border-yellow-600', text: 'text-yellow-500', icon: '' };
    case 'HIGH_RISK':
      return { bg: 'bg-red-900/30', border: 'border-red-500', text: 'text-red-400', icon: '' };
    case 'AVOID':
    default:
      return { bg: 'bg-gray-900/30', border: 'border-gray-600', text: 'text-gray-400', icon: '' };
  }
};

// Lifecycle phase styling
const getLifecycleStyle = (phase?: LifecyclePhase) => {
  switch (phase) {
    case 'GREAT_FIND':
      return { bg: 'bg-purple-900/30', text: 'text-purple-400', icon: '' };
    case 'GOLD_MINE':
      return { bg: 'bg-amber-900/30', text: 'text-amber-400', icon: '' };
    case 'WAIT_TIME':
      return { bg: 'bg-orange-900/30', text: 'text-orange-400', icon: '' };
    default:
      return { bg: 'bg-gray-900/30', text: 'text-gray-400', icon: '' };
  }
};

// Market alert styling
const getMarketAlertStyle = (alert?: MarketAlert | null) => {
  switch (alert) {
    case 'GREEN':
      return { bg: 'bg-green-900/30', text: 'text-green-400', icon: '' };
    case 'YELLOW':
      return { bg: 'bg-yellow-900/30', text: 'text-yellow-400', icon: '' };
    case 'ORANGE':
      return { bg: 'bg-orange-900/30', text: 'text-orange-400', icon: '' };
    case 'RED':
      return { bg: 'bg-red-900/30', text: 'text-red-400', icon: '' };
    default:
      return null;
  }
};

const GomesScoreCard: React.FC<GomesScoreCardProps> = ({ score, onAnalyze }) => {
  const ratingStyle = getRatingStyle(score.rating);
  const lifecycleStyle = getLifecycleStyle(score.lifecycle_phase);
  const marketAlertStyle = score.market_alert ? getMarketAlertStyle(score.market_alert) : null;

  return (
    <div className={`rounded-lg border-2 ${ratingStyle.border} ${ratingStyle.bg} p-6 space-y-4`}>
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-3">
            <h3 className="text-2xl font-bold text-white">{score.ticker}</h3>
            <span className={`text-3xl font-bold ${ratingStyle.text}`}>
              {score.total_score}/10
            </span>
          </div>
          <div className="flex items-center gap-2 mt-1">
            <span className={`px-3 py-1 rounded-full text-sm font-semibold ${ratingStyle.text} bg-black/30`}>
              {ratingStyle.icon} {score.rating.replace('_', ' ')}
            </span>
            <span className={`px-2 py-1 rounded text-xs ${
              score.confidence === 'HIGH' ? 'bg-green-900/50 text-green-300' :
              score.confidence === 'MEDIUM' ? 'bg-yellow-900/50 text-yellow-300' :
              'bg-gray-900/50 text-gray-300'
            }`}>
              {score.confidence}
            </span>
          </div>
        </div>

        {/* Lifecycle Phase */}
        {score.lifecycle_phase && score.lifecycle_phase !== 'UNKNOWN' && (
          <div className={`${lifecycleStyle.bg} px-4 py-2 rounded-lg border border-white/10`}>
            <div className="text-xs text-gray-400 mb-1">Životní cyklus</div>
            <div className={`${lifecycleStyle.text} font-semibold flex items-center gap-1`}>
              <span>{lifecycleStyle.icon}</span>
              <span>{score.lifecycle_phase.replace('_', ' ')}</span>
            </div>
          </div>
        )}
      </div>

      {/* Market Alert */}
      {marketAlertStyle && (
        <div className={`${marketAlertStyle.bg} border border-white/10 rounded-lg p-3`}>
          <div className="flex items-center gap-2">
            <span className="text-xl">{marketAlertStyle.icon}</span>
            <div>
              <div className="text-xs text-gray-400">Stav trhu</div>
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
        <div className="bg-black/30 rounded-lg p-4 space-y-2">
          <div className="text-xs text-gray-400 font-semibold mb-2">CENOVÉ CÍLE</div>
          <div className="grid grid-cols-2 gap-4">
            {(score.green_line || score.is_undervalued) && (
              <div>
                <div className="text-xs text-green-400 mb-1">Zelená linie (NÁKUP)</div>
                <div className="text-lg font-bold text-green-300">
                  {score.green_line ? `$${score.green_line.toFixed(2)}` : 'Podhodnoceno'}
                </div>
              </div>
            )}
            {score.red_line && (
              <div>
                <div className="text-xs text-red-400 mb-1">Červená linie (PRODEJ)</div>
                <div className="text-lg font-bold text-red-300">
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
            ? 'bg-green-900/20 border-green-500/30' 
            : 'bg-orange-900/20 border-orange-500/30'
        }`}>
          <div className="flex items-center gap-2">
            <span className="text-xl">{score.firing_on_10_cylinders ? '' : ''}</span>
            <div>
              <div className="text-xs text-gray-400">Kvalita exekuce</div>
              <div className={score.firing_on_10_cylinders ? 'text-green-300' : 'text-orange-300'}>
                {score.firing_on_10_cylinders ? 'Všechny motory jedou' : 'NEJEDE na plný plyn'}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Reasoning */}
      <div className="bg-black/30 rounded-lg p-4">
        <div className="text-xs text-gray-400 font-semibold mb-2">ANALÝZA</div>
        <div className="text-sm text-gray-200 whitespace-pre-line">
          {score.reasoning}
        </div>
      </div>

      {/* Bull/Bear Cases */}
      {(score.bull_case || score.bear_case) && (
        <div className="grid md:grid-cols-2 gap-4">
          {score.bull_case && (
            <div className="bg-green-900/10 border border-green-500/20 rounded-lg p-3">
              <div className="text-xs text-green-400 font-semibold mb-2">BÝČÍ SCÉNÁŘ</div>
              <div className="text-sm text-gray-300">{score.bull_case}</div>
            </div>
          )}
          {score.bear_case && (
            <div className="bg-red-900/10 border border-red-500/20 rounded-lg p-3">
              <div className="text-xs text-red-400 font-semibold mb-2">MEDVĚDÍ SCÉNÁŘ</div>
              <div className="text-sm text-gray-300">{score.bear_case}</div>
            </div>
          )}
        </div>
      )}

      {/* Catalysts */}
      {score.catalysts && score.catalysts.length > 0 && (
        <div className="bg-black/30 rounded-lg p-4">
          <div className="text-xs text-green-400 font-semibold mb-2">KATALYZÁTORY</div>
          <ul className="space-y-1">
            {score.catalysts.map((catalyst, idx) => (
              <li key={idx} className="text-sm text-gray-300 flex items-start gap-2">
                <span className="text-green-400">•</span>
                <span>{catalyst}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Risk Factors */}
      {score.risk_factors.length > 0 && (
        <div className="bg-red-900/10 border border-red-500/20 rounded-lg p-4">
          <div className="text-xs text-red-400 font-semibold mb-2">RIZIKOVÉ FAKTORY</div>
          <ul className="space-y-1">
            {score.risk_factors.map((risk, idx) => (
              <li key={idx} className="text-sm text-gray-300 flex items-start gap-2">
                <span className="text-red-400">•</span>
                <span>{risk}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Data Sources */}
      <div className="flex items-center gap-4 text-xs text-gray-400 border-t border-white/10 pt-3">
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
          className="w-full py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-semibold transition-colors"
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
  const color = negative ? 'bg-red-500' : value === max ? 'bg-green-500' : value > 0 ? 'bg-yellow-500' : 'bg-gray-600';

  return (
    <div className="bg-black/30 rounded p-2">
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs text-gray-400">{label}</span>
        <span className={`text-sm font-bold ${negative ? 'text-red-400' : 'text-white'}`}>
          {value}/{max}
        </span>
      </div>
      <div className="h-1.5 bg-gray-700 rounded-full overflow-hidden">
        <div
          className={`h-full ${color} transition-all duration-300`}
          style={{ width: negative ? '100%' : `${percentage}%` }}
        />
      </div>
    </div>
  );
};

export default GomesScoreCard;
