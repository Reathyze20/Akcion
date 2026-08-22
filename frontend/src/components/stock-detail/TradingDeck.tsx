/**
 * TradingDeck Component
 * 
 * The "Execution Panel" for trading decisions.
 * LOCKED unless all safety conditions are met.
 * 
 * @fiduciary This component enforces ALL Gomes trading rules:
 * - No buying in RED market
 * - No buying with < 6 months runway
 * - No buying in WAIT_TIME phase
 * - No buying above Red Line (fully valued)
 */

import React from 'react';
import type { MarketAlert } from '../../types';
import { 
  Lock, 
  Unlock, 
  ShoppingCart, 
  TrendingDown,
  AlertTriangle,
  CheckCircle,
  Target
} from 'lucide-react';

export interface TradingDeckProps {
  ticker: string;
  currentPrice: number | null;
  // Safety Conditions
  /**
   * Current market traffic light. `null` means NOT YET KNOWN (still loading,
   * or the fetch failed) — it is deliberately NOT the same as GREEN and must
   * block buying. Defaulting an unknown market to GREEN is how this component
   * shipped for months with the RED-market block unreachable.
   */
  marketAlert: MarketAlert | null;
  cashRunwayMonths: number | null;
  inflectionStatus: 'WAIT_TIME' | 'UPCOMING' | 'ACTIVE_GOLD_MINE' | null;
  priceZone: string | null;
  // Trading Levels
  greenLine: number | null;
  redLine: number | null;
  maxBuyPrice: number | null;
  stopLossPrice: number | null;
  // Action
  actionVerdict: string | null;
  /** Position currency, so prices are not all rendered as USD. */
  currency?: string | null;
  /** Shares held — selling is only possible if there is something to sell. */
  sharesHeld?: number;
  onBuyClick?: () => void;
  onSellClick?: () => void;
  /**
   * Record a trade the owner already executed at the broker despite the
   * blockers. Always available: blocking the *encouragement* to trade is the
   * guardrail; blocking the *truth* about what he did would only make the
   * ledger wrong.
   */
  onRecordOffPlan?: (side: 'BUY' | 'SELL') => void;
}

interface TradeBlocker {
  reason: string;
  severity: 'critical' | 'warning';
}

/**
 * Evaluate all Gomes trading rules and return blockers
 */
const evaluateTradeBlockers = (props: TradingDeckProps): TradeBlocker[] => {
  const blockers: TradeBlocker[] = [];
  
  // Rule 1: Market Alert (Traffic Light) — canon §2.
  // Unknown blocks too: when we don't know the market state, the fiduciary
  // answer is "don't buy", never "go ahead".
  if (props.marketAlert === null) {
    blockers.push({
      reason: 'Stav trhu není známý — dokud se nenačte, nekupuj',
      severity: 'critical',
    });
  } else if (props.marketAlert === 'RED') {
    blockers.push({
      reason: 'Trh je v režimu RED - Cash is King, žádné nákupy',
      severity: 'critical',
    });
  } else if (props.marketAlert === 'ORANGE') {
    blockers.push({
      reason: 'Trh je v režimu ORANGE - navyšuj hotovost, nekupuj',
      severity: 'critical',
    });
  } else if (props.marketAlert === 'YELLOW') {
    blockers.push({
      reason: 'Trh je v režimu YELLOW - spekulativní nákupy stop',
      severity: 'warning',
    });
  }
  
  // Rule 2: Cash Runway (Bankruptcy Risk)
  if (props.cashRunwayMonths !== null && props.cashRunwayMonths < 6) {
    blockers.push({
      reason: `Cash Runway pouze ${props.cashRunwayMonths} měsíců - riziko bankrotu`,
      severity: 'critical',
    });
  }
  
  // Rule 3: Lifecycle Phase
  if (props.inflectionStatus === 'WAIT_TIME') {
    blockers.push({
      reason: 'Fáze WAIT TIME - čekáme na inflexní bod',
      severity: 'critical',
    });
  }
  
  // Rule 4: Price Zone
  if (['SELL_ZONE', 'OVERVALUED'].includes(props.priceZone ?? '')) {
    blockers.push({
      reason: 'Cena je v SELL ZONE - nadhodnoceno',
      severity: 'warning',
    });
  }
  
  // Rule 5: Above Max Buy Price
  if (props.currentPrice !== null && props.maxBuyPrice !== null && 
      props.currentPrice > props.maxBuyPrice) {
    blockers.push({
      reason: `Cena $${props.currentPrice} je nad Max Buy $${props.maxBuyPrice}`,
      severity: 'warning',
    });
  }
  
  // Rule 6: Above Red Line (Fully Valued)
  if (props.currentPrice !== null && props.redLine !== null &&
      props.currentPrice > props.redLine) {
    blockers.push({
      reason: `Cena je nad Red Line (plně ohodnoceno)`,
      severity: 'critical',
    });
  }
  
  return blockers;
};

export const TradingDeck: React.FC<TradingDeckProps> = (props) => {
  const {
    ticker,
    currentPrice,
    greenLine,
    redLine,
    maxBuyPrice,
    stopLossPrice,
    actionVerdict,
    currency,
    sharesHeld = 0,
    onBuyClick,
    onSellClick,
    onRecordOffPlan,
  } = props;
  
  const blockers = evaluateTradeBlockers(props);
  const criticalBlockers = blockers.filter(b => b.severity === 'critical');
  const warningBlockers = blockers.filter(b => b.severity === 'warning');
  
  const isTradeable = criticalBlockers.length === 0;
  const isBuyAction = ['BUY_NOW', 'ACCUMULATE'].includes(actionVerdict ?? '');
  const isSellAction = ['SELL', 'TRIM'].includes(actionVerdict ?? '');
  
  return (
    <div className="card p-0 overflow-hidden">
      {/* Header */}
      <div className={`
        px-4 py-3 flex items-center justify-between
        ${isTradeable ? 'bg-positive/10' : 'bg-negative/10'}
      `}>
        <div className="flex items-center gap-2">
          {isTradeable ? (
            <Unlock className="w-5 h-5 text-positive" />
          ) : (
            <Lock className="w-5 h-5 text-negative" />
          )}
          <span className={`font-semibold ${isTradeable ? 'text-positive' : 'text-negative'}`}>
            {isTradeable ? 'Trading povoleno' : 'Trading zablokován'}
          </span>
        </div>
        
        {/* Trading Signal Badge */}
        <div className={`
          px-3 py-1 rounded-full text-sm font-bold
          ${isBuyAction ? 'bg-positive/20 text-positive' :
            isSellAction ? 'bg-negative/20 text-negative' :
            'bg-text-muted/20 text-text-muted'}
        `}>
          {actionVerdict?.replace('_', ' ') || 'ANALYZE'}
        </div>
      </div>
      
      {/* Blockers List */}
      {blockers.length > 0 && (
        <div className="px-4 py-3 bg-primary-card/50 border-t border-border space-y-2">
          {criticalBlockers.map((blocker, i) => (
            <div key={`critical-${i}`} className="flex items-start gap-2 text-negative">
              <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5" />
              <span className="text-sm">{blocker.reason}</span>
            </div>
          ))}
          {warningBlockers.map((blocker, i) => (
            <div key={`warning-${i}`} className="flex items-start gap-2 text-warning">
              <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5" />
              <span className="text-sm">{blocker.reason}</span>
            </div>
          ))}
        </div>
      )}
      
      {/* All Clear Message */}
      {blockers.length === 0 && (
        <div className="px-4 py-3 bg-positive/5 border-t border-border">
          <div className="flex items-center gap-2 text-positive">
            <CheckCircle className="w-4 h-4" />
            <span className="text-sm">Všechny bezpečnostní kontroly prošly</span>
          </div>
        </div>
      )}
      
      {/* Price Levels */}
      <div className="px-4 py-3 border-t border-border grid grid-cols-2 md:grid-cols-4 gap-3">
        {greenLine !== null && (
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 rounded-full bg-positive" />
            <div>
              <p className="text-xs text-text-muted">Green Line</p>
              <p className="text-sm font-mono font-bold text-positive">${greenLine.toFixed(2)}</p>
            </div>
          </div>
        )}
        
        {maxBuyPrice !== null && (
          <div className="flex items-center gap-2">
            <Target className="w-4 h-4 text-accent" />
            <div>
              <p className="text-xs text-text-muted">Max Buy</p>
              <p className="text-sm font-mono font-bold text-accent">${maxBuyPrice.toFixed(2)}</p>
            </div>
          </div>
        )}
        
        {stopLossPrice !== null && (
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-warning" />
            <div>
              <p className="text-xs text-text-muted">Stop Loss</p>
              <p className="text-sm font-mono font-bold text-warning">${stopLossPrice.toFixed(2)}</p>
            </div>
          </div>
        )}
        
        {redLine !== null && (
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 rounded-full bg-negative" />
            <div>
              <p className="text-xs text-text-muted">Red Line</p>
              <p className="text-sm font-mono font-bold text-negative">${redLine.toFixed(2)}</p>
            </div>
          </div>
        )}
      </div>
      
      {/* Action Buttons */}
      <div className="px-4 py-4 border-t border-border flex gap-3">
        {/* Buy Button */}
        <button
          onClick={onBuyClick}
          disabled={!isTradeable || !isBuyAction}
          className={`
            flex-1 flex items-center justify-center gap-2 py-3 rounded-lg
            font-semibold transition-all
            ${isTradeable && isBuyAction
              ? 'bg-positive text-white hover:bg-positive/90 cursor-pointer'
              : 'bg-text-muted/20 text-text-muted cursor-not-allowed'}
          `}
        >
          {!isTradeable ? (
            <Lock className="w-5 h-5" />
          ) : (
            <ShoppingCart className="w-5 h-5" />
          )}
          <span>Koupit {ticker}</span>
        </button>
        
        {/* Sell Button */}
        <button
          onClick={onSellClick}
          disabled={sharesHeld <= 0}
          className={`
            flex-1 flex items-center justify-center gap-2 py-3 rounded-lg
            font-semibold transition-all
            ${sharesHeld > 0
              ? 'bg-negative text-white hover:bg-negative/90 cursor-pointer'
              : 'bg-text-muted/20 text-text-muted cursor-not-allowed'}
          `}
        >
          <TrendingDown className="w-5 h-5" />
          <span>Prodat {ticker}</span>
        </button>
      </div>
      
      {/* Already traded anyway? The ledger must still be able to record it. */}
      {onRecordOffPlan && (
        <div className="px-4 pb-3 -mt-1 text-center">
          <button
            onClick={() => onRecordOffPlan(isTradeable && isBuyAction ? 'BUY' : 'SELL')}
            className="text-xs text-text-muted underline hover:text-text-primary"
          >
            Už jsem obchod udělal u brokera — zapsat ho
          </button>
        </div>
      )}

      {/* Current Price Reference */}
      {currentPrice !== null && (
        <div className="px-4 py-2 bg-primary-card/30 border-t border-border text-center">
          <span className="text-xs text-text-muted">Aktuální cena: </span>
          <span className="text-sm font-mono font-bold text-text-primary">
            {new Intl.NumberFormat('cs-CZ', {
              style: currency ? 'currency' : 'decimal',
              currency: currency ?? undefined,
              maximumFractionDigits: 2,
            }).format(currentPrice)}
          </span>
        </div>
      )}
    </div>
  );
};

export default TradingDeck;
