import React, { useEffect, useState } from 'react';
import { AlertTriangle, CheckCircle2, RefreshCw } from 'lucide-react';
import { api } from '../../api/client';
import {
  CoarseningPreviewResponse,
  Demonstrator,
  SimulationParameters,
} from '../../types/pipeline';
import { COARSENING_SCALE_PRESETS, COARSENING_STRATEGIES } from './constants';
import { InfoTooltip } from '../InfoTooltip';
import { StageCard, StageCardControl } from './StageCard';

/** Stored value meaning "no limit" (matches existing configs that use 1e18). */
const NO_LIMIT_NODE_WEIGHT = 1e18;
/** Anything this large is treated as "no limit" when displayed. */
const NO_LIMIT_THRESHOLD = 1e12;

export interface CoarseningPreviewState {
  coarseningPreview: CoarseningPreviewResponse | null;
  previewingCoarsening: boolean;
  previewError: string | null;
  handleRunCoarseningPreview: () => Promise<void>;
}

/**
 * Dry-Run Coarsening Trajectory Preview State.
 * Called from PipelineStudio (not from StageCoarsening) so the preview survives the stage card
 * being hidden/shown via the flowchart, exactly as before the split.
 */
export const useCoarseningPreview = (
  demonstratorId: string,
  parameters: SimulationParameters,
  /** Matrix being edited (possibly unsaved); the preview runs on it. */
  matrixId?: string | null
): CoarseningPreviewState => {
  const [coarseningPreview, setCoarseningPreview] = useState<CoarseningPreviewResponse | null>(null);
  const [previewingCoarsening, setPreviewingCoarsening] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);

  useEffect(() => {
    setCoarseningPreview(null);
    setPreviewError(null);
  }, [demonstratorId, matrixId]);

  const handleRunCoarseningPreview = async () => {
    setPreviewingCoarsening(true);
    setPreviewError(null);
    try {
      const res = await api.previewCoarsening(demonstratorId, parameters, matrixId);
      setCoarseningPreview(res);
    } catch (err: any) {
      setPreviewError(err.message || 'Coarsening preview failed');
    } finally {
      setPreviewingCoarsening(false);
    }
  };

  return { coarseningPreview, previewingCoarsening, previewError, handleRunCoarseningPreview };
};

interface StageCoarseningProps {
  /** Error state + collapse wiring for the stage card shell. */
  card: StageCardControl;
  onOpenWiki: (topicId: string) => void;
  demonstrator: Demonstrator;
  parameters: SimulationParameters;
  onParametersChange: (next: SimulationParameters) => void;
  /** Dry-run coarsening preview state, from useCoarseningPreview(). */
  preview: CoarseningPreviewState;
}

/* STAGE 2: MULTILEVEL COARSENING (HEAVY EDGE MATCHING) */
export const StageCoarsening: React.FC<StageCoarseningProps> = ({
  card,
  onOpenWiki,
  demonstrator,
  parameters,
  onParametersChange,
  preview,
}) => {
  const cp = parameters.coarsening_parameters;
  const { coarseningPreview, previewingCoarsening, previewError, handleRunCoarseningPreview } =
    preview;

  const nodeWeightMode: 'auto' | 'none' | 'custom' =
    cp.max_node_weight == null
      ? 'auto'
      : cp.max_node_weight >= NO_LIMIT_THRESHOLD
      ? 'none'
      : 'custom';

  const setMaxNodeWeight = (value: number | null) =>
    onParametersChange({
      ...parameters,
      coarsening_parameters: { ...cp, max_node_weight: value },
    });

  return (
    <StageCard
      n={2}
      title="Coarsening"
      subtitle="Shrink the graph level by level"
      wikiId="stage-2"
      onOpenWiki={onOpenWiki}
      {...card}
      headerRight={
        <>
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
                  type="button"
                  aria-pressed={isSelected}
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
                      ? 'bg-indigo-600/30 border-indigo-400 text-indigo-100'
                      : 'bg-slate-950 border-slate-800 text-slate-300 hover:border-slate-700'
                  }`}
                  title={preset.desc}
                >
                  {preset.label}
                </button>
              );
            })}
          </div>
        </>
      }
    >
      {/* 4 HEM Strategy Cards */}
      <div className="mt-5">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3.5">
          {COARSENING_STRATEGIES.map((item) => {
            const active = cp.strategy === item.key;
            return (
              <button
                key={item.key}
                type="button"
                aria-pressed={active}
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
                    ? 'bg-indigo-950/60 border-indigo-500 ring-2 ring-indigo-500/30'
                    : 'bg-slate-950/70 border-slate-800 hover:border-slate-700'
                }`}
              >
                <div className="min-w-0">
                  <div className="font-bold text-sm text-white truncate">{item.title}</div>
                  <div className="text-xs text-slate-400 mt-0.5 truncate">{item.hint}</div>
                </div>
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
          <div className="flex gap-1 mb-1.5" role="radiogroup" aria-label="Max node weight mode">
            {(
              [
                { mode: 'auto', label: 'Auto', title: 'Derived from k_target (1.5 × total weight / k)' },
                { mode: 'none', label: 'No limit', title: 'Supernodes may grow without bound' },
                { mode: 'custom', label: 'Custom', title: 'Set an explicit maximum supernode weight' },
              ] as const
            ).map((opt) => (
              <button
                key={opt.mode}
                type="button"
                role="radio"
                aria-checked={nodeWeightMode === opt.mode}
                title={opt.title}
                onClick={() =>
                  setMaxNodeWeight(
                    opt.mode === 'auto'
                      ? null
                      : opt.mode === 'none'
                      ? NO_LIMIT_NODE_WEIGHT
                      : nodeWeightMode === 'custom'
                      ? cp.max_node_weight ?? 100
                      : 100
                  )
                }
                className={`flex-1 px-1.5 py-1 rounded-md text-xs font-semibold border transition ${
                  nodeWeightMode === opt.mode
                    ? 'bg-indigo-600/30 border-indigo-400 text-indigo-100'
                    : 'bg-slate-950 border-slate-700 text-slate-400 hover:text-slate-200'
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
          {nodeWeightMode === 'custom' ? (
            <input
              type="number"
              step="any"
              min={0}
              value={cp.max_node_weight ?? ''}
              aria-label="Maximum supernode weight"
              onChange={(e) => {
                const raw = e.target.value.trim();
                setMaxNodeWeight(raw === '' ? null : parseFloat(raw));
              }}
              className="w-full min-w-0 bg-slate-950 border border-slate-700 rounded-lg px-3 py-1.5 text-sm font-mono text-white"
            />
          ) : (
            <div className="text-xs text-slate-400 leading-snug">
              {nodeWeightMode === 'auto'
                ? 'Computed from k_target at run time'
                : 'Supernodes can grow without bound'}
            </div>
          )}
        </div>
      </div>

      {cp.coarsen_ratio >= 1 && (
        <div className="mt-4 p-3 rounded-xl bg-amber-950/40 border border-amber-500/40 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2 text-xs text-amber-200">
            <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0" />
            <span>
              Coarsen Ratio {cp.coarsen_ratio} turns off the “stop when a level barely shrinks” check, so
              coarsening can keep adding levels that shrink only a few nodes each (up to Max Levels). METIS
              typically uses 0.7–0.85.
            </span>
          </div>
          <button
            type="button"
            onClick={() =>
              onParametersChange({
                ...parameters,
                coarsening_parameters: { ...cp, coarsen_ratio: 0.85 },
              })
            }
            className="px-3 py-1 rounded-lg text-xs font-semibold bg-amber-500 hover:bg-amber-400 text-slate-950 transition shrink-0"
          >
            Use 0.85
          </button>
        </div>
      )}

      {/* Interactive Coarsening Trajectory Preview ("Dry-Run Coarsening") */}
      <div className="mt-5 pt-4 border-t border-slate-800/80 space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2 text-xs text-slate-400">
            <span>Check the coarse graph size before running</span>
            <InfoTooltip topicId="tool-dry-run-coarsening" onOpenWiki={onOpenWiki} />
          </div>
          <button
            type="button"
            disabled={previewingCoarsening || !demonstrator.matrix.info.exists}
            onClick={handleRunCoarseningPreview}
            className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl text-xs font-semibold bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 transition disabled:opacity-50"
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

                <span className="text-xs text-slate-400 bg-slate-900 px-2.5 py-1 rounded-lg border border-slate-800">
                  Stop: <strong className="text-slate-200">{coarseningPreview.stop_reason}</strong>
                </span>
              </div>

              <span className="text-xs font-mono text-slate-500">
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
                        ? 'bg-indigo-950/40 border-indigo-500/50 ring-1 ring-indigo-500/30'
                        : 'bg-slate-900/90 border-slate-800'
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2 mb-1">
                      <span className="font-mono font-bold text-white">G_{lvl.level}</span>
                      <span
                        className={`text-[11px] px-1.5 py-0.2 rounded font-mono ${
                          !lvl.accepted
                            ? 'bg-rose-500/20 text-rose-300'
                            : lvl.level === coarseningPreview.accepted_levels_count
                            ? 'bg-indigo-500/20 text-indigo-200'
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
                    <div className="space-y-0.5 text-xs">
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
    </StageCard>
  );
};
