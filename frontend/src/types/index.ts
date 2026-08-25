/**
 * TypeScript Type Definitions for Akcion Investment Analysis
 * 
 * These types match the Pydantic models from the FastAPI backend.
 */

export interface Stock {
  id: number;
  created_at: string;
  ticker: string;
  /**
   * Ticker, pod kterým se firma páruje napříč burzami — KUYA.V i KUYAF mají
   * KUYAF. Počítá ho backend (`app/core/tickers.py`), tady se jen používá.
   * Zobrazuje se vždycky `ticker`, ne tohle.
   */
  canonical_ticker?: string | null;
  company_name: string | null;
  source_type: string;
  /** GOMES / BREAKOUT_INVESTORS / OTHER — na ticker může být řádek od každého. */
  source_key?: 'GOMES' | 'BREAKOUT_INVESTORS' | 'OTHER' | null;
  speaker: string;
  sentiment: 'BULLISH' | 'BEARISH' | 'NEUTRAL' | null;
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
  
  // Price Lines data (from Investment Intelligence)
  current_price: number | null;
  green_line: number | null;
  red_line: number | null;
  grey_line: number | null;
  price_position_pct: number | null; // 0-100%, where 0=at green, 100=at red
  price_zone: 'DEEP_VALUE' | 'BUY_ZONE' | 'ACCUMULATE' | 'FAIR_VALUE' | 'SELL_ZONE' | 'OVERVALUED' | null;
  
  // Master Conviction Table (2026-01-25)
  asset_class?: string | null;
  cash_runway_months?: number | null;
  insider_ownership_pct?: number | null;
  fully_diluted_market_cap?: number | null;
  enterprise_value?: number | null;
  quarterly_burn_rate?: number | null;
  total_cash?: number | null;
  inflection_status?: 'WAIT_TIME' | 'UPCOMING' | 'ACTIVE_GOLD_MINE' | null;
  primary_catalyst?: string | null;
  catalyst_date?: string | null;
  thesis_narrative?: string | null;
  price_floor?: number | null;
  price_target_24m?: number | null;
  current_valuation_stage?: 'UNDERVALUED' | 'FAIR' | 'OVERVALUED' | 'BUBBLE' | null;
  price_base?: number | null;
  price_moon?: number | null;
  forward_pe_2027?: number | null;
  max_allocation_cap?: number | null;
  stop_loss_price?: number | null;
  insider_activity?: 'BUYING' | 'HOLDING' | 'SELLING' | null;
  market_cap?: number | null;
  
  // Trading Zones (Calculated from Price Lines)
  max_buy_price?: number | null;
  start_sell_price?: number | null;
  risk_to_floor_pct?: number | null;
  upside_to_ceiling_pct?: number | null;
  trading_zone_signal?: 'AGGRESSIVE_BUY' | 'BUY' | 'HOLD' | 'SELL' | 'STRONG_SELL' | null;
}

export interface StockAnalysisResult {
  ticker: string;
  company_name: string | null;
  sentiment: string;
  conviction_score: number | null;
  price_target: string | null;
  edge: string | null;
  catalysts: string | null;
  risks: string | null;
  status: string | null;
  time_horizon: string | null;
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
  /** Viz `Stock.canonical_ticker`. Pro párování pozice s analýzou. */
  canonical_ticker?: string | null;
  /**
   * Majitel potvrdil, že měna sedí s výpisem od brokera. Umlčí kontrolu
   * podle přípony tickeru, která u IMP.V a KUYA.V hlásí konflikt,
   * přestože EUR je správně.
   */
  currency_confirmed?: boolean;
  /**
   * Měna, kterou napovídá přípona tickeru, když nesedí s uloženou. `null`
   * znamená „sedí" i „nedá se říct" — ty dva se nerozlišují schválně.
   */
  currency_conflict?: string | null;
  company_name?: string | null;
  shares_count: number;
  // null = purchase price unknown (Degiro exports carry none) — user must
  // fill it in; P/L fields are null until then, never fabricated.
  avg_cost: number | null;
  current_price: number | null;
  last_price_update: string | null;
  cost_basis: number | null;
  market_value: number;
  unrealized_pl: number | null;
  unrealized_pl_percent: number | null;
  currency?: string;
  created_at: string;
  updated_at: string;
}

export interface UnconvertiblePosition {
  ticker: string;
  currency: string;
  reason: string;
}

/** A standing owner instruction that suppresses BUY/ACCUMULATE for this ticker, independent of phase. */
export interface OwnerIntent {
  ticker: string;
  intent: 'EXIT_PENDING' | 'TAX_LOSS_HOLD' | string;
  note: string | null;
  set_by: string;
  set_at: string;
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
  /** Non-empty means the totals above are incomplete — a currency this app cannot rate. */
  unconvertible_positions: UnconvertiblePosition[];
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
  // Tickers imported without a purchase price — user must fill avg_cost in.
  missing_avg_cost?: string[];
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

// Conviction Analyzer Types

export type ConvictionRating = 'STRONG_BUY' | 'BUY' | 'HOLD' | 'AVOID' | 'HIGH_RISK';
export type LifecyclePhase = 'GREAT_FIND' | 'WAIT_TIME' | 'GOLD_MINE' | 'UNKNOWN';
export type MarketAlert = 'GREEN' | 'YELLOW' | 'ORANGE' | 'RED';

export interface ConvictionScoreResponse {
  ticker: string;
  total_score: number;
  rating: ConvictionRating;
  
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
  
  // Extended analysis fields (from AI analysis)
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
  rating: ConvictionRating;
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

export interface AnalyzeRequest {
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
  results: ConvictionScoreResponse[];
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

export interface ScoredStockItem {
  ticker: string;
  company_name: string | null;
  conviction_score: number | null;
  sentiment: string | null;
  action_verdict: string | null;
  lifecycle_phase: string | null;
  
  // Price lines from analysis
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

export interface ScoredStocksResponse {
  stocks: ScoredStockItem[];
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
  conviction_score: number;
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
  conviction_score: number;
  kelly_weight_pct: number;
  recommended_amount: number;
  currency: string;
  reasoning: string;
  risk_level: 'LOW' | 'MEDIUM' | 'HIGH' | 'EXTREME';
}

/**
 * Pozor: tenhle typ musí sedět na to, co skutečně posílá
 * `GET /api/portfolio/family-audit` (backend/app/routes/portfolio.py:1065).
 *
 * Dřív tu stálo `holder` / `missing_from` / `action` — tři jména, která
 * backend nikdy neposlal. Odpověď se jen přetypuje, nevaliduje, takže
 * TypeScript mlčel a panel vykresloval „holds, does not" s prázdnými jmény.
 */
export interface FamilyGap {
  ticker: string;
  company_name: string | null;
  /** Null, dokud pozice nemá hodnocení. Není to nula. */
  conviction_score: number | null;
  owner_with_position: string;
  owner_weight_pct: number;
  missing_owner: string;
  priority: string;
  message: string;
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
  gaps: FamilyGap[];
  /* Volitelné schválně: dvě větve endpointu (portfolio.py:1045 a :1058)
     vracejí jen `message` a prázdné `gaps`. */
  owners_analyzed?: string[];
  gaps_found?: number;
  message?: string;
}

// ==================== Deep Due Diligence Types ====================

export interface DeepDDData {
  ticker: string;
  company_name: string | null;
  conviction_score: number;
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

// Trade ledger — recording a BUY/SELL executed at the broker.

export type TradeSide = 'BUY' | 'SELL';

export interface TradeRequest {
  side: TradeSide;
  shares: number;
  price: number;
  emotion_tag?: string | null;
  note?: string | null;
  /**
   * Den obchodu u brokera (YYYY-MM-DD), ne den zápisu. Bez něj se zpětný
   * zápis starého prodeje počítá jako dnešní obchod.
   */
  trade_date?: string | null;
}

export interface TradeResponse {
  success: boolean;
  log_id: number;
  ticker: string;
  side: TradeSide;
  shares: number;
  price: number;
  currency: string | null;
  gross_amount: number;
  /** null (never 0) when the purchase price was never known. */
  realized_pl: number | null;
  cost_basis: number | null;
  new_shares_count: number;
  new_avg_cost: number | null;
  avg_cost_known: boolean;
  position_closed: boolean;
  message: string;
}

// ============================================================================
// Pásmo — kde cena leží vůči tomu, co si firma zaslouží
// ============================================================================

/**
 * Pásma tak, jak je počítá `ZoneLadder` na serveru.
 *
 * Není to poloha v rozpětí. `POD_ZELENOU` a `NAD_CERVENOU` jsou o ceně, ale
 * `NAKUP`, `DRZET` a `PREPLACENO` porovnávají R/R skóre se zaslouženou úrovní
 * `10 − válce` — tedy stejná cena u dvou různě kvalitních firem dá jiné pásmo.
 * Prohlížeč to nikdy nedopočítává; kdyby ano, ukázal by jiné číslo než engine.
 */
export type Band =
  | 'POD_ZELENOU'
  | 'NAKUP'
  | 'DRZET'
  | 'PREPLACENO'
  | 'NAD_CERVENOU'
  | 'NEZNAME'
  | 'MIMO_METODIKU';

export interface LadderItem {
  ticker: string;
  company_name?: string | null;
  band: Band;
  reason_cs: string;
  rr_score?: number | null;
  deserved?: number | null;
  /** Limitky odvozené z linií, ne z dnešní ceny — přežijí zastaralý kurz. */
  buy_below?: number | null;
  sell_above?: number | null;
  take_profit_above?: number | null;
  add_below?: number | null;
  line_currency?: string | null;
  trigger: string;
  trigger_reason: string;
  /** Potvrzení válců vypršelo: prodejní strana platí, nákupní ne. */
  quality_expired: boolean;
}

export interface LadderResponse {
  generated_at: string;
  items: LadderItem[];
  with_band: number;
  outside_method: number;
}

// ============================================================================
// Tabule „co s tímhle" — jedna karta na firmu, pokyn pro každý účet
// ============================================================================

/** Co má jeden člověk udělat s jednou firmou. */
export interface OwnerLine {
  owner: string;
  portfolio_id: number;
  /** Už česky. Tuhle obrazovku čte někdo, kdo enum nezná. */
  instruction_cs: string;
  detail_cs: string;
  action_type?: string | null;
  quantity?: number | null;
  limit_price?: number | null;
  limit_currency?: string | null;
  estimated_czk?: number | null;
  valid_until?: string | null;
  urgency: number;
  /** Podíl na JEHO účtu, nikdy na součtu obou. */
  weight_pct?: number | null;
  holds: boolean;
}

/** Druhý zdroj, v jedné větě. */
export interface BreakoutLine {
  stance: 'SOUHLASI' | 'NESOUHLASI' | 'MLCI';
  summary_cs: string;
  target?: number | null;
  endorsements: number;
  /** Vyplněné jen tehdy, když něco napsal jmenovaný analytik. */
  analyst?: string | null;
  verdict?: string | null;
  notes_cs: string[];
}

/**
 * Ochranná rezerva — jediné čtení na kartě, které měří dolů.
 *
 * Pásmo, R/R i cíl Breakoutu počítají vzdálenost ke stropu. Tohle se ptá
 * opačně: co drží cenu zdola, když se teze rozpadne. Podlaha je jen z hmotných
 * aktiv — goodwill a nehmotná se při rozbité tezi odepisují první.
 */
export interface SafetyLine {
  floor?: number | null;
  /** TANGIBLE_BOOK je víc než NET_CASH a karta to řekne. */
  layer: 'TANGIBLE_BOOK' | 'NET_CASH' | 'NONE';
  downside_pct?: number | null;
  upside_pct?: number | null;
  asymmetry?: number | null;
  below_floor: boolean;
  notes_cs: string[];
}

export interface BoardCard {
  ticker: string;
  company_name?: string | null;
  band: Band;
  band_label_cs: string;
  band_reason_cs: string;
  rr_score: number | null;
  deserved: number | null;
  buy_below?: number | null;
  sell_above?: number | null;
  take_profit_above?: number | null;
  add_below?: number | null;
  line_currency?: string | null;
  trigger: string;
  trigger_reason: string;
  quality_expired: boolean;
  breakout?: BreakoutLine | null;
  /** Kam až může cena spadnout, než ji něco skutečného zastaví. */
  safety?: SafetyLine | null;
  /** Co appka umí říct o TÉHLE firmě. Na kartě, ne ve zdi nad všemi. */
  notes_cs: string[];
  owners: OwnerLine[];
  urgency: number;
}

export interface BoardResponse {
  generated_at: string;
  cards: BoardCard[];
  /** Varování o celém portfoliu — mění, jak se má číst každá karta. */
  warnings: string[];
  market_alert?: string | null;
}

/** Jedna denní svíčka. Zdroj: tabulka `ohlcv_data`, ne živý kurz. */
export interface OhlcvBar {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface OhlcvResponse {
  ticker: string;
  count: number;
  data: OhlcvBar[];
}

export interface IntakeAnalysisResult {
  ticker: string;
  original_ticker?: string | null;
  company_name: string;
  source_type: string;
  speaker: string;
  green_line?: number | null;
  red_line?: number | null;
  grey_line?: number | null;
  cylinders?: number | null;
  lifecycle_phase: 'GREAT_FIND' | 'WAIT_TIME' | 'GOLD_MINE' | 'UNKNOWN';
  conviction_score?: number | null;
  primary_catalyst?: string | null;
  milestones: string[];
  red_flags: string[];
  verbatim_quote?: string | null;
  summary_cz: string;
  recommended_action: 'BUY' | 'WAIT' | 'SELL' | 'WATCH' | 'RESEARCH';
}

export interface IntakeCommitResponse {
  success: boolean;
  ticker: string;
  message: string;
}
