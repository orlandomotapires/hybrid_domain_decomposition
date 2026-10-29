import {
  CoarseningPreviewResponse,
  Demonstrator,
  SimulationConfig,
  SimulationJob,
  SimulationParameters,
} from '../types/pipeline';

interface DemoSnapshot {
  demonstrators: Demonstrator[];
  presets: Record<string, Record<string, { filename: string; parameters: SimulationParameters }>>;
  batch_config: any;
  batch_runs: any[];
  batch_details: Record<string, any>;
  batch_analysis: Record<string, Record<string, any>>;
  demonstrator_runs: Record<string, { demonstrator_id: string; runs: any[] }>;
  run_details: Record<string, any>;
  hardware_status: any;
}

let cachedSnapshot: DemoSnapshot | null = null;
const simulatedJobs: SimulationJob[] = [];

async function getSnapshot(): Promise<DemoSnapshot> {
  if (cachedSnapshot) return cachedSnapshot;
  const res = await fetch('./demo-snapshot.json');
  if (!res.ok) {
    throw new Error(`Failed to load static demo snapshot (${res.status})`);
  }
  cachedSnapshot = (await res.json()) as DemoSnapshot;
  return cachedSnapshot;
}

function computeEstimates(params: SimulationParameters): Demonstrator['estimates'] {
  const k = params.partitioning_parameters.common.k_target || 8;
  const inf = params.coarsening_parameters.coarsen_inferior_limit || 100;
  const sup = params.coarsening_parameters.coarsen_superior_limit || 175;
  const mid = Math.round((inf + sup) / 2);
  const steps = Math.max(1, Math.round(Math.log2(k)));
  return {
    k_target: k,
    is_power_of_two: (k & (k - 1)) === 0,
    bisection_steps: steps,
    total_subproblems: Math.max(1, k - 1),
    target_coarse_nodes_range: [inf, sup],
    estimated_qubits_per_first_bisection: mid,
  };
}

export const staticFallbackApi = {
  listDemonstrators: async () => {
    const snap = await getSnapshot();
    return { demonstrators: snap.demonstrators };
  },

  getDemonstrator: async (demId: string) => {
    const snap = await getSnapshot();
    const found = snap.demonstrators.find((d) => d.id === demId) || snap.demonstrators[0];
    if (!found) throw new Error(`Demonstrator ${demId} not found`);
    return found;
  },

  createDemonstrator: async (name: string, cloneFrom?: string) => {
    const snap = await getSnapshot();
    const base =
      snap.demonstrators.find((d) => d.id === cloneFrom) || snap.demonstrators[0];
    const cleanId = name.trim().replace(/[^a-zA-Z0-9_-]/g, '_') || `demo_${Date.now()}`;
    const created: Demonstrator = JSON.parse(JSON.stringify(base));
    created.id = cleanId;
    created.demonstrator_dir = `demonstrators/${cleanId}`;
    snap.demonstrators.push(created);
    snap.presets[cleanId] = JSON.parse(JSON.stringify(snap.presets[base.id] || {}));
    return created;
  },

  renameDemonstrator: async (demId: string, newName: string) => {
    const snap = await getSnapshot();
    const found = snap.demonstrators.find((d) => d.id === demId);
    if (!found) throw new Error(`Demonstrator ${demId} not found`);
    const cleanId = newName.trim().replace(/[^a-zA-Z0-9_-]/g, '_');
    found.id = cleanId;
    found.demonstrator_dir = `demonstrators/${cleanId}`;
    return found;
  },

  deleteDemonstrator: async (demId: string) => {
    const snap = await getSnapshot();
    snap.demonstrators = snap.demonstrators.filter((d) => d.id !== demId);
    return {
      deleted: demId,
      remaining_demonstrators: snap.demonstrators.map((d) => d.id),
    };
  },

  updateConfig: async (demId: string, config: SimulationConfig) => {
    const snap = await getSnapshot();
    const found = snap.demonstrators.find((d) => d.id === demId);
    if (!found) throw new Error(`Demonstrator ${demId} not found`);
    found.simulation_config = config;
    found.active_parameters_file = config.parameters_file_path;
    const preset = snap.presets[demId]?.[config.parameters_file_path];
    if (preset?.parameters) {
      found.simulation_parameters = JSON.parse(JSON.stringify(preset.parameters));
      found.estimates = computeEstimates(found.simulation_parameters);
    }
    return found;
  },

  updateParameters: async (demId: string, params: SimulationParameters) => {
    const snap = await getSnapshot();
    const found = snap.demonstrators.find((d) => d.id === demId);
    if (!found) throw new Error(`Demonstrator ${demId} not found`);
    found.simulation_parameters = params;
    found.estimates = computeEstimates(params);
    return found;
  },

  getPreset: async (demId: string, presetFile: string) => {
    const snap = await getSnapshot();
    const preset = snap.presets[demId]?.[presetFile];
    if (preset) return preset;
    const found = snap.demonstrators.find((d) => d.id === demId) || snap.demonstrators[0];
    return {
      filename: presetFile,
      parameters: found.simulation_parameters,
    };
  },

  savePreset: async (
    demId: string,
    filename: string,
    parameters: SimulationParameters,
    setActive = true
  ) => {
    const snap = await getSnapshot();
    const found = snap.demonstrators.find((d) => d.id === demId);
    if (!found) throw new Error(`Demonstrator ${demId} not found`);
    const fname = filename.endsWith('.json') ? filename : `${filename}.json`;
    snap.presets[demId] = snap.presets[demId] || {};
    snap.presets[demId][fname] = { filename: fname, parameters };
    if (!found.preset_files.includes(fname)) {
      found.preset_files.push(fname);
    }
    if (setActive) {
      found.simulation_config.parameters_file_path = fname;
      found.active_parameters_file = fname;
      found.simulation_parameters = parameters;
    }
    return found;
  },

  deletePreset: async (demId: string, presetFile: string) => {
    const snap = await getSnapshot();
    const found = snap.demonstrators.find((d) => d.id === demId);
    if (!found) throw new Error(`Demonstrator ${demId} not found`);
    found.preset_files = found.preset_files.filter((f) => f !== presetFile);
    delete snap.presets[demId]?.[presetFile];
    return found;
  },

  previewCoarsening: async (
    demId: string,
    params: SimulationParameters
  ): Promise<CoarseningPreviewResponse> => {
    const snap = await getSnapshot();
    const found = snap.demonstrators.find((d) => d.id === demId) || snap.demonstrators[0];
    const startNodes = found?.matrices?.expected_nodes || 600;
    const startEdges = Math.round(startNodes * 9.5);
    const cp = params.coarsening_parameters;
    const levels: CoarseningPreviewResponse['levels'] = [];
    let nodes = startNodes;
    let edges = startEdges;
    let reached = false;
    for (let lvl = 0; lvl <= cp.max_levels; lvl++) {
      const inRange =
        nodes >= cp.coarsen_inferior_limit && nodes <= cp.coarsen_superior_limit;
      if (inRange) reached = true;
      levels.push({
        level: lvl,
        nodes,
        edges,
        density: Number(((2 * edges) / Math.max(1, nodes * (nodes - 1))).toFixed(4)),
        max_node_weight: Math.pow(2, lvl),
        mean_node_weight: Number((startNodes / Math.max(1, nodes)).toFixed(2)),
        in_target_range: inRange,
      });
      if (inRange || nodes <= cp.coarsen_inferior_limit) break;
      const nextNodes = Math.max(cp.coarsen_inferior_limit, Math.round(nodes * 0.56));
      if (nextNodes === nodes) break;
      nodes = nextNodes;
      edges = Math.max(nodes, Math.round(edges * 0.45));
    }
    const last = levels[levels.length - 1];
    return {
      demonstrator_id: demId,
      strategy: cp.strategy,
      target_range: [cp.coarsen_inferior_limit, cp.coarsen_superior_limit],
      reached_target_range: reached,
      levels_executed: levels.length - 1,
      initial_nodes: startNodes,
      initial_edges: startEdges,
      final_nodes: last.nodes,
      final_edges: last.edges,
      elapsed_seconds: 0.04,
      levels,
    };
  },

  validateParameters: async (params: SimulationParameters) => {
    const k = params.partitioning_parameters.common.k_target;
    const isPow2 = k >= 2 && (k & (k - 1)) === 0;
    if (!isPow2) {
      return {
        valid: false,
        error: 'k_target must be a power of 2 (e.g., 2, 4, 8, 16)',
      };
    }
    if (
      params.coarsening_parameters.coarsen_inferior_limit >
      params.coarsening_parameters.coarsen_superior_limit
    ) {
      return {
        valid: false,
        error: 'Inferior node limit cannot exceed Superior node limit',
      };
    }
    return {
      valid: true,
      normalized_parameters: params,
      estimates: computeEstimates(params),
    };
  },

  generateDemoMatrices: async (
    demId: string,
    opts: { nx_nodes: number; ny_nodes: number; nz_nodes: number; dof_per_node: number }
  ) => {
    const snap = await getSnapshot();
    const found = snap.demonstrators.find((d) => d.id === demId) || snap.demonstrators[0];
    const totalNodes = opts.nx_nodes * opts.ny_nodes * opts.nz_nodes;
    const totalDofs = totalNodes * opts.dof_per_node;
    found.simulation_config.dof_per_node = opts.dof_per_node;
    if (found.matrices) {
      found.matrices.expected_nodes = totalNodes;
      found.matrices.k_Summary.shape = [totalDofs, totalDofs];
      found.matrices.m_Summary.shape = [totalDofs, totalDofs];
    }
    return found;
  },

  runSimulation: async (demonstratorDir: string, parametersOverride?: SimulationParameters) => {
    const demId = demonstratorDir.replace(/^demonstrators\//, '');
    const snap = await getSnapshot();
    const dem = snap.demonstrators.find((d) => d.id === demId) || snap.demonstrators[0];
    const params = parametersOverride || dem.simulation_parameters;
    const now = new Date().toISOString();
    const jobId = `demo_${Date.now().toString(36)}`;
    const resultDir =
      snap.demonstrator_runs[dem.id]?.runs?.[0]?.result_dir ||
      `demonstrators/${dem.id}/results/run_demo`;
    const job: SimulationJob = {
      job_id: jobId,
      kind: 'single_run',
      target: demonstratorDir,
      status: 'completed',
      created_at: now,
      started_at: now,
      finished_at: now,
      return_code: 0,
      result_dir: resultDir,
      log_lines: [
        '[INFO] Static GitHub Pages Demo Mode — replaying pipeline trajectory in browser',
        `[INFO] Loaded ${dem.id} (expected nodes: ${dem.matrices?.expected_nodes || 600})`,
        `[INFO] Coarsening strategy: ${params.coarsening_parameters.strategy} -> target [${params.coarsening_parameters.coarsen_inferior_limit}, ${params.coarsening_parameters.coarsen_superior_limit}]`,
        `[INFO] Partitioning strategy: ${params.partitioning_parameters.partitioning_strategy} (k = ${params.partitioning_parameters.common.k_target})`,
        `[INFO] Refinement objective: ${params.refinement_parameters.refine_objective}`,
        '[INFO] Permutation & bandwidth metrics ready in Results tab.',
      ],
      total_log_lines: 6,
    };
    simulatedJobs.unshift(job);
    return job;
  },

  listJobs: async () => ({ jobs: simulatedJobs }),

  getJob: async (jobId: string) => {
    const found = simulatedJobs.find((j) => j.job_id === jobId) || simulatedJobs[0];
    if (!found) throw new Error(`Job ${jobId} not found`);
    return found;
  },

  cancelJob: async (jobId: string) => {
    const found = simulatedJobs.find((j) => j.job_id === jobId);
    if (!found) throw new Error(`Job ${jobId} not found`);
    found.status = 'cancelled';
    return found;
  },

  deleteJob: async (jobId: string) => {
    const idx = simulatedJobs.findIndex((j) => j.job_id === jobId);
    if (idx >= 0) simulatedJobs.splice(idx, 1);
    return { deleted: jobId };
  },

  getBatchConfig: async () => {
    const snap = await getSnapshot();
    return snap.batch_config;
  },

  updateBatchConfig: async (config: any) => {
    const snap = await getSnapshot();
    snap.batch_config.configuration = config;
    return snap.batch_config;
  },

  startBatchRun: async () => {
    const now = new Date().toISOString();
    const job: SimulationJob = {
      job_id: `batch_demo_${Date.now().toString(36)}`,
      kind: 'batch_run',
      target: 'batch/batch_configuration.json',
      status: 'completed',
      created_at: now,
      started_at: now,
      finished_at: now,
      return_code: 0,
      result_dir: 'batch/runs/batch_20260521_151902',
      log_lines: [
        '[INFO] Static GitHub Pages Demo Mode — pre-computed batch study batch_20260521_151902 loaded.',
      ],
      total_log_lines: 1,
    };
    simulatedJobs.unshift(job);
    return job;
  },

  listBatchRuns: async () => {
    const snap = await getSnapshot();
    return { batch_runs: snap.batch_runs };
  },

  getBatchRunDetail: async (batchId: string) => {
    const snap = await getSnapshot();
    return (
      snap.batch_details[batchId] ||
      Object.values(snap.batch_details)[0] || {
        id: batchId,
        manifest: {},
        summary: { rows: [] },
        configuration: {},
        log_tail: '',
      }
    );
  },

  listDemonstratorRuns: async (demId: string) => {
    const snap = await getSnapshot();
    return snap.demonstrator_runs[demId] || { demonstrator_id: demId, runs: [] };
  },

  getSingleRunDetail: async (resultDir: string) => {
    const snap = await getSnapshot();
    return (
      snap.run_details[resultDir] ||
      Object.values(snap.run_details)[0] || {
        result_dir: resultDir,
        kpi_summary: null,
        curves: { K: [], M: [] },
        artifacts: [],
        can_render_plots: false,
        available_plots: [],
      }
    );
  },

  getBatchAnalysis: async (batchId: string, demonstrator: string) => {
    const snap = await getSnapshot();
    const byBatch =
      snap.batch_analysis[batchId] || Object.values(snap.batch_analysis)[0] || {};
    return byBatch[demonstrator] || Object.values(byBatch)[0] || {};
  },

  getHardwareStatus: async () => {
    const snap = await getSnapshot();
    return snap.hardware_status;
  },

  checkDWaveQpu: async (solverName: string, region: string) => ({
    reachable: false,
    solver_name: solverName,
    region,
    error:
      'Live D-Wave Leap QPU probing requires running the Python backend locally (./run.sh --ui) with DWAVE_API_TOKEN.',
  }),

  inspectQlmQpu: async (qpuName: string) => ({
    reachable: false,
    qpu_name: qpuName,
    error:
      'Live QLM QPU inspection requires running the Python backend locally (./run.sh --ui) with myQLM installed.',
  }),
};

