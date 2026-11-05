import { CoarseningParameters, PartitioningStrategyKey } from '../../types/pipeline';
import { METHOD_LABELS, MethodKey } from '../../lib/labels';

export const COARSENING_STRATEGIES: Array<{
  key: CoarseningParameters['strategy'];
  wikiId: string;
  title: string;
  hint: string;
}> = [
  {
    key: 'random',
    wikiId: 'method-hem-random',
    title: 'Random HEM',
    hint: 'Random visiting order',
  },
  {
    key: 'sorted',
    wikiId: 'method-hem-sorted',
    title: 'Sorted HEM (SHEM)',
    hint: 'Heaviest edges first',
  },
  {
    key: 'modified',
    wikiId: 'method-hem-modified',
    title: 'Modified HEM (MHEM)',
    hint: 'Balances node weights',
  },
  {
    key: 'light',
    wikiId: 'method-hem-light',
    title: 'Light-Edge Matching',
    hint: 'Prefers light edges',
  },
];

export const COARSENING_SCALE_PRESETS = [
  {
    key: 'small',
    label: 'Small (4–5)',
    inferior: 4,
    superior: 5,
    desc: 'NISQ Gate-Based QAOA & Hardware scale',
  },
  {
    key: 'medium',
    label: 'Medium (100–175)',
    inferior: 100,
    superior: 175,
    desc: 'D-Wave Advantage Clique QUBO scale',
  },
  {
    key: 'big',
    label: 'Big (1500–2500)',
    inferior: 1500,
    superior: 2500,
    desc: 'Classical METIS & Emulated Annealing scale',
  },
];

export const PARTITIONING_METHODS: Array<{
  strategy: PartitioningStrategyKey;
  simulated?: boolean;
  id: MethodKey;
  wikiId: string;
  title: string;
  subtitle: string;
  category: 'Classical' | 'Quantum Hardware' | 'Quantum Emulated';
}> = [
  {
    strategy: 'metis_partitioning',
    id: 'metis',
    wikiId: 'method-metis',
    title: METHOD_LABELS.metis,
    subtitle: 'Classical baseline',
    category: 'Classical',
  },
  {
    strategy: 'quantum_annealing',
    simulated: true,
    id: 'qa_emulated',
    wikiId: 'method-qa-emulated',
    title: METHOD_LABELS.qa_emulated,
    subtitle: 'Local annealing simulator',
    category: 'Quantum Emulated',
  },
  {
    strategy: 'quantum_annealing',
    simulated: false,
    id: 'qa_hardware',
    wikiId: 'method-qa-hardware',
    title: METHOD_LABELS.qa_hardware,
    subtitle: 'D-Wave QPU',
    category: 'Quantum Hardware',
  },
  {
    strategy: 'quantum_approximation_optimizer',
    simulated: true,
    id: 'qaoa_emulated',
    wikiId: 'method-qaoa-emulated',
    title: METHOD_LABELS.qaoa_emulated,
    subtitle: 'PennyLane simulator',
    category: 'Quantum Emulated',
  },
  {
    strategy: 'quantum_approximation_optimizer',
    simulated: false,
    id: 'qaoa_hardware',
    wikiId: 'method-qaoa-hardware',
    title: METHOD_LABELS.qaoa_hardware,
    subtitle: 'QLM gate-based QPU',
    category: 'Quantum Hardware',
  },
];

export const SAVE_OUTPUT_LABELS: Record<
  string,
  { title: string; hint: string; file: string; wikiId: string }
> = {
  coarsened_graph: {
    title: 'Coarsened Graph Matrix',
    hint: 'Graph used for partitioning',
    file: 'coarsened_graph.mtx',
    wikiId: 'output-coarsened-graph',
  },
  matrix_permuted: {
    title: 'Permuted Matrix',
    hint: 'P A Pᵀ, reordered by partition',
    file: 'matrix_permuted.mtx',
    wikiId: 'output-matrix-permuted',
  },
  permutation: {
    title: 'Permutation Vector',
    hint: 'Reorder vector',
    file: 'permutation.txt',
    wikiId: 'output-permutation',
  },
  run_metrics: {
    title: 'Structural & Bandwidth Metrics',
    hint: 'Needed for Results plots',
    file: 'run_metrics.json / .txt',
    wikiId: 'output-run-metrics',
  },
  run_simulation_parameters: {
    title: 'Simulation Parameters Snapshot',
    hint: 'Exact parameters used',
    file: 'run_simulation_parameters.json',
    wikiId: 'output-run-simulation-parameters',
  },
};
