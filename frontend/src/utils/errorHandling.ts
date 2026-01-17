import axios, { AxiosError } from 'axios';

/**
 * Enhanced error handling utility for API calls
 * Provides Czech error messages and distinguishes between error types
 */

export interface ApiError {
  type: 'network' | 'rate-limit' | 'server' | 'client' | 'unknown';
  message: string;
  detail?: string;
  statusCode?: number;
  originalError?: any;
}

/**
 * Parse and categorize API errors with Czech messages
 */
export function handleApiError(error: any): ApiError {
  // Network errors (backend offline, connection refused, timeout)
  if (axios.isAxiosError(error)) {
    const axiosError = error as AxiosError;
    
    // No response - backend is down or network issue
    if (!axiosError.response) {
      if (axiosError.code === 'ERR_NETWORK' || axiosError.code === 'ECONNREFUSED') {
        return {
          type: 'network',
          message: '❌ Server není dostupný',
          detail: 'Backend server neběží nebo není dostupný. Zkuste znovu za chvíli.',
          originalError: error
        };
      }
      
      if (axiosError.code === 'ECONNABORTED' || axiosError.message.includes('timeout')) {
        return {
          type: 'network',
          message: '⏱️ Timeout',
          detail: 'Požadavek trval příliš dlouho. Zkuste to znovu.',
          originalError: error
        };
      }
      
      return {
        type: 'network',
        message: '🌐 Chyba sítě',
        detail: 'Nepodařilo se připojit k serveru. Zkontrolujte připojení.',
        originalError: error
      };
    }
    
    // Rate limiting (429)
    if (axiosError.response.status === 429) {
      const serverMessage = (axiosError.response.data as any)?.detail || '';
      return {
        type: 'rate-limit',
        message: '⚠️ Yahoo Finance API je přetížené',
        detail: serverMessage || 'Počkejte prosím 2-3 minuty a zkuste to znovu.',
        statusCode: 429,
        originalError: error
      };
    }
    
    // Server errors (5xx)
    if (axiosError.response.status >= 500) {
      return {
        type: 'server',
        message: '⚠️ Chyba serveru',
        detail: 'Interní chyba serveru. Zkuste to znovu za chvíli.',
        statusCode: axiosError.response.status,
        originalError: error
      };
    }
    
    // Client errors (4xx) - validation, not found, etc.
    if (axiosError.response.status >= 400) {
      const serverMessage = (axiosError.response.data as any)?.detail || 
                           (axiosError.response.data as any)?.message || 
                           'Neplatný požadavek';
      return {
        type: 'client',
        message: '⚠️ Chyba požadavku',
        detail: serverMessage,
        statusCode: axiosError.response.status,
        originalError: error
      };
    }
  }
  
  // Unknown error
  return {
    type: 'unknown',
    message: '❌ Neočekávaná chyba',
    detail: error?.message || 'Něco se pokazilo. Zkuste to znovu.',
    originalError: error
  };
}

/**
 * Display error message to user
 * Accepts an optional displayFn to use custom toast notifications instead of alerts
 */
export function showError(
  error: ApiError, 
  duration: number = 5000,
  displayFn?: (message: string, duration?: number) => void
): void {
  const fullMessage = error.detail 
    ? `${error.message}\n\n${error.detail}` 
    : error.message;
  
  // Use custom display function if provided (toast), otherwise fallback to alert
  if (displayFn) {
    displayFn(fullMessage, duration);
  } else {
    alert(fullMessage);
  }
  
  // Log to console for debugging
  if (error.originalError) {
    console.error('[API Error]', {
      type: error.type,
      message: error.message,
      detail: error.detail,
      statusCode: error.statusCode,
      original: error.originalError
    });
  }
}

/**
 * Retry logic with exponential backoff
 */
export async function retryRequest<T>(
  requestFn: () => Promise<T>,
  options: {
    maxRetries?: number;
    initialDelay?: number;
    maxDelay?: number;
    shouldRetry?: (error: ApiError) => boolean;
  } = {}
): Promise<T> {
  const {
    maxRetries = 3,
    initialDelay = 1000,
    maxDelay = 10000,
    shouldRetry = (err) => err.type === 'network' || err.type === 'server'
  } = options;
  
  let lastError: ApiError | null = null;
  
  for (let attempt = 0; attempt < maxRetries; attempt++) {
    try {
      return await requestFn();
    } catch (error) {
      lastError = handleApiError(error);
      
      // Don't retry if error type shouldn't be retried
      if (!shouldRetry(lastError)) {
        throw lastError;
      }
      
      // Don't retry on last attempt
      if (attempt === maxRetries - 1) {
        throw lastError;
      }
      
      // Calculate delay with exponential backoff
      const delay = Math.min(initialDelay * Math.pow(2, attempt), maxDelay);
      
      console.log(`[Retry] Attempt ${attempt + 1}/${maxRetries} failed. Retrying in ${delay}ms...`);
      await new Promise(resolve => setTimeout(resolve, delay));
    }
  }
  
  throw lastError;
}

/**
 * Check if backend is reachable
 */
export async function checkBackendConnection(baseURL: string): Promise<boolean> {
  try {
    const response = await fetch(`${baseURL}/api/portfolio/market-status`, {
      method: 'GET',
      signal: AbortSignal.timeout(5000) // 5 second timeout
    });
    return response.ok;
  } catch (error) {
    return false;
  }
}

/**
 * Format error for logging
 */
export function formatErrorForLog(error: ApiError): string {
  return `[${error.type.toUpperCase()}] ${error.message}${error.detail ? ` - ${error.detail}` : ''}${error.statusCode ? ` (${error.statusCode})` : ''}`;
}
