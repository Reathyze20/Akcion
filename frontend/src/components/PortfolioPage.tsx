import React, { useState, useEffect, useCallback } from 'react';
import { Upload, RefreshCw, Trash2, Plus, TrendingUp, TrendingDown, Edit2 } from 'lucide-react';
import { apiClient } from '../api/client';
import { handleApiError, showError, type ApiError } from '../utils/errorHandling';
import { useToast } from '../context/ToastContext';
import ConfirmDialog from './ConfirmDialog';
import type { Portfolio, PortfolioSummary, BrokerType, Position } from '../types';

export default function PortfolioPage() {
  const { showSuccess, showError: showToastError, showWarning } = useToast();
  const [confirmDialog, setConfirmDialog] = React.useState<{
    isOpen: boolean;
    message: string;
    onConfirm: () => void;
    variant?: 'danger' | 'warning';
  }>({ isOpen: false, message: '', onConfirm: () => {} });

  // Wrapper to use toast for error handling
  const showErrorToast = (error: ApiError) => {
    showError(error, 5000, showToastError);
  };
  const [portfolios, setPortfolios] = useState<Portfolio[]>([]);
  const [owners, setOwners] = useState<string[]>([]);
  const [selectedOwner, setSelectedOwner] = useState<string | null>(null);
  const [selectedPortfolio, setSelectedPortfolio] = useState<number | null>(null);
  const [portfolioSummary, setPortfolioSummary] = useState<PortfolioSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  
  // Create portfolio modal state
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newPortfolioName, setNewPortfolioName] = useState('');
  const [newPortfolioOwner, setNewPortfolioOwner] = useState('');
  const [newPortfolioBroker, setNewPortfolioBroker] = useState<BrokerType>('T212');
  
  // CSV upload state
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploadBroker, setUploadBroker] = useState<BrokerType>('T212');
  
  // Edit position state
  const [showEditModal, setShowEditModal] = useState(false);
  const [editingPosition, setEditingPosition] = useState<Position | null>(null);
  const [editShares, setEditShares] = useState('');
  const [editAvgCost, setEditAvgCost] = useState('');

  // Cash balance edit state
  const [showCashModal, setShowCashModal] = useState(false);
  const [editCashBalance, setEditCashBalance] = useState('');

  const loadOwners = useCallback(async () => {
    try {
      const data = await apiClient.getOwners();
      setOwners(data);
      // Don't auto-select owner, show all portfolios by default
    } catch (error) {
      const apiError = error as ApiError;
      showErrorToast(apiError);
    }
  }, []);

  const loadPortfolios = useCallback(async () => {
    try {
      const data = await apiClient.getPortfolios(selectedOwner || undefined);
      console.log('📦 Loaded portfolios:', data);
      setPortfolios(data);
      // Auto-select first portfolio only if none is selected
      if (data.length > 0) {
        setSelectedPortfolio(prev => {
          const newValue = prev || data[0].id;
          console.log('📌 Selected portfolio:', newValue);
          return newValue;
        });
      }
    } catch (error) {
      const apiError = error as ApiError;
      showErrorToast(apiError);
    }
  }, [selectedOwner]);

  // Load owners and portfolios on mount
  useEffect(() => {
    loadOwners();
    loadPortfolios();
  }, [loadOwners, loadPortfolios]);

  // Load selected portfolio summary
  useEffect(() => {
    if (selectedPortfolio) {
      loadPortfolioSummary(selectedPortfolio);
    }
  }, [selectedPortfolio]);

  // Reload portfolios when owner filter changes
  useEffect(() => {
    loadPortfolios();
  }, [selectedOwner, loadPortfolios]);

  const loadPortfolioSummary = async (portfolioId: number) => {
    setLoading(true);
    try {
      const data = await apiClient.getPortfolioSummary(portfolioId);
      setPortfolioSummary(data);
    } catch (error) {
      const apiError = error as ApiError;
      showErrorToast(apiError);
    } finally {
      setLoading(false);
    }
  };

  const handleCreatePortfolio = async () => {
    if (!newPortfolioName.trim() || !newPortfolioOwner.trim()) return;
    
    setLoading(true);
    try {
      const newPortfolio = await apiClient.createPortfolio(newPortfolioName, newPortfolioOwner, newPortfolioBroker);
      console.log('✅ Portfolio created:', newPortfolio);
      console.log('🎯 Setting selectedPortfolio to:', newPortfolio.id);
      
      // Close modal first
      setShowCreateModal(false);
      setNewPortfolioName('');
      setNewPortfolioOwner('');
      
      // Set owner filter to match new portfolio's owner
      setSelectedOwner(newPortfolioOwner);
      
      // Immediately select the new portfolio
      setSelectedPortfolio(newPortfolio.id);
      console.log('📌 selectedPortfolio state updated to:', newPortfolio.id);
      
      // Refresh lists in background
      await loadOwners();
      // Load portfolios for the new owner
      const portfolios = await apiClient.getPortfolios(newPortfolioOwner);
      setPortfolios(portfolios);
      console.log('📦 Portfolios refreshed for', newPortfolioOwner, portfolios);
      
      // Confirm portfolio is now selected
      setTimeout(() => {
        console.log('🔍 Checking selectedPortfolio after 100ms...');
      }, 100);
      
    } catch (error) {
      const apiError = error as ApiError;
      showErrorToast(apiError);
    } finally {
      setLoading(false);
    }
  };

  const handleFileSelect = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) {
      setSelectedFile(file);
    }
  };

  const handleUploadCSV = async () => {
    console.log('🔼 Upload CSV clicked', { selectedFile, selectedPortfolio, uploadBroker });
    
    if (!selectedPortfolio) {
      showWarning('Please create a portfolio first by clicking "New Portfolio"');
      setShowUploadModal(false);
      return;
    }
    
    if (!selectedFile) {
      showWarning('Please select a CSV file');
      return;
    }
    
    setLoading(true);
    try {
      const result = await apiClient.uploadCSV(
        selectedPortfolio,
        uploadBroker,
        selectedFile
      );
      
      console.log('✅ Upload success:', result);
      
      if (result.success) {
        showSuccess(
          `Upload successful! Created: ${result.positions_created} positions, Updated: ${result.positions_updated} positions. ` +
          `NOTE: Degiro CSV contains current prices, not purchase prices. Please use the Edit button to update your actual purchase costs.`,
          5000
        );
        setShowUploadModal(false);
        setSelectedFile(null);
        await loadPortfolioSummary(selectedPortfolio);
      } else {
        showToastError(`Upload failed: ${result.message}`);
      }
    } catch (error) {
      const apiError = error as ApiError;
      showErrorToast(apiError);
    } finally {
      setLoading(false);
    }
  };

  const handleRefreshPrices = async () => {
    if (!selectedPortfolio) return;
    
    setRefreshing(true);
    try {
      const result = await apiClient.refreshPrices(selectedPortfolio);
      showSuccess(`Ceny aktualizovány: ${result.updated_count} úspěšných, ${result.failed_count} neúspěšných`);
      await loadPortfolioSummary(selectedPortfolio);
    } catch (error: any) {
      // Use centralized error handling
      const apiError = error as ApiError;
      
      // Custom handling for rate limits (more detailed message)
      if (apiError.type === 'rate-limit') {
        showErrorToast({
          ...apiError,
          message: '⚠️ Yahoo Finance API je přetížené',
          detail: 'Počkejte prosím 2-3 minuty a zkuste to znovu.\n\nToto je limit od Yahoo Finance, ne chyba aplikace.'
        });
      } else {
        showErrorToast(apiError);
      }
    } finally {
      setRefreshing(false);
    }
  };

  const handleDeletePosition = async (positionId: number) => {
    setConfirmDialog({
      isOpen: true,
      message: 'Are you sure you want to delete this position?',
      variant: 'danger',
      onConfirm: async () => {
        setConfirmDialog({ ...confirmDialog, isOpen: false });
        try {
          await apiClient.deletePosition(positionId);
          showSuccess('Position deleted successfully');
          if (selectedPortfolio) {
            await loadPortfolioSummary(selectedPortfolio);
          }
        } catch (error) {
          const apiError = error as ApiError;
          showErrorToast(apiError);
        }
      }
    });
  };

  const handleDeleteAllPositions = async () => {
    if (!selectedPortfolio) return;
    
    setConfirmDialog({
      isOpen: true,
      message: '⚠️ Are you sure you want to delete ALL positions in this portfolio? This cannot be undone!',
      variant: 'danger',
      onConfirm: async () => {
        setConfirmDialog({ ...confirmDialog, isOpen: false });
        setLoading(true);
        try {
          const result = await apiClient.deleteAllPositions(selectedPortfolio);
          showSuccess(result.message);
          await loadPortfolioSummary(selectedPortfolio);
        } catch (error) {
          const apiError = error as ApiError;
          showErrorToast(apiError);
        } finally {
          setLoading(false);
        }
      }
    });
  };

  const handleEditPosition = (position: Position) => {
    setEditingPosition(position);
    setEditShares(position.shares_count.toString());
    setEditAvgCost(position.avg_cost.toString());
    setShowEditModal(true);
  };

  const handleUpdatePosition = async () => {
    if (!editingPosition) return;
    
    const shares = parseFloat(editShares);
    const avgCost = parseFloat(editAvgCost);
    
    if (isNaN(shares) || isNaN(avgCost) || shares <= 0 || avgCost <= 0) {
      showToastError('Please enter valid positive numbers');
      return;
    }
    
    setLoading(true);
    try {
      await apiClient.updatePosition(editingPosition.id, {
        shares_count: shares,
        avg_cost: avgCost
      });
      
      // Close modal first
      setShowEditModal(false);
      setEditingPosition(null);
      
      // Then reload data
      if (selectedPortfolio) {
        await loadPortfolioSummary(selectedPortfolio);
      }
      
      // Show success after data is loaded
      showSuccess('Position updated successfully');
    } catch (error) {
      const apiError = error as ApiError;
      showErrorToast(apiError);
    } finally {
      setLoading(false);
    }
  };

  const handleEditCashBalance = async () => {
    if (!selectedPortfolio || !portfolioSummary) return;
    
    const cashBalance = parseFloat(editCashBalance);
    
    if (isNaN(cashBalance) || cashBalance < 0) {
      showToastError('Please enter a valid non-negative number');
      return;
    }
    
    setLoading(true);
    try {
      await apiClient.updateCashBalance(selectedPortfolio, cashBalance);
      
      // Close modal first
      setShowCashModal(false);
      setEditCashBalance('');
      
      // Then reload data
      await loadPortfolioSummary(selectedPortfolio);
      
      // Show success after data is loaded
      showSuccess('Cash balance updated successfully');
    } catch (error) {
      const apiError = error as ApiError;
      showErrorToast(apiError);
    } finally {
      setLoading(false);
    }
  };

  const formatCurrency = (value: number, currency: string = 'CZK') => {
    return new Intl.NumberFormat('cs-CZ', {
      style: 'currency',
      currency: currency,
    }).format(value);
  };

  const formatCurrencySummary = (value: number) => {
    // Summary values are in CZK
    return formatCurrency(value, 'CZK');
  };

  const formatPercent = (value: number) => {
    return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`;
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-3xl font-bold text-text-primary">Správa portfolia</h1>
        <div className="flex items-center gap-4">
          {/* Owner Filter */}
          {owners.length > 0 && (
            <div className="flex items-center gap-2">
              <label className="text-sm font-semibold text-text-secondary">Owner:</label>
              <select
                value={selectedOwner || ''}
                onChange={(e) => setSelectedOwner(e.target.value || null)}
                className="px-4 py-2 bg-surface-raised border border-white/10 rounded-lg text-text-primary focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
              >
                <option value="">All</option>
                {owners.map((owner) => (
                  <option key={owner} value={owner}>
                    {owner}
                  </option>
                ))}
              </select>
            </div>
          )}
          
          <button
            onClick={() => setShowCreateModal(true)}
            className="btn btn-primary flex items-center gap-2"
          >
            <Plus size={20} />
            Nové portfolio
          </button>
          {selectedPortfolio && (
            <>
              <button
                onClick={() => setShowUploadModal(true)}
                className="btn btn-secondary flex items-center gap-2"
              >
                <Upload size={20} />
                Nahrát CSV
              </button>
              <button
                onClick={handleRefreshPrices}
                disabled={refreshing}
                className="btn btn-secondary flex items-center gap-2"
              >
                <RefreshCw size={20} className={refreshing ? 'animate-spin' : ''} />
                Aktualizovat ceny
              </button>
              <button
                onClick={handleDeleteAllPositions}
                disabled={loading || !portfolioSummary?.positions?.length}
                className="btn bg-red-600 hover:bg-red-700 text-text-primary flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <Trash2 size={20} />
                Smazat vše
              </button>
            </>
          )}
        </div>
      </div>

      {/* Portfolio Selector */}
      <div className="flex gap-3 flex-wrap">
        {portfolios.map((portfolio) => (
          <button
            key={portfolio.id}
            onClick={() => setSelectedPortfolio(portfolio.id)}
            className={`px-6 py-3 rounded-lg font-semibold transition-all ${
              selectedPortfolio === portfolio.id
                ? 'bg-indigo-600 text-text-primary ring-2 ring-indigo-400'
                : 'bg-surface-raised text-text-secondary hover:bg-surface-hover'
            }`}
          >
            <div className="flex flex-col items-start">
              <span className="text-xs opacity-75">{portfolio.owner}</span>
              <span>{portfolio.name}</span>
            </div>
          </button>
        ))}
      </div>

      {/* Portfolio Summary Cards */}
      {portfolioSummary && (
        <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
          <div className="card p-6">
            <div className="text-sm text-text-secondary mb-1">Tržní hodnota (CZK)</div>
            <div className="text-2xl font-bold text-text-primary">
              {formatCurrencySummary(portfolioSummary.total_market_value)}
            </div>
          </div>
          <div className="card p-6 cursor-pointer hover:bg-gray-50" onClick={() => {
              setEditCashBalance((portfolioSummary.cash_balance || 0).toString());
              setShowCashModal(true);
            }}>
            <div className="text-sm text-text-secondary mb-1 flex items-center gap-1">
              Hotovost (CZK) <Edit2 size={12} />
            </div>
            <div className="text-2xl font-bold text-text-primary">
              {formatCurrencySummary(portfolioSummary.cash_balance || 0)}
            </div>
          </div>
          <div className="card p-6">
            <div className="text-sm text-text-secondary mb-1">Nákladová cena (CZK)</div>
            <div className="text-2xl font-bold text-text-primary">
              {formatCurrencySummary(portfolioSummary.total_cost_basis)}
            </div>
          </div>
          <div className="card p-6">
            <div className="text-sm text-text-secondary mb-1">P/L (CZK)</div>
            <div className={`text-2xl font-bold flex items-center gap-2 ${
              portfolioSummary.total_unrealized_pl >= 0 ? 'text-positive' : 'text-negative'
            }`}>
              {portfolioSummary.total_unrealized_pl >= 0 ? (
                <TrendingUp size={24} />
              ) : (
                <TrendingDown size={24} />
              )}
              {formatCurrencySummary(portfolioSummary.total_unrealized_pl)}
            </div>
          </div>
          <div className="card p-6">
            <div className="text-sm text-text-secondary mb-1">P/L %</div>
            <div className={`text-2xl font-bold ${
              portfolioSummary.total_unrealized_pl_percent >= 0 ? 'text-positive' : 'text-negative'
            }`}>
              {formatPercent(portfolioSummary.total_unrealized_pl_percent)}
            </div>
          </div>
        </div>
      )}

      {/* Holdings Table */}
      {loading ? (
        <div className="card p-8 text-center text-text-secondary">Načítání...</div>
      ) : portfolioSummary && portfolioSummary.positions.length > 0 ? (
        <div className="card overflow-hidden">
          <table className="w-full">
            <thead className="bg-bg-tertiary border-b border-gray-700">
              <tr>
                <th className="px-6 py-4 text-left text-sm font-semibold text-text-primary">Společnost</th>
                <th className="px-6 py-4 text-right text-sm font-semibold text-text-primary">Akcie</th>
                <th className="px-6 py-4 text-right text-sm font-semibold text-text-primary">Prům. cena</th>
                <th className="px-6 py-4 text-right text-sm font-semibold text-text-primary">Aktuální cena</th>
                <th className="px-6 py-4 text-right text-sm font-semibold text-text-primary">Tržní hodnota</th>
                <th className="px-6 py-4 text-right text-sm font-semibold text-text-primary">P/L $</th>
                <th className="px-6 py-4 text-right text-sm font-semibold text-text-primary">P/L %</th>
                <th className="px-6 py-4 text-right text-sm font-semibold text-text-primary">Akce</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-700">
              {portfolioSummary.positions.map((position) => {
                const currency = (position as any).currency || 'USD';
                const companyName = (position as any).company_name;
                return (
                  <tr key={position.id} className="hover:bg-bg-tertiary transition-colors">
                    <td className="px-6 py-4">
                      <div className="flex flex-col">
                        <div className="flex items-center gap-2 mb-1">
                          <span className="font-bold text-accent">{position.ticker}</span>
                          <span className="text-xs text-text-muted bg-surface-raised px-2 py-0.5 rounded">{currency}</span>
                        </div>
                        {companyName && (
                          <span className="text-sm text-text-secondary truncate max-w-xs">{companyName}</span>
                        )}
                      </div>
                    </td>
                    <td className="px-6 py-4 text-right text-text-primary">{position.shares_count}</td>
                    <td className="px-6 py-4 text-right text-text-secondary">
                      {formatCurrency(position.avg_cost, currency)}
                    </td>
                    <td className="px-6 py-4 text-right text-text-primary">
                      {position.current_price ? formatCurrency(position.current_price, currency) : '-'}
                    </td>
                    <td className="px-6 py-4 text-right text-text-primary font-semibold">
                      {formatCurrency(position.market_value, currency)}
                    </td>
                    <td className={`px-6 py-4 text-right font-semibold ${
                      position.unrealized_pl >= 0 ? 'text-positive' : 'text-negative'
                    }`}>
                      {formatCurrency(position.unrealized_pl, currency)}
                    </td>
                    <td className={`px-6 py-4 text-right font-semibold ${
                      position.unrealized_pl_percent >= 0 ? 'text-positive' : 'text-negative'
                    }`}>
                      {formatPercent(position.unrealized_pl_percent)}
                    </td>
                    <td className="px-6 py-4 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <button
                          onClick={() => handleEditPosition(position)}
                          className="text-accent hover:text-indigo-300 transition-colors"
                          title="Edit position"
                        >
                          <Edit2 size={18} />
                        </button>
                        <button
                          onClick={() => handleDeletePosition(position.id)}
                          className="text-negative hover:text-negative transition-colors"
                          title="Delete position"
                        >
                          <Trash2 size={18} />
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="card p-12 text-center">
          <Upload size={48} className="mx-auto mb-4 text-text-secondary" />
          <h3 className="text-xl font-semibold text-text-primary mb-2">Žádné pozice</h3>
          <p className="text-text-secondary mb-6">Nahrajte CSV soubor pro import vašich pozic</p>
          <button
            onClick={() => setShowUploadModal(true)}
            className="btn btn-primary"
          >
            Nahrát CSV
          </button>
        </div>
      )}

      {/* Create Portfolio Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-surface-base p-8 rounded-xl max-w-md w-full mx-4 border border-white/10">
            <h2 className="text-2xl font-bold text-text-primary mb-6">Vytvořit portfolio</h2>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-semibold text-text-secondary mb-2">
                  Vlastník
                </label>
                <input
                  type="text"
                  value={newPortfolioOwner}
                  onChange={(e) => setNewPortfolioOwner(e.target.value)}
                  placeholder="e.g., Já, Přítelkyně"
                  className="w-full px-4 py-3 bg-surface-raised border border-white/10 rounded-lg text-text-primary placeholder-slate-400 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
                />
              </div>
              <div>
                <label className="block text-sm font-semibold text-text-secondary mb-2">
                  Název portfolia
                </label>
                <input
                  type="text"
                  value={newPortfolioName}
                  onChange={(e) => setNewPortfolioName(e.target.value)}
                  placeholder="e.g., Growth Portfolio, Dividend Portfolio"
                  className="w-full px-4 py-3 bg-surface-raised border border-white/10 rounded-lg text-text-primary placeholder-slate-400 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
                />
              </div>
              <div>
                <label className="block text-sm font-semibold text-text-secondary mb-2">
                  Broker
                </label>
                <select
                  value={newPortfolioBroker}
                  onChange={(e) => setNewPortfolioBroker(e.target.value as BrokerType)}
                  className="w-full px-4 py-3 bg-surface-raised border border-white/10 rounded-lg text-text-primary focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
                >
                  <option value="T212">Trading 212</option>
                  <option value="DEGIRO">Degiro</option>
                  <option value="XTB">XTB</option>
                </select>
              </div>
            </div>
            <div className="flex gap-3 mt-6">
              <button
                onClick={() => {
                  setShowCreateModal(false);
                  setNewPortfolioName('');
                  setNewPortfolioOwner('');
                }}
                className="flex-1 px-6 py-3 bg-surface-raised text-text-primary rounded-lg font-semibold hover:bg-surface-hover transition-colors"
              >
                Zrušit
              </button>
              <button
                onClick={handleCreatePortfolio}
                disabled={!newPortfolioName.trim() || !newPortfolioOwner.trim()}
                className="flex-1 px-6 py-3 bg-indigo-600 text-text-primary rounded-lg font-semibold hover:bg-indigo-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Vytvořit
              </button>
            </div>
          </div>
        </div>
      )}

      {/* CSV Upload Modal */}
      {showUploadModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-surface-base p-8 rounded-xl max-w-md w-full mx-4 border border-white/10">
            <h2 className="text-2xl font-bold text-text-primary mb-6">Nahrát CSV</h2>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-semibold text-text-secondary mb-2">
                  Formát brokera
                </label>
                <select
                  value={uploadBroker}
                  onChange={(e) => setUploadBroker(e.target.value as BrokerType)}
                  className="w-full px-4 py-3 bg-surface-raised border border-white/10 rounded-lg text-text-primary focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
                >
                  <option value="T212">Trading 212</option>
                  <option value="DEGIRO">Degiro</option>
                  <option value="XTB">XTB</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-semibold text-text-secondary mb-2">
                  CSV soubor
                </label>
                <input
                  type="file"
                  accept=".csv"
                  onChange={handleFileSelect}
                  className="w-full text-text-primary file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:bg-indigo-600 file:text-text-primary file:cursor-pointer file:font-semibold hover:file:bg-indigo-700 file:transition-colors"
                />
                {selectedFile && (
                  <p className="text-sm text-text-secondary mt-2">
                    Vybráno: {selectedFile.name}
                  </p>
                )}
              </div>
            </div>
            <div className="flex gap-3 mt-6">
              <button
                onClick={() => {
                  setShowUploadModal(false);
                  setSelectedFile(null);
                }}
                className="flex-1 px-6 py-3 bg-surface-raised text-text-primary rounded-lg font-semibold hover:bg-surface-hover transition-colors"
              >
                Zrušit
              </button>
              <button
                onClick={handleUploadCSV}
                disabled={!selectedFile || loading}
                className="flex-1 px-6 py-3 bg-indigo-600 text-text-primary rounded-lg font-semibold hover:bg-indigo-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {loading ? 'Nahrávání...' : 'Nahrát'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Edit Position Modal */}
      {showEditModal && editingPosition && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-surface-base p-8 rounded-xl max-w-md w-full mx-4 border border-white/10">
            <h2 className="text-2xl font-bold text-text-primary mb-6">Upravit pozici</h2>
            <div className="mb-4 p-4 bg-surface-raised rounded-lg">
              <div className="text-2xl font-bold text-accent">{editingPosition.ticker}</div>
              <div className="text-sm text-text-secondary mt-1">
                Aktuálně: {editingPosition.shares_count} akcií @ ${editingPosition.avg_cost.toFixed(2)}
              </div>
            </div>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-semibold text-text-secondary mb-2">
                  Počet akcií
                </label>
                <input
                  type="number"
                  step="0.01"
                  value={editShares}
                  onChange={(e) => setEditShares(e.target.value)}
                  placeholder="e.g., 100"
                  className="w-full px-4 py-3 bg-surface-raised border border-white/10 rounded-lg text-text-primary placeholder-slate-400 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
                />
              </div>
              <div>
                <label className="block text-sm font-semibold text-text-secondary mb-2">
                  Průměrná cena (za akcii)
                </label>
                <input
                  type="number"
                  step="0.01"
                  value={editAvgCost}
                  onChange={(e) => setEditAvgCost(e.target.value)}
                  placeholder="e.g., 150.50"
                  className="w-full px-4 py-3 bg-surface-raised border border-white/10 rounded-lg text-text-primary placeholder-slate-400 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
                />
              </div>
              <div className="p-4 bg-accent/10 border border-indigo-500/30 rounded-lg">
                <div className="text-sm text-text-secondary">
                  <div className="flex justify-between mb-1">
                    <span>Nová nákladová cena:</span>
                    <span className="font-semibold text-text-primary">
                      ${(parseFloat(editShares || '0') * parseFloat(editAvgCost || '0')).toFixed(2)}
                    </span>
                  </div>
                  {editingPosition.current_price && (
                    <div className="flex justify-between">
                      <span>Nová tržní hodnota:</span>
                      <span className="font-semibold text-text-primary">
                        ${(parseFloat(editShares || '0') * editingPosition.current_price).toFixed(2)}
                      </span>
                    </div>
                  )}
                </div>
              </div>
            </div>
            <div className="flex gap-3 mt-6">
              <button
                onClick={() => {
                  setShowEditModal(false);
                  setEditingPosition(null);
                }}
                className="flex-1 px-6 py-3 bg-surface-raised text-text-primary rounded-lg font-semibold hover:bg-surface-hover transition-colors"
              >
                Zrušit
              </button>
              <button
                onClick={handleUpdatePosition}
                disabled={loading || !editShares || !editAvgCost}
                className="flex-1 px-6 py-3 bg-indigo-600 text-text-primary rounded-lg font-semibold hover:bg-indigo-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {loading ? 'Ukládám...' : 'Uložit změny'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Edit Cash Balance Modal */}
      {showCashModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-surface-base p-8 rounded-xl max-w-md w-full mx-4 border border-white/10">
            <h2 className="text-2xl font-bold text-text-primary mb-6">Upravit hotovost</h2>
            <div className="mb-4 p-4 bg-surface-raised rounded-lg">
              <div className="text-lg font-bold text-accent">Dostupná hotovost pro investice</div>
              <div className="text-sm text-text-secondary mt-1">
                Aktuálně: {formatCurrencySummary(portfolioSummary?.cash_balance || 0)}
              </div>
            </div>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-semibold text-text-secondary mb-2">
                  Hotovost (CZK)
                </label>
                <input
                  type="number"
                  step="0.01"
                  value={editCashBalance}
                  onChange={(e) => setEditCashBalance(e.target.value)}
                  placeholder="e.g., 50000"
                  className="w-full px-4 py-3 bg-surface-raised border border-white/10 rounded-lg text-text-primary placeholder-slate-400 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
                />
              </div>
              <div className="p-4 bg-positive/10 border border-positive/30 rounded-lg">
                <div className="text-sm text-text-secondary">
                  <div className="flex justify-between">
                    <span>Nová hotovost:</span>
                    <span className="font-semibold text-text-primary">
                      {formatCurrencySummary(parseFloat(editCashBalance || '0'))}
                    </span>
                  </div>
                </div>
              </div>
            </div>
            <div className="flex gap-3 mt-6">
              <button
                onClick={() => {
                  setShowCashModal(false);
                  setEditCashBalance('');
                }}
                className="flex-1 px-6 py-3 bg-surface-raised text-text-primary rounded-lg font-semibold hover:bg-surface-hover transition-colors"
              >
                Zrušit
              </button>
              <button
                onClick={handleEditCashBalance}
                disabled={loading || !editCashBalance}
                className="flex-1 px-6 py-3 bg-green-600 text-text-primary rounded-lg font-semibold hover:bg-green-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {loading ? 'Ukládám...' : 'Uložit hotovost'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Confirm Dialog */}
      <ConfirmDialog
        isOpen={confirmDialog.isOpen}
        message={confirmDialog.message}
        variant={confirmDialog.variant}
        onConfirm={confirmDialog.onConfirm}
        onCancel={() => setConfirmDialog({ ...confirmDialog, isOpen: false })}
      />
    </div>
  );
}


