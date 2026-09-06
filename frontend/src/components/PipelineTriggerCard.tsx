import React, { useState } from 'react';
import { triggerPipeline } from '../services/api';
import { PipelineTriggerResponse } from '../types';
import { Play, RefreshCw, CheckCircle2, XCircle, Sparkles, Filter, Database, ShieldAlert, Cpu } from 'lucide-react';

interface Props {
  onPipelineSuccess: () => void;
}

export const PipelineTriggerCard: React.FC<Props> = ({ onPipelineSuccess }) => {
  const [running, setRunning] = useState<boolean>(false);
  const [result, setResult] = useState<PipelineTriggerResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [randomSeed, setRandomSeed] = useState<number>(42);

  const handleRunPipeline = async () => {
    setRunning(true);
    setError(null);
    try {
      const res = await triggerPipeline({
        random_seed: randomSeed,
        force_recalculate: true,
      });
      setResult(res);
      onPipelineSuccess();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Pipeline execution failed';
      setError(msg);
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-4 border-b border-slate-100">
        <div>
          <div className="flex items-center space-x-2">
            <h2 className="text-base font-semibold text-slate-800">Pipeline Ingestion & Index Trigger</h2>
            <span className="px-2 py-0.5 text-xs font-semibold bg-emerald-100 text-emerald-800 rounded-full">
              On-Demand
            </span>
          </div>
          <p className="text-xs text-slate-500 mt-0.5">
            Orchestrates configured collection &rarr; validation &rarr; deduplication &rarr; outlier filtering &rarr; APIx calculation
          </p>
        </div>

        <div className="flex items-center space-x-3">
          <div className="flex items-center space-x-1.5 text-xs text-slate-500">
            <label htmlFor="seedInput" className="font-medium">Seed:</label>
            <input
              id="seedInput"
              type="number"
              value={randomSeed}
              onChange={(e) => setRandomSeed(Number(e.target.value))}
              disabled={running}
              className="w-16 px-2 py-1 bg-slate-50 border border-slate-300 rounded text-xs text-slate-800 focus:ring-1 focus:ring-sky-500 focus:outline-none disabled:opacity-50"
              title="Random seed for reproducible configured runs"
            />
          </div>

          <button
            onClick={handleRunPipeline}
            disabled={running}
            className="inline-flex items-center px-4 py-2 text-xs font-semibold text-white bg-sky-600 hover:bg-sky-700 active:bg-sky-800 rounded-lg shadow-sm shadow-sky-200 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {running ? (
              <>
                <RefreshCw className="w-3.5 h-3.5 mr-2 animate-spin" />
                Executing Pipeline...
              </>
            ) : (
              <>
                <Play className="w-3.5 h-3.5 mr-1.5 fill-current" />
                Run Pipeline
              </>
            )}
          </button>
        </div>
      </div>

      {/* Status & Feedback Area */}
      <div className="mt-4">
        {running ? (
          <div className="bg-sky-50 border border-sky-200 rounded-xl p-4 text-sky-800">
            <div className="flex items-center space-x-3">
              <RefreshCw className="w-5 h-5 text-sky-600 animate-spin flex-shrink-0" />
              <div>
                <h4 className="text-xs font-semibold text-sky-900">Executing End-to-End Pipeline</h4>
                <p className="text-xs text-sky-700 mt-0.5">
                  Running the configured collection workflow, normalizing fare observations, eliminating duplicate flight slots, flagging IQR outliers, and computing weighted APIx scores...
                </p>
              </div>
            </div>
          </div>
        ) : error ? (
          <div className="bg-rose-50 border border-rose-200 rounded-xl p-4 text-rose-800">
            <div className="flex items-start space-x-3">
              <XCircle className="w-5 h-5 text-rose-500 flex-shrink-0 mt-0.5" />
              <div>
                <h4 className="text-xs font-semibold text-rose-900">Pipeline Execution Failed</h4>
                <p className="text-xs text-rose-700 mt-0.5">{error}</p>
              </div>
            </div>
          </div>
        ) : result ? (
          <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-600 flex-shrink-0" />
                <span className="text-xs font-semibold text-slate-800">
                  Pipeline Run Completed Successfully &bull; Job #{result.job_id} ({result.source})
                </span>
              </div>
              <span className="text-[11px] text-slate-500">
                Date: <strong>{result.collection_date}</strong>
              </span>
            </div>

            {/* Run Summary Metric Badges */}
            <div className="grid grid-cols-2 sm:grid-cols-5 gap-2 pt-1">
              <div className="bg-white border border-slate-200 rounded-lg p-2.5">
                <div className="flex items-center text-slate-500 text-[11px] mb-1">
                  <Cpu className="w-3 h-3 mr-1 text-sky-600" />
                  Ingested Quotes
                </div>
                <div className="text-sm font-bold text-slate-800">{result.ingested_count}</div>
              </div>

              <div className="bg-white border border-slate-200 rounded-lg p-2.5">
                <div className="flex items-center text-slate-500 text-[11px] mb-1">
                  <Database className="w-3 h-3 mr-1 text-indigo-600" />
                  Processed Quotes
                </div>
                <div className="text-sm font-bold text-slate-800">{result.processed_quotes_count}</div>
              </div>

              <div className="bg-white border border-slate-200 rounded-lg p-2.5">
                <div className="flex items-center text-slate-500 text-[11px] mb-1">
                  <ShieldAlert className="w-3 h-3 mr-1 text-amber-600" />
                  Outliers Flagged
                </div>
                <div className="text-sm font-bold text-amber-700">{result.outliers_count}</div>
              </div>

              <div className="bg-white border border-slate-200 rounded-lg p-2.5">
                <div className="flex items-center text-slate-500 text-[11px] mb-1">
                  <Filter className="w-3 h-3 mr-1 text-emerald-600" />
                  Clean Usable
                </div>
                <div className="text-sm font-bold text-emerald-700">{result.clean_usable_count}</div>
              </div>

              <div className="bg-white border border-slate-200 rounded-lg p-2.5">
                <div className="flex items-center text-slate-500 text-[11px] mb-1">
                  <Sparkles className="w-3 h-3 mr-1 text-sky-600" />
                  New APIx Index
                </div>
                <div className="text-sm font-extrabold text-sky-700">
                  {result.index_value !== null ? result.index_value.toFixed(2) : 'N/A'}
                </div>
              </div>
            </div>
          </div>
        ) : (
          <div className="flex items-center justify-between text-xs text-slate-500 bg-slate-50/70 border border-dashed border-slate-200 rounded-xl px-4 py-3">
            <span>Ready to execute the configured collection cycle. Click <strong>Run Pipeline</strong> to ingest quotes and update index values.</span>
          </div>
        )}
      </div>
    </div>
  );
};
