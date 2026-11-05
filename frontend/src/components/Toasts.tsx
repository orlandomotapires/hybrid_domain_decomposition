import React, { createContext, useCallback, useContext, useRef, useState } from 'react';
import { AlertTriangle, CheckCircle2, Info, X } from 'lucide-react';

export type ToastKind = 'success' | 'error' | 'info';

export interface ToastAction {
  label: string;
  onClick: () => void;
}

interface ToastItem {
  id: number;
  kind: ToastKind;
  message: string;
  action?: ToastAction;
}

interface ToastOptions {
  action?: ToastAction;
  /** Auto-dismiss delay in ms. Errors default to 0 (stay until dismissed). */
  durationMs?: number;
}

interface ToastApi {
  success: (message: string, opts?: ToastOptions) => number;
  error: (message: string, opts?: ToastOptions) => number;
  info: (message: string, opts?: ToastOptions) => number;
  dismiss: (id: number) => void;
}

const ToastContext = createContext<ToastApi | null>(null);

export const useToast = (): ToastApi => {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error('useToast must be used inside <ToastProvider>');
  return ctx;
};

const DEFAULT_DURATION: Record<ToastKind, number> = {
  success: 4000,
  info: 5000,
  error: 0,
};

const KIND_STYLES: Record<ToastKind, { box: string; icon: React.ReactNode }> = {
  success: {
    box: 'bg-slate-900/95 border-emerald-500/60 text-slate-100',
    icon: <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />,
  },
  info: {
    box: 'bg-slate-900/95 border-indigo-500/60 text-slate-100',
    icon: <Info className="w-4 h-4 text-indigo-400 shrink-0" />,
  },
  error: {
    box: 'bg-rose-950/95 border-rose-500/70 text-rose-100',
    icon: <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0" />,
  },
};

export const ToastProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const nextId = useRef(1);

  const dismiss = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const push = useCallback(
    (kind: ToastKind, message: string, opts?: ToastOptions) => {
      const id = nextId.current++;
      setToasts((prev) => [...prev.slice(-4), { id, kind, message, action: opts?.action }]);
      const duration = opts?.durationMs ?? (opts?.action ? 7000 : DEFAULT_DURATION[kind]);
      if (duration > 0) {
        window.setTimeout(() => dismiss(id), duration);
      }
      return id;
    },
    [dismiss]
  );

  const api = React.useMemo<ToastApi>(
    () => ({
      success: (m, o) => push('success', m, o),
      error: (m, o) => push('error', m, o),
      info: (m, o) => push('info', m, o),
      dismiss,
    }),
    [push, dismiss]
  );

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div
        className="fixed top-20 right-6 z-[60] flex flex-col gap-2 w-[min(420px,calc(100vw-3rem))]"
        role="status"
        aria-live="polite"
      >
        {toasts.map((t) => {
          const style = KIND_STYLES[t.kind];
          return (
            <div
              key={t.id}
              role={t.kind === 'error' ? 'alert' : undefined}
              className={`border px-4 py-2.5 rounded-xl shadow-2xl flex items-start gap-2.5 text-xs font-medium ${style.box}`}
            >
              {style.icon}
              <span className="flex-1 break-words leading-relaxed">{t.message}</span>
              {t.action && (
                <button
                  type="button"
                  onClick={() => {
                    t.action!.onClick();
                    dismiss(t.id);
                  }}
                  className="shrink-0 px-2 py-0.5 rounded-md bg-indigo-600 hover:bg-indigo-500 text-white font-semibold"
                >
                  {t.action.label}
                </button>
              )}
              <button
                type="button"
                onClick={() => dismiss(t.id)}
                className="shrink-0 p-0.5 rounded text-slate-400 hover:text-white"
                aria-label="Dismiss notification"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
};
