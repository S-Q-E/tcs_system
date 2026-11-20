import { useState } from "react";

import type { Contact, Deal } from "@/api/deals";
import {
  formatEtDateTime,
  useCreateViewingBooking,
  useUnits,
  useViewingBookings,
  useViewingSlots,
} from "@/api/viewings";
import { CancelBookingModal, RescheduleModal } from "@/pages/schedule";
import { toastError, useToast } from "@/components/toast";
import { Button } from "@/components/ui/button";

export function DealViewingPanel({ deal, contact }: { deal: Deal; contact: Contact | null }) {
  const { push } = useToast();
  const bookingsQuery = useViewingBookings({ deal_id: deal.id, limit: 20 });
  const openSlotsQuery = useViewingSlots({ status: "open", only_future: true, limit: 100 });
  const unitsQuery = useUnits({ status: "available", limit: 100 });
  const createBooking = useCreateViewingBooking();

  const [selectedSlotId, setSelectedSlotId] = useState("");
  const [selectedUnitId, setSelectedUnitId] = useState("");
  const [showReschedule, setShowReschedule] = useState(false);
  const [showCancel, setShowCancel] = useState(false);

  const activeBooking =
    bookingsQuery.data?.items.find((b) => b.status === "pending" || b.status === "confirmed") ??
    null;

  const book = async () => {
    if (!selectedSlotId) return;
    try {
      await createBooking.mutateAsync({
        slot_id: selectedSlotId,
        unit_id: selectedUnitId || null,
        deal_id: deal.id,
        contact_id: deal.contact_id,
        whatsapp_id: contact?.whatsapp_id ?? null,
        client_name: contact?.name ?? deal.title,
        client_phone: contact?.phone ?? null,
      });
      setSelectedSlotId("");
      push({ title: "Viewing booked", variant: "default" });
    } catch (error) {
      toastError(push, error);
    }
  };

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-3 text-sm dark:border-slate-800 dark:bg-slate-900">
      <div className="mb-2 flex items-center justify-between">
        <p className="font-medium">Viewing</p>
        {activeBooking && (
          <span className="rounded-full bg-blue-100 px-2 py-0.5 text-xs font-medium text-blue-800 dark:bg-blue-950 dark:text-blue-200">
            {activeBooking.status}
          </span>
        )}
      </div>

      {activeBooking ? (
        <div className="flex flex-col gap-2">
          <p className="font-medium text-slate-900 dark:text-slate-100">
            {formatEtDateTime(activeBooking.slot_starts_at)}
          </p>
          {activeBooking.unit_label && (
            <p className="text-xs text-slate-600 dark:text-slate-300">
              Unit: {activeBooking.unit_label}
            </p>
          )}
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="secondary" onClick={() => setShowReschedule(true)}>
              Reschedule
            </Button>
            <Button size="sm" variant="danger" onClick={() => setShowCancel(true)}>
              Cancel viewing
            </Button>
          </div>
          {showReschedule && (
            <RescheduleModal
              bookingId={activeBooking.id}
              currentStartsAt={activeBooking.slot_starts_at}
              onClose={() => setShowReschedule(false)}
            />
          )}
          {showCancel && (
            <CancelBookingModal
              bookingId={activeBooking.id}
              startsAt={activeBooking.slot_starts_at}
              onClose={() => setShowCancel(false)}
            />
          )}
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          <select
            aria-label="Viewing unit"
            value={selectedUnitId}
            onChange={(e) => setSelectedUnitId(e.target.value)}
            className="h-9 w-full rounded-md border border-slate-200 bg-white px-2 text-xs dark:border-slate-700 dark:bg-slate-900"
          >
            <option value="">Unit (optional)</option>
            {unitsQuery.data?.items.map((u) => (
              <option key={u.id} value={u.id}>
                {u.building} {u.unit_number} ({u.beds}BR, ${u.rent_usd})
              </option>
            ))}
          </select>
          <select
            aria-label="Open viewing slot"
            value={selectedSlotId}
            onChange={(e) => setSelectedSlotId(e.target.value)}
            className="h-9 w-full rounded-md border border-slate-200 bg-white px-2 text-xs dark:border-slate-700 dark:bg-slate-900"
          >
            <option value="">Choose an open slot…</option>
            {openSlotsQuery.data?.items.map((s) => (
              <option key={s.id} value={s.id}>
                {formatEtDateTime(s.starts_at)}
                {s.unit_label ? ` · ${s.unit_label}` : ""}
              </option>
            ))}
          </select>
          <Button
            size="sm"
            disabled={!selectedSlotId || createBooking.isPending}
            onClick={() => void book()}
          >
            Book viewing
          </Button>
        </div>
      )}
    </div>
  );
}
