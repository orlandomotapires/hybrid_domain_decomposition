/**
 * Single source of truth for user-facing names of partitioning methods, so every
 * screen says "QA Emulated" instead of mixing raw keys (quantum_annealing,
 * qa_hardware, metis_partitioning) with friendly labels.
 */

export type MethodKey = 'metis' | 'qa_emulated' | 'qa_hardware' | 'qaoa_emulated' | 'qaoa_hardware';

export const METHOD_LABELS: Record<MethodKey, string> = {
  metis: 'METIS (Classical)',
  qa_emulated: 'Quantum Annealing (Emulated)',
  qa_hardware: 'Quantum Annealing (D-Wave QPU)',
  qaoa_emulated: 'QAOA (Emulated)',
  qaoa_hardware: 'QAOA (QLM Hardware)',
};

export const METHOD_SHORT_LABELS: Record<MethodKey, string> = {
  metis: 'METIS',
  qa_emulated: 'QA Emulated',
  qa_hardware: 'QA D-Wave',
  qaoa_emulated: 'QAOA Emulated',
  qaoa_hardware: 'QAOA QLM',
};

/** Per-method colours — used only for data (charts, method chips), never for chrome. */
export const METHOD_COLORS: Record<MethodKey | 'Original', string> = {
  Original: '#94a3b8',
  metis: '#10b981',
  qa_emulated: '#6366f1',
  qa_hardware: '#a855f7',
  qaoa_emulated: '#06b6d4',
  qaoa_hardware: '#ec4899',
};

/** Map a partitioning strategy + simulated flag to a method key. */
export function methodKey(strategy: string | null | undefined, simulated?: boolean | null): MethodKey {
  if (strategy === 'metis_partitioning' || strategy === 'metis') return 'metis';
  const hw = simulated === false;
  if (strategy === 'quantum_approximation_optimizer' || strategy?.startsWith('qaoa')) {
    return hw || strategy === 'qaoa_hardware' ? 'qaoa_hardware' : 'qaoa_emulated';
  }
  return hw || strategy === 'qa_hardware' ? 'qa_hardware' : 'qa_emulated';
}

/** True if `key` is already a method key (e.g. batch algorithm keys "qa_hardware"). */
export function isMethodKey(key: string): key is MethodKey {
  return key in METHOD_LABELS;
}

/**
 * Friendly label for anything method-like: a method key ("qa_hardware"), a raw strategy
 * ("quantum_annealing", optionally with `simulated`), or an unknown custom key (returned as-is).
 */
export function methodLabel(
  keyOrStrategy: string | null | undefined,
  simulated?: boolean | null,
  short = false
): string {
  if (!keyOrStrategy) return '—';
  const known =
    isMethodKey(keyOrStrategy) ||
    ['metis_partitioning', 'quantum_annealing', 'quantum_approximation_optimizer'].includes(keyOrStrategy);
  if (!known) return keyOrStrategy;
  const k = isMethodKey(keyOrStrategy) ? keyOrStrategy : methodKey(keyOrStrategy, simulated);
  // A bare strategy without the simulated flag: don't claim emulated vs hardware.
  if (!isMethodKey(keyOrStrategy) && simulated == null && k !== 'metis') {
    return keyOrStrategy === 'quantum_annealing' ? 'Quantum Annealing' : 'QAOA';
  }
  return (short ? METHOD_SHORT_LABELS : METHOD_LABELS)[k];
}

export function methodColor(keyOrStrategy: string, simulated?: boolean | null): string {
  if (keyOrStrategy === 'Original') return METHOD_COLORS.Original;
  const k = isMethodKey(keyOrStrategy) ? keyOrStrategy : methodKey(keyOrStrategy, simulated);
  return METHOD_COLORS[k] || '#38bdf8';
}

/** Coarsening scale names used by batch presets. */
export const SCALE_LABELS: Record<string, string> = {
  small: 'Small',
  medium: 'Medium',
  big: 'Big',
};
