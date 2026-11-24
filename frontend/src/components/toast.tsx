import { createContext, useCallback, useContext, useMemo, useState } from "react";
import type { ReactNode } from "react";

export interface Toast {
  id: number;
  title: string;
  description?: string;
  variant: "default" | "error";
}

const ToastContext = createContext<{ toasts: Toast[]; push: (t: Omit<Toast, "id">) => void }>({
  toasts: [],
  push: () => undefined,
});

let nextId = 1;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const push = useCallback((toast: Omit<Toast, "id">) => {
    const id = nextId++;
    setToasts((prev) => [...prev.slice(-3), { ...toast, id }]);
    window.setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 5000);
  }, []);
  const value = useMemo(() => ({ toasts, push }), [toasts, push]);
  return <ToastContext.Provider value={value}>{children}</ToastContext.Provider>;
}

export function useToast() {
  return useContext(ToastContext);
}

export function Toaster() {
  const { toasts } = useToast();
  return (
    <div className="pointer-events-none fixed bottom-4 right-4 z-50 flex w-80 flex-col gap-2">
      {toasts.map((toast) => (
        <div
          key={toast.id}
          role="status"
          className={
            toast.variant === "error"
              ? "rounded-lg border border-red-200/90 bg-red-50/95 px-3.5 py-2.5 text-xs text-red-900 shadow-elevated backdrop-blur-md dark:border-red-900/80 dark:bg-red-950/95 dark:text-red-100"
              : "rounded-lg border border-slate-200/90 bg-white/95 px-3.5 py-2.5 text-xs text-slate-900 shadow-elevated backdrop-blur-md dark:border-slate-800 dark:bg-[#161920]/95 dark:text-slate-100"
          }
        >
          <p className="font-semibold tracking-[-0.01em]">{toast.title}</p>
          {toast.description && (
            <p className="mt-0.5 text-[11px] opacity-80">{toast.description}</p>
          )}
        </div>
      ))}
    </div>
  );
}

export function toastError(push: (t: Omit<Toast, "id">) => void, error: unknown): void {
  const message = error instanceof Error ? error.message : "Unknown error";
  push({ title: "Error", description: message, variant: "error" });
}
