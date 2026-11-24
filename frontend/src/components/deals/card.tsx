import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { CalendarClock, Lock, MessageSquarePlus, StickyNote } from "lucide-react";

import type { Deal } from "@/api/deals";
import { formatDate, formatMoney, formatPhone, formatRelative, initials } from "@/lib/format";
import { cn } from "@/lib/utils";

interface DealCardProps {
  deal: Deal;
  contactName: string | null;
  contactPhone: string | null;
  contactWhatsappId?: string | null;
  ownerName?: string | null;
  stageId: string;
  onOpen: (deal: Deal) => void;
  onNote: (deal: Deal) => void;
  onWrite: (deal: Deal) => void;
}

export function DealCard({
  deal,
  contactName,
  contactPhone,
  contactWhatsappId = null,
  ownerName = null,
  stageId,
  onOpen,
  onNote,
  onWrite,
}: DealCardProps) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: deal.id,
    data: { deal, stageId },
  });
  const phone = formatPhone(contactPhone, contactWhatsappId);

  return (
    <article
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      data-deal-id={deal.id}
      onClick={() => onOpen(deal)}
      className={cn(
        "group relative cursor-pointer rounded-md border border-slate-200/90 bg-white p-3 shadow-subtle transition-all hover:border-slate-300 hover:shadow-card dark:border-slate-800 dark:bg-[#151820] dark:hover:border-slate-700",
        isDragging && "z-10 opacity-60 shadow-elevated ring-2 ring-brand-500/30",
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <p
          className="min-w-0 flex-1 truncate text-[13px] font-semibold tracking-[-0.01em] text-slate-900 dark:text-slate-100"
          title={contactName ?? undefined}
        >
          {contactName ?? contactPhone ?? "No name"}
        </p>
        {deal.stage_locked && (
          <span
            title="Manager control"
            className="inline-flex h-4 w-4 items-center justify-center rounded bg-amber-100/80 text-amber-600 dark:bg-amber-950/60 dark:text-amber-400"
          >
            <Lock className="h-3 w-3 shrink-0" />
          </span>
        )}
      </div>

      <p className="mt-0.5 truncate text-xs text-slate-500 dark:text-slate-400">{deal.title}</p>
      {phone && (
        <p className="mt-0.5 truncate font-mono text-[11px] text-slate-400 dark:text-slate-500">
          {phone}
        </p>
      )}
      <p className="mt-1.5 font-mono text-xs font-semibold text-slate-800 dark:text-slate-200">
        {formatMoney(deal.amount, deal.currency)}
      </p>

      {deal.tags.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {deal.tags.slice(0, 3).map((tag) => (
            <span
              key={tag.id}
              className="inline-flex items-center rounded border border-slate-200/80 bg-slate-50 px-1.5 py-0.5 text-[10px] font-medium text-slate-600 dark:border-slate-700/80 dark:bg-slate-800/70 dark:text-slate-300"
            >
              {tag.name}
            </span>
          ))}
        </div>
      )}

      <div className="mt-2.5 flex items-center gap-1.5 border-t border-slate-100 pt-2 text-[11px] text-slate-500 dark:border-slate-800/70 dark:text-slate-400">
        <span
          title={deal.owner_id ? "Owner" : "No owner"}
          className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-brand-600/10 text-[9px] font-bold text-brand-700 dark:bg-brand-400/15 dark:text-brand-300"
        >
          {initials(ownerName)}
        </span>
        <span
          title={deal.owner_id ? "Owner" : "No owner"}
          className={cn(
            "max-w-[96px] truncate font-medium",
            !ownerName && "font-normal text-slate-400 dark:text-slate-500",
          )}
        >
          {ownerName ?? "Unassigned"}
        </span>
        <span className="ml-auto text-[10px] text-slate-400" title="Last activity">
          {formatRelative(deal.updated_at)}
        </span>
      </div>

      {deal.trial_at && (
        <div
          title={`Viewing: ${formatDate(deal.trial_at)}`}
          className="mt-1.5 inline-flex items-center gap-1 rounded bg-brand-50/80 px-1.5 py-0.5 text-[10px] font-medium text-brand-700 dark:bg-brand-950/40 dark:text-brand-300"
        >
          <CalendarClock className="h-3 w-3" />
          {formatDate(deal.trial_at)}
        </div>
      )}

      <div className="mt-1.5 flex items-center gap-0.5 opacity-0 transition-opacity group-hover:opacity-100 focus-within:opacity-100">
        <button
          type="button"
          title="Note"
          onClick={(event) => {
            event.stopPropagation();
            onNote(deal);
          }}
          className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-slate-800 dark:hover:text-slate-200"
        >
          <StickyNote className="h-3.5 w-3.5" />
        </button>
        <button
          type="button"
          title="Message"
          onClick={(event) => {
            event.stopPropagation();
            onWrite(deal);
          }}
          className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-slate-800 dark:hover:text-slate-200"
        >
          <MessageSquarePlus className="h-3.5 w-3.5" />
        </button>
        <button
          type="button"
          title="Drag (or Tab + Space)"
          {...attributes}
          {...listeners}
          className="ml-auto cursor-grab rounded px-1.5 py-0.5 text-xs text-slate-400 hover:bg-slate-100 hover:text-slate-700 active:cursor-grabbing dark:hover:bg-slate-800 dark:hover:text-slate-200"
        >
          ⋮⋮
        </button>
      </div>
    </article>
  );
}
