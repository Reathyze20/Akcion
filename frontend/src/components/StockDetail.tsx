/**
 * StockDetail Component
 * 
 * Full detailed view of a stock analysis in a modal.
 */

import React from 'react';
import type { Stock } from '../types';

interface StockDetailProps {
  stock: Stock;
  onClose: () => void;
}

export const StockDetail: React.FC<StockDetailProps> = ({ stock, onClose }) => {
  const getSentimentColor = (sentiment: string | null) => {
    switch (sentiment?.toUpperCase()) {
      case 'BULLISH':
        return 'text-accent-green';
      case 'BEARISH':
        return 'text-accent-red';
      case 'NEUTRAL':
        return 'text-text-secondary';
      default:
        return 'text-text-muted';
    }
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
      <div className="bg-primary-surface border border-border rounded-lg max-w-4xl w-full max-h-[90vh] overflow-y-auto custom-scrollbar">
        {/* Header */}
        <div className="sticky top-0 bg-primary-surface border-b border-border p-6 flex items-start justify-between">
          <div>
            <h2 className="text-3xl font-bold text-accent-blue mb-2">
              {stock.ticker}
            </h2>
            {stock.company_name && (
              <p className="text-lg text-text-secondary">{stock.company_name}</p>
            )}
          </div>
          <button
            onClick={onClose}
            className="text-text-muted hover:text-text-primary transition-colors text-2xl"
          >
            ×
          </button>
        </div>

        {/* Content */}
        <div className="p-6 space-y-6">
          {/* Overview Grid */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="card p-4">
              <p className="text-xs text-text-muted mb-1">Sentiment</p>
              <p className={`text-lg font-bold ${getSentimentColor(stock.sentiment)}`}>
                {stock.sentiment || 'N/A'}
              </p>
            </div>
            <div className="card p-4">
              <p className="text-xs text-text-muted mb-1">Gomes Score</p>
              <p className="text-lg font-bold text-accent-blue">
                {stock.gomes_score !== null ? `${stock.gomes_score}/10` : 'N/A'}
              </p>
            </div>
            <div className="card p-4">
              <p className="text-xs text-text-muted mb-1">Conviction</p>
              <p className="text-lg font-bold text-accent-purple">
                {stock.conviction_score !== null ? `${stock.conviction_score}/10` : 'N/A'}
              </p>
            </div>
            <div className="card p-4">
              <p className="text-xs text-text-muted mb-1">Action</p>
              <p className={`text-sm font-bold ${
                stock.action_verdict === 'BUY_NOW' ? 'text-green-400' :
                stock.action_verdict === 'ACCUMULATE' ? 'text-emerald-400' :
                stock.action_verdict === 'WATCH_LIST' ? 'text-yellow-400' :
                stock.action_verdict === 'TRIM' ? 'text-orange-400' :
                stock.action_verdict === 'SELL' ? 'text-red-400' :
                stock.action_verdict === 'AVOID' ? 'text-gray-400' :
                'text-text-secondary'
              }`}>
                {stock.action_verdict?.replace('_', ' ') || 'ANALYZE'}
              </p>
            </div>
          </div>

          {/* Trading Levels */}
          {(stock.entry_zone || stock.stop_loss_risk) && (
            <div className="grid grid-cols-2 gap-4">
              {stock.entry_zone && (
                <div className="card p-4 border-l-4 border-accent-blue">
                  <p className="text-xs text-text-muted mb-1">📍 Entry Zone</p>
                  <p className="text-lg font-bold text-accent-blue">{stock.entry_zone}</p>
                </div>
              )}
              {stock.stop_loss_risk && (
                <div className="card p-4 border-l-4 border-accent-red">
                  <p className="text-xs text-text-muted mb-1">🛑 Stop Loss / Risk</p>
                  <p className="text-sm font-medium text-accent-red">{stock.stop_loss_risk}</p>
                </div>
              )}
            </div>
          )}

          {/* Price Targets Section */}
          {(stock.price_target || stock.price_target_short || stock.price_target_long) && (
            <div className="card p-4">
              <h3 className="text-sm font-semibold text-accent-blue mb-3">
                💰 Price Targets
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {stock.price_target && (
                  <div className="bg-primary-card/50 rounded-lg p-3 border border-accent-blue/30">
                    <p className="text-xs text-text-muted mb-1">General Target</p>
                    <p className="text-lg font-bold text-accent-blue">{stock.price_target}</p>
                    {stock.time_horizon && (
                      <p className="text-xs text-text-secondary mt-1">⏱️ {stock.time_horizon}</p>
                    )}
                  </div>
                )}
                {stock.price_target_short && (
                  <div className="bg-primary-card/50 rounded-lg p-3 border border-accent-green/30">
                    <p className="text-xs text-text-muted mb-1">Short-Term Target</p>
                    <p className="text-lg font-bold text-accent-green">{stock.price_target_short}</p>
                  </div>
                )}
                {stock.price_target_long && (
                  <div className="bg-primary-card/50 rounded-lg p-3 border border-accent-purple/30">
                    <p className="text-xs text-text-muted mb-1">Long-Term Target</p>
                    <p className="text-lg font-bold text-accent-purple">{stock.price_target_long}</p>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Information Arbitrage / Edge */}
          {stock.edge && (
            <div className="card p-4">
              <h3 className="text-sm font-semibold text-accent-blue mb-2">
                Information Arbitrage (Edge)
              </h3>
              <p className="text-text-primary whitespace-pre-wrap">{stock.edge}</p>
            </div>
          )}

          {/* Catalysts */}
          {stock.catalysts && (
            <div className="card p-4">
              <h3 className="text-sm font-semibold text-accent-green mb-2">
                Catalysts
              </h3>
              <p className="text-text-primary whitespace-pre-wrap">{stock.catalysts}</p>
            </div>
          )}

          {/* Risks */}
          {stock.risks && (
            <div className="card p-4">
              <h3 className="text-sm font-semibold text-accent-red mb-2">
                Risks
              </h3>
              <p className="text-text-primary whitespace-pre-wrap">{stock.risks}</p>
            </div>
          )}

          {/* Raw Notes */}
          {stock.raw_notes && (
            <div className="card p-4">
              <h3 className="text-sm font-semibold text-text-secondary mb-2">
                Full Analysis
              </h3>
              <p className="text-sm text-text-secondary whitespace-pre-wrap font-mono">
                {stock.raw_notes}
              </p>
            </div>
          )}

          {/* Metadata */}
          <div className="card p-4 bg-primary-card/50">
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <p className="text-text-muted">Speaker</p>
                <p className="text-text-primary font-medium">{stock.speaker}</p>
              </div>
              <div>
                <p className="text-text-muted">Source</p>
                <p className="text-text-primary font-medium">{stock.source_type}</p>
              </div>
              <div>
                <p className="text-text-muted">Analyzed</p>
                <p className="text-text-primary font-medium">
                  {formatDate(stock.created_at)}
                </p>
              </div>
              <div>
                <p className="text-text-muted">ID</p>
                <p className="text-text-primary font-mono">{stock.id}</p>
              </div>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="sticky bottom-0 bg-primary-surface border-t border-border p-4 flex justify-end">
          <button onClick={onClose} className="btn btn-secondary px-6">
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
