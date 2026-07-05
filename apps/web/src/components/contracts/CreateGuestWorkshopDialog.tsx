"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, Send, X } from "lucide-react";
import toast from "react-hot-toast";

import { Button } from "@/components/ui/button";
import {
  guestInstructorsApi,
  type GuestInstructor,
} from "@/lib/guest-instructors-api";
import { contractsApi } from "@/lib/contracts-api";

interface Props {
  open: boolean;
  onClose: () => void;
  onCreated?: (signingUrl: string, courseId: string) => void;
}

const NEW_GUEST_VALUE = "__new__";

export function CreateGuestWorkshopDialog({ open, onClose, onCreated }: Props) {
  const queryClient = useQueryClient();
  // Form state
  const [guestSelection, setGuestSelection] = useState<string>("");
  const [newGuestName, setNewGuestName] = useState("");
  const [newGuestEmail, setNewGuestEmail] = useState("");
  const [newGuestPhone, setNewGuestPhone] = useState("");
  const [workshopName, setWorkshopName] = useState("");
  type SessionRow = { date: string; startTime: string; endTime: string };
  const [sessionRows, setSessionRows] = useState<SessionRow[]>([
    { date: "", startTime: "", endTime: "" },
  ]);
  const [cost, setCost] = useState("");
  const [instructorPct, setInstructorPct] = useState(60);
  const [location, setLocation] = useState("295 W Cromwell Ave, Fresno, CA");
  const [capacity, setCapacity] = useState("");
  const [minEnroll, setMinEnroll] = useState("");

  const guestsQ = useQuery({
    queryKey: ["guest_instructors_active"],
    queryFn: () => guestInstructorsApi.list({ active_only: true }).then((r) => r.data),
    enabled: open,
  });

  const createMut = useMutation({
    mutationFn: (body: Parameters<typeof contractsApi.createGuestWorkshop>[0]) =>
      contractsApi.createGuestWorkshop(body),
    onSuccess: (resp) => {
      toast.success(`Workshop created — signing link sent to ${resp.data.guest_instructor_name}`);
      queryClient.invalidateQueries({ queryKey: ["courses"] });
      queryClient.invalidateQueries({ queryKey: ["guest_instructors_active"] });
      if (onCreated) onCreated(resp.signing_url, resp.data.course_id);
      onClose();
      reset();
    },
    onError: (err: unknown, vars) => {
      const e = err as {
        response?: { status?: number; data?: { detail?: string } };
      };
      const status = e?.response?.status;
      const detail = e?.response?.data?.detail || "Could not create workshop";
      // 409 = duplicate workshop guard. Confirm + retry with allow_duplicate.
      if (status === 409 && !vars.allow_duplicate) {
        const ok = window.confirm(
          `${detail}\n\nCreate this workshop anyway?`
        );
        if (ok) {
          createMut.mutate({ ...vars, allow_duplicate: true });
        }
        return;
      }
      toast.error(detail);
    },
  });

  function reset() {
    setGuestSelection("");
    setNewGuestName("");
    setNewGuestEmail("");
    setNewGuestPhone("");
    setWorkshopName("");
    setSessionRows([{ date: "", startTime: "", endTime: "" }]);
    setCost("");
    setInstructorPct(60);
    setCapacity("");
    setMinEnroll("");
  }

  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!workshopName.trim()) return toast.error("Workshop name is required");
    if (!sessionRows.length) return toast.error("Add at least one session");
    const sessions = [];
    for (let i = 0; i < sessionRows.length; i++) {
      const r = sessionRows[i];
      const label = `Session ${i + 1}`;
      if (!r.date || !r.startTime || !r.endTime)
        return toast.error(`${label}: date + start + end time are required`);
      const startsAt = new Date(`${r.date}T${r.startTime}:00`);
      const endsAt = new Date(`${r.date}T${r.endTime}:00`);
      if (endsAt <= startsAt)
        return toast.error(`${label}: end time must be after start time`);
      sessions.push({
        starts_at: startsAt.toISOString(),
        ends_at: endsAt.toISOString(),
      });
    }
    const costCents = Math.round((Number(cost) || 0) * 100);
    if (costCents < 0) return toast.error("Cost must be 0 or more");
    const isNew = guestSelection === NEW_GUEST_VALUE;
    if (!isNew && !guestSelection) return toast.error("Pick a guest instructor or create new");
    if (isNew && !newGuestName.trim()) return toast.error("New guest name is required");
    if (isNew && !newGuestEmail.trim()) return toast.error("New guest email is required (we email the contract here)");

    createMut.mutate({
      workshop_name: workshopName.trim(),
      sessions,
      workshop_cost_cents: costCents,
      instructor_share_percent: instructorPct,
      location: location.trim() || null,
      capacity: capacity ? Number(capacity) : null,
      min_enrollment: minEnroll ? Number(minEnroll) : null,
      guest_instructor_id: isNew ? null : guestSelection,
      new_guest_name: isNew ? newGuestName.trim() : null,
      new_guest_email: isNew ? newGuestEmail.trim() : null,
      new_guest_phone: isNew ? (newGuestPhone.trim() || null) : null,
    });
  }

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="max-h-[92vh] w-full max-w-xl overflow-y-auto rounded-lg bg-white shadow-xl">
        <div className="flex items-center justify-between border-b px-5 py-4">
          <h2 className="text-lg font-semibold">Create Guest Workshop</h2>
          <button onClick={onClose} aria-label="Close" className="text-gray-400 hover:text-gray-600">
            <X size={18} />
          </button>
        </div>

        <form onSubmit={submit} className="space-y-4 px-5 py-4">
          <div>
            <label className="mb-1 block text-sm font-medium">Guest Instructor</label>
            <select
              value={guestSelection}
              onChange={(e) => setGuestSelection(e.target.value)}
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-purple-500 focus:outline-none"
            >
              <option value="">Select existing…</option>
              {guestsQ.data?.map((g: GuestInstructor) => (
                <option key={g.id} value={g.id}>
                  {g.name}{g.email ? ` (${g.email})` : ""}
                </option>
              ))}
              <option value={NEW_GUEST_VALUE}>+ Create new guest instructor</option>
            </select>
          </div>

          {guestSelection === NEW_GUEST_VALUE && (
            <div className="rounded-md border border-purple-200 bg-purple-50 p-3 space-y-3">
              <div>
                <label className="mb-1 block text-sm font-medium">Name</label>
                <input
                  type="text"
                  value={newGuestName}
                  onChange={(e) => setNewGuestName(e.target.value)}
                  className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
                  required
                />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium">Email</label>
                <input
                  type="email"
                  value={newGuestEmail}
                  onChange={(e) => setNewGuestEmail(e.target.value)}
                  placeholder="contract goes here"
                  className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
                  required
                />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium">Phone (optional)</label>
                <input
                  type="tel"
                  value={newGuestPhone}
                  onChange={(e) => setNewGuestPhone(e.target.value)}
                  className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
                />
              </div>
            </div>
          )}

          <hr />

          <div>
            <label className="mb-1 block text-sm font-medium">Workshop Name</label>
            <input
              type="text"
              value={workshopName}
              onChange={(e) => setWorkshopName(e.target.value)}
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
              required
            />
          </div>

          <div>
            <div className="mb-2 flex items-center justify-between">
              <label className="block text-sm font-medium">
                Sessions <span className="text-xs font-normal text-gray-500">
                  ({sessionRows.length} {sessionRows.length === 1 ? "session" : "sessions"})
                </span>
              </label>
              <button
                type="button"
                onClick={() => setSessionRows([...sessionRows, { date: "", startTime: "", endTime: "" }])}
                className="text-xs font-medium text-purple-700 hover:text-purple-900"
              >
                + Add another session
              </button>
            </div>
            <div className="space-y-2">
              {sessionRows.map((row, idx) => (
                <div key={idx} className="grid grid-cols-[auto_1fr_1fr_1fr_auto] items-end gap-2">
                  <span className="pb-2 text-xs font-medium text-gray-500">#{idx + 1}</span>
                  <div>
                    {idx === 0 && <label className="mb-1 block text-xs text-gray-500">Date</label>}
                    <input
                      type="date"
                      value={row.date}
                      onChange={(e) => {
                        const next = [...sessionRows];
                        next[idx] = { ...next[idx], date: e.target.value };
                        setSessionRows(next);
                      }}
                      className="w-full rounded-md border border-gray-300 px-2 py-2 text-sm"
                      required
                    />
                  </div>
                  <div>
                    {idx === 0 && <label className="mb-1 block text-xs text-gray-500">Start</label>}
                    <input
                      type="time"
                      value={row.startTime}
                      onChange={(e) => {
                        const next = [...sessionRows];
                        next[idx] = { ...next[idx], startTime: e.target.value };
                        setSessionRows(next);
                      }}
                      className="w-full rounded-md border border-gray-300 px-2 py-2 text-sm"
                      required
                    />
                  </div>
                  <div>
                    {idx === 0 && <label className="mb-1 block text-xs text-gray-500">End</label>}
                    <input
                      type="time"
                      value={row.endTime}
                      onChange={(e) => {
                        const next = [...sessionRows];
                        next[idx] = { ...next[idx], endTime: e.target.value };
                        setSessionRows(next);
                      }}
                      className="w-full rounded-md border border-gray-300 px-2 py-2 text-sm"
                      required
                    />
                  </div>
                  <button
                    type="button"
                    onClick={() => setSessionRows(sessionRows.filter((_, i) => i !== idx))}
                    disabled={sessionRows.length === 1}
                    className="rounded p-2 text-gray-400 hover:text-red-600 disabled:cursor-not-allowed disabled:opacity-30"
                    aria-label="Remove session"
                    title={sessionRows.length === 1 ? "At least one session required" : "Remove this session"}
                  >
                    <X size={14} />
                  </button>
                </div>
              ))}
            </div>
            <p className="mt-1 text-xs text-gray-500">
              Add a row per session for multi-day workshops, teacher trainings, or retreats.
            </p>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-sm font-medium">Cost ($)</label>
              <input
                type="number"
                step="0.01"
                min="0"
                value={cost}
                onChange={(e) => setCost(e.target.value)}
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
                required
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">
                Instructor share % <span className="text-xs text-gray-500">(studio gets the rest: {100 - instructorPct}%)</span>
              </label>
              <input
                type="number"
                min="0"
                max="100"
                value={instructorPct}
                onChange={(e) => setInstructorPct(Math.max(0, Math.min(100, Number(e.target.value))))}
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
                required
              />
            </div>
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium">Location</label>
            <input
              type="text"
              value={location}
              onChange={(e) => setLocation(e.target.value)}
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-sm font-medium">Capacity (optional)</label>
              <input
                type="number"
                min="1"
                value={capacity}
                onChange={(e) => setCapacity(e.target.value)}
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">Min enrollment</label>
              <input
                type="number"
                min="0"
                value={minEnroll}
                onChange={(e) => setMinEnroll(e.target.value)}
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
              />
            </div>
          </div>

          <div className="rounded-md bg-blue-50 border border-blue-200 p-3 text-xs text-blue-800">
            <strong>What happens next:</strong> we&apos;ll create the workshop in
            the schedule, add the guest to the guest instructor list (if new),
            and email them a private signing link. The instructor fills in their
            workshop description, marketing details, photo, flyer, identity
            info, and signs. Once they sign, you and the instructor each get a
            PDF copy.
          </div>

          <div className="flex justify-end gap-2 border-t pt-4">
            <Button type="button" variant="outline" onClick={onClose} disabled={createMut.isPending}>
              Cancel
            </Button>
            <Button type="submit" disabled={createMut.isPending}>
              {createMut.isPending ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Creating…
                </>
              ) : (
                <>
                  <Send className="mr-2 h-4 w-4" />
                  Create workshop &amp; send contract
                </>
              )}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
