import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";

import { useMe } from "@/api/auth";
import type { ImportPreview } from "@/api/contacts";
import {
  useCreateUnit,
  useDeleteUnit,
  useUnitImportJob,
  useUnits,
  useUpdateUnit,
  type Unit,
  type UnitStatus,
} from "@/api/viewings";
import { ModalShell } from "@/components/deals/modals";
import { toastError, useToast } from "@/components/toast";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

const UNIT_IMPORT_FIELDS = [
  "ignore",
  "building",
  "unit_number",
  "beds",
  "baths",
  "rent_usd",
  "deposit_usd",
  "available_from",
  "pets_policy",
  "description",
  "status",
];

function autoUnitMapping(header: string[]): Record<string, string> {
  const out: Record<string, string> = {};
  for (const col of header) {
    const low = col.trim().toLowerCase().replace(/\s+/g, "_");
    if (UNIT_IMPORT_FIELDS.includes(low) && low !== "ignore") {
      out[col] = low;
    } else if (["unit", "apt", "number"].includes(low)) {
      out[col] = "unit_number";
    } else if (["rent", "price", "monthly_rent"].includes(low)) {
      out[col] = "rent_usd";
    } else if (["deposit"].includes(low)) {
      out[col] = "deposit_usd";
    } else if (["pets"].includes(low)) {
      out[col] = "pets_policy";
    } else {
      out[col] = "ignore";
    }
  }
  return out;
}

const STATUS_BADGE: Record<UnitStatus, string> = {
  available: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200",
  leased: "bg-slate-200 text-slate-700 dark:bg-slate-800 dark:text-slate-300",
  hidden: "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-200",
};

export function UnitsPage() {
  const { data: me } = useMe();
  const isAdmin = me?.role === "admin";
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") ?? "list";
  const setTab = (value: string) => {
    const next = new URLSearchParams(params);
    next.set("tab", value);
    setParams(next);
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <h1 className="text-xl font-bold">Units</h1>
        <nav className="flex flex-wrap gap-1 text-sm md:ml-4">
          <button
            type="button"
            onClick={() => setTab("list")}
            className={cn(
              "rounded-md px-2.5 py-1",
              tab === "list"
                ? "bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900"
                : "hover:bg-slate-100 dark:hover:bg-slate-800",
            )}
          >
            List
          </button>
          {isAdmin && (
            <button
              type="button"
              onClick={() => setTab("import")}
              className={cn(
                "rounded-md px-2.5 py-1",
                tab === "import"
                  ? "bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900"
                  : "hover:bg-slate-100 dark:hover:bg-slate-800",
              )}
            >
              Import CSV
            </button>
          )}
        </nav>
      </div>
      {tab === "import" && isAdmin ? <UnitsImportView /> : <UnitsListView isAdmin={isAdmin} />}
    </div>
  );
}

function UnitsListView({ isAdmin }: { isAdmin: boolean }) {
  const { push } = useToast();
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [bedsFilter, setBedsFilter] = useState("");
  const [maxRent, setMaxRent] = useState("");
  const [offset, setOffset] = useState(0);
  const [editing, setEditing] = useState<Unit | "new" | null>(null);
  const limit = 50;

  const list = useUnits({
    search: search.trim() || undefined,
    status: statusFilter || undefined,
    beds: bedsFilter !== "" ? Number(bedsFilter) : undefined,
    max_rent: maxRent !== "" ? Number(maxRent) : undefined,
    limit,
    offset,
  });
  const updateUnit = useUpdateUnit();
  const deleteUnit = useDeleteUnit();

  const items = list.data?.items ?? [];
  const total = list.data?.total ?? 0;

  const quickStatus = async (unit: Unit, nextStatus: UnitStatus) => {
    try {
      await updateUnit.mutateAsync({ id: unit.id, patch: { status: nextStatus } });
      push({ title: `${unit.building} ${unit.unit_number} → ${nextStatus}`, variant: "default" });
    } catch (error) {
      toastError(push, error);
    }
  };

  const remove = async (unit: Unit) => {
    if (!window.confirm(`Delete ${unit.building} ${unit.unit_number}?`)) return;
    try {
      await deleteUnit.mutateAsync(unit.id);
      push({ title: "Unit deleted", variant: "default" });
    } catch (error) {
      toastError(push, error);
    }
  };

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <Input
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            setOffset(0);
          }}
          placeholder="Search building, unit, pets…"
          className="w-56"
        />
        <select
          aria-label="Status filter"
          value={statusFilter}
          onChange={(e) => {
            setStatusFilter(e.target.value);
            setOffset(0);
          }}
          className="h-11 md:h-9 rounded-md border border-slate-200 bg-white px-2 text-sm dark:border-slate-700 dark:bg-slate-900"
        >
          <option value="">All statuses</option>
          <option value="available">Available</option>
          <option value="leased">Leased</option>
          <option value="hidden">Hidden</option>
        </select>
        <select
          aria-label="Bedrooms filter"
          value={bedsFilter}
          onChange={(e) => {
            setBedsFilter(e.target.value);
            setOffset(0);
          }}
          className="h-11 md:h-9 rounded-md border border-slate-200 bg-white px-2 text-sm dark:border-slate-700 dark:bg-slate-900"
        >
          <option value="">Any beds</option>
          <option value="0">Studio</option>
          <option value="1">1 BR</option>
          <option value="2">2 BR</option>
          <option value="3">3 BR</option>
          <option value="4">4 BR</option>
        </select>
        <Input
          type="number"
          min="0"
          value={maxRent}
          onChange={(e) => {
            setMaxRent(e.target.value);
            setOffset(0);
          }}
          placeholder="Max rent $"
          className="w-32"
        />
        {isAdmin && (
          <Button className="ml-auto" size="sm" onClick={() => setEditing("new")}>
            + Add unit
          </Button>
        )}
      </div>

      <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-slate-200 text-xs uppercase text-slate-500 dark:border-slate-800">
            <tr>
              <th className="p-2.5">Building</th>
              <th className="p-2.5">Unit</th>
              <th className="p-2.5">Beds / Baths</th>
              <th className="p-2.5">Rent</th>
              <th className="p-2.5">Deposit</th>
              <th className="p-2.5">Available</th>
              <th className="p-2.5">Pets</th>
              <th className="p-2.5">Status</th>
              {isAdmin && <th className="p-2.5">Actions</th>}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
            {items.map((u) => (
              <tr key={u.id} className="hover:bg-slate-50 dark:hover:bg-slate-800/40">
                <td className="p-2.5 font-medium">{u.building}</td>
                <td className="p-2.5">{u.unit_number}</td>
                <td className="p-2.5">
                  {u.beds}BR / {u.baths}BA
                </td>
                <td className="p-2.5">${u.rent_usd.toLocaleString()}</td>
                <td className="p-2.5">
                  {u.deposit_usd != null ? `$${u.deposit_usd.toLocaleString()}` : "—"}
                </td>
                <td className="p-2.5">{u.available_from ?? "—"}</td>
                <td className="max-w-44 truncate p-2.5 text-xs text-slate-600 dark:text-slate-300">
                  {u.pets_policy ?? "—"}
                </td>
                <td className="p-2.5">
                  {isAdmin ? (
                    <select
                      aria-label={`Status for ${u.building} ${u.unit_number}`}
                      value={u.status}
                      disabled={updateUnit.isPending}
                      onChange={(e) => void quickStatus(u, e.target.value as UnitStatus)}
                      className={cn(
                        "rounded-full px-2 py-0.5 text-xs font-medium",
                        STATUS_BADGE[u.status],
                      )}
                    >
                      <option value="available">available</option>
                      <option value="leased">leased</option>
                      <option value="hidden">hidden</option>
                    </select>
                  ) : (
                    <span
                      className={cn(
                        "inline-block rounded-full px-2 py-0.5 text-xs font-medium",
                        STATUS_BADGE[u.status],
                      )}
                    >
                      {u.status}
                    </span>
                  )}
                </td>
                {isAdmin && (
                  <td className="p-2.5">
                    <div className="flex gap-2 text-xs">
                      <button
                        type="button"
                        className="text-blue-600 hover:underline"
                        onClick={() => setEditing(u)}
                      >
                        Edit
                      </button>
                      <button
                        type="button"
                        className="text-red-600 hover:underline"
                        onClick={() => void remove(u)}
                      >
                        Delete
                      </button>
                    </div>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
        {list.isPending && <p className="p-4 text-sm text-slate-500">Loading units…</p>}
        {list.isError && <p className="p-4 text-sm text-red-600">Could not load units.</p>}
        {!list.isPending && items.length === 0 && (
          <p className="p-4 text-sm text-slate-500">No units found.</p>
        )}
      </div>

      {total > limit && (
        <div className="flex items-center gap-2 text-sm">
          <Button
            variant="secondary"
            size="sm"
            disabled={offset === 0}
            onClick={() => setOffset((v) => Math.max(0, v - limit))}
          >
            Back
          </Button>
          <span>
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
      )}

      {editing && (
        <UnitFormModal unit={editing === "new" ? null : editing} onClose={() => setEditing(null)} />
      )}
    </div>
  );
}

function UnitFormModal({ unit, onClose }: { unit: Unit | null; onClose: () => void }) {
  const { push } = useToast();
  const createUnit = useCreateUnit();
  const updateUnit = useUpdateUnit();
  const [building, setBuilding] = useState(unit?.building ?? "");
  const [unitNumber, setUnitNumber] = useState(unit?.unit_number ?? "");
  const [beds, setBeds] = useState(String(unit?.beds ?? 1));
  const [baths, setBaths] = useState(String(unit?.baths ?? 1));
  const [rentUsd, setRentUsd] = useState(String(unit?.rent_usd ?? 1800));
  const [depositUsd, setDepositUsd] = useState(unit?.deposit_usd != null ? String(unit.deposit_usd) : "");
  const [availableFrom, setAvailableFrom] = useState(unit?.available_from ?? "");
  const [petsPolicy, setPetsPolicy] = useState(unit?.pets_policy ?? "");
  const [description, setDescription] = useState(unit?.description ?? "");
  const [status, setStatus] = useState<UnitStatus>(unit?.status ?? "available");

  const saving = createUnit.isPending || updateUnit.isPending;

  const save = async () => {
    if (!building.trim() || !unitNumber.trim()) return;
    const payload = {
      building: building.trim(),
      unit_number: unitNumber.trim(),
      beds: Number(beds),
      baths: Number(baths),
      rent_usd: Number(rentUsd),
      deposit_usd: depositUsd !== "" ? Number(depositUsd) : null,
      available_from: availableFrom || null,
      pets_policy: petsPolicy.trim() || null,
      description: description.trim() || null,
      status,
    };
    try {
      if (unit) {
        await updateUnit.mutateAsync({ id: unit.id, patch: payload });
        push({ title: "Unit updated", variant: "default" });
      } else {
        await createUnit.mutateAsync(payload);
        push({ title: "Unit created", variant: "default" });
      }
      onClose();
    } catch (error) {
      toastError(push, error);
    }
  };

  return (
    <ModalShell title={unit ? "Edit unit" : "New unit"} onClose={onClose}>
      <div className="flex flex-col gap-2.5 text-sm">
        <div className="grid grid-cols-2 gap-2">
          <label className="block">
            Building *
            <Input className="mt-1" value={building} onChange={(e) => setBuilding(e.target.value)} />
          </label>
          <label className="block">
            Unit number *
            <Input
              className="mt-1"
              value={unitNumber}
              onChange={(e) => setUnitNumber(e.target.value)}
            />
          </label>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <label className="block">
            Beds
            <Input
              className="mt-1"
              type="number"
              min="0"
              value={beds}
              onChange={(e) => setBeds(e.target.value)}
            />
          </label>
          <label className="block">
            Baths
            <Input
              className="mt-1"
              type="number"
              step="0.5"
              min="0.5"
              value={baths}
              onChange={(e) => setBaths(e.target.value)}
            />
          </label>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <label className="block">
            Rent (USD)
            <Input
              className="mt-1"
              type="number"
              min="0"
              value={rentUsd}
              onChange={(e) => setRentUsd(e.target.value)}
            />
          </label>
          <label className="block">
            Deposit (USD)
            <Input
              className="mt-1"
              type="number"
              min="0"
              value={depositUsd}
              onChange={(e) => setDepositUsd(e.target.value)}
            />
          </label>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <label className="block">
            Available from
            <Input
              className="mt-1"
              type="date"
              value={availableFrom}
              onChange={(e) => setAvailableFrom(e.target.value)}
            />
          </label>
          <label className="block">
            Status
            <select
              value={status}
              onChange={(e) => setStatus(e.target.value as UnitStatus)}
              className="mt-1 h-11 md:h-9 w-full rounded-md border border-slate-200 bg-white px-2 text-sm dark:border-slate-700 dark:bg-slate-900"
            >
              <option value="available">available</option>
              <option value="leased">leased</option>
              <option value="hidden">hidden</option>
            </select>
          </label>
        </div>
        <label className="block">
          Pets policy
          <Input
            className="mt-1"
            value={petsPolicy}
            onChange={(e) => setPetsPolicy(e.target.value)}
          />
        </label>
        <label className="block">
          Description
          <textarea
            rows={3}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            className="mt-1 w-full rounded-md border border-slate-200 bg-white p-2 text-sm dark:border-slate-700 dark:bg-slate-900"
          />
        </label>
        <div className="mt-2 flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button
            disabled={saving || !building.trim() || !unitNumber.trim()}
            onClick={() => void save()}
          >
            {unit ? "Save" : "Create"}
          </Button>
        </div>
      </div>
    </ModalShell>
  );
}

function UnitsImportView() {
  const { push } = useToast();
  const qc = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [header, setHeader] = useState<string[]>([]);
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const job = useUnitImportJob(jobId, running);

  const readHeader = async (f: File) => {
    const text = await f.text();
    const first = text.split(/\r?\n/)[0] ?? "";
    const cols = first
      .split(/[,;]/)
      .map((c) => c.trim())
      .filter(Boolean);
    setHeader(cols);
    setMapping(autoUnitMapping(cols));
  };

  const csrfToken = () => {
    const match = document.cookie.match(/crm_csrf=([^;]+)/)?.[1];
    return match ? decodeURIComponent(match) : "";
  };

  const doPreview = async () => {
    if (!file) return;
    const form = new FormData();
    form.append("file", file);
    form.append("mapping", JSON.stringify(mapping));
    const token = csrfToken();
    const resp = await fetch("/api/units/import/preview", {
      method: "POST",
      body: form,
      credentials: "include",
      headers: token ? { "X-CSRF-Token": token } : {},
    });
    if (!resp.ok) {
      const body = (await resp.json().catch(() => null)) as { error?: { message?: string } } | null;
      push({ title: body?.error?.message ?? "Preview error", variant: "error" });
      return;
    }
    setPreview((await resp.json()) as ImportPreview);
  };

  const doImport = async () => {
    if (!file) return;
    const form = new FormData();
    form.append("file", file);
    form.append("mapping", JSON.stringify(mapping));
    const token = csrfToken();
    const resp = await fetch("/api/units/import", {
      method: "POST",
      body: form,
      credentials: "include",
      headers: token ? { "X-CSRF-Token": token } : {},
    });
    if (!resp.ok) {
      const body = (await resp.json().catch(() => null)) as { error?: { message?: string } } | null;
      push({ title: body?.error?.message ?? "Import error", variant: "error" });
      return;
    }
    const data = (await resp.json()) as { id: string };
    setJobId(data.id);
    setRunning(true);
  };

  const finished =
    job.data?.status === "done" || job.data?.status === "failed" || job.isError;
  useEffect(() => {
    if (finished && running) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setRunning(false);
      void qc.invalidateQueries({ queryKey: ["units"] });
    }
  }, [finished, running, qc]);

  return (
    <div className="flex max-w-2xl flex-col gap-3 rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
      <h2 className="font-medium">Import units from CSV</h2>
      <input
        aria-label="Units CSV file"
        type="file"
        accept=".csv,text/csv"
        onChange={(e) => {
          const f = e.target.files?.[0] ?? null;
          setFile(f);
          setPreview(null);
          if (f) void readHeader(f);
        }}
      />
      {header.length > 0 && (
        <div className="flex flex-col gap-1 text-sm">
          <p className="font-medium">Column mapping:</p>
          {header.map((col) => (
            <label key={col} className="flex items-center gap-2">
              <span className="w-40 truncate font-mono text-xs">{col}</span>
              <select
                value={mapping[col] ?? "ignore"}
                onChange={(e) => setMapping((prev) => ({ ...prev, [col]: e.target.value }))}
                className="h-9 rounded-md border border-slate-200 bg-white px-2 dark:border-slate-700 dark:bg-slate-900"
              >
                {UNIT_IMPORT_FIELDS.map((f) => (
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
        <Button size="sm" variant="secondary" disabled={!file} onClick={() => void doPreview()}>
          Preview
        </Button>
        <Button size="sm" disabled={!file} onClick={() => void doImport()}>
          Import in background
        </Button>
      </div>
      {preview && (
        <div className="text-sm">
          <p>
            Rows: {preview.total} · Valid: {preview.valid} · Errors: {preview.invalid}
          </p>
          {preview.errors.length > 0 && (
            <ul className="mt-1 list-disc pl-5 text-xs text-red-600">
              {preview.errors.slice(0, 10).map((err, i) => (
                <li key={i}>
                  Row {err.row ?? "?"}: {err.error}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
      {job.data && (
        <div className="rounded-md bg-slate-50 p-3 text-sm dark:bg-slate-800">
          <p>
            Job status: <strong>{job.data.status}</strong> · Imported: {job.data.ok_count} ·
            Errors: {job.data.error_count}
          </p>
          {job.data.errors.length > 0 && (
            <ul className="mt-1 list-disc pl-5 text-xs text-red-600">
              {job.data.errors.slice(0, 10).map((err, i) => (
                <li key={i}>
                  Row {err.row ?? "?"}: {err.error}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
