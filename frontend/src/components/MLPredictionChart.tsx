/**
 * ML Prediction Chart Component
 *
 * Interactive chart showing historical prices and ML predictions.
 * Dark theme design matching the Akcion app.
 */

import React, { useEffect, useState } from "react";
import {
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
  Area,
  ComposedChart,
  Line,
} from "recharts";

interface AnalystContext {
  company_name?: string;
  analyst?: string;
  sentiment?: string;
  action_verdict?: string;
  gomes_score?: number;
  edge?: string;
  catalysts?: string;
  risks?: string;
  price_target_short?: string;
  price_target_long?: string;
  time_horizon?: string;
  entry_zone?: string;
  video_date?: string;
}

interface MLPrediction {
  ticker: string;
  prediction_type: string;
  confidence: number;
  current_price: number;
  predicted_price: number;
  horizon_days: number;
  quality: string;
  ci_80_lower: number;
  ci_80_upper: number;
  ci_90_lower: number;
  ci_90_upper: number;
  created_at: string;
  valid_until: string;
  analyst_context?: AnalystContext;
}

interface PriceData {
  date: string;
  price?: number;
  predicted?: number;
  ci_80_lower?: number;
  ci_80_upper?: number;
  ci_90_lower?: number;
  ci_90_upper?: number;
}

interface MLPredictionChartProps {
  ticker: string;
  historicalDays?: number;
  onClose?: () => void;
}

// Custom tooltip component
const CustomTooltip = ({ active, payload, label }: any) => {
  if (active && payload && payload.length) {
    const data = payload[0]?.payload;
    return (
      <div className="bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 shadow-xl">
        <p className="text-slate-400 text-xs mb-1">{label}</p>
        {data?.price && (
          <p className="text-white font-medium">
            Price: <span className="text-blue-400">${data.price.toFixed(2)}</span>
          </p>
        )}
        {data?.predicted && (
          <p className="text-white font-medium">
            Predicted: <span className="text-emerald-400">${data.predicted.toFixed(2)}</span>
          </p>
        )}
        {data?.ci_80_lower && data?.ci_80_upper && (
          <p className="text-slate-400 text-xs mt-1">
            80% CI: ${data.ci_80_lower.toFixed(2)} - ${data.ci_80_upper.toFixed(2)}
          </p>
        )}
      </div>
    );
  }
  return null;
};

const MLPredictionChart: React.FC<MLPredictionChartProps> = ({
  ticker,
  historicalDays = 60,
  onClose,
}) => {
  const [prediction, setPrediction] = useState<MLPrediction | null>(null);
  const [priceData, setPriceData] = useState<PriceData[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);

  useEffect(() => {
    fetchData();
  }, [ticker, historicalDays]);

  const fetchData = async () => {
    try {
      setLoading(true);
      setError(null);

      // Fetch ML prediction first
      const predResponse = await fetch(`/api/trading/predictions/${ticker}`);
      let predData: MLPrediction | null = null;

      if (predResponse.ok) {
        predData = await predResponse.json();
        setPrediction(predData);
      } else if (predResponse.status === 404) {
        setPrediction(null);
      } else {
        const errorData = await predResponse.json();
        throw new Error(errorData.detail || "Failed to fetch prediction");
      }

      // Fetch real historical prices from OHLCV endpoint
      const ohlcvResponse = await fetch(`/api/trading/ohlcv/${ticker}?days=${historicalDays}`);

      if (ohlcvResponse.ok) {
        const ohlcvData = await ohlcvResponse.json();
        const prices: PriceData[] = ohlcvData.data.map((d: any) => ({
          date: d.date,
          price: d.close,
        }));
        setPriceData(prices);
      } else {
        setPriceData([]);
      }

      setError(null);
    } catch (err: any) {
      setError(err.message);
      console.error("Failed to fetch chart data:", err);
    } finally {
      setLoading(false);
    }
  };

  const generatePrediction = async () => {
    try {
      setIsGenerating(true);
      const response = await fetch(`/api/trading/predict/${ticker}`, { method: "POST" });
      if (response.ok) {
        // Refresh data after generating
        await fetchData();
      } else {
        const errorData = await response.json();
        throw new Error(errorData.detail || "Failed to generate prediction");
      }
    } catch (err: any) {
      setError(err.message);
    } finally {
      setIsGenerating(false);
    }
  };

  const getChartData = (): PriceData[] => {
    if (priceData.length === 0) return [];

    const data: PriceData[] = [...priceData];

    // Add prediction points if we have a prediction
    if (prediction) {
      const lastDate = new Date(priceData[priceData.length - 1]?.date || new Date());
      
      // Add intermediate forecast points
      for (let i = 1; i <= prediction.horizon_days; i++) {
        const forecastDate = new Date(lastDate);
        forecastDate.setDate(forecastDate.getDate() + i);
        
        // Interpolate values
        const progress = i / prediction.horizon_days;
        const predictedPrice = prediction.current_price + 
          (prediction.predicted_price - prediction.current_price) * progress;
        
        data.push({
          date: forecastDate.toISOString().split("T")[0],
          price: undefined,
          predicted: predictedPrice,
          ci_80_lower: prediction.ci_80_lower + (predictedPrice - prediction.predicted_price),
          ci_80_upper: prediction.ci_80_upper + (predictedPrice - prediction.predicted_price),
          ci_90_lower: prediction.ci_90_lower + (predictedPrice - prediction.predicted_price),
          ci_90_upper: prediction.ci_90_upper + (predictedPrice - prediction.predicted_price),
        });
      }
    }

    return data;
  };

  const getPredictionColor = (type: string): string => {
    if (type === "UP") return "#10b981";
    if (type === "DOWN") return "#ef4444";
    return "#64748b";
  };

  const getQualityBadge = (quality: string) => {
    const styles: Record<string, string> = {
      HIGH_CONFIDENCE: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
      MEDIUM_CONFIDENCE: "bg-amber-500/10 text-amber-400 border-amber-500/20",
      LOW_CONFIDENCE: "bg-rose-500/10 text-rose-400 border-rose-500/20",
    };
    const labels: Record<string, string> = {
      HIGH_CONFIDENCE: "High",
      MEDIUM_CONFIDENCE: "Medium",
      LOW_CONFIDENCE: "Low",
    };
    return (
      <span className={`px-2 py-0.5 rounded-full text-xs font-medium border ${styles[quality] || styles.LOW_CONFIDENCE}`}>
        {labels[quality] || quality}
      </span>
    );
  };

  // Loading state
  if (loading) {
    return (
      <div className="bg-slate-900 rounded-xl border border-slate-800 p-6">
        <div className="animate-pulse">
          <div className="flex justify-between items-center mb-6">
            <div className="h-6 bg-slate-800 rounded w-48"></div>
            <div className="h-8 bg-slate-800 rounded w-20"></div>
          </div>
          <div className="h-80 bg-slate-800/50 rounded-lg"></div>
          <div className="grid grid-cols-4 gap-4 mt-4">
            {[1, 2, 3, 4].map((i) => (
              <div key={i} className="h-16 bg-slate-800 rounded"></div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  // No data state
  if (priceData.length === 0) {
    return (
      <div className="bg-slate-900 rounded-xl border border-slate-800 p-6">
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-xl font-bold text-white">{ticker} - Price Prediction</h2>
          {onClose && (
            <button onClick={onClose} className="text-slate-400 hover:text-white transition-colors">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          )}
        </div>
        <div className="text-center py-12">
          <div className="text-slate-400 mb-4">
            <svg className="w-16 h-16 mx-auto mb-4 opacity-50" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
            </svg>
            <p className="text-lg">No historical data available for {ticker}</p>
            <p className="text-sm text-slate-500 mt-2">Sync market data first to enable predictions</p>
          </div>
        </div>
      </div>
    );
  }

  const chartData = getChartData();
  const predColor = prediction ? getPredictionColor(prediction.prediction_type) : "#64748b";
  const priceChange = prediction
    ? ((prediction.predicted_price - prediction.current_price) / prediction.current_price) * 100
    : 0;

  return (
    <div className="bg-slate-900 rounded-xl border border-slate-800 overflow-hidden">
      {/* Header */}
      <div className="px-6 py-4 border-b border-slate-800">
        <div className="flex justify-between items-start">
          <div>
            <div className="flex items-center gap-3">
              <h2 className="text-xl font-bold text-white">{ticker}</h2>
              {prediction && getQualityBadge(prediction.quality)}
            </div>
            <p className="text-sm text-slate-400 mt-1">
              {historicalDays}d history + {prediction?.horizon_days || 5}d forecast
            </p>
          </div>
          <div className="flex items-center gap-3">
            {prediction ? (
              <div className="text-right">
                <div className="flex items-center gap-2">
                  <span
                    className="text-2xl font-bold"
                    style={{ color: predColor }}
                  >
                    {prediction.prediction_type === "UP" ? "↑" : prediction.prediction_type === "DOWN" ? "↓" : "→"}
                  </span>
                  <span className="text-lg font-semibold text-white">
                    {prediction.prediction_type}
                  </span>
                </div>
                <div className="text-sm text-slate-400">
                  {(prediction.confidence * 100).toFixed(0)}% confidence
                </div>
              </div>
            ) : (
              <button
                onClick={generatePrediction}
                disabled={isGenerating}
                className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-slate-700 text-white rounded-lg font-medium transition-colors flex items-center gap-2"
              >
                {isGenerating ? (
                  <>
                    <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                    </svg>
                    Generating...
                  </>
                ) : (
                  <>
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                    </svg>
                    Generate Prediction
                  </>
                )}
              </button>
            )}
            {onClose && (
              <button
                onClick={onClose}
                className="p-2 text-slate-400 hover:text-white hover:bg-slate-800 rounded-lg transition-colors"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Chart */}
      <div className="px-4 py-4">
        <ResponsiveContainer width="100%" height={350}>
          <ComposedChart data={chartData} margin={{ top: 10, right: 30, left: 10, bottom: 0 }}>
            <defs>
              <linearGradient id="ci90Gradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#6366f1" stopOpacity={0.1} />
                <stop offset="95%" stopColor="#6366f1" stopOpacity={0.02} />
              </linearGradient>
              <linearGradient id="ci80Gradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#8b5cf6" stopOpacity={0.2} />
                <stop offset="95%" stopColor="#8b5cf6" stopOpacity={0.05} />
              </linearGradient>
            </defs>
            
            <CartesianGrid strokeDasharray="3 3" stroke="#334155" vertical={false} />
            <XAxis
              dataKey="date"
              tick={{ fill: "#94a3b8", fontSize: 11 }}
              tickLine={{ stroke: "#475569" }}
              axisLine={{ stroke: "#475569" }}
              tickFormatter={(value) => {
                const date = new Date(value);
                return `${date.getMonth() + 1}/${date.getDate()}`;
              }}
            />
            <YAxis
              tick={{ fill: "#94a3b8", fontSize: 11 }}
              tickLine={{ stroke: "#475569" }}
              axisLine={{ stroke: "#475569" }}
              domain={["auto", "auto"]}
              tickFormatter={(value) => `$${value.toFixed(0)}`}
            />
            <Tooltip content={<CustomTooltip />} />

            {/* 90% Confidence Interval Area */}
            <Area
              type="monotone"
              dataKey="ci_90_upper"
              fill="url(#ci90Gradient)"
              stroke="none"
            />
            <Area
              type="monotone"
              dataKey="ci_90_lower"
              fill="url(#ci90Gradient)"
              stroke="none"
            />

            {/* 80% Confidence Interval Area */}
            <Area
              type="monotone"
              dataKey="ci_80_upper"
              fill="url(#ci80Gradient)"
              stroke="none"
            />
            <Area
              type="monotone"
              dataKey="ci_80_lower"
              fill="url(#ci80Gradient)"
              stroke="none"
            />

            {/* Historical Price Line */}
            <Line
              type="monotone"
              dataKey="price"
              stroke="#3b82f6"
              strokeWidth={2}
              dot={false}
              connectNulls={false}
            />

            {/* Prediction Line */}
            <Line
              type="monotone"
              dataKey="predicted"
              stroke={predColor}
              strokeWidth={2}
              strokeDasharray="8 4"
              dot={{ r: 4, fill: predColor, strokeWidth: 0 }}
              connectNulls={false}
            />

            {/* Current Price Reference Line */}
            {prediction && (
              <ReferenceLine
                y={prediction.current_price}
                stroke="#64748b"
                strokeDasharray="4 4"
                strokeWidth={1}
              />
            )}
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      {/* Stats Grid */}
      {prediction && (
        <div className="px-6 py-4 bg-slate-800/50 border-t border-slate-800">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="bg-slate-800 rounded-lg p-3">
              <div className="text-xs text-slate-400 uppercase tracking-wide">Current</div>
              <div className="text-lg font-semibold text-white mt-1">
                ${prediction.current_price.toFixed(2)}
              </div>
            </div>
            <div className="bg-slate-800 rounded-lg p-3">
              <div className="text-xs text-slate-400 uppercase tracking-wide">30-Day Target</div>
              <div className="text-lg font-semibold mt-1" style={{ color: predColor }}>
                ${prediction.predicted_price.toFixed(2)}
              </div>
            </div>
            <div className="bg-slate-800 rounded-lg p-3">
              <div className="text-xs text-slate-400 uppercase tracking-wide">Expected</div>
              <div className="text-lg font-semibold mt-1" style={{ color: predColor }}>
                {priceChange >= 0 ? "+" : ""}{priceChange.toFixed(2)}%
              </div>
            </div>
            <div className="bg-slate-800 rounded-lg p-3">
              <div className="text-xs text-slate-400 uppercase tracking-wide">80% Range</div>
              <div className="text-sm font-medium text-slate-300 mt-1">
                ${prediction.ci_80_lower.toFixed(0)} - ${prediction.ci_80_upper.toFixed(0)}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Gomes Analyst Context */}
      {prediction?.analyst_context && (
        <div className="px-6 py-4 border-t border-slate-800">
          <div className="flex items-center gap-2 mb-4">
            <svg className="w-5 h-5 text-purple-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
            </svg>
            <h3 className="text-sm font-semibold text-white">
              {prediction.analyst_context.analyst || "Mark Gomes"} Analysis
            </h3>
            {prediction.analyst_context.video_date && (
              <span className="text-xs text-slate-500 ml-auto">
                {new Date(prediction.analyst_context.video_date).toLocaleDateString()}
              </span>
            )}
          </div>

          {/* Sentiment & Verdict badges */}
          <div className="flex flex-wrap gap-2 mb-4">
            {prediction.analyst_context.sentiment && (
              <span className={`px-3 py-1 rounded-full text-xs font-medium border ${
                prediction.analyst_context.sentiment === "Bullish" 
                  ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
                  : prediction.analyst_context.sentiment === "Bearish"
                  ? "bg-rose-500/10 text-rose-400 border-rose-500/20"
                  : "bg-slate-500/10 text-slate-400 border-slate-500/20"
              }`}>
                {prediction.analyst_context.sentiment}
              </span>
            )}
            {prediction.analyst_context.action_verdict && (
              <span className={`px-3 py-1 rounded-full text-xs font-medium border ${
                prediction.analyst_context.action_verdict === "BUY_NOW" 
                  ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
                  : prediction.analyst_context.action_verdict === "ACCUMULATE"
                  ? "bg-blue-500/10 text-blue-400 border-blue-500/20"
                  : prediction.analyst_context.action_verdict === "SELL" || prediction.analyst_context.action_verdict === "AVOID"
                  ? "bg-rose-500/10 text-rose-400 border-rose-500/20"
                  : "bg-amber-500/10 text-amber-400 border-amber-500/20"
              }`}>
                {prediction.analyst_context.action_verdict.replace("_", " ")}
              </span>
            )}
            {prediction.analyst_context.gomes_score && (
              <span className="px-3 py-1 rounded-full text-xs font-medium border bg-purple-500/10 text-purple-400 border-purple-500/20">
                Score: {prediction.analyst_context.gomes_score}/10
              </span>
            )}
            {prediction.analyst_context.time_horizon && (
              <span className="px-3 py-1 rounded-full text-xs font-medium border bg-slate-500/10 text-slate-400 border-slate-500/20">
                {prediction.analyst_context.time_horizon}
              </span>
            )}
          </div>

          {/* Price Targets from Gomes */}
          {(prediction.analyst_context.price_target_short || prediction.analyst_context.price_target_long) && (
            <div className="grid grid-cols-2 gap-3 mb-4">
              {prediction.analyst_context.price_target_short && (
                <div className="bg-slate-800/50 rounded-lg p-3">
                  <div className="text-xs text-slate-400">Short-Term Target</div>
                  <div className="text-sm font-semibold text-blue-400 mt-1">
                    {prediction.analyst_context.price_target_short}
                  </div>
                </div>
              )}
              {prediction.analyst_context.price_target_long && (
                <div className="bg-slate-800/50 rounded-lg p-3">
                  <div className="text-xs text-slate-400">Long-Term Target</div>
                  <div className="text-sm font-semibold text-purple-400 mt-1">
                    {prediction.analyst_context.price_target_long}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Edge, Catalysts, Risks */}
          <div className="space-y-3">
            {prediction.analyst_context.edge && (
              <div className="bg-emerald-500/5 border border-emerald-500/10 rounded-lg p-3">
                <div className="flex items-center gap-2 mb-1">
                  <svg className="w-4 h-4 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                  </svg>
                  <span className="text-xs font-semibold text-emerald-400 uppercase">Edge</span>
                </div>
                <p className="text-sm text-slate-300 leading-relaxed">{prediction.analyst_context.edge}</p>
              </div>
            )}
            {prediction.analyst_context.catalysts && (
              <div className="bg-blue-500/5 border border-blue-500/10 rounded-lg p-3">
                <div className="flex items-center gap-2 mb-1">
                  <svg className="w-4 h-4 text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
                  </svg>
                  <span className="text-xs font-semibold text-blue-400 uppercase">Catalysts</span>
                </div>
                <p className="text-sm text-slate-300 leading-relaxed">{prediction.analyst_context.catalysts}</p>
              </div>
            )}
            {prediction.analyst_context.risks && (
              <div className="bg-rose-500/5 border border-rose-500/10 rounded-lg p-3">
                <div className="flex items-center gap-2 mb-1">
                  <svg className="w-4 h-4 text-rose-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                  </svg>
                  <span className="text-xs font-semibold text-rose-400 uppercase">Risks</span>
                </div>
                <p className="text-sm text-slate-300 leading-relaxed">{prediction.analyst_context.risks}</p>
              </div>
            )}
          </div>

          {/* Entry Zone */}
          {prediction.analyst_context.entry_zone && (
            <div className="mt-4 bg-slate-800/50 rounded-lg p-3">
              <div className="text-xs text-slate-400">Entry Zone</div>
              <div className="text-sm font-medium text-amber-400 mt-1">
                {prediction.analyst_context.entry_zone}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Error display */}
      {error && (
        <div className="px-6 py-3 bg-rose-500/10 border-t border-rose-500/20">
          <p className="text-rose-400 text-sm">{error}</p>
        </div>
      )}
    </div>
  );
};

export default MLPredictionChart;
