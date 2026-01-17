/**
 * Sidebar Component
 * 
 * Modern navigation and analysis input with premium fintech styling.
 */

import React, { useState } from 'react';
import { TrendingUp, BarChart3, FileText, Youtube, FileCode, Sparkles } from 'lucide-react';
import { toast } from 'sonner';
import { useAppState } from '../hooks/useAppState';
import { apiClient } from '../api/client';
import type { Stock } from '../types';

export const Sidebar: React.FC = () => {
  const { currentView, setCurrentView, setStocks, setIsLoading } = useAppState();
  
  const [inputType, setInputType] = useState<'text' | 'youtube' | 'google-docs'>('text');
  const [transcript, setTranscript] = useState('');
  const [url, setUrl] = useState('');
  const [speaker, setSpeaker] = useState('');

  const handleAnalyze = async () => {
    setIsLoading(true);

    try {
      let response;

      if (inputType === 'text') {
        response = await apiClient.analyzeText({
          transcript,
          speaker: speaker.trim() || 'Unknown',
          source_type: 'manual_input',
        });
      } else if (inputType === 'youtube') {
        response = await apiClient.analyzeYouTube({
          url,
          speaker: speaker.trim() || 'Unknown',
        });
      } else {
        response = await apiClient.analyzeGoogleDocs({
          url,
          speaker: speaker.trim() || 'Unknown',
        });
      }

      if (response.success) {
        // Convert StockAnalysisResult to Stock type
        const newStocks: Stock[] = response.stocks.map((s: any) => ({
          id: s.id || Date.now(),
          ticker: s.ticker,
          company_name: s.company_name || '',
          action_verdict: s.action_verdict,
          conviction_score: s.conviction_score || null,
          gomes_score: s.gomes_score || null,
          current_price: s.current_price || null,
          created_at: new Date().toISOString(),
          source_type: s.source_type || 'transcript',
          speaker: s.speaker || '',
          sentiment: s.sentiment || null,
          price_target: s.price_target || null,
          time_horizon: s.time_horizon || null,
          edge: s.edge || null,
          catalysts: s.catalysts || null,
          risks: s.risks || null,
          raw_notes: s.raw_notes || null,
          entry_zone: s.entry_zone || null,
          price_target_short: s.price_target_short || null,
          price_target_long: s.price_target_long || null,
          stop_loss_risk: s.stop_loss_risk || null,
          moat_rating: s.moat_rating || null,
          trade_rationale: s.trade_rationale || null,
          chart_setup: s.chart_setup || null,
          green_line: s.green_line || null,
          red_line: s.red_line || null,
          grey_line: s.grey_line || null,
          price_position_pct: s.price_position_pct || null,
          price_zone: s.price_zone || null,
        }));
        setStocks((prev: Stock[]) => [...newStocks, ...prev]);
        toast.success('Analysis Complete', {
          description: `Found ${response.stocks.length} stocks. ${response.message}`,
          duration: 4000,
        });
        
        // Clear inputs
        setTranscript('');
        setUrl('');
        
        // Switch to portfolio view
        setCurrentView('portfolio');
      }
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Analysis failed';
      toast.error('Analysis Failed', {
        description: errorMessage,
        duration: 5000,
      });
    } finally {
      setIsLoading(false);
    }
  };

  const isDisabled = (inputType === 'text' ? !transcript : !url);

  return (
    <aside className="w-80 bg-terminal-surface border-r border-terminal-border flex flex-col h-full shadow-xl">
      {/* Header */}
      <div className="p-6 border-b border-terminal-border">
        <div className="flex items-center gap-3 mb-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-accent-blue to-accent-purple flex items-center justify-center">
            <TrendingUp className="w-6 h-6 text-white" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-text-primary">AKCION</h1>
            <p className="text-xs text-text-muted">AI Investment Terminal</p>
          </div>
        </div>
      </div>

      {/* Navigation Tabs */}
      <div className="px-4 py-3 border-b border-terminal-border">
        <div className="flex gap-2">
          <button
            onClick={() => setCurrentView('analysis')}
            className={`flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-button font-medium text-sm transition-all ${
              currentView === 'analysis'
                ? 'bg-accent-blue text-white shadow-card'
                : 'bg-terminal-card text-text-secondary hover:bg-terminal-hover hover:text-text-primary'
            }`}
          >
            <Sparkles className="w-4 h-4" />
            Analysis
          </button>
          <button
            onClick={() => setCurrentView('portfolio')}
            className={`flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-button font-medium text-sm transition-all ${
              currentView === 'portfolio'
                ? 'bg-accent-blue text-white shadow-card'
                : 'bg-terminal-card text-text-secondary hover:bg-terminal-hover hover:text-text-primary'
            }`}
          >
            <BarChart3 className="w-4 h-4" />
            Portfolio
          </button>
        </div>
      </div>

      {/* Analysis Form */}
      <div className="flex-1 overflow-y-auto custom-scrollbar p-4 space-y-4">
        {/* Input Type Selector */}
        <div>
          <label className="block text-xs font-semibold text-text-secondary uppercase tracking-wider mb-2">
            Source Type
          </label>
          <div className="grid grid-cols-3 gap-2">
            <button
              onClick={() => setInputType('text')}
              className={`flex flex-col items-center gap-1.5 p-3 rounded-lg border transition-all ${
                inputType === 'text'
                  ? 'bg-terminal-hover border-accent-blue text-accent-blue'
                  : 'bg-terminal-card border-terminal-border text-text-muted hover:border-terminal-border-light hover:text-text-secondary'
              }`}
            >
              <FileText className="w-5 h-5" />
              <span className="text-xs font-medium">Text</span>
            </button>
            <button
              onClick={() => setInputType('youtube')}
              className={`flex flex-col items-center gap-1.5 p-3 rounded-lg border transition-all ${
                inputType === 'youtube'
                  ? 'bg-terminal-hover border-accent-blue text-accent-blue'
                  : 'bg-terminal-card border-terminal-border text-text-muted hover:border-terminal-border-light hover:text-text-secondary'
              }`}
            >
              <Youtube className="w-5 h-5" />
              <span className="text-xs font-medium">YouTube</span>
            </button>
            <button
              onClick={() => setInputType('google-docs')}
              className={`flex flex-col items-center gap-1.5 p-3 rounded-lg border transition-all ${
                inputType === 'google-docs'
                  ? 'bg-terminal-hover border-accent-blue text-accent-blue'
                  : 'bg-terminal-card border-terminal-border text-text-muted hover:border-terminal-border-light hover:text-text-secondary'
              }`}
            >
              <FileCode className="w-5 h-5" />
              <span className="text-xs font-medium">Docs</span>
            </button>
          </div>
        </div>

        {/* Speaker Input */}
        <div>
          <label className="block text-xs font-semibold text-text-secondary uppercase tracking-wider mb-2">
            Analyst / Speaker <span className="text-text-muted font-normal">(optional)</span>
          </label>
          <input
            type="text"
            value={speaker}
            onChange={(e) => setSpeaker(e.target.value)}
            placeholder="e.g., Mark Gomes (or leave empty for Unknown)"
            className="input"
          />
        </div>

        {/* Content Input */}
        {inputType === 'text' ? (
          <div>
            <label className="block text-xs font-semibold text-text-secondary uppercase tracking-wider mb-2">
              Transcript Content
            </label>
            <textarea
              value={transcript}
              onChange={(e) => setTranscript(e.target.value)}
              placeholder="Paste your investment transcript or analysis here..."
              className="textarea"
              rows={14}
            />
            <p className="text-xs text-text-muted mt-2">
              Tip: Include detailed stock discussions for best results
            </p>
          </div>
        ) : (
          <div>
            <label className="block text-xs font-semibold text-text-secondary uppercase tracking-wider mb-2">
              {inputType === 'youtube' ? 'YouTube URL' : 'Google Docs URL'}
            </label>
            <input
              type="url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder={
                inputType === 'youtube'
                  ? 'https://www.youtube.com/watch?v=...'
                  : 'https://docs.google.com/document/d/...'
              }
              className="input"
            />
            <p className="text-xs text-text-muted mt-2">
              {inputType === 'youtube' 
                ? 'Ensure video has captions/transcript available'
                : 'Make sure document is publicly accessible'
              }
            </p>
          </div>
        )}

        {/* Analyze Button */}
        <button
          onClick={handleAnalyze}
          disabled={isDisabled}
          className="btn btn-primary w-full py-3.5 text-base font-semibold flex items-center justify-center gap-2"
        >
          <Sparkles className="w-5 h-5" />
          Analyze with Gemini AI
        </button>

        {/* Info Card */}
        <div className="card p-4 space-y-3 border-l-2 border-l-accent-blue">
          <div className="flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-accent-blue" />
            <h3 className="text-sm font-semibold text-text-primary">Powered by Gemini 3 Pro</h3>
          </div>
          <ul className="space-y-2 text-xs text-text-secondary">
            <li className="flex items-start gap-2">
              <span className="text-semantic-bullish mt-0.5">•</span>
              <span>Fiduciary-grade analysis with Google Search</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="text-semantic-bullish mt-0.5">•</span>
              <span>Aggressive stock mention extraction</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="text-semantic-bullish mt-0.5">•</span>
              <span>The Gomes Rules scoring framework</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="text-semantic-bullish mt-0.5">•</span>
              <span>Edge, Catalysts & Risk identification</span>
            </li>
          </ul>
        </div>
      </div>
    </aside>
  );
};
