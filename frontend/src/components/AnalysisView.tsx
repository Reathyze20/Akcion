/**
 * AnalysisView Component
 * 
 * Main dashboard with "Top Picks" section highlighting BUY_NOW and ACCUMULATE stocks
 */

import React from 'react';
import { StockCard } from './StockCard';
import { TrendingUp, Zap, Eye, AlertCircle } from 'lucide-react';
import type { Stock } from '../types';

interface AnalysisViewProps {
  stocks: Stock[];
  onStockClick: (stock: Stock) => void;
}

export const AnalysisView: React.FC<AnalysisViewProps> = ({ stocks, onStockClick }) => {
  
  // Separate stocks by action verdict
  const topPicks = stocks.filter(s => 
    s.action_verdict === 'BUY_NOW' || s.action_verdict === 'ACCUMULATE'
  );
  
  const watchList = stocks.filter(s => 
    s.action_verdict === 'WATCH_LIST'
  );
  
  const otherStocks = stocks.filter(s => 
    !['BUY_NOW', 'ACCUMULATE', 'WATCH_LIST'].includes(s.action_verdict || '')
  );

  const renderSection = (title: string, items: Stock[], icon: React.ElementType, iconColor: string, emptyMessage: string) => (
    <div className="mb-12">
      <div className="flex items-center gap-3 mb-6">
        {React.createElement(icon, { className: `w-6 h-6 ${iconColor}` })}
        <h2 className="text-2xl font-bold text-text-primary">{title}</h2>
        <span className="px-3 py-1 bg-surface-raised/50 rounded-full text-sm text-text-secondary font-mono">
          {items.length}
        </span>
      </div>
      
      {items.length === 0 ? (
        <div className="bg-surface-raised/30 backdrop-blur border border-white/5 rounded-2xl p-12 text-center">
          <AlertCircle className="w-12 h-12 text-slate-600 mx-auto mb-4" />
          <p className="text-text-secondary">{emptyMessage}</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {items.map(stock => (
            <StockCard 
              key={stock.id} 
              stock={stock} 
              onClick={() => onStockClick(stock)} 
            />
          ))}
        </div>
      )}
    </div>
  );

  return (
    <div className="space-y-12 animate-in fade-in duration-500">
      {/* Page Header */}
      <div>
        <h1 className="text-3xl font-bold text-text-primary mb-2">
          Přehled investičních signálů
        </h1>
        <p className="text-text-secondary text-sm">
          Akcionovátelné investiční příležitosti podle metodologie Marka Gomese
        </p>
      </div>

      {/* Stats Bar */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="bg-positive/10 border border-positive/30 rounded-xl p-4">
          <div className="text-positive text-sm font-semibold mb-1">SILNÉ NÁKUPY</div>
          <div className="text-3xl font-bold text-text-primary font-mono">{topPicks.length}</div>
        </div>
        <div className="bg-warning/10 border border-yellow-500/30 rounded-xl p-4">
          <div className="text-warning text-sm font-semibold mb-1">SLEDOVANÉ</div>
          <div className="text-3xl font-bold text-text-primary font-mono">{watchList.length}</div>
        </div>
        <div className="bg-accent/10 border border-indigo-500/30 rounded-xl p-4">
          <div className="text-accent text-sm font-semibold mb-1">CELKEM AKCIÍ</div>
          <div className="text-3xl font-bold text-text-primary font-mono">{stocks.length}</div>
        </div>
        <div className="bg-accent/10 border border-purple-500/30 rounded-xl p-4">
          <div className="text-accent text-sm font-semibold mb-1">PRůM. SKÓRE</div>
          <div className="text-3xl font-bold text-text-primary font-mono">
            {stocks.length > 0 
              ? (stocks.reduce((sum, s) => sum + (s.conviction_score || 0), 0) / stocks.length).toFixed(1)
              : '0.0'
            }
          </div>
        </div>
      </div>

      {/* Top Picks Section - PRIORITY */}
      {renderSection(
        'Nejlepší týpky tohoto týdne',
        topPicks,
        TrendingUp,
        'text-positive',
        'Žádné silné nákupní signály. Zkontrolujte po další analýze.'
      )}

      {/* Watch List Section */}
      {renderSection(
        'Sledované',
        watchList,
        Eye,
        'text-warning',
        'Žádné akcie na sledování. Přidejte analýzu se specifickými vstupními body.'
      )}

      {/* Other Stocks Section */}
      {otherStocks.length > 0 && renderSection(
        'Všechny ostatní akcie',
        otherStocks,
        Zap,
        'text-text-secondary',
        ''
      )}
    </div>
  );
};


