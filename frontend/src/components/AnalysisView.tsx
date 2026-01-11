/**
 * AnalysisView Component
 * 
 * Welcome screen and instructions for the analysis feature.
 */

import React from 'react';

export const AnalysisView: React.FC = () => {
  return (
    <div className="flex-1 flex items-center justify-center p-6">
      <div className="max-w-2xl text-center space-y-6">
        <div className="text-6xl mb-4">📊</div>
        <h1 className="text-4xl font-bold text-text-primary mb-4">
          Welcome to <span className="text-accent-blue">AKCION</span>
        </h1>
        <p className="text-lg text-text-secondary mb-8">
          AI-powered investment analysis platform using fiduciary-grade analysis
          and The Gomes Rules framework.
        </p>

        <div className="card p-6 text-left space-y-4">
          <h2 className="text-xl font-semibold text-accent-blue">
            Getting Started
          </h2>
          <ol className="space-y-3 text-text-secondary">
            <li className="flex items-start gap-3">
              <span className="text-accent-blue font-bold">1.</span>
              <span>
                Choose your input type: raw text, YouTube URL, or Google Docs URL
              </span>
            </li>
            <li className="flex items-start gap-3">
              <span className="text-accent-blue font-bold">2.</span>
              <span>
                Enter the speaker/analyst name (e.g., "Mark Gomes")
              </span>
            </li>
            <li className="flex items-start gap-3">
              <span className="text-accent-blue font-bold">3.</span>
              <span>
                Paste your content or URL in the input field
              </span>
            </li>
            <li className="flex items-start gap-3">
              <span className="text-accent-blue font-bold">4.</span>
              <span>
                Click "Analyze" to extract stock mentions and insights
              </span>
            </li>
          </ol>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-8">
          <div className="card p-4">
            <div className="text-2xl mb-2">🤖</div>
            <h3 className="font-semibold text-text-primary mb-1">
              AI-Powered
            </h3>
            <p className="text-sm text-text-secondary">
              Gemini 3 Pro with Google Search integration
            </p>
          </div>
          <div className="card p-4">
            <div className="text-2xl mb-2">📈</div>
            <h3 className="font-semibold text-text-primary mb-1">
              Gomes Rules
            </h3>
            <p className="text-sm text-text-secondary">
              Information Arbitrage, Catalysts, Risks
            </p>
          </div>
          <div className="card p-4">
            <div className="text-2xl mb-2">🎯</div>
            <h3 className="font-semibold text-text-primary mb-1">
              Fiduciary-Grade
            </h3>
            <p className="text-sm text-text-secondary">
              Aggressive extraction with 1-10 scoring
            </p>
          </div>
        </div>

        <div className="mt-8 p-4 bg-accent-blue/10 border border-accent-blue/30 rounded-lg">
          <p className="text-sm text-text-secondary">
            <span className="font-semibold text-accent-blue">Note:</span> This
            application uses sophisticated AI analysis to support family financial
            security decisions. All analysis maintains the fiduciary standard from
            the original Streamlit application.
          </p>
        </div>
      </div>
    </div>
  );
};
