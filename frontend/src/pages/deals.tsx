import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { api } from "@/api/client";
import type { Deal, DealFilters, Stage } from "@/api/deals";
import { usePipelines, useUsersLite } from "@/api/deals";
import { DealsBoard } from "@/components/deals/board";
import { DealFiltersBar } from "@/components/deals/filters";
import { DealDetail } from "@/components/deals/detail";
import { DealsListView } from "@/components/deals/list";
import { CreateDealModal, NoteModal } from "@/components/deals/modals";
import { cn } from "@/lib/utils";

function filtersFromParams(params: URLSearchParams): DealFilters {
  const tags = params.get("tags");
  return {
    search: params.get("q") ?? "",
    owner_id: params.get("owner") || undefined,
    tag: tags ? tags.split(",").filter(Boolean) : [],
    contact_source: params.get("source") || undefined,
    created_from: params.get("from") || undefined,
    created_to: params.get("to") || undefined,
  };
}

function filtersToParams(filters: DealFilters): URLSearchParams {
  const params = new URLSearchParams();
  if (filters.search) params.set("q", filters.search);
  if (filters.owner_id) params.set("owner", filters.owner_id);
  if (filters.tag?.length) params.set("tags", filters.tag.join(","));
  if (filters.contact_source) params.set("source", filters.contact_source);
  if (filters.created_from) params.set("from", filters.created_from);
  if (filters.created_to) params.set("to", filters.created_to);
  return params;
}

export function DealsPage() {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const pipelines = usePipelines();
  const users = useUsersLite();
  const [pipelineId, setPipelineId] = useState<string | null>(null);
  const [view, setView] = useState<"kanban" | "list">("kanban");
  const [createStageId, setCreateStageId] = useState<string | null>(null);
  const [noteDeal, setNoteDeal] = useState<Deal | null>(null);
  const [openDealId, setOpenDealId] = useState<string | null>(null);

  const filters = useMemo(() => filtersFromParams(params), [params]);
  const onFiltersChange = (next: DealFilters) => setParams(filtersToParams(next));

  const activePipeline =
    pipelines.data?.find((item) => item.id === pipelineId) ?? pipelines.data?.[0] ?? null;
  const activePipelineId = activePipeline?.id ?? null;

  const stageKind = useMemo(() => {
    const map = new Map<string, "open" | "won" | "lost">();
    for (const stage of activePipeline?.stages ?? []) {
      if (stage.kind === "open" || stage.kind === "won" || stage.kind === "lost") {
        map.set(stage.id, stage.kind);
      }
    }
    return map;
  }, [activePipeline]);
  const stageColor = useMemo(() => {
    const map = new Map<string, string>();
    for (const stage of activePipeline?.stages ?? []) {
      map.set(stage.id, stage.color);
    }
    return map;
  }, [activePipeline]);
  const stagesById = useMemo(() => {
    const map = new Map<string, Stage>();
    for (const stage of activePipeline?.stages ?? []) {
      map.set(stage.id, stage);
    }
    return map;
  }, [activePipeline]);

  const contacts = useQuery({
    queryKey: ["contacts-map"],
    queryFn: () =>
      api.get<{
        items: {
          id: string;
          name: string | null;
          phone: string | null;
          whatsapp_id: string | null;
        }[];
      }>("/api/contacts?limit=500"),
    staleTime: 60_000,
  });
  const ownerNamesById = useMemo(() => {
    const map = new Map<string, string>();
    for (const user of users.data?.items ?? []) {
      map.set(user.id, user.name);
    }
    return map;
  }, [users.data]);

  const contactsById = useMemo(() => {
    const map = new Map<
      string,
      { name: string | null; phone: string | null; whatsappId: string | null }
    >();
    for (const contact of contacts.data?.items ?? []) {
      map.set(contact.id, {
        name: contact.name,
        phone: contact.phone,
        whatsappId: contact.whatsapp_id,
      });
    }
    return map;
  }, [contacts.data]);

  if (pipelines.isPending) {
    return (
      <div className="flex gap-3 overflow-x-auto pb-4" aria-label="Loading">
        {[0, 1, 2].map((index) => (
          <div
            key={index}
            className="h-64 w-72 shrink-0 animate-pulse rounded-lg border border-slate-200/70 bg-slate-100/70 dark:border-slate-800/70 dark:bg-slate-900/50"
          />
        ))}
      </div>
    );
  }

  if (pipelines.isError || !activePipeline || !activePipelineId) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-5 text-xs text-red-900 dark:border-red-900 dark:bg-red-950 dark:text-red-100">
        Could not load pipelines.{" "}
        <button type="button" className="font-medium underline" onClick={() => pipelines.refetch()}>
          Try again
        </button>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="mr-1 text-base font-semibold tracking-[-0.015em] text-slate-900 dark:text-slate-100">
            Deals
          </h1>
          <select
            aria-label="Pipeline"
            value={activePipelineId}
            onChange={(event) => setPipelineId(event.target.value)}
            className="ui-select font-medium"
          >
            {pipelines.data?.map((pipeline) => (
              <option key={pipeline.id} value={pipeline.id}>
                {pipeline.name}
              </option>
            ))}
          </select>
          <div className="inline-flex rounded-md border border-slate-200/90 bg-slate-100/80 p-0.5 dark:border-slate-800 dark:bg-[#14171D]">
            {(["kanban", "list"] as const).map((mode) => (
              <button
                key={mode}
                type="button"
                onClick={() => setView(mode)}
                className={cn(
                  "rounded-[5px] px-2.5 py-1 text-xs font-medium transition-all",
                  view === mode
                    ? "bg-white text-slate-900 shadow-subtle dark:bg-[#1E222B] dark:text-white"
                    : "text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-200",
                )}
              >
                {mode === "kanban" ? "Kanban" : "List"}
              </button>
            ))}
          </div>
        </div>
      </div>

      <DealFiltersBar filters={filters} onChange={onFiltersChange} />

      {view === "kanban" ? (
        <DealsBoard
          key={`board-${activePipelineId}-${JSON.stringify(filters)}`}
          pipelineId={activePipelineId}
          pipelineName={activePipeline.name}
          stageKind={stageKind}
          stageColor={stageColor}
          filters={filters}
          contactsById={contactsById}
          ownerNamesById={ownerNamesById}
          onQuickCreate={setCreateStageId}
          onOpen={(deal) => setOpenDealId(deal.id)}
          onNote={setNoteDeal}
          onWrite={(deal) => {
            const whatsappId = contactsById.get(deal.contact_id)?.whatsappId;
            navigate(whatsappId ? `/dialogs?wa=${encodeURIComponent(whatsappId)}` : "/dialogs");
          }}
        />
      ) : (
        <DealsListView
          key={`list-${JSON.stringify(filters)}`}
          filters={filters}
          stagesById={stagesById}
          contactsById={contactsById}
          onOpen={(id) => setOpenDealId(id)}
        />
      )}

      {createStageId && (
        <CreateDealModal
          stageId={createStageId}
          pipelineId={activePipelineId}
          onClose={() => setCreateStageId(null)}
        />
      )}
      {noteDeal && <NoteModal deal={noteDeal} onClose={() => setNoteDeal(null)} />}
      {openDealId && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="Deal card"
          className="fixed inset-0 z-30 flex justify-end bg-slate-950/40 backdrop-blur-[1px]"
          onClick={() => setOpenDealId(null)}
        >
          <div
            className="h-full w-full max-w-4xl overflow-y-auto border-l border-slate-200/80 bg-[#F8F9FB] p-4 shadow-modal dark:border-slate-800 dark:bg-[#0E1014] md:p-6"
            onClick={(event) => event.stopPropagation()}
          >
            <DealDetail dealId={openDealId} onClose={() => setOpenDealId(null)} />
          </div>
        </div>
      )}
    </div>
  );
}
