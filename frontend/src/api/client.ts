import {
  CoarseningPreviewResponse,
  Demonstrator,
  LibraryMatrix,
  SimulationConfig,
  SimulationJob,
  SimulationParameters,
} from '../types/pipeline';

const BACKEND_UNREACHABLE =
  'Studio backend not reachable — start it locally with ./run.sh --ui';

async function requestJson<T>(url: string, options?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(url, {
      headers: {
        'Content-Type': 'application/json',
        ...(options?.headers || {}),
      },
      ...options,
    });
  } catch {
    throw new Error(BACKEND_UNREACHABLE);
  }
  if (!res.ok) {
    let errMsg = `HTTP ${res.status}`;
    try {
      const data = await res.json();
      errMsg = data.detail || data.error || errMsg;
    } catch {
      // ignore
    }
    throw new Error(errMsg);
  }
  const contentType = res.headers.get('content-type') || '';
  if (!contentType.includes('application/json')) {
    throw new Error(BACKEND_UNREACHABLE);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: async (): Promise<boolean> => {
    try {
      const res = await fetch('/api/health', { cache: 'no-store' });
      return res.ok;
    } catch {
      return false;
    }
  },

  listDemonstrators: () =>
    requestJson<{ demonstrators: Demonstrator[] }>('/api/demonstrators'),

  getDemonstrator: (demId: string) =>
    requestJson<Demonstrator>(`/api/demonstrators/${encodeURIComponent(demId)}`),

  /** Create a simulation. Empty name -> next free simulation_NN. */
  createDemonstrator: (name: string | null, cloneFrom?: string, matrix?: string) =>
    requestJson<Demonstrator>('/api/demonstrators', {
      method: 'POST',
      body: JSON.stringify({ name: name || null, clone_from: cloneFrom, matrix }),
    }),

  renameDemonstrator: (demId: string, newName: string) =>
    requestJson<Demonstrator>(`/api/demonstrators/${encodeURIComponent(demId)}/rename`, {
      method: 'PUT',
      body: JSON.stringify({ new_name: newName }),
    }),

  deleteDemonstrator: (demId: string) =>
    requestJson<{ deleted: string; remaining_demonstrators: string[] }>(
      `/api/demonstrators/${encodeURIComponent(demId)}`,
      { method: 'DELETE' }
    ),

  updateConfig: (demId: string, config: SimulationConfig) =>
    requestJson<Demonstrator>(`/api/demonstrators/${encodeURIComponent(demId)}/config`, {
      method: 'PUT',
      body: JSON.stringify(config),
    }),

  updateParameters: (demId: string, params: SimulationParameters) =>
    requestJson<Demonstrator>(`/api/demonstrators/${encodeURIComponent(demId)}/parameters`, {
      method: 'PUT',
      body: JSON.stringify(params),
    }),

  getPreset: (demId: string, presetFile: string) =>
    requestJson<{ filename: string; parameters: SimulationParameters }>(
      `/api/demonstrators/${encodeURIComponent(demId)}/presets/${encodeURIComponent(presetFile)}`
    ),

  savePreset: (
    demId: string,
    filename: string,
    parameters: SimulationParameters,
    setActive = true
  ) =>
    requestJson<Demonstrator>(`/api/demonstrators/${encodeURIComponent(demId)}/presets`, {
      method: 'POST',
      body: JSON.stringify({ filename, parameters, set_active: setActive }),
    }),

  deletePreset: (demId: string, presetFile: string) =>
    requestJson<Demonstrator>(
      `/api/demonstrators/${encodeURIComponent(demId)}/presets/${encodeURIComponent(presetFile)}`,
      { method: 'DELETE' }
    ),

  /** Coarsening preview on `matrix` (the possibly unsaved pick) or the simulation's saved matrix. */
  previewCoarsening: (demId: string, params: SimulationParameters, matrix?: string | null) =>
    requestJson<CoarseningPreviewResponse>(
      `/api/demonstrators/${encodeURIComponent(demId)}/preview-coarsening`,
      {
        method: 'POST',
        body: JSON.stringify(matrix ? { ...params, _matrix: matrix } : params),
      }
    ),

  validateParameters: (params: SimulationParameters) =>
    requestJson<{
      valid: boolean;
      normalized_parameters?: SimulationParameters;
      estimates?: Demonstrator['estimates'];
      error?: string;
    }>('/api/demonstrators/validate-parameters', {
      method: 'POST',
      body: JSON.stringify(params),
    }),

  // Shared matrix library (matrices/<matrix_id>/)
  listMatrixLibrary: () => requestJson<{ matrices: LibraryMatrix[] }>('/api/matrix-library'),

  generateDemoMatrix: (opts: {
    nx_nodes: number;
    ny_nodes: number;
    nz_nodes: number;
    dof_per_node: number;
    name?: string;
  }) =>
    requestJson<LibraryMatrix>('/api/matrix-library/generate-demo', {
      method: 'POST',
      body: JSON.stringify(opts),
    }),

  uploadMatrix: async (name: string, file: File): Promise<LibraryMatrix> => {
    const formData = new FormData();
    formData.append('name', name);
    formData.append('file', file);
    let res: Response;
    try {
      res = await fetch('/api/matrix-library/upload', { method: 'POST', body: formData });
    } catch {
      throw new Error(BACKEND_UNREACHABLE);
    }
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.detail || `Upload failed (${res.status})`);
    }
    return res.json();
  },

  deleteLibraryMatrix: (matrixId: string) =>
    requestJson<{ deleted: string }>(`/api/matrix-library/${encodeURIComponent(matrixId)}`, {
      method: 'DELETE',
    }),

  // Execution
  runSimulation: (demonstratorDir: string, parametersOverride?: SimulationParameters) =>
    requestJson<SimulationJob>('/api/execution/run', {
      method: 'POST',
      body: JSON.stringify({
        demonstrator_dir: demonstratorDir,
        parameters_override: parametersOverride,
      }),
    }),

  listJobs: () => requestJson<{ jobs: SimulationJob[] }>('/api/execution/jobs'),

  getJob: (jobId: string, logOffset = 0) =>
    requestJson<SimulationJob>(
      `/api/execution/jobs/${encodeURIComponent(jobId)}?log_offset=${logOffset}`
    ),

  cancelJob: (jobId: string) =>
    requestJson<SimulationJob>(`/api/execution/jobs/${encodeURIComponent(jobId)}/cancel`, {
      method: 'POST',
    }),

  deleteJob: (jobId: string, deleteFiles = false) =>
    requestJson<{ deleted: string }>(
      `/api/execution/jobs/${encodeURIComponent(jobId)}?delete_files=${deleteFiles}`,
      { method: 'DELETE' }
    ),

  // Batch
  getBatchConfig: () => requestJson<any>('/api/batch/config'),

  updateBatchConfig: (config: any) =>
    requestJson<any>('/api/batch/config', {
      method: 'PUT',
      body: JSON.stringify(config),
    }),

  startBatchRun: (stopOnError = false) =>
    requestJson<SimulationJob>('/api/batch/run', {
      method: 'POST',
      body: JSON.stringify({ stop_on_error: stopOnError }),
    }),

  listBatchRuns: () => requestJson<{ batch_runs: any[] }>('/api/batch/runs'),

  /** Median per-case durations from past batch runs (keys: "matrix__alg__scale" and "alg__scale"). */
  getBatchEstimates: () =>
    requestJson<{
      by_case: Record<string, { median_seconds: number; samples: number }>;
      by_algorithm_scale: Record<string, { median_seconds: number; samples: number }>;
      sample_count: number;
      batch_count: number;
    }>('/api/batch/estimates'),

  getBatchRunDetail: (batchId: string) =>
    requestJson<any>(`/api/batch/runs/${encodeURIComponent(batchId)}`),

  // Results
  listDemonstratorRuns: (demId: string) =>
    requestJson<{ demonstrator_id: string; runs: any[] }>(
      `/api/results/demonstrators/${encodeURIComponent(demId)}/runs`
    ),

  getSingleRunDetail: (resultDir: string) =>
    requestJson<any>(`/api/results/run-detail?result_dir=${encodeURIComponent(resultDir)}`),

  getBatchAnalysis: (batchId: string, demonstrator: string) =>
    requestJson<any>(
      `/api/results/batch/${encodeURIComponent(batchId)}/analysis?demonstrator=${encodeURIComponent(demonstrator)}`
    ),

  // Hardware
  getHardwareStatus: () => requestJson<any>('/api/hardware/status'),

  checkDWaveQpu: (solverName: string, region: string) =>
    requestJson<any>('/api/hardware/dwave-check', {
      method: 'POST',
      body: JSON.stringify({ qpu_solver_name: solverName, qpu_region: region }),
    }),

  inspectQlmQpu: (qpuName: string) =>
    requestJson<any>('/api/hardware/qlm-inspect', {
      method: 'POST',
      body: JSON.stringify({ qlm_qpu_name: qpuName }),
    }),
};
