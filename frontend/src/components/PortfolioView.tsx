/**
 * PortfolioView Component
 * 
 * Bloomberg Terminal style dashboard with professional data table.
 */

import React, { useEffect, useState, useCallback, useMemo } from 'react';
import { useAppState } from '../hooks/useAppState';
import { apiClient } from '../api/client';
import { StockDetail } from './StockDetail';
import { 
  TrendingUp, 
  TrendingDown, 
  Minus,
  ArrowUpDown,
  ArrowUp,
  ArrowDown
} from 'lucide-react';

type SortKey = 'ticker' | 'sentiment' | 'conviction_score' | 'technical_score' | 
                'fundamental_score' | 'gomes_score' | 'created_at';
type SortDirection = 'asc' | 'desc';

export const PortfolioView: React.FC = () => {
  const {
    stocks,
    setStocks,
    selectedStock,
    setSelectedStock,
    sentimentFilter,
    setSentimentFilter,
    minGomesScore,
    setMinGomesScore,
    isLoading,
    setIsLoading,
    setError,
  } = useAppState();

  const [sortKey, setSortKey] = useState<SortKey>('created_at');
  const [sortDirection, setSortDirection] = useState<SortDirection>('desc');

  const loadPortfolio = useCallback(async () => {
    setIsLoading(true);
    setError(null);

    try {
      const filters: Record<string, string | number> = {};
      if (sentimentFilter) filters.sentiment = sentimentFilter;
      if (minGomesScore) filters.min_gomes_score = minGomesScore;

      // Try enriched endpoint first for price data, fall back to basic if it fails
      try {
        const response = await apiClient.getEnrichedStocks();
        // Apply client-side filters since enriched doesn't support server-side filters
        let filteredStocks = response.stocks;
        if (sentimentFilter) {
          filteredStocks = filteredStocks.filter(s => s.sentiment?.toUpperCase() === sentimentFilter.toUpperCase());
        }
        if (minGomesScore) {
          filteredStocks = filteredStocks.filter(s => (s.gomes_score || 0) >= minGomesScore);
        }
        setStocks(filteredStocks);
      } catch {
        // Fallback to basic stocks API
        const response = await apiClient.getStocks(filters);
        setStocks(response.stocks);
      }
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to load portfolio';
      setError(errorMessage);
      console.error('Portfolio load error:', errorMessage);
    } finally {
      setIsLoading(false);
    }
  }, [sentimentFilter, minGomesScore, setIsLoading, setError, setStocks]);

  useEffect(() => {
    loadPortfolio();
  }, [loadPortfolio]);

  // Sorting logic
  const handleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc');
    } else {
      setSortKey(key);
      setSortDirection('desc');
    }
  };

  const sortedStocks = useMemo(() => {
    return [...stocks].sort((a, b) => {
      let aVal: string | number | Date = 0;
      let bVal: string | number | Date = 0;

      switch (sortKey) {
        case 'ticker':
          aVal = a.ticker || '';
          bVal = b.ticker || '';
          break;
        case 'sentiment':
          aVal = a.sentiment || '';
          bVal = b.sentiment || '';
          break;
        case 'conviction_score':
          aVal = a.conviction_score || 0;
          bVal = b.conviction_score || 0;
          break;
        case 'gomes_score':
          aVal = a.gomes_score || 0;
          bVal = b.gomes_score || 0;
          break;
        case 'created_at':
          aVal = new Date(a.created_at);
          bVal = new Date(b.created_at);
          break;
      }

      if (aVal < bVal) return sortDirection === 'asc' ? -1 : 1;
      if (aVal > bVal) return sortDirection === 'asc' ? 1 : -1;
      return 0;
    });
  }, [stocks, sortKey, sortDirection]);

  // Metrics calculations
  const metrics = useMemo(() => {
    const bullishCount = stocks.filter(s => s.sentiment === 'BULLISH').length;
    const bearishCount = stocks.filter(s => s.sentiment === 'BEARISH').length;
    const latestDate = stocks.length > 0
      ? new Date(Math.max(...stocks.map(s => new Date(s.created_at).getTime())))
      : null;

    return {
      total: stocks.length,
      bullish: bullishCount,
      bearish: bearishCount,
      latestDate: latestDate?.toLocaleDateString('en-US', { 
        month: 'short', 
        day: 'numeric',
        year: 'numeric'
      })
    };
  }, [stocks]);

  const getSentimentIcon = (sentiment: string | null) => {
    switch (sentiment) {
      case 'BULLISH': return <TrendingUp className="w-4 h-4 text-semantic-bullish" />;
      case 'BEARISH': return <TrendingDown className="w-4 h-4 text-semantic-bearish" />;
      default: return <Minus className="w-4 h-4 text-semantic-neutral" />;
    }
  };

  const getSentimentColor = (sentiment: string | null) => {
    switch (sentiment) {
      case 'BULLISH': return 'text-semantic-bullish';
      case 'BEARISH': return 'text-semantic-bearish';
      default: return 'text-semantic-neutral';
    }
  };

  const getScoreColor = (score: number | null | undefined) => {
    if (!score) return 'text-text-muted';
    if (score >= 7) return 'text-semantic-bullish';
    if (score >= 5) return 'text-semantic-neutral';
    return 'text-semantic-bearish';
  };

  const SortIcon: React.FC<{ column: SortKey }> = ({ column }) => {
    if (sortKey !== column) return <ArrowUpDown className="w-3 h-3 opacity-40" />;
    return sortDirection === 'asc' 
      ? <ArrowUp className="w-3 h-3" />
      : <ArrowDown className="w-3 h-3" />;
  };

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  };

  return (
    <div className="flex-1 flex flex-col h-full bg-terminal-bg">
      {/* Metrics Bar */}
      <div className="bg-terminal-surface border-b border-terminal-border px-6 py-4">
        <div className="grid grid-cols-4 gap-6">
          <div>
            <div className="text-xs text-text-muted uppercase tracking-wider mb-1">
              Total Tracked
            </div>
            <div className="text-2xl font-bold font-mono text-text-primary">
              {metrics.total}
            </div>
          </div>
          <div>
            <div className="text-xs text-text-muted uppercase tracking-wider mb-1">
              Bullish Ideas
            </div>
            <div className="text-2xl font-bold font-mono text-semantic-bullish">
              {metrics.bullish}
            </div>
          </div>
          <div>
            <div className="text-xs text-text-muted uppercase tracking-wider mb-1">
              Bearish Ideas
            </div>
            <div className="text-2xl font-bold font-mono text-semantic-bearish">
              {metrics.bearish}
            </div>
          </div>
          <div>
            <div className="text-xs text-text-muted uppercase tracking-wider mb-1">
              Latest Analysis
            </div>
            <div className="text-2xl font-bold font-mono text-accent-cyan">
              {metrics.latestDate || 'N/A'}
            </div>
          </div>
        </div>
      </div>

      {/* Filters Bar */}
      <div className="bg-terminal-card border-b border-terminal-border px-6 py-3">
        <div className="flex items-center gap-4">
          <select
            value={sentimentFilter || ''}
            onChange={(e) => setSentimentFilter(e.target.value || null)}
            className="input text-xs py-1.5 bg-terminal-surface"
          >
            <option value="">All Sentiments</option>
            <option value="BULLISH">🟢 Bullish</option>
            <option value="BEARISH">🔴 Bearish</option>
            <option value="NEUTRAL">⚪ Neutral</option>
          </select>
          
          <select
            value={minGomesScore || ''}
            onChange={(e) => setMinGomesScore(e.target.value ? parseInt(e.target.value) : null)}
            className="input text-xs py-1.5 bg-terminal-surface"
          >
            <option value="">Any Gomes Score</option>
            <option value="7">7+ High Conviction</option>
            <option value="8">8+ Very High</option>
            <option value="9">9+ Exceptional</option>
          </select>

          <div className="flex-1"></div>

          <button
            onClick={loadPortfolio}
            disabled={isLoading}
            className="btn-secondary text-xs py-1.5 px-3"
          >
            {isLoading ? '⏳ Loading...' : '🔄 Refresh'}
          </button>
        </div>
      </div>

      {/* Data Table */}
      <div className="flex-1 overflow-auto custom-scrollbar">
        {isLoading ? (
          <div className="flex items-center justify-center h-64">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-accent-blue"></div>
          </div>
        ) : stocks.length === 0 ? (
          <div className="flex items-center justify-center h-64">
            <div className="text-center">
              <div className="text-4xl mb-4">📊</div>
              <p className="text-text-secondary">
                No stocks found. Start analyzing to build your portfolio.
              </p>
            </div>
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-terminal-surface sticky top-0 z-10">
              <tr className="border-b border-terminal-border">
                <th 
                  className="text-left px-4 py-3 text-text-muted uppercase tracking-wider text-xs font-medium cursor-pointer hover:text-text-secondary"
                  onClick={() => handleSort('ticker')}
                >
                  <div className="flex items-center gap-2">
                    Ticker
                    <SortIcon column="ticker" />
                  </div>
                </th>
                <th 
                  className="text-left px-4 py-3 text-text-muted uppercase tracking-wider text-xs font-medium cursor-pointer hover:text-text-secondary"
                  onClick={() => handleSort('sentiment')}
                >
                  <div className="flex items-center gap-2">
                    Sentiment
                    <SortIcon column="sentiment" />
                  </div>
                </th>
                <th 
                  className="text-left px-4 py-3 text-text-muted uppercase tracking-wider text-xs font-medium cursor-pointer hover:text-text-secondary"
                  onClick={() => handleSort('conviction_score')}
                >
                  <div className="flex items-center gap-2">
                    Conviction
                    <SortIcon column="conviction_score" />
                  </div>
                </th>
                <th 
                  className="text-left px-4 py-3 text-text-muted uppercase tracking-wider text-xs font-medium cursor-pointer hover:text-text-secondary"
                  onClick={() => handleSort('gomes_score')}
                >
                  <div className="flex items-center gap-2">
                    Gomes
                    <SortIcon column="gomes_score" />
                  </div>
                </th>
                <th className="text-left px-4 py-3 text-text-muted uppercase tracking-wider text-xs font-medium">
                  Edge
                </th>
                <th className="text-left px-4 py-3 text-text-muted uppercase tracking-wider text-xs font-medium">
                  Catalysts
                </th>
                <th className="text-left px-4 py-3 text-text-muted uppercase tracking-wider text-xs font-medium">
                  Price Target
                </th>
                <th 
                  className="text-left px-4 py-3 text-text-muted uppercase tracking-wider text-xs font-medium cursor-pointer hover:text-text-secondary"
                  onClick={() => handleSort('created_at')}
                >
                  <div className="flex items-center gap-2">
                    Date
                    <SortIcon column="created_at" />
                  </div>
                </th>
              </tr>
            </thead>
            <tbody>
              {sortedStocks.map((stock) => (
                <tr 
                  key={stock.id}
                  className="border-b border-terminal-border hover:bg-terminal-surface cursor-pointer transition-colors"
                  onClick={() => setSelectedStock(stock)}
                >
                  <td className="px-4 py-3">
                    <div className="font-mono font-bold text-lg text-text-primary">
                      {stock.ticker}
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      {getSentimentIcon(stock.sentiment)}
                      <span className={`text-xs uppercase font-medium ${getSentimentColor(stock.sentiment)}`}>
                        {stock.sentiment}
                      </span>
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-3">
                      <div className="flex-1 bg-terminal-bg rounded-full h-2 overflow-hidden">
                        <div 
                          className={`h-full ${
                            (stock.conviction_score || 0) >= 7 ? 'bg-semantic-bullish' :
                            (stock.conviction_score || 0) >= 5 ? 'bg-semantic-neutral' :
                            'bg-semantic-bearish'
                          }`}
                          style={{ width: `${((stock.conviction_score || 0) / 10) * 100}%` }}
                        ></div>
                      </div>
                      <span className={`font-mono text-xs font-bold w-6 ${getScoreColor(stock.conviction_score)}`}>
                        {stock.conviction_score || '-'}
                      </span>
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <span className={`font-mono text-sm font-bold ${getScoreColor(stock.gomes_score)}`}>
                      {stock.gomes_score || '-'}
                    </span>
                  </td>
                  <td className="px-4 py-3 max-w-xs">
                    <div className="text-xs text-text-secondary truncate">
                      {stock.edge || '-'}
                    </div>
                  </td>
                  <td className="px-4 py-3 max-w-xs">
                    <div className="text-xs text-text-secondary truncate">
                      {stock.catalysts || '-'}
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    {stock.price_target && (
                      <span className="font-mono text-sm text-accent-cyan font-medium">
                        {stock.price_target}
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <span className="text-xs text-text-muted">
                      {formatDate(stock.created_at)}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Stock Detail Modal */}
      {selectedStock && (
        <StockDetail
          stock={selectedStock}
          onClose={() => setSelectedStock(null)}
        />
      )}
    </div>
  );
};
