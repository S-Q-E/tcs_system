import { useState } from "react";
import type { ReactNode } from "react";

import type { Deal } from "@/api/deals";
import {
  useContact,
  useCustomFields,
  useDeal,
  useMoveDeal,
  usePipelines,
  useSetDealTags,
  useTags,
  useUnlockDeal,
  useUpdateDeal,
  useUsersLite,
} from "@/api/deals";
import { useCreateTask } from "@/api/timeline";
import { Timeline } from "@/components/deals/timeline";
import { DealViewingPanel } from "@/components/deals/viewing-panel";
import { ChatPanel } from "@/components/dialogs/chat-panel";
import { LostReasonModal, NoteModal, WonConfirmModal } from "@/components/deals/modals";
import { useToast, toastError } from "@/components/toast";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { isoToLocalInput, localInputToIso } from "@/lib/datetime";

const BOT_FIELDS: { key: string; label: string }[] = [
  { key: "direction", label: "Unit of interest" },
  { key: "goal", label: "Move-in & budget" },
  { key: "preferred_format", label: "Bedrooms" },
  { key: "preferred_time", label: "Viewing preference" },
  { key: "last_objection", label: "Objection" },
];

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block text-xs">
      <span className="mb-1 block text-[11px] font-medium text-slate-500 dark:text-slate-400">
        {label}
      </span>
      {children}
    </label>
  );
}

function CustomValueInput({
  field,
  value,
  onChange,
}: {
  field: { key: string; label: string; type: string; options: unknown };
  value: unknown;
  onChange: (value: unknown) => void;
}) {
  if (field.type === "bool") {
    return (
      <input
        type="checkbox"
        checked={value === true}
        onChange={(event) => onChange(event.target.checked)}
      />
    );
  }
  if (field.type === "select" && Array.isArray(field.options)) {
    return (
      <select
        value={typeof value === "string" ? value : ""}
        onChange={(event) => onChange(event.target.value || null)}
        className="ui-select w-full"
      >
        <option value="">—</option>
        {field.options.map((option) => (
          <option key={String(option)} value={String(option)}>
            {String(option)}
          </option>
        ))}
      </select>
    );
  }
  if (field.type === "multiselect" && Array.isArray(field.options)) {
    const selected = Array.isArray(value) ? value.map(String) : [];
    return (
      <div className="flex flex-wrap gap-1.5">
        {field.options.map((option) => {
          const text = String(option);
          const on = selected.includes(text);
          return (
            <button
              key={text}
              type="button"
              onClick={() =>
                onChange(on ? selected.filter((item) => item !== text) : [...selected, text])
              }
              className={
                on
                  ? "rounded-md bg-brand-600 px-2 py-0.5 text-xs font-medium text-white dark:bg-brand-500"
                  : "rounded-md border border-slate-200 bg-slate-50 px-2 py-0.5 text-xs text-slate-600 dark:border-slate-800 dark:bg-slate-800/70 dark:text-slate-300"
              }
            >
              {text}
            </button>
          );
        })}
      </div>
    );
  }
  if (field.type === "number") {
    return (
      <Input
        type="number"
        value={typeof value === "number" ? value : ""}
        onChange={(event) =>
          onChange(event.target.value === "" ? null : Number(event.target.value))
        }
      />
    );
  }
  if (field.type === "date") {
    return (
      <Input
        type="date"
        value={typeof value === "string" ? value.slice(0, 10) : ""}
        onChange={(event) => onChange(event.target.value || null)}
      />
    );
  }
  return (
    <Input
      value={typeof value === "string" ? value : ""}
      onChange={(event) => onChange(event.target.value || null)}
    />
  );
}

export function DealDetail({ dealId, onClose }: { dealId: string; onClose?: () => void }) {
  const { push } = useToast();
  const dealQuery = useDeal(dealId);
  const deal = dealQuery.data ?? null;
  const contactQuery = useContact(deal?.contact_id ?? null);
  const contact = contactQuery.data ?? null;
  const users = useUsersLite();
  const tags = useTags();
  const dealFields = useCustomFields("deal");
  const pipelines = usePipelines();

  const updateDeal = useUpdateDeal();
  const moveDeal = useMoveDeal();
  const unlockDeal = useUnlockDeal();
  const setTags = useSetDealTags();
  const createTask = useCreateTask();

  const [draft, setDraft] = useState<Record<string, unknown> | null>(null);
  const [customDraft, setCustomDraft] = useState<Record<string, unknown> | null>(null);
  const [showLost, setShowLost] = useState(false);
  const [showWon, setShowWon] = useState(false);
  const [showNote, setShowNote] = useState(false);
  const [taskTitle, setTaskTitle] = useState("");
  const [taskDue, setTaskDue] = useState("");
  const [tab, setTab] = useState<"chat" | "history">("chat");

  if (dealQuery.isPending) {
    return (
      <div className="flex flex-col gap-2" aria-label="Loading deal">
        {[0, 1, 2, 3].map((index) => (
          <div
            key={index}
            className="h-14 animate-pulse rounded-lg bg-slate-100 dark:bg-slate-800"
          />
        ))}
      </div>
    );
  }
  if (dealQuery.isError || !deal) {
    return (
      <p className="text-xs text-red-600">
        Could not load the deal.{" "}
        <button type="button" className="underline" onClick={() => dealQuery.refetch()}>
          Retry
        </button>
      </p>
    );
  }

  const edit = <K extends keyof Deal>(key: K, value: Deal[K]) =>
    setDraft((prev) => ({ ...(prev ?? {}), [key]: value }));

  const saveDraft = async () => {
    if (!draft && !customDraft) {
      return;
    }
    try {
      const patch: Record<string, unknown> = { ...(draft ?? {}) };
      if (customDraft) {
        patch.custom = { ...deal.custom, ...customDraft };
      }
      await updateDeal.mutateAsync({ id: deal.id, patch });
      setDraft(null);
      setCustomDraft(null);
      push({ title: "Saved", variant: "default" });
    } catch (error) {
      toastError(push, error);
    }
  };

  const changeStage = (stageId: string) => {
    moveDeal.mutate(
      { id: deal.id, stage_id: stageId },
      { onError: (error) => toastError(push, error) },
    );
  };

  const closeLost = (reasonId: string) => {
    setShowLost(false);
    const lostStage = pipelines.data
      ?.find((item) => item.id === deal.pipeline_id)
      ?.stages.find((stage) => stage.kind === "lost");
    if (!lostStage) {
      push({ title: "Error", description: "No lost stage in this pipeline", variant: "error" });
      return;
    }
    moveDeal.mutate(
      { id: deal.id, stage_id: lostStage.id, lost_reason_id: reasonId },
      { onError: (error) => toastError(push, error) },
    );
  };

  const addTask = async () => {
    if (!taskTitle.trim()) {
      return;
    }
    try {
      await createTask.mutateAsync({
        deal_id: deal.id,
        title: taskTitle.trim(),
        due_at: localInputToIso(taskDue),
      });
      setTaskTitle("");
      setTaskDue("");
      push({ title: "Task created", variant: "default" });
    } catch (error) {
      toastError(push, error);
    }
  };

  const toggleTag = (tagId: string) => {
    const has = deal.tags.some((tag) => tag.id === tagId);
    const next = has
      ? deal.tags.filter((tag) => tag.id !== tagId).map((tag) => tag.id)
      : [...deal.tags.map((tag) => tag.id), tagId];
    setTags.mutate({ id: deal.id, tag_ids: next }, { onError: (error) => toastError(push, error) });
  };

  const dirty = draft !== null || customDraft !== null;

  return (
    <div className="flex flex-col gap-5 lg:flex-row">
      <div className="flex w-full flex-col gap-3.5 lg:w-[340px] lg:shrink-0">
        <div className="ui-card p-4">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-base font-semibold tracking-[-0.015em] text-slate-900 dark:text-slate-100">
              {contact?.name ?? "Deal"}
            </h2>
            {onClose && (
              <Button variant="ghost" size="sm" onClick={onClose}>
                Close
              </Button>
            )}
          </div>

          <div className="flex flex-col gap-3">
            <Field label="Title">
              <Input
                defaultValue={deal.title}
                key={`title-${deal.updated_at}`}
                onChange={(event) => edit("title", event.target.value)}
              />
            </Field>
            <div className="grid grid-cols-2 gap-2">
              <Field label="Amount, USD">
                <Input
                  type="number"
                  min="0"
                  defaultValue={deal.amount ?? ""}
                  key={`amount-${deal.updated_at}`}
                  onChange={(event) =>
                    edit("amount", event.target.value === "" ? null : Number(event.target.value))
                  }
                />
              </Field>
              <Field label="Viewing">
                <Input
                  type="datetime-local"
                  defaultValue={isoToLocalInput(deal.trial_at)}
                  key={`trial-${deal.updated_at}`}
                  onChange={(event) => edit("trial_at", localInputToIso(event.target.value))}
                />
              </Field>
            </div>
            <Field label="Owner">
              <select
                value={(draft?.owner_id as string) ?? deal.owner_id ?? ""}
                onChange={(event) => edit("owner_id", event.target.value || null)}
                className="ui-select w-full"
              >
                <option value="">Unassigned</option>
                {users.data?.items.map((user) => (
                  <option key={user.id} value={user.id}>
                    {user.name}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Stage">
              <StageSelect deal={deal} onChange={changeStage} />
            </Field>

            <div>
              <p className="mb-1.5 text-[11px] font-medium text-slate-500 dark:text-slate-400">
                Tags
              </p>
              <div className="flex flex-wrap gap-1">
                {tags.data?.items.map((tag) => {
                  const on = deal.tags.some((item) => item.id === tag.id);
                  return (
                    <button
                      key={tag.id}
                      type="button"
                      onClick={() => toggleTag(tag.id)}
                      className={
                        on
                          ? "rounded-md bg-brand-600 px-2 py-0.5 text-xs font-medium text-white dark:bg-brand-500"
                          : "rounded-md border border-slate-200/80 bg-slate-50 px-2 py-0.5 text-xs text-slate-600 hover:bg-slate-100 dark:border-slate-800 dark:bg-slate-800/70 dark:text-slate-300"
                      }
                    >
                      {tag.name}
                    </button>
                  );
                })}
              </div>
            </div>

            {dealFields.data && dealFields.data.items.length > 0 && (
              <div className="flex flex-col gap-2 border-t border-slate-100 pt-2 dark:border-slate-800">
                <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                  Additional fields
                </p>
                {dealFields.data.items.map((field) => (
                  <Field key={field.id} label={field.label + (field.required ? " *" : "")}>
                    <CustomValueInput
                      field={field}
                      value={
                        customDraft?.[field.key] ??
                        (deal.custom as Record<string, unknown>)[field.key]
                      }
                      onChange={(value) =>
                        setCustomDraft((prev) => ({ ...(prev ?? {}), [field.key]: value }))
                      }
                    />
                  </Field>
                ))}
              </div>
            )}

            {dirty && (
              <Button onClick={() => void saveDraft()} disabled={updateDeal.isPending}>
                Save changes
              </Button>
            )}

            <div className="flex flex-wrap gap-1.5 border-t border-slate-100 pt-2.5 dark:border-slate-800">
              <Button size="sm" onClick={() => setShowWon(true)}>
                Won
              </Button>
              <Button size="sm" variant="danger" onClick={() => setShowLost(true)}>
                Lost
              </Button>
              <Button size="sm" variant="secondary" onClick={() => setShowNote(true)}>
                Note
              </Button>
              {deal.stage_locked && (
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() =>
                    unlockDeal.mutate(deal.id, { onError: (error) => toastError(push, error) })
                  }
                >
                  Return control to bot
                </Button>
              )}
            </div>
          </div>
        </div>

        <DealViewingPanel deal={deal} contact={contact} />

        <div className="ui-card p-3.5 text-xs">
          <p className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
            Bot data
          </p>
          <dl className="grid grid-cols-2 gap-x-3 gap-y-2 text-xs">
            {BOT_FIELDS.map((field) => (
              <div key={field.key} className="flex flex-col">
                <dt className="text-[11px] text-slate-500">{field.label}</dt>
                <dd className="font-medium text-slate-800 dark:text-slate-200">
                  {String(
                    (contact?.custom as Record<string, unknown> | undefined)?.[field.key] ?? "—",
                  )}
                </dd>
              </div>
            ))}
          </dl>
          {contact?.whatsapp_id && (
            <p className="mt-2 border-t border-slate-100 pt-2 font-mono text-[11px] text-slate-500 dark:border-slate-800">
              Chat: {contact.whatsapp_id}
            </p>
          )}
        </div>
      </div>

      <div className="min-w-0 flex-1">
        <div className="mb-2.5 inline-flex rounded-md border border-slate-200/90 bg-slate-100/80 p-0.5 dark:border-slate-800 dark:bg-[#14171D]">
          {(
            [
              ["chat", "Chat"],
              ["history", "History"],
            ] as ["chat" | "history", string][]
          ).map(([id, label]) => (
            <button
              key={id}
              type="button"
              onClick={() => setTab(id)}
              className={
                tab === id
                  ? "rounded-[5px] bg-white px-3 py-1 text-xs font-medium text-slate-900 shadow-subtle dark:bg-[#1E222B] dark:text-white"
                  : "rounded-[5px] px-3 py-1 text-xs font-medium text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-200"
              }
            >
              {label}
            </button>
          ))}
        </div>
        {tab === "chat" ? (
          contact?.whatsapp_id ? (
            <div className="ui-card h-[60vh] min-h-[320px] overflow-hidden">
              <ChatPanel whatsappId={contact.whatsapp_id} contactName={contact.name} />
            </div>
          ) : (
            <p className="text-xs text-slate-500">This contact has no chat yet.</p>
          )
        ) : (
          <Timeline dealId={deal.id} />
        )}
        <div className="ui-card mt-3 flex flex-col gap-2 p-3.5">
          <p className="text-xs font-semibold text-slate-800 dark:text-slate-200">Quick task</p>
          <div className="flex flex-col gap-2 md:flex-row">
            <Input
              value={taskTitle}
              onChange={(event) => setTaskTitle(event.target.value)}
              placeholder="Call the prospect"
              className="flex-1"
            />
            <Input
              type="datetime-local"
              value={taskDue}
              onChange={(event) => setTaskDue(event.target.value)}
              className="md:w-52"
            />
            <Button
              size="sm"
              onClick={() => void addTask()}
              disabled={createTask.isPending || !taskTitle.trim()}
            >
              Add
            </Button>
          </div>
        </div>
      </div>

      {showLost && <LostReasonModal onClose={() => setShowLost(false)} onConfirm={closeLost} />}
      {showWon && (
        <WonConfirmModal
          onClose={() => setShowWon(false)}
          onConfirm={() => {
            setShowWon(false);
            updateDeal.mutate(
              { id: deal.id, patch: { status: "won" } },
              { onError: (error) => toastError(push, error) },
            );
          }}
        />
      )}
      {showNote && <NoteModal deal={deal} onClose={() => setShowNote(false)} />}
    </div>
  );
}

function StageSelect({ deal, onChange }: { deal: Deal; onChange: (stageId: string) => void }) {
  return (
    <select
      value={deal.stage_id}
      onChange={(event) => onChange(event.target.value)}
      className="ui-select w-full"
    >
      <StageOptions pipelineId={deal.pipeline_id} />
    </select>
  );
}

function StageOptions({ pipelineId }: { pipelineId: string }) {
  const pipelines = usePipelines();
  const stages = pipelines.data?.find((item) => item.id === pipelineId)?.stages ?? [];
  return (
    <>
      {stages.map((stage) => (
        <option key={stage.id} value={stage.id}>
          {stage.name}
        </option>
      ))}
    </>
  );
}
