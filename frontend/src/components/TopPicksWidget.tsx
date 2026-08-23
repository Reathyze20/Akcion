/**
 * TopPicksWidget Component
 * 
 * Displays top Gomes picks of the day in a compact widget format.
 * Perfect for dashboard/overview view.
 */

import React, { useEffect, useState, useCallback } from 'react';
import { apiClient } from '../api/client';
import type { WatchlistRanking, ConvictionRating } from '../types';

interface TopPicksWidgetProps {
  minRating?: 'STRONG_BUY' | 'BUY' | 'HOLD';
  limit?: number;
  onTickerClick?: (ticker: string) => void;
  autoRefresh?: boolean;
  refreshInterval?: number; // minutes
}

const getRatingBadge = (rating: ConvictionRating) => {
  switch (rating) {
    case 'STRONG_BUY':
      return { bg: 'bg-positive', text: 'text-text-primary', icon: '', label: 'SILNÝ NÁKUP' };
    case 'BUY':
      return { bg: 'bg-positive', text: 'text-text-primary', icon: '', label: 'NÁKUP' };
    case 'HOLD':
      return { bg: 'bg-warning', text: 'text-text-primary', icon: '', label: 'DRŽET' };
    case 'HIGH_RISK':
      return { bg: 'bg-negative', text: 'text-text-primary', icon: '', label: 'VYSOKÉ RIZIKO' };
    default:
      return { bg: 'bg-surface-active', text: 'text-text-primary', icon: '', label: 'VYHNOUT SE' };
  }
};

const TopPicksWidget: React.FC<TopPicksWidgetProps> = ({
  minRating = 'BUY',
  limit = 10,
  onTickerClick,
  autoRefresh = false,
  refreshInterval = 30
}) => {
  const [rankings, setRankings] = useState<WatchlistRanking[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null);

  const fetchTopPicks = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const response = await apiClient.gomesTopPicks(minRating, limit);
      setRankings(response.rankings);
      setLastUpdate(new Date());
    } catch (err: any) {
      setError(err.message || 'Failed to load top picks');
      console.error('Top picks error:', err);
    } finally {
      setLoading(false);
    }
  }, [minRating, limit]);

  useEffect(() => {
    fetchTopPicks();

    if (autoRefresh && refreshInterval > 0) {
      const interval = setInterval(fetchTopPicks, refreshInterval * 60 * 1000);
      return () => clearInterval(interval);
    }
  }, [fetchTopPicks, autoRefresh, refreshInterval]);

  if (loading && !rankings.length) {
    return (
      <div className="bg-surface-base rounded-lg p-6 border border-border">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-bold text-text-primary">Nejlepší týpky</h3>
          <div className="animate-spin h-5 w-5 border-2 border-accent border-t-transparent rounded-full" />
        </div>
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-16 bg-surface-raised rounded animate-pulse" />
          ))}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-surface-base rounded-lg p-6 border border-negative/30">
        <h3 className="text-lg font-bold text-text-primary mb-2">Nejlepší týpky</h3>
        <div className="text-negative text-sm">{error}</div>
        <button
          onClick={fetchTopPicks}
          className="mt-3 px-4 py-2 bg-negative hover:bg-negative text-text-primary rounded text-sm transition-colors"
        >
          Zkusit znovu
        </button>
      </div>
    );
  }

  if (rankings.length === 0) {
    return (
      <div className="bg-surface-base rounded-lg p-6 border border-border">
        <h3 className="text-lg font-bold text-text-primary mb-2">Nejlepší týpky</h3>
        <p className="text-text-secondary text-sm">
          Žádné týpky odpovídající kritériím ({minRating} nebo lepší)
        </p>
        <button
          onClick={fetchTopPicks}
          className="mt-3 px-4 py-2 bg-accent hover:bg-accent text-text-primary rounded text-sm transition-colors"
        >
          Obnovit
        </button>
      </div>
    );
  }

  return (
    <div className="bg-surface-base rounded-lg p-6 border border-border">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="text-lg font-bold text-text-primary flex items-center gap-2">
            Nejlepší týpky
            <span className="text-sm font-normal text-text-secondary">
              ({rankings.length})
            </span>
          </h3>
          {lastUpdate && (
            <div className="text-xs text-text-muted mt-1">
              Aktualizováno: {lastUpdate.toLocaleTimeString()}
            </div>
          )}
        </div>
        <button
          onClick={fetchTopPicks}
          disabled={loading}
          className="p-2 hover:bg-surface-raised rounded transition-colors disabled:opacity-50"
          title="Refresh"
        >
          <svg
            className={`w-5 h-5 text-text-secondary ${loading ? 'animate-spin' : ''}`}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
            />
          </svg>
        </button>
      </div>

      {/* Rankings List */}
      <div className="space-y-2">
        {rankings.map((item, index) => {
          const badge = getRatingBadge(item.rating);
          const rank = index + 1;
          const medalEmoji = rank === 1 ? '🥇' : rank === 2 ? '🥈' : rank === 3 ? '🥉' : '';

          return (
            <div
              key={item.ticker}
              onClick={() => onTickerClick?.(item.ticker)}
              className={`
                bg-surface-raised rounded-lg p-3 border border-border
                ${onTickerClick ? 'cursor-pointer hover:border-accent hover:bg-surface-hover' : ''}
                transition-all duration-200
              `}
            >
              <div className="flex items-center justify-between">
                {/* Left: Rank & Ticker */}
                <div className="flex items-center gap-3">
                  <div className="text-2xl min-w-[2rem] text-center">
                    {medalEmoji || `${rank}.`}
                  </div>
                  <div>
                    <div className="font-bold text-text-primary text-lg">
                      {item.ticker}
                    </div>
                    <div className="text-xs text-text-secondary">
                      {item.confidence} confidence
                    </div>
                  </div>
                </div>

                {/* Right: Score & Rating */}
                <div className="text-right">
                  <div className="text-2xl font-bold text-positive">
                    {item.score}/10
                  </div>
                  <div className={`text-xs px-2 py-0.5 rounded ${badge.bg} ${badge.text} inline-block mt-1`}>
                    {badge.icon} {badge.label}
                  </div>
                </div>
              </div>

              {/* Reasoning (truncated) */}
              {item.reasoning && (
                <div className="mt-2 text-xs text-text-secondary line-clamp-2">
                  {item.reasoning.split('\n')[0]}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Footer */}
      {autoRefresh && (
        <div className="mt-4 text-xs text-text-muted text-center">
          Auto-refreshes every {refreshInterval} minutes
        </div>
      )}
    </div>
  );
};

export default TopPicksWidget;


