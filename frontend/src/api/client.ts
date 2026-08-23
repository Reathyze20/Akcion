/**
 * API Client for Akcion Backend
 * 
 * Centralized API communication layer for the FastAPI backend.
 */

import axios, { type AxiosInstance, type AxiosError } from 'axios';
import { handleApiError } from '../utils/errorHandling';
import type {
  Stock,
  AnalysisRequest,
  YouTubeAnalysisRequest,
  GoogleDocsAnalysisRequest,
  AnalysisResponse,
  PortfolioResponse,
  PortfolioStats,
  ErrorResponse,
  // Phase 2 types
  Portfolio,
  PortfolioSummary,
  Position,
  EnrichedStock,
  MatchAnalysisResponse,
  CSVUploadResponse,
  PriceRefreshResponse,
  MarketStatusData,
  BrokerType,
  MarketStatus,
  // Trade ledger
  TradeRequest,
  TradeResponse,
  // Gomes Analyzer types
  ConvictionScoreResponse,
  AnalyzeRequest,
  WatchlistRankingResponse,
  BatchAnalyzeResponse,
  // Timeline types
  TickerTimelineResponse,
  TranscriptImportRequest,
  TranscriptImportResponse,
  TranscriptSummary,
  // ML Stocks types
  ScoredStocksResponse,
  // Price Lines History
  PriceLinesHistoryResponse,
  // Score History & Kelly
  DriftAlertsResponse,
  AllocationPlanResponse,
  FamilyAuditResponse,
  // Deep DD
  DeepDDResponse,
  StockUpdateResponse,
  PriceUpdateResponse,
} from '../types';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8002';

class ApiClient {
  private client: AxiosInstance;

  constructor(baseURL: string = API_BASE_URL) {
    this.client = axios.create({
      baseURL,
      headers: {
        'Content-Type': 'application/json',
      },
      timeout: 60000, // 60 seconds for AI analysis
    });

    // Response interceptor for centralized error handling
    this.client.interceptors.response.use(
      (response) => response,
      (error: AxiosError<ErrorResponse>) => {
        // Use centralized error handler
        const apiError = handleApiError(error);
        
        // Log structured error
        console.error('[API Client Error]', {
          type: apiError.type,
          message: apiError.message,
          detail: apiError.detail,
          statusCode: apiError.statusCode,
          url: error.config?.url,
          method: error.config?.method
        });
        
        // Throw the structured error for upstream handling
        throw apiError;
      }
    );
  }

  // ==================== Analysis Endpoints ====================

  async analyzeText(request: AnalysisRequest): Promise<AnalysisResponse> {
    const response = await this.client.post<AnalysisResponse>(
      '/api/analyze/text',
      request
    );
    return response.data;
  }

  async analyzeYouTube(request: YouTubeAnalysisRequest): Promise<AnalysisResponse> {
    const response = await this.client.post<AnalysisResponse>(
      '/api/analyze/youtube',
      request
    );
    return response.data;
  }

  async analyzeGoogleDocs(request: GoogleDocsAnalysisRequest): Promise<AnalysisResponse> {
    const response = await this.client.post<AnalysisResponse>(
      '/api/analyze/google-docs',
      request
    );
    return response.data;
  }

  async analyzeUrl(request: { url: string }): Promise<AnalysisResponse> {
    // Try to detect if it's a YouTube URL or plain text
    const isYouTube = request.url.includes('youtube.com') || request.url.includes('youtu.be');
    const isGoogleDocs = request.url.includes('docs.google.com');
    
    if (isYouTube) {
      const response = await this.client.post<AnalysisResponse>(
        '/api/analyze/youtube',
        { url: request.url, speaker: 'Unknown' }
      );
      return response.data;
    } else if (isGoogleDocs) {
      const response = await this.client.post<AnalysisResponse>(
        '/api/analyze/google-docs',
        { url: request.url, speaker: 'Unknown' }
      );
      return response.data;
    } else {
      // Treat as plain text/transcript
      const response = await this.client.post<AnalysisResponse>(
        '/api/analyze/text',
        { transcript: request.url, speaker: 'Unknown' }
      );
      return response.data;
    }
  }

  // ==================== Portfolio Endpoints ====================

  async getStocks(filters?: {
    sentiment?: string;
    min_conviction_score?: number;
    min_conviction?: number;
    speaker?: string;
  }): Promise<PortfolioResponse> {
    const response = await this.client.get<PortfolioResponse>('/api/stocks', {
      params: filters,
    });
    return response.data;
  }

  async getEnrichedStocks(): Promise<PortfolioResponse> {
    const response = await this.client.get<PortfolioResponse>(
      '/api/stocks/enriched'
    );
    return response.data;
  }

  async getHighConvictionStocks(): Promise<PortfolioResponse> {
    const response = await this.client.get<PortfolioResponse>(
      '/api/stocks/high-conviction'
    );
    return response.data;
  }

  async getStockByTicker(ticker: string): Promise<Stock> {
    const response = await this.client.get<Stock>(`/api/stocks/${ticker}`);
    return response.data;
  }

  async getTickerHistory(ticker: string): Promise<Stock[]> {
    const response = await this.client.get<Stock[]>(
      `/api/stocks/${ticker}/history`
    );
    return response.data;
  }

  async getPortfolioStats(): Promise<PortfolioStats> {
    const response = await this.client.get<PortfolioStats>(
      '/api/stocks/stats/summary'
    );
    return response.data;
  }

  // ==================== Phase 2: Portfolio Management ====================

  async getPortfolios(owner?: string): Promise<Portfolio[]> {
    const params = owner ? { owner } : {};
    const response = await this.client.get<Portfolio[]>('/api/portfolio/portfolios', { params });
    return response.data;
  }

  async createPortfolio(name: string, owner: string, broker: BrokerType): Promise<Portfolio> {
    const response = await this.client.post<Portfolio>('/api/portfolio/portfolios', {
      name,
      owner,
      broker,
    });
    return response.data;
  }

  async getPortfolioSummary(portfolioId: number): Promise<PortfolioSummary> {
    const response = await this.client.get<PortfolioSummary>(
      `/api/portfolio/portfolios/${portfolioId}`
    );
    return response.data;
  }

  async deletePortfolio(portfolioId: number): Promise<void> {
    await this.client.delete(`/api/portfolio/portfolios/${portfolioId}`);
  }

  async uploadCSV(
    portfolioId: number,
    broker: BrokerType,
    file: File
  ): Promise<CSVUploadResponse> {
    const formData = new FormData();
    formData.append('portfolio_id', portfolioId.toString());
    formData.append('broker', broker);
    formData.append('file', file);

    const response = await this.client.post<CSVUploadResponse>(
      '/api/portfolio/upload-csv',
      formData,
      {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      }
    );
    return response.data;
  }

  async addPosition(
    portfolioId: number,
    data: {
      ticker: string;
      shares_count: number;
      avg_cost: number;
      current_price?: number;
      company_name?: string;
    }
  ): Promise<{
    success: boolean;
    action: 'created' | 'updated';
    position: {
      id: number;
      ticker: string;
      shares_count: number;
      avg_cost: number;
      current_price: number;
      market_value: number;
    };
  }> {
    const response = await this.client.post(
      `/api/portfolio/portfolios/${portfolioId}/positions`,
      data
    );
    return response.data;
  }

  async removePosition(
    portfolioId: number,
    ticker: string
  ): Promise<{ success: boolean; message: string }> {
    const response = await this.client.delete(
      `/api/portfolio/portfolios/${portfolioId}/positions/${ticker}`
    );
    return response.data;
  }

  async refreshPrices(portfolioId?: number): Promise<PriceRefreshResponse> {
    const response = await this.client.post<PriceRefreshResponse>(
      '/api/portfolio/refresh',
      { portfolio_id: portfolioId }
    );
    return response.data;
  }

  async getPositions(portfolioId?: number): Promise<Position[]> {
    const response = await this.client.get<Position[]>('/api/portfolio/positions', {
      params: portfolioId ? { portfolio_id: portfolioId } : {},
    });
    return response.data;
  }

  // ==========================================================================
  // SEC EDGAR — results, outlook, insiders
  // ==========================================================================

  async getSecData(ticker: string): Promise<SecTickerData> {
    const response = await this.client.get<SecTickerData>(
      `/api/sec/${encodeURIComponent(ticker)}`
    );
    return response.data;
  }

  async syncSecTicker(ticker: string, withOutlook = true): Promise<SecSyncResult> {
    const response = await this.client.post<SecSyncResult>(
      `/api/sec/sync/${encodeURIComponent(ticker)}`,
      null,
      { params: { with_outlook: withOutlook } }
    );
    return response.data;
  }

  async syncSecAll(withOutlook = false): Promise<SecSyncResult[]> {
    const response = await this.client.post<SecSyncResult[]>(
      '/api/sec/sync', null, { params: { with_outlook: withOutlook } }
    );
    return response.data;
  }


  // ==========================================================================
  // Away mode — one message a day, and never one built on stale data
  // ==========================================================================

  async getAwayStatus(): Promise<AwayStatus> {
    const response = await this.client.get<AwayStatus>('/api/away');
    return response.data;
  }

  async setAwayMode(update: AwayUpdate): Promise<AwayStatus> {
    const response = await this.client.put<AwayStatus>('/api/away', update);
    return response.data;
  }

  async previewAway(): Promise<AwayPreview> {
    const response = await this.client.post<AwayPreview>('/api/away/preview');
    return response.data;
  }

  // ==========================================================================
  // Market gauge — where the S&P sits on its 40-year chart
  // ==========================================================================

  async getMarketGauge(refresh = false): Promise<MarketGauge> {
    const response = await this.client.get<MarketGauge>(
      '/api/market-gauge', { params: { refresh } }
    );
    return response.data;
  }

  // ==========================================================================
  // Cash and hedge — the semafor in instruments, not percentages
  // ==========================================================================

  async getCashHedgePlan(alert?: string): Promise<CashHedgePlan> {
    const response = await this.client.get<CashHedgePlan>(
      '/api/cash-hedge', { params: alert ? { alert } : undefined }
    );
    return response.data;
  }

  async deletePosition(positionId: number): Promise<void> {
    await this.client.delete(`/api/portfolio/positions/${positionId}`);
  }

  async updatePosition(
    positionId: number,
    data: {
      shares_count?: number;
      avg_cost?: number;
      current_price?: number;
      currency?: string;
      company_name?: string;
      ticker?: string;
    }
  ): Promise<Position> {
    const response = await this.client.put<Position>(
      `/api/portfolio/positions/${positionId}`,
      data
    );
    return response.data;
  }

  /**
   * Record a BUY/SELL already executed at the broker.
   *
   * Writes the ledger row and moves the position server-side in ONE
   * transaction — do not emulate this with updatePosition(), which discards
   * the trade price and leaves realized P/L unrecoverable.
   */
  async recordTrade(
    positionId: number,
    trade: TradeRequest
  ): Promise<TradeResponse> {
    const response = await this.client.post<TradeResponse>(
      `/api/portfolio/positions/${positionId}/trade`,
      trade
    );
    return response.data;
  }

  async updateCashBalance(
    portfolioId: number,
    cashBalance: number
  ): Promise<{ success: boolean; cash_balance: number }> {
    const response = await this.client.put(
      `/api/portfolio/portfolios/${portfolioId}/cash-balance?cash_balance=${cashBalance}`
    );
    return response.data;
  }

  async updateMonthlyContribution(
    portfolioId: number,
    monthlyContribution: number
  ): Promise<{ success: boolean; monthly_contribution: number }> {
    const response = await this.client.put(
      `/api/portfolio/portfolios/${portfolioId}/monthly-contribution?monthly_contribution=${monthlyContribution}`
    );
    return response.data;
  }

  async deleteAllPositions(portfolioId: number): Promise<{ success: boolean; message: string; deleted_count: number }> {
    const response = await this.client.delete(`/api/portfolio/portfolios/${portfolioId}/positions`);
    return response.data;
  }

  async getOwners(): Promise<string[]> {
    const response = await this.client.get<string[]>('/api/portfolio/owners');
    return response.data;
  }

  async getMarketStatus(): Promise<MarketStatusData> {
    const response = await this.client.get<MarketStatusData>(
      '/api/portfolio/market-status'
    );
    return response.data;
  }

  async updateMarketStatus(
    status: MarketStatus,
    note?: string
  ): Promise<MarketStatusData> {
    const response = await this.client.put<MarketStatusData>(
      '/api/portfolio/market-status',
      { status, note }
    );
    return response.data;
  }

  // ==================== Phase 2: Gap Analysis ====================

  async getMatchAnalysis(portfolioId?: number): Promise<MatchAnalysisResponse> {
    const response = await this.client.get<MatchAnalysisResponse>(
      '/api/analysis/match',
      {
        params: portfolioId ? { portfolio_id: portfolioId } : {},
      }
    );
    return response.data;
  }

  async getOpportunities(portfolioId?: number): Promise<EnrichedStock[]> {
    const response = await this.client.get<EnrichedStock[]>(
      '/api/analysis/opportunities',
      {
        params: portfolioId ? { portfolio_id: portfolioId } : {},
      }
    );
    return response.data;
  }

  async getDangerExits(portfolioId?: number): Promise<EnrichedStock[]> {
    const response = await this.client.get<EnrichedStock[]>(
      '/api/analysis/danger-exits',
      {
        params: portfolioId ? { portfolio_id: portfolioId } : {},
      }
    );
    return response.data;
  }

  // ==================== Gomes Analyzer Endpoints ====================

  /**
   * Analyze ticker using Gomes Investment Committee methodology
   */
  async gomesAnalyze(request: AnalyzeRequest): Promise<ConvictionScoreResponse> {
    const response = await this.client.post<ConvictionScoreResponse>(
      '/api/gomes/analyze',
      request
    );
    return response.data;
  }

  /**
   * Simple GET analyze for ticker (uses DB data)
   */
  async gomesAnalyzeTicker(ticker: string, forceRefresh: boolean = false): Promise<ConvictionScoreResponse> {
    const response = await this.client.get<ConvictionScoreResponse>(
      `/api/gomes/analyze/${ticker}`,
      {
        params: { force_refresh: forceRefresh }
      }
    );
    return response.data;
  }

  /**
   * Scan entire watchlist and rank by Gomes score
   */
  async gomesScanWatchlist(
    minScore: number = 5,
    limit: number = 20,
    forceRefresh: boolean = false
  ): Promise<WatchlistRankingResponse> {
    const response = await this.client.post<WatchlistRankingResponse>(
      '/api/gomes/scan-watchlist',
      null,
      {
        params: {
          min_score: minScore,
          limit: limit,
          force_refresh: forceRefresh
        }
      }
    );
    return response.data;
  }

  /**
   * Get top Gomes picks (filtered by rating)
   */
  async gomesTopPicks(
    minRating: 'STRONG_BUY' | 'BUY' | 'HOLD' = 'BUY',
    limit: number = 10
  ): Promise<WatchlistRankingResponse> {
    const response = await this.client.get<WatchlistRankingResponse>(
      '/api/gomes/top-picks',
      {
        params: {
          min_rating: minRating,
          limit: limit
        }
      }
    );
    return response.data;
  }

  /**
   * Batch analyze multiple tickers
   */
  async gomesBatchAnalyze(
    tickers: string[],
    forceRefresh: boolean = false
  ): Promise<BatchAnalyzeResponse> {
    const response = await this.client.post<BatchAnalyzeResponse>(
      '/api/gomes/analyze/batch',
      {
        tickers: tickers,
        force_refresh: forceRefresh
      }
    );
    return response.data;
  }

  // ==================== Transcript & Timeline ====================

  /**
   * Import a transcript with historical date
   */
  async importTranscript(
    request: TranscriptImportRequest
  ): Promise<TranscriptImportResponse> {
    const response = await this.client.post<TranscriptImportResponse>(
      '/api/gomes/transcripts/import',
      request
    );
    return response.data;
  }

  /**
   * Get timeline of mentions for a ticker
   */
  async getTickerTimeline(
    ticker: string,
    limit: number = 20
  ): Promise<TickerTimelineResponse> {
    const response = await this.client.get<TickerTimelineResponse>(
      `/api/gomes/ticker/${ticker}/timeline`,
      { params: { limit } }
    );
    return response.data;
  }

  /**
   * List all imported transcripts
   */
  async listTranscripts(
    source?: string,
    limit: number = 20
  ): Promise<TranscriptSummary[]> {
    const response = await this.client.get<TranscriptSummary[]>(
      '/api/gomes/transcripts',
      { params: { source, limit } }
    );
    return response.data;
  }

  /**
   * Process transcript with AI to extract sentiments and actions
   */
  async processTranscriptAI(
    transcriptId: number
  ): Promise<{ message: string; transcript_id: number; mentions_processed: number; price_lines_created: number; tickers: string[] }> {
    const response = await this.client.post(
      `/api/gomes/transcripts/${transcriptId}/process`
    );
    return response.data;
  }

  /**
   * Get price lines history for a ticker
   */
  async getPriceLinesHistory(ticker: string): Promise<PriceLinesHistoryResponse> {
    const response = await this.client.get<PriceLinesHistoryResponse>(
      `/api/gomes/ticker/${ticker}/price-lines-history`
    );
    return response.data;
  }

  // ==================== Gomes Intelligence ML Stocks ====================

  /**
   * Get all Gomes stocks with price lines for ML prediction page
   */
  async getGomesMLStocks(): Promise<ScoredStocksResponse> {
    const response = await this.client.get<ScoredStocksResponse>(
      '/api/intelligence/ml-stocks'
    );
    return response.data;
  }

  // ==================== Score History & Thesis Drift ====================

  /**
   * Get unacknowledged thesis drift alerts
   */
  async getDriftAlerts(unacknowledgedOnly: boolean = true): Promise<DriftAlertsResponse> {
    const response = await this.client.get<DriftAlertsResponse>(
      '/api/gomes/drift-alerts',
      { params: { unacknowledged_only: unacknowledgedOnly } }
    );
    return response.data;
  }

  /**
   * Acknowledge a drift alert
   */
  async acknowledgeDriftAlert(alertId: number): Promise<{ success: boolean }> {
    const response = await this.client.post(`/api/gomes/drift-alerts/${alertId}/acknowledge`);
    return response.data;
  }

  // ==================== Kelly Allocator ====================

  /**
   * Get allocation recommendations for a portfolio
   */
  async getAllocationPlan(
    portfolioId: number, 
    availableCzk: number, 
    availableEur: number
  ): Promise<AllocationPlanResponse> {
    const response = await this.client.post<AllocationPlanResponse>(
      `/api/portfolio/allocate/${portfolioId}`,
      null,
      { 
        params: { 
          available_czk: availableCzk, 
          available_eur: availableEur 
        } 
      }
    );
    return response.data;
  }

  /**
   * Get family audit - gaps between portfolios
   */
  async getFamilyAudit(): Promise<FamilyAuditResponse> {
    const response = await this.client.get<FamilyAuditResponse>(
      '/api/portfolio/family-audit'
    );
    return response.data;
  }

  // ==================== Deep Due Diligence ====================

  /**
   * Run Deep Due Diligence analysis on a transcript
   */
  async runDeepDD(
    transcript: string, 
    ticker?: string,
    saveToDb: boolean = true
  ): Promise<DeepDDResponse> {
    const params = new URLSearchParams();
    params.append('transcript', transcript);
    if (ticker) params.append('ticker', ticker);
    params.append('save_to_db', String(saveToDb));
    
    const response = await this.client.post<DeepDDResponse>(
      `/api/gomes/deep-dd?${params.toString()}`
    );
    return response.data;
  }

  /**
   * Update existing stock with new analysis (earnings, news, chat)
   */
  async updateStockAnalysis(
    ticker: string,
    transcript: string,
    sourceType: 'earnings' | 'news' | 'chat' | 'transcript' | 'manual' = 'manual'
  ): Promise<StockUpdateResponse> {
    const response = await this.client.post<StockUpdateResponse>(
      `/api/gomes/update-stock/${ticker}`,
      {
        transcript,
        source_type: sourceType,
      }
    );
    return response.data;
  }

  /**
   * Manually update stock price (when API is unavailable)
   */
  async updateStockPrice(
    ticker: string,
    currentPrice: number,
    greenLine?: number,
    redLine?: number
  ): Promise<PriceUpdateResponse> {
    const response = await this.client.put<PriceUpdateResponse>(
      `/api/stocks/${ticker}/price`,
      {
        current_price: currentPrice,
        green_line: greenLine,
        red_line: redLine,
      }
    );
    return response.data;
  }

  // ==================== Health Check ====================

  async healthCheck(): Promise<{ status: string; services: Record<string, string> }> {
    const response = await this.client.get('/health');
    return response.data;
  }

  // ==================== Currency Exchange Rates ====================

  /**
   * Get all exchange rates to CZK from Czech National Bank
   */
  async getExchangeRates(): Promise<{ rates: Record<string, number>; base: string }> {
    const response = await this.client.get('/api/currency/rates');
    return response.data;
  }

  /**
   * Get exchange rate for specific currency to CZK
   */
  async getExchangeRate(currency: string): Promise<{ currency: string; rate_to_czk: number; base: string }> {
    const response = await this.client.get(`/api/currency/rate/${currency}`);
    return response.data;
  }

  // ==================== Intelligence / Brain Logic ====================

  /**
   * Smart CSV upload with automatic reconciliation (Sync Logic)
   * Detects sales, moves to watchlist, preserves data
   */
  async uploadCSVSmart(
    portfolioId: number,
    broker: BrokerType,
    file: File
  ): Promise<SmartUploadResponse> {
    const formData = new FormData();
    formData.append('portfolio_id', portfolioId.toString());
    formData.append('broker', broker);
    formData.append('file', file);
    formData.append('detect_sales', 'true');

    const response = await this.client.post<SmartUploadResponse>(
      '/api/portfolio/upload-csv-smart',
      formData,
      {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      }
    );
    return response.data;
  }

  /**
   * Synthesize new knowledge into stock (Brain Logic)
   * Never overwrites - merges and refines data
   */
  async synthesizeKnowledge(request: {
    ticker: string;
    new_info: string;
    source?: string;
    force_score?: number;
  }): Promise<KnowledgeSynthesisResponse> {
    const response = await this.client.post<KnowledgeSynthesisResponse>(
      '/api/intelligence/synthesize',
      request
    );
    return response.data;
  }

  /**
   * Add a quick note to a stock's knowledge base
   */
  async addQuickNote(
    ticker: string,
    note: string,
    source: string = 'Quick Note'
  ): Promise<{ success: boolean; ticker: string; action: string; new_score: number | null; conflicts_detected: boolean }> {
    const response = await this.client.post(
      `/api/intelligence/quick-note/${ticker}`,
      null,
      { params: { note, source } }
    );
    return response.data;
  }

  /**
   * Get all notifications (thesis drift, score changes, reconciliation)
   */
  async getNotifications(
    includeAcknowledged: boolean = false,
    limit: number = 20
  ): Promise<NotificationItem[]> {
    const response = await this.client.get<NotificationItem[]>(
      '/api/intelligence/notifications',
      { params: { include_acknowledged: includeAcknowledged, limit } }
    );
    return response.data;
  }

  /**
   * Get thesis drift alerts
   */
  async getThesisDriftAlerts(params?: {
    ticker?: string;
    severity?: string;
    acknowledged?: boolean;
    limit?: number;
  }): Promise<ThesisDriftAlertItem[]> {
    const response = await this.client.get<ThesisDriftAlertItem[]>(
      '/api/intelligence/alerts',
      { params }
    );
    return response.data;
  }

  /**
   * Acknowledge a thesis drift alert
   */
  async acknowledgeAlert(alertId: number): Promise<{ success: boolean; alert_id: number }> {
    const response = await this.client.post(`/api/intelligence/alerts/${alertId}/acknowledge`);
    return response.data;
  }

  /**
   * Acknowledge all unread alerts
   */
  async acknowledgeAllAlerts(ticker?: string): Promise<{ success: boolean; acknowledged_count: number }> {
    const response = await this.client.post(
      '/api/intelligence/alerts/acknowledge-all',
      null,
      { params: ticker ? { ticker } : {} }
    );
    return response.data;
  }

  /**
   * Get score history for a ticker
   */
  async getScoreHistory(ticker: string, limit: number = 30): Promise<ScoreHistoryItem[]> {
    const response = await this.client.get<ScoreHistoryItem[]>(
      `/api/intelligence/score-history/${ticker}`,
      { params: { limit } }
    );
    return response.data;
  }

  /**
   * Daily Action list — "Co mám dnes udělat?" (max 3 actions or Nic. Drž.)
   */
  async getDailyActions(): Promise<DailyActionsResponse> {
    const response = await this.client.get<DailyActionsResponse>(
      '/api/trading/daily-actions'
    );
    return response.data;
  }
}

// ==================== New Types ====================

export interface SmartUploadResponse {
  success: boolean;
  portfolio: string;
  summary: string;
  positions_before: number;
  positions_after: number;
  changes: {
    added: number;
    updated: number;
    sold: number;
  };
  notifications: string[];
  price_refresh: {
    updated: number;
    failed: number;
  };
}

export interface KnowledgeSynthesisResponse {
  success: boolean;
  action: string;
  ticker: string;
  old_score: number | null;
  new_score: number | null;
  conflicts: string[];
  merged_fields: string[];
  alert_generated: boolean;
  explanation: string;
}

export interface NotificationItem {
  id: string;
  type: 'THESIS_DRIFT' | 'SCORE_CHANGE' | 'RECONCILIATION';
  severity: 'INFO' | 'WARNING' | 'CRITICAL';
  ticker: string | null;
  title: string;
  message: string;
  is_read: boolean;
  timestamp: string | null;
  data?: Record<string, unknown>;
}

export interface ThesisDriftAlertItem {
  id: number;
  ticker: string;
  alert_type: string;
  severity: string;
  old_score: number | null;
  new_score: number | null;
  message: string;
  is_acknowledged: boolean;
  created_at: string | null;
}

export interface ScoreHistoryItem {
  id: number;
  score: number;
  source: string | null;
  note: string | null;
  created_at: string | null;
}

// Daily Action list (Path 1: "Co mám dnes udělat?")
export interface DailyAction {
  id: string;
  ticker: string;
  source_key: 'GOMES' | 'BREAKOUT_INVESTORS' | 'COMBINED';
  action_type: 'BUY' | 'TRIM' | 'SELL' | 'SELL_WAIT_TIME' | 'LIQUIDATE_HEAVY';
  current_price: number;
  currency: string;
  target_price: number | null;
  quantity: number;
  estimated_czk_value: number;
  reason: string;
  urgency_score: number;
  review_required: boolean;
}

export interface DailyActionsResponse {
  market_alert: 'GREEN' | 'YELLOW' | 'ORANGE' | 'RED' | 'UNKNOWN';
  available_cash_czk: number;
  status: 'HOLD_HOLD_HOLD' | 'ACTION_REQUIRED';
  actions: DailyAction[];
  warnings: string[];
  generated_at: string;
}

// ==========================================================================
// SEC EDGAR
// ==========================================================================

/**
 * Why a ticker has the SEC data it has — or has none.
 *
 * Four distinct absences, none of which means the company reported nothing:
 * a foreign listing, an ISIN stored where a symbol belongs, a foreign private
 * issuer on the 20-F schedule, and EDGAR being unreachable.
 */
export type SecCoverageStatus =
  | 'COVERED'
  | 'NOT_AN_SEC_FILER'
  | 'FOREIGN_PRIVATE_ISSUER'
  | 'NOT_A_TICKER'
  | 'LOOKUP_FAILED';

export interface SecFiling {
  form: string;
  filed_date: string;
  period_date: string | null;
  url: string | null;
  /** Czech reading of the filing's narrative. null = not analysed yet. */
  analysis: string | null;
  analyzed: boolean;
}

export interface SecInsiderTrade {
  insider_name: string;
  role: string;
  transaction_date: string | null;
  code: string;
  code_label: string | null;
  /** Only BUY and SELL reach the UI; the rest are counted, not listed. */
  signal: 'BUY' | 'SELL' | 'NO_SIGNAL';
  shares: number | null;
  price_per_share: number | null;
}

export interface SecTickerData {
  ticker: string;
  status: SecCoverageStatus;
  company_name: string | null;
  note: string | null;
  last_checked_at: string | null;
  /** Exact figures from XBRL, each carrying the period it covers. */
  findings: string[];
  /** Line items the company does not tag. A gap, not a zero. */
  gaps: string[];
  filings: SecFiling[];
  insider_trades: SecInsiderTrade[];
  /** Grants, gifts, tax withholding — recorded, but no decision behind them. */
  insider_non_signal_count: number;
}

export interface SecSyncResult {
  ticker: string;
  status: SecCoverageStatus | 'ERROR';
  company_name?: string | null;
  filings_stored?: number;
  insider_stored?: number;
  findings?: string[];
  gaps?: string[];
  note?: string | null;
  error?: string | null;
}


// ============================================================================
// Away mode
// ============================================================================

export interface AwayStatus {
  is_away: boolean;
  /** On *and* inside its window. An `until` in the past reads as off. */
  active: boolean;
  since?: string | null;
  until?: string | null;
  reason?: string | null;
  days_away?: number | null;
  last_push_at?: string | null;
  last_push_subject?: string | null;
  /**
   * Why the last cycle did or did not send. Away mode is quiet on purpose;
   * this is what makes the quiet readable rather than indistinguishable from
   * the app having stopped working.
   */
  last_digest_reason?: string | null;
  max_data_age_hours: number;
  quiet_period_hours: number;
}

export interface AwayUpdate {
  is_away: boolean;
  until?: string | null;
  reason?: string | null;
}

export interface AwayPreview {
  away: boolean;
  would_send: boolean;
  decision: string;
  subject?: string | null;
  body?: string | null;
  /** What was held back, and why. Never silently dropped. */
  held: string[];
}

// ============================================================================
// Market gauge
// ============================================================================

export type ChannelPosition =
  | 'AT_UPPER_LINE'
  | 'EXPENSIVE'
  | 'ABOVE_TREND'
  | 'BELOW_GREY'
  | 'AT_LOWER_LINE';

export interface MarketGauge {
  index: string;
  as_of: string;
  close: number;
  z_score: number;
  percentile: number;
  position: ChannelPosition;
  position_cs: string;
  /** A suggestion. Nothing in the app acts on it by itself. */
  suggested_alert: string;
  current_alert?: string | null;
  agreement_cs: string;
  trend_value: number;
  upper_line: number;
  grey_line: number;
  lower_line: number;
  trend_pct_per_year: number;
  years: number;
  /** What this measure cannot see — it finds the 1999 top, misses 2007. */
  blind_spot_cs: string;
}

// ============================================================================
// Cash and hedge
// ============================================================================

export type HedgeAvailability =
  | 'LIKELY_AVAILABLE'
  | 'LIKELY_BLOCKED_EU_RETAIL'
  | 'UNKNOWN';

export interface CashHedgeLeg {
  ticker: string;
  name: string;
  role: 'CASH_PARK' | 'HEDGE';
  currency: string;
  exchange: string;
  availability: HedgeAvailability;
  note_cs: string;
  target_czk: number;
  price?: number | null;
  /** null when the price or the rate could not be read — never a guess. */
  shares?: number | null;
  blocker_cs?: string | null;
}

export interface CashHedgePlan {
  alert: string;
  portfolio_czk: number;
  stocks_pct: number;
  cash_pct: number;
  hedge_pct: number;
  canon_text: string;
  /** True when the percentages are the app's reading, not the canon's. */
  interpreted: boolean;
  legs: CashHedgeLeg[];
  fallback_cs?: string | null;
  /** Proof that UCITS inverse ETFs exist — explicitly not a substitute. */
  ucits_example?: CashHedgeLeg | null;
  gaps: string[];
}

// Export singleton instance
export const apiClient = new ApiClient();
export default apiClient;
