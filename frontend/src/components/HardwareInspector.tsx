import React, { useEffect, useState } from 'react';
import {
  CheckCircle2,
  Cpu,
  Loader2,
  Radio,
  Server,
  ShieldAlert,
  Zap,
} from 'lucide-react';
import { api } from '../api/client';
import { InfoTooltip } from './InfoTooltip';

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

  useEffect(() => {
    api.getHardwareStatus().then((res) => setHwStatus(res));
  }, []);

  const runDwaveCheck = async () => {
    setProbingDwave(true);
    try {
      const res = await api.checkDWaveQpu(dwaveSolver, dwaveRegion);
      setDwaveResult(res);
    } finally {
      setProbingDwave(false);
    }
  };

  const runQlmCheck = async () => {
    setProbingQlm(true);
    try {
      const res = await api.inspectQlmQpu(qlmQpu);
      setQlmResult(res);
    } finally {
      setProbingQlm(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Environment & SDK Readiness Matrix */}
      <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-5 space-y-4">
        <div className="flex items-center gap-2">
          <span className="px-2.5 py-0.5 text-xs font-semibold rounded-full bg-cyan-500/20 text-cyan-300 border border-cyan-500/30">
            Hardware & Backends
          </span>
          <InfoTooltip topicId="hardware-backends" onOpenWiki={onOpenWiki} />
        </div>

        {hwStatus && (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3.5">
            {Object.entries(hwStatus.backends || {}).map(([key, info]: [string, any]) => (
              <div
                key={key}
                className={`p-3.5 rounded-xl border flex items-center justify-between gap-2 ${
                  info.ready
                    ? 'bg-slate-950/80 border-emerald-500/40'
                    : 'bg-slate-950/60 border-amber-500/30'
                }`}
              >
                <span className="text-xs font-bold font-mono uppercase text-white truncate">
                  {key}
                </span>
                {info.ready ? (
                  <span className="inline-flex items-center gap-1 text-[11px] text-emerald-400 shrink-0">
                    <CheckCircle2 className="w-3.5 h-3.5" /> Ready
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1 text-[11px] text-amber-400 shrink-0">
                    <ShieldAlert className="w-3.5 h-3.5" /> Missing
                  </span>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Live Hardware Probes */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* D-Wave Leap QPU Clique Capacity Inspector */}
        <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-6 space-y-4">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-xl bg-violet-500/15 border border-violet-500/30 text-violet-400">
              <Zap className="w-5 h-5" />
            </div>
            <h3 className="text-base font-bold text-white">
              D-Wave QPU Capacity
            </h3>
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
            className="inline-flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold bg-violet-600 hover:bg-violet-500 text-white transition disabled:opacity-50"
          >
            {probingDwave ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Radio className="w-4 h-4" />
            )}
            Probe D-Wave Solver Capacity
          </button>

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
            <div className="p-2.5 rounded-xl bg-fuchsia-500/15 border border-fuchsia-500/30 text-fuchsia-400">
              <Server className="w-5 h-5" />
            </div>
            <h3 className="text-base font-bold text-white">
              QLM QPU Inspector
            </h3>
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-300 mb-1">
              Target QLM QPU Name (<code>qlm_qpu_name</code>)
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
                className="px-2.5 py-1 rounded-lg text-[11px] font-mono bg-slate-800 text-slate-300 hover:bg-slate-700"
              >
                Jiqcer5QPU
              </button>
              <button
                type="button"
                onClick={() => setQlmQpu('qat.qpus:QSolidQPU10')}
                className="px-2.5 py-1 rounded-lg text-[11px] font-mono bg-slate-800 text-slate-300 hover:bg-slate-700"
              >
                QSolidQPU10
              </button>
            </div>
          </div>

          <button
            disabled={probingQlm}
            onClick={runQlmCheck}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold bg-fuchsia-600 hover:bg-fuchsia-500 text-white transition disabled:opacity-50"
          >
            {probingQlm ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Cpu className="w-4 h-4" />
            )}
            Inspect QLM Backend
          </button>

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

