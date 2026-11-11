/**
 * App-wide toast notifications — one consistent, auto-dismissing feedback channel for the whole app,
 * replacing the ad-hoc inline success/error banners each screen used to roll itself. Mount <ToastProvider>
 * once near the root; call useToast() anywhere for toast.success / toast.error / toast.info / toast.show.
 *
 * Accessible (polite for success/info, assertive for errors), dismissible, stacked bottom-right, and
 * capped so a burst never buries the screen. Degrades to a no-op if used outside a provider.
 */
import { CheckCircle2, Info, X, AlertTriangle } from "lucide-react";
import { createContext, useCallback, useContext, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";

export type ToastKind = "success" | "error" | "info";
type Toast = { id: number; kind: ToastKind; message: string };

type ToastApi = {
  show: (kind: ToastKind, message: string) => void;
  success: (message: string) => void;
  error: (message: string) => void;
  info: (message: string) => void;
};

const noop: ToastApi = { show: () => {}, success: () => {}, error: () => {}, info: () => {} };
const ToastContext = createContext<ToastApi>(noop);

const AUTO_DISMISS_MS = 4500;
const MAX_VISIBLE = 4;

export function useToast(): ToastApi {
  return useContext(ToastContext);
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const nextId = useRef(1);
  const timers = useRef<Map<number, ReturnType<typeof setTimeout>>>(new Map());

  const dismiss = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
    const timer = timers.current.get(id);
    if (timer) { clearTimeout(timer); timers.current.delete(id); }
  }, []);

  const show = useCallback((kind: ToastKind, message: string) => {
    const text = (message ?? "").toString().trim();
    if (!text) return;
    const id = nextId.current++;
    setToasts((prev) => [...prev.slice(-(MAX_VISIBLE - 1)), { id, kind, message: text }]);
    // Errors linger a little longer so they can be read.
    const ttl = kind === "error" ? AUTO_DISMISS_MS + 2500 : AUTO_DISMISS_MS;
    timers.current.set(id, setTimeout(() => dismiss(id), ttl));
  }, [dismiss]);

  const api = useMemo<ToastApi>(() => ({
    show,
    success: (m: string) => show("success", m),
    error: (m: string) => show("error", m),
    info: (m: string) => show("info", m),
  }), [show]);

  return (
    <ToastContext.Provider value={api}>
      {children}
      <Toaster toasts={toasts} onDismiss={dismiss} />
    </ToastContext.Provider>
  );
}

const TONE: Record<ToastKind, { border: string; text: string; Icon: typeof Info; aria: "polite" | "assertive" }> = {
  success: { border: "border-success/40", text: "text-success", Icon: CheckCircle2, aria: "polite" },
  error: { border: "border-danger/50", text: "text-danger", Icon: AlertTriangle, aria: "assertive" },
  info: { border: "border-brand/40", text: "text-brand", Icon: Info, aria: "polite" },
};

function Toaster({ toasts, onDismiss }: { toasts: Toast[]; onDismiss: (id: number) => void }) {
  if (toasts.length === 0) return null;
  return (
    <div className="pointer-events-none fixed bottom-4 right-4 z-[100] flex w-[22rem] max-w-[calc(100vw-2rem)] flex-col gap-2">
      {toasts.map((t) => {
        const tone = TONE[t.kind];
        return (
          <div key={t.id} role="status" aria-live={tone.aria}
            className={`toast-enter pointer-events-auto flex items-start gap-2 rounded-[var(--radius-app)] border ${tone.border} bg-card p-3 text-sm shadow-lg`}>
            <tone.Icon className={`mt-0.5 h-4 w-4 shrink-0 ${tone.text}`} aria-hidden />
            <span className="min-w-0 flex-1 break-words text-foreground">{t.message}</span>
            <button type="button" aria-label="Dismiss" className="shrink-0 text-muted-foreground hover:text-foreground"
              onClick={() => onDismiss(t.id)}>
              <X className="h-4 w-4" aria-hidden />
            </button>
          </div>
        );
      })}
    </div>
  );
}
