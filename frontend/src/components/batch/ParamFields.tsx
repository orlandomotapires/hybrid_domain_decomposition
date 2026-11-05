import React from 'react';
import { X } from 'lucide-react';
import { COARSENING_STRATEGIES } from '../pipeline/constants';

/**
 * Editable parameter fields for the batch screen. An empty field removes the key, so the
 * backend default (src/libs/runtime/utils.py) applies; the placeholder shows that default.
 */

export type ParamKind = 'int' | 'float' | 'string' | 'bool' | 'select';

export interface ParamSpec {
  key: string;
  label: string;
  kind: ParamKind;
  /** Backend default used when the key is absent (shown as placeholder). */
  def?: number | string | boolean | null;
  min?: number;
  /** Lower bound is exclusive (e.g. learning rate > 0). */
  minExclusive?: boolean;
  step?: number;
  hint?: string;
  options?: Array<{ value: string; label: string }>;
  /** Only shown for hardware (simulated=false) or emulated (simulated=true) runs. */
  onlyWhen?: 'hardware' | 'emulated';
  /** Must be set (non-empty) when shown. */
  required?: boolean;
}

const SIMULATED: ParamSpec = { key: 'simulated', label: 'Backend', kind: 'bool', def: true };

export const STRATEGY_PARAM_SPECS: Record<string, ParamSpec[]> = {
  metis_partitioning: [],
  quantum_annealing: [
    SIMULATED,
    { key: 'num_starts', label: 'Starts', kind: 'int', def: 5, min: 1, hint: 'Independent restarts of the recursive bisection' },
    { key: 'num_reads', label: 'Reads', kind: 'int', def: 5, min: 1, hint: 'Annealing samples per QUBO' },
    { key: 'qubo_balance_lambda', label: 'QUBO balance λ', kind: 'float', def: 0.1, step: 0.1, hint: 'Weight of the balance penalty inside the QUBO' },
    { key: 'balance_violation_lambda', label: 'Violation λ', kind: 'float', def: 0.1, min: 0, step: 0.1, hint: 'Penalty for samples violating the balance tolerance' },
    { key: 'qpu_solver_name', label: 'D-Wave solver', kind: 'string', def: null, onlyWhen: 'hardware', hint: 'Leave empty for the default Leap solver' },
  ],
  quantum_approximation_optimizer: [
    SIMULATED,
    { key: 'num_starts', label: 'Starts', kind: 'int', def: 12, min: 1, hint: 'Independent restarts of the recursive bisection' },
    { key: 'circuit_depth', label: 'Depth (p)', kind: 'int', def: 12, min: 1, hint: 'QAOA layers' },
    { key: 'num_steps', label: 'Optimizer steps', kind: 'int', def: 12, min: 1 },
    { key: 'num_shots', label: 'Shots', kind: 'int', def: 5, min: 1, hint: 'Circuit samples per evaluation' },
    { key: 'qubo_balance_lambda', label: 'QUBO balance λ', kind: 'float', def: 0.1, step: 0.1 },
    { key: 'balance_violation_lambda', label: 'Violation λ', kind: 'float', def: 0.1, min: 0, step: 0.1 },
    { key: 'adam_learning_rate', label: 'Adam LR', kind: 'float', def: 0.1, min: 0, minExclusive: true, step: 0.01, onlyWhen: 'emulated' },
    { key: 'qlm_qpu_name', label: 'QLM QPU', kind: 'string', def: null, onlyWhen: 'hardware', required: true, hint: 'e.g. qat.qpus:Jiqcer5QPU' },
  ],
};

export const COMMON_PARAM_GROUPS: Array<{ group: string; title: string; specs: ParamSpec[] }> = [
  {
    group: 'partitioning_common',
    title: 'Partitioning',
    specs: [
      { key: 'k_target', label: 'Parts (k)', kind: 'int', def: 2, min: 1 },
      { key: 'balance_tolerance', label: 'Balance tol.', kind: 'float', def: 0.1, min: 0, step: 0.1 },
    ],
  },
  {
    group: 'coarsening_parameters',
    title: 'Coarsening',
    specs: [
      {
        key: 'strategy',
        label: 'Matching',
        kind: 'select',
        def: 'modified',
        options: COARSENING_STRATEGIES.map((s) => ({ value: s.key, label: s.title.replace(/\s*\(.*\)$/, '') })),
      },
      { key: 'coarsen_ratio', label: 'Ratio', kind: 'float', def: 0.99, min: 0, step: 0.01, hint: '1 disables the stop-on-slow-shrinkage check' },
      { key: 'max_levels', label: 'Max levels', kind: 'int', def: 30, min: 1 },
      { key: 'max_node_weight', label: 'Max node weight', kind: 'float', def: null, min: 0, minExclusive: true, hint: 'Empty = Auto; 1e18 = no limit' },
      { key: 'weight', label: 'Edge weight attr', kind: 'string', def: 'weight' },
    ],
  },
  {
    group: 'general_parameters',
    title: 'General',
    specs: [
      { key: 'dof_per_node', label: 'DOFs per node', kind: 'int', def: 3, min: 1 },
      { key: 'seed', label: 'Seed', kind: 'int', def: null },
    ],
  },
  {
    group: 'uncoarsening_parameters',
    title: 'Refinement',
    specs: [
      {
        key: 'refine_objective',
        label: 'KL objective',
        kind: 'select',
        def: 'cut_balance',
        options: [
          { value: 'cut_balance', label: 'Cut + balance' },
          { value: 'cut', label: 'Cut only' },
        ],
      },
      { key: 'refine_balance_lambda', label: 'KL balance λ', kind: 'float', def: 1.0, min: 0, step: 0.1 },
      { key: 'refine_max_passes_per_level', label: 'KL passes / level', kind: 'int', def: 50, min: 1 },
      { key: 'refine_max_moves_per_pass', label: 'KL moves / pass', kind: 'int', def: 5000, min: 1 },
    ],
  },
];

/** Returns an error message for a value, or null when valid / unset. */
export function validateParam(spec: ParamSpec, value: unknown): string | null {
  if (value === undefined || value === null || value === '') {
    return spec.required ? 'Required' : null;
  }
  if (spec.kind === 'int' || spec.kind === 'float') {
    const n = Number(value);
    if (!Number.isFinite(n)) return 'Not a number';
    if (spec.kind === 'int' && !Number.isInteger(n)) return 'Must be an integer';
    if (spec.min !== undefined && (spec.minExclusive ? n <= spec.min : n < spec.min)) {
      return `Must be ${spec.minExclusive ? '>' : '≥'} ${spec.min}`;
    }
  }
  return null;
}

/** Visible specs given the current simulated flag. */
export function visibleSpecs(specs: ParamSpec[], params: Record<string, any>): ParamSpec[] {
  const simulated = params.simulated ?? true;
  return specs.filter(
    (s) => !s.onlyWhen || (s.onlyWhen === 'hardware' ? simulated === false : simulated !== false)
  );
}

/** Very large numbers (e.g. max_node_weight = 1e18 meaning "no limit") shown in exponent form. */
function displayValue(value: unknown): string {
  if (value === undefined || value === null) return '';
  if (typeof value === 'number' && Math.abs(value) >= 1e12) return value.toExponential().replace('e+', 'e');
  return String(value);
}

const inputCls = (err: boolean) =>
  `w-full min-w-0 bg-slate-950 border rounded px-2 py-1 text-xs font-mono text-white placeholder:text-slate-600 focus:outline-none focus-visible:ring-1 ${
    err ? 'border-rose-500/70 focus-visible:ring-rose-400' : 'border-slate-700 focus-visible:ring-indigo-400'
  }`;

interface ParamFieldProps {
  spec: ParamSpec;
  value: unknown;
  /** undefined removes the key (backend default applies). */
  onChange: (value: unknown) => void;
  idPrefix: string;
}

export const ParamField: React.FC<ParamFieldProps> = ({ spec, value, onChange, idPrefix }) => {
  const id = `${idPrefix}-${spec.key}`;
  const error = validateParam(spec, value);
  const title = [spec.key, spec.hint].filter(Boolean).join(' — ');

  if (spec.kind === 'bool') {
    const on = (value ?? spec.def) !== false;
    return (
      <div className="min-w-0" title={title}>
        <span className="block text-xs text-slate-400 mb-0.5 truncate">{spec.label}</span>
        <div role="radiogroup" aria-label={spec.label} className="grid grid-cols-2 rounded border border-slate-700 overflow-hidden text-xs">
          {[
            { v: true, l: 'Emulated' },
            { v: false, l: 'Hardware' },
          ].map((o) => (
            <button
              key={o.l}
              type="button"
              role="radio"
              aria-checked={on === o.v}
              onClick={() => onChange(o.v)}
              className={`px-1.5 py-1 transition ${
                on === o.v ? 'bg-indigo-600/40 text-indigo-100' : 'bg-slate-950 text-slate-400 hover:text-slate-200'
              }`}
            >
              {o.l}
            </button>
          ))}
        </div>
      </div>
    );
  }

  const placeholder = spec.def === null || spec.def === undefined ? (spec.required ? 'required' : 'auto') : `${spec.def}`;

  return (
    <div className="min-w-0" title={title}>
      <label htmlFor={id} className="block text-xs text-slate-400 mb-0.5 truncate">
        {spec.label}
      </label>
      {spec.kind === 'select' ? (
        <select
          id={id}
          value={(value as string) ?? ''}
          onChange={(e) => onChange(e.target.value === '' ? undefined : e.target.value)}
          className={inputCls(false) + ' font-sans'}
        >
          <option value="">default ({String(spec.def)})</option>
          {spec.options?.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      ) : (
        <input
          id={id}
          type={spec.kind === 'string' ? 'text' : 'number'}
          inputMode={spec.kind === 'int' ? 'numeric' : spec.kind === 'float' ? 'decimal' : undefined}
          step={spec.kind === 'int' ? 1 : spec.step ?? 'any'}
          min={spec.min}
          value={displayValue(value)}
          placeholder={placeholder}
          aria-invalid={!!error}
          onChange={(e) => {
            const raw = e.target.value;
            if (raw === '') return onChange(undefined);
            if (spec.kind === 'string') return onChange(raw);
            const n = Number(raw);
            onChange(Number.isFinite(n) ? n : raw);
          }}
          className={inputCls(!!error)}
        />
      )}
      {error && <span className="block text-xs text-rose-300 mt-0.5">{error}</span>}
    </div>
  );
};

interface ExtraParamFieldProps {
  name: string;
  value: unknown;
  onChange: (value: unknown) => void;
  onRemove: () => void;
}

/** A key present in the config but unknown to the schema: edit as JSON-ish text. */
export const ExtraParamField: React.FC<ExtraParamFieldProps> = ({ name, value, onChange, onRemove }) => (
  <div className="min-w-0" title={`${name} (custom parameter)`}>
    <div className="flex items-center justify-between gap-1 mb-0.5">
      <span className="text-xs text-slate-400 font-mono truncate">{name}</span>
      <button type="button" onClick={onRemove} aria-label={`Remove ${name}`} className="text-slate-500 hover:text-rose-300">
        <X className="w-3 h-3" />
      </button>
    </div>
    <input
      type="text"
      value={typeof value === 'string' ? value : JSON.stringify(value)}
      onChange={(e) => {
        const raw = e.target.value;
        try {
          onChange(JSON.parse(raw));
        } catch {
          onChange(raw);
        }
      }}
      className={inputCls(false)}
    />
  </div>
);
