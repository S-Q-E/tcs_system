import { useMemo, useState } from "react";

import type { Deal, DealFilters, Stage } from "@/api/deals";
import { useBulkDeals, useDealsList, useLostReasons, useTags, useUsersLite } from "@/api/deals";
import { useToast, toastError } from "@/components/toast";
import { Button } from "@/components/ui/button";
import { formatMoney, formatRelative } from "@/lib/format";
import { cn } from "@/lib/utils";

const ALL_COLUMNS = [
  { id: "title", label: "Title" },
  { id: "contact", label: "Contact" },
  { id: "amount", label: "Amount" },
  { id: "owner", label: "Owner" },
  { id: "tags", label: "Tags" },
  { id: "updated", label: "Activity" },
] as const;

type ColumnId = (typeof ALL_COLUMNS)[number]["id"];

// Only columns the backend can sort by (DEAL_SORTS); other headers are plain text.
export function dealSortField(column: string): string | null {
  if (column === "amount") return "amount";
  if (column === "updated") return "updated_at";
  return null;
}

const STORAGE_KEY = "tcs-leasing-deal-columns";

function loadColumns(): ColumnId[] {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as string[];
      const valid = parsed.filter((id): id is ColumnId => ALL_COLUMNS.some((col) => col.id === id));
      if (valid.length > 0) {
        return valid;
      }
    }
  } catch {
    // Fall through to defaults.
  }
  return ALL_COLUMNS.map((col) => col.id);
}

interface ListViewProps {
  filters: DealFilters;
  stagesById: Map<string, Stage>;
  contactsById: Map<string, { name: string | null; phone: string | null }>;
  onOpen: (id: string) => void;
}

export function DealsListView({ filters, stagesById, contactsById, onOpen }: ListViewProps) {
  const { push } = useToast();
  const [sort, setSort] = useState("-created_at");
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [columns, setColumns] = useState<ColumnId[]>(loadColumns);
  const [bulkStage, setBulkStage] = useState("");
  const [bulkOwner, setBulkOwner] = useState("");
  const [bulkTag, setBulkTag] = useState("");
  const [bulkReason, setBulkReason] = useState("");
  const limit = 50;

  const list = useDealsList({ ...filters, sort, limit, offset });
  const bulk = useBulkDeals();
  const users = useUsersLite();
  const tags = useTags();
  const reasons = useLostReasons();

  const items = useMemo(() => list.data?.items ?? [], [list.data]);
  const total = list.data?.total ?? 0;

  const toggleSort = (field: string) => {
    setSort((prev) => (prev === field ? `-${field}` : field));
  };

  const toggleSelect = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const runBulk = async () => {
    if (selected.size === 0) {
      return;
    }
    try {
      await bulk.mutateAsync({
        ids: [...selected],
        set_stage_id: bulkStage || undefined,
        set_owner_id: bulkOwner || undefined,
        add_tag_id: bulkTag || undefined,
        close_lost_reason_id: bulkReason || undefined,
      });
      setSelected(new Set());
      push({ title: `Deals updated: ${selected.size}`, variant: "default" });
    } catch (error) {
      toastError(push, error);
    }
  };

  const toggleColumn = (id: ColumnId) => {
    setColumns((prev) => {
      const next = prev.includes(id) ? prev.filter((col) => col !== id) : [...prev, id];
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
      return next;
    });
  };

  const cell = (deal: Deal, column: ColumnId): React.ReactNode => {
    const contact = contactsById.get(deal.contact_id);
    switch (column) {
      case "title":
        return <span className="font-medium text-slate-900 dark:text-slate-100">{deal.title}</span>;
      case "contact":
        return contact?.name ?? contact?.phone ?? "—";
      case "amount":
        return <span className="font-mono text-xs">{formatMoney(deal.amount, deal.currency)}</span>;
      case "owner":
        return users.data?.items.find((user) => user.id === deal.owner_id)?.name ?? "—";
      case "tags":
        return deal.tags.map((tag) => tag.name).join(", ") || "—";
      case "updated":
        return <span className="text-xs text-slate-500">{formatRelative(deal.updated_at)}</span>;
    }
  };

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-3 text-xs text-slate-600 dark:text-slate-400">
        <span className="font-semibold uppercase tracking-wider text-slate-400">Columns:</span>
        {ALL_COLUMNS.map((col) => (
          <label key={col.id} className="inline-flex cursor-pointer items-center gap-1.5">
            <input
              type="checkbox"
              className="rounded border-slate-300 text-brand-600 focus:ring-brand-500"
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
            aria-label="Bulk: stage"
            value={bulkStage}
            onChange={(event) => setBulkStage(event.target.value)}
            className="ui-select"
          >
            <option value="">Stage…</option>
            {[...stagesById.values()].map((stage) => (
              <option key={stage.id} value={stage.id}>
                {stage.name}
              </option>
            ))}
          </select>
          <select
            aria-label="Bulk: owner"
            value={bulkOwner}
            onChange={(event) => setBulkOwner(event.target.value)}
            className="ui-select"
          >
            <option value="">Owner…</option>
            {users.data?.items.map((user) => (
              <option key={user.id} value={user.id}>
                {user.name}
              </option>
            ))}
          </select>
          <select
            aria-label="Bulk: tag"
            value={bulkTag}
            onChange={(event) => setBulkTag(event.target.value)}
            className="ui-select"
          >
            <option value="">Tag…</option>
            {tags.data?.items.map((tag) => (
              <option key={tag.id} value={tag.id}>
                {tag.name}
              </option>
            ))}
          </select>
          <select
            aria-label="Bulk: close as lost"
            value={bulkReason}
            onChange={(event) => setBulkReason(event.target.value)}
            className="ui-select"
          >
            <option value="">Close as lost…</option>
            {reasons.data?.items.map((reason) => (
              <option key={reason.id} value={reason.id}>
                {reason.name}
              </option>
            ))}
          </select>
          <Button size="sm" onClick={() => void runBulk()} disabled={bulk.isPending}>
            Apply
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
                  checked={items.length > 0 && items.every((item) => selected.has(item.id))}
                  onChange={() =>
                    setSelected((prev) =>
                      prev.size === items.length
                        ? new Set()
                        : new Set(items.map((item) => item.id)),
                    )
                  }
                />
              </th>
              {columns.map((col) => {
                const label = ALL_COLUMNS.find((candidate) => candidate.id === col)?.label;
                const sortField = dealSortField(col);
                return (
                  <th key={col}>
                    {sortField ? (
                      <button
                        type="button"
                        onClick={() => toggleSort(sortField)}
                        className={cn("font-medium hover:text-slate-900 dark:hover:text-white")}
                      >
                        {label}
                        {sort.replace("-", "") === sortField &&
                          (sort.startsWith("-") ? " ↓" : " ↑")}
                      </button>
                    ) : (
                      <span className="font-medium">{label}</span>
                    )}
                  </th>
                );
              })}
              <th>Stage</th>
            </tr>
          </thead>
          <tbody>
            {items.map((deal) => {
              const stage = stagesById.get(deal.stage_id);
              return (
                <tr
                  key={deal.id}
                  data-deal-id={deal.id}
                  onClick={() => onOpen(deal.id)}
                  className="cursor-pointer"
                >
                  <td onClick={(event) => event.stopPropagation()}>
                    <input
                      type="checkbox"
                      aria-label={`Select ${deal.title}`}
                      checked={selected.has(deal.id)}
                      onChange={() => toggleSelect(deal.id)}
                    />
                  </td>
                  {columns.map((col) => (
                    <td key={col} className="max-w-60 truncate">
                      {cell(deal, col)}
                    </td>
                  ))}
                  <td>
                    <span className="inline-flex items-center gap-1.5 rounded-md border border-slate-200/80 bg-slate-50 px-2 py-0.5 text-xs font-medium text-slate-700 dark:border-slate-700/80 dark:bg-slate-800/70 dark:text-slate-300">
                      {stage && (
                        <span
                          className="h-1.5 w-1.5 rounded-full"
                          style={{ backgroundColor: stage.color }}
                        />
                      )}
                      {stage?.name ?? "—"}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {list.isPending && <p className="p-4 text-xs text-slate-500">Loading…</p>}
        {list.isError && <p className="p-4 text-xs text-red-600">Could not load deals.</p>}
        {!list.isPending && items.length === 0 && (
          <p className="p-4 text-xs text-slate-500">No deals. Adjust the filters.</p>
        )}
      </div>

      <div className="flex items-center gap-2 text-xs text-slate-500">
        <Button
          variant="secondary"
          size="sm"
          disabled={offset === 0}
          onClick={() => setOffset((value) => Math.max(0, value - limit))}
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
          onClick={() => setOffset((value) => value + limit)}
        >
          Next
        </Button>
      </div>
    </div>
  );
}
