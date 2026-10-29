import React, { useEffect, useState } from 'react';
import {
  Activity,
  BarChart3,
  BookOpen,
  CheckCircle2,
  Cpu,
  FolderPlus,
  HelpCircle,
  Layers,
  Moon,
  Play,
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
import {
  Demonstrator,
  SimulationConfig,
  SimulationParameters,
} from './types/pipeline';

type ActiveTab = 'pipeline' | 'execution' | 'batch' | 'results' | 'hardware' | 'help';

export function App() {
  const [activeTab, setActiveTab] = useState<ActiveTab>('pipeline');
  const [demonstrators, setDemonstrators] = useState<Demonstrator[]>([]);
  const [selectedDemId, setSelectedDemId] = useState<string>('demonstrator_01');
  const [config, setConfig] = useState<SimulationConfig | null>(null);
  const [parameters, setParameters] = useState<SimulationParameters | null>(null);
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  // Navigation targets across tabs
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [inspectResultDir, setInspectResultDir] = useState<string | null>(null);
  const [inspectBatchId, setInspectBatchId] = useState<string | null>(null);
  const [wikiTopicId, setWikiTopicId] = useState<string | null>(null);

  // Dark / Light theme (persisted in localStorage, applied as a class on <html>)
  const [theme, setTheme] = useState<'dark' | 'light'>(() =>
    localStorage.getItem('studio-theme') === 'light' ? 'light' : 'dark'
  );
  useEffect(() => {
    const root = document.documentElement;
    root.classList.toggle('light', theme === 'light');
    root.classList.toggle('dark', theme === 'dark');
    localStorage.setItem('studio-theme', theme);
  }, [theme]);
  const handleOpenWiki = (topicId: string) => {
    setWikiTopicId(topicId);
    setActiveTab('help');
  };

  // New demonstrator modal
  const [showNewDemModal, setShowNewDemModal] = useState(false);
  const [newDemName, setNewDemName] = useState('');
  const [cloneFromDem, setCloneFromDem] = useState('demonstrator_01');

  const showToast = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 3500);
  };

  const loadDemonstrators = async (preferId?: string) => {
    try {
      const res = await api.listDemonstrators();
      const valid = res.demonstrators.filter((d) => !d.error);
      setDemonstrators(valid);
      const targetId = preferId || selectedDemId || valid[0]?.id;
      const found = valid.find((d) => d.id === targetId) || valid[0];
      if (found) {
        setSelectedDemId(found.id);
        setConfig(found.simulation_config);
        setParameters(found.simulation_parameters);
        setHasUnsavedChanges(false);
        setValidationError(null);
      }
    } catch (err: any) {
      showToast(`Failed to load demonstrators: ${err.message}`);
    }
  };

  useEffect(() => {
    loadDemonstrators();
  }, []);

  const currentDemonstrator = demonstrators.find((d) => d.id === selectedDemId);

  const handleSelectDemonstrator = (dem: Demonstrator) => {
    setSelectedDemId(dem.id);
    setConfig(dem.simulation_config);
    setParameters(dem.simulation_parameters);
    setHasUnsavedChanges(false);
    setValidationError(null);
  };

  const handleParametersChange = async (nextParams: SimulationParameters) => {
    setParameters(nextParams);
    setHasUnsavedChanges(true);
    try {
      const check = await api.validateParameters(nextParams);
      if (!check.valid) {
        setValidationError(check.error || 'Invalid simulation parameters');
      } else {
        setValidationError(null);
      }
    } catch {
      // ignore transient network check
    }
  };

  const handleConfigChange = (nextConfig: SimulationConfig) => {
    setConfig(nextConfig);
    setHasUnsavedChanges(true);
  };

  const handleSaveAll = async () => {
    if (!currentDemonstrator || !config || !parameters) return;
    setSaving(true);
    try {
      await api.updateConfig(currentDemonstrator.id, config);
      const updated = await api.updateParameters(currentDemonstrator.id, parameters);
      setDemonstrators((prev) =>
        prev.map((d) => (d.id === updated.id ? updated : d))
      );
      setConfig(updated.simulation_config);
      setParameters(updated.simulation_parameters);
      setHasUnsavedChanges(false);
      showToast(`Saved configuration & parameters for ${updated.id}`);
    } catch (err: any) {
      showToast(`Save error: ${err.message}`);
    } finally {
      setSaving(false);
    }
  };

  const handleRunSimulation = async (useInMemoryOverride = true) => {
    if (!currentDemonstrator || !parameters) return;
    try {
      if (hasUnsavedChanges && config) {
        await api.updateConfig(currentDemonstrator.id, config);
        await api.updateParameters(currentDemonstrator.id, parameters);
        setHasUnsavedChanges(false);
      }
      const job = await api.runSimulation(
        currentDemonstrator.demonstrator_dir,
        useInMemoryOverride ? parameters : undefined
      );
      setActiveJobId(job.job_id);
      setActiveTab('execution');
      showToast(`Started simulation job ${job.job_id}`);
    } catch (err: any) {
      showToast(`Failed to start run: ${err.message}`);
    }
  };

  const handleRunFromConsole = async (
    targetDem?: Demonstrator,
    overrideParams?: SimulationParameters
  ) => {
    const dem = targetDem || currentDemonstrator;
    if (!dem) return;
    try {
      const job = await api.runSimulation(
        dem.demonstrator_dir,
        overrideParams || dem.simulation_parameters
      );
      setActiveJobId(job.job_id);
      showToast(`Started simulation job ${job.job_id} (${dem.id})`);
    } catch (err: any) {
      showToast(`Failed to start run: ${err.message}`);
    }
  };

  const handleGenerateDemoMatrices = async (preset: 'small' | 'medium' | 'large') => {
    if (!currentDemonstrator || !parameters) return;
    const dims =
      preset === 'small'
        ? { nx_nodes: 12, ny_nodes: 5, nz_nodes: 4 }
        : preset === 'medium'
        ? { nx_nodes: 15, ny_nodes: 6, nz_nodes: 4 }
        : { nx_nodes: 20, ny_nodes: 6, nz_nodes: 5 };

    try {
      const updated = await api.generateDemoMatrices(currentDemonstrator.id, {
        ...dims,
        dof_per_node: parameters.general_parameters.dof_per_node || 3,
      });
      setDemonstrators((prev) =>
        prev.map((d) => (d.id === updated.id ? updated : d))
      );
      showToast(`Generated 3D FEM K & M matrices for ${updated.id}`);
    } catch (err: any) {
      showToast(`Matrix generation failed: ${err.message}`);
    }
  };

  const handleUploadMatrix = async (file: File) => {
    if (!currentDemonstrator) return;
    try {
      const updated = await api.uploadMatrixFile(currentDemonstrator.id, file);
      setDemonstrators((prev) =>
        prev.map((d) => (d.id === updated.id ? updated : d))
      );
      showToast(`Uploaded ${file.name} to ${updated.id}/data/matrices/`);
    } catch (err: any) {
      showToast(`Upload failed: ${err.message}`);
    }
  };

  const handleSelectPreset = async (filename: string) => {
    if (!currentDemonstrator || !config) return;
    try {
      const presetRes = await api.getPreset(currentDemonstrator.id, filename);
      const nextCfg = { ...config, parameters_file_path: filename };
      const updated = await api.updateConfig(currentDemonstrator.id, nextCfg);
      setDemonstrators((prev) =>
        prev.map((d) => (d.id === updated.id ? updated : d))
      );
      setConfig(updated.simulation_config);
      setParameters(presetRes.parameters);
      setHasUnsavedChanges(false);
      showToast(`Switched active parameters file to ${filename}`);
    } catch (err: any) {
      showToast(`Preset switch failed: ${err.message}`);
    }
  };

  const handleSavePreset = async (filename: string) => {
    if (!currentDemonstrator || !parameters) return;
    try {
      const updated = await api.savePreset(
        currentDemonstrator.id,
        filename,
        parameters,
        true
      );
      setDemonstrators((prev) =>
        prev.map((d) => (d.id === updated.id ? updated : d))
      );
      setConfig(updated.simulation_config);
      setParameters(updated.simulation_parameters);
      setHasUnsavedChanges(false);
      showToast(`Created and activated preset ${updated.active_parameters_file}`);
    } catch (err: any) {
      showToast(`Save preset failed: ${err.message}`);
    }
  };

  const handleDeletePreset = async (filename: string) => {
    if (!currentDemonstrator) return;
    try {
      const updated = await api.deletePreset(currentDemonstrator.id, filename);
      setDemonstrators((prev) =>
        prev.map((d) => (d.id === updated.id ? updated : d))
      );
      setConfig(updated.simulation_config);
      setParameters(updated.simulation_parameters);
      setHasUnsavedChanges(false);
      showToast(`Deleted preset ${filename}`);
    } catch (err: any) {
      showToast(`Delete preset failed: ${err.message}`);
    }
  };

  const handleRenameDemonstrator = async (demId: string, newName: string) => {
    try {
      const renamed = await api.renameDemonstrator(demId, newName);
      await loadDemonstrators(renamed.id);
      showToast(`Renamed ${demId} to ${renamed.id}`);
    } catch (err: any) {
      showToast(`Rename failed: ${err.message}`);
    }
  };

  const handleDeleteDemonstrator = async (demId: string) => {
    try {
      const res = await api.deleteDemonstrator(demId);
      const nextId = res.remaining_demonstrators[0];
      await loadDemonstrators(nextId);
      showToast(`Deleted demonstrator ${demId}`);
    } catch (err: any) {
      showToast(`Delete failed: ${err.message}`);
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col">
      {/* Top Studio Header */}
      <header className="sticky top-0 z-30 bg-slate-950/90 backdrop-blur border-b border-slate-800 px-6 py-3">
        <div className="max-w-7xl mx-auto flex flex-wrap items-center justify-between gap-4">
          {/* Clean Brand Title */}
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center shadow-lg shadow-indigo-500/20">
              <Cpu className="w-4 h-4 text-white" />
            </div>
            <h1 className="text-base font-bold tracking-tight text-white">
              Hybrid Domain Decomposition Studio
            </h1>
          </div>

          {/* Navigation Tabs */}
          <nav className="flex flex-wrap items-center gap-1.5">
            {[
              { id: 'pipeline', label: 'Pipeline', title: 'Pipeline & Methods Manager', icon: Sliders },
              { id: 'execution', label: 'Run', title: 'Live Execution Console', icon: Terminal },
              { id: 'batch', label: 'Batch', title: 'Batch Study Orchestrator', icon: Layers },
              { id: 'results', label: 'Results', title: 'Results, Plots & LaTeX Tables', icon: BarChart3 },
              { id: 'hardware', label: 'Hardware', title: 'Quantum Hardware Inspector', icon: Cpu },
              { id: 'help', label: 'Wiki', title: 'Project Wiki & Guide', icon: BookOpen },
            ].map((tab) => {
              const Icon = tab.icon;
              const isCurrent = activeTab === tab.id;
              return (
                <button
                  key={tab.id}
                  title={tab.title}
                  onClick={() => setActiveTab(tab.id as ActiveTab)}
                  className={`inline-flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs font-semibold transition ${
                    isCurrent
                      ? 'bg-slate-800 text-white border border-slate-700 shadow-sm'
                      : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900'
                  }`}
                >
                  <Icon
                    className={`w-4 h-4 ${
                      isCurrent ? 'text-indigo-400' : 'text-slate-500'
                    }`}
                  />
                  {tab.label}
                </button>
              );
            })}
            <button
              type="button"
              onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
              title={theme === 'dark' ? 'Switch to Light mode' : 'Switch to Dark mode'}
              aria-label="Toggle color theme"
              className="ml-1 inline-flex items-center justify-center w-9 h-9 rounded-xl border border-slate-800 text-slate-400 hover:text-amber-300 hover:bg-slate-900 transition"
            >
              {theme === 'dark' ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
            </button>
          </nav>
        </div>
      </header>

      {/* Toast Notification */}
      {toast && (
        <div className="fixed top-20 right-6 z-50 bg-indigo-950/95 border border-indigo-500 text-indigo-100 px-4 py-2.5 rounded-xl shadow-2xl flex items-center gap-2 text-xs font-medium">
          <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
          {toast}
        </div>
      )}

      {/* Main Content Area */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-6 py-6 min-w-0">
        {activeTab === 'pipeline' && currentDemonstrator && config && parameters && (
          <PipelineStudio
            demonstrators={demonstrators}
            demonstrator={currentDemonstrator}
            config={config}
            parameters={parameters}
            hasUnsavedChanges={hasUnsavedChanges}
            validationError={validationError}
            saving={saving}
            onSelectDemonstrator={handleSelectDemonstrator}
            onOpenNewDemonstrator={() => setShowNewDemModal(true)}
            onRenameDemonstrator={handleRenameDemonstrator}
            onDeleteDemonstrator={handleDeleteDemonstrator}
            onConfigChange={handleConfigChange}
            onParametersChange={handleParametersChange}
            onSaveAll={handleSaveAll}
            onRunSimulation={handleRunSimulation}
            onGenerateDemoMatrices={handleGenerateDemoMatrices}
            onUploadMatrix={handleUploadMatrix}
            onSavePreset={handleSavePreset}
            onSelectPreset={handleSelectPreset}
            onDeletePreset={handleDeletePreset}
            onOpenWiki={handleOpenWiki}
          />
        )}

        {activeTab === 'execution' && (
          <ExecutionConsole
            demonstrators={demonstrators}
            selectedDemonstratorId={selectedDemId}
            onSelectDemonstrator={handleSelectDemonstrator}
            activeJobId={activeJobId}
            onSelectJob={(jid) => setActiveJobId(jid)}
            onInspectResultDir={(rdir) => {
              setInspectResultDir(rdir);
              setActiveTab('results');
              loadDemonstrators(selectedDemId);
            }}
            onTriggerRun={handleRunFromConsole}
          />
        )}

        {activeTab === 'batch' && (
          <BatchOrchestrator
            demonstrators={demonstrators}
            onBatchStarted={(jid) => {
              setActiveJobId(jid);
              setActiveTab('execution');
            }}
            onInspectBatchRun={(bid) => {
              setInspectBatchId(bid);
              setInspectResultDir(null);
              setActiveTab('results');
            }}
            onOpenWiki={handleOpenWiki}
          />
        )}

        {activeTab === 'results' && (
          <ResultsExplorer
            demonstrators={demonstrators}
            selectedDemonstratorId={selectedDemId}
            initialResultDir={inspectResultDir}
            initialBatchId={inspectBatchId}
            onOpenWiki={handleOpenWiki}
          />
        )}

        {activeTab === 'hardware' && <HardwareInspector onOpenWiki={handleOpenWiki} />}

        {activeTab === 'help' && (
          <HelpGuide
            onNavigateTab={(tab) => setActiveTab(tab)}
            onOpenNewDemonstrator={() => setShowNewDemModal(true)}
            focusedTopicId={wikiTopicId}
            onClearFocus={() => setWikiTopicId(null)}
          />
        )}
      </main>

      {/* New / Clone Demonstrator Modal */}
      {showNewDemModal && (
        <div className="fixed inset-0 z-50 bg-black/75 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-2xl max-w-md w-full p-6 space-y-4">
            <h3 className="text-base font-bold text-white">
              Create or Clone Simulation Demonstrator
            </h3>
            <div>
              <label className="block text-xs text-slate-300 mb-1">
                New Demonstrator Folder Name
              </label>
              <input
                type="text"
                value={newDemName}
                onChange={(e) => setNewDemName(e.target.value)}
                placeholder="e.g. demonstrator_04_turbine"
                className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm font-mono text-white"
              />
            </div>

            <div>
              <label className="block text-xs text-slate-300 mb-1">
                Clone Initial Configuration From
              </label>
              <select
                value={cloneFromDem}
                onChange={(e) => setCloneFromDem(e.target.value)}
                className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs text-white"
              >
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
                onClick={async () => {
                  if (!newDemName.trim()) return;
                  try {
                    const created = await api.createDemonstrator(
                      newDemName.trim(),
                      cloneFromDem
                    );
                    await loadDemonstrators(created.id);
                    setNewDemName('');
                    setShowNewDemModal(false);
                    showToast(`Created demonstrator ${created.id}`);
                  } catch (err: any) {
                    showToast(`Error: ${err.message}`);
                  }
                }}
                className="px-4 py-2 rounded-lg text-xs font-semibold bg-indigo-600 text-white hover:bg-indigo-500"
              >
                Create Demonstrator
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

