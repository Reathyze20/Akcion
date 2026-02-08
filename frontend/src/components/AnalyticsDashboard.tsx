/**
 * GomesDashboard Page
 * 
 * Main dashboard for Gomes Investment Committee analysis.
 * Integrates TopPicksWidget, WatchlistRankingTable, GomesScoreCard,
 * TickerTimeline, and TranscriptImporter.
 */

import React, { useState } from 'react';
import TopPicksWidget from './TopPicksWidget';
import WatchlistRankingTable from './WatchlistRankingTable';
import GomesScoreCard from './GomesScoreCard';
import TickerTimeline from './TickerTimeline';
import TranscriptImporter from './TranscriptImporter';
import { apiClient } from '../api/client';
import type { GomesScoreResponse } from '../types';

type ViewMode = 'analysis' | 'timeline' | 'import';

const GomesDashboard: React.FC = () => {
  const [selectedTicker, setSelectedTicker] = useState<string | null>(null);
  const [tickerScore, setTickerScore] = useState<GomesScoreResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<ViewMode>('analysis');

  const handleTickerClick = async (ticker: string) => {
    setSelectedTicker(ticker);
    setLoading(true);
    setError(null);

    try {
      const score = await apiClient.gomesAnalyzeTicker(ticker, false);
      setTickerScore(score);
    } catch (err: any) {
      setError(err.message || 'Failed to analyze ticker');
      console.error('Analysis error:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleRefreshAnalysis = async (ticker: string) => {
    setLoading(true);
    setError(null);

    try {
      const score = await apiClient.gomesAnalyzeTicker(ticker, true); // force refresh
      setTickerScore(score);
    } catch (err: any) {
      setError(err.message || 'Failed to refresh analysis');
      console.error('Refresh error:', err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-950 text-text-primary p-6">
      {/* Header */}
      <div className="max-w-7xl mx-auto mb-8">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-4xl font-bold mb-2">
              Investiční komise Gomes
            </h1>
            <p className="text-gray-400">
              AI analýza podle metodologie Marka Gomese
            </p>
          </div>
          
          {/* View Mode Toggle */}
          <div className="flex items-center gap-2">
            <button
              onClick={() => setViewMode('import')}
              className={`px-4 py-2 rounded-lg transition-colors ${
                viewMode === 'import'
                  ? 'bg-blue-600 text-text-primary'
                  : 'bg-gray-800 text-gray-300 hover:bg-gray-700'
              }`}
            >
              Importovat přepis
            </button>
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto">
        {/* Top Section: Top Picks Widget */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-6">
          {/* Top Picks */}
          <div className="lg:col-span-1">
            <TopPicksWidget
              minRating="BUY"
              limit={10}
              onTickerClick={handleTickerClick}
              autoRefresh={false}
            />
          </div>

          {/* Selected Ticker Analysis */}
          <div className="lg:col-span-2">
            {/* Import Mode */}
            {viewMode === 'import' ? (
              <TranscriptImporter 
                onImportSuccess={() => {
                  // Could refresh data here
                }}
                onClose={() => setViewMode('analysis')}
              />
            ) : viewMode === 'timeline' && selectedTicker ? (
              /* Timeline Mode */
              <TickerTimeline 
                ticker={selectedTicker}
                onClose={() => setViewMode('analysis')}
              />
            ) : loading ? (
              <div className="bg-gray-900 rounded-lg p-6 border border-gray-700 h-full flex items-center justify-center">
                <div className="text-center">
                  <div className="animate-spin h-12 w-12 border-4 border-blue-500 border-t-transparent rounded-full mx-auto mb-4" />
                  <p className="text-gray-400">
                    Analyzuji {selectedTicker}...
                  </p>
                </div>
              </div>
            ) : error ? (
              <div className="bg-gray-900 rounded-lg p-6 border border-negative/30">
                <h3 className="text-xl font-bold text-text-primary mb-4">
                  Chyba analýzy
                </h3>
                <p className="text-negative mb-4">{error}</p>
                <button
                  onClick={() => selectedTicker && handleTickerClick(selectedTicker)}
                  className="px-4 py-2 bg-red-600 hover:bg-red-700 text-text-primary rounded transition-colors"
                >
                  Zkusit znovu
                </button>
              </div>
            ) : tickerScore ? (
              <div>
                <GomesScoreCard
                  score={tickerScore}
                  onAnalyze={handleRefreshAnalysis}
                />
                {/* Timeline button */}
                <button
                  onClick={() => {
                    setSelectedTicker(tickerScore.ticker);
                    setViewMode('timeline');
                  }}
                  className="mt-4 w-full py-3 bg-purple-600 hover:bg-purple-700 text-text-primary rounded-lg transition-colors flex items-center justify-center gap-2"
                >
                  Zobrazit historii {tickerScore.ticker}
                </button>
              </div>
            ) : (
              <div className="bg-gray-900 rounded-lg p-6 border border-gray-700 h-full flex items-center justify-center">
                <div className="text-center text-gray-400">
                  <p className="text-lg mb-2">
                    Vyberte ticker z Top Výběrů
                  </p>
                  <p className="text-sm">
                    nebo klikněte na ticker v tabulce níže
                  </p>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Bottom Section: Full Watchlist Table */}
        <div>
          <WatchlistRankingTable
            minScore={5}
            limit={50}
            onTickerClick={handleTickerClick}
          />
        </div>

        {/* Info Footer */}
        <div className="mt-8 bg-blue-900/20 border border-blue-500/30 rounded-lg p-6">
          <h4 className="text-lg font-semibold text-blue-300 mb-3">
            O metodologii Gomes
          </h4>
          <div className="grid md:grid-cols-2 gap-4 text-sm text-gray-300">
            <div>
              <h5 className="font-semibold text-text-primary mb-2">Bodovací systém (0-10):</h5>
              <ul className="space-y-1 text-gray-400">
                <li>• Příběh/Katalyzátor: +2</li>
                <li>• Breakout pattern: +2</li>
                <li>• Insider nákupy: +2</li>
                <li>• ML predikce: +2</li>
                <li>• Volume trend: +1</li>
                <li>• Výsledky &lt; 14d: -5</li>
              </ul>
            </div>
            <div>
              <h5 className="font-semibold text-text-primary mb-2">Fáze životního cyklu:</h5>
              <ul className="space-y-1 text-gray-400">
                <li>• <strong>Skvělý nález</strong>: Časné momentum, NÁKUP</li>
                <li>• <strong>Čekací doba</strong>: Mrtvé peníze, VYHNOUT SE</li>
                <li>• <strong>Zlatý důl</strong>: Ziskové, instituce vstupují</li>
              </ul>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default GomesDashboard;


