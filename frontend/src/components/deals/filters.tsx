import { useState } from "react";

import type { DealFilters } from "@/api/deals";
import {
  useCreateSavedView,
  useDeleteSavedView,
  useSavedViews,
  useTags,
  useUsersLite,
} from "@/api/deals";
import { useToast, toastError } from "@/components/toast";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

interface FiltersProps {
  filters: DealFilters;
  onChange: (filters: DealFilters) => void;
}

export function DealFiltersBar({ filters, onChange }: FiltersProps) {
  const { push } = useToast();
  const tags = useTags();
  const users = useUsersLite();
  const savedViews = useSavedViews();
  const createView = useCreateSavedView();
  const deleteView = useDeleteSavedView();
  const [viewName, setViewName] = useState("");
  const [saving, setSaving] = useState(false);

  const set = (patch: Partial<DealFilters>) => onChange({ ...filters, ...patch });

  const saveView = async () => {
    const name = viewName.trim();
    if (!name) {
      return;
    }
    try {
      await createView.mutateAsync({ name, filters });
      setViewName("");
      setSaving(false);
    } catch (error) {
      toastError(push, error);
    }
  };

  const applyView = (viewFilters: DealFilters) => onChange({ ...viewFilters });

  const removeView = async (id: string) => {
    try {
      await deleteView.mutateAsync(id);
    } catch (error) {
      toastError(push, error);
    }
  };

  const clearAll = () =>
    onChange({
      search: "",
      owner_id: undefined,
      tag: [],
      contact_source: "",
      created_from: "",
      created_to: "",
    });

  return (
    <div className="flex flex-wrap items-center gap-1.5 rounded-lg border border-slate-200/80 bg-white/80 p-2 shadow-subtle dark:border-slate-800/80 dark:bg-[#121418]/80">
      <Input
        value={filters.search ?? ""}
        onChange={(event) => set({ search: event.target.value })}
        placeholder="Search by title"
        className="w-44"
      />
      <select
        aria-label="Owner"
        value={filters.owner_id ?? ""}
        onChange={(event) => set({ owner_id: event.target.value || undefined })}
        className="ui-select"
      >
        <option value="">All owners</option>
        {users.data?.items.map((user) => (
          <option key={user.id} value={user.id}>
            {user.name}
          </option>
        ))}
      </select>
      <select
        aria-label="Tag"
        value={filters.tag?.[0] ?? ""}
        onChange={(event) => set({ tag: event.target.value ? [event.target.value] : [] })}
        className="ui-select"
      >
        <option value="">All tags</option>
        {tags.data?.items.map((tag) => (
          <option key={tag.id} value={tag.id}>
            {tag.name}
          </option>
        ))}
      </select>
      <select
        aria-label="Source"
        value={filters.contact_source ?? ""}
        onChange={(event) => set({ contact_source: event.target.value || undefined })}
        className="ui-select"
      >
        <option value="">All sources</option>
        <option value="bot">Bot</option>
        <option value="manual">Manual</option>
      </select>
      <Input
        aria-label="Created from"
        type="date"
        value={filters.created_from?.slice(0, 10) ?? ""}
        onChange={(event) => set({ created_from: event.target.value || undefined })}
        className="w-36"
      />
      <Input
        aria-label="Created to"
        type="date"
        value={filters.created_to?.slice(0, 10) ?? ""}
        onChange={(event) => set({ created_to: event.target.value || undefined })}
        className="w-36"
      />
      <Button variant="ghost" size="sm" onClick={clearAll}>
        Reset
      </Button>

      <span className="mx-1 hidden h-4 w-px bg-slate-200 dark:bg-slate-800 md:block" />

      <div className="flex flex-wrap items-center gap-1">
        {savedViews.data?.items.map((view) => (
          <span
            key={view.id}
            className="inline-flex items-center gap-1 rounded-md border border-slate-200/80 bg-slate-50 py-0.5 pl-2 pr-1 text-xs font-medium text-slate-700 dark:border-slate-800 dark:bg-[#181B22] dark:text-slate-300"
          >
            <button
              type="button"
              onClick={() => applyView(view.filters)}
              title={view.name}
              className="hover:text-brand-600 dark:hover:text-brand-400"
            >
              {view.name}
            </button>
            <button
              type="button"
              aria-label={`Delete view ${view.name}`}
              onClick={() => void removeView(view.id)}
              className="rounded px-1 text-slate-400 hover:text-red-600"
            >
              ×
            </button>
          </span>
        ))}
        {saving ? (
          <span className="flex items-center gap-1">
            <Input
              value={viewName}
              onChange={(event) => setViewName(event.target.value)}
              placeholder="View name"
              className="h-7 w-36"
            />
            <Button size="sm" onClick={() => void saveView()} disabled={createView.isPending}>
              OK
            </Button>
          </span>
        ) : (
          <Button variant="ghost" size="sm" onClick={() => setSaving(true)}>
            Save view
          </Button>
        )}
      </div>
    </div>
  );
}
