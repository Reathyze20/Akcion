/**
 * WatchlistRankingTable Component
 * 
 * Full table view of watchlist ranked by Gomes scores.
 * Includes filtering and detailed information.
 */

import React, { useEffect, useState } from 'react';
import { apiClient } from '../api/client';
import type { WatchlistRanking, GomesRating } from '../types';

interface WatchlistRankingTableProps {
  minScore?: number;
  limit?: number;
  onTickerClick?: (ticker: string) => void;
}

const getRatingColor = (rating: GomesRating) => {
  switch (rating) {
    case 'STRONG_BUY':
      return 'text-green-400 bg-green-900/30';
    case 'BUY':
      return 'text-green-500 bg-green-900/20';
    case 'HOLD':
      return 'text-yellow-500 bg-yellow-900/20';
    case 'HIGH_RISK':
      return 'text-red-400 bg-red-900/30';
    default:
      return 'text-gray-400 bg-gray-900/30';
  }
};

const WatchlistRankingTable: React.FC<WatchlistRankingTableProps> = ({
  minScore = 5,
  limit = 20,
  onTickerClick
}) => {
  const [rankings, setRankings] = useState<WatchlistRanking[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [scanning, setScanning] = useState(false);
  const [filterScore, setFilterScore] = useState(minScore);
  const [totalTickers, setTotalTickers] = useState(0);

  const scanWatchlist = async (forceRefresh: boolean = false) => {
    try {
      setScanning(forceRefresh);
      setLoading(!forceRefresh); // Only show main loader on first load
      setError(null);
      
      const response = await apiClient.gomesScanWatchlist(filterScore, limit, forceRefresh);
      
      setRankings(response.rankings);
      setTotalTickers(response.total_tickers);
    } catch (err: any) {
      setError(err.message || 'Failed to scan watchlist');
      console.error('Watchlist scan error:', err);
    } finally {
      setLoading(false);
      setScanning(false);
    }
  };

  useEffect(() => {
    scanWatchlist(false);
  }, [filterScore, limit]);

  if (loading) {
    return (
      <div className="bg-gray-900 rounded-lg p-6 border border-gray-700">
        <h3 className="text-xl font-bold text-white mb-4">📊 Watchlist Rankings</h3>
        <div className="flex items-center justify-center py-12">
          <div className="animate-spin h-8 w-8 border-3 border-blue-500 border-t-transparent rounded-full" />
          <span className="ml-3 text-gray-400">Scanning watchlist...</span>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-gray-900 rounded-lg p-6 border border-red-500/30">
        <h3 className="text-xl font-bold text-white mb-4">📊 Watchlist Rankings</h3>
        <div className="text-red-400 mb-4">{error}</div>
        <button
          onClick={() => scanWatchlist(false)}
          className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded transition-colors"
        >
          Retry
        </button>
      </div>
    );
  }

  return (
    <div className="bg-gray-900 rounded-lg p-6 border border-gray-700">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h3 className="text-xl font-bold text-white flex items-center gap-2">
            📊 Watchlist Rankings
            {scanning && <div className="animate-spin h-4 w-4 border-2 border-blue-500 border-t-transparent rounded-full" />}
          </h3>
          <p className="text-sm text-gray-400 mt-1">
            Showing {rankings.length} of {totalTickers} tickers
          </p>
        </div>

        <div className="flex items-center gap-3">
          {/* Filter */}
          <div className="flex items-center gap-2">
            <label className="text-sm text-gray-400">Min Score:</label>
            <select
              value={filterScore}
              onChange={(e) => setFilterScore(Number(e.target.value))}
              className="bg-gray-800 text-white border border-gray-600 rounded px-3 py-1.5 text-sm"
            >
              <option value="0">All (0+)</option>
              <option value="5">5+</option>
              <option value="7">7+ (BUY)</option>
              <option value="9">9+ (STRONG BUY)</option>
            </select>
          </div>

          {/* Refresh Buttons */}
          <button
            onClick={() => scanWatchlist(false)}
            disabled={scanning}
            className="px-4 py-2 bg-gray-800 hover:bg-gray-700 text-white rounded transition-colors disabled:opacity-50 text-sm"
          >
            Refresh
          </button>
          <button
            onClick={() => scanWatchlist(true)}
            disabled={scanning}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded transition-colors disabled:opacity-50 text-sm flex items-center gap-2"
          >
            {scanning ? (
              <>
                <div className="animate-spin h-4 w-4 border-2 border-white border-t-transparent rounded-full" />
                Scanning...
              </>
            ) : (
              <>
                🔄 Force Scan
              </>
            )}
          </button>
        </div>
      </div>

      {/* Empty State */}
      {rankings.length === 0 ? (
        <div className="text-center py-12 text-gray-400">
          <p className="text-lg mb-2">No tickers match your criteria</p>
          <p className="text-sm">Try lowering the minimum score filter</p>
        </div>
      ) : (
        /* Table */
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-gray-700 text-left">
                <th className="py-3 px-4 text-xs font-semibold text-gray-400 uppercase">Rank</th>
                <th className="py-3 px-4 text-xs font-semibold text-gray-400 uppercase">Ticker</th>
                <th className="py-3 px-4 text-xs font-semibold text-gray-400 uppercase">Score</th>
                <th className="py-3 px-4 text-xs font-semibold text-gray-400 uppercase">Rating</th>
                <th className="py-3 px-4 text-xs font-semibold text-gray-400 uppercase">Confidence</th>
                <th className="py-3 px-4 text-xs font-semibold text-gray-400 uppercase w-1/3">Analysis</th>
                <th className="py-3 px-4 text-xs font-semibold text-gray-400 uppercase">Analyzed</th>
              </tr>
            </thead>
            <tbody>
              {rankings.map((item, index) => {
                const rank = index + 1;
                const medalEmoji = rank === 1 ? '🥇' : rank === 2 ? '🥈' : rank === 3 ? '🥉' : null;
                const ratingColor = getRatingColor(item.rating);

                return (
                  <tr
                    key={item.ticker}
                    onClick={() => onTickerClick?.(item.ticker)}
                    className={`
                      border-b border-gray-800 hover:bg-gray-800 transition-colors
                      ${onTickerClick ? 'cursor-pointer' : ''}
                    `}
                  >
                    {/* Rank */}
                    <td className="py-4 px-4">
                      <span className="text-lg font-semibold text-gray-300">
                        {medalEmoji || rank}
                      </span>
                    </td>

                    {/* Ticker */}
                    <td className="py-4 px-4">
                      <span className="font-bold text-white text-lg">
                        {item.ticker}
                      </span>
                    </td>

                    {/* Score */}
                    <td className="py-4 px-4">
                      <div className="flex items-center gap-2">
                        <span className="text-2xl font-bold text-green-400">
                          {item.score}
                        </span>
                        <span className="text-gray-500">/10</span>
                      </div>
                    </td>

                    {/* Rating */}
                    <td className="py-4 px-4">
                      <span className={`px-3 py-1 rounded-full text-sm font-semibold ${ratingColor}`}>
                        {item.rating.replace('_', ' ')}
                      </span>
                    </td>

                    {/* Confidence */}
                    <td className="py-4 px-4">
                      <span className={`px-2 py-1 rounded text-xs font-semibold ${
                        item.confidence === 'HIGH' ? 'bg-green-900/50 text-green-300' :
                        item.confidence === 'MEDIUM' ? 'bg-yellow-900/50 text-yellow-300' :
                        'bg-gray-800 text-gray-400'
                      }`}>
                        {item.confidence}
                      </span>
                    </td>

                    {/* Reasoning */}
                    <td className="py-4 px-4">
                      <div className="text-sm text-gray-400 line-clamp-2">
                        {item.reasoning.split('\n')[0]}
                      </div>
                    </td>

                    {/* Analyzed */}
                    <td className="py-4 px-4 text-sm text-gray-500">
                      {new Date(item.last_analyzed).toLocaleDateString()}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Footer Info */}
      {rankings.length > 0 && (
        <div className="mt-4 pt-4 border-t border-gray-800 flex items-center justify-between text-sm text-gray-500">
          <div>
            💡 Click on a ticker to see detailed analysis
          </div>
          <div>
            Force Scan refreshes ML predictions and recalculates scores
          </div>
        </div>
      )}
    </div>
  );
};

export default WatchlistRankingTable;
