import React from 'react';
import { AlertTriangle, CheckCircle2 } from 'lucide-react';
import {
  PartitioningStrategyKey,
  QAOAParams,
  QuantumAnnealingParams,
  SimulationParameters,
} from '../../types/pipeline';
import { PARTITIONING_METHODS } from './constants';
import { InfoTooltip } from '../InfoTooltip';
import { StageCard, StageCardControl } from './StageCard';

interface StagePartitioningProps {
  /** Error state + collapse wiring for the stage card shell. */
  card: StageCardControl;
  onOpenWiki: (topicId: string) => void;
  parameters: SimulationParameters;
  onParametersChange: (next: SimulationParameters) => void;
  /** QA strategy params with defaults applied. */
  qaParams: QuantumAnnealingParams;
  /** QAOA strategy params with defaults applied. */
  qaoaParams: QAOAParams;
  /** Whether the active quantum strategy runs emulated (true for METIS). */
  currentSimulated: boolean;
  selectPartitionMethod: (strategy: PartitioningStrategyKey, simulated?: boolean) => void;
  bipartitionsPerStart: number;
  expectedQaSubmissions: number;
  expectedQaReads: number;
  expectedQaoaJobs: number;
}

/* STAGE 3: COARSE GRAPH PARTITIONING */
export const StagePartitioning: React.FC<StagePartitioningProps> = ({
  card,
  onOpenWiki,
  parameters,
  onParametersChange,
  qaParams,
  qaoaParams,
  currentSimulated,
  selectPartitionMethod,
  bipartitionsPerStart,
  expectedQaSubmissions,
  expectedQaReads,
  expectedQaoaJobs,
}) => {
  const cp = parameters.coarsening_parameters;
  const pp = parameters.partitioning_parameters;
  const activeStrategy = pp.partitioning_strategy;

  return (
    <StageCard
      n={3}
      title="Partitioning"
      subtitle="Split the coarse graph into k parts"
      wikiId="stage-3"
      onOpenWiki={onOpenWiki}
      {...card}
      headerRight={
        <>
          {/* Common Target Subdomains k_target */}
          <div className="flex flex-wrap items-center gap-4">
            <div className="flex items-center gap-2">
              <span className="text-xs text-slate-300 font-medium flex items-center gap-1">
                Subdomains (k):
                <InfoTooltip topicId="param-k-target" onOpenWiki={onOpenWiki} />
              </span>
              <div className="flex items-center gap-1">
                {[2, 4, 8, 16].map((kVal) => (
                  <button
                    key={kVal}
                    type="button"
                    aria-pressed={pp.common.k_target === kVal}
                    onClick={() =>
                      onParametersChange({
                        ...parameters,
                        partitioning_parameters: {
                          ...pp,
                          common: { ...pp.common, k_target: kVal },
                        },
                      })
                    }
                    className={`px-2.5 py-1 rounded text-xs font-mono font-semibold transition ${
                      pp.common.k_target === kVal
                        ? 'bg-indigo-600 text-white'
                        : 'bg-slate-950 text-slate-400 hover:bg-slate-800'
                    }`}
                  >
                    {kVal}
                  </button>
                ))}
                <input
                  type="number"
                  min={1}
                  max={256}
                  value={pp.common.k_target}
                  onChange={(e) =>
                    onParametersChange({
                      ...parameters,
                      partitioning_parameters: {
                        ...pp,
                        common: {
                          ...pp.common,
                          k_target: Math.max(1, parseInt(e.target.value || '2', 10)),
                        },
                      },
                    })
                  }
                  className="w-16 bg-slate-950 border border-slate-700 rounded px-2 py-1 text-xs font-mono text-center text-white ml-1"
                />
              </div>
            </div>

            <div className="flex items-center gap-2">
              <span className="text-xs text-slate-300 font-medium flex items-center gap-1">
                Balance Tol (%):
                <InfoTooltip topicId="param-balance-tolerance" onOpenWiki={onOpenWiki} />
              </span>
              <input
                type="number"
                step="0.1"
                min={0}
                value={pp.common.balance_tolerance}
                onChange={(e) =>
                  onParametersChange({
                    ...parameters,
                    partitioning_parameters: {
                      ...pp,
                      common: {
                        ...pp.common,
                        balance_tolerance: Math.max(0, parseFloat(e.target.value || '0')),
                      },
                    },
                  })
                }
                className="w-20 bg-slate-950 border border-slate-700 rounded px-2 py-1 text-xs font-mono text-white"
              />
            </div>
          </div>
        </>
      }
    >
      {/* Smart Cross-Stage Feasibility Warning Banner */}
      {activeStrategy === 'quantum_approximation_optimizer' &&
        qaoaParams.simulated &&
        (cp.coarsen_inferior_limit > 18 || (cp.coarsen_superior_limit ?? 9999) > 20) && (
          <div className="mt-4 p-3 rounded-xl bg-amber-950/40 border border-amber-500/40 flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2 text-xs text-amber-200">
              <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0" />
              <span>
                Coarse range{' '}
                <code className="text-white font-bold">
                  [{cp.coarsen_inferior_limit}, {cp.coarsen_superior_limit ?? '∞'}]
                </code>{' '}
                exceeds statevector emulation limit (~18 qubits).
              </span>
              <InfoTooltip topicId="tool-feasibility-check" onOpenWiki={onOpenWiki} />
            </div>
            <button
              type="button"
              onClick={() =>
                onParametersChange({
                  ...parameters,
                  coarsening_parameters: {
                    ...cp,
                    coarsen_inferior_limit: 4,
                    coarsen_superior_limit: 5,
                  },
                })
              }
              className="px-3 py-1 rounded-lg text-xs font-semibold bg-amber-500 hover:bg-amber-400 text-slate-950 transition shrink-0"
            >
              Use Small [4, 5]
            </button>
          </div>
        )}

      {activeStrategy === 'quantum_annealing' &&
        !qaParams.simulated &&
        (cp.coarsen_inferior_limit > 180 || (cp.coarsen_superior_limit ?? 9999) > 180) && (
          <div className="mt-4 p-3 rounded-xl bg-amber-950/40 border border-amber-500/40 flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2 text-xs text-amber-200">
              <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0" />
              <span>
                Coarse range{' '}
                <code className="text-white font-bold">
                  [{cp.coarsen_inferior_limit}, {cp.coarsen_superior_limit ?? '∞'}]
                </code>{' '}
                exceeds D-Wave clique capacity (~175 nodes).
              </span>
              <InfoTooltip topicId="tool-feasibility-check" onOpenWiki={onOpenWiki} />
            </div>
            <button
              type="button"
              onClick={() =>
                onParametersChange({
                  ...parameters,
                  coarsening_parameters: {
                    ...cp,
                    coarsen_inferior_limit: 100,
                    coarsen_superior_limit: 175,
                  },
                })
              }
              className="px-3 py-1 rounded-lg text-xs font-semibold bg-amber-500 hover:bg-amber-400 text-slate-950 transition shrink-0"
            >
              Use Medium [100, 175]
            </button>
          </div>
        )}

      {/* 5 Partitioning Method Cards */}
      <div className="mt-5">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
          {PARTITIONING_METHODS.map((m) => {
            const isSelected =
              activeStrategy === m.strategy &&
              (m.simulated === undefined || currentSimulated === m.simulated);

            return (
              <button
                key={m.id}
                type="button"
                aria-pressed={isSelected}
                onClick={() => selectPartitionMethod(m.strategy, m.simulated)}
                className={`text-left p-3.5 rounded-xl border transition-all flex flex-col justify-between min-w-0 overflow-hidden ${
                  isSelected
                    ? 'bg-indigo-950/60 border-indigo-500 ring-2 ring-indigo-500/30 shadow-lg'
                    : 'bg-slate-950/70 border-slate-800 hover:border-slate-700'
                }`}
              >
                <div className="flex items-center justify-between gap-1.5 mb-2">
                  <span
                    className={`text-xs px-2 py-0.5 rounded-full font-semibold truncate ${
                      m.category === 'Classical'
                        ? 'bg-slate-800 text-slate-300 border border-slate-700'
                        : m.category === 'Quantum Hardware'
                        ? 'bg-slate-800 text-slate-300 border border-slate-700'
                        : 'bg-slate-800 text-slate-300 border border-slate-700'
                    }`}
                  >
                    {m.category}
                  </span>
                  <div className="flex items-center gap-1 shrink-0">
                    {isSelected && <CheckCircle2 className="w-3.5 h-3.5 text-indigo-400" />}
                    <InfoTooltip topicId={m.wikiId} onOpenWiki={onOpenWiki} />
                  </div>
                </div>
                <div className="font-bold text-sm text-white truncate" title={m.title}>
                  {m.title}
                </div>
                <div className="text-xs text-slate-400 mt-0.5 truncate" title={m.subtitle}>
                  {m.subtitle}
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {activeStrategy === 'metis_partitioning' && (
        <div className="mt-4 pt-3 border-t border-slate-800/80 text-xs text-slate-400">
          No extra settings — METIS splits directly into <strong className="text-slate-200 font-mono">k = {pp.common.k_target}</strong> parts.
        </div>
      )}

      {/* Strategy-Specific Parameter Controls */}
      {activeStrategy !== 'metis_partitioning' && (
        <div className="mt-5 pt-4 border-t border-slate-800">
          {activeStrategy === 'quantum_annealing' && (
            <div className="space-y-4">
              <div className="flex flex-wrap items-center justify-end gap-2">
                <InfoTooltip topicId="theory-qubo-ising" onOpenWiki={onOpenWiki} />
                <div className="flex flex-wrap items-center gap-3 text-xs bg-slate-950 px-3.5 py-1.5 rounded-xl border border-slate-800">
                  <span className="text-slate-400">
                    Bipartitions/start: <strong className="text-white font-mono">{bipartitionsPerStart}</strong>
                  </span>
                  <span className="text-slate-600">|</span>
                  <span className="text-slate-400">
                    QPU Jobs: <strong className="text-white font-mono">{expectedQaSubmissions}</strong>
                  </span>
                  <span className="text-slate-600">|</span>
                  <span className="text-slate-400">
                    Total Reads: <strong className="text-white font-mono">{expectedQaReads.toLocaleString()}</strong>
                  </span>
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                <div className="min-w-0">
                  <label className="text-xs font-medium text-slate-300 flex items-center gap-1.5 mb-1.5">
                    <span className="truncate">QUBO Balance λ</span>
                    <InfoTooltip topicId="param-qubo-balance-lambda" onOpenWiki={onOpenWiki} />
                  </label>
                  <input
                    type="number"
                    step="any"
                    value={qaParams.qubo_balance_lambda}
                    onChange={(e) =>
                      onParametersChange({
                        ...parameters,
                        partitioning_parameters: {
                          ...pp,
                          strategies: {
                            ...pp.strategies,
                            quantum_annealing: {
                              ...qaParams,
                              qubo_balance_lambda: parseFloat(e.target.value || '0'),
                            },
                          },
                        },
                      })
                    }
                    className="w-full min-w-0 bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm font-mono text-white"
                  />
                </div>

                <div className="min-w-0">
                  <label className="text-xs font-medium text-slate-300 flex items-center gap-1.5 mb-1.5">
                    <span className="truncate">Recursive Starts</span>
                    <InfoTooltip topicId="param-num-starts" onOpenWiki={onOpenWiki} />
                  </label>
                  <input
                    type="number"
                    min={1}
                    value={qaParams.num_starts}
                    onChange={(e) =>
                      onParametersChange({
                        ...parameters,
                        partitioning_parameters: {
                          ...pp,
                          strategies: {
                            ...pp.strategies,
                            quantum_annealing: {
                              ...qaParams,
                              num_starts: Math.max(1, parseInt(e.target.value || '1', 10)),
                            },
                          },
                        },
                      })
                    }
                    className="w-full min-w-0 bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm font-mono text-white"
                  />
                </div>

                <div className="min-w-0">
                  <label className="text-xs font-medium text-slate-300 flex items-center gap-1.5 mb-1.5">
                    <span className="truncate">Reads per Job</span>
                    <InfoTooltip topicId="param-num-reads" onOpenWiki={onOpenWiki} />
                  </label>
                  <input
                    type="number"
                    min={1}
                    value={qaParams.num_reads}
                    onChange={(e) =>
                      onParametersChange({
                        ...parameters,
                        partitioning_parameters: {
                          ...pp,
                          strategies: {
                            ...pp.strategies,
                            quantum_annealing: {
                              ...qaParams,
                              num_reads: Math.max(1, parseInt(e.target.value || '1', 10)),
                            },
                          },
                        },
                      })
                    }
                    className="w-full min-w-0 bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm font-mono text-white"
                  />
                </div>

                <div className="min-w-0">
                  <label className="text-xs font-medium text-slate-300 flex items-center gap-1.5 mb-1.5">
                    <span className="truncate">Balance Violation λ</span>
                    <InfoTooltip topicId="param-balance-violation-lambda" onOpenWiki={onOpenWiki} />
                  </label>
                  <input
                    type="number"
                    step="any"
                    min={0}
                    value={qaParams.balance_violation_lambda}
                    onChange={(e) =>
                      onParametersChange({
                        ...parameters,
                        partitioning_parameters: {
                          ...pp,
                          strategies: {
                            ...pp.strategies,
                            quantum_annealing: {
                              ...qaParams,
                              balance_violation_lambda: Math.max(0, parseFloat(e.target.value || '0')),
                            },
                          },
                        },
                      })
                    }
                    className="w-full min-w-0 bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm font-mono text-white"
                  />
                </div>
              </div>

              {/* D-Wave Hardware Specific Fields */}
              {!qaParams.simulated && (
                <div className="p-4 rounded-xl bg-slate-950/60 border border-slate-700 grid grid-cols-1 md:grid-cols-3 gap-4">
                  <div className="min-w-0">
                    <label className="text-xs font-medium text-slate-300 flex items-center gap-1.5 mb-1.5">
                      <span className="truncate">D-Wave QPU Solver</span>
                      <InfoTooltip topicId="param-qpu-solver-name" onOpenWiki={onOpenWiki} />
                    </label>
                    <input
                      type="text"
                      value={qaParams.qpu_solver_name ?? ''}
                      placeholder="Advantage2_system2.1"
                      onChange={(e) =>
                        onParametersChange({
                          ...parameters,
                          partitioning_parameters: {
                            ...pp,
                            strategies: {
                              ...pp.strategies,
                              quantum_annealing: {
                                ...qaParams,
                                qpu_solver_name: e.target.value || null,
                              },
                            },
                          },
                        })
                      }
                      className="w-full min-w-0 bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs font-mono text-white"
                    />
                  </div>
                  <div className="min-w-0">
                    <label className="text-xs font-medium text-slate-300 flex items-center gap-1.5 mb-1.5">
                      <span className="truncate">Leap Cloud Region</span>
                      <InfoTooltip topicId="param-qpu-region" onOpenWiki={onOpenWiki} />
                    </label>
                    <input
                      type="text"
                      value={qaParams.qpu_region ?? ''}
                      placeholder="eu-central-1"
                      onChange={(e) =>
                        onParametersChange({
                          ...parameters,
                          partitioning_parameters: {
                            ...pp,
                            strategies: {
                              ...pp.strategies,
                              quantum_annealing: {
                                ...qaParams,
                                qpu_region: e.target.value || null,
                              },
                            },
                          },
                        })
                      }
                      className="w-full min-w-0 bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs font-mono text-white"
                    />
                  </div>
                  <div className="min-w-0">
                    <label className="text-xs font-medium text-slate-300 flex items-center gap-1.5 mb-1.5">
                      <span className="truncate">Problem Label</span>
                      <InfoTooltip topicId="param-qpu-problem-label" onOpenWiki={onOpenWiki} />
                    </label>
                    <input
                      type="text"
                      value={qaParams.qpu_problem_label ?? ''}
                      placeholder="DD_ansys_v0"
                      onChange={(e) =>
                        onParametersChange({
                          ...parameters,
                          partitioning_parameters: {
                            ...pp,
                            strategies: {
                              ...pp.strategies,
                              quantum_annealing: {
                                ...qaParams,
                                qpu_problem_label: e.target.value || null,
                              },
                            },
                          },
                        })
                      }
                      className="w-full min-w-0 bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs font-mono text-white"
                    />
                  </div>
                </div>
              )}
            </div>
          )}

          {activeStrategy === 'quantum_approximation_optimizer' && (
            <div className="space-y-4">
              <div className="flex flex-wrap items-center justify-end gap-2">
                <InfoTooltip topicId="theory-qubo-ising" onOpenWiki={onOpenWiki} />
                <div className="flex flex-wrap items-center gap-3 text-xs bg-slate-950 px-3.5 py-1.5 rounded-xl border border-slate-800">
                  <span className="text-slate-400">
                    Circuit Evaluations: <strong className="text-white font-mono">{expectedQaoaJobs}</strong>
                  </span>
                  <span className="text-slate-600">|</span>
                  <span className="text-slate-400">
                    Total Shots:{' '}
                    <strong className="text-white font-mono">
                      {(expectedQaoaJobs * (qaoaParams.num_shots || 1)).toLocaleString()}
                    </strong>
                  </span>
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                <div className="min-w-0">
                  <label className="text-xs font-medium text-slate-300 flex items-center gap-1.5 mb-1.5">
                    <span className="truncate">Circuit Depth (p)</span>
                    <InfoTooltip topicId="param-circuit-depth" onOpenWiki={onOpenWiki} />
                  </label>
                  <input
                    type="number"
                    min={1}
                    value={qaoaParams.circuit_depth}
                    onChange={(e) =>
                      onParametersChange({
                        ...parameters,
                        partitioning_parameters: {
                          ...pp,
                          strategies: {
                            ...pp.strategies,
                            quantum_approximation_optimizer: {
                              ...qaoaParams,
                              circuit_depth: Math.max(1, parseInt(e.target.value || '1', 10)),
                            },
                          },
                        },
                      })
                    }
                    className="w-full min-w-0 bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm font-mono text-white"
                  />
                </div>

                <div className="min-w-0">
                  <label className="text-xs font-medium text-slate-300 flex items-center gap-1.5 mb-1.5">
                    <span className="truncate">Optimizer Steps</span>
                    <InfoTooltip topicId="param-num-steps" onOpenWiki={onOpenWiki} />
                  </label>
                  <input
                    type="number"
                    min={1}
                    value={qaoaParams.num_steps}
                    onChange={(e) =>
                      onParametersChange({
                        ...parameters,
                        partitioning_parameters: {
                          ...pp,
                          strategies: {
                            ...pp.strategies,
                            quantum_approximation_optimizer: {
                              ...qaoaParams,
                              num_steps: Math.max(1, parseInt(e.target.value || '1', 10)),
                            },
                          },
                        },
                      })
                    }
                    className="w-full min-w-0 bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm font-mono text-white"
                  />
                </div>

                <div className="min-w-0">
                  <label className="text-xs font-medium text-slate-300 flex items-center gap-1.5 mb-1.5">
                    <span className="truncate">Measurement Shots</span>
                    <InfoTooltip topicId="param-num-shots" onOpenWiki={onOpenWiki} />
                  </label>
                  <input
                    type="number"
                    min={1}
                    value={qaoaParams.num_shots}
                    onChange={(e) =>
                      onParametersChange({
                        ...parameters,
                        partitioning_parameters: {
                          ...pp,
                          strategies: {
                            ...pp.strategies,
                            quantum_approximation_optimizer: {
                              ...qaoaParams,
                              num_shots: Math.max(1, parseInt(e.target.value || '1', 10)),
                            },
                          },
                        },
                      })
                    }
                    className="w-full min-w-0 bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm font-mono text-white"
                  />
                </div>

                <div className="min-w-0">
                  <label className="text-xs font-medium text-slate-300 flex items-center gap-1.5 mb-1.5">
                    <span className="truncate">Multi-Starts</span>
                    <InfoTooltip topicId="param-num-starts" onOpenWiki={onOpenWiki} />
                  </label>
                  <input
                    type="number"
                    min={1}
                    value={qaoaParams.num_starts}
                    onChange={(e) =>
                      onParametersChange({
                        ...parameters,
                        partitioning_parameters: {
                          ...pp,
                          strategies: {
                            ...pp.strategies,
                            quantum_approximation_optimizer: {
                              ...qaoaParams,
                              num_starts: Math.max(1, parseInt(e.target.value || '1', 10)),
                            },
                          },
                        },
                      })
                    }
                    className="w-full min-w-0 bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm font-mono text-white"
                  />
                </div>

                <div className="min-w-0">
                  <label className="text-xs font-medium text-slate-300 flex items-center gap-1.5 mb-1.5">
                    <span className="truncate">QUBO Balance λ</span>
                    <InfoTooltip topicId="param-qubo-balance-lambda" onOpenWiki={onOpenWiki} />
                  </label>
                  <input
                    type="number"
                    step="any"
                    value={qaoaParams.qubo_balance_lambda}
                    onChange={(e) =>
                      onParametersChange({
                        ...parameters,
                        partitioning_parameters: {
                          ...pp,
                          strategies: {
                            ...pp.strategies,
                            quantum_approximation_optimizer: {
                              ...qaoaParams,
                              qubo_balance_lambda: parseFloat(e.target.value || '0'),
                            },
                          },
                        },
                      })
                    }
                    className="w-full min-w-0 bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm font-mono text-white"
                  />
                </div>

                <div className="min-w-0">
                  <label className="text-xs font-medium text-slate-300 flex items-center gap-1.5 mb-1.5">
                    <span className="truncate">Balance Violation λ</span>
                    <InfoTooltip topicId="param-balance-violation-lambda" onOpenWiki={onOpenWiki} />
                  </label>
                  <input
                    type="number"
                    step="any"
                    min={0}
                    value={qaoaParams.balance_violation_lambda}
                    onChange={(e) =>
                      onParametersChange({
                        ...parameters,
                        partitioning_parameters: {
                          ...pp,
                          strategies: {
                            ...pp.strategies,
                            quantum_approximation_optimizer: {
                              ...qaoaParams,
                              balance_violation_lambda: Math.max(0, parseFloat(e.target.value || '0')),
                            },
                          },
                        },
                      })
                    }
                    className="w-full min-w-0 bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm font-mono text-white"
                  />
                </div>

                {qaoaParams.simulated ? (
                  <div className="sm:col-span-2 min-w-0">
                    <label className="text-xs font-medium text-slate-300 flex items-center gap-1.5 mb-1.5">
                      <span className="truncate">PennyLane Adam Learning Rate</span>
                      <InfoTooltip topicId="param-adam-learning-rate" onOpenWiki={onOpenWiki} />
                    </label>
                    <input
                      type="number"
                      step="0.01"
                      min={0.0001}
                      value={qaoaParams.adam_learning_rate ?? 0.1}
                      onChange={(e) =>
                        onParametersChange({
                          ...parameters,
                          partitioning_parameters: {
                            ...pp,
                            strategies: {
                              ...pp.strategies,
                              quantum_approximation_optimizer: {
                                ...qaoaParams,
                                adam_learning_rate: parseFloat(e.target.value || '0.1'),
                              },
                            },
                          },
                        })
                      }
                      className="w-full min-w-0 bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm font-mono text-white"
                    />
                  </div>
                ) : (
                  <div className="sm:col-span-2 min-w-0">
                    <label className="text-xs font-medium text-slate-300 flex items-center gap-1.5 mb-1.5">
                      <span className="truncate">Remote QLM QPU Target</span>
                      <InfoTooltip topicId="param-qlm-qpu-name" onOpenWiki={onOpenWiki} />
                    </label>
                    <input
                      type="text"
                      value={qaoaParams.qlm_qpu_name ?? 'qat.qpus:QSolidQPU10'}
                      onChange={(e) =>
                        onParametersChange({
                          ...parameters,
                          partitioning_parameters: {
                            ...pp,
                            strategies: {
                              ...pp.strategies,
                              quantum_approximation_optimizer: {
                                ...qaoaParams,
                                qlm_qpu_name: e.target.value,
                              },
                            },
                          },
                        })
                      }
                      className="w-full min-w-0 bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm font-mono text-white"
                    />
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </StageCard>
  );
};
