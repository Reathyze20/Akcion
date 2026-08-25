/**
 * Akcion Investment Terminal
 * 
 * Enterprise-grade portfolio management dashboard:
 * - Multi-Account Portfolio Consolidation
 * - Conviction Scoring & Risk Assessment
 * - Position Sizing (Kelly Criterion)
 * - Thesis Drift Monitoring & Alerts
 */

import React, { useState, useEffect, useMemo, useRef } from 'react';
import {
  TrendingUp, TrendingDown, AlertTriangle, Shield,
  PlusCircle, RefreshCw, Search,
  Target, Zap, X, Check, BarChart3,
  Upload, Plus, FileSpreadsheet, Edit3
} from 'lucide-react';
import { apiClient } from '../api/client';
import { canonicalOf, canonicalSet, pickAnalysis } from '../lib/tickers';
import type {
  Band,
  EarningsInfo,
  MarketAlert,
  PortfolioSummary, Position, Stock,
  BrokerType
} from '../types';
import { StockDetail } from './StockDetail';
import NotificationBell from './NotificationBell';
import DailyActionWidget from './DailyActionWidget';
import DecisionBoard from './DecisionBoard';
import ClearPortfolioButton from './ClearPortfolioButton';
import RiskMeter from './RiskMeter';
import Term from './ui/Term';
import { percent, plural, verdictName, verdictTone, zoneName, zoneTone } from '../lib/format';
import GoalPage from './goal/GoalPage';
import FindsPage from './finds/FindsPage';
import RevenueModelsPage from './models/RevenueModelsPage';
import ThemeToggle from './ui/ThemeToggle';
import SideRail from './shell/SideRail';
import ContextPanel from './shell/ContextPanel';
import RemovePositionDialog from './RemovePositionDialog';
import PaymentsPage from './payments/PaymentsPage';
import { GomesIntakeModal } from './GomesIntakeModal';

// ============================================================================
// TYPES
// ============================================================================

type EnrichedPosition = Position & {
  stock?: Stock;
  conviction_score: number | null;
  // Gomes Gap Analysis
  max_allocation_cap: number;    // Maximum allocation % (from Gomes Logic)
  target_weight_pct: number;     // Ideální váha podle skóre (deprecated - use max_allocation_cap)
  weight_in_portfolio: number;   // Aktuální váha v portfoliu
  gap_czk: number;               // Mezera v CZK (+ = dokoupit, - = prodat)
  optimal_size: number;          // Kolik investovat TENTO MĚSÍC (po prioritizaci)
  allocation_priority: number;   // Priorita (1 = nejvyšší)
  // Status
  trend_status: 'BULLISH' | 'BEARISH' | 'NEUTRAL' | 'UNKNOWN';
  /** Pásmo tak, jak ho spočítal engine. Nedopočítává se v prohlížeči. */
  band?: Band;
  // Whether the analysis behind the numbers above may drive a recommendation
  analysis_usable: boolean;
  analysis_note: string | null;
  is_deteriorated: boolean;
  is_overweight: boolean;
  is_underweight: boolean;
  action_signal: 'BUY' | 'HOLD' | 'SELL' | 'SNIPER';  // Akční signál
  inflection_status?: string;
  // Next Catalyst
  next_catalyst?: string;  // Format: "EVENT / DATE" or null
};

interface FamilyPortfolioData {
  totalValue: number;
  totalValueEUR: number;  // EUR equivalent
  totalCash: number;
  monthlyContribution: number;  // Celkový měsíční příspěvek ze všech portfolií
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
const MIN_INVESTMENT_CZK = 1000; // Min vklad (kvůli poplatkům)

// ============================================================================
// HELPER FUNCTIONS
// ============================================================================

const formatCurrency = (amount: number, currency: string = 'CZK'): string => {
  return new Intl.NumberFormat('cs-CZ', { 
    style: 'currency', 
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2 
  }).format(amount);
};

const formatPercent = (value: number | undefined | null): string => {
  if (value === undefined || value === null || isNaN(value)) {
    return '0.00%';
  }
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

  // Strop není odpověď. Vrátit 240 znamená tvrdit „za dvacet let" i tam,
  // kde se při nulovém vkladu cíl nesplní nikdy — a to je přesně ta záměna
  // chybějícího údaje za verdikt, které se tahle aplikace má vyhýbat.
  return value >= targetValue ? months : Infinity;
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
  targetWeight: number,
  analysisUsable: boolean = true
): 'BUY' | 'HOLD' | 'SELL' | 'SNIPER' => {
  // No usable analysis is not a verdict. Holding still is the only honest
  // answer, and the ACTION column says why.
  if (!analysisUsable) return 'HOLD';
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
  unrealizedProfitPct: number,
  analysisUsable: boolean = true,
  //  Buy Guard veto, added 2026-08-25. This function used to compute
  //  STRONG BUY/BUY from score and weight alone — no idea whether the
  //  market was GREEN, whether Gomes ever issued a valuation line for the
  //  ticker, or whether it is in Wait Time. `GomesGatekeeper.evaluate_buy_guard`
  //  already refuses a buy on any of those three; this is the presentation
  //  layer's half of that same rule, because a table cell that says STRONG
  //  BUY is a verdict whether or not the backend agrees with it.
  hasBand: boolean = false,
  marketAlert: MarketAlert | null = null,
  isWaitTime: boolean = false
): { text: string; color: string; bgColor?: string } => {
  // Priority 1: Free Ride at 150%+ — this one is pure arithmetic on the
  // owner's own cost basis, so it holds without any analysis.
  if (unrealizedProfitPct >= 150) {
    return { text: 'FREE RIDE', color: 'text-warning', bgColor: 'bg-warning/10' };
  }

  // Nothing below here may fire on an analysis we do not have or no longer
  // trust. A stale January score was producing HARD EXIT and #1-priority BUY
  // in August.
  if (!analysisUsable) {
    return { text: 'DOPLŇ ANALÝZU', color: 'text-text-muted' };
  }

  // Priority 2: Hard Exit for score < 4 — a sell-side call, so none of the
  // buy-side vetoes below apply to it.
  if (score !== null && score < 4) {
    return { text: 'HARD EXIT', color: 'text-negative', bgColor: 'bg-negative/20' };
  }

  // Buy Guard veto: anything that would otherwise print a buy-side verdict
  // has to clear the same three gates the backend enforces. Checked once,
  // ahead of STRONG BUY/BUY, so neither can slip past it.
  const wouldBuy = score !== null && score >= 5 && currentWeight < targetWeight;
  if (wouldBuy && isWaitTime) {
    return { text: 'ČEKÁNÍ', color: 'text-warning', bgColor: 'bg-warning/10' };
  }
  if (wouldBuy && !hasBand) {
    return { text: 'BEZ PÁSMA', color: 'text-text-muted' };
  }
  if (wouldBuy && marketAlert === null) {
    return { text: 'SEMAFOR?', color: 'text-text-muted' };
  }
  if (wouldBuy && marketAlert !== 'GREEN') {
    return { text: `TRH ${marketAlert}`, color: 'text-warning', bgColor: 'bg-warning/10' };
  }

  // Priority 3: Strong Buy for score >= 8 and underweight
  if (score !== null && score >= 8 && currentWeight < targetWeight) {
    return { text: 'STRONG BUY', color: 'text-positive font-bold' };
  }

  // Priority 4: Hold if at or above target weight
  if (score !== null && score >= 5 && currentWeight >= targetWeight) {
    return { text: 'HOLD', color: 'text-text-muted' };
  }

  // Default: BUY signal for underweight positions with score 5-7
  if (score !== null && score >= 5 && currentWeight < targetWeight) {
    return { text: 'BUY', color: 'text-positive' };
  }

  // No score or edge case
  return { text: 'ANALYZE', color: 'text-text-muted' };
};

/**
 * An analysis older than this is not a current opinion.
 *
 * The database held a conviction score from January that was still driving a
 * "#1 priorita BUY" in August. A number on screen with no date attached reads
 * as today's view of the company.
 */
const ANALYSIS_STALE_AFTER_DAYS = 30;

type AnalysisState = {
  usable: boolean;
  ageDays: number | null;
  note: string | null;
};

/**
 * Whether a stock's analysis may drive a recommendation — and if not, why.
 *
 * Absent and stale both mean "we do not know". The table has to say that,
 * because the alternative was turning it into a target weight of 0 %, which
 * on screen reads as "you are overweight everything you own".
 */
const getAnalysisState = (
  stock: Stock | undefined,
  score: number | null
): AnalysisState => {
  if (score === null) return { usable: false, ageDays: null, note: 'bez analýzy' };
  const created = stock?.created_at ? new Date(stock.created_at) : null;
  const ageDays =
    created && !Number.isNaN(created.getTime())
      ? Math.floor((Date.now() - created.getTime()) / 86_400_000)
      : null;
  if (ageDays === null) return { usable: false, ageDays: null, note: 'analýza bez data' };
  if (ageDays > ANALYSIS_STALE_AFTER_DAYS) {
    return { usable: false, ageDays, note: `analýza ${ageDays} dní stará` };
  }
  return { usable: true, ageDays, note: null };
};

const CURRENCY_SYMBOL: Record<string, string> = {
  USD: '$', EUR: '€', CAD: 'CA$', CZK: 'Kč', GBP: '£', ILS: '₪',
};

/**
 * A price in the currency the position is actually held in.
 *
 * Four of the holdings trade in CAD or EUR. Printing "$0.62" for a euro price
 * is not a rounding difference — it is a different number.
 */
const formatPrice = (value: number, currency?: string | null): string => {
  const code = (currency || 'USD').toUpperCase();
  const symbol = CURRENCY_SYMBOL[code] ?? code;
  const digits = Math.abs(value) < 1 ? 4 : 2;
  return symbol === 'Kč' || symbol === code
    ? `${value.toFixed(digits)} ${symbol}`
    : `${symbol}${value.toFixed(digits)}`;
};

/**
 * Where the price sits inside the green/red band. NOT a trend — it says
 * nothing about direction, only about how much of the range is left.
 */
/**
 * Pásmo do sloupce — z API, nikdy z prohlížeče.
 *
 * Tady dřív stála vlastní matematika: poloha ceny v rozpětí zelená–červená
 * s prahy 0,4 a 0,7. Vypadalo to jako pásmo a nebylo. Engine pásmo počítá
 * proti tomu, co si firma **zaslouží** (`10 − válce`), takže stejná cena u
 * dvou různě kvalitních firem dá jiné pásmo — a prohlížeč o válcích nevěděl.
 * Akcie na 28 % rozpětí tak byla U ZELENÉ na obrazovce a PŘEPLACENO v enginu.
 *
 * Chybějící řádek je `UNKNOWN`, ne střed. Nemít odpověď a mít neutrální
 * odpověď jsou dvě různé věci a jen jedna z nich je informace.
 */
const bandToTrend = (
  band: Band | undefined
): 'BULLISH' | 'BEARISH' | 'NEUTRAL' | 'UNKNOWN' => {
  switch (band) {
    case 'POD_ZELENOU':
    case 'NAKUP':
      return 'BULLISH';
    case 'DRZET':
      return 'NEUTRAL';
    case 'PREPLACENO':
    case 'NAD_CERVENOU':
      return 'BEARISH';
    default:
      return 'UNKNOWN';
  }
};

/** České názvy pásem. Syrový enum se na obrazovku nikdy nedostane. */
const BAND_LABELS_CS: Record<Band, string> = {
  POD_ZELENOU: 'POD ZELENOU',
  NAKUP: 'NÁKUP',
  DRZET: 'DRŽET',
  PREPLACENO: 'PŘEPLACENO',
  NAD_CERVENOU: 'NAD ČERVENOU',
  NEZNAME: 'NEZNÁMÉ',
  MIMO_METODIKU: 'MIMO METODIKU',
};

// ============================================================================
// SUB-COMPONENTS
// ============================================================================

// Portfolio Row Component
/**
 * Které nepovinné sloupce má smysl kreslit.
 *
 * Deset sloupců, z nichž čtyři jsou u čtrnácti z patnácti řádků prázdné,
 * není tabulka — je to mřížka pomlček. Sloupec, pro který nemá data ani
 * jedna pozice, se proto nevykreslí vůbec a řádek se o jeho výšku zkrátí.
 */
export interface PositionColumns {
  score: boolean;
  size: boolean;
  catalyst: boolean;
  band: boolean;
  /** Cesta ke zdvojnásobení. Bez známé nákupní ceny se nedá spočítat. */
  freeride: boolean;
  /** Odpočet do výsledků. Bez data u kterékoli pozice se sloupec nekreslí. */
  earnings: boolean;
  /**
   * Sloupec s pokynem.
   *
   * Když aplikace nemá analýzu ani u jedné pozice, napsala patnáctkrát pod
   * sebe „DOPLŇ ANALÝZU". Patnáct stejných vět není sloupec — je to jedna
   * věta, a ta stojí i s důsledkem v denním seznamu vlevo. Zůstane tu jen
   * to, co platí pro konkrétní řádek: WAIT TIME a FREE RIDE.
   */
  action: boolean;
  /**
   * Vysvětlivka „bez analýzy“ pod pokynem.
   *
   * Kreslí se jen tehdy, když se pozice v tomhle liší. Když analýzu nemá
   * ani jedna, je to vlastnost portfolia, ne řádku — a stojí to jednou
   * v denním seznamu vlevo, se všemi důsledky, místo patnáctkrát tady.
   */
  analysisNote: boolean;
}

/**
 * Hlavička sloupce.
 *
 * Devět hlaviček psaných ručně mělo šest různých kombinací velikosti,
 * tučnosti a odsazení, a dvouřádkové („Váha" nad „Aktuální / Cíl")
 * přidávaly hlavičce výšku, kterou pak neměla tabulka. Upřesnění se
 * proto píše za název, ne pod něj.
 */
const Th: React.FC<{
  children: React.ReactNode;
  width: string;
  align?: 'left' | 'center' | 'right';
  /** Upřesnění za názvem — „teď / cíl", „tento měsíc". */
  sub?: string;
  hint?: string;
}> = ({ children, width, align = 'left', sub, hint }) => (
  <th
    title={hint}
    className={`eyebrow px-2.5 py-2 font-medium text-text-muted ${width} ${
      align === 'right' ? 'text-right' : align === 'center' ? 'text-center' : 'text-left'
    }`}
  >
    {children}
    {sub && (
      <span className="ml-1 font-normal normal-case tracking-normal opacity-60">{sub}</span>
    )}
  </th>
);

/**
 * Odpočet do nejbližších výsledků.
 *
 * Jedna komponenta pro portfolio i pro sledované, protože ta samá otázka se
 * nesmí ve dvou tabulkách čtvrtletně rozejít. Text píše backend
 * (`earnings_lookup.py`) — „za 78 dní" u oznámeného data, „asi za 98 dní"
 * u odhadu z vlastní historie zveřejňování firmy. Ten rozdíl je celý smysl
 * kalendáře, takže se nese ve slovech, ne jen v tooltipu.
 *
 * Blackout kreslí backend taky. Kdyby si čtrnáct dnů počítal prohlížeč, mohla
 * by tabulka tvrdit něco jiného než brána, která nákup opravdu odmítne.
 */
const EarningsCell: React.FC<{ earnings?: EarningsInfo | null }> = ({ earnings }) => {
  if (!earnings) {
    // Chybějící datum není zpráva o firmě. Pomlčka, ne nula.
    return <span className="text-[9px] uppercase text-text-muted">—</span>;
  }
  const tone = earnings.blackout
    ? 'text-warning'
    : earnings.confirmed
      ? 'text-text-secondary'
      : 'text-text-muted';
  return (
    <span
      title={earnings.detail_cs}
      className={`text-[10px] font-mono tabular-nums whitespace-nowrap ${tone}`}
    >
      {earnings.label_cs}
    </span>
  );
};

const PortfolioRow: React.FC<{
  position: EnrichedPosition;
  columns: PositionColumns;
  marketAlert: MarketAlert | null;
  onClick: () => void;
  onRemove: () => void;
}> = ({ position, columns, marketAlert, onClick, onRemove }) => {
  const scoreColor = position.conviction_score
    ? position.conviction_score >= 7 ? 'text-positive'
      : position.conviction_score >= 5 ? 'text-warning'
      : 'text-negative'
    : 'text-text-muted';

  const trendIcon = position.trend_status === 'BULLISH'
    ? <TrendingUp className="w-4 h-4 text-positive" />
    : position.trend_status === 'BEARISH'
    ? <TrendingDown className="w-4 h-4 text-negative" />
    : <BarChart3 className="w-4 h-4 text-text-muted" />;

  // null P/L = purchase price unknown (user must fill it in) — neutral color
  const hasCostBasis = position.avg_cost != null;
  const plColor = position.unrealized_pl_percent == null
    ? 'text-warning'
    : position.unrealized_pl_percent >= 0 ? 'text-positive' : 'text-negative';

  const isWaitTime = position.inflection_status?.toUpperCase() === 'WAIT_TIME';

  // Get action command (unknown P/L treated as 0: no free-ride claims).
  // `!!position.band` is the same "does Gomes have a valuation line for this
  // company" question the Pásmo column answers — a buy-side verdict without
  // one is the KUYAF/OPTX pattern (IMPLEMENTATION_PLAN.md §20): a score with
  // nothing under it.
  const actionCmd = getActionCommand(
    position.conviction_score,
    position.weight_in_portfolio,
    position.target_weight_pct,
    position.unrealized_pl_percent ?? 0,
    position.analysis_usable,
    !!position.band,
    marketAlert,
    isWaitTime
  );

  // Check if row should be highlighted (HARD EXIT)
  const isHardExit =
    position.analysis_usable &&
    position.conviction_score !== null &&
    position.conviction_score < 4;

  // Strategy: Free Ride eligible vs everything else (never without a cost basis)
  const isFreeRideEligible = position.unrealized_pl_percent != null && position.unrealized_pl_percent >= 150;
  // Clamped at BOTH ends. Without a lower bound a −60 % position produced a
  // CSS width of "-40%", which browsers discard — so the biggest losses
  // rendered as a full green bar.
  const progressTo150 = Math.max(
    0, Math.min(100, ((position.unrealized_pl_percent ?? 0) / 150) * 100)
  );

  // Calculate shares to sell for Free Ride
  const sharesToSellForFreeRide = useMemo(() => {
    if (!isFreeRideEligible || position.avg_cost == null) return 0;
    const currentPrice = position.stock?.current_price ?? position.current_price ?? 0;
    if (currentPrice <= 0) return 0;
    const costBasis = position.shares_count * position.avg_cost;
    return Math.ceil(costBasis / currentPrice);
  }, [position, isFreeRideEligible]);

  return (
    <tr 
      onClick={onClick}
      className={`
        border-b border-border/50 cursor-pointer transition-all
        hover:bg-surface-raised/70
        ${isHardExit ? 'bg-negative/15' : ''}
        ${position.is_deteriorated && !isHardExit ? 'bg-negative/10' : ''}
      `}
    >
      {/* Ticker & Name */}
      <td className="py-1.5 px-2.5">
        <div className="flex flex-col">
          <div className="flex items-center gap-2">
            <span className="font-bold text-text-primary text-base">{position.ticker}</span>
            {position.is_deteriorated && (
              <span className="px-1.5 py-0.5 bg-negative/20 text-negative text-[10px] font-bold rounded">
                REVIEW
              </span>
            )}
            {/* SEC nález (going concern, neúčinné kontroly, restatement...).
                Dřív viditelné jen po otevření detailu pozice — čtvrtina
                portfolia ho nese a na řádku po něm nebyla ani stopa. */}
            {position.sec_material_finding && (
              <span
                className="px-1.5 py-0.5 bg-warning/20 text-warning text-[10px] font-bold rounded"
                title="Vlastní SEC výkaz firmy má CRITICAL/HIGH nález (going concern, neúčinné kontroly, restatement...) — detail v kartě pozice"
              >
                ⚠ SEC
              </span>
            )}
          </div>
          <div className="text-[10px] text-text-secondary truncate">
            {position.company_name || 'Unknown'}
          </div>
        </div>
      </td>

      {/* Pokyn. Věta „bez analýzy“ pod ním se kreslí, jen když se tím
          liší od ostatních — když ji nemá ani jedna pozice, stojí to
          jednou nad tabulkou místo patnáctkrát v ní. */}
      <td className="py-1.5 px-2.5">
        {(columns.action || actionCmd.text !== 'DOPLŇ ANALÝZU') && (
          <div className={`text-[10px] font-bold uppercase tracking-wide ${actionCmd.color} ${actionCmd.bgColor ? actionCmd.bgColor + ' px-2 py-1 rounded' : ''}`}>
            {actionCmd.text}
          </div>
        )}
        {columns.analysisNote && !position.analysis_usable && position.analysis_note && (
          <div className="text-[9px] text-text-muted mt-0.5">{position.analysis_note}</div>
        )}
        {isWaitTime && (
          <div className="text-[9px] text-warning font-bold mt-0.5" title="Kánon: mrtvé peníze, neinvestovat">
            WAIT TIME
          </div>
        )}
      </td>

      {/* Váha aktuální / cílová. Pomlčka na místě cíle už říká, že cíl
          neznáme — řádek „CÍL NEZNÁMÝ“ pod ní byl totéž podruhé. */}
      <td className="py-1.5 px-2.5">
        <div className="flex flex-col">
          {/* Numbers stay neutral; only the small status tag carries color.
              A column of red values reads as panic — this is a caution, not a loss. */}
          <div className="flex items-center gap-1">
            <span className="font-mono text-sm font-semibold text-text-secondary">
              {position.weight_in_portfolio.toFixed(1)}%
            </span>
            {/* A target of "0.0 %" computed from a missing score used to read
                as "sell it all". Without an analysis there is no target — a
                cílová váha se pak nekreslí vůbec, protože „/ —" na patnácti
                řádcích je jen patnáctkrát tatáž pomlčka. */}
            {columns.action && (
              <>
                <span className="text-text-muted text-xs">/</span>
                <span
                  className="font-mono text-xs text-text-muted"
                  title={position.analysis_usable ? undefined : 'Cílovou váhu aplikace bez konvikčního skóre nespočítá.'}
                >
                  {position.analysis_usable ? `${position.max_allocation_cap.toFixed(1)}%` : '—'}
                </span>
              </>
            )}
          </div>
          {position.analysis_usable && position.is_overweight ? (
            <div className="text-[9px] text-warning">NAD LIMITEM</div>
          ) : position.analysis_usable && position.is_underweight ? (
            <div className="text-[9px] text-text-muted">POD CÍLEM</div>
          ) : null}
        </div>
      </td>

      {/* Konvikční skóre — číslo bez data se čte jako dnešní pohled. */}
      {columns.score && (
        <td className="py-1.5 px-2.5 text-center">
          <div className={`text-xl font-black ${position.analysis_usable ? scoreColor : 'text-text-muted'}`}>
            {position.conviction_score ?? '—'}
          </div>
          {position.conviction_score !== null && !position.analysis_usable && (
            <div className="text-[9px] text-warning" title={position.analysis_note ?? ''}>
              neaktuální
            </div>
          )}
        </td>
      )}

      {/* Cena. Nákupní cena se píše, jen když ji známe — že chybí, stojí
          ve sloupci P/L, kde na ní záleží. */}
      <td className="py-1.5 px-2.5 text-right">
        <div className="flex flex-col items-end">
          {position.current_price ? (
            <>
              <div className="text-sm font-bold text-text-primary font-mono">
                {formatPrice(position.current_price, position.currency)}
              </div>
              {position.avg_cost != null && (
                <div className="text-[9px] text-text-muted">
                  Nákup: {formatPrice(position.avg_cost, position.currency)}
                </div>
              )}
            </>
          ) : (
            <div className="text-xs text-text-muted">—</div>
          )}
        </div>
      </td>

      {/* Optimální dávka na tento měsíc. */}
      {columns.size && (
        <td className="py-1.5 px-2.5">
          {!position.analysis_usable ? (
            <div className="text-text-muted font-mono text-xs">—</div>
          ) : position.action_signal === 'SELL' ? (
            <div className="flex flex-col">
              <div className="text-negative font-bold text-xs">PRODAT</div>
              <div className="text-[9px] text-negative/80">Skóre &lt; 5</div>
            </div>
          ) : position.optimal_size < 0 ? (
            // OVERWEIGHT: Show how much to SELL (negative optimal_size)
            <div className="flex flex-col">
              <div className="flex items-center gap-1">
                <span className="text-warning font-bold text-[9px]">ODEBRAT</span>
                <span className="text-sm font-bold text-warning font-mono">
                  {formatCurrency(Math.abs(position.optimal_size))}
                </span>
              </div>
              <div className="text-[9px] text-warning/80">
                Nad limit {position.max_allocation_cap.toFixed(1)}%
              </div>
            </div>
          ) : position.optimal_size > 0 ? (
            <div className="flex flex-col">
              <div className="flex items-center gap-1">
                {position.action_signal === 'SNIPER' && <span className="text-warning text-[9px] font-bold">SNIPER</span>}
                <span className="text-sm font-bold text-positive font-mono">
                  {formatCurrency(position.optimal_size)}
                </span>
              </div>
              {position.allocation_priority > 0 && position.allocation_priority <= 3 && (
                <div className="text-[9px] text-warning font-bold">
                  #{position.allocation_priority} priorita
                </div>
              )}
            </div>
          ) : (
            <div className="flex flex-col">
              <div className="text-text-muted font-mono text-xs">0 Kč</div>
              <div className="text-[9px] text-text-muted">
                {position.gap_czk <= 0 ? 'Na cíli' : 'Nízká priorita'}
              </div>
            </div>
          )}
        </td>
      )}

      {/* Nejbližší katalyzátor. */}
      {columns.catalyst && (
        <td className="py-1.5 px-2.5">
          {position.next_catalyst ? (
            <div className="text-[9px] text-text-secondary uppercase tracking-wide font-mono truncate" title={position.next_catalyst}>
              {position.next_catalyst.length > 18 ? position.next_catalyst.slice(0, 18) + '...' : position.next_catalyst}
            </div>
          ) : (
            // Absent data is not a red flag about the company.
            <div className="text-[9px] text-text-muted uppercase">—</div>
          )}
        </td>
      )}

      {/* Odpočet do výsledků. Uvnitř čtrnácti dnů brána nákup odmítne, tak
          to buňka zvýrazní — je to důsledek, ne dekorace. */}
      {columns.earnings && (
        <td className="py-1.5 px-2.5">
          <EarningsCell earnings={position.earnings} />
        </td>
      )}

      {/* Pásmo z enginu: kde cena leží vůči tomu, co si firma zaslouží
          (`10 − válce`), ne kde leží v rozpětí. Prázdné, když engine pásmo
          nevydal — mimo metodiku, neznámé válce, nebo server neodpověděl. */}
      {columns.band && (
        <td className="py-1.5 px-2.5">
          {/* Prázdno, ne pomlčka — ale jen když engine neřekl vůbec nic.
              „MIMO METODIKU" prázdno není: je to odpověď, že Gomes pro tu
              firmu linku nevydal, takže žádné pásmo neexistuje a nemá smysl
              ho čekat. Dokud byly prázdné všechny řádky, byl ten rozdíl
              neviditelný; vedle vyplněných čte prázdná buňka jako rozbitá
              aplikace. Šedě a bez šipky, aby se nepletlo s pásmem, které
              o ceně něco tvrdí — barva by z chybějícího údaje udělala verdikt. */}
          <div className="flex flex-col items-center gap-1">
            {position.band ? (
              position.trend_status !== 'UNKNOWN' ? (
                <>
                  {trendIcon}
                  <span className={`text-[10px] font-medium ${
                    position.trend_status === 'BULLISH' ? 'text-positive' :
                    position.trend_status === 'BEARISH' ? 'text-negative' :
                    'text-text-muted'
                  }`}>
                    {BAND_LABELS_CS[position.band]}
                  </span>
                </>
              ) : (
                <span className="text-[10px] text-text-muted">
                  {BAND_LABELS_CS[position.band]}
                </span>
              )
            ) : null}
          </div>
        </td>
      )}

      {/* Cesta k free ride.

          Tenhle sloupec dřív psal „VE ZTRÁTĚ“, pruh a „−60 % od nákupu“ —
          tedy potřetí totéž, co vedle stojí jako −60,30 % a −746,53 US$.
          Zbylo z něj jen to, co P/L neříká: jak daleko je pozice ke
          zdvojnásobení, po kterém se podle kánonu vybírá vklad. */}
      {columns.freeride && (
        <td className="py-1.5 px-2.5">
          {isFreeRideEligible ? (
            <div className="flex flex-col">
              <div className="text-[9px] text-warning font-bold uppercase">FREE RIDE</div>
              <div className="text-[8px] text-warning/70">
                prodat {sharesToSellForFreeRide} ks
              </div>
            </div>
          ) : position.unrealized_pl_percent != null && position.unrealized_pl_percent > 0 ? (
            <div className="flex flex-col gap-1">
              <div className="w-full h-1.5 bg-surface-hover rounded-full overflow-hidden">
                <div
                  className="h-full bg-positive/60 transition-all"
                  style={{ width: `${progressTo150}%` }}
                />
              </div>
              <div className="text-[8px] text-text-muted">
                {position.unrealized_pl_percent.toFixed(0)} % ze 150 %
              </div>
            </div>
          ) : null}
        </td>
      )}

      {/* P/L % — unknown cost basis renders as a prompt, never as 0.00% */}
      <td className="py-1.5 px-2.5 text-right">
        {hasCostBasis && position.unrealized_pl_percent != null ? (
          <>
            <div className={`font-bold text-sm ${plColor}`}>
              {formatPercent(position.unrealized_pl_percent)}
            </div>
            <div className="text-[10px] text-text-muted">
              {formatCurrency(position.unrealized_pl ?? 0, position.currency || 'USD')}
            </div>
          </>
        ) : (
          <div className="text-[10px] text-text-muted" title="Doplň nákupní cenu v detailu pozice">
            bez nákupní ceny
          </div>
        )}
      </td>

      {/* „Už nedržím". Vždycky viditelné, ne až po najetí myší: akce, která
          se objeví jen na hover, je pro někoho, kdo míří hůř, akce, která
          neexistuje. `stopPropagation` proto, že klik na řádek otevírá
          detail — a tenhle klik má dělat něco jiného. */}
      <td className="py-1.5 px-1 text-right">
        <button
          onClick={(e) => { e.stopPropagation(); onRemove(); }}
          className="rounded-button p-1.5 text-text-muted transition-colors hover:bg-negative/15 hover:text-negative"
          title={`Už nedržím ${position.ticker}`}
          aria-label={`Už nedržím ${position.ticker}`}
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </td>
    </tr>
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

  const scoreColor = stock.conviction_score 
    ? stock.conviction_score >= 7 ? 'bg-positive/20 text-positive' 
      : stock.conviction_score >= 5 ? 'bg-warning/20 text-warning' 
      : 'bg-negative/20 text-negative'
    : 'bg-surface-hover text-text-muted';

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
    <div className="fixed inset-0 bg-surface-base/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-surface-base border border-info/50 rounded-2xl w-full max-w-3xl max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="sticky top-0 bg-surface-base border-b border-info/50 p-4 flex items-center justify-between z-10">
          <div className="flex items-center gap-4">
            <div className={`w-14 h-14 rounded-xl flex items-center justify-center font-black text-2xl ${scoreColor}`}>
              {stock.conviction_score ?? '?'}
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-2xl font-black text-text-primary">{stock.ticker}</h2>
                <span className="px-2 py-0.5 bg-info/20 text-info text-xs font-bold rounded">
                  WATCHLIST
                </span>
              </div>
              <p className="text-text-secondary">{stock.company_name || 'Unknown Company'}</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button 
              onClick={() => setShowUpdateForm(!showUpdateForm)}
              className="px-3 py-2 bg-info hover:bg-info/80 text-text-primary rounded-lg text-sm font-medium flex items-center gap-2 transition-colors"
            >
              <RefreshCw className="w-4 h-4" />
              Update Analysis
            </button>
            <button onClick={onClose} className="p-2 hover:bg-surface-raised rounded-lg">
              <X className="w-6 h-6 text-text-secondary" />
            </button>
          </div>
        </div>

        {/* Update Form */}
        {showUpdateForm && (
          <div className="p-4 bg-info/10 border-b border-info/30">
            <h3 className="text-lg font-bold text-info mb-3 flex items-center gap-2">
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
                      ? 'bg-info text-text-primary'
                      : 'bg-surface-hover text-text-secondary hover:bg-surface-active'
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
              className="w-full px-4 py-3 bg-surface-raised border border-border rounded-lg text-text-primary placeholder-text-muted focus:outline-none focus:border-info resize-none mb-3"
            />
            
            <div className="flex items-center justify-between">
              <div className="text-xs text-text-muted">{updateText.length} characters (min. 50)</div>
              <div className="flex items-center gap-3">
                {updateResult && (
                  <span className={`text-sm ${updateResult.success ? 'text-positive' : 'text-negative'}`}>
                    {updateResult.message}
                  </span>
                )}
                <button
                  onClick={handleUpdate}
                  disabled={isUpdating || updateText.length < 50}
                  className="px-4 py-2 bg-info hover:bg-info/80 disabled:bg-surface-active text-text-primary rounded-lg font-medium flex items-center gap-2 transition-colors"
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
          <div className="bg-surface-raised/50 rounded-xl p-4 border border-border">
            <h3 className="text-sm font-bold text-text-secondary uppercase tracking-wider mb-4">Investment Thesis</h3>
            
            <div className="space-y-4">
              <div>
                <div className="text-xs text-text-muted uppercase mb-1">Trade Rationale</div>
                <p className="text-text-secondary text-sm">
                  {stock.trade_rationale || stock.edge || 'No analysis available.'}
                </p>
              </div>
              
              <div>
                <div className="text-xs text-text-muted uppercase mb-1">Catalysts</div>
                <p className="text-text-secondary text-sm">
                  {stock.catalysts || 'No catalysts identified.'}
                </p>
              </div>
              
              <div>
                <div className="text-xs text-text-muted uppercase mb-1">Risks</div>
                <p className="text-negative/80 text-sm">
                  {stock.risks || 'No risks documented.'}
                </p>
              </div>
            </div>
          </div>

          {/* Right: Valuation */}
          <div className="bg-surface-raised/50 rounded-xl p-4 border border-border">
            <h3 className="text-sm font-bold text-text-secondary uppercase tracking-wider mb-4">Valuation & Targets</h3>
            
            <div className="space-y-3">
              <div className="flex justify-between">
                <span className="text-text-secondary">Verdikt</span>
                <span className={`font-bold px-2 py-0.5 rounded text-sm ${
                  stock.action_verdict === 'BUY_NOW' ? 'bg-positive/20 text-positive' :
                  stock.action_verdict === 'ACCUMULATE' ? 'bg-positive/20 text-positive' :
                  stock.action_verdict === 'WATCH_LIST' ? 'bg-accent/20 text-accent' :
                  'bg-surface-hover text-text-secondary'
                }`}>
                  {stock.action_verdict || 'N/A'}
                </span>
              </div>
              
              <div className="flex justify-between">
                <span className="text-text-secondary">Current Price</span>
                <span className="font-mono text-text-primary">${stock.current_price?.toFixed(2) || 'N/A'}</span>
              </div>
              
              <div className="flex justify-between">
                <span className="text-text-secondary">Entry Zone (Green)</span>
                <span className="font-mono text-positive">${stock.green_line?.toFixed(2) || 'N/A'}</span>
              </div>
              
              <div className="flex justify-between">
                <span className="text-text-secondary">Target (Red)</span>
                <span className="font-mono text-negative">${stock.red_line?.toFixed(2) || 'N/A'}</span>
              </div>
              
              <div className="flex justify-between">
                <span className="text-text-secondary">Cenové pásmo</span>
                <span className={`font-bold px-2 py-0.5 rounded text-sm border ${zoneTone(stock.price_zone).pill}`}>
                  {zoneName(stock.price_zone)}
                </span>
              </div>
              
              {stock.price_target && (
                <div className="flex justify-between">
                  <span className="text-text-secondary">Price Target</span>
                  <span className="font-mono text-text-primary">{stock.price_target}</span>
                </div>
              )}
              
              {stock.moat_rating && (
                <div className="flex justify-between">
                  <span className="text-text-secondary">Moat Rating</span>
                  <span className="font-bold text-warning">{stock.moat_rating}/5</span>
                </div>
              )}
            </div>
            
            {/* Buy Signal */}
            {stock.conviction_score && stock.conviction_score >= 7 && stock.price_zone && ['DEEP_VALUE', 'BUY_ZONE', 'ACCUMULATE'].includes(stock.price_zone) && (
              <div className="mt-4 p-3 bg-positive/20 border border-positive/50 rounded-lg">
                <div className="flex items-center gap-2 text-positive font-bold">
                  <Target className="w-4 h-4" />
                  Strong Buy Signal
                </div>
                <p className="text-positive/90 text-sm mt-1">
                  High score ({stock.conviction_score}/10) + undervalued zone. Consider initiating position.
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
          setSuccess(
            result.missing_avg_cost?.length
              ? `Imported ${result.positions_created} positions. ⚠️ Bez nákupní ceny: ${result.missing_avg_cost.join(', ')} — doplň je v detailu pozice.`
              : `Imported ${result.positions_created} positions successfully!`
          );
          onSuccess();
          setTimeout(() => onClose(), 1500);
        } catch {
          setError('Portfolio created, but CSV upload failed. Try importing again.');
          onSuccess(); // Still refresh to show new portfolio
        }
      } else {
        setSuccess(`Portfolio "${portfolio.name}" created! Now select a CSV file.`);
        onSuccess();
      }
    } catch {
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
        setSuccess(
          result.missing_avg_cost?.length
            ? `Imported ${result.positions_created} new, updated ${result.positions_updated}. ⚠️ Bez nákupní ceny: ${result.missing_avg_cost.join(', ')} — doplň je v detailu pozice.`
            : `Imported ${result.positions_created} new, updated ${result.positions_updated} positions`
        );
        setTimeout(() => {
          onSuccess();
          onClose();
        }, result.missing_avg_cost?.length ? 4000 : 1500);
      } else {
        setError(result.message || 'Import failed');
      }
    } catch {
      setError('Upload failed. Check file format.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-surface-base/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-surface-base border border-positive/50 rounded-2xl w-full max-w-lg">
        <div className="p-4 border-b border-border flex items-center justify-between">
          <h2 className="text-xl font-bold text-text-primary flex items-center gap-2">
            <FileSpreadsheet className="w-5 h-5 text-positive" />
            Import Portfolio CSV
          </h2>
          <button onClick={onClose} className="p-2 hover:bg-surface-raised rounded-lg">
            <X className="w-5 h-5 text-text-secondary" />
          </button>
        </div>
        
        <div className="p-4 space-y-4">
          {/* Broker Selection */}
          <div>
            <label className="text-sm text-text-secondary block mb-2">Broker</label>
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
                      ? 'bg-positive text-text-primary'
                      : 'bg-surface-hover text-text-secondary hover:bg-surface-active'
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
              <label className="text-sm text-text-secondary block mb-2">Target Portfolio</label>
              <div className="flex gap-2">
                <select
                  value={selectedPortfolioId || ''}
                  onChange={(e) => setSelectedPortfolioId(Number(e.target.value))}
                  className="flex-1 px-4 py-2 bg-surface-raised border border-border rounded-lg text-text-primary focus:outline-none focus:border-positive"
                >
                  {portfolios.map((p) => (
                    <option key={p.portfolio.id} value={p.portfolio.id}>
                      {p.portfolio.name} ({p.portfolio.owner})
                    </option>
                  ))}
                </select>
                <button
                  onClick={() => setShowNewPortfolio(true)}
                  className="px-3 py-2 bg-surface-hover hover:bg-surface-active rounded-lg text-text-secondary"
                >
                  <Plus className="w-5 h-5" />
                </button>
              </div>
            </div>
          ) : (
            <div className="space-y-3 p-3 bg-surface-raised/50 rounded-lg border border-border">
              <div className="text-sm text-text-secondary font-medium">Create New Portfolio</div>
              <input
                type="text"
                value={newPortfolioName}
                onChange={(e) => setNewPortfolioName(e.target.value)}
                placeholder="Portfolio name (e.g., Main, Wife, Kids)"
                className="w-full px-4 py-2 bg-surface-raised border border-border rounded-lg text-text-primary placeholder-text-muted focus:outline-none focus:border-positive"
              />
              <input
                type="text"
                value={newPortfolioOwner}
                onChange={(e) => setNewPortfolioOwner(e.target.value)}
                placeholder="Owner name (optional)"
                className="w-full px-4 py-2 bg-surface-raised border border-border rounded-lg text-text-primary placeholder-text-muted focus:outline-none focus:border-positive"
              />
              <div className="flex gap-2">
                <button
                  onClick={handleCreatePortfolio}
                  disabled={loading || !newPortfolioName.trim()}
                  className="flex-1 px-4 py-2 bg-positive hover:bg-positive/80 disabled:bg-surface-active text-text-primary rounded-lg font-medium"
                >
                  Create Portfolio
                </button>
                {portfolios.length > 0 && (
                  <button
                    onClick={() => setShowNewPortfolio(false)}
                    className="px-4 py-2 bg-surface-hover text-text-secondary rounded-lg"
                  >
                    Cancel
                  </button>
                )}
              </div>
            </div>
          )}

          {/* File Upload */}
          <div>
            <label className="text-sm text-text-secondary block mb-2">CSV File</label>
            <div
              onClick={() => fileInputRef.current?.click()}
              className={`border-2 border-dashed rounded-lg p-6 text-center cursor-pointer transition-colors ${
                file 
                  ? 'border-positive bg-positive/10' 
                  : 'border-border hover:border-border-strong bg-surface-raised/50'
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
                <div className="flex items-center justify-center gap-2 text-positive">
                  <FileSpreadsheet className="w-6 h-6" />
                  <span className="font-medium">{file.name}</span>
                </div>
              ) : (
                <div className="text-text-secondary">
                  <Upload className="w-8 h-8 mx-auto mb-2" />
                  <p>Click to select CSV file</p>
                  <p className="text-xs text-text-muted mt-1">
                    Export from {broker === 'DEGIRO' ? 'DEGIRO' : broker === 'T212' ? 'Trading 212' : 'XTB'}
                  </p>
                </div>
              )}
            </div>
          </div>

          {/* Error/Success Messages */}
          {error && (
            <div className="p-3 bg-negative/10 border border-negative/50 rounded-lg text-negative text-sm">
              {error}
            </div>
          )}
          {success && (
            <div className="p-3 bg-positive/10 border border-positive/50 rounded-lg text-positive text-sm">
              {success}
            </div>
          )}
        </div>

        <div className="p-4 border-t border-border flex gap-3 justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 text-text-secondary hover:text-text-primary transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleUpload}
            disabled={!file || !selectedPortfolioId || loading}
            className="px-6 py-2 bg-positive hover:bg-positive/80 disabled:bg-surface-active text-text-primary font-bold rounded-lg transition-colors flex items-center gap-2"
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
    } catch {
      setError('Failed to add position');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-surface-base/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-surface-base border border-border rounded-2xl w-full max-w-md">
        <div className="p-4 border-b border-border flex items-center justify-between">
          <h2 className="text-xl font-bold text-text-primary flex items-center gap-2">
            <Plus className="w-5 h-5 text-accent" />
            Add Position Manually
          </h2>
          <button onClick={onClose} className="p-2 hover:bg-surface-raised rounded-lg">
            <X className="w-5 h-5 text-text-secondary" />
          </button>
        </div>
        
        <div className="p-4 space-y-4">
          {portfolios.length === 0 ? (
            <div className="p-4 bg-warning/10 border border-warning/50 rounded-lg text-warning text-sm">
              <AlertTriangle className="w-5 h-5 inline mr-2" />
              No portfolios yet. Import a CSV first to create a portfolio.
            </div>
          ) : (
            <>
              {/* Portfolio Selection */}
              <div>
                <label className="text-sm text-text-secondary block mb-2">Portfolio</label>
                <select
                  value={selectedPortfolioId || ''}
                  onChange={(e) => setSelectedPortfolioId(Number(e.target.value))}
                  className="w-full px-4 py-2 bg-surface-raised border border-border rounded-lg text-text-primary focus:outline-none focus:border-accent"
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
                <label className="text-sm text-text-secondary block mb-2">Ticker Symbol</label>
                <input
                  type="text"
                  value={ticker}
                  onChange={(e) => setTicker(e.target.value.toUpperCase())}
                  placeholder="e.g., GKPRF"
                  className="w-full px-4 py-2 bg-surface-raised border border-border rounded-lg text-text-primary placeholder-text-muted focus:outline-none focus:border-accent"
                />
              </div>

              {/* Shares & Cost */}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-sm text-text-secondary block mb-2">Shares</label>
                  <input
                    type="number"
                    step="0.01"
                    value={shares}
                    onChange={(e) => setShares(e.target.value)}
                    placeholder="100"
                    className="w-full px-4 py-2 bg-surface-raised border border-border rounded-lg text-text-primary placeholder-text-muted focus:outline-none focus:border-accent"
                  />
                </div>
                <div>
                  <label className="text-sm text-text-secondary block mb-2">Avg. Cost ($)</label>
                  <input
                    type="number"
                    step="0.01"
                    value={avgCost}
                    onChange={(e) => setAvgCost(e.target.value)}
                    placeholder="1.50"
                    className="w-full px-4 py-2 bg-surface-raised border border-border rounded-lg text-text-primary placeholder-text-muted focus:outline-none focus:border-accent"
                  />
                </div>
              </div>

              {/* Current Price (Optional) */}
              <div>
                <label className="text-sm text-text-secondary block mb-2">Current Price (optional)</label>
                <input
                  type="number"
                  step="0.01"
                  value={currentPrice}
                  onChange={(e) => setCurrentPrice(e.target.value)}
                  placeholder="Leave empty to use avg. cost"
                  className="w-full px-4 py-2 bg-surface-raised border border-border rounded-lg text-text-primary placeholder-text-muted focus:outline-none focus:border-accent"
                />
              </div>
            </>
          )}

          {/* Error/Success Messages */}
          {error && (
            <div className="p-3 bg-negative/10 border border-negative/50 rounded-lg text-negative text-sm">
              {error}
            </div>
          )}
          {success && (
            <div className="p-3 bg-positive/10 border border-positive/50 rounded-lg text-positive text-sm">
              {success}
            </div>
          )}
        </div>

        <div className="p-4 border-t border-border flex gap-3 justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 text-text-secondary hover:text-text-primary transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={loading || portfolios.length === 0}
            className="px-6 py-2 bg-accent hover:bg-accent disabled:bg-surface-active text-text-primary font-bold rounded-lg transition-colors flex items-center gap-2"
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
  onSubmit: (transcript: string, ticker?: string, sourceType?: 'text' | 'youtube' | 'google-docs', url?: string) => void;
}

const NewAnalysisModal: React.FC<NewAnalysisModalProps> = ({ onClose, onSubmit }) => {
  const [inputType, setInputType] = useState<'text' | 'youtube' | 'google-docs'>('text');
  const [transcript, setTranscript] = useState('');
  const [url, setUrl] = useState('');
  const [ticker, setTicker] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async () => {
    setError(null);
    
    if (inputType === 'text' && !transcript.trim()) {
      setError('Please enter transcript text');
      return;
    }
    if ((inputType === 'youtube' || inputType === 'google-docs') && !url.trim()) {
      setError('Please enter a URL');
      return;
    }
    
    setLoading(true);
    try {
      await onSubmit(transcript, ticker || undefined, inputType, url || undefined);
      onClose();
    } catch {
      setError('Analysis failed. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-surface-base/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-surface-base border border-border rounded-2xl w-full max-w-2xl">
        <div className="p-4 border-b border-border flex items-center justify-between">
          <h2 className="text-xl font-bold text-text-primary flex items-center gap-2">
            <Zap className="w-5 h-5 text-warning" />
            New Deep Due Diligence
          </h2>
          <button onClick={onClose} className="p-2 hover:bg-surface-raised rounded-lg">
            <X className="w-5 h-5 text-text-secondary" />
          </button>
        </div>
        
        <div className="p-4 space-y-4">
          {/* Input Type Selector */}
          <div className="flex gap-2 p-1 bg-surface-raised rounded-lg">
            <button
              onClick={() => setInputType('text')}
              className={`flex-1 py-2 px-3 rounded-md text-sm font-medium transition-colors ${
                inputType === 'text' 
                  ? 'bg-accent text-text-primary' 
                  : 'text-text-secondary hover:text-text-primary'
              }`}
            >
              Text / Transcript
            </button>
            <button
              onClick={() => setInputType('youtube')}
              className={`flex-1 py-2 px-3 rounded-md text-sm font-medium transition-colors ${
                inputType === 'youtube' 
                  ? 'bg-negative text-text-primary' 
                  : 'text-text-secondary hover:text-text-primary'
              }`}
            >
              YouTube
            </button>
            <button
              onClick={() => setInputType('google-docs')}
              className={`flex-1 py-2 px-3 rounded-md text-sm font-medium transition-colors ${
                inputType === 'google-docs' 
                  ? 'bg-accent text-text-primary' 
                  : 'text-text-secondary hover:text-text-primary'
              }`}
            >
              Google Docs
            </button>
          </div>
          
          {/* Error Message */}
          {error && (
            <div className="p-3 bg-negative/20 border border-negative/50 rounded-lg text-negative/80 text-sm">
              {error}
            </div>
          )}
          
          {/* Ticker (optional for all types) */}
          <div>
            <label className="text-sm text-text-secondary block mb-2">Ticker Symbol (optional - auto-detected)</label>
            <input
              type="text"
              value={ticker}
              onChange={(e) => setTicker(e.target.value.toUpperCase())}
              placeholder="e.g. GKPRF"
              className="w-full px-4 py-2 bg-surface-raised border border-border rounded-lg text-text-primary placeholder-text-muted focus:outline-none focus:border-accent"
            />
          </div>
          
          {/* URL Input for YouTube / Google Docs */}
          {(inputType === 'youtube' || inputType === 'google-docs') && (
            <div>
              <label className="text-sm text-text-secondary block mb-2">
                {inputType === 'youtube' ? 'YouTube Video URL' : 'Google Docs URL'}
              </label>
              <input
                type="url"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder={
                  inputType === 'youtube' 
                    ? 'https://www.youtube.com/watch?v=...' 
                    : 'https://docs.google.com/document/d/...'
                }
                className="w-full px-4 py-2 bg-surface-raised border border-border rounded-lg text-text-primary placeholder-text-muted focus:outline-none focus:border-accent"
              />
              <p className="mt-2 text-xs text-text-muted">
                {inputType === 'youtube' 
                  ? 'AI will automatically transcribe the video and extract stock analysis.' 
                  : 'Make sure the document is shared with "Anyone with the link can view".'}
              </p>
            </div>
          )}
          
          {/* Text Input */}
          {inputType === 'text' && (
            <div>
              <label className="text-sm text-text-secondary block mb-2">Transcript / Research Notes</label>
              <textarea
                value={transcript}
                onChange={(e) => setTranscript(e.target.value)}
                placeholder="Paste earnings call transcript, video notes, or research analysis..."
                rows={10}
                className="w-full px-4 py-3 bg-surface-raised border border-border rounded-lg text-text-primary placeholder-text-muted focus:outline-none focus:border-accent resize-none"
              />
            </div>
          )}
        </div>

        <div className="p-4 border-t border-border flex gap-3 justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 text-text-secondary hover:text-text-primary transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={loading}
            className="px-6 py-2 bg-accent hover:bg-accent disabled:bg-surface-active text-text-primary font-bold rounded-lg transition-colors flex items-center gap-2"
          >
            {loading ? (
              <RefreshCw className="w-4 h-4 animate-spin" />
            ) : (
              <Target className="w-4 h-4" />
            )}
            {loading ? 'Analyzing...' : 'Run Analysis'}
          </button>
        </div>
      </div>
    </div>
  );
};

// ============================================================================
// GOMES LOGIC - Max Allocation Calculator (Frontend Implementation)
// ============================================================================

/**
 * Calculate max allocation cap using Gomes Logic rules.
 * 
 * Base Caps by Asset Class:
 * - ANCHOR: 12%
 * - HIGH_BETA_ROCKET: 8%
 * - BIOTECH_BINARY: 3%
 * - TURNAROUND: 2%
 * - VALUE_TRAP: 0%
 * 
 * Safety Multipliers:
 * - Score < 7: 0.5x
 * - Cash Runway < 6 months: 0.0x (STOP)
 * - Cash Runway < 12 months: 0.7x
 * - Inflection Status = ACTIVE_GOLD_MINE: 1.2x
 */
function calculateMaxAllocationCap(
  stock: Stock | undefined,
  gomesScore: number | null,
  fallbackTarget: number
): number {
  // Wait Time is the canon's loudest refusal — dead money, do not invest.
  // It outranks every cap, including one already stored on the record: the
  // Gatekeeper row carried max_allocation_cap 15 % AND inflection_status
  // WAIT_TIME, and the table made it the #1 buy of the month.
  if (stock?.inflection_status?.toUpperCase() === 'WAIT_TIME') {
    return 0;
  }

  // If stock has pre-calculated cap from backend, use it
  if (stock?.max_allocation_cap) {
    return stock.max_allocation_cap;
  }

  // Determine asset class
  const assetClass = stock?.asset_class?.toUpperCase();
  
  // Base caps by asset class
  let baseCap: number;
  switch (assetClass) {
    case 'ANCHOR':
      baseCap = 12.0;
      break;
    case 'HIGH_BETA_ROCKET':
      baseCap = 8.0;
      break;
    case 'BIOTECH_BINARY':
      baseCap = 3.0;
      break;
    case 'TURNAROUND':
      baseCap = 2.0;
      break;
    case 'VALUE_TRAP':
      baseCap = 0.0;
      break;
    default:
      // Unknown asset class: use score-based fallback
      if (gomesScore !== null && gomesScore >= 9) {
        baseCap = 8.0; // Treat as High Beta Rocket
      } else if (gomesScore !== null && gomesScore >= 7) {
        baseCap = 12.0; // Treat as Anchor
      } else {
        return fallbackTarget; // Use old logic
      }
  }

  // Start with base cap
  let finalCap = baseCap;

  // Safety Multiplier 1: Conviction Score
  if (gomesScore !== null && gomesScore < 7) {
    finalCap *= 0.5; // Reduce by half if low quality
  }

  // Safety Multiplier 2: Cash Runway
  const cashRunway = stock?.cash_runway_months;
  if (cashRunway !== null && cashRunway !== undefined) {
    if (cashRunway < 6) {
      finalCap = 0.0; // HARD STOP - insolvency risk
    } else if (cashRunway < 12) {
      finalCap *= 0.7; // Reduce allocation
    }
  }

  // Safety Multiplier 3: Inflection Status
  const inflectionStatus = stock?.inflection_status?.toUpperCase();
  if (inflectionStatus === 'ACTIVE_GOLD_MINE') {
    finalCap *= 1.2; // Increase allocation for active inflection
  }

  return Math.max(0, finalCap);
}

// ============================================================================
// MAIN DASHBOARD COMPONENT
// ============================================================================

/**
 * Bezpečné čtení seznamu z localStorage.
 *
 * Evidence plateb a dluhů žije jen v prohlížeči — není záloha, není
 * server, git ji nezachrání. Dvě věci proto nesmí nastat:
 *
 *  1. Poškozený záznam nesmí shodit render. Dřív by výjimka z JSON.parse
 *     vzala celou aplikaci, ne jen jednu sekci.
 *  2. Poškozený záznam se nesmí tiše přepsat. Efekt, který stav ukládá
 *     zpátky, by prázdné pole zapsal do klíče a původní data by zmizela
 *     bez možnosti obnovy. Originál se proto odloží pod příponu
 *     `__poskozeno`, odkud se dá zachránit ručně.
 */
function readStoredList<T>(key: string): T[] {
  let raw: string | null = null;
  try {
    raw = window.localStorage.getItem(key);
  } catch {
    return []; // Zakázaná data webu. Číst není z čeho.
  }
  if (!raw) return [];

  try {
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? (parsed as T[]) : [];
  } catch {
    try {
      window.localStorage.setItem(`${key}__poskozeno`, raw);
    } catch {
      /* Odložit se nepovedlo. Aspoň nespadneme. */
    }
    console.error(`Záznam ${key} je poškozený; odložen jako ${key}__poskozeno.`);
    return [];
  }
}

/** Prázdný formulář platby. Stejný tvar pro všech pět knih. */
const PRAZDNA_PLATBA = {
  name: '',
  amount: '',
  date: '',
  monthlyPayment: '',
  creditor: '',
  accountNumber: '',
  variableSymbol: '',
  note: '',
};

export const InvestmentTerminal: React.FC = () => {
  const [loading, setLoading] = useState(true);
  const [portfolios, setPortfolios] = useState<PortfolioSummary[]>([]);
  const [stocks, setStocks] = useState<Stock[]>([]);
  const [exchangeRates, setExchangeRates] = useState<Record<string, number>>({ EUR: 25, USD: 24 });
  /**
   * Pásmo na ticker, tak jak ho spočítal engine.
   *
   * Prázdná mapa znamená „server neodpověděl", ne „žádná akcie nemá pásmo" —
   * proto se ze scházejícího klíče stane NEZNÁMÉ a ne střed.
   */
  const [bandByTicker, setBandByTicker] = useState<Map<string, Band>>(new Map());
  /**
   * Semafor. Zůstává `null`, dokud se opravdu nenačte — `null` se v „Pokynu"
   * čte jako veto, ne jako GREEN. Appka dřív neznala semafor vůbec: sloupec
   * mohl doporučit STRONG BUY i uprostřed ORANŽOVÉ, protože se ho nikdo neptal.
   */
  const [marketAlert, setMarketAlert] = useState<MarketAlert | null>(null);
  const [selectedPosition, setSelectedPosition] = useState<EnrichedPosition | null>(null);
  /** Pozice, u které se právě řeší „už ji nedržím". */
  const [removingPosition, setRemovingPosition] = useState<EnrichedPosition | null>(null);
  const [selectedWatchlistStock, setSelectedWatchlistStock] = useState<Stock | null>(null);
  const [showAnalysisModal, setShowAnalysisModal] = useState(false);
  const [showImportModal, setShowImportModal] = useState(false);
  const [showAddPositionModal, setShowAddPositionModal] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [sortBy, setSortBy] = useState<'weight' | 'score' | 'pl'>('score');
  // Otevírá se na Rozhodnutí, ne na tabulce. Otázka, kvůli které se sem
  // chodí, je „co s tím mám dělat", a tabulka pozic na ni neodpovídá —
  // odpověď byla o jedno kliknutí dál, než kam se člověk podívá.
  const [activeTab, setActiveTab] = useState<'rozhodnuti' | 'portfolio' | 'watchlist' | 'nalezy' | 'modely' | 'cil' | 'splaceni'>('rozhodnuti');
  
  // Cash editing state
  const [isEditingCash, setIsEditingCash] = useState(false);
  const [editCashValue, setEditCashValue] = useState('');
  const [editCashCurrency, setEditCashCurrency] = useState('CZK');
  const [isSavingCash, setIsSavingCash] = useState(false);
  
  // Monthly contribution editing state
  const [isEditingContribution, setIsEditingContribution] = useState(false);
  const [editContributionValue, setEditContributionValue] = useState('');
  const [isSavingContribution, setIsSavingContribution] = useState(false);
  
  // Debt management state
  const [showAddDebtModal, setShowAddDebtModal] = useState(false);
  const [editingDebtId, setEditingDebtId] = useState<number | null>(null);
  const [debtForm, setDebtForm] = useState({
    name: '',
    amount: '',
    date: '',
    monthlyPayment: '',
    creditor: '',
    accountNumber: '',
    variableSymbol: '',
    note: ''
  });
  const [debts, setDebts] = useState<Array<{
    id: number;
    name: string;
    amount: string;
    date: string;
    monthlyPayment: string;
    creditor: string;
    accountNumber: string;
    variableSymbol: string;
    note: string;
  }>>(() => {
    // Load from localStorage on init
    return readStoredList('akcion_debts');
  });
  
  // Šetření Míša state
  const [showAddSavingsModal, setShowAddSavingsModal] = useState(false);
  const [editingSavingsId, setEditingSavingsId] = useState<number | null>(null);
  const [savingsForm, setSavingsForm] = useState({
    name: '',
    amount: '',
    date: '',
    monthlyPayment: '',
    creditor: '',
    accountNumber: '',
    variableSymbol: '',
    note: ''
  });
  const [savings, setSavings] = useState<Array<{
    id: number;
    name: string;
    amount: string;
    date: string;
    monthlyPayment: string;
    creditor: string;
    accountNumber: string;
    variableSymbol: string;
    note: string;
  }>>(() => {
    // Load from localStorage on init
    return readStoredList('akcion_savings');
  });
  
  // Save debts to localStorage whenever they change
  useEffect(() => {
    localStorage.setItem('akcion_debts', JSON.stringify(debts));
  }, [debts]);
  
  // Save savings to localStorage whenever they change
  useEffect(() => {
    localStorage.setItem('akcion_savings', JSON.stringify(savings));
  }, [savings]);
  
  // Společné platby state
  const [showAddSharedPaymentsModal, setShowAddSharedPaymentsModal] = useState(false);
  const [editingSharedPaymentsId, setEditingSharedPaymentsId] = useState<number | null>(null);
  const [sharedPaymentsForm, setSharedPaymentsForm] = useState({
    name: '',
    amount: '',
    date: '',
    monthlyPayment: '',
    creditor: '',
    accountNumber: '',
    variableSymbol: '',
    note: ''
  });
  const [sharedPayments, setSharedPayments] = useState<Array<{
    id: number;
    name: string;
    amount: string;
    date: string;
    monthlyPayment: string;
    creditor: string;
    accountNumber: string;
    variableSymbol: string;
    note: string;
  }>>(() => {
    // Load from localStorage on init
    return readStoredList('akcion_shared_payments');
  });
  
  // Save shared payments to localStorage whenever they change
  useEffect(() => {
    localStorage.setItem('akcion_shared_payments', JSON.stringify(sharedPayments));
  }, [sharedPayments]);
  
  // Platby Tom state
  const [showAddTomPaymentsModal, setShowAddTomPaymentsModal] = useState(false);
  const [editingTomPaymentsId, setEditingTomPaymentsId] = useState<number | null>(null);
  const [tomPaymentsForm, setTomPaymentsForm] = useState({
    name: '',
    amount: '',
    date: '',
    monthlyPayment: '',
    creditor: '',
    accountNumber: '',
    variableSymbol: '',
    note: ''
  });
  const [tomPayments, setTomPayments] = useState<Array<{
    id: number;
    name: string;
    amount: string;
    date: string;
    monthlyPayment: string;
    creditor: string;
    accountNumber: string;
    variableSymbol: string;
    note: string;
  }>>(() => {
    // Load from localStorage on init
    return readStoredList('akcion_tom_payments');
  });
  
  // Save Tom payments to localStorage whenever they change
  useEffect(() => {
    localStorage.setItem('akcion_tom_payments', JSON.stringify(tomPayments));
  }, [tomPayments]);
  
  // Platby Míša state
  const [showAddMisaPaymentsModal, setShowAddMisaPaymentsModal] = useState(false);
  const [editingMisaPaymentsId, setEditingMisaPaymentsId] = useState<number | null>(null);
  const [misaPaymentsForm, setMisaPaymentsForm] = useState({
    name: '',
    amount: '',
    date: '',
    monthlyPayment: '',
    creditor: '',
    accountNumber: '',
    variableSymbol: '',
    note: ''
  });
  const [misaPayments, setMisaPayments] = useState<Array<{
    id: number;
    name: string;
    amount: string;
    date: string;
    monthlyPayment: string;
    creditor: string;
    accountNumber: string;
    variableSymbol: string;
    note: string;
  }>>(() => {
    // Load from localStorage on init
    return readStoredList('akcion_misa_payments');
  });
  
  // Save Míša payments to localStorage whenever they change
  useEffect(() => {
    localStorage.setItem('akcion_misa_payments', JSON.stringify(misaPayments));
  }, [misaPayments]);
  
  // Available currencies for cash
  const CASH_CURRENCIES = ['CZK', 'EUR', 'USD', 'CAD', 'GBP'];
  
  const [showIntakeModal, setShowIntakeModal] = useState(false);
  
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

        // Pásma. Selhání tady nesmí shodit portfolio — sloupec zůstane
        // prázdný, což je poctivější než dopočítat ho v prohlížeči.
        try {
          const ladder = await apiClient.getLadder();
          setBandByTicker(new Map(ladder.items.map((i) => [i.ticker, i.band])));
        } catch {
          console.warn('Žebřík pásem se nenačetl — sloupec Pásmo zůstane prázdný');
        }

        // Semafor. Selhání nechává marketAlert na `null` — Pokyn to čte jako
        // veto, nikdy jako GREEN.
        try {
          const status = await apiClient.getMarketStatus();
          setMarketAlert(status.status as MarketAlert);
        } catch {
          console.warn('Semafor se nenačetl — Pokyn nesmí nabízet nákup bez něj');
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

        // Fetch stocks for Gomes data (with enriched price lines & zones)
        const stocksData = await apiClient.getEnrichedStocks();
        setStocks(stocksData.stocks);

        // Rozdíly portfolií si načítá PortfolioDiffCard sám, až když si
        // člověk tu odrážku otevře. Tady to byl dotaz na každé spuštění
        // aplikace pro panel, který se většinou nezobrazil.
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

    // First pass: calculate total value and monthly contribution
    let totalMonthlyContribution = 0;
    for (const portfolio of portfolios) {
      totalValue += portfolio.total_market_value || 0;
      totalCash += portfolio.cash_balance || 0;
      // Sum up monthly contributions from all portfolios
      totalMonthlyContribution += portfolio.portfolio.monthly_contribution ?? 0;
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
        // Napříč burzami: pozice KUYA.V najde analýzu vedenou jako KUYAF.
        // Když jsou řádky dva, vyhraje ten od Gomese — viz lib/tickers.ts.
        const stock = pickAnalysis(stocks, pos);
        const gomesScore = stock?.conviction_score ?? null;
        
        // 1. Cílová váha podle skóre (Target Weight)
        const targetWeightPct = getTargetWeight(gomesScore);
        
        // 2. Aktuální váha v portfoliu (cost_basis may be null: unknown buy price)
        const positionValueOriginal = pos.market_value > 0 ? pos.market_value : (pos.cost_basis ?? 0);
        const positionCurrency = pos.currency || 'CZK';
        const currencyRate = exchangeRates[positionCurrency] || 1;
        const positionValueCZK = positionValueOriginal * currencyRate;
        const currentWeightPct = grandTotal > 0 ? (positionValueCZK / grandTotal) * 100 : 0;
        
        // Calculate max_allocation_cap using Gomes Logic
        const maxAllocationCap = calculateMaxAllocationCap(stock, gomesScore, targetWeightPct);
        
        // 3. GAP ANALYSIS - Kolik CZK chybí/přebývá
        // Gap = (Total_AUM * Max_Allocation_Cap) - Current_Value
        // Uses max_allocation_cap (dynamic from Gomes Logic) instead of targetWeightPct
        const targetValueCZK = (grandTotal * maxAllocationCap) / 100;
        const gapCZK = targetValueCZK - positionValueCZK;
        
        // 4. Action signal — but only if the analysis is one we still trust
        const analysisState = getAnalysisState(stock, gomesScore);
        const actionSignal = getActionSignal(
          gomesScore, currentWeightPct, maxAllocationCap, analysisState.usable
        );
        
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

        // Calculate optimal_size for OVERWEIGHT positions (how much to SELL)
        let initialOptimalSize = 0;
        if (currentWeightPct > maxAllocationCap && gapCZK < 0) {
          // OVERWEIGHT: optimal_size = negative (amount to SELL in CZK)
          initialOptimalSize = Math.round(gapCZK); // gapCZK is already negative
        }

        const posBand =
          bandByTicker.get(pos.ticker) ??
          (pos.canonical_ticker ? bandByTicker.get(pos.canonical_ticker) : undefined) ??
          (stock?.ticker ? bandByTicker.get(stock.ticker) : undefined) ??
          (stock?.canonical_ticker ? bandByTicker.get(stock.canonical_ticker) : undefined);

        const enriched: EnrichedPosition = {
          ...pos,
          stock,
          conviction_score: gomesScore,
          max_allocation_cap: maxAllocationCap,
          target_weight_pct: maxAllocationCap,
          weight_in_portfolio: currentWeightPct,
          gap_czk: gapCZK,
          optimal_size: initialOptimalSize, // Negative for OVERWEIGHT, will be recalculated for UNDERWEIGHT
          allocation_priority: 999, // Will be set after sorting
          trend_status: bandToTrend(posBand),
          band: posBand,
          is_deteriorated: analysisState.usable && gomesScore !== null && gomesScore < 4,
          // "Overweight" against a target we could not compute is not a fact
          // about the position, it is a fact about our data.
          is_overweight: analysisState.usable && currentWeightPct > maxAllocationCap,
          is_underweight:
            analysisState.usable &&
            currentWeightPct < maxAllocationCap &&
            gapCZK > MIN_INVESTMENT_CZK,
          action_signal: actionSignal,
          analysis_usable: analysisState.usable,
          analysis_note: analysisState.note,
          // The real phase, not a constant. This field was pinned to
          // 'UPCOMING', so a WAIT_TIME record never showed as one.
          inflection_status: stock?.inflection_status ?? undefined,
          next_catalyst:
            stock?.next_catalyst ??
            stock?.primary_catalyst ??
            (stock?.catalysts ? stock.catalysts.split(',')[0].trim() : undefined),
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
      .filter(p => p.conviction_score !== null && p.conviction_score >= 5 && p.gap_czk > 0)
      .sort((a, b) => {
        // Primary: Higher score = higher priority
        const scoreDiff = (b.conviction_score ?? 0) - (a.conviction_score ?? 0);
        if (scoreDiff !== 0) return scoreDiff;
        // Secondary: Larger gap = higher priority
        return b.gap_czk - a.gap_czk;
      });
    
    // Distribute monthly contribution according to priority
    let remainingBudget = totalMonthlyContribution;
    
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
      // 1. Don't exceed max_allocation_cap (dynamic from Gomes Logic: 3-15%)
      const currentValueCZK = (grandTotal * pos.weight_in_portfolio) / 100;
      const maxAllowedValue = (grandTotal * pos.max_allocation_cap) / 100;
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
      monthlyContribution: totalMonthlyContribution,
      portfolios,
      allPositions,
      rocketCount,
      anchorCount,
      waitTimeCount,
      unanalyzedCount,
      riskScore,
    };
  }, [portfolios, stocks, exchangeRates, bandByTicker]);

  // Pozice, jejichž měnu appka neumí přepočítat na koruny — součty výš je
  // tiše vynechávají. Prázdné dnes pro všech dvanáct pozic; existuje kvůli
  // incidentu, kdy neznámá měna spadla na výchozí kurz USD a ocenila
  // izraelskou pozici na 3,3násobek skutečné hodnoty.
  const unconvertiblePositions = useMemo(() => {
    // Backend nemá pole `unconvertible_positions` v odpovědi zapojené —
    // bez zálohy na [] vracelo `flatMap` na každé portfolio `undefined`
    // jako jednu položku (flatMap nesplošťuje ne-pole), pole se čtou
    // .ticker na undefined a záložka Portfolio spadla na prázdnou obrazovku.
    return portfolios.flatMap((p) => p.unconvertible_positions ?? []);
  }, [portfolios]);

  // Které firmy držíme — kanonicky, ne podle zápisu tickeru. Bez toho se
  // KUYAF ukazovalo mezi sledovanými, přestože KUYA.V je v portfoliu.
  const ownedTickers = useMemo(() => {
    return canonicalSet(familyData.allPositions);
  }, [familyData.allPositions]);

  // Sledované: papíry s analýzou, které nedržíme.
  const watchlistStocks = useMemo(() => {
    return stocks.filter(
      s => !ownedTickers.has(canonicalOf(s)) && s.conviction_score !== null
    );
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
          return (b.conviction_score ?? 0) - (a.conviction_score ?? 0);
        case 'pl':
          return (b.unrealized_pl_percent ?? 0) - (a.unrealized_pl_percent ?? 0);
        default:
          return 0;
      }
    });

    return filtered;
  }, [familyData.allPositions, searchQuery, sortBy]);

  /**
   * Které nepovinné sloupce vůbec nakreslit.
   *
   * Skóre bylo prázdné u třinácti řádků z patnácti, optimální dávka
   * a katalyzátor u čtrnácti, pásmo u dvanácti. Čtyřicet procent tabulky
   * byly pomlčky — a každá z nich přidávala řádku výšku, kvůli které se
   * portfolio nevešlo na obrazovku.
   *
   * Sloupec se ukáže, jakmile pro něj má data aspoň jedna pozice. Nic se
   * neskrývá natrvalo: zmizí přesně to, o čem aplikace nic neví.
   */
  const columns: PositionColumns = useMemo(() => {
    /*
     * Doplňkový sloupec má smysl, až když ho vyplní aspoň pětina řádků.
     *
     * Pravidlo „stačí jedna pozice" nechalo stát sloupec Katalyzátor s
     * jediným záznamem ze čtrnácti a Pásmo se třemi — dva svislé pruhy
     * pomlček přes celou tabulku. Údaj se neztrácí, je v detailu pozice;
     * jen nedělá sloupec tam, kde ho nemá čím naplnit.
     */
    const alesponPetina = (test: (p: EnrichedPosition) => boolean) => {
      const kolik = displayedPositions.filter(test).length;
      return kolik > 0 && kolik >= Math.ceil(displayedPositions.length / 5);
    };

    return {
      /* Skóre a dávka jsou vlastní výstupy aplikace. Ty se kreslí, jakmile
         existuje aspoň jeden — na nich se rozhoduje. */
      score: displayedPositions.some((p) => p.analysis_usable && p.conviction_score != null),
      size: displayedPositions.some((p) => (p.optimal_size ?? 0) > 0),
      catalyst: alesponPetina((p) => Boolean(p.next_catalyst)),
      band: alesponPetina(
        (p) => p.stock?.green_line != null || p.stock?.red_line != null,
      ),
      freeride: alesponPetina(
        (p) => p.unrealized_pl_percent != null && p.unrealized_pl_percent > 0,
      ),
      earnings: alesponPetina((p) => Boolean(p.earnings)),
      analysisNote: displayedPositions.some((p) => p.analysis_usable),
      action: displayedPositions.some((p) => p.analysis_usable),
    };
  }, [displayedPositions]);

  /** Kolik sloupců se opravdu kreslí — pro colSpan prázdného řádku.
      Šest napevno: symbol, pokyn, váha, cena, P/L a sloupec s akcí. */
  const columnCount = 6
    + (columns.score ? 1 : 0)
    + (columns.size ? 1 : 0)
    + (columns.catalyst ? 1 : 0)
    + (columns.band ? 1 : 0)
    + (columns.freeride ? 1 : 0)
    + (columns.earnings ? 1 : 0);

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
    filtered.sort((a, b) => (b.conviction_score ?? 0) - (a.conviction_score ?? 0));

    return filtered;
  }, [watchlistStocks, searchQuery]);

  // Handle new analysis
  const handleNewAnalysis = async (
    transcript: string, 
    ticker?: string, 
    sourceType?: 'text' | 'youtube' | 'google-docs',
    url?: string
  ) => {
    try {
      if (sourceType === 'youtube' && url) {
        // YouTube analysis
        await apiClient.analyzeYouTube({ url, speaker: 'Mark Gomes' });
      } else if (sourceType === 'google-docs' && url) {
        // Google Docs analysis
        await apiClient.analyzeGoogleDocs({ url, speaker: 'Mark Gomes' });
      } else {
        // Text/transcript analysis
        await apiClient.runDeepDD(transcript, ticker);
      }
      // Refresh data
      const stocksData = await apiClient.getEnrichedStocks();
      setStocks(stocksData.stocks);
    } catch (err) {
      console.error('Analysis failed:', err);
      throw err; // Re-throw to show error in modal
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-surface-base flex items-center justify-center">
        <div className="text-center">
          <RefreshCw className="w-12 h-12 text-accent animate-spin mx-auto mb-4" />
          <p className="text-text-secondary">Loading portfolio data...</p>
        </div>
      </div>
    );
  }

  /* ====================================================================
     SKOŘÁPKA, KTERÁ NESCROLLUJE

     Stránka měla 1 791 px na obrazovce vysoké 1 000. Zkracovat obsah do
     nekonečna nejde — dřív nebo později se dlouhý seznam nevejde vždycky.
     Scrolluje proto to, co scrollovat má: tabulka pozic ve svém rámu a
     podklady ve svém pruhu. Okno samo stojí.

     Prakticky to znamená `h-screen` a `overflow-hidden` tady nahoře a
     `min-h-0` na každém článku řetězu dolů — bez něj flexbox nedovolí
     dítěti být menší než jeho obsah a scrollování propadne až na stránku.
  ==================================================================== */
  return (
    <div className="flex h-screen overflow-hidden bg-surface-base text-text-primary">

      {/* Navigace vlevo. Svislé místo je v aplikaci vzácné, vodorovné ne. */}
      <SideRail
        active={activeTab}
        onSelect={setActiveTab}
        onOpenIntake={() => setShowIntakeModal(true)}
        positionCount={familyData.allPositions.length}
        watchlistCount={watchlistStocks.length}
      />

      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
      {/* HEADER */}
      {/* ==================================================================
          HLAVIČKA — jeden pruh, ne třetina obrazovky

          Předtím tu byly čtyři karty pod řádkem se značkou: 253 px, tedy
          čtvrtina obrazovky na údaje, které se vejdou na jednu řádku.
          Podrobnosti nezmizely — postup k cíli je tenká linka pod částkou
          a celá věta ve vysvětlivce, rozpad rizika se přesunul do těla
          stránky, kde je na něj místo.
      ================================================================== */}
      <header className="shrink-0 border-b border-border-subtle bg-surface-base">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-2.5">

          <div className="flex items-center gap-2.5">
            <Shield className="h-6 w-6 text-accent" aria-hidden="true" />
            <h1 className="font-display text-[17px] font-extrabold uppercase tracking-[0.10em] [font-stretch:78%]">
              Akcion
            </h1>
          </div>

          <span className="hidden h-5 w-px bg-border sm:block" aria-hidden="true" />

          {/* Hodnota portfolia. Postup k cíli je tenká linka pod číslem —
              na periferní vidění to stačí, věta je ve vysvětlivce. */}
          <div
            className="flex flex-col"
            title={(() => {
              const months = calculateMonthsToTarget(
                familyData.totalValue, 500000, familyData.monthlyContribution, 0.15,
              );
              if (months <= 0) return 'Cíl 500 tis. Kč je splněn.';
              if (!Number.isFinite(months)) {
                return familyData.monthlyContribution > 0
                  ? 'Při tomhle vkladu se cíl 500 tis. Kč do dvaceti let nesplní.'
                  : 'Žádný účet nemá zadaný měsíční vklad, takže se cíl neplní.';
              }
              const years = Math.floor(months / 12);
              const rest = months % 12;
              const casti = [
                years > 0 ? `${years} ${plural(years, 'rok', 'roky', 'let')}` : '',
                rest > 0 ? `${rest} ${plural(rest, 'měsíc', 'měsíce', 'měsíců')}` : '',
              ].filter(Boolean).join(' a ');
              return `Do cíle 500 tis. Kč zbývá ${casti} při 15 % ročně a vkladu `
                + `${formatCurrency(familyData.monthlyContribution)} měsíčně.`;
            })()}
          >
            <div className="flex items-baseline gap-2">
              <span className="font-mono text-[17px] font-medium tabular-nums text-text-primary">
                {formatCurrency(familyData.totalValue)}
              </span>
              {/* Nerealizovaný výsledek. Dřív byl až uprostřed stránky ve
                  čtveřici karet, které zbytek jen opakovaly hlavičku. Je to
                  nejdůležitější číslo na obrazovce a patří vedle celku. */}
              {(() => {
                const t = portfolios.reduce((a, x) => ({
                  cost: a.cost + (x.total_cost_basis || 0),
                  pl: a.pl + (x.total_unrealized_pl || 0),
                }), { cost: 0, pl: 0 });
                if (t.cost <= 0) return null;
                const pct = (t.pl / t.cost) * 100;
                const down = t.pl < 0;
                return (
                  <span
                    className={`font-mono text-[13px] tabular-nums ${down ? 'text-negative' : 'text-positive'}`}
                    title={`Pořizovací cena ${formatCurrency(t.cost)}`}
                  >
                    {down ? '' : '+'}{formatCurrency(t.pl)} ({percent(pct, { sign: true })})
                  </span>
                );
              })()}
              <span className="font-mono text-[11px] text-text-muted">
                ≈ €{familyData.totalValueEUR.toLocaleString('cs-CZ', { maximumFractionDigits: 0 })}
              </span>
            </div>
            <div className="mt-1 h-[3px] w-full overflow-hidden rounded-full bg-surface-active">
              <div
                className="h-full bg-accent"
                style={{ width: `${Math.min(100, (familyData.totalValue / 500000) * 100)}%` }}
              />
            </div>
          </div>

          {/* Hotovost. Klik přepne na úpravu přímo v pruhu — chování
              zůstalo stejné, jen se vešlo na řádek. */}
          {isEditingCash ? (
            <div className="flex items-center gap-1.5">
              <input
                type="number"
                value={editCashValue}
                onChange={(e) => setEditCashValue(e.target.value)}
                className="w-28 rounded-input border border-accent/50 bg-surface-hover px-2 py-1 font-mono text-[13px] text-text-primary focus:border-accent focus:outline-none"
                placeholder="0"
                autoFocus
              />
              <select
                value={editCashCurrency}
                onChange={(e) => setEditCashCurrency(e.target.value)}
                className="rounded-input border border-border bg-surface-hover px-1.5 py-1 text-[12px] text-text-primary focus:border-accent focus:outline-none"
              >
                {CASH_CURRENCIES.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
              <button
                onClick={async () => {
                  const amount = parseFloat(editCashValue);
                  if (isNaN(amount) || amount < 0) return;
                  setIsSavingCash(true);
                  try {
                    let amountInCZK = amount;
                    if (editCashCurrency !== 'CZK') {
                      const rate = exchangeRates[editCashCurrency] || 1;
                      amountInCZK = amount * rate;
                    }
                    // Jen jedno portfolio. Při dvou by se sem uložil součet
                    // hotovosti obou lidí do účtu toho prvního — pole se proto
                    // v tom případě vůbec nedá otevřít (viz spouštěč níž).
                    if (portfolios.length === 1) {
                      await apiClient.updateCashBalance(portfolios[0].portfolio.id, amountInCZK);
                      await refreshPortfolios();
                    }
                    setIsEditingCash(false);
                  } catch (err) {
                    console.error('Uložení hotovosti selhalo:', err);
                  } finally {
                    setIsSavingCash(false);
                  }
                }}
                disabled={isSavingCash}
                className="rounded-input border border-positive-border bg-positive-bg p-1.5 text-positive disabled:opacity-40"
                title="Uložit"
              >
                {isSavingCash ? <RefreshCw className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />}
              </button>
              <button
                onClick={() => setIsEditingCash(false)}
                className="rounded-input border border-border p-1.5 text-text-muted hover:text-text-primary"
                title="Zrušit"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
          ) : (
            /*
             * Číslo je součet hotovosti přes všechna portfolia, ale zápis umí
             * mířit jen do jednoho. Dokud je portfolio jediné, je to totéž a
             * úprava rovnou v pruhu dává smysl. Jakmile jsou dvě, uložení by
             * hodilo součet obou lidí na účet toho prvního — tichý přesun cizí
             * hotovosti. Proto se tužka schová a upravuje se po účtech
             * v záložce Portfolia, kde zápis a čtení míří na tentýž řádek.
             */
            (() => {
              const jedine = portfolios.length === 1;
              const rozpis = portfolios
                .map((p) => `${p.portfolio.owner}: ${formatCurrency(p.cash_balance || 0)}`)
                .join(' · ');
              const obsah = (
                <>
                  <span className="eyebrow text-text-muted">hotovost</span>
                  <span className="font-mono text-[13px] tabular-nums text-text-primary">
                    {formatCurrency(familyData.totalCash)}
                  </span>
                  <span className="font-mono text-[11px] text-text-muted">
                    {percent(familyData.totalValue > 0 ? (familyData.totalCash / familyData.totalValue) * 100 : 0)}
                  </span>
                </>
              );

              return jedine ? (
                <button
                  onClick={() => {
                    setEditCashValue((portfolios[0].cash_balance || 0).toString());
                    setEditCashCurrency('CZK');
                    setIsEditingCash(true);
                  }}
                  className="group flex items-center gap-1.5 rounded-button border border-border px-2.5 py-1 text-left transition-colors hover:bg-surface-hover"
                  title="Upravit volnou hotovost"
                >
                  {obsah}
                  <Edit3 className="h-3 w-3 text-text-muted opacity-0 transition-opacity group-hover:opacity-100" />
                </button>
              ) : (
                <span
                  className="flex items-center gap-1.5 rounded-button border border-border px-2.5 py-1"
                  title={`${rozpis} — hotovost se upravuje po účtech v záložce Portfolia.`}
                >
                  {obsah}
                </span>
              );
            })()
          )}

          {/* Kolik pozic a kolik z nich aplikace neumí posoudit. */}
          {(() => {
            const celkem = familyData.allPositions.length;
            const bezHodnoceni = familyData.allPositions.filter((p) => !p.analysis_usable).length;
            const vsechny = bezHodnoceni === celkem && celkem > 0;
            return (
              <span
                className={`inline-flex items-center gap-1.5 rounded-button border px-2.5 py-1 ${
                  bezHodnoceni > 0
                    ? 'border-warning-border bg-warning-bg text-warning'
                    : 'border-border text-text-secondary'
                }`}
                title={
                  bezHodnoceni > 0
                    ? 'Bez konvikčního skóre aplikace nespočítá cílové váhy ani nevydá pokyn.'
                    : 'Všechny pozice mají použitelné hodnocení.'
                }
              >
                <span className="font-mono text-[13px] tabular-nums">{celkem}</span>
                <span className="text-[11px]">
                  {plural(celkem, 'pozice', 'pozice', 'pozic')}
                  {/* Kolik z nich je bez hodnocení, stojí v denním seznamu
                      i s důsledkem. Tady by to byla tatáž věta potřetí. */}
                  {bezHodnoceni > 0 && !vsechny && ` · ${bezHodnoceni} bez hodnocení`}
                </span>
              </span>
            );
          })()}

          <div className="ml-auto flex items-center gap-2">
            <ThemeToggle tone="sheet" />

            <NotificationBell
              onNotificationClick={(notification) => {
                if (notification.ticker) {
                  const position = familyData.allPositions.find(
                    (p: EnrichedPosition) => p.ticker === notification.ticker
                  );
                  if (position) {
                    setSelectedPosition(position);
                  }
                }
              }}
            />

            <ClearPortfolioButton portfolios={portfolios} onCleared={refreshPortfolios} />

            <button
              onClick={() => setShowImportModal(true)}
              className="btn-secondary px-3 py-1.5 text-[13px]"
            >
              <Upload className="h-3.5 w-3.5" />
              Import
            </button>

            <button
              onClick={() => setShowAddPositionModal(true)}
              className="btn-secondary px-3 py-1.5 text-[13px]"
            >
              <Plus className="h-3.5 w-3.5" />
              Pozice
            </button>

            <button
              onClick={() => setShowAnalysisModal(true)}
              className="btn-primary px-3 py-1.5 text-[13px]"
            >
              <PlusCircle className="h-4 w-4" />
              Nová analýza
            </button>
          </div>
        </div>
      </header>

      {/* MAIN CONTENT */}
      <main className="flex min-h-0 flex-1 flex-col overflow-hidden px-4 py-3">

        {/* Panel nástrojů — jen pro sledované; u pozic sedí uvnitř sloupce. */}
        {activeTab === 'watchlist' && (
          <div className="flex items-center justify-between mb-3">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted" />
              <input
                type="text"
                placeholder="Hledat mezi sledovanými…"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-10 pr-4 py-2 bg-surface-raised border border-border rounded-lg text-text-primary placeholder-text-muted focus:outline-none focus:border-accent w-64"
              />
            </div>
            
          </div>
        )}

        {/* ==============================================================
            DESKA — verdikt vlevo, pozice vpravo.

            Dřív šlo všechno pod sebe: verdikt, čtyři karty přes celou
            šířku, alokační plán a teprve pak tabulka. Pozice, tedy to
            jediné, co člověk opravdu vlastní, začínaly na 1 919 px —
            po dvou obrazovkách scrollování.

            Verdikt je úzký sloupec, protože je to pár vět. Vedle něj
            je místo na celou tabulku.
        ============================================================== */}
        {/* „Co s tím" — jedna karta na firmu, pokyn pro oba účty. Vlastní
            záložka, protože je to jiná otázka než „co dnes udělat": denní
            seznam ukazuje nejvýš tři věci, tohle ukazuje stanovisko ke všemu,
            co držíte, a dá se to přečíst po třech týdnech bez otevření. */}
        {activeTab === 'rozhodnuti' && (
          <div className="flex min-h-0 flex-1 flex-col">
            <DecisionBoard />
          </div>
        )}

        {activeTab === 'portfolio' && (
          <div className="flex min-h-0 flex-1 flex-col gap-3">
          <div className="grid min-h-0 flex-1 gap-3 min-[1480px]:grid-cols-[352px_minmax(0,1fr)]">

            {/* Levý sloupec: co dnes dělat a na čem portfolio stojí. */}
            <div className="flex min-h-0 min-w-0 flex-col gap-3 overflow-y-auto pr-0.5">
              <DailyActionWidget
                onExecuteAction={(action) => {
                  const pos = displayedPositions.find((p) => p.ticker === action.ticker);
                  if (pos) {
                    setSelectedPosition(pos);
                    return true;
                  }
                  return false;
                }}
                onOpenRozpor={() => setActiveTab('rozhodnuti')}
              />
              <RiskMeter
                rocketCount={familyData.rocketCount}
                anchorCount={familyData.anchorCount}
                waitTimeCount={familyData.waitTimeCount}
                unanalyzedCount={familyData.unanalyzedCount}
                riskScore={familyData.riskScore}
              />
            </div>

            {/* Pravý sloupec: hledání, alokace a pozice. */}
            <div className="flex min-h-0 min-w-0 flex-col gap-3">

              {/* Ovládací pruh: alokační plán vlevo, hledání a řazení
                  vpravo. Hledání mělo dřív vlastní řádek nad plánem —
                  čtyřicet pixelů výšky na dva prvky, které spolu s ním
                  nevyplnily ani polovinu šířky. Tabulka o ten řádek
                  povyrostla. */}
              <div className="flex items-stretch gap-2">

        {/* Gomes Allocation Plan - Monthly Summary */}
        {activeTab === 'portfolio' && (
          <div className="min-w-0 flex-1 p-2.5 bg-surface-raised rounded-card border border-positive/20">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-positive/10 rounded-lg">
                  <Target className="w-5 h-5 text-positive" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-positive uppercase tracking-wider">
                    Měsíční alokační plán
                  </h3>
                  {isEditingContribution ? (
                    <div className="flex items-center gap-2 mt-1">
                      <span className="text-xs text-text-secondary">Rozpočet:</span>
                      <input
                        type="number"
                        value={editContributionValue}
                        onChange={(e) => setEditContributionValue(e.target.value)}
                        className="w-24 px-2 py-1 bg-surface-hover border border-border rounded text-text-primary text-sm font-mono focus:outline-none focus:border-positive"
                        placeholder="20000"
                      />
                      <span className="text-xs text-text-secondary">Kč</span>
                      <button
                        onClick={async () => {
                          const amount = parseFloat(editContributionValue);
                          if (isNaN(amount) || amount < 0) return;
                          setIsSavingContribution(true);
                          try {
                            // Update monthly contribution for all portfolios proportionally
                            // For simplicity, update first portfolio with total amount
                            if (portfolios.length > 0) {
                              const perPortfolio = amount / portfolios.length;
                              for (const p of portfolios) {
                                await apiClient.updateMonthlyContribution(p.portfolio.id, perPortfolio);
                              }
                              await refreshPortfolios();
                            }
                            setIsEditingContribution(false);
                          } catch (err) {
                            console.error('Failed to update contribution:', err);
                          } finally {
                            setIsSavingContribution(false);
                          }
                        }}
                        disabled={isSavingContribution}
                        className="p-1 bg-positive/20 hover:bg-positive/80/30 text-positive rounded transition-colors"
                      >
                        {isSavingContribution ? <RefreshCw className="w-3 h-3 animate-spin" /> : <Check className="w-3 h-3" />}
                      </button>
                      <button
                        onClick={() => setIsEditingContribution(false)}
                        className="p-1 bg-surface-active hover:bg-surface-active text-text-secondary rounded transition-colors"
                      >
                        <X className="w-3 h-3" />
                      </button>
                    </div>
                  ) : (
                    <p className="text-xs text-text-secondary flex items-center gap-2">
                      <span>
                        Rozpočet: <span className="font-bold text-positive">{formatCurrency(familyData.monthlyContribution)}</span>
                      </span>
                      <button
                        onClick={() => {
                          setEditContributionValue(familyData.monthlyContribution.toString());
                          setIsEditingContribution(true);
                        }}
                        className="p-0.5 hover:bg-surface-hover rounded transition-colors"
                        title="Upravit měsíční rozpočet"
                      >
                        <Edit3 className="w-3 h-3 text-text-muted hover:text-positive" />
                      </button>
                      <span className="text-text-muted">|</span>
                      <span>Alokováno: {formatCurrency(familyData.allPositions.reduce((sum, p) => sum + p.optimal_size, 0))}</span>
                      <span className="text-text-muted">|</span>
                      <span>Zbývá: {formatCurrency(familyData.monthlyContribution - familyData.allPositions.reduce((sum, p) => sum + p.optimal_size, 0))}</span>
                    </p>
                  )}
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
                        i === 0 ? 'bg-positive/20 text-positive border border-positive/50' :
                        'bg-surface-hover/50 text-text-secondary'
                      }`}
                    >
                      {pos.action_signal === 'SNIPER' && '[S] '}
                      {pos.ticker}: {formatCurrency(pos.optimal_size)}
                    </div>
                  ))
                }
                {familyData.allPositions.filter(p => p.action_signal === 'SELL').length > 0 && (
                  <div className="px-3 py-1.5 rounded-lg text-xs font-bold bg-negative/20 text-negative border border-negative/50">
                    {familyData.allPositions.filter(p => p.action_signal === 'SELL').length}x PRODAT
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

                <div className="flex shrink-0 items-center gap-2 rounded-card border border-border bg-surface-raised px-2.5">
                  <div className="relative">
                    <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-text-muted" />
                    <input
                      type="text"
                      placeholder="Hledat pozici…"
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      className="w-44 rounded-button border border-border bg-surface-base py-1 pl-8 pr-2 text-[12.5px] text-text-primary placeholder-text-muted focus:border-accent focus:outline-none"
                    />
                  </div>
                  <select
                    value={sortBy}
                    onChange={(e) => setSortBy(e.target.value as 'weight' | 'score' | 'pl')}
                    title="Podle čeho se pozice řadí"
                    className="rounded-button border border-border bg-surface-base px-2 py-1 text-[12.5px] text-text-primary focus:border-accent focus:outline-none"
                  >
                    <option value="score">řadit podle skóre</option>
                    <option value="weight">řadit podle váhy</option>
                    <option value="pl">řadit podle zisku a ztráty</option>
                  </select>
                </div>
              </div>

              {activeTab === 'portfolio' && unconvertiblePositions.length > 0 && (
                <div className="shrink-0 rounded-card border border-warning-border bg-warning-bg px-3 py-2 text-[12.5px] text-warning">
                  Součty výš nepočítají {unconvertiblePositions.length === 1 ? 'jednu pozici' : `${unconvertiblePositions.length} pozice`} —
                  appka nezná kurz pro {unconvertiblePositions.map((u) => u.ticker).join(', ')}.
                </div>
              )}

        {/* Portfolio Table */}
        {activeTab === 'portfolio' && (
        <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-card border border-border-subtle bg-surface-base/50">
        <div className="min-h-0 flex-1 overflow-y-auto">
          <table className="w-full table-fixed">
            <thead className="sticky top-0 z-10 bg-surface-raised">
              <tr className="border-b border-border">
                <Th width="w-[150px]">Symbol</Th>
                <Th
                  width="w-[108px]"
                  hint={columns.action ? undefined : 'Pokyn aplikace vydá, jen když má analýzu. U ostatních pozic zůstane prázdno — proč, stojí v denním seznamu vlevo.'}
                >
                  Pokyn
                </Th>
                <Th width="w-[96px]" sub={columns.action ? 'teď / cíl' : undefined}>Váha</Th>
                {columns.score && (
                  <Th width="w-[62px]" align="center"><Term id="konvikcniSkore">Skóre</Term></Th>
                )}
                <Th width="w-[96px]" align="right">Cena</Th>
                {columns.size && <Th width="w-[128px]" sub="tento měsíc">Dávka</Th>}
                {columns.catalyst && <Th width="w-[118px]">Katalyzátor</Th>}
                {columns.earnings && (
                  <Th
                    width="w-[104px]"
                    hint="Nejbližší výsledky. Uvnitř čtrnácti dnů před nimi brána nákup odmítne. Slovo asi znamená odhad, ne oznámené datum."
                  >
                    Výsledky
                  </Th>
                )}
                {columns.band && (
                  <Th width="w-[88px]" align="center" hint="Kde leží cena v pásmu mezi zelenou a červenou linkou">
                    Pásmo
                  </Th>
                )}
                {columns.freeride && (
                  <Th width="w-[106px]" hint="Kolik chybí do zdvojnásobení, po kterém se podle kánonu vybírá vklad">
                    Do free ride
                  </Th>
                )}
                <Th width="w-[108px]" align="right"><Term id="pl">P/L</Term></Th>
                <Th width="w-[44px]" align="right"><span className="sr-only">Akce</span></Th>
              </tr>
            </thead>
            <tbody>
              {displayedPositions.map((pos) => (
                <PortfolioRow
                  key={`${pos.portfolio_id}-${pos.ticker}`}
                  position={pos}
                  columns={columns}
                  marketAlert={marketAlert}
                  onClick={() => setSelectedPosition(pos)}
                  onRemove={() => setRemovingPosition(pos)}
                />
              ))}
              {displayedPositions.length === 0 && (
                <tr>
                  <td colSpan={columnCount} className="text-center py-12 text-text-muted">
                    {searchQuery
                      ? 'Hledání neodpovídá žádná pozice.'
                      : 'V portfoliu zatím nejsou žádné pozice. Začni importem CSV z DEGIRO.'}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        </div>
        )}

            </div>
          </div>

          {/* Podklady jako odrážky. Zavřené zabírají 38 px; otevřená je
              vždycky jen jedna a scrolluje sama v sobě. */}
          <ContextPanel />
          </div>
        )}

        {/* Watchlist Table */}
        {activeTab === 'watchlist' && (
          <div className="min-h-0 flex-1 overflow-y-auto rounded-card border border-border bg-surface-raised">
            <table className="w-full">
              <thead>
                <tr className="border-b border-border bg-surface-overlay">
                  <th className="text-left py-3 px-4 text-xs font-bold text-text-muted uppercase tracking-wider">Symbol</th>
                  <th className="text-left py-3 px-4 text-xs font-bold text-text-muted uppercase tracking-wider">Firma</th>
                  <th className="text-left py-3 px-4 text-xs font-bold text-text-muted uppercase tracking-wider"><Term id="konvikcniSkore">Skóre</Term></th>
                  <th className="text-left py-3 px-4 text-xs font-bold text-text-muted uppercase tracking-wider">Verdikt</th>
                  <th className="text-left py-3 px-4 text-xs font-bold text-text-muted uppercase tracking-wider">Cenové pásmo</th>
                  <th
                    title="Nejbližší výsledky. Uvnitř čtrnácti dnů před nimi brána nákup odmítne. Slovo asi znamená odhad, ne oznámené datum."
                    className="text-left py-3 px-4 text-xs font-bold text-text-muted uppercase tracking-wider"
                  >
                    Výsledky
                  </th>
                  <th className="text-right py-3 px-4 text-xs font-bold text-text-muted uppercase tracking-wider">Detail</th>
                </tr>
              </thead>
              <tbody>
                {displayedWatchlist.map((stock) => {
                  const scoreColor = stock.conviction_score 
                    ? stock.conviction_score >= 7 ? 'text-positive' 
                      : stock.conviction_score >= 5 ? 'text-warning' 
                      : 'text-negative'
                    : 'text-text-muted';
                  
                  return (
                    <tr 
                      key={stock.id}
                      onClick={() => setSelectedWatchlistStock(stock)}
                      className="border-b border-border-subtle cursor-pointer transition-all hover:bg-surface-hover"
                    >
                      <td className="py-3 px-4">
                        <div className="font-bold text-text-primary text-lg">{stock.ticker}</div>
                      </td>
                      <td className="py-3 px-4">
                        <div className="text-text-secondary text-sm truncate max-w-[200px]">
                          {stock.company_name || 'Unknown'}
                        </div>
                      </td>
                      <td className="py-3 px-4">
                        <div className={`text-2xl font-black ${scoreColor}`}>
                          {stock.conviction_score ?? '-'}
                        </div>
                      </td>
                      <td className="py-3 px-4">
                        <span className={`px-2 py-1 rounded border text-xs font-bold ${verdictTone(stock.action_verdict).pill}`}>
                          {verdictName(stock.action_verdict)}
                        </span>
                      </td>
                      <td className="py-3 px-4">
                        <span className={`px-2 py-1 rounded border text-xs font-medium ${zoneTone(stock.price_zone).pill}`}>
                          {zoneName(stock.price_zone)}
                        </span>
                      </td>
                      <td className="py-3 px-4">
                        <EarningsCell earnings={stock.earnings} />
                      </td>
                      <td className="py-3 px-4 text-right">
                        <button className="px-3 py-1 bg-accent hover:bg-accent/80 text-text-primary text-xs font-bold rounded transition-colors">
                          Otevřít
                        </button>
                      </td>
                    </tr>
                  );
                })}
                {displayedWatchlist.length === 0 && (
                  <tr>
                    <td colSpan={7} className="text-center py-12 text-text-muted">
                      {searchQuery 
                        ? 'No stocks found in watchlist' 
                        : 'Zatím žádná analýza. Novou přidáš tlačítkem „Nová analýza“ v hlavičce.'}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}

        {/* Rozdíly portfolií se přestěhovaly mezi podklady (ContextPanel →
            „Rozdíly portfolií"). Pod tabulkou to byl pruh, který po každém
            otevření aplikace tvrdil, že se něco našlo — přitom dokud druhý
            účet nemá pozice, je „rozdílem" celé portfolio toho prvního. */}

        {/* CÍL — složené úročení, kam to míří a co to znamená.
            Nahradilo dřívější Freedom a Platby: Freedom byla z poloviny
            gamifikace, Platby pětkrát prázdný stav se zelenou fajfkou. */}
        {/* ==============================================================
            NÁLEZY — vlastní nápady, posouzené podle metodiky
            ============================================================== */}
        {activeTab === 'nalezy' && (
          <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
            <FindsPage />
          </div>
        )}

        {/* ==============================================================
            MODELY — analytikovy modely tržeb vs. realita
            ============================================================== */}
        {activeTab === 'modely' && (
          <div className="flex min-h-0 flex-1 flex-col overflow-hidden p-3">
            <RevenueModelsPage />
          </div>
        )}

        {activeTab === 'cil' && (
          <div className="min-h-0 flex-1 overflow-y-auto pr-0.5">
            <GoalPage
              portfolioValue={familyData.totalValue}
              monthlyContribution={familyData.monthlyContribution}
            />
          </div>
        )}

        {/* ==============================================================
            PLATBY

            Pět knih, které stály pod sebou přes tři obrazovky, jsou teď
            odrážky s vlastní měsíční částkou a jedna tabulka pod nimi.
            Data, formuláře i dialogy zůstávají tady — PaymentsPage jen
            kreslí, takže se přes ni nedá o nic přijít.
        ============================================================== */}
        {activeTab === 'splaceni' && (
          <PaymentsPage
            debts={debts}
            sharedPayments={sharedPayments}
            misaPayments={misaPayments}
            savings={savings}
            tomPayments={tomPayments}
            formatCurrency={formatCurrency}
            onAdd={(ledger) => {
              /* Rozepsaná úprava se před přidáním zahodí. Bez tohohle
                 kroku zůstalo `editing…Id` viset po opuštěné úpravě a
                 „Přidat" tiše přepsalo cizí záznam. */
              switch (ledger) {
                case 'debts':
                  setEditingDebtId(null);
                  setDebtForm(PRAZDNA_PLATBA);
                  setShowAddDebtModal(true);
                  break;
                case 'shared':
                  setEditingSharedPaymentsId(null);
                  setSharedPaymentsForm(PRAZDNA_PLATBA);
                  setShowAddSharedPaymentsModal(true);
                  break;
                case 'misa':
                  setEditingMisaPaymentsId(null);
                  setMisaPaymentsForm(PRAZDNA_PLATBA);
                  setShowAddMisaPaymentsModal(true);
                  break;
                case 'savings':
                  setEditingSavingsId(null);
                  setSavingsForm(PRAZDNA_PLATBA);
                  setShowAddSavingsModal(true);
                  break;
                case 'tom':
                  setEditingTomPaymentsId(null);
                  setTomPaymentsForm(PRAZDNA_PLATBA);
                  setShowAddTomPaymentsModal(true);
                  break;
              }
            }}
            onEdit={(ledger, item) => {
              const form = {
                name: item.name,
                amount: item.amount,
                date: item.date,
                monthlyPayment: item.monthlyPayment,
                creditor: item.creditor,
                accountNumber: item.accountNumber,
                variableSymbol: item.variableSymbol,
                note: item.note,
              };
              switch (ledger) {
                case 'debts':
                  setEditingDebtId(item.id);
                  setDebtForm(form);
                  setShowAddDebtModal(true);
                  break;
                case 'shared':
                  setEditingSharedPaymentsId(item.id);
                  setSharedPaymentsForm(form);
                  setShowAddSharedPaymentsModal(true);
                  break;
                case 'misa':
                  setEditingMisaPaymentsId(item.id);
                  setMisaPaymentsForm(form);
                  setShowAddMisaPaymentsModal(true);
                  break;
                case 'savings':
                  setEditingSavingsId(item.id);
                  setSavingsForm(form);
                  setShowAddSavingsModal(true);
                  break;
                case 'tom':
                  setEditingTomPaymentsId(item.id);
                  setTomPaymentsForm(form);
                  setShowAddTomPaymentsModal(true);
                  break;
              }
            }}
          />
        )}
      </main>

      {/* MODALS */}
      {selectedPosition && (
        <StockDetail
          position={selectedPosition}
          onClose={() => setSelectedPosition(null)}
          onUpdate={async () => {
            // Refresh portfolio data after position update
            await refreshPortfolios();
            // Also refresh stocks data for conviction scores and price lines
            const stocksData = await apiClient.getEnrichedStocks();
            setStocks(stocksData.stocks);
          }}
        />
      )}

      {/* „Už nedržím" — prodej se zapisuje, řádek z importu se maže.
          Rozdíl mezi tím rozhoduje dialog, ne tohle místo. */}
      {removingPosition && (
        <RemovePositionDialog
          position={removingPosition}
          onCancel={() => setRemovingPosition(null)}
          onDone={async () => {
            setRemovingPosition(null);
            await refreshPortfolios();
          }}
        />
      )}

      {/* Watchlist Stock Detail Modal */}
      {selectedWatchlistStock && (
        <WatchlistDetailModal
          stock={selectedWatchlistStock}
          onClose={() => setSelectedWatchlistStock(null)}
          onUpdate={async () => {
            const stocksData = await apiClient.getEnrichedStocks();
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

      {/* Gomes Intake Modal (Gemini 3.7 Flash) */}
      <GomesIntakeModal
        isOpen={showIntakeModal}
        onClose={() => setShowIntakeModal(false)}
        onSuccess={async () => {
          await refreshPortfolios();
          const stocksData = await apiClient.getEnrichedStocks();
          setStocks(stocksData.stocks);
        }}
      />

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
            setShowAddPositionModal(false);
          }}
        />
      )}

      {/* Add Debt Modal */}
      {showAddDebtModal && (
        <div className="fixed inset-0 bg-surface-base/60 backdrop-blur-sm flex items-center justify-center z-50 p-4">
          <div className="bg-surface-base rounded-xl shadow-2xl max-w-2xl w-full max-h-[90vh] overflow-y-auto">
            {/* Header */}
            <div className="sticky top-0 bg-surface-base border-b border-border px-6 py-4 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-accent/20 flex items-center justify-center">
                  {editingDebtId ? <Edit3 className="w-5 h-5 text-accent" /> : <Plus className="w-5 h-5 text-accent" />}
                </div>
                <div>
                  <h2 className="text-xl font-bold text-text-primary">
                    {editingDebtId ? 'Upravit závazek' : 'Přidat závazek'}
                  </h2>
                  <p className="text-sm text-text-muted">
                    {editingDebtId ? 'Upravte údaje o závazku' : 'Evidujte nový dluh nebo splátku'}
                  </p>
                </div>
              </div>
              <button
                onClick={() => {
                  setShowAddDebtModal(false);
                  setEditingDebtId(null);
                  setDebtForm({
                    name: '',
                    amount: '',
                    date: '',
                    monthlyPayment: '',
                    creditor: '',
                    accountNumber: '',
                    variableSymbol: '',
                    note: ''
                  });
                }}
                className="w-8 h-8 rounded-lg hover:bg-surface-hover flex items-center justify-center text-text-muted hover:text-text-primary transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Form */}
            <div className="p-6 space-y-4">
              {/* Název */}
              <div>
                <label className="block text-sm font-semibold text-text-primary mb-2">
                  Název *
                </label>
                <input
                  type="text"
                  value={debtForm.name}
                  onChange={(e) => setDebtForm({ ...debtForm, name: e.target.value })}
                  placeholder="Např. Hypotéka, Auto, Studijní půjčka"
                  className="w-full px-4 py-2.5 bg-surface-raised border border-border rounded-lg text-text-primary placeholder-text-muted focus:outline-none focus:border-accent transition-colors"
                  required
                />
              </div>

              {/* Částka závazku */}
              <div>
                <label className="block text-sm font-semibold text-text-primary mb-2">
                  Částka závazku *
                </label>
                <input
                  type="number"
                  step="0.01"
                  value={debtForm.amount}
                  onChange={(e) => setDebtForm({ ...debtForm, amount: e.target.value })}
                  placeholder="Např. 500000"
                  className="w-full px-4 py-2.5 bg-surface-raised border border-border rounded-lg text-text-primary placeholder-text-muted focus:outline-none focus:border-accent transition-colors"
                  required
                />
              </div>

              {/* První splátka */}
              <div>
                <label className="block text-sm font-semibold text-text-primary mb-2">
                  1. splátka *
                </label>
                <input
                  type="date"
                  value={debtForm.date}
                  onChange={(e) => setDebtForm({ ...debtForm, date: e.target.value })}
                  className="w-full px-4 py-2.5 bg-surface-raised border border-border rounded-lg text-text-primary focus:outline-none focus:border-accent transition-colors"
                  required
                />
              </div>

              {/* Splátka */}
              <div>
                <label className="block text-sm font-semibold text-text-primary mb-2">
                  Splátka *
                </label>
                <input
                  type="number"
                  step="0.01"
                  value={debtForm.monthlyPayment}
                  onChange={(e) => setDebtForm({ ...debtForm, monthlyPayment: e.target.value })}
                  placeholder="Např. 8500"
                  className="w-full px-4 py-2.5 bg-surface-raised border border-border rounded-lg text-text-primary placeholder-text-muted focus:outline-none focus:border-accent transition-colors"
                  required
                />
              </div>

              {/* Komu */}
              <div>
                <label className="block text-sm font-semibold text-text-primary mb-2">
                  Komu *
                </label>
                <input
                  type="text"
                  value={debtForm.creditor}
                  onChange={(e) => setDebtForm({ ...debtForm, creditor: e.target.value })}
                  placeholder="Např. Česká spořitelna"
                  className="w-full px-4 py-2.5 bg-surface-raised border border-border rounded-lg text-text-primary placeholder-text-muted focus:outline-none focus:border-accent transition-colors"
                  required
                />
              </div>

              {/* Číslo účtu */}
              <div>
                <label className="block text-sm font-semibold text-text-primary mb-2">
                  Číslo účtu
                </label>
                <input
                  type="text"
                  value={debtForm.accountNumber}
                  onChange={(e) => setDebtForm({ ...debtForm, accountNumber: e.target.value })}
                  placeholder="Např. 123456789/0800"
                  className="w-full px-4 py-2.5 bg-surface-raised border border-border rounded-lg text-text-primary placeholder-text-muted focus:outline-none focus:border-accent transition-colors"
                />
              </div>

              {/* Variabilní symbol */}
              <div>
                <label className="block text-sm font-semibold text-text-primary mb-2">
                  VS
                </label>
                <input
                  type="text"
                  value={debtForm.variableSymbol}
                  onChange={(e) => setDebtForm({ ...debtForm, variableSymbol: e.target.value })}
                  placeholder="Např. 1234567890"
                  className="w-full px-4 py-2.5 bg-surface-raised border border-border rounded-lg text-text-primary placeholder-text-muted focus:outline-none focus:border-accent transition-colors"
                />
              </div>

              {/* Info */}
              <div>
                <label className="block text-sm font-semibold text-text-primary mb-2">
                  Info
                </label>
                <textarea
                  value={debtForm.note}
                  onChange={(e) => setDebtForm({ ...debtForm, note: e.target.value })}
                  placeholder="Doplňující informace..."
                  rows={3}
                  className="w-full px-4 py-2.5 bg-surface-raised border border-border rounded-lg text-text-primary placeholder-text-muted focus:outline-none focus:border-accent transition-colors resize-none"
                />
              </div>
            </div>

            {/* Footer */}
            <div className="sticky bottom-0 bg-surface-base border-t border-border px-6 py-4 flex items-center justify-between">
              <button
                onClick={() => {
                  setShowAddDebtModal(false);
                  setEditingDebtId(null);
                  setDebtForm({
                    name: '',
                    amount: '',
                    date: '',
                    monthlyPayment: '',
                    creditor: '',
                    accountNumber: '',
                    variableSymbol: '',
                    note: ''
                  });
                }}
                className="px-4 py-2 text-text-secondary hover:text-text-primary transition-colors font-medium"
              >
                Zrušit
              </button>
              <div className="flex items-center gap-2">
                {editingDebtId && (
                  <button
                    onClick={() => {
                      if (confirm('Opravdu chcete odstranit tento závazek?')) {
                        setDebts(debts.filter(d => d.id !== editingDebtId));
                        setShowAddDebtModal(false);
                        setEditingDebtId(null);
                        setDebtForm({
                          name: '',
                          amount: '',
                          date: '',
                          monthlyPayment: '',
                          creditor: '',
                          accountNumber: '',
                          variableSymbol: '',
                          note: ''
                        });
                      }
                    }}
                    className="px-4 py-2 bg-negative/10 text-negative rounded-lg font-medium hover:bg-negative/20 transition-colors flex items-center gap-2"
                  >
                    <X className="w-4 h-4" />
                    Odstranit
                  </button>
                )}
                <button
                  onClick={() => {
                    if (editingDebtId) {
                      // Update existing debt
                      setDebts(debts.map(d => 
                        d.id === editingDebtId ? { id: d.id, ...debtForm } : d
                      ));
                    } else {
                      // Add new debt
                      const newDebt = {
                        id: Date.now(),
                        ...debtForm
                      };
                      setDebts([...debts, newDebt]);
                    }
                    
                    // Close modal and reset form
                    setShowAddDebtModal(false);
                    setEditingDebtId(null);
                    setDebtForm({
                      name: '',
                      amount: '',
                      date: '',
                      monthlyPayment: '',
                      creditor: '',
                      accountNumber: '',
                      variableSymbol: '',
                      note: ''
                    });
                  }}
                  disabled={!debtForm.name || !debtForm.amount || !debtForm.date || !debtForm.monthlyPayment || !debtForm.creditor}
                  className="px-6 py-2 bg-accent text-text-primary rounded-lg font-bold hover:bg-accent/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                >
                  <Check className="w-4 h-4" />
                  Uložit závazek
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Add Shared Payments Modal */}
      {showAddSharedPaymentsModal && (
        <div className="fixed inset-0 bg-surface-base/60 backdrop-blur-sm flex items-center justify-center z-50 p-4">
          <div className="bg-surface-base rounded-xl shadow-2xl max-w-2xl w-full max-h-[90vh] overflow-y-auto">
            {/* Header */}
            <div className="sticky top-0 bg-surface-base border-b border-border px-6 py-4 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-accent/20 flex items-center justify-center">
                  {editingSharedPaymentsId ? <Edit3 className="w-5 h-5 text-accent" /> : <Plus className="w-5 h-5 text-accent" />}
                </div>
                <div>
                  <h2 className="text-xl font-bold text-text-primary">
                    {editingSharedPaymentsId ? 'Upravit položku' : 'Přidat položku'}
                  </h2>
                  <p className="text-sm text-text-muted">
                    {editingSharedPaymentsId ? 'Upravte údaje o společné platbě' : 'Evidujte novou společnou platbu'}
                  </p>
                </div>
              </div>
              <button
                onClick={() => {
                  setShowAddSharedPaymentsModal(false);
                  setEditingSharedPaymentsId(null);
                  setSharedPaymentsForm({
                    name: '',
                    amount: '',
                    date: '',
                    monthlyPayment: '',
                    creditor: '',
                    accountNumber: '',
                    variableSymbol: '',
                    note: ''
                  });
                }}
                className="w-8 h-8 rounded-lg hover:bg-surface-hover flex items-center justify-center text-text-muted hover:text-text-primary transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Form */}
            <div className="p-6 space-y-4">
              {/* Název */}
              <div>
                <label className="block text-sm font-semibold text-text-primary mb-2">
                  Název *
                </label>
                <input
                  type="text"
                  value={sharedPaymentsForm.name}
                  onChange={(e) => setSharedPaymentsForm({ ...sharedPaymentsForm, name: e.target.value })}
                  placeholder="Např. Netflix, Elektřina, Internet"
                  className="w-full px-4 py-2.5 bg-surface-raised border border-border rounded-lg text-text-primary placeholder-text-muted focus:outline-none focus:border-accent transition-colors"
                  required
                />
              </div>

              {/* Splátka */}
              <div>
                <label className="block text-sm font-semibold text-text-primary mb-2">
                  Splátka *
                </label>
                <input
                  type="number"
                  step="0.01"
                  value={sharedPaymentsForm.monthlyPayment}
                  onChange={(e) => setSharedPaymentsForm({ ...sharedPaymentsForm, monthlyPayment: e.target.value })}
                  placeholder="Např. 500"
                  className="w-full px-4 py-2.5 bg-surface-raised border border-border rounded-lg text-text-primary placeholder-text-muted focus:outline-none focus:border-accent transition-colors"
                  required
                />
              </div>

              {/* Číslo účtu */}
              <div>
                <label className="block text-sm font-semibold text-text-primary mb-2">
                  Číslo účtu
                </label>
                <input
                  type="text"
                  value={sharedPaymentsForm.accountNumber}
                  onChange={(e) => setSharedPaymentsForm({ ...sharedPaymentsForm, accountNumber: e.target.value })}
                  placeholder="Např. 123456789/0800"
                  className="w-full px-4 py-2.5 bg-surface-raised border border-border rounded-lg text-text-primary placeholder-text-muted focus:outline-none focus:border-accent transition-colors"
                />
              </div>

              {/* Variabilní symbol */}
              <div>
                <label className="block text-sm font-semibold text-text-primary mb-2">
                  VS
                </label>
                <input
                  type="text"
                  value={sharedPaymentsForm.variableSymbol}
                  onChange={(e) => setSharedPaymentsForm({ ...sharedPaymentsForm, variableSymbol: e.target.value })}
                  placeholder="Např. 1234567890"
                  className="w-full px-4 py-2.5 bg-surface-raised border border-border rounded-lg text-text-primary placeholder-text-muted focus:outline-none focus:border-accent transition-colors"
                />
              </div>

              {/* Info */}
              <div>
                <label className="block text-sm font-semibold text-text-primary mb-2">
                  Info
                </label>
                <textarea
                  value={sharedPaymentsForm.note}
                  onChange={(e) => setSharedPaymentsForm({ ...sharedPaymentsForm, note: e.target.value })}
                  placeholder="Doplňující informace..."
                  rows={3}
                  className="w-full px-4 py-2.5 bg-surface-raised border border-border rounded-lg text-text-primary placeholder-text-muted focus:outline-none focus:border-accent transition-colors resize-none"
                />
              </div>
            </div>

            {/* Footer */}
            <div className="sticky bottom-0 bg-surface-base border-t border-border px-6 py-4 flex items-center justify-between">
              <button
                onClick={() => {
                  setShowAddSharedPaymentsModal(false);
                  setEditingSharedPaymentsId(null);
                  setSharedPaymentsForm({
                    name: '',
                    amount: '',
                    date: '',
                    monthlyPayment: '',
                    creditor: '',
                    accountNumber: '',
                    variableSymbol: '',
                    note: ''
                  });
                }}
                className="px-4 py-2 text-text-secondary hover:text-text-primary transition-colors font-medium"
              >
                Zrušit
              </button>
              <div className="flex items-center gap-2">
                {editingSharedPaymentsId && (
                  <button
                    onClick={() => {
                      if (confirm('Opravdu chcete odstranit tuto položku?')) {
                        setSharedPayments(sharedPayments.filter(d => d.id !== editingSharedPaymentsId));
                        setShowAddSharedPaymentsModal(false);
                        setEditingSharedPaymentsId(null);
                        setSharedPaymentsForm({
                          name: '',
                          amount: '',
                          date: '',
                          monthlyPayment: '',
                          creditor: '',
                          accountNumber: '',
                          variableSymbol: '',
                          note: ''
                        });
                      }
                    }}
                    className="px-4 py-2 bg-negative/10 text-negative rounded-lg font-medium hover:bg-negative/20 transition-colors flex items-center gap-2"
                  >
                    <X className="w-4 h-4" />
                    Odstranit
                  </button>
                )}
                <button
                  onClick={() => {
                    if (editingSharedPaymentsId) {
                      // Update existing item
                      setSharedPayments(sharedPayments.map(d => 
                        d.id === editingSharedPaymentsId ? { id: d.id, ...sharedPaymentsForm } : d
                      ));
                    } else {
                      // Add new item
                      const newItem = {
                        id: Date.now(),
                        ...sharedPaymentsForm
                      };
                      setSharedPayments([...sharedPayments, newItem]);
                    }
                    
                    // Close modal and reset form
                    setShowAddSharedPaymentsModal(false);
                    setEditingSharedPaymentsId(null);
                    setSharedPaymentsForm({
                      name: '',
                      amount: '',
                      date: '',
                      monthlyPayment: '',
                      creditor: '',
                      accountNumber: '',
                      variableSymbol: '',
                      note: ''
                    });
                  }}
                  disabled={!sharedPaymentsForm.name || !sharedPaymentsForm.monthlyPayment}
                  className="px-6 py-2 bg-accent text-text-primary rounded-lg font-bold hover:bg-accent/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                >
                  <Check className="w-4 h-4" />
                  Uložit položku
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Add Savings Modal */}
      {showAddSavingsModal && (
        <div className="fixed inset-0 bg-surface-base/60 backdrop-blur-sm flex items-center justify-center z-50 p-4">
          <div className="bg-surface-base rounded-xl shadow-2xl max-w-2xl w-full max-h-[90vh] overflow-y-auto">
            {/* Header */}
            <div className="sticky top-0 bg-surface-base border-b border-border px-6 py-4 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-accent/20 flex items-center justify-center">
                  {editingSavingsId ? <Edit3 className="w-5 h-5 text-accent" /> : <Plus className="w-5 h-5 text-accent" />}
                </div>
                <div>
                  <h2 className="text-xl font-bold text-text-primary">
                    {editingSavingsId ? 'Upravit položku' : 'Přidat položku'}
                  </h2>
                  <p className="text-sm text-text-muted">
                    {editingSavingsId ? 'Upravte údaje o šetření' : 'Evidujte nové šetření'}
                  </p>
                </div>
              </div>
              <button
                onClick={() => {
                  setShowAddSavingsModal(false);
                  setEditingSavingsId(null);
                  setSavingsForm({
                    name: '',
                    amount: '',
                    date: '',
                    monthlyPayment: '',
                    creditor: '',
                    accountNumber: '',
                    variableSymbol: '',
                    note: ''
                  });
                }}
                className="w-8 h-8 rounded-lg hover:bg-surface-hover flex items-center justify-center text-text-muted hover:text-text-primary transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Form */}
            <div className="p-6 space-y-4">
              {/* Název */}
              <div>
                <label className="block text-sm font-semibold text-text-primary mb-2">
                  Název *
                </label>
                <input
                  type="text"
                  value={savingsForm.name}
                  onChange={(e) => setSavingsForm({ ...savingsForm, name: e.target.value })}
                  placeholder="Např. Hypotéka, Auto, Studijní půjčka"
                  className="w-full px-4 py-2.5 bg-surface-raised border border-border rounded-lg text-text-primary placeholder-text-muted focus:outline-none focus:border-accent transition-colors"
                  required
                />
              </div>

              {/* Splátka */}
              <div>
                <label className="block text-sm font-semibold text-text-primary mb-2">
                  Splátka *
                </label>
                <input
                  type="number"
                  step="0.01"
                  value={savingsForm.monthlyPayment}
                  onChange={(e) => setSavingsForm({ ...savingsForm, monthlyPayment: e.target.value })}
                  placeholder="Např. 8500"
                  className="w-full px-4 py-2.5 bg-surface-raised border border-border rounded-lg text-text-primary placeholder-text-muted focus:outline-none focus:border-accent transition-colors"
                  required
                />
              </div>

              {/* Číslo účtu */}
              <div>
                <label className="block text-sm font-semibold text-text-primary mb-2">
                  Číslo účtu
                </label>
                <input
                  type="text"
                  value={savingsForm.accountNumber}
                  onChange={(e) => setSavingsForm({ ...savingsForm, accountNumber: e.target.value })}
                  placeholder="Např. 123456789/0800"
                  className="w-full px-4 py-2.5 bg-surface-raised border border-border rounded-lg text-text-primary placeholder-text-muted focus:outline-none focus:border-accent transition-colors"
                />
              </div>

              {/* Variabilní symbol */}
              <div>
                <label className="block text-sm font-semibold text-text-primary mb-2">
                  VS
                </label>
                <input
                  type="text"
                  value={savingsForm.variableSymbol}
                  onChange={(e) => setSavingsForm({ ...savingsForm, variableSymbol: e.target.value })}
                  placeholder="Např. 1234567890"
                  className="w-full px-4 py-2.5 bg-surface-raised border border-border rounded-lg text-text-primary placeholder-text-muted focus:outline-none focus:border-accent transition-colors"
                />
              </div>
            </div>

            {/* Footer */}
            <div className="sticky bottom-0 bg-surface-base border-t border-border px-6 py-4 flex items-center justify-between">
              <button
                onClick={() => {
                  setShowAddSavingsModal(false);
                  setEditingSavingsId(null);
                  setSavingsForm({
                    name: '',
                    amount: '',
                    date: '',
                    monthlyPayment: '',
                    creditor: '',
                    accountNumber: '',
                    variableSymbol: '',
                    note: ''
                  });
                }}
                className="px-4 py-2 text-text-secondary hover:text-text-primary transition-colors font-medium"
              >
                Zrušit
              </button>
              <div className="flex items-center gap-2">
                {editingSavingsId && (
                  <button
                    onClick={() => {
                      if (confirm('Opravdu chcete odstranit tuto položku?')) {
                        setSavings(savings.filter(d => d.id !== editingSavingsId));
                        setShowAddSavingsModal(false);
                        setEditingSavingsId(null);
                        setSavingsForm({
                          name: '',
                          amount: '',
                          date: '',
                          monthlyPayment: '',
                          creditor: '',
                          accountNumber: '',
                          variableSymbol: '',
                          note: ''
                        });
                      }
                    }}
                    className="px-4 py-2 bg-negative/10 text-negative rounded-lg font-medium hover:bg-negative/20 transition-colors flex items-center gap-2"
                  >
                    <X className="w-4 h-4" />
                    Odstranit
                  </button>
                )}
                <button
                  onClick={() => {
                    if (editingSavingsId) {
                      // Update existing item
                      setSavings(savings.map(d => 
                        d.id === editingSavingsId ? { id: d.id, ...savingsForm } : d
                      ));
                    } else {
                      // Add new item
                      const newItem = {
                        id: Date.now(),
                        ...savingsForm
                      };
                      setSavings([...savings, newItem]);
                    }
                    
                    // Close modal and reset form
                    setShowAddSavingsModal(false);
                    setEditingSavingsId(null);
                    setSavingsForm({
                      name: '',
                      amount: '',
                      date: '',
                      monthlyPayment: '',
                      creditor: '',
                      accountNumber: '',
                      variableSymbol: '',
                      note: ''
                    });
                  }}
                  disabled={!savingsForm.name || !savingsForm.monthlyPayment}
                  className="px-6 py-2 bg-accent text-text-primary rounded-lg font-bold hover:bg-accent/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                >
                  <Check className="w-4 h-4" />
                  Uložit položku
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Add Tom Payments Modal */}
      {showAddTomPaymentsModal && (
        <div className="fixed inset-0 bg-surface-base/60 backdrop-blur-sm flex items-center justify-center z-50 p-4">
          <div className="bg-surface-base rounded-xl shadow-2xl max-w-2xl w-full max-h-[90vh] overflow-y-auto">
            {/* Header */}
            <div className="sticky top-0 bg-surface-base border-b border-border px-6 py-4 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-warning/20 flex items-center justify-center">
                  {editingTomPaymentsId ? <Edit3 className="w-5 h-5 text-warning" /> : <Plus className="w-5 h-5 text-warning" />}
                </div>
                <div>
                  <h2 className="text-xl font-bold text-text-primary">
                    {editingTomPaymentsId ? 'Upravit položku' : 'Přidat položku'}
                  </h2>
                  <p className="text-sm text-text-muted">
                    {editingTomPaymentsId ? 'Upravte údaje o platbě Tom' : 'Evidujte novou platbu Tom'}
                  </p>
                </div>
              </div>
              <button
                onClick={() => {
                  setShowAddTomPaymentsModal(false);
                  setEditingTomPaymentsId(null);
                  setTomPaymentsForm({
                    name: '',
                    amount: '',
                    date: '',
                    monthlyPayment: '',
                    creditor: '',
                    accountNumber: '',
                    variableSymbol: '',
                    note: ''
                  });
                }}
                className="w-8 h-8 rounded-lg hover:bg-surface-hover flex items-center justify-center text-text-muted hover:text-text-primary transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Form */}
            <div className="p-6 space-y-4">
              {/* Název */}
              <div>
                <label className="block text-sm font-semibold text-text-primary mb-2">
                  Název *
                </label>
                <input
                  type="text"
                  value={tomPaymentsForm.name}
                  onChange={(e) => setTomPaymentsForm({ ...tomPaymentsForm, name: e.target.value })}
                  placeholder="Např. Nájem, Auto, Telefon"
                  className="w-full px-4 py-2.5 bg-surface-raised border border-border rounded-lg text-text-primary placeholder-text-muted focus:outline-none focus:border-warning transition-colors"
                  required
                />
              </div>

              {/* Splátka */}
              <div>
                <label className="block text-sm font-semibold text-text-primary mb-2">
                  Splátka *
                </label>
                <input
                  type="number"
                  step="0.01"
                  value={tomPaymentsForm.monthlyPayment}
                  onChange={(e) => setTomPaymentsForm({ ...tomPaymentsForm, monthlyPayment: e.target.value })}
                  placeholder="Např. 1500"
                  className="w-full px-4 py-2.5 bg-surface-raised border border-border rounded-lg text-text-primary placeholder-text-muted focus:outline-none focus:border-warning transition-colors"
                  required
                />
              </div>

              {/* Číslo účtu */}
              <div>
                <label className="block text-sm font-semibold text-text-primary mb-2">
                  Číslo účtu
                </label>
                <input
                  type="text"
                  value={tomPaymentsForm.accountNumber}
                  onChange={(e) => setTomPaymentsForm({ ...tomPaymentsForm, accountNumber: e.target.value })}
                  placeholder="Např. 123456789/0800"
                  className="w-full px-4 py-2.5 bg-surface-raised border border-border rounded-lg text-text-primary placeholder-text-muted focus:outline-none focus:border-warning transition-colors"
                />
              </div>

              {/* Variabilní symbol */}
              <div>
                <label className="block text-sm font-semibold text-text-primary mb-2">
                  VS
                </label>
                <input
                  type="text"
                  value={tomPaymentsForm.variableSymbol}
                  onChange={(e) => setTomPaymentsForm({ ...tomPaymentsForm, variableSymbol: e.target.value })}
                  placeholder="Např. 1234567890"
                  className="w-full px-4 py-2.5 bg-surface-raised border border-border rounded-lg text-text-primary placeholder-text-muted focus:outline-none focus:border-warning transition-colors"
                />
              </div>
            </div>

            {/* Footer */}
            <div className="sticky bottom-0 bg-surface-base border-t border-border px-6 py-4 flex items-center justify-between">
              <button
                onClick={() => {
                  setShowAddTomPaymentsModal(false);
                  setEditingTomPaymentsId(null);
                  setTomPaymentsForm({
                    name: '',
                    amount: '',
                    date: '',
                    monthlyPayment: '',
                    creditor: '',
                    accountNumber: '',
                    variableSymbol: '',
                    note: ''
                  });
                }}
                className="px-4 py-2 text-text-secondary hover:text-text-primary transition-colors font-medium"
              >
                Zrušit
              </button>
              <div className="flex items-center gap-2">
                {editingTomPaymentsId && (
                  <button
                    onClick={() => {
                      if (confirm('Opravdu chcete odstranit tuto položku?')) {
                        setTomPayments(tomPayments.filter(d => d.id !== editingTomPaymentsId));
                        setShowAddTomPaymentsModal(false);
                        setEditingTomPaymentsId(null);
                        setTomPaymentsForm({
                          name: '',
                          amount: '',
                          date: '',
                          monthlyPayment: '',
                          creditor: '',
                          accountNumber: '',
                          variableSymbol: '',
                          note: ''
                        });
                      }
                    }}
                    className="px-4 py-2 bg-negative/10 text-negative rounded-lg font-medium hover:bg-negative/20 transition-colors flex items-center gap-2"
                  >
                    <X className="w-4 h-4" />
                    Odstranit
                  </button>
                )}
                <button
                  onClick={() => {
                    if (editingTomPaymentsId) {
                      // Update existing item
                      setTomPayments(tomPayments.map(d => 
                        d.id === editingTomPaymentsId ? { id: d.id, ...tomPaymentsForm } : d
                      ));
                    } else {
                      // Add new item
                      const newItem = {
                        id: Date.now(),
                        ...tomPaymentsForm
                      };
                      setTomPayments([...tomPayments, newItem]);
                    }
                    
                    // Close modal and reset form
                    setShowAddTomPaymentsModal(false);
                    setEditingTomPaymentsId(null);
                    setTomPaymentsForm({
                      name: '',
                      amount: '',
                      date: '',
                      monthlyPayment: '',
                      creditor: '',
                      accountNumber: '',
                      variableSymbol: '',
                      note: ''
                    });
                  }}
                  disabled={!tomPaymentsForm.name || !tomPaymentsForm.monthlyPayment}
                  className="px-6 py-2 bg-accent text-text-primary rounded-lg font-bold hover:bg-accent/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                >
                  <Check className="w-4 h-4" />
                  Uložit položku
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Add Míša Payments Modal */}
      {showAddMisaPaymentsModal && (
        <div className="fixed inset-0 bg-surface-base/60 backdrop-blur-sm flex items-center justify-center z-50 p-4">
          <div className="bg-surface-base rounded-xl shadow-2xl max-w-2xl w-full max-h-[90vh] overflow-y-auto">
            {/* Header */}
            <div className="sticky top-0 bg-surface-base border-b border-border px-6 py-4 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-accent/20 flex items-center justify-center">
                  {editingMisaPaymentsId ? <Edit3 className="w-5 h-5 text-accent" /> : <Plus className="w-5 h-5 text-accent" />}
                </div>
                <div>
                  <h2 className="text-xl font-bold text-text-primary">
                    {editingMisaPaymentsId ? 'Upravit položku' : 'Přidat položku'}
                  </h2>
                  <p className="text-sm text-text-muted">
                    {editingMisaPaymentsId ? 'Upravte údaje o platbě Míša' : 'Evidujte novou platbu Míša'}
                  </p>
                </div>
              </div>
              <button
                onClick={() => {
                  setShowAddMisaPaymentsModal(false);
                  setEditingMisaPaymentsId(null);
                  setMisaPaymentsForm({
                    name: '',
                    amount: '',
                    date: '',
                    monthlyPayment: '',
                    creditor: '',
                    accountNumber: '',
                    variableSymbol: '',
                    note: ''
                  });
                }}
                className="w-8 h-8 rounded-lg hover:bg-surface-hover flex items-center justify-center text-text-muted hover:text-text-primary transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Form */}
            <div className="p-6 space-y-4">
              {/* Název */}
              <div>
                <label className="block text-sm font-semibold text-text-primary mb-2">
                  Název *
                </label>
                <input
                  type="text"
                  value={misaPaymentsForm.name}
                  onChange={(e) => setMisaPaymentsForm({ ...misaPaymentsForm, name: e.target.value })}
                  placeholder="Např. Pojištění, Kredity, Předplatné"
                  className="w-full px-4 py-2.5 bg-surface-raised border border-border rounded-lg text-text-primary placeholder-text-muted focus:outline-none focus:border-accent transition-colors"
                  required
                />
              </div>

              {/* Splátka */}
              <div>
                <label className="block text-sm font-semibold text-text-primary mb-2">
                  Splátka *
                </label>
                <input
                  type="number"
                  step="0.01"
                  value={misaPaymentsForm.monthlyPayment}
                  onChange={(e) => setMisaPaymentsForm({ ...misaPaymentsForm, monthlyPayment: e.target.value })}
                  placeholder="Např. 800"
                  className="w-full px-4 py-2.5 bg-surface-raised border border-border rounded-lg text-text-primary placeholder-text-muted focus:outline-none focus:border-accent transition-colors"
                  required
                />
              </div>

              {/* Číslo účtu */}
              <div>
                <label className="block text-sm font-semibold text-text-primary mb-2">
                  Číslo účtu
                </label>
                <input
                  type="text"
                  value={misaPaymentsForm.accountNumber}
                  onChange={(e) => setMisaPaymentsForm({ ...misaPaymentsForm, accountNumber: e.target.value })}
                  placeholder="Např. 123456789/0800"
                  className="w-full px-4 py-2.5 bg-surface-raised border border-border rounded-lg text-text-primary placeholder-text-muted focus:outline-none focus:border-accent transition-colors"
                />
              </div>

              {/* Variabilní symbol */}
              <div>
                <label className="block text-sm font-semibold text-text-primary mb-2">
                  VS
                </label>
                <input
                  type="text"
                  value={misaPaymentsForm.variableSymbol}
                  onChange={(e) => setMisaPaymentsForm({ ...misaPaymentsForm, variableSymbol: e.target.value })}
                  placeholder="Např. 1234567890"
                  className="w-full px-4 py-2.5 bg-surface-raised border border-border rounded-lg text-text-primary placeholder-text-muted focus:outline-none focus:border-accent transition-colors"
                />
              </div>
            </div>

            {/* Footer */}
            <div className="sticky bottom-0 bg-surface-base border-t border-border px-6 py-4 flex items-center justify-between">
              <button
                onClick={() => {
                  setShowAddMisaPaymentsModal(false);
                  setEditingMisaPaymentsId(null);
                  setMisaPaymentsForm({
                    name: '',
                    amount: '',
                    date: '',
                    monthlyPayment: '',
                    creditor: '',
                    accountNumber: '',
                    variableSymbol: '',
                    note: ''
                  });
                }}
                className="px-4 py-2 text-text-secondary hover:text-text-primary transition-colors font-medium"
              >
                Zrušit
              </button>
              <div className="flex items-center gap-2">
                {editingMisaPaymentsId && (
                  <button
                    onClick={() => {
                      if (confirm('Opravdu chcete odstranit tuto položku?')) {
                        setMisaPayments(misaPayments.filter(d => d.id !== editingMisaPaymentsId));
                        setShowAddMisaPaymentsModal(false);
                        setEditingMisaPaymentsId(null);
                        setMisaPaymentsForm({
                          name: '',
                          amount: '',
                          date: '',
                          monthlyPayment: '',
                          creditor: '',
                          accountNumber: '',
                          variableSymbol: '',
                          note: ''
                        });
                      }
                    }}
                    className="px-4 py-2 bg-negative/10 text-negative rounded-lg font-medium hover:bg-negative/20 transition-colors flex items-center gap-2"
                  >
                    <X className="w-4 h-4" />
                    Odstranit
                  </button>
                )}
                <button
                  onClick={() => {
                    if (editingMisaPaymentsId) {
                      // Update existing item
                      setMisaPayments(misaPayments.map(d => 
                        d.id === editingMisaPaymentsId ? { id: d.id, ...misaPaymentsForm } : d
                      ));
                    } else {
                      // Add new item
                      const newItem = {
                        id: Date.now(),
                        ...misaPaymentsForm
                      };
                      setMisaPayments([...misaPayments, newItem]);
                    }
                    
                    // Close modal and reset form
                    setShowAddMisaPaymentsModal(false);
                    setEditingMisaPaymentsId(null);
                    setMisaPaymentsForm({
                      name: '',
                      amount: '',
                      date: '',
                      monthlyPayment: '',
                      creditor: '',
                      accountNumber: '',
                      variableSymbol: '',
                      note: ''
                    });
                  }}
                  disabled={!misaPaymentsForm.name || !misaPaymentsForm.monthlyPayment}
                  className="px-6 py-2 bg-accent text-text-primary rounded-lg font-bold hover:bg-accent/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                >
                  <Check className="w-4 h-4" />
                  Uložit položku
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {showAnalysisModal && (
        <NewAnalysisModal
          onClose={() => setShowAnalysisModal(false)}
          onSubmit={handleNewAnalysis}
        />
      )}
      </div>
    </div>
  );
};

export default InvestmentTerminal;


