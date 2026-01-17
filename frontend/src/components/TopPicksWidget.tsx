/**
 * TopPicksWidget Component
 * 
 * Displays top Gomes picks of the day in a compact widget format.
 * Perfect for dashboard/overview view.
 */

import React, { useEffect, useState, useCallback } from 'react';
import { apiClient } from '../api/client';
import type { WatchlistRanking, GomesRating } from '../types';

interface TopPicksWidgetProps {
  minRating?: 'STRONG_BUY' | 'BUY' | 'HOLD';
  limit?: number;
  onTickerClick?: (ticker: string) => void;
  autoRefresh?: boolean;
  refreshInterval?: number; // minutes
}

const getRatingBadge = (rating: GomesRating) => {
  switch (rating) {
    case 'STRONG_BUY':
      return { bg: 'bg-green-500', text: 'text-white', icon: '🚀', label: 'STRONG BUY' };
    case 'BUY':
      return { bg: 'bg-green-600', text: 'text-white', icon: '✅', label: 'BUY' };
    case 'HOLD':
      return { bg: 'bg-yellow-600', text: 'text-white', icon: '⏸️', label: 'HOLD' };
    case 'HIGH_RISK':
      return { bg: 'bg-red-500', text: 'text-white', icon: '🚨', label: 'HIGH RISK' };
    default:
      return { bg: 'bg-gray-600', text: 'text-white', icon: '❌', label: 'AVOID' };
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
      <div className="bg-gray-900 rounded-lg p-6 border border-gray-700">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-bold text-white">🏆 Top Picks</h3>
          <div className="animate-spin h-5 w-5 border-2 border-blue-500 border-t-transparent rounded-full" />
        </div>
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-16 bg-gray-800 rounded animate-pulse" />
          ))}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-gray-900 rounded-lg p-6 border border-red-500/30">
        <h3 className="text-lg font-bold text-white mb-2">🏆 Top Picks</h3>
        <div className="text-red-400 text-sm">{error}</div>
        <button
          onClick={fetchTopPicks}
          className="mt-3 px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded text-sm transition-colors"
        >
          Retry
        </button>
      </div>
    );
  }

  if (rankings.length === 0) {
    return (
      <div className="bg-gray-900 rounded-lg p-6 border border-gray-700">
        <h3 className="text-lg font-bold text-white mb-2">🏆 Top Picks</h3>
        <p className="text-gray-400 text-sm">
          No picks matching criteria ({minRating} or better)
        </p>
        <button
          onClick={fetchTopPicks}
          className="mt-3 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded text-sm transition-colors"
        >
          Refresh
        </button>
      </div>
    );
  }

  return (
    <div className="bg-gray-900 rounded-lg p-6 border border-gray-700">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="text-lg font-bold text-white flex items-center gap-2">
            🏆 Top Picks
            <span className="text-sm font-normal text-gray-400">
              ({rankings.length})
            </span>
          </h3>
          {lastUpdate && (
            <div className="text-xs text-gray-500 mt-1">
              Updated: {lastUpdate.toLocaleTimeString()}
            </div>
          )}
        </div>
        <button
          onClick={fetchTopPicks}
          disabled={loading}
          className="p-2 hover:bg-gray-800 rounded transition-colors disabled:opacity-50"
          title="Refresh"
        >
          <svg
            className={`w-5 h-5 text-gray-400 ${loading ? 'animate-spin' : ''}`}
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
                bg-gray-800 rounded-lg p-3 border border-gray-700
                ${onTickerClick ? 'cursor-pointer hover:border-blue-500 hover:bg-gray-750' : ''}
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
                    <div className="font-bold text-white text-lg">
                      {item.ticker}
                    </div>
                    <div className="text-xs text-gray-400">
                      {item.confidence} confidence
                    </div>
                  </div>
                </div>

                {/* Right: Score & Rating */}
                <div className="text-right">
                  <div className="text-2xl font-bold text-green-400">
                    {item.score}/10
                  </div>
                  <div className={`text-xs px-2 py-0.5 rounded ${badge.bg} ${badge.text} inline-block mt-1`}>
                    {badge.icon} {badge.label}
                  </div>
                </div>
              </div>

              {/* Reasoning (truncated) */}
              {item.reasoning && (
                <div className="mt-2 text-xs text-gray-400 line-clamp-2">
                  {item.reasoning.split('\n')[0]}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Footer */}
      {autoRefresh && (
        <div className="mt-4 text-xs text-gray-500 text-center">
          Auto-refreshes every {refreshInterval} minutes
        </div>
      )}
    </div>
  );
};

export default TopPicksWidget;
