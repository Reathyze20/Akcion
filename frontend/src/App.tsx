
import GomesGuardianDashboard from './components/GomesGuardianDashboard';
import { ToastProvider } from './context/ToastContext';
import { ToastContainer } from './components/Toast';

/**
 * Akcion - Gomes Guardian
 * 
 * Single Page Application for family portfolio management
 * using Mark Gomes' investment methodology.
 */
export default function App() {
  return (
    <ToastProvider>
      <div className="min-h-screen bg-slate-950">
        <GomesGuardianDashboard />
        <ToastContainer />
      </div>
    </ToastProvider>
  );
}
