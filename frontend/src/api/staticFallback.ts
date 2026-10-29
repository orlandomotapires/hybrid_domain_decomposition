import {
  CoarseningPreviewLevel,
  CoarseningPreviewResponse,
  Demonstrator,
  LogEntry,
  QuantumEstimates,
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
const jobFullLogs: Record<string, LogEntry[]> = {};

async function getSnapshot(): Promise<DemoSnapshot> {
  if (cachedSnapshot) return cachedSnapshot;
  const res = await fetch('./demo-snapshot.json');
  if (!res.ok) {
    throw new Error(`Failed to load static demo snapshot (${res.status})`);
  }
  cachedSnapshot = (await res.json()) as DemoSnapshot;
  return cachedSnapshot;
}

function nowTimeStr(): string {
  const d = new Date();
  return d.toTimeString().split(' ')[0];
}

function computeEstimates(params: SimulationParameters): QuantumEstimates {
  const pp = params.partitioning_parameters;
  const cp = params.coarsening_parameters;
  const k = pp.common.k_target || 8;
  const inf = cp.coarsen_inferior_limit || 100;
  const sup = cp.coarsen_superior_limit || 175;
  const mid = Math.round((inf + sup) / 2);
  const steps = Math.max(1, Math.round(Math.log2(Math.max(2, k))));
  const totalSubproblems = Math.max(1, k - 1);
  const warnings: string[] = [];

  if (pp.partitioning_strategy === 'quantum_approximation_optimizer') {
    const qaoa = pp.strategies.quantum_approximation_optimizer;
    if (qaoa.simulated && sup > 24) {
      warnings.push(
        `Local QAOA statevector simulation scales as 2^N; keep Superior Node Limit <= 22 (currently ${sup}).`
      );
    }
  }

  return {
    k_target: k,
    is_power_of_two: k >= 2 && (k & (k - 1)) === 0,
    bisection_depth: steps,
    total_bipartition_subproblems: totalSubproblems,
    first_subproblem_qubits_range: [inf, sup],
    expected_dwave_calls:
      pp.partitioning_strategy === 'quantum_annealing'
        ? totalSubproblems * (pp.strategies.quantum_annealing?.num_starts || 1)
        : undefined,
    total_annealing_reads:
      pp.partitioning_strategy === 'quantum_annealing'
        ? totalSubproblems *
          (pp.strategies.quantum_annealing?.num_starts || 1) *
          (pp.strategies.quantum_annealing?.num_reads || 100)
        : undefined,
    expected_qlm_jobs:
      pp.partitioning_strategy === 'quantum_approximation_optimizer'
        ? totalSubproblems *
          (pp.strategies.quantum_approximation_optimizer?.num_starts || 1)
        : undefined,
    total_circuit_shots:
      pp.partitioning_strategy === 'quantum_approximation_optimizer'
        ? totalSubproblems *
          (pp.strategies.quantum_approximation_optimizer?.num_starts || 1) *
          (pp.strategies.quantum_approximation_optimizer?.num_steps || 10) *
          (pp.strategies.quantum_approximation_optimizer?.num_shots || 100)
        : undefined,
    warnings,
  };
}

function simulateCoarseningTrajectory(
  demId: string,
  startNodes: number,
  startEdges: number,
  params: SimulationParameters
): CoarseningPreviewResponse {
  const cp = params.coarsening_parameters;
  const levels: CoarseningPreviewLevel[] = [
    {
      level: 0,
      nodes: startNodes,
      edges: startEdges,
      ratio: 1.0,
      max_node_weight: 1,
      accepted: true,
      stop_reason: null,
    },
  ];

  let currNodes = startNodes;
  let currEdges = startEdges;
  let currMaxWeight = 1;
  let stopReason = 'reached_target_range';
  const reductionFactor =
    cp.strategy === 'heavy_edge'
      ? 0.53
      : cp.strategy === 'modified'
      ? 0.56
      : cp.strategy === 'light_edge'
      ? 0.58
      : 0.55;

  for (let lvl = 1; lvl <= cp.max_levels; lvl++) {
    if (
      currNodes >= cp.coarsen_inferior_limit &&
      currNodes <= cp.coarsen_superior_limit
    ) {
      stopReason = 'reached_target_range';
      break;
    }
    const nextNodes = Math.max(2, Math.round(currNodes * reductionFactor));
    const ratio = Number((nextNodes / currNodes).toFixed(3));
    const nextEdges = Math.max(nextNodes - 1, Math.round(currEdges * 0.46));
    const nextWeight = currMaxWeight * 2;

    if (nextNodes < cp.coarsen_inferior_limit) {
      levels.push({
        level: lvl,
        nodes: nextNodes,
        edges: nextEdges,
        ratio,
        max_node_weight: nextWeight,
        accepted: false,
        stop_reason: 'below_inferior_limit',
      });
      stopReason =
        currNodes <= cp.coarsen_superior_limit
          ? 'reached_target_range'
          : 'next_level_below_inferior_limit';
      break;
    }

    if (ratio > cp.coarsen_ratio) {
      levels.push({
        level: lvl,
        nodes: nextNodes,
        edges: nextEdges,
        ratio,
        max_node_weight: nextWeight,
        accepted: false,
        stop_reason: 'coarsen_ratio_exceeded',
      });
      stopReason = 'coarsen_ratio_exceeded';
      break;
    }

    if (cp.max_node_weight && nextWeight > cp.max_node_weight) {
      levels.push({
        level: lvl,
        nodes: nextNodes,
        edges: nextEdges,
        ratio,
        max_node_weight: nextWeight,
        accepted: false,
        stop_reason: 'max_node_weight_exceeded',
      });
      stopReason = 'max_node_weight_exceeded';
      break;
    }

    currNodes = nextNodes;
    currEdges = nextEdges;
    currMaxWeight = nextWeight;
    levels.push({
      level: lvl,
      nodes: currNodes,
      edges: currEdges,
      ratio,
      max_node_weight: currMaxWeight,
      accepted: true,
      stop_reason: null,
    });

    if (
      currNodes >= cp.coarsen_inferior_limit &&
      currNodes <= cp.coarsen_superior_limit
    ) {
      stopReason = 'reached_target_range';
      break;
    }
  }

  const acceptedLevels = levels.filter((l) => l.accepted);
  const lastAccepted = acceptedLevels[acceptedLevels.length - 1];
  const reachable =
    lastAccepted.nodes >= cp.coarsen_inferior_limit &&
    lastAccepted.nodes <= cp.coarsen_superior_limit;

  return {
    demonstrator_id: demId,
    reachable,
    final_coarse_nodes: lastAccepted.nodes,
    final_coarse_edges: lastAccepted.edges,
    accepted_levels_count: acceptedLevels.length - 1,
    stop_reason: stopReason,
    elapsed_ms: 14,
    levels,
  };
}

export const staticFallbackApi = {
  listDemonstrators: async (): Promise<{ demonstrators: Demonstrator[] }> => {
    const snap = await getSnapshot();
    return { demonstrators: snap.demonstrators };
  },

  getDemonstrator: async (demId: string): Promise<Demonstrator> => {
    const snap = await getSnapshot();
    const found = snap.demonstrators.find((d) => d.id === demId) || snap.demonstrators[0];
    if (!found) throw new Error(`Demonstrator ${demId} not found`);
    return found;
  },

  createDemonstrator: async (name: string, cloneFrom?: string): Promise<Demonstrator> => {
    const snap = await getSnapshot();
    const base =
      snap.demonstrators.find((d) => d.id === cloneFrom) || snap.demonstrators[0];
    const cleanId = name.trim().replace(/[^a-zA-Z0-9_-]/g, '_') || `matrix_${Date.now()}`;
    const created: Demonstrator = JSON.parse(JSON.stringify(base));
    created.id = cleanId;
    created.demonstrator_dir = `matrices/${cleanId}`;
    snap.demonstrators.push(created);
    snap.presets[cleanId] = JSON.parse(JSON.stringify(snap.presets[base.id] || {}));
    snap.demonstrator_runs[cleanId] = {
      demonstrator_id: cleanId,
      runs: JSON.parse(JSON.stringify(snap.demonstrator_runs[base.id]?.runs || [])),
    };
    return created;
  },

  renameDemonstrator: async (demId: string, newName: string): Promise<Demonstrator> => {
    const snap = await getSnapshot();
    const found = snap.demonstrators.find((d) => d.id === demId);
    if (!found) throw new Error(`Matrix ${demId} not found`);
    const cleanId = newName.trim().replace(/[^a-zA-Z0-9_-]/g, '_');
    found.id = cleanId;
    found.demonstrator_dir = `matrices/${cleanId}`;
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

  updateConfig: async (demId: string, config: SimulationConfig): Promise<Demonstrator> => {
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

  updateParameters: async (
    demId: string,
    params: SimulationParameters
  ): Promise<Demonstrator> => {
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
  ): Promise<Demonstrator> => {
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
      found.estimates = computeEstimates(parameters);
    }
    return found;
  },

  deletePreset: async (demId: string, presetFile: string): Promise<Demonstrator> => {
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
    const dof = params.general_parameters.dof_per_node || 3;
    const rows = found?.matrices?.matrix_k?.rows || 1800;
    const startNodes = Math.max(10, Math.round(rows / dof));
    const startEdges = Math.round(startNodes * 9.55);
    return simulateCoarseningTrajectory(demId, startNodes, startEdges, params);
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
  ): Promise<Demonstrator> => {
    const snap = await getSnapshot();
    const found = snap.demonstrators.find((d) => d.id === demId) || snap.demonstrators[0];
    const totalNodes = opts.nx_nodes * opts.ny_nodes * opts.nz_nodes;
    const totalDofs = totalNodes * opts.dof_per_node;
    const nnz = totalDofs * 58;
    found.simulation_parameters.general_parameters.dof_per_node = opts.dof_per_node;
    if (found.matrices) {
      found.matrices.matrix_k.rows = totalDofs;
      found.matrices.matrix_k.cols = totalDofs;
      found.matrices.matrix_k.nnz = nnz;
      found.matrices.matrix_m.rows = totalDofs;
      found.matrices.matrix_m.cols = totalDofs;
      found.matrices.matrix_m.nnz = nnz;
    }
    return JSON.parse(JSON.stringify(found));
  },

  runSimulation: async (
    demonstratorDir: string,
    parametersOverride?: SimulationParameters
  ): Promise<SimulationJob> => {
    const demId = demonstratorDir.replace(/^(demonstrators|matrices)\//, '');
    const snap = await getSnapshot();
    const dem = snap.demonstrators.find((d) => d.id === demId) || snap.demonstrators[0];
    const params = parametersOverride || dem.simulation_parameters;
    const dof = params.general_parameters.dof_per_node || 3;
    const rows = dem.matrices?.matrix_k?.rows || 1800;
    const fineNodes = Math.max(10, Math.round(rows / dof));
    const fineEdges = Math.round(fineNodes * 9.55);
    const preview = simulateCoarseningTrajectory(dem.id, fineNodes, fineEdges, params);

    const kTarget = params.partitioning_parameters.common.k_target || 8;
    const strat = params.partitioning_parameters.partitioning_strategy;
    const stratCfg = (params.partitioning_parameters.strategies as any)[strat] || {};
    const isSimulated = strat === 'metis_partitioning' ? true : stratCfg.simulated !== false;

    const jobId = `job_${Date.now().toString(36).slice(-6)}`;
    const runStamp = new Date()
      .toISOString()
      .replace(/[:T-]/g, '_')
      .slice(0, 19);
    const resultDir = `matrices/${dem.id}/results/run_${runStamp}_browser`;

    const job: SimulationJob = {
      job_id: jobId,
      job_type: 'single',
      title: `Simulation (${dem.id})`,
      demonstrator_dir: demonstratorDir,
      status: 'running',
      current_stage: 'initialization',
      stage_progress: 15,
      created_at: new Date().toISOString(),
      finished_at: null,
      elapsed_sec: 0.2,
      stage_durations_sec: { initialization: 0.2 },
      result_dir: null,
      pid: 4200,
      exit_code: null,
      error_message: null,
      telemetry: {
        initial_nodes: fineNodes,
        initial_edges: fineEdges,
      },
      log_count: 0,
      logs: [],
    };

    const appendLogs = (entries: Array<[string, string]>) => {
      const ts = nowTimeStr();
      for (const [level, message] of entries) {
        jobFullLogs[jobId].push({ timestamp: ts, level, message });
      }
      job.log_count = jobFullLogs[jobId].length;
    };

    jobFullLogs[jobId] = [];
    appendLogs([
      ['INFO', `Running in-browser simulation for ${dem.id} (GitHub Pages mode)`],
      ['INFO', 'Converting matrices to graphs'],
      [
        'INFO',
        `Graph G_K with ${fineNodes} nodes and ${fineEdges} edges created from K matrix`,
      ],
    ]);

    simulatedJobs.unshift(job);

    // Progress through the 5 pipeline stages asynchronously so the Execution Console animates live
    setTimeout(() => {
      if (job.status === 'cancelled') return;
      job.current_stage = 'coarsening';
      job.stage_progress = 40;
      job.elapsed_sec = 0.8;
      job.stage_durations_sec = { ...job.stage_durations_sec, coarsening: 0.6 };
      job.telemetry.coarse_nodes = preview.final_coarse_nodes;
      job.telemetry.coarse_edges = preview.final_coarse_edges;
      job.telemetry.coarsening_levels = preview.accepted_levels_count;
      appendLogs([
        ['INFO', `Coarsening Heavy Edge Matching (${params.coarsening_parameters.strategy})`],
        [
          'VERBOSE',
          `Coarse graph has ${preview.final_coarse_nodes} nodes and ${preview.final_coarse_edges} edges with ${preview.accepted_levels_count} levels`,
        ],
      ]);
    }, 550);

    setTimeout(() => {
      if (job.status === 'cancelled') return;
      job.current_stage = 'partitioning';
      job.stage_progress = 68;
      job.elapsed_sec = 1.6;
      job.stage_durations_sec = { ...job.stage_durations_sec, partitioning: 0.8 };
      job.telemetry.coarse_parts = kTarget;
      const methodDesc =
        strat === 'metis_partitioning'
          ? 'METIS k-way partitioning'
          : strat === 'quantum_annealing'
          ? isSimulated
            ? 'simulated quantum annealing for bipartitioning'
            : 'D-Wave QPU annealing (browser preview)'
          : isSimulated
          ? 'PennyLane QAOA simulator for bipartitioning'
          : 'QLM QAOA (browser preview)';
      appendLogs([
        ['INFO', `Running ${methodDesc}`],
        ['VERBOSE', `Partitioning on coarse graph produced ${kTarget} parts`],
      ]);
    }, 1150);

    setTimeout(() => {
      if (job.status === 'cancelled') return;
      job.current_stage = 'uncoarsening';
      job.stage_progress = 85;
      job.elapsed_sec = 2.1;
      job.stage_durations_sec = { ...job.stage_durations_sec, uncoarsening: 0.5 };
      appendLogs([
        [
          'INFO',
          `Uncoarsening Kernighan-Lin (objective: ${params.refinement_parameters.refine_objective})`,
        ],
      ]);
    }, 1700);

    setTimeout(() => {
      if (job.status === 'cancelled') return;
      job.current_stage = 'permutation';
      job.stage_progress = 100;
      job.status = 'completed';
      job.finished_at = new Date().toISOString();
      job.elapsed_sec = 2.5;
      job.exit_code = 0;
      job.result_dir = resultDir;
      job.stage_durations_sec = { ...job.stage_durations_sec, permutation: 0.4 };

      // Build a new run result entry based on the template run + user parameters
      const templateDetail =
        Object.values(snap.run_details)[0] || ({} as Record<string, any>);
      const clonedDetail = JSON.parse(JSON.stringify(templateDetail));
      clonedDetail.result_dir = resultDir;
      clonedDetail.run_id = `run_${runStamp}_browser`;
      clonedDetail.run_parameters = JSON.parse(JSON.stringify(params));

      // Slightly vary KPIs deterministically by strategy + k_target so comparisons show real differences
      const factor =
        strat === 'metis_partitioning'
          ? 0.96
          : strat === 'quantum_annealing'
          ? 0.99
          : 1.02;
      if (clonedDetail.kpi_summary) {
        for (const mKey of ['K', 'M']) {
          const mk = clonedDetail.kpi_summary[mKey];
          if (mk) {
            mk.permuted_bandwidth = Math.round(mk.permuted_bandwidth * factor);
            mk.permuted_avg_bandwidth = Number(
              (mk.permuted_avg_bandwidth * factor).toFixed(2)
            );
            mk.bandwidth_reduction_pct = Number(
              (
                ((mk.original_bandwidth - mk.permuted_bandwidth) /
                  Math.max(1, mk.original_bandwidth)) *
                100
              ).toFixed(2)
            );
            mk.avg_bandwidth_reduction_pct = Number(
              (
                ((mk.original_avg_bandwidth - mk.permuted_avg_bandwidth) /
                  Math.max(1, mk.original_avg_bandwidth)) *
                100
              ).toFixed(2)
            );
          }
        }
      }

      snap.run_details[resultDir] = clonedDetail;
      snap.demonstrator_runs[dem.id] = snap.demonstrator_runs[dem.id] || {
        demonstrator_id: dem.id,
        runs: [],
      };
      snap.demonstrator_runs[dem.id].runs.unshift({
        run_id: `run_${runStamp}_browser`,
        result_dir: resultDir,
        demonstrator_id: dem.id,
        partitioning_strategy: strat,
        simulated: strat === 'metis_partitioning' ? null : isSimulated,
        k_target: kTarget,
        coarsening_strategy: params.coarsening_parameters.strategy,
        coarsen_limits: [
          params.coarsening_parameters.coarsen_inferior_limit,
          params.coarsening_parameters.coarsen_superior_limit,
        ],
        kpi_summary: clonedDetail.kpi_summary,
        can_render_plots: false,
      });
      dem.runs_count = snap.demonstrator_runs[dem.id].runs.length;
      dem.latest_run = resultDir;

      appendLogs([
        ['INFO', 'Permuting matrices'],
        ['INFO', `Simulation completed -> ${resultDir}`],
      ]);
    }, 2200);

    return {
      ...job,
      logs: jobFullLogs[jobId].slice(0),
    };
  },

  listJobs: async () => ({ jobs: simulatedJobs }),

  getJob: async (jobId: string, logOffset = 0): Promise<SimulationJob> => {
    const found = simulatedJobs.find((j) => j.job_id === jobId) || simulatedJobs[0];
    if (!found) throw new Error(`Job ${jobId} not found`);
    const allLogs = jobFullLogs[found.job_id] || [];
    return {
      ...found,
      log_count: allLogs.length,
      logs: allLogs.slice(logOffset),
    };
  },

  cancelJob: async (jobId: string): Promise<SimulationJob> => {
    const found = simulatedJobs.find((j) => j.job_id === jobId);
    if (!found) throw new Error(`Job ${jobId} not found`);
    found.status = 'cancelled';
    found.finished_at = new Date().toISOString();
    return found;
  },

  deleteJob: async (jobId: string) => {
    const idx = simulatedJobs.findIndex((j) => j.job_id === jobId);
    if (idx >= 0) simulatedJobs.splice(idx, 1);
    delete jobFullLogs[jobId];
    return { deleted: jobId };
  },

  getBatchConfig: async () => {
    const snap = await getSnapshot();
    return snap.batch_config;
  },

  updateBatchConfig: async (config: any) => {
    const snap = await getSnapshot();
    const geometries = config.geometries || [];
    const coarseningPresets = config.coarsening_presets || [];
    const algorithmPresets = config.algorithm_presets || [];
    const asyncKeys = new Set(config.async_remote_case_keys || []);
    const cases: any[] = [];
    for (const geom of geometries) {
      for (const alg of algorithmPresets) {
        const allowed = new Set(alg.allowed_sizes || []);
        for (const coarsen of coarseningPresets) {
          const cKey = coarsen.key;
          if (!allowed.has(cKey)) continue;
          cases.push({
            case_key: `${geom.key}__${alg.key}__${cKey}`,
            geometry: geom.key,
            demonstrator_dir: geom.demonstrator_dir,
            algorithm: alg.key,
            partitioning_strategy: alg.partitioning_strategy,
            coarsening_size: cKey,
            coarsen_inferior_limit: coarsen.coarsen_inferior_limit,
            coarsen_superior_limit: coarsen.coarsen_superior_limit,
            is_async: asyncKeys.has(alg.key),
            strategy_parameters: alg.strategy_parameters || {},
          });
        }
      }
    }
    snap.batch_config = {
      configuration: config,
      dry_run_cases: cases,
      case_count: cases.length,
    };
    return snap.batch_config;
  },

  startBatchRun: async (): Promise<SimulationJob> => {
    const snap = await getSnapshot();
    const config = snap.batch_config.configuration || {};
    const dryRunCases: any[] = snap.batch_config.dry_run_cases || [];
    const commonDefaults = config.common_defaults || {};
    const kTarget = commonDefaults.partitioning_common?.k_target || 4;
    const coarsenStrat = commonDefaults.coarsening_parameters?.strategy || 'modified';

    const now = new Date();
    const stamp = now
      .toISOString()
      .replace(/[:T-]/g, '')
      .slice(0, 15)
      .replace(/^(\d{8})(\d{6}).*$/, '$1_$2');
    const batchId = `batch_${stamp}`;
    const batchDir = `batch/runs/${batchId}`;
    const jobId = `batch_${Date.now().toString(36).slice(-6)}`;

    const job: SimulationJob = {
      job_id: jobId,
      job_type: 'batch',
      title: `Batch Study (${batchId})`,
      demonstrator_dir: null,
      status: 'running',
      current_stage: 'initialization',
      stage_progress: 5,
      created_at: now.toISOString(),
      finished_at: null,
      elapsed_sec: 0.1,
      stage_durations_sec: {
        initialization: 0,
        coarsening: 0,
        partitioning: 0,
        uncoarsening: 0,
        permutation: 0,
      },
      result_dir: null,
      batch_dir: batchDir,
      pid: 4300,
      exit_code: null,
      error_message: null,
      telemetry: {},
      log_count: 0,
      logs: [],
    };

    jobFullLogs[jobId] = [];
    const appendLogs = (entries: Array<[string, string]>) => {
      const ts = nowTimeStr();
      for (const [level, message] of entries) {
        jobFullLogs[jobId].push({ timestamp: ts, level, message });
      }
      job.log_count = jobFullLogs[jobId].length;
    };

    const totalCases = Math.max(1, dryRunCases.length);
    appendLogs([
      [
        'INFO',
        `Starting batch study ${batchId} with ${dryRunCases.length} cases across ${(config.geometries || []).length} matrices`,
      ],
    ]);

    simulatedJobs.unshift(job);

    // Step through each case and all 5 pipeline stages asynchronously so the console streams live
    const stepMs = Math.max(120, Math.min(280, Math.floor(4500 / (totalCases * 5))));
    let currentCaseIdx = 0;
    let currentSubStage = 0;
    const stageNames = [
      'initialization',
      'coarsening',
      'partitioning',
      'uncoarsening',
      'permutation',
    ] as const;

    const timer = setInterval(() => {
      if (job.status === 'cancelled') {
        clearInterval(timer);
        appendLogs([['WARNING', 'Job cancelled by user.']]);
        return;
      }

      if (currentCaseIdx >= dryRunCases.length) {
        clearInterval(timer);
        job.status = 'completed';
        job.current_stage = 'permutation';
        job.stage_progress = 100;
        job.finished_at = new Date().toISOString();
        job.exit_code = 0;
        appendLogs([
          [
            'INFO',
            `Batch study ${batchId} finished: ${dryRunCases.length}/${dryRunCases.length} cases completed -> ${batchDir}/batch_summary.json`,
          ],
        ]);

        // Build batch summary rows & analysis from the template batch so the new batch is inspectable in Results
        const templateDetail: any = Object.values(snap.batch_details)[0] || {};
        const templateRows: any[] = templateDetail?.summary?.rows || [];
        const templateAnalysisByDem: Record<string, any> =
          Object.values(snap.batch_analysis)[0] || {};

        const generatedRows: any[] = dryRunCases.map((c) => {
          const exact = templateRows.find(
            (r) =>
              r.geometry === c.geometry &&
              r.algorithm === c.algorithm &&
              r.coarsening_size === c.coarsening_size
          );
          const sameGeom = templateRows.find((r) => r.geometry === c.geometry);
          const baseRow = JSON.parse(
            JSON.stringify(exact || sameGeom || templateRows[0] || {})
          );
          return {
            ...baseRow,
            case_key: c.case_key,
            geometry: c.geometry,
            algorithm: c.algorithm,
            partitioning_strategy: c.partitioning_strategy,
            coarsening_size: c.coarsening_size,
            coarsen_inferior_limit: c.coarsen_inferior_limit,
            coarsen_superior_limit: c.coarsen_superior_limit,
            status: 'completed',
            error_message: null,
            error_type: null,
          };
        });

        const geoms = Array.from(
          new Set(generatedRows.map((r) => r.geometry).filter(Boolean))
        ).sort();

        snap.batch_runs.unshift({
          id: batchId,
          batch_directory: batchDir,
          started_at: job.created_at,
          finished_at: job.finished_at,
          total_cases: generatedRows.length,
          completed_cases: generatedRows.length,
          failed_cases: 0,
          running_cases: 0,
          geometries: geoms,
          has_summary: true,
        });

        snap.batch_details[batchId] = {
          id: batchId,
          manifest: {
            batch_started_at: job.created_at,
            batch_finished_at: job.finished_at,
            cases: generatedRows,
          },
          summary: { rows: generatedRows },
          configuration: JSON.parse(JSON.stringify(config)),
          log_tail: jobFullLogs[jobId]
            .map((l) => `[${l.timestamp} ${l.level}] ${l.message}`)
            .join('\n'),
        };

        snap.batch_analysis[batchId] = {};
        for (const g of geoms) {
          const gRows = generatedRows.filter((r) => r.geometry === g);
          const tmpl =
            templateAnalysisByDem[g] || Object.values(templateAnalysisByDem)[0] || {};
          snap.batch_analysis[batchId][g] = {
            ...JSON.parse(JSON.stringify(tmpl)),
            batch_id: batchId,
            demonstrator: g,
            available_demonstrators: geoms,
            rows: gRows,
            completed_rows: gRows,
          };
        }
        return;
      }

      const c = dryRunCases[currentCaseIdx];
      const dem =
        snap.demonstrators.find((d) => d.id === c.geometry) || snap.demonstrators[0];
      const dof = dem?.simulation_parameters?.general_parameters?.dof_per_node || 3;
      const rows = dem?.matrices?.matrix_k?.rows || 1800;
      const fineNodes = Math.max(10, Math.round(rows / dof));
      const fineEdges = Math.round(fineNodes * 9.55);
      const coarseNodes = Math.min(
        fineNodes,
        Math.round(
          ((c.coarsen_inferior_limit || 100) + (c.coarsen_superior_limit || 175)) / 2
        )
      );
      const coarseEdges = Math.max(coarseNodes - 1, Math.round(coarseNodes * 6.5));
      const levelsCount = Math.max(
        1,
        Math.round(Math.log(fineNodes / Math.max(1, coarseNodes)) / Math.log(1.8))
      );

      const stageId = stageNames[currentSubStage];
      job.current_stage = stageId;
      const dt = Number((stepMs / 1000).toFixed(2));
      job.stage_durations_sec = {
        ...job.stage_durations_sec,
        [stageId]: Number(((job.stage_durations_sec?.[stageId] || 0) + dt).toFixed(2)),
      };
      job.elapsed_sec = Number(((job.elapsed_sec || 0) + dt).toFixed(2));
      const completedSteps = currentCaseIdx * 5 + currentSubStage + 1;
      job.stage_progress = Math.min(
        98,
        Math.max(5, Math.round((completedSteps / (totalCases * 5)) * 100))
      );

      const prefix = `[${currentCaseIdx + 1}/${dryRunCases.length}] (${c.case_key})`;
      if (currentSubStage === 0) {
        job.telemetry = {
          initial_nodes: fineNodes,
          initial_edges: fineEdges,
          coarse_nodes: coarseNodes,
          coarse_edges: coarseEdges,
          coarsening_levels: levelsCount,
          coarse_parts: kTarget,
        };
        appendLogs([
          ['INFO', `${prefix} Converting matrices to graphs (${c.demonstrator_dir})`],
          [
            'INFO',
            `Graph G_K with ${fineNodes} nodes and ${fineEdges} edges created from K matrix`,
          ],
        ]);
      } else if (currentSubStage === 1) {
        appendLogs([
          ['INFO', `${prefix} Coarsening Heavy Edge Matching (${coarsenStrat})`],
          [
            'VERBOSE',
            `Coarse graph has ${coarseNodes} nodes and ${coarseEdges} edges with ${levelsCount} levels`,
          ],
        ]);
      } else if (currentSubStage === 2) {
        appendLogs([
          ['INFO', `${prefix} Running ${c.algorithm} (${c.partitioning_strategy})`],
          ['VERBOSE', `Partitioning on coarse graph produced ${kTarget} parts`],
        ]);
      } else if (currentSubStage === 3) {
        appendLogs([['INFO', `${prefix} Uncoarsening Kernighan-Lin`]]);
      } else if (currentSubStage === 4) {
        appendLogs([
          ['INFO', `${prefix} Permuting matrices`],
          ['INFO', `${prefix} Completed case ${c.case_key}`],
        ]);
      }

      currentSubStage += 1;
      if (currentSubStage >= 5) {
        currentSubStage = 0;
        currentCaseIdx += 1;
      }
    }, stepMs);

    return {
      ...job,
      logs: jobFullLogs[jobId].slice(0),
    };
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
