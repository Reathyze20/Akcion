/**
 * App State Hook
 * 
 * Custom hook to access application state from context.
 * Separated from AppContext to maintain Fast Refresh compatibility.
 */

import { useContext } from 'react';
import type { Stock, NavigationView, ViewMode } from '../types';
import { AppContext } from '../context/AppContext';

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
  minGomesScore: number | null;
  setMinGomesScore: (score: number | null) => void;
}

export const useAppState = (): AppState => {
  const context = useContext(AppContext);
  if (!context) {
    throw new Error('useAppState must be used within AppProvider');
  }
  return context;
};
