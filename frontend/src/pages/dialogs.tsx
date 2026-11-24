import { ArrowLeft } from "lucide-react";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { useDialog, useDialogs } from "@/api/timeline";
import { ChatPanel } from "@/components/dialogs/chat-panel";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { formatRelative, initials } from "@/lib/format";
import { cn } from "@/lib/utils";

type Filter = "all" | "mine" | "unassigned" | "unread" | "needs_reply";

export function DialogsPage() {
  const [params, setParams] = useSearchParams();
  const [filter, setFilter] = useState<Filter>("all");
  const [search, setSearch] = useState("");
  // The selected dialog lives in the URL (?wa=), so the browser back button
  // returns to the list, while a /dialogs?wa= link from a deal opens the chat.
  const selected = params.get("wa");

  const dialogs = useDialogs({
    assigned: filter === "mine" || filter === "unassigned" ? filter : undefined,
    unread: filter === "unread",
    needsReply: filter === "needs_reply",
    search: search || undefined,
  });
  const dialog = useDialog(selected);

  const totalUnread = dialogs.data?.items.reduce((sum, item) => sum + item.unread_count, 0) ?? 0;
  useEffect(() => {
    document.title = totalUnread > 0 ? `(${totalUnread}) TCS Leasing CRM` : "TCS Leasing CRM";
    return () => {
      document.title = "TCS Leasing CRM";
    };
  }, [totalUnread]);

  const open = (whatsappId: string) => {
    // Push, not replace: browser back returns to the list.
    setParams({ wa: whatsappId });
  };

  const back = () => {
    setParams({});
  };

  return (
    <div className="flex h-[calc(100dvh-12.5rem-env(safe-area-inset-bottom))] flex-col gap-3 md:h-[calc(100vh-7.5rem)] md:flex-row">
      <aside
        className={cn(
          "w-full flex-col gap-2.5 md:flex md:w-80 md:shrink-0",
          selected ? "hidden" : "flex",
        )}
      >
        <div className="flex flex-nowrap gap-1 overflow-x-auto pb-0.5">
          {(
            [
              ["all", "All"],
              ["mine", "Mine"],
              ["unassigned", "Unassigned"],
              ["unread", "Unread"],
              ["needs_reply", "Needs reply"],
            ] as [Filter, string][]
          ).map(([id, label]) => (
            <button
              key={id}
              type="button"
              onClick={() => setFilter(id)}
              className={cn(
                "min-h-8 shrink-0 rounded-md border px-2.5 py-1 text-xs font-medium transition-colors",
                filter === id
                  ? "border-brand-600 bg-brand-600 text-white shadow-subtle dark:border-brand-500 dark:bg-brand-500"
                  : "border-slate-200/80 bg-white text-slate-600 hover:bg-slate-50 dark:border-slate-800 dark:bg-[#121418] dark:text-slate-300",
              )}
            >
              {label}
            </button>
          ))}
        </div>
        <Input
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Search dialogs"
        />
        <div className="flex min-h-0 flex-1 flex-col gap-1.5 overflow-y-auto pr-0.5">
          {dialogs.isPending && <p className="text-xs text-slate-500">Loading…</p>}
          {dialogs.data?.items.map((item) => {
            const isSelected = selected === item.whatsapp_id;
            const displayName = item.contact_name ?? item.contact_phone ?? item.whatsapp_id;
            return (
              <button
                key={item.whatsapp_id}
                type="button"
                onClick={() => open(item.whatsapp_id)}
                className={cn(
                  "group relative rounded-lg border p-2.5 text-left text-xs transition-all",
                  isSelected
                    ? "border-brand-500/70 bg-brand-50/40 shadow-subtle dark:border-brand-500/60 dark:bg-brand-950/20"
                    : "border-slate-200/80 bg-white hover:border-slate-300 dark:border-slate-800/90 dark:bg-[#121418] dark:hover:border-slate-700",
                )}
              >
                <span className="flex items-center justify-between gap-2">
                  <span className="flex min-w-0 items-center gap-2">
                    <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-brand-600/10 text-[10px] font-bold text-brand-700 dark:bg-brand-400/15 dark:text-brand-300">
                      {initials(displayName)}
                    </span>
                    <span className="truncate text-[13px] font-semibold text-slate-900 dark:text-slate-100">
                      {displayName}
                    </span>
                  </span>
                  <span className="flex shrink-0 items-center gap-1">
                    {item.needs_reply && (
                      <span className="rounded-md bg-amber-100/90 px-1.5 py-0.5 text-[10px] font-medium text-amber-800 dark:bg-amber-950/60 dark:text-amber-300">
                        awaiting reply
                      </span>
                    )}
                    {item.unread_count > 0 && (
                      <span className="rounded-full bg-brand-600 px-1.5 py-0.5 text-[10px] font-semibold text-white dark:bg-brand-500">
                        {item.unread_count}
                      </span>
                    )}
                  </span>
                </span>
                <span className="mt-1 block truncate text-xs text-slate-500 dark:text-slate-400">
                  {item.last_message?.content ?? "No messages"}
                </span>
                <span className="mt-1 flex items-center gap-1 text-[11px] text-slate-400 dark:text-slate-500">
                  {item.last_message ? formatRelative(item.last_message.created_at) : ""}
                  {item.bot_paused ? " · Bot paused" : " · Bot replying"}
                  {item.assignee_name ? ` · ${item.assignee_name}` : ""}
                </span>
              </button>
            );
          })}
          {!dialogs.isPending && (dialogs.data?.total ?? 0) === 0 && (
            <p className="text-xs text-slate-500">No dialogs.</p>
          )}
        </div>
      </aside>

      <section
        className={cn(
          "ui-card min-h-0 flex-1 flex-col overflow-hidden",
          selected ? "flex" : "hidden md:flex",
        )}
      >
        {!selected || !dialog.data ? (
          <p className="m-auto hidden text-xs text-slate-400 md:block">
            Select a dialog on the left.
          </p>
        ) : (
          <>
            <header className="flex flex-wrap items-center gap-2 border-b border-slate-200/80 bg-slate-50/50 px-3.5 py-2.5 dark:border-slate-800/80 dark:bg-[#14171D]">
              <Button
                type="button"
                variant="ghost"
                size="icon"
                aria-label="Back to list"
                onClick={back}
                className="md:hidden"
              >
                <ArrowLeft className="h-4 w-4" />
              </Button>
              <div className="min-w-0 flex-1">
                <p className="truncate text-[13px] font-semibold text-slate-900 dark:text-slate-100">
                  {dialog.data.contact_name ?? dialog.data.whatsapp_id}
                </p>
                <p className="flex flex-wrap items-center gap-1 text-[11px] text-slate-500">
                  <span>{dialog.data.assignee_name ?? "Unassigned"}</span>
                  <span className="text-slate-400">· Changed in the deal card</span>
                </p>
              </div>
            </header>
            <ChatPanel
              key={dialog.data.whatsapp_id}
              whatsappId={dialog.data.whatsapp_id}
              contactName={dialog.data.contact_name}
            />
          </>
        )}
      </section>
    </div>
  );
}
