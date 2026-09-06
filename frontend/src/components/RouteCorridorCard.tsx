import React, { useState } from 'react';
import { RouteItem, RouteCorridorIndexResponse, RouteWindowBreakdown } from '../types';
import {
  Plane,
  RefreshCw,
  AlertCircle,
  Calendar,
  Scale,
  Navigation,
  Layers,
  TrendingUp,
  TrendingDown,
  Minus,
  Info,
} from 'lucide-react';

interface Props {
  routes: RouteItem[];
  selectedRouteCode: string;
  routeData: RouteCorridorIndexResponse | null;
  loading: boolean;
  routesLoading: boolean;
  error: string | null;
  onSelectRoute: (code: string) => void;
  onRefresh: () => void;
  onTriggerPrompt?: () => void;
}

const formatWeight = (weight: number | null | undefined): string => (
  weight === null || weight === undefined ? 'Not available' : `${(weight * 100).toFixed(1)}%`
);

const EMPTY_VALUE = '—';

const isNumber = (value: number | null | undefined): value is number => (
  value !== null && value !== undefined && Number.isFinite(value)
);

const formatNumber = (value: number | null | undefined, digits = 2): string => (
  isNumber(value) ? value.toFixed(digits) : EMPTY_VALUE
);

const formatFare = (value: number | null | undefined): string => (
  isNumber(value) ? `INR ${Math.round(value).toLocaleString('en-IN')}` : EMPTY_VALUE
);

const isIndexDisplayable = (
  window: RouteWindowBreakdown
): window is RouteWindowBreakdown & { mean_fare: number; baseline_fare: number; sub_index: number } => (
  isNumber(window.mean_fare) && isNumber(window.baseline_fare) && isNumber(window.sub_index)
);

export const RouteCorridorCard: React.FC<Props> = ({
  routes,
  selectedRouteCode,
  routeData,
  loading,
  routesLoading,
  error,
  onSelectRoute,
  onRefresh,
  onTriggerPrompt,
}) => {
  const [viewMode, setViewMode] = useState<'cards' | 'table'>('cards');
  const observedWindowCount = routeData?.windows.filter((win) => win.quotes_count > 0).length || 0;

  return (
    <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm">
      {/* Header & Route Selector */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 pb-4 border-b border-slate-100">
        <div>
          <div className="flex items-center space-x-2">
            <h2 className="text-base font-semibold text-slate-800">Route Corridor & Window Pricing</h2>
            <span className="px-2 py-0.5 text-xs font-semibold bg-indigo-100 text-indigo-800 rounded-full">
              DGCA Corridors
            </span>
          </div>
          <p className="text-xs text-slate-500 mt-0.5">
            Advance booking pricing curves: T+1, T+7, T+15, T+30, T+45
          </p>
        </div>

        {/* Route Dropdown & Actions */}
        <div className="flex items-center space-x-2">
          <div className="relative">
            <select
              value={selectedRouteCode}
              onChange={(e) => onSelectRoute(e.target.value)}
              disabled={routesLoading || routes.length === 0}
              className="appearance-none bg-slate-50 border border-slate-300 text-slate-800 text-xs rounded-lg pl-3 pr-8 py-2 font-medium focus:ring-2 focus:ring-sky-500 focus:border-sky-500 disabled:opacity-50"
            >
              {routesLoading ? (
                <option>Loading routes...</option>
              ) : routes.length === 0 ? (
                <option>No routes available</option>
              ) : (
                routes.map((r) => (
                  <option key={r.id} value={r.route_code || r.route_key}>
                    {r.route_code} ({r.origin} &rarr; {r.destination}) &bull; {formatWeight(r.dgca_weight)} wt
                  </option>
                ))
              )}
            </select>
            <div className="pointer-events-none absolute inset-y-0 right-0 flex items-center px-2 text-slate-500">
              <Plane className="w-3.5 h-3.5 transform rotate-90" />
            </div>
          </div>

          <div className="inline-flex rounded-lg border border-slate-200 p-0.5 bg-slate-50 text-xs">
            <button
              onClick={() => setViewMode('cards')}
              className={`px-2.5 py-1 rounded-md font-medium transition-colors ${
                viewMode === 'cards' ? 'bg-white shadow-sm text-slate-800' : 'text-slate-500 hover:text-slate-700'
              }`}
            >
              Cards
            </button>
            <button
              onClick={() => setViewMode('table')}
              className={`px-2.5 py-1 rounded-md font-medium transition-colors ${
                viewMode === 'table' ? 'bg-white shadow-sm text-slate-800' : 'text-slate-500 hover:text-slate-700'
              }`}
            >
              Table
            </button>
          </div>

          <button
            onClick={onRefresh}
            disabled={loading}
            title="Refresh route data"
            className="p-2 text-slate-700 bg-slate-100 hover:bg-slate-200 rounded-lg transition-colors disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      <div className="mt-5">
        {loading && !routeData ? (
          <div className="py-12 flex flex-col items-center justify-center text-slate-400">
            <RefreshCw className="w-8 h-8 animate-spin text-sky-500 mb-2" />
            <span className="text-sm font-medium">Fetching route index and advance windows...</span>
          </div>
        ) : error ? (
          <div className="bg-amber-50 border border-amber-200 rounded-xl p-5 text-amber-800">
            <div className="flex items-start">
              <AlertCircle className="w-5 h-5 text-amber-600 mr-3 flex-shrink-0 mt-0.5" />
              <div className="flex-1">
                <h3 className="text-sm font-semibold text-amber-900">No Data for {selectedRouteCode}</h3>
                <p className="text-xs text-amber-700 mt-1">{error}</p>
                {onTriggerPrompt && (
                  <button
                    onClick={onTriggerPrompt}
                    className="mt-3 inline-flex items-center px-3 py-1.5 text-xs font-medium text-white bg-sky-600 hover:bg-sky-700 rounded-lg shadow-sm transition-colors"
                  >
                    Run Ingestion Pipeline to Generate Data
                  </button>
                )}
              </div>
            </div>
          </div>
        ) : routeData ? (
          <div className="space-y-6">
            {/* Route Overview Header */}
            <div className="bg-slate-50 border border-slate-200/80 rounded-xl p-5">
              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
                <div>
                  <div className="flex items-center space-x-3">
                    <span className="text-2xl font-bold text-slate-900">
                      {routeData.origin} &rarr; {routeData.destination}
                    </span>
                    <span className="px-2.5 py-0.5 text-xs font-mono font-semibold bg-sky-100 text-sky-800 rounded-md">
                      {routeData.route_code}
                    </span>
                  </div>
                  <div className="flex flex-wrap items-center gap-4 mt-2 text-xs text-slate-600">
                    <span className="flex items-center">
                      <Navigation className="w-3.5 h-3.5 mr-1 text-slate-400" />
                      Distance: <strong className="ml-1 text-slate-800">{routeData.distance ? `${routeData.distance.toLocaleString()} km` : 'N/A'}</strong>
                    </span>
                    <span className="flex items-center">
                      <Scale className="w-3.5 h-3.5 mr-1 text-slate-400" />
                      DGCA Weight: <strong className="ml-1 text-slate-800">{formatWeight(routeData.dgca_weight)}</strong>
                    </span>
                    <span className="flex items-center">
                      <Calendar className="w-3.5 h-3.5 mr-1 text-slate-400" />
                      Date: <strong className="ml-1 text-slate-800">{routeData.target_date}</strong>
                    </span>
                  </div>
                </div>

                {/* Sub-Index Badge */}
                <div className="bg-white border border-slate-200 rounded-xl p-3 sm:text-right shadow-sm">
                  <div className="text-[11px] text-slate-500 font-medium uppercase tracking-wider">
                    LIVE Route Sub-Index
                  </div>
                  <div className="flex items-baseline sm:justify-end space-x-2 mt-0.5">
                    <span className="text-2xl font-extrabold text-slate-900">
                      {formatNumber(routeData.route_index)}
                    </span>
                    {isNumber(routeData.route_index) && <span className="text-xs text-slate-500">pts</span>}
                  </div>
                  <div className="mt-1 text-[11px] text-slate-500">
                    Based on {observedWindowCount}/{routeData.windows.length} advance windows
                  </div>
                </div>
              </div>
            </div>

            {/* Advance Booking Window Breakdown */}
            <div>
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-xs font-semibold text-slate-700 uppercase tracking-wider flex items-center">
                  <Layers className="w-3.5 h-3.5 mr-1 text-sky-600" />
                  Advance Booking Curve (T+1 to T+45)
                </h3>
                <span className="text-[11px] text-slate-400 flex items-center">
                  <Info className="w-3 h-3 mr-1" />
                  Normalized against route reference baselines
                </span>
              </div>

              {viewMode === 'cards' ? (
                <div className="grid grid-cols-1 sm:grid-cols-5 gap-3">
                  {routeData.windows.map((win) => {
                    const hasFareData = win.quotes_count > 0 && isNumber(win.mean_fare);
                    const hasIndexData = win.quotes_count > 0 && isIndexDisplayable(win);
                    const diffPct = hasIndexData && win.baseline_fare > 0
                      ? ((win.mean_fare - win.baseline_fare) / win.baseline_fare) * 100
                      : null;
                    return (
                      <div
                        key={win.advance_window_days}
                        className="bg-white border border-slate-200 rounded-xl p-3.5 flex flex-col justify-between hover:border-sky-300 transition-colors shadow-sm"
                      >
                        <div className="flex items-center justify-between">
                          <span className="px-2 py-0.5 text-xs font-bold bg-slate-900 text-white rounded-md">
                            {win.window_label || `T+${win.advance_window_days}`}
                          </span>
                          <span className="text-[11px] text-slate-500 font-medium">
                            {win.advance_window_days}d out
                          </span>
                        </div>

                        <div className="my-3">
                          <div className="text-[11px] text-slate-400 uppercase tracking-wider">Sub-Index</div>
                          <div className="text-xl font-bold text-slate-900 mt-0.5">
                            {hasIndexData ? formatNumber(win.sub_index, 1) : EMPTY_VALUE}
                          </div>
                          <div className="flex items-center text-[11px] mt-0.5">
                            {!hasIndexData ? (
                              <span className="text-slate-500 font-medium">{hasFareData ? 'Reference unavailable' : 'No live data'}</span>
                            ) : diffPct !== null && diffPct > 0 ? (
                              <span className="text-rose-600 flex items-center font-medium">
                                <TrendingUp className="w-3 h-3 mr-0.5" /> +{diffPct.toFixed(1)}%
                              </span>
                            ) : diffPct !== null && diffPct < 0 ? (
                              <span className="text-emerald-600 flex items-center font-medium">
                                <TrendingDown className="w-3 h-3 mr-0.5" /> {diffPct.toFixed(1)}%
                              </span>
                            ) : (
                              <span className="text-slate-500 flex items-center">
                                <Minus className="w-3 h-3 mr-0.5" /> 0%
                              </span>
                            )}
                            <span className="text-slate-400 ml-1">vs base</span>
                          </div>
                        </div>

                        <div className="pt-2.5 border-t border-slate-100 text-[11px] space-y-1">
                          <div className="flex justify-between text-slate-600">
                            <span>Mean Fare:</span>
                            <strong className="text-slate-800">{hasFareData ? formatFare(win.mean_fare) : EMPTY_VALUE}</strong>
                          </div>
                          <div className="flex justify-between text-slate-400">
                            <span>Baseline:</span>
                            <span>{hasIndexData ? formatFare(win.baseline_fare) : EMPTY_VALUE}</span>
                          </div>
                          <div className="flex justify-between text-slate-400 pt-0.5">
                            <span>Samples:</span>
                            <span>{win.quotes_count} quotes</span>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div className="overflow-x-auto border border-slate-200 rounded-xl">
                  <table className="w-full text-xs text-left">
                    <thead className="bg-slate-50 text-slate-600 border-b border-slate-200">
                      <tr>
                        <th className="py-2.5 px-4 font-semibold">Advance Window</th>
                        <th className="py-2.5 px-4 font-semibold">Days Before Travel</th>
                        <th className="py-2.5 px-4 font-semibold">Observed Mean Fare</th>
                        <th className="py-2.5 px-4 font-semibold">Baseline Reference Fare</th>
                        <th className="py-2.5 px-4 font-semibold">Sub-Index</th>
                        <th className="py-2.5 px-4 font-semibold">Usable Quotes</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {routeData.windows.map((win) => {
                        const hasFareData = win.quotes_count > 0 && isNumber(win.mean_fare);
                        const hasIndexData = win.quotes_count > 0 && isIndexDisplayable(win);
                        return (
                          <tr key={win.advance_window_days} className="hover:bg-slate-50/80">
                            <td className="py-2.5 px-4 font-bold text-slate-900">
                              <span className="px-2 py-0.5 bg-slate-100 text-slate-800 rounded font-mono">
                                {win.window_label || `T+${win.advance_window_days}`}
                              </span>
                            </td>
                            <td className="py-2.5 px-4 text-slate-600">{win.advance_window_days} days</td>
                            <td className="py-2.5 px-4 font-semibold text-slate-900">{hasFareData ? formatFare(win.mean_fare) : EMPTY_VALUE}</td>
                            <td className="py-2.5 px-4 text-slate-500">{hasIndexData ? formatFare(win.baseline_fare) : EMPTY_VALUE}</td>
                            <td className="py-2.5 px-4">
                              <span className={`font-bold ${hasIndexData ? (win.sub_index >= 100 ? 'text-rose-600' : 'text-emerald-600') : 'text-slate-400'}`}>
                                {hasIndexData ? formatNumber(win.sub_index) : EMPTY_VALUE}
                              </span>
                            </td>
                            <td className="py-2.5 px-4 text-slate-600">{win.quotes_count} quotes</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
};
