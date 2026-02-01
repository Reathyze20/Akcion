/**
 * GatekeeperShield Component
 * ==========================
 *
 * Higher-Order Component (HOC) wrapper that enforces Gomes investment rules.
 * Psychologically blocks investors from "falling in love" with toxic stocks.
 *
 * Priority Logic (top-down, highest priority first):
 * 1. LOCKED (Toxic): cash_runway < 6 months → Full blur, ☣️ icon
 * 2. LOCKED (Bear): price < wma_30 AND stage == 4 → Full blur, 📉 icon
 * 3. WARNING: gomes_score < 7 → Yellow banner, max 3% allocation
 * 4. SAFE: All checks passed → Standard display
 *
 * Author: GitHub Copilot with Claude Opus 4.5
 * Date: 2026-02-01
 */

import React from "react";
import { ShieldX } from "lucide-react";
import { evaluateShieldState, type GatekeeperAnalysis, type ShieldState } from "../hooks/useGatekeeperStatus";

// Types are re-exported for convenience
export type { GatekeeperAnalysis, ShieldState, ShieldConfig } from "../hooks/useGatekeeperStatus";

interface GatekeeperShieldProps {
  analysis: GatekeeperAnalysis;
  children: React.ReactNode;
  /**
   * Optional callback when shield blocks content
   */
  onBlocked?: (reason: ShieldState) => void;
}

// ============================================================================
// COMPONENT
// ============================================================================

export const GatekeeperShield: React.FC<GatekeeperShieldProps> = ({ analysis, children, onBlocked }) => {
  const config = evaluateShieldState(analysis);

  // Notify parent if blocked
  React.useEffect(() => {
    if (config.state !== "OPEN" && onBlocked) {
      onBlocked(config.state);
    }
  }, [config.state, onBlocked]);

  // -------------------------------------------------------------------------
  // LOCKED STATES: Full Blur + Overlay
  // -------------------------------------------------------------------------
  if (config.blur && config.showOverlay) {
    return (
      <div className="relative w-full h-full">
        {/* Blurred Content */}
        <div className="filter blur-lg pointer-events-none select-none opacity-50">{children}</div>

        {/* Blocking Overlay */}
        <div className={`absolute inset-0 ${config.overlayColor} flex flex-col items-center justify-center z-50 rounded-xl`}>
          {/* Icon */}
          <div className="mb-4 animate-pulse">{config.icon}</div>

          {/* Title */}
          <h2 className="text-2xl font-black text-text-primary mb-2 tracking-wider">{config.title}</h2>

          {/* Message */}
          <p className="text-center text-text-secondary max-w-md px-8 leading-relaxed">{config.message}</p>

          {/* Lock Badge */}
          <div className="mt-6 flex items-center gap-2 px-4 py-2 bg-surface-overlay/50 rounded-lg border border-border">
            <ShieldX className="w-4 h-4 text-negative" />
            <span className="text-xs font-bold text-negative uppercase tracking-wider">Position Blocked by Gomes Gatekeeper</span>
          </div>

          {/* Explanation for Stage 4 */}
          {config.state === "LOCKED_BEAR" && (
            <div className="mt-6 p-4 bg-surface-raised/30 rounded-lg border border-border max-w-md">
              <h4 className="text-xs font-bold text-text-secondary mb-2">WEINSTEIN RULES:</h4>
              <ul className="text-xs text-text-muted space-y-1">
                <li>• Stage 4 = Declining phase (price below falling 30 WMA)</li>
                <li>• Never buy into falling momentum</li>
                <li>• Wait for Stage 1 (basing) or Stage 2 (breakout)</li>
              </ul>
            </div>
          )}

          {/* Explanation for Dilution */}
          {config.state === "LOCKED_TOXIC" && (
            <div className="mt-6 p-4 bg-negative/10 rounded-lg border border-negative/30 max-w-md">
              <h4 className="text-xs font-bold text-negative mb-2">DILUTION RISK EXPLAINED:</h4>
              <ul className="text-xs text-negative/80 space-y-1">
                <li>• Company has less than 6 months of cash</li>
                <li>• Will likely raise capital via share issuance</li>
                <li>• New shares = your ownership gets diluted</li>
                <li>• "You can't win a race with broken legs" - Gomes</li>
              </ul>
            </div>
          )}
        </div>
      </div>
    );
  }

  // -------------------------------------------------------------------------
  // WARNING STATE: Yellow Banner at Top
  // -------------------------------------------------------------------------
  if (config.state === "WARNING") {
    return (
      <div className="relative w-full h-full">
        {/* Warning Banner */}
        <div className="sticky top-0 z-40 bg-warning/20 border-b border-warning/50 px-4 py-2 flex items-center gap-3">
          {config.icon}
          <div className="flex-1">
            <span className="font-bold text-warning text-sm">{config.title}:</span>
            <span className="text-warning/80 text-sm ml-2">{config.message}</span>
          </div>
          <div className="px-3 py-1 bg-warning/30 rounded-lg border border-warning/50">
            <span className="text-xs font-bold text-warning">MAX 3%</span>
          </div>
        </div>

        {/* Normal Content */}
        {children}
      </div>
    );
  }

  // -------------------------------------------------------------------------
  // OPEN STATE: Normal display
  // -------------------------------------------------------------------------
  return <>{children}</>;
};

export default GatekeeperShield;
