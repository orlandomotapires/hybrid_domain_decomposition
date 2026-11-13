import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle,
  Check,
  FlaskConical,
  Lightbulb,
  Loader2,
  Play,
  RefreshCw,
  Sparkles,
  Square,
  Trash2,
  Wand2,
} from 'lucide-react';
import { api } from '../api/client';
import { Demonstrator, SimulationJob } from '../types/pipeline';
import {
  AutoSelectResult,
  ObjectiveKey,
  SearchSpace,
  StudyBrief,
  StudyDetail,
  StudyTrial,
  TunableParameterMeta,
  TuningDefaults,
  TuningMeta,
} from '../types/tuning';
import { methodLabel } from '../lib/labels';
import { useToast } from './Toasts';
import { ConvergenceChart, ParetoChart } from './tuning/TuningCharts';

interface TuningStudioProps {
  demonstrators: Demonstrator[];
  selectedDemId: string;
  hasUnsavedChanges: boolean;
  jobs: SimulationJob[];
  onSelectDemonstrator: (dem: Demonstrator) => void;
  /** Reload the simulation after parameters were written by the tuner. */
  onParametersApplied: () => void;
  onOpenJob: (jobId: string) => void;
  onRefreshJobs: () => void;
}

type Mode = 'auto' | 'iterative' | 'studies';

const card = 'bg-slate-900/80 border border-slate-800 rounded-2xl p-5 space-y-3 min-w-0';
const inputBase =
  'bg-slate-950 border border-slate-700 rounded-lg px-2 py-1 text-xs text-slate-100 focus:outline-none focus:border-indigo-500';
const input = `${inputBase} w-full`;
const btn =
  'inline-flex items-center gap-1.5 rounded-xl font-bold text-xs px-3 py-2 transition disabled:opacity-50 disabled:cursor-not-allowed';
const btnPrimary = `${btn} bg-indigo-600 hover:bg-indigo-500 text-white`;
const btnGhost = `${btn} bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700`;

const GROUP_LABELS: Record<string, string> = {
  partitioning: 'Partitioning',
  coarsening: 'Coarsening',
  uncoarsening: 'Uncoarsening / refinement',
  quantum_annealing: 'Quantum annealing',
  qaoa: 'QAOA',
};
const HIGHLIGHTED = ['k_target', 'partitioning_strategy'];
const STRATEGY_LABEL: Record<string, string> = {
  metis_partitioning: 'METIS',
  quantum_annealing: 'Quantum annealing',
  quantum_approximation_optimizer: 'QAOA',
};

function fmt(v: number | null | undefined, digits = 4): string {
  if (v == null || !isFinite(v)) return '–';
  const a = Math.abs(v);
  if (a !== 0 && (a >= 1e5 || a < 1e-3)) return v.toExponential(2);
  return Number(v.toPrecision(digits)).toString();
}

/* ------------------------------------------------------------------ */
/* Matrix features                                                     */
/* ------------------------------------------------------------------ */

const FeaturesPanel: React.FC<{ defaults: TuningDefaults | null; loading: boolean }> = ({ defaults, loading }) => {
  if (loading && !defaults) {
    return <div className={card}><Loader2 className="w-4 h-4 animate-spin text-slate-400" /></div>;
  }
  if (!defaults) return null;
  const f = defaults.features;
  const items: Array<[string, string]> = [
    ['Rows (n)', f.matrix.n.toLocaleString()],
    ['Nonzeros', f.matrix.nnz.toLocaleString()],
    ['nnz / row', fmt(f.matrix.nnz_per_row, 3)],
    ['Bandwidth', `${f.matrix.bandwidth} (${fmt(f.matrix.relative_bandwidth * 100, 3)}% of n)`],
    ['Symmetric', f.matrix.numeric_symmetric ? 'yes' : f.matrix.pattern_symmetric ? 'pattern only' : 'no'],
    ['Diag. dominant rows', `${fmt(f.matrix.diag_dominant_fraction * 100, 3)}%`],
    [`Graph nodes (dof=${f.dof_per_node})`, f.graph.nodes.toLocaleString()],
    ['Graph edges', f.graph.edges.toLocaleString()],
    ['Degree mean / max', `${fmt(f.graph.degree_mean, 3)} / ${f.graph.degree_max}`],
    ['Components', String(f.graph.connected_components)],
  ];
  return (
    <section className={card}>
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-bold text-white">Matrix features</h3>
        <span className="text-[11px] font-mono text-slate-400">{defaults.matrix_id}</span>
      </div>
      <dl className="grid grid-cols-2 gap-x-3 gap-y-1.5 text-[11px]">
        {items.map(([k, v]) => (
          <React.Fragment key={k}>
            <dt className="text-slate-400">{k}</dt>
            <dd className="text-slate-100 font-mono text-right truncate" title={v}>{v}</dd>
          </React.Fragment>
        ))}
      </dl>
    </section>
  );
};

/* ------------------------------------------------------------------ */
/* Mode A: auto-select                                                 */
/* ------------------------------------------------------------------ */

const AutoPanel: React.FC<{
  simulation: string;
  hasUnsavedChanges: boolean;
  onApplied: () => void;
}> = ({ simulation, hasUnsavedChanges, onApplied }) => {
  const toast = useToast();
  const [result, setResult] = useState<AutoSelectResult | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => setResult(null), [simulation]);

  const run = async (apply: boolean) => {
    setBusy(true);
    try {
      const res = await api.autoSelectParameters(simulation, null, apply);
      setResult(res);
      if (apply && res.applied) {
        toast.success('Auto-selected parameters saved to the simulation');
        onApplied();
      }
    } catch (err: any) {
      toast.error(`Auto-select failed: ${err.message}`);
    } finally {
      setBusy(false);
    }
  };

  const cp = result?.parameters.coarsening_parameters;
  return (
    <section className={card}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1 max-w-2xl">
          <h3 className="text-sm font-bold text-white flex items-center gap-2"><Wand2 className="w-4 h-4" /> Automatic selection</h3>
          <p className="text-xs text-slate-400 leading-relaxed">
            Rules from the matrix features pick a coarse-graph target size (METIS-style, or the quantum backend
            capacity), then a grid of coarsening settings is dry-run with the real coarsening code and the one closest to
            the target with the most even supernode weights wins. k and the partitioning strategy stay as configured.
          </p>
        </div>
        <div className="flex gap-2">
          <button type="button" className={btnGhost} disabled={busy} onClick={() => run(false)}>
            {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Sparkles className="w-3.5 h-3.5" />} Preview
          </button>
          <button type="button" className={btnPrimary} disabled={busy || !result?.feasible} onClick={() => run(true)}
            title={hasUnsavedChanges ? 'Unsaved Single Run edits will be replaced' : undefined}>
            <Check className="w-3.5 h-3.5" /> Apply to simulation
          </button>
        </div>
      </div>
      {hasUnsavedChanges && (
        <p className="text-[11px] text-amber-300 flex items-center gap-1.5">
          <AlertTriangle className="w-3.5 h-3.5" /> Auto-select uses the saved parameters; unsaved Single Run edits are ignored.
        </p>
      )}
      {result && (
        <div className="space-y-3">
          <div className={`text-xs font-bold flex items-center gap-1.5 ${result.feasible ? 'text-emerald-300' : 'text-rose-300'}`}>
            {result.feasible ? <Check className="w-3.5 h-3.5" /> : <AlertTriangle className="w-3.5 h-3.5" />}
            {result.feasible
              ? `Feasible: ${result.dry_run.coarse_nodes} coarse nodes in ${result.dry_run.levels} levels`
              : `Not feasible: ${result.reasons.join('; ')}`}
          </div>
          <ol className="list-decimal list-inside space-y-1 text-xs text-slate-300">
            {result.rationale.map((r, i) => <li key={i}>{r}</li>)}
          </ol>
          {cp && (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-[11px]">
              {[
                ['Range', `[${cp.coarsen_inferior_limit}, ${cp.coarsen_superior_limit ?? '–'}]`],
                ['Strategy', String(cp.strategy)],
                ['Ratio', String(cp.coarsen_ratio)],
                ['Max levels', String(cp.max_levels)],
              ].map(([k, v]) => (
                <div key={k} className="bg-slate-950/70 border border-slate-800 rounded-xl p-2">
                  <div className="text-slate-500">{k}</div>
                  <div className="font-mono text-slate-100">{v}</div>
                </div>
              ))}
            </div>
          )}
          <details className="text-[11px] text-slate-400">
            <summary className="cursor-pointer">{result.candidates.length} dry-run candidates</summary>
            <table className="w-full mt-2 font-mono">
              <thead className="text-slate-500"><tr><th className="text-left">strategy</th><th>ratio</th><th>target</th><th>coarse</th><th>levels</th><th className="text-left">status</th></tr></thead>
              <tbody>
                {result.candidates.map((c, i) => (
                  <tr key={i} className="border-t border-slate-800">
                    <td>{c.strategy}</td><td className="text-center">{c.coarsen_ratio}</td><td className="text-center">{c.coarse_target}</td>
                    <td className="text-center">{c.dry_run.coarse_nodes ?? '–'}</td><td className="text-center">{c.dry_run.levels ?? '–'}</td>
                    <td className={c.feasible ? 'text-emerald-400' : 'text-rose-400'} title={c.reasons.join('\n')}>{c.feasible ? 'ok' : 'infeasible'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </details>
        </div>
      )}
    </section>
  );
};

/* ------------------------------------------------------------------ */
/* Mode B: study form                                                  */
/* ------------------------------------------------------------------ */

const ParamRow: React.FC<{
  spec: TunableParameterMeta;
  entry: SearchSpace[string];
  fixedValue: unknown;
  onChange: (e: SearchSpace[string]) => void;
}> = ({ spec, entry, fixedValue, onChange }) => {
  const num = (v: string) => (spec.type === 'int' ? parseInt(v, 10) : parseFloat(v));
  return (
    <div className="grid grid-cols-[minmax(0,1fr)_auto] sm:grid-cols-[minmax(0,14rem)_5.5rem_minmax(0,1fr)] gap-2 items-center py-1.5 border-t border-slate-800/70">
      <span className="text-xs text-slate-200 truncate" title={spec.key}>{spec.label}</span>
      <label className="inline-flex items-center gap-1.5 text-[11px] text-slate-300 cursor-pointer select-none">
        <input type="checkbox" checked={entry.free} onChange={(e) => onChange({ ...entry, free: e.target.checked })}
          className="accent-indigo-500" />
        {entry.free ? 'free' : 'fixed'}
      </label>
      <div className="col-span-2 sm:col-span-1 min-w-0">
        {!entry.free ? (
          <span className="text-[11px] font-mono text-slate-400">
            {fixedValue == null ? 'default' : spec.key === 'partitioning_strategy' ? STRATEGY_LABEL[String(fixedValue)] : String(fixedValue)}
          </span>
        ) : spec.type === 'categorical' ? (
          <div className="flex flex-wrap gap-x-3 gap-y-1">
            {(spec.choices || []).map((c) => {
              const on = (entry.choices || []).includes(c);
              return (
                <label key={c} className="inline-flex items-center gap-1 text-[11px] text-slate-300 cursor-pointer">
                  <input type="checkbox" className="accent-indigo-500" checked={on}
                    onChange={() => {
                      const next = on ? (entry.choices || []).filter((x) => x !== c) : [...(entry.choices || []), c];
                      if (next.length) onChange({ ...entry, choices: next });
                    }} />
                  {STRATEGY_LABEL[c] || c}
                </label>
              );
            })}
          </div>
        ) : (
          <div className="flex items-center gap-1.5">
            <input type="number" className={input} value={entry.low ?? ''} step={spec.type === 'int' ? 1 : 'any'}
              onChange={(e) => onChange({ ...entry, low: num(e.target.value) })} aria-label={`${spec.label} minimum`} />
            <span className="text-slate-500 text-[11px]">to</span>
            <input type="number" className={input} value={entry.high ?? ''} step={spec.type === 'int' ? 1 : 'any'}
              onChange={(e) => onChange({ ...entry, high: num(e.target.value) })} aria-label={`${spec.label} maximum`} />
            {entry.log && <span className="text-[10px] text-slate-500">log</span>}
          </div>
        )}
      </div>
    </div>
  );
};

function fixedValueOf(key: string, params: any): unknown {
  const cp = params?.coarsening_parameters || {};
  const pp = params?.partitioning_parameters || {};
  const up = params?.uncoarsening_parameters || {};
  switch (key) {
    case 'partitioning_strategy': return pp.partitioning_strategy;
    case 'k_target': return pp.common?.k_target;
    case 'balance_tolerance': return pp.common?.balance_tolerance;
    case 'coarse_target': return cp.coarsen_superior_limit ?? cp.coarsen_inferior_limit;
    case 'coarse_window': {
      const sup = cp.coarsen_superior_limit ?? cp.coarsen_inferior_limit;
      return sup ? Number((1 - cp.coarsen_inferior_limit / sup).toFixed(3)) : null;
    }
    case 'coarsening_strategy': return cp.strategy;
    case 'coarsen_ratio': return cp.coarsen_ratio;
    case 'max_levels': return cp.max_levels;
    case 'refine_objective': return up.refine_objective;
    case 'refine_balance_lambda': return up.refine_balance_lambda;
    case 'refine_max_passes_per_level': return up.refine_max_passes_per_level;
    default: {
      const [prefix, name] = key.split('.');
      const strat = prefix === 'qa' ? 'quantum_annealing' : 'quantum_approximation_optimizer';
      return pp.strategies?.[strat]?.[name];
    }
  }
}

const StudyForm: React.FC<{
  simulation: string;
  meta: TuningMeta;
  defaults: TuningDefaults;
  onCreated: (study: StudyBrief, jobId: string | null) => void;
}> = ({ simulation, meta, defaults, onCreated }) => {
  const toast = useToast();
  const [objectives, setObjectives] = useState<ObjectiveKey[]>(['edge_cut', 'imbalance']);
  const [aggregation, setAggregation] = useState<'pareto' | 'weighted'>('pareto');
  const [weights, setWeights] = useState<Record<string, number>>({});
  const [bandPercent, setBandPercent] = useState(1.0);
  const [sampler, setSampler] = useState('auto');
  const [nTrials, setNTrials] = useState(30);
  const [repeats, setRepeats] = useState(1);
  const [timeoutMin, setTimeoutMin] = useState<string>('');
  const [patience, setPatience] = useState<string>('');
  const [space, setSpace] = useState<SearchSpace>(defaults.search_space);
  const [warm, setWarm] = useState({ base: true, auto: true, history: true });
  const [busy, setBusy] = useState(false);

  useEffect(() => setSpace(defaults.search_space), [defaults]);

  const multi = objectives.length > 1;
  const strategyEntry = space.partitioning_strategy;
  const baseStrategy = String(fixedValueOf('partitioning_strategy', defaults.parameters));
  const activeStrategies = new Set(strategyEntry?.free ? strategyEntry.choices || [] : [baseStrategy]);
  const groups = useMemo(() => {
    const g: Record<string, TunableParameterMeta[]> = {};
    for (const p of meta.parameters) {
      if (HIGHLIGHTED.includes(p.key)) continue;
      if (p.when && !activeStrategies.has(p.when)) continue;
      (g[p.group] ||= []).push(p);
    }
    return g;
  }, [meta, strategyEntry?.free, (strategyEntry?.choices || []).join(','), baseStrategy]);

  const toggleObjective = (k: ObjectiveKey) =>
    setObjectives((prev) => (prev.includes(k) ? (prev.length > 1 ? prev.filter((o) => o !== k) : prev) : [...prev, k]));

  const submit = async (start: boolean) => {
    setBusy(true);
    try {
      const res = await api.createStudy({
        simulation,
        objectives,
        aggregation: multi ? aggregation : 'weighted',
        weights: multi && aggregation === 'weighted' ? Object.fromEntries(objectives.map((o) => [o, weights[o] ?? 1])) : undefined,
        band_percent: bandPercent,
        sampler,
        n_trials: nTrials,
        repeats,
        timeout_sec: timeoutMin ? parseFloat(timeoutMin) * 60 : null,
        patience: patience ? parseInt(patience, 10) : null,
        search_space: space,
        warm_start: warm,
        start,
      });
      toast.success(start ? `Study ${res.study.id} started` : `Study ${res.study.id} created for manual suggestions`);
      onCreated(res.study, res.job?.job_id || null);
    } catch (err: any) {
      toast.error(`Could not create the study: ${err.message}`);
    } finally {
      setBusy(false);
    }
  };

  const specByKey = Object.fromEntries(meta.parameters.map((p) => [p.key, p]));
  const samplerOptions = meta.samplers.filter((s) => !(s.key === 'cmaes' && multi && aggregation === 'pareto'));

  return (
    <div className="space-y-4">
      <section className={card}>
        <h3 className="text-sm font-bold text-white">1 · Objectives</h3>
        <p className="text-xs text-slate-400">Tick one or more metrics to minimise.</p>
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-2">
          {meta.objectives.map((o) => {
            const on = objectives.includes(o.key);
            return (
              <label key={o.key} className={`flex gap-2 p-2.5 rounded-xl border cursor-pointer transition ${on ? 'border-indigo-500 bg-indigo-950/40' : 'border-slate-800 bg-slate-950/50 hover:border-slate-700'}`}>
                <input type="checkbox" className="accent-indigo-500 mt-0.5" checked={on} onChange={() => toggleObjective(o.key)} />
                <span>
                  <span className="block text-xs font-bold text-slate-100">{o.label}</span>
                  <span className="block text-[11px] text-slate-400 leading-snug">{o.description}</span>
                </span>
              </label>
            );
          })}
        </div>
        {objectives.includes('band_quality') && (
          <label className="flex items-center gap-2 text-xs text-slate-300 max-w-xs">
            Band width X (% of n)
            <input type="number" min={0.05} max={4.95} step={0.05} className={input} value={bandPercent}
              onChange={(e) => setBandPercent(parseFloat(e.target.value))} />
          </label>
        )}
        {multi && (
          <div className="space-y-2">
            <div className="flex flex-wrap gap-4 text-xs text-slate-300">
              <label className="inline-flex items-center gap-1.5 cursor-pointer">
                <input type="radio" className="accent-indigo-500" checked={aggregation === 'pareto'} onChange={() => setAggregation('pareto')} />
                Pareto front (multi-objective)
              </label>
              <label className="inline-flex items-center gap-1.5 cursor-pointer">
                <input type="radio" className="accent-indigo-500" checked={aggregation === 'weighted'} onChange={() => setAggregation('weighted')} />
                Weighted sum (normalised by the first successful trial)
              </label>
            </div>
            {aggregation === 'weighted' && (
              <div className="flex flex-wrap gap-3">
                {objectives.map((o) => (
                  <label key={o} className="flex items-center gap-1.5 text-[11px] text-slate-300">
                    {meta.objectives.find((m) => m.key === o)?.label}
                    <input type="number" min={0} step={0.1} className={`${inputBase} w-20`} value={weights[o] ?? 1}
                      onChange={(e) => setWeights({ ...weights, [o]: parseFloat(e.target.value) })} />
                  </label>
                ))}
              </div>
            )}
          </div>
        )}
      </section>

      <section className={card}>
        <h3 className="text-sm font-bold text-white">2 · Fixed or free for the tuner</h3>
        <p className="text-xs text-slate-400">Fixed keeps the simulation's value; free lets the optimizer choose within the range.</p>
        <div className="rounded-xl border border-indigo-900/60 bg-indigo-950/20 px-3 pb-1">
          {HIGHLIGHTED.map((k) => specByKey[k] && (
            <ParamRow key={k} spec={specByKey[k]} entry={space[k]} fixedValue={fixedValueOf(k, defaults.parameters)}
              onChange={(e) => setSpace({ ...space, [k]: e })} />
          ))}
        </div>
        {Object.entries(groups).map(([group, specs]) => (
          <details key={group} open={group !== 'quantum_annealing' && group !== 'qaoa' ? true : undefined} className="group">
            <summary className="cursor-pointer text-xs font-bold text-slate-300 py-1">
              {GROUP_LABELS[group] || group}
              <span className="ml-2 font-normal text-slate-500">{specs.filter((s) => space[s.key]?.free).length} free</span>
            </summary>
            <div>
              {specs.map((s) => (
                <ParamRow key={s.key} spec={s} entry={space[s.key]} fixedValue={fixedValueOf(s.key, defaults.parameters)}
                  onChange={(e) => setSpace({ ...space, [s.key]: e })} />
              ))}
            </div>
          </details>
        ))}
      </section>

      <section className={card}>
        <h3 className="text-sm font-bold text-white">3 · Optimizer and budget</h3>
        <div className="grid sm:grid-cols-2 lg:grid-cols-5 gap-3 text-xs text-slate-300">
          <label className="space-y-1 lg:col-span-2">
            <span>Algorithm</span>
            <select className={input} value={sampler} onChange={(e) => setSampler(e.target.value)}>
              {samplerOptions.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
            </select>
            <span className="block text-[11px] text-slate-500">{meta.samplers.find((s) => s.key === sampler)?.description}</span>
          </label>
          <label className="space-y-1"><span>Trials</span>
            <input type="number" min={1} className={input} value={nTrials} onChange={(e) => setNTrials(parseInt(e.target.value, 10) || 1)} /></label>
          <label className="space-y-1"><span>Repeats per trial (seeds)</span>
            <input type="number" min={1} className={input} value={repeats} onChange={(e) => setRepeats(parseInt(e.target.value, 10) || 1)} /></label>
          <label className="space-y-1"><span>Time limit (min)</span>
            <input type="number" min={0} className={input} value={timeoutMin} placeholder="none" onChange={(e) => setTimeoutMin(e.target.value)} /></label>
          {!(multi && aggregation === 'pareto') && (
            <label className="space-y-1"><span>Stop after N trials w/o improvement</span>
              <input type="number" min={1} className={input} value={patience} placeholder="off" onChange={(e) => setPatience(e.target.value)} /></label>
          )}
        </div>
        <div className="flex flex-wrap gap-4 text-xs text-slate-300">
          <span className="text-slate-500">Warm start:</span>
          {([['base', 'current parameters'], ['auto', 'auto-selected parameters'], ['history', 'previous runs of this matrix']] as const).map(([k, label]) => (
            <label key={k} className="inline-flex items-center gap-1.5 cursor-pointer">
              <input type="checkbox" className="accent-indigo-500" checked={warm[k]} onChange={(e) => setWarm({ ...warm, [k]: e.target.checked })} />
              {label}
            </label>
          ))}
        </div>
        <div className="flex flex-wrap gap-2 pt-1">
          <button type="button" className={btnPrimary} disabled={busy} onClick={() => submit(true)}>
            {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5 fill-current" />} Start study
          </button>
          <button type="button" className={btnGhost} disabled={busy} onClick={() => submit(false)}
            title="Create the study without running it; ask it for one suggestion at a time and run it yourself">
            <Lightbulb className="w-3.5 h-3.5" /> Create for manual suggestions
          </button>
        </div>
      </section>
    </div>
  );
};

/* ------------------------------------------------------------------ */
/* Studies                                                             */
/* ------------------------------------------------------------------ */

function trialSummary(t: StudyTrial): string {
  const pp: any = t.parameters?.partitioning_parameters || {};
  const cp: any = t.parameters?.coarsening_parameters || {};
  const parts = [
    STRATEGY_LABEL[pp.partitioning_strategy] || pp.partitioning_strategy,
    `k=${pp.common?.k_target}`,
    `[${cp.coarsen_inferior_limit}, ${cp.coarsen_superior_limit}]`,
    cp.strategy,
  ];
  return parts.filter(Boolean).join(' · ');
}

const StudyView: React.FC<{
  simulation: string;
  studyId: string;
  meta: TuningMeta;
  jobs: SimulationJob[];
  onApplied: () => void;
  onOpenJob: (jobId: string) => void;
  onRefreshJobs: () => void;
  onDeleted: () => void;
}> = ({ simulation, studyId, meta, jobs, onApplied, onOpenJob, onRefreshJobs, onDeleted }) => {
  const toast = useToast();
  const [study, setStudy] = useState<StudyDetail | null>(null);
  const [selectedTrial, setSelectedTrial] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [extraTrials, setExtraTrials] = useState(20);

  const load = useCallback(async () => {
    try {
      setStudy(await api.getStudy(simulation, studyId));
    } catch (err: any) {
      toast.error(`Could not load study: ${err.message}`);
    }
  }, [simulation, studyId]);

  const job = study?.running_job_id ? jobs.find((j) => j.job_id === study.running_job_id) : undefined;
  const running = !!study?.running_job_id && (!job || job.status === 'running');

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    if (!running) return;
    const t = window.setInterval(load, 2000);
    return () => window.clearInterval(t);
  }, [running, load]);

  const act = async (label: string, fn: () => Promise<unknown>, after?: () => void) => {
    setBusy(true);
    try {
      await fn();
      after?.();
      await load();
    } catch (err: any) {
      toast.error(`${label} failed: ${err.message}`);
    } finally {
      setBusy(false);
    }
  };

  if (!study) return <div className={card}><Loader2 className="w-4 h-4 animate-spin text-slate-400" /></div>;

  const s = study.summary || {};
  const labels = Object.fromEntries(meta.objectives.map((o) => [o.key, o.label]));
  const pct = s.n_trials ? Math.round(((s.trials_done || 0) / s.n_trials) * 100) : 0;
  const pendingNumbers = Object.keys(study.pending || {}).map(Number);
  const chosen = study.trials.find((t) => t.number === (selectedTrial ?? s.best_trial));
  const front = new Set(s.pareto_front || []);

  return (
    <div className="space-y-4">
      <section className={card}>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h3 className="text-sm font-bold text-white font-mono">{study.id}</h3>
            <p className="text-[11px] text-slate-400">
              {study.objectives.map((o) => labels[o] || o).join(', ')} · {study.objectives.length > 1 ? study.aggregation : 'single objective'} ·
              sampler {study.sampler} · free: {study.free_parameters.join(', ') || 'none'}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            {running ? (
              <>
                {study.running_job_id && (
                  <button type="button" className={btnGhost} onClick={() => onOpenJob(study.running_job_id!)}>Logs</button>
                )}
                <button type="button" className={btnGhost} disabled={busy}
                  onClick={() => act('Stop', () => api.stopStudy(simulation, studyId), () => toast.info('Stopping after the current trial'))}>
                  <Square className="w-3.5 h-3.5" /> Stop
                </button>
              </>
            ) : (
              <>
                <span className="inline-flex items-center gap-1">
                  <input type="number" min={1} className={`${inputBase} w-16`} value={extraTrials}
                    onChange={(e) => setExtraTrials(parseInt(e.target.value, 10) || 1)} aria-label="Additional trials" />
                  <button type="button" className={btnGhost} disabled={busy}
                    onClick={() => act('Resume', () => api.resumeStudy(simulation, studyId, (s.trials_done || 0) + extraTrials), onRefreshJobs)}>
                    <RefreshCw className="w-3.5 h-3.5" /> Run more trials
                  </button>
                </span>
                <button type="button" className={btnGhost} disabled={busy}
                  onClick={() => act('Suggest', () => api.suggestNext(simulation, studyId, true), () => {
                    toast.success('Suggested parameters saved to the simulation. Run it in Single Run, then report it here.');
                    onApplied();
                  })}>
                  <Lightbulb className="w-3.5 h-3.5" /> Suggest next
                </button>
                <button type="button" className={`${btn} text-rose-300 hover:bg-rose-950/40`} disabled={busy}
                  onClick={() => { if (window.confirm(`Delete study ${studyId} and its trial runs?`)) act('Delete', () => api.deleteStudy(simulation, studyId), onDeleted); }}>
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </>
            )}
          </div>
        </div>

        <div className="space-y-1">
          <div className="flex justify-between text-[11px] text-slate-400">
            <span>{s.trials_done || 0} / {s.n_trials} trials · {s.trials_ok || 0} ok · {s.trials_infeasible || 0} infeasible · {s.trials_error || 0} errors</span>
            <span>{running ? 'running' : s.stop_reason || s.state}</span>
          </div>
          <div className="h-1.5 rounded-full bg-slate-800 overflow-hidden">
            <div className="h-full bg-indigo-500 transition-all" style={{ width: `${pct}%` }} />
          </div>
        </div>

        {pendingNumbers.length > 0 && (
          <div className="rounded-xl border border-amber-700/50 bg-amber-950/20 p-3 text-xs text-amber-200 space-y-2">
            <p>Pending suggestion(s): {pendingNumbers.map((n) => `#${n}`).join(', ')}. Run the simulation, then report the newest run.</p>
            <div className="flex gap-2">
              {pendingNumbers.map((n) => (
                <button key={n} type="button" className={btnGhost} disabled={busy}
                  onClick={() => act('Report', () => api.reportRun(simulation, studyId, n), () => toast.success(`Trial #${n} scored`))}>
                  Report latest run for #{n}
                </button>
              ))}
            </div>
          </div>
        )}
      </section>

      <section className={card}>
        <h3 className="text-sm font-bold text-white">{s.multi_objective ? 'Pareto front' : 'Convergence'}</h3>
        {s.multi_objective ? (
          <ParetoChart trials={study.trials} objectives={study.objectives} labels={labels}
            front={s.pareto_front || []} best={s.best_trial} onSelect={setSelectedTrial} />
        ) : (
          <ConvergenceChart trials={study.trials} onSelect={setSelectedTrial} />
        )}
      </section>

      {chosen && (
        <section className={card}>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className="text-sm font-bold text-white">
              Trial #{chosen.number} {chosen.number === s.best_trial && <span className="text-indigo-300">· {s.multi_objective ? 'knee of the front' : 'best'}</span>}
            </h3>
            <button type="button" className={btnPrimary} disabled={busy || chosen.status !== 'ok'}
              onClick={() => act('Apply', () => api.applyStudyParameters(simulation, studyId, chosen.number), () => {
                toast.success(`Trial #${chosen.number} parameters saved to ${simulation}`);
                onApplied();
              })}>
              <Check className="w-3.5 h-3.5" /> Apply to simulation
            </button>
          </div>
          <p className="text-[11px] text-slate-400">{trialSummary(chosen)}</p>
          {chosen.values && (
            <div className="flex flex-wrap gap-2">
              {Object.entries(chosen.values).map(([k, v]) => (
                <div key={k} className="bg-slate-950/70 border border-slate-800 rounded-xl px-3 py-2">
                  <div className="text-[10px] text-slate-500">{labels[k] || k}</div>
                  <div className="text-sm font-mono text-slate-100">{fmt(v)}</div>
                </div>
              ))}
            </div>
          )}
          <details className="text-[11px]">
            <summary className="cursor-pointer text-slate-400">Suggested values</summary>
            <pre className="mt-2 bg-slate-950/70 rounded-xl p-3 text-slate-300 overflow-x-auto">{JSON.stringify(chosen.suggested, null, 2)}</pre>
          </details>
        </section>
      )}

      <section className={card}>
        <h3 className="text-sm font-bold text-white">Trials</h3>
        <div className="overflow-x-auto">
          <table className="w-full text-[11px]">
            <thead className="text-slate-500 text-left">
              <tr>
                <th className="py-1 pr-2">#</th><th className="pr-2">status</th>
                {study.objectives.map((o) => <th key={o} className="pr-2 text-right">{labels[o] || o}</th>)}
                {!s.multi_objective && study.objectives.length > 1 && <th className="pr-2 text-right">score</th>}
                <th className="pr-2">parameters</th><th className="text-right">time</th>
              </tr>
            </thead>
            <tbody>
              {[...study.trials].reverse().map((t) => (
                <tr key={t.number} onClick={() => setSelectedTrial(t.number)}
                  className={`border-t border-slate-800 cursor-pointer hover:bg-slate-800/40 ${t.number === chosen?.number ? 'bg-indigo-950/40' : ''}`}>
                  <td className="py-1 pr-2 font-mono text-slate-300">
                    {t.number}{t.number === s.best_trial ? ' ★' : front.has(t.number) ? ' ◆' : ''}{t.manual ? ' (manual)' : ''}
                  </td>
                  <td className={`pr-2 ${t.status === 'ok' ? 'text-emerald-400' : t.status === 'infeasible' ? 'text-amber-400' : 'text-rose-400'}`}
                    title={t.reasons.join('\n')}>{t.status}</td>
                  {study.objectives.map((o) => <td key={o} className="pr-2 text-right font-mono text-slate-200">{fmt(t.values?.[o])}</td>)}
                  {!s.multi_objective && study.objectives.length > 1 && <td className="pr-2 text-right font-mono text-slate-200">{fmt(t.score)}</td>}
                  <td className="pr-2 text-slate-400 truncate max-w-[22rem]" title={t.reasons.join('\n')}>{trialSummary(t)}</td>
                  <td className="text-right text-slate-500">{t.duration_sec != null ? `${fmt(t.duration_sec, 3)}s` : ''}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="text-[10px] text-slate-500">★ best / knee · ◆ Pareto front · hover a status to see why a trial failed</p>
      </section>
    </div>
  );
};

/* ------------------------------------------------------------------ */
/* Root                                                                */
/* ------------------------------------------------------------------ */

export const TuningStudio: React.FC<TuningStudioProps> = ({
  demonstrators,
  selectedDemId,
  hasUnsavedChanges,
  jobs,
  onSelectDemonstrator,
  onParametersApplied,
  onOpenJob,
  onRefreshJobs,
}) => {
  const toast = useToast();
  // Optional deep link: #/tuning?tmode=studies&study=study_...
  const initialLink = useMemo(() => {
    const q = new URLSearchParams(window.location.hash.split('?')[1] || '');
    const m = q.get('tmode');
    return { mode: (m === 'iterative' || m === 'studies' ? m : 'auto') as Mode, study: q.get('study') };
  }, []);
  const [mode, setMode] = useState<Mode>(initialLink.mode);
  const [meta, setMeta] = useState<TuningMeta | null>(null);
  const [defaults, setDefaults] = useState<TuningDefaults | null>(null);
  const [loadingDefaults, setLoadingDefaults] = useState(false);
  const [studies, setStudies] = useState<StudyBrief[]>([]);
  const [selectedStudy, setSelectedStudy] = useState<string | null>(initialLink.study);
  const firstLoad = React.useRef(true);

  useEffect(() => {
    api.getTuningMeta().then(setMeta).catch((err) => toast.error(`Tuning metadata: ${err.message}`));
  }, []);

  const loadDefaults = useCallback(async () => {
    setLoadingDefaults(true);
    try {
      setDefaults(await api.getTuningDefaults(selectedDemId));
    } catch (err: any) {
      setDefaults(null);
      toast.error(`Could not read ${selectedDemId}: ${err.message}`);
    } finally {
      setLoadingDefaults(false);
    }
  }, [selectedDemId]);

  const loadStudies = useCallback(async () => {
    try {
      setStudies(await api.listStudies(selectedDemId));
    } catch {
      setStudies([]);
    }
  }, [selectedDemId]);

  useEffect(() => {
    if (!firstLoad.current) setSelectedStudy(null);
    firstLoad.current = false;
    loadDefaults();
    loadStudies();
  }, [selectedDemId]);

  // Refresh the list when a tuning job finishes.
  const tuningRunning = jobs.filter((j) => j.job_type === 'tuning' && j.status === 'running').length;
  useEffect(() => { loadStudies(); }, [tuningRunning]);

  const applied = () => {
    onParametersApplied();
    loadDefaults();
  };

  const modes: Array<{ id: Mode; label: string; icon: typeof Wand2 }> = [
    { id: 'auto', label: 'Automatic', icon: Wand2 },
    { id: 'iterative', label: 'Iterative tuning', icon: FlaskConical },
    { id: 'studies', label: `Studies (${studies.length})`, icon: RefreshCw },
  ];
  const strategy = (defaults?.parameters as any)?.partitioning_parameters?.partitioning_strategy;

  return (
    <div className="grid lg:grid-cols-[18rem_minmax(0,1fr)] gap-5">
      <aside className="space-y-4 min-w-0">
        <section className={card}>
          <label className="block space-y-1 text-xs text-slate-300">
            <span className="font-bold text-white text-sm">Simulation</span>
            <select className={input} value={selectedDemId}
              onChange={(e) => {
                const dem = demonstrators.find((d) => d.id === e.target.value);
                if (dem) onSelectDemonstrator(dem);
              }}>
              {demonstrators.map((d) => <option key={d.id} value={d.id}>{d.id}</option>)}
            </select>
          </label>
          {strategy && (
            <p className="text-[11px] text-slate-400">
              Current method: <span className="text-slate-200">{methodLabel(strategy, (defaults?.parameters as any)?.partitioning_parameters?.strategies?.[strategy]?.simulated, true)}</span>
              {' · '}k = <span className="text-slate-200">{(defaults?.parameters as any)?.partitioning_parameters?.common?.k_target}</span>
            </p>
          )}
        </section>
        <FeaturesPanel defaults={defaults} loading={loadingDefaults} />
        {studies.length > 0 && (
          <section className={card}>
            <h3 className="text-sm font-bold text-white">Studies</h3>
            <div className="space-y-1.5">
              {studies.map((st) => (
                <button key={st.id} type="button"
                  onClick={() => { setSelectedStudy(st.id); setMode('studies'); }}
                  className={`w-full text-left p-2 rounded-xl border text-[11px] transition ${selectedStudy === st.id && mode === 'studies' ? 'border-indigo-500 bg-indigo-950/40' : 'border-slate-800 bg-slate-950/50 hover:border-slate-700'}`}>
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-mono text-slate-200 truncate">{st.id.replace('study_', '')}</span>
                    {st.running_job_id ? <Loader2 className="w-3 h-3 animate-spin text-indigo-300" /> : <span className="text-slate-500">{st.summary?.trials_done || 0}/{st.n_trials}</span>}
                  </div>
                  <div className="text-slate-500 truncate">{(st.objectives || []).join(', ')}</div>
                </button>
              ))}
            </div>
          </section>
        )}
      </aside>

      <div className="space-y-4 min-w-0">
        <nav className="flex flex-wrap gap-2" aria-label="Tuning modes">
          {modes.map((m) => (
            <button key={m.id} type="button" onClick={() => setMode(m.id)}
              className={`${btn} ${mode === m.id ? 'bg-indigo-600 text-white' : 'bg-slate-900 border border-slate-800 text-slate-300 hover:border-slate-700'}`}>
              <m.icon className="w-3.5 h-3.5" /> {m.label}
            </button>
          ))}
        </nav>

        {mode === 'auto' && (
          <AutoPanel simulation={selectedDemId} hasUnsavedChanges={hasUnsavedChanges} onApplied={applied} />
        )}

        {mode === 'iterative' && meta && defaults && (
          <StudyForm simulation={selectedDemId} meta={meta} defaults={defaults}
            onCreated={(st, jobId) => {
              setSelectedStudy(st.id);
              setMode('studies');
              loadStudies();
              if (jobId) onRefreshJobs();
            }} />
        )}

        {mode === 'studies' && meta && (
          selectedStudy ? (
            <StudyView key={selectedStudy} simulation={selectedDemId} studyId={selectedStudy} meta={meta} jobs={jobs}
              onApplied={applied} onOpenJob={onOpenJob} onRefreshJobs={() => { onRefreshJobs(); loadStudies(); }}
              onDeleted={() => { setSelectedStudy(null); loadStudies(); }} />
          ) : (
            <section className={card}>
              <p className="text-xs text-slate-400">
                {studies.length ? 'Pick a study on the left.' : 'No study yet for this simulation. Create one in "Iterative tuning".'}
              </p>
            </section>
          )
        )}
      </div>
    </div>
  );
};
