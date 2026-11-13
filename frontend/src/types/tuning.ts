import { SimulationJob, SimulationParameters } from './pipeline';

export type ObjectiveKey = 'edge_cut' | 'imbalance' | 'band_quality' | 'bandwidth' | 'time';

export interface ObjectiveMeta {
  key: ObjectiveKey;
  label: string;
  description: string;
}

export interface SamplerMeta {
  key: string;
  label: string;
  description: string;
}

export interface TunableParameterMeta {
  key: string;
  label: string;
  group: string;
  type: 'int' | 'float' | 'categorical';
  choices?: string[];
  low?: number;
  high?: number;
  log?: boolean;
  free: boolean;
  when?: string;
  virtual: boolean;
}

export interface TuningMeta {
  objectives: ObjectiveMeta[];
  samplers: SamplerMeta[];
  parameters: TunableParameterMeta[];
}

export interface SearchSpaceEntry {
  free: boolean;
  low?: number;
  high?: number;
  log?: boolean;
  choices?: string[];
}
export type SearchSpace = Record<string, SearchSpaceEntry>;

export interface MatrixFeatures {
  matrix_id: string;
  dof_per_node: number;
  matrix: {
    n: number;
    nnz: number;
    density: number;
    nnz_per_row: number;
    bandwidth: number;
    avg_bandwidth: number;
    relative_bandwidth: number;
    pattern_symmetric: boolean;
    numeric_symmetric: boolean;
    zero_diagonal_rows: number;
    diag_dominant_fraction: number;
    diag_to_offdiag_ratio: number;
  };
  graph: {
    nodes: number;
    edges: number;
    degree_mean: number;
    degree_max: number;
    degree_std: number;
    connected_components: number;
    vweight_cv: number;
    eweight_cv: number;
  };
  valid_dof_per_node: number[];
}

export interface TuningDefaults {
  simulation: string;
  matrix_id: string;
  parameters: SimulationParameters;
  features: MatrixFeatures;
  search_space: SearchSpace;
}

export interface DryRun {
  reachable: boolean;
  coarse_nodes?: number;
  coarse_edges?: number;
  levels?: number;
  vweight_spread?: number;
  reason?: string | null;
}

export interface AutoSelectResult {
  matrix_id: string;
  parameters: SimulationParameters;
  rationale: string[];
  feasible: boolean;
  reasons: string[];
  dry_run: DryRun;
  features: MatrixFeatures;
  candidates: Array<{
    strategy: string;
    coarsen_ratio: number;
    coarse_target: number;
    feasible: boolean;
    score: number | null;
    dry_run: DryRun;
    reasons: string[];
  }>;
  applied?: boolean;
}

export interface StudySummary {
  state?: 'created' | 'running' | 'completed' | 'manual';
  n_trials?: number;
  trials_done?: number;
  trials_ok?: number;
  trials_infeasible?: number;
  trials_error?: number;
  objectives?: ObjectiveKey[];
  aggregation?: 'pareto' | 'weighted';
  multi_objective?: boolean;
  pareto_front?: number[];
  best_trial?: number;
  best_values?: Record<string, number>;
  best_score?: number | null;
  best_curve?: Array<number | null>;
  stop_reason?: string;
  updated_at?: string;
}

export interface StudyBrief {
  id: string;
  simulation: string;
  matrix_id: string;
  objectives: ObjectiveKey[];
  aggregation: 'pareto' | 'weighted';
  sampler: string;
  n_trials: number;
  free_parameters: string[];
  summary: StudySummary;
  running_job_id: string | null;
}

export interface StudyTrial {
  number: number;
  status: 'ok' | 'infeasible' | 'error';
  suggested: Record<string, string | number>;
  parameters: SimulationParameters;
  values: Record<string, number> | null;
  score: number | null;
  reasons: string[];
  run_dirs: string[];
  duration_sec?: number;
  finished_at?: string;
  manual?: boolean;
}

export interface StudyDetail extends StudyBrief {
  config: Record<string, any>;
  trials: StudyTrial[];
  pending: Record<string, { parameters: SimulationParameters; created_at: string }>;
  best_parameters: SimulationParameters | null;
}

export interface StudyRequest {
  simulation: string;
  objectives: ObjectiveKey[];
  aggregation: 'pareto' | 'weighted';
  weights?: Record<string, number>;
  band_percent?: number;
  sampler: string;
  n_trials: number;
  repeats: number;
  timeout_sec?: number | null;
  patience?: number | null;
  search_space: SearchSpace;
  warm_start: { base: boolean; auto: boolean; history: boolean };
  start: boolean;
}

export interface CreateStudyResponse {
  study: StudyBrief;
  job: SimulationJob | null;
}
