
import InvestmentTerminal from './components/InvestmentTerminal';
import { ToastProvider } from './context/ToastContext';
import { ToastContainer } from './components/Toast';

/**
 * Akcion Investment Terminal
 * 
 * Single Page Application for family portfolio management
 * using proprietary fiduciary investment methodology.
 */
export default function App() {
  return (
    <ToastProvider>
      <div className="min-h-screen bg-slate-950">
        <InvestmentTerminal />
        <ToastContainer />
      </div>
    </ToastProvider>
  );
}
