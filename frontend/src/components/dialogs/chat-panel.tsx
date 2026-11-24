import { useEffect, useState } from "react";

import type { DialogSummary, LeadMessage, OutboxItem } from "@/api/timeline";
import {
  fetchOlderLeadMessages,
  mergeLeadMessages,
  useDialog,
  useLeadMessages,
  useMarkRead,
  useOutbox,
  usePauseBot,
  useQuickReplies,
  useResumeBot,
  useRetryOutbox,
  useSendMessage,
} from "@/api/timeline";
import { ChatComposer } from "@/components/dialogs/composer";
import { toastError, useToast } from "@/components/toast";
import { Button } from "@/components/ui/button";
import { formatDate } from "@/lib/format";
import { substituteQuickReply } from "@/lib/quick_replies";
import { cn } from "@/lib/utils";

interface ChatPanelProps {
  whatsappId: string;
  contactName?: string | null;
}

export function ChatPanel({ whatsappId, contactName = null }: ChatPanelProps) {
  const [draft, setDraft] = useState("");
  const [older, setOlder] = useState<{
    whatsappId: string;
    items: LeadMessage[];
    hasMore: boolean;
  } | null>(null);
  const [loadingOlder, setLoadingOlder] = useState(false);
  const { push } = useToast();
  const markRead = useMarkRead();
  const pauseBot = usePauseBot();
  const resumeBot = useResumeBot();
  const sendMessage = useSendMessage();
  const retryOutbox = useRetryOutbox();

  const dialog = useDialog(whatsappId);
  const messages = useLeadMessages(whatsappId);
  const outbox = useOutbox(whatsappId);
  const quickReplies = useQuickReplies();

  useEffect(() => {
    markRead.mutate(whatsappId);
    // Mark read once per opened dialog.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [whatsappId]);

  const togglePause = (current: DialogSummary) => {
    const mutate = current.bot_paused ? resumeBot : pauseBot;
    mutate.mutate(current.whatsapp_id, { onError: (error) => toastError(push, error) });
  };

  const send = (body: string) => {
    sendMessage.mutate(
      { whatsapp_id: whatsappId, body },
      {
        onSuccess: () => setDraft(""),
        onError: (error) => toastError(push, error),
      },
    );
  };

  const olderForSelected = older?.whatsappId === whatsappId ? older : null;
  const olderItems = olderForSelected?.items ?? [];
  const shownMessages = mergeLeadMessages(olderItems, messages.data?.items ?? []);
  const hasMoreOlder = olderForSelected?.hasMore ?? messages.data?.has_more ?? false;

  const loadOlder = async () => {
    const oldest = shownMessages[0];
    if (!oldest) {
      return;
    }
    setLoadingOlder(true);
    try {
      const page = await fetchOlderLeadMessages(whatsappId, oldest.id);
      setOlder({
        whatsappId,
        items: mergeLeadMessages(page.items, olderItems),
        hasMore: page.has_more,
      });
    } catch (error) {
      toastError(push, error);
    } finally {
      setLoadingOlder(false);
    }
  };

  const applyQuickReply = (body: string) => {
    setDraft(substituteQuickReply(body, contactName ?? dialog.data?.contact_name ?? null));
  };

  const retry = (item: OutboxItem) => {
    retryOutbox.mutate(
      { whatsapp_id: item.whatsapp_id, outbox_id: item.id },
      { onError: (error) => toastError(push, error) },
    );
  };

  if (!dialog.data) {
    return (
      <div className="flex h-full min-h-0 flex-col items-center justify-center">
        {dialog.isPending ? (
          <p className="text-xs text-slate-500">Loading…</p>
        ) : (
          <p className="text-xs text-slate-500">Dialog unavailable.</p>
        )}
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex items-center gap-2 border-b border-slate-200/80 px-3.5 py-2 dark:border-slate-800/80">
        <span className="inline-flex min-w-0 flex-1 items-center gap-1.5 truncate text-xs font-medium text-slate-600 dark:text-slate-300">
          <span
            className={cn(
              "h-2 w-2 rounded-full",
              dialog.data.bot_paused ? "bg-amber-500" : "bg-emerald-500",
            )}
          />
          {dialog.data.bot_paused ? "Bot paused" : "Bot replying"}
        </span>
        <Button
          size="sm"
          variant="secondary"
          disabled={pauseBot.isPending || resumeBot.isPending}
          onClick={() => togglePause(dialog.data)}
        >
          {dialog.data.bot_paused ? "Resume bot" : "Pause bot"}
        </Button>
      </div>

      {dialog.data.bot_paused && (
        <div className="flex items-center justify-between gap-2 border-b border-amber-200/80 bg-amber-50/80 px-3.5 py-2 text-xs text-amber-900 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-200">
          <span>Bot paused. The prospect will not receive automatic replies.</span>
          <Button
            size="sm"
            variant="secondary"
            disabled={resumeBot.isPending}
            onClick={() => togglePause(dialog.data)}
          >
            Return to bot
          </Button>
        </div>
      )}

      <div className="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto p-3.5">
        {messages.isPending && <p className="text-xs text-slate-500">Loading…</p>}
        {hasMoreOlder && (
          <Button
            size="sm"
            variant="secondary"
            className="self-center"
            disabled={loadingOlder}
            onClick={() => void loadOlder()}
          >
            Show earlier
          </Button>
        )}
        {shownMessages.map((message) => (
          <div
            key={message.id}
            className={cn(
              "max-w-[85%] rounded-lg px-3 py-2 text-[13px]",
              message.direction === "in"
                ? "border border-slate-200/80 bg-slate-50 text-slate-800 dark:border-slate-800 dark:bg-[#171A22] dark:text-slate-100"
                : "ml-auto bg-brand-600 text-white shadow-subtle dark:bg-brand-500",
            )}
          >
            <p className="whitespace-pre-wrap leading-relaxed">{message.content ?? ""}</p>
            <p className="mt-1 font-mono text-[10px] opacity-75">
              {message.message_type === "manager" ? "Manager · " : ""}
              {message.stage_at_moment ? `${message.stage_at_moment} · ` : ""}
              {formatDate(message.created_at)}
            </p>
          </div>
        ))}
        {(outbox.data?.items ?? [])
          .filter((item) => item.status !== "sent")
          .map((item) => (
            <div
              key={item.id}
              className={cn(
                "ml-auto max-w-[85%] rounded-lg px-3 py-2 text-[13px]",
                item.status === "failed"
                  ? "border border-red-200 bg-red-50 text-red-900 dark:border-red-900 dark:bg-red-950 dark:text-red-100"
                  : "bg-slate-200 text-slate-700 dark:bg-slate-800 dark:text-slate-200",
              )}
            >
              <p className="whitespace-pre-wrap">{item.body}</p>
              <p className="mt-1 flex items-center gap-2 font-mono text-[10px] opacity-80">
                {item.status === "failed" ? "Send failed" : "Queued…"}
                {formatDate(item.created_at)}
                {item.status === "failed" && (
                  <button
                    type="button"
                    onClick={() => retry(item)}
                    disabled={retryOutbox.isPending}
                    title="The message may already have reached the prospect — a duplicate is possible"
                    className="font-sans font-medium underline underline-offset-2"
                  >
                    Retry (duplicate possible)
                  </button>
                )}
              </p>
            </div>
          ))}
      </div>

      <div className="border-t border-slate-200/80 bg-slate-50/40 p-3 pb-[calc(0.75rem+env(safe-area-inset-bottom))] dark:border-slate-800/80 dark:bg-[#14171D] md:pb-3">
        {quickReplies.data && quickReplies.data.items.length > 0 && (
          <div className="mb-2 flex flex-wrap gap-1">
            {quickReplies.data.items.map((reply) => (
              <button
                key={reply.id}
                type="button"
                title={reply.body}
                onClick={() => applyQuickReply(reply.body)}
                className="rounded-md border border-slate-200/90 bg-white px-2.5 py-1 text-xs font-medium text-slate-600 shadow-subtle transition-colors hover:border-slate-300 hover:bg-slate-50 dark:border-slate-800 dark:bg-[#121418] dark:text-slate-300 dark:hover:bg-slate-800"
              >
                {reply.title}
              </button>
            ))}
          </div>
        )}
        <ChatComposer
          botPaused={dialog.data.bot_paused}
          sending={sendMessage.isPending}
          draft={draft}
          onDraftChange={setDraft}
          onSend={send}
        />
      </div>
    </div>
  );
}
