import React from 'react';
import { ChevronDown } from 'lucide-react';
import { InfoTooltip } from '../InfoTooltip';

/** Collapse state + error wiring every stage card receives from PipelineStudio. */
export interface StageCardControl {
  /** Whether the backend validation error belongs to this stage (drives the card border). */
  hasError: boolean;
  /** Pre-rendered stage validation banner (or null). */
  errorBanner: React.ReactNode;
  /** Whether the stage body is hidden. */
  collapsed: boolean;
  onToggleCollapsed: () => void;
}

/** DOM id of a stage card, used by the flowchart stepper to scroll to it. */
export const stageDomId = (n: number) => `pipeline-stage-${n}`;

interface StageCardProps extends StageCardControl {
  n: number;
  title: string;
  subtitle: string;
  wikiId: string;
  onOpenWiki: (topicId: string) => void;
  /** Controls shown on the right of the header (hidden while collapsed). */
  headerRight?: React.ReactNode;
  children: React.ReactNode;
}

/** Shared, collapsible shell for the five Pipeline stage cards. */
export const StageCard: React.FC<StageCardProps> = ({
  n,
  title,
  subtitle,
  wikiId,
  onOpenWiki,
  hasError,
  errorBanner,
  collapsed,
  onToggleCollapsed,
  headerRight,
  children,
}) => {
  const bodyId = `${stageDomId(n)}-body`;
  return (
    <section
      id={stageDomId(n)}
      data-stage={n}
      aria-labelledby={`${stageDomId(n)}-title`}
      className={`bg-slate-900/80 border rounded-2xl p-6 shadow-lg overflow-hidden scroll-mt-28 ${
        hasError ? 'border-rose-500/60' : 'border-slate-800'
      }`}
    >
      {errorBanner}
      <div
        className={`flex flex-wrap items-center justify-between gap-4 ${
          collapsed ? '' : 'pb-4 border-b border-slate-800'
        }`}
      >
        <div className="flex items-center gap-2 min-w-0">
          <button
            type="button"
            onClick={onToggleCollapsed}
            aria-expanded={!collapsed}
            aria-controls={bodyId}
            title={collapsed ? `Expand stage ${n}` : `Collapse stage ${n}`}
            className="flex items-center gap-3 min-w-0 text-left rounded-lg -m-1 p-1 hover:bg-slate-800/60 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 transition"
          >
            <ChevronDown
              className={`w-4 h-4 text-slate-400 shrink-0 transition-transform ${
                collapsed ? '-rotate-90' : ''
              }`}
            />
            <span className="w-8 h-8 rounded-xl bg-slate-800 border border-slate-700 flex items-center justify-center text-slate-200 font-bold text-sm shrink-0">
              {n}
            </span>
            <h3 id={`${stageDomId(n)}-title`} className="text-base font-bold text-white truncate">
              {title}
            </h3>
            <span className="text-xs text-slate-400 hidden sm:inline">— {subtitle}</span>
          </button>
          <InfoTooltip topicId={wikiId} onOpenWiki={onOpenWiki} />
        </div>
        {!collapsed && headerRight}
      </div>
      {!collapsed && <div id={bodyId}>{children}</div>}
    </section>
  );
};
