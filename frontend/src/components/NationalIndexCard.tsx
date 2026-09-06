import React from 'react';
import { IndexLatestResponse } from '../types';
import { TrendingUp, TrendingDown, Minus, Calendar, Clock, RefreshCw, AlertCircle } from 'lucide-react';

interface Props {
  data: IndexLatestResponse | null;
  loading: boolean;
  error: string | null;
  onRefresh: () => void;
  onTriggerPrompt?: () => void;
}

export const NationalIndexCard: React.FC<Props> = ({
  data,
  loading,
  error,
  onRefresh,
  onTriggerPrompt,
}) => {
  return (
    <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm relative">
      <div className="flex items-center justify-between pb-4 border-b border-slate-100">
        <div>
          <div className="flex items-center space-x-2">
            <h2 className="text-base font-semibold text-slate-800">National Composite Index (APIx)</h2>
            <span className="px-2 py-0.5 text-xs font-semibold bg-sky-100 text-sky-800 rounded-full">
              Live
            </span>
          </div>
          <p className="text-xs text-slate-500 mt-0.5">
            DGCA Passenger-Weighted National Composite Metric &bull; Baseline = 100.0
          </p>
        </div>
        <button
          onClick={onRefresh}
          disabled={loading}
          title="Refresh latest index"
          className="inline-flex items-center px-3 py-1.5 text-xs font-medium text-slate-700 bg-slate-100 hover:bg-slate-200 rounded-lg transition-colors disabled:opacity-50"
        >
          <RefreshCw className={`w-3.5 h-3.5 mr-1.5 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      <div className="mt-5">
        {loading && !data ? (
          <div className="py-12 flex flex-col items-center justify-center text-slate-400">
            <RefreshCw className="w-8 h-8 animate-spin text-sky-500 mb-2" />
            <span className="text-sm font-medium">Fetching latest index calculation...</span>
          </div>
        ) : error ? (
          <div className="bg-amber-50 border border-amber-200 rounded-xl p-5 text-amber-800">
            <div className="flex items-start">
              <AlertCircle className="w-5 h-5 text-amber-600 mr-3 flex-shrink-0 mt-0.5" />
              <div className="flex-1">
                <h3 className="text-sm font-semibold text-amber-900">No Computed Index Records</h3>
                <p className="text-xs text-amber-700 mt-1">{error}</p>
                {onTriggerPrompt && (
                  <button
                    onClick={onTriggerPrompt}
                    className="mt-3 inline-flex items-center px-3 py-1.5 text-xs font-medium text-white bg-sky-600 hover:bg-sky-700 rounded-lg shadow-sm transition-colors"
                  >
                    Run Data Pipeline Now
                  </button>
                )}
              </div>
            </div>
          </div>
        ) : data ? (
          <div className="space-y-6">
            {/* Top Score Display */}
            <div className="flex flex-col sm:flex-row sm:items-baseline sm:justify-between gap-4 bg-slate-50 border border-slate-200/80 rounded-xl p-5">
              <div>
                <div className="text-xs text-slate-500 font-medium uppercase tracking-wider">
                  Composite Index Score
                </div>
                <div className="flex items-baseline space-x-3 mt-1">
                  <span className="text-4xl font-extrabold text-slate-900 tracking-tight">
                    {data.index_value.toFixed(2)}
                  </span>
                  <span className="text-xs text-slate-500 font-medium">
                    (Base: 100.0 in {data.baseline_period})
                  </span>
                </div>
              </div>

              {/* Day-over-Day Badge */}
              <div className="flex items-center">
                {data.dod_change_pct !== null && data.dod_change_pct !== undefined ? (
                  <div
                    className={`inline-flex items-center px-3 py-1.5 rounded-lg text-xs font-semibold ${
                      data.dod_change_pct > 0
                        ? 'bg-rose-100 text-rose-800'
                        : data.dod_change_pct < 0
                        ? 'bg-emerald-100 text-emerald-800'
                        : 'bg-slate-200 text-slate-700'
                    }`}
                  >
                    {data.dod_change_pct > 0 ? (
                      <TrendingUp className="w-3.5 h-3.5 mr-1 text-rose-600" />
                    ) : data.dod_change_pct < 0 ? (
                      <TrendingDown className="w-3.5 h-3.5 mr-1 text-emerald-600" />
                    ) : (
                      <Minus className="w-3.5 h-3.5 mr-1 text-slate-600" />
                    )}
                    {data.dod_change_pct > 0 ? `+${data.dod_change_pct}%` : `${data.dod_change_pct}%`} DoD
                  </div>
                ) : (
                  <span className="inline-flex items-center px-2.5 py-1 rounded-md text-xs text-slate-500 bg-slate-100">
                    Baseline Point
                  </span>
                )}
              </div>
            </div>

            {/* Metrics Breakdown Grid */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <div className="bg-white border border-slate-200 rounded-lg p-3">
                <div className="text-xs text-slate-500">Evaluation Date</div>
                <div className="text-sm font-semibold text-slate-800 flex items-center mt-1">
                  <Calendar className="w-3.5 h-3.5 text-sky-600 mr-1.5 flex-shrink-0" />
                  {data.date}
                </div>
              </div>

              <div className="bg-white border border-slate-200 rounded-lg p-3">
                <div className="text-xs text-slate-500">Baseline Period</div>
                <div className="text-sm font-semibold text-slate-800 mt-1">
                  {data.baseline_period}
                </div>
              </div>

              <div className="bg-white border border-slate-200 rounded-lg p-3">
                <div className="text-xs text-slate-500">7-Day Moving Avg</div>
                <div className="text-sm font-semibold text-sky-700 mt-1">
                  {data.ma_7d !== null ? data.ma_7d.toFixed(2) : 'N/A'}
                </div>
              </div>

              <div className="bg-white border border-slate-200 rounded-lg p-3">
                <div className="text-xs text-slate-500">30-Day Moving Avg</div>
                <div className="text-sm font-semibold text-indigo-700 mt-1">
                  {data.ma_30d !== null ? data.ma_30d.toFixed(2) : 'N/A'}
                </div>
              </div>
            </div>

            <div className="flex items-center text-[11px] text-slate-400">
              <Clock className="w-3 h-3 mr-1" />
              Calculated at: {new Date(data.calculated_at).toLocaleString()}
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
};
