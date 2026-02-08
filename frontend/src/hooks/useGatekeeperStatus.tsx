/**
 * useGatekeeperStatus Hook
 * =========================
 *
 * Standalone hook to get Gatekeeper status without rendering the shield.
 * Separated from GatekeeperShield.tsx to enable Fast Refresh.
 *
 * @author GitHub Copilot with Claude Opus 4.5
 * @date 2026-02-01
 */

import { useMemo } from "react";
import { TrendingDown, ShieldAlert, ShieldCheck } from "lucide-react";
import type { ReactNode } from "react";

// ============================================================================
// TYPES
// ============================================================================

export interface GatekeeperAnalysis {
  cash_runway_months: number | null;
  stock_price: number | null;
  wma_30: number | null;
  stage_analysis: 1 | 2 | 3 | 4 | null;
  gomes_score: number | null;
}

export type ShieldState = "LOCKED_TOXIC" | "LOCKED_BEAR" | "WARNING" | "OPEN";

export interface ShieldConfig {
  state: ShieldState;
  blur: boolean;
  showOverlay: boolean;
  overlayColor: string;
  icon: ReactNode;
  title: string;
  message: string;
  hideBuyButton: boolean;
  maxAllocation: number | null;
}

// ============================================================================
// SHIELD LOGIC
// ============================================================================

export function evaluateShieldState(analysis: GatekeeperAnalysis): ShieldConfig {
  const { cash_runway_months, stock_price, wma_30, stage_analysis, gomes_score } = analysis;

  // -------------------------------------------------------------------------
  // Priority 1 (CRITICAL): Cash Runway < 6 months = DILUTION IMMINENT
  // -------------------------------------------------------------------------
  if (cash_runway_months !== null && cash_runway_months < 6) {
    return {
      state: "LOCKED_TOXIC",
      blur: true,
      showOverlay: true,
      overlayColor: "bg-negative/90",
      icon: <span className="text-6xl">☣️</span>,
      title: "DILUTION IMMINENT",
      message: `Cash runway: ${cash_runway_months} months. Company will likely issue new shares at unfavorable terms. UNINVESTABLE.`,
      hideBuyButton: true,
      maxAllocation: 0,
    };
  }

  // -------------------------------------------------------------------------
  // Priority 2 (CRITICAL): Weinstein Stage 4 (price < falling 30 WMA)
  // -------------------------------------------------------------------------
  if (stock_price !== null && wma_30 !== null && stage_analysis === 4 && stock_price < wma_30) {
    const percentBelow = (((wma_30 - stock_price) / wma_30) * 100).toFixed(1);
    return {
      state: "LOCKED_BEAR",
      blur: true,
      showOverlay: true,
      overlayColor: "bg-slate-900/95",
      icon: <TrendingDown className="w-16 h-16 text-negative" />,
      title: "WEINSTEIN STAGE 4",
      message: `Price ${percentBelow}% below falling 30 WMA. DON'T CATCH A FALLING KNIFE. Wait for Stage 1 base formation.`,
      hideBuyButton: true,
      maxAllocation: 0,
    };
  }

  // -------------------------------------------------------------------------
  // Priority 3 (WARNING): Low Conviction Score < 7
  // -------------------------------------------------------------------------
  if (gomes_score !== null && gomes_score < 7) {
    return {
      state: "WARNING",
      blur: false,
      showOverlay: false,
      overlayColor: "",
      icon: <ShieldAlert className="w-5 h-5 text-warning" />,
      title: "LOW CONVICTION",
      message: `Score ${gomes_score}/10. Speculative position only. Max 3% portfolio allocation.`,
      hideBuyButton: false,
      maxAllocation: 3,
    };
  }

  // -------------------------------------------------------------------------
  // Priority 4 (SAFE): All checks passed
  // -------------------------------------------------------------------------
  return {
    state: "OPEN",
    blur: false,
    showOverlay: false,
    overlayColor: "",
    icon: <ShieldCheck className="w-5 h-5 text-positive" />,
    title: "CLEAR TO TRADE",
    message: "",
    hideBuyButton: false,
    maxAllocation: null, // Use default from Gomes Logic
  };
}

// ============================================================================
// HOOK
// ============================================================================

/**
 * Hook to get Gatekeeper status without rendering the shield
 */
export function useGatekeeperStatus(analysis: GatekeeperAnalysis): ShieldConfig {
  return useMemo(() => evaluateShieldState(analysis), [analysis]);
}
