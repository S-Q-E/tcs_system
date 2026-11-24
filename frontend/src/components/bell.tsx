import { useNavigate } from "react-router-dom";

import type { Notification } from "@/api/tasks";
import { useNotifications, useReadAllNotifications, useReadNotification } from "@/api/tasks";
import { useToast, toastError } from "@/components/toast";
import { Button } from "@/components/ui/button";
import { formatRelative } from "@/lib/format";
import { cn } from "@/lib/utils";

const TYPE_LABEL: Record<string, string> = {
  deal_assigned: "Deal assigned",
  task_overdue: "Overdue task",
  task_due_soon: "Task due soon",
  manager_handover: "Prospect waiting for manager",
  dialog_message: "New message",
  locked_stage: "Bot hit a locked stage",
  unanswered: "Prospect waiting for reply",
  bot_paused_long: "Bot paused too long",
  automation: "Automation",
};

function target(notification: Notification): string | null {
  const payload = notification.payload;
  if (typeof payload.deal_id === "string") {
    return `/deals/${payload.deal_id}`;
  }
  if (typeof payload.whatsapp_id === "string") {
    return `/dialogs?wa=${encodeURIComponent(payload.whatsapp_id)}`;
  }
  if (typeof payload.task_id === "string") {
    return "/tasks";
  }
  return null;
}

export function BellBadge() {
  const query = useNotifications(true);
  const count = query.data?.unread_total ?? 0;
  if (count === 0) {
    return null;
  }
  return (
    <span className="absolute -right-1 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-brand-600 px-1 text-[10px] font-semibold text-white ring-2 ring-white dark:bg-brand-500 dark:ring-[#121418]">
      {count > 99 ? "99+" : count}
    </span>
  );
}

export function BellDropdown({ onClose }: { onClose: () => void }) {
  const { push } = useToast();
  const navigate = useNavigate();
  const list = useNotifications(false);
  const readOne = useReadNotification();
  const readAll = useReadAllNotifications();

  const open = (notification: Notification) => {
    if (!notification.read_at) {
      readOne.mutate(notification.id);
    }
    const to = target(notification);
    onClose();
    if (to) {
      navigate(to);
    }
  };

  return (
    <div className="absolute right-0 z-30 mt-2 max-h-96 w-80 overflow-y-auto rounded-lg border border-slate-200/90 bg-white p-1.5 text-xs shadow-elevated dark:border-slate-800 dark:bg-[#14171E]">
      <div className="flex items-center justify-between border-b border-slate-100 px-2.5 py-2 dark:border-slate-800/80">
        <p className="text-xs font-semibold text-slate-900 dark:text-slate-100">Notifications</p>
        {(list.data?.unread_total ?? 0) > 0 && (
          <button
            type="button"
            className="text-[11px] font-medium text-brand-600 hover:underline dark:text-brand-400"
            onClick={() =>
              readAll.mutate(undefined, { onError: (error) => toastError(push, error) })
            }
          >
            Mark all read
          </button>
        )}
      </div>
      <div className="my-1 flex flex-col gap-0.5">
        {(list.data?.items ?? []).map((notification) => (
          <button
            key={notification.id}
            type="button"
            onClick={() => open(notification)}
            className={cn(
              "group flex w-full items-start gap-2 rounded-md px-2.5 py-2 text-left transition-colors hover:bg-slate-50 dark:hover:bg-slate-800/50",
              !notification.read_at && "bg-brand-50/40 dark:bg-brand-950/20",
            )}
          >
            <span
              className={cn(
                "mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full",
                !notification.read_at ? "bg-brand-500" : "bg-transparent",
              )}
            />
            <span className="min-w-0 flex-1">
              <span className="block font-medium text-slate-800 dark:text-slate-100">
                {TYPE_LABEL[notification.type] ?? notification.type}
              </span>
              <span className="mt-0.5 block truncate text-[11px] text-slate-500 dark:text-slate-400">
                {typeof notification.payload.text === "string"
                  ? notification.payload.text
                  : typeof notification.payload.title === "string"
                    ? notification.payload.title
                    : ""}
              </span>
              <span className="mt-0.5 block text-[10px] text-slate-400 dark:text-slate-500">
                {formatRelative(notification.created_at)}
              </span>
            </span>
          </button>
        ))}
      </div>
      {(list.data?.items.length ?? 0) === 0 && !list.isPending && (
        <p className="px-2.5 py-6 text-center text-xs text-slate-500">No notifications yet.</p>
      )}
      <div className="border-t border-slate-100 pt-1 dark:border-slate-800/80">
        <Button variant="ghost" size="sm" className="w-full" onClick={onClose}>
          Close
        </Button>
      </div>
    </div>
  );
}
