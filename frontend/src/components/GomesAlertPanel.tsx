/**
 * Gomes Alert Panel Component
 *
 * Displays critical thesis drift alerts prominently at the top of the page.
 * THESIS_BROKEN alerts are shown in red with immediate action required.
 *
 * Alert Priority:
 * 1. CRITICAL (THESIS_BROKEN) - Red, skull icon
 * 2. WARNING (THESIS_DRIFT) - Yellow, warning icon
 * 3. OPPORTUNITY (IMPROVEMENT) - Green, rocket icon
 * 4. INFO - Gray, info icon
 *
 * @author GitHub Copilot with Claude Opus 4.5
 * @date 2026-02-01
 */

import React, { useEffect, useState, useCallback } from "react";
import {
  AlertTriangle,
  XCircle,
  Skull,
  TrendingDown,
  TrendingUp,
  Info,
  CheckCircle,
  X,
  Bell,
} from "lucide-react";

// ==============================================================================
// TYPES
// ==============================================================================

interface GomesAlert {
  id: number;
  ticker: string;
  alert_type: "THESIS_BROKEN" | "THESIS_DRIFT" | "IMPROVEMENT" | "MAJOR_IMPROVEMENT" | "STABLE";
  severity: "CRITICAL" | "WARNING" | "INFO" | "OPPORTUNITY";
  title: string;
  message: string;
  recommendation: string | null;
  previous_score: number | null;
  current_score: number;
  score_delta: number;
  is_read: boolean;
  created_at: string;
}

interface AlertCount {
  total: number;
  critical: number;
  warning: number;
  info: number;
  opportunity: number;
}

interface GomesAlertPanelProps {
  /** Whether to show all alerts or just critical ones */
  showAllAlerts?: boolean;
  /** Maximum number of alerts to display */
  maxAlerts?: number;
  /** Callback when an alert is dismissed */
  onAlertDismiss?: (alertId: number) => void;
  /** Callback when user clicks "Take Action" */
  onTakeAction?: (ticker: string, alertType: string) => void;
}

// ==============================================================================
// ALERT CONFIGURATION
// ==============================================================================

const ALERT_CONFIG = {
  CRITICAL: {
    icon: Skull,
    bgClass: "bg-red-50 border-red-200",
    textClass: "text-red-800",
    iconClass: "text-red-600",
    badgeClass: "bg-red-600",
    label: "KRITICKÉ",
  },
  WARNING: {
    icon: AlertTriangle,
    bgClass: "bg-yellow-50 border-yellow-200",
    textClass: "text-yellow-800",
    iconClass: "text-yellow-600",
    badgeClass: "bg-yellow-500",
    label: "VAROVÁNÍ",
  },
  OPPORTUNITY: {
    icon: TrendingUp,
    bgClass: "bg-positive-bg border-positive",
    textClass: "text-positive",
    iconClass: "text-positive",
    badgeClass: "bg-positive",
    label: "PŘÍLEŽITOST",
  },
  INFO: {
    icon: Info,
    bgClass: "bg-gray-50 border-gray-200",
    textClass: "text-gray-800",
    iconClass: "text-gray-600",
    badgeClass: "bg-gray-500",
    label: "INFO",
  },
};

// ==============================================================================
// COMPONENT
// ==============================================================================

export const GomesAlertPanel: React.FC<GomesAlertPanelProps> = ({
  showAllAlerts = false,
  maxAlerts = 5,
  onAlertDismiss,
  onTakeAction,
}) => {
  const [alerts, setAlerts] = useState<GomesAlert[]>([]);
  const [alertCount, setAlertCount] = useState<AlertCount>({
    total: 0,
    critical: 0,
    warning: 0,
    info: 0,
    opportunity: 0,
  });
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState(false);

  // Fetch alerts from API
  const fetchAlerts = useCallback(async () => {
    try {
      setLoading(true);

      // Fetch alert count
      const countResponse = await fetch("/api/trading/alerts/count");
      if (countResponse.ok) {
        const countData = await countResponse.json();
        setAlertCount(countData);
      }

      // Fetch alerts
      const severity = showAllAlerts ? "" : "CRITICAL";
      const url = `/api/trading/alerts?unread_only=true&limit=${maxAlerts}${severity ? `&severity=${severity}` : ""}`;

      const response = await fetch(url);
      if (!response.ok) throw new Error("Nepodařilo se načíst alerty");

      const data = await response.json();
      setAlerts(data);
    } catch (err) {
      console.error("Failed to fetch alerts:", err);
    } finally {
      setLoading(false);
    }
  }, [showAllAlerts, maxAlerts]);

  useEffect(() => {
    fetchAlerts();
    // Refresh every 30 seconds
    const interval = setInterval(fetchAlerts, 30000);
    return () => clearInterval(interval);
  }, [fetchAlerts]);

  // Handle alert dismissal
  const handleDismiss = async (alertId: number) => {
    try {
      const response = await fetch(`/api/trading/alerts/${alertId}/action`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "dismissed" }),
      });

      if (response.ok) {
        setAlerts((prev) => prev.filter((a) => a.id !== alertId));
        setAlertCount((prev) => ({
          ...prev,
          total: prev.total - 1,
        }));
        onAlertDismiss?.(alertId);
      }
    } catch (err) {
      console.error("Failed to dismiss alert:", err);
    }
  };

  // Handle taking action on alert
  const handleTakeAction = async (alert: GomesAlert) => {
    try {
      await fetch(`/api/trading/alerts/${alert.id}/action`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "acted_upon" }),
      });

      onTakeAction?.(alert.ticker, alert.alert_type);
    } catch (err) {
      console.error("Failed to mark action:", err);
    }
  };

  // Get score delta display
  const getScoreDeltaDisplay = (delta: number): React.ReactNode => {
    if (delta < 0) {
      return (
        <span className="flex items-center text-red-600 font-bold">
          <TrendingDown className="w-4 h-4 mr-1" />
          {delta}
        </span>
      );
    } else if (delta > 0) {
      return (
        <span className="flex items-center text-positive font-bold">
          <TrendingUp className="w-4 h-4 mr-1" />+{delta}
        </span>
      );
    }
    return <span className="text-gray-500">0</span>;
  };

  // Render nothing if no critical alerts
  if (!loading && alerts.length === 0 && alertCount.critical === 0) {
    return null;
  }

  // Loading skeleton
  if (loading && alerts.length === 0) {
    return (
      <div className="mb-4 p-4 bg-gray-50 border border-gray-200 rounded-lg animate-pulse">
        <div className="h-6 bg-gray-200 rounded w-1/3 mb-2"></div>
        <div className="h-4 bg-gray-200 rounded w-2/3"></div>
      </div>
    );
  }

  return (
    <div className="mb-4">
      {/* Alert Summary Header */}
      {alertCount.total > 0 && (
        <div
          className={`
            flex items-center justify-between p-3 rounded-lg cursor-pointer
            ${alertCount.critical > 0 ? "bg-red-100 border border-red-300" : "bg-yellow-100 border border-yellow-300"}
          `}
          onClick={() => setExpanded(!expanded)}
        >
          <div className="flex items-center gap-3">
            <Bell className={`w-5 h-5 ${alertCount.critical > 0 ? "text-red-600" : "text-yellow-600"}`} />
            <span className={`font-semibold ${alertCount.critical > 0 ? "text-red-800" : "text-yellow-800"}`}>
              {alertCount.total} nepřečtených alertů
            </span>

            {/* Severity badges */}
            <div className="flex gap-2">
              {alertCount.critical > 0 && (
                <span className="px-2 py-0.5 text-xs font-bold bg-red-600 text-text-primary rounded-full">
                  {alertCount.critical} kritických
                </span>
              )}
              {alertCount.warning > 0 && (
                <span className="px-2 py-0.5 text-xs font-bold bg-yellow-500 text-white rounded-full">{alertCount.warning} varování</span>
              )}
              {alertCount.opportunity > 0 && (
                <span className="px-2 py-0.5 text-xs font-bold bg-positive text-text-primary rounded-full">
                  {alertCount.opportunity} příležitostí
                </span>
              )}
            </div>
          </div>

          <span className={`text-sm ${alertCount.critical > 0 ? "text-red-600" : "text-yellow-600"}`}>{expanded ? "Skrýt ▲" : "Zobrazit ▼"}</span>
        </div>
      )}

      {/* Alert Details */}
      {expanded && (
        <div className="mt-2 space-y-2">
          {alerts.map((alert) => {
            const config = ALERT_CONFIG[alert.severity] || ALERT_CONFIG.INFO;
            const Icon = config.icon;

            return (
              <div key={alert.id} className={`p-4 rounded-lg border ${config.bgClass} relative`}>
                {/* Dismiss button */}
                <button
                  onClick={() => handleDismiss(alert.id)}
                  className="absolute top-2 right-2 p-1 rounded hover:bg-black/10 transition-colors"
                  title="Zavřít"
                >
                  <X className="w-4 h-4 text-gray-500" />
                </button>

                {/* Alert content */}
                <div className="flex items-start gap-3">
                  <div className={`p-2 rounded-full ${config.bgClass}`}>
                    <Icon className={`w-6 h-6 ${config.iconClass}`} />
                  </div>

                  <div className="flex-1">
                    {/* Header */}
                    <div className="flex items-center gap-2 mb-1">
                      <span className={`px-2 py-0.5 text-xs font-bold text-text-primary rounded ${config.badgeClass}`}>{config.label}</span>
                      <span className="font-bold text-lg">{alert.ticker}</span>
                      <span className="text-sm text-gray-500">{new Date(alert.created_at).toLocaleString("cs-CZ")}</span>
                    </div>

                    {/* Title */}
                    <h4 className={`font-semibold ${config.textClass}`}>{alert.title}</h4>

                    {/* Message */}
                    <p className="text-sm text-gray-700 mt-1">{alert.message}</p>

                    {/* Score change */}
                    <div className="flex items-center gap-4 mt-2 text-sm">
                      <div>
                        <span className="text-gray-500">Score:</span>{" "}
                        <span className="font-semibold">
                          {alert.previous_score ?? "?"} → {alert.current_score}
                        </span>
                      </div>
                      <div>
                        <span className="text-gray-500">Změna:</span> {getScoreDeltaDisplay(alert.score_delta)}
                      </div>
                    </div>

                    {/* Recommendation */}
                    {alert.recommendation && (
                      <div className={`mt-2 p-2 rounded ${alert.severity === "CRITICAL" ? "bg-red-100" : "bg-gray-100"}`}>
                        <span className="font-semibold text-sm">Doporučení: </span>
                        <span className="text-sm">{alert.recommendation}</span>
                      </div>
                    )}

                    {/* Action buttons */}
                    <div className="flex gap-2 mt-3">
                      {alert.severity === "CRITICAL" && (
                        <button
                          onClick={() => handleTakeAction(alert)}
                          className="px-3 py-1.5 bg-red-600 text-text-primary text-sm font-semibold rounded hover:bg-red-700 transition-colors flex items-center gap-1"
                        >
                          <XCircle className="w-4 h-4" />
                          Prodat pozici
                        </button>
                      )}
                      {alert.severity === "OPPORTUNITY" && (
                        <button
                          onClick={() => handleTakeAction(alert)}
                          className="px-3 py-1.5 bg-positive text-text-primary text-sm font-semibold rounded hover:bg-green-600 transition-colors flex items-center gap-1"
                        >
                          <CheckCircle className="w-4 h-4" />
                          Přidat pozici
                        </button>
                      )}
                      <button
                        onClick={() => handleDismiss(alert.id)}
                        className="px-3 py-1.5 bg-gray-200 text-gray-700 text-sm rounded hover:bg-gray-300 transition-colors"
                      >
                        Zamítnout
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

// ==============================================================================
// COMPACT BADGE (For header/navbar)
// ==============================================================================

interface AlertBadgeProps {
  onClick?: () => void;
}

export const GomesAlertBadge: React.FC<AlertBadgeProps> = ({ onClick }) => {
  const [count, setCount] = useState<AlertCount>({
    total: 0,
    critical: 0,
    warning: 0,
    info: 0,
    opportunity: 0,
  });

  useEffect(() => {
    const fetchCount = async () => {
      try {
        const response = await fetch("/api/trading/alerts/count");
        if (response.ok) {
          setCount(await response.json());
        }
      } catch (err) {
        console.error("Failed to fetch alert count:", err);
      }
    };

    fetchCount();
    const interval = setInterval(fetchCount, 30000);
    return () => clearInterval(interval);
  }, []);

  if (count.total === 0) return null;

  return (
    <button onClick={onClick} className="relative p-2 rounded-full hover:bg-gray-100 transition-colors" title={`${count.total} nepřečtených alertů`}>
      <Bell className={`w-5 h-5 ${count.critical > 0 ? "text-red-600" : "text-gray-600"}`} />

      {/* Badge */}
      <span
        className={`
        absolute -top-1 -right-1 px-1.5 py-0.5 text-xs font-bold text-text-primary rounded-full
        ${count.critical > 0 ? "bg-red-600 animate-pulse" : "bg-yellow-500"}
      `}
      >
        {count.total}
      </span>
    </button>
  );
};

export default GomesAlertPanel;
