/**
 * Main App Component
 * 
 * Root component for the Akcion Investment Analysis Platform.
 * Premium dark modular UI with modern fintech terminal styling.
 */

import React from 'react';
import { Toaster } from 'sonner';
import { AppProvider } from './context/AppContext';
import { useAppState } from './hooks/useAppState';
import { Sidebar } from './components/Sidebar';
import { AnalysisView } from './components/AnalysisView';
import { PortfolioView } from './components/PortfolioView';

const AppContent: React.FC = () => {
  const { currentView, isLoading } = useAppState();

  return (
    <div className="flex h-screen w-screen bg-terminal-bg text-text-primary overflow-hidden">
      {/* Sidebar */}
      <Sidebar />

      {/* Main Content */}
      <main className="flex-1 flex flex-col relative">
        {/* Loading Overlay with Modern Spinner */}
        {isLoading && (
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50">
            <div className="bg-terminal-surface border border-accent-blue rounded-card p-8 shadow-glow-blue animate-fade-in">
              <div className="flex items-center gap-4">
                <div className="relative">
                  <div className="w-12 h-12 border-4 border-terminal-border rounded-full"></div>
                  <div className="absolute top-0 left-0 w-12 h-12 border-4 border-accent-blue border-t-transparent rounded-full animate-spin"></div>
                </div>
                <div>
                  <p className="text-lg font-semibold text-text-primary mb-1">
                    Analyzing with Gemini AI
                  </p>
                  <p className="text-sm text-text-secondary">
                    Extracting stock insights & scoring...
                  </p>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* View Content */}
        <div className="flex-1 overflow-hidden">
          {currentView === 'analysis' ? <AnalysisView /> : <PortfolioView />}
        </div>
      </main>
      
      {/* Toast Notifications */}
      <Toaster 
        position="top-right"
        theme="dark"
        toastOptions={{
          style: {
            background: '#1C2128',
            border: '1px solid #30363D',
            color: '#E6EDF3',
          },
          className: 'sonner-toast',
        }}
      />
    </div>
  );
};

function App() {
  return (
    <AppProvider>
      <AppContent />
    </AppProvider>
  );
}

export default App;
