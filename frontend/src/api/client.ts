import {
  CoarseningPreviewResponse,
  Demonstrator,
  SimulationConfig,
  SimulationJob,
  SimulationParameters,
} from '../types/pipeline';

async function requestJson<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    headers: {
      'Content-Type': 'application/json',
      ...(options?.headers || {}),
    },
    ...options,
  });
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
  return res.json() as Promise<T>;
}

export const api = {
  listDemonstrators: () =>
    requestJson<{ demonstrators: Demonstrator[] }>('/api/demonstrators'),

  getDemonstrator: (demId: string) =>
    requestJson<Demonstrator>(`/api/demonstrators/${encodeURIComponent(demId)}`),

  createDemonstrator: (name: string, cloneFrom?: string) =>
    requestJson<Demonstrator>('/api/demonstrators', {
      method: 'POST',
      body: JSON.stringify({ name, clone_from: cloneFrom }),
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

  previewCoarsening: (demId: string, params: SimulationParameters) =>
    requestJson<CoarseningPreviewResponse>(
      `/api/demonstrators/${encodeURIComponent(demId)}/preview-coarsening`,
      {
        method: 'POST',
        body: JSON.stringify(params),
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

  generateDemoMatrices: (
    demId: string,
    opts: { nx_nodes: number; ny_nodes: number; nz_nodes: number; dof_per_node: number }
  ) =>
    requestJson<Demonstrator>(
      `/api/demonstrators/${encodeURIComponent(demId)}/matrices/generate-demo`,
      {
        method: 'POST',
        body: JSON.stringify(opts),
      }
    ),

  uploadMatrixFile: async (demId: string, file: File): Promise<Demonstrator> => {
    const formData = new FormData();
    formData.append('file', file);
    const res = await fetch(
      `/api/demonstrators/${encodeURIComponent(demId)}/matrices/upload`,
      {
        method: 'POST',
        body: formData,
      }
    );
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.detail || `Upload failed (${res.status})`);
    }
    return res.json();
  },

  // Execution
  runSimulation: (
    demonstratorDir: string,
    parametersOverride?: SimulationParameters
  ) =>
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
    requestJson<SimulationJob>(
      `/api/execution/jobs/${encodeURIComponent(jobId)}/cancel`,
      { method: 'POST' }
    ),

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

  getBatchRunDetail: (batchId: string) =>
    requestJson<any>(`/api/batch/runs/${encodeURIComponent(batchId)}`),

  // Results
  listDemonstratorRuns: (demId: string) =>
    requestJson<{ demonstrator_id: string; runs: any[] }>(
      `/api/results/demonstrators/${encodeURIComponent(demId)}/runs`
    ),

  getSingleRunDetail: (resultDir: string) =>
    requestJson<any>(
      `/api/results/run-detail?result_dir=${encodeURIComponent(resultDir)}`
    ),

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

