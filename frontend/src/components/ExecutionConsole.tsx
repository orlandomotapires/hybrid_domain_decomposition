import React, { useEffect, useRef, useState } from 'react';
import {
  Activity,
  CheckCircle2,
  Clock,
  ExternalLink,
  Loader2,
  Play,
  Square,
  Terminal,
  Trash2,
  XCircle,
} from 'lucide-react';
import { api } from '../api/client';
import {
  Demonstrator,
  LogEntry,
  SimulationJob,
  SimulationParameters,
} from '../types/pipeline';

interface ExecutionConsoleProps {
  demonstrators: Demonstrator[];
  selectedDemonstratorId: string;
  onSelectDemonstrator: (dem: Demonstrator) => void;
  activeJobId: string | null;
  onSelectJob: (jobId: string) => void;
  onInspectResultDir: (resultDir: string) => void;
  onTriggerRun: (
    dem?: Demonstrator,
    overrideParams?: SimulationParameters
  ) => Promise<void>;
}

const STAGES = [
  { id: 'initialization', label: '1. Input' },
  { id: 'coarsening', label: '2. Coarsen' },
  { id: 'partitioning', label: '3. Partition' },
  { id: 'uncoarsening', label: '4. Refine' },
  { id: 'permutation', label: '5. Output' },
];

export const ExecutionConsole: React.FC<ExecutionConsoleProps> = ({
  demonstrators,
  selectedDemonstratorId,
  onSelectDemonstrator,
  activeJobId,
  onSelectJob,
  onInspectResultDir,
  onTriggerRun,
}) => {
  const [jobs, setJobs] = useState<SimulationJob[]>([]);
  const [currentJob, setCurrentJob] = useState<SimulationJob | null>(null);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [levelFilter, setLevelFilter] = useState<string>('ALL');
  const logContainerRef = useRef<HTMLDivElement | null>(null);

  // Selected demonstrator & preset inside the Execution Console
  const selectedDem =
    demonstrators.find((d) => d.id === selectedDemonstratorId) || demonstrators[0];
  const [selectedPresetFile, setSelectedPresetFile] = useState<string>(
    selectedDem?.active_parameters_file || 'simulation_parameters.json'
  );
  const [presetParams, setPresetParams] = useState<SimulationParameters | null>(
    selectedDem?.simulation_parameters || null
  );

  useEffect(() => {
    if (!selectedDem) return;
    setSelectedPresetFile(selectedDem.active_parameters_file);
    setPresetParams(selectedDem.simulation_parameters);
  }, [selectedDem?.id, selectedDem?.active_parameters_file]);

  const handlePresetChange = async (filename: string) => {
    setSelectedPresetFile(filename);
    if (!selectedDem) return;
    if (filename === selectedDem.active_parameters_file) {
      setPresetParams(selectedDem.simulation_parameters);
      return;
    }
    try {
      const res = await api.getPreset(selectedDem.id, filename);
      setPresetParams(res.parameters);
    } catch {
      setPresetParams(selectedDem.simulation_parameters);
    }
  };

  const refreshJobsList = async () => {
    try {
      const res = await api.listJobs();
      setJobs(res.jobs);
      if (!activeJobId && res.jobs.length > 0) {
        onSelectJob(res.jobs[0].job_id);
      }
    } catch {
      // ignore
    }
  };

  const handleDeleteJobRecord = async (e: React.MouseEvent, jobId: string) => {
    e.stopPropagation();
    try {
      await api.deleteJob(jobId, false);
      const res = await api.listJobs();
      setJobs(res.jobs);
      if (activeJobId === jobId) {
        onSelectJob(res.jobs[0]?.job_id || '');
      }
    } catch {
      // ignore
    }
  };

  useEffect(() => {
    refreshJobsList();
    const timer = setInterval(refreshJobsList, 3000);
    return () => clearInterval(timer);
  }, [activeJobId]);

  useEffect(() => {
    if (!activeJobId) {
      setCurrentJob(null);
      setLogs([]);
      return;
    }

    let cancelled = false;
    let offset = 0;
    setLogs([]);

    const pollJob = async () => {
      try {
        const snapshot = await api.getJob(activeJobId, offset);
        if (cancelled) return;
        setCurrentJob(snapshot);
        if (snapshot.logs && snapshot.logs.length > 0) {
          setLogs((prev) => [...prev, ...(snapshot.logs || [])]);
          offset = snapshot.log_count;
        }
      } catch {
        // ignore
      }
    };

    pollJob();
    const interval = setInterval(pollJob, 600);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [activeJobId]);

  useEffect(() => {
    if (logContainerRef.current) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
    }
  }, [logs]);

  const filteredLogs =
    levelFilter === 'ALL' ? logs : logs.filter((l) => l.level === levelFilter);

  const currentStageIndex = STAGES.findIndex(
    (s) => s.id === (currentJob?.current_stage || 'initialization')
  );

  const activeParams = presetParams || selectedDem?.simulation_parameters;
  const activeStrat =
    activeParams?.partitioning_parameters.partitioning_strategy || 'quantum_annealing';
  const activeStratLabel =
    activeStrat === 'metis_partitioning'
      ? 'METIS Classical'
      : activeStrat === 'quantum_annealing'
      ? activeParams?.partitioning_parameters.strategies.quantum_annealing?.simulated
        ? 'Quantum Annealing (Emulated)'
        : 'Quantum Annealing (D-Wave QPU)'
      : activeParams?.partitioning_parameters.strategies.quantum_approximation_optimizer
          ?.simulated
      ? 'QAOA (Emulated)'
      : 'QAOA (QLM Hardware)';

  return (
    <div className="space-y-6 min-w-0">
      {/* Top Simulation & Demonstrator Launcher Bar */}
      {selectedDem && (
        <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-4 shadow-xl flex flex-wrap items-center justify-between gap-4 overflow-hidden">
          <div className="flex flex-wrap items-center gap-3 min-w-0">
            {/* Demonstrator Selector */}
            <div className="flex flex-wrap items-center gap-1.5 bg-slate-950 p-1 rounded-xl border border-slate-800">
              {demonstrators.map((dem) => {
                const active = dem.id === selectedDem.id;
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
                        active
                          ? 'bg-indigo-800 text-indigo-100'
                          : 'bg-slate-800 text-slate-400'
                      }`}
                    >
                      {stratShort}
                    </span>
                  </button>
                );
              })}
            </div>

            {/* Simulation Preset File Selector */}
            <select
              value={selectedPresetFile}
              onChange={(e) => handlePresetChange(e.target.value)}
              className="bg-slate-950 border border-slate-700 rounded-xl px-3 py-1.5 text-xs font-mono text-white focus:border-indigo-500 focus:outline-none max-w-[230px] truncate"
            >
              {selectedDem.preset_files.map((pf) => (
                <option key={pf} value={pf}>
                  {pf}
                </option>
              ))}
            </select>

            {/* Summary Badge of Selected Simulation */}
            {activeParams && (
              <span className="px-2.5 py-1 rounded-lg text-[11px] font-mono bg-violet-500/15 text-violet-300 border border-violet-500/30">
                {activeStratLabel}
              </span>
            )}
          </div>

          <button
            onClick={() => onTriggerRun(selectedDem, activeParams || undefined)}
            className="inline-flex items-center gap-2 px-5 py-2 rounded-xl text-xs font-bold bg-gradient-to-r from-indigo-600 to-violet-600 hover:from-indigo-500 hover:to-violet-500 text-white shadow-lg shadow-indigo-600/30 transition shrink-0"
          >
            <Play className="w-4 h-4 fill-current" />
            Run
          </button>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        {/* Left Sidebar: Recent Jobs */}
        <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-4 flex flex-col justify-between h-[680px] min-w-0 overflow-hidden">
          <div className="overflow-y-auto space-y-3 pr-1">
            <div className="flex items-center justify-between pb-3 border-b border-slate-800">
              <span className="text-xs font-bold uppercase tracking-wider text-slate-400">
                History
              </span>
              <span className="text-xs font-mono text-slate-400">{jobs.length}</span>
            </div>

            {jobs.length === 0 ? (
              <div className="text-center py-12 px-3 space-y-3">
                <Terminal className="w-8 h-8 text-slate-600 mx-auto" />
                <div className="text-xs text-slate-400">No runs yet</div>
                <button
                  onClick={() => onTriggerRun(selectedDem, activeParams || undefined)}
                  className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-semibold bg-indigo-600 text-white hover:bg-indigo-500 transition"
                >
                  <Play className="w-3.5 h-3.5 fill-current" />
                  Run
                </button>
              </div>
            ) : (
              jobs.map((job) => {
                const selected = job.job_id === activeJobId;
                return (
                  <div
                    key={job.job_id}
                    onClick={() => onSelectJob(job.job_id)}
                    className={`cursor-pointer w-full text-left p-3 rounded-xl border transition min-w-0 overflow-hidden ${
                      selected
                        ? 'bg-indigo-950/60 border-indigo-500'
                        : 'bg-slate-950/60 border-slate-800 hover:border-slate-700'
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-xs font-bold text-white truncate">{job.title}</span>
                      <div className="flex items-center gap-1.5 shrink-0">
                        {job.status === 'running' && (
                          <Loader2 className="w-3.5 h-3.5 text-indigo-400 animate-spin" />
                        )}
                        {job.status === 'completed' && (
                          <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                        )}
                        {job.status === 'failed' && (
                          <XCircle className="w-3.5 h-3.5 text-rose-400" />
                        )}
                        {job.status !== 'running' && (
                          <button
                            type="button"
                            onClick={(e) => handleDeleteJobRecord(e, job.job_id)}
                            className="p-1 rounded text-slate-500 hover:text-rose-400 hover:bg-rose-950/40 transition"
                            title="Remove from history"
                          >
                            <Trash2 className="w-3 h-3" />
                          </button>
                        )}
                      </div>
                    </div>
                    <div className="mt-1.5 flex items-center justify-between text-[11px] text-slate-400 font-mono">
                      <span className="truncate">{job.job_id.slice(0, 19)}</span>
                      <span className="shrink-0">
                        {job.elapsed_sec && job.elapsed_sec > 0
                          ? `${job.elapsed_sec.toFixed(1)}s`
                          : job.status}
                      </span>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* Main Execution Monitor */}
        <div className="lg:col-span-3 space-y-5 min-w-0">
          {currentJob ? (
            <>
              {/* Stage Progress & Telemetry Card */}
              <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 space-y-5 overflow-hidden">
                <div className="flex flex-wrap items-center justify-between gap-4">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2.5">
                      <h3
                        className="text-base font-bold text-white truncate"
                        title={`Job ID: ${currentJob.job_id}${
                          currentJob.pid ? ` • PID: ${currentJob.pid}` : ''
                        }`}
                      >
                        {currentJob.title}
                      </h3>
                      <span
                        className={`px-2.5 py-0.5 rounded-full text-xs font-semibold uppercase shrink-0 ${
                          currentJob.status === 'running'
                            ? 'bg-indigo-500/20 text-indigo-300 border border-indigo-500/40'
                            : currentJob.status === 'completed'
                            ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
                            : 'bg-rose-500/20 text-rose-300 border border-rose-500/40'
                        }`}
                      >
                        {currentJob.status}
                      </span>
                      {currentJob.elapsed_sec !== undefined && currentJob.elapsed_sec > 0 && (
                        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-mono text-cyan-300 bg-cyan-500/10 border border-cyan-500/30 shrink-0">
                          <Clock className="w-3 h-3" />
                          {currentJob.elapsed_sec.toFixed(2)}s
                        </span>
                      )}
                    </div>
                  </div>

                  <div className="flex items-center gap-2.5">
                    {currentJob.status === 'running' && (
                      <button
                        onClick={() => api.cancelJob(currentJob.job_id)}
                        className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl text-xs font-semibold bg-rose-600/20 text-rose-300 border border-rose-500/40 hover:bg-rose-600/30 transition"
                      >
                        <Square className="w-3.5 h-3.5 fill-current" />
                        Stop
                      </button>
                    )}
                    {currentJob.result_dir && (
                      <button
                        onClick={() => onInspectResultDir(currentJob.result_dir!)}
                        className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-bold bg-emerald-600 hover:bg-emerald-500 text-white shadow-lg shadow-emerald-600/20 transition"
                      >
                        <ExternalLink className="w-3.5 h-3.5" />
                        View Results
                      </button>
                    )}
                  </div>
                </div>

                {/* 5-Stage Progress Stepper with Per-Stage Timing */}
                <div className="grid grid-cols-5 gap-2">
                  {STAGES.map((stage, idx) => {
                    const isDone =
                      currentJob.status === 'completed' || idx < currentStageIndex;
                    const isActive =
                      currentJob.status === 'running' && idx === currentStageIndex;
                    const dur = currentJob.stage_durations_sec?.[stage.id];
                    return (
                      <div
                        key={stage.id}
                        className={`p-2.5 rounded-xl border text-center transition min-w-0 overflow-hidden ${
                          isDone
                            ? 'bg-emerald-950/40 border-emerald-500/40 text-emerald-300'
                            : isActive
                            ? 'bg-indigo-950/60 border-indigo-400 text-white ring-2 ring-indigo-500/20'
                            : 'bg-slate-950/50 border-slate-800 text-slate-400'
                        }`}
                      >
                        <div className="text-xs font-semibold truncate">{stage.label}</div>
                        {dur !== undefined && dur > 0 && (
                          <div className="text-[10px] font-mono text-slate-300 mt-0.5">
                            {dur.toFixed(2)}s
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>

                {/* Live Extracted Graph Telemetry */}
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-2">
                  <div className="p-3 rounded-xl bg-slate-950/80 border border-slate-800 min-w-0 overflow-hidden">
                    <div className="text-[11px] text-slate-400">Fine Graph</div>
                    <div className="text-sm font-mono font-bold text-white mt-0.5 truncate">
                      {currentJob.telemetry.initial_nodes !== undefined
                        ? `${currentJob.telemetry.initial_nodes.toLocaleString()} nodes`
                        : '—'}
                    </div>
                    <div className="text-[11px] font-mono text-slate-400 truncate">
                      {currentJob.telemetry.initial_edges !== undefined
                        ? `${currentJob.telemetry.initial_edges.toLocaleString()} edges`
                        : ''}
                    </div>
                  </div>

                  <div className="p-3 rounded-xl bg-slate-950/80 border border-slate-800 min-w-0 overflow-hidden">
                    <div className="text-[11px] text-slate-400">Coarse Graph</div>
                    <div className="text-sm font-mono font-bold text-amber-300 mt-0.5 truncate">
                      {currentJob.telemetry.coarse_nodes !== undefined
                        ? `${currentJob.telemetry.coarse_nodes.toLocaleString()} nodes`
                        : '—'}
                    </div>
                    <div className="text-[11px] font-mono text-slate-400 truncate">
                      {currentJob.telemetry.coarse_edges !== undefined
                        ? `${currentJob.telemetry.coarse_edges.toLocaleString()} edges`
                        : ''}
                    </div>
                  </div>

                  <div className="p-3 rounded-xl bg-slate-950/80 border border-slate-800 min-w-0 overflow-hidden">
                    <div className="text-[11px] text-slate-400">Levels</div>
                    <div className="text-sm font-mono font-bold text-cyan-300 mt-0.5 truncate">
                      {currentJob.telemetry.coarsening_levels !== undefined
                        ? `${currentJob.telemetry.coarsening_levels}`
                        : '—'}
                    </div>
                  </div>

                  <div className="p-3 rounded-xl bg-slate-950/80 border border-slate-800 min-w-0 overflow-hidden">
                    <div className="text-[11px] text-slate-400">Parts</div>
                    <div className="text-sm font-mono font-bold text-violet-300 mt-0.5 truncate">
                      {currentJob.telemetry.coarse_parts !== undefined
                        ? `k = ${currentJob.telemetry.coarse_parts}`
                        : '—'}
                    </div>
                  </div>
                </div>
              </div>

              {/* Live Log Terminal */}
              <div className="bg-slate-950 border border-slate-800 rounded-2xl overflow-hidden shadow-xl">
                <div className="px-4 py-3 bg-slate-900 border-b border-slate-800 flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <Terminal className="w-4 h-4 text-indigo-400" />
                    <span className="text-xs font-mono font-semibold text-slate-200">
                      Log
                    </span>
                  </div>

                  <div className="flex flex-wrap items-center gap-1.5">
                    {['ALL', 'INFO', 'VERBOSE', 'WARNING', 'ERROR'].map((lvl) => {
                      const count =
                        lvl === 'ALL'
                          ? logs.length
                          : logs.filter((l) => l.level === lvl).length;
                      return (
                        <button
                          key={lvl}
                          onClick={() => setLevelFilter(lvl)}
                          className={`px-2 py-0.5 rounded text-[11px] font-mono transition flex items-center gap-1 ${
                            levelFilter === lvl
                              ? 'bg-indigo-600 text-white'
                              : 'bg-slate-800 text-slate-400 hover:text-slate-200'
                          }`}
                        >
                          <span>{lvl}</span>
                          <span
                            className={`text-[10px] ${
                              levelFilter === lvl ? 'text-indigo-200' : 'text-slate-500'
                            }`}
                          >
                            ({count})
                          </span>
                        </button>
                      );
                    })}
                  </div>
                </div>

                <div
                  ref={logContainerRef}
                  className="p-4 h-[420px] overflow-y-auto font-mono text-xs space-y-1.5"
                >
                  {filteredLogs.length === 0 ? (
                    <div className="text-slate-500 py-8 text-center">
                      {logs.length === 0
                        ? 'Waiting for log output...'
                        : `No ${levelFilter} entries.`}
                    </div>
                  ) : (
                    filteredLogs.map((entry, idx) => (
                      <div key={idx} className="flex items-start gap-2.5 leading-relaxed">
                        <span className="text-slate-500 shrink-0">{entry.timestamp}</span>
                        <span
                          className={`px-1.5 py-0.2 rounded text-[10px] font-bold shrink-0 ${
                            entry.level === 'ERROR'
                              ? 'bg-rose-500/20 text-rose-400'
                              : entry.level === 'WARNING'
                              ? 'bg-amber-500/20 text-amber-300'
                              : entry.level === 'VERBOSE'
                              ? 'bg-cyan-500/15 text-cyan-300'
                              : 'bg-emerald-500/15 text-emerald-300'
                          }`}
                        >
                          {entry.level}
                        </span>
                        <span className="text-slate-200 break-all">{entry.message}</span>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </>
          ) : (
            <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-12 text-center space-y-4">
              <Activity className="w-10 h-10 text-indigo-400 mx-auto" />
              <h3 className="text-base font-bold text-white">No Run Selected</h3>
              <button
                onClick={() => onTriggerRun(selectedDem, activeParams || undefined)}
                className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl text-xs font-bold bg-indigo-600 hover:bg-indigo-500 text-white transition"
              >
                <Play className="w-4 h-4 fill-current" />
                Run
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
