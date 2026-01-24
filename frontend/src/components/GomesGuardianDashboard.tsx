/**
 * Akcion Investment Terminal
 * 
 * Professional portfolio management dashboard:
 * - Multi-Account Portfolio Consolidation
 * - Proprietary Scoring & Risk Assessment
 * - Position Sizing (Kelly Criterion)
 * - Thesis Drift Monitoring & Alerts
 */

import React, { useState, useEffect, useMemo, useRef } from 'react';
import { 
  TrendingUp, TrendingDown, AlertTriangle, Shield, Rocket, Anchor,
  DollarSign, Users, PlusCircle, RefreshCw, Search,
  Target, Zap, AlertCircle, X, Check, Clock, BarChart3, Eye, Briefcase,
  Upload, Plus, FileSpreadsheet, Edit3
} from 'lucide-react';
import { apiClient } from '../api/client';
import type { 
  PortfolioSummary, Position, Stock,
  FamilyAuditResponse, BrokerType
} from '../types';

// ============================================================================
// TYPES
// ============================================================================

interface EnrichedPosition extends Position {
  stock?: Stock;
  gomes_score: number | null;
  // Gomes Gap Analysis
  target_weight_pct: number;     // Cílová váha podle skóre
  weight_in_portfolio: number;   // Aktuální váha v portfoliu
  gap_czk: number;               // Mezera v CZK (+ = dokoupit, - = prodat)
  optimal_size: number;          // Kolik investovat TENTO MĚSÍC (po prioritizaci)
  allocation_priority: number;   // Priorita (1 = nejvyšší)
  // Status
  trend_status: 'BULLISH' | 'BEARISH' | 'NEUTRAL';
  is_deteriorated: boolean;
  is_overweight: boolean;
  is_underweight: boolean;
  action_signal: 'BUY' | 'HOLD' | 'SELL' | 'SNIPER';  // Akční signál
  inflection_status?: string;
  // Next Catalyst
  next_catalyst?: string;  // Format: "EVENT / DATE" or null
}

interface FamilyPortfolioData {
  totalValue: number;
  totalValueEUR: number;  // EUR equivalent
  totalCash: number;
  portfolios: PortfolioSummary[];
  allPositions: EnrichedPosition[];
  rocketCount: number;  // High growth (score >= 7)
  anchorCount: number;  // Core positions (score 5-6)
  waitTimeCount: number; // Wait Time positions (score 1-4)
  unanalyzedCount: number; // Not yet analyzed (no score)
  riskScore: number;    // 0-100
}

// ============================================================================
// GOMES TARGET WEIGHTS (Conviction Mapping)
// ============================================================================
// Kolik % celého portfolia si akcie ZASLOUŽÍ na základě skóre
const TARGET_WEIGHTS: Record<number, number> = {
  10: 15,   // CORE - Highest conviction (12-15%)
  9: 15,    // CORE - High conviction  
  8: 12,    // STRONG - Solid position (10-12%)
  7: 10,    // GROWTH - Growth position (7-10%)
  6: 5,     // WATCH - Monitor closely (3-5%)
  5: 3,     // WATCH - Small position
  4: 0,     // EXIT - Should not hold
  3: 0,     // EXIT - Sell signal
  2: 0,     // EXIT - Strong sell
  1: 0,     // EXIT - Avoid completely
  0: 0,
};

// Hard Caps (Gomesova pojistka)
const MAX_POSITION_WEIGHT = 15;  // Max 15% portfolia v jedné akcii
const MIN_INVESTMENT_CZK = 1000; // Min vklad (kvůli poplatkům)
const MONTHLY_CONTRIBUTION = 20000; // Měsíční vklad v CZK

// ============================================================================
// HELPER FUNCTIONS
// ============================================================================

const formatCurrency = (amount: number, currency: string = 'CZK'): string => {
  return new Intl.NumberFormat('cs-CZ', { 
    style: 'currency', 
    currency,
    maximumFractionDigits: 0 
  }).format(amount);
};

const formatPercent = (value: number): string => {
  const sign = value >= 0 ? '+' : '';
  return `${sign}${value.toFixed(2)}%`;
};

/**
 * Calculate estimated months to reach target with monthly contributions and returns
 * Formula: Future Value = PV * (1 + r)^n + PMT * ((1 + r)^n - 1) / r
 */
const calculateMonthsToTarget = (
  currentValue: number,
  targetValue: number,
  monthlyContribution: number = 20000,
  annualReturn: number = 0.15
): number => {
  if (currentValue >= targetValue) return 0;
  const monthlyReturn = annualReturn / 12;
  let value = currentValue;
  let months = 0;
  const maxMonths = 240; // 20 years max
  
  while (value < targetValue && months < maxMonths) {
    value = value * (1 + monthlyReturn) + monthlyContribution;
    months++;
  }
  return months;
};

const getTargetWeight = (score: number | null): number => {
  if (score === null) return 0;
  const roundedScore = Math.round(score);
  return TARGET_WEIGHTS[roundedScore] ?? 0;
};

/**
 * Get action signal based on score and weight gap
 */
const getActionSignal = (
  score: number | null, 
  currentWeight: number, 
  targetWeight: number
): 'BUY' | 'HOLD' | 'SELL' | 'SNIPER' => {
  if (score === null) return 'HOLD';
  if (score < 5) return 'SELL';  // Score < 5 = EXIT
  
  const gapPct = targetWeight - currentWeight;
  
  // Sniper opportunity: score 8+ and significantly underweight (>5% gap)
  if (score >= 8 && gapPct > 5) return 'SNIPER';
  
  // Buy signal: underweight by >2%
  if (gapPct > 2) return 'BUY';
  
  // Hold: roughly at target
  return 'HOLD';
};

/**
 * Get dynamic action command for position
 * STRONG BUY, HARD EXIT, HOLD, FREE RIDE
 */
const getActionCommand = (
  score: number | null,
  currentWeight: number,
  targetWeight: number,
  unrealizedProfitPct: number
): { text: string; color: string; bgColor?: string } => {
  // Priority 1: Free Ride at 150%+
  if (unrealizedProfitPct >= 150) {
    return { text: 'FREE RIDE', color: 'text-amber-400', bgColor: 'bg-amber-500/10' };
  }
  
  // Priority 2: Hard Exit for score < 4
  if (score !== null && score < 4) {
    return { text: 'HARD EXIT', color: 'text-red-400', bgColor: 'bg-red-500/20' };
  }
  
  // Priority 3: Strong Buy for score >= 8 and underweight
  if (score !== null && score >= 8 && currentWeight < targetWeight) {
    return { text: 'STRONG BUY', color: 'text-green-400 font-bold' };
  }
  
  // Priority 4: Hold if at or above target weight
  if (score !== null && score >= 5 && currentWeight >= targetWeight) {
    return { text: 'HOLD', color: 'text-slate-500' };
  }
  
  // Default: BUY signal for underweight positions with score 5-7
  if (score !== null && score >= 5 && currentWeight < targetWeight) {
    return { text: 'BUY', color: 'text-emerald-400' };
  }
  
  // No score or edge case
  return { text: 'ANALYZE', color: 'text-slate-600' };
};

const getTrendStatus = (stock: Stock | undefined): 'BULLISH' | 'BEARISH' | 'NEUTRAL' => {
  if (!stock || !stock.current_price || !stock.green_line || !stock.red_line) {
    return 'NEUTRAL';
  }
  const priceRange = stock.red_line - stock.green_line;
  if (priceRange <= 0) return 'NEUTRAL';
  const position = (stock.current_price - stock.green_line) / priceRange;
  if (position <= 0.4) return 'BULLISH';
  if (position >= 0.7) return 'BEARISH';
  return 'NEUTRAL';
};

// ============================================================================
// SUB-COMPONENTS
// ============================================================================

// Risk Meter Component - warns when Growth > 60%
const RiskMeter: React.FC<{ 
  rocketCount: number; 
  anchorCount: number; 
  waitTimeCount: number; 
  unanalyzedCount: number;
  riskScore: number 
}> = ({
  rocketCount, anchorCount, waitTimeCount, unanalyzedCount, riskScore
}) => {
  // Risk thresholds: >60% Growth = Orange warning, >70% = Red danger
  const analyzedTotal = rocketCount + anchorCount + waitTimeCount;
  const isOverexposed = analyzedTotal > 0 && riskScore > 60;
  const isDangerous = analyzedTotal > 0 && riskScore > 70;
  const hasUnanalyzed = unanalyzedCount > 0;
  const riskColor = isDangerous ? 'text-red-400' : isOverexposed ? 'text-amber-400' : 'text-green-400';
  const riskBg = isDangerous ? 'bg-red-500' : isOverexposed ? 'bg-amber-500' : 'bg-green-500';
  const borderColor = isDangerous ? 'border-red-500/50' : isOverexposed ? 'border-amber-500/50' : hasUnanalyzed ? 'border-slate-600' : 'border-slate-700';
  
  return (
    <div className={`bg-slate-800/50 rounded-xl p-4 border ${borderColor} ${isDangerous ? 'animate-pulse' : ''}`}>
      <div className="flex items-center justify-between mb-3">
        <div className="text-xs text-slate-400 uppercase tracking-wider">Risk Exposure</div>
        {hasUnanalyzed && !isOverexposed && (
          <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-slate-600 text-slate-300">
            RUN DEEP DD
          </span>
        )}
        {isOverexposed && (
          <span className={`text-[10px] font-bold px-2 py-0.5 rounded ${isDangerous ? 'bg-red-500/20 text-red-400' : 'bg-amber-500/20 text-amber-400'}`}>
            {isDangerous ? 'REBALANCE' : 'MONITOR'}
          </span>
        )}
      </div>
      
      {/* Score display */}
      <div className={`text-3xl font-black ${riskColor} text-center mb-3`}>
        {riskScore}%
      </div>
      
      {/* Categories row */}
      <div className="grid grid-cols-4 gap-1 text-center">
        <div className="flex flex-col items-center">
          <Rocket className={`w-4 h-4 mb-0.5 ${rocketCount > 0 ? 'text-purple-400' : 'text-slate-600'}`} />
          <span className={`font-bold text-sm ${rocketCount > 0 ? 'text-purple-400' : 'text-slate-600'}`}>{rocketCount}</span>
          <span className="text-[8px] text-slate-500">Growth</span>
        </div>
        <div className="flex flex-col items-center">
          <Anchor className={`w-4 h-4 mb-0.5 ${anchorCount > 0 ? 'text-blue-400' : 'text-slate-600'}`} />
          <span className={`font-bold text-sm ${anchorCount > 0 ? 'text-blue-400' : 'text-slate-600'}`}>{anchorCount}</span>
          <span className="text-[8px] text-slate-500">Core</span>
        </div>
        <div className="flex flex-col items-center">
          <Clock className={`w-4 h-4 mb-0.5 ${waitTimeCount > 0 ? 'text-amber-400' : 'text-slate-600'}`} />
          <span className={`font-bold text-sm ${waitTimeCount > 0 ? 'text-amber-400' : 'text-slate-600'}`}>{waitTimeCount}</span>
          <span className="text-[8px] text-slate-500">Wait</span>
        </div>
        <div className="flex flex-col items-center">
          <AlertCircle className={`w-4 h-4 mb-0.5 ${unanalyzedCount > 0 ? 'text-slate-400' : 'text-slate-600'}`} />
          <span className={`font-bold text-sm ${unanalyzedCount > 0 ? 'text-slate-400' : 'text-slate-600'}`}>{unanalyzedCount}</span>
          <span className="text-[8px] text-slate-500">New</span>
        </div>
      </div>
      
      {isOverexposed && (
        <div className={`mt-2 text-[10px] text-center ${isDangerous ? 'text-red-400' : 'text-amber-400'}`}>
          {isDangerous ? 'Rebalance needed' : 'Monitor growth allocation'}
        </div>
      )}
    </div>
  );
};

// ============================================================================
// FREEDOM COUNTDOWN - Retirement Visualization
// ============================================================================

interface FreedomCountdownProps {
  currentValue: number;
  targetValue: number;  // e.g. 30,000,000 CZK
  monthlyContribution: number;
  annualReturn: number;
  targetAge: number;    // e.g. 50
  currentAge: number;   // calculated from target
}

const FreedomCountdown: React.FC<FreedomCountdownProps> = ({
  currentValue,
  targetValue,
  monthlyContribution,
  annualReturn,
  targetAge,
  currentAge
}) => {
  // Calculate months to reach target with compound growth
  const calculateFreedomDate = (): { months: number; projectedValue: number; daysSaved: number } => {
    const monthlyReturn = annualReturn / 12;
    let value = currentValue;
    let months = 0;
    const maxMonths = 360; // 30 years max
    
    while (value < targetValue && months < maxMonths) {
      value = value * (1 + monthlyReturn) + monthlyContribution;
      months++;
    }
    
    // Calculate how many days the last contribution "saved"
    // Without last contribution, how many extra months needed?
    let valueWithoutLastContribution = currentValue - monthlyContribution;
    if (valueWithoutLastContribution < 0) valueWithoutLastContribution = 0;
    let monthsWithout = 0;
    let tempValue = valueWithoutLastContribution;
    while (tempValue < targetValue && monthsWithout < maxMonths) {
      tempValue = tempValue * (1 + monthlyReturn) + monthlyContribution;
      monthsWithout++;
    }
    const daysSaved = (monthsWithout - months) * 30; // Approximate days
    
    return { months, projectedValue: value, daysSaved: Math.max(0, daysSaved) };
  };

  const { months, daysSaved } = calculateFreedomDate();
  const yearsToFreedom = Math.floor(months / 12);
  const monthsRemaining = months % 12;
  const freedomAge = currentAge + yearsToFreedom;
  const progressPercent = Math.min(100, (currentValue / targetValue) * 100);
  
  // Milestones
  const milestones = [
    { value: 500000, label: '500k', emoji: '🌱' },
    { value: 1000000, label: '1M', emoji: '🚀' },
    { value: 5000000, label: '5M', emoji: '💎' },
    { value: 10000000, label: '10M', emoji: '👑' },
    { value: 30000000, label: '30M', emoji: '🏰' },
  ];
  
  const currentMilestone = milestones.filter(m => currentValue >= m.value).pop();
  const nextMilestone = milestones.find(m => currentValue < m.value);

  return (
    <div className="bg-gradient-to-br from-slate-800/80 to-indigo-900/30 rounded-xl p-5 border border-indigo-500/30">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Target className="w-5 h-5 text-indigo-400" />
          <span className="text-sm font-bold text-indigo-300 uppercase tracking-wider">Freedom Countdown</span>
        </div>
        <div className="text-xs text-slate-400">
          Cíl: {(targetValue / 1000000).toFixed(0)}M Kč @ {targetAge} let
        </div>
      </div>
      
      {/* Main countdown display */}
      <div className="grid grid-cols-3 gap-4 mb-4">
        <div className="text-center">
          <div className="text-3xl font-black text-white">{yearsToFreedom}</div>
          <div className="text-xs text-slate-400">let</div>
        </div>
        <div className="text-center border-x border-slate-700">
          <div className="text-3xl font-black text-white">{monthsRemaining}</div>
          <div className="text-xs text-slate-400">měsíců</div>
        </div>
        <div className="text-center">
          <div className="text-3xl font-black text-indigo-400">{freedomAge}</div>
          <div className="text-xs text-slate-400">věk svobody</div>
        </div>
      </div>
      
      {/* Progress bar with milestones */}
      <div className="relative mb-4">
        <div className="h-3 bg-slate-700 rounded-full overflow-hidden">
          <div 
            className="h-full bg-gradient-to-r from-indigo-500 via-purple-500 to-pink-500 transition-all duration-1000 relative"
            style={{ width: `${progressPercent}%` }}
          >
            <div className="absolute inset-0 bg-white/20 animate-pulse" />
          </div>
        </div>
        {/* Milestone markers */}
        <div className="absolute inset-0 flex items-center">
          {milestones.map((m) => {
            const pos = (m.value / targetValue) * 100;
            if (pos > 100) return null;
            return (
              <div 
                key={m.label}
                className="absolute transform -translate-x-1/2"
                style={{ left: `${pos}%` }}
                title={`${m.label} Kč`}
              >
                <div className={`text-xs ${currentValue >= m.value ? 'opacity-100' : 'opacity-30'}`}>
                  {m.emoji}
                </div>
              </div>
            );
          })}
        </div>
      </div>
      
      {/* Current milestone & next target */}
      <div className="flex justify-between items-center text-xs mb-3">
        <div className="flex items-center gap-1">
          {currentMilestone && (
            <span className="text-green-400">
              {currentMilestone.emoji} {currentMilestone.label} dosaženo!
            </span>
          )}
        </div>
        {nextMilestone && (
          <div className="text-slate-400">
            Další: {nextMilestone.emoji} {nextMilestone.label} 
            <span className="text-indigo-400 ml-1">
              ({((currentValue / nextMilestone.value) * 100).toFixed(0)}%)
            </span>
          </div>
        )}
      </div>
      
      {/* Motivational message */}
      {daysSaved > 0 && (
        <div className="bg-green-500/10 border border-green-500/30 rounded-lg p-3 text-center">
          <div className="text-green-400 text-sm">
            🎉 Tvůj poslední vklad {formatCurrency(monthlyContribution)} přiblížil důchod o <span className="font-bold">{daysSaved} dní</span>!
          </div>
          <div className="text-xs text-green-300/70 mt-1">
            Každý vklad = nákup času pro tebe a rodinu
          </div>
        </div>
      )}
      
      {/* Quick stats */}
      <div className="grid grid-cols-2 gap-3 mt-4 text-xs">
        <div className="bg-slate-800/50 rounded-lg p-2 text-center">
          <div className="text-slate-400">Aktuální hodnota</div>
          <div className="text-white font-bold">{formatCurrency(currentValue)}</div>
        </div>
        <div className="bg-slate-800/50 rounded-lg p-2 text-center">
          <div className="text-slate-400">Progress</div>
          <div className="text-indigo-400 font-bold">{progressPercent.toFixed(2)}%</div>
        </div>
      </div>
    </div>
  );
};

// ============================================================================
// COMPOUND SNOWBALL - Future Value Projection
// ============================================================================

interface CompoundSnowballProps {
  currentValue: number;
  monthlyContribution: number;
  annualReturn: number;
  years: number;
}

const CompoundSnowball: React.FC<CompoundSnowballProps> = ({
  currentValue,
  monthlyContribution,
  annualReturn,
  years
}) => {
  // Calculate projection points
  const projectionPoints = useMemo(() => {
    const points: { year: number; projected: number; target: number }[] = [];
    const monthlyReturn = annualReturn / 12;
    let value = currentValue;
    
    for (let year = 0; year <= years; year++) {
      // Target line (ideal path)
      const targetValue = currentValue * Math.pow(1 + annualReturn, year) + 
        monthlyContribution * 12 * ((Math.pow(1 + annualReturn, year) - 1) / annualReturn);
      
      points.push({
        year,
        projected: value,
        target: targetValue
      });
      
      // Compound for next year
      for (let month = 0; month < 12; month++) {
        value = value * (1 + monthlyReturn) + monthlyContribution;
      }
    }
    return points;
  }, [currentValue, monthlyContribution, annualReturn, years]);
  
  const maxValue = Math.max(...projectionPoints.map(p => Math.max(p.projected, p.target)));
  const finalProjected = projectionPoints[projectionPoints.length - 1]?.projected || 0;
  
  return (
    <div className="bg-slate-800/50 rounded-xl p-4 border border-slate-700">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <TrendingUp className="w-4 h-4 text-purple-400" />
          <span className="text-xs font-bold text-slate-300 uppercase tracking-wider">Compound Snowball</span>
        </div>
        <div className="text-xs text-slate-400">
          {years}Y projekce @ {(annualReturn * 100).toFixed(0)}% p.a.
        </div>
      </div>
      
      {/* Simple bar visualization */}
      <div className="space-y-2 mb-3">
        {projectionPoints.filter((_, i) => i % 5 === 0 || i === projectionPoints.length - 1).map((point) => (
          <div key={point.year} className="flex items-center gap-2 text-xs">
            <span className="w-8 text-slate-500">{point.year}Y</span>
            <div className="flex-1 h-4 bg-slate-700 rounded overflow-hidden relative">
              <div 
                className="h-full bg-gradient-to-r from-purple-500 to-pink-500 transition-all"
                style={{ width: `${(point.projected / maxValue) * 100}%` }}
              />
            </div>
            <span className="w-20 text-right text-slate-300 font-mono">
              {point.projected >= 1000000 
                ? `${(point.projected / 1000000).toFixed(1)}M` 
                : `${(point.projected / 1000).toFixed(0)}k`}
            </span>
          </div>
        ))}
      </div>
      
      {/* Final projection highlight */}
      <div className="bg-purple-500/10 border border-purple-500/30 rounded-lg p-3 text-center">
        <div className="text-xs text-slate-400">Za {years} let budeš mít</div>
        <div className="text-2xl font-black text-purple-400">
          {formatCurrency(finalProjected)}
        </div>
        <div className="text-xs text-purple-300/70">
          při {(annualReturn * 100).toFixed(0)}% ročním výnosu + {formatCurrency(monthlyContribution)}/měsíc
        </div>
      </div>
    </div>
  );
};

// ============================================================================
// MERIT BADGES - Gamification
// ============================================================================

interface MeritBadge {
  id: string;
  name: string;
  icon: string;
  description: string;
  earned: boolean;
  earnedDate?: string;
  category: 'discipline' | 'strategy' | 'growth';
}

const MeritBadges: React.FC<{ positions: EnrichedPosition[]; totalValue: number }> = ({ positions, totalValue }) => {
  // Calculate earned badges based on portfolio state
  const badges: MeritBadge[] = useMemo(() => {
    const allBadges: MeritBadge[] = [
      // Discipline badges
      {
        id: 'weed-cutter',
        name: 'Weed Cutter',
        icon: 'scissors',
        description: 'Prodej akcii se skóre pod 3',
        earned: false, // Would track in DB when sale happens
        category: 'discipline'
      },
      {
        id: 'diamond-hands',
        name: 'Diamond Hands',
        icon: 'diamond',
        description: 'Drž akcii 9/10 i při -20% drawdown',
        earned: positions.some(p => 
          p.gomes_score && p.gomes_score >= 9 && p.unrealized_pl_percent <= -20
        ),
        category: 'discipline'
      },
      {
        id: 'sniper',
        name: 'Sniper',
        icon: 'target',
        description: 'Nakup přesně na supportu 30WMA',
        earned: false, // Would track entry vs 30WMA
        category: 'strategy'
      },
      {
        id: 'first-rocket',
        name: 'First Rocket',
        icon: 'rocket',
        description: 'Měj první pozici se skóre 9+',
        earned: positions.some(p => p.gomes_score && p.gomes_score >= 9),
        category: 'growth'
      },
      {
        id: 'diversified',
        name: 'Diversified',
        icon: 'grid',
        description: 'Měj 5+ různých pozic',
        earned: positions.length >= 5,
        category: 'strategy'
      },
      {
        id: 'free-rider',
        name: 'Free Rider',
        icon: 'bird',
        description: 'Měj pozici s P/L 100%+ (house money)',
        earned: positions.some(p => p.unrealized_pl_percent >= 100),
        category: 'growth'
      },
      {
        id: 'patient-investor',
        name: 'Patient Investor',
        icon: 'zen',
        description: 'Drž portfolio bez panického prodeje 6+ měsíců',
        earned: false, // Would track in DB
        category: 'discipline'
      },
      {
        id: 'six-figures',
        name: 'Six Figures',
        icon: 'money',
        description: 'Portfolio přesáhlo 100k Kč',
        earned: totalValue >= 100000,
        category: 'growth'
      },
      {
        id: 'half-million',
        name: 'Half Millionaire',
        icon: 'trophy',
        description: 'Portfolio přesáhlo 500k Kč',
        earned: totalValue >= 500000,
        category: 'growth'
      }
    ];
    
    return allBadges;
  }, [positions, totalValue]);
  
  const earnedCount = badges.filter(b => b.earned).length;
  
  return (
    <div className="bg-slate-800/50 rounded-xl p-4 border border-amber-500/30">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Shield className="w-4 h-4 text-amber-400" />
          <span className="text-xs font-bold text-amber-300 uppercase tracking-wider">Gomes Merit Badges</span>
        </div>
        <div className="text-xs text-slate-400">
          {earnedCount}/{badges.length} získáno
        </div>
      </div>
      
      <div className="grid grid-cols-3 gap-2">
        {badges.map((badge) => (
          <div 
            key={badge.id}
            className={`
              p-2 rounded-lg text-center transition-all
              ${badge.earned 
                ? 'bg-amber-500/20 border border-amber-500/40' 
                : 'bg-slate-700/30 border border-slate-600/30 opacity-40'
              }
            `}
            title={badge.description}
          >
            <div className={`text-xl mb-1 ${badge.earned ? 'text-amber-400' : 'text-slate-500'}`}>
              {badge.icon === 'scissors' && <span className="inline-block w-6 h-6">✂</span>}
              {badge.icon === 'diamond' && <span className="inline-block w-6 h-6">◆</span>}
              {badge.icon === 'target' && <span className="inline-block w-6 h-6">◎</span>}
              {badge.icon === 'rocket' && <span className="inline-block w-6 h-6">↑</span>}
              {badge.icon === 'grid' && <span className="inline-block w-6 h-6">#</span>}
              {badge.icon === 'bird' && <span className="inline-block w-6 h-6">~</span>}
              {badge.icon === 'zen' && <span className="inline-block w-6 h-6">○</span>}
              {badge.icon === 'money' && <span className="inline-block w-6 h-6">$</span>}
              {badge.icon === 'trophy' && <span className="inline-block w-6 h-6">★</span>}
            </div>
            <div className={`text-[10px] font-bold ${badge.earned ? 'text-amber-300' : 'text-slate-500'}`}>
              {badge.name}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

// Portfolio Row Component
const PortfolioRow: React.FC<{
  position: EnrichedPosition;
  onClick: () => void;
}> = ({ position, onClick }) => {
  const scoreColor = position.gomes_score 
    ? position.gomes_score >= 7 ? 'text-green-400' 
      : position.gomes_score >= 5 ? 'text-yellow-400' 
      : 'text-red-400'
    : 'text-slate-500';

  const trendIcon = position.trend_status === 'BULLISH' 
    ? <TrendingUp className="w-4 h-4 text-green-400" />
    : position.trend_status === 'BEARISH'
    ? <TrendingDown className="w-4 h-4 text-red-400" />
    : <BarChart3 className="w-4 h-4 text-slate-400" />;

  const plColor = position.unrealized_pl_percent >= 0 ? 'text-green-400' : 'text-red-400';
  
  // Get action command
  const actionCmd = getActionCommand(
    position.gomes_score,
    position.weight_in_portfolio,
    position.target_weight_pct,
    position.unrealized_pl_percent
  );
  
  // Check if row should be highlighted (HARD EXIT)
  const isHardExit = position.gomes_score !== null && position.gomes_score < 4;
  
  // Strategy: Free Ride eligible vs Growing
  const isFreeRideEligible = position.unrealized_pl_percent >= 150;
  const progressTo150 = Math.min(100, (position.unrealized_pl_percent / 150) * 100);
  
  // Calculate shares to sell for Free Ride
  const sharesToSellForFreeRide = useMemo(() => {
    if (!isFreeRideEligible) return 0;
    const currentPrice = position.stock?.current_price ?? position.current_price ?? 0;
    if (currentPrice <= 0) return 0;
    const costBasis = position.shares_count * position.avg_cost;
    return Math.ceil(costBasis / currentPrice);
  }, [position, isFreeRideEligible]);

  return (
    <tr 
      onClick={onClick}
      className={`
        border-b border-slate-700/50 cursor-pointer transition-all
        hover:bg-slate-800/70
        ${isHardExit ? 'bg-red-900/30' : ''}
        ${position.is_deteriorated && !isHardExit ? 'animate-pulse bg-red-900/20' : ''}
      `}
    >
      {/* Ticker & Name */}
      <td className="py-3 px-4">
        <div className="flex items-center gap-3">
          <div>
            <div className="flex items-center gap-2">
              <span className="font-bold text-white text-lg">{position.ticker}</span>
            </div>
            <div className="text-xs text-slate-400 truncate max-w-[150px]">
              {position.company_name || 'Unknown'}
            </div>
          </div>
          {position.is_deteriorated && (
            <span className="px-2 py-0.5 bg-red-500/20 text-red-400 text-xs font-bold rounded animate-pulse">
              REVIEW
            </span>
          )}
        </div>
      </td>

      {/* ACTION - Dynamic Command */}
      <td className="py-3 px-3">
        <div className={`text-xs font-bold uppercase tracking-wide ${actionCmd.color} ${actionCmd.bgColor ? actionCmd.bgColor + ' px-2 py-1 rounded' : ''}`}>
          {actionCmd.text}
        </div>
      </td>

      {/* Weight % - Aktuální vs Cílová */}
      <td className="py-3 px-4">
        <div className="flex items-center gap-1">
          <span className={`font-mono font-bold ${position.is_overweight ? 'text-red-400' : position.is_underweight ? 'text-amber-400' : 'text-slate-300'}`}>
            {position.weight_in_portfolio.toFixed(1)}%
          </span>
          <span className="text-slate-500">/</span>
          <span className="font-mono text-slate-400">{position.target_weight_pct}%</span>
        </div>
        {position.is_overweight && (
          <div className="text-[10px] text-red-400">OVERWEIGHT</div>
        )}
        {position.is_underweight && !position.is_overweight && (
          <div className="text-[10px] text-amber-400">UNDERWEIGHT</div>
        )}
      </td>

      {/* Gomes Score */}
      <td className="py-3 px-4">
        <div className={`text-2xl font-black ${scoreColor}`}>
          {position.gomes_score ?? '-'}
        </div>
      </td>

      {/* Optimal Size - GAP ANALYSIS */}
      <td className="py-3 px-4">
        {position.action_signal === 'SELL' ? (
          <div className="text-center">
            <div className="text-red-400 font-bold text-sm">SELL</div>
            <div className="text-[10px] text-red-300">Score &lt; 5</div>
          </div>
        ) : position.optimal_size > 0 ? (
          <div>
            <div className="flex items-center gap-1">
              {position.action_signal === 'SNIPER' && <span className="text-amber-400 text-xs font-bold">SNIPER</span>}
              <span className="text-lg font-bold text-emerald-400 font-mono">
                {formatCurrency(position.optimal_size)}
              </span>
            </div>
            <div className="text-[10px] text-slate-500">
              Gap: {formatCurrency(position.gap_czk)}
            </div>
            {position.allocation_priority > 0 && position.allocation_priority <= 3 && (
              <div className="text-[10px] text-amber-400 font-bold">
                #{position.allocation_priority} priorita
              </div>
            )}
          </div>
        ) : (
          <div className="text-center">
            <div className="text-slate-500 font-mono text-sm">0 Kč</div>
            <div className="text-[10px] text-slate-600">
              {position.gap_czk <= 0 ? 'Na cíli' : 'Nízká priorita'}
            </div>
          </div>
        )}
      </td>

      {/* NEXT CATALYST */}
      <td className="py-3 px-3">
        {position.next_catalyst ? (
          <div className="text-[10px] text-slate-400 uppercase tracking-wide font-mono truncate max-w-[100px]" title={position.next_catalyst}>
            {position.next_catalyst.length > 20 ? position.next_catalyst.slice(0, 20) + '...' : position.next_catalyst}
          </div>
        ) : (
          <div className="text-[10px] text-red-400/70 uppercase">NONE</div>
        )}
      </td>

      {/* 30 WMA Status */}
      <td className="py-3 px-4">
        <div className="flex items-center gap-2">
          {trendIcon}
          <span className={`text-sm ${
            position.trend_status === 'BULLISH' ? 'text-green-400' :
            position.trend_status === 'BEARISH' ? 'text-red-400' :
            'text-slate-400'
          }`}>
            {position.trend_status}
          </span>
        </div>
      </td>

      {/* STRATEGY - Position Health */}
      <td className="py-3 px-3">
        {isFreeRideEligible ? (
          <div>
            <div className="text-[10px] text-amber-400 font-bold uppercase">FREE RIDE</div>
            <div className="text-[9px] text-amber-300/70">
              Sell {sharesToSellForFreeRide} shares
            </div>
          </div>
        ) : (
          <div>
            <div className="text-[10px] text-slate-500 uppercase">GROWING</div>
            <div className="w-16 h-1.5 bg-slate-700 rounded-full overflow-hidden mt-1">
              <div 
                className="h-full bg-gradient-to-r from-slate-600 to-emerald-500 transition-all"
                style={{ width: `${progressTo150}%` }}
              />
            </div>
            <div className="text-[8px] text-slate-600 mt-0.5">
              {position.unrealized_pl_percent.toFixed(0)}% / 150%
            </div>
          </div>
        )}
      </td>

      {/* P/L % */}
      <td className="py-3 px-4 text-right">
        <div className={`font-bold ${plColor}`}>
          {formatPercent(position.unrealized_pl_percent)}
        </div>
        <div className="text-xs text-slate-500">
          {formatCurrency(position.unrealized_pl, position.currency || 'USD')}
        </div>
      </td>
    </tr>
  );
};

// ============================================================================
// STOCK DETAIL MODAL
// ============================================================================

interface StockDetailModalProps {
  position: EnrichedPosition;
  familyGaps: FamilyAuditResponse | null;
  onClose: () => void;
  onUpdate: () => void;  // Callback to refresh data after update
}

const StockDetailModal: React.FC<StockDetailModalProps> = ({ position, familyGaps, onClose, onUpdate }) => {
  const stock = position.stock;
  const [showUpdateForm, setShowUpdateForm] = useState(false);
  const [updateText, setUpdateText] = useState('');
  const [sourceType, setSourceType] = useState<'earnings' | 'news' | 'chat' | 'transcript' | 'manual'>('manual');
  const [isUpdating, setIsUpdating] = useState(false);
  const [updateResult, setUpdateResult] = useState<{ success: boolean; message: string } | null>(null);
  
  // Position editing state
  const [isEditingPosition, setIsEditingPosition] = useState(false);
  const [editShares, setEditShares] = useState(position.shares_count.toString());
  const [editAvgCost, setEditAvgCost] = useState(position.avg_cost.toString());
  const [editCurrentPrice, setEditCurrentPrice] = useState((stock?.current_price ?? position.current_price ?? 0).toString());
  const [editCompanyName, setEditCompanyName] = useState(position.company_name || stock?.company_name || '');
  const [editTicker, setEditTicker] = useState(position.ticker);
  const [editCurrency, setEditCurrency] = useState(position.currency || 'USD');
  const [isSavingPosition, setIsSavingPosition] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  
  // Available currencies
  const CURRENCIES = ['USD', 'EUR', 'CZK', 'CAD', 'GBP', 'HKD', 'CHF'];
  
  // Legacy price editing state (for inline price edit)
  const [isEditingPrice, setIsEditingPrice] = useState(false);
  const [editPrice, setEditPrice] = useState('');
  const [isSavingPrice, setIsSavingPrice] = useState(false);
  
  // Price targets (mock calculation - should come from Deep DD)
  const currentPrice = stock?.current_price ?? position.current_price ?? 0;
  const greenLine = stock?.green_line ?? currentPrice * 0.7;
  const redLine = stock?.red_line ?? currentPrice * 1.5;
  const moonTarget = redLine * 1.5;
  
  // Calculate price position percentage
  const priceRange = moonTarget - greenLine;
  const pricePosition = priceRange > 0 ? ((currentPrice - greenLine) / priceRange) * 100 : 50;
  
  // Check if this stock has family gap
  const familyGap = familyGaps?.gaps.find(g => g.ticker === position.ticker);
  
  // Market cap warning (mock - should be from stock data)
  const isLargeCap = false; // TODO: Get from actual market cap data
  
  // Handle stock update
  const handleUpdate = async () => {
    if (!updateText.trim() || updateText.length < 50) {
      setUpdateResult({ success: false, message: 'Text must be at least 50 characters.' });
      return;
    }
    
    setIsUpdating(true);
    setUpdateResult(null);
    
    try {
      const result = await apiClient.updateStockAnalysis(position.ticker, updateText, sourceType);
      
      if (result.success) {
        const driftLabel = result.thesis_drift === 'IMPROVED' ? '[UP]' : 
                          result.thesis_drift === 'DETERIORATED' ? '[DOWN]' : '[STABLE]';
        setUpdateResult({ 
          success: true, 
          message: `${driftLabel} Updated! Score: ${result.previous_score || '?'} → ${result.new_score}/10` 
        });
        // Refresh parent data
        setTimeout(() => {
          onUpdate();
          setShowUpdateForm(false);
          setUpdateText('');
        }, 2000);
      }
    } catch {
      setUpdateResult({ success: false, message: 'Update failed. Please try again.' });
    } finally {
      setIsUpdating(false);
    }
  };
  
  // Handle position update (shares, avg_cost, current_price, company_name, ticker, currency)
  const handleSavePosition = async () => {
    setIsSavingPosition(true);
    setSaveError(null);
    
    try {
      const shares = parseFloat(editShares);
      const avgCost = parseFloat(editAvgCost);
      const price = parseFloat(editCurrentPrice);
      
      if (isNaN(shares) || shares <= 0) {
        setSaveError('Shares must be a positive number');
        return;
      }
      if (isNaN(avgCost) || avgCost < 0) {
        setSaveError('Average cost must be a non-negative number');
        return;
      }
      if (isNaN(price) || price <= 0) {
        setSaveError('Current price must be a positive number');
        return;
      }
      
      await apiClient.updatePosition(position.id, {
        shares_count: shares,
        avg_cost: avgCost,
        current_price: price,
        company_name: editCompanyName.trim() || undefined,
        ticker: editTicker.trim() !== position.ticker ? editTicker.trim() : undefined,
        currency: editCurrency,
      });
      
      // Also update the stock price if it changed
      if (price !== currentPrice) {
        await apiClient.updateStockPrice(position.ticker, price);
      }
      
      setIsEditingPosition(false);
      onUpdate();
    } catch (err) {
      console.error('Failed to save position:', err);
      setSaveError('Failed to save changes. Please try again.');
    } finally {
      setIsSavingPosition(false);
    }
  };
  
  return (
    <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-slate-900 border border-slate-700 rounded-2xl w-full max-w-5xl max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="sticky top-0 bg-slate-900 border-b border-slate-700 p-4 flex items-center justify-between z-10">
          <div className="flex items-center gap-4">
            <div className={`w-14 h-14 rounded-xl flex items-center justify-center font-black text-2xl
              ${position.gomes_score && position.gomes_score >= 7 ? 'bg-green-500/20 text-green-400' :
                position.gomes_score && position.gomes_score >= 5 ? 'bg-yellow-500/20 text-yellow-400' :
                'bg-red-500/20 text-red-400'}`}>
              {position.gomes_score ?? '?'}
            </div>
            <div>
              <h2 className="text-2xl font-black text-white">{position.ticker}</h2>
              <p className="text-slate-400">{stock?.company_name || 'Unknown Company'}</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button 
              onClick={() => setShowUpdateForm(!showUpdateForm)}
              className="px-3 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg text-sm font-medium flex items-center gap-2 transition-colors"
            >
              <RefreshCw className="w-4 h-4" />
              Update Analysis
            </button>
            <button onClick={onClose} className="p-2 hover:bg-slate-800 rounded-lg">
              <X className="w-6 h-6 text-slate-400" />
            </button>
          </div>
        </div>

        {/* Update Form (collapsible) */}
        {showUpdateForm && (
          <div className="p-4 bg-indigo-500/10 border-b border-indigo-500/30">
            <h3 className="text-lg font-bold text-indigo-300 mb-3 flex items-center gap-2">
              <PlusCircle className="w-5 h-5" />
              Add New Intelligence for {position.ticker}
            </h3>
            
            {/* Source Type Selector */}
            <div className="flex gap-2 mb-3">
              {[
                { value: 'earnings', label: 'Earnings Call' },
                { value: 'news', label: 'News/PR' },
                { value: 'transcript', label: 'Video Transcript' },
                { value: 'chat', label: 'Research Note' },
                { value: 'manual', label: 'Manual Entry' },
              ].map((opt) => (
                <button
                  key={opt.value}
                  onClick={() => setSourceType(opt.value as typeof sourceType)}
                  className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                    sourceType === opt.value
                      ? 'bg-indigo-600 text-white'
                      : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                  }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>
            
            <textarea
              value={updateText}
              onChange={(e) => setUpdateText(e.target.value)}
              placeholder={
                sourceType === 'earnings' 
                  ? 'Paste earnings call summary, key metrics, guidance updates...' 
                  : sourceType === 'news' 
                  ? 'Paste news article, press release content...'
                  : sourceType === 'transcript'
                  ? 'Paste video transcript or interview notes...'
                  : sourceType === 'chat'
                  ? 'Paste research notes or analyst commentary...'
                  : 'Enter your analysis notes...'
              }
              rows={6}
              className="w-full px-4 py-3 bg-slate-800 border border-slate-600 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500 resize-none mb-3"
            />
            
            <div className="flex items-center justify-between">
              <div className="text-xs text-slate-500">
                {updateText.length} characters (min. 50)
              </div>
              <div className="flex items-center gap-3">
                {updateResult && (
                  <span className={`text-sm ${updateResult.success ? 'text-green-400' : 'text-red-400'}`}>
                    {updateResult.message}
                  </span>
                )}
                <button
                  onClick={handleUpdate}
                  disabled={isUpdating || updateText.length < 50}
                  className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:bg-slate-600 text-white rounded-lg font-medium flex items-center gap-2 transition-colors"
                >
                  {isUpdating ? (
                    <>
                      <RefreshCw className="w-4 h-4 animate-spin" />
                      Processing...
                    </>
                  ) : (
                    <>
                      <Zap className="w-4 h-4" />
                      Run Analysis
                    </>
                  )}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Warnings - Trend Broken is CRITICAL (Weinstein Rule) */}
        {(position.trend_status === 'BEARISH' || isLargeCap || position.is_deteriorated || familyGap) && (
          <div className="p-4 space-y-2">
            {/* TREND BROKEN - Most Critical Warning */}
            {position.trend_status === 'BEARISH' && (
              <div className="p-4 bg-red-500/20 border-2 border-red-500 rounded-lg flex items-start gap-3 animate-pulse">
                <TrendingDown className="w-6 h-6 text-red-400 flex-shrink-0 mt-0.5" />
                <div>
                  <div className="text-red-400 font-black text-lg">TREND IS BROKEN</div>
                  <div className="text-red-300 text-sm mt-1">
                    Price below 30-week moving average. Re-evaluate fundamentals immediately!
                  </div>
                  <div className="text-red-400/70 text-xs mt-2">
                    Weinstein Rule: Do not add to positions with broken trends regardless of fundamentals.
                  </div>
                </div>
              </div>
            )}
            {isLargeCap && (
              <div className="p-3 bg-amber-500/10 border border-amber-500/50 rounded-lg flex items-center gap-3">
                <AlertTriangle className="w-5 h-5 text-amber-400" />
                <span className="text-amber-300 font-semibold">
                  Large Cap Alert: Limited asymmetric upside potential
                </span>
              </div>
            )}
            {position.is_deteriorated && (
              <div className="p-3 bg-red-500/10 border border-red-500/50 rounded-lg flex items-center gap-3 animate-pulse">
                <AlertCircle className="w-5 h-5 text-red-400" />
                <span className="text-red-300 font-semibold">
                  Position Under Review: Fundamental score below threshold (4/10)
                </span>
              </div>
            )}
            {familyGap && (
              <div className="p-3 bg-purple-500/10 border border-purple-500/50 rounded-lg flex items-center gap-3">
                <Users className="w-5 h-5 text-purple-400" />
                <span className="text-purple-300">
                  Cross-Account: Consider adding to <span className="font-bold">{familyGap.missing_from}</span> for balanced exposure
                </span>
              </div>
            )}
          </div>
        )}

        {/* Three Column Layout */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 p-4">
          {/* LEFT: Holdings Stats */}
          <div className="bg-slate-800/50 rounded-xl p-4 border border-slate-700">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-bold text-slate-400 uppercase tracking-wider flex items-center gap-2">
                <DollarSign className="w-4 h-4" /> Position Details
              </h3>
              {!isEditingPosition ? (
                <button
                  onClick={() => setIsEditingPosition(true)}
                  className="p-1.5 text-slate-400 hover:text-indigo-400 hover:bg-slate-700 rounded-lg transition-colors"
                  title="Edit position"
                >
                  <Edit3 className="w-4 h-4" />
                </button>
              ) : (
                <div className="flex items-center gap-1">
                  <button
                    onClick={handleSavePosition}
                    disabled={isSavingPosition}
                    className="p-1.5 bg-green-500/20 hover:bg-green-500/30 text-green-400 rounded-lg transition-colors disabled:opacity-50"
                    title="Save changes"
                  >
                    {isSavingPosition ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />}
                  </button>
                  <button
                    onClick={() => {
                      setIsEditingPosition(false);
                      setEditShares(position.shares_count.toString());
                      setEditAvgCost(position.avg_cost.toString());
                      setEditCurrentPrice(currentPrice.toString());
                      setEditCompanyName(position.company_name || stock?.company_name || '');
                      setEditTicker(position.ticker);
                      setEditCurrency(position.currency || 'USD');
                      setSaveError(null);
                    }}
                    className="p-1.5 bg-slate-600 hover:bg-slate-500 text-slate-300 rounded-lg transition-colors"
                    title="Cancel"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>
              )}
            </div>
            
            {saveError && (
              <div className="mb-3 p-2 bg-red-500/20 border border-red-500/50 rounded-lg text-red-300 text-sm">
                {saveError}
              </div>
            )}
            
            <div className="space-y-3">
              {/* Ticker (editable) */}
              <div className="flex justify-between items-center">
                <span className="text-slate-400">Ticker</span>
                {isEditingPosition ? (
                  <input
                    type="text"
                    value={editTicker}
                    onChange={(e) => setEditTicker(e.target.value.toUpperCase())}
                    className="w-24 px-2 py-1 bg-slate-700 border border-slate-600 rounded text-white text-right font-mono text-sm focus:outline-none focus:border-indigo-500"
                  />
                ) : (
                  <span className="font-bold text-white">{position.ticker}</span>
                )}
              </div>
              
              {/* Company Name (editable) */}
              <div className="flex justify-between items-center">
                <span className="text-slate-400">Company</span>
                {isEditingPosition ? (
                  <input
                    type="text"
                    value={editCompanyName}
                    onChange={(e) => setEditCompanyName(e.target.value)}
                    className="w-40 px-2 py-1 bg-slate-700 border border-slate-600 rounded text-white text-right text-sm focus:outline-none focus:border-indigo-500"
                    placeholder="Company name"
                  />
                ) : (
                  <span className="text-white text-sm">{position.company_name || stock?.company_name || 'Unknown'}</span>
                )}
              </div>
              
              {/* Shares (editable) */}
              <div className="flex justify-between items-center">
                <span className="text-slate-400">Shares</span>
                {isEditingPosition ? (
                  <input
                    type="number"
                    step="0.01"
                    value={editShares}
                    onChange={(e) => setEditShares(e.target.value)}
                    className="w-24 px-2 py-1 bg-slate-700 border border-slate-600 rounded text-white text-right font-mono text-sm focus:outline-none focus:border-indigo-500"
                  />
                ) : (
                  <span className="font-bold text-white">{position.shares_count.toFixed(2)}</span>
                )}
              </div>
              
              {/* Avg Cost (editable) */}
              <div className="flex justify-between items-center">
                <span className="text-slate-400">Avg. Cost</span>
                {isEditingPosition ? (
                  <div className="flex items-center gap-1">
                    <span className="text-slate-500">$</span>
                    <input
                      type="number"
                      step="0.01"
                      value={editAvgCost}
                      onChange={(e) => setEditAvgCost(e.target.value)}
                      className="w-20 px-2 py-1 bg-slate-700 border border-slate-600 rounded text-white text-right font-mono text-sm focus:outline-none focus:border-indigo-500"
                    />
                  </div>
                ) : (
                  <span className="font-mono text-white">${position.avg_cost.toFixed(2)}</span>
                )}
              </div>
              
              {/* Current Price (editable) */}
              <div className="flex justify-between items-center">
                <span className="text-slate-400">Current Price</span>
                {isEditingPosition ? (
                  <div className="flex items-center gap-1">
                    <span className="text-slate-500">$</span>
                    <input
                      type="number"
                      step="0.01"
                      value={editCurrentPrice}
                      onChange={(e) => setEditCurrentPrice(e.target.value)}
                      className="w-20 px-2 py-1 bg-slate-700 border border-slate-600 rounded text-white text-right font-mono text-sm focus:outline-none focus:border-indigo-500"
                    />
                  </div>
                ) : isEditingPrice ? (
                  <div className="flex items-center gap-2">
                    <input
                      type="number"
                      step="0.01"
                      value={editPrice}
                      onChange={(e) => setEditPrice(e.target.value)}
                      className="w-24 px-2 py-1 bg-slate-700 border border-slate-600 rounded text-white text-right font-mono text-sm focus:outline-none focus:border-indigo-500"
                      placeholder={currentPrice.toFixed(2)}
                      autoFocus
                    />
                    <button
                      onClick={async () => {
                        const price = parseFloat(editPrice);
                        if (isNaN(price) || price <= 0) return;
                        setIsSavingPrice(true);
                        try {
                          await apiClient.updateStockPrice(position.ticker, price);
                          onUpdate();
                          setIsEditingPrice(false);
                        } catch (err) {
                          console.error('Failed to update price:', err);
                        } finally {
                          setIsSavingPrice(false);
                        }
                      }}
                      disabled={isSavingPrice}
                      className="p-1 bg-green-500/20 hover:bg-green-500/30 text-green-400 rounded transition-colors"
                    >
                      <Check className="w-4 h-4" />
                    </button>
                    <button
                      onClick={() => setIsEditingPrice(false)}
                      className="p-1 bg-slate-600 hover:bg-slate-500 text-slate-300 rounded transition-colors"
                    >
                      <X className="w-4 h-4" />
                    </button>
                  </div>
                ) : (
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-white">${currentPrice.toFixed(2)}</span>
                    <button
                      onClick={() => {
                        setEditPrice(currentPrice.toFixed(2));
                        setIsEditingPrice(true);
                      }}
                      className="p-1 text-slate-500 hover:text-indigo-400 transition-colors"
                      title="Update price manually"
                    >
                      <RefreshCw className="w-3 h-3" />
                    </button>
                  </div>
                )}
              </div>
              
              {/* Currency (editable) */}
              <div className="flex justify-between items-center">
                <span className="text-slate-400">Currency</span>
                {isEditingPosition ? (
                  <select
                    value={editCurrency}
                    onChange={(e) => setEditCurrency(e.target.value)}
                    className="w-24 px-2 py-1 bg-slate-700 border border-slate-600 rounded text-white text-right text-sm focus:outline-none focus:border-indigo-500"
                  >
                    {CURRENCIES.map(c => <option key={c} value={c}>{c}</option>)}
                  </select>
                ) : (
                  <span className="font-mono text-white">{position.currency || 'USD'}</span>
                )}
              </div>
              
              <div className="border-t border-slate-600 pt-3 flex justify-between">
                <span className="text-slate-400">Cost Basis</span>
                <span className="font-mono text-slate-300">{formatCurrency(position.cost_basis, position.currency || 'USD')}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Market Value</span>
                <span className="font-mono text-white">{formatCurrency(position.market_value, position.currency || 'USD')}</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-slate-400">Unrealized P/L</span>
                <div className="text-right">
                  <span className={`font-bold ${position.unrealized_pl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                    {formatCurrency(position.unrealized_pl, position.currency || 'USD')}
                  </span>
                  <div className={`text-xs ${position.unrealized_pl_percent >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                    ({formatPercent(position.unrealized_pl_percent)})
                  </div>
                </div>
              </div>
            </div>
            
            {/* Free Ride Alert */}
            {position.unrealized_pl_percent >= 150 && (
              <div className="mt-4 p-3 bg-amber-500/20 border border-amber-500/50 rounded-lg">
                <div className="flex items-center gap-2 text-amber-400 font-bold mb-1">
                  <Zap className="w-4 h-4" />
                  Rule of 150%
                </div>
                <p className="text-amber-200 text-sm mb-2">
                  Gain exceeds 150%. Consider selling half to lock in profits and ride free shares.
                </p>
                <button className="w-full py-2 bg-amber-500/30 hover:bg-amber-500/50 text-amber-300 font-bold rounded-lg transition-colors">
                  Take the Free Ride 🎰
                </button>
              </div>
            )}
          </div>

          {/* MIDDLE: The Thesis */}
          <div className="bg-slate-800/50 rounded-xl p-4 border border-slate-700">
            <h3 className="text-sm font-bold text-slate-400 uppercase tracking-wider mb-4 flex items-center gap-2">
              <Target className="w-4 h-4" /> Investment Thesis
            </h3>
            
            {/* Narrative */}
            <div className="mb-4">
              <div className="text-xs text-slate-500 uppercase mb-1">Latest Analysis</div>
              <p className="text-slate-300 text-sm leading-relaxed">
                {stock?.trade_rationale || stock?.edge || 'No analysis available. Run Deep DD to generate.'}
              </p>
            </div>

            {/* Inflection Point Status */}
            <div className="mb-4 p-3 bg-slate-700/50 rounded-lg">
              <div className="text-xs text-slate-500 uppercase mb-1">Inflection Point</div>
              <div className="flex items-center gap-2">
                <span className={`w-3 h-3 rounded-full ${
                  position.inflection_status === 'ACHIEVED' ? 'bg-green-400' :
                  position.inflection_status === 'UPCOMING' ? 'bg-amber-400 animate-pulse' :
                  'bg-slate-500'
                }`} />
                <span className="font-semibold text-white">
                  {position.inflection_status || 'PENDING'}
                </span>
              </div>
            </div>

            {/* Milestones */}
            <div className="mb-4">
              <div className="text-xs text-slate-500 uppercase mb-2">Key Milestones</div>
              <div className="space-y-2">
                {stock?.catalysts?.split(',').slice(0, 3).map((catalyst, i) => (
                  <div key={i} className="flex items-center gap-2 text-sm">
                    <Check className="w-4 h-4 text-green-400" />
                    <span className="text-slate-300">{catalyst.trim()}</span>
                  </div>
                )) || (
                  <div className="text-slate-500 text-sm">No milestones defined</div>
                )}
              </div>
            </div>

            {/* Catalysts */}
            <div>
              <div className="text-xs text-slate-500 uppercase mb-2">Upcoming Catalysts</div>
              <div className="flex flex-wrap gap-2">
                {stock?.catalysts?.split(',').map((c, i) => (
                  <span key={i} className="px-2 py-1 bg-blue-500/20 text-blue-300 text-xs rounded">
                    {c.trim()}
                  </span>
                )) || (
                  <span className="text-slate-500 text-sm">None identified</span>
                )}
              </div>
            </div>
          </div>

          {/* RIGHT: Valuation & Exit */}
          <div className="bg-slate-800/50 rounded-xl p-4 border border-slate-700">
            <h3 className="text-sm font-bold text-slate-400 uppercase tracking-wider mb-4 flex items-center gap-2">
              <BarChart3 className="w-4 h-4" /> Valuation & Exit
            </h3>

            {/* Price Axis Visualization */}
            <div className="mb-6">
              <div className="relative pt-8 pb-4">
                {/* Labels */}
                <div className="absolute top-0 left-0 text-xs text-slate-500">Floor</div>
                <div className="absolute top-0 right-0 text-xs text-slate-500">Moon</div>
                
                {/* The Bar */}
                <div className="h-4 bg-gradient-to-r from-green-500 via-yellow-500 to-red-500 rounded-full relative">
                  {/* Current Price Marker */}
                  <div 
                    className="absolute top-1/2 -translate-y-1/2 w-1 h-8 bg-white rounded shadow-lg shadow-white/50"
                    style={{ left: `${Math.max(0, Math.min(100, pricePosition))}%` }}
                  >
                    <div className="absolute -top-6 left-1/2 -translate-x-1/2 whitespace-nowrap text-xs font-bold text-white bg-slate-900 px-2 py-1 rounded">
                      ${currentPrice.toFixed(2)}
                    </div>
                  </div>
                </div>
                
                {/* Price Labels */}
                <div className="flex justify-between mt-2 text-xs">
                  <span className="text-green-400">${greenLine.toFixed(2)}</span>
                  <span className="text-yellow-400">${redLine.toFixed(2)}</span>
                  <span className="text-red-400">${moonTarget.toFixed(2)}</span>
                </div>
                <div className="flex justify-between text-[10px] text-slate-500">
                  <span>Conservative</span>
                  <span>Base Case</span>
                  <span>Optimistic</span>
                </div>
              </div>
            </div>

            {/* Gomes Gap Analysis Recommendation */}
            <div className="mb-4 p-3 bg-emerald-500/10 border border-emerald-500/30 rounded-lg">
              <div className="text-xs text-slate-500 uppercase mb-2">Gap Analysis - Tento měsíc</div>
              
              {/* Target vs Current Weight */}
              <div className="flex items-center justify-between mb-2">
                <span className="text-slate-400 text-sm">Cílová váha:</span>
                <span className="font-mono text-white">{position.target_weight_pct}%</span>
              </div>
              <div className="flex items-center justify-between mb-2">
                <span className="text-slate-400 text-sm">Aktuální váha:</span>
                <span className={`font-mono ${position.is_underweight ? 'text-amber-400' : position.is_overweight ? 'text-red-400' : 'text-green-400'}`}>
                  {position.weight_in_portfolio.toFixed(1)}%
                </span>
              </div>
              <div className="flex items-center justify-between mb-3 pb-2 border-b border-slate-700">
                <span className="text-slate-400 text-sm">Mezera (Gap):</span>
                <span className={`font-mono font-bold ${position.gap_czk > 0 ? 'text-amber-400' : position.gap_czk < 0 ? 'text-red-400' : 'text-green-400'}`}>
                  {position.gap_czk > 0 ? '+' : ''}{formatCurrency(position.gap_czk)}
                </span>
              </div>
              
              {/* Optimal Size */}
              <div className="flex items-center justify-between">
                <span className="text-slate-300 font-semibold">Doporučený vklad:</span>
                {position.action_signal === 'SELL' ? (
                  <span className="text-xl font-bold text-red-400">PRODAT</span>
                ) : (
                  <span className={`text-xl font-bold ${position.optimal_size > 0 ? 'text-emerald-400' : 'text-slate-500'}`}>
                    {formatCurrency(position.optimal_size)}
                  </span>
                )}
              </div>
              
              {position.action_signal === 'SNIPER' && (
                <div className="mt-2 text-xs text-amber-400 flex items-center gap-1">
                  Sniper příležitost! Vysoké skóre + velká mezera.
                </div>
              )}
              {position.optimal_size === 0 && position.gap_czk > MIN_INVESTMENT_CZK && position.action_signal !== 'SELL' && (
                <div className="mt-2 text-xs text-slate-500">
                  Nízká priorita - tento měsíc mají přednost lepší příležitosti
                </div>
              )}
            </div>

            {/* Action Buttons */}
            <div className="space-y-2">
              <button className="w-full py-2 bg-green-500/20 hover:bg-green-500/30 text-green-400 font-bold rounded-lg transition-colors flex items-center justify-center gap-2">
                <PlusCircle className="w-4 h-4" />
                Add to Position
              </button>
              {position.unrealized_pl_percent >= 100 && (
                <button className="w-full py-2 bg-amber-500/20 hover:bg-amber-500/30 text-amber-400 font-bold rounded-lg transition-colors flex items-center justify-center gap-2">
                  <TrendingUp className="w-4 h-4" />
                  Take Partial Profits (House Money)
                </button>
              )}
              {position.is_deteriorated && (
                <button className="w-full py-2 bg-red-500/20 hover:bg-red-500/30 text-red-400 font-bold rounded-lg transition-colors flex items-center justify-center gap-2">
                  <AlertCircle className="w-4 h-4" />
                  Close Entire Position
                </button>
              )}
            </div>
          </div>
        </div>

        {/* Bottom: Thesis Drift Log */}
        <div className="p-4 border-t border-slate-700">
          <h3 className="text-sm font-bold text-slate-400 uppercase tracking-wider mb-3 flex items-center gap-2">
            <Clock className="w-4 h-4" /> Score History (Thesis Drift)
          </h3>
          <div className="flex gap-4 overflow-x-auto pb-2">
            {/* Mock history - should come from score_history API */}
            {[
              { date: '2026-01-20', score: 8, status: 'IMPROVED' },
              { date: '2026-01-10', score: 7, status: 'STABLE' },
              { date: '2025-12-15', score: 6, status: 'DETERIORATED' },
            ].map((entry, i) => (
              <div key={i} className="flex-shrink-0 p-3 bg-slate-800 rounded-lg border border-slate-700 min-w-[120px]">
                <div className="text-xs text-slate-500">{entry.date}</div>
                <div className={`text-2xl font-black ${
                  entry.score >= 7 ? 'text-green-400' : 
                  entry.score >= 5 ? 'text-yellow-400' : 
                  'text-red-400'
                }`}>
                  {entry.score}/10
                </div>
                <div className={`text-xs ${
                  entry.status === 'IMPROVED' ? 'text-green-400' :
                  entry.status === 'DETERIORATED' ? 'text-red-400' :
                  'text-slate-400'
                }`}>
                  {entry.status}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};

// ============================================================================
// WATCHLIST DETAIL MODAL (for stocks not owned)
// ============================================================================

interface WatchlistDetailModalProps {
  stock: Stock;
  onClose: () => void;
  onUpdate: () => void;
}

const WatchlistDetailModal: React.FC<WatchlistDetailModalProps> = ({ stock, onClose, onUpdate }) => {
  const [showUpdateForm, setShowUpdateForm] = useState(false);
  const [updateText, setUpdateText] = useState('');
  const [sourceType, setSourceType] = useState<'earnings' | 'news' | 'chat' | 'transcript' | 'manual'>('manual');
  const [isUpdating, setIsUpdating] = useState(false);
  const [updateResult, setUpdateResult] = useState<{ success: boolean; message: string } | null>(null);

  const scoreColor = stock.gomes_score 
    ? stock.gomes_score >= 7 ? 'bg-green-500/20 text-green-400' 
      : stock.gomes_score >= 5 ? 'bg-yellow-500/20 text-yellow-400' 
      : 'bg-red-500/20 text-red-400'
    : 'bg-slate-700 text-slate-500';

  const handleUpdate = async () => {
    if (!updateText.trim() || updateText.length < 50) {
      setUpdateResult({ success: false, message: 'Text must be at least 50 characters.' });
      return;
    }
    
    setIsUpdating(true);
    setUpdateResult(null);
    
    try {
      const result = await apiClient.updateStockAnalysis(stock.ticker, updateText, sourceType);
      
      if (result.success) {
        const driftLabel = result.thesis_drift === 'IMPROVED' ? '[UP]' : 
                          result.thesis_drift === 'DETERIORATED' ? '[DOWN]' : '[STABLE]';
        setUpdateResult({ 
          success: true, 
          message: `${driftLabel} Updated! Score: ${result.previous_score || '?'} → ${result.new_score}/10` 
        });
        setTimeout(() => {
          onUpdate();
          setShowUpdateForm(false);
          setUpdateText('');
        }, 2000);
      }
    } catch {
      setUpdateResult({ success: false, message: 'Update failed. Please try again.' });
    } finally {
      setIsUpdating(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-slate-900 border border-purple-700/50 rounded-2xl w-full max-w-3xl max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="sticky top-0 bg-slate-900 border-b border-purple-700/50 p-4 flex items-center justify-between z-10">
          <div className="flex items-center gap-4">
            <div className={`w-14 h-14 rounded-xl flex items-center justify-center font-black text-2xl ${scoreColor}`}>
              {stock.gomes_score ?? '?'}
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-2xl font-black text-white">{stock.ticker}</h2>
                <span className="px-2 py-0.5 bg-purple-500/20 text-purple-400 text-xs font-bold rounded">
                  WATCHLIST
                </span>
              </div>
              <p className="text-slate-400">{stock.company_name || 'Unknown Company'}</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button 
              onClick={() => setShowUpdateForm(!showUpdateForm)}
              className="px-3 py-2 bg-purple-600 hover:bg-purple-500 text-white rounded-lg text-sm font-medium flex items-center gap-2 transition-colors"
            >
              <RefreshCw className="w-4 h-4" />
              Update Analysis
            </button>
            <button onClick={onClose} className="p-2 hover:bg-slate-800 rounded-lg">
              <X className="w-6 h-6 text-slate-400" />
            </button>
          </div>
        </div>

        {/* Update Form */}
        {showUpdateForm && (
          <div className="p-4 bg-purple-500/10 border-b border-purple-500/30">
            <h3 className="text-lg font-bold text-purple-300 mb-3 flex items-center gap-2">
              <PlusCircle className="w-5 h-5" />
              Add New Intelligence for {stock.ticker}
            </h3>
            
            <div className="flex gap-2 mb-3">
              {[
                { value: 'earnings', label: 'Earnings Call' },
                { value: 'news', label: 'News/PR' },
                { value: 'transcript', label: 'Video Transcript' },
                { value: 'chat', label: 'Research Note' },
                { value: 'manual', label: 'Manual Entry' },
              ].map((opt) => (
                <button
                  key={opt.value}
                  onClick={() => setSourceType(opt.value as typeof sourceType)}
                  className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                    sourceType === opt.value
                      ? 'bg-purple-600 text-white'
                      : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                  }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>
            
            <textarea
              value={updateText}
              onChange={(e) => setUpdateText(e.target.value)}
              placeholder="Paste new information about this stock..."
              rows={4}
              className="w-full px-4 py-3 bg-slate-800 border border-slate-600 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:border-purple-500 resize-none mb-3"
            />
            
            <div className="flex items-center justify-between">
              <div className="text-xs text-slate-500">{updateText.length} characters (min. 50)</div>
              <div className="flex items-center gap-3">
                {updateResult && (
                  <span className={`text-sm ${updateResult.success ? 'text-green-400' : 'text-red-400'}`}>
                    {updateResult.message}
                  </span>
                )}
                <button
                  onClick={handleUpdate}
                  disabled={isUpdating || updateText.length < 50}
                  className="px-4 py-2 bg-purple-600 hover:bg-purple-500 disabled:bg-slate-600 text-white rounded-lg font-medium flex items-center gap-2 transition-colors"
                >
                  {isUpdating ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Zap className="w-4 h-4" />}
                  {isUpdating ? 'Processing...' : 'Run Analysis'}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Content */}
        <div className="p-4 grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Left: Analysis */}
          <div className="bg-slate-800/50 rounded-xl p-4 border border-slate-700">
            <h3 className="text-sm font-bold text-slate-400 uppercase tracking-wider mb-4">Investment Thesis</h3>
            
            <div className="space-y-4">
              <div>
                <div className="text-xs text-slate-500 uppercase mb-1">Trade Rationale</div>
                <p className="text-slate-300 text-sm">
                  {stock.trade_rationale || stock.edge || 'No analysis available.'}
                </p>
              </div>
              
              <div>
                <div className="text-xs text-slate-500 uppercase mb-1">Catalysts</div>
                <p className="text-slate-300 text-sm">
                  {stock.catalysts || 'No catalysts identified.'}
                </p>
              </div>
              
              <div>
                <div className="text-xs text-slate-500 uppercase mb-1">Risks</div>
                <p className="text-red-300 text-sm">
                  {stock.risks || 'No risks documented.'}
                </p>
              </div>
            </div>
          </div>

          {/* Right: Valuation */}
          <div className="bg-slate-800/50 rounded-xl p-4 border border-slate-700">
            <h3 className="text-sm font-bold text-slate-400 uppercase tracking-wider mb-4">Valuation & Targets</h3>
            
            <div className="space-y-3">
              <div className="flex justify-between">
                <span className="text-slate-400">Verdict</span>
                <span className={`font-bold px-2 py-0.5 rounded text-sm ${
                  stock.action_verdict === 'BUY_NOW' ? 'bg-green-500/20 text-green-400' :
                  stock.action_verdict === 'ACCUMULATE' ? 'bg-emerald-500/20 text-emerald-400' :
                  stock.action_verdict === 'WATCH_LIST' ? 'bg-blue-500/20 text-blue-400' :
                  'bg-slate-700 text-slate-400'
                }`}>
                  {stock.action_verdict || 'N/A'}
                </span>
              </div>
              
              <div className="flex justify-between">
                <span className="text-slate-400">Current Price</span>
                <span className="font-mono text-white">${stock.current_price?.toFixed(2) || 'N/A'}</span>
              </div>
              
              <div className="flex justify-between">
                <span className="text-slate-400">Entry Zone (Green)</span>
                <span className="font-mono text-green-400">${stock.green_line?.toFixed(2) || 'N/A'}</span>
              </div>
              
              <div className="flex justify-between">
                <span className="text-slate-400">Target (Red)</span>
                <span className="font-mono text-red-400">${stock.red_line?.toFixed(2) || 'N/A'}</span>
              </div>
              
              <div className="flex justify-between">
                <span className="text-slate-400">Price Zone</span>
                <span className={`font-bold px-2 py-0.5 rounded text-sm ${
                  stock.price_zone === 'DEEP_VALUE' ? 'bg-green-500/20 text-green-400' :
                  stock.price_zone === 'BUY_ZONE' ? 'bg-emerald-500/20 text-emerald-400' :
                  stock.price_zone === 'ACCUMULATE' ? 'bg-blue-500/20 text-blue-400' :
                  stock.price_zone === 'FAIR_VALUE' ? 'bg-yellow-500/20 text-yellow-400' :
                  'bg-slate-700 text-slate-400'
                }`}>
                  {stock.price_zone || 'N/A'}
                </span>
              </div>
              
              {stock.price_target && (
                <div className="flex justify-between">
                  <span className="text-slate-400">Price Target</span>
                  <span className="font-mono text-white">{stock.price_target}</span>
                </div>
              )}
              
              {stock.moat_rating && (
                <div className="flex justify-between">
                  <span className="text-slate-400">Moat Rating</span>
                  <span className="font-bold text-amber-400">{stock.moat_rating}/5</span>
                </div>
              )}
            </div>
            
            {/* Buy Signal */}
            {stock.gomes_score && stock.gomes_score >= 7 && stock.price_zone && ['DEEP_VALUE', 'BUY_ZONE', 'ACCUMULATE'].includes(stock.price_zone) && (
              <div className="mt-4 p-3 bg-green-500/20 border border-green-500/50 rounded-lg">
                <div className="flex items-center gap-2 text-green-400 font-bold">
                  <Target className="w-4 h-4" />
                  Strong Buy Signal
                </div>
                <p className="text-green-200 text-sm mt-1">
                  High score ({stock.gomes_score}/10) + undervalued zone. Consider initiating position.
                </p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

// ============================================================================
// IMPORT CSV MODAL
// ============================================================================

interface ImportCSVModalProps {
  onClose: () => void;
  onSuccess: () => void;
  portfolios: PortfolioSummary[];
}

const ImportCSVModal: React.FC<ImportCSVModalProps> = ({ onClose, onSuccess, portfolios }) => {
  const [selectedPortfolioId, setSelectedPortfolioId] = useState<number | null>(
    portfolios.length > 0 ? portfolios[0].portfolio.id : null
  );
  const [broker, setBroker] = useState<BrokerType>('DEGIRO');
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [showNewPortfolio, setShowNewPortfolio] = useState(portfolios.length === 0);
  const [newPortfolioName, setNewPortfolioName] = useState('');
  const [newPortfolioOwner, setNewPortfolioOwner] = useState('');
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setFile(e.target.files[0]);
      setError(null);
    }
  };

  const handleCreatePortfolio = async () => {
    if (!newPortfolioName.trim()) {
      setError('Portfolio name is required');
      return;
    }
    
    setLoading(true);
    try {
      const portfolio = await apiClient.createPortfolio(
        newPortfolioName,
        newPortfolioOwner || 'Me',
        broker
      );
      setSelectedPortfolioId(portfolio.id);
      setShowNewPortfolio(false);
      
      // If file is already selected, upload it immediately
      if (file) {
        setSuccess(`Portfolio "${portfolio.name}" created! Uploading CSV...`);
        try {
          const result = await apiClient.uploadCSV(portfolio.id, broker, file);
          setSuccess(`Imported ${result.positions_created} positions successfully!`);
          onSuccess();
          setTimeout(() => onClose(), 1500);
        } catch (uploadErr) {
          setError('Portfolio created, but CSV upload failed. Try importing again.');
          onSuccess(); // Still refresh to show new portfolio
        }
      } else {
        setSuccess(`Portfolio "${portfolio.name}" created! Now select a CSV file.`);
        onSuccess();
      }
    } catch (err) {
      setError('Failed to create portfolio');
    } finally {
      setLoading(false);
    }
  };

  const handleUpload = async () => {
    if (!file) {
      setError('Please select a CSV file');
      return;
    }
    if (!selectedPortfolioId) {
      setError('Please select or create a portfolio first');
      return;
    }

    setLoading(true);
    setError(null);
    
    try {
      const result = await apiClient.uploadCSV(selectedPortfolioId, broker, file);
      
      if (result.success) {
        setSuccess(`Imported ${result.positions_created} new, updated ${result.positions_updated} positions`);
        setTimeout(() => {
          onSuccess();
          onClose();
        }, 1500);
      } else {
        setError(result.message || 'Import failed');
      }
    } catch (err) {
      setError('Upload failed. Check file format.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-slate-900 border border-emerald-700/50 rounded-2xl w-full max-w-lg">
        <div className="p-4 border-b border-slate-700 flex items-center justify-between">
          <h2 className="text-xl font-bold text-white flex items-center gap-2">
            <FileSpreadsheet className="w-5 h-5 text-emerald-400" />
            Import Portfolio CSV
          </h2>
          <button onClick={onClose} className="p-2 hover:bg-slate-800 rounded-lg">
            <X className="w-5 h-5 text-slate-400" />
          </button>
        </div>
        
        <div className="p-4 space-y-4">
          {/* Broker Selection */}
          <div>
            <label className="text-sm text-slate-400 block mb-2">Broker</label>
            <div className="flex gap-2">
              {[
                { value: 'DEGIRO', label: 'DEGIRO' },
                { value: 'T212', label: 'Trading 212' },
                { value: 'XTB', label: 'XTB' },
              ].map((b) => (
                <button
                  key={b.value}
                  onClick={() => setBroker(b.value as BrokerType)}
                  className={`px-4 py-2 rounded-lg font-medium transition-colors ${
                    broker === b.value
                      ? 'bg-emerald-600 text-white'
                      : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                  }`}
                >
                  {b.label}
                </button>
              ))}
            </div>
          </div>

          {/* Portfolio Selection */}
          {!showNewPortfolio && portfolios.length > 0 ? (
            <div>
              <label className="text-sm text-slate-400 block mb-2">Target Portfolio</label>
              <div className="flex gap-2">
                <select
                  value={selectedPortfolioId || ''}
                  onChange={(e) => setSelectedPortfolioId(Number(e.target.value))}
                  className="flex-1 px-4 py-2 bg-slate-800 border border-slate-600 rounded-lg text-white focus:outline-none focus:border-emerald-500"
                >
                  {portfolios.map((p) => (
                    <option key={p.portfolio.id} value={p.portfolio.id}>
                      {p.portfolio.name} ({p.portfolio.owner})
                    </option>
                  ))}
                </select>
                <button
                  onClick={() => setShowNewPortfolio(true)}
                  className="px-3 py-2 bg-slate-700 hover:bg-slate-600 rounded-lg text-slate-300"
                >
                  <Plus className="w-5 h-5" />
                </button>
              </div>
            </div>
          ) : (
            <div className="space-y-3 p-3 bg-slate-800/50 rounded-lg border border-slate-700">
              <div className="text-sm text-slate-300 font-medium">Create New Portfolio</div>
              <input
                type="text"
                value={newPortfolioName}
                onChange={(e) => setNewPortfolioName(e.target.value)}
                placeholder="Portfolio name (e.g., Main, Wife, Kids)"
                className="w-full px-4 py-2 bg-slate-800 border border-slate-600 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:border-emerald-500"
              />
              <input
                type="text"
                value={newPortfolioOwner}
                onChange={(e) => setNewPortfolioOwner(e.target.value)}
                placeholder="Owner name (optional)"
                className="w-full px-4 py-2 bg-slate-800 border border-slate-600 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:border-emerald-500"
              />
              <div className="flex gap-2">
                <button
                  onClick={handleCreatePortfolio}
                  disabled={loading || !newPortfolioName.trim()}
                  className="flex-1 px-4 py-2 bg-emerald-600 hover:bg-emerald-500 disabled:bg-slate-600 text-white rounded-lg font-medium"
                >
                  Create Portfolio
                </button>
                {portfolios.length > 0 && (
                  <button
                    onClick={() => setShowNewPortfolio(false)}
                    className="px-4 py-2 bg-slate-700 text-slate-300 rounded-lg"
                  >
                    Cancel
                  </button>
                )}
              </div>
            </div>
          )}

          {/* File Upload */}
          <div>
            <label className="text-sm text-slate-400 block mb-2">CSV File</label>
            <div
              onClick={() => fileInputRef.current?.click()}
              className={`border-2 border-dashed rounded-lg p-6 text-center cursor-pointer transition-colors ${
                file 
                  ? 'border-emerald-500 bg-emerald-500/10' 
                  : 'border-slate-600 hover:border-slate-500 bg-slate-800/50'
              }`}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept=".csv"
                onChange={handleFileChange}
                className="hidden"
              />
              {file ? (
                <div className="flex items-center justify-center gap-2 text-emerald-400">
                  <FileSpreadsheet className="w-6 h-6" />
                  <span className="font-medium">{file.name}</span>
                </div>
              ) : (
                <div className="text-slate-400">
                  <Upload className="w-8 h-8 mx-auto mb-2" />
                  <p>Click to select CSV file</p>
                  <p className="text-xs text-slate-500 mt-1">
                    Export from {broker === 'DEGIRO' ? 'DEGIRO' : broker === 'T212' ? 'Trading 212' : 'XTB'}
                  </p>
                </div>
              )}
            </div>
          </div>

          {/* Error/Success Messages */}
          {error && (
            <div className="p-3 bg-red-500/10 border border-red-500/50 rounded-lg text-red-400 text-sm">
              {error}
            </div>
          )}
          {success && (
            <div className="p-3 bg-emerald-500/10 border border-emerald-500/50 rounded-lg text-emerald-400 text-sm">
              {success}
            </div>
          )}
        </div>

        <div className="p-4 border-t border-slate-700 flex gap-3 justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 text-slate-400 hover:text-white transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleUpload}
            disabled={!file || !selectedPortfolioId || loading}
            className="px-6 py-2 bg-emerald-600 hover:bg-emerald-500 disabled:bg-slate-600 text-white font-bold rounded-lg transition-colors flex items-center gap-2"
          >
            {loading ? (
              <RefreshCw className="w-4 h-4 animate-spin" />
            ) : (
              <Upload className="w-4 h-4" />
            )}
            Import
          </button>
        </div>
      </div>
    </div>
  );
};

// ============================================================================
// ADD POSITION MODAL (Manual Entry)
// ============================================================================

interface AddPositionModalProps {
  onClose: () => void;
  onSuccess: () => void;
  portfolios: PortfolioSummary[];
}

const AddPositionModal: React.FC<AddPositionModalProps> = ({ onClose, onSuccess, portfolios }) => {
  const [selectedPortfolioId, setSelectedPortfolioId] = useState<number | null>(
    portfolios.length > 0 ? portfolios[0].portfolio.id : null
  );
  const [ticker, setTicker] = useState('');
  const [shares, setShares] = useState('');
  const [avgCost, setAvgCost] = useState('');
  const [currentPrice, setCurrentPrice] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const handleSubmit = async () => {
    if (!ticker.trim() || !shares || !avgCost) {
      setError('Ticker, shares, and average cost are required');
      return;
    }
    if (!selectedPortfolioId) {
      setError('Please select a portfolio or import CSV first');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      // Use the positions API to add position
      await apiClient.addPosition(selectedPortfolioId, {
        ticker: ticker.toUpperCase(),
        shares_count: parseFloat(shares),
        avg_cost: parseFloat(avgCost),
        current_price: currentPrice ? parseFloat(currentPrice) : parseFloat(avgCost),
      });
      
      setSuccess(`Position ${ticker.toUpperCase()} added!`);
      setTimeout(() => {
        onSuccess();
        onClose();
      }, 1000);
    } catch (err) {
      setError('Failed to add position');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-slate-900 border border-slate-700 rounded-2xl w-full max-w-md">
        <div className="p-4 border-b border-slate-700 flex items-center justify-between">
          <h2 className="text-xl font-bold text-white flex items-center gap-2">
            <Plus className="w-5 h-5 text-indigo-400" />
            Add Position Manually
          </h2>
          <button onClick={onClose} className="p-2 hover:bg-slate-800 rounded-lg">
            <X className="w-5 h-5 text-slate-400" />
          </button>
        </div>
        
        <div className="p-4 space-y-4">
          {portfolios.length === 0 ? (
            <div className="p-4 bg-amber-500/10 border border-amber-500/50 rounded-lg text-amber-300 text-sm">
              <AlertTriangle className="w-5 h-5 inline mr-2" />
              No portfolios yet. Import a CSV first to create a portfolio.
            </div>
          ) : (
            <>
              {/* Portfolio Selection */}
              <div>
                <label className="text-sm text-slate-400 block mb-2">Portfolio</label>
                <select
                  value={selectedPortfolioId || ''}
                  onChange={(e) => setSelectedPortfolioId(Number(e.target.value))}
                  className="w-full px-4 py-2 bg-slate-800 border border-slate-600 rounded-lg text-white focus:outline-none focus:border-indigo-500"
                >
                  {portfolios.map((p) => (
                    <option key={p.portfolio.id} value={p.portfolio.id}>
                      {p.portfolio.name} ({p.portfolio.owner})
                    </option>
                  ))}
                </select>
              </div>

              {/* Ticker */}
              <div>
                <label className="text-sm text-slate-400 block mb-2">Ticker Symbol</label>
                <input
                  type="text"
                  value={ticker}
                  onChange={(e) => setTicker(e.target.value.toUpperCase())}
                  placeholder="e.g., GKPRF"
                  className="w-full px-4 py-2 bg-slate-800 border border-slate-600 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500"
                />
              </div>

              {/* Shares & Cost */}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-sm text-slate-400 block mb-2">Shares</label>
                  <input
                    type="number"
                    step="0.01"
                    value={shares}
                    onChange={(e) => setShares(e.target.value)}
                    placeholder="100"
                    className="w-full px-4 py-2 bg-slate-800 border border-slate-600 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500"
                  />
                </div>
                <div>
                  <label className="text-sm text-slate-400 block mb-2">Avg. Cost ($)</label>
                  <input
                    type="number"
                    step="0.01"
                    value={avgCost}
                    onChange={(e) => setAvgCost(e.target.value)}
                    placeholder="1.50"
                    className="w-full px-4 py-2 bg-slate-800 border border-slate-600 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500"
                  />
                </div>
              </div>

              {/* Current Price (Optional) */}
              <div>
                <label className="text-sm text-slate-400 block mb-2">Current Price (optional)</label>
                <input
                  type="number"
                  step="0.01"
                  value={currentPrice}
                  onChange={(e) => setCurrentPrice(e.target.value)}
                  placeholder="Leave empty to use avg. cost"
                  className="w-full px-4 py-2 bg-slate-800 border border-slate-600 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500"
                />
              </div>
            </>
          )}

          {/* Error/Success Messages */}
          {error && (
            <div className="p-3 bg-red-500/10 border border-red-500/50 rounded-lg text-red-400 text-sm">
              {error}
            </div>
          )}
          {success && (
            <div className="p-3 bg-emerald-500/10 border border-emerald-500/50 rounded-lg text-emerald-400 text-sm">
              {success}
            </div>
          )}
        </div>

        <div className="p-4 border-t border-slate-700 flex gap-3 justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 text-slate-400 hover:text-white transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={loading || portfolios.length === 0}
            className="px-6 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:bg-slate-600 text-white font-bold rounded-lg transition-colors flex items-center gap-2"
          >
            {loading ? (
              <RefreshCw className="w-4 h-4 animate-spin" />
            ) : (
              <Plus className="w-4 h-4" />
            )}
            Add Position
          </button>
        </div>
      </div>
    </div>
  );
};

// ============================================================================
// NEW ANALYSIS MODAL
// ============================================================================

interface NewAnalysisModalProps {
  onClose: () => void;
  onSubmit: (transcript: string, ticker?: string) => void;
}

const NewAnalysisModal: React.FC<NewAnalysisModalProps> = ({ onClose, onSubmit }) => {
  const [transcript, setTranscript] = useState('');
  const [ticker, setTicker] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async () => {
    if (!transcript.trim()) return;
    setLoading(true);
    await onSubmit(transcript, ticker || undefined);
    setLoading(false);
    onClose();
  };

  return (
    <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-slate-900 border border-slate-700 rounded-2xl w-full max-w-2xl">
        <div className="p-4 border-b border-slate-700 flex items-center justify-between">
          <h2 className="text-xl font-bold text-white flex items-center gap-2">
            <Zap className="w-5 h-5 text-amber-400" />
            New Deep Due Diligence
          </h2>
          <button onClick={onClose} className="p-2 hover:bg-slate-800 rounded-lg">
            <X className="w-5 h-5 text-slate-400" />
          </button>
        </div>
        
        <div className="p-4 space-y-4">
          <div>
            <label className="text-sm text-slate-400 block mb-2">Ticker Symbol (optional)</label>
            <input
              type="text"
              value={ticker}
              onChange={(e) => setTicker(e.target.value.toUpperCase())}
              placeholder="e.g. GKPRF"
              className="w-full px-4 py-2 bg-slate-800 border border-slate-600 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500"
            />
          </div>
          
          <div>
            <label className="text-sm text-slate-400 block mb-2">Transcript / Research Notes</label>
            <textarea
              value={transcript}
              onChange={(e) => setTranscript(e.target.value)}
              placeholder="Paste earnings call transcript, YouTube video notes, or research analysis..."
              rows={10}
              className="w-full px-4 py-3 bg-slate-800 border border-slate-600 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500 resize-none"
            />
          </div>
        </div>

        <div className="p-4 border-t border-slate-700 flex gap-3 justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 text-slate-400 hover:text-white transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={!transcript.trim() || loading}
            className="px-6 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:bg-slate-600 text-white font-bold rounded-lg transition-colors flex items-center gap-2"
          >
            {loading ? (
              <RefreshCw className="w-4 h-4 animate-spin" />
            ) : (
              <Target className="w-4 h-4" />
            )}
            Run Analysis
          </button>
        </div>
      </div>
    </div>
  );
};

// ============================================================================
// MAIN DASHBOARD COMPONENT
// ============================================================================

export const GomesGuardianDashboard: React.FC = () => {
  const [loading, setLoading] = useState(true);
  const [portfolios, setPortfolios] = useState<PortfolioSummary[]>([]);
  const [stocks, setStocks] = useState<Stock[]>([]);
  const [exchangeRates, setExchangeRates] = useState<Record<string, number>>({ EUR: 25, USD: 24 });
  const [familyGaps, setFamilyGaps] = useState<FamilyAuditResponse | null>(null);
  const [selectedPosition, setSelectedPosition] = useState<EnrichedPosition | null>(null);
  const [selectedWatchlistStock, setSelectedWatchlistStock] = useState<Stock | null>(null);
  const [showAnalysisModal, setShowAnalysisModal] = useState(false);
  const [showImportModal, setShowImportModal] = useState(false);
  const [showAddPositionModal, setShowAddPositionModal] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [sortBy, setSortBy] = useState<'weight' | 'score' | 'pl'>('score');
  const [activeTab, setActiveTab] = useState<'portfolio' | 'watchlist' | 'freedom'>('portfolio');
  
  // Cash editing state
  const [isEditingCash, setIsEditingCash] = useState(false);
  const [editCashValue, setEditCashValue] = useState('');
  const [editCashCurrency, setEditCashCurrency] = useState('CZK');
  const [isSavingCash, setIsSavingCash] = useState(false);
  
  // Available currencies for cash
  const CASH_CURRENCIES = ['CZK', 'EUR', 'USD', 'CAD', 'GBP'];
  
  // Refresh portfolios helper
  const refreshPortfolios = async () => {
    const portfolioList = await apiClient.getPortfolios();
    const summaries: PortfolioSummary[] = [];
    for (const p of portfolioList) {
      try {
        const summary = await apiClient.getPortfolioSummary(p.id);
        summaries.push(summary);
      } catch { /* skip */ }
    }
    setPortfolios(summaries);
  };

  // Fetch all data
  useEffect(() => {
    const fetchData = async () => {
      setLoading(true);
      try {
        // Fetch exchange rates from CNB
        try {
          const ratesData = await apiClient.getExchangeRates();
          setExchangeRates(ratesData.rates);
        } catch {
          console.warn('Failed to fetch exchange rates, using fallback');
        }
        
        // Fetch portfolios
        const portfolioList = await apiClient.getPortfolios();
        const summaries: PortfolioSummary[] = [];
        
        for (const p of portfolioList) {
          try {
            const summary = await apiClient.getPortfolioSummary(p.id);
            summaries.push(summary);
          } catch {
            // Skip failed portfolio
          }
        }
        setPortfolios(summaries);

        // Fetch stocks for Gomes data
        const stocksData = await apiClient.getStocks();
        setStocks(stocksData.stocks);

        // Fetch family gaps
        try {
          const gaps = await apiClient.getFamilyAudit();
          setFamilyGaps(gaps);
        } catch {
          // No family audit available
        }
      } catch (err) {
        console.error('Failed to fetch data:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, []);

  // Calculate family portfolio data
  const familyData: FamilyPortfolioData = useMemo(() => {
    let totalValue = 0;
    let totalCash = 0;
    const allPositions: EnrichedPosition[] = [];
    let rocketCount = 0;      // Score >= 7 (Growth)
    let anchorCount = 0;      // Score 5-6 (Core)
    let waitTimeCount = 0;    // Score 1-4 (Wait Time/Avoid)
    let unanalyzedCount = 0;  // No score yet (needs Deep DD)

    // First pass: calculate total value
    for (const portfolio of portfolios) {
      totalValue += portfolio.total_market_value || 0;
      totalCash += portfolio.cash_balance || 0;
    }
    
    // Include cash in total
    const grandTotal = totalValue + totalCash;
    
    // EUR equivalent using live CNB rates
    const eurRate = exchangeRates.EUR || 25;
    const totalValueEUR = grandTotal / eurRate;

    // ========================================================================
    // GOMES GAP ANALYSIS - Výpočet mezer a optimal size
    // ========================================================================
    
    // Temporary array to collect positions before priority sorting
    const tempPositions: EnrichedPosition[] = [];
    
    for (const portfolio of portfolios) {
      for (const pos of portfolio.positions) {
        // Find matching stock from Gomes analysis (may not exist)
        const stock = stocks.find(s => s.ticker.toUpperCase() === pos.ticker.toUpperCase());
        const gomesScore = stock?.gomes_score ?? null;
        
        // 1. Cílová váha podle skóre (Target Weight)
        const targetWeightPct = getTargetWeight(gomesScore);
        
        // 2. Aktuální váha v portfoliu
        const positionValueOriginal = pos.market_value > 0 ? pos.market_value : pos.cost_basis;
        const positionCurrency = pos.currency || 'CZK';
        const currencyRate = exchangeRates[positionCurrency] || 1;
        const positionValueCZK = positionValueOriginal * currencyRate;
        const currentWeightPct = grandTotal > 0 ? (positionValueCZK / grandTotal) * 100 : 0;
        
        // 3. GAP ANALYSIS - Kolik CZK chybí/přebývá
        // Gap = (Total_AUM * Target_Weight) - Current_Value
        const targetValueCZK = (grandTotal * targetWeightPct) / 100;
        const gapCZK = targetValueCZK - positionValueCZK;
        
        // 4. Action signal based on score and gap
        const actionSignal = getActionSignal(gomesScore, currentWeightPct, targetWeightPct);
        
        // 5. Classify for risk meter
        if (gomesScore !== null && gomesScore >= 9) {
          rocketCount++;
        } else if (gomesScore !== null && gomesScore >= 7) {
          anchorCount++;
        } else if (gomesScore !== null && gomesScore >= 5) {
          waitTimeCount++;
        } else if (gomesScore !== null) {
          waitTimeCount++; // 1-4 = sell candidates
        } else {
          unanalyzedCount++;
        }

        const enriched: EnrichedPosition = {
          ...pos,
          stock,
          gomes_score: gomesScore,
          target_weight_pct: targetWeightPct,
          weight_in_portfolio: currentWeightPct,
          gap_czk: gapCZK,
          optimal_size: 0, // Will be calculated after sorting
          allocation_priority: 999, // Will be set after sorting
          trend_status: getTrendStatus(stock),
          is_deteriorated: gomesScore !== null && gomesScore < 4,
          is_overweight: currentWeightPct > MAX_POSITION_WEIGHT,
          is_underweight: gapCZK > MIN_INVESTMENT_CZK,
          action_signal: actionSignal,
          inflection_status: 'UPCOMING',
          next_catalyst: stock?.next_catalyst ?? undefined,
        };

        tempPositions.push(enriched);
      }
    }
    
    // ========================================================================
    // PRIORITIZACE A DISTRIBUCE MĚSÍČNÍHO VKLADU
    // ========================================================================
    
    // Sort by: 1) Score (highest first), 2) Gap (largest positive first)
    // Only positions with score >= 5 and positive gap get allocation
    const sortedForAllocation = [...tempPositions]
      .filter(p => p.gomes_score !== null && p.gomes_score >= 5 && p.gap_czk > 0)
      .sort((a, b) => {
        // Primary: Higher score = higher priority
        const scoreDiff = (b.gomes_score ?? 0) - (a.gomes_score ?? 0);
        if (scoreDiff !== 0) return scoreDiff;
        // Secondary: Larger gap = higher priority
        return b.gap_czk - a.gap_czk;
      });
    
    // Distribute monthly contribution according to priority
    let remainingBudget = MONTHLY_CONTRIBUTION;
    
    for (let i = 0; i < sortedForAllocation.length; i++) {
      const pos = sortedForAllocation[i];
      pos.allocation_priority = i + 1;
      
      if (remainingBudget <= 0) {
        pos.optimal_size = 0;
        continue;
      }
      
      // Calculate how much to allocate (min of gap and remaining budget)
      let allocation = Math.min(pos.gap_czk, remainingBudget);
      
      // Apply hard caps
      // 1. Don't exceed MAX_POSITION_WEIGHT (15%)
      const currentValueCZK = (grandTotal * pos.weight_in_portfolio) / 100;
      const maxAllowedValue = (grandTotal * MAX_POSITION_WEIGHT) / 100;
      const maxAllocation = maxAllowedValue - currentValueCZK;
      allocation = Math.min(allocation, Math.max(0, maxAllocation));
      
      // 2. If allocation < MIN_INVESTMENT, skip (not worth the fees)
      if (allocation < MIN_INVESTMENT_CZK) {
        allocation = 0;
      }
      
      pos.optimal_size = Math.round(allocation);
      remainingBudget -= pos.optimal_size;
    }
    
    // Set priority=0 and optimal_size=0 for positions not in allocation list
    // (score < 5 or negative gap or no score)
    for (const pos of tempPositions) {
      if (!sortedForAllocation.includes(pos)) {
        pos.allocation_priority = 0;
        pos.optimal_size = 0;
      }
    }
    
    // Copy to final array
    allPositions.push(...tempPositions);

    // Calculate risk score (only from analyzed positions)
    const analyzedTotal = rocketCount + anchorCount + waitTimeCount;
    const riskScore = analyzedTotal > 0 ? Math.round((rocketCount / analyzedTotal) * 100) : 0;

    return {
      totalValue: grandTotal,
      totalValueEUR,
      totalCash,
      portfolios,
      allPositions,
      rocketCount,
      anchorCount,
      waitTimeCount,
      unanalyzedCount,
      riskScore,
    };
  }, [portfolios, stocks, exchangeRates]);

  // Get tickers that are in portfolio (owned)
  const ownedTickers = useMemo(() => {
    return new Set(familyData.allPositions.map(p => p.ticker.toUpperCase()));
  }, [familyData.allPositions]);

  // Watchlist: stocks with analysis but NOT owned
  const watchlistStocks = useMemo(() => {
    return stocks.filter(s => !ownedTickers.has(s.ticker.toUpperCase()) && s.gomes_score !== null);
  }, [stocks, ownedTickers]);

  // Filter and sort positions
  const displayedPositions = useMemo(() => {
    let filtered = [...familyData.allPositions];

    // Search filter
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      filtered = filtered.filter(p => 
        p.ticker.toLowerCase().includes(q) ||
        p.stock?.company_name?.toLowerCase().includes(q)
      );
    }

    // Sort
    filtered.sort((a, b) => {
      switch (sortBy) {
        case 'weight':
          return b.weight_in_portfolio - a.weight_in_portfolio;
        case 'score':
          return (b.gomes_score ?? 0) - (a.gomes_score ?? 0);
        case 'pl':
          return b.unrealized_pl_percent - a.unrealized_pl_percent;
        default:
          return 0;
      }
    });

    return filtered;
  }, [familyData.allPositions, searchQuery, sortBy]);

  // Filter and sort watchlist
  const displayedWatchlist = useMemo(() => {
    let filtered = [...watchlistStocks];

    // Search filter
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      filtered = filtered.filter(s => 
        s.ticker.toLowerCase().includes(q) ||
        s.company_name?.toLowerCase().includes(q)
      );
    }

    // Sort by score
    filtered.sort((a, b) => (b.gomes_score ?? 0) - (a.gomes_score ?? 0));

    return filtered;
  }, [watchlistStocks, searchQuery]);

  // Handle new analysis
  const handleNewAnalysis = async (transcript: string, ticker?: string) => {
    try {
      await apiClient.runDeepDD(transcript, ticker);
      // Refresh data
      const stocksData = await apiClient.getStocks();
      setStocks(stocksData.stocks);
    } catch (err) {
      console.error('Analysis failed:', err);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-950 flex items-center justify-center">
        <div className="text-center">
          <RefreshCw className="w-12 h-12 text-indigo-400 animate-spin mx-auto mb-4" />
          <p className="text-slate-400">Loading portfolio data...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-950 text-white">
      {/* HEADER */}
      <header className="bg-slate-900/80 backdrop-blur-sm border-b border-slate-800 sticky top-0 z-40">
        <div className="max-w-7xl mx-auto px-4 py-4">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-3">
              <Shield className="w-8 h-8 text-indigo-400" />
              <h1 className="text-2xl font-black tracking-tight">AKCION</h1>
            </div>
            
            {/* Action Buttons */}
            <div className="flex items-center gap-2">
              {/* Import Portfolio */}
              <button
                onClick={() => setShowImportModal(true)}
                className="px-3 py-2 bg-emerald-600 hover:bg-emerald-500 rounded-lg font-bold flex items-center gap-2 transition-colors text-sm"
              >
                <Upload className="w-4 h-4" />
                Import CSV
              </button>
              
              {/* Add Position Manually */}
              <button
                onClick={() => setShowAddPositionModal(true)}
                className="px-3 py-2 bg-slate-700 hover:bg-slate-600 rounded-lg font-bold flex items-center gap-2 transition-colors text-sm"
              >
                <Plus className="w-4 h-4" />
                Add Position
              </button>
              
              {/* New Analysis */}
              <button
                onClick={() => setShowAnalysisModal(true)}
                className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 rounded-lg font-bold flex items-center gap-2 transition-colors"
              >
                <PlusCircle className="w-5 h-5" />
                New Analysis
              </button>
            </div>
          </div>

          {/* Stats Row */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            {/* Total Value with Target Progress */}
            <div className="bg-slate-800/50 rounded-xl p-4 border border-slate-700 text-center">
              <div className="text-xs text-slate-400 uppercase tracking-wider">Total AUM</div>
              <div className="text-2xl font-black text-white mt-1">
                {formatCurrency(familyData.totalValue)}
              </div>
              <div className="text-xs text-slate-500 mt-0.5">
                ≈ €{familyData.totalValueEUR.toLocaleString('cs-CZ', { maximumFractionDigits: 0 })} EUR
              </div>
              {/* Target Progress Bar - Goal: 500,000 CZK */}
              <div className="mt-2">
                <div className="flex justify-between items-center text-[10px] text-slate-500 mb-1">
                  <span>Target: 500k Kč</span>
                  <span className="font-mono">{Math.min(100, (familyData.totalValue / 500000 * 100)).toFixed(0)}%</span>
                </div>
                <div className="h-1.5 bg-slate-700 rounded-full overflow-hidden">
                  <div 
                    className="h-full bg-gradient-to-r from-indigo-500 to-purple-500 transition-all duration-500"
                    style={{ width: `${Math.min(100, familyData.totalValue / 500000 * 100)}%` }}
                  />
                </div>
                {/* Estimated time to target */}
                {(() => {
                  const months = calculateMonthsToTarget(familyData.totalValue, 500000, 20000, 0.15);
                  const years = Math.floor(months / 12);
                  const remainingMonths = months % 12;
                  return months > 0 ? (
                    <div className="text-[10px] text-indigo-400 mt-1 flex items-center justify-center gap-1">
                      <span>
                        {years > 0 ? `${years}y ` : ''}{remainingMonths}m to target
                        {' '}(15% return + 20k/mo)
                      </span>
                    </div>
                  ) : (
                    <div className="text-[10px] text-green-400 mt-1">Target reached!</div>
                  );
                })()}
              </div>
            </div>

            {/* Cash (Munice) - Editable */}
            <div className="bg-slate-800/50 rounded-xl p-4 border border-emerald-500/30 text-center">
              <div className="flex items-center justify-center gap-2">
                <div className="text-xs text-slate-400 uppercase tracking-wider">Available Cash</div>
                {!isEditingCash && (
                  <button
                    onClick={() => {
                      setEditCashValue(familyData.totalCash.toString());
                      setEditCashCurrency('CZK');
                      setIsEditingCash(true);
                    }}
                    className="p-1 text-slate-500 hover:text-emerald-400 transition-colors"
                    title="Edit cash balance"
                  >
                    <Edit3 className="w-3 h-3" />
                  </button>
                )}
              </div>
              {isEditingCash ? (
                <div className="mt-1">
                  <div className="flex items-center gap-2">
                    <input
                      type="number"
                      value={editCashValue}
                      onChange={(e) => setEditCashValue(e.target.value)}
                      className="flex-1 px-2 py-1 bg-slate-700 border border-emerald-500/50 rounded text-white font-mono text-lg focus:outline-none focus:border-emerald-400"
                      placeholder="0"
                      autoFocus
                    />
                    <select
                      value={editCashCurrency}
                      onChange={(e) => setEditCashCurrency(e.target.value)}
                      className="px-2 py-1 bg-slate-700 border border-slate-600 rounded text-white text-sm focus:outline-none focus:border-emerald-400"
                    >
                      {CASH_CURRENCIES.map(c => <option key={c} value={c}>{c}</option>)}
                    </select>
                  </div>
                  <div className="flex gap-2 mt-2">
                    <button
                      onClick={async () => {
                        const amount = parseFloat(editCashValue);
                        if (isNaN(amount) || amount < 0) return;
                        setIsSavingCash(true);
                        try {
                          // Convert to CZK if different currency
                          let amountInCZK = amount;
                          if (editCashCurrency !== 'CZK') {
                            const rate = exchangeRates[editCashCurrency] || 1;
                            amountInCZK = amount * rate;
                          }
                          // Update cash for first portfolio
                          if (portfolios.length > 0) {
                            const portfolioId = portfolios[0].portfolio.id;
                            console.log('Updating cash for portfolio', portfolioId, 'amount:', amountInCZK);
                            await apiClient.updateCashBalance(portfolioId, amountInCZK);
                            await refreshPortfolios();
                          } else {
                            console.error('No portfolios found!');
                          }
                          setIsEditingCash(false);
                        } catch (err) {
                          console.error('Failed to update cash:', err);
                        } finally {
                          setIsSavingCash(false);
                        }
                      }}
                      disabled={isSavingCash}
                      className="flex-1 py-1 bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-400 text-sm font-bold rounded transition-colors flex items-center justify-center gap-1"
                    >
                      {isSavingCash ? <RefreshCw className="w-3 h-3 animate-spin" /> : <Check className="w-3 h-3" />}
                      Save
                    </button>
                    <button
                      onClick={() => setIsEditingCash(false)}
                      className="px-3 py-1 bg-slate-600 hover:bg-slate-500 text-slate-300 text-sm rounded transition-colors"
                    >
                      <X className="w-3 h-3" />
                    </button>
                  </div>
                </div>
              ) : (
                <>
                  <div className="text-2xl font-black text-emerald-400 mt-1">
                    {formatCurrency(familyData.totalCash)}
                  </div>
                  <div className="text-xs text-slate-500 mt-0.5">
                    ≈ €{(familyData.totalCash / (exchangeRates.EUR || 25)).toLocaleString('cs-CZ', { maximumFractionDigits: 0 })} EUR
                  </div>
                  <div className="text-xs text-slate-500 mt-1">
                    {familyData.totalValue > 0 ? ((familyData.totalCash / familyData.totalValue) * 100).toFixed(1) : 0}% of portfolio
                  </div>
                </>
              )}
            </div>

            {/* Position Count */}
            <div className="bg-slate-800/50 rounded-xl p-4 border border-slate-700 text-center">
              <div className="text-xs text-slate-400 uppercase tracking-wider">Positions</div>
              <div className="text-2xl font-black text-white mt-1">
                {familyData.allPositions.length}
              </div>
              <div className="text-xs text-slate-500 mt-1">
                {familyData.allPositions.filter(p => p.is_deteriorated).length} require attention
              </div>
            </div>

            {/* Risk Meter */}
            <RiskMeter 
              rocketCount={familyData.rocketCount}
              anchorCount={familyData.anchorCount}
              waitTimeCount={familyData.waitTimeCount}
              unanalyzedCount={familyData.unanalyzedCount}
              riskScore={familyData.riskScore}
            />
          </div>
        </div>
      </header>

      {/* MAIN CONTENT */}
      <main className="max-w-7xl mx-auto px-4 py-6">
        {/* Tab Navigation */}
        <div className="flex items-center gap-4 mb-6">
          <button
            onClick={() => setActiveTab('portfolio')}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg font-bold transition-colors ${
              activeTab === 'portfolio'
                ? 'bg-indigo-600 text-white'
                : 'bg-slate-800 text-slate-400 hover:bg-slate-700 hover:text-white'
            }`}
          >
            <Briefcase className="w-5 h-5" />
            Portfolio
            <span className="ml-1 px-2 py-0.5 bg-black/20 rounded text-xs">
              {familyData.allPositions.length}
            </span>
          </button>
          <button
            onClick={() => setActiveTab('watchlist')}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg font-bold transition-colors ${
              activeTab === 'watchlist'
                ? 'bg-purple-600 text-white'
                : 'bg-slate-800 text-slate-400 hover:bg-slate-700 hover:text-white'
            }`}
          >
            <Eye className="w-5 h-5" />
            Watchlist
            <span className="ml-1 px-2 py-0.5 bg-black/20 rounded text-xs">
              {watchlistStocks.length}
            </span>
          </button>
          <button
            onClick={() => setActiveTab('freedom')}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg font-bold transition-colors ${
              activeTab === 'freedom'
                ? 'bg-gradient-to-r from-amber-500 to-orange-500 text-white'
                : 'bg-slate-800 text-slate-400 hover:bg-slate-700 hover:text-white'
            }`}
          >
            <Target className="w-5 h-5" />
            Freedom
            <span className="ml-1 text-lg">🏰</span>
          </button>
        </div>

        {/* Toolbar */}
        <div className="flex items-center justify-between mb-4">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
            <input
              type="text"
              placeholder={activeTab === 'portfolio' ? "Search positions..." : "Search watchlist..."}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-10 pr-4 py-2 bg-slate-800 border border-slate-700 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500 w-64"
            />
          </div>
          
          {activeTab === 'portfolio' && (
            <div className="flex items-center gap-2">
              <span className="text-xs text-slate-500">Sort by:</span>
              <select
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value as 'weight' | 'score' | 'pl')}
                className="px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-white text-sm focus:outline-none focus:border-indigo-500"
              >
                <option value="score">Score</option>
                <option value="weight">Weight</option>
                <option value="pl">P/L %</option>
              </select>
            </div>
          )}
        </div>

        {/* Portfolio Summary Stats */}
        {activeTab === 'portfolio' && portfolios.length > 0 && (
          <div className="grid grid-cols-4 gap-4 mb-4">
            {(() => {
              // Calculate totals across all portfolios
              const totals = portfolios.reduce((acc, p) => ({
                costBasis: acc.costBasis + (p.total_cost_basis || 0),
                marketValue: acc.marketValue + (p.total_market_value || 0),
                unrealizedPL: acc.unrealizedPL + (p.total_unrealized_pl || 0),
                cash: acc.cash + (p.cash_balance || 0),
              }), { costBasis: 0, marketValue: 0, unrealizedPL: 0, cash: 0 });
              
              const totalValue = totals.marketValue + totals.cash;
              const plPercent = totals.costBasis > 0 
                ? ((totals.marketValue / totals.costBasis) - 1) * 100 
                : 0;
              
              return (
                <>
                  <div className="bg-slate-800/50 rounded-lg p-4 border border-slate-700">
                    <div className="text-xs text-slate-500 uppercase tracking-wider mb-1">Total Value</div>
                    <div className="text-2xl font-bold text-white">
                      {totalValue.toLocaleString('cs-CZ', { style: 'currency', currency: 'CZK', maximumFractionDigits: 0 })}
                    </div>
                  </div>
                  <div className="bg-slate-800/50 rounded-lg p-4 border border-slate-700">
                    <div className="text-xs text-slate-500 uppercase tracking-wider mb-1">Cost Basis</div>
                    <div className="text-2xl font-bold text-slate-300">
                      {totals.costBasis.toLocaleString('cs-CZ', { style: 'currency', currency: 'CZK', maximumFractionDigits: 0 })}
                    </div>
                  </div>
                  <div className="bg-slate-800/50 rounded-lg p-4 border border-slate-700">
                    <div className="text-xs text-slate-500 uppercase tracking-wider mb-1">Unrealized P/L</div>
                    <div className={`text-2xl font-bold ${totals.unrealizedPL >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                      {totals.unrealizedPL >= 0 ? '+' : ''}{totals.unrealizedPL.toLocaleString('cs-CZ', { style: 'currency', currency: 'CZK', maximumFractionDigits: 0 })}
                      <span className="text-sm ml-2">
                        ({plPercent >= 0 ? '+' : ''}{plPercent.toFixed(2)}%)
                      </span>
                    </div>
                  </div>
                  <div className="bg-slate-800/50 rounded-lg p-4 border border-slate-700">
                    <div className="text-xs text-slate-500 uppercase tracking-wider mb-1">Cash Balance</div>
                    <div className="text-2xl font-bold text-blue-400">
                      {totals.cash.toLocaleString('cs-CZ', { style: 'currency', currency: 'CZK', maximumFractionDigits: 0 })}
                    </div>
                  </div>
                </>
              );
            })()}
          </div>
        )}

        {/* Gomes Allocation Plan - Monthly Summary */}
        {activeTab === 'portfolio' && (
          <div className="mb-4 p-4 bg-gradient-to-r from-emerald-900/30 to-slate-800/50 rounded-xl border border-emerald-500/30">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-emerald-500/20 rounded-lg">
                  <Target className="w-5 h-5 text-emerald-400" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-emerald-300 uppercase tracking-wider">
                    Měsíční alokační plán
                  </h3>
                  <p className="text-xs text-slate-400">
                    Rozpočet: {formatCurrency(MONTHLY_CONTRIBUTION)} | 
                    Alokováno: {formatCurrency(familyData.allPositions.reduce((sum, p) => sum + p.optimal_size, 0))} | 
                    Zbývá: {formatCurrency(MONTHLY_CONTRIBUTION - familyData.allPositions.reduce((sum, p) => sum + p.optimal_size, 0))}
                  </p>
                </div>
              </div>
              
              {/* Top 3 recommendations */}
              <div className="flex items-center gap-2">
                {familyData.allPositions
                  .filter(p => p.optimal_size > 0)
                  .sort((a, b) => a.allocation_priority - b.allocation_priority)
                  .slice(0, 3)
                  .map((pos, i) => (
                    <div 
                      key={pos.ticker}
                      className={`px-3 py-1.5 rounded-lg text-xs font-bold ${
                        i === 0 ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/50' :
                        'bg-slate-700/50 text-slate-300'
                      }`}
                    >
                      {pos.action_signal === 'SNIPER' && '[S] '}
                      {pos.ticker}: {formatCurrency(pos.optimal_size)}
                    </div>
                  ))
                }
                {familyData.allPositions.filter(p => p.action_signal === 'SELL').length > 0 && (
                  <div className="px-3 py-1.5 rounded-lg text-xs font-bold bg-red-500/20 text-red-400 border border-red-500/50">
                    {familyData.allPositions.filter(p => p.action_signal === 'SELL').length}x PRODAT
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Portfolio Table */}
        {activeTab === 'portfolio' && (
        <div className="bg-slate-900/50 rounded-xl border border-slate-800 overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="border-b border-slate-700 bg-slate-800/50">
                <th className="text-left py-3 px-4 text-xs font-bold text-slate-400 uppercase tracking-wider">Symbol</th>
                <th className="text-left py-3 px-3 text-xs font-bold text-slate-400 uppercase tracking-wider">Action</th>
                <th className="text-left py-3 px-4 text-xs font-bold text-slate-400 uppercase tracking-wider">
                  <div>Váha</div>
                  <div className="text-[9px] text-slate-500 font-normal">Aktuální / Cíl</div>
                </th>
                <th className="text-left py-3 px-4 text-xs font-bold text-slate-400 uppercase tracking-wider">Score</th>
                <th className="text-left py-3 px-4 text-xs font-bold text-slate-400 uppercase tracking-wider">
                  <div>Optimal Size</div>
                  <div className="text-[9px] text-slate-500 font-normal">Tento měsíc</div>
                </th>
                <th className="text-left py-3 px-3 text-xs font-bold text-slate-400 uppercase tracking-wider">Catalyst</th>
                <th className="text-left py-3 px-4 text-xs font-bold text-slate-400 uppercase tracking-wider">Trend</th>
                <th className="text-left py-3 px-3 text-xs font-bold text-slate-400 uppercase tracking-wider">Strategy</th>
                <th className="text-right py-3 px-4 text-xs font-bold text-slate-400 uppercase tracking-wider">P/L</th>
              </tr>
            </thead>
            <tbody>
              {displayedPositions.map((pos) => (
                <PortfolioRow
                  key={`${pos.portfolio_id}-${pos.ticker}`}
                  position={pos}
                  onClick={() => setSelectedPosition(pos)}
                />
              ))}
              {displayedPositions.length === 0 && (
                <tr>
                  <td colSpan={9} className="text-center py-12 text-slate-500">
                    {searchQuery ? 'No positions found' : 'No positions in portfolio. Import your DEGIRO CSV to get started.'}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        )}

        {/* Watchlist Table */}
        {activeTab === 'watchlist' && (
          <div className="bg-slate-900/50 rounded-xl border border-purple-800/50 overflow-hidden">
            <table className="w-full">
              <thead>
                <tr className="border-b border-purple-700/50 bg-purple-900/30">
                  <th className="text-left py-3 px-4 text-xs font-bold text-purple-300 uppercase tracking-wider">Symbol</th>
                  <th className="text-left py-3 px-4 text-xs font-bold text-purple-300 uppercase tracking-wider">Company</th>
                  <th className="text-left py-3 px-4 text-xs font-bold text-purple-300 uppercase tracking-wider">Score</th>
                  <th className="text-left py-3 px-4 text-xs font-bold text-purple-300 uppercase tracking-wider">Verdict</th>
                  <th className="text-left py-3 px-4 text-xs font-bold text-purple-300 uppercase tracking-wider">Price Zone</th>
                  <th className="text-right py-3 px-4 text-xs font-bold text-purple-300 uppercase tracking-wider">Action</th>
                </tr>
              </thead>
              <tbody>
                {displayedWatchlist.map((stock) => {
                  const scoreColor = stock.gomes_score 
                    ? stock.gomes_score >= 7 ? 'text-green-400' 
                      : stock.gomes_score >= 5 ? 'text-yellow-400' 
                      : 'text-red-400'
                    : 'text-slate-500';
                  
                  const zoneColor = stock.price_zone === 'DEEP_VALUE' ? 'bg-green-500/20 text-green-400' :
                                    stock.price_zone === 'BUY_ZONE' ? 'bg-emerald-500/20 text-emerald-400' :
                                    stock.price_zone === 'ACCUMULATE' ? 'bg-blue-500/20 text-blue-400' :
                                    stock.price_zone === 'FAIR_VALUE' ? 'bg-yellow-500/20 text-yellow-400' :
                                    stock.price_zone === 'SELL_ZONE' ? 'bg-orange-500/20 text-orange-400' :
                                    stock.price_zone === 'OVERVALUED' ? 'bg-red-500/20 text-red-400' :
                                    'bg-slate-700 text-slate-400';

                  return (
                    <tr 
                      key={stock.id}
                      onClick={() => setSelectedWatchlistStock(stock)}
                      className="border-b border-slate-700/50 cursor-pointer transition-all hover:bg-purple-900/20"
                    >
                      <td className="py-3 px-4">
                        <div className="font-bold text-white text-lg">{stock.ticker}</div>
                      </td>
                      <td className="py-3 px-4">
                        <div className="text-slate-300 text-sm truncate max-w-[200px]">
                          {stock.company_name || 'Unknown'}
                        </div>
                      </td>
                      <td className="py-3 px-4">
                        <div className={`text-2xl font-black ${scoreColor}`}>
                          {stock.gomes_score ?? '-'}
                        </div>
                      </td>
                      <td className="py-3 px-4">
                        <span className={`px-2 py-1 rounded text-xs font-bold ${
                          stock.action_verdict === 'BUY_NOW' ? 'bg-green-500/20 text-green-400' :
                          stock.action_verdict === 'ACCUMULATE' ? 'bg-emerald-500/20 text-emerald-400' :
                          stock.action_verdict === 'WATCH_LIST' ? 'bg-blue-500/20 text-blue-400' :
                          stock.action_verdict === 'TRIM' ? 'bg-orange-500/20 text-orange-400' :
                          stock.action_verdict === 'SELL' ? 'bg-red-500/20 text-red-400' :
                          stock.action_verdict === 'AVOID' ? 'bg-red-800/30 text-red-500' :
                          'bg-slate-700 text-slate-400'
                        }`}>
                          {stock.action_verdict || 'N/A'}
                        </span>
                      </td>
                      <td className="py-3 px-4">
                        <span className={`px-2 py-1 rounded text-xs font-medium ${zoneColor}`}>
                          {stock.price_zone || 'N/A'}
                        </span>
                      </td>
                      <td className="py-3 px-4 text-right">
                        <button className="px-3 py-1 bg-purple-600 hover:bg-purple-500 text-white text-xs font-bold rounded transition-colors">
                          View Details
                        </button>
                      </td>
                    </tr>
                  );
                })}
                {displayedWatchlist.length === 0 && (
                  <tr>
                    <td colSpan={6} className="text-center py-12 text-slate-500">
                      {searchQuery 
                        ? 'No stocks found in watchlist' 
                        : 'No analyzed stocks yet. Click "New Analysis" to add stocks to your watchlist.'}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}

        {/* Family Gaps Alert */}
        {activeTab === 'portfolio' && familyGaps && familyGaps.gaps.length > 0 && (
          <div className="mt-6 p-4 bg-purple-500/10 border border-purple-500/30 rounded-xl">
            <h3 className="text-lg font-bold text-purple-400 flex items-center gap-2 mb-3">
              <Users className="w-5 h-5" />
              Cross-Account Discrepancies ({familyGaps.gaps.length})
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
              {familyGaps.gaps.slice(0, 6).map((gap, i) => (
                <div key={i} className="p-3 bg-slate-800/50 rounded-lg">
                  <div className="font-bold text-white">{gap.ticker}</div>
                  <div className="text-sm text-slate-400">
                    <span className="text-purple-400">{gap.holder}</span> holds, 
                    <span className="text-amber-400"> {gap.missing_from}</span> does not
                  </div>
                  <div className="text-xs text-slate-500 mt-1">
                    Score: {gap.gomes_score}/10 • {gap.action}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* FREEDOM TAB - Dopamine Dashboard */}
        {activeTab === 'freedom' && (
          <div className="space-y-6">
            {/* Hero: Freedom Countdown */}
            <FreedomCountdown
              currentValue={familyData.totalValue}
              targetValue={30000000} // 30M CZK
              monthlyContribution={20000}
              annualReturn={0.15}
              targetAge={50}
              currentAge={35} // TODO: Make configurable
            />
            
            {/* Two column layout */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Compound Snowball */}
              <CompoundSnowball
                currentValue={familyData.totalValue}
                monthlyContribution={20000}
                annualReturn={0.15}
                years={15}
              />
              
              {/* Merit Badges */}
              <MeritBadges 
                positions={familyData.allPositions}
                totalValue={familyData.totalValue}
              />
            </div>
            
            {/* Family Wealth Empire Preview */}
            <div className="bg-gradient-to-br from-slate-800/80 to-emerald-900/30 rounded-xl p-5 border border-emerald-500/30">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2">
                  <Users className="w-5 h-5 text-emerald-400" />
                  <span className="text-sm font-bold text-emerald-300 uppercase tracking-wider">Family Wealth Empire</span>
                </div>
                <div className="text-xs text-slate-400">
                  Společná mise
                </div>
              </div>
              
              <div className="grid grid-cols-2 gap-4 mb-4">
                <div className="bg-slate-800/50 rounded-lg p-4 text-center">
                  <div className="text-3xl mb-2">🏰</div>
                  <div className="text-lg font-bold text-white">{formatCurrency(familyData.totalValue)}</div>
                  <div className="text-xs text-slate-400">Rodinný hrad</div>
                </div>
                <div className="bg-slate-800/50 rounded-lg p-4 text-center">
                  <div className="text-3xl mb-2">💰</div>
                  <div className="text-lg font-bold text-emerald-400">{formatCurrency(familyData.totalCash)}</div>
                  <div className="text-xs text-slate-400">Válečná pokladna</div>
                </div>
              </div>
              
              {/* Monthly discipline tracker */}
              <div className="bg-emerald-500/10 border border-emerald-500/30 rounded-lg p-4">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm text-emerald-300">Měsíční disciplína</span>
                  <span className="text-xs text-slate-400">Leden 2026</span>
                </div>
                <div className="flex items-center gap-3">
                  <div className="flex-1">
                    <div className="h-2 bg-slate-700 rounded-full overflow-hidden">
                      <div className="h-full bg-emerald-500 w-1/2" /> {/* TODO: Track actual deposits */}
                    </div>
                  </div>
                  <div className="text-xs text-emerald-400 font-bold">20k / 40k</div>
                </div>
                <div className="text-xs text-slate-400 mt-2">
                  💪 Přítelkyně: ✅ 20k posláno • Ty: ⏳ Čeká na vklad
                </div>
              </div>
            </div>
            
            {/* Ghost of Mistakes Past - Placeholder */}
            <div className="bg-slate-800/50 rounded-xl p-5 border border-red-500/20">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2">
                  <AlertTriangle className="w-5 h-5 text-red-400" />
                  <span className="text-sm font-bold text-red-300 uppercase tracking-wider">Ghost of Mistakes Past</span>
                </div>
                <div className="text-xs text-slate-400">
                  Hřbitov chyb
                </div>
              </div>
              
              <div className="text-center py-8 text-slate-500">
                <div className="text-4xl mb-3">👻</div>
                <div className="text-sm">Zatím žádné záznamy</div>
                <div className="text-xs mt-1">
                  Tady se budou zobrazovat "Co by se stalo, kdybych..."
                </div>
              </div>
            </div>
          </div>
        )}
      </main>

      {/* MODALS */}
      {selectedPosition && (
        <StockDetailModal
          position={selectedPosition}
          familyGaps={familyGaps}
          onClose={() => setSelectedPosition(null)}
          onUpdate={async () => {
            // Refresh stocks data after update
            const stocksData = await apiClient.getStocks();
            setStocks(stocksData.stocks);
          }}
        />
      )}

      {/* Watchlist Stock Detail Modal */}
      {selectedWatchlistStock && (
        <WatchlistDetailModal
          stock={selectedWatchlistStock}
          onClose={() => setSelectedWatchlistStock(null)}
          onUpdate={async () => {
            const stocksData = await apiClient.getStocks();
            setStocks(stocksData.stocks);
          }}
        />
      )}

      {/* Import CSV Modal */}
      {showImportModal && (
        <ImportCSVModal
          portfolios={portfolios}
          onClose={() => setShowImportModal(false)}
          onSuccess={async () => {
            // Refresh all data
            const portfolioList = await apiClient.getPortfolios();
            const summaries: PortfolioSummary[] = [];
            for (const p of portfolioList) {
              try {
                const summary = await apiClient.getPortfolioSummary(p.id);
                summaries.push(summary);
              } catch { /* skip */ }
            }
            setPortfolios(summaries);
          }}
        />
      )}

      {/* Add Position Modal */}
      {showAddPositionModal && (
        <AddPositionModal
          portfolios={portfolios}
          onClose={() => setShowAddPositionModal(false)}
          onSuccess={async () => {
            // Refresh portfolios
            const portfolioList = await apiClient.getPortfolios();
            const summaries: PortfolioSummary[] = [];
            for (const p of portfolioList) {
              try {
                const summary = await apiClient.getPortfolioSummary(p.id);
                summaries.push(summary);
              } catch { /* skip */ }
            }
            setPortfolios(summaries);
          }}
        />
      )}

      {showAnalysisModal && (
        <NewAnalysisModal
          onClose={() => setShowAnalysisModal(false)}
          onSubmit={handleNewAnalysis}
        />
      )}
    </div>
  );
};

export default GomesGuardianDashboard;
