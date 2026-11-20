import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/api/client";

export type UnitStatus = "available" | "leased" | "hidden";
export type SlotStatus = "open" | "booked" | "blocked";
export type BookingStatus = "pending" | "confirmed" | "cancelled" | "no_show";

export interface Unit {
  id: string;
  building: string;
  unit_number: string;
  beds: number;
  baths: number;
  rent_usd: number;
  deposit_usd: number | null;
  available_from: string | null;
  pets_policy: string | null;
  description: string | null;
  status: UnitStatus;
  photos: string[];
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
}

export interface UnitFilters {
  status?: string;
  building?: string;
  beds?: number;
  max_rent?: number;
  search?: string;
  limit?: number;
  offset?: number;
}

export interface UnitCreateInput {
  building: string;
  unit_number: string;
  beds: number;
  baths: number;
  rent_usd: number;
  deposit_usd?: number | null;
  available_from?: string | null;
  pets_policy?: string | null;
  description?: string | null;
  status?: UnitStatus;
}

export interface SlotBookingBrief {
  id: string;
  status: BookingStatus;
  unit_id: string | null;
  unit_label: string | null;
  deal_id: string | null;
  contact_id: string | null;
  whatsapp_id: string | null;
  client_name: string | null;
  client_phone: string | null;
  notes: string | null;
}

export interface ViewingSlot {
  id: string;
  starts_at: string;
  duration_min: number;
  unit_id: string | null;
  unit_label: string | null;
  status: SlotStatus;
  created_by: string | null;
  created_at: string;
  booking: SlotBookingBrief | null;
}

export interface ViewingBooking {
  id: string;
  slot_id: string;
  slot_starts_at: string | null;
  slot_duration_min: number | null;
  unit_id: string | null;
  unit_label: string | null;
  deal_id: string | null;
  contact_id: string | null;
  whatsapp_id: string | null;
  client_name: string | null;
  client_phone: string | null;
  status: BookingStatus;
  notes: string | null;
  created_by: string | null;
  created_at: string;
  updated_at: string;
  cancelled_at: string | null;
}

export interface UnitImportJob {
  id: string;
  entity: string;
  status: "queued" | "running" | "done" | "failed";
  total: number;
  ok_count: number;
  error_count: number;
  errors: { row?: number; error: string }[];
  created_at: string;
  finished_at: string | null;
}

export const VIEWING_TZ = "America/New_York";

export function formatEtDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return (
    new Intl.DateTimeFormat("en-US", {
      timeZone: VIEWING_TZ,
      weekday: "short",
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
    }).format(date) + " ET"
  );
}

export function formatEtDayKey(iso: string): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: VIEWING_TZ,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date(iso));
  const map = Object.fromEntries(parts.map((p) => [p.type, p.value]));
  return `${map.year}-${map.month}-${map.day}`;
}

export function formatEtDayLabel(iso: string): string {
  return new Intl.DateTimeFormat("en-US", {
    timeZone: VIEWING_TZ,
    weekday: "long",
    month: "short",
    day: "numeric",
  }).format(new Date(iso));
}

export function formatEtTime(iso: string): string {
  return (
    new Intl.DateTimeFormat("en-US", {
      timeZone: VIEWING_TZ,
      hour: "numeric",
      minute: "2-digit",
    }).format(new Date(iso)) + " ET"
  );
}

function buildQuery(params: Record<string, string | number | boolean | undefined | null>): string {
  const search = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === "") continue;
    search.set(k, String(v));
  }
  const s = search.toString();
  return s ? `?${s}` : "";
}

export function useUnits(filters: UnitFilters = {}) {
  const qs = buildQuery({
    status: filters.status,
    building: filters.building,
    beds: filters.beds,
    max_rent: filters.max_rent,
    search: filters.search,
    limit: filters.limit ?? 100,
    offset: filters.offset ?? 0,
  });
  return useQuery({
    queryKey: ["units", filters],
    queryFn: () => api.get<{ items: Unit[]; total: number }>(`/api/units${qs}`),
  });
}

export function useCreateUnit() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: UnitCreateInput) => api.post<Unit>("/api/units", input),
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: ["units"] });
    },
  });
}

export function useUpdateUnit() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: { id: string; patch: Partial<UnitCreateInput> }) =>
      api.patch<Unit>(`/api/units/${input.id}`, input.patch),
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: ["units"] });
      void qc.invalidateQueries({ queryKey: ["viewing-slots"] });
      void qc.invalidateQueries({ queryKey: ["viewing-bookings"] });
    },
  });
}

export function useDeleteUnit() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.del<{ ok: boolean }>(`/api/units/${id}`),
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: ["units"] });
    },
  });
}

export function useUnitImportJob(jobId: string | null, enabled: boolean) {
  return useQuery({
    queryKey: ["unit-import-job", jobId],
    queryFn: () => api.get<UnitImportJob>(`/api/units/import/${jobId}`),
    enabled: Boolean(jobId) && enabled,
    refetchInterval: 1000,
  });
}

export interface SlotFilters {
  from?: string;
  to?: string;
  status?: string;
  unit_id?: string;
  only_future?: boolean;
  limit?: number;
}

export function useViewingSlots(filters: SlotFilters = {}) {
  const qs = buildQuery({
    from: filters.from,
    to: filters.to,
    status: filters.status,
    unit_id: filters.unit_id,
    only_future: filters.only_future ? "true" : undefined,
    limit: filters.limit ?? 300,
  });
  return useQuery({
    queryKey: ["viewing-slots", filters],
    queryFn: () => api.get<{ items: ViewingSlot[]; total: number }>(`/api/viewing-slots${qs}`),
  });
}

export function useCreateViewingSlot() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: {
      starts_at: string;
      duration_min?: number;
      unit_id?: string | null;
      status?: "open" | "blocked";
    }) => api.post<ViewingSlot>("/api/viewing-slots", input),
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: ["viewing-slots"] });
    },
  });
}

export function useGenerateViewingSlots() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input?: { days?: number; unit_id?: string | null; duration_min?: number }) =>
      api.post<{ created: number; total_candidates: number }>(
        "/api/viewing-slots/generate",
        input ?? { days: 14 },
      ),
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: ["viewing-slots"] });
    },
  });
}

export function useUpdateViewingSlot() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: {
      id: string;
      patch: { starts_at?: string; duration_min?: number; status?: "open" | "blocked" };
    }) => api.patch<ViewingSlot>(`/api/viewing-slots/${input.id}`, input.patch),
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: ["viewing-slots"] });
    },
  });
}

export function useDeleteViewingSlot() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.del<{ ok: boolean }>(`/api/viewing-slots/${id}`),
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: ["viewing-slots"] });
    },
  });
}

export interface BookingFilters {
  deal_id?: string;
  contact_id?: string;
  whatsapp_id?: string;
  status?: string;
  limit?: number;
}

export function useViewingBookings(filters: BookingFilters = {}, enabled = true) {
  const qs = buildQuery({
    deal_id: filters.deal_id,
    contact_id: filters.contact_id,
    whatsapp_id: filters.whatsapp_id,
    status: filters.status,
    limit: filters.limit ?? 100,
  });
  return useQuery({
    queryKey: ["viewing-bookings", filters],
    queryFn: () =>
      api.get<{ items: ViewingBooking[]; total: number }>(`/api/viewing-bookings${qs}`),
    enabled,
  });
}

export function useCreateViewingBooking() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: {
      slot_id: string;
      unit_id?: string | null;
      deal_id?: string | null;
      contact_id?: string | null;
      whatsapp_id?: string | null;
      client_name?: string | null;
      client_phone?: string | null;
      notes?: string | null;
    }) => api.post<ViewingBooking>("/api/viewing-bookings", input),
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: ["viewing-bookings"] });
      void qc.invalidateQueries({ queryKey: ["viewing-slots"] });
      void qc.invalidateQueries({ queryKey: ["deal"] });
      void qc.invalidateQueries({ queryKey: ["deals"] });
      void qc.invalidateQueries({ queryKey: ["board"] });
      void qc.invalidateQueries({ queryKey: ["timeline"] });
    },
  });
}

export function useCancelViewingBooking() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: { id: string; reason?: string | null }) =>
      api.post<ViewingBooking>(`/api/viewing-bookings/${input.id}/cancel`, {
        reason: input.reason ?? null,
      }),
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: ["viewing-bookings"] });
      void qc.invalidateQueries({ queryKey: ["viewing-slots"] });
      void qc.invalidateQueries({ queryKey: ["deal"] });
      void qc.invalidateQueries({ queryKey: ["deals"] });
      void qc.invalidateQueries({ queryKey: ["board"] });
      void qc.invalidateQueries({ queryKey: ["timeline"] });
    },
  });
}

export function useRescheduleViewingBooking() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: { id: string; new_slot_id: string }) =>
      api.post<ViewingBooking>(`/api/viewing-bookings/${input.id}/reschedule`, {
        new_slot_id: input.new_slot_id,
      }),
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: ["viewing-bookings"] });
      void qc.invalidateQueries({ queryKey: ["viewing-slots"] });
      void qc.invalidateQueries({ queryKey: ["deal"] });
      void qc.invalidateQueries({ queryKey: ["deals"] });
      void qc.invalidateQueries({ queryKey: ["board"] });
      void qc.invalidateQueries({ queryKey: ["timeline"] });
    },
  });
}
