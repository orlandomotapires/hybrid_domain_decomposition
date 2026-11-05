import React, { useEffect, useMemo, useState } from 'react';
import { AlertTriangle, Check, Clock, Play, Save, Zap } from 'lucide-react';
import { api } from '../api/client';
import { LibraryMatrix } from '../types/pipeline';
import { capacityFor, isRemoteHardware, maxCoarseNodes } from '../lib/feasibility';
import { methodColor, methodLabel, SCALE_LABELS } from '../lib/labels';
import { InfoTooltip } from './InfoTooltip';
import { useToast } from './Toasts';
import {
  COMMON_PARAM_GROUPS,
  ExtraParamField,
  ParamField,
  STRATEGY_PARAM_SPECS,
  validateParam,
  visibleSpecs,
} from './batch/ParamFields';

/** Remote QPU workload of one case: submissions (QA problems / QAOA jobs) and total reads/shots. */
interface QpuLoad {
  submissions: number;
  samples: number;
  /** "reads" for D-Wave annealing, "shots" for QLM QAOA. */
  unit: 'reads' | 'shots';
  /** Human-readable formula, for tooltips. */
  formula: string;
}

interface DurationEstimate {
  seconds: number;
  samples: number;
  /** "matrix" = same matrix + algorithm + scale; "algorithm" = any matrix, same algorithm + scale. */
  basis: 'matrix' | 'algorithm';
}

interface EstimatesResponse {
  by_case: Record<string, { median_seconds: number; samples: number }>;
  by_algorithm_scale: Record<string, { median_seconds: number; samples: number }>;
  sample_count: number;
  batch_count: number;
}

interface BatchCase {
  case_key: string;
  geometry: string;
  algorithm: string;
  coarsening_size: string;
  is_async: boolean;
  remote: boolean;
  maxNodes: number;
  /** Set when the coarse graph can exceed the backend's capacity. */
  overLimit: { limit: number; what: string } | null;
  qpu: QpuLoad | null;
  estimate: DurationEstimate | null;
}

// Backend defaults (src/libs/runtime/utils.py) used when a preset omits a parameter.
const QA_DEFAULTS = { num_starts: 5, num_reads: 5 };
const QAOA_DEFAULTS = { num_starts: 12, num_steps: 12, num_shots: 5 };

/**
 * Expected remote QPU workload. Recursive bisection to k parts runs (k−1) bipartitions per start.
 * QA: one annealing problem per bipartition. QAOA: (num_steps + 1) circuit evaluations per bipartition.
 */
function qpuLoadFor(alg: any, kTarget: number): QpuLoad | null {
  if (!isRemoteHardware(alg.partitioning_strategy, alg.strategy_parameters)) return null;
  const p = alg.strategy_parameters || {};
  const bisections = Math.max(1, kTarget - 1);
  if (alg.partitioning_strategy === 'quantum_annealing') {
    const starts = Number(p.num_starts ?? QA_DEFAULTS.num_starts);
    const reads = Number(p.num_reads ?? QA_DEFAULTS.num_reads);
    const submissions = starts * bisections;
    return {
      submissions,
      samples: submissions * reads,
      unit: 'reads',
      formula: `${starts} starts × ${bisections} bipartitions (k=${kTarget}) = ${submissions} QPU problems, × ${reads} reads each`,
    };
  }
  if (alg.partitioning_strategy === 'quantum_approximation_optimizer') {
    const starts = Number(p.num_starts ?? QAOA_DEFAULTS.num_starts);
    const steps = Number(p.num_steps ?? QAOA_DEFAULTS.num_steps);
    const shots = Number(p.num_shots ?? QAOA_DEFAULTS.num_shots);
    const submissions = starts * bisections * (steps + 1);
    return {
      submissions,
      samples: submissions * shots,
      unit: 'shots',
      formula: `${starts} starts × ${bisections} bipartitions (k=${kTarget}) × ${steps + 1} evaluations (num_steps+1) = ${submissions} QLM jobs, × ${shots} shots each`,
    };
  }
  return null;
}

function lookupEstimate(
  estimates: EstimatesResponse | null,
  geometry: string,
  algorithm: string,
  size: string
): DurationEstimate | null {
  if (!estimates) return null;
  const exact = estimates.by_case[`${geometry}__${algorithm}__${size}`];
  if (exact) return { seconds: exact.median_seconds, samples: exact.samples, basis: 'matrix' };
  const general = estimates.by_algorithm_scale[`${algorithm}__${size}`];
  if (general) return { seconds: general.median_seconds, samples: general.samples, basis: 'algorithm' };
  return null;
}

/** Mirror of backend `_compute_dry_run_cases`, computed live so edits show up before saving. */
function computeCases(config: any, estimates: EstimatesResponse | null): BatchCase[] {
  if (!config) return [];
  const asyncKeys = new Set<string>(config.async_remote_case_keys || []);
  const kTarget = Number(config.common_defaults?.partitioning_common?.k_target ?? 2);
  const cases: BatchCase[] = [];
  for (const geom of config.matrices || []) {
    for (const alg of config.algorithm_presets || []) {
      const allowed = new Set<string>(alg.allowed_sizes || []);
      const cap = capacityFor(alg.partitioning_strategy, alg.strategy_parameters);
      const qpu = qpuLoadFor(alg, kTarget);
      for (const preset of config.coarsening_presets || []) {
        if (!allowed.has(preset.key)) continue;
        const maxNodes = maxCoarseNodes(preset.coarsen_inferior_limit, preset.coarsen_superior_limit);
        cases.push({
          case_key: `${geom.key}__${alg.key}__${preset.key}`,
          geometry: geom.key,
          algorithm: alg.key,
          coarsening_size: preset.key,
          is_async: asyncKeys.has(alg.key),
          remote: isRemoteHardware(alg.partitioning_strategy, alg.strategy_parameters),
          maxNodes,
          overLimit: cap && maxNodes > cap.limit ? cap : null,
          qpu,
          estimate: lookupEstimate(estimates, geom.key, alg.key, preset.key),
        });
      }
    }
  }
  return cases;
}

function fmtDuration(seconds: number): string {
  const s = Math.round(seconds);
  if (s < 60) return `${s}s`;
  if (s < 3600) {
    const m = Math.floor(s / 60);
    const r = s % 60;
    return r ? `${m}m ${r}s` : `${m}m`;
  }
  const h = Math.floor(s / 3600);
  const m = Math.round((s % 3600) / 60);
  return m ? `${h}h ${m}m` : `${h}h`;
}

const fmtInt = (n: number) => n.toLocaleString();

/** Friendly label for a batch algorithm preset ("qa_hardware" → "Quantum Annealing (D-Wave QPU)"). */
function presetLabel(alg: any, short = false): string {
  const simulated = alg.partitioning_strategy === 'metis_partitioning' ? null : alg.strategy_parameters?.simulated ?? true;
  return methodLabel(alg.partitioning_strategy, simulated, short);
}

function presetColor(alg: any): string {
  return methodColor(alg.partitioning_strategy, alg.strategy_parameters?.simulated ?? true);
}

interface BatchTotals {
  /** Sum of estimates for cases that block the batch (async cases run in the background). */
  seconds: number;
  estimated: number;
  missing: number;
  asyncCount: number;
  submissions: number;
  reads: number;
  shots: number;
}

function totalsFor(cases: BatchCase[]): BatchTotals {
  const t: BatchTotals = { seconds: 0, estimated: 0, missing: 0, asyncCount: 0, submissions: 0, reads: 0, shots: 0 };
  for (const c of cases) {
    if (c.is_async) t.asyncCount += 1;
    if (c.estimate) {
      t.estimated += 1;
      if (!c.is_async) t.seconds += c.estimate.seconds;
    } else {
      t.missing += 1;
    }
    if (c.qpu) {
      t.submissions += c.qpu.submissions;
      if (c.qpu.unit === 'reads') t.reads += c.qpu.samples;
      else t.shots += c.qpu.samples;
    }
  }
  return t;
}

/** One-line summary: "≈ 42m (3 cases without estimate)" / "no estimate". */
function durationSummary(t: BatchTotals): string {
  if (t.estimated === 0) return 'no estimate';
  const base = `≈ ${fmtDuration(t.seconds)}`;
  return t.missing > 0 ? `${base} + ${t.missing} without estimate` : base;
}

function qpuSummary(t: BatchTotals): string | null {
  if (t.submissions === 0) return null;
  const parts = [`${fmtInt(t.submissions)} QPU submissions`];
  if (t.reads) parts.push(`${fmtInt(t.reads)} reads`);
  if (t.shots) parts.push(`${fmtInt(t.shots)} shots`);
  return parts.join(' · ');
}

/** Value of a shared parameter in the batch's base_parameters (shown when the override is empty). */
function baseValue(config: any, group: string, key: string): any {
  const base = config?.base_parameters;
  if (!base) return undefined;
  const block = group === 'partitioning_common' ? base.partitioning_parameters?.common : base[group];
  return block?.[key];
}

/** Number of invalid parameter values (blocks save / run). */
function countParamErrors(config: any): number {
  if (!config) return 0;
  let n = 0;
  for (const alg of config.algorithm_presets || []) {
    const params = alg.strategy_parameters || {};
    for (const spec of visibleSpecs(STRATEGY_PARAM_SPECS[alg.partitioning_strategy] || [], params)) {
      if (validateParam(spec, params[spec.key])) n += 1;
    }
  }
  for (const g of COMMON_PARAM_GROUPS) {
    for (const spec of g.specs) {
      if (validateParam(spec, config.common_defaults?.[g.group]?.[spec.key])) n += 1;
    }
  }
  return n;
}

/** Show the confirm dialog for long (estimated) batches even without QPU / capacity concerns. */
const LONG_BATCH_SECONDS = 15 * 60;

interface BatchOrchestratorProps {
  /** Shared matrix library; the batch runs every selected matrix (simulation settings are not used). */
  matrixLibrary: LibraryMatrix[];
  onBatchStarted: (jobId: string) => void;
  onInspectBatchRun: (batchId: string) => void;
  onOpenWiki: (topicId: string) => void;
}

export const BatchOrchestrator: React.FC<BatchOrchestratorProps> = ({
  matrixLibrary,
  onBatchStarted,
  onInspectBatchRun,
  onOpenWiki,
}) => {
  const toast = useToast();
  const [config, setConfig] = useState<any | null>(null);
  const [savedConfigJson, setSavedConfigJson] = useState<string>('');
  const [confirmRun, setConfirmRun] = useState(false);
  const [starting, setStarting] = useState(false);
  const [batchRuns, setBatchRuns] = useState<any[]>([]);
  const [estimates, setEstimates] = useState<EstimatesResponse | null>(null);
  const [stopOnError, setStopOnError] = useState(false);
  const [saving, setSaving] = useState(false);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);

  const loadData = async () => {
    try {
      const [cfgRes, runsRes] = await Promise.all([api.getBatchConfig(), api.listBatchRuns()]);
      setConfig(cfgRes.configuration);
      setSavedConfigJson(JSON.stringify(cfgRes.configuration));
      setBatchRuns(runsRes.batch_runs);
    } catch (err: any) {
      toast.error(`Could not load the batch configuration: ${err.message}`);
    }
    // Estimates are a nice-to-have; a failure just means "no estimate".
    try {
      setEstimates(await api.getBatchEstimates());
    } catch {
      setEstimates(null);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleSaveConfig = async (nextConfig: any): Promise<boolean> => {
    setSaving(true);
    setStatusMsg(null);
    try {
      const res = await api.updateBatchConfig(nextConfig);
      setConfig(res.configuration);
      setSavedConfigJson(JSON.stringify(res.configuration));
      setStatusMsg('Saved batch_configuration.json.');
      return true;
    } catch (err: any) {
      toast.error(`Could not save the batch configuration: ${err.message}`);
      return false;
    } finally {
      setSaving(false);
    }
  };

  const cases = useMemo(() => computeCases(config, estimates), [config, estimates]);
  const totals = useMemo(() => totalsFor(cases), [cases]);
  const overLimitCases = cases.filter((c) => c.overLimit);
  const remoteCases = cases.filter((c) => c.remote);
  const algScalePairs = (config?.algorithm_presets || []).reduce(
    (n: number, alg: any) =>
      n +
      (config?.coarsening_presets || []).filter((p: any) => (alg.allowed_sizes || []).includes(p.key)).length,
    0
  );
  const unsaved = !!config && JSON.stringify(config) !== savedConfigJson;
  const kTarget = Number(config?.common_defaults?.partitioning_common?.k_target ?? 2);
  const qpuLine = qpuSummary(totals);
  const paramErrors = useMemo(() => countParamErrors(config), [config]);

  const startBatch = async () => {
    setConfirmRun(false);
    setStarting(true);
    try {
      if (!(await handleSaveConfig(config))) return;
      const job = await api.startBatchRun(stopOnError);
      onBatchStarted(job.job_id);
    } catch (err: any) {
      toast.error(`Could not start the batch: ${err.message}`);
    } finally {
      setStarting(false);
    }
  };

  const requestRun = () => {
    if (cases.length === 0) {
      toast.error('No cases selected: pick at least one matrix and one algorithm scale.');
      return;
    }
    if (overLimitCases.length > 0 || remoteCases.length > 0 || totals.seconds > LONG_BATCH_SECONDS) {
      setConfirmRun(true);
    } else {
      startBatch();
    }
  };

  const toggleMatrix = (pairId: string) => {
    if (!config) return;
    const pairs: any[] = config.matrices || [];
    const exists = pairs.some((g: any) => g.key === pairId);
    const next = exists ? pairs.filter((g: any) => g.key !== pairId) : [...pairs, { key: pairId }];
    setConfig({ ...config, matrices: next });
  };

  const toggleAllowedSize = (algIndex: number, sizeKey: string) => {
    if (!config) return;
    const nextAlgs = [...config.algorithm_presets];
    const alg = { ...nextAlgs[algIndex] };
    const allowed: string[] = alg.allowed_sizes || [];
    alg.allowed_sizes = allowed.includes(sizeKey) ? allowed.filter((s) => s !== sizeKey) : [...allowed, sizeKey];
    nextAlgs[algIndex] = alg;
    setConfig({ ...config, algorithm_presets: nextAlgs });
  };

  const updateStrategyParam = (algIndex: number, key: string, value: unknown) => {
    if (!config) return;
    const nextAlgs = [...config.algorithm_presets];
    const params = { ...(nextAlgs[algIndex].strategy_parameters || {}) };
    if (value === undefined) delete params[key];
    else params[key] = value;
    nextAlgs[algIndex] = { ...nextAlgs[algIndex], strategy_parameters: params };
    setConfig({ ...config, algorithm_presets: nextAlgs });
  };

  const updateCommon = (group: string, key: string, value: unknown) => {
    if (!config) return;
    const groupVals = { ...(config.common_defaults?.[group] || {}) };
    if (value === undefined) delete groupVals[key];
    else groupVals[key] = value;
    setConfig({ ...config, common_defaults: { ...(config.common_defaults || {}), [group]: groupVals } });
  };

  const toggleAsync = (algKey: string) => {
    if (!config) return;
    const keys: string[] = config.async_remote_case_keys || [];
    setConfig({
      ...config,
      async_remote_case_keys: keys.includes(algKey) ? keys.filter((k) => k !== algKey) : [...keys, algKey],
    });
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
    return <div className="p-12 text-center text-sm text-slate-400">Loading batch study configuration...</div>;
  }

  const scalePresets: any[] = config.coarsening_presets || [];
  const scrollToId = (id: string) =>
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  const gridCols = { gridTemplateColumns: `minmax(0,1fr) repeat(${scalePresets.length}, minmax(4.25rem, 5rem))` };

  return (
    <div className="grid grid-cols-1 xl:grid-cols-[260px_minmax(0,1fr)_340px] gap-6 items-start">
      {/* LEFT — study setup: what the cases are made of, and an index of the algorithms */}
      <aside
        aria-label="Batch setup"
        className="order-2 xl:order-1 xl:sticky xl:top-[124px] xl:max-h-[calc(100vh-140px)] xl:overflow-y-auto min-w-0 grid grid-cols-1 md:grid-cols-3 xl:grid-cols-1 gap-4 content-start"
      >
        <section className="bg-slate-900/80 border border-slate-800 rounded-2xl p-4 space-y-2.5 min-w-0">
          <div className="text-xs text-slate-500"><span className="font-mono text-indigo-300">1</span> What to run on</div>
          <div className="flex items-center justify-between gap-2">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-400">Matrices</span>
            <span className="flex gap-2 text-xs">
              <button
                type="button"
                onClick={() => setConfig({ ...config, matrices: matrixLibrary.map((p) => ({ key: p.id })) })}
                className="text-indigo-300 hover:text-indigo-200"
              >
                All
              </button>
              <button
                type="button"
                onClick={() => setConfig({ ...config, matrices: [] })}
                className="text-slate-400 hover:text-slate-200"
              >
                None
              </button>
            </span>
          </div>
          <div className="space-y-1 max-h-40 overflow-y-auto pr-1">
            {matrixLibrary.length === 0 && (
              <span className="text-xs text-slate-500">The matrix library is empty — add a matrix in Single Run.</span>
            )}
            {matrixLibrary.map((pair) => {
              const active = (config.matrices || []).some((g: any) => g.key === pair.id);
              const rows = pair.info.rows;
              return (
                <button
                  key={pair.id}
                  type="button"
                  role="checkbox"
                  aria-checked={active}
                  onClick={() => toggleMatrix(pair.id)}
                  title={`${pair.name} (${pair.id})${pair.used_by.length ? ` · used by ${pair.used_by.join(', ')}` : ''}`}
                  className={`w-full flex items-center gap-2 px-2 py-1.5 rounded-lg border text-left transition ${
                    active
                      ? 'bg-indigo-950/60 border-indigo-500 text-white'
                      : 'bg-slate-950/60 border-slate-800 text-slate-400 hover:border-slate-600'
                  }`}
                >
                  <span
                    className={`w-3.5 h-3.5 rounded flex items-center justify-center border shrink-0 ${
                      active ? 'bg-indigo-500 border-indigo-400 text-white' : 'border-slate-600'
                    }`}
                    aria-hidden
                  >
                    {active && <Check className="w-2.5 h-2.5" strokeWidth={3} />}
                  </span>
                  <span className="text-xs font-mono break-all flex-1 min-w-0">{pair.id}</span>
                  {rows != null && <span className="text-xs font-mono text-slate-500 shrink-0">n={rows.toLocaleString()}</span>}
                  {(!pair.ready || !pair.square) && (
                    <AlertTriangle className="w-3 h-3 text-amber-400 shrink-0" aria-label={pair.ready ? 'Not square' : 'File missing'} />
                  )}
                </button>
              );
            })}
            {(config.matrices || [])
              .filter((g: any) => !matrixLibrary.some((p) => p.id === g.key))
              .map((g: any) => (
                <div key={g.key} className="flex items-center gap-2 px-2 py-1.5 rounded-lg border border-amber-500/50 text-xs text-amber-200">
                  <AlertTriangle className="w-3 h-3 shrink-0" />
                  <span className="font-mono truncate flex-1">{g.key}</span>
                  <button type="button" onClick={() => toggleMatrix(g.key)} className="underline">
                    remove
                  </button>
                </div>
              ))}
          </div>
        </section>

        <section className="bg-slate-900/80 border border-slate-800 rounded-2xl p-4 space-y-2 min-w-0">
          <div className="text-xs text-slate-500"><span className="font-mono text-indigo-300">2</span> Coarse graph sizes</div>
          <div className="flex items-baseline justify-between gap-2">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-400">Scales</span>
            <span className="text-xs text-slate-500">coarse nodes</span>
          </div>
          <div className="grid grid-cols-[auto_1fr_auto_1fr] items-center gap-x-1.5 gap-y-1.5">
            {scalePresets.map((preset: any, idx: number) => (
              <React.Fragment key={preset.key}>
                <span className="text-xs font-semibold text-slate-200 pr-1" title={preset.key}>
                  {SCALE_LABELS[preset.key] || preset.key}
                </span>
                <input
                  type="number"
                  min={1}
                  aria-label={`${SCALE_LABELS[preset.key] || preset.key} inferior limit`}
                  title="Inferior limit"
                  value={preset.coarsen_inferior_limit}
                  onChange={(e) =>
                    updateCoarseningLimit(idx, 'coarsen_inferior_limit', Math.max(1, parseInt(e.target.value || '1', 10)))
                  }
                  className="w-full min-w-0 bg-slate-950 border border-slate-700 rounded px-2 py-1 text-xs font-mono text-white"
                />
                <span className="text-xs text-slate-500">–</span>
                <input
                  type="number"
                  min={1}
                  aria-label={`${SCALE_LABELS[preset.key] || preset.key} superior limit`}
                  title="Superior limit"
                  value={preset.coarsen_superior_limit ?? ''}
                  onChange={(e) =>
                    updateCoarseningLimit(idx, 'coarsen_superior_limit', Math.max(1, parseInt(e.target.value || '1', 10)))
                  }
                  className="w-full min-w-0 bg-slate-950 border border-slate-700 rounded px-2 py-1 text-xs font-mono text-white"
                />
              </React.Fragment>
            ))}
          </div>
        </section>

        <nav aria-label="Batch sections" className="bg-slate-900/80 border border-slate-800 rounded-2xl p-4 space-y-2 min-w-0">
          <div className="text-xs text-slate-500"><span className="font-mono text-indigo-300">3</span> Configure</div>
          <button
            type="button"
            onClick={() => scrollToId('batch-shared')}
            className="w-full flex items-center justify-between gap-2 px-2.5 py-2 rounded-lg bg-slate-950/60 border border-slate-800 hover:border-slate-600 text-left transition"
          >
            <span className="text-xs font-semibold text-slate-200">Shared parameters</span>
            <span className="text-xs text-slate-500">
              {Object.values(config.common_defaults || {}).reduce((n: number, g: any) => n + Object.keys(g || {}).length, 0)} set
            </span>
          </button>
          <div className="pt-1 text-xs font-bold uppercase tracking-wider text-slate-400">Algorithms</div>
          <ul className="space-y-1">
            {config.algorithm_presets.map((alg: any) => {
              const ticked = (alg.allowed_sizes || []).filter((k: string) => scalePresets.some((cp) => cp.key === k)).length;
              const remote = isRemoteHardware(alg.partitioning_strategy, alg.strategy_parameters);
              const tooLarge = overLimitCases.some((c) => c.algorithm === alg.key);
              const params = alg.strategy_parameters || {};
              const invalid = visibleSpecs(STRATEGY_PARAM_SPECS[alg.partitioning_strategy] || [], params).some(
                (spec) => !!validateParam(spec, params[spec.key])
              );
              return (
                <li key={alg.key}>
                  <button
                    type="button"
                    onClick={() => scrollToId(`batch-alg-${alg.key}`)}
                    title={`${presetLabel(alg)} · ${ticked} of ${scalePresets.length} scales ticked`}
                    className={`w-full flex items-center gap-2 px-2.5 py-1.5 rounded-lg border text-left transition ${
                      ticked > 0
                        ? 'bg-slate-950/70 border-slate-700 hover:border-slate-500'
                        : 'bg-slate-950/30 border-slate-800 opacity-60 hover:opacity-100'
                    }`}
                  >
                    <span className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: presetColor(alg) }} aria-hidden />
                    <span className="text-xs font-medium text-slate-100 truncate flex-1 min-w-0">{presetLabel(alg, true)}</span>
                    {invalid && <AlertTriangle className="w-3 h-3 text-rose-400 shrink-0" aria-label="Invalid parameter" />}
                    {tooLarge && <AlertTriangle className="w-3 h-3 text-amber-400 shrink-0" aria-label="Scale too large" />}
                    {remote && <Zap className="w-3 h-3 text-slate-400 shrink-0" aria-label="Real QPU" />}
                    <span className={`text-xs font-mono shrink-0 ${ticked ? 'text-indigo-300' : 'text-slate-600'}`}>
                      {ticked}/{scalePresets.length}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        </nav>
      </aside>

      {/* CENTER — the editors */}
      <div className="order-3 xl:order-2 space-y-6 min-w-0">
        <section id="batch-shared" className="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 space-y-3 scroll-mt-32">
          <div className="flex items-baseline justify-between gap-2">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-400">Shared parameters</span>
            <span className="text-xs text-slate-500" title="Empty fields keep the value from base_parameters in batch_configuration.json">applied to every case · empty = base value</span>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 2xl:grid-cols-5 gap-2">
            {COMMON_PARAM_GROUPS.flatMap((g) =>
              g.specs.map((spec) => (
                <ParamField
                  key={`${g.group}.${spec.key}`}
                  idPrefix={`common-${g.group}`}
                  spec={{
                    ...spec,
                    def: baseValue(config, g.group, spec.key) ?? spec.def,
                    hint: [g.title, spec.hint].filter(Boolean).join(' · '),
                  }}
                  value={config.common_defaults?.[g.group]?.[spec.key]}
                  onChange={(v) => updateCommon(g.group, spec.key, v)}
                />
              ))
            )}
          </div>
        </section>

        <section className="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 space-y-3 min-w-0 overflow-hidden">
          <div className="flex items-baseline justify-between gap-2">
            <div className="text-xs font-bold uppercase tracking-wider text-slate-400">Algorithms</div>
            <div className="text-xs text-slate-500">k = {kTarget}</div>
          </div>
          <p className="text-xs text-slate-400 leading-snug">
            Tick the scales each algorithm should run at (every ticked cell runs once per selected matrix) and tune its
            parameters below. Empty fields use the backend default shown in grey.
          </p>

          <div role="group" aria-label="Algorithm and scale selection" className="text-xs">
            {/* Header row */}
            <div className="grid items-end gap-1.5 pb-2 border-b border-slate-800" style={gridCols}>
              <div className="text-xs font-semibold text-slate-400">Algorithm</div>
              {scalePresets.map((cp) => (
                <div key={cp.key} className="text-center">
                  <div className="text-xs font-semibold text-slate-200">{SCALE_LABELS[cp.key] || cp.key}</div>
                  <div className="text-xs font-mono text-slate-500">
                    ≤{maxCoarseNodes(cp.coarsen_inferior_limit, cp.coarsen_superior_limit).toLocaleString()}
                  </div>
                </div>
              ))}
            </div>

            {config.algorithm_presets.map((alg: any, idx: number) => {
              const cap = capacityFor(alg.partitioning_strategy, alg.strategy_parameters);
              const remote = isRemoteHardware(alg.partitioning_strategy, alg.strategy_parameters);
              const params: Record<string, any> = alg.strategy_parameters || {};
              const specs = STRATEGY_PARAM_SPECS[alg.partitioning_strategy] || [];
              const shown = visibleSpecs(specs, params);
              const extraKeys = Object.keys(params).filter((k) => !specs.some((s) => s.key === k));
              const isAsync = (config.async_remote_case_keys || []).includes(alg.key);
              return (
                <div
                  key={alg.key}
                  id={`batch-alg-${alg.key}`}
                  className="py-3 border-b border-slate-800/70 last:border-b-0 scroll-mt-32"
                >
                  <div className="grid items-center gap-1.5" style={gridCols}>
                    <div className="min-w-0">
                      <div className="flex items-center gap-1.5 min-w-0">
                        <span
                          className="w-2 h-2 rounded-full shrink-0"
                          style={{ backgroundColor: presetColor(alg) }}
                          aria-hidden
                        />
                        <span className="text-xs font-semibold text-slate-100 truncate" title={presetLabel(alg)}>
                          {presetLabel(alg, true)}
                        </span>
                      </div>
                      <div className="pl-3.5 flex items-center gap-1.5 text-xs text-slate-500 min-w-0">
                        <code className="font-mono truncate">{alg.key}</code>
                        {remote && (
                          <span className="inline-flex items-center gap-0.5 text-slate-300 shrink-0" title="Runs on real remote quantum hardware">
                            <Zap className="w-3 h-3" />
                            QPU
                          </span>
                        )}
                      </div>
                    </div>
                    {scalePresets.map((cp) => {
                      const active = (alg.allowed_sizes || []).includes(cp.key);
                      const nodes = maxCoarseNodes(cp.coarsen_inferior_limit, cp.coarsen_superior_limit);
                      const tooBig = !!cap && nodes > cap.limit;
                      const label = `${presetLabel(alg)} at ${SCALE_LABELS[cp.key] || cp.key} scale`;
                      return (
                        <button
                          key={cp.key}
                          type="button"
                          role="checkbox"
                          aria-checked={active}
                          aria-label={label}
                          onClick={() => toggleAllowedSize(idx, cp.key)}
                          title={`${label}: ${active ? 'included' : 'not included'} · coarse graph up to ${nodes.toLocaleString()} nodes${
                            tooBig ? ` — exceeds ~${cap!.limit} (${cap!.what}), likely to fail` : ''
                          }`}
                          className={`h-11 rounded-lg border flex flex-col items-center justify-center gap-0.5 transition focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 ${
                            active && tooBig
                              ? 'bg-amber-500/15 border-amber-400/80 text-amber-200'
                              : active
                              ? 'bg-indigo-600/25 border-indigo-400 text-indigo-100'
                              : 'bg-slate-950/60 border-slate-800 text-slate-500 hover:border-slate-600 hover:text-slate-300'
                          }`}
                        >
                          <span
                            className={`w-4 h-4 rounded flex items-center justify-center border ${
                              active
                                ? tooBig
                                  ? 'bg-amber-500 border-amber-400 text-slate-950'
                                  : 'bg-indigo-500 border-indigo-400 text-white'
                                : 'border-slate-600 bg-slate-900'
                            }`}
                            aria-hidden
                          >
                            {active && <Check className="w-3 h-3" strokeWidth={3} />}
                          </span>
                          {tooBig ? (
                            <span className={`inline-flex items-center gap-0.5 text-xs leading-none ${active ? 'text-amber-300' : 'text-amber-400/70'}`}>
                              <AlertTriangle className="w-3 h-3" />
                              too large
                            </span>
                          ) : (
                            <span className="text-xs leading-none">{active ? 'on' : 'off'}</span>
                          )}
                        </button>
                      );
                    })}
                  </div>

                  {specs.length === 0 && extraKeys.length === 0 ? (
                    <div className="mt-2 pl-3.5 text-xs text-slate-500">
                      No algorithm-specific parameters — uses the shared partitioning settings.
                    </div>
                  ) : (
                    <div className="mt-2.5 ml-3.5 p-2.5 rounded-lg bg-slate-950/50 border border-slate-800/80 grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2">
                      {shown.map((spec) => (
                        <ParamField
                          key={spec.key}
                          idPrefix={`alg-${alg.key}`}
                          spec={spec}
                          value={params[spec.key]}
                          onChange={(v) => updateStrategyParam(idx, spec.key, v)}
                        />
                      ))}
                      {extraKeys.map((k) => (
                        <ExtraParamField
                          key={k}
                          name={k}
                          value={params[k]}
                          onChange={(v) => updateStrategyParam(idx, k, v)}
                          onRemove={() => updateStrategyParam(idx, k, undefined)}
                        />
                      ))}
                      {remote && (
                        <label
                          className="col-span-full flex items-center gap-2 text-xs text-slate-300 cursor-pointer"
                          title="Submit to the remote backend in the background so the batch continues with other cases meanwhile"
                        >
                          <input
                            type="checkbox"
                            checked={isAsync}
                            onChange={() => toggleAsync(alg.key)}
                            className="rounded border-slate-700 bg-slate-900 text-indigo-600"
                          />
                          Run asynchronously (don't block the batch while waiting for the QPU)
                        </label>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </section>
      </div>

      {/* RIGHT — run panel: what will happen, warnings, and the actions */}
      <aside
        aria-label="Run summary"
        className="order-1 xl:order-3 xl:sticky xl:top-[124px] xl:max-h-[calc(100vh-140px)] xl:overflow-y-auto space-y-4 min-w-0"
      >
        <section className="bg-slate-900/90 border border-slate-700 rounded-2xl p-4 space-y-3">
          <div className="flex items-center justify-between gap-2">
            <span className="inline-flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-slate-400">
              Batch study <InfoTooltip topicId="batch-study" onOpenWiki={onOpenWiki} />
            </span>
            {unsaved ? (
              <span className="text-xs text-amber-300">unsaved changes</span>
            ) : (
              <span className="text-xs text-emerald-400">saved</span>
            )}
          </div>

          <div className="flex items-baseline gap-2">
            <span className="text-3xl font-bold text-white tabular-nums">{cases.length}</span>
            <span className="text-xs text-slate-400">
              {cases.length === 1 ? 'case' : 'cases'} = {(config.matrices || []).length}{' '}
              {(config.matrices || []).length === 1 ? 'matrix' : 'matrices'} × {algScalePairs} algorithm/scale{' '}
              {algScalePairs === 1 ? 'pair' : 'pairs'}
            </span>
          </div>

          <dl className="space-y-1.5 text-xs">
            <div
              className="flex items-start justify-between gap-3"
              title={
                'Sum of median durations of past batch runs with the same algorithm and scale ' +
                '(same matrix when available). Async remote cases run in the background and are not added.' +
                (estimates ? ` Based on ${estimates.sample_count} past cases from ${estimates.batch_count} batch(es).` : '')
              }
            >
              <dt className="inline-flex items-center gap-1.5 text-slate-400">
                <Clock className="w-3.5 h-3.5" /> Duration
              </dt>
              <dd className="text-right text-slate-100 font-medium">
                {cases.length ? durationSummary(totals) : '—'}
                {totals.asyncCount > 0 && <div className="text-slate-500 font-normal">+ {totals.asyncCount} async in background</div>}
              </dd>
            </div>
            <div className="flex items-start justify-between gap-3" title="Remote quantum workload billed to your D-Wave Leap / QLM account">
              <dt className="inline-flex items-center gap-1.5 text-slate-400">
                <Zap className="w-3.5 h-3.5" /> Real QPU
              </dt>
              <dd className="text-right text-slate-100 font-medium">
                {remoteCases.length ? (
                  <>
                    {remoteCases.length} {remoteCases.length === 1 ? 'case' : 'cases'}
                    {qpuLine && <div className="text-slate-400 font-normal">{qpuLine}</div>}
                  </>
                ) : (
                  <span className="text-slate-500 font-normal">none</span>
                )}
              </dd>
            </div>
          </dl>

          {paramErrors > 0 && (
            <div className="p-2.5 rounded-lg bg-rose-950/50 border border-rose-500/50 text-xs text-rose-200 flex items-start gap-2">
              <AlertTriangle className="w-3.5 h-3.5 text-rose-400 shrink-0 mt-0.5" />
              {paramErrors} invalid {paramErrors === 1 ? 'parameter' : 'parameters'} — fix the fields outlined in red before saving or running.
            </div>
          )}

          {overLimitCases.length > 0 && (
            <div className="p-2.5 rounded-lg bg-amber-950/40 border border-amber-500/50 text-xs text-amber-100 space-y-1">
              <div className="flex items-start gap-2 font-semibold">
                <AlertTriangle className="w-3.5 h-3.5 text-amber-400 shrink-0 mt-0.5" />
                {overLimitCases.length} {overLimitCases.length === 1 ? 'case is' : 'cases are'} too large for their backend
              </div>
          <ul className="pl-4 list-disc space-y-0.5 text-amber-200/90">
            {Array.from(
              new Map(overLimitCases.map((c) => [`${c.algorithm}/${c.coarsening_size}`, c] as const)).values()
            ).map((c) => (
              <li key={`${c.algorithm}/${c.coarsening_size}`}>
                {methodLabel(c.algorithm)} at <strong>{SCALE_LABELS[c.coarsening_size] || c.coarsening_size}</strong>{' '}
                scale — coarse graph up to {c.maxNodes.toLocaleString()} nodes, limit ~{c.overLimit!.limit} for{' '}
                {c.overLimit!.what}
              </li>
            ))}
          </ul>
              <div className="text-amber-200/80">Untick those cells, or pick a smaller scale.</div>
            </div>
          )}

          {statusMsg && !unsaved && (
            <div className="p-2.5 rounded-lg bg-indigo-950/60 border border-indigo-500/40 text-xs text-indigo-200">{statusMsg}</div>
          )}

          <label className="flex items-center gap-2 text-xs text-slate-300 cursor-pointer">
            <input
              type="checkbox"
              checked={stopOnError}
              onChange={(e) => setStopOnError(e.target.checked)}
              className="rounded border-slate-700 bg-slate-900 text-indigo-600"
            />
            Stop the batch at the first failed case
          </label>

          <div className="grid grid-cols-[auto_1fr] gap-2">
            <button
              disabled={saving || paramErrors > 0 || !unsaved}
              onClick={() => handleSaveConfig(config)}
              className="inline-flex items-center justify-center gap-2 px-4 py-2 rounded-xl text-xs font-semibold bg-slate-800 hover:bg-slate-700 text-white border border-slate-700 transition disabled:opacity-50"
            >
              <Save className="w-4 h-4 text-indigo-400" />
              {saving ? 'Saving...' : 'Save'}
            </button>
            <button
              onClick={requestRun}
              disabled={starting || cases.length === 0 || paramErrors > 0}
              className="inline-flex items-center justify-center gap-2 px-5 py-2 rounded-xl text-xs font-bold bg-indigo-600 hover:bg-indigo-500 text-white shadow-lg shadow-indigo-600/30 transition disabled:opacity-50"
            >
              <Play className="w-4 h-4 fill-current" />
              {starting ? 'Starting…' : `Run ${cases.length} ${cases.length === 1 ? 'case' : 'cases'}`}
            </button>
          </div>
        </section>

        <section className="bg-slate-900/80 border border-slate-800 rounded-2xl p-4 space-y-2.5">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-400">Cases</span>
            <span className="px-2 py-0.5 rounded-full text-xs font-mono bg-indigo-500/20 text-indigo-300">{cases.length}</span>
          </div>
            <div className="max-h-[340px] xl:max-h-[38vh] overflow-y-auto space-y-1.5 pr-1">
              {cases.length === 0 && (
                <div className="text-xs text-slate-500 py-6 text-center">
                  No cases — select at least one matrix and tick at least one scale in the Algorithms panel.
                </div>
              )}
              {cases.map((c, idx) => (
                <div
                  key={c.case_key}
                  className={`px-3 py-2 rounded-lg bg-slate-950 border text-xs space-y-1 ${
                    c.overLimit ? 'border-amber-500/50' : 'border-slate-800/80'
                  }`}
                  title={
                    c.overLimit
                      ? `Coarse graph up to ${c.maxNodes} nodes exceeds ~${c.overLimit.limit} (${c.overLimit.what})`
                      : undefined
                  }
                >
                  <div className="flex items-start justify-between gap-2" title={c.case_key}>
                    <span className="min-w-0">
                      <span className="flex items-center gap-1.5 text-slate-100 font-medium">
                        <span className="font-mono text-slate-500">{String(idx + 1).padStart(2, '0')}.</span>
                        <span
                          className="w-2 h-2 rounded-full shrink-0"
                          style={{ backgroundColor: methodColor(c.algorithm) }}
                          aria-hidden
                        />
                        <span className="truncate">
                          {methodLabel(c.algorithm, undefined, true)} · {SCALE_LABELS[c.coarsening_size] || c.coarsening_size}
                        </span>
                      </span>
                      <span className="block pl-7 font-mono text-slate-500 break-all">{c.geometry}</span>
                    </span>
                    <span className="flex flex-wrap justify-end items-center gap-1 shrink-0 font-sans">
                      {c.overLimit && (
                        <span className="inline-flex items-center gap-0.5 text-xs px-1.5 rounded bg-amber-500/20 text-amber-300">
                          <AlertTriangle className="w-3 h-3" /> too large
                        </span>
                      )}
                      {c.remote && (
                        <span
                          className="inline-flex items-center gap-0.5 text-xs px-1.5 rounded bg-slate-700/60 text-slate-200 border border-slate-600"
                          title="Runs on real remote quantum hardware (uses QPU time / credentials)"
                        >
                          <Zap className="w-3 h-3" />
                          QPU
                        </span>
                      )}
                      {c.is_async && (
                        <span
                          className="text-xs px-1.5 rounded bg-slate-800 text-slate-300 border border-slate-700"
                          title="Submitted to the remote QLM in the background; the batch continues with other cases meanwhile"
                        >
                          async
                        </span>
                      )}
                    </span>
                  </div>
                  <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 pl-7 text-xs text-slate-400">
                    <span
                      className="inline-flex items-center gap-1"
                      title={
                        c.estimate
                          ? `Median of ${c.estimate.samples} past ${c.estimate.samples === 1 ? 'run' : 'runs'} of ${methodLabel(c.algorithm)} at ${
                              SCALE_LABELS[c.coarsening_size] || c.coarsening_size
                            } scale${c.estimate.basis === 'matrix' ? ` on ${c.geometry}` : ' (any matrix)'}`
                          : 'No past batch run of this algorithm and scale'
                      }
                    >
                      <Clock className="w-3 h-3" />
                      {c.estimate ? (
                        <>
                          ≈ {fmtDuration(c.estimate.seconds)}
                          {c.estimate.basis === 'algorithm' && <span className="text-slate-500">(other matrix)</span>}
                        </>
                      ) : (
                        <span className="text-slate-500">no estimate</span>
                      )}
                    </span>
                    {c.qpu ? (
                      <span className="inline-flex items-center gap-1" title={c.qpu.formula}>
                        <Zap className="w-3 h-3" />
                        {fmtInt(c.qpu.submissions)} submissions · {fmtInt(c.qpu.samples)} {c.qpu.unit}
                      </span>
                    ) : (
                      <span className="text-slate-500">no remote QPU use</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
        </section>

        <details className="bg-slate-900/80 border border-slate-800 rounded-2xl p-4 group" open={batchRuns.length > 0 && batchRuns.length <= 3}>
          <summary className="cursor-pointer list-none flex items-center justify-between text-xs font-bold uppercase tracking-wider text-slate-400">
            Past runs
            <span className="font-mono font-normal normal-case text-slate-500">{batchRuns.length}</span>
          </summary>
          <div className="mt-2.5">
            <div className="space-y-2">
              {batchRuns.length === 0 && (
                <div className="text-xs text-slate-500">No batch has been run yet. Estimates appear after the first one.</div>
              )}
              {batchRuns.map((br) => (
                <div
                  key={br.id}
                  className="p-3 rounded-xl bg-slate-950 border border-slate-800 flex items-center justify-between gap-2"
                >
                  <div>
                    <div className="text-xs font-bold font-mono text-white">{br.id}</div>
                    <div className="text-xs text-slate-400 mt-0.5">
                      {br.completed_cases} / {br.total_cases} completed
                      {br.failed_cases > 0 && <span className="text-rose-300"> · {br.failed_cases} failed</span>} •{' '}
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
        </details>
      </aside>

      {confirmRun && (
        <div className="fixed inset-0 z-50 bg-black/75 backdrop-blur-sm flex items-center justify-center p-4">
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="batch-confirm-title"
            className="bg-slate-900 border border-slate-700 rounded-2xl max-w-lg w-full p-6 space-y-4"
          >
            <h3 id="batch-confirm-title" className="text-base font-bold text-white">
              Start {cases.length} batch cases?
            </h3>
            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-xs">
              <dt className="text-slate-400">Estimated duration</dt>
              <dd className="text-slate-100 font-semibold">
                {durationSummary(totals)}
                {totals.asyncCount > 0 && (
                  <span className="font-normal text-slate-400"> ({totals.asyncCount} async case(s) run in the background)</span>
                )}
              </dd>
              <dt className="text-slate-400">QPU workload</dt>
              <dd className="text-slate-100 font-semibold">{qpuLine || 'none (no remote hardware cases)'}</dd>
            </dl>
            {remoteCases.length > 0 && (
              <p className="text-xs text-slate-300 leading-relaxed">
                <strong className="text-white">{remoteCases.length}</strong>{' '}
                {remoteCases.length === 1 ? 'case runs' : 'cases run'} on real quantum hardware and will use QPU time on
                your D-Wave Leap / QLM account.
              </p>
            )}
            {overLimitCases.length > 0 && (
              <p className="text-xs text-amber-200 leading-relaxed">
                <AlertTriangle className="w-3.5 h-3.5 inline -mt-0.5 mr-1 text-amber-400" />
                <strong>{overLimitCases.length}</strong>{' '}
                {overLimitCases.length === 1 ? 'case exceeds' : 'cases exceed'} the backend capacity and will likely fail:{' '}
                {overLimitCases
                  .slice(0, 4)
                  .map((c) => c.case_key)
                  .join(', ')}
                {overLimitCases.length > 4 ? ` and ${overLimitCases.length - 4} more` : ''}.
              </p>
            )}
            <div className="flex justify-end gap-2 pt-2">
              <button onClick={() => setConfirmRun(false)} className="px-4 py-2 rounded-lg text-xs text-slate-300 hover:bg-slate-800">
                Cancel
              </button>
              <button
                onClick={startBatch}
                className="px-4 py-2 rounded-lg text-xs font-semibold bg-indigo-600 text-white hover:bg-indigo-500"
              >
                {overLimitCases.length > 0 ? 'Run anyway' : 'Run batch'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
