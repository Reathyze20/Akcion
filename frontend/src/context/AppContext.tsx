/**
 * Application State Management
 * 
 * Simple React Context for global state management without external dependencies.
 */

import React, { createContext, useState, type ReactNode } from 'react';
import type { Stock, NavigationView, ViewMode } from '../types';

interface AppState {
  // Navigation
  currentView: NavigationView;
  setCurrentView: (view: NavigationView) => void;

  // Portfolio
  stocks: Stock[];
  setStocks: (stocks: Stock[] | ((prev: Stock[]) => Stock[])) => void;
  selectedStock: Stock | null;
  setSelectedStock: (stock: Stock | null) => void;

  // View Mode
  viewMode: ViewMode;
  setViewMode: (mode: ViewMode) => void;

  // Loading & Error States
  isLoading: boolean;
  setIsLoading: (loading: boolean) => void;
  error: string | null;
  setError: (error: string | null) => void;

  // Filters
  sentimentFilter: string | null;
  setSentimentFilter: (sentiment: string | null) => void;
  minConvictionScore: number | null;
  setminConvictionScore: (score: number | null) => void;
}

const AppContext = createContext<AppState | undefined>(undefined);

export const AppProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [currentView, setCurrentView] = useState<NavigationView>('analysis');
  const [stocks, setStocks] = useState<Stock[]>([]);
  const [selectedStock, setSelectedStock] = useState<Stock | null>(null);
  const [viewMode, setViewMode] = useState<ViewMode>('grid');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sentimentFilter, setSentimentFilter] = useState<string | null>(null);
  const [minConvictionScore, setminConvictionScore] = useState<number | null>(null);

  const value: AppState = {
    currentView,
    setCurrentView,
    stocks,
    setStocks,
    selectedStock,
    setSelectedStock,
    viewMode,
    setViewMode,
    isLoading,
    setIsLoading,
    error,
    setError,
    sentimentFilter,
    setSentimentFilter,
    minConvictionScore,
    setminConvictionScore,
  };

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
};

// Export context for custom hooks
export { AppContext };
