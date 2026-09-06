import React, { useEffect, useState } from 'react';
import { checkHealth } from '../services/api';
import { HealthResponse } from '../types';
import { CheckCircle2, XCircle, RefreshCw, Server, Database, Layers } from 'lucide-react';

export const HealthStatus: React.FC = () => {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const fetchHealth = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await checkHealth();
      setHealth(data);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Backend connection failed';
      setError(msg);
      setHealth(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchHealth();
  }, []);

  return (
    <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm">
      <div className="flex items-center justify-between pb-4 border-b border-slate-100">
        <div>
          <h2 className="text-base font-semibold text-slate-800">System Health Monitor</h2>
          <p className="text-xs text-slate-500">Live check against FastAPI backend at <code className="text-sky-600 font-mono">/api/health</code></p>
        </div>
        <button
          onClick={fetchHealth}
          disabled={loading}
          className="inline-flex items-center px-3 py-1.5 text-xs font-medium text-slate-700 bg-slate-100 hover:bg-slate-200 rounded-lg transition-colors disabled:opacity-50"
        >
          <RefreshCw className={`w-3.5 h-3.5 mr-1.5 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      <div className="mt-4">
        {loading && !health && !error ? (
          <div className="flex items-center justify-center py-6 text-slate-400 text-sm">
            <RefreshCw className="w-5 h-5 animate-spin mr-2 text-sky-500" />
            Connecting to APIx backend...
          </div>
        ) : error ? (
          <div className="bg-rose-50 border border-rose-200 rounded-lg p-4 text-rose-800">
            <div className="flex items-start">
              <XCircle className="w-5 h-5 text-rose-500 mr-3 flex-shrink-0 mt-0.5" />
              <div>
                <h3 className="text-sm font-semibold text-rose-900">Backend Offline or Unreachable</h3>
                <p className="text-xs text-rose-700 mt-1">{error}</p>
                <p className="text-xs text-rose-600 mt-2">
                  Ensure the FastAPI backend is running on <code className="font-mono bg-rose-100 px-1 py-0.5 rounded">http://127.0.0.1:8000</code>.
                </p>
              </div>
            </div>
          </div>
        ) : health ? (
          <div className="space-y-4">
            <div className="flex items-center justify-between bg-emerald-50 border border-emerald-200 rounded-lg p-3.5">
              <div className="flex items-center space-x-3">
                <CheckCircle2 className="w-5 h-5 text-emerald-600" />
                <div>
                  <div className="text-sm font-medium text-emerald-900">Backend API Online</div>
                  <div className="text-xs text-emerald-700">Status: <span className="font-semibold uppercase">{health.status}</span></div>
                </div>
              </div>
              <span className="px-2.5 py-1 text-xs font-semibold bg-emerald-100 text-emerald-800 rounded-md">
                v{health.version}
              </span>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <div className="bg-slate-50 border border-slate-200/80 rounded-lg p-3">
                <div className="flex items-center text-slate-500 text-xs mb-1">
                  <Server className="w-3.5 h-3.5 mr-1 text-sky-600" />
                  Service
                </div>
                <div className="text-xs font-semibold text-slate-800 truncate">{health.app}</div>
              </div>

              <div className="bg-slate-50 border border-slate-200/80 rounded-lg p-3">
                <div className="flex items-center text-slate-500 text-xs mb-1">
                  <Layers className="w-3.5 h-3.5 mr-1 text-sky-600" />
                  Environment
                </div>
                <div className="text-xs font-semibold text-slate-800 uppercase tracking-wider">{health.environment}</div>
              </div>

              <div className="bg-slate-50 border border-slate-200/80 rounded-lg p-3">
                <div className="flex items-center text-slate-500 text-xs mb-1">
                  <Database className="w-3.5 h-3.5 mr-1 text-sky-600" />
                  Database
                </div>
                <div className="text-xs font-semibold text-slate-800 capitalize">{health.database || 'Configured'}</div>
              </div>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
};
