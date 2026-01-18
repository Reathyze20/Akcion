/**
 * ML Prediction Chart Component
 *
 * Interactive chart showing historical prices and ML predictions.
 * Displays prediction confidence intervals and target prices.
 */

import React, { useEffect, useState } from "react";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, ReferenceLine, Area, ComposedChart } from "recharts";

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
}

interface PriceData {
  date: string;
  price: number;
}

interface MLPredictionChartProps {
  ticker: string;
  historicalDays?: number;
}

const MLPredictionChart: React.FC<MLPredictionChartProps> = ({ ticker, historicalDays = 60 }) => {
  const [prediction, setPrediction] = useState<MLPrediction | null>(null);
  const [priceData, setPriceData] = useState<PriceData[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchData();
  }, [ticker, historicalDays]);

  const fetchData = async () => {
    try {
      setLoading(true);

      // Fetch ML prediction
      const predResponse = await fetch(`/api/trading/predictions/${ticker}`);
      if (predResponse.ok) {
        const predData = await predResponse.json();
        setPrediction(predData);
      }

      // Fetch historical prices (mock data for now)
      // TODO: Implement actual OHLCV endpoint
      const mockPrices: PriceData[] = [];
      const today = new Date();
      const currentPrice = prediction?.current_price || 100;

      for (let i = historicalDays; i >= 0; i--) {
        const date = new Date(today);
        date.setDate(date.getDate() - i);
        const randomWalk = (Math.random() - 0.5) * 2;
        const price = currentPrice * (1 + ((randomWalk / 100) * (historicalDays - i)) / historicalDays);

        mockPrices.push({
          date: date.toISOString().split("T")[0],
          price: parseFloat(price.toFixed(2)),
        });
      }

      setPriceData(mockPrices);
      setError(null);
    } catch (err: any) {
      setError(err.message);
      console.error("Failed to fetch chart data:", err);
    } finally {
      setLoading(false);
    }
  };

  const getChartData = () => {
    if (!prediction || priceData.length === 0) return [];

    const data = [...priceData];

    // Add prediction point
    const predictionDate = new Date(prediction.valid_until);
    data.push({
      date: predictionDate.toISOString().split("T")[0],
      price: prediction.predicted_price,
      predicted: prediction.predicted_price,
      ci_80_lower: prediction.ci_80_lower,
      ci_80_upper: prediction.ci_80_upper,
      ci_90_lower: prediction.ci_90_lower,
      ci_90_upper: prediction.ci_90_upper,
    } as any);

    return data;
  };

  const getPredictionColor = (type: string): string => {
    if (type === "UP") return "#10b981"; // green
    if (type === "DOWN") return "#ef4444"; // red
    return "#6b7280"; // gray
  };

  if (loading) {
    return (
      <div className="bg-white rounded-lg shadow p-6">
        <div className="animate-pulse">
          <div className="h-6 bg-gray-200 rounded w-1/3 mb-4"></div>
          <div className="h-64 bg-gray-200 rounded"></div>
        </div>
      </div>
    );
  }

  if (error || !prediction) {
    return (
      <div className="bg-white rounded-lg shadow p-6">
        <div className="text-center text-gray-500">
          <p>No prediction data available for {ticker}</p>
          {error && <p className="text-sm text-red-600 mt-2">{error}</p>}
        </div>
      </div>
    );
  }

  const chartData = getChartData();
  const predColor = getPredictionColor(prediction.prediction_type);

  return (
    <div className="bg-white rounded-lg shadow">
      {/* Header */}
      <div className="px-6 py-4 border-b border-gray-200">
        <div className="flex justify-between items-start">
          <div>
            <h2 className="text-xl font-bold text-gray-900">{ticker} - Price Prediction</h2>
            <p className="text-sm text-gray-500 mt-1">
              {historicalDays} days historical + {prediction.horizon_days} days forecast
            </p>
          </div>
          <div className="text-right">
            <div className={`text-lg font-bold`} style={{ color: predColor }}>
              {prediction.prediction_type}
            </div>
            <div className="text-sm text-gray-500">{(prediction.confidence * 100).toFixed(1)}% confidence</div>
          </div>
        </div>
      </div>

      {/* Chart */}
      <div className="px-6 py-4">
        <ResponsiveContainer width="100%" height={400}>
          <ComposedChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis
              dataKey="date"
              tick={{ fontSize: 12 }}
              tickFormatter={(value) => {
                const date = new Date(value);
                return `${date.getMonth() + 1}/${date.getDate()}`;
              }}
            />
            <YAxis tick={{ fontSize: 12 }} domain={["auto", "auto"]} tickFormatter={(value) => `$${value.toFixed(0)}`} />
            <Tooltip formatter={(value: number) => `$${value.toFixed(2)}`} labelFormatter={(label) => `Date: ${label}`} />
            <Legend />

            {/* 90% Confidence Interval */}
            <Area type="monotone" dataKey="ci_90_upper" fill="#e0e7ff" stroke="none" fillOpacity={0.3} name="90% CI Upper" />
            <Area type="monotone" dataKey="ci_90_lower" fill="#e0e7ff" stroke="none" fillOpacity={0.3} name="90% CI Lower" />

            {/* 80% Confidence Interval */}
            <Area type="monotone" dataKey="ci_80_upper" fill="#c7d2fe" stroke="none" fillOpacity={0.4} name="80% CI Upper" />
            <Area type="monotone" dataKey="ci_80_lower" fill="#c7d2fe" stroke="none" fillOpacity={0.4} name="80% CI Lower" />

            {/* Historical Price */}
            <Line type="monotone" dataKey="price" stroke="#3b82f6" strokeWidth={2} dot={false} name="Historical Price" />

            {/* Prediction */}
            <Line type="monotone" dataKey="predicted" stroke={predColor} strokeWidth={3} strokeDasharray="5 5" dot={{ r: 6 }} name="Predicted Price" />

            {/* Current Price Line */}
            <ReferenceLine y={prediction.current_price} stroke="#6b7280" strokeDasharray="3 3" label={{ value: "Current", position: "right" }} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      {/* Stats */}
      <div className="px-6 py-4 bg-gray-50 border-t border-gray-200">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
          <div>
            <div className="text-gray-500">Current Price</div>
            <div className="font-semibold text-gray-900">${prediction.current_price.toFixed(2)}</div>
          </div>
          <div>
            <div className="text-gray-500">Predicted Price</div>
            <div className="font-semibold" style={{ color: predColor }}>
              ${prediction.predicted_price.toFixed(2)}
            </div>
          </div>
          <div>
            <div className="text-gray-500">Expected Change</div>
            <div className="font-semibold" style={{ color: predColor }}>
              {(((prediction.predicted_price - prediction.current_price) / prediction.current_price) * 100).toFixed(2)}%
            </div>
          </div>
          <div>
            <div className="text-gray-500">Quality</div>
            <div className={`font-semibold ${prediction.quality === "HIGH_CONFIDENCE" ? "text-green-600" : prediction.quality === "MEDIUM_CONFIDENCE" ? "text-yellow-600" : "text-red-600"}`}>
              {prediction.quality.replace("_", " ")}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default MLPredictionChart;
