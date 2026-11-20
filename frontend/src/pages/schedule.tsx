import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { useMe } from "@/api/auth";
import {
  formatEtDateTime,
  formatEtDayKey,
  formatEtDayLabel,
  formatEtTime,
  useCancelViewingBooking,
  useCreateViewingBooking,
  useCreateViewingSlot,
  useDeleteViewingSlot,
  useGenerateViewingSlots,
  useRescheduleViewingBooking,
  useUnits,
  useUpdateViewingSlot,
  useViewingSlots,
  type SlotStatus,
  type ViewingSlot,
} from "@/api/viewings";
import { ModalShell } from "@/components/deals/modals";
import { toastError, useToast } from "@/components/toast";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { localInputToIso } from "@/lib/datetime";
import { cn } from "@/lib/utils";

const SLOT_BADGE: Record<SlotStatus, string> = {
  open: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200",
  booked: "bg-blue-100 text-blue-800 dark:bg-blue-950 dark:text-blue-200",
  blocked: "bg-slate-200 text-slate-700 dark:bg-slate-800 dark:text-slate-300",
};

function startOfWeekUtc(weekOffset: number): Date {
  const now = new Date();
  const day = now.getUTCDay(); // 0=Sun..6=Sat
  const diffToMon = (day + 6) % 7;
  const mon = new Date(
    Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate() - diffToMon + weekOffset * 7),
  );
  return mon;
}

export function SchedulePage() {
  const { data: me } = useMe();
  const isAdmin = me?.role === "admin";
  const { push } = useToast();

  const [weekOffset, setWeekOffset] = useState(0);
  const [statusFilter, setStatusFilter] = useState("");
  const [showAddSlot, setShowAddSlot] = useState(false);
  const [bookingSlot, setBookingSlot] = useState<ViewingSlot | null>(null);
  const [rescheduleTarget, setRescheduleTarget] = useState<ViewingSlot | null>(null);
  const [cancelTarget, setCancelTarget] = useState<ViewingSlot | null>(null);

  const { fromIso, toIso, rangeLabel } = useMemo(() => {
    const start = startOfWeekUtc(weekOffset);
    const end = new Date(start.getTime() + 7 * 24 * 60 * 60 * 1000);
    const fmt = new Intl.DateTimeFormat("en-US", {
      month: "short",
      day: "numeric",
      timeZone: "UTC",
    });
    const endDisplay = new Date(end.getTime() - 1000);
    return {
      fromIso: start.toISOString(),
      toIso: end.toISOString(),
      rangeLabel: `${fmt.format(start)} – ${fmt.format(endDisplay)}`,
    };
  }, [weekOffset]);

  const slotsQuery = useViewingSlots({
    from: fromIso,
    to: toIso,
    status: statusFilter || undefined,
    limit: 300,
  });
  const generateSlots = useGenerateViewingSlots();
  const updateSlot = useUpdateViewingSlot();
  const deleteSlot = useDeleteViewingSlot();

  const grouped = useMemo(() => {
    const items = slotsQuery.data?.items ?? [];
    const map = new Map<string, { label: string; slots: ViewingSlot[] }>();
    for (const slot of items) {
      const key = formatEtDayKey(slot.starts_at);
      const bucket = map.get(key) ?? { label: formatEtDayLabel(slot.starts_at), slots: [] };
      bucket.slots.push(slot);
      map.set(key, bucket);
    }
    return Array.from(map.entries());
  }, [slotsQuery.data]);

  const onGenerate = async () => {
    try {
      const res = await generateSlots.mutateAsync({ days: 14 });
      push({
        title: `Generated ${res.created} new slot(s)`,
        description: `${res.total_candidates} weekday slots checked for next 14 days`,
        variant: "default",
      });
    } catch (error) {
      toastError(push, error);
    }
  };

  const toggleBlock = async (slot: ViewingSlot) => {
    const next = slot.status === "blocked" ? "open" : "blocked";
    try {
      await updateSlot.mutateAsync({ id: slot.id, patch: { status: next } });
      push({ title: next === "blocked" ? "Slot blocked" : "Slot opened", variant: "default" });
    } catch (error) {
      toastError(push, error);
    }
  };

  const removeSlot = async (slot: ViewingSlot) => {
    if (!window.confirm(`Delete slot ${formatEtDateTime(slot.starts_at)}?`)) return;
    try {
      await deleteSlot.mutateAsync(slot.id);
      push({ title: "Slot deleted", variant: "default" });
    } catch (error) {
      toastError(push, error);
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <h1 className="text-xl font-bold">Schedule</h1>
        <span className="text-xs text-slate-500">(times shown in America/New_York)</span>
        <div className="flex items-center gap-1 md:ml-4">
          <Button variant="secondary" size="sm" onClick={() => setWeekOffset((w) => w - 1)}>
            Prev week
          </Button>
          <Button variant="ghost" size="sm" onClick={() => setWeekOffset(0)}>
            {rangeLabel}
          </Button>
          <Button variant="secondary" size="sm" onClick={() => setWeekOffset((w) => w + 1)}>
            Next week
          </Button>
        </div>
        <select
          aria-label="Slot status filter"
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="h-9 rounded-md border border-slate-200 bg-white px-2 text-sm dark:border-slate-700 dark:bg-slate-900"
        >
          <option value="">All slots</option>
          <option value="open">Open</option>
          <option value="booked">Booked</option>
          <option value="blocked">Blocked</option>
        </select>
        {isAdmin && (
          <div className="ml-auto flex gap-2">
            <Button
              variant="secondary"
              size="sm"
              disabled={generateSlots.isPending}
              onClick={() => void onGenerate()}
            >
              Generate 14 days
            </Button>
            <Button size="sm" onClick={() => setShowAddSlot(true)}>
              + Add slot
            </Button>
          </div>
        )}
      </div>

      {slotsQuery.isPending && <p className="text-sm text-slate-500">Loading schedule…</p>}
      {slotsQuery.isError && <p className="text-sm text-red-600">Could not load schedule.</p>}
      {!slotsQuery.isPending && grouped.length === 0 && (
        <div className="rounded-lg border border-slate-200 bg-white p-6 text-sm text-slate-500 dark:border-slate-800 dark:bg-slate-900">
          No viewing slots in this week.
          {isAdmin && " Click “Generate 14 days” or “+ Add slot” to create slots."}
        </div>
      )}

      <div className="flex flex-col gap-4">
        {grouped.map(([dayKey, group]) => (
          <section
            key={dayKey}
            className="rounded-lg border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900"
          >
            <header className="border-b border-slate-200 px-3 py-2 text-sm font-semibold dark:border-slate-800">
              {group.label}
            </header>
            <ul className="divide-y divide-slate-100 dark:divide-slate-800">
              {group.slots.map((slot) => (
                <li
                  key={slot.id}
                  className="flex flex-wrap items-center gap-3 px-3 py-2.5 text-sm"
                >
                  <span className="w-24 font-mono text-xs font-medium">
                    {formatEtTime(slot.starts_at)}
                  </span>
                  <span className="text-xs text-slate-500">{slot.duration_min}m</span>
                  <span
                    className={cn(
                      "rounded-full px-2 py-0.5 text-xs font-medium",
                      SLOT_BADGE[slot.status],
                    )}
                  >
                    {slot.status}
                  </span>
                  {slot.unit_label && (
                    <span className="text-xs text-slate-600 dark:text-slate-300">
                      Unit: {slot.unit_label}
                    </span>
                  )}
                  {slot.booking && (
                    <div className="flex flex-wrap items-center gap-2 text-xs">
                      <span className="font-medium">
                        {slot.booking.client_name ?? slot.booking.whatsapp_id ?? "Client"}
                      </span>
                      {slot.booking.client_phone && (
                        <span className="text-slate-500">{slot.booking.client_phone}</span>
                      )}
                      {slot.booking.unit_label && (
                        <span className="rounded bg-slate-100 px-1.5 py-0.5 dark:bg-slate-800">
                          {slot.booking.unit_label}
                        </span>
                      )}
                      {slot.booking.deal_id && (
                        <Link
                          to={`/deals/${slot.booking.deal_id}`}
                          className="text-blue-600 hover:underline"
                        >
                          Open deal
                        </Link>
                      )}
                    </div>
                  )}
                  <div className="ml-auto flex flex-wrap gap-1.5">
                    {slot.status === "open" && (
                      <>
                        <Button size="sm" variant="secondary" onClick={() => setBookingSlot(slot)}>
                          Book
                        </Button>
                        {isAdmin && (
                          <>
                            <Button
                              size="sm"
                              variant="ghost"
                              onClick={() => void toggleBlock(slot)}
                            >
                              Block
                            </Button>
                            <Button
                              size="sm"
                              variant="ghost"
                              onClick={() => void removeSlot(slot)}
                            >
                              Delete
                            </Button>
                          </>
                        )}
                      </>
                    )}
                    {slot.status === "blocked" && isAdmin && (
                      <>
                        <Button
                          size="sm"
                          variant="secondary"
                          onClick={() => void toggleBlock(slot)}
                        >
                          Unblock
                        </Button>
                        <Button size="sm" variant="ghost" onClick={() => void removeSlot(slot)}>
                          Delete
                        </Button>
                      </>
                    )}
                    {slot.status === "booked" && slot.booking && (
                      <>
                        <Button
                          size="sm"
                          variant="secondary"
                          onClick={() => setRescheduleTarget(slot)}
                        >
                          Reschedule
                        </Button>
                        <Button size="sm" variant="danger" onClick={() => setCancelTarget(slot)}>
                          Cancel
                        </Button>
                      </>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>

      {showAddSlot && <AddSlotModal onClose={() => setShowAddSlot(false)} />}
      {bookingSlot && <BookSlotModal slot={bookingSlot} onClose={() => setBookingSlot(null)} />}
      {rescheduleTarget && rescheduleTarget.booking && (
        <RescheduleModal
          bookingId={rescheduleTarget.booking.id}
          currentStartsAt={rescheduleTarget.starts_at}
          onClose={() => setRescheduleTarget(null)}
        />
      )}
      {cancelTarget && cancelTarget.booking && (
        <CancelBookingModal
          bookingId={cancelTarget.booking.id}
          startsAt={cancelTarget.starts_at}
          onClose={() => setCancelTarget(null)}
        />
      )}
    </div>
  );
}

function AddSlotModal({ onClose }: { onClose: () => void }) {
  const { push } = useToast();
  const createSlot = useCreateViewingSlot();
  const units = useUnits({ status: "available", limit: 100 });
  const [startsLocal, setStartsLocal] = useState("");
  const [durationMin, setDurationMin] = useState("60");
  const [unitId, setUnitId] = useState("");

  const save = async () => {
    const iso = localInputToIso(startsLocal);
    if (!iso) return;
    try {
      await createSlot.mutateAsync({
        starts_at: iso,
        duration_min: Number(durationMin) || 60,
        unit_id: unitId || null,
      });
      push({ title: "Slot created", variant: "default" });
      onClose();
    } catch (error) {
      toastError(push, error);
    }
  };

  return (
    <ModalShell title="Add viewing slot" onClose={onClose}>
      <div className="flex flex-col gap-3 text-sm">
        <label className="block">
          Date & time *
          <Input
            className="mt-1"
            type="datetime-local"
            value={startsLocal}
            onChange={(e) => setStartsLocal(e.target.value)}
          />
        </label>
        <label className="block">
          Duration (minutes)
          <Input
            className="mt-1"
            type="number"
            min="15"
            max="480"
            value={durationMin}
            onChange={(e) => setDurationMin(e.target.value)}
          />
        </label>
        <label className="block">
          Unit (optional)
          <select
            value={unitId}
            onChange={(e) => setUnitId(e.target.value)}
            className="mt-1 h-9 w-full rounded-md border border-slate-200 bg-white px-2 text-sm dark:border-slate-700 dark:bg-slate-900"
          >
            <option value="">Any unit (general slot)</option>
            {units.data?.items.map((u) => (
              <option key={u.id} value={u.id}>
                {u.building} {u.unit_number} ({u.beds}BR, ${u.rent_usd})
              </option>
            ))}
          </select>
        </label>
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button disabled={createSlot.isPending || !startsLocal} onClick={() => void save()}>
            Create
          </Button>
        </div>
      </div>
    </ModalShell>
  );
}

function BookSlotModal({ slot, onClose }: { slot: ViewingSlot; onClose: () => void }) {
  const { push } = useToast();
  const createBooking = useCreateViewingBooking();
  const units = useUnits({ status: "available", limit: 100 });
  const [unitId, setUnitId] = useState(slot.unit_id ?? "");
  const [clientName, setClientName] = useState("");
  const [clientPhone, setClientPhone] = useState("");
  const [notes, setNotes] = useState("");

  const save = async () => {
    try {
      await createBooking.mutateAsync({
        slot_id: slot.id,
        unit_id: unitId || null,
        client_name: clientName.trim() || null,
        client_phone: clientPhone.trim() || null,
        notes: notes.trim() || null,
      });
      push({ title: "Viewing booked", variant: "default" });
      onClose();
    } catch (error) {
      toastError(push, error);
    }
  };

  return (
    <ModalShell title={`Book ${formatEtDateTime(slot.starts_at)}`} onClose={onClose}>
      <div className="flex flex-col gap-2.5 text-sm">
        <label className="block">
          Unit
          <select
            value={unitId}
            disabled={Boolean(slot.unit_id)}
            onChange={(e) => setUnitId(e.target.value)}
            className="mt-1 h-9 w-full rounded-md border border-slate-200 bg-white px-2 text-sm dark:border-slate-700 dark:bg-slate-900"
          >
            <option value="">Not specified</option>
            {units.data?.items.map((u) => (
              <option key={u.id} value={u.id}>
                {u.building} {u.unit_number}
              </option>
            ))}
          </select>
        </label>
        <label className="block">
          Client name
          <Input
            className="mt-1"
            value={clientName}
            onChange={(e) => setClientName(e.target.value)}
          />
        </label>
        <label className="block">
          Client phone
          <Input
            className="mt-1"
            value={clientPhone}
            onChange={(e) => setClientPhone(e.target.value)}
          />
        </label>
        <label className="block">
          Notes
          <Input className="mt-1" value={notes} onChange={(e) => setNotes(e.target.value)} />
        </label>
        <div className="mt-2 flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button disabled={createBooking.isPending} onClick={() => void save()}>
            Book viewing
          </Button>
        </div>
      </div>
    </ModalShell>
  );
}

export function RescheduleModal({
  bookingId,
  currentStartsAt,
  onClose,
}: {
  bookingId: string;
  currentStartsAt: string | null;
  onClose: () => void;
}) {
  const { push } = useToast();
  const reschedule = useRescheduleViewingBooking();
  const openSlots = useViewingSlots({ status: "open", only_future: true, limit: 100 });
  const [newSlotId, setNewSlotId] = useState("");

  const save = async () => {
    if (!newSlotId) return;
    try {
      await reschedule.mutateAsync({ id: bookingId, new_slot_id: newSlotId });
      push({ title: "Viewing rescheduled", variant: "default" });
      onClose();
    } catch (error) {
      toastError(push, error);
    }
  };

  return (
    <ModalShell title="Reschedule viewing" onClose={onClose}>
      <div className="flex flex-col gap-3 text-sm">
        {currentStartsAt && (
          <p className="text-slate-500">Current: {formatEtDateTime(currentStartsAt)}</p>
        )}
        <label className="block">
          New open slot
          <select
            aria-label="New open slot"
            value={newSlotId}
            onChange={(e) => setNewSlotId(e.target.value)}
            className="mt-1 h-9 w-full rounded-md border border-slate-200 bg-white px-2 text-sm dark:border-slate-700 dark:bg-slate-900"
          >
            <option value="">Choose a slot…</option>
            {openSlots.data?.items.map((s) => (
              <option key={s.id} value={s.id}>
                {formatEtDateTime(s.starts_at)}
                {s.unit_label ? ` · ${s.unit_label}` : ""}
              </option>
            ))}
          </select>
        </label>
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button disabled={reschedule.isPending || !newSlotId} onClick={() => void save()}>
            Reschedule
          </Button>
        </div>
      </div>
    </ModalShell>
  );
}

export function CancelBookingModal({
  bookingId,
  startsAt,
  onClose,
}: {
  bookingId: string;
  startsAt: string | null;
  onClose: () => void;
}) {
  const { push } = useToast();
  const cancelBooking = useCancelViewingBooking();
  const [reason, setReason] = useState("");

  const save = async () => {
    try {
      await cancelBooking.mutateAsync({ id: bookingId, reason: reason.trim() || null });
      push({ title: "Viewing cancelled", variant: "default" });
      onClose();
    } catch (error) {
      toastError(push, error);
    }
  };

  return (
    <ModalShell title="Cancel viewing" onClose={onClose}>
      <div className="flex flex-col gap-3 text-sm">
        {startsAt && <p className="text-slate-600">Viewing: {formatEtDateTime(startsAt)}</p>}
        <label className="block">
          Reason (optional)
          <Input
            className="mt-1"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Client plans changed…"
          />
        </label>
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>
            Keep
          </Button>
          <Button variant="danger" disabled={cancelBooking.isPending} onClick={() => void save()}>
            Cancel viewing
          </Button>
        </div>
      </div>
    </ModalShell>
  );
}
