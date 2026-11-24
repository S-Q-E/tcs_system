import { useDroppable } from "@dnd-kit/core";
import { SortableContext, verticalListSortingStrategy } from "@dnd-kit/sortable";
import { Plus } from "lucide-react";

import type { BoardColumn, Deal } from "@/api/deals";
import { DealCard } from "@/components/deals/card";
import { Button } from "@/components/ui/button";
import { formatMoney } from "@/lib/format";
import { cn } from "@/lib/utils";

interface ColumnProps {
  column: BoardColumn;
  color: string;
  contactsById: Map<
    string,
    { name: string | null; phone: string | null; whatsappId?: string | null }
  >;
  ownerNamesById: Map<string, string>;
  activeStageId: string | null;
  loadingMore: boolean;
  onShowMore: (stageId: string) => void;
  onQuickCreate: (stageId: string) => void;
  onOpen: (deal: Deal) => void;
  onNote: (deal: Deal) => void;
  onWrite: (deal: Deal) => void;
}

export function BoardColumnView({
  column,
  color,
  contactsById,
  ownerNamesById,
  activeStageId,
  loadingMore,
  onShowMore,
  onQuickCreate,
  onOpen,
  onNote,
  onWrite,
}: ColumnProps) {
  const { setNodeRef, isOver } = useDroppable({
    id: column.stage_id,
    data: { stageId: column.stage_id },
  });
  const dealIds = column.items.map((item) => item.id);

  return (
    <section
      aria-label={column.name}
      className={cn(
        "flex max-h-full w-72 shrink-0 flex-col rounded-lg border border-slate-200/75 bg-slate-100/60 transition-all dark:border-slate-800/80 dark:bg-[#111318]",
        isOver && "border-brand-400/70 bg-brand-50/30 ring-2 ring-brand-500/20 dark:border-brand-500/50 dark:bg-brand-950/15",
      )}
    >
      <header className="flex items-center gap-2 border-b border-slate-200/60 px-3 py-2.5 dark:border-slate-800/70">
        <span
          aria-hidden
          className="h-2 w-2 shrink-0 rounded-full"
          style={{ backgroundColor: color }}
        />
        <h2 className="min-w-0 flex-1 truncate text-xs font-semibold tracking-[-0.01em] text-slate-800 dark:text-slate-100">
          {column.name}
        </h2>
        <span className="rounded-md bg-slate-200/70 px-1.5 py-0.5 font-mono text-[11px] font-medium text-slate-600 dark:bg-slate-800 dark:text-slate-400">
          {column.total}
        </span>
      </header>
      <p className="px-3 py-1.5 font-mono text-[11px] font-medium text-slate-500 dark:text-slate-400">
        {formatMoney(column.amount_total)}
      </p>

      <div
        ref={setNodeRef}
        className="flex min-h-16 flex-1 flex-col gap-2 overflow-y-auto px-2 pb-2"
      >
        <SortableContext items={dealIds} strategy={verticalListSortingStrategy}>
          {column.items.map((deal) => {
            const contact = contactsById.get(deal.contact_id);
            return (
              <DealCard
                key={deal.id}
                deal={deal}
                contactName={contact?.name ?? null}
                contactPhone={contact?.phone ?? null}
                contactWhatsappId={contact?.whatsappId ?? null}
                ownerName={deal.owner_id ? (ownerNamesById.get(deal.owner_id) ?? null) : null}
                stageId={column.stage_id}
                onOpen={onOpen}
                onNote={onNote}
                onWrite={onWrite}
              />
            );
          })}
        </SortableContext>
        {column.items.length === 0 && (
          <p className="rounded-md border border-dashed border-slate-300/80 p-5 text-center text-xs text-slate-400 dark:border-slate-800 dark:text-slate-500">
            Drop a deal here
          </p>
        )}
        {column.next_cursor && (
          <Button
            variant="secondary"
            size="sm"
            disabled={loadingMore}
            onClick={() => onShowMore(column.stage_id)}
          >
            {loadingMore ? "Loading…" : `Show more (${column.total} total)`}
          </Button>
        )}
      </div>

      <div className="border-t border-slate-200/50 p-1.5 dark:border-slate-800/60">
        <Button
          variant="ghost"
          size="sm"
          className="w-full justify-start text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-100"
          onClick={() => onQuickCreate(column.stage_id)}
        >
          <Plus className="h-3.5 w-3.5" /> Quick deal
        </Button>
      </div>
      {activeStageId === column.stage_id && <span className="sr-only">Target column</span>}
    </section>
  );
}
