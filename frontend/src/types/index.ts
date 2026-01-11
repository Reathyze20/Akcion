/**
 * TypeScript Type Definitions for Akcion Investment Analysis
 * 
 * These types match the Pydantic models from the FastAPI backend.
 */

export interface Stock {
  id: number;
  created_at: string;
  ticker: string;
  company_name: string | null;
  source_type: string;
  speaker: string;
  sentiment: 'BULLISH' | 'BEARISH' | 'NEUTRAL' | null;
  gomes_score: number | null;
  conviction_score: number | null;
  price_target: string | null;
  time_horizon: string | null;
  edge: string | null; // Information Arbitrage
  catalysts: string | null;
  risks: string | null;
  raw_notes: string | null;
}

export interface AnalysisRequest {
  transcript: string;
  speaker: string;
  source_type?: string;
}

export interface YouTubeAnalysisRequest {
  url: string;
  speaker?: string;
}

export interface GoogleDocsAnalysisRequest {
  url: string;
  speaker: string;
}

export interface AnalysisResponse {
  success: boolean;
  message: string;
  stocks_found: number;
  stocks: Stock[];
}

export interface PortfolioResponse {
  total_stocks: number;
  stocks: Stock[];
  filters_applied: Record<string, string | number> | null;
}

export interface PortfolioStats {
  total_analyses: number;
  unique_tickers: number;
  sentiment_breakdown: {
    bullish: number;
    bearish: number;
    neutral: number;
  };
  high_conviction_count: number;
  average_gomes_score: number;
  average_conviction_score: number;
}

export interface ErrorResponse {
  success: false;
  error: string;
  detail?: string;
}

export type ViewMode = 'grid' | 'list' | 'table';
export type NavigationView = 'analysis' | 'portfolio';
