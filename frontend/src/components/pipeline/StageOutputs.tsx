import React from 'react';
import { Demonstrator, SimulationConfig } from '../../types/pipeline';
import { SAVE_OUTPUT_LABELS } from './constants';
import { InfoTooltip } from '../InfoTooltip';
import { StageCard, StageCardControl } from './StageCard';

interface StageOutputsProps {
  /** Error state + collapse wiring for the stage card shell. */
  card: StageCardControl;
  onOpenWiki: (topicId: string) => void;
  demonstrator: Demonstrator;
  config: SimulationConfig;
  onConfigChange: (next: SimulationConfig) => void;
}

/* STAGE 5: MATRIX PERMUTATION & OUTPUT ARTIFACTS */
export const StageOutputs: React.FC<StageOutputsProps> = ({
  card,
  onOpenWiki,
  demonstrator,
  config,
  onConfigChange,
}) => {
  return (
    <StageCard
      n={5}
      title="Outputs"
      subtitle="Files written after each run"
      wikiId="stage-5"
      onOpenWiki={onOpenWiki}
      {...card}
      headerRight={
        <>
          <button
            type="button"
            onClick={() =>
              onConfigChange({
                ...config,
                save_output: [...demonstrator.available_save_outputs],
              })
            }
            className="text-xs text-indigo-400 hover:text-indigo-300 font-medium"
          >
            Select All
          </button>
        </>
      }
    >
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3.5 mt-5">
        {demonstrator.available_save_outputs.map((key) => {
          const checked = config.save_output.includes(key);
          const meta = SAVE_OUTPUT_LABELS[key] || {
            title: key,
            hint: key,
            file: key,
            wikiId: 'stage-5',
          };
          return (
            <label
              key={key}
              title={meta.file}
              className={`cursor-pointer p-3.5 rounded-xl border transition flex items-center justify-between gap-3 min-w-0 overflow-hidden ${
                checked
                  ? 'bg-slate-950 border-indigo-500/60'
                  : 'bg-slate-950/40 border-slate-800 opacity-70 hover:opacity-100'
              }`}
            >
              <div className="flex items-center gap-3 min-w-0">
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={(e) => {
                    const next = e.target.checked
                      ? [...config.save_output, key]
                      : config.save_output.filter((item) => item !== key);
                    onConfigChange({ ...config, save_output: next });
                  }}
                  className="rounded border-slate-700 bg-slate-900 text-indigo-600 focus:ring-indigo-500 shrink-0"
                />
                <div className="min-w-0">
                  <div className="text-xs font-bold text-white truncate">{meta.title}</div>
                  <div className="text-xs text-slate-400 truncate">{meta.hint}</div>
                </div>
              </div>
              <InfoTooltip topicId={meta.wikiId} onOpenWiki={onOpenWiki} />
            </label>
          );
        })}
      </div>
    </StageCard>
  );
};
