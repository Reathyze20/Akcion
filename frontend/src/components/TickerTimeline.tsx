/**
 * TickerTimeline Component
 * 
 * Displays historical mentions of a ticker from Mark Gomes transcripts.
 * Shows sentiment evolution over time with weighted scoring.
 */

import React, { useEffect, useState, useCallback } from 'react';
import { apiClient } from '../api/client';
import type { TickerTimelineResponse, TickerMention } from '../types';

interface TickerTimelineProps {
  ticker: string;
  onClose?: () => void;
}

const getSentimentColor = (sentiment: string) => {
  switch (sentiment) {
    case 'VERY_BULLISH':
      return 'text-green-400 bg-green-500/20';
    case 'BULLISH':
      return 'text-green-500 bg-green-500/10';
    case 'NEUTRAL':
      return 'text-gray-400 bg-gray-500/10';
    case 'BEARISH':
      return 'text-orange-400 bg-orange-500/10';
    case 'VERY_BEARISH':
      return 'text-red-400 bg-red-500/20';
    default:
      return 'text-gray-400 bg-gray-500/10';
  }
};

const getSentimentIcon = (sentiment: string) => {
  switch (sentiment) {
    case 'VERY_BULLISH':
      return '';
    case 'BULLISH':
      return '';
    case 'NEUTRAL':
      return '';
    case 'BEARISH':
      return '';
    case 'VERY_BEARISH':
      return '';
    default:
      return '';
  }
};

const getActionBadge = (action: string | null) => {
  if (!action) return null;
  
  const colors: Record<string, string> = {
    'BUY_NOW': 'bg-green-600',
    'ACCUMULATE': 'bg-green-500',
    'BUY': 'bg-green-500',
    'WATCH': 'bg-yellow-600',
    'HOLD': 'bg-yellow-600',
    'TRIM': 'bg-orange-500',
    'SELL': 'bg-red-500',
    'AVOID': 'bg-red-600',
  };
  
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-medium ${colors[action] || 'bg-gray-600'}`}>
      {action.replace('_', ' ')}
    </span>
  );
};

const formatDate = (dateStr: string) => {
  const date = new Date(dateStr);
  return date.toLocaleDateString('cs-CZ', {
    day: 'numeric',
    month: 'short',
    year: 'numeric'
  });
};

const WeightedSentimentBar: React.FC<{ score: number }> = ({ score }) => {
  // Score is -1 to +1, we need to map to 0-100
  const percentage = ((score + 1) / 2) * 100;
  
  return (
    <div className="flex items-center gap-3">
      <span className="text-sm text-red-400">Medvěd</span>
      <div className="flex-1 h-3 bg-gray-700 rounded-full overflow-hidden">
        <div 
          className="h-full transition-all duration-500"
          style={{
            width: `${percentage}%`,
            background: `linear-gradient(90deg, 
              #ef4444 0%, 
              #f97316 25%, 
              #eab308 50%, 
              #84cc16 75%, 
              #22c55e 100%
            )`
          }}
        />
      </div>
      <span className="text-sm text-green-400">Býk</span>
      <span className="text-sm font-mono text-gray-400 w-16 text-right">
        {score >= 0 ? '+' : ''}{(score * 100).toFixed(0)}%
      </span>
    </div>
  );
};

const MentionCard: React.FC<{ mention: TickerMention }> = ({ mention }) => {
  return (
    <div className="relative pl-6 pb-6 border-l-2 border-gray-700 last:border-l-0 last:pb-0">
      {/* Timeline dot */}
      <div className="absolute -left-2 top-0 w-4 h-4 rounded-full bg-gray-800 border-2 border-blue-500" />
      
      {/* Card */}
      <div className="bg-gray-800/50 rounded-lg p-4 ml-4">
        {/* Header */}
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <span className={`px-2 py-1 rounded text-sm font-medium ${getSentimentColor(mention.sentiment)}`}>
              {getSentimentIcon(mention.sentiment)} {mention.sentiment.replace('_', ' ')}
            </span>
            {getActionBadge(mention.action_mentioned)}
            {mention.conviction_level && (
              <span className="text-xs text-gray-400">
                {mention.conviction_level} přesvědčení
              </span>
            )}
          </div>
          <div className="flex items-center gap-2 text-sm text-gray-400">
            <span>{formatDate(mention.mention_date)}</span>
            <span className="text-xs">({mention.age_days}d ago)</span>
          </div>
        </div>
        
        {/* Context snippet */}
        {mention.context_snippet && (
          <p className="text-gray-300 text-sm italic mb-2">
            "{mention.context_snippet}"
          </p>
        )}
        
        {/* Key points */}
        {mention.key_points && mention.key_points.length > 0 && (
          <ul className="text-sm text-gray-400 space-y-1 mb-2">
            {mention.key_points.map((point, i) => (
              <li key={i} className="flex items-start gap-2">
                <span className="text-blue-400">•</span>
                <span>{point}</span>
              </li>
            ))}
          </ul>
        )}
        
        {/* Price target */}
        {mention.price_target && (
          <div className="text-sm text-yellow-400">
            Cenový cíl: ${mention.price_target.toFixed(2)}
          </div>
        )}
        
        {/* Source & Weight */}
        <div className="flex items-center justify-between mt-3 pt-2 border-t border-gray-700">
          <div className="text-xs text-gray-500">
            {mention.source_name}
            {mention.video_url && (
              <a 
                href={mention.video_url} 
                target="_blank" 
                rel="noopener noreferrer"
                className="ml-2 text-blue-400 hover:underline"
              >
                Sledovat
              </a>
            )}
          </div>
          <div className="text-xs text-gray-500">
            Váha: {(mention.weight * 100).toFixed(0)}%
          </div>
        </div>
      </div>
    </div>
  );
};

const TickerTimeline: React.FC<TickerTimelineProps> = ({ ticker, onClose }) => {
  const [timeline, setTimeline] = useState<TickerTimelineResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchTimeline = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await apiClient.getTickerTimeline(ticker);
      setTimeline(data);
    } catch (err: any) {
      setError(err.message || 'Failed to load timeline');
      console.error('Timeline error:', err);
    } finally {
      setLoading(false);
    }
  }, [ticker]);

  useEffect(() => {
    fetchTimeline();
  }, [fetchTimeline]);

  if (loading) {
    return (
      <div className="bg-gray-900 rounded-lg p-6 border border-gray-700">
        <div className="flex items-center justify-center h-40">
          <div className="animate-spin h-8 w-8 border-2 border-blue-500 border-t-transparent rounded-full" />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-gray-900 rounded-lg p-6 border border-red-700">
        <div className="text-red-400 text-center">
          <span className="text-2xl mb-2"></span>
          <p>{error}</p>
          <button 
            onClick={fetchTimeline}
            className="mt-4 px-4 py-2 bg-red-600 hover:bg-red-700 rounded text-white"
          >
            Zkusit znovu
          </button>
        </div>
      </div>
    );
  }

  if (!timeline || timeline.total_mentions === 0) {
    return (
      <div className="bg-gray-900 rounded-lg p-6 border border-gray-700">
        <div className="text-center text-gray-400">
          <span className="text-4xl mb-4 block"></span>
          <h3 className="text-lg font-medium text-white mb-2">Žádné zmínky nenalezeny</h3>
          <p className="text-sm">
            {ticker} nebyl zmíněn v žádném importovaném přepisu.
          </p>
          <p className="text-xs mt-2">
            Importujte přepisy od Marka Gomese pro vytvoření historie.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-gray-900 rounded-lg border border-gray-700 overflow-hidden">
      {/* Header */}
      <div className="p-4 border-b border-gray-700 bg-gray-800/50">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-lg font-bold text-white flex items-center gap-2">
            {ticker} Časová osa
            <span className="text-sm font-normal text-gray-400">
              ({timeline.total_mentions} zmínek)
            </span>
          </h3>
          {onClose && (
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-white transition-colors"
            >
              ✕
            </button>
          )}
        </div>
        
        {/* Latest info */}
        <div className="flex items-center gap-4 mb-3">
          {timeline.latest_sentiment && (
            <div className="flex items-center gap-2">
              <span className="text-sm text-gray-400">Nejnovější:</span>
              <span className={`px-2 py-1 rounded text-sm ${getSentimentColor(timeline.latest_sentiment)}`}>
                {getSentimentIcon(timeline.latest_sentiment)} {timeline.latest_sentiment.replace('_', ' ')}
              </span>
            </div>
          )}
          {timeline.latest_action && (
            getActionBadge(timeline.latest_action)
          )}
        </div>
        
        {/* Weighted sentiment bar */}
        <div className="mt-3">
          <div className="text-xs text-gray-400 mb-1">Vážené skóre sentimentu</div>
          <WeightedSentimentBar score={timeline.weighted_sentiment_score} />
        </div>
      </div>
      
      {/* Timeline */}
      <div className="p-4 max-h-96 overflow-y-auto">
        <div className="space-y-0">
          {timeline.mentions.map((mention) => (
            <MentionCard key={mention.id} mention={mention} />
          ))}
        </div>
      </div>
    </div>
  );
};

export default TickerTimeline;
