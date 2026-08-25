/**
 * API Client for Akcion Backend
 * 
 * Centralized API communication layer for the FastAPI backend.
 */

import axios, { type AxiosInstance, type AxiosError } from 'axios';
import { handleApiError } from '../utils/errorHandling';
import type {
  BoardResponse,
  LadderResponse,
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
  OhlcvResponse,
  IntakeAnalysisResult,
  IntakeCommitResponse,
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

  /**
   * Pásmo pro každou firmu v portfoliu, včetně dvou limitních cen.
   *
   * Jeden řádek na FIRMU, ne na účet: pásmo je vlastnost byznysu, takže dva
   * lidé držící tutéž akcii mají číst totéž. Co s tím má kdo udělat, závisí na
   * jeho nákupní ceně a hotovosti, a to počítá denní seznam.
   */
  /**
   * Tabule „co s tímhle" — jedna karta na firmu, pokyn pro každý účet.
   *
   * Pásmo se počítá jednou (je to vlastnost firmy), pokyn jednou na účet
   * a nikdy proti součtu obou — ten součet je účet, který nikdo nedrží.
   */
  async getBoard(): Promise<BoardResponse> {
    const response = await this.client.get<BoardResponse>('/api/trading/board');
    return response.data;
  }

  /** Denní svíčky z `ohlcv_data`. 404, když je pro ticker ještě nemáme. */
  async getOhlcv(ticker: string, days = 180): Promise<OhlcvResponse> {
    const response = await this.client.get<OhlcvResponse>(
      `/api/trading/ohlcv/${encodeURIComponent(ticker)}`,
      { params: { days } }
    );
    return response.data;
  }

  async getLadder(): Promise<LadderResponse> {
    const response = await this.client.get<LadderResponse>('/api/gomes/ladder');
    return response.data;
  }

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

  // ==========================================================================
  // Breakout Investors — druhý zdroj: ukazuje se, neposlouchá se
  // ==========================================================================

  async getBreakoutWatchlist(days?: number): Promise<BreakoutWatchlist> {
    const response = await this.client.get<BreakoutWatchlist>(
      '/api/breakout/watchlist', { params: days ? { days } : undefined }
    );
    return response.data;
  }

  /** Přečte zdroj hned, mimo denní interval. Jen na stisk tlačítka. */
  async refreshBreakoutWatchlist(days?: number): Promise<BreakoutWatchlist> {
    const response = await this.client.post<BreakoutWatchlist>(
      '/api/breakout/refresh', null, { params: days ? { days } : undefined }
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
      /** Potvrzení, že měna sedí s výpisem od brokera. */
      currency_confirmed?: boolean;
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
   * Kalibrace — jak dopadla skóre, která aplikace vydala.
   *
   * `sufficient: false` znamená, že měření zatím není dost; pole s mediány
   * jsou pak prázdná záměrně, ne kvůli chybě.
   */
  async getScoreCalibration(horizon = 90): Promise<ScoreCalibration> {
    const response = await this.client.get<ScoreCalibration>(
      '/api/intelligence/score-calibration',
      { params: { horizon } }
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

  /**
   * Gemini 3.7 Flash - Blesková analýza videa nebo textu
   */
  async analyzeIntake(request: {
    text?: string;
    url?: string;
    source_type?: string;
  }): Promise<IntakeAnalysisResult> {
    const response = await this.client.post<IntakeAnalysisResult>(
      '/api/intake/analyze',
      request
    );
    return response.data;
  }

  /**
   * Uložit ověřený výsledek analýzy do databáze
   */
  async commitIntake(data: IntakeAnalysisResult): Promise<IntakeCommitResponse> {
    const response = await this.client.post<IntakeCommitResponse>(
      '/api/intake/commit',
      data
    );
    return response.data;
  }

  // ==========================================================================
  // Nálezy — vlastní nápady
  //
  // Jediná placená cesta je `explainFind`. Zbytek je čtení z databáze nebo
  // bezplatný sběr veřejných dat.
  // ==========================================================================

  async getFinds(includeClosed = false): Promise<Find[]> {
    const response = await this.client.get<Find[]>('/api/finds', {
      params: { include_closed: includeClosed },
    });
    return response.data;
  }

  /**
   * Založit nález. Sbírá data ze sítě (Yahoo, EDGAR, Finnhub), takže
   * u neznámého tickeru trvá pár sekund — proto delší timeout než výchozí.
   */
  async createFind(body: {
    symbol: string;
    note: string;
    found_at?: string;
  }): Promise<FindDetail> {
    const response = await this.client.post<FindDetail>('/api/finds', body, {
      timeout: 120_000,
    });
    return response.data;
  }

  async getFind(id: number): Promise<FindDetail> {
    const response = await this.client.get<FindDetail>(`/api/finds/${id}`);
    return response.data;
  }

  /** Dotáhnout data znovu a připsat další posudek. Zdarma. */
  async refreshFind(id: number): Promise<FindDetail> {
    const response = await this.client.post<FindDetail>(
      `/api/finds/${id}/refresh`, null, { timeout: 120_000 },
    );
    return response.data;
  }

  /**
   * Nechat vysvětlit poslední posudek. **Placené volání.**
   *
   * Výchozích 60 s nestačí: model přemýšlí a odpověď je dlouhá. Kdyby to
   * spadlo na timeout, majitel by viděl chybu u volání, které už zaplatil.
   */
  async explainFind(id: number, force = false): Promise<FindAssessment> {
    const response = await this.client.post<FindAssessment>(
      `/api/finds/${id}/explain`, null,
      { params: { force }, timeout: 300_000 },
    );
    return response.data;
  }

  // ==========================================================================
  // Analytikovy modely tržeb — model vs. realita
  //
  // Žádná placená cesta. `compareRevenueModel` sahá na SEC EDGAR (zdarma),
  // proto delší timeout a proto je to samostatná akce, ne něco na GETu.
  // ==========================================================================

  async getRevenueModels(ticker?: string): Promise<RevenueModelSummary[]> {
    const response = await this.client.get<RevenueModelSummary[]>('/api/revenue-models', {
      params: ticker ? { ticker } : undefined,
    });
    return response.data;
  }

  async getRevenueModel(id: number): Promise<RevenueModelDetail> {
    const response = await this.client.get<RevenueModelDetail>(`/api/revenue-models/${id}`);
    return response.data;
  }

  /** Dotáhne aktuální výkazy z SEC a postaví je vedle modelu. Zdarma, ale síť. */
  async compareRevenueModel(id: number): Promise<RevenueModelComparison> {
    const response = await this.client.post<RevenueModelComparison>(
      `/api/revenue-models/${id}/compare`, null, { timeout: 60_000 },
    );
    return response.data;
  }

  async updateFind(
    id: number,
    body: { note?: string; status?: string; close_reason?: string },
  ): Promise<Find> {
    const response = await this.client.patch<Find>(`/api/finds/${id}`, body);
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
  thesis_status: string | null;
  action_signal: string | null;
  /** Kdy skóre padlo. Dřív se tu čekalo `created_at`, které backend nikdy
      neposílal — pole bylo vždy undefined a nikdo si toho nevšiml, protože
      graf kreslí jen skóre. */
  recorded_at: string | null;
}

/** Jedno pásmo skóre v kalibračním přehledu. */
export interface CalibrationBand {
  label: string;
  score_min: number;
  score_max: number;
  n_evaluated: number;
  n_pending: number;
  n_unable: number;
  n_with_benchmark: number;
  median_excess_pct: number | null;
  median_return_pct: number | null;
  share_positive_excess: number | null;
  /** Má pásmo dost změřených výsledků na medián? Rozhoduje backend. */
  sufficient: boolean;
}

/** Jak si vedla skóre, která aplikace vydala. */
export interface ScoreCalibration {
  horizon_days: number;
  min_sample: number;
  sufficient: boolean;
  n_evaluated: number;
  n_pending: number;
  n_unable: number;
  /** Datum, kdy dozraje první čekající měření. */
  first_result_expected: string | null;
  bands: CalibrationBand[];
}

// Daily Action list (Path 1: "Co mám dnes udělat?")
export interface DailyAction {
  id: string;
  ticker: string;
  source_key: 'GOMES' | 'BREAKOUT_INVESTORS' | 'COMBINED';
  /** ROZPOR není pokyn — je to spor dvou motorů předaný k rozhodnutí. */
  action_type: 'BUY' | 'TRIM' | 'SELL' | 'SELL_WAIT_TIME' | 'LIQUIDATE_HEAVY' | 'ROZPOR';
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

/** Vztah jména na jejich watchlistu k našemu portfoliu. */
export type BreakoutRelation = 'OWNED' | 'WATCHED' | 'THEIRS';

/** Kam jejich cíl padne v Gomesově valuačním pásmu. */
export type BreakoutVsGomes = 'ABOVE_RED' | 'IN_BAND' | 'BELOW_GREEN';

export interface BreakoutEntry {
  symbol: string;
  company_name?: string | null;
  relation: BreakoutRelation;
  /** Kolik jejich členů jméno podepsalo. */
  endorsements: number;
  /** Jejich očekávaný růst v procentech. null = nezveřejněný. */
  upside_pct?: number | null;
  price_at_read?: number | null;
  /**
   * Jejich cílová cena, dopočítaná z kurzu a očekávaného růstu.
   * null vždy, když jeden ze vstupů chyběl — nikdy nula, nikdy stará hodnota.
   */
  implied_target?: number | null;
  gomes_green_line?: number | null;
  gomes_red_line?: number | null;
  vs_gomes?: BreakoutVsGomes | null;
  /** Kdy jméno přidali ONI. */
  added_at?: string | null;
  /** Kdy jsme ho poprvé viděli MY. */
  first_seen_at?: string | null;
}

export interface BreakoutChange {
  symbol: string;
  relation: BreakoutRelation;
  kind: 'ADDED' | 'REMOVED' | 'ENDORSEMENTS' | 'UPSIDE';
  detail_cs: string;
  detected_at: string;
}

export interface BreakoutWatchlist {
  last_attempt_at?: string | null;
  last_success_at?: string | null;
  last_error?: string | null;
  /** Přes 48 h bez úspěšného čtení — čísla níž jsou stará. */
  stale: boolean;
  /** Zdroj nebyl nikdy přečtený. Prázdno není „žádná jména". */
  never_read: boolean;
  entries_total: number;
  ours_total: number;
  entries: BreakoutEntry[];
  changes: BreakoutChange[];
}

// ============================================================================
// Nálezy — vlastní nápady a jejich posudky
// ============================================================================

export type FindLayer = 'VLASTNI' | 'GOMES' | 'BREAKOUT' | 'FUNDAMENTY' | 'METODIKA' | 'TRH';
export type FactDirection = 'PRO' | 'PROTI' | 'NEUTRAL';
export type PointSide = 'PRO' | 'PROTI';
export type PointWeight = 'ROZHODUJICI' | 'PODSTATNY' | 'DROBNY';

export interface FindFact {
  id: string;
  layer: FindLayer | string;
  text_cs: string;
  source: string;
  as_of?: string | null;
  /** Doslovný citát, když to někdo řekl. Jinak null. */
  quote?: string | null;
  /** Určuje backend podle pravidla, které fakt vyrobilo — nikdy model. */
  direction: FactDirection | string;
}

export interface FindGap {
  id: string;
  layer: FindLayer | string;
  text_cs: string;
  /** Co s tím jde udělat. null = ten údaj prostě neexistuje. */
  fixable_cs?: string | null;
}

export interface FindMethod {
  band: string;
  band_reason_cs: string;
  rr_score?: number | null;
  deserved?: number | null;
  buy_below?: number | null;
  sell_above?: number | null;
  green_line?: number | null;
  red_line?: number | null;
  line_currency?: string | null;
  /** Válce, které potvrdil člověk. null = pásmo se spočítat nedá. */
  cylinders_confirmed?: number | null;
  /** Návrh rubriky. Neautorizuje nic. */
  cylinders_proposed?: number | null;
  if_cylinders_cs?: string | null;
  phase_proposed?: string | null;
  /** Vždy true — fáze je návrh, ne potvrzený stav. */
  phase_is_proposal: boolean;
  phase_rough_patch?: boolean;
  market_alert?: string | null;
  market_alert_stale: boolean;
  gate_passed?: boolean | null;
  gate_code?: string | null;
  /** Věta brány česky. Syrový kód na obrazovku nepatří. */
  gate_reason_cs: string;
}

export interface FindDossier {
  ticker: string;
  symbol: string;
  company_name?: string | null;
  as_of: string;
  price?: number | null;
  price_currency?: string | null;
  price_is_stale: boolean;
  facts: FindFact[];
  gaps: FindGap[];
  method: FindMethod;
}

export interface FindPoint {
  side: PointSide | string;
  headline_cs: string;
  body_cs: string;
  fact_ids: string[];
  canon_ref: string;
  /** Znění pravidla doplňuje server — kánon se nepřevypravuje modelem. */
  canon_text_cs: string;
  check_yourself_cs: string;
  weight: PointWeight | string;
}

export interface FindExplanation {
  one_line_cs: string;
  points: FindPoint[];
  own_reason_cs: string;
  own_reason_verdict: string;
  lesson_cs: string;
}

export interface FindAssessment {
  id: number;
  assessed_at: string;
  price_at_assessment?: number | null;
  price_currency?: string | null;
  price_is_stale: boolean;
  band?: string | null;
  gate_code?: string | null;
  gate_reason_cs?: string | null;
  explanation?: FindExplanation | null;
  explanation_model?: string | null;
  explained_at?: string | null;
  /** Kolik bodů od AI citovalo neexistující fakt. Nenulové patří na obrazovku. */
  points_dropped: number;
  dossier?: FindDossier | null;
}

export interface Find {
  id: number;
  ticker: string;
  symbol: string;
  company_name?: string | null;
  note: string;
  found_at: string;
  status: string;
  closed_at?: string | null;
  close_reason?: string | null;
  assessment_count: number;
  last_assessed_at?: string | null;
  last_band?: string | null;
  last_price?: number | null;
  last_one_line_cs?: string | null;
}

export interface FindDetail {
  find: Find;
  dossier: FindDossier;
  assessments: FindAssessment[];
  collect_notes_cs: string[];
  collect_errors_cs: string[];
}

// ==============================================================================
// Analytikovy modely tržeb
// ==============================================================================

export interface RevenueModelPeriodTotal {
  period_label: string;
  total: number;
  currency: string;
  /** Kolik řádků nemá přečtenou barvu (LOCKED/ESTIMATE) z originálu. */
  unrated_lines: number;
  line_count: number;
}

export interface RevenueModelSummary {
  id: number;
  ticker: string;
  company_name?: string | null;
  source_name: string;
  model_name: string;
  document_date?: string | null;
  notes?: string | null;
  line_count: number;
  period_totals: RevenueModelPeriodTotal[];
}

export interface RevenueModelLine {
  id: number;
  category: string;
  item_name: string;
  period_label: string;
  quantity?: number | null;
  price_per_unit?: number | null;
  amount?: number | null;
  resolved_amount?: number | null;
  currency: string;
  /** LOCKED | ESTIMATE | null — appka barvu z PDF sama nepřečte. */
  confidence?: string | null;
  note?: string | null;
}

export interface RevenueModelDetail extends RevenueModelSummary {
  lines: RevenueModelLine[];
}

export interface RevenueModelPeriodComparison {
  period_label: string;
  model_total: number;
  currency: string;
  actual?: number | null;
  variance_pct?: number | null;
  /** Proč actual chybí, když chybí. */
  gap_cs?: string | null;
}

export interface RevenueModelComparison {
  model_id: number;
  ticker: string;
  comparisons: RevenueModelPeriodComparison[];
}

// Export singleton instance
export const apiClient = new ApiClient();
export default apiClient;
