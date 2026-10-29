import React, { useEffect, useState } from 'react';
import {
  ArrowLeftRight,
  BarChart3,
  Check,
  CheckCircle2,
  Copy,
  Download,
  FileText,
  Image as ImageIcon,
  Layers,
  Loader2,
  RefreshCw,
  Sparkles,
  Table,
  ZoomIn,
} from 'lucide-react';
import { api } from '../api/client';
import { Demonstrator } from '../types/pipeline';
import { InfoTooltip } from './InfoTooltip';

interface ResultsExplorerProps {
  demonstrators: Demonstrator[];
  selectedDemonstratorId: string;
  initialResultDir: string | null;
  initialBatchId: string | null;
  onOpenWiki: (topicId: string) => void;
}

const METHOD_COLORS: Record<string, string> = {
  Original: '#94a3b8',
  metis: '#10b981',
  qa_hardware: '#a855f7',
  qa_emulated: '#6366f1',
  qaoa_emulated: '#06b6d4',
  qaoa_hardware: '#ec4899',
};

const METHOD_LABELS: Record<string, string> = {
  Original: 'Original',
  metis: 'METIS',
  qa_hardware: 'QA Hardware (D-Wave)',
  qa_emulated: 'QA Emulated',
  qaoa_emulated: 'QAOA Emulated',
  qaoa_hardware: 'QAOA Hardware (QLM)',
};

export const ResultsExplorer: React.FC<ResultsExplorerProps> = ({
  demonstrators,
  selectedDemonstratorId,
  initialResultDir,
  initialBatchId,
  onOpenWiki,
}) => {
  const [mode, setMode] = useState<'batch' | 'single'>(
    initialResultDir ? 'single' : 'batch'
  );

  // Single Run State
  const [demId, setDemId] = useState<string>(selectedDemonstratorId);
  const [singleRuns, setSingleRuns] = useState<any[]>([]);
  const [activeResultDir, setActiveResultDir] = useState<string | null>(initialResultDir);
  const [runDetail, setRunDetail] = useState<any | null>(null);
  const [compareResultDir, setCompareResultDir] = useState<string>('');
  const [compareRunDetail, setCompareRunDetail] = useState<any | null>(null);
  const [loadingSingle, setLoadingSingle] = useState(false);
  const [activePlots, setActivePlots] = useState<Record<string, boolean>>({});
  const [zoomImageUrl, setZoomImageUrl] = useState<{ url: string; title: string } | null>(null);

  // Batch Analysis State
  const [batchRuns, setBatchRuns] = useState<any[]>([]);
  const [activeBatchId, setActiveBatchId] = useState<string>(
    initialBatchId || 'batch_20260521_151902'
  );
  const [batchDem, setBatchDem] = useState<string>('matrix_01');
  const [batchAnalysis, setBatchAnalysis] = useState<any | null>(null);
  const [matrixTab, setMatrixTab] = useState<'K' | 'M'>('K');
  const [activeLatexTab, setActiveLatexTab] = useState<
    'k_summary' | 'm_summary' | 'k_nb2' | 'm_nb2'
  >('k_summary');
  const [copiedLatex, setCopiedLatex] = useState(false);

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
    api.listBatchRuns().then((res) => {
      setBatchRuns(res.batch_runs);
      if (!activeBatchId && res.batch_runs.length > 0) {
        setActiveBatchId(res.batch_runs[0].id);
      }
    });
  }, []);

  useEffect(() => {
    if (!activeBatchId) return;
    api
      .getBatchAnalysis(activeBatchId, batchDem)
      .then((res) => setBatchAnalysis(res))
      .catch(() => setBatchAnalysis(null));
  }, [activeBatchId, batchDem]);

  useEffect(() => {
    api
      .listDemonstratorRuns(demId)
      .then((res) => {
        setSingleRuns(res.runs);
        if (!activeResultDir && res.runs.length > 0) {
          setActiveResultDir(res.runs[0].result_dir);
        }
      })
      .catch(() => setSingleRuns([]));
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
          k_original_matrix_partitioned: true,
          k_permuted_matrix_partitioned: true,
          k_coarsened_graph_partitioned: true,
          k_uncoarsened_graph_partitioned: true,
        });
      })
      .catch(() => setRunDetail(null))
      .finally(() => setLoadingSingle(false));
  }, [activeResultDir]);

  useEffect(() => {
    if (!compareResultDir) {
      setCompareRunDetail(null);
      return;
    }
    api
      .getSingleRunDetail(compareResultDir)
      .then((res) => setCompareRunDetail(res))
      .catch(() => setCompareRunDetail(null));
  }, [compareResultDir]);

  const copyLatex = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedLatex(true);
    setTimeout(() => setCopiedLatex(false), 2000);
  };

  return (
    <div className="space-y-6">
      {/* Top Mode Switcher */}
      <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-4 flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-2.5">
          <span className="px-2.5 py-0.5 text-xs font-semibold rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
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
                  className="bg-slate-950 border border-slate-700 rounded-lg px-3 py-1.5 text-xs font-mono text-white"
                >
                  {batchRuns.map((br) => (
                    <option key={br.id} value={br.id}>
                      {br.id} ({br.completed_cases}/{br.total_cases} completed)
                    </option>
                  ))}
                </select>
              </div>

              <div className="flex items-center gap-2">
                <span className="text-xs text-slate-400 font-medium">Matrix:</span>
                <div className="flex items-center gap-1">
                  {(batchAnalysis?.available_demonstrators || ['matrix_01', 'matrix_02']).map(
                    (d: string) => (
                      <button
                        key={d}
                        onClick={() => setBatchDem(d)}
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

            {/* Matrix K vs M Toggle */}
            <div className="flex items-center gap-1.5 bg-slate-950 p-1 rounded-xl border border-slate-800">
              <button
                onClick={() => setMatrixTab('K')}
                className={`px-3.5 py-1.5 rounded-lg text-xs font-bold transition ${
                  matrixTab === 'K'
                    ? 'bg-indigo-600 text-white'
                    : 'text-slate-400 hover:text-white'
                }`}
              >
                Stiffness Matrix (K)
              </button>
              <button
                onClick={() => setMatrixTab('M')}
                className={`px-3.5 py-1.5 rounded-lg text-xs font-bold transition ${
                  matrixTab === 'M'
                    ? 'bg-cyan-600 text-white'
                    : 'text-slate-400 hover:text-white'
                }`}
              >
                Mass Matrix (M)
              </button>
            </div>
          </div>

          {batchAnalysis && batchAnalysis.completed_rows?.length > 0 ? (
            <>
              {/* Comparative Metrics Table */}
              <div className="bg-slate-900/80 border border-slate-800 rounded-2xl overflow-hidden shadow-lg">
                <div className="p-4 border-b border-slate-800 flex items-center justify-between">
                  <h3 className="text-sm font-bold text-white">
                    {matrixTab}-Matrix Summary ({batchDem})
                  </h3>
                </div>

                <div className="overflow-x-auto">
                  <table className="w-full text-left border-collapse text-xs">
                    <thead>
                      <tr className="bg-slate-950/90 text-slate-400 border-b border-slate-800 font-mono uppercase text-[11px]">
                        <th className="py-3 px-4">Method</th>
                        <th className="py-3 px-3">Coarse Scale</th>
                        <th className="py-3 px-3 text-right">
                          <span className="inline-flex items-center gap-1 justify-end">
                            Bandwidth B({matrixTab})
                            <InfoTooltip topicId="metric-bandwidth" onOpenWiki={onOpenWiki} />
                          </span>
                        </th>
                        <th className="py-3 px-3 text-right">BW Change</th>
                        <th className="py-3 px-3 text-right">
                          <span className="inline-flex items-center gap-1 justify-end">
                            nB² Reduction
                            <InfoTooltip topicId="metric-nb2" onOpenWiki={onOpenWiki} />
                          </span>
                        </th>
                        <th className="py-3 px-3 text-right">
                          <span className="inline-flex items-center gap-1 justify-end">
                            Avg. Bandwidth
                            <InfoTooltip topicId="metric-avg-bandwidth" onOpenWiki={onOpenWiki} />
                          </span>
                        </th>
                        <th className="py-3 px-3 text-right">
                          <span className="inline-flex items-center gap-1 justify-end">
                            frac 0.1%
                            <InfoTooltip topicId="metric-diag-fractions" onOpenWiki={onOpenWiki} />
                          </span>
                        </th>
                        <th className="py-3 px-3 text-right">frac 0.4%</th>
                        <th className="py-3 px-3 text-right">frac 0.7%</th>
                        <th className="py-3 px-3 text-right">frac 1.0%</th>
                        <th className="py-3 px-3 text-center">Perm Check</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800/70 font-mono">
                      {/* Baseline Original Row */}
                      {(() => {
                        const first = batchAnalysis.completed_rows[0];
                        const bwOrig = first[`${matrixTab}_bandwidth_original`];
                        const avgOrig = first[`${matrixTab}_avg_bandwidth_original`];
                        return (
                          <tr className="bg-slate-950/40 text-slate-300 font-semibold">
                            <td className="py-3 px-4 font-sans text-white">Original Unpermuted</td>
                            <td className="py-3 px-3 text-slate-500">N/A</td>
                            <td className="py-3 px-3 text-right">{bwOrig?.toLocaleString()}</td>
                            <td className="py-3 px-3 text-right text-slate-500">—</td>
                            <td className="py-3 px-3 text-right text-slate-500">—</td>
                            <td className="py-3 px-3 text-right">{avgOrig?.toFixed(2)}</td>
                            <td className="py-3 px-3 text-right">
                              {(first[`${matrixTab}_frac_0_1pct_original`] * 100).toFixed(2)}%
                            </td>
                            <td className="py-3 px-3 text-right">
                              {(first[`${matrixTab}_frac_0_4pct_original`] * 100).toFixed(2)}%
                            </td>
                            <td className="py-3 px-3 text-right">
                              {(first[`${matrixTab}_frac_0_7pct_original`] * 100).toFixed(2)}%
                            </td>
                            <td className="py-3 px-3 text-right">
                              {(first[`${matrixTab}_frac_1_0pct_original`] * 100).toFixed(2)}%
                            </td>
                            <td className="py-3 px-3 text-center text-slate-500">Baseline</td>
                          </tr>
                        );
                      })()}

                      {batchAnalysis.rows.map((row: any) => {
                        if (row.status !== 'completed') {
                          return (
                            <tr key={row.case_key} className="bg-rose-950/20 text-rose-300">
                              <td className="py-3 px-4 font-sans font-semibold">
                                {METHOD_LABELS[row.algorithm] || row.algorithm}
                              </td>
                              <td className="py-3 px-3 uppercase">{row.coarsening_size}</td>
                              <td colSpan={9} className="py-3 px-4 text-xs">
                                Failed: {row.error_message || row.error_type}
                              </td>
                            </tr>
                          );
                        }

                        const bwOrig = row[`${matrixTab}_bandwidth_original`];
                        const bwPerm = row[`${matrixTab}_bandwidth_permuted`];
                        const bwRed =
                          bwOrig > 0 ? ((bwOrig - bwPerm) / bwOrig) * 100 : 0;
                        const nb2Red =
                          bwOrig > 0
                            ? ((bwOrig * bwOrig - bwPerm * bwPerm) / (bwOrig * bwOrig)) * 100
                            : 0;
                        const f01Orig = row[`${matrixTab}_frac_0_1pct_original`];
                        const f01Perm = row[`${matrixTab}_frac_0_1pct_permuted`];
                        const f04Orig = row[`${matrixTab}_frac_0_4pct_original`];
                        const f04Perm = row[`${matrixTab}_frac_0_4pct_permuted`];

                        return (
                          <tr
                            key={row.case_key}
                            className="hover:bg-slate-800/40 transition text-slate-200"
                          >
                            <td className="py-3 px-4 font-sans font-semibold text-white">
                              {METHOD_LABELS[row.algorithm] || row.algorithm}
                            </td>
                            <td className="py-3 px-3">
                              <span className="px-2 py-0.5 rounded bg-slate-800 text-amber-300 text-[11px] uppercase">
                                {row.coarsening_size}
                              </span>
                            </td>
                            <td className="py-3 px-3 text-right font-bold">
                              {bwPerm?.toLocaleString()}
                            </td>
                            <td
                              className={`py-3 px-3 text-right font-semibold ${
                                bwRed > 0 ? 'text-emerald-400' : 'text-amber-400'
                              }`}
                            >
                              {bwRed > 0 ? `-${bwRed.toFixed(1)}%` : `+${Math.abs(bwRed).toFixed(1)}%`}
                            </td>
                            <td
                              className={`py-3 px-3 text-right font-bold ${
                                nb2Red > 0 ? 'text-emerald-400' : 'text-slate-400'
                              }`}
                            >
                              {nb2Red > 0 ? `-${nb2Red.toFixed(1)}%` : `${nb2Red.toFixed(1)}%`}
                            </td>
                            <td className="py-3 px-3 text-right">
                              {row[`${matrixTab}_avg_bandwidth_permuted`]?.toFixed(2)}
                            </td>
                            <td
                              className={`py-3 px-3 text-right ${
                                f01Perm > f01Orig ? 'text-emerald-300 font-semibold' : ''
                              }`}
                            >
                              {(f01Perm * 100).toFixed(2)}%
                            </td>
                            <td
                              className={`py-3 px-3 text-right ${
                                f04Perm > f04Orig ? 'text-emerald-300 font-semibold' : ''
                              }`}
                            >
                              {(f04Perm * 100).toFixed(2)}%
                            </td>
                            <td className="py-3 px-3 text-right">
                              {(row[`${matrixTab}_frac_0_7pct_permuted`] * 100).toFixed(2)}%
                            </td>
                            <td className="py-3 px-3 text-right">
                              {(row[`${matrixTab}_frac_1_0pct_permuted`] * 100).toFixed(2)}%
                            </td>
                            <td className="py-3 px-3 text-center">
                              {row[`${matrixTab}_permutation_mismatches`] === 0 ? (
                                <span className="inline-flex items-center gap-1 text-emerald-400 text-[11px]">
                                  <CheckCircle2 className="w-3.5 h-3.5" /> 0 err
                                </span>
                              ) : (
                                <span className="text-rose-400">Mismatch</span>
                              )}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Multi-Method Locality Curves by Scale */}
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
                {(batchAnalysis.comparison_curves?.[matrixTab] || []).map((scaleBlock: any) => (
                  <div
                    key={scaleBlock.coarsening_size}
                    className="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 space-y-3"
                  >
                    <div className="flex items-center justify-between">
                      <div>
                        <span className="text-[11px] font-mono uppercase text-amber-300">
                          Coarsening Scale: {scaleBlock.coarsening_size}
                        </span>
                        <h4 className="text-sm font-bold text-white">
                          {matrixTab}-Matrix Diagonal Band Concentration
                        </h4>
                      </div>
                    </div>

                    <MultiMethodSvgChart
                      points={scaleBlock.points}
                      methods={['Original', ...scaleBlock.methods]}
                    />
                  </div>
                ))}
              </div>

              {/* Thesis LaTeX Table Generator */}
              <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-6 space-y-4">
                <div className="flex flex-wrap items-center justify-between gap-4">
                  <h3 className="text-sm font-bold text-white flex items-center gap-2">
                    <FileText className="w-4 h-4 text-indigo-400" />
                    Thesis LaTeX Table
                  </h3>

                  <div className="flex flex-wrap items-center gap-2">
                    {[
                      { id: 'k_summary', label: 'K Numerical Summary' },
                      { id: 'm_summary', label: 'M Numerical Summary' },
                      { id: 'k_nb2', label: 'K nB² Complexity Table' },
                      { id: 'm_nb2', label: 'M nB² Complexity Table' },
                    ].map((t) => (
                      <button
                        key={t.id}
                        onClick={() => setActiveLatexTab(t.id as any)}
                        className={`px-3 py-1.5 rounded-lg text-xs font-medium transition ${
                          activeLatexTab === t.id
                            ? 'bg-indigo-600 text-white'
                            : 'bg-slate-950 text-slate-400 hover:text-white border border-slate-800'
                        }`}
                      >
                        {t.label}
                      </button>
                    ))}

                    <button
                      onClick={() =>
                        copyLatex(batchAnalysis.latex_tables?.[activeLatexTab] || '')
                      }
                      className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-semibold bg-emerald-600/20 text-emerald-300 border border-emerald-500/30 hover:bg-emerald-600/30 transition"
                    >
                      {copiedLatex ? (
                        <>
                          <Check className="w-3.5 h-3.5" /> Copied!
                        </>
                      ) : (
                        <>
                          <Copy className="w-3.5 h-3.5" /> Copy LaTeX
                        </>
                      )}
                    </button>
                  </div>
                </div>

                <pre className="p-4 rounded-xl bg-slate-950 border border-slate-800 text-xs font-mono text-slate-200 overflow-x-auto leading-relaxed">
                  {batchAnalysis.latex_tables?.[activeLatexTab] || 'No LaTeX table available.'}
                </pre>
              </div>
            </>
          ) : (
            <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-12 text-center text-sm text-slate-400">
              No completed batch rows found for {batchDem} in {activeBatchId}.
            </div>
          )}
        </div>
      )}

      {/* MODE 2: SINGLE RUN DEEP-DIVE & 10-PLOT VISUAL GALLERY */}
      {mode === 'single' && (
        <div className="space-y-6">
          {/* Demonstrator & Run Folder Selector */}
          <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-4 flex flex-wrap items-center justify-between gap-4">
            <div className="flex flex-wrap items-center gap-4 min-w-0">
              <div className="flex items-center gap-2">
                <span className="text-xs text-slate-400 font-medium">Matrix:</span>
                <select
                  value={demId}
                  onChange={(e) => {
                    setDemId(e.target.value);
                    setActiveResultDir(null);
                    setCompareResultDir('');
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
                  onChange={(e) => setActiveResultDir(e.target.value)}
                  className="bg-slate-950 border border-slate-700 rounded-lg px-3 py-1.5 text-xs font-mono text-white max-w-[260px] truncate"
                >
                  {singleRuns.length === 0 && (
                    <option value="">No local runs in demonstrators/{demId}/results/</option>
                  )}
                  {singleRuns.map((r) => (
                    <option key={r.result_dir} value={r.result_dir}>
                      {r.run_id} — {r.partitioning_strategy} (k={r.k_target})
                    </option>
                  ))}
                </select>
              </div>

              {singleRuns.length > 1 && (
                <div className="flex items-center gap-2 min-w-0">
                  <ArrowLeftRight className="w-3.5 h-3.5 text-amber-400 shrink-0" />
                  <span className="text-xs text-slate-400 font-medium shrink-0">
                    Compare Run B:
                  </span>
                  <select
                    value={compareResultDir}
                    onChange={(e) => setCompareResultDir(e.target.value)}
                    className="bg-slate-950 border border-slate-700 rounded-lg px-3 py-1.5 text-xs font-mono text-amber-200 max-w-[260px] truncate"
                  >
                    <option value="">None (Single Run View)</option>
                    {singleRuns
                      .filter((r) => r.result_dir !== activeResultDir)
                      .map((r) => (
                        <option key={r.result_dir} value={r.result_dir}>
                          {r.run_id} — {r.partitioning_strategy} (k={r.k_target})
                        </option>
                      ))}
                  </select>
                </div>
              )}
            </div>

            {activeResultDir && (
              <a
                href={`/api/results/download-bundle?result_dir=${encodeURIComponent(
                  activeResultDir
                )}`}
                download
                className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-xl text-xs font-semibold bg-emerald-600/20 hover:bg-emerald-600/30 text-emerald-300 border border-emerald-500/40 transition shrink-0"
              >
                <Download className="w-3.5 h-3.5" />
                Download Run Bundle (.zip)
              </a>
            )}
          </div>

          {loadingSingle ? (
            <div className="p-12 text-center text-sm text-slate-400 flex items-center justify-center gap-2">
              <Loader2 className="w-5 h-5 animate-spin text-indigo-400" />
              Loading run metrics and artifacts...
            </div>
          ) : runDetail ? (
            <>
              {/* KPI Summary Cards for K and M */}
              {runDetail.kpi_summary && (
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
                  {(['K', 'M'] as const).map((mName) => {
                    const kpi = runDetail.kpi_summary[mName];
                    if (!kpi) return null;
                    const bwRed = kpi.bandwidth_reduction_pct ?? 0;
                    const nb2Red = kpi.nb2_reduction_pct ?? 0;
                    return (
                      <div
                        key={mName}
                        className="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 space-y-4"
                      >
                        <div className="flex items-center justify-between">
                          <h3 className="text-sm font-bold text-white">
                            Matrix {mName} Structural Performance
                          </h3>
                          {kpi.permutation_check?.mismatches === 0 && (
                            <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
                              <CheckCircle2 className="w-3.5 h-3.5" /> Valid Permutation (0 mismatches)
                            </span>
                          )}
                        </div>

                        <div className="grid grid-cols-3 gap-3">
                          <div className="p-3 rounded-xl bg-slate-950 border border-slate-800">
                            <div className="text-[11px] text-slate-400">Max Bandwidth B({mName})</div>
                            <div className="text-sm font-mono font-bold text-white mt-0.5">
                              {kpi.bandwidth_original?.toLocaleString()} →{' '}
                              {kpi.bandwidth_permuted?.toLocaleString()}
                            </div>
                            <div
                              className={`text-xs font-mono font-semibold mt-0.5 ${
                                bwRed >= 0 ? 'text-emerald-400' : 'text-amber-400'
                              }`}
                            >
                              {bwRed >= 0
                                ? `-${bwRed.toFixed(2)}% reduction`
                                : `+${Math.abs(bwRed).toFixed(2)}%`}
                            </div>
                          </div>

                          <div className="p-3 rounded-xl bg-slate-950 border border-slate-800">
                            <div className="text-[11px] text-slate-400">Avg. Bandwidth</div>
                            <div className="text-sm font-mono font-bold text-white mt-0.5">
                              {kpi.avg_bandwidth_original?.toFixed(1)} →{' '}
                              {kpi.avg_bandwidth_permuted?.toFixed(1)}
                            </div>
                            <div className="text-[11px] font-mono text-slate-400 mt-0.5">
                              NNZ: {kpi.nnz_permuted?.toLocaleString()}
                            </div>
                          </div>

                          <div className="p-3 rounded-xl bg-slate-950 border border-slate-800">
                            <div className="text-[11px] text-slate-400">nB² Complexity</div>
                            <div
                              className={`text-sm font-mono font-bold mt-0.5 ${
                                nb2Red >= 0 ? 'text-emerald-400' : 'text-amber-400'
                              }`}
                            >
                              {nb2Red >= 0
                                ? `-${nb2Red.toFixed(1)}%`
                                : `+${Math.abs(nb2Red).toFixed(1)}%`}
                            </div>
                            <div className="text-[11px] font-mono text-slate-400 mt-0.5">
                              frac 0.4%: {((kpi.frac_0_4pct_permuted || 0) * 100).toFixed(1)}%
                            </div>
                          </div>
                        </div>

                        {/* Interactive 100-Point Locality Curve */}
                        {runDetail.curves?.[mName]?.length > 0 && (
                          <SingleRunCurveSvg
                            points={runDetail.curves[mName]}
                            comparePoints={compareRunDetail?.curves?.[mName]}
                            matrixName={mName}
                          />
                        )}
                      </div>
                    );
                  })}
                </div>
              )}

              {/* Side-by-Side Single Run Comparator (Run A vs. Run B) */}
              {compareRunDetail?.kpi_summary && runDetail?.kpi_summary && (
                <div className="bg-slate-900/80 border border-amber-500/30 rounded-2xl p-5 space-y-4 overflow-hidden">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <ArrowLeftRight className="w-4 h-4 text-amber-400" />
                      <h3 className="text-sm font-bold text-white">
                        Side-by-Side Single Run Comparison (Run A vs. Run B)
                      </h3>
                    </div>
                    <div className="flex items-center gap-3 text-xs font-mono">
                      <span className="text-indigo-300">
                        Run A: {activeResultDir?.split('/').pop()}
                      </span>
                      <span className="text-slate-600">vs.</span>
                      <span className="text-amber-300">
                        Run B: {compareResultDir.split('/').pop()}
                      </span>
                    </div>
                  </div>

                  <div className="overflow-x-auto">
                    <table className="w-full text-left border-collapse text-xs font-mono">
                      <thead>
                        <tr className="bg-slate-950/90 text-slate-400 border-b border-slate-800 uppercase text-[11px]">
                          <th className="py-2.5 px-3 font-sans">Matrix</th>
                          <th className="py-2.5 px-3 font-sans">Metric</th>
                          <th className="py-2.5 px-3 text-right text-indigo-300">Run A (Permuted)</th>
                          <th className="py-2.5 px-3 text-right text-amber-300">Run B (Permuted)</th>
                          <th className="py-2.5 px-3 text-right">Delta (A vs B)</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-800/70">
                        {(['K', 'M'] as const).flatMap((mName) => {
                          const kA = runDetail.kpi_summary[mName];
                          const kB = compareRunDetail.kpi_summary[mName];
                          if (!kA || !kB) return [];
                          return [
                            {
                              matrix: mName,
                              label: `Max Bandwidth B(${mName})`,
                              a: kA.bandwidth_permuted,
                              b: kB.bandwidth_permuted,
                              fmt: (v: number) => v?.toLocaleString(),
                              lowerIsBetter: true,
                            },
                            {
                              matrix: mName,
                              label: `Bandwidth Reduction (%)`,
                              a: kA.bandwidth_reduction_pct,
                              b: kB.bandwidth_reduction_pct,
                              fmt: (v: number) => `${v?.toFixed(2)}%`,
                              lowerIsBetter: false,
                            },
                            {
                              matrix: mName,
                              label: `nB² Complexity Reduction (%)`,
                              a: kA.nb2_reduction_pct,
                              b: kB.nb2_reduction_pct,
                              fmt: (v: number) => `${v?.toFixed(2)}%`,
                              lowerIsBetter: false,
                            },
                            {
                              matrix: mName,
                              label: `Avg. Bandwidth`,
                              a: kA.avg_bandwidth_permuted,
                              b: kB.avg_bandwidth_permuted,
                              fmt: (v: number) => v?.toFixed(2),
                              lowerIsBetter: true,
                            },
                            {
                              matrix: mName,
                              label: `Diagonal Band frac 0.4%`,
                              a: (kA.frac_0_4pct_permuted || 0) * 100,
                              b: (kB.frac_0_4pct_permuted || 0) * 100,
                              fmt: (v: number) => `${v?.toFixed(2)}%`,
                              lowerIsBetter: false,
                            },
                          ].map((row, idx) => {
                            const diff = (row.a ?? 0) - (row.b ?? 0);
                            const aBetter = row.lowerIsBetter ? diff < 0 : diff > 0;
                            const bBetter = row.lowerIsBetter ? diff > 0 : diff < 0;
                            return (
                              <tr key={`${mName}-${idx}`} className="hover:bg-slate-800/40">
                                <td className="py-2 px-3 font-bold text-white">{row.matrix}</td>
                                <td className="py-2 px-3 font-sans text-slate-300">{row.label}</td>
                                <td
                                  className={`py-2 px-3 text-right ${
                                    aBetter ? 'text-emerald-400 font-bold' : 'text-slate-200'
                                  }`}
                                >
                                  {row.fmt(row.a)}
                                </td>
                                <td
                                  className={`py-2 px-3 text-right ${
                                    bBetter ? 'text-amber-300 font-bold' : 'text-slate-200'
                                  }`}
                                >
                                  {row.fmt(row.b)}
                                </td>
                                <td className="py-2 px-3 text-right text-slate-400">
                                  {Math.abs(diff) < 1e-6
                                    ? 'Equal'
                                    : `${diff > 0 ? '+' : ''}${diff.toFixed(2)}`}
                                </td>
                              </tr>
                            );
                          });
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
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
            <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-12 text-center space-y-3">
              <div className="text-sm font-bold text-white">
                No Local Single Run Selected for {demId}
              </div>
              <p className="text-xs text-slate-400 max-w-md mx-auto">
                Run a simulation in the Pipeline Studio to generate local matrix and graph artifacts, or switch to the{' '}
                <button
                  onClick={() => setMode('batch')}
                  className="text-indigo-400 underline font-semibold"
                >
                  Batch & Thesis Study Comparison
                </button>{' '}
                mode to explore existing thesis results.
              </p>
            </div>
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
const SingleRunCurveSvg: React.FC<{
  points: Array<{ percent: number; original: number; permuted: number }>;
  comparePoints?: Array<{ percent: number; original: number; permuted: number }>;
  matrixName: string;
}> = ({ points, comparePoints, matrixName }) => {
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
  const filteredCompare = comparePoints?.filter((p) => p.percent <= maxPct) || [];

  const toX = (pct: number) => padL + (pct / maxPct) * plotW;
  const toY = (val: number) => padT + plotH - Math.min(1, Math.max(0, val)) * plotH;

  const origPath = filtered
    .map((p, i) => `${i === 0 ? 'M' : 'L'}${toX(p.percent).toFixed(1)},${toY(p.original).toFixed(1)}`)
    .join(' ');
  const permPath = filtered
    .map((p, i) => `${i === 0 ? 'M' : 'L'}${toX(p.percent).toFixed(1)},${toY(p.permuted).toFixed(1)}`)
    .join(' ');
  const comparePermPath = filteredCompare
    .map((p, i) => `${i === 0 ? 'M' : 'L'}${toX(p.percent).toFixed(1)},${toY(p.permuted).toFixed(1)}`)
    .join(' ');

  return (
    <div className="p-3 rounded-xl bg-slate-950 border border-slate-800">
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs mb-2">
        <span className="font-semibold text-slate-300">
          Fraction of Nonzeros within Diagonal Band (0% – 2% of n)
        </span>
        <div className="flex items-center gap-3 text-[11px]">
          <span className="flex items-center gap-1 text-slate-400">
            <span className="w-2.5 h-0.5 bg-slate-400 inline-block" /> Original {matrixName}
          </span>
          <span className="flex items-center gap-1 text-indigo-400 font-semibold">
            <span className="w-2.5 h-0.5 bg-indigo-400 inline-block" /> Run A Permuted
          </span>
          {filteredCompare.length > 0 && (
            <span className="flex items-center gap-1 text-amber-400 font-semibold">
              <span className="w-2.5 h-0.5 bg-amber-400 inline-block" /> Run B Permuted
            </span>
          )}
        </div>
      </div>
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
            <text x={padL - 6} y={toY(yVal) + 3} textAnchor="end" fontSize="9" fill="#64748b">
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
            fontSize="9"
            fill="#64748b"
          >
            {xVal.toFixed(1)}%
          </text>
        ))}
        <path d={origPath} fill="none" stroke="#94a3b8" strokeWidth="2" />
        <path d={permPath} fill="none" stroke="#6366f1" strokeWidth="2.5" />
        {comparePermPath && (
          <path
            d={comparePermPath}
            fill="none"
            stroke="#f59e0b"
            strokeWidth="2.2"
            strokeDasharray="5 3"
          />
        )}
      </svg>
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
            <text x={padL - 5} y={toY(yVal) + 3} textAnchor="end" fontSize="9" fill="#64748b">
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
            fontSize="9"
            fill="#64748b"
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
          const color = METHOD_COLORS[m] || '#38bdf8';
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
          <span key={m} className="inline-flex items-center gap-1.5 text-[11px] text-slate-300">
            <span
              className="w-2.5 h-2.5 rounded-full"
              style={{ backgroundColor: METHOD_COLORS[m] || '#38bdf8' }}
            />
            {METHOD_LABELS[m] || m}
          </span>
        ))}
      </div>
    </div>
  );
};

