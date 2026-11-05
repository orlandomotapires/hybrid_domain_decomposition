import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  ArrowDown,
  ArrowLeftRight,
  ArrowUp,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  ChevronsUpDown,
  Download,
  Image as ImageIcon,
  Loader2,
  Play,
  Plus,
  Sliders,
  X,
  ZoomIn,
} from 'lucide-react';
import { api } from '../api/client';
import { Demonstrator, SimulationParameters } from '../types/pipeline';
import { downloadCsv, downloadSvg, downloadSvgAsPng, safeFilename } from '../lib/download';
import { methodColor, methodLabel, SCALE_LABELS } from '../lib/labels';
import { InfoTooltip } from './InfoTooltip';
import { useToast } from './Toasts';

interface ResultsExplorerProps {
  demonstrators: Demonstrator[];
  selectedDemonstratorId: string;
  initialResultDir: string | null;
  initialBatchId: string | null;
  onSelectionChange: (sel: { resultDir: string | null; batchId: string | null }) => void;
  onLoadParameters: (demId: string, params: SimulationParameters) => void;
  onRerun: (demId: string, params: SimulationParameters) => Promise<void>;
  onOpenWiki: (topicId: string) => void;
}

/** Colors for compared runs B, C, D, … (Run A is indigo). */
const COMPARE_COLORS = ['#f59e0b', '#10b981', '#ec4899', '#06b6d4', '#a855f7'];
const MAX_COMPARE = COMPARE_COLORS.length;
const RUN_LETTERS = 'BCDEF';
const runShortName = (dir: string) => dir.split('/').pop() || dir;

/** Label for a batch method key, with "Original" for the unpermuted baseline series. */
const seriesLabel = (m: string, short = false) => (m === 'Original' ? 'Original' : methodLabel(m, undefined, short));
const scaleLabel = (s: string | null | undefined) => (s ? SCALE_LABELS[s] || s : '—');

/** Single-run selector text: "run_2026… — QA Emulated (k=4)". */
const runOptionLabel = (r: any) =>
  `${r.run_id} — ${methodLabel(r.partitioning_strategy, r.simulated, true)}${r.k_target != null ? ` (k=${r.k_target})` : ''}`;

/** Signed percentage change: negative = smaller = better. Uses a real minus sign. */
const fmtChange = (pct: number, digits = 1) => {
  if (!isFinite(pct)) return '—';
  const v = Math.abs(pct).toFixed(digits);
  if (Number(v) === 0) return `${(0).toFixed(digits)}%`;
  return pct < 0 ? `\u2212${v}%` : `+${v}%`;
};
const changeClass = (pct: number) => (pct < 0 ? 'text-emerald-400' : pct > 0 ? 'text-amber-400' : 'text-slate-400');

/** Short, human reason for a failed batch case; the full message stays available in "details". */
function shortFailureReason(message: string | null | undefined, errorType?: string | null): string {
  const msg = (message || '').trim();
  if (!msg) return errorType || 'unknown error';
  const unreachable =
    /could not connect|connection refused|connection reset|connectionerror|ttransportexception|unreachable|timed out|timeout|max retries|name or service not known|failed to establish/i.test(
      msg
    );
  if (unreachable) {
    if (/qlm|qat\.qpus|myqlm/i.test(msg)) return 'QLM backend unreachable';
    if (/d-?wave|leap|advantage/i.test(msg)) return 'D-Wave backend unreachable';
    return 'remote backend unreachable';
  }
  const firstLine = msg.split('\n')[0];
  // "SomeError: detail" → keep the detail; long messages are clipped.
  const stripped = firstLine.replace(/^[A-Za-z_.]+(Error|Exception):\s*/, '');
  const text = stripped || firstLine;
  return text.length > 90 ? `${text.slice(0, 87)}…` : text;
}

export const ResultsExplorer: React.FC<ResultsExplorerProps> = ({
  demonstrators,
  selectedDemonstratorId,
  initialResultDir,
  initialBatchId,
  onSelectionChange,
  onLoadParameters,
  onRerun,
  onOpenWiki,
}) => {
  const toast = useToast();
  const [mode, setMode] = useState<'batch' | 'single'>(
    initialResultDir ? 'single' : 'batch'
  );

  // Single Run State
  const [demId, setDemId] = useState<string>(selectedDemonstratorId);
  const [singleRuns, setSingleRuns] = useState<any[]>([]);
  const [activeResultDir, setActiveResultDir] = useState<string | null>(initialResultDir);
  const [runDetail, setRunDetail] = useState<any | null>(null);
  const [compareResultDirs, setCompareResultDirs] = useState<string[]>([]);
  const [compareRunDetails, setCompareRunDetails] = useState<Record<string, any>>({});
  const [rerunning, setRerunning] = useState(false);
  const [loadingSingle, setLoadingSingle] = useState(false);
  const [activePlots, setActivePlots] = useState<Record<string, boolean>>({});
  const [zoomImageUrl, setZoomImageUrl] = useState<{ url: string; title: string } | null>(null);

  // Batch Analysis State
  const [batchRuns, setBatchRuns] = useState<any[]>([]);
  const [batchRunsLoaded, setBatchRunsLoaded] = useState(false);
  const [activeBatchId, setActiveBatchId] = useState<string>(initialBatchId || '');
  const [batchDem, setBatchDem] = useState<string>(selectedDemonstratorId || '');
  const [batchAnalysis, setBatchAnalysis] = useState<any | null>(null);
  const [batchError, setBatchError] = useState<string | null>(null);
  const [singleRunsLoaded, setSingleRunsLoaded] = useState(false);

  useEffect(() => {
    if (initialResultDir) {
      setMode('single');
      setActiveResultDir(initialResultDir);
    }
  }, [initialResultDir]);

  useEffect(() => {
    if (initialBatchId) {
      setMode('batch');
      setActiveBatchId(initialBatchId);
    }
  }, [initialBatchId]);

  useEffect(() => {
    api
      .listBatchRuns()
      .then((res) => {
        setBatchRuns(res.batch_runs);
        setActiveBatchId((cur) => cur || res.batch_runs[0]?.id || '');
      })
      .catch(() => setBatchRuns([]))
      .finally(() => setBatchRunsLoaded(true));
  }, []);

  useEffect(() => {
    if (!activeBatchId) return;
    let cancelled = false;
    setBatchError(null);
    api
      .getBatchAnalysis(activeBatchId, batchDem)
      .then((res) => {
        if (cancelled) return;
        // Only offer matrices that are actually in this batch; jump to the first one if needed.
        const available: string[] = res.available_demonstrators || [];
        if (available.length > 0 && !available.includes(batchDem)) {
          setBatchDem(available[0]);
          return;
        }
        setBatchAnalysis(res);
      })
      .catch((err) => {
        if (cancelled) return;
        setBatchAnalysis(null);
        setBatchError(err.message || 'Could not load the batch analysis');
      });
    return () => {
      cancelled = true;
    };
  }, [activeBatchId, batchDem]);

  useEffect(() => {
    setSingleRunsLoaded(false);
    api
      .listDemonstratorRuns(demId)
      .then((res) => {
        setSingleRuns(res.runs);
        if (!activeResultDir && res.runs.length > 0) {
          setActiveResultDir(res.runs[0].result_dir);
        }
      })
      .catch(() => setSingleRuns([]))
      .finally(() => setSingleRunsLoaded(true));
  }, [demId]);

  useEffect(() => {
    if (!activeResultDir) {
      setRunDetail(null);
      return;
    }
    setLoadingSingle(true);
    api
      .getSingleRunDetail(activeResultDir)
      .then((res) => {
        setRunDetail(res);
        setActivePlots({
          original_matrix_partitioned: true,
          permuted_matrix_partitioned: true,
          coarsened_graph_partitioned: true,
          uncoarsened_graph_partitioned: true,
        });
      })
      .catch(() => setRunDetail(null))
      .finally(() => setLoadingSingle(false));
  }, [activeResultDir]);

  // Load details for every compared run we don't have yet
  useEffect(() => {
    compareResultDirs.forEach((dir) => {
      if (compareRunDetails[dir]) return;
      api
        .getSingleRunDetail(dir)
        .then((res) => setCompareRunDetails((prev) => ({ ...prev, [dir]: res })))
        .catch((err) => toast.error(`Could not load ${runShortName(dir)}: ${err.message}`));
    });
  }, [compareResultDirs]);

  // Keep the URL in sync with what is being inspected
  useEffect(() => {
    onSelectionChange(
      mode === 'single'
        ? { resultDir: activeResultDir, batchId: null }
        : { resultDir: null, batchId: activeBatchId || null }
    );
  }, [mode, activeResultDir, activeBatchId]);

  const compared = compareResultDirs
    .map((dir, i) => ({
      dir,
      label: `Run ${RUN_LETTERS[i]}`,
      color: COMPARE_COLORS[i],
      detail: compareRunDetails[dir],
    }))
    .filter((c) => c.detail);

  const addCompare = (dir: string) => {
    if (!dir || compareResultDirs.includes(dir) || compareResultDirs.length >= MAX_COMPARE) return;
    setCompareResultDirs((prev) => [...prev, dir]);
  };
  const removeCompare = (dir: string) =>
    setCompareResultDirs((prev) => prev.filter((d) => d !== dir));

  const runParams: SimulationParameters | null = runDetail?.run_parameters || null;

  // Matrices present in the selected batch (from the analysis, else from the runs listing).
  const batchMatrices: string[] =
    batchAnalysis?.batch_id === activeBatchId && batchAnalysis?.available_demonstrators
      ? batchAnalysis.available_demonstrators
      : batchRuns.find((b) => b.id === activeBatchId)?.geometries || [];
  const matricesWithRuns = demonstrators.filter((d) => d.id !== demId && (d.runs_count ?? 0) > 0);

  const handleRerun = async () => {
    if (!runParams) return;
    setRerunning(true);
    try {
      await onRerun(demId, runParams);
    } finally {
      setRerunning(false);
    }
  };

  const exportBatchCsv = () => {
    if (!batchAnalysis) return;
    const headers = [
      'case_key', 'algorithm', 'coarsening_size', 'status',
      'bandwidth_original', 'bandwidth_permuted',
      'avg_bandwidth_original', 'avg_bandwidth_permuted',
      'frac_0_1pct_original', 'frac_0_1pct_permuted',
      'frac_0_4pct_original', 'frac_0_4pct_permuted',
      'frac_0_7pct_original', 'frac_0_7pct_permuted',
      'frac_1_0pct_original', 'frac_1_0pct_permuted',
      'permutation_mismatches', 'error_message',
    ];
    const rows = batchAnalysis.rows.map((r: any) => headers.map((h) => r[h]));
    downloadCsv(headers, rows, safeFilename(`${activeBatchId}_${batchDem}.csv`));
  };

  return (
    <div className="space-y-6">
      {/* Top Mode Switcher */}
      <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-4 flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-2.5">
          <span className="px-2.5 py-0.5 text-xs font-semibold rounded-full bg-indigo-500/15 text-indigo-300 border border-indigo-500/30">
            Results & Plots
          </span>
          <span className="text-xs text-slate-400">
            {mode === 'batch' ? 'Compare methods across a study' : 'Inspect one run in detail'}
          </span>
          <InfoTooltip topicId="results-analytics" onOpenWiki={onOpenWiki} />
        </div>

        <div className="flex items-center gap-2 bg-slate-950 p-1.5 rounded-xl border border-slate-800">
          <button
            onClick={() => setMode('batch')}
            aria-pressed={mode === 'batch'}
            className={`px-3.5 py-1.5 rounded-lg text-xs font-bold transition ${
              mode === 'batch'
                ? 'bg-indigo-600 text-white shadow'
                : 'text-slate-400 hover:text-white'
            }`}
          >
            Batch
          </button>
          <button
            onClick={() => setMode('single')}
            aria-pressed={mode === 'single'}
            className={`px-3.5 py-1.5 rounded-lg text-xs font-bold transition ${
              mode === 'single'
                ? 'bg-indigo-600 text-white shadow'
                : 'text-slate-400 hover:text-white'
            }`}
          >
            Single Run
          </button>
        </div>
      </div>

      {/* MODE 1: BATCH & THESIS STUDY COMPARISON */}
      {mode === 'batch' && (
        <div className="space-y-6">
          {/* Batch & Demonstrator Selector Bar */}
          <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-4 flex flex-wrap items-center justify-between gap-4">
            <div className="flex flex-wrap items-center gap-4">
              <div className="flex items-center gap-2">
                <span className="text-xs text-slate-400 font-medium">Batch Study:</span>
                <select
                  value={activeBatchId}
                  onChange={(e) => setActiveBatchId(e.target.value)}
                  disabled={batchRuns.length === 0}
                  className="bg-slate-950 border border-slate-700 rounded-lg px-3 py-1.5 text-xs font-mono text-white"
                >
                  {batchRuns.length === 0 && <option value="">No batch studies</option>}
                  {batchRuns.map((br) => (
                    <option key={br.id} value={br.id}>
                      {br.id} ({br.completed_cases}/{br.total_cases} completed{br.failed_cases ? `, ${br.failed_cases} failed` : ''})
                    </option>
                  ))}
                </select>
              </div>

              <div className="flex items-center gap-2">
                <span className="text-xs text-slate-400 font-medium">Matrix:</span>
                <div className="flex items-center gap-1">
                  {batchMatrices.length === 0 && <span className="text-xs text-slate-500">—</span>}
                  {batchMatrices.map(
                    (d: string) => (
                      <button
                        key={d}
                        onClick={() => setBatchDem(d)}
                        aria-pressed={batchDem === d}
                        className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition ${
                          batchDem === d
                            ? 'bg-indigo-600 text-white'
                            : 'bg-slate-950 text-slate-400 hover:text-white border border-slate-800'
                        }`}
                      >
                        {d}
                      </button>
                    )
                  )}
                </div>
              </div>
            </div>
          </div>

          {batchRuns.length === 0 && batchRunsLoaded ? (
            <EmptyState
              title="No batch studies yet"
              body="A batch study runs several methods and coarsening scales over your matrices and compares them here. Configure and start one from Batch Run; results appear in this view as soon as its summary is written."
              actions={
                <button onClick={() => setMode('single')} className={EMPTY_BTN}>
                  View single runs instead
                </button>
              }
            />
          ) : batchError ? (
            <EmptyState
              title={`No summary for ${activeBatchId} yet`}
              body={`${batchError}. If the batch is still running, its summary is written when it finishes. Pick another batch above, or inspect individual runs.`}
              actions={
                <button onClick={() => setMode('single')} className={EMPTY_BTN}>
                  View single runs instead
                </button>
              }
            />
          ) : batchAnalysis && batchAnalysis.rows?.length > 0 ? (
            <>
              <BatchSummaryTable
                rows={batchAnalysis.rows}
                title={`Matrix Summary (${batchDem})`}
                onExportCsv={exportBatchCsv}
                onOpenWiki={onOpenWiki}
              />

              {batchAnalysis.completed_rows?.length > 0 ? (
                <>
                  {/* Multi-Method Locality Curves by Scale */}
                  <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
                    {(batchAnalysis.comparison_curves || []).map((scaleBlock: any) => (
                      <div
                        key={scaleBlock.coarsening_size}
                        className="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 space-y-3"
                      >
                        <div className="flex items-center justify-between">
                          <div>
                            <span className="text-xs font-semibold uppercase tracking-wide text-slate-400">
                              Coarsening scale: {scaleLabel(scaleBlock.coarsening_size)}
                            </span>
                            <h4 className="text-sm font-bold text-white">
                              Diagonal Band Concentration
                            </h4>
                          </div>
                        </div>

                        <ChartExport
                          filename={`${activeBatchId}_${batchDem}_${scaleBlock.coarsening_size}_locality`}
                        >
                          <MultiMethodSvgChart
                            points={scaleBlock.points}
                            methods={['Original', ...scaleBlock.methods]}
                          />
                        </ChartExport>
                      </div>
                    ))}
                  </div>

                </>
              ) : (
                <EmptyState
                  title={`Every case for ${batchDem} failed`}
                  body="There are no completed cases to plot or tabulate. Expand a failed row above to see the full error, fix the cause (e.g. start the remote backend or check credentials) and re-run the batch."
                />
              )}
            </>
          ) : batchAnalysis ? (
            <EmptyState
              title={batchMatrices.length > 0 ? `${batchDem} is not part of ${activeBatchId}` : `${activeBatchId} has no results yet`}
              body={
                batchMatrices.length > 0
                  ? 'This batch has no cases for the selected matrix. Pick one of the matrices it did run:'
                  : 'This batch has no result rows yet.'
              }
              actions={
                <>
                  {batchMatrices.map((d: string) => (
                    <button key={d} onClick={() => setBatchDem(d)} className={EMPTY_BTN}>
                      {d}
                    </button>
                  ))}
                  <button onClick={() => setMode('single')} className={EMPTY_BTN}>
                    View single runs instead
                  </button>
                </>
              }
            />
          ) : (
            <div className="p-12 text-center text-sm text-slate-400 flex items-center justify-center gap-2">
              <Loader2 className="w-5 h-5 animate-spin text-indigo-400" />
              Loading batch analysis...
            </div>
          )}
        </div>
      )}

      {/* MODE 2: SINGLE RUN DEEP-DIVE & PLOT GALLERY */}
      {mode === 'single' && (
        <div className="space-y-6">
          {/* Demonstrator & Run Folder Selector */}
          <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-4 flex flex-wrap items-center justify-between gap-4">
            <div className="flex flex-wrap items-center gap-4 min-w-0">
              <div className="flex items-center gap-2">
                <span className="text-xs text-slate-400 font-medium">Simulation:</span>
                <select
                  value={demId}
                  onChange={(e) => {
                    setDemId(e.target.value);
                    setActiveResultDir(null);
                    setCompareResultDirs([]);
                  }}
                  className="bg-slate-950 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-white"
                >
                  {demonstrators.map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.id} ({d.runs_count} runs)
                    </option>
                  ))}
                </select>
              </div>

              <div className="flex items-center gap-2 min-w-0">
                <span className="text-xs text-slate-400 font-medium shrink-0">Run A:</span>
                <select
                  value={activeResultDir || ''}
                  onChange={(e) => {
                    setActiveResultDir(e.target.value);
                    setCompareResultDirs((prev) => prev.filter((d) => d !== e.target.value));
                  }}
                  className="bg-slate-950 border border-slate-700 rounded-lg px-3 py-1.5 text-xs font-mono text-white max-w-[260px] truncate"
                >
                  {singleRuns.length === 0 && (
                    <option value="">No local runs in simulations/{demId}/results/</option>
                  )}
                  {singleRuns.map((r) => (
                    <option key={r.result_dir} value={r.result_dir}>
                      {runOptionLabel(r)}
                    </option>
                  ))}
                </select>
              </div>

              {singleRuns.length > 1 && (
                <div className="flex flex-wrap items-center gap-2 min-w-0">
                  <ArrowLeftRight className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                  <span className="text-xs text-slate-400 font-medium shrink-0">Compare with:</span>
                  {compareResultDirs.map((dir, i) => (
                    <span
                      key={dir}
                      className="inline-flex items-center gap-1.5 pl-2 pr-1 py-0.5 rounded-lg text-xs font-mono border"
                      style={{ borderColor: COMPARE_COLORS[i], color: COMPARE_COLORS[i] }}
                      title={dir}
                    >
                      {RUN_LETTERS[i]}: {runShortName(dir)}
                      <button
                        onClick={() => removeCompare(dir)}
                        className="p-0.5 rounded hover:bg-slate-800"
                        aria-label={`Stop comparing ${runShortName(dir)}`}
                      >
                        <X className="w-3 h-3" />
                      </button>
                    </span>
                  ))}
                  {compareResultDirs.length < MAX_COMPARE && (
                    <div className="relative inline-flex items-center">
                      <Plus className="w-3.5 h-3.5 text-slate-400 absolute left-2 pointer-events-none" />
                      <select
                        value=""
                        onChange={(e) => addCompare(e.target.value)}
                        aria-label="Add a run to compare"
                        className="bg-slate-950 border border-slate-700 rounded-lg pl-7 pr-3 py-1.5 text-xs font-mono text-slate-200 max-w-[230px] truncate"
                      >
                        <option value="">Add run…</option>
                        {singleRuns
                          .filter(
                            (r) =>
                              r.result_dir !== activeResultDir &&
                              !compareResultDirs.includes(r.result_dir)
                          )
                          .map((r) => (
                            <option key={r.result_dir} value={r.result_dir}>
                              {runOptionLabel(r)}
                            </option>
                          ))}
                      </select>
                    </div>
                  )}
                </div>
              )}
            </div>

            {activeResultDir && (
              <div className="flex flex-wrap items-center gap-2 shrink-0">
              {runParams && (
                <>
                  <button
                    onClick={() => onLoadParameters(demId, runParams)}
                    title="Open this run's exact parameters in Single Run"
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700"
                  >
                    <Sliders className="w-3.5 h-3.5 text-indigo-400" /> Load into Single Run
                  </button>
                  <button
                    onClick={handleRerun}
                    disabled={rerunning}
                    title="Start a new run on this matrix with this run's exact parameters"
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold bg-indigo-600 hover:bg-indigo-500 text-white disabled:opacity-50"
                  >
                    {rerunning ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5 fill-current" />}
                    Re-run
                  </button>
                </>
              )}
              <a
                href={`/api/results/download-bundle?result_dir=${encodeURIComponent(
                  activeResultDir
                )}`}
                download
                className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-xl text-xs font-semibold bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 transition shrink-0"
              >
                <Download className="w-3.5 h-3.5" />
                Download Run Bundle (.zip)
              </a>
              </div>
            )}
          </div>

          {loadingSingle ? (
            <div className="p-12 text-center text-sm text-slate-400 flex items-center justify-center gap-2">
              <Loader2 className="w-5 h-5 animate-spin text-indigo-400" />
              Loading run metrics and artifacts...
            </div>
          ) : runDetail ? (
            <>
              {/* KPI Summary for the permuted matrix */}
              {runDetail.kpi_summary && (
                <div className="grid grid-cols-1 gap-5">
                  {[runDetail.kpi_summary].map((kpi: any) => {
                    if (!kpi) return null;
                    // Backend reports reductions (positive = smaller); show signed change (negative = better).
                    const bwChange = -(kpi.bandwidth_reduction_pct ?? 0);
                    const nb2Change = -(kpi.nb2_reduction_pct ?? 0);
                    return (
                      <div
                        key="matrix"
                        className="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 space-y-4"
                      >
                        <div className="flex items-center justify-between">
                          <h3 className="text-sm font-bold text-white">
                            Matrix Structural Performance
                          </h3>
                          {kpi.permutation_check?.mismatches === 0 && (
                            <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
                              <CheckCircle2 className="w-3.5 h-3.5" /> Valid Permutation (0 mismatches)
                            </span>
                          )}
                        </div>

                        <div className="grid grid-cols-3 gap-3">
                          <div className="p-3 rounded-xl bg-slate-950 border border-slate-800">
                            <div className="text-xs text-slate-400">Max Bandwidth B</div>
                            <div className="text-sm font-mono font-bold text-white mt-0.5">
                              {kpi.bandwidth_original?.toLocaleString()} →{' '}
                              {kpi.bandwidth_permuted?.toLocaleString()}
                            </div>
                            <div className={`text-xs font-mono font-semibold mt-0.5 ${changeClass(bwChange)}`}>
                              {fmtChange(bwChange, 2)} change
                            </div>
                          </div>

                          <div className="p-3 rounded-xl bg-slate-950 border border-slate-800">
                            <div className="text-xs text-slate-400">Avg. Bandwidth</div>
                            <div className="text-sm font-mono font-bold text-white mt-0.5">
                              {kpi.avg_bandwidth_original?.toFixed(1)} →{' '}
                              {kpi.avg_bandwidth_permuted?.toFixed(1)}
                            </div>
                            <div className="text-xs font-mono text-slate-400 mt-0.5">
                              NNZ: {kpi.nnz_permuted?.toLocaleString()}
                            </div>
                          </div>

                          <div className="p-3 rounded-xl bg-slate-950 border border-slate-800">
                            <div className="text-xs text-slate-400">nB² change</div>
                            <div className={`text-sm font-mono font-bold mt-0.5 ${changeClass(nb2Change)}`}>
                              {fmtChange(nb2Change)}
                            </div>
                            <div className="text-xs font-mono text-slate-400 mt-0.5">
                              frac 0.4%: {((kpi.frac_0_4pct_permuted || 0) * 100).toFixed(1)}%
                            </div>
                          </div>
                        </div>

                        {/* Interactive 100-Point Locality Curve */}
                        {runDetail.curves?.length > 0 && (
                          <SingleRunCurveSvg
                            points={runDetail.curves}
                            compareSeries={compared
                              .filter((c) => c.detail.curves?.length)
                              .map((c) => ({ label: c.label, color: c.color, points: c.detail.curves }))}
                            exportName={`${runShortName(runDetail.result_dir)}_locality`}
                          />
                        )}
                      </div>
                    );
                  })}
                </div>
              )}

              {/* Multi-run comparison (Run A vs. B, C, …) */}
              {compared.length > 0 && runDetail?.kpi_summary && (
                <RunComparisonTable
                  runA={{ label: 'Run A', dir: activeResultDir || '', detail: runDetail }}
                  others={compared}
                />
              )}

              {/* 10-Plot Matrix & Graph Partitioning Visual Gallery */}
              {runDetail.can_render_plots && (
                <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-6 space-y-5">
                  <div className="flex flex-wrap items-center justify-between gap-4">
                    <h3 className="text-base font-bold text-white flex items-center gap-2">
                      <ImageIcon className="w-4 h-4 text-indigo-400" />
                      Visual Gallery
                    </h3>

                    <button
                      onClick={() => {
                        const all: Record<string, boolean> = {};
                        runDetail.available_plots.forEach((p: any) => {
                          all[p.id] = true;
                        });
                        setActivePlots(all);
                      }}
                      className="px-3.5 py-1.5 rounded-xl text-xs font-semibold bg-indigo-600 text-white hover:bg-indigo-500 transition"
                    >
                      Show All
                    </button>
                  </div>

                  {/* Plot Toggle Pills */}
                  <div className="flex flex-wrap gap-2">
                    {runDetail.available_plots.map((p: any) => {
                      const enabled = !!activePlots[p.id];
                      return (
                        <button
                          key={p.id}
                          onClick={() =>
                            setActivePlots((prev) => ({ ...prev, [p.id]: !prev[p.id] }))
                          }
                          className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition ${
                            enabled
                              ? 'bg-indigo-950/60 border-indigo-500 text-indigo-200'
                              : 'bg-slate-950 border-slate-800 text-slate-400 hover:text-slate-200'
                          }`}
                        >
                          {p.label}
                        </button>
                      );
                    })}
                  </div>

                  {/* Rendered Plot Grid */}
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                    {runDetail.available_plots
                      .filter((p: any) => activePlots[p.id])
                      .map((p: any) => {
                        const imgUrl = `/api/results/plot-image?result_dir=${encodeURIComponent(
                          runDetail.result_dir
                        )}&plot_name=${encodeURIComponent(p.id)}`;
                        return (
                          <div
                            key={p.id}
                            className="bg-slate-950 border border-slate-800 rounded-xl overflow-hidden flex flex-col justify-between group"
                          >
                            <div className="p-3 border-b border-slate-800 flex items-center justify-between">
                              <span className="text-xs font-semibold text-white truncate">
                                {p.label}
                              </span>
                              <button
                                onClick={() => setZoomImageUrl({ url: imgUrl, title: p.label })}
                                className="p-1 rounded hover:bg-slate-800 text-slate-400 hover:text-white"
                                title="Zoom plot"
                              >
                                <ZoomIn className="w-3.5 h-3.5" />
                              </button>
                            </div>
                            <div
                              onClick={() => setZoomImageUrl({ url: imgUrl, title: p.label })}
                              className="p-2 bg-white flex items-center justify-center cursor-pointer min-h-[220px]"
                            >
                              <img
                                src={imgUrl}
                                alt={p.label}
                                className="max-h-[240px] w-auto object-contain"
                                loading="lazy"
                              />
                            </div>
                          </div>
                        );
                      })}
                  </div>
                </div>
              )}
            </>
          ) : (
            <EmptyState
              title={
                !singleRunsLoaded
                  ? `Loading runs for ${demId}…`
                  : singleRuns.length === 0
                  ? `No runs yet for ${demId}`
                  : 'Could not load this run'
              }
              body={
                !singleRunsLoaded
                  ? ''
                  : singleRuns.length === 0
                  ? `Run the pipeline on ${demId} from Single Run — each run writes its metrics and plots to simulations/${demId}/results/ and shows up here.` +
                    (matricesWithRuns.length > 0 ? ' Or open a matrix that already has runs:' : '')
                  : 'The selected run folder has no readable metrics (it may still be running or was interrupted). Pick another run above.'
              }
              actions={
                singleRunsLoaded ? (
                  <>
                    {singleRuns.length === 0 &&
                      matricesWithRuns.map((d) => (
                        <button
                          key={d.id}
                          onClick={() => {
                            setDemId(d.id);
                            setActiveResultDir(null);
                            setCompareResultDirs([]);
                          }}
                          className={EMPTY_BTN}
                        >
                          {d.id} ({d.runs_count} runs)
                        </button>
                      ))}
                    {batchRuns.length > 0 && (
                      <button onClick={() => setMode('batch')} className={EMPTY_BTN}>
                        Compare methods in a batch study instead
                      </button>
                    )}
                  </>
                ) : undefined
              }
            />
          )}
        </div>
      )}

      {/* Lightbox Modal for Plot Zoom */}
      {zoomImageUrl && (
        <div
          onClick={() => setZoomImageUrl(null)}
          className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-6"
        >
          <div
            onClick={(e) => e.stopPropagation()}
            className="bg-slate-900 border border-slate-700 rounded-2xl max-w-3xl w-full overflow-hidden shadow-2xl"
          >
            <div className="p-4 border-b border-slate-800 flex items-center justify-between">
              <span className="font-bold text-sm text-white">{zoomImageUrl.title}</span>
              <button
                onClick={() => setZoomImageUrl(null)}
                className="px-3 py-1 rounded-lg text-xs bg-slate-800 text-slate-300 hover:bg-slate-700"
              >
                Close
              </button>
            </div>
            <div className="p-6 bg-white flex items-center justify-center">
              <img
                src={zoomImageUrl.url}
                alt={zoomImageUrl.title}
                className="max-h-[75vh] w-auto object-contain"
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

/* Interactive SVG Curve Component for Single Run (0% to 5%) */
type CurvePoint = { percent: number; original: number; permuted: number };

const SingleRunCurveSvg: React.FC<{
  points: CurvePoint[];
  compareSeries: Array<{ label: string; color: string; points: CurvePoint[] }>;
  exportName: string;
}> = ({ points, compareSeries, exportName }) => {
  const width = 520;
  const height = 210;
  const padL = 42;
  const padR = 16;
  const padT = 16;
  const padB = 30;
  const plotW = width - padL - padR;
  const plotH = height - padT - padB;

  const maxPct = 2.0; // Thesis plots focus on 0% to 2.0% band range
  const filtered = points.filter((p) => p.percent <= maxPct);

  const toX = (pct: number) => padL + (pct / maxPct) * plotW;
  const toY = (val: number) => padT + plotH - Math.min(1, Math.max(0, val)) * plotH;

  const origPath = filtered
    .map((p, i) => `${i === 0 ? 'M' : 'L'}${toX(p.percent).toFixed(1)},${toY(p.original).toFixed(1)}`)
    .join(' ');
  const permPath = filtered
    .map((p, i) => `${i === 0 ? 'M' : 'L'}${toX(p.percent).toFixed(1)},${toY(p.permuted).toFixed(1)}`)
    .join(' ');
  const comparePaths = compareSeries.map((c) => ({
    ...c,
    d: c.points
      .filter((p) => p.percent <= maxPct)
      .map((p, i) => `${i === 0 ? 'M' : 'L'}${toX(p.percent).toFixed(1)},${toY(p.permuted).toFixed(1)}`)
      .join(' '),
  }));

  return (
    <div className="p-3 rounded-xl bg-slate-950 border border-slate-800">
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs mb-2">
        <span className="font-semibold text-slate-300">
          Fraction of Nonzeros within Diagonal Band (0% – 2% of n)
        </span>
        <div className="flex items-center gap-3 text-xs">
          <span className="flex items-center gap-1 text-slate-400">
            <span className="w-2.5 h-0.5 bg-slate-400 inline-block" /> Original
          </span>
          <span className="flex items-center gap-1 text-indigo-400 font-semibold">
            <span className="w-2.5 h-0.5 bg-indigo-400 inline-block" /> Run A Permuted
          </span>
          {comparePaths.map((c) => (
            <span key={c.label} className="flex items-center gap-1 font-semibold" style={{ color: c.color }}>
              <span className="w-2.5 h-0.5 inline-block" style={{ backgroundColor: c.color }} /> {c.label}
            </span>
          ))}
        </div>
      </div>
      <ChartExport filename={exportName}>
      <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-auto">
        {[0, 0.25, 0.5, 0.75, 1.0].map((yVal) => (
          <g key={yVal}>
            <line
              x1={padL}
              y1={toY(yVal)}
              x2={width - padR}
              y2={toY(yVal)}
              stroke="rgb(var(--c-slate-800))"
              strokeDasharray="3 3"
            />
            <text x={padL - 6} y={toY(yVal) + 3} textAnchor="end" fontSize="10.5" fill="rgb(var(--c-slate-400))">
              {yVal.toFixed(2)}
            </text>
          </g>
        ))}
        {[0, 0.5, 1.0, 1.5, 2.0].map((xVal) => (
          <text
            key={xVal}
            x={toX(xVal)}
            y={height - 8}
            textAnchor="middle"
            fontSize="10.5"
            fill="rgb(var(--c-slate-400))"
          >
            {xVal.toFixed(1)}%
          </text>
        ))}
        <path d={origPath} fill="none" stroke="#94a3b8" strokeWidth="2" />
        <path d={permPath} fill="none" stroke="#6366f1" strokeWidth="2.5" />
        {comparePaths.map((c) => (
          <path key={c.label} d={c.d} fill="none" stroke={c.color} strokeWidth="2.2" strokeDasharray="5 3" />
        ))}
      </svg>
      </ChartExport>
    </div>
  );
};

/* Multi-Method SVG Chart for Batch Comparison */
const MultiMethodSvgChart: React.FC<{
  points: Array<Record<string, number>>;
  methods: string[];
}> = ({ points, methods }) => {
  const width = 380;
  const height = 200;
  const padL = 36;
  const padR = 14;
  const padT = 12;
  const padB = 26;
  const plotW = width - padL - padR;
  const plotH = height - padT - padB;

  const toX = (pct: number) => padL + (pct / 1.0) * plotW;
  const toY = (val: number) => padT + plotH - Math.min(1, Math.max(0, val)) * plotH;

  return (
    <div className="space-y-2">
      <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-auto bg-slate-950 rounded-xl p-2 border border-slate-800">
        {[0, 0.25, 0.5, 0.75, 1.0].map((yVal) => (
          <g key={yVal}>
            <line
              x1={padL}
              y1={toY(yVal)}
              x2={width - padR}
              y2={toY(yVal)}
              stroke="rgb(var(--c-slate-800))"
              strokeDasharray="3 3"
            />
            <text x={padL - 5} y={toY(yVal) + 3} textAnchor="end" fontSize="10.5" fill="rgb(var(--c-slate-400))">
              {yVal.toFixed(2)}
            </text>
          </g>
        ))}
        {[0, 0.1, 0.4, 0.7, 1.0].map((xVal) => (
          <text
            key={xVal}
            x={toX(xVal)}
            y={height - 6}
            textAnchor="middle"
            fontSize="10.5"
            fill="rgb(var(--c-slate-400))"
          >
            {xVal}%
          </text>
        ))}
        {methods.map((m) => {
          const validPts = points.filter((pt) => pt[m] !== undefined);
          if (validPts.length === 0) return null;
          const d = validPts
            .map((pt, i) => `${i === 0 ? 'M' : 'L'}${toX(pt.percent).toFixed(1)},${toY(pt[m]).toFixed(1)}`)
            .join(' ');
          const color = methodColor(m);
          return (
            <g key={m}>
              <path
                d={d}
                fill="none"
                stroke={color}
                strokeWidth={m === 'Original' ? '1.8' : '2.2'}
                strokeDasharray={m === 'Original' ? '4 3' : undefined}
              />
              {validPts.map((pt, idx) => (
                <circle
                  key={idx}
                  cx={toX(pt.percent)}
                  cy={toY(pt[m])}
                  r="2.8"
                  fill={color}
                />
              ))}
            </g>
          );
        })}
      </svg>

      <div className="flex flex-wrap gap-2 pt-1">
        {methods.map((m) => (
          <span key={m} className="inline-flex items-center gap-1.5 text-xs text-slate-300">
            <span
              className="w-2.5 h-2.5 rounded-full"
              style={{ backgroundColor: methodColor(m) }}
            />
            {seriesLabel(m, true)}
          </span>
        ))}
      </div>
    </div>
  );
};


/* Wraps a chart and adds PNG / SVG download buttons for its <svg>. */
const ChartExport: React.FC<{ filename: string; children: React.ReactNode }> = ({ filename, children }) => {
  const ref = useRef<HTMLDivElement | null>(null);
  const toast = useToast();
  const getSvg = () => ref.current?.querySelector('svg') as SVGSVGElement | null;
  const name = safeFilename(filename);
  return (
    <div className="relative group">
      <div ref={ref}>{children}</div>
      <div className="absolute top-1.5 right-1.5 flex gap-1 opacity-0 group-hover:opacity-100 focus-within:opacity-100 transition">
        <button
          onClick={async () => {
            const svg = getSvg();
            if (!svg) return;
            try {
              await downloadSvgAsPng(svg, `${name}.png`);
            } catch (err: any) {
              toast.error(`PNG export failed: ${err.message}`);
            }
          }}
          className="px-1.5 py-0.5 rounded text-xs font-semibold bg-slate-800/90 text-slate-200 border border-slate-700 hover:bg-slate-700"
          title="Download chart as PNG"
        >
          PNG
        </button>
        <button
          onClick={() => {
            const svg = getSvg();
            if (svg) downloadSvg(svg, `${name}.svg`);
          }}
          className="px-1.5 py-0.5 rounded text-xs font-semibold bg-slate-800/90 text-slate-200 border border-slate-700 hover:bg-slate-700"
          title="Download chart as SVG (vector, for papers)"
        >
          SVG
        </button>
      </div>
    </div>
  );
};

/* KPI table comparing Run A with up to five other runs; best value per row is highlighted. */
const RunComparisonTable: React.FC<{
  runA: { label: string; dir: string; detail: any };
  others: Array<{ label: string; dir: string; color: string; detail: any }>;
}> = ({ runA, others }) => {
  const runs = [{ ...runA, color: '#818cf8' }, ...others];
  const metrics: Array<{
    label: string;
    get: (k: any) => number | null | undefined;
    fmt: (v: number) => string;
    lowerIsBetter: boolean;
  }> = [
    { label: 'Max Bandwidth', get: (k) => k?.bandwidth_permuted, fmt: (v) => v.toLocaleString(), lowerIsBetter: true },
    {
      label: 'BW change (%)',
      get: (k) => (k?.bandwidth_reduction_pct == null ? null : -k.bandwidth_reduction_pct),
      fmt: (v) => fmtChange(v, 2),
      lowerIsBetter: true,
    },
    {
      label: 'nB² change (%)',
      get: (k) => (k?.nb2_reduction_pct == null ? null : -k.nb2_reduction_pct),
      fmt: (v) => fmtChange(v, 2),
      lowerIsBetter: true,
    },
    { label: 'Avg. Bandwidth', get: (k) => k?.avg_bandwidth_permuted, fmt: (v) => v.toFixed(2), lowerIsBetter: true },
    {
      label: 'Diagonal Band frac 0.4%',
      get: (k) => (k?.frac_0_4pct_permuted == null ? null : k.frac_0_4pct_permuted * 100),
      fmt: (v) => `${v.toFixed(2)}%`,
      lowerIsBetter: false,
    },
  ];

  const rows = metrics.map((metric) => {
    const values = runs.map((r) => {
      const v = metric.get(r.detail.kpi_summary);
      return typeof v === 'number' && isFinite(v) ? v : null;
    });
    const valid = values.filter((v): v is number => v !== null);
    const best = valid.length > 1 ? (metric.lowerIsBetter ? Math.min(...valid) : Math.max(...valid)) : null;
    return { metric, values, best };
  });

  const exportCsv = () => {
    downloadCsv(
      ['metric', ...runs.map((r) => `${r.label} (${runShortName(r.dir)})`)],
      rows.map((r) => [r.metric.label, ...r.values]),
      'run_comparison.csv'
    );
  };

  return (
    <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 space-y-4 overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <ArrowLeftRight className="w-4 h-4 text-indigo-400" />
          <h3 className="text-sm font-bold text-white">Run Comparison ({runs.length} runs)</h3>
        </div>
        <button
          onClick={exportCsv}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-slate-800 text-slate-200 hover:bg-slate-700 border border-slate-700"
        >
          <Download className="w-3.5 h-3.5" /> CSV
        </button>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-left border-collapse text-xs font-mono">
          <thead>
            <tr className="bg-slate-950/90 text-slate-400 border-b border-slate-800 uppercase text-xs">
              <th className="py-2.5 px-3 font-sans">Metric (permuted)</th>
              {runs.map((r) => (
                <th key={r.dir} className="py-2.5 px-3 text-right normal-case" style={{ color: r.color }} title={r.dir}>
                  {r.label}
                  <div className="text-xs text-slate-500 font-normal truncate max-w-[160px]">
                    {runShortName(r.dir)}
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/70">
            {rows.map((row, idx) => (
              <tr key={idx} className="hover:bg-slate-800/40">
                <td className="py-2 px-3 font-sans text-slate-300">{row.metric.label}</td>
                {row.values.map((v, i) => (
                  <td
                    key={i}
                    className={`py-2 px-3 text-right ${
                      v !== null && v === row.best ? 'text-emerald-400 font-bold' : 'text-slate-200'
                    }`}
                  >
                    {v === null ? '—' : row.metric.fmt(v)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-slate-500">Best value in each row is highlighted in green.</p>
    </div>
  );
};

const EMPTY_BTN =
  'px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-800 text-slate-200 border border-slate-700 hover:bg-slate-700 hover:text-white transition';

/** Guidance panel shown instead of a bare "nothing here" sentence. */
const EmptyState: React.FC<{ title: string; body?: string; actions?: React.ReactNode }> = ({ title, body, actions }) => (
  <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-10 text-center space-y-3">
    <div className="text-sm font-bold text-white">{title}</div>
    {body && <p className="text-xs text-slate-400 max-w-lg mx-auto leading-relaxed">{body}</p>}
    {actions && <div className="flex flex-wrap items-center justify-center gap-2 pt-1">{actions}</div>}
  </div>
);

/* ---------- Batch summary table: sortable columns, best-value highlight, grouping, failure summaries ---------- */

type SortDir = 'asc' | 'desc';
type GroupBy = 'none' | 'method' | 'scale';

interface MetricColumn {
  id: string;
  label: string;
  /** Wiki topic for the header tooltip. */
  topic?: string;
  /** Extra header tooltip text. */
  hint?: string;
  better: 'lower' | 'higher';
  get: (row: any) => number | null;
  render: (v: number) => React.ReactNode;
  /** Optional text colour for the value (e.g. green for a reduction). */
  tone?: (v: number) => string;
}

const num = (v: unknown): number | null => (typeof v === 'number' && isFinite(v) ? v : null);
const pctChange = (orig: number | null, perm: number | null, square = false) => {
  if (orig == null || perm == null || orig <= 0) return null;
  const o = square ? orig * orig : orig;
  const p = square ? perm * perm : perm;
  return ((p - o) / o) * 100;
};
const fracCol = (key: string, label: string, topic?: string): MetricColumn => ({
  id: `frac_${key}`,
  label,
  topic,
  hint: 'Share of nonzeros inside a diagonal band of this width (higher is better)',
  better: 'higher',
  get: (r) => num(r[`frac_${key}pct_permuted`]),
  render: (v) => `${(v * 100).toFixed(2)}%`,
});

const METRIC_COLUMNS: MetricColumn[] = [
  {
    id: 'bandwidth',
    label: 'Bandwidth B',
    topic: 'metric-bandwidth',
    better: 'lower',
    get: (r) => num(r.bandwidth_permuted),
    render: (v) => v.toLocaleString(),
  },
  {
    id: 'bw_change',
    label: 'BW change',
    hint: 'Bandwidth after permutation vs. original. Negative = smaller = better.',
    better: 'lower',
    get: (r) => pctChange(num(r.bandwidth_original), num(r.bandwidth_permuted)),
    render: (v) => fmtChange(v),
    tone: changeClass,
  },
  {
    id: 'nb2_change',
    label: 'nB² change',
    topic: 'metric-nb2',
    hint: 'Change of the banded-solver cost n·B² vs. original. Negative = cheaper = better.',
    better: 'lower',
    get: (r) => pctChange(num(r.bandwidth_original), num(r.bandwidth_permuted), true),
    render: (v) => fmtChange(v),
    tone: changeClass,
  },
  {
    id: 'avg_bandwidth',
    label: 'Avg. bandwidth',
    topic: 'metric-avg-bandwidth',
    better: 'lower',
    get: (r) => num(r.avg_bandwidth_permuted),
    render: (v) => v.toFixed(2),
  },
  fracCol('0_1', 'frac 0.1%', 'metric-diag-fractions'),
  fracCol('0_4', 'frac 0.4%'),
  fracCol('0_7', 'frac 0.7%'),
  fracCol('1_0', 'frac 1.0%'),
];

const SCALE_ORDER = ['small', 'medium', 'big'];
const TOTAL_COLS = 3 + METRIC_COLUMNS.length;

const BatchSummaryTable: React.FC<{
  rows: any[];
  title: string;
  onExportCsv: () => void;
  onOpenWiki: (topicId: string) => void;
}> = ({ rows, title, onExportCsv, onOpenWiki }) => {
  const [sort, setSort] = useState<{ col: string; dir: SortDir } | null>(null);
  const [groupBy, setGroupBy] = useState<GroupBy>('none');
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const completed = rows.filter((r) => r.status === 'completed');
  const failed = rows.filter((r) => r.status !== 'completed');
  const baseline = completed[0];

  const toggleSort = (col: string) =>
    setSort((cur) => (cur?.col !== col ? { col, dir: 'asc' } : cur.dir === 'asc' ? { col, dir: 'desc' } : null));

  const toggleExpanded = (key: string) =>
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });

  const sortRows = (list: any[]) => {
    if (!sort) return list;
    const col = METRIC_COLUMNS.find((c) => c.id === sort.col);
    const keyOf = (r: any): string | number | null =>
      sort.col === 'method'
        ? methodLabel(r.algorithm)
        : sort.col === 'scale'
        ? SCALE_ORDER.indexOf(r.coarsening_size)
        : col
        ? col.get(r)
        : null;
    const sign = sort.dir === 'asc' ? 1 : -1;
    return [...list].sort((a, b) => {
      const ka = keyOf(a);
      const kb = keyOf(b);
      if (ka == null && kb == null) return 0;
      if (ka == null) return 1; // missing values always last
      if (kb == null) return -1;
      if (typeof ka === 'string' || typeof kb === 'string') return String(ka).localeCompare(String(kb)) * sign;
      return (ka - kb) * sign;
    });
  };

  // Groups: [{ key, label, color?, rows }]; a single unnamed group when not grouping.
  const groups = useMemo(() => {
    if (groupBy === 'none') return [{ key: 'all', label: '', color: undefined as string | undefined, rows }];
    const keyOf = (r: any) => (groupBy === 'method' ? r.algorithm : r.coarsening_size) || '—';
    const order: string[] = [];
    const byKey = new Map<string, any[]>();
    for (const r of rows) {
      const k = keyOf(r);
      if (!byKey.has(k)) {
        byKey.set(k, []);
        order.push(k);
      }
      byKey.get(k)!.push(r);
    }
    if (groupBy === 'scale') order.sort((a, b) => SCALE_ORDER.indexOf(a) - SCALE_ORDER.indexOf(b));
    return order.map((k) => ({
      key: k,
      label: groupBy === 'method' ? methodLabel(k) : `${scaleLabel(k)} scale`,
      color: groupBy === 'method' ? methodColor(k) : undefined,
      rows: byKey.get(k)!,
    }));
  }, [rows, groupBy]);

  /** Best value per metric column within a set of rows (only meaningful with ≥2 values). */
  const bestFor = (list: any[]) => {
    const best: Record<string, number | null> = {};
    for (const col of METRIC_COLUMNS) {
      const vals = list
        .filter((r) => r.status === 'completed')
        .map((r) => col.get(r))
        .filter((v): v is number => v !== null);
      best[col.id] = vals.length > 1 ? (col.better === 'lower' ? Math.min(...vals) : Math.max(...vals)) : null;
    }
    return best;
  };

  const ariaSort = (col: string): React.AriaAttributes['aria-sort'] =>
    sort?.col === col ? (sort.dir === 'asc' ? 'ascending' : 'descending') : 'none';

  // A render function (not a nested component) so the header buttons keep focus across re-sorts.
  const sortHeader = ({
    col,
    label,
    align = 'right',
    topic,
    hint,
    better,
  }: {
    col: string;
    label: string;
    align?: 'left' | 'right';
    topic?: string;
    hint?: string;
    better?: 'lower' | 'higher';
  }) => {
    const active = sort?.col === col;
    const Icon = !active ? ChevronsUpDown : sort!.dir === 'asc' ? ArrowUp : ArrowDown;
    return (
      <th key={col} aria-sort={ariaSort(col)} className={`py-2.5 px-3 ${align === 'right' ? 'text-right' : 'text-left'} whitespace-nowrap`}>
        <span className={`inline-flex items-center gap-1 ${align === 'right' ? 'justify-end' : ''}`}>
          <button
            type="button"
            onClick={() => toggleSort(col)}
            title={`${hint ? `${hint} ` : ''}${better ? `(${better} is better) ` : ''}Click to sort`}
            className={`inline-flex items-center gap-1 rounded px-1 -mx-1 hover:text-white focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 ${
              active ? 'text-indigo-300' : ''
            }`}
          >
            {label}
            <Icon className={`w-3 h-3 ${active ? '' : 'opacity-50'}`} aria-hidden />
          </button>
          {topic && <InfoTooltip topicId={topic} onOpenWiki={onOpenWiki} />}
        </span>
      </th>
    );
  };

  const renderRow = (row: any, best: Record<string, number | null>) => {
    if (row.status !== 'completed') {
      const reason = shortFailureReason(row.error_message, row.error_type);
      const open = expanded.has(row.case_key);
      return (
        <React.Fragment key={row.case_key}>
          <tr className="bg-rose-950/20">
            <td className="py-2.5 px-4 font-sans">
              <MethodName method={row.algorithm} />
            </td>
            <td className="py-2.5 px-3">
              <ScaleChip scale={row.coarsening_size} />
            </td>
            <td colSpan={METRIC_COLUMNS.length + 1} className="py-2.5 px-3 font-sans text-xs">
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                <span className="text-rose-300 font-semibold">Failed: {reason}</span>
                {(row.error_message || row.error_type) && (
                  <button
                    type="button"
                    onClick={() => toggleExpanded(row.case_key)}
                    aria-expanded={open}
                    className="inline-flex items-center gap-0.5 text-xs text-slate-400 hover:text-white underline-offset-2 hover:underline"
                  >
                    {open ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
                    {open ? 'hide details' : 'details'}
                  </button>
                )}
              </div>
            </td>
          </tr>
          {open && (
            <tr className="bg-rose-950/10">
              <td colSpan={TOTAL_COLS} className="px-4 pb-3 pt-0">
                <pre className="whitespace-pre-wrap break-words text-xs leading-relaxed text-rose-200/90 bg-slate-950 border border-rose-900/50 rounded-lg p-3 max-h-60 overflow-auto">
                  {row.error_type ? `${row.error_type}: ` : ''}
                  {row.error_message || ''}
                  {'\n'}case: {row.case_key}
                </pre>
              </td>
            </tr>
          )}
        </React.Fragment>
      );
    }
    return (
      <tr key={row.case_key} className="hover:bg-slate-800/40 transition text-slate-200">
        <td className="py-2.5 px-4 font-sans">
          <MethodName method={row.algorithm} />
        </td>
        <td className="py-2.5 px-3">
          <ScaleChip scale={row.coarsening_size} />
        </td>
        {METRIC_COLUMNS.map((col) => {
          const v = col.get(row);
          const isBest = v !== null && best[col.id] !== null && v === best[col.id];
          return (
            <td
              key={col.id}
              className={`py-2.5 px-3 text-right whitespace-nowrap ${col.tone && v !== null ? col.tone(v) : ''} ${
                isBest ? 'font-bold bg-emerald-500/10 shadow-[inset_0_0_0_1px_rgba(16,185,129,0.45)]' : ''
              }`}
              title={isBest ? `Best ${col.label} (${col.better} is better)` : undefined}
            >
              {v === null ? '—' : col.render(v)}
              {isBest && <span className="sr-only"> (best)</span>}
            </td>
          );
        })}
        <td className="py-2.5 px-3 text-center">
          {row.permutation_mismatches === 0 ? (
            <span className="inline-flex items-center gap-1 text-emerald-400 text-xs">
              <CheckCircle2 className="w-3.5 h-3.5" /> 0 err
            </span>
          ) : (
            <span className="text-rose-400">Mismatch</span>
          )}
        </td>
      </tr>
    );
  };

  return (
    <div className="bg-slate-900/80 border border-slate-800 rounded-2xl overflow-hidden shadow-lg">
      <div className="p-4 border-b border-slate-800 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-bold text-white">{title}</h3>
          <div className="text-xs text-slate-400 mt-0.5">
            {completed.length} completed
            {failed.length > 0 && <span className="text-rose-300"> · {failed.length} failed</span>} · outlined cell = best
            value in its column{groupBy !== 'none' ? ' within the group' : ''}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex items-center gap-1 bg-slate-950 p-1 rounded-lg border border-slate-800" role="group" aria-label="Group rows by">
            <span className="text-xs text-slate-400 px-1.5">Group by</span>
            {(['none', 'method', 'scale'] as const).map((g) => (
              <button
                key={g}
                type="button"
                onClick={() => setGroupBy(g)}
                aria-pressed={groupBy === g}
                className={`px-2.5 py-1 rounded-md text-xs font-semibold capitalize transition ${
                  groupBy === g ? 'bg-indigo-600 text-white' : 'text-slate-400 hover:text-white'
                }`}
              >
                {g}
              </button>
            ))}
          </div>
          <button
            onClick={onExportCsv}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-slate-800 text-slate-200 hover:bg-slate-700 border border-slate-700"
            title="Download this table (raw values, all cases) as CSV"
          >
            <Download className="w-3.5 h-3.5" /> CSV
          </button>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left border-collapse text-xs">
          <thead>
            <tr className="bg-slate-950/90 text-slate-400 border-b border-slate-800 font-sans font-semibold text-xs">
              {sortHeader({ col: 'method', label: 'Method', align: 'left' })}
              {sortHeader({ col: 'scale', label: 'Scale', align: 'left' })}
              {METRIC_COLUMNS.map((c) =>
                sortHeader({ col: c.id, label: c.label, topic: c.topic, hint: c.hint, better: c.better })
              )}
              <th className="py-2.5 px-3 text-center whitespace-nowrap">Perm check</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/70 font-mono">
            {baseline && (
              <tr className="bg-slate-950/40 text-slate-300 font-semibold">
                <td className="py-2.5 px-4 font-sans text-white">Original (unpermuted)</td>
                <td className="py-2.5 px-3 text-slate-500 font-sans">—</td>
                <td className="py-2.5 px-3 text-right">{num(baseline.bandwidth_original)?.toLocaleString() ?? '—'}</td>
                <td className="py-2.5 px-3 text-right text-slate-500">—</td>
                <td className="py-2.5 px-3 text-right text-slate-500">—</td>
                <td className="py-2.5 px-3 text-right">{num(baseline.avg_bandwidth_original)?.toFixed(2) ?? '—'}</td>
                {['0_1', '0_4', '0_7', '1_0'].map((k) => {
                  const v = num(baseline[`frac_${k}pct_original`]);
                  return (
                    <td key={k} className="py-2.5 px-3 text-right">
                      {v === null ? '—' : `${(v * 100).toFixed(2)}%`}
                    </td>
                  );
                })}
                <td className="py-2.5 px-3 text-center text-slate-500 font-sans">Baseline</td>
              </tr>
            )}
            {groups.map((g) => {
              const best = bestFor(g.rows);
              const ordered = [...sortRows(g.rows.filter((r) => r.status === 'completed')), ...g.rows.filter((r) => r.status !== 'completed')];
              return (
                <React.Fragment key={g.key}>
                  {groupBy !== 'none' && (
                    <tr className="bg-slate-950/80 border-t border-slate-700">
                      <th colSpan={TOTAL_COLS} scope="rowgroup" className="py-2 px-4 text-left font-sans text-xs font-semibold text-slate-200">
                        <span className="inline-flex items-center gap-2">
                          {g.color && <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: g.color }} aria-hidden />}
                          {g.label}
                          <span className="text-xs font-normal text-slate-500">
                            {g.rows.length} {g.rows.length === 1 ? 'case' : 'cases'}
                          </span>
                        </span>
                      </th>
                    </tr>
                  )}
                  {ordered.map((r) => renderRow(r, best))}
                </React.Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
};

const MethodName: React.FC<{ method: string }> = ({ method }) => (
  <span className="inline-flex items-center gap-2 font-semibold text-white whitespace-nowrap" title={methodLabel(method)}>
    <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ backgroundColor: methodColor(method) }} aria-hidden />
    {methodLabel(method, undefined, true)}
  </span>
);

const ScaleChip: React.FC<{ scale: string }> = ({ scale }) => (
  <span className="px-2 py-0.5 rounded-md bg-slate-800 border border-slate-700 text-slate-200 text-xs font-sans font-medium">
    {scaleLabel(scale)}
  </span>
);
