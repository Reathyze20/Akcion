import React, { useState } from 'react';

// --- ICONS (Inline SVG pro odstranění závislosti na lucide-react) ---
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
};

// --- MOCK DATA (Simulace backendu) ---
const MOCK_STOCKS = [
  {
    id: 1,
    ticker: "ACME",
    name: "Acme BioTech Solutions",
    price: 4.25,
    change: 12.5,
    marketCap: "125M",
    phase: "Phase 2",
    conviction: "High",
    category: "Biotech",
    summary: "Společnost se blíží ke klíčovému schválení FDA. Mark Gomes zmiňuje, že risk/reward je zde 1:10. Insider nákupy za poslední měsíc vzrostly.",
    bullCase: ["Schválení patentu v Q3", "Nízký float", "Zájem velkých hráčů"],
    bearCase: ["Ředění akcií (Dilution risk)", "Konkurence od Big Pharma"],
    catalysts: [
      { event: "FDA Meeting", date: "12. 10. 2023", impact: "High" },
      { event: "Earnings Q3", date: "15. 11. 2023", impact: "Medium" }
    ]
  },
  {
    id: 2,
    ticker: "NEXU",
    name: "Nexus AI Infrastructure",
    price: 18.40,
    change: -2.3,
    marketCap: "450M",
    phase: "Phase 1",
    conviction: "Medium",
    category: "Technology",
    summary: "Silná technologie, ale trh čeká na potvrzení tržeb. Breakout Investors doporučují akumulaci pod $18.",
    bullCase: ["Unikátní AI čip", "Partnerství s Nvidia"],
    bearCase: ["Vysoký cash burn", "Zpoždění výroby"],
    catalysts: [
      { event: "Product Launch", date: "01. 12. 2023", impact: "High" }
    ]
  },
  {
    id: 3,
    ticker: "GDRX",
    name: "Gold Resourcer",
    price: 0.85,
    change: 5.1,
    marketCap: "45M",
    phase: "Phase 3",
    conviction: "Speculative",
    category: "Mining",
    summary: "Junior miner s obrovským potenciálem v Nevadě. Čeká se na výsledky vrtů.",
    bullCase: ["Vysoká cena zlata", "Nové ložisko"],
    bearCase: ["Geopolitické riziko", "Potřeba financování"],
    catalysts: []
  }
];

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
      {change && (
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

const StockCard = ({ stock, onClick }: { stock: any, onClick: () => void }) => (
  <div 
    onClick={onClick}
    className="bg-slate-800/40 backdrop-blur-md border border-white/5 p-5 rounded-2xl cursor-pointer hover:bg-slate-800/60 hover:border-indigo-500/30 hover:shadow-lg hover:shadow-indigo-500/10 transition-all duration-300 group relative overflow-hidden"
  >
    <div className="absolute top-0 right-0 p-3 opacity-0 group-hover:opacity-100 transition-opacity">
        <Icons.ArrowUpRight className="w-5 h-5 text-indigo-400" />
    </div>
    
    <div className="flex justify-between items-start mb-4">
      <div>
        <div className="flex items-center gap-2 mb-1">
            <h3 className="text-lg font-bold text-white tracking-wide">{stock.ticker}</h3>
            {stock.conviction === 'High' && <Icons.Star className="w-3 h-3 text-amber-400 fill-amber-400" />}
        </div>
        <p className="text-xs text-slate-400 truncate max-w-[150px]">{stock.name}</p>
      </div>
      <div className="text-right">
        <p className="text-lg font-bold text-white">${stock.price.toFixed(2)}</p>
        <span className={`text-xs font-medium flex items-center justify-end ${stock.change >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
          {stock.change > 0 ? '+' : ''}{stock.change}%
        </span>
      </div>
    </div>

    <div className="space-y-3">
        <div className="flex gap-2 flex-wrap">
            <Badge type="purple">{stock.phase}</Badge>
            <Badge type="neutral">{stock.category}</Badge>
        </div>
        
        <div className="pt-3 border-t border-white/5">
            <p className="text-xs text-slate-400 line-clamp-2 leading-relaxed">
                {stock.summary}
            </p>
        </div>
    </div>
  </div>
);

const DetailView = ({ stock, onBack }: { stock: any, onBack: () => void }) => (
    <div className="animate-in fade-in slide-in-from-bottom-4 duration-500">
        <button 
            onClick={onBack}
            className="mb-6 flex items-center text-slate-400 hover:text-white transition-colors text-sm"
        >
            <Icons.ChevronRight className="w-4 h-4 rotate-180 mr-1" />
            Zpět na přehled
        </button>

        {/* Header */}
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-8">
            <div>
                <div className="flex items-center gap-3 mb-2">
                    <h1 className="text-4xl font-bold text-white tracking-tight">{stock.ticker}</h1>
                    <Badge type={stock.conviction === 'High' ? 'warning' : 'neutral'}>
                        {stock.conviction} Conviction
                    </Badge>
                </div>
                <h2 className="text-xl text-slate-400">{stock.name}</h2>
            </div>
            <div className="flex items-end flex-col">
                <div className="text-3xl font-bold text-white">${stock.price}</div>
                <div className={`flex items-center ${stock.change >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                    {stock.change >= 0 ? <Icons.TrendingUp className="w-4 h-4 mr-1" /> : <Icons.Activity className="w-4 h-4 mr-1" />}
                    {stock.change > 0 ? '+' : ''}{stock.change}% (Today)
                </div>
            </div>
        </div>

        {/* Bento Grid Layout for Details */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            
            {/* Main Analysis */}
            <div className="md:col-span-2 space-y-6">
                <div className="bg-slate-800/40 backdrop-blur border border-white/5 rounded-2xl p-6">
                    <h3 className="flex items-center text-lg font-semibold text-white mb-4">
                        <Icons.Zap className="w-5 h-5 text-amber-400 mr-2" />
                        AI Shrnutí analýzy
                    </h3>
                    <p className="text-slate-300 leading-relaxed text-sm md:text-base">
                        {stock.summary}
                        <br /><br />
                        Tato společnost vykazuje klasické znaky "breakout" fáze. Objem obchodů se zvyšuje a technické indikátory ukazují na akumulaci ze strany institucí.
                    </p>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <div className="bg-emerald-900/10 border border-emerald-500/10 rounded-2xl p-6">
                        <h3 className="flex items-center text-emerald-400 font-semibold mb-4">
                            <Icons.ArrowUpRight className="w-5 h-5 mr-2" /> Bull Case
                        </h3>
                        <ul className="space-y-2">
                            {stock.bullCase.map((item: string, idx: number) => (
                                <li key={idx} className="flex items-start text-sm text-slate-300">
                                    <span className="w-1.5 h-1.5 bg-emerald-500 rounded-full mt-1.5 mr-2 shrink-0" />
                                    {item}
                                </li>
                            ))}
                        </ul>
                    </div>
                    <div className="bg-rose-900/10 border border-rose-500/10 rounded-2xl p-6">
                        <h3 className="flex items-center text-rose-400 font-semibold mb-4">
                            <Icons.ShieldAlert className="w-5 h-5 mr-2" /> Bear Case
                        </h3>
                         <ul className="space-y-2">
                            {stock.bearCase.map((item: string, idx: number) => (
                                <li key={idx} className="flex items-start text-sm text-slate-300">
                                    <span className="w-1.5 h-1.5 bg-rose-500 rounded-full mt-1.5 mr-2 shrink-0" />
                                    {item}
                                </li>
                            ))}
                        </ul>
                    </div>
                </div>
            </div>

            {/* Sidebar Details */}
            <div className="space-y-6">
                <div className="bg-slate-800/40 backdrop-blur border border-white/5 rounded-2xl p-6">
                    <h3 className="flex items-center text-white font-semibold mb-4">
                        <Icons.Target className="w-5 h-5 text-indigo-400 mr-2" />
                        Klíčová data
                    </h3>
                    <div className="space-y-4">
                        <div className="flex justify-between items-center py-2 border-b border-white/5">
                            <span className="text-slate-400 text-sm">Market Cap</span>
                            <span className="text-white font-medium">{stock.marketCap}</span>
                        </div>
                        <div className="flex justify-between items-center py-2 border-b border-white/5">
                            <span className="text-slate-400 text-sm">Fáze</span>
                            <Badge type="purple">{stock.phase}</Badge>
                        </div>
                        <div className="flex justify-between items-center py-2 border-b border-white/5">
                            <span className="text-slate-400 text-sm">Sektor</span>
                            <span className="text-white font-medium">{stock.category}</span>
                        </div>
                    </div>
                </div>

                <div className="bg-slate-800/40 backdrop-blur border border-white/5 rounded-2xl p-6">
                    <h3 className="flex items-center text-white font-semibold mb-4">
                        <Icons.Clock className="w-5 h-5 text-blue-400 mr-2" />
                        Katalyzátory
                    </h3>
                    {stock.catalysts.length > 0 ? (
                        <div className="space-y-4">
                            {stock.catalysts.map((cat: any, idx: number) => (
                                <div key={idx} className="relative pl-4 border-l-2 border-slate-700">
                                    <div className="text-xs text-slate-500 mb-0.5">{cat.date}</div>
                                    <div className="text-sm text-white font-medium">{cat.event}</div>
                                    <div className="mt-1">
                                        <Badge type={cat.impact === 'High' ? 'danger' : 'neutral'}>
                                            {cat.impact} Impact
                                        </Badge>
                                    </div>
                                </div>
                            ))}
                        </div>
                    ) : (
                         <p className="text-sm text-slate-500 italic">Žádné známé katalyzátory v blízké době.</p>
                    )}
                </div>
            </div>
        </div>
    </div>
);

export default function App() {
  const [selectedStock, setSelectedStock] = useState<any>(null);
  const [activeTab, setActiveTab] = useState('dashboard');

  return (
    <div className="min-h-screen bg-[#0f111a] text-slate-200 font-sans selection:bg-indigo-500/30">
        {/* Background Gradients */}
        <div className="fixed top-0 left-0 w-full h-full overflow-hidden pointer-events-none z-0">
            <div className="absolute top-[-10%] left-[-10%] w-[40%] h-[40%] bg-indigo-500/10 rounded-full blur-[120px]" />
            <div className="absolute bottom-[-10%] right-[-10%] w-[40%] h-[40%] bg-purple-500/10 rounded-full blur-[120px]" />
        </div>

        <div className="relative z-10 flex h-screen overflow-hidden">
            {/* Sidebar */}
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

            {/* Main Content */}
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
                         <button className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-sm font-medium flex items-center gap-2 transition-colors">
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
                    {selectedStock ? (
                        <DetailView stock={selectedStock} onBack={() => setSelectedStock(null)} />
                    ) : (
                        <div className="space-y-8 animate-in fade-in duration-500">
                            {/* Dashboard Header */}
                            <div>
                                <h1 className="text-2xl font-bold text-white mb-2">Přehled Trhu</h1>
                                <p className="text-slate-400 text-sm">Vítej zpět. Máš 2 nové analýzy od Marka Gomese.</p>
                            </div>

                            {/* Metrics Row */}
                            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                                <MetricCard title="Celkem Aktiv" value="14" icon={Icons.BookOpen} />
                                <MetricCard title="Vysoká Konvikce" value="3" icon={Icons.Target} />
                                <MetricCard title="Denní Změna" value="+2.4%" change={2.4} icon={Icons.TrendingUp} />
                                <MetricCard title="Nové Příležitosti" value="5" icon={Icons.Zap} />
                            </div>

                            {/* Main Content Grid */}
                            <div>
                                <div className="flex items-center justify-between mb-6">
                                    <h2 className="text-lg font-semibold text-white">Doporučené Akcie</h2>
                                    <button className="text-sm text-indigo-400 hover:text-indigo-300 font-medium">Zobrazit vše</button>
                                </div>
                                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                                    {MOCK_STOCKS.map(stock => (
                                        <StockCard key={stock.id} stock={stock} onClick={() => setSelectedStock(stock)} />
                                    ))}
                                </div>
                            </div>

                             {/* Recent Activity / Updates Section */}
                             <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                                <div className="lg:col-span-2 bg-slate-800/30 backdrop-blur border border-white/5 rounded-2xl p-6">
                                    <h3 className="text-white font-semibold mb-4">Poslední aktualizace v analýzách</h3>
                                    <div className="space-y-4">
                                        {[1, 2, 3].map((i) => (
                                            <div key={i} className="flex items-start gap-4 p-3 hover:bg-white/5 rounded-xl transition-colors cursor-pointer">
                                                <div className="w-10 h-10 rounded-full bg-indigo-500/10 flex items-center justify-center shrink-0">
                                                    <Icons.BookOpen className="w-5 h-5 text-indigo-400" />
                                                </div>
                                                <div>
                                                    <p className="text-sm text-white font-medium">Aktualizace analýzy pro <span className="text-indigo-400">ACME</span></p>
                                                    <p className="text-xs text-slate-400 mt-1">Přidána nová poznámka o vnitřních nákupech. Cílová cena zvýšena.</p>
                                                </div>
                                                <span className="ml-auto text-xs text-slate-500 whitespace-nowrap">před 2h</span>
                                            </div>
                                        ))}
                                    </div>
                                </div>

                                <div className="bg-gradient-to-br from-indigo-600 to-purple-700 rounded-2xl p-6 relative overflow-hidden">
                                     <div className="relative z-10">
                                        <h3 className="text-white font-bold text-lg mb-2">Breakout Alert</h3>
                                        <p className="text-indigo-100 text-sm mb-6">NEXU prorazilo klíčovou rezistenci $18. Objem vzrostl o 150%.</p>
                                        <button className="bg-white text-indigo-600 px-4 py-2 rounded-lg text-sm font-bold shadow-lg hover:bg-slate-50 transition-colors w-full">
                                            Zobrazit detail
                                        </button>
                                     </div>
                                     <Icons.Zap className="absolute -bottom-4 -right-4 w-32 h-32 text-white/10 rotate-12" />
                                </div>
                             </div>
                        </div>
                    )}
                </div>
            </main>
        </div>
    </div>
  );
}
