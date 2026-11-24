import { useStreamStatus } from "@/api/stream";
import type { StreamStatus } from "@/api/stream";
import { cn } from "@/lib/utils";

export interface StatusView {
  label: string;
  hint: string;
  dot: string;
}

/** Header indicator text for the realtime connection (P3-6). */
export function statusView(status: StreamStatus): StatusView {
  if (status.connected) {
    return {
      label: "Online",
      hint: "Updates arrive in real time",
      dot: "bg-emerald-500 shadow-[0_0_0_3px_rgba(16,185,129,0.16)]",
    };
  }
  if (status.fallback) {
    return {
      label: "Backup polling",
      hint: "Connection unavailable: lists refresh every 15 seconds",
      dot: "bg-amber-500 shadow-[0_0_0_3px_rgba(245,158,11,0.16)]",
    };
  }
  return {
    label: "No connection",
    hint: "Reconnecting. Lists may lag",
    dot: "bg-red-500 shadow-[0_0_0_3px_rgba(239,68,68,0.16)]",
  };
}

export function RealtimeStatus() {
  const status = useStreamStatus();
  const view = statusView(status);
  return (
    <span
      role="status"
      title={view.hint}
      aria-label={`Realtime: ${view.label}`}
      className="inline-flex items-center gap-1.5 rounded-full border border-slate-200/80 bg-slate-50/70 px-2.5 py-1 text-[11px] font-medium text-slate-600 dark:border-slate-800 dark:bg-[#14171D] dark:text-slate-400"
    >
      <span className={cn("h-1.5 w-1.5 rounded-full", view.dot)} aria-hidden="true" />
      <span className="hidden md:inline">{view.label}</span>
    </span>
  );
}
