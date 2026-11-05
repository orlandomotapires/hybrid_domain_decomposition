/**
 * Rough capacity limits for quantum partitioning backends. One QUBO variable (qubit)
 * per coarse-graph node, so the coarse graph must fit the backend.
 */

/** Largest dense clique a D-Wave Advantage QPU embeds reliably. */
export const DWAVE_CLIQUE_LIMIT = 175;

/** Practical statevector limit for local QAOA emulation. */
export const QAOA_EMULATED_QUBIT_LIMIT = 18;

/** Fallback when the QLM QPU name doesn't reveal its size. */
const QLM_DEFAULT_QUBITS = 10;

/** Infer qubit count from QLM QPU names like "qat.qpus:Jiqcer5QPU" or "qat.qpus:QSolidQPU10". */
export function qlmQubitLimit(qpuName?: string | null): number {
  const m = (qpuName || '').match(/(\d+)QPU|QPU(\d+)/i);
  const n = m ? parseInt(m[1] || m[2], 10) : NaN;
  return Number.isFinite(n) && n > 0 ? n : QLM_DEFAULT_QUBITS;
}

export interface CapacityLimit {
  limit: number;
  what: string;
}

/** Capacity limit for a strategy, or null when classical/unbounded (METIS, emulated annealing). */
export function capacityFor(
  strategy: string,
  params: { simulated?: boolean; qlm_qpu_name?: string | null } | undefined
): CapacityLimit | null {
  const simulated = params?.simulated ?? true;
  if (strategy === 'quantum_annealing' && !simulated) {
    return { limit: DWAVE_CLIQUE_LIMIT, what: 'D-Wave clique embedding' };
  }
  if (strategy === 'quantum_approximation_optimizer') {
    if (simulated) return { limit: QAOA_EMULATED_QUBIT_LIMIT, what: 'statevector emulation' };
    const limit = qlmQubitLimit(params?.qlm_qpu_name);
    return { limit, what: `QLM QPU (${limit} qubits)` };
  }
  return null;
}

/** True when the strategy runs on real, remote quantum hardware. */
export function isRemoteHardware(strategy: string, params: { simulated?: boolean } | undefined): boolean {
  return strategy !== 'metis_partitioning' && params?.simulated === false;
}

/** Largest coarse graph a [inferior, superior] range can produce. */
export function maxCoarseNodes(inferior: number, superior: number | null | undefined): number {
  return superior ?? inferior;
}
