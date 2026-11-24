import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import {
  useContact,
  useContactDeals,
  useContactTimeline,
  useDeleteContact,
  useUpdateContact,
} from "@/api/contacts";
import { useCreateNote, useCustomFields, useTags, useUsersLite } from "@/api/deals";
import { api } from "@/api/client";
import { toastError, useToast } from "@/components/toast";
import { ItemBody } from "@/components/deals/timeline";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export function ContactPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { push } = useToast();
  const queryClient = useQueryClient();
  const contact = useContact(id ?? null);
  const deals = useContactDeals(id ?? null);
  const timeline = useContactTimeline(id ?? null);
  const update = useUpdateContact();
  const remove = useDeleteContact();
  const users = useUsersLite();
  const tags = useTags();
  const customDefs = useCustomFields("contact");
  const createNote = useCreateNote();
  const [noteBody, setNoteBody] = useState("");
  const [form, setForm] = useState<Record<string, string>>({});
  const [customForm, setCustomForm] = useState<Record<string, string>>({});

  if (contact.isPending) return <p className="text-xs text-slate-500">Loading contact…</p>;
  if (contact.isError || !contact.data) {
    return <p className="text-xs text-red-600">Contact not found.</p>;
  }
  const c = contact.data;

  const save = async () => {
    const patch: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(form)) {
      // The owner is changed in the deal card only (D40).
      if (k !== "owner_id" && v !== "") patch[k] = v;
    }
    if (Object.keys(customForm).length > 0) {
      patch.custom = { ...c.custom, ...customForm };
    }
    if (Object.keys(patch).length === 0) return;
    try {
      await update.mutateAsync({ id: c.id, patch });
      setForm({});
      setCustomForm({});
      push({ title: "Contact updated", variant: "default" });
    } catch (error) {
      toastError(push, error);
    }
  };

  const setTags = async (tagIds: string[]) => {
    try {
      await api.put(`/api/contacts/${c.id}/tags`, { tag_ids: tagIds });
      push({ title: "Tags updated", variant: "default" });
    } catch (error) {
      toastError(push, error);
    } finally {
      void queryClient.invalidateQueries({ queryKey: ["contact", c.id] });
      void queryClient.invalidateQueries({ queryKey: ["contacts"] });
    }
  };

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-4">
      <Link
        className="self-start text-xs font-medium text-brand-600 hover:underline dark:text-brand-400"
        to="/contacts"
      >
        ← Back to contacts
      </Link>
      <div className="ui-card p-5">
        <h1 className="text-base font-semibold tracking-[-0.015em] text-slate-900 dark:text-slate-100">
          {c.name ?? "No name"}
        </h1>
        <p className="mt-1 font-mono text-xs text-slate-500">
          {c.phone ?? "—"} · {c.email ?? "—"} · {c.whatsapp_id ?? "—"} · source: {c.source ?? "—"}
        </p>
        <div className="mt-4 grid max-w-2xl grid-cols-1 gap-3 text-xs sm:grid-cols-2">
          {(["name", "phone", "email", "source"] as const).map((field) => (
            <label key={field} className="flex flex-col gap-1">
              <span className="text-[11px] font-medium capitalize text-slate-500">{field}</span>
              <Input
                defaultValue={String(c[field] ?? "")}
                onChange={(e) => setForm((prev) => ({ ...prev, [field]: e.target.value }))}
              />
            </label>
          ))}
          <div className="flex flex-col gap-1">
            <span className="text-[11px] font-medium text-slate-500">Owner</span>
            <p className="px-1 py-1 text-xs font-medium text-slate-800 dark:text-slate-200">
              {users.data?.items.find((u) => u.id === c.owner_id)?.name ?? "Unassigned"}
            </p>
            <span className="text-[11px] text-slate-400">Changed in the deal card</span>
          </div>
        </div>
        {customDefs.data && customDefs.data.items.length > 0 && (
          <div className="mt-4 grid max-w-2xl grid-cols-1 gap-3 border-t border-slate-100 pt-3 text-xs dark:border-slate-800 sm:grid-cols-2">
            {customDefs.data.items.map((def) => (
              <label key={def.id} className="flex flex-col gap-1">
                <span className="text-[11px] font-medium text-slate-500">{def.label}</span>
                <Input
                  defaultValue={String(c.custom[def.key] ?? "")}
                  onChange={(e) =>
                    setCustomForm((prev) => ({ ...prev, [def.key]: e.target.value }))
                  }
                />
              </label>
            ))}
          </div>
        )}
        <div className="mt-4 flex flex-wrap gap-2">
          <Button size="sm" onClick={() => void save()} disabled={update.isPending}>
            Save
          </Button>
          <Button
            size="sm"
            variant="secondary"
            onClick={() => {
              if (window.confirm("Move this contact to trash?")) {
                void remove
                  .mutateAsync(c.id)
                  .then(() => navigate("/contacts"))
                  .catch((e: unknown) => toastError(push, e));
              }
            }}
          >
            To trash
          </Button>
        </div>
        <div className="mt-4 flex flex-wrap gap-1.5 border-t border-slate-100 pt-3 text-xs dark:border-slate-800">
          {tags.data?.items.map((t) => {
            const active = c.tags.some((ct) => ct.id === t.id);
            return (
              <button
                key={t.id}
                type="button"
                onClick={() => {
                  const next = active
                    ? c.tags.filter((ct) => ct.id !== t.id).map((ct) => ct.id)
                    : [...c.tags.map((ct) => ct.id), t.id];
                  void setTags(next);
                }}
                className={
                  active
                    ? "rounded-md bg-brand-600 px-2 py-0.5 font-medium text-white dark:bg-brand-500"
                    : "rounded-md border border-slate-200/80 bg-slate-50 px-2 py-0.5 text-slate-600 hover:bg-slate-100 dark:border-slate-800 dark:bg-slate-800/70 dark:text-slate-300"
                }
              >
                {t.name}
              </button>
            );
          })}
        </div>
      </div>

      <div className="ui-card p-4">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-400">
          Contact deals ({deals.data?.total ?? 0})
        </h2>
        <ul className="mt-2.5 flex flex-col gap-1.5 text-xs">
          {(deals.data?.items ?? []).map((d) => (
            <li key={d.id} className="flex items-center justify-between">
              <Link
                className="font-medium text-brand-600 hover:underline dark:text-brand-400"
                to={`/deals/${d.id}`}
              >
                {d.title}
              </Link>
              <span className="font-mono text-slate-500">
                {d.status} · {d.amount ?? "—"} {d.currency}
              </span>
            </li>
          ))}
        </ul>
      </div>

      <div className="ui-card p-4">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-400">Note</h2>
        <div className="mt-2 flex gap-2">
          <Input
            aria-label="Note text"
            value={noteBody}
            onChange={(e) => setNoteBody(e.target.value)}
            placeholder="New note…"
            className="flex-1"
          />
          <Button
            size="sm"
            disabled={!noteBody.trim()}
            onClick={() => {
              void createNote
                .mutateAsync({ contact_id: c.id, body: noteBody.trim() })
                .then(() => {
                  setNoteBody("");
                  push({ title: "Note added", variant: "default" });
                })
                .catch((e: unknown) => toastError(push, e));
            }}
          >
            Add
          </Button>
        </div>
      </div>

      <div className="ui-card p-4">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-400">Activity</h2>
        {timeline.isPending && <p className="mt-2 text-xs text-slate-500">Loading timeline…</p>}
        {timeline.data && (
          <ul className="mt-2.5 flex flex-col gap-1.5 text-xs">
            {timeline.data.items.map((item) => (
              <li
                key={item.key}
                className="rounded-md border border-slate-100 p-2.5 dark:border-slate-800/80"
              >
                <ItemBody item={item} />
              </li>
            ))}
            {timeline.data.items.length === 0 && (
              <li className="text-slate-500">Nothing here yet.</li>
            )}
          </ul>
        )}
      </div>
    </div>
  );
}
