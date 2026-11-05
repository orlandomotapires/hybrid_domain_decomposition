import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  Activity,
  ArrowDown,
  Bell,
  BellOff,
  CheckCircle2,
  Clock,
  Copy,
  Download,
  ExternalLink,
  Layers,
  Loader2,
  Play,
  Search,
  Square,
  Terminal,
  Trash2,
  X,
  XCircle,
} from 'lucide-react';
import { api } from '../api/client';
import { downloadText, safeFilename } from '../lib/download';
import { METHOD_SHORT_LABELS, MethodKey, methodColor, methodKey, methodLabel } from '../lib/labels';
import {
  notificationPermission,
  requestNotificationPermission,
} from '../lib/notify';
import {
  Demonstrator,
  LogEntry,
  SimulationJob,
} from '../types/pipeline';
import { useToast } from './Toasts';

interface ExecutionConsoleProps {
  demonstrators: Demonstrator[];
  jobs: SimulationJob[];
  onRefreshJobs: () => Promise<void> | void;
  activeJobId: string | null;
  onSelectJob: (jobId: string) => void;
  onInspectResultDir: (resultDir: string) => void;
  onInspectBatchRun?: (batchId: string) => void;
  /** Switch to the Single Run tab, where runs are configured and started. */
  onGoToSingleRun: () => void;
}

const STAGES = [
  { id: 'initialization', label: '1. Input' },
  { id: 'coarsening', label: '2. Coarsen' },
  { id: 'partitioning', label: '3. Partition' },
  { id: 'uncoarsening', label: '4. Refine' },
  { id: 'permutation', label: '5. Output' },
];

const TERMINAL_STATUSES: SimulationJob['status'][] = ['completed', 'failed', 'cancelled'];
const UNDO_DELETE_MS = 7000;
const RECENT_RUNS_IN_EMPTY_STATE = 5;

/** Shared height for the history list and the monitor column so both fill the viewport. */
const PANEL_HEIGHT = 'h-[480px] lg:h-[calc(100vh-14rem)] lg:min-h-[600px]';

function formatDuration(sec: number): string {
  if (!isFinite(sec) || sec < 0) return '—';
  if (sec < 60) return `${Math.round(sec)}s`;
  const m = Math.floor(sec / 60);
  const s = Math.round(sec % 60);
  if (m < 60) return `${m}m ${s.toString().padStart(2, '0')}s`;
  const h = Math.floor(m / 60);
  return `${h}h ${(m % 60).toString().padStart(2, '0')}m`;
}

/* ---------------- Run metadata helpers ---------------- */

function jobMatrix(job: SimulationJob): string | null {
  if (job.demonstrator_id) return job.demonstrator_id;
  if (job.demonstrator_dir) return job.demonstrator_dir.replace(/\/+$/, '').split('/').pop() || null;
  return null;
}

function jobMethodKey(job: SimulationJob): MethodKey | null {
  return job.partitioning_strategy ? methodKey(job.partitioning_strategy, job.simulated) : null;
}

function jobMethodLabel(job: SimulationJob, short = true): string | null {
  return job.partitioning_strategy ? methodLabel(job.partitioning_strategy, job.simulated, short) : null;
}

function jobK(job: SimulationJob): number | null {
  return job.k_target ?? job.telemetry?.coarse_parts ?? null;
}

/** "simulation_01 · QA Emulated" for single runs; batch jobs keep their backend title. */
function jobDisplayTitle(job: SimulationJob): string {
  if (job.job_type === 'batch') return job.title;
  const matrix = jobMatrix(job);
  const method = jobMethodLabel(job);
  if (!matrix) return job.title.replace(/^Simulation: /, '');
  return method ? `${matrix} · ${method}` : matrix;
}

function parseDate(iso: string | null | undefined): Date | null {
  if (!iso) return null;
  const d = new Date(iso);
  return isNaN(d.getTime()) ? null : d;
}

function localDayKey(d: Date): string {
  return `${d.getFullYear()}-${d.getMonth() + 1}-${d.getDate()}`;
}

function dayLabel(d: Date): string {
  const today = new Date();
  const yesterday = new Date();
  yesterday.setDate(today.getDate() - 1);
  if (localDayKey(d) === localDayKey(today)) return 'Today';
  if (localDayKey(d) === localDayKey(yesterday)) return 'Yesterday';
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

function shortTime(d: Date): string {
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

/** Time, plus a short date when the run is not from today. */
function cardTime(d: Date): string {
  if (localDayKey(d) === localDayKey(new Date())) return shortTime(d);
  return `${d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })} ${shortTime(d)}`;
}

function fullDateTime(d: Date): string {
  return d.toLocaleString('en-US', {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

const StatusIcon: React.FC<{ status: SimulationJob['status'] }> = ({ status }) => {
  if (status === 'running') return <Loader2 className="w-3.5 h-3.5 text-indigo-400 animate-spin" aria-label="Running" />;
  if (status === 'completed') return <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" aria-label="Completed" />;
  if (status === 'cancelled') return <XCircle className="w-3.5 h-3.5 text-amber-400" aria-label="Cancelled" />;
  return <XCircle className="w-3.5 h-3.5 text-rose-400" aria-label="Failed" />;
};

const MethodDot: React.FC<{ job: SimulationJob }> = ({ job }) => {
  const k = jobMethodKey(job);
  if (!k) return null;
  return (
    <span
      className="inline-block w-2 h-2 rounded-full shrink-0"
      style={{ backgroundColor: methodColor(k) }}
      aria-hidden="true"
    />
  );
};

const FILTER_SELECT_CLS =
  'min-w-0 flex-1 bg-slate-950 border border-slate-700 rounded-lg px-2 py-1 text-xs text-slate-200 focus:border-indigo-500 focus:outline-none';

export const ExecutionConsole: React.FC<ExecutionConsoleProps> = ({
  demonstrators,
  jobs,
  onRefreshJobs,
  activeJobId,
  onSelectJob,
  onInspectResultDir,
  onInspectBatchRun,
  onGoToSingleRun,
}) => {
  const toast = useToast();
  const [currentJob, setCurrentJob] = useState<SimulationJob | null>(null);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [levelFilter, setLevelFilter] = useState<string>('ALL');
  const [logSearch, setLogSearch] = useState('');
  const [followLog, setFollowLog] = useState(true);
  const [pendingDeletes, setPendingDeletes] = useState<Set<string>>(new Set());
  const [notifyState, setNotifyState] = useState(notificationPermission());
  const [matrixFilter, setMatrixFilter] = useState('all');
  const [methodFilter, setMethodFilter] = useState('all');
  const [statusFilter, setStatusFilter] = useState('all');
  const logContainerRef = useRef<HTMLDivElement | null>(null);

  /* ---------------- History (filters, grouping, undo-able delete) ---------------- */

  const visibleJobs = jobs.filter((j) => !pendingDeletes.has(j.job_id));

  // Auto-open a live run so its log streams immediately; otherwise show the overview.
  const runningJobId = visibleJobs.find((j) => j.status === 'running')?.job_id;
  useEffect(() => {
    if (!activeJobId && runningJobId) onSelectJob(runningJobId);
  }, [activeJobId, runningJobId]);

  const matrixOptions = useMemo(
    () =>
      Array.from(new Set(visibleJobs.map(jobMatrix).filter((m): m is string => !!m))).sort(),
    [visibleJobs]
  );
  const methodOptions = useMemo(() => {
    const keys = new Set<string>();
    for (const j of visibleJobs) {
      if (j.job_type === 'batch') keys.add('batch');
      else {
        const k = jobMethodKey(j);
        if (k) keys.add(k);
      }
    }
    return Array.from(keys);
  }, [visibleJobs]);

  const filtersActive = matrixFilter !== 'all' || methodFilter !== 'all' || statusFilter !== 'all';

  const filteredJobs = visibleJobs.filter((j) => {
    if (matrixFilter !== 'all' && jobMatrix(j) !== matrixFilter) return false;
    if (methodFilter !== 'all') {
      const k = j.job_type === 'batch' ? 'batch' : jobMethodKey(j);
      if (k !== methodFilter) return false;
    }
    if (statusFilter !== 'all' && j.status !== statusFilter) return false;
    return true;
  });

  const groupedJobs = useMemo(() => {
    const groups: Array<{ key: string; label: string; jobs: SimulationJob[] }> = [];
    const sorted = [...filteredJobs].sort((a, b) => (b.created_at || '').localeCompare(a.created_at || ''));
    for (const job of sorted) {
      const d = parseDate(job.created_at);
      const key = d ? localDayKey(d) : 'unknown';
      let g = groups[groups.length - 1];
      if (!g || g.key !== key) {
        g = { key, label: d ? dayLabel(d) : 'Unknown date', jobs: [] };
        groups.push(g);
      }
      g.jobs.push(job);
    }
    return groups;
  }, [filteredJobs]);

  const recentCompleted = visibleJobs
    .filter((j) => j.status === 'completed')
    .slice(0, RECENT_RUNS_IN_EMPTY_STATE);

  const handleDeleteJobRecord = (e: React.MouseEvent, job: SimulationJob) => {
    e.stopPropagation();
    const jobId = job.job_id;
    setPendingDeletes((prev) => new Set(prev).add(jobId));
    if (activeJobId === jobId) onSelectJob('');
    let undone = false;
    toast.info(`Removed "${jobDisplayTitle(job)}" from history. Result files are kept.`, {
      durationMs: UNDO_DELETE_MS,
      action: {
        label: 'Undo',
        onClick: () => {
          undone = true;
          setPendingDeletes((prev) => {
            const next = new Set(prev);
            next.delete(jobId);
            return next;
          });
        },
      },
    });
    window.setTimeout(async () => {
      if (undone) return;
      try {
        await api.deleteJob(jobId, false);
        await onRefreshJobs();
      } catch (err: any) {
        toast.error(`Could not remove run record: ${err.message}`);
      } finally {
        setPendingDeletes((prev) => {
          const next = new Set(prev);
          next.delete(jobId);
          return next;
        });
      }
    }, UNDO_DELETE_MS);
  };

  /* ---------------- Live job polling ---------------- */

  useEffect(() => {
    if (!activeJobId) {
      setCurrentJob(null);
      setLogs([]);
      return;
    }

    let cancelled = false;
    let offset = 0;
    let timer: number | null = null;
    setLogs([]);
    setFollowLog(true);

    const pollJob = async () => {
      try {
        const snapshot = await api.getJob(activeJobId, offset);
        if (cancelled) return;
        setCurrentJob(snapshot);
        if (snapshot.logs && snapshot.logs.length > 0) {
          setLogs((prev) => [...prev, ...(snapshot.logs || [])]);
          offset = snapshot.log_count;
        }
        // Finished jobs don't change any more: stop polling.
        if (TERMINAL_STATUSES.includes(snapshot.status)) return;
      } catch {
        // connectivity is reported by the header indicator; keep retrying
      }
      if (!cancelled) timer = window.setTimeout(pollJob, 700);
    };

    pollJob();
    return () => {
      cancelled = true;
      if (timer) window.clearTimeout(timer);
    };
  }, [activeJobId]);

  /* ---------------- Log view ---------------- */

  // Only stick to the bottom while the user hasn't scrolled up to read something.
  useEffect(() => {
    const el = logContainerRef.current;
    if (el && followLog) el.scrollTop = el.scrollHeight;
  }, [logs, followLog, levelFilter, logSearch]);

  const handleLogScroll = () => {
    const el = logContainerRef.current;
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 24;
    setFollowLog(atBottom);
  };

  const jumpToLatest = () => {
    setFollowLog(true);
    const el = logContainerRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  };

  const filteredLogs = useMemo(() => {
    const q = logSearch.trim().toLowerCase();
    return logs.filter(
      (l) =>
        (levelFilter === 'ALL' || l.level === levelFilter) &&
        (!q || l.message.toLowerCase().includes(q))
    );
  }, [logs, levelFilter, logSearch]);

  const logsAsText = (entries: LogEntry[]) =>
    entries.map((l) => `[${l.timestamp} ${l.level}] ${l.message}`).join('\n');

  const copyLogs = async () => {
    try {
      await navigator.clipboard.writeText(logsAsText(filteredLogs));
      toast.success(`Copied ${filteredLogs.length} log lines`);
    } catch {
      toast.error('Clipboard is not available in this browser context');
    }
  };

  const downloadLogs = () => {
    if (!currentJob) return;
    downloadText(logsAsText(logs) + '\n', `${safeFilename(currentJob.job_id)}.log`);
  };

  const toggleNotifications = async () => {
    if (notifyState === 'granted') {
      toast.info('To turn notifications off, change this site’s permission in your browser.');
      return;
    }
    const res = await requestNotificationPermission();
    setNotifyState(res);
    if (res === 'granted') toast.success('You’ll get a desktop notification when a run finishes.');
    else if (res === 'denied') toast.error('Notifications are blocked for this site in your browser settings.');
  };

  const currentStageIndex = STAGES.findIndex(
    (s) => s.id === (currentJob?.current_stage || 'initialization')
  );

  /* ---------------- Monitor heading ---------------- */

  const viewingParts: string[] = [];
  if (currentJob) {
    if (currentJob.job_type === 'batch') {
      viewingParts.push(currentJob.title);
    } else {
      const m = jobMatrix(currentJob);
      const meth = jobMethodLabel(currentJob, false);
      const k = jobK(currentJob);
      if (m) viewingParts.push(m);
      if (meth) viewingParts.push(meth);
      if (k != null) viewingParts.push(`k=${k}`);
      if (viewingParts.length === 0) viewingParts.push(jobDisplayTitle(currentJob));
    }
  }
  const currentCreated = parseDate(currentJob?.created_at);
  const currentFinished = parseDate(currentJob?.finished_at);

  /* ---------------- Batch progress ---------------- */

  const batch = currentJob?.job_type === 'batch' ? currentJob.telemetry : null;
  const batchTotal = batch?.batch_total || 0;
  const batchDone = batch?.batch_done || 0;
  const batchEtaSec =
    currentJob?.status === 'running' && batchDone > 0 && batchTotal > batchDone
      ? ((currentJob.elapsed_sec || 0) / batchDone) * (batchTotal - batchDone)
      : null;

  const newRunButton = () => (
    <button
      type="button"
      onClick={onGoToSingleRun}
      className="inline-flex items-center gap-2 rounded-xl font-bold bg-indigo-600 hover:bg-indigo-500 text-white shadow-lg shadow-indigo-600/30 transition px-3.5 py-2 text-xs"
    >
      <Play className="w-3.5 h-3.5 fill-current" />
      New run in Single Run
    </button>
  );

  const notifyButton =
    notifyState !== 'unsupported' ? (
      <button
        type="button"
        onClick={toggleNotifications}
        title={
          notifyState === 'granted'
            ? 'Desktop notifications are on for finished runs'
            : 'Get a desktop notification when a run finishes'
        }
        aria-label={notifyState === 'granted' ? 'Desktop notifications on' : 'Enable desktop notifications'}
        className={`p-1.5 rounded-lg border transition ${
          notifyState === 'granted'
            ? 'border-emerald-500/40 text-emerald-300 bg-emerald-500/10'
            : 'border-slate-700 text-slate-400 hover:text-white hover:bg-slate-800'
        }`}
      >
        {notifyState === 'granted' ? <Bell className="w-3.5 h-3.5" /> : <BellOff className="w-3.5 h-3.5" />}
      </button>
    ) : null;

  return (
    <div className="space-y-6 min-w-0">
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        {/* History */}
        <aside
          aria-label="Run history"
          className={`bg-slate-900/80 border border-slate-800 rounded-2xl p-4 flex flex-col gap-3 min-w-0 overflow-hidden ${PANEL_HEIGHT}`}
        >
          <div className="shrink-0 space-y-2.5">
            <div className="flex items-center justify-between pb-2.5 border-b border-slate-800">
              <span className="text-xs font-bold uppercase tracking-wider text-slate-400">History</span>
              <span className="flex items-center gap-2">
                <span className="text-xs font-mono text-slate-400">
                  {filtersActive ? `${filteredJobs.length}/${visibleJobs.length}` : visibleJobs.length}
                </span>
                {notifyButton}
              </span>
            </div>
            {visibleJobs.length > 0 && (
              <div className="space-y-1.5">
                <div className="flex gap-1.5">
                  <select
                    value={matrixFilter}
                    onChange={(e) => setMatrixFilter(e.target.value)}
                    aria-label="Filter history by simulation"
                    className={FILTER_SELECT_CLS}
                  >
                    <option value="all">All simulations</option>
                    {matrixOptions.map((m) => (
                      <option key={m} value={m}>
                        {m}
                      </option>
                    ))}
                  </select>
                  <select
                    value={statusFilter}
                    onChange={(e) => setStatusFilter(e.target.value)}
                    aria-label="Filter history by status"
                    className={FILTER_SELECT_CLS}
                  >
                    <option value="all">Any status</option>
                    <option value="running">Running</option>
                    <option value="completed">Completed</option>
                    <option value="failed">Failed</option>
                    <option value="cancelled">Cancelled</option>
                  </select>
                </div>
                <div className="flex gap-1.5">
                  <select
                    value={methodFilter}
                    onChange={(e) => setMethodFilter(e.target.value)}
                    aria-label="Filter history by method"
                    className={FILTER_SELECT_CLS}
                  >
                    <option value="all">All methods</option>
                    {methodOptions.map((k) => (
                      <option key={k} value={k}>
                        {k === 'batch' ? 'Batch studies' : METHOD_SHORT_LABELS[k as MethodKey] || k}
                      </option>
                    ))}
                  </select>
                  {filtersActive && (
                    <button
                      type="button"
                      onClick={() => {
                        setMatrixFilter('all');
                        setMethodFilter('all');
                        setStatusFilter('all');
                      }}
                      className="shrink-0 px-2 py-1 rounded-lg text-xs text-slate-300 hover:text-white hover:bg-slate-800"
                    >
                      Clear
                    </button>
                  )}
                </div>
              </div>
            )}
          </div>

          <div className="flex-1 min-h-0 overflow-y-auto pr-1 space-y-4">
            {visibleJobs.length === 0 ? (
              <div className="text-center py-12 px-3 space-y-3">
                <Terminal className="w-8 h-8 text-slate-600 mx-auto" />
                <div className="text-xs text-slate-400">Runs you start will appear here.</div>
                {newRunButton()}
              </div>
            ) : filteredJobs.length === 0 ? (
              <div className="text-center py-10 px-3 text-xs text-slate-400">No runs match these filters.</div>
            ) : (
              groupedJobs.map((group) => (
                <div key={group.key} className="space-y-2">
                  <div className="sticky top-0 z-10 bg-slate-900 py-1 text-xs font-semibold uppercase tracking-wider text-slate-400">
                    {group.label}
                  </div>
                  {group.jobs.map((job) => {
                    const selected = job.job_id === activeJobId;
                    const jt = job.telemetry;
                    const created = parseDate(job.created_at);
                    const k = jobK(job);
                    const meta: string[] = [];
                    if (created) meta.push(cardTime(created));
                    if (job.job_type === 'batch' && job.status === 'running' && jt.batch_total) {
                      meta.push(`${jt.batch_done || 0}/${jt.batch_total}`);
                    } else if (job.elapsed_sec && job.elapsed_sec > 0) {
                      meta.push(formatDuration(job.elapsed_sec));
                    }
                    if (job.job_type !== 'batch' && k != null) meta.push(`k=${k}`);
                    const title = jobDisplayTitle(job);
                    return (
                      <div
                        key={job.job_id}
                        role="button"
                        tabIndex={0}
                        aria-current={selected ? 'true' : undefined}
                        onClick={() => onSelectJob(job.job_id)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' || e.key === ' ') {
                            e.preventDefault();
                            onSelectJob(job.job_id);
                          }
                        }}
                        className={`cursor-pointer w-full text-left p-3 rounded-xl border transition min-w-0 overflow-hidden focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 ${
                          selected
                            ? 'bg-indigo-950/60 border-indigo-500'
                            : 'bg-slate-950/60 border-slate-800 hover:border-slate-700'
                        }`}
                      >
                        <div className="flex items-center justify-between gap-2">
                          <span className="flex items-center gap-1.5 min-w-0">
                            {job.job_type === 'batch' ? (
                              <Layers className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                            ) : (
                              <MethodDot job={job} />
                            )}
                            <span className="text-xs font-bold text-white truncate" title={`${title}\n${job.job_id}`}>
                              {title}
                            </span>
                          </span>
                          <div className="flex items-center gap-1.5 shrink-0">
                            <StatusIcon status={job.status} />
                            {job.status !== 'running' && (
                              <button
                                type="button"
                                onClick={(e) => handleDeleteJobRecord(e, job)}
                                className="p-1 rounded text-slate-500 hover:text-rose-400 hover:bg-rose-950/40 transition"
                                title="Remove from history (result files are kept)"
                                aria-label={`Remove ${title} from history`}
                              >
                                <Trash2 className="w-3 h-3" />
                              </button>
                            )}
                          </div>
                        </div>
                        <div className="mt-1.5 text-xs text-slate-400 font-mono truncate">
                          {meta.join(' · ') || job.status}
                        </div>
                      </div>
                    );
                  })}
                </div>
              ))
            )}
          </div>
        </aside>

        {/* Main monitor */}
        <div className={`lg:col-span-3 flex flex-col gap-5 min-w-0 ${currentJob ? PANEL_HEIGHT.replace('h-[480px] ', '') : ''}`}>
          {currentJob ? (
            <>
              <div className="shrink-0 bg-slate-900/80 border border-slate-800 rounded-2xl p-5 space-y-5 overflow-hidden">
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div className="min-w-0 space-y-1">
                    <div className="flex flex-wrap items-center gap-2.5">
                      <h2
                        className="text-base font-bold text-white truncate"
                        title={`Job ID: ${currentJob.job_id}${currentJob.pid ? ` • PID: ${currentJob.pid}` : ''}`}
                      >
                        <span className="text-slate-400 font-semibold">Viewing:</span>{' '}
                        {viewingParts.join(' · ')}
                      </h2>
                      <span
                        className={`px-2.5 py-0.5 rounded-full text-xs font-semibold uppercase shrink-0 ${
                          currentJob.status === 'running'
                            ? 'bg-indigo-500/20 text-indigo-300 border border-indigo-500/40'
                            : currentJob.status === 'completed'
                            ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
                            : currentJob.status === 'cancelled'
                            ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40'
                            : 'bg-rose-500/20 text-rose-300 border border-rose-500/40'
                        }`}
                      >
                        {currentJob.status}
                      </span>
                      {currentJob.elapsed_sec !== undefined && currentJob.elapsed_sec > 0 && (
                        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-mono text-slate-200 bg-slate-800 border border-slate-700 shrink-0">
                          <Clock className="w-3 h-3" />
                          {formatDuration(currentJob.elapsed_sec)}
                        </span>
                      )}
                    </div>
                    {currentCreated && (
                      <p className="text-xs text-slate-400">
                        {currentJob.status === 'running' ? 'Started' : 'Run on'} {fullDateTime(currentCreated)}
                        {currentFinished &&
                          currentJob.status !== 'running' &&
                          currentFinished.getTime() - currentCreated.getTime() > 1000 && (
                            <> · finished {shortTime(currentFinished)}</>
                          )}
                      </p>
                    )}
                    {currentJob.status === 'failed' && currentJob.error_message && (
                      <p className="text-xs text-rose-300 break-words">{currentJob.error_message}</p>
                    )}
                  </div>

                  <div className="flex items-center gap-2.5">
                    {currentJob.status === 'running' && (
                      <button
                        type="button"
                        onClick={async () => {
                          if (!window.confirm('Stop this run? Partial results will not be saved.')) return;
                          try {
                            await api.cancelJob(currentJob.job_id);
                            onRefreshJobs();
                          } catch (err: any) {
                            toast.error(`Could not stop run: ${err.message}`);
                          }
                        }}
                        className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl text-xs font-semibold bg-rose-600/20 text-rose-300 border border-rose-500/40 hover:bg-rose-600/30 transition"
                      >
                        <Square className="w-3.5 h-3.5 fill-current" />
                        Stop
                      </button>
                    )}
                    {currentJob.result_dir && (
                      <button
                        type="button"
                        onClick={() => onInspectResultDir(currentJob.result_dir!)}
                        className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-bold bg-indigo-600 hover:bg-indigo-500 text-white shadow-lg shadow-indigo-600/20 transition"
                      >
                        <ExternalLink className="w-3.5 h-3.5" />
                        View Results
                      </button>
                    )}
                    {!currentJob.result_dir &&
                      currentJob.batch_dir &&
                      currentJob.status === 'completed' &&
                      onInspectBatchRun && (
                        <button
                          type="button"
                          onClick={() => onInspectBatchRun(currentJob.batch_dir!.split('/').pop() || '')}
                          className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-bold bg-indigo-600 hover:bg-indigo-500 text-white shadow-lg shadow-indigo-600/20 transition"
                        >
                          <ExternalLink className="w-3.5 h-3.5" />
                          View Batch Results
                        </button>
                      )}
                    <button
                      type="button"
                      onClick={() => onSelectJob('')}
                      title="Close this run and go back to the overview"
                      aria-label="Close run"
                      className="p-2 rounded-xl text-slate-400 hover:text-white hover:bg-slate-800 transition"
                    >
                      <X className="w-4 h-4" />
                    </button>
                  </div>
                </div>

                {/* Batch progress */}
                {batch && batchTotal > 0 && (
                  <div className="p-3.5 rounded-xl bg-slate-950/80 border border-slate-800 space-y-2">
                    <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
                      <span className="text-slate-300">
                        <strong className="text-white">
                          {batchDone} / {batchTotal}
                        </strong>{' '}
                        cases finished
                        {batch.batch_failed ? (
                          <span className="text-rose-300"> · {batch.batch_failed} failed</span>
                        ) : null}
                      </span>
                      <span className="font-mono text-slate-400">
                        {currentJob.status === 'running'
                          ? batchEtaSec !== null
                            ? `≈ ${formatDuration(batchEtaSec)} left`
                            : 'estimating time left…'
                          : `took ${formatDuration(currentJob.elapsed_sec || 0)}`}
                      </span>
                    </div>
                    <div className="h-2 rounded-full bg-slate-800 overflow-hidden">
                      <div
                        className="h-full bg-indigo-500 transition-all"
                        style={{ width: `${Math.min(100, (batchDone / batchTotal) * 100)}%` }}
                      />
                    </div>
                    {currentJob.status === 'running' && batch.batch_case && (
                      <div className="text-xs font-mono text-slate-400 truncate">
                        Now running [{batch.batch_index}/{batchTotal}] {batch.batch_case}
                      </div>
                    )}
                  </div>
                )}

                {/* 5-stage stepper */}
                <div className="grid grid-cols-5 gap-2">
                  {STAGES.map((stage, idx) => {
                    const isDone = currentJob.status === 'completed' || idx < currentStageIndex;
                    const isActive = currentJob.status === 'running' && idx === currentStageIndex;
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
                          <div className="text-xs font-mono text-slate-300 mt-0.5">{dur.toFixed(2)}s</div>
                        )}
                      </div>
                    );
                  })}
                </div>

                {/* Graph telemetry */}
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  <TelemetryTile
                    label="Fine Graph"
                    value={currentJob.telemetry.initial_nodes !== undefined ? `${currentJob.telemetry.initial_nodes.toLocaleString()} nodes` : '—'}
                    sub={currentJob.telemetry.initial_edges !== undefined ? `${currentJob.telemetry.initial_edges.toLocaleString()} edges` : ''}
                  />
                  <TelemetryTile
                    label="Coarse Graph"
                    value={currentJob.telemetry.coarse_nodes !== undefined ? `${currentJob.telemetry.coarse_nodes.toLocaleString()} nodes` : '—'}
                    sub={currentJob.telemetry.coarse_edges !== undefined ? `${currentJob.telemetry.coarse_edges.toLocaleString()} edges` : ''}
                  />
                  <TelemetryTile
                    label="Levels"
                    value={currentJob.telemetry.coarsening_levels !== undefined ? `${currentJob.telemetry.coarsening_levels}` : '—'}
                  />
                  <TelemetryTile
                    label="Parts"
                    value={currentJob.telemetry.coarse_parts !== undefined ? `k = ${currentJob.telemetry.coarse_parts}` : '—'}
                  />
                </div>
              </div>

              {/* Log terminal */}
              <div className="flex-1 min-h-[320px] flex flex-col bg-slate-950 border border-slate-800 rounded-2xl overflow-hidden shadow-xl">
                <div className="shrink-0 px-4 py-3 bg-slate-900 border-b border-slate-800 flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-3 min-w-0">
                    <Terminal className="w-4 h-4 text-indigo-400 shrink-0" />
                    <span className="text-xs font-mono font-semibold text-slate-200">Log</span>
                    <div className="relative">
                      <Search className="w-3.5 h-3.5 text-slate-500 absolute left-2 top-1/2 -translate-y-1/2" />
                      <input
                        type="search"
                        value={logSearch}
                        onChange={(e) => setLogSearch(e.target.value)}
                        placeholder="Search log…"
                        aria-label="Search log"
                        className="w-44 bg-slate-950 border border-slate-700 rounded-lg pl-7 pr-2 py-1 text-xs font-mono text-slate-200 focus:border-indigo-500 focus:outline-none"
                      />
                    </div>
                  </div>

                  <div className="flex flex-wrap items-center gap-1.5">
                    {['ALL', 'INFO', 'VERBOSE', 'WARNING', 'ERROR'].map((lvl) => {
                      const count = lvl === 'ALL' ? logs.length : logs.filter((l) => l.level === lvl).length;
                      return (
                        <button
                          key={lvl}
                          type="button"
                          aria-pressed={levelFilter === lvl}
                          onClick={() => setLevelFilter(lvl)}
                          className={`px-2 py-0.5 rounded text-xs font-mono transition flex items-center gap-1 ${
                            levelFilter === lvl ? 'bg-indigo-600 text-white' : 'bg-slate-800 text-slate-400 hover:text-slate-200'
                          }`}
                        >
                          <span>{lvl}</span>
                          <span className={levelFilter === lvl ? 'text-indigo-200' : 'text-slate-500'}>({count})</span>
                        </button>
                      );
                    })}
                    <span className="w-px h-4 bg-slate-700 mx-1" />
                    <button
                      type="button"
                      onClick={copyLogs}
                      title="Copy the visible log lines"
                      aria-label="Copy visible log lines"
                      className="p-1.5 rounded text-slate-400 hover:text-white hover:bg-slate-800"
                    >
                      <Copy className="w-3.5 h-3.5" />
                    </button>
                    <button
                      type="button"
                      onClick={downloadLogs}
                      title="Download the full log as a .log file"
                      aria-label="Download full log"
                      className="p-1.5 rounded text-slate-400 hover:text-white hover:bg-slate-800"
                    >
                      <Download className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>

                <div className="relative flex-1 min-h-0">
                  <div
                    ref={logContainerRef}
                    onScroll={handleLogScroll}
                    className="absolute inset-0 p-4 overflow-y-auto font-mono text-xs space-y-1.5"
                  >
                    {filteredLogs.length === 0 ? (
                      <div className="text-slate-500 py-8 text-center">
                        {logs.length === 0
                          ? 'Waiting for log output...'
                          : logSearch
                          ? `No lines match "${logSearch}".`
                          : `No ${levelFilter} entries.`}
                      </div>
                    ) : (
                      filteredLogs.map((entry, idx) => (
                        <div key={idx} className="flex items-start gap-2.5 leading-relaxed">
                          <span className="text-slate-500 shrink-0">{entry.timestamp}</span>
                          <span
                            className={`px-1.5 rounded text-xs font-bold shrink-0 ${
                              entry.level === 'ERROR'
                                ? 'bg-rose-500/20 text-rose-400'
                                : entry.level === 'WARNING'
                                ? 'bg-amber-500/20 text-amber-300'
                                : entry.level === 'VERBOSE'
                                ? 'bg-slate-800 text-slate-400'
                                : 'bg-slate-700/60 text-slate-200'
                            }`}
                          >
                            {entry.level}
                          </span>
                          <span className="text-slate-200 break-all">{entry.message}</span>
                        </div>
                      ))
                    )}
                  </div>
                  {!followLog && filteredLogs.length > 0 && (
                    <button
                      type="button"
                      onClick={jumpToLatest}
                      className="absolute bottom-3 right-5 inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold bg-indigo-600 text-white shadow-lg hover:bg-indigo-500"
                    >
                      <ArrowDown className="w-3.5 h-3.5" />
                      Jump to latest
                    </button>
                  )}
                </div>
              </div>
            </>
          ) : activeJobId ? (
            <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-12 flex items-center justify-center gap-2 text-xs text-slate-400">
              <Loader2 className="w-4 h-4 animate-spin" />
              Loading run…
            </div>
          ) : (
            <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-8 space-y-6">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div className="flex items-start gap-3 min-w-0">
                  <Activity className="w-8 h-8 text-indigo-400 shrink-0" />
                  <div className="space-y-1.5">
                    <h2 className="text-base font-bold text-white">No run selected</h2>
                    <ul className="text-xs text-slate-400 space-y-1 list-disc list-inside">
                      <li>
                        Start a run from <span className="text-slate-200">Single Run</span> (or a batch from{' '}
                        <span className="text-slate-200">Batch Run</span>) — the log streams here live.
                      </li>
                      <li>Or open a past run from the history on the left (filter by simulation, method or status).</li>
                      <li>Finished runs link straight to the Results tab.</li>
                    </ul>
                  </div>
                </div>
                {newRunButton()}
              </div>

              {recentCompleted.length > 0 && (
                <div className="space-y-2">
                  <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                    Recent completed runs
                  </h3>
                  <ul className="divide-y divide-slate-800 border border-slate-800 rounded-xl overflow-hidden">
                    {recentCompleted.map((job) => {
                      const created = parseDate(job.created_at);
                      const k = jobK(job);
                      return (
                        <li key={job.job_id}>
                          <button
                            type="button"
                            onClick={() => onSelectJob(job.job_id)}
                            className="w-full flex items-center justify-between gap-3 px-4 py-2.5 text-left bg-slate-950/60 hover:bg-slate-800/60 transition focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-indigo-400"
                          >
                            <span className="flex items-center gap-2 min-w-0">
                              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                              {job.job_type === 'batch' ? (
                                <Layers className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                              ) : (
                                <MethodDot job={job} />
                              )}
                              <span className="text-xs font-semibold text-white truncate">{jobDisplayTitle(job)}</span>
                              {job.job_type !== 'batch' && k != null && (
                                <span className="text-xs font-mono text-slate-400 shrink-0">k={k}</span>
                              )}
                            </span>
                            <span className="text-xs font-mono text-slate-400 shrink-0">
                              {created ? `${dayLabel(created)} ${shortTime(created)}` : ''}
                            </span>
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

const TelemetryTile: React.FC<{ label: string; value: string; sub?: string }> = ({ label, value, sub }) => (
  <div className="p-3 rounded-xl bg-slate-950/80 border border-slate-800 min-w-0 overflow-hidden">
    <div className="text-xs text-slate-400">{label}</div>
    <div className="text-sm font-mono font-bold mt-0.5 truncate text-white">{value}</div>
    {sub !== undefined && <div className="text-xs font-mono text-slate-400 truncate">{sub}</div>}
  </div>
);
