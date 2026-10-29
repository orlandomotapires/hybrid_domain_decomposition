import {
  CoarseningPreviewResponse,
  Demonstrator,
  SimulationConfig,
  SimulationJob,
  SimulationParameters,
} from '../types/pipeline';
import { staticFallbackApi } from './staticFallback';

let useStaticDemo = false;

async function withFallback<T>(
  liveCall: () => Promise<T>,
  fallbackCall: () => Promise<T>
): Promise<T> {
  if (useStaticDemo) {
    return fallbackCall();
  }
  try {
    return await liveCall();
  } catch (err: any) {
    const msg = String(err?.message || '');
    // Switch to static fallback if /api is not served (e.g., GitHub Pages 404/405 or network error)
    if (
      msg.includes('HTTP 404') ||
      msg.includes('HTTP 405') ||
      msg.includes('Failed to fetch') ||
      msg.includes('NetworkError') ||
      msg.includes('Unexpected token')
    ) {
      useStaticDemo = true;
      return fallbackCall();
    }
    throw err;
  }
}

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
  const contentType = res.headers.get('content-type') || '';
  if (!contentType.includes('application/json')) {
    throw new Error('HTTP 404');
  }
  return res.json() as Promise<T>;
}

export const api = {
  isStaticDemo: () => useStaticDemo,

  listDemonstrators: () =>
    withFallback(
      () => requestJson<{ demonstrators: Demonstrator[] }>('/api/demonstrators'),
      () => staticFallbackApi.listDemonstrators()
    ),

  getDemonstrator: (demId: string) =>
    withFallback(
      () => requestJson<Demonstrator>(`/api/demonstrators/${encodeURIComponent(demId)}`),
      () => staticFallbackApi.getDemonstrator(demId)
    ),

  createDemonstrator: (name: string, cloneFrom?: string) =>
    withFallback(
      () =>
        requestJson<Demonstrator>('/api/demonstrators', {
          method: 'POST',
          body: JSON.stringify({ name, clone_from: cloneFrom }),
        }),
      () => staticFallbackApi.createDemonstrator(name, cloneFrom)
    ),

  renameDemonstrator: (demId: string, newName: string) =>
    withFallback(
      () =>
        requestJson<Demonstrator>(`/api/demonstrators/${encodeURIComponent(demId)}/rename`, {
          method: 'PUT',
          body: JSON.stringify({ new_name: newName }),
        }),
      () => staticFallbackApi.renameDemonstrator(demId, newName)
    ),

  deleteDemonstrator: (demId: string) =>
    withFallback(
      () =>
        requestJson<{ deleted: string; remaining_demonstrators: string[] }>(
          `/api/demonstrators/${encodeURIComponent(demId)}`,
          { method: 'DELETE' }
        ),
      () => staticFallbackApi.deleteDemonstrator(demId)
    ),

  updateConfig: (demId: string, config: SimulationConfig) =>
    withFallback(
      () =>
        requestJson<Demonstrator>(`/api/demonstrators/${encodeURIComponent(demId)}/config`, {
          method: 'PUT',
          body: JSON.stringify(config),
        }),
      () => staticFallbackApi.updateConfig(demId, config)
    ),

  updateParameters: (demId: string, params: SimulationParameters) =>
    withFallback(
      () =>
        requestJson<Demonstrator>(
          `/api/demonstrators/${encodeURIComponent(demId)}/parameters`,
          {
            method: 'PUT',
            body: JSON.stringify(params),
          }
        ),
      () => staticFallbackApi.updateParameters(demId, params)
    ),

  getPreset: (demId: string, presetFile: string) =>
    withFallback(
      () =>
        requestJson<{ filename: string; parameters: SimulationParameters }>(
          `/api/demonstrators/${encodeURIComponent(demId)}/presets/${encodeURIComponent(presetFile)}`
        ),
      () => staticFallbackApi.getPreset(demId, presetFile)
    ),

  savePreset: (
    demId: string,
    filename: string,
    parameters: SimulationParameters,
    setActive = true
  ) =>
    withFallback(
      () =>
        requestJson<Demonstrator>(`/api/demonstrators/${encodeURIComponent(demId)}/presets`, {
          method: 'POST',
          body: JSON.stringify({ filename, parameters, set_active: setActive }),
        }),
      () => staticFallbackApi.savePreset(demId, filename, parameters, setActive)
    ),

  deletePreset: (demId: string, presetFile: string) =>
    withFallback(
      () =>
        requestJson<Demonstrator>(
          `/api/demonstrators/${encodeURIComponent(demId)}/presets/${encodeURIComponent(presetFile)}`,
          { method: 'DELETE' }
        ),
      () => staticFallbackApi.deletePreset(demId, presetFile)
    ),

  previewCoarsening: (demId: string, params: SimulationParameters) =>
    withFallback(
      () =>
        requestJson<CoarseningPreviewResponse>(
          `/api/demonstrators/${encodeURIComponent(demId)}/preview-coarsening`,
          {
            method: 'POST',
            body: JSON.stringify(params),
          }
        ),
      () => staticFallbackApi.previewCoarsening(demId, params)
    ),

  validateParameters: (params: SimulationParameters) =>
    withFallback(
      () =>
        requestJson<{
          valid: boolean;
          normalized_parameters?: SimulationParameters;
          estimates?: Demonstrator['estimates'];
          error?: string;
        }>('/api/demonstrators/validate-parameters', {
          method: 'POST',
          body: JSON.stringify(params),
        }),
      () => staticFallbackApi.validateParameters(params)
    ),

  generateDemoMatrices: (
    demId: string,
    opts: { nx_nodes: number; ny_nodes: number; nz_nodes: number; dof_per_node: number }
  ) =>
    withFallback(
      () =>
        requestJson<Demonstrator>(
          `/api/demonstrators/${encodeURIComponent(demId)}/matrices/generate-demo`,
          {
            method: 'POST',
            body: JSON.stringify(opts),
          }
        ),
      () => staticFallbackApi.generateDemoMatrices(demId, opts)
    ),

  uploadMatrixFile: async (demId: string, file: File): Promise<Demonstrator> => {
    if (useStaticDemo) {
      return staticFallbackApi.getDemonstrator(demId);
    }
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
    withFallback(
      () =>
        requestJson<SimulationJob>('/api/execution/run', {
          method: 'POST',
          body: JSON.stringify({
            demonstrator_dir: demonstratorDir,
            parameters_override: parametersOverride,
          }),
        }),
      () => staticFallbackApi.runSimulation(demonstratorDir, parametersOverride)
    ),

  listJobs: () =>
    withFallback(
      () => requestJson<{ jobs: SimulationJob[] }>('/api/execution/jobs'),
      () => staticFallbackApi.listJobs()
    ),

  getJob: (jobId: string, logOffset = 0) =>
    withFallback(
      () =>
        requestJson<SimulationJob>(
          `/api/execution/jobs/${encodeURIComponent(jobId)}?log_offset=${logOffset}`
        ),
      () => staticFallbackApi.getJob(jobId)
    ),

  cancelJob: (jobId: string) =>
    withFallback(
      () =>
        requestJson<SimulationJob>(
          `/api/execution/jobs/${encodeURIComponent(jobId)}/cancel`,
          { method: 'POST' }
        ),
      () => staticFallbackApi.cancelJob(jobId)
    ),

  deleteJob: (jobId: string, deleteFiles = false) =>
    withFallback(
      () =>
        requestJson<{ deleted: string }>(
          `/api/execution/jobs/${encodeURIComponent(jobId)}?delete_files=${deleteFiles}`,
          { method: 'DELETE' }
        ),
      () => staticFallbackApi.deleteJob(jobId)
    ),

  // Batch
  getBatchConfig: () =>
    withFallback(
      () => requestJson<any>('/api/batch/config'),
      () => staticFallbackApi.getBatchConfig()
    ),

  updateBatchConfig: (config: any) =>
    withFallback(
      () =>
        requestJson<any>('/api/batch/config', {
          method: 'PUT',
          body: JSON.stringify(config),
        }),
      () => staticFallbackApi.updateBatchConfig(config)
    ),

  startBatchRun: (stopOnError = false) =>
    withFallback(
      () =>
        requestJson<SimulationJob>('/api/batch/run', {
          method: 'POST',
          body: JSON.stringify({ stop_on_error: stopOnError }),
        }),
      () => staticFallbackApi.startBatchRun()
    ),

  listBatchRuns: () =>
    withFallback(
      () => requestJson<{ batch_runs: any[] }>('/api/batch/runs'),
      () => staticFallbackApi.listBatchRuns()
    ),

  getBatchRunDetail: (batchId: string) =>
    withFallback(
      () => requestJson<any>(`/api/batch/runs/${encodeURIComponent(batchId)}`),
      () => staticFallbackApi.getBatchRunDetail(batchId)
    ),

  // Results
  listDemonstratorRuns: (demId: string) =>
    withFallback(
      () =>
        requestJson<{ demonstrator_id: string; runs: any[] }>(
          `/api/results/demonstrators/${encodeURIComponent(demId)}/runs`
        ),
      () => staticFallbackApi.listDemonstratorRuns(demId)
    ),

  getSingleRunDetail: (resultDir: string) =>
    withFallback(
      () =>
        requestJson<any>(
          `/api/results/run-detail?result_dir=${encodeURIComponent(resultDir)}`
        ),
      () => staticFallbackApi.getSingleRunDetail(resultDir)
    ),

  getBatchAnalysis: (batchId: string, demonstrator: string) =>
    withFallback(
      () =>
        requestJson<any>(
          `/api/results/batch/${encodeURIComponent(batchId)}/analysis?demonstrator=${encodeURIComponent(demonstrator)}`
        ),
      () => staticFallbackApi.getBatchAnalysis(batchId, demonstrator)
    ),

  // Hardware
  getHardwareStatus: () =>
    withFallback(
      () => requestJson<any>('/api/hardware/status'),
      () => staticFallbackApi.getHardwareStatus()
    ),

  checkDWaveQpu: (solverName: string, region: string) =>
    withFallback(
      () =>
        requestJson<any>('/api/hardware/dwave-check', {
          method: 'POST',
          body: JSON.stringify({ qpu_solver_name: solverName, qpu_region: region }),
        }),
      () => staticFallbackApi.checkDWaveQpu(solverName, region)
    ),

  inspectQlmQpu: (qpuName: string) =>
    withFallback(
      () =>
        requestJson<any>('/api/hardware/qlm-inspect', {
          method: 'POST',
          body: JSON.stringify({ qlm_qpu_name: qpuName }),
        }),
      () => staticFallbackApi.inspectQlmQpu(qpuName)
    ),
};
