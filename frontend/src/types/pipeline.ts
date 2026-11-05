export interface MatrixInfo {
  filename: string;
  exists: boolean;
  size_bytes?: number;
  rows?: number | null;
  cols?: number | null;
  nnz?: number | null;
  symmetry?: string | null;
  format_type?: string | null;
  field_type?: string | null;
}

/** A sparse matrix in the shared matrix library (matrices/<id>/). Any square matrix can be permuted. */
export interface LibraryMatrix {
  id: string;
  name: string;
  description?: string | null;
  /** Header of the .mtx file (size, nnz, symmetry). */
  info: MatrixInfo;
  ready: boolean;
  /** rows === cols (required for a symmetric permutation P A Pᵀ). */
  square: boolean;
  /** Simulations whose config points at this matrix. */
  used_by: string[];
  error?: string;
}

export interface SimulationConfig {
  parameters_file_path: string;
  /** Id of the library matrix to partition and permute (a folder in matrices/). */
  input_matrix: string;
  save_output: string[];
}

export interface GeneralParameters {
  dof_per_node: number;
  seed: number;
}

export interface CoarseningParameters {
  coarsen_inferior_limit: number;
  coarsen_superior_limit: number | null;
  max_levels: number;
  weight: string;
  strategy: 'random' | 'sorted' | 'modified' | 'light';
  coarsen_ratio: number;
  max_node_weight?: number | null;
}

export interface QuantumAnnealingParams {
  qubo_balance_lambda: number;
  num_starts: number;
  num_reads: number;
  balance_violation_lambda: number;
  simulated: boolean;
  qpu_region?: string | null;
  qpu_solver_name?: string | null;
  qpu_problem_label?: string | null;
}

export interface QAOAParams {
  qubo_balance_lambda: number;
  num_starts: number;
  num_steps: number;
  num_shots: number;
  balance_violation_lambda: number;
  circuit_depth: number;
  adam_learning_rate?: number | null;
  simulated: boolean;
  qlm_qpu_name?: string | null;
  qlm_job_timeout_seconds?: number | null;
}

export type PartitioningStrategyKey =
  | 'metis_partitioning'
  | 'quantum_annealing'
  | 'quantum_approximation_optimizer';

export interface PartitioningParameters {
  partitioning_strategy: PartitioningStrategyKey;
  common: {
    k_target: number;
    balance_tolerance: number;
  };
  strategies: {
    metis_partitioning?: Record<string, unknown>;
    quantum_annealing?: QuantumAnnealingParams;
    quantum_approximation_optimizer?: QAOAParams;
  };
}

export interface UncoarseningParameters {
  refine_objective: 'cut' | 'cut_balance';
  refine_balance_lambda: number;
  refine_max_passes_per_level: number;
  refine_max_moves_per_pass?: number | null;
  validate_node_weights?: boolean | null;
}

export interface SimulationParameters {
  general_parameters: GeneralParameters;
  coarsening_parameters: CoarseningParameters;
  partitioning_parameters: PartitioningParameters;
  uncoarsening_parameters: UncoarseningParameters;
}

export interface QuantumEstimates {
  partitioning_strategy: string;
  bipartitions_per_start: number;
  simulated?: boolean;
  expected_qpu_submissions?: number;
  expected_qpu_reads?: number;
  expected_qlm_jobs?: number;
  total_circuit_shots?: number;
  warnings: string[];
}

export interface Demonstrator {
  id: string;
  demonstrator_dir: string;
  simulation_config: SimulationConfig;
  simulation_parameters: SimulationParameters;
  active_parameters_file: string;
  preset_files: string[];
  /** The matrix this simulation uses (as saved). */
  matrix: {
    id: string | null;
    name: string | null;
    error?: string;
    info: MatrixInfo;
    ready: boolean;
  };
  runs_count: number;
  latest_run: string | null;
  estimates: QuantumEstimates;
  available_save_outputs: string[];
  error?: string;
}

export interface LogEntry {
  timestamp: string;
  level: 'INFO' | 'VERBOSE' | 'WARNING' | 'ERROR' | string;
  message: string;
}

export interface CoarseningPreviewLevel {
  level: number;
  nodes: number;
  edges: number;
  ratio: number;
  max_node_weight: number;
  accepted: boolean;
  stop_reason: string | null;
}

export interface CoarseningPreviewResponse {
  demonstrator_id: string;
  reachable: boolean;
  final_coarse_nodes: number;
  final_coarse_edges: number;
  accepted_levels_count: number;
  stop_reason: string;
  elapsed_ms: number;
  levels: CoarseningPreviewLevel[];
}

export interface SimulationJob {
  job_id: string;
  job_type: 'single' | 'batch';
  title: string;
  demonstrator_dir?: string | null;
  /** Simulation id (e.g. "simulation_01"); null for batch jobs. */
  demonstrator_id?: string | null;
  /** Raw partitioning strategy key (e.g. "quantum_annealing"). */
  partitioning_strategy?: string | null;
  /** Emulated (true) vs hardware (false); null for METIS / unknown. */
  simulated?: boolean | null;
  /** Requested number of parts. */
  k_target?: number | null;
  status: 'running' | 'completed' | 'failed' | 'cancelled';
  current_stage: string;
  stage_progress: number;
  created_at: string;
  finished_at?: string | null;
  elapsed_sec?: number;
  stage_durations_sec?: Record<string, number>;
  result_dir?: string | null;
  batch_dir?: string | null;
  pid?: number | null;
  exit_code?: number | null;
  error_message?: string | null;
  telemetry: {
    initial_nodes?: number;
    initial_edges?: number;
    coarse_nodes?: number;
    coarse_edges?: number;
    coarsening_levels?: number;
    coarse_parts?: number;
    batch_total?: number;
    batch_index?: number;
    batch_case?: string;
    batch_done?: number;
    batch_failed?: number;
  };
  log_count: number;
  logs?: LogEntry[];
}

export interface MatrixKPI {
  n: number | null;
  nnz_original: number | null;
  nnz_permuted: number | null;
  bandwidth_original: number | null;
  bandwidth_permuted: number | null;
  bandwidth_reduction_pct: number | null;
  avg_bandwidth_original: number | null;
  avg_bandwidth_permuted: number | null;
  nb2_original: number | null;
  nb2_permuted: number | null;
  nb2_reduction_pct: number | null;
  frac_0_1pct_original: number | null;
  frac_0_1pct_permuted: number | null;
  frac_0_4pct_original: number | null;
  frac_0_4pct_permuted: number | null;
  frac_0_7pct_original: number | null;
  frac_0_7pct_permuted: number | null;
  frac_1_0pct_original: number | null;
  frac_1_0pct_permuted: number | null;
  permutation_check?: {
    samples?: number;
    seed?: number;
    tol?: number;
    mismatches?: number;
    max_abs_err?: number;
  };
}

