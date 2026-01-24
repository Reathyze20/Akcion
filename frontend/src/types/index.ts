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
  next_catalyst: string | null; // Next catalyst: "Q1 EARNINGS / MAY 26"
  risks: string | null;
  raw_notes: string | null;
  
  // Trading action fields
  action_verdict: 'BUY_NOW' | 'ACCUMULATE' | 'WATCH_LIST' | 'TRIM' | 'SELL' | 'AVOID' | null;
  entry_zone: string | null;
  price_target_short: string | null;
  price_target_long: string | null;
  stop_loss_risk: string | null;
  moat_rating: number | null; // 1-5
  trade_rationale: string | null;
  chart_setup: string | null;
  
  // Price Lines data (from Gomes Intelligence)
  current_price: number | null;
  green_line: number | null;
  red_line: number | null;
  grey_line: number | null;
  price_position_pct: number | null; // 0-100%, where 0=at green, 100=at red
  price_zone: 'DEEP_VALUE' | 'BUY_ZONE' | 'ACCUMULATE' | 'FAIR_VALUE' | 'SELL_ZONE' | 'OVERVALUED' | null;
}

export interface StockAnalysisResult {
  ticker: string;
  company_name: string | null;
  sentiment: string;
  gomes_score: number;
  price_target: string | null;
  edge: string | null;
  catalysts: string | null;
  risks: string | null;
  status: string | null;
  time_horizon: string | null;
  conviction_score: number | null;
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
  stocks: StockAnalysisResult[];
  source_id: string;
  source_type: string;
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

// Phase 2: Portfolio Management Types

export type BrokerType = 'T212' | 'DEGIRO' | 'XTB';
export type MarketStatus = 'GREEN' | 'YELLOW' | 'ORANGE' | 'RED';
export type MatchSignal = 
  | 'OPPORTUNITY' 
  | 'ACCUMULATE' 
  | 'DANGER_EXIT' 
  | 'WAIT_MARKET_BAD' 
  | 'HOLD' 
  | 'NO_ACTION';

export interface Portfolio {
  id: number;
  name: string;
  owner: string; // e.g., "Já", "Přítelkyně"
  broker: BrokerType;
  created_at: string;
  updated_at: string;
  cash_balance?: number;
  monthly_contribution?: number; // Měsíční vklad v CZK
  position_count?: number;
  total_value?: number;
}

export interface Position {
  id: number;
  portfolio_id: number;
  ticker: string;
  company_name?: string | null;
  shares_count: number;
  avg_cost: number;
  current_price: number | null;
  last_price_update: string | null;
  cost_basis: number;
  market_value: number;
  unrealized_pl: number;
  unrealized_pl_percent: number;
  currency?: string;
  created_at: string;
  updated_at: string;
}

export interface PortfolioSummary {
  portfolio: Portfolio;
  positions: Position[];
  total_cost_basis: number;
  total_market_value: number;
  total_unrealized_pl: number;
  total_unrealized_pl_percent: number;
  total_value: number; // total_market_value + cash_balance
  cash_balance: number;
  last_price_update: string | null;
}

export interface EnrichedStock extends Stock {
  user_holding: boolean;
  holding_quantity: number | null;
  holding_avg_cost: number | null;
  holding_current_price: number | null;
  holding_unrealized_pl: number | null;
  holding_unrealized_pl_percent: number | null;
  match_signal: MatchSignal;
  market_status: MarketStatus;
}

export interface MatchAnalysisResponse {
  total_stocks: number;
  opportunities: number;
  accumulate: number;
  danger_exits: number;
  wait_market_bad: number;
  market_status: MarketStatus;
  stocks: EnrichedStock[];
}

export interface CSVUploadResponse {
  success: boolean;
  message: string;
  positions_created: number;
  positions_updated: number;
  errors: string[];
}

export interface PriceRefreshResponse {
  success: boolean;
  updated_count: number;
  failed_count: number;
  tickers: string[];
  prices: Record<string, number | null>;
}

export interface MarketStatusData {
  id: number;
  status: MarketStatus;
  last_updated: string;
  note: string | null;
}

// Gomes Analyzer Types

export type GomesRating = 'STRONG_BUY' | 'BUY' | 'HOLD' | 'AVOID' | 'HIGH_RISK';
export type LifecyclePhase = 'GREAT_FIND' | 'WAIT_TIME' | 'GOLD_MINE' | 'UNKNOWN';
export type MarketAlert = 'GREEN' | 'YELLOW' | 'ORANGE' | 'RED';

export interface GomesScoreResponse {
  ticker: string;
  total_score: number;
  rating: GomesRating;
  
  // Score components
  story_score: number;
  breakout_score: number;
  insider_score: number;
  ml_score: number;
  volume_score: number;
  earnings_penalty: number;
  
  // Metadata
  analysis_timestamp: string;
  confidence: 'HIGH' | 'MEDIUM' | 'LOW';
  reasoning: string;
  risk_factors: string[];
  
  // Data sources
  has_transcript: boolean;
  has_swot: boolean;
  has_ml_prediction: boolean;
  earnings_date: string | null;
  
  // Extended Gomes fields (from AI analysis)
  lifecycle_phase?: LifecyclePhase;
  green_line?: number | null;
  red_line?: number | null;
  is_undervalued?: boolean;
  firing_on_10_cylinders?: boolean | null;
  market_alert?: MarketAlert | null;
  catalysts?: string[];
  bull_case?: string;
  bear_case?: string;
}

export interface WatchlistRanking {
  ticker: string;
  score: number;
  rating: GomesRating;
  confidence: string;
  reasoning: string;
  last_analyzed: string;
}

export interface WatchlistRankingResponse {
  total_tickers: number;
  analyzed_tickers: number;
  rankings: WatchlistRanking[];
  timestamp: string;
}

export interface GomesAnalyzeRequest {
  ticker: string;
  transcript_text?: string;
  market_data?: {
    insider_buying?: boolean;
    earnings_date?: string;
  };
  force_refresh?: boolean;
}

export interface BatchAnalyzeResponse {
  total_requested: number;
  successful: number;
  failed: number;
  results: GomesScoreResponse[];
  errors: Array<{ ticker: string; error: string }>;
}

// ==================== Transcript & Timeline Types ====================

export interface TickerMention {
  id: number;
  ticker: string;
  mention_date: string;
  sentiment: 'VERY_BULLISH' | 'BULLISH' | 'NEUTRAL' | 'BEARISH' | 'VERY_BEARISH';
  action_mentioned: string | null;
  context_snippet: string | null;
  key_points: string[] | null;
  price_target: number | null;
  conviction_level: 'HIGH' | 'MEDIUM' | 'LOW' | null;
  source_name: string;
  video_url: string | null;
  weight: number;
  age_days: number;
}

export interface TickerTimelineResponse {
  ticker: string;
  total_mentions: number;
  latest_sentiment: string | null;
  latest_action: string | null;
  weighted_sentiment_score: number;
  mentions: TickerMention[];
}

export interface TranscriptImportRequest {
  source_name: string;
  video_date: string;
  raw_text: string;
  video_url?: string;
  transcript_quality?: 'high' | 'medium' | 'low';
}

export interface TranscriptImportResponse {
  transcript_id: number;
  source_name: string;
  video_date: string;
  detected_tickers: string[];
  ticker_mentions_created: number;
  message: string;
}

export interface TranscriptSummary {
  id: number;
  source_name: string;
  date: string;
  video_url: string | null;
  detected_tickers: string[];
  ticker_count: number;
  is_processed: boolean;
  quality: string;
  created_at: string | null;
}

// ==================== Gomes ML Stocks Types ====================

export interface GomesStockItem {
  ticker: string;
  company_name: string | null;
  gomes_score: number | null;
  sentiment: string | null;
  action_verdict: string | null;
  lifecycle_phase: string | null;
  
  // Price lines from Gomes
  green_line: number | null;
  red_line: number | null;
  current_price: number | null;
  price_zone: string | null;
  price_position_pct: number | null;
  
  // ML prediction
  has_ml_prediction: boolean;
  ml_direction: 'UP' | 'DOWN' | 'NEUTRAL' | null;
  ml_confidence: number | null;
  
  // Context
  video_date: string | null;
  notes: string | null;
}

export interface GomesMLStocksResponse {
  stocks: GomesStockItem[];
  total_count: number;
  stocks_with_lines: number;
  stocks_with_ml: number;
  market_alert: string;
}

// ==================== Price Lines History Types ====================

export interface PriceLinesHistoryItem {
  id: number;
  ticker: string;
  green_line: number | null;
  red_line: number | null;
  effective_from: string;
  valid_until: string | null;
  source: string | null;
  source_reference: string | null;
}

export interface PriceLinesHistoryResponse {
  ticker: string;
  total_records: number;
  current_green_line: number | null;
  current_red_line: number | null;
  history: PriceLinesHistoryItem[];
}

// ==================== Thesis Drift & Score History Types ====================

export type ThesisStatus = 'IMPROVED' | 'STABLE' | 'DETERIORATED' | 'BROKEN';
export type AlertSeverity = 'INFO' | 'WARNING' | 'CRITICAL';
export type DriftAlertType = 'HYPE_AHEAD_OF_FUNDAMENTALS' | 'THESIS_BREAKING' | 'ACCUMULATE_SIGNAL';

export interface ScoreHistoryPoint {
  id: number;
  ticker: string;
  gomes_score: number;
  thesis_status: ThesisStatus | null;
  action_signal: string | null;
  price_at_analysis: number | null;
  recorded_at: string;
  analysis_source: string | null;
}

export interface ScoreHistoryResponse {
  ticker: string;
  total_records: number;
  latest_score: number | null;
  score_trend: 'UP' | 'DOWN' | 'STABLE';
  history: ScoreHistoryPoint[];
}

export interface ThesisDriftAlert {
  id: number;
  ticker: string;
  alert_type: DriftAlertType;
  severity: AlertSeverity;
  old_score: number | null;
  new_score: number | null;
  price_change_pct: number | null;
  message: string;
  is_acknowledged: boolean;
  created_at: string;
}

export interface DriftAlertsResponse {
  total_alerts: number;
  unacknowledged: number;
  alerts: ThesisDriftAlert[];
}

// ==================== Kelly Allocator Types ====================

export interface AllocationRecommendation {
  ticker: string;
  gomes_score: number;
  kelly_weight_pct: number;
  recommended_amount: number;
  currency: string;
  reasoning: string;
  risk_level: 'LOW' | 'MEDIUM' | 'HIGH' | 'EXTREME';
}

export interface FamilyGap {
  ticker: string;
  holder: string;
  missing_from: string;
  gomes_score: number;
  action: string;
}

export interface AllocationPlanRequest {
  available_capital_czk: number;
  available_capital_eur: number;
}

export interface AllocationPlanResponse {
  total_available_czk: number;
  total_available_eur: number;
  recommendations: AllocationRecommendation[];
  total_allocated_czk: number;
  remaining_czk: number;
}

export interface FamilyAuditResponse {
  portfolios_compared: string[];
  gaps: FamilyGap[];
  summary: string;
}

// ==================== Deep Due Diligence Types ====================

export interface DeepDDData {
  ticker: string;
  company_name: string | null;
  gomes_score: number;
  thesis_status: 'IMPROVED' | 'STABLE' | 'DETERIORATED' | 'UNKNOWN';
  action_signal: 'BUY_NOW' | 'ACCUMULATE' | 'HOLD' | 'SELL' | 'AVOID';
  kelly_criterion_hint: number;
  inflection_status: string;
  green_line: number | null;
  red_line: number | null;
  current_price: number | null;
  catalysts: string[];
  risks: string[];
  edge: string | null;
  cash_runway_months: number | null;
  management_ownership_pct: number | null;
}

export interface DeepDDResponse {
  analysis_text: string;
  data: DeepDDData;
  thesis_drift: 'IMPROVED' | 'STABLE' | 'DETERIORATED';
  score_change: number;
}

export interface StockUpdateResponse {
  success: boolean;
  ticker: string;
  previous_score: number | null;
  new_score: number;
  score_change: number | null;
  thesis_drift: 'IMPROVED' | 'STABLE' | 'DETERIORATED' | null;
  action_signal: string;
  source_type: string;
  analysis_summary: string;
}

// Price Update Response (manual price update)
export interface PriceUpdateResponse {
  success: boolean;
  ticker: string;
  current_price: number;
  green_line: number | null;
  red_line: number | null;
  price_position_pct: number | null;
  price_zone: string | null;
  message: string;
}
