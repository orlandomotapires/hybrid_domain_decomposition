import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  Activity,
  AlertTriangle,
  ArrowLeftRight,
  Code2,
  Cpu,
  Database,
  Edit3,
  FolderPlus,
  GitBranch,
  Layers,
  Play,
  Save,
  Trash2,
} from 'lucide-react';
import {
  Demonstrator,
  LibraryMatrix,
  PartitioningStrategyKey,
  QuantumAnnealingParams,
  QuantumEstimates,
  QAOAParams,
  SimulationConfig,
  SimulationParameters,
} from '../types/pipeline';
import { capacityFor } from '../lib/feasibility';
import { methodLabel } from '../lib/labels';
import { InfoTooltip } from './InfoTooltip';
import { CompareConfigsModal, useCompareConfigs } from './pipeline/CompareConfigsModal';
import {
  DeleteMatrixModal,
  RawJsonModal,
  RenameMatrixModal,
  SavePresetModal,
} from './pipeline/PipelineModals';
import { StageCoarsening, useCoarseningPreview } from './pipeline/StageCoarsening';
import { StageInputMatrices } from './pipeline/StageInputMatrices';
import { StageOutputs } from './pipeline/StageOutputs';
import { StagePartitioning } from './pipeline/StagePartitioning';
import { StageRefinement } from './pipeline/StageRefinement';
import { StageCardControl, stageDomId } from './pipeline/StageCard';
import { COARSENING_STRATEGIES } from './pipeline/constants';

const STAGE_NUMBERS = [1, 2, 3, 4, 5] as const;
const COLLAPSED_STORAGE_KEY = 'studio-collapsed-stages';

const readCollapsedStages = (): Set<number> => {
  try {
    const raw = window.localStorage.getItem(COLLAPSED_STORAGE_KEY);
    const parsed: unknown = raw ? JSON.parse(raw) : [];
    return new Set(
      Array.isArray(parsed) ? parsed.filter((n): n is number => typeof n === 'number') : []
    );
  } catch {
    return new Set();
  }
};

const writeCollapsedStages = (stages: Set<number>) => {
  try {
    window.localStorage.setItem(COLLAPSED_STORAGE_KEY, JSON.stringify([...stages].sort()));
  } catch {
    /* storage unavailable (private mode, quota) — collapse state just won't persist */
  }
};

interface PipelineStudioProps {
  demonstrators: Demonstrator[];
  demonstrator: Demonstrator;
  config: SimulationConfig;
  parameters: SimulationParameters;
  /** Latest estimates returned by parameter validation (QPU submissions, shots, warnings). */
  liveEstimates: QuantumEstimates | null;
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
  /** Shared matrix library; the simulation picks one matrix in Stage 1. */
  matrixLibrary: LibraryMatrix[];
  onSelectMatrix: (matrixId: string) => void;
  onGenerateDemoMatrices: (preset: 'small' | 'medium' | 'large') => Promise<void>;
  onUploadMatrix: (name: string, file: File) => Promise<boolean>;
  onDeleteLibraryMatrix: (matrixId: string) => Promise<void>;
  onSavePreset: (filename: string) => Promise<void>;
  onSelectPreset: (filename: string) => void | Promise<void>;
  onDeletePreset: (filename: string) => Promise<void>;
  onOpenWiki: (topicId: string) => void;
}

export const PipelineStudio: React.FC<PipelineStudioProps> = ({
  demonstrators,
  demonstrator,
  config,
  parameters,
  liveEstimates,
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
  matrixLibrary,
  onSelectMatrix,
  onGenerateDemoMatrices,
  onUploadMatrix,
  onDeleteLibraryMatrix,
  onSavePreset,
  onSelectPreset,
  onDeletePreset,
  onOpenWiki,
}) => {
  /** Stage card currently in view (drives the stepper highlight). */
  const [stageInView, setStageInView] = useState<number>(1);
  const [collapsedStages, setCollapsedStages] = useState<Set<number>>(readCollapsedStages);
  /** Height of the sticky action bar, used to pad the page so it never covers content. */
  const actionBarRef = useRef<HTMLDivElement | null>(null);
  const [actionBarHeight, setActionBarHeight] = useState(140);
  const [showJsonModal, setShowJsonModal] = useState(false);
  const [newPresetName, setNewPresetName] = useState('');
  const [showPresetModal, setShowPresetModal] = useState(false);
  const [generatingMatrices, setGeneratingMatrices] = useState(false);

  // Rename & Delete Demonstrator Modal State
  const [showRenameModal, setShowRenameModal] = useState(false);
  const [renameValue, setRenameValue] = useState('');
  const [showDeleteDemModal, setShowDeleteDemModal] = useState(false);

  // Diff / Compare Configs Modal State
  const compare = useCompareConfigs(demonstrators, demonstrator);

  // Dry-Run Coarsening Trajectory Preview State
  // The matrix being edited (may differ from the saved one until Save).
  const selectedMatrixId = config.input_matrix || null;
  const selectedMatrix = selectedMatrixId ? matrixLibrary.find((m) => m.id === selectedMatrixId) : undefined;
  const matrixInfo = selectedMatrix
    ? { info: selectedMatrix.info, ready: selectedMatrix.ready && selectedMatrix.square }
    : selectedMatrixId && selectedMatrixId !== demonstrator.matrix.id
    ? { info: { filename: '', exists: false }, ready: false }
    : { info: demonstrator.matrix.info, ready: demonstrator.matrix.ready };

  const coarseningPreview = useCoarseningPreview(demonstrator.id, parameters, selectedMatrixId);

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
    matrixInfo.info.rows && gp.dof_per_node > 0
      ? Math.floor(matrixInfo.info.rows / gp.dof_per_node)
      : null;

  // Map backend validation errors ("coarsening_parameters.x must be …") to their pipeline stage
  const errorStage: number | null = !validationError
    ? null
    : /general_parameters/.test(validationError)
    ? 1
    : /coarsening_parameters/.test(validationError)
    ? 2
    : /partitioning_parameters/.test(validationError)
    ? 3
    : /uncoarsening_parameters/.test(validationError)
    ? 4
    : null;

  const updateCollapsed = useCallback((update: (prev: Set<number>) => Set<number>) => {
    setCollapsedStages((prev) => {
      const next = update(prev);
      writeCollapsedStages(next);
      return next;
    });
  }, []);

  const toggleStageCollapsed = (n: number) =>
    updateCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(n)) next.delete(n);
      else next.add(n);
      return next;
    });

  // A stage with a validation error must always be visible.
  useEffect(() => {
    if (errorStage !== null && collapsedStages.has(errorStage)) {
      updateCollapsed((prev) => {
        const next = new Set(prev);
        next.delete(errorStage);
        return next;
      });
    }
  }, [errorStage, collapsedStages, updateCollapsed]);

  /**
   * Stage shown on its own (null = every stage is shown). Clicking a stage box focuses it;
   * clicking the focused box again (or "Show all stages") shows them all again.
   */
  const [focusedStage, setFocusedStage] = useState<number | null>(null);
  const isStageShown = (n: number) => focusedStage === null || focusedStage === n || errorStage === n;

  const toggleFocusStage = (n: number) => {
    if (focusedStage === n) {
      setFocusedStage(null);
      return;
    }
    setFocusedStage(n);
    goToStage(n);
  };

  // Switching simulation starts again with every stage visible.
  useEffect(() => {
    setFocusedStage(null);
  }, [demonstrator.id]);

  /** Expand (if needed) and smooth-scroll to a stage card. */
  const goToStage = (n: number) => {
    if (collapsedStages.has(n)) {
      updateCollapsed((prev) => {
        const next = new Set(prev);
        next.delete(n);
        return next;
      });
    }
    setStageInView(n);
    // Wait a frame so an expanded card has its final layout before scrolling.
    window.requestAnimationFrame(() => {
      document.getElementById(stageDomId(n))?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  };

  // Highlight the stepper tile of the stage currently in view: the stage whose card
  // crosses a 1px "reading line" just below the sticky app header.
  const [viewportHeight, setViewportHeight] = useState(() => window.innerHeight);
  useEffect(() => {
    const onResize = () => setViewportHeight(window.innerHeight);
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

  useEffect(() => {
    const sections = STAGE_NUMBERS.map((n) => document.getElementById(stageDomId(n))).filter(
      (el): el is HTMLElement => !!el
    );
    if (sections.length === 0 || typeof IntersectionObserver === 'undefined') return;
    const READING_LINE_PX = 140;
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            setStageInView(Number((entry.target as HTMLElement).dataset.stage));
          }
        });
      },
      {
        rootMargin: `-${READING_LINE_PX}px 0px -${Math.max(0, viewportHeight - READING_LINE_PX - 1)}px 0px`,
        threshold: 0,
      }
    );
    sections.forEach((el) => observer.observe(el));

    // Near the bottom of the page the last (short) stages may never reach the reading line.
    const onScroll = () => {
      const doc = document.documentElement;
      if (window.scrollY > 0 && window.innerHeight + window.scrollY >= doc.scrollHeight - 8) {
        setStageInView(sections.length ? Number(sections[sections.length - 1].dataset.stage) : 5);
      }
    };
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => {
      observer.disconnect();
      window.removeEventListener('scroll', onScroll);
    };
  }, [viewportHeight, focusedStage]);

  // Track the sticky action bar's height (it grows with warning lines).
  useEffect(() => {
    const el = actionBarRef.current;
    if (!el || typeof ResizeObserver === 'undefined') return;
    const ro = new ResizeObserver(() => setActionBarHeight(el.offsetHeight));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const stageCard = (n: number): StageCardControl => ({
    hasError: errorStage === n,
    errorBanner: stageErrorBanner(n),
    collapsed: collapsedStages.has(n) && errorStage !== n,
    onToggleCollapsed: () => toggleStageCollapsed(n),
  });

  const stageErrorBanner = (n: number) =>
    errorStage === n && validationError ? (
      <div className="mb-4 p-3 rounded-xl bg-rose-950/60 border border-rose-500/50 flex items-start gap-2.5 text-xs text-rose-200">
        <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
        <span className="break-words">
          <strong>Fix this before saving or running:</strong> {validationError}
        </span>
      </div>
    ) : null;

  // Run cost / feasibility summary shown next to the Run button
  const matrixRows = matrixInfo.info.rows;
  const blockMismatch = matrixRows != null && gp.dof_per_node > 0 && matrixRows % gp.dof_per_node !== 0;
  const maxCoarseNodes = cp.coarsen_superior_limit ?? cp.coarsen_inferior_limit;
  const qubitCapacity = capacityFor(
    activeStrategy,
    activeStrategy === 'quantum_annealing'
      ? qaParams
      : activeStrategy === 'quantum_approximation_optimizer'
      ? qaoaParams
      : undefined
  );
  const overCapacity = !!qubitCapacity && maxCoarseNodes > qubitCapacity.limit;
  const costItems: string[] = [];
  if (inferredGraphNodes !== null) costItems.push(`G₀ ${inferredGraphNodes.toLocaleString()} nodes`);
  costItems.push(`coarse ≤ ${cp.coarsen_superior_limit ?? '∞'} nodes`);
  if (activeStrategy !== 'metis_partitioning') {
    costItems.push(`≤ ${maxCoarseNodes} qubits / QUBO`);
  }
  if (activeStrategy === 'quantum_annealing') {
    const subs = liveEstimates?.expected_qpu_submissions ?? expectedQaSubmissions;
    const reads = liveEstimates?.expected_qpu_reads ?? expectedQaReads;
    costItems.push(
      `${subs.toLocaleString()} ${currentSimulated ? 'annealer calls' : 'QPU submissions'} · ${reads.toLocaleString()} reads`
    );
  } else if (activeStrategy === 'quantum_approximation_optimizer') {
    const jobs = liveEstimates?.expected_qlm_jobs ?? expectedQaoaJobs;
    costItems.push(`${jobs.toLocaleString()} ${currentSimulated ? 'circuit evaluations' : 'QLM jobs'}`);
    if (liveEstimates?.total_circuit_shots != null) {
      costItems.push(`${liveEstimates.total_circuit_shots.toLocaleString()} shots`);
    }
  }
  const costWarnings = [
    ...(overCapacity
      ? [`Coarse graph may reach ${maxCoarseNodes} nodes — above the ~${qubitCapacity!.limit} limit of ${qubitCapacity!.what}.`]
      : []),
    ...(blockMismatch
      ? [`The matrix has ${matrixRows} rows, which is not divisible by the block size ${gp.dof_per_node}.`]
      : []),
    ...(!matrixInfo.ready ? ['No usable matrix selected (missing file or not square).'] : []),
    ...(liveEstimates?.warnings || []),
  ];

  const handleGenerateMatrices = async (preset: 'small' | 'medium' | 'large') => {
    setGeneratingMatrices(true);
    try {
      await onGenerateDemoMatrices(preset);
    } finally {
      setGeneratingMatrices(false);
    }
  };

  return (
    <div
      className="min-w-0 lg:grid lg:grid-cols-[236px_minmax(0,1fr)] lg:gap-6 lg:items-start"
      style={{ paddingBottom: actionBarHeight + 24 }}
    >
      {/* Left menu: the 5 pipeline stages (click = show only that stage) + simulation actions */}
      <aside
        aria-label="Pipeline stages and actions"
        className="mb-6 lg:mb-0 lg:sticky lg:top-[124px] lg:max-h-[calc(100vh-140px)] lg:overflow-y-auto space-y-4"
      >
        <nav aria-label="Pipeline stages" className="bg-slate-900/90 border border-slate-800 rounded-2xl p-3 space-y-2">
          <div className="flex items-center justify-between gap-2 px-1">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-400">Stages</span>
            {focusedStage !== null ? (
              <button
                type="button"
                onClick={() => setFocusedStage(null)}
                className="text-xs text-indigo-300 hover:text-indigo-200"
              >
                Show all
              </button>
            ) : (
              <span className="text-xs text-slate-500">all shown</span>
            )}
          </div>
          <ol className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-5 lg:grid-cols-1 gap-2">
            {[
            {
              n: 1,
              label: 'Input Matrix',
              wiki: 'stage-1',
              Icon: Database,
              value: matrixInfo.ready
                ? `${selectedMatrix?.name || selectedMatrixId || 'Matrix ready'}${
                    inferredGraphNodes !== null ? ` · ${inferredGraphNodes.toLocaleString()} nodes` : ''
                  }`
                : 'No matrix',
              valueClass: matrixInfo.ready ? 'text-slate-300' : 'text-amber-400',
            },
            {
              n: 2,
              label: 'Coarsening',
              wiki: 'stage-2',
              Icon: Layers,
              value: `${
                COARSENING_STRATEGIES.find((st) => st.key === cp.strategy)?.title ?? cp.strategy
              } · [${cp.coarsen_inferior_limit}–${cp.coarsen_superior_limit ?? '∞'}]`,
              valueClass: 'text-slate-300',
            },
            {
              n: 3,
              label: 'Partitioning',
              wiki: 'stage-3',
              Icon: Cpu,
              value: `${methodLabel(activeStrategy, currentSimulated, true)} · k=${pp.common.k_target}`,
              valueClass: 'text-slate-300',
            },
            {
              n: 4,
              label: 'Refinement',
              wiki: 'stage-4',
              Icon: GitBranch,
              value: up.refine_objective === 'cut' ? 'Cut' : 'Cut + Balance',
              valueClass: 'text-slate-300',
            },
            {
              n: 5,
              label: 'Outputs',
              wiki: 'stage-5',
              Icon: Activity,
              value: `${config.save_output.length} / ${demonstrator.available_save_outputs.length} artifacts`,
              valueClass: 'text-slate-300',
            },
            ].map((stage) => {
              const focused = focusedStage === stage.n;
              const shown = focusedStage === null || focused;
              const inView = focusedStage === null && stageInView === stage.n;
              const hasError = errorStage === stage.n;
              const StageIcon = stage.Icon;
              return (
                <li key={stage.n} className="min-w-0">
                  <button
                    type="button"
                    onClick={() => toggleFocusStage(stage.n)}
                    aria-pressed={focused}
                    aria-current={inView ? 'step' : undefined}
                    className={`w-full text-left p-3 rounded-xl border transition-all min-w-0 overflow-hidden ${
                      hasError
                        ? 'bg-rose-950/40 border-rose-500 ring-2 ring-rose-500/30'
                        : focused
                        ? 'bg-indigo-950/70 border-indigo-400 ring-2 ring-indigo-500/40'
                        : inView
                        ? 'bg-indigo-950/40 border-indigo-500/70'
                        : shown
                        ? 'bg-slate-950/70 border-slate-700 hover:border-slate-500'
                        : 'bg-slate-950/40 border-slate-800 opacity-60 hover:opacity-100'
                    }`}
                    title={
                      hasError
                        ? 'This stage has an invalid parameter — click to show it'
                        : focused
                        ? 'Click again to show every stage'
                        : `Show only stage ${stage.n}: ${stage.label}`
                    }
                  >
                    <div className="flex items-center justify-between gap-2 mb-1">
                      <div className="flex items-center gap-2 min-w-0">
                        <span
                          className={`w-5 h-5 rounded-md text-xs font-bold flex items-center justify-center shrink-0 ${
                            focused || inView ? 'bg-indigo-600 text-white' : 'bg-slate-800 text-slate-300'
                          }`}
                        >
                          {stage.n}
                        </span>
                        <StageIcon
                          className={`w-4 h-4 shrink-0 ${
                            hasError ? 'text-rose-400' : focused || inView ? 'text-indigo-300' : 'text-slate-400'
                          }`}
                        />
                        <span className="font-semibold text-xs text-white truncate">{stage.label}</span>
                      </div>
                      <InfoTooltip topicId={stage.wiki} onOpenWiki={onOpenWiki} />
                    </div>
                    <div className={`text-xs font-mono truncate pl-7 ${stage.valueClass}`} title={stage.value}>
                      {stage.value}
                    </div>
                  </button>
                </li>
              );
            })}
          </ol>
        </nav>

        <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-3 space-y-1.5">
          <div className="px-1 pb-1 text-xs font-bold uppercase tracking-wider text-slate-400">Configuration</div>
          <div className="grid grid-cols-1 sm:grid-cols-3 lg:grid-cols-1 gap-1.5">
            <button
              type="button"
              onClick={compare.openCompare}
              className="flex items-center gap-2 px-3 py-2 rounded-lg text-xs font-medium bg-slate-800 text-slate-200 hover:bg-slate-700 border border-slate-700 transition"
              title="Compare active parameters against another preset or simulation"
            >
              <ArrowLeftRight className="w-3.5 h-3.5 text-slate-400" />
              Compare Configs
            </button>
            <button
              type="button"
              onClick={() => setShowPresetModal(true)}
              className="flex items-center gap-2 px-3 py-2 rounded-lg text-xs font-medium bg-slate-800 text-slate-200 hover:bg-slate-700 border border-slate-700 transition"
            >
              <FolderPlus className="w-3.5 h-3.5 text-slate-400" />
              Save as Preset
            </button>
            <button
              type="button"
              onClick={() => setShowJsonModal(true)}
              className="flex items-center gap-2 px-3 py-2 rounded-lg text-xs font-medium bg-slate-800 text-slate-200 hover:bg-slate-700 border border-slate-700 transition"
            >
              <Code2 className="w-3.5 h-3.5 text-slate-400" />
              Inspect JSON
            </button>
          </div>
        </div>
      </aside>

      <div className="space-y-6 min-w-0">
      {/* Active simulation switcher */}
      <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-4 shadow-xl overflow-hidden">
        <div className="flex flex-wrap items-center gap-2.5 min-w-0">
            <div className="flex flex-wrap items-center gap-1.5 bg-slate-950 p-1 rounded-xl border border-slate-800">
              {demonstrators.map((dem) => {
                const active = dem.id === demonstrator.id;
                const demPp = dem.simulation_parameters.partitioning_parameters;
                const strat = demPp.partitioning_strategy;
                const demSimulated =
                  strat === 'quantum_annealing'
                    ? demPp.strategies.quantum_annealing?.simulated ?? true
                    : strat === 'quantum_approximation_optimizer'
                    ? demPp.strategies.quantum_approximation_optimizer?.simulated ?? true
                    : true;
                const stratShort = methodLabel(strat, demSimulated, true);
                return (
                  <button
                    key={dem.id}
                    type="button"
                    onClick={() => onSelectDemonstrator(dem)}
                    aria-pressed={active}
                    title={`${dem.id} · ${dem.matrix.name || dem.matrix.id || 'no matrix'} · ${methodLabel(strat, demSimulated)}`}
                    className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition flex items-center gap-2 ${
                      active
                        ? 'bg-indigo-600 text-white ring-2 ring-indigo-300 ring-offset-2 ring-offset-slate-950 shadow'
                        : 'text-slate-300 hover:text-white hover:bg-slate-800'
                    }`}
                  >
                    <span>{dem.id}</span>
                    <span
                      className={`text-xs px-1.5 py-0.5 rounded ${
                        active ? 'bg-indigo-800 text-indigo-100' : 'bg-slate-800 text-slate-300'
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
                title="Create a new simulation (optionally copying this one's parameters)"
              >
                <FolderPlus className="w-3.5 h-3.5" />
                New simulation
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
                title={`Rename simulation ${demonstrator.id}`}
                aria-label={`Rename simulation ${demonstrator.id}`}
              >
                <Edit3 className="w-3.5 h-3.5" />
              </button>
              {demonstrators.length > 1 && (
                <button
                  type="button"
                  onClick={() => setShowDeleteDemModal(true)}
                  className="p-1.5 rounded-lg text-slate-400 hover:text-rose-400 hover:bg-rose-950/40 border border-transparent hover:border-rose-500/30 transition"
                  title={`Delete simulation ${demonstrator.id}`}
                  aria-label={`Delete simulation ${demonstrator.id}`}
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              )}
            </div>
        </div>
        {/* Validation Error Alert */}
        {validationError && (
          <div className="mt-3 p-3 rounded-xl bg-rose-950/60 border border-rose-500/50 flex items-center gap-2.5 text-xs text-rose-200">
            <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0" />
            <span className="break-words flex-1">
              <strong>Parameter Validation Error:</strong> {validationError}
            </span>
            {errorStage !== null && (
              <button
                type="button"
                onClick={() => {
                  setFocusedStage(errorStage);
                  goToStage(errorStage);
                }}
                className="shrink-0 px-2.5 py-1 rounded-lg bg-rose-600/30 hover:bg-rose-600/50 text-rose-100 font-semibold"
              >
                Go to stage {errorStage}
              </button>
            )}
          </div>
        )}
      </div>

      {/* STAGE 1: INPUT MATRIX & GRAPH CONSTRUCTION */}
      {isStageShown(1) && (
        <StageInputMatrices
          card={stageCard(1)}
          onOpenWiki={onOpenWiki}
          demonstrator={demonstrator}
          config={config}
          parameters={parameters}
          inferredGraphNodes={inferredGraphNodes}
          matrixRows={matrixRows}
          blockMismatch={blockMismatch}
          matrixLibrary={matrixLibrary}
          generatingMatrices={generatingMatrices}
          onGenerateMatrices={handleGenerateMatrices}
          onSelectMatrix={onSelectMatrix}
          onUploadMatrix={onUploadMatrix}
          onDeleteLibraryMatrix={onDeleteLibraryMatrix}
          onParametersChange={onParametersChange}
          onSelectPreset={onSelectPreset}
          onDeletePreset={onDeletePreset}
        />
      )}

      {/* STAGE 2: MULTILEVEL COARSENING (HEAVY EDGE MATCHING) */}
      {isStageShown(2) && (
        <StageCoarsening
          card={stageCard(2)}
          onOpenWiki={onOpenWiki}
          demonstrator={demonstrator}
          parameters={parameters}
          onParametersChange={onParametersChange}
          preview={coarseningPreview}
        />
      )}

      {/* STAGE 3: COARSE GRAPH PARTITIONING */}
      {isStageShown(3) && (
        <StagePartitioning
          card={stageCard(3)}
          onOpenWiki={onOpenWiki}
          parameters={parameters}
          onParametersChange={onParametersChange}
          qaParams={qaParams}
          qaoaParams={qaoaParams}
          currentSimulated={currentSimulated}
          selectPartitionMethod={selectPartitionMethod}
          bipartitionsPerStart={bipartitionsPerStart}
          expectedQaSubmissions={expectedQaSubmissions}
          expectedQaReads={expectedQaReads}
          expectedQaoaJobs={expectedQaoaJobs}
        />
      )}

      {/* STAGE 4: UNCOARSENING & REFINEMENT */}
      {isStageShown(4) && (
        <StageRefinement
          card={stageCard(4)}
          onOpenWiki={onOpenWiki}
          parameters={parameters}
          onParametersChange={onParametersChange}
        />
      )}

      {/* STAGE 5: MATRIX PERMUTATION & OUTPUT ARTIFACTS */}
      {isStageShown(5) && (
        <StageOutputs
          card={stageCard(5)}
          onOpenWiki={onOpenWiki}
          demonstrator={demonstrator}
          config={config}
          onConfigChange={onConfigChange}
        />
      )}

      {/* Bottom Sticky Action Bar */}
      <div
        ref={actionBarRef}
        className="sticky bottom-4 z-20 bg-slate-900/95 backdrop-blur border border-slate-700 rounded-2xl p-4 shadow-2xl flex flex-wrap items-center justify-between gap-4"
      >
        <div className="flex flex-col gap-1.5 min-w-0 flex-1">
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
            {hasUnsavedChanges ? (
              'Unsaved changes'
            ) : (
              <>
                Saved <span className="text-slate-500">· {config.parameters_file_path}</span>
              </>
            )}
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs font-mono text-slate-400">
          <span className="font-sans font-semibold text-slate-300">This run:</span>
          {costItems.map((c, i) => (
            <span key={i} className="whitespace-nowrap">
              {i > 0 && <span className="text-slate-600 mr-2">·</span>}
              {c}
            </span>
          ))}
        </div>
        {costWarnings.map((w, i) => (
          <div key={i} className="flex items-center gap-1.5 text-xs text-amber-300">
            <AlertTriangle className="w-3.5 h-3.5 shrink-0" /> {w}
          </div>
        ))}
        </div>

        <div className="flex items-center gap-3">
          <button
            type="button"
            disabled={saving || !!validationError}
            onClick={onSaveAll}
            title="Save (Ctrl/⌘ + S)"
            className="inline-flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-semibold bg-slate-800 hover:bg-slate-700 text-white border border-slate-600 transition disabled:opacity-50"
          >
            <Save className="w-4 h-4 text-indigo-400" />
            {saving ? 'Saving...' : 'Save'}
          </button>

          <button
            type="button"
            disabled={!!validationError}
            onClick={() => onRunSimulation(true)}
            title={validationError ? 'Fix the parameter error first' : 'Run (Ctrl/⌘ + Enter)'}
            className="inline-flex items-center gap-2 px-5 py-2 rounded-xl text-xs font-bold bg-indigo-600 hover:bg-indigo-500 text-white shadow-lg shadow-indigo-600/30 transition disabled:opacity-50"
          >
            <Play className="w-4 h-4 fill-current" />
            Run
          </button>
        </div>
      </div>

      {/* Save Preset Modal */}
      {showPresetModal && (
        <SavePresetModal
          demonstrator={demonstrator}
          newPresetName={newPresetName}
          setNewPresetName={setNewPresetName}
          onSavePreset={onSavePreset}
          onClose={() => setShowPresetModal(false)}
        />
      )}

      {/* Raw JSON Modal */}
      {showJsonModal && (
        <RawJsonModal
          config={config}
          parameters={parameters}
          onClose={() => setShowJsonModal(false)}
        />
      )}

      {/* Rename Matrix Modal */}
      {showRenameModal && (
        <RenameMatrixModal
          demonstrator={demonstrator}
          renameValue={renameValue}
          setRenameValue={setRenameValue}
          onRenameDemonstrator={onRenameDemonstrator}
          onClose={() => setShowRenameModal(false)}
        />
      )}

      {/* Delete Matrix Confirmation Modal */}
      {showDeleteDemModal && (
        <DeleteMatrixModal
          demonstrator={demonstrator}
          onDeleteDemonstrator={onDeleteDemonstrator}
          onClose={() => setShowDeleteDemModal(false)}
        />
      )}

      {/* Diff / Compare Two Presets or Demonstrators Modal */}
      {compare.showDiffModal && (
        <CompareConfigsModal
          demonstrators={demonstrators}
          demonstrator={demonstrator}
          config={config}
          parameters={parameters}
          qaParams={qaParams}
          qaoaParams={qaoaParams}
          compare={compare}
        />
      )}
      </div>
    </div>
  );
};
