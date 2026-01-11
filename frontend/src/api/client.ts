/**
 * API Client for Akcion Backend
 * 
 * Centralized API communication layer for the FastAPI backend.
 */

import axios, { type AxiosInstance, type AxiosError } from 'axios';
import type {
  Stock,
  AnalysisRequest,
  YouTubeAnalysisRequest,
  GoogleDocsAnalysisRequest,
  AnalysisResponse,
  PortfolioResponse,
  PortfolioStats,
  ErrorResponse,
} from '../types';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

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

    // Response interceptor for error handling
    this.client.interceptors.response.use(
      (response) => response,
      (error: AxiosError<ErrorResponse>) => {
        const errorMessage = error.response?.data?.detail || error.message;
        console.error('API Error:', errorMessage);
        throw new Error(errorMessage);
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
        { text: request.url, speaker: 'Unknown' }
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

  // ==================== Health Check ====================

  async healthCheck(): Promise<{ status: string; services: Record<string, string> }> {
    const response = await this.client.get('/health');
    return response.data;
  }
}

// Export singleton instance
export const apiClient = new ApiClient();
export default apiClient;
