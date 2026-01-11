import React, { useState, useEffect } from 'react';
import { apiClient } from './api/client';
import { StockCard } from './components/StockCard';
import { AnalysisView } from './components/AnalysisView';
import type { Stock } from './types';

// --- ICONS (Inline SVG) ---
const Icons = {
  Activity: (props: any) => (
    <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...props}><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg>
  ),
  ArrowUpRight: (props: any) => (
    <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...props}><path d="M7 7h10v10"/><path d="M7 17 17 7"/></svg>
  ),
  ArrowDownRight: (props: any) => (
    <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...props}><path d="m7 7 10 10"/><path d="M17 7v10H7"/></svg>
  ),
  BookOpen: (props: any) => (
    <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...props}><path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/></svg>
  ),
  ChevronRight: (props: any) => (
    <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...props}><path d="m9 18 6-6-6-6"/></svg>
  ),
  Clock: (props: any) => (
    <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...props}><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
  ),
  LayoutGrid: (props: any) => (
    <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...props}><rect width="7" height="7" x="3" y="3" rx="1"/><rect width="7" height="7" x="14" y="3" rx="1"/><rect width="7" height="7" x="14" y="14" rx="1"/><rect width="7" height="7" x="3" y="14" rx="1"/></svg>
  ),
  List: (props: any) => (
    <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...props}><line x1="8" x2="21" y1="6" y2="6"/><line x1="8" x2="21" y1="12" y2="12"/><line x1="8" x2="21" y1="18" y2="18"/><line x1="3" x2="3.01" y1="6" y2="6"/><line x1="3" x2="3.01" y1="12" y2="12"/><line x1="3" x2="3.01" y1="18" y2="18"/></svg>
  ),
  PieChart: (props: any) => (
    <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...props}><path d="M21.21 15.89A10 10 0 1 1 8 2.83"/><path d="M22 12A10 10 0 0 0 12 2v10z"/></svg>
  ),
  Search: (props: any) => (
    <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...props}><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>
  ),
  ShieldAlert: (props: any) => (
    <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...props}><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10"/><line x1="12" x2="12" y1="8" y2="12"/><line x1="12" x2="12.01" y1="16" y2="16"/></svg>
  ),
  Star: (props: any) => (
    <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...props}><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>
  ),
  Target: (props: any) => (
    <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...props}><circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/></svg>
  ),
  TrendingUp: (props: any) => (
    <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...props}><polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/><polyline points="17 6 23 6 23 12"/></svg>
  ),
  Zap: (props: any) => (
    <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...props}><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
  ),
  X: (props: any) => (
    <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...props}><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>
  ),
};

// --- COMPONENTS ---

const Badge = ({ children, type }: { children: React.ReactNode, type: 'success' | 'warning' | 'danger' | 'neutral' | 'purple' }) => {
  const styles = {
    success: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
    warning: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
    danger: 'bg-rose-500/10 text-rose-400 border-rose-500/20',
    neutral: 'bg-slate-500/10 text-slate-400 border-slate-500/20',
    purple: 'bg-purple-500/10 text-purple-400 border-purple-500/20',
  };

  return (
    <span className={`px-2.5 py-0.5 rounded-full text-xs font-medium border ${styles[type]}`}>
      {children}
    </span>
  );
};

const MetricCard = ({ title, value, change, icon: Icon }: any) => (
  <div className="bg-slate-900/50 backdrop-blur-xl border border-white/5 p-5 rounded-2xl hover:border-white/10 transition-all duration-300 group">
    <div className="flex justify-between items-start mb-4">
      <div className="p-2 bg-indigo-500/10 rounded-lg group-hover:bg-indigo-500/20 transition-colors">
        <Icon className="w-5 h-5 text-indigo-400" />
      </div>
      {change !== undefined && (
        <span className={`flex items-center text-xs font-medium ${change >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
          {change >= 0 ? <Icons.ArrowUpRight className="w-3 h-3 mr-1" /> : <Icons.ArrowDownRight className="w-3 h-3 mr-1" />}
          {Math.abs(change)}%
        </span>
      )}
    </div>
    <h3 className="text-slate-400 text-sm font-medium mb-1">{title}</h3>
    <p className="text-2xl font-bold text-white tracking-tight">{value}</p>
  </div>
);

const DetailView = ({ stock, onBack }: { stock: Stock, onBack: () => void }) => {
  const getSentimentBadge = () => {
    const s = stock.sentiment?.toUpperCase();
    if (s === 'BULLISH') return <Badge type="success">BULLISH</Badge>;
    if (s === 'BEARISH') return <Badge type="danger">BEARISH</Badge>;
    return <Badge type="neutral">NEUTRAL</Badge>;
  };

  return (
    <div className="animate-in fade-in slide-in-from-bottom-4 duration-500">
        <button 
            onClick={onBack}
            className="mb-6 flex items-center text-slate-400 hover:text-white transition-colors text-sm"
        >
            <Icons.ChevronRight className="w-4 h-4 rotate-180 mr-1" />
            Zpět na přehled
        </button>

        <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-8">
            <div>
                <div className="flex items-center gap-3 mb-2">
                    <h1 className="text-4xl font-bold text-white tracking-tight">{stock.ticker}</h1>
                    {getSentimentBadge()}
                    {stock.gomes_score && (
                      <span className="text-2xl font-bold text-indigo-400 font-mono">{stock.gomes_score}/10</span>
                    )}
                </div>
                <h2 className="text-xl text-slate-400">{stock.company_name || 'Company Name'}</h2>
            </div>
            <div className="flex items-end flex-col">
                {stock.price_target && (
                  <div className="text-xl font-mono text-indigo-400">{stock.price_target}</div>
                )}
                {stock.time_horizon && (
                  <div className="text-sm text-slate-500">{stock.time_horizon}</div>
                )}
            </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="md:col-span-2 space-y-6">
                {stock.edge && (
                  <div className="bg-slate-800/40 backdrop-blur border border-white/5 rounded-2xl p-6">
                      <h3 className="flex items-center text-lg font-semibold text-white mb-4">
                          <Icons.Zap className="w-5 h-5 text-amber-400 mr-2" />
                          Edge (Information Arbitrage)
                      </h3>
                      <p className="text-slate-300 leading-relaxed text-sm md:text-base whitespace-pre-wrap">
                          {stock.edge}
                      </p>
                  </div>
                )}

                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    {stock.catalysts && (
                      <div className="bg-emerald-900/10 border border-emerald-500/10 rounded-2xl p-6">
                          <h3 className="flex items-center text-emerald-400 font-semibold mb-4">
                              <Icons.Target className="w-5 h-5 mr-2" /> Catalysts
                          </h3>
                          <p className="text-sm text-slate-300 whitespace-pre-wrap leading-relaxed">
                              {stock.catalysts}
                          </p>
                      </div>
                    )}
                    {stock.risks && (
                      <div className="bg-rose-900/10 border border-rose-500/10 rounded-2xl p-6">
                          <h3 className="flex items-center text-rose-400 font-semibold mb-4">
                              <Icons.ShieldAlert className="w-5 h-5 mr-2" /> Risks
                          </h3>
                          <p className="text-sm text-slate-300 whitespace-pre-wrap leading-relaxed">
                              {stock.risks}
                          </p>
                      </div>
                    )}
                </div>
            </div>

            <div className="space-y-6">
                <div className="bg-slate-800/40 backdrop-blur border border-white/5 rounded-2xl p-6">
                    <h3 className="flex items-center text-white font-semibold mb-4">
                        <Icons.Target className="w-5 h-5 text-indigo-400 mr-2" />
                        Metadata
                    </h3>
                    <div className="space-y-4">
                        {stock.source_type && (
                          <div className="flex justify-between items-center py-2 border-b border-white/5">
                              <span className="text-slate-400 text-sm">Source</span>
                              <Badge type="purple">{stock.source_type}</Badge>
                          </div>
                        )}
                        {stock.speaker && (
                          <div className="flex justify-between items-center py-2 border-b border-white/5">
                              <span className="text-slate-400 text-sm">Speaker</span>
                              <span className="text-white font-medium">{stock.speaker}</span>
                          </div>
                        )}
                        {stock.conviction_score !== null && stock.conviction_score !== undefined && (
                          <div className="flex justify-between items-center py-2 border-b border-white/5">
                              <span className="text-slate-400 text-sm">Conviction Score</span>
                              <span className="text-white font-mono font-bold">{stock.conviction_score}/10</span>
                          </div>
                        )}
                        <div className="flex justify-between items-center py-2">
                            <span className="text-slate-400 text-sm">Created</span>
                            <span className="text-white text-xs">{new Date(stock.created_at).toLocaleDateString('cs-CZ')}</span>
                        </div>
                    </div>
                </div>

                {stock.raw_notes && (
                  <div className="bg-slate-800/40 backdrop-blur border border-white/5 rounded-2xl p-6">
                      <h3 className="flex items-center text-white font-semibold mb-4">
                          <Icons.List className="w-5 h-5 text-blue-400 mr-2" />
                          Raw Notes
                      </h3>
                      <p className="text-xs text-slate-400 whitespace-pre-wrap leading-relaxed max-h-64 overflow-y-auto">
                          {stock.raw_notes}
                      </p>
                  </div>
                )}
            </div>
        </div>
    </div>
  );
};

// Modal pro novou analýzu
const NewAnalysisModal = ({ isOpen, onClose, onSubmit }: { isOpen: boolean, onClose: () => void, onSubmit: (url: string) => void }) => {
  const [inputType, setInputType] = useState<'url' | 'transcript'>('url');
  const [url, setUrl] = useState('');
  const [transcript, setTranscript] = useState('');
  const [isAnalyzing, setIsAnalyzing] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (inputType === 'url' && !url.trim()) return;
    if (inputType === 'transcript' && !transcript.trim()) return;
    
    setIsAnalyzing(true);
    try {
      if (inputType === 'url') {
        await onSubmit(url);
      } else {
        // Pro transcript použijeme stejnou metodu, backend to rozpozná
        await onSubmit(transcript);
      }
      setUrl('');
      setTranscript('');
      onClose();
    } catch (error) {
      console.error('Analysis failed:', error);
      alert('Analýza selhala. Zkuste to prosím znovu.');
    } finally {
      setIsAnalyzing(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div 
      className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-[9999]"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="bg-slate-900 border border-white/10 rounded-2xl p-6 w-full max-w-2xl mx-4 shadow-xl">
        <div className="flex justify-between items-center mb-6">
          <h2 className="text-xl font-bold text-white">Nová Analýza</h2>
          <button 
            onClick={onClose} 
            className="text-slate-400 hover:text-white transition-colors"
            type="button"
          >
            <Icons.X className="w-5 h-5" />
          </button>
        </div>

        {/* Tab switcher */}
        <div className="flex gap-2 mb-6 p-1 bg-slate-800/50 rounded-lg">
          <button
            type="button"
            onClick={() => setInputType('url')}
            className={`flex-1 px-4 py-2 rounded-md text-sm font-medium transition-colors ${
              inputType === 'url'
                ? 'bg-indigo-600 text-white'
                : 'text-slate-400 hover:text-white'
            }`}
          >
            URL (YouTube/Docs)
          </button>
          <button
            type="button"
            onClick={() => setInputType('transcript')}
            className={`flex-1 px-4 py-2 rounded-md text-sm font-medium transition-colors ${
              inputType === 'transcript'
                ? 'bg-indigo-600 text-white'
                : 'text-slate-400 hover:text-white'
            }`}
          >
            Transcript Text
          </button>
        </div>
        
        <form onSubmit={handleSubmit}>
          {inputType === 'url' ? (
            <div className="mb-6">
              <label className="block text-sm font-medium text-slate-300 mb-2">
                URL (YouTube nebo Google Docs)
              </label>
              <input
                type="url"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="https://youtube.com/watch?v=..."
                className="w-full bg-slate-800/50 border border-white/10 rounded-lg px-4 py-3 text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/50 focus:border-transparent"
                disabled={isAnalyzing}
                required
              />
            </div>
          ) : (
            <div className="mb-6">
              <label className="block text-sm font-medium text-slate-300 mb-2">
                Transcript nebo Text k analýze
              </label>
              <textarea
                value={transcript}
                onChange={(e) => setTranscript(e.target.value)}
                placeholder="Vložte zde transcript z YouTube nebo jakýkoliv text k analýze..."
                rows={12}
                className="w-full bg-slate-800/50 border border-white/10 rounded-lg px-4 py-3 text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/50 focus:border-transparent resize-vertical"
                disabled={isAnalyzing}
                required
              />
              <p className="text-xs text-slate-500 mt-2">
                Tip: V YouTube videu klikněte na "..." → "Zobrazit přepis" a zkopírujte text
              </p>
            </div>
          )}
          
          <div className="flex gap-3">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 px-4 py-2 bg-slate-800 hover:bg-slate-700 text-white rounded-lg transition-colors"
              disabled={isAnalyzing}
            >
              Zrušit
            </button>
            <button
              type="submit"
              className="flex-1 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              disabled={isAnalyzing}
            >
              {isAnalyzing ? 'Analyzuji...' : 'Analyzovat'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default function App() {
  const [stocks, setStocks] = useState<Stock[]>([]);
  const [selectedStock, setSelectedStock] = useState<Stock | null>(null);
  const [activeTab, setActiveTab] = useState('dashboard');
  const [isLoading, setIsLoading] = useState(true);
  const [isModalOpen, setIsModalOpen] = useState(false);

  // Načtení stocks z API
  useEffect(() => {
    loadStocks();
  }, []);

  const loadStocks = async () => {
    try {
      setIsLoading(true);
      const response = await apiClient.getStocks();
      setStocks(response.stocks || []);
    } catch (error) {
      console.error('Failed to load stocks:', error);
      setStocks([]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleAnalyzeUrl = async (url: string) => {
    await apiClient.analyzeUrl({ url });
    await loadStocks(); // Reload stocks after analysis
  };

  const highConvictionCount = stocks.filter(s => (s.gomes_score || 0) >= 7).length;
  const bullishCount = stocks.filter(s => s.sentiment?.toUpperCase() === 'BULLISH').length;

  return (
    <div className="min-h-screen bg-[#0f111a] text-slate-200 font-sans selection:bg-indigo-500/30">
        <div className="fixed top-0 left-0 w-full h-full overflow-hidden pointer-events-none z-0">
            <div className="absolute top-[-10%] left-[-10%] w-[40%] h-[40%] bg-indigo-500/10 rounded-full blur-[120px]" />
            <div className="absolute bottom-[-10%] right-[-10%] w-[40%] h-[40%] bg-purple-500/10 rounded-full blur-[120px]" />
        </div>

        <div className="relative z-10 flex h-screen overflow-hidden">
            <aside className="hidden lg:flex w-64 flex-col border-r border-white/5 bg-[#0f111a]/50 backdrop-blur-xl">
                <div className="p-6">
                    <div className="flex items-center gap-2 mb-8">
                        <div className="w-8 h-8 bg-gradient-to-tr from-indigo-500 to-purple-500 rounded-lg flex items-center justify-center">
                            <Icons.Activity className="w-5 h-5 text-white" />
                        </div>
                        <span className="text-xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-white to-slate-400">
                            Akcion
                        </span>
                    </div>

                    <nav className="space-y-1">
                        {[
                            { id: 'dashboard', icon: Icons.LayoutGrid, label: 'Dashboard' },
                            { id: 'portfolio', icon: Icons.PieChart, label: 'Portfolio' },
                            { id: 'watchlist', icon: Icons.List, label: 'Sledované' },
                            { id: 'analysis', icon: Icons.BookOpen, label: 'Analýzy' },
                        ].map((item) => (
                            <button
                                key={item.id}
                                onClick={() => { setActiveTab(item.id); setSelectedStock(null); }}
                                className={`w-full flex items-center px-3 py-2.5 rounded-xl text-sm font-medium transition-all ${
                                    activeTab === item.id 
                                    ? 'bg-indigo-500/10 text-indigo-400' 
                                    : 'text-slate-400 hover:text-white hover:bg-white/5'
                                }`}
                            >
                                <item.icon className="w-4 h-4 mr-3" />
                                {item.label}
                            </button>
                        ))}
                    </nav>
                </div>

                <div className="mt-auto p-6 border-t border-white/5">
                     <div className="bg-slate-800/50 rounded-xl p-4">
                        <p className="text-xs text-slate-400 mb-2">Portfolio Value</p>
                        <p className="text-lg font-bold text-white">$12,450.00</p>
                        <div className="w-full bg-slate-700 h-1.5 rounded-full mt-3 overflow-hidden">
                            <div className="bg-gradient-to-r from-indigo-500 to-purple-500 h-full w-[70%]" />
                        </div>
                     </div>
                </div>
            </aside>

            <main className="flex-1 overflow-y-auto">
                <header className="sticky top-0 z-20 flex items-center justify-between px-6 py-4 bg-[#0f111a]/80 backdrop-blur border-b border-white/5">
                    <div className="lg:hidden flex items-center gap-2">
                         <div className="w-8 h-8 bg-gradient-to-tr from-indigo-500 to-purple-500 rounded-lg flex items-center justify-center">
                            <Icons.Activity className="w-5 h-5 text-white" />
                        </div>
                    </div>
                    
                    <div className="flex-1 max-w-xl mx-auto lg:mx-0 lg:mr-auto pl-4 lg:pl-0">
                        <div className="relative group">
                            <Icons.Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500 group-focus-within:text-indigo-400 transition-colors" />
                            <input 
                                type="text" 
                                placeholder="Hledat ticker, společnost nebo analýzu..." 
                                className="w-full bg-slate-800/50 border border-white/5 rounded-xl py-2 pl-10 pr-4 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/50 focus:border-transparent transition-all"
                            />
                        </div>
                    </div>

                    <div className="flex items-center gap-4">
                         <button 
                           onClick={() => setIsModalOpen(true)}
                           className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-sm font-medium flex items-center gap-2 transition-colors">
                            <span className="text-lg">+</span>
                            Nová Analýza
                         </button>
                         <button className="p-2 text-slate-400 hover:text-white transition-colors relative">
                            <Icons.Activity className="w-5 h-5" />
                         </button>
                        <div className="h-8 w-8 rounded-full bg-slate-700 flex items-center justify-center border border-white/10">
                            <span className="text-xs font-bold text-white">JD</span>
                        </div>
                    </div>
                </header>

                <div className="p-6 max-w-7xl mx-auto">
                    {isLoading ? (
                      <div className="flex items-center justify-center h-96">
                        <div className="text-slate-400">Načítám data...</div>
                      </div>
                    ) : selectedStock ? (
                        <DetailView stock={selectedStock} onBack={() => setSelectedStock(null)} />
                    ) : (
                        <AnalysisView stocks={stocks} onStockClick={setSelectedStock} />
                    )}
                </div>
            </main>
        </div>

        <NewAnalysisModal 
          isOpen={isModalOpen} 
          onClose={() => setIsModalOpen(false)} 
          onSubmit={handleAnalyzeUrl}
        />
    </div>
  );
}
