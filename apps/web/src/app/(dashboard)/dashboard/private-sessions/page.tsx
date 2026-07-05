"use client";

import { useEffect, useMemo, useState, useCallback } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  format,
  startOfWeek,
  endOfWeek,
  addWeeks,
  subWeeks,
  addDays,
} from "date-fns";
import {
  Loader2,
  Plus,
  Pencil,
  XCircle,
  CheckCircle,
  Clock,
  Save,
  ChevronLeft,
  ChevronRight,
  Calendar as CalendarIcon,
  List,
  Search,
  User,
  CreditCard,
} from "lucide-react";
import toast from "react-hot-toast";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  privateServicesApi,
  availabilityApi,
  privateBookingsApi,
  slotsApi,
  type PrivateService,
  type PrivateBooking,
  type AvailabilitySlot,
  type TimeSlot,
} from "@/lib/private-sessions-api";
import { instructorsApi, type Instructor } from "@/lib/instructors-api";
import { membersApi, type Member } from "@/lib/members-api";
import { CancelBookingModal, type CancelRole } from "@/components/private-sessions/cancel-booking-modal";
import { POSChargeModal } from "@/components/payments/pos-charge-modal";

// ── Badge helpers ────────────────────────────────────────────────────────────

function VisibilityBadge({ visibility }: { visibility: string }) {
  const styles: Record<string, string> = {
    public: "bg-green-50 text-green-700",
    unlisted: "bg-yellow-50 text-yellow-700",
    private: "bg-gray-100 text-gray-600",
    members_only: "bg-blue-50 text-blue-700",
  };
  const labels: Record<string, string> = {
    public: "Public",
    unlisted: "Unlisted",
    private: "Private",
    members_only: "Members Only",
  };
  return (
    <span
      className={`rounded-full px-2 py-0.5 text-xs font-medium ${styles[visibility] || "bg-gray-100 text-gray-600"}`}
    >
      {labels[visibility] || visibility}
    </span>
  );
}

function StatusBadge({ active }: { active: boolean }) {
  return (
    <span
      className={`rounded-full px-2 py-0.5 text-xs font-medium ${
        active
          ? "bg-green-50 text-green-700"
          : "bg-gray-100 text-gray-500"
      }`}
    >
      {active ? "Active" : "Inactive"}
    </span>
  );
}

function BookingStatusBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    pending: "bg-yellow-50 text-yellow-700",
    confirmed: "bg-blue-50 text-blue-700",
    cancelled: "bg-red-50 text-red-600",
    completed: "bg-green-50 text-green-700",
    no_show: "bg-gray-100 text-gray-500",
  };
  const labels: Record<string, string> = {
    pending: "Pending",
    confirmed: "Confirmed",
    cancelled: "Cancelled",
    completed: "Completed",
    no_show: "No Show",
  };
  return (
    <span
      className={`rounded-full px-2 py-0.5 text-xs font-medium ${styles[status] || "bg-gray-100 text-gray-500"}`}
    >
      {labels[status] || status}
    </span>
  );
}

// ── Day-of-week helpers ─────────────────────────────────────────────────────

const DAYS_OF_WEEK = [
  { value: 0, label: "Monday" },
  { value: 1, label: "Tuesday" },
  { value: 2, label: "Wednesday" },
  { value: 3, label: "Thursday" },
  { value: 4, label: "Friday" },
  { value: 5, label: "Saturday" },
  { value: 6, label: "Sunday" },
];

interface DaySlot {
  day_of_week: number;
  start_time: string;
  end_time: string;
  enabled: boolean;
}

interface MultiDaySlots {
  day_of_week: number;
  slots: { id?: string; start_time: string; end_time: string }[];
  enabled: boolean;
}

function buildDaySlots(slots: AvailabilitySlot[]): DaySlot[] {
  return DAYS_OF_WEEK.map((d) => {
    const existing = slots.find(
      (s) => s.day_of_week === d.value && s.is_recurring && !s.is_blocked
    );
    return {
      day_of_week: d.value,
      start_time: existing?.start_time || "09:00",
      end_time: existing?.end_time || "17:00",
      enabled: !!existing,
    };
  });
}

function buildMultiDaySlots(slots: AvailabilitySlot[]): MultiDaySlots[] {
  return DAYS_OF_WEEK.map((d) => {
    const daySlots = slots.filter(
      (s) => s.day_of_week === d.value && s.is_recurring && !s.is_blocked
    );
    return {
      day_of_week: d.value,
      slots: daySlots.length > 0
        ? daySlots.map((s) => ({ id: s.id, start_time: s.start_time, end_time: s.end_time }))
        : [],
      enabled: daySlots.length > 0,
    };
  });
}

const fmt = (cents: number) => `$${(cents / 100).toFixed(2)}`;

// ── Service Form Modal ──────────────────────────────────────────────────────

function ServiceFormModal({
  service,
  instructors,
  onClose,
}: {
  service: PrivateService | null;
  instructors: Instructor[];
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const isEdit = !!service;

  const [form, setForm] = useState({
    instructor_id: service?.instructor_id || (instructors[0]?.id ?? ""),
    name: service?.name || "",
    description: service?.description || "",
    duration_minutes: service?.duration_minutes || 60,
    price_cents: service?.price_cents || 0,
    buffer_before_minutes: service?.buffer_before_minutes || 0,
    buffer_after_minutes: service?.buffer_after_minutes || 15,
    max_per_day: service?.max_per_day || 8,
    visibility: service?.visibility || "public",
    is_virtual: service?.is_virtual || false,
  });

  const createMutation = useMutation({
    mutationFn: (data: typeof form) =>
      privateServicesApi.create(data as Parameters<typeof privateServicesApi.create>[0]),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["private-services"] });
      toast.success("Service created");
      onClose();
    },
    onError: () => toast.error("Failed to create service"),
  });

  const updateMutation = useMutation({
    mutationFn: (data: typeof form) =>
      privateServicesApi.update(service!.id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["private-services"] });
      toast.success("Service updated");
      onClose();
    },
    onError: () => toast.error("Failed to update service"),
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (isEdit) {
      updateMutation.mutate(form);
    } else {
      createMutation.mutate(form);
    }
  };

  const isPending = createMutation.isPending || updateMutation.isPending;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={onClose}>
      <div className="w-full max-w-lg rounded-lg bg-white p-6 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <h2 className="text-lg font-bold text-gray-900">
          {isEdit ? "Edit Service" : "Add Service"}
        </h2>
        <form onSubmit={handleSubmit} className="mt-4 space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700">Instructor</label>
            <select
              value={form.instructor_id}
              onChange={(e) => setForm({ ...form, instructor_id: e.target.value })}
              className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:ring-indigo-500"
            >
              {instructors.map((inst) => (
                <option key={inst.id} value={inst.id}>
                  {inst.display_name}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700">Service Name</label>
            <input
              type="text"
              required
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:ring-indigo-500"
              placeholder="e.g. Private Yoga Session"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700">Description</label>
            <textarea
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
              rows={2}
              className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:ring-indigo-500"
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700">Duration (min)</label>
              <input
                type="number"
                min={15}
                step={15}
                value={form.duration_minutes}
                onChange={(e) => setForm({ ...form, duration_minutes: parseInt(e.target.value) || 60 })}
                className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:ring-indigo-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700">Price ($)</label>
              <input
                type="number"
                min={0}
                step={0.01}
                value={(form.price_cents / 100).toFixed(2)}
                onChange={(e) => setForm({ ...form, price_cents: Math.round(parseFloat(e.target.value || "0") * 100) })}
                className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:ring-indigo-500"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700">Buffer Before (min)</label>
              <input
                type="number"
                min={0}
                step={5}
                value={form.buffer_before_minutes}
                onChange={(e) => setForm({ ...form, buffer_before_minutes: parseInt(e.target.value) || 0 })}
                className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:ring-indigo-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700">Buffer After (min)</label>
              <input
                type="number"
                min={0}
                step={5}
                value={form.buffer_after_minutes}
                onChange={(e) => setForm({ ...form, buffer_after_minutes: parseInt(e.target.value) || 0 })}
                className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:ring-indigo-500"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700">Max Per Day</label>
              <input
                type="number"
                min={1}
                value={form.max_per_day}
                onChange={(e) => setForm({ ...form, max_per_day: parseInt(e.target.value) || 1 })}
                className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:ring-indigo-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700">Visibility</label>
              <select
                value={form.visibility}
                onChange={(e) => setForm({ ...form, visibility: e.target.value as PrivateService["visibility"] })}
                className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:ring-indigo-500"
              >
                <option value="public">Public</option>
                <option value="members_only">Members Only</option>
                <option value="unlisted">Unlisted</option>
                <option value="private">Private</option>
              </select>
            </div>
          </div>

          <label className="flex items-center gap-2 text-sm text-gray-700">
            <input
              type="checkbox"
              checked={form.is_virtual}
              onChange={(e) => setForm({ ...form, is_virtual: e.target.checked })}
              className="rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
            />
            Virtual / Online session
          </label>

          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="outline" size="sm" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" size="sm" disabled={isPending}>
              {isPending && <Loader2 className="mr-1 h-4 w-4 animate-spin" />}
              {isEdit ? "Update Service" : "Create Service"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ── Book Session Modal ──────────────────────────────────────────────────────

function BookSessionModal({
  services,
  instructors,
  onClose,
}: {
  services: PrivateService[];
  instructors: Instructor[];
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [step, setStep] = useState<"select" | "slots">("select");
  const [memberSearch, setMemberSearch] = useState("");
  const [selectedMember, setSelectedMember] = useState<Member | null>(null);
  const [selectedServiceId, setSelectedServiceId] = useState(services[0]?.id || "");
  const [selectedDate, setSelectedDate] = useState(format(new Date(), "yyyy-MM-dd"));
  const [selectedSlot, setSelectedSlot] = useState<TimeSlot | null>(null);
  const [intakeNotes, setIntakeNotes] = useState("");
  const [asPackage, setAsPackage] = useState(false);
  const [applyCreditId, setApplyCreditId] = useState<string>("");

  const activeServices = services.filter((s) => s.is_active);
  const selectedService = activeServices.find((s) => s.id === selectedServiceId);
  const instructorId = selectedService?.instructor_id || "";

  // Search members
  const { data: searchResults, isFetching: searchingMembers } = useQuery({
    queryKey: ["member-search", memberSearch],
    queryFn: () => membersApi.list({ search: memberSearch, limit: 10 }).then((r) => {
      const d = r.data;
      return Array.isArray(d) ? d : (d as { data: Member[] }).data || [];
    }),
    enabled: memberSearch.length >= 2,
  });

  // Fetch available slots
  const { data: availableSlots, isLoading: slotsLoading } = useQuery({
    queryKey: ["available-slots", instructorId, selectedServiceId, selectedDate],
    queryFn: () =>
      slotsApi.getSlots(instructorId, selectedServiceId, selectedDate).then((r) => {
        const d = r.data;
        return Array.isArray(d) ? d : (d as { data: TimeSlot[] }).data || [];
      }),
    enabled: !!instructorId && !!selectedServiceId && !!selectedDate && step === "slots",
  });

  // Available banked credits for the selected member, restricted to
  // private_session. Refreshed when the member changes.
  const { data: memberCredits } = useQuery({
    queryKey: ["member-credits-private", selectedMember?.id],
    queryFn: async () => {
      if (!selectedMember) return [];
      const resp = await membersApi.getCredits(selectedMember.id);
      return resp.data.filter(
        (c) =>
          !c.used_at &&
          (!c.expires_at || new Date(c.expires_at) > new Date()) &&
          (c.service_filter === null ||
            c.service_filter === "private_session"),
      );
    },
    enabled: !!selectedMember,
  });

  const bookMutation = useMutation({
    mutationFn: () =>
      privateBookingsApi.create({
        member_id: selectedMember!.id,
        instructor_id: instructorId,
        private_service_id: selectedServiceId,
        starts_at: `${selectedDate}T${selectedSlot!.start_time}`,
        intake_notes: intakeNotes || undefined,
        as_package: asPackage || undefined,
        apply_credit_id: applyCreditId || undefined,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["private-bookings"] });
      toast.success("Session booked successfully");
      onClose();
    },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => {
      toast.error(err.response?.data?.detail || "Failed to book session");
    },
  });

  const canProceedToSlots = selectedMember && selectedServiceId && selectedDate;
  const canBook = selectedSlot && selectedMember;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={onClose}>
      <div className="w-full max-w-xl rounded-lg bg-white p-6 shadow-xl max-h-[90vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        <h2 className="text-lg font-bold text-gray-900">Book Private Session</h2>

        {step === "select" && (
          <div className="mt-4 space-y-4">
            {/* Member Search */}
            <div>
              <label className="block text-sm font-medium text-gray-700">Member</label>
              {selectedMember ? (
                <div className="mt-1 flex items-center justify-between rounded-md border border-gray-300 px-3 py-2">
                  <div className="flex items-center gap-2">
                    <User className="h-4 w-4 text-gray-400" />
                    <span className="text-sm font-medium text-gray-900">
                      {selectedMember.first_name} {selectedMember.last_name}
                    </span>
                    <span className="text-xs text-gray-400">{selectedMember.email}</span>
                  </div>
                  <button
                    onClick={() => { setSelectedMember(null); setMemberSearch(""); }}
                    className="text-xs text-gray-400 hover:text-gray-600"
                  >
                    Change
                  </button>
                </div>
              ) : (
                <div className="relative mt-1">
                  <div className="relative">
                    <Search className="absolute left-3 top-2.5 h-4 w-4 text-gray-400" />
                    <input
                      type="text"
                      value={memberSearch}
                      onChange={(e) => setMemberSearch(e.target.value)}
                      placeholder="Search by name or email..."
                      className="block w-full rounded-md border border-gray-300 py-2 pl-9 pr-3 text-sm shadow-sm focus:border-indigo-500 focus:ring-indigo-500"
                      autoFocus
                    />
                    {searchingMembers && (
                      <Loader2 className="absolute right-3 top-2.5 h-4 w-4 animate-spin text-gray-400" />
                    )}
                  </div>
                  {searchResults && searchResults.length > 0 && (
                    <div className="absolute z-10 mt-1 w-full rounded-md border border-gray-200 bg-white shadow-lg">
                      {searchResults.map((m) => (
                        <button
                          key={m.id}
                          onClick={() => { setSelectedMember(m); setMemberSearch(""); }}
                          className="flex w-full items-center gap-3 px-3 py-2 text-left text-sm hover:bg-gray-50"
                        >
                          <User className="h-4 w-4 text-gray-400" />
                          <div>
                            <div className="font-medium text-gray-900">{m.first_name} {m.last_name}</div>
                            <div className="text-xs text-gray-400">{m.email}</div>
                          </div>
                        </button>
                      ))}
                    </div>
                  )}
                  {memberSearch.length >= 2 && searchResults && searchResults.length === 0 && !searchingMembers && (
                    <div className="absolute z-10 mt-1 w-full rounded-md border border-gray-200 bg-white p-3 text-center text-sm text-gray-500 shadow-lg">
                      No members found
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Service */}
            <div>
              <label className="block text-sm font-medium text-gray-700">Service</label>
              <select
                value={selectedServiceId}
                onChange={(e) => setSelectedServiceId(e.target.value)}
                className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:ring-indigo-500"
              >
                {activeServices.map((s) => {
                  const inst = instructors.find((i) => i.id === s.instructor_id);
                  return (
                    <option key={s.id} value={s.id}>
                      {s.name} — {inst?.display_name || "Unknown"} ({s.duration_minutes}min, {fmt(s.price_cents)})
                    </option>
                  );
                })}
              </select>
            </div>

            {/* Date */}
            <div>
              <label className="block text-sm font-medium text-gray-700">Date</label>
              <input
                type="date"
                value={selectedDate}
                min={format(new Date(), "yyyy-MM-dd")}
                onChange={(e) => setSelectedDate(e.target.value)}
                className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:ring-indigo-500"
              />
            </div>

            {/* Intake Notes */}
            <div>
              <label className="block text-sm font-medium text-gray-700">Intake Notes (optional)</label>
              <textarea
                value={intakeNotes}
                onChange={(e) => setIntakeNotes(e.target.value)}
                rows={2}
                placeholder="Any special requests, injuries, goals..."
                className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:ring-indigo-500"
              />
            </div>

            {/* Apply banked credit */}
            {memberCredits && memberCredits.length > 0 && (
              <div className="rounded-md border border-emerald-200 bg-emerald-50 p-3">
                <label className="block text-sm font-medium text-emerald-900">
                  Apply a banked credit
                </label>
                <p className="mt-0.5 text-xs text-emerald-700">
                  This member has unused credits. Pick one to cover this
                  session at $0.
                </p>
                <select
                  value={applyCreditId}
                  onChange={(e) => setApplyCreditId(e.target.value)}
                  className="mt-2 block w-full rounded-md border border-emerald-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-emerald-500 focus:ring-emerald-500"
                >
                  <option value="">No — charge normally</option>
                  {memberCredits.map((c) => {
                    const label =
                      c.source === "instructor_cancellation"
                        ? "Instructor-cancel credit"
                        : c.source === "courtesy"
                          ? "Courtesy"
                          : c.source === "refund_to_credit"
                            ? "Refund-to-credit"
                            : c.source === "gift"
                              ? "Gift"
                              : "Manual";
                    const amt = `$${(c.amount_cents / 100).toFixed(2)}`;
                    const exp = c.expires_at
                      ? ` (expires ${format(new Date(c.expires_at), "MMM d, yyyy")})`
                      : "";
                    return (
                      <option key={c.id} value={c.id}>
                        {label} — {amt}
                        {exp}
                      </option>
                    );
                  })}
                </select>
              </div>
            )}

            {/* Package option (disabled when applying a credit) */}
            {!applyCreditId &&
              selectedService?.package_sessions &&
              selectedService.package_sessions > 0 && (
                <div className="rounded-md border border-indigo-200 bg-indigo-50 p-3">
                  <label className="flex items-center gap-3 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={asPackage}
                      onChange={(e) => setAsPackage(e.target.checked)}
                      className="h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                    />
                    <div>
                      <span className="text-sm font-medium text-indigo-900">
                        Book as {selectedService.package_sessions}-Session Package
                      </span>
                      <p className="text-xs text-indigo-600">
                        {fmt(selectedService.package_price_cents || 0)} for{" "}
                        {selectedService.package_sessions} sessions (first
                        session is this booking)
                      </p>
                    </div>
                  </label>
                </div>
              )}

            <div className="flex justify-end gap-2 pt-2">
              <Button type="button" variant="outline" size="sm" onClick={onClose}>
                Cancel
              </Button>
              <Button
                size="sm"
                disabled={!canProceedToSlots}
                onClick={() => setStep("slots")}
              >
                Choose Time Slot
              </Button>
            </div>
          </div>
        )}

        {step === "slots" && (
          <div className="mt-4 space-y-4">
            {/* Summary */}
            <div className="rounded-md bg-gray-50 p-3 text-sm">
              <div className="flex justify-between">
                <span className="text-gray-500">Member</span>
                <span className="font-medium text-gray-900">{selectedMember?.first_name} {selectedMember?.last_name}</span>
              </div>
              <div className="mt-1 flex justify-between">
                <span className="text-gray-500">Service</span>
                <span className="font-medium text-gray-900">{selectedService?.name}</span>
              </div>
              <div className="mt-1 flex justify-between">
                <span className="text-gray-500">Date</span>
                <span className="font-medium text-gray-900">{format(new Date(selectedDate + "T12:00:00"), "EEEE, MMM d, yyyy")}</span>
              </div>
              <div className="mt-1 flex justify-between">
                <span className="text-gray-500">Price</span>
                <span className="font-medium text-gray-900">
                  {asPackage && selectedService?.package_price_cents
                    ? `${fmt(selectedService.package_price_cents)} (${selectedService.package_sessions}-session package)`
                    : fmt(selectedService?.price_cents || 0)}
                </span>
              </div>
            </div>

            {/* Available Slots */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Available Time Slots</label>
              {slotsLoading ? (
                <div className="flex items-center justify-center py-8">
                  <Loader2 className="h-6 w-6 animate-spin text-indigo-600" />
                </div>
              ) : !availableSlots?.length ? (
                <div className="rounded-md border border-dashed border-gray-300 py-8 text-center text-sm text-gray-500">
                  No available slots for this date. Try another date or check instructor availability.
                </div>
              ) : (
                <div className="grid grid-cols-3 gap-2 sm:grid-cols-4">
                  {availableSlots.map((slot, idx) => {
                    const isSelected = selectedSlot?.start_time === slot.start_time;
                    return (
                      <button
                        key={idx}
                        onClick={() => setSelectedSlot(slot)}
                        className={`rounded-md border px-3 py-2 text-sm font-medium transition-colors ${
                          isSelected
                            ? "border-indigo-500 bg-indigo-50 text-indigo-700 ring-1 ring-indigo-500"
                            : "border-gray-200 text-gray-700 hover:border-indigo-300 hover:bg-indigo-50/50"
                        }`}
                      >
                        {slot.start_time}
                      </button>
                    );
                  })}
                </div>
              )}
            </div>

            <div className="flex justify-between pt-2">
              <Button type="button" variant="outline" size="sm" onClick={() => { setStep("select"); setSelectedSlot(null); }}>
                Back
              </Button>
              <div className="flex gap-2">
                <Button type="button" variant="outline" size="sm" onClick={onClose}>
                  Cancel
                </Button>
                <Button
                  size="sm"
                  disabled={!canBook || bookMutation.isPending}
                  onClick={() => bookMutation.mutate()}
                >
                  {bookMutation.isPending && <Loader2 className="mr-1 h-4 w-4 animate-spin" />}
                  {asPackage ? "Book Package & Send Payment Link" : "Book Session"}
                </Button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Booking Detail Modal ────────────────────────────────────────────────────

function BookingDetailModal({
  booking,
  onClose,
  onConfirm,
  onCancel,
  onComplete,
  onSendPaymentLink,
  onChargeInPerson,
}: {
  booking: PrivateBooking;
  onClose: () => void;
  onConfirm: (id: string) => void;
  onCancel: (id: string) => void;
  onComplete: (id: string) => void;
  onSendPaymentLink?: (id: string) => void;
  onChargeInPerson?: (b: PrivateBooking) => void;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={onClose}>
      <div className="w-full max-w-md rounded-lg bg-white p-6 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-bold text-gray-900">Booking Details</h2>
          <BookingStatusBadge status={booking.status} />
        </div>

        <div className="mt-4 space-y-3 text-sm">
          <div className="flex justify-between border-b border-gray-100 pb-2">
            <span className="text-gray-500">Member</span>
            <span className="font-medium text-gray-900">
              {booking.member_first_name || ""} {booking.member_last_name || ""}
            </span>
          </div>
          <div className="flex justify-between border-b border-gray-100 pb-2">
            <span className="text-gray-500">Service</span>
            <span className="font-medium text-gray-900">{booking.service_name || "—"}</span>
          </div>
          <div className="flex justify-between border-b border-gray-100 pb-2">
            <span className="text-gray-500">Instructor</span>
            <span className="font-medium text-gray-900">
              {booking.instructor_first_name || ""} {booking.instructor_last_name || ""}
            </span>
          </div>
          <div className="flex justify-between border-b border-gray-100 pb-2">
            <span className="text-gray-500">Date</span>
            <span className="font-medium text-gray-900">
              {format(new Date(booking.starts_at), "EEEE, MMM d, yyyy")}
            </span>
          </div>
          <div className="flex justify-between border-b border-gray-100 pb-2">
            <span className="text-gray-500">Time</span>
            <span className="font-medium text-gray-900">
              {format(new Date(booking.starts_at), "h:mm a")} – {format(new Date(booking.ends_at), "h:mm a")}
            </span>
          </div>
          <div className="flex justify-between border-b border-gray-100 pb-2">
            <span className="text-gray-500">Price</span>
            <span className="font-medium text-gray-900">{fmt(booking.price_cents)}</span>
          </div>
          {booking.price_cents > 0 && (
            <div className="flex justify-between border-b border-gray-100 pb-2">
              <span className="text-gray-500">Payment</span>
              {booking.payment_status === "paid" ? (
                <span className="rounded-full bg-green-50 px-2 py-0.5 text-xs font-medium text-green-700">Paid</span>
              ) : (
                <span className="rounded-full bg-red-50 px-2 py-0.5 text-xs font-medium text-red-700">Unpaid</span>
              )}
            </div>
          )}
          {booking.is_virtual && (
            <div className="flex justify-between border-b border-gray-100 pb-2">
              <span className="text-gray-500">Type</span>
              <span className="rounded bg-blue-50 px-2 py-0.5 text-xs font-medium text-blue-700">Virtual</span>
            </div>
          )}
          {booking.intake_notes && (
            <div className="border-b border-gray-100 pb-2">
              <span className="text-gray-500">Intake Notes</span>
              <p className="mt-1 text-gray-900">{booking.intake_notes}</p>
            </div>
          )}
          {booking.cancellation_reason && (
            <div className="border-b border-gray-100 pb-2">
              <span className="text-gray-500">Cancellation Reason</span>
              <p className="mt-1 text-gray-900">{booking.cancellation_reason}</p>
            </div>
          )}
        </div>

        <div className="mt-6 flex flex-wrap justify-end gap-2">
          {booking.payment_status !== "paid" && booking.price_cents > 0 && booking.status !== "cancelled" && onSendPaymentLink && (
            <Button size="sm" variant="outline" className="text-indigo-600 hover:bg-indigo-50" onClick={() => onSendPaymentLink(booking.id)}>
              <CreditCard className="mr-1 h-4 w-4" /> Send Payment Link
            </Button>
          )}
          {booking.payment_status !== "paid" && booking.price_cents > 0 && booking.status !== "cancelled" && onChargeInPerson && (
            <Button size="sm" variant="outline" className="text-indigo-600 hover:bg-indigo-50" onClick={() => onChargeInPerson(booking)}>
              <CreditCard className="mr-1 h-4 w-4" /> Charge via Square POS
            </Button>
          )}
          {(booking.status === "pending" || booking.status === "confirmed") && (
            <Button size="sm" variant="outline" onClick={() => onComplete(booking.id)}>
              <CheckCircle className="mr-1 h-4 w-4" /> Mark Completed
            </Button>
          )}
          {(booking.status === "pending" || booking.status === "confirmed") && (
            <Button size="sm" variant="outline" className="text-red-600 hover:bg-red-50" onClick={() => onCancel(booking.id)}>
              <XCircle className="mr-1 h-4 w-4" /> Cancel
            </Button>
          )}
          <Button size="sm" variant="outline" onClick={onClose}>Close</Button>
        </div>
      </div>
    </div>
  );
}

// ── Calendar View (Private Sessions) ────────────────────────────────────────

function BookingsCalendarView({
  bookings,
  currentDate,
  viewMode,
  onBookingClick,
}: {
  bookings: PrivateBooking[];
  currentDate: Date;
  viewMode: "week" | "day";
  onBookingClick: (booking: PrivateBooking) => void;
}) {
  const dateRange = useMemo(() => {
    if (viewMode === "week") {
      const start = startOfWeek(currentDate, { weekStartsOn: 0 });
      const end = endOfWeek(currentDate, { weekStartsOn: 0 });
      return { start, end };
    }
    return { start: currentDate, end: addDays(currentDate, 1) };
  }, [currentDate, viewMode]);

  // Filter bookings to current range
  const visibleBookings = useMemo(() => {
    const rangeStart = dateRange.start.getTime();
    const rangeEnd = dateRange.end.getTime();
    return bookings.filter((b) => {
      const t = new Date(b.starts_at).getTime();
      return t >= rangeStart && t <= rangeEnd;
    });
  }, [bookings, dateRange]);

  // Build day columns
  const days = useMemo(() => {
    const result: Date[] = [];
    if (viewMode === "day") {
      result.push(currentDate);
    } else {
      for (let i = 0; i < 7; i++) {
        result.push(addDays(dateRange.start, i));
      }
    }
    return result;
  }, [viewMode, currentDate, dateRange.start]);

  // Hours from 6am to 10pm
  const hours = Array.from({ length: 17 }, (_, i) => i + 6);

  const statusColors: Record<string, string> = {
    pending: "bg-yellow-100 border-yellow-300 text-yellow-800",
    confirmed: "bg-indigo-100 border-indigo-300 text-indigo-800",
    completed: "bg-green-100 border-green-300 text-green-800",
    cancelled: "bg-red-100 border-red-300 text-red-500 line-through opacity-60",
    no_show: "bg-gray-100 border-gray-300 text-gray-500 opacity-60",
  };

  return (
    <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white">
      <div className="min-w-[700px]">
        {/* Day headers */}
        <div className="grid border-b border-gray-200 bg-gray-50" style={{ gridTemplateColumns: `60px repeat(${days.length}, 1fr)` }}>
          <div className="border-r border-gray-200 px-2 py-3" />
          {days.map((day) => {
            const isToday = format(day, "yyyy-MM-dd") === format(new Date(), "yyyy-MM-dd");
            return (
              <div key={day.toISOString()} className="border-r border-gray-200 px-2 py-3 text-center last:border-r-0">
                <div className="text-xs font-medium uppercase text-gray-500">{format(day, "EEE")}</div>
                <div className={`mt-0.5 text-sm font-semibold ${isToday ? "text-indigo-600" : "text-gray-900"}`}>
                  {format(day, "d")}
                </div>
              </div>
            );
          })}
        </div>

        {/* Time grid */}
        <div className="relative">
          {hours.map((hour) => (
            <div
              key={hour}
              className="grid border-b border-gray-100"
              style={{ gridTemplateColumns: `60px repeat(${days.length}, 1fr)`, height: 60 }}
            >
              <div className="border-r border-gray-200 px-2 py-1 text-right text-xs text-gray-400">
                {hour === 0 ? "12 AM" : hour <= 12 ? `${hour} ${hour < 12 ? "AM" : "PM"}` : `${hour - 12} PM`}
              </div>
              {days.map((day) => {
                const dayStr = format(day, "yyyy-MM-dd");
                const hourBookings = visibleBookings.filter((b) => {
                  const bDate = format(new Date(b.starts_at), "yyyy-MM-dd");
                  const bHour = new Date(b.starts_at).getHours();
                  return bDate === dayStr && bHour === hour;
                });
                return (
                  <div key={day.toISOString()} className="relative border-r border-gray-100 last:border-r-0">
                    {hourBookings.map((bk) => {
                      const startMin = new Date(bk.starts_at).getMinutes();
                      const durationMs = new Date(bk.ends_at).getTime() - new Date(bk.starts_at).getTime();
                      const durationMin = durationMs / 60000;
                      const topPx = (startMin / 60) * 60;
                      const heightPx = Math.max((durationMin / 60) * 60, 20);
                      return (
                        <button
                          key={bk.id}
                          onClick={() => onBookingClick(bk)}
                          className={`absolute inset-x-1 overflow-hidden rounded border px-1 py-0.5 text-left text-[10px] leading-tight ${statusColors[bk.status] || "bg-gray-100 border-gray-300 text-gray-700"}`}
                          style={{ top: topPx, height: heightPx }}
                          title={`${bk.service_name} — ${bk.member_first_name} ${bk.member_last_name}`}
                        >
                          <div className="truncate font-semibold">
                            {format(new Date(bk.starts_at), "h:mm a")}
                          </div>
                          <div className="truncate">
                            {bk.member_first_name} {bk.member_last_name?.[0]}.
                          </div>
                          <div className="truncate opacity-80">{bk.service_name}</div>
                        </button>
                      );
                    })}
                  </div>
                );
              })}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ── Main Page ────────────────────────────────────────────────────────────────

export default function PrivateSessionsPage() {
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<"services" | "availability" | "bookings">("services");
  const [showServiceModal, setShowServiceModal] = useState(false);
  const [editingService, setEditingService] = useState<PrivateService | null>(null);
  const [showBookingModal, setShowBookingModal] = useState(false);
  const [selectedBooking, setSelectedBooking] = useState<PrivateBooking | null>(null);
  const [posChargeBooking, setPosChargeBooking] = useState<PrivateBooking | null>(null);
  const [selectedInstructorId, setSelectedInstructorId] = useState<string | null>(null);
  const [daySlots, setDaySlots] = useState<DaySlot[]>([]);
  const [multiSlots, setMultiSlots] = useState<MultiDaySlots[]>([]);

  // Bookings view state
  const [bookingsViewMode, setBookingsViewMode] = useState<"calendar" | "list">("calendar");
  const [calendarViewMode, setCalendarViewMode] = useState<"week" | "day">("week");
  const [calendarDate, setCalendarDate] = useState(new Date());

  // Fetch instructors
  const { data: instructors } = useQuery({
    queryKey: ["instructors"],
    queryFn: () => instructorsApi.list().then((r) => r.data),
  });

  useEffect(() => {
    if (instructors && instructors.length > 0 && !selectedInstructorId) {
      setSelectedInstructorId(instructors[0].id);
    }
  }, [instructors, selectedInstructorId]);

  // Private services
  const { data: services, isLoading: servicesLoading } = useQuery({
    queryKey: ["private-services"],
    queryFn: () => privateServicesApi.list().then((r) => r.data.data),
  });

  // Bookings
  const { data: bookings, isLoading: bookingsLoading } = useQuery({
    queryKey: ["private-bookings"],
    queryFn: () => privateBookingsApi.list().then((r) => r.data.data),
  });

  // Availability for selected instructor
  const { data: availabilitySlots, isLoading: availabilityLoading } = useQuery({
    queryKey: ["private-availability", selectedInstructorId],
    queryFn: () =>
      availabilityApi.get(selectedInstructorId!).then((r) => r.data.data),
    enabled: !!selectedInstructorId,
  });

  // Build day slots when availability data changes
  useEffect(() => {
    if (availabilitySlots) {
      setDaySlots(buildDaySlots(availabilitySlots));
      setMultiSlots(buildMultiDaySlots(availabilitySlots));
    }
  }, [availabilitySlots]);

  // Mutations
  const deactivateMutation = useMutation({
    mutationFn: (id: string) => privateServicesApi.deactivate(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["private-services"] });
      toast.success("Service deactivated");
    },
    onError: () => toast.error("Failed to deactivate"),
  });

  const reactivateMutation = useMutation({
    mutationFn: (id: string) => privateServicesApi.update(id, { is_active: true }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["private-services"] });
      toast.success("Service activated");
    },
    onError: () => toast.error("Failed to activate"),
  });

  const saveAvailabilityMutation = useMutation({
    mutationFn: (slots: Partial<AvailabilitySlot>[]) =>
      availabilityApi.set(selectedInstructorId!, slots),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["private-availability", selectedInstructorId] });
      toast.success("Availability saved");
    },
    onError: () => toast.error("Failed to save availability"),
  });

  const confirmMutation = useMutation({
    mutationFn: (id: string) => privateBookingsApi.confirm(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["private-bookings"] });
      toast.success("Booking confirmed");
      setSelectedBooking(null);
    },
    onError: () => toast.error("Failed to confirm booking"),
  });

  const [cancelTarget, setCancelTarget] = useState<{
    id: string;
    memberName: string;
    pricePaid: number;
    paymentStatus?: string;
  } | null>(null);

  const cancelBookingMutation = useMutation({
    mutationFn: ({
      id,
      role,
      reason,
    }: {
      id: string;
      role: CancelRole;
      reason: string;
    }) => privateBookingsApi.cancel(id, reason || undefined, role),
    onSuccess: (resp) => {
      queryClient.invalidateQueries({ queryKey: ["private-bookings"] });
      const granted = (resp.data as unknown as { granted_credit?: { amount_cents: number } }).granted_credit;
      if (granted) {
        toast.success(
          `Booking cancelled — $${(granted.amount_cents / 100).toFixed(2)} credit preserved`,
        );
      } else {
        toast.success("Booking cancelled");
      }
      setSelectedBooking(null);
      setCancelTarget(null);
    },
    onError: () => toast.error("Failed to cancel booking"),
  });

  const openCancelModal = (booking: {
    id: string;
    member_first_name?: string;
    member_last_name?: string;
    price_cents?: number;
    payment_status?: string;
  }) => {
    setCancelTarget({
      id: booking.id,
      memberName: `${booking.member_first_name || ""} ${booking.member_last_name || ""}`.trim(),
      pricePaid: booking.price_cents || 0,
      paymentStatus: booking.payment_status,
    });
  };

  const completeMutation = useMutation({
    mutationFn: (id: string) => privateBookingsApi.complete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["private-bookings"] });
      toast.success("Booking completed");
      setSelectedBooking(null);
    },
    onError: () => toast.error("Failed to complete booking"),
  });

  const sendPaymentLinkMutation = useMutation({
    mutationFn: (id: string) => privateBookingsApi.sendPaymentLink(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["private-bookings"] });
      toast.success("Payment link sent to member's email");
      setSelectedBooking(null);
    },
    onError: () => toast.error("Failed to send payment link"),
  });

  const handleAddService = () => {
    if (!instructors || instructors.length === 0) {
      toast.error("Add an instructor first before creating a service");
      return;
    }
    setEditingService(null);
    setShowServiceModal(true);
  };

  const handleEditService = (svc: PrivateService) => {
    setEditingService(svc);
    setShowServiceModal(true);
  };

  const handleCloseServiceModal = () => {
    setShowServiceModal(false);
    setEditingService(null);
  };

  const handleBookSession = () => {
    if (!services || services.filter((s) => s.is_active).length === 0) {
      toast.error("Create a service first before booking a session");
      return;
    }
    if (!instructors || instructors.length === 0) {
      toast.error("Add an instructor first");
      return;
    }
    setShowBookingModal(true);
  };

  const handleSaveAvailability = () => {
    const enabledSlots = daySlots
      .filter((d) => d.enabled)
      .map((d) => ({
        day_of_week: d.day_of_week,
        start_time: d.start_time,
        end_time: d.end_time,
      }));
    saveAvailabilityMutation.mutate(enabledSlots);
  };

  const updateDaySlot = (dayOfWeek: number, field: keyof DaySlot, value: string | boolean) => {
    setDaySlots((prev) =>
      prev.map((d) => (d.day_of_week === dayOfWeek ? { ...d, [field]: value } : d))
    );
  };

  const instructorName = (id: string) => {
    const inst = instructors?.find((i) => i.id === id);
    return inst?.display_name || "—";
  };

  const navigateCalendar = useCallback(
    (direction: "prev" | "next") => {
      setCalendarDate((d) =>
        direction === "next"
          ? calendarViewMode === "week" ? addWeeks(d, 1) : addDays(d, 1)
          : calendarViewMode === "week" ? subWeeks(d, 1) : addDays(d, -1)
      );
    },
    [calendarViewMode]
  );

  // Summary stats
  const activeServicesCount = services?.filter((s) => s.is_active).length ?? 0;
  const pendingBookingsCount = bookings?.filter((b) => b.status === "pending").length ?? 0;
  const confirmedBookingsCount = bookings?.filter((b) => b.status === "confirmed").length ?? 0;

  // Calendar date range label
  const calendarDateRange = useMemo(() => {
    if (calendarViewMode === "week") {
      const start = startOfWeek(calendarDate, { weekStartsOn: 0 });
      const end = endOfWeek(calendarDate, { weekStartsOn: 0 });
      return `${format(start, "MMM d")} – ${format(end, "MMM d, yyyy")}`;
    }
    return format(calendarDate, "EEEE, MMM d, yyyy");
  }, [calendarDate, calendarViewMode]);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Private Sessions</h1>
          <p className="text-sm text-gray-500">
            Manage private services, instructor availability, and bookings
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={handleBookSession}>
            <CalendarIcon className="mr-1 h-4 w-4" />
            Book Session
          </Button>
          <Button onClick={handleAddService}>
            <Plus className="mr-1 h-4 w-4" />
            Add Service
          </Button>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardContent className="pt-6">
            <p className="text-sm font-medium text-gray-500">Active Services</p>
            <p className="mt-1 text-2xl font-bold text-gray-900">
              {servicesLoading ? <Loader2 className="h-5 w-5 animate-spin" /> : activeServicesCount}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <p className="text-sm font-medium text-gray-500">Total Services</p>
            <p className="mt-1 text-2xl font-bold text-gray-900">
              {servicesLoading ? <Loader2 className="h-5 w-5 animate-spin" /> : services?.length ?? 0}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <p className="text-sm font-medium text-gray-500">Pending Bookings</p>
            <p className="mt-1 text-2xl font-bold text-yellow-600">
              {bookingsLoading ? <Loader2 className="h-5 w-5 animate-spin" /> : pendingBookingsCount}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <p className="text-sm font-medium text-gray-500">Confirmed Bookings</p>
            <p className="mt-1 text-2xl font-bold text-blue-600">
              {bookingsLoading ? <Loader2 className="h-5 w-5 animate-spin" /> : confirmedBookingsCount}
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Tabs */}
      <div className="flex gap-4 overflow-x-auto border-b border-gray-200">
        {([
          { key: "services" as const, label: "Services", count: services?.length },
          { key: "availability" as const, label: "Availability", count: undefined },
          { key: "bookings" as const, label: "Bookings", count: bookings?.length },
        ]).map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`whitespace-nowrap border-b-2 px-1 pb-3 text-sm font-medium ${
              activeTab === tab.key
                ? "border-indigo-500 text-indigo-600"
                : "border-transparent text-gray-500 hover:text-gray-700"
            }`}
          >
            {tab.label}
            {tab.count != null && tab.count > 0 ? (
              <span className="ml-1.5 rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-600">
                {tab.count}
              </span>
            ) : null}
          </button>
        ))}
      </div>

      {/* ── Services Tab ───────────────────────────────────────────────────────── */}
      {activeTab === "services" && (
        <>
          {servicesLoading ? (
            <div className="flex items-center justify-center py-20">
              <Loader2 className="h-8 w-8 animate-spin text-indigo-600" />
            </div>
          ) : !services?.length ? (
            <div className="rounded-lg border border-dashed border-gray-300 py-12 text-center">
              <p className="text-sm text-gray-500">
                No private services yet. Click &quot;Add Service&quot; to create one.
              </p>
            </div>
          ) : (
            <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">Name</th>
                    <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">Instructor</th>
                    <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">Duration</th>
                    <th className="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-gray-500">Price</th>
                    <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">Visibility</th>
                    <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">Status</th>
                    <th className="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-gray-500">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200">
                  {services.map((svc) => (
                    <tr key={svc.id} className="hover:bg-gray-50">
                      <td className="whitespace-nowrap px-4 py-3 text-sm font-medium text-gray-900">
                        {svc.name}
                        {svc.is_virtual && (
                          <span className="ml-2 rounded bg-blue-50 px-1.5 py-0.5 text-[10px] font-medium uppercase text-blue-600">
                            Virtual
                          </span>
                        )}
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 text-sm text-gray-600">
                        {svc.instructor_display_name || instructorName(svc.instructor_id)}
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 text-sm text-gray-600">
                        {svc.duration_minutes} min
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 text-right text-sm font-medium text-gray-900">
                        {fmt(svc.price_cents)}
                      </td>
                      <td className="whitespace-nowrap px-4 py-3">
                        <VisibilityBadge visibility={svc.visibility} />
                      </td>
                      <td className="whitespace-nowrap px-4 py-3">
                        <StatusBadge active={svc.is_active} />
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 text-right">
                        <div className="flex items-center justify-end gap-1">
                          <button
                            onClick={() => handleEditService(svc)}
                            className="rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
                            title="Edit"
                          >
                            <Pencil className="h-4 w-4" />
                          </button>
                          {svc.is_active ? (
                            <button
                              onClick={() => deactivateMutation.mutate(svc.id)}
                              className="rounded p-1 text-gray-400 hover:bg-red-50 hover:text-red-600"
                              title="Deactivate"
                            >
                              <XCircle className="h-4 w-4" />
                            </button>
                          ) : (
                            <button
                              onClick={() => reactivateMutation.mutate(svc.id)}
                              className="rounded px-2 py-0.5 text-xs font-medium text-indigo-600 hover:bg-indigo-50"
                              title="Activate"
                            >
                              Activate
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {/* ── Availability Tab ───────────────────────────────────────────────────── */}
      {activeTab === "availability" && (
        <>
          <div className="flex items-center gap-4">
            <label className="text-sm font-medium text-gray-700">Instructor</label>
            <select
              value={selectedInstructorId || ""}
              onChange={(e) => setSelectedInstructorId(e.target.value)}
              className="rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:ring-indigo-500"
            >
              {instructors?.map((inst) => (
                <option key={inst.id} value={inst.id}>
                  {inst.display_name}
                </option>
              ))}
            </select>
          </div>

          {availabilityLoading ? (
            <div className="flex items-center justify-center py-20">
              <Loader2 className="h-8 w-8 animate-spin text-indigo-600" />
            </div>
          ) : (
            <div className="space-y-4">
              <div className="space-y-3">
                {multiSlots.map((day) => {
                  const dayLabel = DAYS_OF_WEEK.find((d) => d.value === day.day_of_week)?.label || "";
                  return (
                    <div key={day.day_of_week} className="rounded-lg border border-gray-200 bg-white p-4">
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-3">
                          <input
                            type="checkbox"
                            checked={day.enabled}
                            onChange={(e) => {
                              setMultiSlots((prev) => prev.map((d) =>
                                d.day_of_week === day.day_of_week
                                  ? { ...d, enabled: e.target.checked, slots: e.target.checked && d.slots.length === 0 ? [{ start_time: "09:00", end_time: "12:00" }] : d.slots }
                                  : d
                              ));
                            }}
                            className="rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                          />
                          <span className={`text-sm font-semibold ${day.enabled ? "text-gray-900" : "text-gray-400"}`}>{dayLabel}</span>
                        </div>
                        {day.enabled && (
                          <button
                            type="button"
                            onClick={() => {
                              setMultiSlots((prev) => prev.map((d) =>
                                d.day_of_week === day.day_of_week
                                  ? { ...d, slots: [...d.slots, { start_time: "13:00", end_time: "17:00" }] }
                                  : d
                              ));
                            }}
                            className="text-xs text-indigo-600 hover:text-indigo-800 font-medium"
                          >
                            + Add Time Slot
                          </button>
                        )}
                      </div>
                      {day.enabled && day.slots.length > 0 && (
                        <div className="ml-7 space-y-2">
                          {day.slots.map((slot, idx) => (
                            <div key={idx} className="flex items-center gap-2">
                              <input
                                type="time"
                                value={slot.start_time}
                                onChange={(e) => {
                                  setMultiSlots((prev) => prev.map((d) =>
                                    d.day_of_week === day.day_of_week
                                      ? { ...d, slots: d.slots.map((s, i) => i === idx ? { ...s, start_time: e.target.value } : s) }
                                      : d
                                  ));
                                }}
                                className="rounded-md border border-gray-300 px-2 py-1 text-sm"
                              />
                              <span className="text-gray-400">to</span>
                              <input
                                type="time"
                                value={slot.end_time}
                                onChange={(e) => {
                                  setMultiSlots((prev) => prev.map((d) =>
                                    d.day_of_week === day.day_of_week
                                      ? { ...d, slots: d.slots.map((s, i) => i === idx ? { ...s, end_time: e.target.value } : s) }
                                      : d
                                  ));
                                }}
                                className="rounded-md border border-gray-300 px-2 py-1 text-sm"
                              />
                              {day.slots.length > 1 && (
                                <button
                                  type="button"
                                  onClick={() => {
                                    setMultiSlots((prev) => prev.map((d) =>
                                      d.day_of_week === day.day_of_week
                                        ? { ...d, slots: d.slots.filter((_, i) => i !== idx) }
                                        : d
                                    ));
                                  }}
                                  className="text-red-400 hover:text-red-600 text-xs"
                                >
                                  Remove
                                </button>
                              )}
                            </div>
                          ))}
                        </div>
                      )}
                      {day.enabled && day.slots.length === 0 && (
                        <p className="ml-7 text-xs text-gray-400">No time slots — click "+ Add Time Slot"</p>
                      )}
                    </div>
                  );
                })}
              </div>
              <div className="flex justify-end">
                <Button
                  onClick={() => {
                    const slots: Partial<AvailabilitySlot>[] = [];
                    for (const day of multiSlots) {
                      if (day.enabled) {
                        for (const slot of day.slots) {
                          slots.push({
                            day_of_week: day.day_of_week,
                            start_time: slot.start_time,
                            end_time: slot.end_time,
                            is_recurring: true,
                            is_blocked: false,
                          });
                        }
                      }
                    }
                    saveAvailabilityMutation.mutate(slots);
                  }}
                  disabled={saveAvailabilityMutation.isPending}
                >
                  {saveAvailabilityMutation.isPending ? (
                    <Loader2 className="mr-1 h-4 w-4 animate-spin" />
                  ) : (
                    <Save className="mr-1 h-4 w-4" />
                  )}
                  Save Availability
                </Button>
              </div>
            </div>
          )}
        </>
      )}

      {/* ── Bookings Tab ───────────────────────────────────────────────────────── */}
      {activeTab === "bookings" && (
        <>
          {/* Bookings toolbar */}
          <div className="flex items-center justify-between">
            {/* Calendar navigation */}
            {bookingsViewMode === "calendar" && (
              <div className="flex items-center gap-2">
                <Button variant="outline" size="sm" onClick={() => setCalendarDate(new Date())}>
                  Today
                </Button>
                <Button variant="ghost" size="sm" onClick={() => navigateCalendar("prev")}>
                  <ChevronLeft className="h-4 w-4" />
                </Button>
                <Button variant="ghost" size="sm" onClick={() => navigateCalendar("next")}>
                  <ChevronRight className="h-4 w-4" />
                </Button>
                <span className="text-sm font-medium text-gray-700">{calendarDateRange}</span>
              </div>
            )}
            {bookingsViewMode === "list" && <div />}

            {/* View toggle */}
            <div className="flex items-center gap-2">
              {bookingsViewMode === "calendar" && (
                <div className="flex gap-1 rounded-md border border-gray-200 p-0.5">
                  <button
                    className={`rounded px-3 py-1 text-xs font-medium ${
                      calendarViewMode === "day" ? "bg-indigo-100 text-indigo-700" : "text-gray-500 hover:text-gray-700"
                    }`}
                    onClick={() => setCalendarViewMode("day")}
                  >
                    Day
                  </button>
                  <button
                    className={`rounded px-3 py-1 text-xs font-medium ${
                      calendarViewMode === "week" ? "bg-indigo-100 text-indigo-700" : "text-gray-500 hover:text-gray-700"
                    }`}
                    onClick={() => setCalendarViewMode("week")}
                  >
                    Week
                  </button>
                </div>
              )}
              <div className="flex gap-1 rounded-md border border-gray-200 p-0.5">
                <button
                  className={`rounded p-1.5 ${
                    bookingsViewMode === "calendar" ? "bg-indigo-100 text-indigo-700" : "text-gray-500 hover:text-gray-700"
                  }`}
                  onClick={() => setBookingsViewMode("calendar")}
                  title="Calendar view"
                >
                  <CalendarIcon className="h-4 w-4" />
                </button>
                <button
                  className={`rounded p-1.5 ${
                    bookingsViewMode === "list" ? "bg-indigo-100 text-indigo-700" : "text-gray-500 hover:text-gray-700"
                  }`}
                  onClick={() => setBookingsViewMode("list")}
                  title="List view"
                >
                  <List className="h-4 w-4" />
                </button>
              </div>
            </div>
          </div>

          {bookingsLoading ? (
            <div className="flex items-center justify-center py-20">
              <Loader2 className="h-8 w-8 animate-spin text-indigo-600" />
            </div>
          ) : !bookings?.length ? (
            <div className="rounded-lg border border-dashed border-gray-300 py-12 text-center">
              <p className="text-sm text-gray-500">
                No bookings yet. Click &quot;Book Session&quot; to create one.
              </p>
            </div>
          ) : bookingsViewMode === "calendar" ? (
            <BookingsCalendarView
              bookings={bookings}
              currentDate={calendarDate}
              viewMode={calendarViewMode}
              onBookingClick={setSelectedBooking}
            />
          ) : (
            /* List view */
            <div className="overflow-hidden rounded-lg border border-gray-200 bg-white">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">Member</th>
                    <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">Instructor</th>
                    <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">Service</th>
                    <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">Date / Time</th>
                    <th className="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-gray-500">Price</th>
                    <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">Status</th>
                    <th className="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-gray-500">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200">
                  {bookings.map((bk) => (
                    <tr key={bk.id} className="cursor-pointer hover:bg-gray-50" onClick={() => setSelectedBooking(bk)}>
                      <td className="whitespace-nowrap px-4 py-3 text-sm font-medium text-gray-900">
                        {bk.member_first_name || ""} {bk.member_last_name || ""}
                        {!bk.member_first_name && !bk.member_last_name && bk.member_id}
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 text-sm text-gray-600">
                        {bk.instructor_first_name || ""} {bk.instructor_last_name || ""}
                        {!bk.instructor_first_name && !bk.instructor_last_name && instructorName(bk.instructor_id)}
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 text-sm text-gray-600">
                        {bk.service_name || "—"}
                        {bk.is_virtual && (
                          <span className="ml-2 rounded bg-blue-50 px-1.5 py-0.5 text-[10px] font-medium uppercase text-blue-600">
                            Virtual
                          </span>
                        )}
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 text-sm text-gray-600">
                        <div>{format(new Date(bk.starts_at), "MMM d, yyyy")}</div>
                        <div className="text-xs text-gray-400">
                          {format(new Date(bk.starts_at), "h:mm a")} – {format(new Date(bk.ends_at), "h:mm a")}
                        </div>
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 text-right text-sm font-medium text-gray-900">
                        {fmt(bk.price_cents)}
                      </td>
                      <td className="whitespace-nowrap px-4 py-3">
                        <BookingStatusBadge status={bk.status} />
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 text-right">
                        <div className="flex items-center justify-end gap-1" onClick={(e) => e.stopPropagation()}>
                          {bk.status === "pending" && (
                            <button
                              onClick={() => confirmMutation.mutate(bk.id)}
                              className="rounded p-1 text-gray-400 hover:bg-green-50 hover:text-green-600"
                              title="Confirm"
                            >
                              <CheckCircle className="h-4 w-4" />
                            </button>
                          )}
                          {bk.status === "confirmed" && (
                            <button
                              onClick={() => completeMutation.mutate(bk.id)}
                              className="rounded p-1 text-gray-400 hover:bg-green-50 hover:text-green-600"
                              title="Complete"
                            >
                              <Clock className="h-4 w-4" />
                            </button>
                          )}
                          {(bk.status === "pending" || bk.status === "confirmed") && (
                            <button
                              onClick={() => openCancelModal(bk)}
                              className="rounded p-1 text-gray-400 hover:bg-red-50 hover:text-red-600"
                              title="Cancel"
                            >
                              <XCircle className="h-4 w-4" />
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {/* ── Modals ──────────────────────────────────────────────────────────────── */}

      {showServiceModal && instructors && instructors.length > 0 && (
        <ServiceFormModal
          service={editingService}
          instructors={instructors}
          onClose={handleCloseServiceModal}
        />
      )}

      {showBookingModal && instructors && services && (
        <BookSessionModal
          services={services}
          instructors={instructors}
          onClose={() => setShowBookingModal(false)}
        />
      )}

      {selectedBooking && (
        <BookingDetailModal
          booking={selectedBooking}
          onClose={() => setSelectedBooking(null)}
          onConfirm={(id) => confirmMutation.mutate(id)}
          onCancel={(id) => {
            const bk = bookings?.find((b) => b.id === id);
            if (bk) openCancelModal(bk);
          }}
          onComplete={(id) => completeMutation.mutate(id)}
          onSendPaymentLink={(id) => sendPaymentLinkMutation.mutate(id)}
          onChargeInPerson={(bk) => {
            setSelectedBooking(null);
            setPosChargeBooking(bk);
          }}
        />
      )}

      {posChargeBooking && (
        <POSChargeModal
          open={true}
          member={{
            id: posChargeBooking.member_id,
            first_name: posChargeBooking.member_first_name,
            last_name: posChargeBooking.member_last_name,
          }}
          amountCents={posChargeBooking.price_cents}
          description={`Private session: ${posChargeBooking.service_name || "Private"}`}
          onClose={() => setPosChargeBooking(null)}
          onSuccess={() => {
            setPosChargeBooking(null);
            queryClient.invalidateQueries({ queryKey: ["private-bookings"] });
            toast.success("Charge captured on Square");
          }}
        />
      )}

      {cancelTarget && (
        <CancelBookingModal
          bookingMemberName={cancelTarget.memberName}
          pricePaid={cancelTarget.pricePaid}
          paymentStatus={cancelTarget.paymentStatus}
          submitting={cancelBookingMutation.isPending}
          onClose={() => setCancelTarget(null)}
          onConfirm={(role, reason) =>
            cancelBookingMutation.mutate({
              id: cancelTarget.id,
              role,
              reason,
            })
          }
        />
      )}
    </div>
  );
}
