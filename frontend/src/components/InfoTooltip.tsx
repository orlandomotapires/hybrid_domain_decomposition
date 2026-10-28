import React, { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { ArrowUpRight, BookOpen, Info } from 'lucide-react';
import { getWikiTopic } from '../data/wikiKnowledgeBase';

interface InfoTooltipProps {
  topicId: string;
  onOpenWiki?: (topicId: string) => void;
  titleOverride?: string;
  summaryOverride?: string;
  codeKeyOverride?: string;
  formulaOverride?: string;
  className?: string;
}

export const InfoTooltip: React.FC<InfoTooltipProps> = ({
  topicId,
  onOpenWiki,
  titleOverride,
  summaryOverride,
  codeKeyOverride,
  formulaOverride,
  className = '',
}) => {
  const topic = getWikiTopic(topicId);
  const [open, setOpen] = useState(false);
  const [coords, setCoords] = useState<{ top: number; left: number; placement: 'bottom' | 'top' }>({
    top: 0,
    left: 0,
    placement: 'bottom',
  });

  const triggerRef = useRef<HTMLSpanElement | null>(null);
  const closeTimerRef = useRef<number | null>(null);

  const title = titleOverride || topic?.title || topicId;
  const summary =
    summaryOverride ||
    topic?.shortSummary ||
    'Click "More details" to view the complete scientific & parameter reference in the Project Wiki.';
  const codeKey = codeKeyOverride || topic?.codeKey;
  const formula = formulaOverride || topic?.formula;
  const badge = topic?.badge;

  const updatePosition = () => {
    if (!triggerRef.current) return;
    const rect = triggerRef.current.getBoundingClientRect();
    const popoverWidth = 340;
    const estimatedHeight = 220;
    const margin = 12;

    let left = rect.left + rect.width / 2 - popoverWidth / 2;
    if (left < margin) left = margin;
    if (left + popoverWidth > window.innerWidth - margin) {
      left = window.innerWidth - popoverWidth - margin;
    }

    const spaceBelow = window.innerHeight - rect.bottom;
    const placement: 'bottom' | 'top' =
      spaceBelow < estimatedHeight && rect.top > estimatedHeight ? 'top' : 'bottom';

    const top = placement === 'bottom' ? rect.bottom + 8 : rect.top - 8;
    setCoords({ top, left, placement });
  };

  const handleOpen = () => {
    if (closeTimerRef.current) {
      window.clearTimeout(closeTimerRef.current);
      closeTimerRef.current = null;
    }
    updatePosition();
    setOpen(true);
  };

  const handleDelayedClose = () => {
    if (closeTimerRef.current) {
      window.clearTimeout(closeTimerRef.current);
    }
    closeTimerRef.current = window.setTimeout(() => {
      setOpen(false);
    }, 180);
  };

  useEffect(() => {
    if (!open) return;
    const onScrollOrResize = () => updatePosition();
    window.addEventListener('scroll', onScrollOrResize, true);
    window.addEventListener('resize', onScrollOrResize);
    return () => {
      window.removeEventListener('scroll', onScrollOrResize, true);
      window.removeEventListener('resize', onScrollOrResize);
    };
  }, [open]);

  useEffect(() => {
    return () => {
      if (closeTimerRef.current) {
        window.clearTimeout(closeTimerRef.current);
      }
    };
  }, []);

  return (
    <>
      <span
        ref={triggerRef}
        role="button"
        tabIndex={0}
        aria-label={`Information about ${title}`}
        onMouseEnter={handleOpen}
        onMouseLeave={handleDelayedClose}
        onFocus={handleOpen}
        onBlur={handleDelayedClose}
        onClick={(e) => {
          e.stopPropagation();
          e.preventDefault();
          if (open && onOpenWiki) {
            setOpen(false);
            onOpenWiki(topicId);
          } else {
            handleOpen();
          }
        }}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.stopPropagation();
            e.preventDefault();
            handleOpen();
          } else if (e.key === 'Escape') {
            setOpen(false);
          }
        }}
        className={`inline-flex items-center justify-center w-4 h-4 rounded-full bg-indigo-500/15 hover:bg-indigo-500/35 border border-indigo-400/40 text-indigo-300 hover:text-white transition cursor-pointer shrink-0 select-none ${className}`}
      >
        <Info className="w-2.5 h-2.5" />
      </span>

      {open &&
        createPortal(
          <div
            onMouseEnter={handleOpen}
            onMouseLeave={handleDelayedClose}
            onClick={(e) => {
              e.stopPropagation();
            }}
            style={{
              position: 'fixed',
              top: coords.top,
              left: coords.left,
              width: 340,
              transform: coords.placement === 'top' ? 'translateY(-100%)' : undefined,
              zIndex: 9999,
            }}
            className="bg-slate-900/98 backdrop-blur-md border border-indigo-500/50 rounded-xl p-3.5 shadow-2xl shadow-black/80 text-left space-y-2.5 animate-in fade-in duration-100"
          >
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <div className="text-xs font-bold text-white leading-snug break-words">
                  {title}
                </div>
                {codeKey && (
                  <div className="text-[10px] font-mono text-indigo-300 mt-0.5 truncate" title={codeKey}>
                    {codeKey}
                  </div>
                )}
              </div>
              {badge && (
                <span className="px-1.5 py-0.5 text-[9px] font-mono font-semibold rounded bg-indigo-500/20 text-indigo-200 border border-indigo-500/30 shrink-0">
                  {badge}
                </span>
              )}
            </div>

            <p className="text-[11px] text-slate-300 leading-relaxed break-words">
              {summary}
            </p>

            {formula && (
              <div className="px-2.5 py-1.5 rounded-lg bg-slate-950 border border-slate-800 text-[10px] font-mono text-amber-300 overflow-x-auto">
                {formula}
              </div>
            )}

            {onOpenWiki && (
              <div className="pt-1 border-t border-slate-800 flex items-center justify-between">
                <span className="text-[10px] text-slate-400 flex items-center gap-1">
                  <BookOpen className="w-3 h-3 text-indigo-400" />
                  Scientific Wiki Entry
                </span>
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    e.preventDefault();
                    setOpen(false);
                    onOpenWiki(topicId);
                  }}
                  className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-[11px] font-bold bg-indigo-600 hover:bg-indigo-500 text-white shadow transition"
                >
                  More details
                  <ArrowUpRight className="w-3 h-3" />
                </button>
              </div>
            )}
          </div>,
          document.body
        )}
    </>
  );
};

