import React, { useEffect, useState } from 'react';
import { ArrowLeftRight } from 'lucide-react';
import { methodLabel } from '../../lib/labels';
import { api } from '../../api/client';
import {
  Demonstrator,
  QAOAParams,
  QuantumAnnealingParams,
  SimulationConfig,
  SimulationParameters,
} from '../../types/pipeline';

/** The `simulated` flag that applies to a strategy (null for METIS / unknown). */
const strategySimulated = (
  strategy: string,
  qaSimulated: boolean | undefined,
  qaoaSimulated: boolean | undefined
): boolean | null =>
  strategy === 'quantum_annealing'
    ? qaSimulated ?? null
    : strategy === 'quantum_approximation_optimizer'
    ? qaoaSimulated ?? null
    : null;

export interface CompareConfigsState {
  showDiffModal: boolean;
  setShowDiffModal: (open: boolean) => void;
  /** Opens the modal, pre-selecting another simulation (and its active preset) as Config B. */
  openCompare: () => void;
  compareDemId: string;
  setCompareDemId: (id: string) => void;
  comparePresetFile: string;
  setComparePresetFile: (filename: string) => void;
  compareParams: SimulationParameters | null;
  onlyDiffs: boolean;
  setOnlyDiffs: (value: boolean) => void;
  loadingCompare: boolean;
}

/**
 * Diff / Compare Configs Modal State.
 * Called from PipelineStudio so the selection and "Show Only Differences" toggle persist across
 * opening/closing the modal, exactly as before the split.
 */
export const useCompareConfigs = (
  demonstrators: Demonstrator[],
  demonstrator: Demonstrator
): CompareConfigsState => {
  const [showDiffModal, setShowDiffModal] = useState(false);
  const [compareDemId, setCompareDemId] = useState<string>(
    demonstrators.find((d) => d.id !== demonstrator.id)?.id || demonstrator.id
  );
  const [comparePresetFile, setComparePresetFile] = useState<string>('simulation_parameters.json');
  const [compareParams, setCompareParams] = useState<SimulationParameters | null>(null);
  const [onlyDiffs, setOnlyDiffs] = useState(false);
  const [loadingCompare, setLoadingCompare] = useState(false);

  useEffect(() => {
    if (!showDiffModal) return;
    const targetDem = demonstrators.find((d) => d.id === compareDemId) || demonstrator;
    const presetToLoad = targetDem.preset_files.includes(comparePresetFile)
      ? comparePresetFile
      : targetDem.active_parameters_file || 'simulation_parameters.json';
    setLoadingCompare(true);
    api
      .getPreset(targetDem.id, presetToLoad)
      .then((res) => setCompareParams(res.parameters))
      .catch(() => setCompareParams(targetDem.simulation_parameters))
      .finally(() => setLoadingCompare(false));
  }, [showDiffModal, compareDemId, comparePresetFile, demonstrators, demonstrator]);

  const openCompare = () => {
    const otherDem = demonstrators.find((d) => d.id !== demonstrator.id) || demonstrator;
    setCompareDemId(otherDem.id);
    setComparePresetFile(otherDem.active_parameters_file || 'simulation_parameters.json');
    setShowDiffModal(true);
  };

  return {
    showDiffModal,
    setShowDiffModal,
    openCompare,
    compareDemId,
    setCompareDemId,
    comparePresetFile,
    setComparePresetFile,
    compareParams,
    onlyDiffs,
    setOnlyDiffs,
    loadingCompare,
  };
};

interface CompareConfigsModalProps {
  demonstrators: Demonstrator[];
  demonstrator: Demonstrator;
  config: SimulationConfig;
  parameters: SimulationParameters;
  /** QA strategy params (with defaults) of the active editor (Config A). */
  qaParams: QuantumAnnealingParams;
  /** QAOA strategy params (with defaults) of the active editor (Config A). */
  qaoaParams: QAOAParams;
  /** State from useCompareConfigs(). */
  compare: CompareConfigsState;
}

/* Diff / Compare Two Presets or Demonstrators Modal */
export const CompareConfigsModal: React.FC<CompareConfigsModalProps> = ({
  demonstrators,
  demonstrator,
  config,
  parameters,
  qaParams,
  qaoaParams,
  compare,
}) => {
  const gp = parameters.general_parameters;
  const cp = parameters.coarsening_parameters;
  const pp = parameters.partitioning_parameters;
  const up = parameters.uncoarsening_parameters;
  const {
    setShowDiffModal,
    compareDemId,
    setCompareDemId,
    comparePresetFile,
    setComparePresetFile,
    compareParams,
    onlyDiffs,
    setOnlyDiffs,
    loadingCompare,
  } = compare;

  return (
    <div className="fixed inset-0 z-50 bg-black/75 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-slate-900 border border-slate-700 rounded-2xl max-w-4xl w-full max-h-[86vh] flex flex-col overflow-hidden shadow-2xl">
        <div className="p-4 border-b border-slate-800 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <ArrowLeftRight className="w-4 h-4 text-indigo-400" />
            <span className="font-bold text-sm text-white">
              Compare Configurations (Side-by-Side Diff)
            </span>
          </div>
          <div className="flex items-center gap-3">
            <label className="inline-flex items-center gap-2 text-xs text-slate-300 cursor-pointer">
              <input
                type="checkbox"
                checked={onlyDiffs}
                onChange={(e) => setOnlyDiffs(e.target.checked)}
                className="rounded border-slate-700 bg-slate-950 text-indigo-600 focus:ring-indigo-500"
              />
              Show Only Differences
            </label>
            <button
              type="button"
              onClick={() => setShowDiffModal(false)}
              className="px-3 py-1 rounded-lg text-xs bg-slate-800 text-slate-300 hover:bg-slate-700"
            >
              Close
            </button>
          </div>
        </div>

        {/* Selector Header */}
        <div className="p-4 bg-slate-950/70 border-b border-slate-800 grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="p-3 rounded-xl bg-indigo-950/30 border border-indigo-500/30">
            <div className="text-xs font-semibold uppercase tracking-wider text-indigo-300 mb-1">
              Configuration A (Current Active Editor)
            </div>
            <div className="text-xs font-mono text-white truncate">
              {demonstrator.id} / data/{config.parameters_file_path}
            </div>
          </div>

          <div className="p-3 rounded-xl bg-slate-900/60 border border-slate-700 space-y-2">
            <div className="text-xs font-semibold uppercase tracking-wider text-slate-300">
              Configuration B (Target to Compare Against)
            </div>
            <div className="grid grid-cols-2 gap-2">
              <select
                value={compareDemId}
                onChange={(e) => {
                  const nextId = e.target.value;
                  setCompareDemId(nextId);
                  const found = demonstrators.find((d) => d.id === nextId);
                  if (found) {
                    setComparePresetFile(
                      found.active_parameters_file || 'simulation_parameters.json'
                    );
                  }
                }}
                className="bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs text-white truncate"
              >
                {demonstrators.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.id}
                  </option>
                ))}
              </select>
              <select
                value={comparePresetFile}
                onChange={(e) => setComparePresetFile(e.target.value)}
                className="bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs text-white font-mono truncate"
              >
                {(
                  demonstrators.find((d) => d.id === compareDemId)?.preset_files || [
                    'simulation_parameters.json',
                  ]
                ).map((pf) => (
                  <option key={pf} value={pf}>
                    {pf}
                  </option>
                ))}
              </select>
            </div>
          </div>
        </div>

        {/* Diff Table Body */}
        <div className="p-4 overflow-y-auto flex-1">
          {loadingCompare || !compareParams ? (
            <div className="py-12 text-center text-xs text-slate-400">
              Loading comparison configuration...
            </div>
          ) : (
            (() => {
              const qaB = compareParams.partitioning_parameters.strategies.quantum_annealing;
              const qaoaB =
                compareParams.partitioning_parameters.strategies.quantum_approximation_optimizer;

              const rows: Array<{
                stage: string;
                label: string;
                valA: string;
                valB: string;
              }> = [
                {
                  stage: 'Stage 1 (General)',
                  label: 'DOFs per Node (dof_per_node)',
                  valA: String(gp.dof_per_node),
                  valB: String(compareParams.general_parameters.dof_per_node),
                },
                {
                  stage: 'Stage 1 (General)',
                  label: 'Master Seed (seed)',
                  valA: String(gp.seed),
                  valB: String(compareParams.general_parameters.seed),
                },
                {
                  stage: 'Stage 2 (Coarsening)',
                  label: 'HEM Strategy (strategy)',
                  valA: cp.strategy,
                  valB: compareParams.coarsening_parameters.strategy,
                },
                {
                  stage: 'Stage 2 (Coarsening)',
                  label: 'Inferior Node Limit',
                  valA: String(cp.coarsen_inferior_limit),
                  valB: String(compareParams.coarsening_parameters.coarsen_inferior_limit),
                },
                {
                  stage: 'Stage 2 (Coarsening)',
                  label: 'Superior Node Limit',
                  valA: String(cp.coarsen_superior_limit ?? 'None'),
                  valB: String(
                    compareParams.coarsening_parameters.coarsen_superior_limit ?? 'None'
                  ),
                },
                {
                  stage: 'Stage 2 (Coarsening)',
                  label: 'Max Coarsening Levels (max_levels)',
                  valA: String(cp.max_levels),
                  valB: String(compareParams.coarsening_parameters.max_levels),
                },
                {
                  stage: 'Stage 2 (Coarsening)',
                  label: 'Coarsen Ratio (coarsen_ratio)',
                  valA: String(cp.coarsen_ratio),
                  valB: String(compareParams.coarsening_parameters.coarsen_ratio),
                },
                {
                  stage: 'Stage 2 (Coarsening)',
                  label: 'Max Node Weight (max_node_weight)',
                  valA: String(cp.max_node_weight ?? 'Auto'),
                  valB: String(compareParams.coarsening_parameters.max_node_weight ?? 'Auto'),
                },
                {
                  stage: 'Stage 3 (Partitioning)',
                  label: 'Partitioning Method',
                  valA: methodLabel(pp.partitioning_strategy, strategySimulated(pp.partitioning_strategy, qaParams.simulated, qaoaParams.simulated)),
                  valB: methodLabel(
                    compareParams.partitioning_parameters.partitioning_strategy,
                    strategySimulated(
                      compareParams.partitioning_parameters.partitioning_strategy,
                      qaB?.simulated,
                      qaoaB?.simulated
                    )
                  ),
                },
                {
                  stage: 'Stage 3 (Partitioning)',
                  label: 'Target Subdomains (k_target)',
                  valA: String(pp.common.k_target),
                  valB: String(compareParams.partitioning_parameters.common.k_target),
                },
                {
                  stage: 'Stage 3 (Partitioning)',
                  label: 'Balance Tolerance (%)',
                  valA: String(pp.common.balance_tolerance),
                  valB: String(compareParams.partitioning_parameters.common.balance_tolerance),
                },
                {
                  stage: 'Stage 3 (QA)',
                  label: 'QA Mode (simulated)',
                  valA: String(qaParams.simulated),
                  valB: String(qaB?.simulated ?? '—'),
                },
                {
                  stage: 'Stage 3 (QA)',
                  label: 'QA QUBO Balance λ',
                  valA: String(qaParams.qubo_balance_lambda),
                  valB: String(qaB?.qubo_balance_lambda ?? '—'),
                },
                {
                  stage: 'Stage 3 (QA)',
                  label: 'QA Starts × Reads',
                  valA: `${qaParams.num_starts} × ${qaParams.num_reads}`,
                  valB: qaB ? `${qaB.num_starts} × ${qaB.num_reads}` : '—',
                },
                {
                  stage: 'Stage 3 (QAOA)',
                  label: 'QAOA Mode (simulated)',
                  valA: String(qaoaParams.simulated),
                  valB: String(qaoaB?.simulated ?? '—'),
                },
                {
                  stage: 'Stage 3 (QAOA)',
                  label: 'QAOA Depth (p) / Steps / Shots',
                  valA: `p=${qaoaParams.circuit_depth}, steps=${qaoaParams.num_steps}, shots=${qaoaParams.num_shots}`,
                  valB: qaoaB
                    ? `p=${qaoaB.circuit_depth}, steps=${qaoaB.num_steps}, shots=${qaoaB.num_shots}`
                    : '—',
                },
                {
                  stage: 'Stage 4 (Refinement)',
                  label: 'Refinement Objective',
                  valA: up.refine_objective,
                  valB: compareParams.uncoarsening_parameters.refine_objective,
                },
                {
                  stage: 'Stage 4 (Refinement)',
                  label: 'Refine Balance λ',
                  valA: String(up.refine_balance_lambda),
                  valB: String(compareParams.uncoarsening_parameters.refine_balance_lambda),
                },
                {
                  stage: 'Stage 4 (Refinement)',
                  label: 'Max Passes / Level',
                  valA: String(up.refine_max_passes_per_level),
                  valB: String(
                    compareParams.uncoarsening_parameters.refine_max_passes_per_level
                  ),
                },
                {
                  stage: 'Stage 4 (Refinement)',
                  label: 'Max Moves / Pass',
                  valA: String(up.refine_max_moves_per_pass ?? 'Unlimited'),
                  valB: String(
                    compareParams.uncoarsening_parameters.refine_max_moves_per_pass ??
                      'Unlimited'
                  ),
                },
              ];

              const filtered = onlyDiffs ? rows.filter((r) => r.valA !== r.valB) : rows;

              if (filtered.length === 0) {
                return (
                  <div className="py-10 text-center text-xs text-emerald-400">
                    Both configurations are 100% identical across all compared parameters.
                  </div>
                );
              }

              return (
                <table className="w-full text-left border-collapse text-xs">
                  <thead>
                    <tr className="border-b border-slate-800 text-slate-400">
                      <th className="py-2 px-3">Pipeline Stage</th>
                      <th className="py-2 px-3">Parameter</th>
                      <th className="py-2 px-3 text-indigo-300">
                        Config A ({demonstrator.id})
                      </th>
                      <th className="py-2 px-3 text-slate-200">
                        Config B ({compareDemId}/{comparePresetFile})
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/70">
                    {filtered.map((r, i) => {
                      const isDiff = r.valA !== r.valB;
                      return (
                        <tr
                          key={i}
                          className="hover:bg-slate-950/40"
                        >
                          <td className="py-2 px-3 text-slate-400 font-medium">{r.stage}</td>
                          <td className="py-2 px-3 text-slate-200 font-medium">
                            {r.label}
                          </td>
                          <td
                            className={`py-2 px-3 font-mono ${
                              isDiff ? 'text-amber-400 font-bold' : 'text-slate-300'
                            }`}
                          >
                            {r.valA}
                          </td>
                          <td
                            className={`py-2 px-3 font-mono ${
                              isDiff ? 'text-amber-400 font-bold' : 'text-slate-300'
                            }`}
                          >
                            {r.valB}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              );
            })()
          )}
        </div>
      </div>
    </div>
  );
};
