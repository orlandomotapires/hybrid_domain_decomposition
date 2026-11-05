import React, { useState } from 'react';
import { AlertTriangle, CheckCircle2, Library, Trash2, Upload, X } from 'lucide-react';
import { Demonstrator, LibraryMatrix, MatrixInfo, SimulationConfig, SimulationParameters } from '../../types/pipeline';
import { InfoTooltip } from '../InfoTooltip';
import { StageCard, StageCardControl } from './StageCard';

type MeshPreset = 'small' | 'medium' | 'large';

/** Synthetic FEM meshes the backend can generate (node count of the resulting graph). */
const MESH_PRESETS: Array<{ preset: MeshPreset; nodes: number; label: string }> = [
  { preset: 'small', nodes: 240, label: 'Demo matrix (240 nodes)' },
  { preset: 'large', nodes: 600, label: 'Demo matrix (600 nodes)' },
];

interface StageInputMatricesProps {
  /** Error state + collapse wiring for the stage card shell. */
  card: StageCardControl;
  onOpenWiki: (topicId: string) => void;
  demonstrator: Demonstrator;
  config: SimulationConfig;
  parameters: SimulationParameters;
  /** Every matrix in the shared library (matrices/<id>/). */
  matrixLibrary: LibraryMatrix[];
  /** Graph node count inferred from matrix rows / block size. */
  inferredGraphNodes: number | null;
  matrixRows: number | null | undefined;
  /** Matrix rows are not divisible by the block size. */
  blockMismatch: boolean;
  generatingMatrices: boolean;
  onGenerateMatrices: (preset: MeshPreset) => Promise<void>;
  onSelectMatrix: (matrixId: string) => void;
  onUploadMatrix: (name: string, file: File) => Promise<boolean>;
  onDeleteLibraryMatrix: (matrixId: string) => Promise<void>;
  onParametersChange: (next: SimulationParameters) => void;
  onSelectPreset: (filename: string) => void | Promise<void>;
  onDeletePreset: (filename: string) => Promise<void>;
}

const shape = (m: MatrixInfo) =>
  m.exists && m.rows != null ? `${m.rows.toLocaleString()} × ${(m.cols ?? m.rows).toLocaleString()}` : 'missing';

/* STAGE 1: INPUT MATRIX & GRAPH CONSTRUCTION */
export const StageInputMatrices: React.FC<StageInputMatricesProps> = ({
  card,
  onOpenWiki,
  demonstrator,
  config,
  parameters,
  matrixLibrary,
  inferredGraphNodes,
  matrixRows,
  blockMismatch,
  generatingMatrices,
  onGenerateMatrices,
  onSelectMatrix,
  onUploadMatrix,
  onDeleteLibraryMatrix,
  onParametersChange,
  onSelectPreset,
  onDeletePreset,
}) => {
  const gp = parameters.general_parameters;
  const selectedId = config.input_matrix || null;
  const selectedMissing = !!selectedId && !matrixLibrary.some((m) => m.id === selectedId);

  const [showUpload, setShowUpload] = useState(false);
  const [uploadName, setUploadName] = useState('');
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);

  const resetUpload = () => {
    setShowUpload(false);
    setUploadName('');
    setUploadFile(null);
  };

  const submitUpload = async () => {
    if (!uploadName.trim() || !uploadFile) return;
    setUploading(true);
    try {
      if (await onUploadMatrix(uploadName.trim(), uploadFile)) resetUpload();
    } finally {
      setUploading(false);
    }
  };

  return (
    <StageCard
      n={1}
      title="Input Matrix"
      subtitle="Any square sparse matrix from the shared library"
      wikiId="stage-1"
      onOpenWiki={onOpenWiki}
      {...card}
      headerRight={
        <>
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
        </>
      }
    >
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5 mt-5">
        {/* Matrix picker */}
        <div className="lg:col-span-2 space-y-3 min-w-0">
          <div className="flex items-center justify-between gap-2">
            <span className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-indigo-400">
              <Library className="w-3.5 h-3.5" />
              Matrix
              <InfoTooltip topicId="param-matrix" onOpenWiki={onOpenWiki} />
            </span>
            <span className="text-xs text-slate-500">
              {matrixLibrary.length} in library · <code className="font-mono">matrices/</code>
            </span>
          </div>

          {selectedMissing && (
            <div className="p-3 rounded-xl bg-amber-950/40 border border-amber-500/40 flex items-center gap-2 text-xs text-amber-200">
              <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0" />
              Matrix <code className="font-mono">{selectedId}</code> is not in the library. Pick another one.
            </div>
          )}

          <div role="radiogroup" aria-label="Matrix" className="space-y-1.5 max-h-72 overflow-y-auto pr-1">
            {matrixLibrary.length === 0 && (
              <div className="p-4 rounded-xl border border-dashed border-slate-700 text-xs text-slate-400 text-center">
                The library is empty. Upload a .mtx matrix or generate a demo matrix below.
              </div>
            )}
            {matrixLibrary.map((m) => {
              const active = m.id === selectedId;
              const usedElsewhere = m.used_by.filter((u) => u !== demonstrator.id);
              const problem = !m.ready ? 'file missing' : !m.square ? 'not square' : null;
              return (
                <div
                  key={m.id}
                  className={`flex items-center gap-3 p-3 rounded-xl border transition ${
                    active
                      ? 'bg-indigo-950/50 border-indigo-500'
                      : 'bg-slate-950/70 border-slate-800 hover:border-slate-600'
                  }`}
                >
                  <button
                    type="button"
                    role="radio"
                    aria-checked={active}
                    onClick={() => onSelectMatrix(m.id)}
                    className="flex-1 min-w-0 text-left flex items-start gap-3 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 rounded-lg"
                  >
                    <span
                      className={`mt-0.5 w-4 h-4 rounded-full border-2 shrink-0 flex items-center justify-center ${
                        active ? 'border-indigo-400' : 'border-slate-600'
                      }`}
                      aria-hidden
                    >
                      {active && <span className="w-2 h-2 rounded-full bg-indigo-400" />}
                    </span>
                    <span className="min-w-0 space-y-0.5">
                      <span className="flex items-center gap-2 min-w-0">
                        <span className="text-xs font-semibold text-slate-100 truncate">{m.name}</span>
                        {problem ? (
                          <span className="inline-flex items-center gap-1 text-xs text-amber-300 shrink-0">
                            <AlertTriangle className="w-3 h-3" /> {problem}
                          </span>
                        ) : (
                          <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0" aria-label="Ready" />
                        )}
                      </span>
                      <span className="block text-xs font-mono text-slate-500 truncate">{m.id}</span>
                      <span className="flex flex-wrap gap-x-3 text-xs text-slate-400">
                        <span title={m.info.filename}>
                          <span className="font-mono text-slate-300">{shape(m.info)}</span>
                          {m.info.nnz != null && <> · nnz {m.info.nnz.toLocaleString()}</>}
                          {m.info.symmetry && <> · {m.info.symmetry}</>}
                        </span>
                        {usedElsewhere.length > 0 && <span>also used by {usedElsewhere.join(', ')}</span>}
                      </span>
                    </span>
                  </button>
                  <button
                    type="button"
                    disabled={m.used_by.length > 0 || active}
                    onClick={() => onDeleteLibraryMatrix(m.id)}
                    className="p-1.5 rounded-lg text-slate-500 hover:text-rose-400 hover:bg-rose-950/40 transition disabled:opacity-30 disabled:hover:text-slate-500 disabled:hover:bg-transparent shrink-0"
                    title={m.used_by.length > 0 || active ? 'In use by a simulation — cannot delete' : `Delete ${m.id} from the library`}
                    aria-label={`Delete matrix ${m.id}`}
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              );
            })}
          </div>

          {blockMismatch && (
            <div className="p-3 rounded-xl bg-amber-950/40 border border-amber-500/40 flex items-center gap-2 text-xs text-amber-200">
              <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0" />
              The matrix has {matrixRows?.toLocaleString()} rows, which is not divisible by the block size{' '}
              {gp.dof_per_node}. Use a block size that divides it (1 always works).
            </div>
          )}

          {/* Add to the library: upload a pair or generate a synthetic FEM mesh */}
          {showUpload ? (
            <div className="p-3.5 rounded-xl bg-slate-950/80 border border-slate-700 space-y-2.5">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-slate-200">Upload a matrix</span>
                <button type="button" onClick={resetUpload} aria-label="Cancel upload" className="text-slate-500 hover:text-slate-200">
                  <X className="w-4 h-4" />
                </button>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                <label className="text-xs text-slate-400 space-y-1">
                  <span>Name</span>
                  <input
                    type="text"
                    value={uploadName}
                    onChange={(e) => setUploadName(e.target.value)}
                    placeholder="e.g. turbine_blade_v2"
                    className="w-full bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs font-mono text-white"
                  />
                </label>
                <label className="text-xs text-slate-400 space-y-1 min-w-0">
                  <span>Matrix Market file (.mtx)</span>
                  <span className="flex items-center gap-1.5 w-full bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1.5 cursor-pointer hover:border-slate-500">
                    <Upload className="w-3.5 h-3.5 shrink-0" />
                    <span className="truncate font-mono text-slate-200">{uploadFile ? uploadFile.name : 'Choose file…'}</span>
                    <input
                      type="file"
                      accept=".mtx"
                      className="hidden"
                      onChange={(e) => {
                        const f = e.target.files?.[0] || null;
                        setUploadFile(f);
                        if (f && !uploadName.trim()) setUploadName(f.name.replace(/\.mtx$/i, ''));
                        e.target.value = '';
                      }}
                    />
                  </span>
                </label>
              </div>
              <div className="flex justify-end">
                <button
                  type="button"
                  disabled={uploading || !uploadName.trim() || !uploadFile}
                  onClick={submitUpload}
                  className="px-3.5 py-1.5 rounded-lg text-xs font-semibold bg-indigo-600 hover:bg-indigo-500 text-white transition disabled:opacity-50"
                >
                  {uploading ? 'Uploading…' : 'Add to library & select'}
                </button>
              </div>
            </div>
          ) : (
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs text-slate-400">Add to library:</span>
              <InfoTooltip topicId="stage-1-mtx-tools" onOpenWiki={onOpenWiki} />
              <button
                type="button"
                onClick={() => setShowUpload(true)}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 transition"
              >
                <Upload className="w-3.5 h-3.5 text-slate-400" />
                Upload .mtx
              </button>
              {MESH_PRESETS.map((mesh) => (
                <button
                  key={mesh.preset}
                  type="button"
                  disabled={generatingMatrices}
                  onClick={() => onGenerateMatrices(mesh.preset)}
                  className="px-3 py-1.5 rounded-lg text-xs font-medium bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 transition disabled:opacity-50"
                  title={`Generate a synthetic ${mesh.nodes}-node FEM test matrix as a new library matrix and select it`}
                >
                  {generatingMatrices ? 'Generating…' : mesh.label}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* General Parameters */}
        <div className="p-4 rounded-xl bg-slate-950/80 border border-slate-800 space-y-4 min-w-0 overflow-hidden">
          <div>
            <div className="flex items-center justify-between gap-2 mb-1.5">
              <label className="text-xs font-medium text-slate-300 flex items-center gap-1.5">
                <span>Block size (rows per node)</span>
                <InfoTooltip topicId="param-dof-per-node" onOpenWiki={onOpenWiki} />
              </label>
              {inferredGraphNodes !== null && (
                <span className="text-xs font-mono text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded">
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
    </StageCard>
  );
};
