import React, { useEffect, useState } from 'react';
import {
  Activity,
  AlertTriangle,
  ArrowLeftRight,
  CheckCircle2,
  Code2,
  Cpu,
  Database,
  Edit3,
  FileCode,
  FolderPlus,
  GitBranch,
  Layers,
  Play,
  RefreshCw,
  Save,
  Sparkles,
  Trash2,
  Upload,
  Zap,
} from 'lucide-react';
import { api } from '../api/client';
import {
  CoarseningParameters,
  CoarseningPreviewResponse,
  Demonstrator,
  MatrixInfo,
  PartitioningStrategyKey,
  QuantumAnnealingParams,
  QAOAParams,
  SimulationConfig,
  SimulationParameters,
} from '../types/pipeline';
import { InfoTooltip } from './InfoTooltip';

interface PipelineStudioProps {
  demonstrators: Demonstrator[];
  demonstrator: Demonstrator;
  config: SimulationConfig;
  parameters: SimulationParameters;
  hasUnsavedChanges: boolean;
  validationError: string | null;
  saving: boolean;
  onSelectDemonstrator: (dem: Demonstrator) => void;
  onOpenNewDemonstrator: () => void;
  onRenameDemonstrator: (demId: string, newName: string) => Promise<void>;
  onDeleteDemonstrator: (demId: string) => Promise<void>;
  onConfigChange: (next: SimulationConfig) => void;
  onParametersChange: (next: SimulationParameters) => void;
  onSaveAll: () => Promise<void>;
  onRunSimulation: (useInMemoryOverride: boolean) => Promise<void>;
  onGenerateDemoMatrices: (preset: 'small' | 'medium' | 'large') => Promise<void>;
  onUploadMatrix: (file: File) => Promise<void>;
  onSavePreset: (filename: string) => Promise<void>;
  onSelectPreset: (filename: string) => Promise<void>;
  onDeletePreset: (filename: string) => Promise<void>;
  onOpenWiki: (topicId: string) => void;
}

const COARSENING_STRATEGIES: Array<{
  key: CoarseningParameters['strategy'];
  wikiId: string;
  title: string;
  badge: string;
  formula: string;
}> = [
  {
    key: 'random',
    wikiId: 'method-hem-random',
    title: 'Random HEM',
    badge: 'Foundational',
    formula: 'score(u, v) = w(u, v)',
  },
  {
    key: 'sorted',
    wikiId: 'method-hem-sorted',
    title: 'Sorted HEM (SHEM)',
    badge: 'Degree-Ordered',
    formula: 'Order by deg_w(u) desc',
  },
  {
    key: 'modified',
    wikiId: 'method-hem-modified',
    title: 'Modified HEM (MHEM)',
    badge: 'Weight-Balanced',
    formula: 'w(u,v) / √(c(u)·c(v))',
  },
  {
    key: 'light',
    wikiId: 'method-hem-light',
    title: 'Light-Edge Matching',
    badge: 'Sparse Variant',
    formula: 'score(u, v) = -w(u, v)',
  },
];

const COARSENING_SCALE_PRESETS = [
  {
    key: 'small',
    label: 'Small (4–5)',
    inferior: 4,
    superior: 5,
    desc: 'NISQ Gate-Based QAOA & Hardware scale',
  },
  {
    key: 'medium',
    label: 'Medium (100–175)',
    inferior: 100,
    superior: 175,
    desc: 'D-Wave Advantage Clique QUBO scale',
  },
  {
    key: 'big',
    label: 'Big (1500–2500)',
    inferior: 1500,
    superior: 2500,
    desc: 'Classical METIS & Emulated Annealing scale',
  },
];

const PARTITIONING_METHODS: Array<{
  strategy: PartitioningStrategyKey;
  simulated?: boolean;
  id: string;
  wikiId: string;
  title: string;
  subtitle: string;
  category: 'Classical' | 'Quantum Hardware' | 'Quantum Emulated';
}> = [
  {
    strategy: 'metis_partitioning',
    id: 'metis',
    wikiId: 'method-metis',
    title: 'METIS Baseline',
    subtitle: 'PyMETIS Weighted k-Way',
    category: 'Classical',
  },
  {
    strategy: 'quantum_annealing',
    simulated: true,
    id: 'qa_emulated',
    wikiId: 'method-qa-emulated',
    title: 'Quantum Annealing (Emulated)',
    subtitle: 'dwave-neal Simulated Annealing',
    category: 'Quantum Emulated',
  },
  {
    strategy: 'quantum_annealing',
    simulated: false,
    id: 'qa_hardware',
    wikiId: 'method-qa-hardware',
    title: 'Quantum Annealing (D-Wave QPU)',
    subtitle: 'D-Wave Leap Superconducting QPU',
    category: 'Quantum Hardware',
  },
  {
    strategy: 'quantum_approximation_optimizer',
    simulated: true,
    id: 'qaoa_emulated',
    wikiId: 'method-qaoa-emulated',
    title: 'QAOA (Emulated)',
    subtitle: 'PennyLane Circuit + Adam',
    category: 'Quantum Emulated',
  },
  {
    strategy: 'quantum_approximation_optimizer',
    simulated: false,
    id: 'qaoa_hardware',
    wikiId: 'method-qaoa-hardware',
    title: 'QAOA (QLM Hardware)',
    subtitle: 'myQLM / QLMaaS Gate QPU',
    category: 'Quantum Hardware',
  },
];

const SAVE_OUTPUT_LABELS: Record<string, { title: string; file: string; wikiId: string }> = {
  coarsened_graph: {
    title: 'Coarsened Graph Matrix',
    file: 'coarsened_graph.mtx',
    wikiId: 'output-coarsened-graph',
  },
  matrix_k_permuted: {
    title: 'Permuted Stiffness Matrix K',
    file: 'matrix_k_permuted.mtx',
    wikiId: 'output-matrix-k-permuted',
  },
  matrix_m_permuted: {
    title: 'Permuted Mass Matrix M',
    file: 'matrix_m_permuted.mtx',
    wikiId: 'output-matrix-m-permuted',
  },
  permutation: {
    title: 'Permutation Vector',
    file: 'permutation.txt',
    wikiId: 'output-permutation',
  },
  run_metrics: {
    title: 'Structural & Bandwidth Metrics',
    file: 'run_metrics.json / .txt',
    wikiId: 'output-run-metrics',
  },
  run_simulation_parameters: {
    title: 'Simulation Parameters Snapshot',
    file: 'run_simulation_parameters.json',
    wikiId: 'output-run-simulation-parameters',
  },
};

export const PipelineStudio: React.FC<PipelineStudioProps> = ({
  demonstrators,
  demonstrator,
  config,
  parameters,
  hasUnsavedChanges,
  validationError,
  saving,
  onSelectDemonstrator,
  onOpenNewDemonstrator,
  onRenameDemonstrator,
  onDeleteDemonstrator,
  onConfigChange,
  onParametersChange,
  onSaveAll,
  onRunSimulation,
  onGenerateDemoMatrices,
  onUploadMatrix,
  onSavePreset,
  onSelectPreset,
  onDeletePreset,
  onOpenWiki,
}) => {
  const [activeStage, setActiveStage] = useState<number | 'all'>('all');
  const [showJsonModal, setShowJsonModal] = useState(false);
  const [newPresetName, setNewPresetName] = useState('');
  const [showPresetModal, setShowPresetModal] = useState(false);
  const [generatingMatrices, setGeneratingMatrices] = useState(false);

  // Rename & Delete Demonstrator Modal State
  const [showRenameModal, setShowRenameModal] = useState(false);
  const [renameValue, setRenameValue] = useState('');
  const [showDeleteDemModal, setShowDeleteDemModal] = useState(false);

  // Diff / Compare Configs Modal State
  const [showDiffModal, setShowDiffModal] = useState(false);
  const [compareDemId, setCompareDemId] = useState<string>(
    demonstrators.find((d) => d.id !== demonstrator.id)?.id || demonstrator.id
  );
  const [comparePresetFile, setComparePresetFile] = useState<string>('simulation_parameters.json');
  const [compareParams, setCompareParams] = useState<SimulationParameters | null>(null);
  const [onlyDiffs, setOnlyDiffs] = useState(false);
  const [loadingCompare, setLoadingCompare] = useState(false);

  // Dry-Run Coarsening Trajectory Preview State
  const [coarseningPreview, setCoarseningPreview] = useState<CoarseningPreviewResponse | null>(null);
  const [previewingCoarsening, setPreviewingCoarsening] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);

  useEffect(() => {
    setCoarseningPreview(null);
    setPreviewError(null);
  }, [demonstrator.id]);

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

  const handleRunCoarseningPreview = async () => {
    setPreviewingCoarsening(true);
    setPreviewError(null);
    try {
      const res = await api.previewCoarsening(demonstrator.id, parameters);
      setCoarseningPreview(res);
    } catch (err: any) {
      setPreviewError(err.message || 'Coarsening preview failed');
    } finally {
      setPreviewingCoarsening(false);
    }
  };

  const gp = parameters.general_parameters;
  const cp = parameters.coarsening_parameters;
  const pp = parameters.partitioning_parameters;
  const up = parameters.uncoarsening_parameters;

  const activeStrategy = pp.partitioning_strategy;
  const qaParams: QuantumAnnealingParams = pp.strategies.quantum_annealing || {
    qubo_balance_lambda: 2.0,
    num_starts: 20,
    num_reads: 20,
    balance_violation_lambda: 1e6,
    simulated: true,
    qpu_region: 'eu-central-1',
    qpu_solver_name: 'Advantage2_system2.1',
    qpu_problem_label: 'DD_ansys_run',
  };
  const qaoaParams: QAOAParams = pp.strategies.quantum_approximation_optimizer || {
    qubo_balance_lambda: 2.0,
    num_starts: 5,
    num_steps: 5,
    num_shots: 5,
    balance_violation_lambda: 1e6,
    circuit_depth: 1,
    adam_learning_rate: 0.1,
    simulated: true,
    qlm_qpu_name: 'qat.qpus:QSolidQPU10',
  };

  const currentSimulated =
    activeStrategy === 'quantum_annealing'
      ? qaParams.simulated
      : activeStrategy === 'quantum_approximation_optimizer'
      ? qaoaParams.simulated
      : true;

  const selectPartitionMethod = (strategy: PartitioningStrategyKey, simulated?: boolean) => {
    const nextStrategies = { ...pp.strategies };
    if (strategy === 'quantum_annealing' && simulated !== undefined) {
      nextStrategies.quantum_annealing = {
        ...qaParams,
        simulated,
      };
    } else if (strategy === 'quantum_approximation_optimizer' && simulated !== undefined) {
      nextStrategies.quantum_approximation_optimizer = {
        ...qaoaParams,
        simulated,
        adam_learning_rate: qaoaParams.adam_learning_rate ?? 0.1,
        qlm_qpu_name: qaoaParams.qlm_qpu_name || 'qat.qpus:QSolidQPU10',
      };
    }

    onParametersChange({
      ...parameters,
      partitioning_parameters: {
        ...pp,
        partitioning_strategy: strategy,
        strategies: nextStrategies,
      },
    });
  };

  // Live Quantum Estimations
  const bipartitionsPerStart = Math.max(1, (pp.common.k_target || 2) - 1);
  const expectedQaSubmissions = Math.max(1, qaParams.num_starts || 1) * bipartitionsPerStart;
  const expectedQaReads = expectedQaSubmissions * Math.max(1, qaParams.num_reads || 1);
  const expectedQaoaJobs =
    Math.max(1, qaoaParams.num_starts || 1) *
    bipartitionsPerStart *
    (Math.max(1, qaoaParams.num_steps || 1) + 1);

  const inferredGraphNodes =
    demonstrator.matrices.matrix_k.rows && gp.dof_per_node > 0
      ? Math.floor(demonstrator.matrices.matrix_k.rows / gp.dof_per_node)
      : null;

  const handleGenerateMatrices = async (preset: 'small' | 'medium' | 'large') => {
    setGeneratingMatrices(true);
    try {
      await onGenerateDemoMatrices(preset);
    } finally {
      setGeneratingMatrices(false);
    }
  };

  return (
    <div className="space-y-6 min-w-0">
      {/* Interactive Visual Pipeline Architecture & Active Simulation Selector */}
      <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-5 shadow-xl overflow-hidden">
        {/* Active Simulation Switcher Bar */}
        <div className="flex flex-wrap items-center justify-between gap-4 pb-4 mb-4 border-b border-slate-800/80">
          <div className="flex flex-wrap items-center gap-2.5 min-w-0">
            <div className="flex flex-wrap items-center gap-1.5 bg-slate-950 p-1 rounded-xl border border-slate-800">
              {demonstrators.map((dem) => {
                const active = dem.id === demonstrator.id;
                const strat =
                  dem.simulation_parameters.partitioning_parameters.partitioning_strategy;
                const stratShort =
                  strat === 'metis_partitioning'
                    ? 'METIS'
                    : strat === 'quantum_annealing'
                    ? 'QA'
                    : 'QAOA';
                return (
                  <button
                    key={dem.id}
                    type="button"
                    onClick={() => onSelectDemonstrator(dem)}
                    className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition flex items-center gap-2 ${
                      active
                        ? 'bg-indigo-600 text-white shadow'
                        : 'text-slate-400 hover:text-white hover:bg-slate-800'
                    }`}
                  >
                    <span>{dem.id}</span>
                    <span
                      className={`text-[10px] font-mono px-1.5 py-0.2 rounded ${
                        active ? 'bg-indigo-800 text-indigo-100' : 'bg-slate-800 text-slate-400'
                      }`}
                    >
                      {stratShort}
                    </span>
                  </button>
                );
              })}

              <button
                type="button"
                onClick={onOpenNewDemonstrator}
                className="px-2.5 py-1.5 rounded-lg text-xs font-medium text-indigo-400 hover:bg-slate-800 flex items-center gap-1"
                title="Create or clone a demonstrator"
              >
                <FolderPlus className="w-3.5 h-3.5" />
                New
              </button>
            </div>

            {/* Rename & Delete Active Demonstrator Actions */}
            <div className="flex items-center gap-1">
              <button
                type="button"
                onClick={() => {
                  setRenameValue(demonstrator.id);
                  setShowRenameModal(true);
                }}
                className="p-1.5 rounded-lg text-slate-400 hover:text-indigo-300 hover:bg-slate-800 border border-transparent hover:border-slate-700 transition"
                title={`Rename ${demonstrator.id}`}
              >
                <Edit3 className="w-3.5 h-3.5" />
              </button>
              {demonstrators.length > 1 && (
                <button
                  type="button"
                  onClick={() => setShowDeleteDemModal(true)}
                  className="p-1.5 rounded-lg text-slate-400 hover:text-rose-400 hover:bg-rose-950/40 border border-transparent hover:border-rose-500/30 transition"
                  title={`Delete ${demonstrator.id}`}
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              )}
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <button
              onClick={() => {
                const otherDem =
                  demonstrators.find((d) => d.id !== demonstrator.id) || demonstrator;
                setCompareDemId(otherDem.id);
                setComparePresetFile(otherDem.active_parameters_file || 'simulation_parameters.json');
                setShowDiffModal(true);
              }}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-slate-800 text-slate-200 hover:bg-slate-700 border border-slate-700 transition"
              title="Compare active parameters against another preset or demonstrator"
            >
              <ArrowLeftRight className="w-3.5 h-3.5 text-amber-400" />
              Compare Configs
            </button>
            <button
              onClick={() => setShowPresetModal(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-slate-800 text-slate-200 hover:bg-slate-700 border border-slate-700 transition"
            >
              <FolderPlus className="w-3.5 h-3.5 text-indigo-400" />
              Save as Preset
            </button>
            <button
              onClick={() => setShowJsonModal(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-slate-800 text-slate-200 hover:bg-slate-700 border border-slate-700 transition"
            >
              <Code2 className="w-3.5 h-3.5 text-cyan-400" />
              Inspect JSON
            </button>
          </div>
        </div>

        {/* 5-Stage Visual Flowchart */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
          {[
            {
              n: 1,
              label: 'Input Matrices',
              wiki: 'stage-1',
              Icon: Database,
              iconClass: 'text-emerald-400',
              value: demonstrator.matrices.ready
                ? `K & M ready${inferredGraphNodes !== null ? ` · ${inferredGraphNodes.toLocaleString()} nodes` : ''}`
                : 'Missing .mtx',
              valueClass: demonstrator.matrices.ready ? 'text-emerald-300' : 'text-amber-400',
            },
            {
              n: 2,
              label: 'Coarsening',
              wiki: 'stage-2',
              Icon: Layers,
              iconClass: 'text-amber-400',
              value: `${cp.strategy} · [${cp.coarsen_inferior_limit}–${cp.coarsen_superior_limit ?? '∞'}]`,
              valueClass: 'text-amber-300',
            },
            {
              n: 3,
              label: 'Partitioning',
              wiki: 'stage-3',
              Icon: Cpu,
              iconClass: 'text-violet-400',
              value: `${
                activeStrategy === 'metis_partitioning'
                  ? 'METIS'
                  : activeStrategy === 'quantum_annealing'
                  ? currentSimulated
                    ? 'QA Emulated'
                    : 'QA QPU'
                  : currentSimulated
                  ? 'QAOA Emulated'
                  : 'QAOA QLM'
              } · k=${pp.common.k_target}`,
              valueClass: 'text-violet-300',
            },
            {
              n: 4,
              label: 'Refinement',
              wiki: 'stage-4',
              Icon: GitBranch,
              iconClass: 'text-cyan-400',
              value: up.refine_objective === 'cut' ? 'Cut' : 'Cut + Balance',
              valueClass: 'text-cyan-300',
            },
            {
              n: 5,
              label: 'Outputs',
              wiki: 'stage-5',
              Icon: Activity,
              iconClass: 'text-rose-400',
              value: `${config.save_output.length} / ${demonstrator.available_save_outputs.length} artifacts`,
              valueClass: 'text-rose-300',
            },
          ].map((stage) => {
            const isOpen = activeStage === stage.n;
            const StageIcon = stage.Icon;
            return (
              <button
                key={stage.n}
                onClick={() => setActiveStage(isOpen ? 'all' : stage.n)}
                className={`text-left p-3.5 rounded-xl border transition-all min-w-0 overflow-hidden ${
                  isOpen
                    ? 'bg-indigo-950/60 border-indigo-500 ring-2 ring-indigo-500/30'
                    : 'bg-slate-950/70 border-slate-800 hover:border-slate-700'
                }`}
              >
                <div className="flex items-center justify-between gap-2 mb-1.5">
                  <div className="flex items-center gap-2 min-w-0">
                    <StageIcon className={`w-4 h-4 shrink-0 ${stage.iconClass}`} />
                    <span className="font-semibold text-xs text-white truncate">
                      {stage.label}
                    </span>
                  </div>
                  <InfoTooltip topicId={stage.wiki} onOpenWiki={onOpenWiki} />
                </div>
                <div
                  className={`text-[11px] font-mono truncate ${stage.valueClass}`}
                  title={stage.value}
                >
                  {stage.value}
                </div>
              </button>
            );
          })}
        </div>

        {/* Validation Error Alert */}
        {validationError && (
          <div className="mt-4 p-3 rounded-xl bg-rose-950/60 border border-rose-500/50 flex items-center gap-2.5 text-xs text-rose-200">
            <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0" />
            <span className="break-words">
              <strong>Parameter Validation Error:</strong> {validationError}
            </span>
          </div>
        )}
      </div>

      {/* STAGE 1: FEM INPUT MATRICES & INITIALIZATION */}
      {(activeStage === 'all' || activeStage === 1) && (
        <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-6 shadow-lg overflow-hidden">
          <div className="flex flex-wrap items-center justify-between gap-4 pb-4 border-b border-slate-800">
            <div className="flex items-center gap-3 min-w-0">
              <div className="w-8 h-8 rounded-xl bg-emerald-500/15 border border-emerald-500/30 flex items-center justify-center text-emerald-400 font-bold text-sm shrink-0">
                1
              </div>
              <h3 className="text-base font-bold text-white truncate">
                Input Matrices
              </h3>
              <InfoTooltip topicId="stage-1" onOpenWiki={onOpenWiki} />
            </div>

            {/* Preset Switcher */}
            <div className="flex items-center gap-2 min-w-0 max-w-full">
              <span className="text-xs text-slate-400 shrink-0">Parameters File:</span>
              <InfoTooltip topicId="param-preset-file" onOpenWiki={onOpenWiki} />
              <select
                value={config.parameters_file_path}
                onChange={(e) => onSelectPreset(e.target.value)}
                className="bg-slate-950 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-slate-100 focus:border-indigo-500 focus:outline-none max-w-[220px] truncate"
              >
                {demonstrator.preset_files.map((pf) => (
                  <option key={pf} value={pf}>
                    {pf}
                  </option>
                ))}
              </select>
              {config.parameters_file_path !== 'simulation_parameters.json' && (
                <button
                  type="button"
                  onClick={() => onDeletePreset(config.parameters_file_path)}
                  className="p-1.5 rounded-lg text-slate-400 hover:text-rose-400 hover:bg-rose-950/40 border border-slate-800 hover:border-rose-500/30 transition shrink-0"
                  title={`Delete custom preset ${config.parameters_file_path}`}
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              )}
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-5 mt-5">
            {/* Matrix K & M Selector */}
            <div className="lg:col-span-2 space-y-4 min-w-0">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <MatrixFileCard
                  label="Stiffness Matrix (K)"
                  labelClass="text-indigo-400"
                  wikiId="param-matrix-k"
                  info={demonstrator.matrices.matrix_k}
                  value={config.input_matrices.matrix_k_file_path}
                  availableFiles={demonstrator.matrices.available_files.map((f) => f.filename)}
                  placeholder="Ksparse_...mtx"
                  onOpenWiki={onOpenWiki}
                  onChange={(next) =>
                    onConfigChange({
                      ...config,
                      input_matrices: { ...config.input_matrices, matrix_k_file_path: next },
                    })
                  }
                />
                <MatrixFileCard
                  label="Mass Matrix (M)"
                  labelClass="text-cyan-400"
                  wikiId="param-matrix-m"
                  info={demonstrator.matrices.matrix_m}
                  value={config.input_matrices.matrix_m_file_path}
                  availableFiles={demonstrator.matrices.available_files.map((f) => f.filename)}
                  placeholder="Msparse_...mtx"
                  onOpenWiki={onOpenWiki}
                  onChange={(next) =>
                    onConfigChange({
                      ...config,
                      input_matrices: { ...config.input_matrices, matrix_m_file_path: next },
                    })
                  }
                />
              </div>

              {/* Matrix Upload & Synthetic 3D FEM Mesh Generator */}
              <div className="flex flex-wrap items-center gap-2">
                <div className="flex flex-wrap items-center gap-2">
                  <InfoTooltip topicId="stage-1-mtx-tools" onOpenWiki={onOpenWiki} />
                  <label className="cursor-pointer inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 transition">
                    <Upload className="w-3.5 h-3.5 text-cyan-400" />
                    Upload .mtx
                    <input
                      type="file"
                      accept=".mtx"
                      className="hidden"
                      onChange={(e) => {
                        const file = e.target.files?.[0];
                        if (file) onUploadMatrix(file);
                      }}
                    />
                  </label>
                  <button
                    disabled={generatingMatrices}
                    onClick={() => handleGenerateMatrices('small')}
                    className={`px-3 py-1.5 rounded-lg text-xs font-medium transition disabled:opacity-50 ${
                      inferredGraphNodes === 240
                        ? 'bg-indigo-600 hover:bg-indigo-500 text-white shadow'
                        : 'bg-slate-800 hover:bg-slate-700 text-indigo-300 border border-indigo-500/30'
                    }`}
                  >
                    {generatingMatrices ? 'Generating...' : 'Demo Mesh (240)'}
                  </button>
                  <button
                    disabled={generatingMatrices}
                    onClick={() => handleGenerateMatrices('large')}
                    className={`px-3 py-1.5 rounded-lg text-xs font-medium transition disabled:opacity-50 ${
                      inferredGraphNodes === 600
                        ? 'bg-indigo-600 hover:bg-indigo-500 text-white shadow'
                        : 'bg-slate-800 hover:bg-slate-700 text-indigo-300 border border-indigo-500/30'
                    }`}
                  >
                    {generatingMatrices ? 'Generating...' : 'Large Mesh (600)'}
                  </button>
                </div>
              </div>
            </div>

            {/* General Parameters */}
            <div className="p-4 rounded-xl bg-slate-950/80 border border-slate-800 space-y-4 min-w-0 overflow-hidden">
              <div>
                <div className="flex items-center justify-between gap-2 mb-1.5">
                  <label className="text-xs font-medium text-slate-300 flex items-center gap-1.5">
                    <span>DOFs per Node</span>
                    <InfoTooltip topicId="param-dof-per-node" onOpenWiki={onOpenWiki} />
                  </label>
                  {inferredGraphNodes !== null && (
                    <span className="text-[11px] font-mono text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded">
                      G₀: {inferredGraphNodes.toLocaleString()} nodes
                    </span>
                  )}
                </div>
                <input
                  type="number"
                  min={1}
                  max={12}
                  value={gp.dof_per_node}
                  onChange={(e) =>
                    onParametersChange({
                      ...parameters,
                      general_parameters: {
                        ...gp,
                        dof_per_node: Math.max(1, parseInt(e.target.value || '1', 10)),
                      },
                    })
                  }
                  className="w-full min-w-0 bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm font-mono text-white"
                />
              </div>

              <div>
                <label className="text-xs font-medium text-slate-300 flex items-center gap-1.5 mb-1.5">
                  <span>Seed</span>
                  <InfoTooltip topicId="param-seed" onOpenWiki={onOpenWiki} />
                </label>
                <input
                  type="number"
                  value={gp.seed}
                  onChange={(e) =>
                    onParametersChange({
                      ...parameters,
                      general_parameters: {
                        ...gp,
                        seed: parseInt(e.target.value || '42', 10),
                      },
                    })
                  }
                  className="w-full min-w-0 bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm font-mono text-white"
                />
              </div>
            </div>
          </div>
        </div>
      )}

      {/* STAGE 2: MULTILEVEL COARSENING (HEAVY EDGE MATCHING) */}
      {(activeStage === 'all' || activeStage === 2) && (
        <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-6 shadow-lg overflow-hidden">
          <div className="flex flex-wrap items-center justify-between gap-4 pb-4 border-b border-slate-800">
            <div className="flex items-center gap-3 min-w-0">
              <div className="w-8 h-8 rounded-xl bg-amber-500/15 border border-amber-500/30 flex items-center justify-center text-amber-400 font-bold text-sm shrink-0">
                2
              </div>
              <h3 className="text-base font-bold text-white truncate">
                Coarsening
              </h3>
              <InfoTooltip topicId="stage-2" onOpenWiki={onOpenWiki} />
            </div>

            {/* Quick Scale Preset Buttons */}
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs text-slate-400">Scale:</span>
              {COARSENING_SCALE_PRESETS.map((preset) => {
                const isSelected =
                  cp.coarsen_inferior_limit === preset.inferior &&
                  cp.coarsen_superior_limit === preset.superior;
                return (
                  <button
                    key={preset.key}
                    onClick={() =>
                      onParametersChange({
                        ...parameters,
                        coarsening_parameters: {
                          ...cp,
                          coarsen_inferior_limit: preset.inferior,
                          coarsen_superior_limit: preset.superior,
                        },
                      })
                    }
                    className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition ${
                      isSelected
                        ? 'bg-amber-500/20 border-amber-400 text-amber-200'
                        : 'bg-slate-950 border-slate-800 text-slate-300 hover:border-slate-700'
                    }`}
                    title={preset.desc}
                  >
                    {preset.label}
                  </button>
                );
              })}
            </div>
          </div>

          {/* 4 HEM Strategy Cards */}
          <div className="mt-5">
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3.5">
              {COARSENING_STRATEGIES.map((item) => {
                const active = cp.strategy === item.key;
                return (
                  <button
                    key={item.key}
                    type="button"
                    onClick={() =>
                      onParametersChange({
                        ...parameters,
                        coarsening_parameters: {
                          ...cp,
                          strategy: item.key,
                        },
                      })
                    }
                    className={`text-left p-3.5 rounded-xl border transition-all flex items-center justify-between gap-2 min-w-0 overflow-hidden ${
                      active
                        ? 'bg-amber-950/30 border-amber-500 ring-2 ring-amber-500/20'
                        : 'bg-slate-950/70 border-slate-800 hover:border-slate-700'
                    }`}
                  >
                    <span className="font-bold text-sm text-white truncate">{item.title}</span>
                    <InfoTooltip topicId={item.wikiId} onOpenWiki={onOpenWiki} />
                  </button>
                );
              })}
            </div>
          </div>

          {/* Coarsening Numeric Parameters */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4 mt-5 pt-4 border-t border-slate-800/80">
            <div className="min-w-0">
              <label className="text-xs font-medium text-slate-300 flex items-center gap-1.5 mb-1.5">
                <span className="truncate">Inferior Node Limit</span>
                <InfoTooltip topicId="param-coarsen-inferior" onOpenWiki={onOpenWiki} />
              </label>
              <input
                type="number"
                min={1}
                value={cp.coarsen_inferior_limit}
                onChange={(e) =>
                  onParametersChange({
                    ...parameters,
                    coarsening_parameters: {
                      ...cp,
                      coarsen_inferior_limit: Math.max(1, parseInt(e.target.value || '1', 10)),
                    },
                  })
                }
                className="w-full min-w-0 bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm font-mono text-white"
              />
            </div>

            <div className="min-w-0">
              <label className="text-xs font-medium text-slate-300 flex items-center gap-1.5 mb-1.5">
                <span className="truncate">Superior Node Limit</span>
                <InfoTooltip topicId="param-coarsen-superior" onOpenWiki={onOpenWiki} />
              </label>
              <input
                type="number"
                min={cp.coarsen_inferior_limit}
                value={cp.coarsen_superior_limit ?? ''}
                placeholder="No upper bound"
                onChange={(e) => {
                  const raw = e.target.value.trim();
                  onParametersChange({
                    ...parameters,
                    coarsening_parameters: {
                      ...cp,
                      coarsen_superior_limit: raw === '' ? null : parseInt(raw, 10),
                    },
                  });
                }}
                className="w-full min-w-0 bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm font-mono text-white"
              />
            </div>

            <div className="min-w-0">
              <label className="text-xs font-medium text-slate-300 flex items-center gap-1.5 mb-1.5">
                <span className="truncate">Max Levels</span>
                <InfoTooltip topicId="param-max-levels" onOpenWiki={onOpenWiki} />
              </label>
              <input
                type="number"
                min={1}
                max={100}
                value={cp.max_levels}
                onChange={(e) =>
                  onParametersChange({
                    ...parameters,
                    coarsening_parameters: {
                      ...cp,
                      max_levels: Math.max(1, parseInt(e.target.value || '15', 10)),
                    },
                  })
                }
                className="w-full min-w-0 bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm font-mono text-white"
              />
            </div>

            <div className="min-w-0">
              <label className="text-xs font-medium text-slate-300 flex items-center gap-1.5 mb-1.5">
                <span className="truncate">Coarsen Ratio</span>
                <InfoTooltip topicId="param-coarsen-ratio" onOpenWiki={onOpenWiki} />
              </label>
              <input
                type="number"
                step="0.01"
                min={0.1}
                max={1.0}
                value={cp.coarsen_ratio}
                onChange={(e) =>
                  onParametersChange({
                    ...parameters,
                    coarsening_parameters: {
                      ...cp,
                      coarsen_ratio: parseFloat(e.target.value || '0.85'),
                    },
                  })
                }
                className="w-full min-w-0 bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm font-mono text-white"
              />
            </div>

            <div className="min-w-0">
              <label className="text-xs font-medium text-slate-300 flex items-center gap-1.5 mb-1.5">
                <span className="truncate">Max Node Weight</span>
                <InfoTooltip topicId="param-max-node-weight" onOpenWiki={onOpenWiki} />
              </label>
              <input
                type="number"
                step="any"
                value={cp.max_node_weight ?? ''}
                placeholder="Auto"
                onChange={(e) => {
                  const raw = e.target.value.trim();
                  onParametersChange({
                    ...parameters,
                    coarsening_parameters: {
                      ...cp,
                      max_node_weight: raw === '' ? null : parseFloat(raw),
                    },
                  });
                }}
                className="w-full min-w-0 bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm font-mono text-white"
              />
            </div>
          </div>

          {/* Interactive Coarsening Trajectory Preview ("Dry-Run Coarsening") */}
          <div className="mt-5 pt-4 border-t border-slate-800/80 space-y-3">
            <div className="flex flex-wrap items-center justify-end gap-2">
              <InfoTooltip topicId="tool-dry-run-coarsening" onOpenWiki={onOpenWiki} />
              <button
                type="button"
                disabled={previewingCoarsening || !demonstrator.matrices.matrix_k.exists}
                onClick={handleRunCoarseningPreview}
                className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl text-xs font-semibold bg-amber-500/20 hover:bg-amber-500/30 text-amber-200 border border-amber-500/40 transition disabled:opacity-50"
              >
                <RefreshCw
                  className={`w-3.5 h-3.5 ${previewingCoarsening ? 'animate-spin' : ''}`}
                />
                {previewingCoarsening ? 'Previewing...' : 'Preview Coarsening'}
              </button>
            </div>

            {previewError && (
              <div className="p-3 rounded-xl bg-rose-950/50 border border-rose-500/40 text-xs text-rose-200 flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0" />
                <span>{previewError}</span>
              </div>
            )}

            {coarseningPreview && (
              <div className="p-4 rounded-xl bg-slate-950/90 border border-slate-800 space-y-3">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <span
                      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold border ${
                        coarseningPreview.reachable
                          ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30'
                          : 'bg-amber-500/15 text-amber-300 border-amber-500/30'
                      }`}
                    >
                      {coarseningPreview.reachable ? (
                        <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                      ) : (
                        <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />
                      )}
                      {coarseningPreview.reachable
                        ? 'Target Range Reached'
                        : 'Stopped Above Superior Limit'}
                    </span>

                    <span className="text-xs text-slate-300 bg-slate-900 px-2.5 py-1 rounded-lg border border-slate-800 font-mono">
                      Final G_{coarseningPreview.accepted_levels_count}:{' '}
                      <strong className="text-amber-300">
                        {coarseningPreview.final_coarse_nodes.toLocaleString()} nodes
                      </strong>{' '}
                      ({coarseningPreview.final_coarse_edges.toLocaleString()} edges)
                    </span>

                    <span className="text-[11px] text-slate-400 bg-slate-900 px-2.5 py-1 rounded-lg border border-slate-800">
                      Stop: <strong className="text-slate-200">{coarseningPreview.stop_reason}</strong>
                    </span>
                  </div>

                  <span className="text-[11px] font-mono text-slate-500">
                    {coarseningPreview.elapsed_ms} ms
                  </span>
                </div>

                {/* Horizontal Level Step Chain */}
                <div className="overflow-x-auto pb-1">
                  <div className="flex items-stretch gap-2 min-w-max">
                    {coarseningPreview.levels.map((lvl) => (
                      <div
                        key={lvl.level}
                        title={`Max w(v): ${lvl.max_node_weight}`}
                        className={`p-2.5 rounded-xl border text-xs min-w-[130px] flex flex-col justify-between ${
                          !lvl.accepted
                            ? 'bg-rose-950/20 border-rose-500/30 opacity-75'
                            : lvl.level === coarseningPreview.accepted_levels_count
                            ? 'bg-amber-950/30 border-amber-500/50 ring-1 ring-amber-500/30'
                            : 'bg-slate-900/90 border-slate-800'
                        }`}
                      >
                        <div className="flex items-center justify-between gap-2 mb-1">
                          <span className="font-mono font-bold text-white">G_{lvl.level}</span>
                          <span
                            className={`text-[10px] px-1.5 py-0.2 rounded font-mono ${
                              !lvl.accepted
                                ? 'bg-rose-500/20 text-rose-300'
                                : lvl.level === coarseningPreview.accepted_levels_count
                                ? 'bg-amber-500/20 text-amber-300'
                                : 'bg-slate-800 text-slate-400'
                            }`}
                          >
                            {lvl.level === 0
                              ? 'Fine Mesh'
                              : !lvl.accepted
                              ? 'Rejected'
                              : `r=${lvl.ratio}`}
                          </span>
                        </div>
                        <div className="space-y-0.5 text-[11px]">
                          <div className="flex justify-between text-slate-300">
                            <span className="text-slate-500">Nodes:</span>
                            <span className="font-mono font-semibold text-white">
                              {lvl.nodes.toLocaleString()}
                            </span>
                          </div>
                          <div className="flex justify-between text-slate-300">
                            <span className="text-slate-500">Edges:</span>
                            <span className="font-mono">{lvl.edges.toLocaleString()}</span>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* STAGE 3: COARSE GRAPH PARTITIONING */}
      {(activeStage === 'all' || activeStage === 3) && (
        <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-6 shadow-lg overflow-hidden">
          <div className="flex flex-wrap items-center justify-between gap-4 pb-4 border-b border-slate-800">
            <div className="flex items-center gap-3 min-w-0">
              <div className="w-8 h-8 rounded-xl bg-violet-500/15 border border-violet-500/30 flex items-center justify-center text-violet-400 font-bold text-sm shrink-0">
                3
              </div>
              <h3 className="text-base font-bold text-white truncate">
                Partitioning
              </h3>
              <InfoTooltip topicId="stage-3" onOpenWiki={onOpenWiki} />
            </div>

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
                          ? 'bg-violet-600 text-white'
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
          </div>

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
                    onClick={() => selectPartitionMethod(m.strategy, m.simulated)}
                    className={`text-left p-3.5 rounded-xl border transition-all flex flex-col justify-between min-w-0 overflow-hidden ${
                      isSelected
                        ? 'bg-violet-950/40 border-violet-500 ring-2 ring-violet-500/30 shadow-lg'
                        : 'bg-slate-950/70 border-slate-800 hover:border-slate-700'
                    }`}
                  >
                    <div className="flex items-center justify-between gap-1.5 mb-2">
                      <span
                        className={`text-[10px] px-2 py-0.5 rounded-full font-semibold truncate ${
                          m.category === 'Classical'
                            ? 'bg-emerald-500/15 text-emerald-300 border border-emerald-500/30'
                            : m.category === 'Quantum Hardware'
                            ? 'bg-fuchsia-500/15 text-fuchsia-300 border border-fuchsia-500/30'
                            : 'bg-cyan-500/15 text-cyan-300 border border-cyan-500/30'
                        }`}
                      >
                        {m.category}
                      </span>
                      <div className="flex items-center gap-1 shrink-0">
                        {isSelected && <CheckCircle2 className="w-3.5 h-3.5 text-violet-400" />}
                        <InfoTooltip topicId={m.wikiId} onOpenWiki={onOpenWiki} />
                      </div>
                    </div>
                    <div className="font-bold text-sm text-white truncate" title={m.title}>
                      {m.title}
                    </div>
                  </button>
                );
              })}
            </div>
          </div>

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
                        QPU Jobs: <strong className="text-violet-300 font-mono">{expectedQaSubmissions}</strong>
                      </span>
                      <span className="text-slate-600">|</span>
                      <span className="text-slate-400">
                        Total Reads: <strong className="text-cyan-300 font-mono">{expectedQaReads.toLocaleString()}</strong>
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
                    <div className="p-4 rounded-xl bg-violet-950/30 border border-violet-500/30 grid grid-cols-1 md:grid-cols-3 gap-4">
                      <div className="min-w-0">
                        <label className="text-xs font-medium text-violet-200 flex items-center gap-1.5 mb-1.5">
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
                        <label className="text-xs font-medium text-violet-200 flex items-center gap-1.5 mb-1.5">
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
                        <label className="text-xs font-medium text-violet-200 flex items-center gap-1.5 mb-1.5">
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
                        Circuit Evaluations: <strong className="text-cyan-300 font-mono">{expectedQaoaJobs}</strong>
                      </span>
                      <span className="text-slate-600">|</span>
                      <span className="text-slate-400">
                        Total Shots:{' '}
                        <strong className="text-violet-300 font-mono">
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
                        <label className="text-xs font-medium text-cyan-200 flex items-center gap-1.5 mb-1.5">
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
                        <label className="text-xs font-medium text-fuchsia-200 flex items-center gap-1.5 mb-1.5">
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
                          className="w-full min-w-0 bg-slate-950 border border-fuchsia-500/40 rounded-lg px-3 py-2 text-sm font-mono text-white"
                        />
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* STAGE 4: UNCOARSENING & REFINEMENT */}
      {(activeStage === 'all' || activeStage === 4) && (
        <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-6 shadow-lg overflow-hidden">
          <div className="flex items-center gap-3 pb-4 border-b border-slate-800 min-w-0">
            <div className="w-8 h-8 rounded-xl bg-cyan-500/15 border border-cyan-500/30 flex items-center justify-center text-cyan-400 font-bold text-sm shrink-0">
              4
            </div>
            <h3 className="text-base font-bold text-white truncate">
              Refinement
            </h3>
            <InfoTooltip topicId="stage-4" onOpenWiki={onOpenWiki} />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-5">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5">
              <button
                type="button"
                onClick={() =>
                  onParametersChange({
                    ...parameters,
                    uncoarsening_parameters: {
                      ...up,
                      refine_objective: 'cut',
                    },
                  })
                }
                className={`text-left p-4 rounded-xl border transition min-w-0 overflow-hidden flex items-center justify-between gap-2 ${
                  up.refine_objective === 'cut'
                    ? 'bg-cyan-950/40 border-cyan-500 ring-2 ring-cyan-500/20'
                    : 'bg-slate-950/70 border-slate-800 hover:border-slate-700'
                }`}
              >
                <span className="font-bold text-sm text-white truncate">
                  Cut
                </span>
                <InfoTooltip topicId="method-refine-cut" onOpenWiki={onOpenWiki} />
              </button>

              <button
                type="button"
                onClick={() =>
                  onParametersChange({
                    ...parameters,
                    uncoarsening_parameters: {
                      ...up,
                      refine_objective: 'cut_balance',
                    },
                  })
                }
                className={`text-left p-4 rounded-xl border transition min-w-0 overflow-hidden flex items-center justify-between gap-2 ${
                  up.refine_objective === 'cut_balance'
                    ? 'bg-cyan-950/40 border-cyan-500 ring-2 ring-cyan-500/20'
                    : 'bg-slate-950/70 border-slate-800 hover:border-slate-700'
                }`}
              >
                <span className="font-bold text-sm text-white truncate">
                  Cut + Balance
                </span>
                <InfoTooltip topicId="method-refine-cut-balance" onOpenWiki={onOpenWiki} />
              </button>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div className="min-w-0">
                <label className="text-xs font-medium text-slate-300 flex items-center gap-1.5 mb-1.5">
                  <span className="truncate">Refine Balance λ</span>
                  <InfoTooltip topicId="param-refine-balance-lambda" onOpenWiki={onOpenWiki} />
                </label>
                <input
                  type="number"
                  step="0.1"
                  min={0}
                  value={up.refine_balance_lambda}
                  onChange={(e) =>
                    onParametersChange({
                      ...parameters,
                      uncoarsening_parameters: {
                        ...up,
                        refine_balance_lambda: Math.max(0, parseFloat(e.target.value || '0')),
                      },
                    })
                  }
                  className="w-full min-w-0 bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm font-mono text-white"
                />
              </div>

              <div className="min-w-0">
                <label className="text-xs font-medium text-slate-300 flex items-center gap-1.5 mb-1.5">
                  <span className="truncate">Max Passes / Lvl</span>
                  <InfoTooltip topicId="param-refine-max-passes" onOpenWiki={onOpenWiki} />
                </label>
                <input
                  type="number"
                  min={0}
                  value={up.refine_max_passes_per_level}
                  onChange={(e) =>
                    onParametersChange({
                      ...parameters,
                      uncoarsening_parameters: {
                        ...up,
                        refine_max_passes_per_level: Math.max(0, parseInt(e.target.value || '0', 10)),
                      },
                    })
                  }
                  className="w-full min-w-0 bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm font-mono text-white"
                />
              </div>

              <div className="min-w-0">
                <label className="text-xs font-medium text-slate-300 flex items-center gap-1.5 mb-1.5">
                  <span className="truncate">Max Moves / Pass</span>
                  <InfoTooltip topicId="param-refine-max-moves" onOpenWiki={onOpenWiki} />
                </label>
                <input
                  type="number"
                  min={1}
                  value={up.refine_max_moves_per_pass ?? ''}
                  placeholder="Unlimited"
                  onChange={(e) => {
                    const raw = e.target.value.trim();
                    onParametersChange({
                      ...parameters,
                      uncoarsening_parameters: {
                        ...up,
                        refine_max_moves_per_pass: raw === '' ? null : Math.max(1, parseInt(raw, 10)),
                      },
                    });
                  }}
                  className="w-full min-w-0 bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm font-mono text-white"
                />
              </div>
            </div>
          </div>
        </div>
      )}

      {/* STAGE 5: MATRIX PERMUTATION & OUTPUT ARTIFACTS */}
      {(activeStage === 'all' || activeStage === 5) && (
        <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-6 shadow-lg overflow-hidden">
          <div className="flex flex-wrap items-center justify-between gap-4 pb-4 border-b border-slate-800">
            <div className="flex items-center gap-3 min-w-0">
              <div className="w-8 h-8 rounded-xl bg-rose-500/15 border border-rose-500/30 flex items-center justify-center text-rose-400 font-bold text-sm shrink-0">
                5
              </div>
              <h3 className="text-base font-bold text-white truncate">
                Outputs
              </h3>
              <InfoTooltip topicId="stage-5" onOpenWiki={onOpenWiki} />
            </div>

            <button
              type="button"
              onClick={() =>
                onConfigChange({
                  ...config,
                  save_output: [...demonstrator.available_save_outputs],
                })
              }
              className="text-xs text-indigo-400 hover:text-indigo-300 font-medium"
            >
              Select All
            </button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3.5 mt-5">
            {demonstrator.available_save_outputs.map((key) => {
              const checked = config.save_output.includes(key);
              const meta = SAVE_OUTPUT_LABELS[key] || {
                title: key,
                file: key,
                wikiId: 'stage-5',
              };
              return (
                <label
                  key={key}
                  title={meta.file}
                  className={`cursor-pointer p-3.5 rounded-xl border transition flex items-center justify-between gap-3 min-w-0 overflow-hidden ${
                    checked
                      ? 'bg-slate-950 border-indigo-500/60'
                      : 'bg-slate-950/40 border-slate-800 opacity-70 hover:opacity-100'
                  }`}
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={(e) => {
                        const next = e.target.checked
                          ? [...config.save_output, key]
                          : config.save_output.filter((item) => item !== key);
                        onConfigChange({ ...config, save_output: next });
                      }}
                      className="rounded border-slate-700 bg-slate-900 text-indigo-600 focus:ring-indigo-500 shrink-0"
                    />
                    <div className="text-xs font-bold text-white truncate">{meta.title}</div>
                  </div>
                  <InfoTooltip topicId={meta.wikiId} onOpenWiki={onOpenWiki} />
                </label>
              );
            })}
          </div>
        </div>
      )}

      {/* Bottom Sticky Action Bar */}
      <div className="sticky bottom-4 z-20 bg-slate-900/95 backdrop-blur border border-slate-700 rounded-2xl p-4 shadow-2xl flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-2.5 min-w-0">
          <div
            className={`w-2.5 h-2.5 rounded-full shrink-0 ${
              hasUnsavedChanges ? 'bg-amber-400 animate-pulse' : 'bg-emerald-400'
            }`}
          />
          <span
            className="text-xs text-slate-300 truncate"
            title={`${demonstrator.id}/data/${config.parameters_file_path}`}
          >
            {hasUnsavedChanges ? 'Unsaved changes' : 'Saved'}
          </span>
        </div>

        <div className="flex items-center gap-3">
          <button
            disabled={saving || !!validationError}
            onClick={onSaveAll}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-semibold bg-slate-800 hover:bg-slate-700 text-white border border-slate-600 transition disabled:opacity-50"
          >
            <Save className="w-4 h-4 text-indigo-400" />
            {saving ? 'Saving...' : 'Save'}
          </button>

          <button
            disabled={!!validationError}
            onClick={() => onRunSimulation(true)}
            className="inline-flex items-center gap-2 px-5 py-2 rounded-xl text-xs font-bold bg-gradient-to-r from-indigo-600 to-violet-600 hover:from-indigo-500 hover:to-violet-500 text-white shadow-lg shadow-indigo-600/30 transition disabled:opacity-50"
          >
            <Play className="w-4 h-4 fill-current" />
            Run
          </button>
        </div>
      </div>

      {/* Save Preset Modal */}
      {showPresetModal && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-2xl max-w-md w-full p-6 space-y-4">
            <h3 className="text-base font-bold text-white">Save Parameters as New Preset</h3>
            <p className="text-xs text-slate-400">
              Creates a new JSON preset inside <code>demonstrators/{demonstrator.id}/data/</code> and sets it active.
            </p>
            <input
              type="text"
              value={newPresetName}
              onChange={(e) => setNewPresetName(e.target.value)}
              placeholder="e.g. qa_medium_preset.json"
              className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm font-mono text-white"
            />
            <div className="flex justify-end gap-2">
              <button
                onClick={() => setShowPresetModal(false)}
                className="px-4 py-2 rounded-lg text-xs text-slate-300 hover:bg-slate-800"
              >
                Cancel
              </button>
              <button
                onClick={async () => {
                  if (!newPresetName.trim()) return;
                  await onSavePreset(newPresetName.trim());
                  setNewPresetName('');
                  setShowPresetModal(false);
                }}
                className="px-4 py-2 rounded-lg text-xs font-semibold bg-indigo-600 text-white hover:bg-indigo-500"
              >
                Save & Activate
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Raw JSON Modal */}
      {showJsonModal && (
        <div className="fixed inset-0 z-50 bg-black/75 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-2xl max-w-4xl w-full max-h-[85vh] flex flex-col overflow-hidden">
            <div className="p-4 border-b border-slate-800 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <FileCode className="w-4 h-4 text-cyan-400" />
                <span className="font-bold text-sm text-white">
                  Live Configuration & Parameters JSON Preview
                </span>
              </div>
              <button
                onClick={() => setShowJsonModal(false)}
                className="px-3 py-1 rounded-lg text-xs bg-slate-800 text-slate-300 hover:bg-slate-700"
              >
                Close
              </button>
            </div>
            <div className="p-5 overflow-y-auto grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="min-w-0">
                <div className="text-xs font-mono text-indigo-300 mb-2">
                  data/simulation_config.json
                </div>
                <pre className="p-4 rounded-xl bg-slate-950 border border-slate-800 text-xs font-mono text-slate-200 overflow-x-auto">
                  {JSON.stringify(config, null, 2)}
                </pre>
              </div>
              <div className="min-w-0">
                <div className="text-xs font-mono text-cyan-300 mb-2">
                  data/{config.parameters_file_path}
                </div>
                <pre className="p-4 rounded-xl bg-slate-950 border border-slate-800 text-xs font-mono text-slate-200 overflow-x-auto">
                  {JSON.stringify(parameters, null, 2)}
                </pre>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Rename Demonstrator Modal */}
      {showRenameModal && (
        <div className="fixed inset-0 z-50 bg-black/75 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-2xl max-w-md w-full p-6 space-y-4">
            <h3 className="text-base font-bold text-white">
              Rename Demonstrator ({demonstrator.id})
            </h3>
            <p className="text-xs text-slate-400">
              Renames the folder inside <code>demonstrators/</code> while preserving all matrices,
              parameter presets, and run history.
            </p>
            <input
              type="text"
              value={renameValue}
              onChange={(e) => setRenameValue(e.target.value)}
              placeholder="e.g. demonstrator_01_blade_qa"
              className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm font-mono text-white"
            />
            <div className="flex justify-end gap-2 pt-2">
              <button
                onClick={() => setShowRenameModal(false)}
                className="px-4 py-2 rounded-lg text-xs text-slate-300 hover:bg-slate-800"
              >
                Cancel
              </button>
              <button
                onClick={async () => {
                  const trimmed = renameValue.trim();
                  if (!trimmed || trimmed === demonstrator.id) {
                    setShowRenameModal(false);
                    return;
                  }
                  await onRenameDemonstrator(demonstrator.id, trimmed);
                  setShowRenameModal(false);
                }}
                className="px-4 py-2 rounded-lg text-xs font-semibold bg-indigo-600 text-white hover:bg-indigo-500"
              >
                Rename Folder
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Delete Demonstrator Confirmation Modal */}
      {showDeleteDemModal && (
        <div className="fixed inset-0 z-50 bg-black/75 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-rose-500/40 rounded-2xl max-w-md w-full p-6 space-y-4">
            <div className="flex items-center gap-2.5 text-rose-400">
              <AlertTriangle className="w-5 h-5 shrink-0" />
              <h3 className="text-base font-bold text-white">
                Delete Demonstrator &quot;{demonstrator.id}&quot;?
              </h3>
            </div>
            <p className="text-xs text-slate-300 leading-relaxed">
              This will permanently remove <code>demonstrators/{demonstrator.id}/</code> along with
              its local matrices, parameter presets, and saved run folders.
            </p>
            <div className="flex justify-end gap-2 pt-2">
              <button
                onClick={() => setShowDeleteDemModal(false)}
                className="px-4 py-2 rounded-lg text-xs text-slate-300 hover:bg-slate-800"
              >
                Cancel
              </button>
              <button
                onClick={async () => {
                  await onDeleteDemonstrator(demonstrator.id);
                  setShowDeleteDemModal(false);
                }}
                className="px-4 py-2 rounded-lg text-xs font-semibold bg-rose-600 text-white hover:bg-rose-500"
              >
                Delete Permanently
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Diff / Compare Two Presets or Demonstrators Modal */}
      {showDiffModal && (
        <div className="fixed inset-0 z-50 bg-black/75 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-2xl max-w-4xl w-full max-h-[86vh] flex flex-col overflow-hidden shadow-2xl">
            <div className="p-4 border-b border-slate-800 flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <ArrowLeftRight className="w-4 h-4 text-amber-400" />
                <span className="font-bold text-sm text-white">
                  Compare Pipeline Configurations (Side-by-Side Diff)
                </span>
              </div>
              <div className="flex items-center gap-3">
                <label className="inline-flex items-center gap-2 text-xs text-slate-300 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={onlyDiffs}
                    onChange={(e) => setOnlyDiffs(e.target.checked)}
                    className="rounded border-slate-700 bg-slate-950 text-amber-500"
                  />
                  Show Only Differences
                </label>
                <button
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
                <div className="text-[11px] font-semibold uppercase tracking-wider text-indigo-300 mb-1">
                  Configuration A (Current Active Editor)
                </div>
                <div className="text-xs font-mono text-white truncate">
                  {demonstrator.id} / data/{config.parameters_file_path}
                </div>
              </div>

              <div className="p-3 rounded-xl bg-amber-950/20 border border-amber-500/30 space-y-2">
                <div className="text-[11px] font-semibold uppercase tracking-wider text-amber-300">
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
                      label: 'Partitioning Strategy',
                      valA: pp.partitioning_strategy,
                      valB: compareParams.partitioning_parameters.partitioning_strategy,
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
                          <th className="py-2 px-3 text-amber-300">
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
      )}
    </div>
  );
};

/* Compact matrix file picker: a single dropdown of available .mtx files with an "Other…" free-text fallback */
const MatrixFileCard: React.FC<{
  label: string;
  labelClass: string;
  wikiId: string;
  info: MatrixInfo;
  value: string;
  availableFiles: string[];
  placeholder: string;
  onChange: (next: string) => void;
  onOpenWiki: (topicId: string) => void;
}> = ({ label, labelClass, wikiId, info, value, availableFiles, placeholder, onChange, onOpenWiki }) => {
  const inList = availableFiles.includes(value);
  const [customMode, setCustomMode] = useState(!inList || availableFiles.length === 0);

  useEffect(() => {
    if (availableFiles.includes(value)) setCustomMode(false);
  }, [value, availableFiles.join('|')]);

  return (
    <div className="p-4 rounded-xl bg-slate-950/80 border border-slate-800 min-w-0 overflow-hidden space-y-2.5">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5 min-w-0">
          <span className={`text-xs font-semibold uppercase tracking-wider truncate ${labelClass}`}>
            {label}
          </span>
          <InfoTooltip topicId={wikiId} onOpenWiki={onOpenWiki} />
        </div>
        {info.exists ? (
          <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" aria-label="Found on disk" />
        ) : (
          <span className="inline-flex items-center gap-1 text-[11px] text-amber-400 bg-amber-500/10 px-2 py-0.5 rounded-full shrink-0">
            <AlertTriangle className="w-3 h-3" /> Missing
          </span>
        )}
      </div>

      {availableFiles.length > 0 && (
        <select
          value={customMode ? '__other__' : value}
          onChange={(e) => {
            if (e.target.value === '__other__') {
              setCustomMode(true);
            } else {
              setCustomMode(false);
              onChange(e.target.value);
            }
          }}
          className="w-full min-w-0 truncate bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs font-mono text-slate-100 focus:border-indigo-500 focus:outline-none"
        >
          {availableFiles.map((f) => (
            <option key={f} value={f}>
              {f}
            </option>
          ))}
          <option value="__other__">Other…</option>
        </select>
      )}

      {customMode && (
        <input
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="w-full min-w-0 bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs font-mono text-slate-100 focus:border-indigo-500 focus:outline-none"
          placeholder={placeholder}
        />
      )}

      {info.exists && (
        <div className="pt-2 border-t border-slate-800/80 flex flex-wrap items-center justify-between gap-2 text-xs text-slate-400">
          <span>
            Shape:{' '}
            <strong className="text-slate-200 font-mono">
              {info.rows?.toLocaleString()} × {info.cols?.toLocaleString()}
            </strong>
          </span>
          <span>
            NNZ: <strong className="text-slate-200 font-mono">{info.nnz?.toLocaleString()}</strong>
          </span>
        </div>
      )}
    </div>
  );
};
