import React, { useEffect, useState } from 'react';
import {
  CheckCircle2,
  Layers,
  Play,
  Plus,
  Save,
  Settings2,
  Trash2,
  Zap,
} from 'lucide-react';
import { api } from '../api/client';
import { Demonstrator } from '../types/pipeline';
import { InfoTooltip } from './InfoTooltip';

interface BatchOrchestratorProps {
  demonstrators: Demonstrator[];
  onBatchStarted: (jobId: string) => void;
  onInspectBatchRun: (batchId: string) => void;
  onOpenWiki: (topicId: string) => void;
}

export const BatchOrchestrator: React.FC<BatchOrchestratorProps> = ({
  demonstrators,
  onBatchStarted,
  onInspectBatchRun,
  onOpenWiki,
}) => {
  const [config, setConfig] = useState<any | null>(null);
  const [dryRunCases, setDryRunCases] = useState<any[]>([]);
  const [batchRuns, setBatchRuns] = useState<any[]>([]);
  const [stopOnError, setStopOnError] = useState(false);
  const [saving, setSaving] = useState(false);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);

  const loadData = async () => {
    try {
      const [cfgRes, runsRes] = await Promise.all([
        api.getBatchConfig(),
        api.listBatchRuns(),
      ]);
      setConfig(cfgRes.configuration);
      setDryRunCases(cfgRes.dry_run_cases);
      setBatchRuns(runsRes.batch_runs);
    } catch {
      // ignore
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleSaveConfig = async (nextConfig: any) => {
    setSaving(true);
    setStatusMsg(null);
    try {
      const res = await api.updateBatchConfig(nextConfig);
      setConfig(res.configuration);
      setDryRunCases(res.dry_run_cases);
      setStatusMsg('Saved batch_configuration.json and updated dry-run case matrix.');
    } catch (err: any) {
      setStatusMsg(`Error: ${err.message}`);
    } finally {
      setSaving(false);
    }
  };

  const toggleGeometry = (dem: Demonstrator) => {
    if (!config) return;
    const exists = config.geometries.some((g: any) => g.key === dem.id);
    const nextGeoms = exists
      ? config.geometries.filter((g: any) => g.key !== dem.id)
      : [...config.geometries, { key: dem.id, demonstrator_dir: dem.demonstrator_dir }];
    const next = { ...config, geometries: nextGeoms };
    setConfig(next);
  };

  const toggleAllowedSize = (algIndex: number, sizeKey: string) => {
    if (!config) return;
    const nextAlgs = [...config.algorithm_presets];
    const alg = { ...nextAlgs[algIndex] };
    const allowed: string[] = alg.allowed_sizes || [];
    alg.allowed_sizes = allowed.includes(sizeKey)
      ? allowed.filter((s) => s !== sizeKey)
      : [...allowed, sizeKey];
    nextAlgs[algIndex] = alg;
    setConfig({ ...config, algorithm_presets: nextAlgs });
  };

  const updateCoarseningLimit = (
    idx: number,
    field: 'coarsen_inferior_limit' | 'coarsen_superior_limit',
    value: number
  ) => {
    if (!config) return;
    const nextPresets = [...config.coarsening_presets];
    nextPresets[idx] = { ...nextPresets[idx], [field]: value };
    setConfig({ ...config, coarsening_presets: nextPresets });
  };

  if (!config) {
    return (
      <div className="p-12 text-center text-sm text-slate-400">
        Loading batch study configuration...
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Top Banner */}
      <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-4 flex flex-wrap items-center justify-between gap-4 overflow-hidden">
        <div className="flex flex-wrap items-center gap-2.5 min-w-0">
          <span className="px-2.5 py-0.5 text-xs font-semibold rounded-full bg-violet-500/20 text-violet-300 border border-violet-500/30 shrink-0">
            Batch Study
          </span>
          <span className="text-xs text-slate-400">
            {config.geometries.length} geometries × {config.coarsening_presets.length} scales ×{' '}
            {config.algorithm_presets.length} algorithms →{' '}
            <strong className="text-slate-200">{dryRunCases.length} cases</strong>
          </span>
          <InfoTooltip topicId="batch-study" onOpenWiki={onOpenWiki} />
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <label className="flex items-center gap-2 text-xs text-slate-300 bg-slate-950 px-3 py-2 rounded-xl border border-slate-800 cursor-pointer">
            <input
              type="checkbox"
              checked={stopOnError}
              onChange={(e) => setStopOnError(e.target.checked)}
              className="rounded border-slate-700 bg-slate-900 text-indigo-600"
            />
            Stop on error
          </label>

          <button
            disabled={saving}
            onClick={() => handleSaveConfig(config)}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-semibold bg-slate-800 hover:bg-slate-700 text-white border border-slate-700 transition"
          >
            <Save className="w-4 h-4 text-indigo-400" />
            {saving ? 'Saving...' : 'Save'}
          </button>

          <button
            onClick={async () => {
              await handleSaveConfig(config);
              const job = await api.startBatchRun(stopOnError);
              onBatchStarted(job.job_id);
            }}
            className="inline-flex items-center gap-2 px-5 py-2 rounded-xl text-xs font-bold bg-gradient-to-r from-indigo-600 to-violet-600 hover:from-indigo-500 hover:to-violet-500 text-white shadow-lg shadow-indigo-600/30 transition"
          >
            <Play className="w-4 h-4 fill-current" />
            Run {dryRunCases.length} Cases
          </button>
        </div>
      </div>

      {statusMsg && (
        <div className="p-3 rounded-xl bg-indigo-950/60 border border-indigo-500/40 text-xs text-indigo-200">
          {statusMsg}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Column 1: Geometries & Coarsening Scales */}
        <div className="space-y-6">
          {/* Geometries */}
          <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 space-y-4">
            <div className="text-xs font-bold uppercase tracking-wider text-slate-400">
              Geometries
            </div>
            <div className="space-y-2.5">
              {demonstrators.map((dem) => {
                const active = config.geometries.some((g: any) => g.key === dem.id);
                return (
                  <button
                    key={dem.id}
                    type="button"
                    onClick={() => toggleGeometry(dem)}
                    className={`w-full text-left p-3 rounded-xl border transition flex items-center justify-between ${
                      active
                        ? 'bg-indigo-950/50 border-indigo-500 text-white'
                        : 'bg-slate-950/60 border-slate-800 text-slate-400 hover:border-slate-700'
                    }`}
                  >
                    <span className="text-xs font-bold">{dem.id}</span>
                    {active && <CheckCircle2 className="w-4 h-4 text-indigo-400" />}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Coarsening Size Presets */}
          <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 space-y-4">
            <div className="text-xs font-bold uppercase tracking-wider text-slate-400">
              Scales
            </div>
            <div className="space-y-3">
              {config.coarsening_presets.map((preset: any, idx: number) => (
                <div
                  key={preset.key}
                  className="p-3.5 rounded-xl bg-slate-950/80 border border-slate-800 space-y-2"
                >
                  <span className="text-xs font-bold uppercase text-amber-300 font-mono">
                    {preset.key}
                  </span>
                  <div className="grid grid-cols-2 gap-2">
                    <div>
                      <label className="block text-[10px] text-slate-400 mb-0.5">
                        Inferior
                      </label>
                      <input
                        type="number"
                        min={1}
                        value={preset.coarsen_inferior_limit}
                        onChange={(e) =>
                          updateCoarseningLimit(
                            idx,
                            'coarsen_inferior_limit',
                            Math.max(1, parseInt(e.target.value || '1', 10))
                          )
                        }
                        className="w-full bg-slate-900 border border-slate-700 rounded px-2 py-1 text-xs font-mono text-white"
                      />
                    </div>
                    <div>
                      <label className="block text-[10px] text-slate-400 mb-0.5">
                        Superior
                      </label>
                      <input
                        type="number"
                        min={1}
                        value={preset.coarsen_superior_limit ?? ''}
                        onChange={(e) =>
                          updateCoarseningLimit(
                            idx,
                            'coarsen_superior_limit',
                            Math.max(1, parseInt(e.target.value || '1', 10))
                          )
                        }
                        className="w-full bg-slate-900 border border-slate-700 rounded px-2 py-1 text-xs font-mono text-white"
                      />
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Column 2: Algorithm Presets & Allowed Scales Matrix */}
        <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 space-y-4 min-w-0 overflow-hidden">
          <div className="text-xs font-bold uppercase tracking-wider text-slate-400">
            Algorithms
          </div>
          <div className="space-y-3">
            {config.algorithm_presets.map((alg: any, idx: number) => {
              const simulated = alg.strategy_parameters?.simulated;
              const friendlyStrat =
                alg.partitioning_strategy === 'metis_partitioning'
                  ? 'METIS · classical'
                  : alg.partitioning_strategy === 'quantum_annealing'
                  ? simulated
                    ? 'Quantum Annealing · emulated'
                    : 'Quantum Annealing · D-Wave QPU'
                  : simulated
                  ? 'QAOA · emulated'
                  : 'QAOA · QLM QPU';
              return (
              <div
                key={alg.key}
                className="p-3.5 rounded-xl bg-slate-950/80 border border-slate-800 space-y-3 min-w-0 overflow-hidden"
              >
                <div className="flex flex-wrap items-start justify-between gap-2 min-w-0">
                  <div className="min-w-0 flex-1">
                    <div className="text-sm font-bold text-white font-mono truncate">
                      {alg.key}
                    </div>
                    <div
                      className="text-[11px] text-slate-400 truncate"
                      title={alg.partitioning_strategy}
                    >
                      {friendlyStrat}
                    </div>
                  </div>
                  <div className="flex flex-wrap items-center gap-1 shrink-0">
                    {config.coarsening_presets.map((cp: any) => {
                      const active = (alg.allowed_sizes || []).includes(cp.key);
                      return (
                        <button
                          key={cp.key}
                          type="button"
                          onClick={() => toggleAllowedSize(idx, cp.key)}
                          className={`px-2 py-0.5 rounded text-[11px] font-mono font-semibold border transition ${
                            active
                              ? 'bg-violet-600/30 border-violet-400 text-violet-200'
                              : 'bg-slate-900 border-slate-800 text-slate-500 hover:text-slate-300'
                          }`}
                        >
                          {cp.key}
                        </button>
                      );
                    })}
                  </div>
                </div>

                {Object.keys(alg.strategy_parameters || {}).length > 0 && (
                  <details className="text-[11px] font-mono text-slate-400 pt-1 border-t border-slate-800/80">
                    <summary className="cursor-pointer text-xs text-slate-400 hover:text-slate-200 py-0.5">
                      Parameters ({Object.keys(alg.strategy_parameters).length})
                    </summary>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-3 gap-y-1 mt-2">
                      {Object.entries(alg.strategy_parameters).map(([k, v]) => (
                        <div
                          key={k}
                          className="flex items-center justify-between gap-1.5 min-w-0"
                          title={`${k}: ${String(v)}`}
                        >
                          <span className="text-slate-500 truncate">{k}:</span>
                          <span className="text-slate-200 shrink-0 max-w-[110px] truncate">
                            {String(v)}
                          </span>
                        </div>
                      ))}
                    </div>
                  </details>
                )}
              </div>
              );
            })}
          </div>
        </div>

        {/* Column 3: Generated Dry-Run Case Matrix & Past Batch Runs */}
        <div className="space-y-6">
          <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold uppercase tracking-wider text-slate-400">
                Cases
              </span>
              <span className="px-2 py-0.5 rounded-full text-xs font-mono bg-indigo-500/20 text-indigo-300">
                {dryRunCases.length}
              </span>
            </div>

            <div className="max-h-[340px] overflow-y-auto space-y-1.5 pr-1">
              {dryRunCases.map((c, idx) => (
                <div
                  key={c.case_key}
                  className="px-3 py-2 rounded-lg bg-slate-950 border border-slate-800/80 flex items-center justify-between text-xs font-mono"
                >
                  <span className="text-slate-200 truncate">
                    <span className="text-slate-500 mr-2">
                      {String(idx + 1).padStart(2, '0')}.
                    </span>
                    {c.case_key}
                  </span>
                  {c.is_async && (
                    <span className="text-[10px] px-1.5 py-0.2 rounded bg-fuchsia-500/20 text-fuchsia-300">
                      async
                    </span>
                  )}
                </div>
              ))}
            </div>
          </div>

          {/* Past Batch Runs */}
          <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 space-y-3">
            <div className="text-xs font-bold uppercase tracking-wider text-slate-400">
              Past Runs
            </div>
            <div className="space-y-2">
              {batchRuns.map((br) => (
                <div
                  key={br.id}
                  className="p-3 rounded-xl bg-slate-950 border border-slate-800 flex items-center justify-between gap-2"
                >
                  <div>
                    <div className="text-xs font-bold font-mono text-white">{br.id}</div>
                    <div className="text-[11px] text-slate-400 mt-0.5">
                      {br.completed_cases} / {br.total_cases} completed •{' '}
                      {br.geometries.join(', ')}
                    </div>
                  </div>
                  <button
                    onClick={() => onInspectBatchRun(br.id)}
                    className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-indigo-600/20 text-indigo-300 border border-indigo-500/30 hover:bg-indigo-600/30 transition"
                  >
                    Analyze
                  </button>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

