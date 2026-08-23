/**
 * WatchlistRankingTable Component
 * 
 * Full table view of watchlist ranked by Conviction Scores.
 * Includes filtering and detailed information.
 */

import React, { useEffect, useState } from 'react';
import { apiClient } from '../api/client';
import type { WatchlistRanking, ConvictionRating } from '../types';

interface WatchlistRankingTableProps {
  minScore?: number;
  limit?: number;
  onTickerClick?: (ticker: string) => void;
}

const getRatingColor = (rating: ConvictionRating) => {
  switch (rating) {
    case 'STRONG_BUY':
      return 'text-positive bg-positive/30';
    case 'BUY':
      return 'text-positive bg-positive/20';
    case 'HOLD':
      return 'text-warning bg-warning/20';
    case 'HIGH_RISK':
      return 'text-negative bg-negative/30';
    default:
      return 'text-text-secondary bg-surface-base/30';
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
      <div className="bg-surface-base rounded-lg p-6 border border-border">
        <h3 className="text-xl font-bold text-text-primary mb-4">Žebříček sledování</h3>
        <div className="flex items-center justify-center py-12">
          <div className="animate-spin h-8 w-8 border-3 border-accent border-t-transparent rounded-full" />
          <span className="ml-3 text-text-secondary">Skenování sledovaných...</span>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-surface-base rounded-lg p-6 border border-negative/30">
        <h3 className="text-xl font-bold text-text-primary mb-4">Žebříček sledování</h3>
        <div className="text-negative mb-4">{error}</div>
        <button
          onClick={() => scanWatchlist(false)}
          className="px-4 py-2 bg-negative hover:bg-negative text-text-primary rounded transition-colors"
        >
          Zkusit znovu
        </button>
      </div>
    );
  }

  return (
    <div className="bg-surface-base rounded-lg p-6 border border-border">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h3 className="text-xl font-bold text-text-primary flex items-center gap-2">
            Žebříček sledování
            {scanning && <div className="animate-spin h-4 w-4 border-2 border-accent border-t-transparent rounded-full" />}
          </h3>
          <p className="text-sm text-text-secondary mt-1">
            Zobrazeno {rankings.length} z {totalTickers} tickerů
          </p>
        </div>

        <div className="flex items-center gap-3">
          {/* Filter */}
          <div className="flex items-center gap-2">
            <label className="text-sm text-text-secondary">Min. skóre:</label>
            <select
              value={filterScore}
              onChange={(e) => setFilterScore(Number(e.target.value))}
              className="bg-surface-raised text-text-primary border border-border-strong rounded px-3 py-1.5 text-sm"
            >
              <option value="0">Vše (0+)</option>
              <option value="5">5+</option>
              <option value="7">7+ (NÁKUP)</option>
              <option value="9">9+ (SILNÝ NÁKUP)</option>
            </select>
          </div>

          {/* Refresh Buttons */}
          <button
            onClick={() => scanWatchlist(false)}
            disabled={scanning}
            className="px-4 py-2 bg-surface-raised hover:bg-surface-hover text-text-primary rounded transition-colors disabled:opacity-50 text-sm"
          >
            Obnovit
          </button>
          <button
            onClick={() => scanWatchlist(true)}
            disabled={scanning}
            className="px-4 py-2 bg-accent hover:bg-accent text-text-primary rounded transition-colors disabled:opacity-50 text-sm flex items-center gap-2"
          >
            {scanning ? (
              <>
                <div className="animate-spin h-4 w-4 border-2 border-border-strong border-t-transparent rounded-full" />
                Skenování...
              </>
            ) : (
              <>
                Vynucené skenování
              </>
            )}
          </button>
        </div>
      </div>

      {/* Empty State */}
      {rankings.length === 0 ? (
        <div className="text-center py-12 text-text-secondary">
          <p className="text-lg mb-2">Žádné tickery neodpovídají vašim kritériím</p>
          <p className="text-sm">Zkuste snížit minimální skóre</p>
        </div>
      ) : (
        /* Table */
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-border text-left">
                <th className="py-3 px-4 text-xs font-semibold text-text-secondary uppercase">Pořadí</th>
                <th className="py-3 px-4 text-xs font-semibold text-text-secondary uppercase">Ticker</th>
                <th className="py-3 px-4 text-xs font-semibold text-text-secondary uppercase">Skóre</th>
                <th className="py-3 px-4 text-xs font-semibold text-text-secondary uppercase">Hodnocení</th>
                <th className="py-3 px-4 text-xs font-semibold text-text-secondary uppercase">Spolehlivost</th>
                <th className="py-3 px-4 text-xs font-semibold text-text-secondary uppercase w-1/3">Analýza</th>
                <th className="py-3 px-4 text-xs font-semibold text-text-secondary uppercase">Analyzováno</th>
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
                      border-b border-border-subtle hover:bg-surface-raised transition-colors
                      ${onTickerClick ? 'cursor-pointer' : ''}
                    `}
                  >
                    {/* Rank */}
                    <td className="py-4 px-4">
                      <span className="text-lg font-semibold text-text-primary">
                        {medalEmoji || rank}
                      </span>
                    </td>

                    {/* Ticker */}
                    <td className="py-4 px-4">
                      <span className="font-bold text-text-primary text-lg">
                        {item.ticker}
                      </span>
                    </td>

                    {/* Score */}
                    <td className="py-4 px-4">
                      <div className="flex items-center gap-2">
                        <span className="text-2xl font-bold text-positive">
                          {item.score}
                        </span>
                        <span className="text-text-muted">/10</span>
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
                        item.confidence === 'HIGH' ? 'bg-positive/50 text-positive' :
                        item.confidence === 'MEDIUM' ? 'bg-warning/50 text-warning' :
                        'bg-surface-raised text-text-secondary'
                      }`}>
                        {item.confidence}
                      </span>
                    </td>

                    {/* Reasoning */}
                    <td className="py-4 px-4">
                      <div className="text-sm text-text-secondary line-clamp-2">
                        {item.reasoning.split('\n')[0]}
                      </div>
                    </td>

                    {/* Analyzed */}
                    <td className="py-4 px-4 text-sm text-text-muted">
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
        <div className="mt-4 pt-4 border-t border-border-subtle flex items-center justify-between text-sm text-text-muted">
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


