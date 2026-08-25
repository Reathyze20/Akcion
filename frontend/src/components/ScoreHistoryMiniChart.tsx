/**
 * ScoreHistoryMiniChart Component
 * 
 * Mini sparkline graph showing Conviction Score evolution over time.
 * Used in StockCard to show thesis drift visually.
 */

import React, { useState, useEffect } from 'react';
import { TrendingUp, TrendingDown, Minus, AlertTriangle } from 'lucide-react';
import { apiClient } from '../api/client';
import type { ScoreHistoryItem } from '../api/client';

interface ScoreHistoryMiniChartProps {
  ticker: string;
  currentScore?: number;
  showAlert?: boolean;
  height?: number;
  width?: number;
}

export const ScoreHistoryMiniChart: React.FC<ScoreHistoryMiniChartProps> = ({
  ticker,
  currentScore,
  showAlert = true,
  height = 40,
  width = 100,
}) => {
  const [history, setHistory] = useState<ScoreHistoryItem[]>([]);
  const [trend, setTrend] = useState<'UP' | 'DOWN' | 'STABLE'>('STABLE');
  const [loading, setLoading] = useState(true);
  const [hasAlert, setHasAlert] = useState(false);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const fetchHistory = async () => {
      try {
        // API returns a flat list, newest first.
        const data = await apiClient.getScoreHistory(ticker);
        const oldestFirst = [...data].reverse().slice(-10);
        setHistory(oldestFirst);

        // Trend + score-drop alert from the two most recent records.
        if (data.length >= 2) {
          const latest = data[0];
          const previous = data[1];
          setTrend(
            latest.score > previous.score ? 'UP'
              : latest.score < previous.score ? 'DOWN'
              : 'STABLE'
          );
          if (latest.score < previous.score - 1) {
            setHasAlert(true); // score dropped by more than a point
          }
        }
      } catch {
        /* Nenačteno není totéž co prázdno. Dřív obojí skončilo stejně —
           komponenta zmizela — takže rozbitý endpoint vypadal jako ticker
           bez historie a nikdo se to nedozvěděl. Endpoint byl přitom
           rozbitý měsíce. */
        setFailed(true);
      } finally {
        setLoading(false);
      }
    };

    fetchHistory();
  }, [ticker]);

  if (failed) {
    /* Malé, tiché, ale viditelné: sparkline vedle skóre není místo na
       chybovou hlášku, ale mlčet o tom, že data nedorazila, taky nejde. */
    return (
      <span
        className="text-[10px] text-text-muted"
        title="Historii skóre se nepodařilo načíst"
      >
        historie ?
      </span>
    );
  }

  if (loading || history.length < 2) {
    /* Jeden bod není trend a nula bodů není nic k nakreslení. Ticker, který
       byl oskórován jednou, tu prostě žádnou křivku nemá. */
    return null;
  }

  // Calculate SVG path for sparkline
  const maxScore = 10;
  const minScore = 0;
  const points = history.map((point, index) => {
    const x = (index / (history.length - 1)) * width;
    const y = height - ((point.score - minScore) / (maxScore - minScore)) * height;
    return { x, y, score: point.score };
  });

  const pathD = points.map((p, i) => 
    `${i === 0 ? 'M' : 'L'} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`
  ).join(' ');

  // Color based on trend
  const strokeColor = trend === 'UP'
    ? 'rgb(var(--positive))'
    : trend === 'DOWN'
      ? 'rgb(var(--negative))'
      : 'rgb(var(--text-muted))';
  const TrendIcon = trend === 'UP' ? TrendingUp : trend === 'DOWN' ? TrendingDown : Minus;

  return (
    <div className="flex items-center gap-2">
      {/* Sparkline */}
      <div className="relative">
        <svg width={width} height={height} className="overflow-visible">
          {/* Gradient fill */}
          <defs>
            <linearGradient id={`gradient-${ticker}`} x1="0%" y1="0%" x2="0%" y2="100%">
              <stop offset="0%" stopColor={strokeColor} stopOpacity="0.3" />
              <stop offset="100%" stopColor={strokeColor} stopOpacity="0" />
            </linearGradient>
          </defs>
          
          {/* Area under line */}
          <path
            d={`${pathD} L ${width} ${height} L 0 ${height} Z`}
            fill={`url(#gradient-${ticker})`}
          />
          
          {/* Line */}
          <path
            d={pathD}
            fill="none"
            stroke={strokeColor}
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          
          {/* Current point */}
          {points.length > 0 && (
            <circle
              cx={points[points.length - 1].x}
              cy={points[points.length - 1].y}
              r="3"
              fill={strokeColor}
              className="animate-pulse"
            />
          )}
        </svg>
      </div>

      {/* Trend indicator */}
      <div className="flex flex-col items-center">
        <TrendIcon 
          className={`w-4 h-4 ${
            trend === 'UP' ? 'text-positive' : 
            trend === 'DOWN' ? 'text-negative' : 
            'text-text-secondary'
          }`} 
        />
        {currentScore !== undefined && (
          <span className={`text-xs font-bold ${
            currentScore >= 8 ? 'text-positive' :
            currentScore >= 5 ? 'text-warning' :
            'text-negative'
          }`}>
            {currentScore}
          </span>
        )}
      </div>

      {/* Thesis Drift Alert */}
      {showAlert && hasAlert && (
        <div className="relative group">
          <AlertTriangle className="w-4 h-4 text-warning animate-pulse" />
          <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1 px-2 py-1 
                          bg-warning/90 text-warning text-[10px] rounded whitespace-nowrap
                          opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none
                          border border-warning/50">
            Skóre kleslo o víc než 1 bod!
          </div>
        </div>
      )}
    </div>
  );
};

export default ScoreHistoryMiniChart;


