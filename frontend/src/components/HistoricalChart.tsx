import React from 'react';
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ReferenceLine,
} from 'recharts';
import { IndexHistoricalResponse } from '../types';
import { RefreshCw, BarChart3, AlertCircle } from 'lucide-react';

interface Props {
  data: IndexHistoricalResponse | null;
  loading: boolean;
  error: string | null;
  onRefresh: () => void;
}

export const HistoricalChart: React.FC<Props> = ({
  data,
  loading,
  error,
  onRefresh,
}) => {
  const chartData = (data?.items || []).map((item) => ({
    date: item.date,
    index_value: Number(item.index_value.toFixed(2)),
    ma_7d: item.ma_7d !== null ? Number(item.ma_7d.toFixed(2)) : undefined,
    ma_30d: item.ma_30d !== null ? Number(item.ma_30d.toFixed(2)) : undefined,
  }));

  // Determine dynamic domain bounds centered around 100
  const values = chartData.map((d) => d.index_value);
  const minVal = values.length ? Math.min(...values, 95) : 90;
  const maxVal = values.length ? Math.max(...values, 105) : 110;
  const yDomain = [Math.floor(minVal - 5), Math.ceil(maxVal + 5)];

  return (
    <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm">
      <div className="flex items-center justify-between pb-4 border-b border-slate-100">
        <div>
          <div className="flex items-center space-x-2">
            <h2 className="text-base font-semibold text-slate-800">Historical Index Trend</h2>
            <span className="px-2 py-0.5 text-xs font-semibold bg-slate-100 text-slate-700 rounded-full">
              Daily
            </span>
          </div>
          <p className="text-xs text-slate-500 mt-0.5">
            Chronological APIx time-series with 7-day rolling moving average
          </p>
        </div>
        <button
          onClick={onRefresh}
          disabled={loading}
          title="Refresh historical data"
          className="inline-flex items-center px-3 py-1.5 text-xs font-medium text-slate-700 bg-slate-100 hover:bg-slate-200 rounded-lg transition-colors disabled:opacity-50"
        >
          <RefreshCw className={`w-3.5 h-3.5 mr-1.5 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      <div className="mt-5">
        {loading && !data ? (
          <div className="h-64 flex flex-col items-center justify-center text-slate-400">
            <RefreshCw className="w-8 h-8 animate-spin text-sky-500 mb-2" />
            <span className="text-sm font-medium">Loading historical time-series...</span>
          </div>
        ) : error ? (
          <div className="h-64 flex flex-col items-center justify-center p-6 text-center">
            <AlertCircle className="w-8 h-8 text-amber-500 mb-2" />
            <p className="text-sm text-slate-700 font-medium">Unable to load history</p>
            <p className="text-xs text-slate-500 mt-1 max-w-sm">{error}</p>
          </div>
        ) : chartData.length === 0 ? (
          <div className="h-64 flex flex-col items-center justify-center p-6 text-center text-slate-400">
            <BarChart3 className="w-10 h-10 text-slate-300 mb-2" />
            <p className="text-sm font-medium text-slate-700">No historical APIx data available yet.</p>
            <p className="text-xs text-slate-500 mt-1">
              Daily historical APIx will appear after sufficient LIVE coverage is collected.
            </p>
          </div>
        ) : (
          <div className="space-y-2">
            {chartData.length === 1 && (
              <div className="bg-sky-50 border border-sky-200 rounded-lg px-3 py-2 text-xs text-sky-800">
                Single observation available ({chartData[0].date}: {chartData[0].index_value}). Additional daily APIx observations are required to view trend trajectories.
              </div>
            )}
            <div className="h-72 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chartData} margin={{ top: 10, right: 20, left: 0, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                  <XAxis
                    dataKey="date"
                    tick={{ fontSize: 11, fill: '#64748b' }}
                    stroke="#cbd5e1"
                  />
                  <YAxis
                    domain={yDomain}
                    tick={{ fontSize: 11, fill: '#64748b' }}
                    stroke="#cbd5e1"
                    unit=""
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: '#ffffff',
                      borderRadius: '0.5rem',
                      boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)',
                      border: '1px solid #e2e8f0',
                      fontSize: '12px',
                    }}
                    formatter={(val: number) => [`${val.toFixed(2)}`, '']}
                    labelFormatter={(label) => `Date: ${label}`}
                  />
                  <Legend wrapperStyle={{ fontSize: '12px', paddingTop: '8px' }} />
                  <ReferenceLine
                    y={100}
                    stroke="#94a3b8"
                    strokeDasharray="4 4"
                    label={{ value: '100 Baseline', position: 'insideTopLeft', fill: '#94a3b8', fontSize: 10 }}
                  />
                  <Line
                    type="monotone"
                    dataKey="index_value"
                    name="APIx Composite Index"
                    stroke="#0284c7"
                    strokeWidth={2.5}
                    dot={{ r: 4, fill: '#0284c7', strokeWidth: 1.5, stroke: '#ffffff' }}
                    activeDot={{ r: 6 }}
                  />
                  <Line
                    type="monotone"
                    dataKey="ma_7d"
                    name="7-Day Moving Avg"
                    stroke="#8b5cf6"
                    strokeWidth={1.5}
                    strokeDasharray="4 2"
                    dot={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
