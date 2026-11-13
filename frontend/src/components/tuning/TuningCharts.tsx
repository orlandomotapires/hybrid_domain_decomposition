import React, { useState } from 'react';
import { ObjectiveKey, StudyTrial } from '../../types/tuning';

const W = 600;
const H = 260;
const PAD = { l: 52, r: 16, t: 14, b: 34 };
// Data colours: one accent series, one recessive series (text never uses them).
const ACCENT = '#818cf8';
const MUTED = '#64748b';

function ticks(min: number, max: number, count = 4): number[] {
  if (!isFinite(min) || !isFinite(max)) return [];
  if (min === max) return [min];
  const step = (max - min) / count;
  return Array.from({ length: count + 1 }, (_, i) => min + i * step);
}

function fmt(v: number): string {
  if (v === 0) return '0';
  const a = Math.abs(v);
  if (a >= 1000 || a < 0.01) return v.toExponential(1);
  return v.toPrecision(3).replace(/\.?0+$/, '');
}

function Axes({ xs, ys, sx, sy, xLabel, yLabel }: {
  xs: number[]; ys: number[]; sx: (v: number) => number; sy: (v: number) => number; xLabel: string; yLabel: string;
}) {
  return (
    <g className="text-slate-500" fontSize={10}>
      {ys.map((v) => (
        <g key={`y${v}`}>
          <line x1={PAD.l} x2={W - PAD.r} y1={sy(v)} y2={sy(v)} stroke="currentColor" strokeOpacity={0.18} />
          <text x={PAD.l - 6} y={sy(v) + 3} textAnchor="end" fill="currentColor">{fmt(v)}</text>
        </g>
      ))}
      {xs.map((v) => (
        <text key={`x${v}`} x={sx(v)} y={H - PAD.b + 14} textAnchor="middle" fill="currentColor">{fmt(v)}</text>
      ))}
      <text x={(PAD.l + W - PAD.r) / 2} y={H - 4} textAnchor="middle" fill="currentColor">{xLabel}</text>
      <text x={12} y={(PAD.t + H - PAD.b) / 2} textAnchor="middle" fill="currentColor"
        transform={`rotate(-90 12 ${(PAD.t + H - PAD.b) / 2})`}>{yLabel}</text>
    </g>
  );
}

function Legend({ items }: { items: Array<{ label: string; color: string; ring?: boolean }> }) {
  return (
    <div className="flex flex-wrap gap-3 text-[11px] text-slate-400">
      {items.map((it) => (
        <span key={it.label} className="inline-flex items-center gap-1.5">
          <span className="inline-block w-2.5 h-2.5 rounded-full"
            style={{ background: it.ring ? 'transparent' : it.color, boxShadow: it.ring ? `0 0 0 2px ${it.color}` : undefined }} />
          {it.label}
        </span>
      ))}
    </div>
  );
}

/** Score per trial (dots) and best-so-far (line) for single-objective / weighted studies. */
export const ConvergenceChart: React.FC<{ trials: StudyTrial[]; onSelect?: (n: number) => void }> = ({ trials, onSelect }) => {
  const points = trials.map((t, i) => ({ i: i + 1, t, y: t.status === 'ok' ? t.score : null }));
  const ok = points.filter((p) => p.y != null) as Array<{ i: number; t: StudyTrial; y: number }>;
  if (ok.length === 0) return <p className="text-xs text-slate-500">No successful trial yet.</p>;
  let best = Infinity;
  const bestLine = points.map((p) => {
    if (p.y != null) best = Math.min(best, p.y);
    return { i: p.i, y: isFinite(best) ? best : null };
  }).filter((p) => p.y != null) as Array<{ i: number; y: number }>;
  const yMin = Math.min(...ok.map((p) => p.y));
  const yMax = Math.max(...ok.map((p) => p.y));
  const pad = (yMax - yMin) * 0.08 || Math.abs(yMax) * 0.1 || 1;
  const lo = yMin >= 0 ? Math.max(0, yMin - pad) : yMin - pad, hi = yMax + pad;
  const n = Math.max(points.length, 2);
  const sx = (v: number) => PAD.l + ((v - 1) / (n - 1)) * (W - PAD.l - PAD.r);
  const sy = (v: number) => PAD.t + (1 - (v - lo) / (hi - lo)) * (H - PAD.t - PAD.b);
  const xs = ticks(1, n, Math.min(5, n - 1)).map(Math.round);
  return (
    <div className="space-y-2">
      <Legend items={[{ label: 'Trial score', color: MUTED }, { label: 'Best so far', color: ACCENT }]} />
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto" role="img" aria-label="Objective score per trial and best so far">
        <Axes xs={Array.from(new Set(xs))} ys={ticks(lo, hi)} sx={sx} sy={sy} xLabel="Trial" yLabel="Score (lower is better)" />
        <polyline fill="none" stroke={ACCENT} strokeWidth={2} strokeLinejoin="round"
          points={bestLine.map((p) => `${sx(p.i)},${sy(p.y)}`).join(' ')} />
        {ok.map((p) => (
          <g key={p.t.number} onClick={() => onSelect?.(p.t.number)} className="cursor-pointer">
            <circle cx={sx(p.i)} cy={sy(p.y)} r={9} fill="transparent" />
            <circle cx={sx(p.i)} cy={sy(p.y)} r={4} fill={MUTED} stroke="var(--chart-surface, #0f172a)" strokeWidth={2} />
            <title>{`Trial #${p.t.number}: score ${fmt(p.y)}${p.t.values ? '\n' + Object.entries(p.t.values).map(([k, v]) => `${k} = ${fmt(v)}`).join('\n') : ''}`}</title>
          </g>
        ))}
      </svg>
    </div>
  );
};

/** Two objectives of a Pareto study; front points highlighted, knee ringed. */
export const ParetoChart: React.FC<{
  trials: StudyTrial[];
  objectives: ObjectiveKey[];
  labels: Record<string, string>;
  front: number[];
  best?: number;
  onSelect?: (n: number) => void;
}> = ({ trials, objectives, labels, front, best, onSelect }) => {
  const [xKey, setXKey] = useState<ObjectiveKey>(objectives[0]);
  const [yKey, setYKey] = useState<ObjectiveKey>(objectives[1] || objectives[0]);
  const ok = trials.filter((t) => t.status === 'ok' && t.values);
  if (ok.length === 0) return <p className="text-xs text-slate-500">No successful trial yet.</p>;
  const frontSet = new Set(front);
  const xv = ok.map((t) => t.values![xKey]);
  const yv = ok.map((t) => t.values![yKey]);
  const span = (a: number[]) => {
    const mn = Math.min(...a), mx = Math.max(...a);
    const p = (mx - mn) * 0.08 || Math.abs(mx) * 0.1 || 1;
    // Objectives are non-negative: never pad the axis below zero.
    return [mn >= 0 ? Math.max(0, mn - p) : mn - p, mx + p];
  };
  const [x0, x1] = span(xv);
  const [y0, y1] = span(yv);
  const sx = (v: number) => PAD.l + ((v - x0) / (x1 - x0)) * (W - PAD.l - PAD.r);
  const sy = (v: number) => PAD.t + (1 - (v - y0) / (y1 - y0)) * (H - PAD.t - PAD.b);
  const ordered = [...ok].sort((a, b) => Number(frontSet.has(a.number)) - Number(frontSet.has(b.number)));
  const select = (value: ObjectiveKey, set: (k: ObjectiveKey) => void) => (
    <select value={value} onChange={(e) => set(e.target.value as ObjectiveKey)}
      className="bg-slate-950 border border-slate-700 rounded-lg px-2 py-1 text-[11px] text-slate-200">
      {objectives.map((o) => <option key={o} value={o}>{labels[o] || o}</option>)}
    </select>
  );
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Legend items={[
          { label: 'Pareto front', color: ACCENT },
          { label: 'Dominated', color: MUTED },
          { label: 'Selected (knee)', color: '#e2e8f0', ring: true },
        ]} />
        {objectives.length > 2 && (
          <div className="flex items-center gap-1.5 text-[11px] text-slate-400">x {select(xKey, setXKey)} y {select(yKey, setYKey)}</div>
        )}
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto" role="img" aria-label="Pareto front of the study">
        <Axes xs={ticks(x0, x1)} ys={ticks(y0, y1)} sx={sx} sy={sy} xLabel={labels[xKey] || xKey} yLabel={labels[yKey] || yKey} />
        {ordered.map((t) => {
          const onFront = frontSet.has(t.number);
          const cx = sx(t.values![xKey]), cy = sy(t.values![yKey]);
          return (
            <g key={t.number} onClick={() => onSelect?.(t.number)} className="cursor-pointer">
              <circle cx={cx} cy={cy} r={10} fill="transparent" />
              {t.number === best && <circle cx={cx} cy={cy} r={8} fill="none" stroke="#e2e8f0" strokeWidth={2} />}
              <circle cx={cx} cy={cy} r={onFront ? 5 : 4} fill={onFront ? ACCENT : MUTED}
                stroke="var(--chart-surface, #0f172a)" strokeWidth={2} />
              <title>{`Trial #${t.number}${onFront ? ' (Pareto)' : ''}\n` +
                objectives.map((o) => `${labels[o] || o} = ${fmt(t.values![o])}`).join('\n')}</title>
            </g>
          );
        })}
      </svg>
    </div>
  );
};
