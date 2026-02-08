/**
 * SafetyBadge Component
 * 
 * Visual traffic light indicator for critical safety metrics.
 * Part of the "Decision Cockpit" design - Safety First approach.
 * 
 * @fiduciary This component enforces Gomes Rule #2: Never buy with < 6 months runway
 */

import React from 'react';
import { 
  Shield, 
  AlertTriangle, 
  CheckCircle, 
  XCircle,
  Clock,
  TrendingUp,
  Activity
} from 'lucide-react';

export type SafetyStatus = 'safe' | 'warning' | 'danger' | 'unknown';

export interface SafetyBadgeProps {
  label: string;
  value: string | number | null;
  status: SafetyStatus;
  icon?: 'shield' | 'clock' | 'trend' | 'activity';
  tooltip?: string;
}

const statusColors: Record<SafetyStatus, string> = {
  safe: 'bg-positive/20 border-positive text-positive',
  warning: 'bg-warning/20 border-warning text-warning',
  danger: 'bg-negative/20 border-negative text-negative',
  unknown: 'bg-text-muted/20 border-text-muted text-text-muted',
};

const statusIcons: Record<SafetyStatus, React.ReactNode> = {
  safe: <CheckCircle className="w-4 h-4" />,
  warning: <AlertTriangle className="w-4 h-4" />,
  danger: <XCircle className="w-4 h-4" />,
  unknown: <Shield className="w-4 h-4" />,
};

const labelIcons: Record<string, React.ReactNode> = {
  shield: <Shield className="w-4 h-4" />,
  clock: <Clock className="w-4 h-4" />,
  trend: <TrendingUp className="w-4 h-4" />,
  activity: <Activity className="w-4 h-4" />,
};

export const SafetyBadge: React.FC<SafetyBadgeProps> = ({
  label,
  value,
  status,
  icon,
  tooltip,
}) => {
  return (
    <div
      className={`
        flex items-center gap-2 px-3 py-2 rounded-lg border
        ${statusColors[status]}
        transition-all hover:scale-105
      `}
      title={tooltip}
    >
      {/* Icon */}
      <span className="flex-shrink-0">
        {icon ? labelIcons[icon] : statusIcons[status]}
      </span>
      
      {/* Content */}
      <div className="flex flex-col">
        <span className="text-xs opacity-80">{label}</span>
        <span className="font-bold text-sm">
          {value ?? 'N/A'}
        </span>
      </div>
    </div>
  );
};

/**
 * SafetyGaugeRow Component
 * 
 * A row of safety badges that act as "pre-flight checks" before trading.
 * Shows Cash Runway, Weinstein Stage, and Lifecycle Phase at a glance.
 */
export interface SafetyGaugeRowProps {
  cashRunwayMonths: number | null;
  inflectionStatus: 'WAIT_TIME' | 'UPCOMING' | 'ACTIVE_GOLD_MINE' | null;
  priceZone: string | null;
  marketAlert?: 'RED' | 'YELLOW' | 'GREEN';
}

/**
 * Determine cash runway safety status
 * @fiduciary Rule: < 6 months = DANGER (potential bankruptcy)
 */
const getCashRunwayStatus = (months: number | null): SafetyStatus => {
  if (months === null) return 'unknown';
  if (months < 6) return 'danger';
  if (months < 12) return 'warning';
  return 'safe';
};

/**
 * Determine lifecycle stage safety status
 * @fiduciary Rule: Only "GOLD_MINE" is safe to buy
 */
const getLifecycleStatus = (status: string | null): SafetyStatus => {
  if (!status) return 'unknown';
  if (status === 'ACTIVE_GOLD_MINE') return 'safe';
  if (status === 'UPCOMING') return 'warning';
  return 'danger'; // WAIT_TIME
};

/**
 * Determine price zone safety status
 */
const getPriceZoneStatus = (zone: string | null): SafetyStatus => {
  if (!zone) return 'unknown';
  if (['DEEP_VALUE', 'BUY_ZONE'].includes(zone)) return 'safe';
  if (['ACCUMULATE', 'FAIR_VALUE'].includes(zone)) return 'warning';
  return 'danger'; // SELL_ZONE, OVERVALUED
};

export const SafetyGaugeRow: React.FC<SafetyGaugeRowProps> = ({
  cashRunwayMonths,
  inflectionStatus,
  priceZone,
  marketAlert = 'GREEN',
}) => {
  const runwayStatus = getCashRunwayStatus(cashRunwayMonths);
  const lifecycleStatus = getLifecycleStatus(inflectionStatus);
  const zoneStatus = getPriceZoneStatus(priceZone);
  
  // Market alert badge
  const marketStatus: SafetyStatus = 
    marketAlert === 'RED' ? 'danger' :
    marketAlert === 'YELLOW' ? 'warning' : 'safe';
  
  return (
    <div className="flex flex-wrap gap-2 p-3 bg-primary-card rounded-lg border border-border">
      {/* Market Alert */}
      <SafetyBadge
        label="Trh"
        value={marketAlert}
        status={marketStatus}
        icon="activity"
        tooltip="Aktuální stav trhu podle Gomes Traffic Light"
      />
      
      {/* Cash Runway */}
      <SafetyBadge
        label="Cash Runway"
        value={cashRunwayMonths ? `${cashRunwayMonths} měs.` : null}
        status={runwayStatus}
        icon="clock"
        tooltip={runwayStatus === 'danger' 
          ? '⚠️ NEBEZPEČÍ: Méně než 6 měsíců hotovosti!'
          : 'Počet měsíců hotovosti před potřebou financování'}
      />
      
      {/* Lifecycle Phase */}
      <SafetyBadge
        label="Fáze"
        value={inflectionStatus?.replace('_', ' ') ?? null}
        status={lifecycleStatus}
        icon="trend"
        tooltip={lifecycleStatus === 'danger'
          ? '⏸️ WAIT TIME: Nekupovat dokud nedojde k inflexnímu bodu'
          : 'Fáze investičního životního cyklu'}
      />
      
      {/* Price Zone */}
      <SafetyBadge
        label="Cenová zóna"
        value={priceZone?.replace('_', ' ') ?? null}
        status={zoneStatus}
        icon="shield"
        tooltip="Pozice aktuální ceny mezi Green Line a Red Line"
      />
    </div>
  );
};

export default SafetyBadge;
