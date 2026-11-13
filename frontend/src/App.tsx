import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  BarChart3,
  BookOpen,
  Cpu,
  FlaskConical,
  Keyboard,
  Layers,
  Moon,
  Sliders,
  Sun,
  Terminal,
} from 'lucide-react';
import { api } from './api/client';
import { BatchOrchestrator } from './components/BatchOrchestrator';
import { ExecutionConsole } from './components/ExecutionConsole';
import { HardwareInspector } from './components/HardwareInspector';
import { HelpGuide } from './components/HelpGuide';
import { PipelineStudio } from './components/PipelineStudio';
import { ResultsExplorer } from './components/ResultsExplorer';
import { TuningStudio } from './components/TuningStudio';
import { useToast } from './components/Toasts';
import { notifyIfHidden } from './lib/notify';
import { ActiveTab, readUrlState, writeUrlState } from './lib/urlState';
import {
  Demonstrator,
  LibraryMatrix,
  QuantumEstimates,
  SimulationConfig,
  SimulationJob,
  SimulationParameters,
} from './types/pipeline';

const LAST_MATRIX_KEY = 'studio-last-simulation';
const APP_TITLE = 'Hybrid Domain Decomposition Studio';

type NavTab = { id: ActiveTab; label: string; title: string; icon: typeof Sliders };

/** The kernel of the Studio: configure, run and analyse. Shown as the main tab row. */
const CORE_TABS: NavTab[] = [
  { id: 'pipeline', label: 'Single Run', title: 'Configure and run one simulation', icon: Sliders },
  { id: 'batch', label: 'Batch Run', title: 'Batch study across matrices, algorithms and scales', icon: Layers },
  { id: 'tuning', label: 'Tuning', title: 'Parameter selection: automatic or iterative tuning', icon: FlaskConical },
  { id: 'execution', label: 'Runs', title: 'Live logs and history of every run', icon: Terminal },
  { id: 'results', label: 'Results', title: 'Results & Plots', icon: BarChart3 },
];

/** Reference pages, shown as quieter links in the title bar. */
const INFO_TABS: NavTab[] = [
  { id: 'hardware', label: 'Hardware', title: 'Quantum Hardware Inspector', icon: Cpu },
  { id: 'help', label: 'Wiki', title: 'Project Wiki & Guide', icon: BookOpen },
];

/** Number-key order for tab shortcuts (1–7). */
const SHORTCUT_TABS: ActiveTab[] = [...CORE_TABS, ...INFO_TABS].map((t) => t.id);

const SHORTCUTS: Array<{ keys: string; action: string }> = [
  { keys: 'Ctrl/⌘ + S', action: 'Save configuration & parameters (Single Run)' },
  { keys: 'Ctrl/⌘ + Enter', action: 'Run the current simulation (Single Run)' },
  { keys: '1 – 7', action: 'Switch tab (Single Run, Batch Run, Tuning, Runs, Results, Hardware, Wiki)' },
  { keys: '?', action: 'Show this list' },
  { keys: 'Esc', action: 'Close dialogs' },
];

function readStoredMatrix(): string | null {
  try {
    return localStorage.getItem(LAST_MATRIX_KEY);
  } catch {
    return null;
  }
}

function isTypingTarget(el: EventTarget | null): boolean {
  if (!(el instanceof HTMLElement)) return false;
  const tag = el.tagName;
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || el.isContentEditable;
}

export function App() {
  const toast = useToast();
  const initialUrl = useRef(readUrlState()).current;

  const [activeTab, setActiveTab] = useState<ActiveTab>(initialUrl.tab);
  const [demonstrators, setDemonstrators] = useState<Demonstrator[]>([]);
  const [selectedDemId, setSelectedDemId] = useState<string>(
    initialUrl.matrix || readStoredMatrix() || 'simulation_01'
  );
  const [config, setConfig] = useState<SimulationConfig | null>(null);
  const [parameters, setParameters] = useState<SimulationParameters | null>(null);
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [liveEstimates, setLiveEstimates] = useState<QuantumEstimates | null>(null);
  const [saving, setSaving] = useState(false);

  // Navigation targets across tabs
  const [activeJobId, setActiveJobId] = useState<string | null>(initialUrl.job || null);
  const [inspectResultDir, setInspectResultDir] = useState<string | null>(initialUrl.run || null);
  const [inspectBatchId, setInspectBatchId] = useState<string | null>(initialUrl.batch || null);
  const [wikiTopicId, setWikiTopicId] = useState<string | null>(initialUrl.topic || null);

  // Jobs (polled here so finished runs are announced from any tab)
  const [jobs, setJobs] = useState<SimulationJob[]>([]);
  const knownStatuses = useRef<Map<string, SimulationJob['status']> | null>(null);
  const [unseenFinished, setUnseenFinished] = useState(0);

  // Backend connectivity
  const [backendOnline, setBackendOnline] = useState<boolean | null>(null);

  // Unsaved-changes guard: an action waiting for Save / Discard / Cancel
  const [pendingAction, setPendingAction] = useState<{ label: string; run: () => void } | null>(
    null
  );
  const [showShortcuts, setShowShortcuts] = useState(false);

  // Dark / Light theme (persisted in localStorage, applied as a class on <html>)
  const [theme, setTheme] = useState<'dark' | 'light'>(() => {
    try {
      return localStorage.getItem('studio-theme') === 'light' ? 'light' : 'dark';
    } catch {
      return 'dark';
    }
  });
  useEffect(() => {
    const root = document.documentElement;
    root.classList.toggle('light', theme === 'light');
    root.classList.toggle('dark', theme === 'dark');
    try {
      localStorage.setItem('studio-theme', theme);
    } catch {
      // ignore
    }
  }, [theme]);

  // Shared matrix library (matrices/<matrix_id>/)
  const [matrixLibrary, setMatrixLibrary] = useState<LibraryMatrix[]>([]);

  // New simulation modal
  const [showNewDemModal, setShowNewDemModal] = useState(false);
  const [newDemName, setNewDemName] = useState('');
  const [cloneFromDem, setCloneFromDem] = useState('');
  const [newDemMatrix, setNewDemMatrix] = useState('');

  const currentDemonstrator = demonstrators.find((d) => d.id === selectedDemId);

  /* ------------------------------------------------------------------ */
  /* URL state & persistence                                             */
  /* ------------------------------------------------------------------ */

  useEffect(() => {
    writeUrlState({
      tab: activeTab,
      matrix: selectedDemId,
      job: activeJobId || undefined,
      run: inspectResultDir || undefined,
      batch: inspectBatchId || undefined,
      topic: wikiTopicId || undefined,
    });
  }, [activeTab, selectedDemId, activeJobId, inspectResultDir, inspectBatchId, wikiTopicId]);

  useEffect(() => {
    try {
      localStorage.setItem(LAST_MATRIX_KEY, selectedDemId);
    } catch {
      // ignore
    }
  }, [selectedDemId]);

  /* ------------------------------------------------------------------ */
  /* Simulations                                                         */
  /* ------------------------------------------------------------------ */

  const applyDemonstrator = (dem: Demonstrator) => {
    setSelectedDemId(dem.id);
    setConfig(dem.simulation_config);
    setParameters(dem.simulation_parameters);
    setLiveEstimates(dem.estimates);
    setHasUnsavedChanges(false);
    setValidationError(null);
  };

  const loadDemonstrators = async (preferId?: string) => {
    try {
      const res = await api.listDemonstrators();
      const valid = res.demonstrators.filter((d) => !d.error);
      setDemonstrators(valid);
      const targetId = preferId || selectedDemId || valid[0]?.id;
      const found = valid.find((d) => d.id === targetId) || valid[0];
      if (found) applyDemonstrator(found);
    } catch (err: any) {
      toast.error(`Failed to load simulations: ${err.message}`);
    }
  };

  const loadMatrixLibrary = async (): Promise<LibraryMatrix[]> => {
    try {
      const res = await api.listMatrixLibrary();
      setMatrixLibrary(res.matrices);
      return res.matrices;
    } catch (err: any) {
      toast.error(`Failed to load the matrix library: ${err.message}`);
      return [];
    }
  };

  useEffect(() => {
    loadDemonstrators();
    loadMatrixLibrary();
  }, []);

  /** Run `action` now, or ask first when it would throw away unsaved edits. */
  const guardUnsaved = (label: string, action: () => void) => {
    if (hasUnsavedChanges) {
      setPendingAction({ label, run: action });
    } else {
      action();
    }
  };

  const handleSelectDemonstrator = (dem: Demonstrator) => {
    if (dem.id === selectedDemId) return;
    guardUnsaved(`switch to ${dem.id}`, () => applyDemonstrator(dem));
  };

  // Browser back/forward
  useEffect(() => {
    const onHashChange = () => {
      const s = readUrlState();
      setActiveTab(s.tab);
      if (s.job) setActiveJobId(s.job);
      if (s.run) setInspectResultDir(s.run);
      if (s.batch) setInspectBatchId(s.batch);
      if (s.topic) setWikiTopicId(s.topic);
      if (s.matrix && s.matrix !== selectedDemId) {
        const dem = demonstrators.find((d) => d.id === s.matrix);
        if (dem) handleSelectDemonstrator(dem);
      }
    };
    window.addEventListener('popstate', onHashChange);
    return () => window.removeEventListener('popstate', onHashChange);
  });

  // Warn before closing the tab with unsaved edits
  useEffect(() => {
    if (!hasUnsavedChanges) return;
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = '';
    };
    window.addEventListener('beforeunload', handler);
    return () => window.removeEventListener('beforeunload', handler);
  }, [hasUnsavedChanges]);

  /* ------------------------------------------------------------------ */
  /* Parameter editing with debounced validation                         */
  /* ------------------------------------------------------------------ */

  const validateTimer = useRef<number | null>(null);
  const validateSeq = useRef(0);

  const handleParametersChange = (nextParams: SimulationParameters) => {
    setParameters(nextParams);
    setHasUnsavedChanges(true);
    if (validateTimer.current) window.clearTimeout(validateTimer.current);
    validateTimer.current = window.setTimeout(async () => {
      const seq = ++validateSeq.current;
      try {
        const check = await api.validateParameters(nextParams);
        if (seq !== validateSeq.current) return; // a newer edit superseded this reply
        if (!check.valid) {
          setValidationError(check.error || 'Invalid simulation parameters');
        } else {
          setValidationError(null);
          if (check.estimates) setLiveEstimates(check.estimates);
        }
      } catch {
        // backend status indicator covers connectivity problems
      }
    }, 300);
  };

  const handleConfigChange = (nextConfig: SimulationConfig) => {
    setConfig(nextConfig);
    setHasUnsavedChanges(true);
  };

  const saveCurrent = async (): Promise<boolean> => {
    if (!currentDemonstrator || !config || !parameters) return false;
    setSaving(true);
    try {
      await api.updateConfig(currentDemonstrator.id, config);
      const updated = await api.updateParameters(currentDemonstrator.id, parameters);
      setDemonstrators((prev) => prev.map((d) => (d.id === updated.id ? updated : d)));
      setConfig(updated.simulation_config);
      setParameters(updated.simulation_parameters);
      setHasUnsavedChanges(false);
      return true;
    } catch (err: any) {
      toast.error(`Save failed: ${err.message}`);
      return false;
    } finally {
      setSaving(false);
    }
  };

  const handleSaveAll = async () => {
    if (await saveCurrent()) {
      toast.success(`Saved ${currentDemonstrator?.id}/${config?.parameters_file_path}`);
    }
  };

  /* ------------------------------------------------------------------ */
  /* Runs                                                                */
  /* ------------------------------------------------------------------ */

  const startRun = async (dem: Demonstrator, params: SimulationParameters, note = '') => {
    try {
      const job = await api.runSimulation(dem.demonstrator_dir, params);
      setActiveJobId(job.job_id);
      setActiveTab('execution');
      refreshJobs();
      toast.success(`Started run on ${dem.id}${note}`);
    } catch (err: any) {
      toast.error(`Failed to start run: ${err.message}`);
    }
  };

  /** Run the editor's current state. Unsaved edits are saved first, and the user is told. */
  const handleRunSimulation = async () => {
    if (!currentDemonstrator || !parameters) return;
    if (validationError) {
      toast.error(`Fix the parameter error before running: ${validationError}`);
      return;
    }
    let note = '';
    if (hasUnsavedChanges) {
      if (!(await saveCurrent())) return;
      note = ` (unsaved edits were saved to ${config?.parameters_file_path})`;
    }
    await startRun(currentDemonstrator, parameters, note);
  };

  /**
   * Run a simulation. When it targets the edited simulation and active parameters
   * file, it runs exactly what Single Run shows (same as its Run button).
   */
  /** Results tab: load a past run's parameters into the editor (unsaved). */
  const handleLoadRunParameters = (demId: string, params: SimulationParameters) => {
    const dem = demonstrators.find((d) => d.id === demId);
    if (!dem) return;
    guardUnsaved(`load parameters into ${demId}`, () => {
      applyDemonstrator(dem);
      setParameters(params);
      setHasUnsavedChanges(true);
      setActiveTab('pipeline');
      toast.info(`Loaded run parameters into ${demId}. Review them, then Save or Run.`);
    });
  };

  const handleRerun = async (demId: string, params: SimulationParameters) => {
    const dem = demonstrators.find((d) => d.id === demId);
    if (!dem) {
      toast.error(`Simulation ${demId} no longer exists`);
      return;
    }
    await startRun(dem, params, ' with the same parameters as the selected run');
  };

  /* ------------------------------------------------------------------ */
  /* Job polling, completion notifications & tab title                    */
  /* ------------------------------------------------------------------ */

  const refreshJobs = useCallback(async () => {
    try {
      const res = await api.listJobs();
      setJobs(res.jobs);
      setBackendOnline(true);

      const prev = knownStatuses.current;
      const next = new Map(res.jobs.map((j) => [j.job_id, j.status] as const));
      if (prev) {
        for (const job of res.jobs) {
          if (prev.get(job.job_id) !== 'running' || job.status === 'running') continue;
          const label = job.title.replace(/^Simulation: /, '');
          if (job.status === 'completed') {
            toast.success(`Finished: ${label}`, {
              action: {
                label: 'Open',
                onClick: () => {
                  setActiveJobId(job.job_id);
                  setActiveTab('execution');
                },
              },
            });
            notifyIfHidden('Run finished ✓', label);
          } else if (job.status === 'failed') {
            toast.error(`Failed: ${label}${job.error_message ? ` — ${job.error_message}` : ''}`);
            notifyIfHidden('Run failed ✗', label);
          }
          if (document.visibilityState !== 'visible') setUnseenFinished((n) => n + 1);
        }
      }
      knownStatuses.current = next;
    } catch {
      setBackendOnline(false);
    }
  }, [toast]);

  const runningCount = jobs.filter((j) => j.status === 'running').length;

  useEffect(() => {
    refreshJobs();
    const timer = window.setInterval(refreshJobs, runningCount > 0 ? 2000 : 5000);
    return () => window.clearInterval(timer);
  }, [refreshJobs, runningCount > 0]);

  // Health check when there is no other traffic to tell us the backend went away
  useEffect(() => {
    const check = async () => setBackendOnline(await api.health());
    const timer = window.setInterval(check, 10000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    const onVisible = () => {
      if (document.visibilityState === 'visible') setUnseenFinished(0);
    };
    document.addEventListener('visibilitychange', onVisible);
    return () => document.removeEventListener('visibilitychange', onVisible);
  }, []);

  useEffect(() => {
    const prefix =
      unseenFinished > 0
        ? `✓ ${unseenFinished} finished · `
        : runningCount > 0
        ? `⏳ ${runningCount} running · `
        : '';
    document.title = `${prefix}${hasUnsavedChanges ? '• ' : ''}${APP_TITLE}`;
  }, [runningCount, unseenFinished, hasUnsavedChanges]);

  /* ------------------------------------------------------------------ */
  /* Keyboard shortcuts                                                  */
  /* ------------------------------------------------------------------ */

  const shortcutHandlers = useRef({ save: handleSaveAll, run: handleRunSimulation, activeTab });
  shortcutHandlers.current = { save: handleSaveAll, run: handleRunSimulation, activeTab };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const mod = e.ctrlKey || e.metaKey;
      const h = shortcutHandlers.current;
      if (mod && e.key.toLowerCase() === 's') {
        if (h.activeTab === 'pipeline') {
          e.preventDefault();
          h.save();
        }
        return;
      }
      if (mod && e.key === 'Enter') {
        if (h.activeTab === 'pipeline') {
          e.preventDefault();
          h.run();
        }
        return;
      }
      if (e.key === 'Escape') {
        setShowShortcuts(false);
        setShowNewDemModal(false);
        setPendingAction(null);
        return;
      }
      if (mod || e.altKey || isTypingTarget(e.target)) return;
      if (e.key === '?') {
        setShowShortcuts((v) => !v);
        return;
      }
      const idx = parseInt(e.key, 10);
      if (idx >= 1 && idx <= SHORTCUT_TABS.length) {
        setActiveTab(SHORTCUT_TABS[idx - 1]);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  /* ------------------------------------------------------------------ */
  /* Matrix files & presets                                              */
  /* ------------------------------------------------------------------ */

  const replaceDemonstrator = (updated: Demonstrator) =>
    setDemonstrators((prev) => prev.map((d) => (d.id === updated.id ? updated : d)));

  /** Point the edited simulation at a library matrix (an unsaved change, like any other edit). */
  const selectMatrix = (matrixId: string) => {
    if (!config) return;
    handleConfigChange({ ...config, input_matrix: matrixId });
  };

  const handleGenerateDemoMatrices = async (preset: 'small' | 'medium' | 'large') => {
    if (!parameters) return;
    const dims =
      preset === 'small'
        ? { nx_nodes: 12, ny_nodes: 5, nz_nodes: 4 }
        : preset === 'medium'
        ? { nx_nodes: 15, ny_nodes: 6, nz_nodes: 4 }
        : { nx_nodes: 20, ny_nodes: 6, nz_nodes: 5 };

    try {
      const m = await api.generateDemoMatrix({
        ...dims,
        dof_per_node: parameters.general_parameters.dof_per_node || 1,
      });
      await loadMatrixLibrary();
      selectMatrix(m.id);
      toast.success(`Added ${m.name} to the matrix library and selected it — save to keep it`);
    } catch (err: any) {
      toast.error(`Matrix generation failed: ${err.message}`);
    }
  };

  const handleUploadMatrix = async (name: string, file: File): Promise<boolean> => {
    try {
      const m = await api.uploadMatrix(name, file);
      await loadMatrixLibrary();
      selectMatrix(m.id);
      toast.success(`Uploaded ${m.id} to the matrix library and selected it — save to keep it`);
      return true;
    } catch (err: any) {
      toast.error(`Upload rejected: ${err.message}`);
      return false;
    }
  };

  const handleDeleteLibraryMatrix = async (matrixId: string) => {
    if (!window.confirm(`Delete matrix ${matrixId} from the library? This removes its .mtx file from disk.`)) return;
    try {
      await api.deleteLibraryMatrix(matrixId);
      await loadMatrixLibrary();
      toast.success(`Deleted matrix ${matrixId}`);
    } catch (err: any) {
      toast.error(`Delete failed: ${err.message}`);
    }
  };

  const openNewSimulation = () => {
    setCloneFromDem(selectedDemId);
    setNewDemMatrix(config?.input_matrix || matrixLibrary[0]?.id || '');
    setShowNewDemModal(true);
  };

  const handleSelectPreset = (filename: string) => {
    if (!currentDemonstrator || !config) return;
    guardUnsaved(`switch to preset ${filename}`, async () => {
      try {
        const presetRes = await api.getPreset(currentDemonstrator.id, filename);
        const updated = await api.updateConfig(currentDemonstrator.id, {
          ...config,
          parameters_file_path: filename,
        });
        replaceDemonstrator(updated);
        setConfig(updated.simulation_config);
        setParameters(presetRes.parameters);
        setHasUnsavedChanges(false);
        setValidationError(null);
        toast.success(`Switched active parameters file to ${filename}`);
      } catch (err: any) {
        toast.error(`Preset switch failed: ${err.message}`);
      }
    });
  };

  const handleSavePreset = async (filename: string) => {
    if (!currentDemonstrator || !parameters) return;
    try {
      const updated = await api.savePreset(currentDemonstrator.id, filename, parameters, true);
      replaceDemonstrator(updated);
      setConfig(updated.simulation_config);
      setParameters(updated.simulation_parameters);
      setHasUnsavedChanges(false);
      toast.success(`Created and activated preset ${updated.active_parameters_file}`);
    } catch (err: any) {
      toast.error(`Save preset failed: ${err.message}`);
    }
  };

  const handleDeletePreset = async (filename: string) => {
    if (!currentDemonstrator) return;
    if (!window.confirm(`Delete preset ${filename}? This removes the JSON file from disk.`)) return;
    try {
      const updated = await api.deletePreset(currentDemonstrator.id, filename);
      replaceDemonstrator(updated);
      setConfig(updated.simulation_config);
      setParameters(updated.simulation_parameters);
      setHasUnsavedChanges(false);
      toast.success(`Deleted preset ${filename}`);
    } catch (err: any) {
      toast.error(`Delete preset failed: ${err.message}`);
    }
  };

  const handleRenameDemonstrator = async (demId: string, newName: string) => {
    try {
      const renamed = await api.renameDemonstrator(demId, newName);
      await loadDemonstrators(renamed.id);
      toast.success(`Renamed ${demId} to ${renamed.id}`);
    } catch (err: any) {
      toast.error(`Rename failed: ${err.message}`);
    }
  };

  const handleDeleteDemonstrator = async (demId: string) => {
    try {
      const res = await api.deleteDemonstrator(demId);
      await loadDemonstrators(res.remaining_demonstrators[0]);
      toast.success(`Deleted simulation ${demId}`);
    } catch (err: any) {
      toast.error(`Delete failed: ${err.message}`);
    }
  };

  const handleOpenWiki = (topicId: string) => {
    setWikiTopicId(topicId);
    setActiveTab('help');
  };

  /* ------------------------------------------------------------------ */
  /* Render                                                              */
  /* ------------------------------------------------------------------ */

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col">
      {/* Top Studio Header */}
      <header className="sticky top-0 z-30 bg-slate-950/90 backdrop-blur border-b border-slate-800">
        {/* Row 1: identity + reference links */}
        <div className="px-6 py-2.5 border-b border-slate-800/70">
          <div className="max-w-7xl mx-auto flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center shadow-lg shadow-indigo-500/20">
                <Cpu className="w-4 h-4 text-white" />
              </div>
              <h1 className="text-base font-bold tracking-tight text-white">{APP_TITLE}</h1>
              <span
                className="inline-flex items-center gap-1.5 text-xs text-slate-400"
                title={
                  backendOnline === false
                    ? 'The Python backend is not responding'
                    : 'Connected to the local Python backend'
                }
              >
                <span
                  className={`w-2 h-2 rounded-full ${
                    backendOnline === false
                      ? 'bg-rose-500'
                      : backendOnline
                      ? 'bg-emerald-400'
                      : 'bg-slate-500'
                  }`}
                />
                {backendOnline === false ? 'Backend offline' : backendOnline ? 'Connected' : '…'}
              </span>
            </div>

            <nav aria-label="Reference" className="flex flex-wrap items-center gap-1">
              {INFO_TABS.map((tab) => {
                const Icon = tab.icon;
                const isCurrent = activeTab === tab.id;
                return (
                  <button
                    key={tab.id}
                    title={`${tab.title} (${SHORTCUT_TABS.indexOf(tab.id) + 1})`}
                    aria-current={isCurrent ? 'page' : undefined}
                    onClick={() => setActiveTab(tab.id)}
                    className={`inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs transition ${
                      isCurrent ? 'text-white bg-slate-800' : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900'
                    }`}
                  >
                    <Icon className={`w-3.5 h-3.5 ${isCurrent ? 'text-indigo-400' : 'text-slate-500'}`} />
                    {tab.label}
                  </button>
                );
              })}
              <span className="mx-1 h-5 w-px bg-slate-800" aria-hidden />
              <button
                type="button"
                onClick={() => setShowShortcuts(true)}
                title="Keyboard shortcuts (?)"
                aria-label="Show keyboard shortcuts"
                className="inline-flex items-center justify-center w-8 h-8 rounded-lg text-slate-400 hover:text-indigo-300 hover:bg-slate-900 transition"
              >
                <Keyboard className="w-4 h-4" />
              </button>
              <button
                type="button"
                onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
                title={theme === 'dark' ? 'Switch to Light mode' : 'Switch to Dark mode'}
                aria-label="Toggle color theme"
                className="inline-flex items-center justify-center w-8 h-8 rounded-lg text-slate-400 hover:text-amber-300 hover:bg-slate-900 transition"
              >
                {theme === 'dark' ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
              </button>
            </nav>
          </div>
        </div>

        {/* Row 2: the core workflow */}
        <div className="px-6">
          <nav aria-label="Main" className="max-w-7xl mx-auto flex flex-wrap items-center gap-1 -mb-px">
            {CORE_TABS.map((tab) => {
              const Icon = tab.icon;
              const isCurrent = activeTab === tab.id;
              return (
                <button
                  key={tab.id}
                  title={`${tab.title} (${SHORTCUT_TABS.indexOf(tab.id) + 1})`}
                  aria-current={isCurrent ? 'page' : undefined}
                  onClick={() => setActiveTab(tab.id)}
                  className={`inline-flex items-center gap-2 px-4 py-3 text-sm font-semibold border-b-2 transition ${
                    isCurrent
                      ? 'border-indigo-500 text-white'
                      : 'border-transparent text-slate-400 hover:text-slate-200 hover:border-slate-600'
                  }`}
                >
                  <Icon className={`w-4 h-4 ${isCurrent ? 'text-indigo-400' : 'text-slate-500'}`} />
                  {tab.label}
                  {tab.id === 'execution' && runningCount > 0 && (
                    <span className="ml-0.5 px-1.5 rounded-full bg-indigo-600 text-white text-[11px]">
                      {runningCount}
                    </span>
                  )}
                </button>
              );
            })}
          </nav>
        </div>
      </header>

      {backendOnline === false && (
        <div className="bg-rose-950/80 border-b border-rose-500/40 px-6 py-2 text-xs text-rose-200 text-center">
          The Studio backend is not responding. Check the terminal running{' '}
          <code className="font-mono text-rose-100">./run.sh --ui</code> or restart it — this page
          reconnects automatically.
        </div>
      )}

      {/* Main Content Area */}
      <main
        className={`flex-1 w-full mx-auto px-6 py-6 min-w-0 ${
          // Single Run and Batch Run use the side space for their menus; the content column keeps about the usual width.
          activeTab === 'pipeline' ? 'max-w-[1560px]' : activeTab === 'batch' ? 'max-w-[1720px]' : 'max-w-7xl'
        }`}
      >
        {activeTab === 'pipeline' && currentDemonstrator && config && parameters && (
          <PipelineStudio
            demonstrators={demonstrators}
            demonstrator={currentDemonstrator}
            config={config}
            parameters={parameters}
            liveEstimates={liveEstimates}
            hasUnsavedChanges={hasUnsavedChanges}
            validationError={validationError}
            saving={saving}
            onSelectDemonstrator={handleSelectDemonstrator}
            onOpenNewDemonstrator={openNewSimulation}
            onRenameDemonstrator={handleRenameDemonstrator}
            onDeleteDemonstrator={handleDeleteDemonstrator}
            onConfigChange={handleConfigChange}
            onParametersChange={handleParametersChange}
            onSaveAll={handleSaveAll}
            onRunSimulation={handleRunSimulation}
            matrixLibrary={matrixLibrary}
            onSelectMatrix={selectMatrix}
            onGenerateDemoMatrices={handleGenerateDemoMatrices}
            onUploadMatrix={handleUploadMatrix}
            onDeleteLibraryMatrix={handleDeleteLibraryMatrix}
            onSavePreset={handleSavePreset}
            onSelectPreset={handleSelectPreset}
            onDeletePreset={handleDeletePreset}
            onOpenWiki={handleOpenWiki}
          />
        )}

        {activeTab === 'execution' && (
          <ExecutionConsole
            demonstrators={demonstrators}
            jobs={jobs}
            onRefreshJobs={refreshJobs}
            activeJobId={activeJobId}
            onSelectJob={(jid) => setActiveJobId(jid || null)}
            onInspectResultDir={(rdir) => {
              setInspectResultDir(rdir);
              setInspectBatchId(null);
              setActiveTab('results');
              loadDemonstrators(selectedDemId);
            }}
            onInspectBatchRun={(bid) => {
              setInspectBatchId(bid);
              setInspectResultDir(null);
              setActiveTab('results');
            }}
            onGoToSingleRun={() => setActiveTab('pipeline')}
          />
        )}

        {activeTab === 'batch' && (
          <BatchOrchestrator
            matrixLibrary={matrixLibrary}
            onBatchStarted={(jid) => {
              setActiveJobId(jid);
              setActiveTab('execution');
              refreshJobs();
            }}
            onInspectBatchRun={(bid) => {
              setInspectBatchId(bid);
              setInspectResultDir(null);
              setActiveTab('results');
            }}
            onOpenWiki={handleOpenWiki}
          />
        )}

        {activeTab === 'tuning' && (
          <TuningStudio
            demonstrators={demonstrators}
            selectedDemId={selectedDemId}
            hasUnsavedChanges={hasUnsavedChanges}
            jobs={jobs}
            onSelectDemonstrator={handleSelectDemonstrator}
            onParametersApplied={() => loadDemonstrators(selectedDemId)}
            onOpenJob={(jid) => {
              setActiveJobId(jid);
              setActiveTab('execution');
            }}
            onRefreshJobs={refreshJobs}
          />
        )}

        {activeTab === 'results' && (
          <ResultsExplorer
            demonstrators={demonstrators}
            selectedDemonstratorId={selectedDemId}
            initialResultDir={inspectResultDir}
            initialBatchId={inspectBatchId}
            onSelectionChange={(sel) => {
              setInspectResultDir(sel.resultDir);
              setInspectBatchId(sel.batchId);
            }}
            onLoadParameters={handleLoadRunParameters}
            onRerun={handleRerun}
            onOpenWiki={handleOpenWiki}
          />
        )}

        {activeTab === 'hardware' && <HardwareInspector onOpenWiki={handleOpenWiki} />}

        {activeTab === 'help' && (
          <HelpGuide
            onNavigateTab={(tab) => setActiveTab(tab)}
            onOpenNewDemonstrator={openNewSimulation}
            focusedTopicId={wikiTopicId}
            onClearFocus={() => setWikiTopicId(null)}
          />
        )}
      </main>

      {/* Unsaved changes guard */}
      {pendingAction && (
        <div className="fixed inset-0 z-[55] bg-black/75 backdrop-blur-sm flex items-center justify-center p-4">
          <div
            role="dialog"
            aria-modal="true"
            className="bg-slate-900 border border-slate-700 rounded-2xl max-w-md w-full p-6 space-y-4"
          >
            <h3 className="text-base font-bold text-white">Unsaved changes</h3>
            <p className="text-xs text-slate-300 leading-relaxed">
              You have unsaved edits to <strong>{selectedDemId}</strong> (
              <code className="font-mono">{config?.parameters_file_path}</code>). Save them before
              you {pendingAction.label}?
            </p>
            <div className="flex justify-end gap-2 pt-2">
              <button
                onClick={() => setPendingAction(null)}
                className="px-4 py-2 rounded-lg text-xs text-slate-300 hover:bg-slate-800"
              >
                Cancel
              </button>
              <button
                onClick={() => {
                  const action = pendingAction;
                  setPendingAction(null);
                  setHasUnsavedChanges(false);
                  action.run();
                }}
                className="px-4 py-2 rounded-lg text-xs font-semibold bg-rose-600/20 text-rose-200 border border-rose-500/40 hover:bg-rose-600/30"
              >
                Discard edits
              </button>
              <button
                onClick={async () => {
                  const action = pendingAction;
                  setPendingAction(null);
                  if (await saveCurrent()) action.run();
                }}
                className="px-4 py-2 rounded-lg text-xs font-semibold bg-indigo-600 text-white hover:bg-indigo-500"
              >
                Save & continue
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Keyboard shortcuts */}
      {showShortcuts && (
        <div
          onClick={() => setShowShortcuts(false)}
          className="fixed inset-0 z-50 bg-black/75 backdrop-blur-sm flex items-center justify-center p-4"
        >
          <div
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-modal="true"
            className="bg-slate-900 border border-slate-700 rounded-2xl max-w-md w-full p-6 space-y-4"
          >
            <h3 className="text-base font-bold text-white flex items-center gap-2">
              <Keyboard className="w-4 h-4 text-indigo-400" /> Keyboard shortcuts
            </h3>
            <table className="w-full text-xs">
              <tbody className="divide-y divide-slate-800">
                {SHORTCUTS.map((s) => (
                  <tr key={s.keys}>
                    <td className="py-2 pr-4 font-mono text-indigo-300 whitespace-nowrap">{s.keys}</td>
                    <td className="py-2 text-slate-300">{s.action}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="flex justify-end">
              <button
                onClick={() => setShowShortcuts(false)}
                className="px-4 py-2 rounded-lg text-xs text-slate-300 hover:bg-slate-800"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* New / Clone Matrix Modal */}
      {showNewDemModal && (
        <div className="fixed inset-0 z-50 bg-black/75 backdrop-blur-sm flex items-center justify-center p-4">
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="new-sim-title"
            className="bg-slate-900 border border-slate-700 rounded-2xl max-w-md w-full p-6 space-y-4"
          >
            <h3 id="new-sim-title" className="text-base font-bold text-white">New simulation</h3>
            <div>
              <label htmlFor="new-sim-name" className="block text-xs text-slate-300 mb-1">Name</label>
              <input
                id="new-sim-name"
                type="text"
                value={newDemName}
                onChange={(e) => setNewDemName(e.target.value)}
                placeholder="leave empty for the next simulation_NN"
                className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm font-mono text-white"
              />
            </div>

            <div>
              <label htmlFor="new-sim-matrix" className="block text-xs text-slate-300 mb-1">Matrix</label>
              <select
                id="new-sim-matrix"
                value={newDemMatrix}
                onChange={(e) => setNewDemMatrix(e.target.value)}
                className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs text-white"
              >
                {matrixLibrary.length === 0 && <option value="">Library is empty — add a matrix in Input Matrix</option>}
                {matrixLibrary.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name} ({p.id})
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label htmlFor="new-sim-clone" className="block text-xs text-slate-300 mb-1">
                Copy parameters from
              </label>
              <select
                id="new-sim-clone"
                value={cloneFromDem}
                onChange={(e) => setCloneFromDem(e.target.value)}
                className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs text-white"
              >
                <option value="">Defaults</option>
                {demonstrators.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.id}
                  </option>
                ))}
              </select>
            </div>

            <div className="flex justify-end gap-2 pt-2">
              <button
                onClick={() => setShowNewDemModal(false)}
                className="px-4 py-2 rounded-lg text-xs text-slate-300 hover:bg-slate-800"
              >
                Cancel
              </button>
              <button
                onClick={() => {
                  guardUnsaved('create a new simulation', async () => {
                    try {
                      const created = await api.createDemonstrator(
                        newDemName.trim() || null,
                        cloneFromDem || undefined,
                        newDemMatrix || undefined
                      );
                      await loadDemonstrators(created.id);
                      await loadMatrixLibrary();
                      setNewDemName('');
                      setShowNewDemModal(false);
                      toast.success(`Created ${created.id}`);
                    } catch (err: any) {
                      toast.error(`Could not create the simulation: ${err.message}`);
                    }
                  });
                }}
                className="px-4 py-2 rounded-lg text-xs font-semibold bg-indigo-600 text-white hover:bg-indigo-500"
              >
                Create simulation
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
