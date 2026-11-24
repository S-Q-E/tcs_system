import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import {
  contactQueryString,
  exportUrl,
  toContactParams,
  useBulkContacts,
  useContactSavedViews,
  useContactsList,
  useCreateContactSavedView,
  useDeleteContactSavedView,
  useDeleteContact,
  useDuplicates,
  useImportJob,
  useMergeContacts,
  useRestoreContact,
  useTrash,
  type ContactFilters,
  type ImportPreview,
} from "@/api/contacts";
import { useTags, useUsersLite } from "@/api/deals";
import { useMe } from "@/api/auth";
import { api } from "@/api/client";
import { toastError, useToast } from "@/components/toast";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

const ALL_COLUMNS = [
  { id: "name", label: "Name" },
  { id: "phone", label: "Phone" },
  { id: "email", label: "Email" },
  { id: "telegram", label: "Chat" },
  { id: "owner", label: "Owner" },
  { id: "tags", label: "Tags" },
] as const;

type ColumnId = (typeof ALL_COLUMNS)[number]["id"];
const STORAGE_KEY = "tcs-leasing-contact-columns";

function loadColumns(): ColumnId[] {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as string[];
      const valid = parsed.filter((id): id is ColumnId => ALL_COLUMNS.some((c) => c.id === id));
      if (valid.length > 0) return valid;
    }
  } catch {
    // defaults
  }
  return ALL_COLUMNS.map((c) => c.id);
}

const IMPORT_FIELDS = ["ignore", "name", "phone", "email", "whatsapp_id", "source"];

export function autoMapping(header: string[]): Record<string, string> {
  const out: Record<string, string> = {};
  for (const col of header) {
    const low = col.trim().toLowerCase();
    if (["name", "full_name"].includes(low)) out[col] = "name";
    else if (["phone", "phone_number", "tel"].includes(low)) out[col] = "phone";
    else if (["email", "e-mail"].includes(low)) out[col] = "email";
    else if (["telegram", "whatsapp_id", "wa"].includes(low)) out[col] = "whatsapp_id";
    else if (["source"].includes(low)) out[col] = "source";
    else out[col] = "ignore";
  }
  return out;
}

export function ContactsPage() {
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") ?? "list";
  const setTab = (value: string) => {
    const next = new URLSearchParams(params);
    next.set("tab", value);
    setParams(next);
  };
  return (
    <div className="flex flex-col gap-3.5">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-base font-semibold tracking-[-0.015em] text-slate-900 dark:text-slate-100">
          Contacts
        </h1>
        <nav className="inline-flex rounded-md border border-slate-200/90 bg-slate-100/80 p-0.5 dark:border-slate-800 dark:bg-[#14171D]">
          {[
            ["list", "List"],
            ["duplicates", "Duplicates"],
            ["import", "Import"],
            ["trash", "Trash"],
          ].map(([id, label]) => (
            <button
              key={id}
              type="button"
              onClick={() => setTab(id)}
              className={cn(
                "rounded-[5px] px-2.5 py-1 text-xs font-medium transition-all",
                tab === id
                  ? "bg-white text-slate-900 shadow-subtle dark:bg-[#1E222B] dark:text-white"
                  : "text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-200",
              )}
            >
              {label}
            </button>
          ))}
        </nav>
      </div>
      {tab === "list" && <ContactsList />}
      {tab === "duplicates" && <DuplicatesView />}
      {tab === "import" && <ImportView />}
      {tab === "trash" && <TrashView />}
    </div>
  );
}

function ContactsList() {
  const { push } = useToast();
  const [params, setParams] = useSearchParams();
  const search = params.get("q") ?? "";
  const [sort, setSort] = useState("-created_at");
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [columns, setColumns] = useState<ColumnId[]>(loadColumns);
  const [ownerId, setOwnerId] = useState("");
  const [source, setSource] = useState("");
  const [viewName, setViewName] = useState("");
  const [bulkOwner, setBulkOwner] = useState("");
  const [bulkTag, setBulkTag] = useState("");
  const limit = 50;

  const filters: ContactFilters = useMemo(
    () => ({
      search: search || undefined,
      owner_id: ownerId || undefined,
      source: source || undefined,
    }),
    [search, ownerId, source],
  );
  const list = useContactsList({ ...filters, sort, limit, offset });
  const bulk = useBulkContacts();
  const remove = useDeleteContact();
  const users = useUsersLite();
  const tags = useTags();
  const savedViews = useContactSavedViews();
  const createView = useCreateContactSavedView();
  const deleteView = useDeleteContactSavedView();

  const items = list.data?.items ?? [];
  const total = list.data?.total ?? 0;
  const qs = contactQueryString({ ...toContactParams(filters), sort });

  const toggleSort = (field: string) => setSort((prev) => (prev === field ? `-${field}` : field));

  const toggleColumn = (id: ColumnId) => {
    setColumns((prev) => {
      const next = prev.includes(id) ? prev.filter((c) => c !== id) : [...prev, id];
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
      return next;
    });
  };

  const runBulk = async (del = false) => {
    if (selected.size === 0) return;
    try {
      await bulk.mutateAsync({
        ids: [...selected],
        set_owner_id: bulkOwner || undefined,
        add_tag_id: bulkTag || undefined,
        delete: del,
      });
      setSelected(new Set());
      push({
        title: del ? `To trash: ${selected.size}` : `Updated: ${selected.size}`,
        variant: "default",
      });
    } catch (error) {
      toastError(push, error);
    }
  };

  const saveView = async () => {
    if (!viewName.trim()) return;
    try {
      await createView.mutateAsync({ name: viewName.trim(), filters });
      setViewName("");
      push({ title: "View saved", variant: "default" });
    } catch (error) {
      toastError(push, error);
    }
  };

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-1.5 rounded-lg border border-slate-200/80 bg-white/80 p-2 shadow-subtle dark:border-slate-800/80 dark:bg-[#121418]/80">
        <Input
          aria-label="Quick search"
          placeholder="Quick search: name, phone, email…"
          value={search}
          onChange={(e) => {
            const next = new URLSearchParams(params);
            if (e.target.value) next.set("q", e.target.value);
            else next.delete("q");
            setParams(next);
            setOffset(0);
          }}
          className="w-full sm:w-64"
        />
        <select
          aria-label="Owner"
          value={ownerId}
          onChange={(e) => setOwnerId(e.target.value)}
          className="ui-select"
        >
          <option value="">All owners</option>
          {users.data?.items.map((u) => (
            <option key={u.id} value={u.id}>
              {u.name}
            </option>
          ))}
        </select>
        <select
          aria-label="Source"
          value={source}
          onChange={(e) => setSource(e.target.value)}
          className="ui-select"
        >
          <option value="">All sources</option>
          <option value="bot">Bot</option>
          <option value="manual">Manual</option>
          <option value="import">Import</option>
        </select>
        <div className="ml-auto flex items-center gap-1.5">
          <a
            className="inline-flex h-8 items-center rounded-md border border-slate-200/90 bg-white px-2.5 text-xs font-medium text-slate-700 shadow-subtle hover:bg-slate-50 dark:border-slate-800 dark:bg-[#161920] dark:text-slate-200 dark:hover:bg-[#1D212A]"
            href={exportUrl("contacts", "csv", qs)}
          >
            CSV
          </a>
          <a
            className="inline-flex h-8 items-center rounded-md border border-slate-200/90 bg-white px-2.5 text-xs font-medium text-slate-700 shadow-subtle hover:bg-slate-50 dark:border-slate-800 dark:bg-[#161920] dark:text-slate-200 dark:hover:bg-[#1D212A]"
            href={exportUrl("contacts", "xlsx", qs)}
          >
            XLSX
          </a>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span className="font-semibold uppercase tracking-wider text-slate-400">Views:</span>
        {savedViews.data?.items.map((v) => (
          <span
            key={v.id}
            className="inline-flex items-center gap-1 rounded-md border border-slate-200/80 bg-white px-2 py-0.5 font-medium text-slate-700 shadow-subtle dark:border-slate-800 dark:bg-[#14171D] dark:text-slate-300"
          >
            <button
              type="button"
              className="hover:text-brand-600 dark:hover:text-brand-400"
              onClick={() => {
                setOwnerId(v.filters.owner_id ?? "");
                setSource(v.filters.source ?? "");
                const next = new URLSearchParams(params);
                if (v.filters.search) next.set("q", v.filters.search);
                else next.delete("q");
                setParams(next);
                setOffset(0);
              }}
            >
              {v.name}
            </button>
            <button
              type="button"
              aria-label={`Delete view ${v.name}`}
              onClick={() => void deleteView.mutateAsync(v.id)}
              className="text-slate-400 hover:text-red-600"
            >
              ×
            </button>
          </span>
        ))}
        <Input
          aria-label="View name"
          placeholder="View name…"
          value={viewName}
          onChange={(e) => setViewName(e.target.value)}
          className="h-7 w-36"
        />
        <Button size="sm" variant="secondary" onClick={() => void saveView()}>
          Save view
        </Button>
      </div>

      <div className="flex flex-wrap items-center gap-3 text-xs text-slate-600 dark:text-slate-400">
        <span className="font-semibold uppercase tracking-wider text-slate-400">Columns:</span>
        {ALL_COLUMNS.map((col) => (
          <label key={col.id} className="inline-flex cursor-pointer items-center gap-1.5">
            <input
              type="checkbox"
              checked={columns.includes(col.id)}
              onChange={() => toggleColumn(col.id)}
            />
            {col.label}
          </label>
        ))}
      </div>

      {selected.size > 0 && (
        <div className="flex flex-wrap items-center gap-2 rounded-lg border border-brand-200 bg-brand-50/50 p-2.5 text-xs dark:border-brand-900/50 dark:bg-brand-950/20">
          <span className="font-semibold text-brand-800 dark:text-brand-200">
            Selected: {selected.size}
          </span>
          <select
            aria-label="Bulk: owner"
            value={bulkOwner}
            onChange={(e) => setBulkOwner(e.target.value)}
            className="ui-select"
          >
            <option value="">Owner…</option>
            {users.data?.items.map((u) => (
              <option key={u.id} value={u.id}>
                {u.name}
              </option>
            ))}
          </select>
          <select
            aria-label="Bulk: tag"
            value={bulkTag}
            onChange={(e) => setBulkTag(e.target.value)}
            className="ui-select"
          >
            <option value="">Tag…</option>
            {tags.data?.items.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </select>
          <Button size="sm" onClick={() => void runBulk(false)} disabled={bulk.isPending}>
            Apply
          </Button>
          <Button
            size="sm"
            variant="secondary"
            onClick={() => void runBulk(true)}
            disabled={bulk.isPending}
          >
            To trash
          </Button>
        </div>
      )}

      <div className="ui-table-wrapper">
        <table className="ui-table min-w-160">
          <thead>
            <tr>
              <th className="w-8">
                <input
                  type="checkbox"
                  aria-label="Select all"
                  checked={items.length > 0 && items.every((i) => selected.has(i.id))}
                  onChange={() =>
                    setSelected((prev) =>
                      prev.size === items.length ? new Set() : new Set(items.map((i) => i.id)),
                    )
                  }
                />
              </th>
              {columns.map((col) => (
                <th key={col}>
                  <button
                    type="button"
                    onClick={() =>
                      toggleSort(
                        col === "telegram"
                          ? "created_at"
                          : col === "tags"
                            ? "created_at"
                            : col === "owner"
                              ? "created_at"
                              : col === "phone"
                                ? "created_at"
                                : col === "email"
                                  ? "created_at"
                                  : col,
                      )
                    }
                    className="font-medium hover:text-slate-900 dark:hover:text-white"
                  >
                    {ALL_COLUMNS.find((c) => c.id === col)?.label}
                    {sort.replace("-", "") === col && (sort.startsWith("-") ? " ↓" : " ↑")}
                  </button>
                </th>
              ))}
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {items.map((c) => (
              <tr key={c.id}>
                <td>
                  <input
                    type="checkbox"
                    aria-label={`Select ${c.name ?? c.phone ?? c.id}`}
                    checked={selected.has(c.id)}
                    onChange={() =>
                      setSelected((prev) => {
                        const next = new Set(prev);
                        if (next.has(c.id)) next.delete(c.id);
                        else next.add(c.id);
                        return next;
                      })
                    }
                  />
                </td>
                {columns.map((col) => (
                  <td key={col} className="max-w-60 truncate">
                    {col === "name" ? (
                      <Link
                        className="font-medium text-brand-600 hover:underline dark:text-brand-400"
                        to={`/contacts/${c.id}`}
                      >
                        {c.name ?? "—"}
                      </Link>
                    ) : col === "phone" ? (
                      <span className="font-mono text-xs">{c.phone ?? "—"}</span>
                    ) : col === "email" ? (
                      (c.email ?? "—")
                    ) : col === "telegram" ? (
                      <span className="font-mono text-xs">{c.whatsapp_id ?? "—"}</span>
                    ) : col === "owner" ? (
                      (users.data?.items.find((u) => u.id === c.owner_id)?.name ?? "—")
                    ) : (
                      c.tags.map((t) => t.name).join(", ") || "—"
                    )}
                  </td>
                ))}
                <td>
                  <button
                    type="button"
                    className="text-xs font-medium text-red-600 hover:underline dark:text-red-400"
                    onClick={() => {
                      if (window.confirm("Move this contact to trash?")) {
                        void remove.mutateAsync(c.id).catch((e: unknown) => toastError(push, e));
                      }
                    }}
                  >
                    To trash
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {list.isPending && <p className="p-4 text-xs text-slate-500">Loading…</p>}
        {list.isError && <p className="p-4 text-xs text-red-600">Could not load contacts.</p>}
        {!list.isPending && items.length === 0 && (
          <p className="p-4 text-xs text-slate-500">No contacts. Adjust the filters.</p>
        )}
      </div>

      <div className="flex items-center gap-2 text-xs text-slate-500">
        <Button
          variant="secondary"
          size="sm"
          disabled={offset === 0}
          onClick={() => setOffset((v) => Math.max(0, v - limit))}
        >
          Back
        </Button>
        <span className="font-mono">
          {offset + 1}–{Math.min(offset + limit, total)} of {total}
        </span>
        <Button
          variant="secondary"
          size="sm"
          disabled={offset + limit >= total}
          onClick={() => setOffset((v) => v + limit)}
        >
          Next
        </Button>
      </div>
    </div>
  );
}

function DuplicatesView() {
  const { push } = useToast();
  const dup = useDuplicates();
  const merge = useMergeContacts();
  const [winners, setWinners] = useState<Record<string, string>>({});
  const groups = dup.data?.groups ?? [];
  if (dup.isPending) return <p className="text-xs text-slate-500">Looking for duplicates…</p>;
  if (dup.isError) return <p className="text-xs text-red-600">Could not load duplicates.</p>;
  if (groups.length === 0) return <p className="text-xs text-slate-500">No duplicates found.</p>;
  return (
    <div className="flex flex-col gap-3">
      <p className="text-xs text-slate-500">
        Groups: {groups.length}. Merging moves deals, notes, tasks and tags; the source stays in
        the trash.
      </p>
      {groups.map((g) => (
        <div key={g.key} className="ui-card p-3.5">
          <p className="text-xs font-semibold text-slate-800 dark:text-slate-100">
            {g.kind === "phone" ? "Phone" : "Email"}:{" "}
            <span className="font-mono">{g.value}</span>
          </p>
          <div className="mt-2 flex flex-col gap-1">
            {g.contact_ids.map((id) => (
              <label key={id} className="flex items-center gap-2 text-xs">
                <input
                  type="radio"
                  name={`winner-${g.key}`}
                  checked={winners[g.key] === id}
                  onChange={() => setWinners((prev) => ({ ...prev, [g.key]: id }))}
                />
                <Link
                  className="font-mono text-brand-600 hover:underline dark:text-brand-400"
                  to={`/contacts/${id}`}
                >
                  {id.slice(0, 8)}
                </Link>
                <span className="text-slate-500">keep as primary</span>
              </label>
            ))}
          </div>
          <div className="mt-2.5 flex gap-2">
            {g.contact_ids
              .filter((id) => id !== winners[g.key])
              .map((loser) => (
                <Button
                  key={loser}
                  size="sm"
                  disabled={!winners[g.key] || merge.isPending}
                  onClick={() => {
                    const winner = winners[g.key];
                    if (!winner) return;
                    if (!window.confirm("Merge contacts? This cannot be undone.")) return;
                    void merge
                      .mutateAsync({ winner_id: winner, loser_id: loser })
                      .then(() => push({ title: "Contacts merged", variant: "default" }))
                      .catch((e: unknown) => toastError(push, e));
                  }}
                >
                  Merge {loser.slice(0, 8)} into primary
                </Button>
              ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function ImportView() {
  const { push } = useToast();
  const [file, setFile] = useState<File | null>(null);
  const [header, setHeader] = useState<string[]>([]);
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const job = useImportJob(jobId, running);

  const readHeader = async (f: File) => {
    const text = await f.text();
    const first = text.split(/\r?\n/)[0] ?? "";
    const cols = first
      .split(/[,;]/)
      .map((c) => c.trim())
      .filter(Boolean);
    setHeader(cols);
    setMapping(autoMapping(cols));
  };

  const doPreviewFetch = async () => {
    if (!file) return;
    const form = new FormData();
    form.append("file", file);
    form.append("mapping", JSON.stringify(mapping));
    const token = document.cookie.match(/crm_csrf=([^;]+)/)?.[1] ?? "";
    const resp = await fetch("/api/contacts/import/preview", {
      method: "POST",
      body: form,
      credentials: "include",
      headers: token ? { "X-CSRF-Token": decodeURIComponent(token) } : {},
    });
    if (!resp.ok) {
      const body = (await resp.json().catch(() => null)) as { error?: { message?: string } } | null;
      push({ title: body?.error?.message ?? "Preview error", variant: "error" });
      return;
    }
    const data = (await resp.json()) as ImportPreview;
    setPreview(data);
  };

  const doImport = async () => {
    if (!file) return;
    const form = new FormData();
    form.append("file", file);
    form.append("mapping", JSON.stringify(mapping));
    const token = document.cookie.match(/crm_csrf=([^;]+)/)?.[1] ?? "";
    const resp = await fetch("/api/contacts/import", {
      method: "POST",
      body: form,
      credentials: "include",
      headers: token ? { "X-CSRF-Token": decodeURIComponent(token) } : {},
    });
    if (!resp.ok) {
      push({ title: "Import error", variant: "error" });
      return;
    }
    const data = (await resp.json()) as { id: string };
    setJobId(data.id);
    setRunning(true);
  };

  const finished =
    job.data?.status === "done" || job.data?.status === "failed" || job.isError;
  useEffect(() => {
    // Intentional sync: stop polling once the polled import reaches a terminal state or errors.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (finished && running) setRunning(false);
  }, [finished, running]);

  return (
    <div className="ui-card flex max-w-2xl flex-col gap-3 p-4">
      <h2 className="text-sm font-semibold text-slate-900 dark:text-slate-100">Import CSV</h2>
      <input
        aria-label="CSV file"
        type="file"
        accept=".csv,text/csv"
        className="text-xs text-slate-600 file:mr-3 file:rounded-md file:border-0 file:bg-brand-50 file:px-3 file:py-1.5 file:text-xs file:font-medium file:text-brand-700 hover:file:bg-brand-100 dark:text-slate-300 dark:file:bg-brand-950/60 dark:file:text-brand-300"
        onChange={(e) => {
          const f = e.target.files?.[0] ?? null;
          setFile(f);
          setPreview(null);
          if (f) void readHeader(f);
        }}
      />
      {header.length > 0 && (
        <div className="flex flex-col gap-1.5 text-xs">
          <p className="font-medium text-slate-700 dark:text-slate-300">Column mapping:</p>
          {header.map((col) => (
            <label key={col} className="flex items-center gap-2">
              <span className="w-40 truncate font-mono text-xs text-slate-600 dark:text-slate-400">
                {col}
              </span>
              <select
                value={mapping[col] ?? "ignore"}
                onChange={(e) => setMapping((prev) => ({ ...prev, [col]: e.target.value }))}
                className="ui-select"
              >
                {IMPORT_FIELDS.map((f) => (
                  <option key={f} value={f}>
                    {f}
                  </option>
                ))}
              </select>
            </label>
          ))}
        </div>
      )}
      <div className="flex gap-2">
        <Button
          size="sm"
          variant="secondary"
          disabled={!file}
          onClick={() => void doPreviewFetch()}
        >
          Preview
        </Button>
        <Button size="sm" disabled={!file} onClick={() => void doImport()}>
          Import in background
        </Button>
      </div>
      {preview && (
        <div className="rounded-md bg-slate-50 p-3 text-xs dark:bg-slate-800/50">
          <p>
            Total rows: {preview.total}, valid: {preview.valid}, with errors: {preview.invalid}
          </p>
          {preview.errors.length > 0 && (
            <ul className="mt-1 max-h-32 overflow-auto text-red-600">
              {preview.errors.map((e, i) => (
                <li key={i}>
                  Row {e.row}: {e.error}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
      {job.data && (
        <div className="rounded-md bg-slate-50 p-3 text-xs dark:bg-slate-800/50">
          <p>
            Job {job.data.id}: {job.data.status}, ok: {job.data.ok_count}, errors:{" "}
            {job.data.error_count}
          </p>
          {job.data.errors.length > 0 && (
            <ul className="mt-1 max-h-32 overflow-auto text-red-600">
              {job.data.errors.map((e, i) => (
                <li key={i}>
                  Row {e.row}: {e.error}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

function TrashView() {
  const { push } = useToast();
  const me = useMe();
  const trash = useTrash("all");
  const restoreContact = useRestoreContact();
  if (me.data && me.data.role !== "admin") {
    return <p className="text-xs text-slate-500">Trash is available to admins only.</p>;
  }
  if (trash.isPending) return <p className="text-xs text-slate-500">Loading trash…</p>;
  if (trash.isError) return <p className="text-xs text-red-600">No access or loading error.</p>;
  const items = trash.data?.items ?? [];
  if (items.length === 0) return <p className="text-xs text-slate-500">Trash is empty.</p>;
  return (
    <div className="flex flex-col gap-2">
      {items.map((item) => (
        <div
          key={`${item.kind}-${item.id}`}
          className="ui-card flex items-center gap-3 px-3.5 py-2.5 text-xs"
        >
          <span className="rounded border border-slate-200 bg-slate-50 px-1.5 py-0.5 font-mono text-[11px] dark:border-slate-800 dark:bg-slate-800">
            {item.kind}
          </span>
          <span className="font-medium text-slate-900 dark:text-slate-100">
            {item.name ?? item.id.slice(0, 8)}
          </span>
          <button
            type="button"
            className="ml-auto font-medium text-brand-600 hover:underline dark:text-brand-400"
            onClick={() => {
              const doRestore =
                item.kind === "contact"
                  ? restoreContact.mutateAsync(item.id)
                  : api.post(`/api/deals/${item.id}/restore`).then(() => undefined);
              void doRestore
                .then(() => push({ title: "Restored", variant: "default" }))
                .catch((e: unknown) => toastError(push, e));
            }}
          >
            Restore
          </button>
        </div>
      ))}
    </div>
  );
}
