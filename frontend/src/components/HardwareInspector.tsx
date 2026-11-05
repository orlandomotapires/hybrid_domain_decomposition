import React, { useEffect, useState } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  Cpu,
  KeyRound,
  Loader2,
  Package,
  Radio,
  Server,
  ShieldAlert,
  Terminal,
  XCircle,
  Zap,
} from 'lucide-react';
import { api } from '../api/client';
import { InfoTooltip } from './InfoTooltip';

interface ProbeRecord {
  ok: boolean;
  message: string;
  at: string;
}

const PROBE_KEY: Record<string, string> = {
  qa_hardware: 'studio-probe-qa_hardware',
  qaoa_hardware: 'studio-probe-qaoa_hardware',
};

function loadProbe(backend: string): ProbeRecord | null {
  try {
    const raw = localStorage.getItem(PROBE_KEY[backend]);
    return raw ? (JSON.parse(raw) as ProbeRecord) : null;
  } catch {
    return null;
  }
}

function saveProbe(backend: string, rec: ProbeRecord): void {
  try {
    localStorage.setItem(PROBE_KEY[backend], JSON.stringify(rec));
  } catch {
    // ignore
  }
}

const STATUS_UI: Record<string, { label: string; cls: string; border: string; Icon: typeof CheckCircle2 }> = {
  ready: { label: 'Ready', cls: 'text-emerald-400', border: 'border-emerald-500/40', Icon: CheckCircle2 },
  configured: { label: 'Configured', cls: 'text-slate-200', border: 'border-slate-600', Icon: KeyRound },
  needs_credentials: { label: 'Needs credentials', cls: 'text-amber-400', border: 'border-amber-500/40', Icon: AlertTriangle },
  missing_sdk: { label: 'SDK missing', cls: 'text-rose-400', border: 'border-rose-500/40', Icon: ShieldAlert },
};

interface HardwareInspectorProps {
  onOpenWiki?: (topicId: string) => void;
}

export const HardwareInspector: React.FC<HardwareInspectorProps> = ({ onOpenWiki }) => {
  const [hwStatus, setHwStatus] = useState<any | null>(null);

  // D-Wave probe state
  const [dwaveSolver, setDwaveSolver] = useState('Advantage2_system2.1');
  const [dwaveRegion, setDwaveRegion] = useState('eu-central-1');
  const [dwaveResult, setDwaveResult] = useState<any | null>(null);
  const [probingDwave, setProbingDwave] = useState(false);

  // QLM probe state
  const [qlmQpu, setQlmQpu] = useState('qat.qpus:QSolidQPU10');
  const [qlmResult, setQlmResult] = useState<any | null>(null);
  const [probingQlm, setProbingQlm] = useState(false);

  const [probes, setProbes] = useState<Record<string, ProbeRecord | null>>(() => ({
    qa_hardware: loadProbe('qa_hardware'),
    qaoa_hardware: loadProbe('qaoa_hardware'),
  }));
  const [statusError, setStatusError] = useState<string | null>(null);

  useEffect(() => {
    api
      .getHardwareStatus()
      .then((res) => setHwStatus(res))
      .catch((err) => setStatusError(err.message));
  }, []);

  const recordProbe = (backend: string, rec: ProbeRecord) => {
    saveProbe(backend, rec);
    setProbes((prev) => ({ ...prev, [backend]: rec }));
  };

  const runDwaveCheck = async () => {
    setProbingDwave(true);
    try {
      const res = await api.checkDWaveQpu(dwaveSolver, dwaveRegion);
      setDwaveResult(res);
      recordProbe('qa_hardware', {
        ok: !!res.reachable,
        message: res.reachable
          ? `${res.solver_name}: clique capacity ${res.largest_clique_capacity}`
          : res.error || 'Unreachable',
        at: new Date().toISOString(),
      });
    } catch (err: any) {
      setDwaveResult({ reachable: false, error: err.message });
    } finally {
      setProbingDwave(false);
    }
  };

  const runQlmCheck = async () => {
    setProbingQlm(true);
    try {
      const res = await api.inspectQlmQpu(qlmQpu);
      setQlmResult(res);
      recordProbe('qaoa_hardware', {
        ok: !!res.reachable,
        message: res.reachable
          ? `${res.requested_qpu_name} reachable`
          : String(res.summary?.inspection_error || 'Unreachable'),
        at: new Date().toISOString(),
      });
    } catch (err: any) {
      setQlmResult({ reachable: false, summary: { inspection_error: err.message } });
    } finally {
      setProbingQlm(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Environment & SDK Readiness Matrix */}
      <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-5 space-y-4">
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-bold text-white">Hardware &amp; Backends</h2>
          <InfoTooltip topicId="hardware-backends" onOpenWiki={onOpenWiki} />
        </div>

        {statusError && (
          <div className="text-xs text-rose-300">Could not read backend status: {statusError}</div>
        )}

        {hwStatus && (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3.5">
            {Object.entries(hwStatus.backends || {}).map(([key, info]: [string, any]) => {
              const ui = STATUS_UI[info.status] || STATUS_UI.missing_sdk;
              const probe = probes[key];
              return (
                <div
                  key={key}
                  className={`p-3.5 rounded-xl border bg-slate-950/80 flex flex-col gap-2.5 ${ui.border}`}
                >
                  <div className="space-y-1">
                    <div className="text-xs font-bold text-white leading-snug">{info.label || key}</div>
                    <span className={`inline-flex items-center gap-1 text-xs font-semibold ${ui.cls}`}>
                      <ui.Icon className="w-3.5 h-3.5" /> {ui.label}
                    </span>
                  </div>
                  <ul className="space-y-1.5">
                    {(info.checks || []).map((c: any) => (
                      <li key={c.label} className="flex items-start gap-1.5 text-xs leading-snug">
                        {c.ok ? (
                          <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0 mt-px" />
                        ) : (
                          <XCircle className="w-3.5 h-3.5 text-rose-400 shrink-0 mt-px" />
                        )}
                        <span className="text-slate-300">
                          <span className="font-semibold text-slate-200">{c.label}:</span>{' '}
                          <span className="break-words">{c.detail}</span>
                        </span>
                      </li>
                    ))}
                  </ul>
                  {info.remote && (
                    <div className="pt-2 border-t border-slate-800 text-xs leading-snug">
                      {probe ? (
                        <span className={probe.ok ? 'text-emerald-300' : 'text-amber-300'}>
                          Last probe {new Date(probe.at).toLocaleString()}:{' '}
                          <span className="break-words">{probe.ok ? 'OK' : 'failed'} — {probe.message}</span>
                        </span>
                      ) : (
                        <span className="text-slate-400">Not probed yet — use the inspector below.</span>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {hwStatus && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <PackageTable status={hwStatus} />
          <EnvironmentPanel env={hwStatus.environment} />
        </div>
      )}

      {/* Live Hardware Probes */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* D-Wave Leap QPU Clique Capacity Inspector */}
        <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-6 space-y-4">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-xl bg-slate-800 border border-slate-700 text-indigo-300">
              <Zap className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-base font-bold text-white">
                D-Wave QPU Capacity
              </h3>
              <p className="text-xs text-slate-400">
                Largest problem the QPU can embed
              </p>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-slate-300 mb-1">
                QPU Solver Name
              </label>
              <input
                type="text"
                value={dwaveSolver}
                onChange={(e) => setDwaveSolver(e.target.value)}
                className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs font-mono text-white"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-300 mb-1">
                Leap Region
              </label>
              <input
                type="text"
                value={dwaveRegion}
                onChange={(e) => setDwaveRegion(e.target.value)}
                className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs font-mono text-white"
              />
            </div>
          </div>

          <button
            disabled={probingDwave}
            onClick={runDwaveCheck}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold bg-indigo-600 hover:bg-indigo-500 text-white transition disabled:opacity-50"
          >
            {probingDwave ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Radio className="w-4 h-4" />
            )}
            Probe D-Wave Solver Capacity
          </button>

          {!dwaveResult && !probingDwave && (
            <ProbePlaceholder
              last={probes.qa_hardware}
              lines={[
                'Probe a backend to see its capacity: connects to D-Wave Leap with your configured token and asks the solver for the largest fully-connected (clique) problem it can embed.',
                'The result is the maximum number of coarse-graph nodes a single QPU call can handle — keep the coarse graph at or below it.',
              ]}
            />
          )}

          {dwaveResult && (
            <div
              className={`p-4 rounded-xl border text-xs font-mono space-y-1.5 ${
                dwaveResult.reachable
                  ? 'bg-emerald-950/30 border-emerald-500/40 text-emerald-200'
                  : 'bg-amber-950/30 border-amber-500/40 text-amber-200'
              }`}
            >
              {dwaveResult.reachable ? (
                <>
                  <div>Resolved Solver: {dwaveResult.solver_name}</div>
                  <div>
                    Largest Dense Clique Capacity: {dwaveResult.largest_clique_capacity} logical variables
                  </div>
                </>
              ) : (
                <div>{dwaveResult.error}</div>
              )}
            </div>
          )}
        </div>

        {/* QLM / myQLM Gate-Based QPU Inspector */}
        <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-6 space-y-4">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-xl bg-slate-800 border border-slate-700 text-indigo-300">
              <Server className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-base font-bold text-white">
                QLM QPU Inspector
              </h3>
              <p className="text-xs text-slate-400">
                Qubits and topology of a QLM QPU
              </p>
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-300 mb-1">
              Target QLM QPU Name
            </label>
            <div className="flex gap-2">
              <input
                type="text"
                value={qlmQpu}
                onChange={(e) => setQlmQpu(e.target.value)}
                className="flex-1 bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs font-mono text-white"
              />
              <button
                type="button"
                onClick={() => setQlmQpu('qat.qpus:Jiqcer5QPU')}
                className="px-2.5 py-1 rounded-lg text-xs font-mono bg-slate-800 text-slate-300 hover:bg-slate-700"
              >
                Jiqcer5QPU
              </button>
              <button
                type="button"
                onClick={() => setQlmQpu('qat.qpus:QSolidQPU10')}
                className="px-2.5 py-1 rounded-lg text-xs font-mono bg-slate-800 text-slate-300 hover:bg-slate-700"
              >
                QSolidQPU10
              </button>
            </div>
          </div>

          <button
            disabled={probingQlm}
            onClick={runQlmCheck}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold bg-indigo-600 hover:bg-indigo-500 text-white transition disabled:opacity-50"
          >
            {probingQlm ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Cpu className="w-4 h-4" />
            )}
            Inspect QLM Backend
          </button>

          {!qlmResult && !probingQlm && (
            <ProbePlaceholder
              last={probes.qaoa_hardware}
              lines={[
                'Probe a backend to see its capacity: loads the named QLM / myQLM QPU and reports its qubit count and connectivity.',
                'Reachable means QAOA hardware runs can be submitted; qubit count bounds the coarse-graph size (one qubit per node and part).',
              ]}
            />
          )}

          {qlmResult && (
            <div
              className={`p-4 rounded-xl border text-xs font-mono space-y-1.5 ${
                qlmResult.reachable
                  ? 'bg-emerald-950/30 border-emerald-500/40 text-emerald-200'
                  : 'bg-amber-950/30 border-amber-500/40 text-amber-200'
              }`}
            >
              <pre className="whitespace-pre-wrap break-all">
                {JSON.stringify(qlmResult.summary, null, 2)}
              </pre>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

/* ---------------- Sub-panels ---------------- */

const ProbePlaceholder: React.FC<{ lines: string[]; last: ProbeRecord | null | undefined }> = ({ lines, last }) => (
  <div className="p-4 rounded-xl border border-dashed border-slate-700 bg-slate-950/40 text-xs text-slate-400 space-y-1.5">
    {lines.map((l) => (
      <p key={l}>{l}</p>
    ))}
    {last && (
      <p className="text-slate-300">
        Last probe {new Date(last.at).toLocaleString()}: {last.ok ? 'OK' : 'failed'} — {last.message}
      </p>
    )}
  </div>
);

interface PackageVersion {
  name: string;
  version: string | null;
  purpose: string;
}

const PackageTable: React.FC<{ status: any }> = ({ status }) => {
  const rows: PackageVersion[] = status?.package_versions || [];
  return (
    <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 space-y-3 min-w-0">
      <div className="flex items-center justify-between gap-2">
        <h3 className="flex items-center gap-2 text-sm font-bold text-white">
          <Package className="w-4 h-4 text-slate-400" />
          Packages
        </h3>
        {status?.python_version && (
          <span className="text-xs font-mono text-slate-400">Python {status.python_version}</span>
        )}
      </div>
      {rows.length === 0 ? (
        <p className="text-xs text-slate-400">Version information is not available from this backend.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-left text-xs uppercase tracking-wider text-slate-400 border-b border-slate-800">
                <th className="py-1.5 pr-3 font-semibold">Package</th>
                <th className="py-1.5 pr-3 font-semibold">Version</th>
                <th className="py-1.5 font-semibold">Used for</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/70">
              {rows.map((r) => (
                <tr key={r.name}>
                  <td className="py-1.5 pr-3 font-mono text-slate-200 whitespace-nowrap">{r.name}</td>
                  <td className="py-1.5 pr-3 font-mono whitespace-nowrap">
                    {r.version ? (
                      <span className="text-slate-200">{r.version}</span>
                    ) : (
                      <span className="text-amber-300">not installed</span>
                    )}
                  </td>
                  <td className="py-1.5 text-slate-400">{r.purpose}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

const EnvRow: React.FC<{ ok: boolean | null; label: string; children: React.ReactNode }> = ({ ok, label, children }) => (
  <li className="flex items-start gap-2 text-xs leading-snug">
    {ok === null ? (
      <span className="w-3.5 h-3.5 shrink-0 mt-px rounded-full border border-slate-600" aria-hidden="true" />
    ) : ok ? (
      <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0 mt-px" />
    ) : (
      <XCircle className="w-3.5 h-3.5 text-amber-400 shrink-0 mt-px" />
    )}
    <span className="min-w-0">
      <span className="font-semibold text-slate-200">{label}:</span>{' '}
      <span className="text-slate-300 break-words">{children}</span>
    </span>
  </li>
);

const EnvironmentPanel: React.FC<{ env: any }> = ({ env }) => {
  const dw = env?.dwave || {};
  const qlm = env?.qlmaas || {};
  return (
    <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 space-y-3 min-w-0">
      <h3 className="flex items-center gap-2 text-sm font-bold text-white">
        <Terminal className="w-4 h-4 text-slate-400" />
        Environment checks
      </h3>
      {!env ? (
        <p className="text-xs text-slate-400">Environment details are not available from this backend.</p>
      ) : (
        <>
          <div className="space-y-1.5">
            <div className="text-xs font-semibold uppercase tracking-wider text-slate-400">D-Wave Leap</div>
            <ul className="space-y-1.5">
              <EnvRow ok={!!dw.token_present} label="API token">
                {dw.token_present
                  ? dw.token_env_set
                    ? 'present (from DWAVE_API_TOKEN)'
                    : 'present (from dwave config file)'
                  : 'not found — run `dwave setup` or set DWAVE_API_TOKEN'}
              </EnvRow>
              <EnvRow ok={dw.config_file ? true : null} label="Config file">
                <span className="font-mono">{dw.config_file || 'none found'}</span>
                {dw.config_file_env ? ' (via DWAVE_CONFIG_FILE)' : ''}
              </EnvRow>
              <EnvRow ok={null} label="Profile">
                <span className="font-mono">{dw.profile || 'default'}</span>
                {dw.region ? (
                  <>
                    {' '}· region <span className="font-mono">{dw.region}</span>
                  </>
                ) : null}
              </EnvRow>
              {dw.error && (
                <EnvRow ok={false} label="Note">
                  {dw.error}
                </EnvRow>
              )}
            </ul>
          </div>
          <div className="space-y-1.5 pt-2 border-t border-slate-800">
            <div className="text-xs font-semibold uppercase tracking-wider text-slate-400">QLMaaS</div>
            <ul className="space-y-1.5">
              <EnvRow ok={!!qlm.config_file} label="Config file">
                <span className="font-mono">{qlm.config_file || `not found (expected ${qlm.expected_config_file || '~/.qlmaas/config.ini'})`}</span>
              </EnvRow>
              <EnvRow ok={qlm.env_vars?.length ? true : null} label="Environment">
                {qlm.env_vars?.length ? (
                  <span className="font-mono">{qlm.env_vars.join(', ')}</span>
                ) : (
                  'no QLMAAS_* variables set'
                )}
              </EnvRow>
            </ul>
          </div>
          {env.python_executable && (
            <div className="pt-2 border-t border-slate-800 text-xs text-slate-400 break-all">
              Python {env.python_version} · <span className="font-mono">{env.python_executable}</span>
            </div>
          )}
        </>
      )}
    </div>
  );
};
