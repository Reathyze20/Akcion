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
  // Gomes Analyzer types
  GomesScoreResponse,
  GomesAnalyzeRequest,
  WatchlistRankingResponse,
  BatchAnalyzeResponse,
  // Timeline types
  TickerTimelineResponse,
  TranscriptImportRequest,
  TranscriptImportResponse,
  TranscriptSummary,
  // ML Stocks types
  GomesMLStocksResponse,
  // Price Lines History
  PriceLinesHistoryResponse,
  // Score History & Kelly
  ScoreHistoryResponse,
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
    min_gomes_score?: number;
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
  async gomesAnalyze(request: GomesAnalyzeRequest): Promise<GomesScoreResponse> {
    const response = await this.client.post<GomesScoreResponse>(
      '/api/gomes/analyze',
      request
    );
    return response.data;
  }

  /**
   * Simple GET analyze for ticker (uses DB data)
   */
  async gomesAnalyzeTicker(ticker: string, forceRefresh: boolean = false): Promise<GomesScoreResponse> {
    const response = await this.client.get<GomesScoreResponse>(
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
  async getGomesMLStocks(): Promise<GomesMLStocksResponse> {
    const response = await this.client.get<GomesMLStocksResponse>(
      '/api/intelligence/ml-stocks'
    );
    return response.data;
  }

  // ==================== Score History & Thesis Drift ====================

  /**
   * Get score history for a ticker
   */
  async getScoreHistory(ticker: string): Promise<ScoreHistoryResponse> {
    const response = await this.client.get<ScoreHistoryResponse>(
      `/api/gomes/score-history/${ticker}`
    );
    return response.data;
  }

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
    const params = new URLSearchParams();
    params.append('transcript', transcript);
    params.append('source_type', sourceType);
    
    const response = await this.client.post<StockUpdateResponse>(
      `/api/gomes/update-stock/${ticker}?${params.toString()}`
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
}

// Export singleton instance
export const apiClient = new ApiClient();
export default apiClient;
