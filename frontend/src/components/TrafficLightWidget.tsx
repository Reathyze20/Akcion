import { useState, useEffect } from 'react';
import { AlertCircle, CheckCircle, AlertTriangle, Shield } from 'lucide-react';
import { apiClient } from '../api/client';
import { useToast } from '../context/ToastContext';
import type { MarketStatus } from '../types';

interface TrafficLightWidgetProps {
  className?: string;
}

export default function TrafficLightWidget({ className = '' }: TrafficLightWidgetProps) {
  const [status, setStatus] = useState<MarketStatus>('GREEN');
  const [note, setNote] = useState<string>('');
  const [loading, setLoading] = useState(true);
  const [showMenu, setShowMenu] = useState(false);
  const { showError } = useToast();

  useEffect(() => {
    loadMarketStatus();
  }, []);

  const loadMarketStatus = async () => {
    try {
      const data = await apiClient.getMarketStatus();
      setStatus(data.status);
      setNote(data.note || '');
    } catch (error) {
      console.error('Failed to load market status:', error);
    } finally {
      setLoading(false);
    }
  };

  const updateStatus = async (newStatus: MarketStatus) => {
    try {
      await apiClient.updateMarketStatus(newStatus, note);
      setStatus(newStatus);
      setShowMenu(false);
    } catch (error) {
      console.error('Failed to update market status:', error);
      showError('Failed to update market status');
    }
  };

  const getStatusConfig = () => {
    switch (status) {
      case 'GREEN':
        return {
          icon: CheckCircle,
          label: 'OFFENSE',
          color: 'text-positive',
          bgColor: 'bg-positive/10',
          borderColor: 'border-positive/30',
          hoverBg: 'hover:bg-positive/20',
          dotColor: 'bg-positive',
          description: 'Aggressively deploying capital - Good time to buy'
        };
      case 'YELLOW':
        return {
          icon: AlertTriangle,
          label: 'SELECTIVE',
          color: 'text-warning',
          bgColor: 'bg-warning/10',
          borderColor: 'border-yellow-500/30',
          hoverBg: 'hover:bg-warning/20',
          dotColor: 'bg-warning',
          description: 'Be cautious - Only best setups'
        };
      case 'ORANGE':
        return {
          icon: Shield,
          label: 'DEFENSE',
          color: 'text-orange-500',
          bgColor: 'bg-warning/10',
          borderColor: 'border-orange-500/30',
          hoverBg: 'hover:bg-warning/20',
          dotColor: 'bg-warning',
          description: 'Reducing exposure - Protecting gains'
        };
      case 'RED':
        return {
          icon: AlertCircle,
          label: 'CASH IS KING',
          color: 'text-negative',
          bgColor: 'bg-negative/10',
          borderColor: 'border-negative/30',
          hoverBg: 'hover:bg-negative/20',
          dotColor: 'bg-negative',
          description: 'Maximum defensive - Preserve capital'
        };
    }
  };

  const config = getStatusConfig();
  const Icon = config.icon;

  if (loading) {
    return (
      <div className={`flex items-center gap-2 px-3 py-2 rounded-lg bg-bg-tertiary ${className}`}>
        <div className="w-2 h-2 rounded-full bg-gray-500 animate-pulse" />
        <span className="text-sm text-text-secondary">Loading...</span>
      </div>
    );
  }

  return (
    <div className={`relative ${className}`}>
      <button
        onClick={() => setShowMenu(!showMenu)}        title={note || 'Click to change market status'}        className={`flex items-center gap-2 px-4 py-2 rounded-lg border transition-all ${
          config.bgColor
        } ${config.borderColor} ${config.hoverBg}`}
      >
        <div className="relative">
          <div className={`w-2 h-2 rounded-full ${config.dotColor} animate-pulse`} />
          <div className={`absolute inset-0 w-2 h-2 rounded-full ${config.dotColor} animate-ping opacity-75`} />
        </div>
        <Icon size={18} className={config.color} />
        <span className={`text-sm font-semibold ${config.color}`}>
          {config.label}
        </span>
      </button>

      {showMenu && (
        <>
          {/* Backdrop */}
          <div
            className="fixed inset-0 z-40"
            onClick={() => setShowMenu(false)}
          />
          
          {/* Dropdown Menu */}
          <div className="absolute right-0 mt-2 w-72 bg-[#161B22] border border-gray-700 rounded-xl shadow-2xl z-50 overflow-hidden">
            <div className="p-4 border-b border-gray-700 bg-[#1C2128]">
              <h3 className="text-sm font-bold text-text-primary mb-1">Market Status</h3>
              <p className="text-xs text-text-secondary">{config.description}</p>
            </div>
            
            <div className="p-2 space-y-1 bg-[#161B22]">
              <button
                onClick={() => updateStatus('GREEN')}
                disabled={status === 'GREEN'}
                className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg transition-all ${
                  status === 'GREEN'
                    ? 'bg-positive/20 border border-positive/30'
                    : 'hover:bg-[#22272E]'
                }`}
              >
                <CheckCircle size={18} className="text-positive" />
                <div className="flex-1 text-left">
                  <div className="text-sm font-semibold text-positive">GREEN ALERT - OFFENSE</div>
                  <div className="text-xs text-text-secondary">Aggressively deploying capital</div>
                </div>
              </button>

              <button
                onClick={() => updateStatus('YELLOW')}
                disabled={status === 'YELLOW'}
                className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg transition-all ${
                  status === 'YELLOW'
                    ? 'bg-warning/20 border border-yellow-500/30'
                    : 'hover:bg-[#22272E]'
                }`}
              >
                <AlertTriangle size={18} className="text-warning" />
                <div className="flex-1 text-left">
                  <div className="text-sm font-semibold text-warning">YELLOW ALERT - SELECTIVE</div>
                  <div className="text-xs text-text-secondary">Only best setups</div>
                </div>
              </button>

              <button
                onClick={() => updateStatus('ORANGE')}
                disabled={status === 'ORANGE'}
                className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg transition-all ${
                  status === 'ORANGE'
                    ? 'bg-warning/20 border border-orange-500/30'
                    : 'hover:bg-[#22272E]'
                }`}
              >
                <Shield size={18} className="text-orange-500" />
                <div className="flex-1 text-left">
                  <div className="text-sm font-semibold text-orange-500">ORANGE ALERT - DEFENSE</div>
                  <div className="text-xs text-text-secondary">Reducing exposure</div>
                </div>
              </button>

              <button
                onClick={() => updateStatus('RED')}
                disabled={status === 'RED'}
                className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg transition-all ${
                  status === 'RED'
                    ? 'bg-negative/20 border border-negative/30'
                    : 'hover:bg-[#22272E]'
                }`}
              >
                <AlertCircle size={18} className="text-negative" />
                <div className="flex-1 text-left">
                  <div className="text-sm font-semibold text-negative">RED ALERT - CASH IS KING</div>
                  <div className="text-xs text-text-secondary">Preserve capital</div>
                </div>
              </button>
            </div>

            {note && (
              <div className="p-3 border-t border-gray-700 bg-[#1C2128]">
                <p className="text-xs text-text-secondary italic">&quot;{note}&quot;</p>
              </div>
            )}
            
            <div className="p-3 border-t border-gray-700 bg-[#0E1117]">
              <p className="text-xs text-text-muted">Default market status</p>
            </div>
          </div>
        </>
      )}
    </div>
  );
}


