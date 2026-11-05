import React from 'react';
import { SimulationParameters } from '../../types/pipeline';
import { InfoTooltip } from '../InfoTooltip';
import { StageCard, StageCardControl } from './StageCard';

interface StageRefinementProps {
  /** Error state + collapse wiring for the stage card shell. */
  card: StageCardControl;
  onOpenWiki: (topicId: string) => void;
  parameters: SimulationParameters;
  onParametersChange: (next: SimulationParameters) => void;
}

/* STAGE 4: UNCOARSENING & REFINEMENT */
export const StageRefinement: React.FC<StageRefinementProps> = ({
  card,
  onOpenWiki,
  parameters,
  onParametersChange,
}) => {
  const up = parameters.uncoarsening_parameters;

  return (
    <StageCard
      n={4}
      title="Refinement"
      subtitle="Project back and polish the cut"
      wikiId="stage-4"
      onOpenWiki={onOpenWiki}
      {...card}
    >
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-5">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5">
          <button
            type="button"
            aria-pressed={up.refine_objective === 'cut'}
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
                ? 'bg-indigo-950/60 border-indigo-500 ring-2 ring-indigo-500/30'
                : 'bg-slate-950/70 border-slate-800 hover:border-slate-700'
            }`}
          >
            <div className="min-w-0">
              <div className="font-bold text-sm text-white truncate">Cut</div>
              <div className="text-xs text-slate-400 mt-0.5 truncate">
                Minimize edges cut
              </div>
            </div>
            <InfoTooltip topicId="method-refine-cut" onOpenWiki={onOpenWiki} />
          </button>

          <button
            type="button"
            aria-pressed={up.refine_objective === 'cut_balance'}
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
                ? 'bg-indigo-950/60 border-indigo-500 ring-2 ring-indigo-500/30'
                : 'bg-slate-950/70 border-slate-800 hover:border-slate-700'
            }`}
          >
            <div className="min-w-0">
              <div className="font-bold text-sm text-white truncate">Cut + Balance</div>
              <div className="text-xs text-slate-400 mt-0.5 truncate">
                Trade cut for balance
              </div>
            </div>
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
    </StageCard>
  );
};
