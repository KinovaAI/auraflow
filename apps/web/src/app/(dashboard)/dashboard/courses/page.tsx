"use client";

import { useEffect, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { format } from "date-fns";
import {
  Loader2,
  Plus,
  BookOpen,
  Users,
  DollarSign,
  Trash2,
  Pencil,
  X,
  ClipboardList,
} from "lucide-react";
import toast from "react-hot-toast";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  coursesApi,
  type Course,
  type CourseCreate,
  type CourseUpdate,
  type CourseSession,
} from "@/lib/courses-api";
import { instructorsApi, type Instructor } from "@/lib/instructors-api";
import { guestInstructorsApi, type GuestInstructor } from "@/lib/guest-instructors-api";
import { CreateGuestWorkshopDialog } from "@/components/contracts/CreateGuestWorkshopDialog";
import { WorkshopRosterModal } from "@/components/courses/workshop-roster-modal";

// ── Badge helpers ────────────────────────────────────────────────────────────

const statusColors: Record<string, string> = {
  draft: "bg-gray-100 text-gray-700",
  published: "bg-blue-50 text-blue-700",
  in_progress: "bg-yellow-50 text-yellow-700",
  completed: "bg-green-50 text-green-700",
  cancelled: "bg-red-50 text-red-600",
};

const statusLabels: Record<string, string> = {
  draft: "Draft",
  published: "Published",
  in_progress: "In Progress",
  completed: "Completed",
  cancelled: "Cancelled",
};

function StatusBadge({ status }: { status: string }) {
  return (
    <span
      className={`rounded-full px-2 py-0.5 text-xs font-medium ${
        statusColors[status] || "bg-gray-100 text-gray-500"
      }`}
    >
      {statusLabels[status] || status}
    </span>
  );
}

const typeColors: Record<string, string> = {
  workshop: "bg-purple-50 text-purple-700",
  course: "bg-indigo-50 text-indigo-700",
  teacher_training: "bg-orange-50 text-orange-700",
  retreat: "bg-teal-50 text-teal-700",
};

const typeLabels: Record<string, string> = {
  workshop: "Workshop",
  course: "Course",
  teacher_training: "Teacher Training",
  retreat: "Retreat",
};

function TypeBadge({ type }: { type: string }) {
  return (
    <span
      className={`rounded-full px-2 py-0.5 text-xs font-medium ${
        typeColors[type] || "bg-gray-100 text-gray-600"
      }`}
    >
      {typeLabels[type] || type}
    </span>
  );
}


// ── Sessions Editor (shared by Create + Edit dialogs) ───────────────────────

type SessionRow = {
  id?: string;             // present if loaded from server
  starts_at: string;       // datetime-local string (YYYY-MM-DDTHH:MM)
  ends_at: string;
  location?: string;
  is_virtual?: boolean;
  title?: string;
};

function SessionsEditor({
  rows,
  setRows,
}: {
  rows: SessionRow[];
  setRows: (next: SessionRow[]) => void;
}) {
  return (
    <div>
      <div className="mb-2 flex items-center justify-between">
        <label className="block text-sm font-medium text-gray-700">
          Sessions{" "}
          <span className="text-xs font-normal text-gray-500">
            ({rows.length} {rows.length === 1 ? "session" : "sessions"})
          </span>
        </label>
        <button
          type="button"
          onClick={() =>
            setRows([...rows, { starts_at: "", ends_at: "" }])
          }
          className="text-xs font-medium text-indigo-700 hover:text-indigo-900"
        >
          + Add another session
        </button>
      </div>
      <div className="space-y-2">
        {rows.map((row, idx) => (
          <div
            key={row.id ?? `new-${idx}`}
            className="grid grid-cols-[auto_1fr_1fr_auto] items-end gap-2"
          >
            <span className="pb-2 text-xs font-medium text-gray-500">
              #{idx + 1}
            </span>
            <div>
              {idx === 0 && (
                <label className="mb-1 block text-xs text-gray-500">
                  Start (date &amp; time)
                </label>
              )}
              <input
                type="datetime-local"
                value={row.starts_at}
                onChange={(e) => {
                  const next = [...rows];
                  next[idx] = { ...next[idx], starts_at: e.target.value };
                  setRows(next);
                }}
                className="w-full rounded-md border border-gray-300 px-2 py-2 text-sm"
                required
              />
            </div>
            <div>
              {idx === 0 && (
                <label className="mb-1 block text-xs text-gray-500">
                  End (date &amp; time)
                </label>
              )}
              <input
                type="datetime-local"
                value={row.ends_at}
                onChange={(e) => {
                  const next = [...rows];
                  next[idx] = { ...next[idx], ends_at: e.target.value };
                  setRows(next);
                }}
                className="w-full rounded-md border border-gray-300 px-2 py-2 text-sm"
                required
              />
            </div>
            <button
              type="button"
              onClick={() => setRows(rows.filter((_, i) => i !== idx))}
              disabled={rows.length === 1}
              className="rounded p-2 text-gray-400 hover:text-red-600 disabled:cursor-not-allowed disabled:opacity-30"
              aria-label="Remove session"
              title={
                rows.length === 1
                  ? "At least one session required"
                  : "Remove this session"
              }
            >
              <X size={14} />
            </button>
          </div>
        ))}
      </div>
      <p className="mt-1 text-xs text-gray-500">
        Add a row per session for multi-day workshops, teacher trainings, or
        retreats.
      </p>
    </div>
  );
}

function rowsToSessionsPayload(rows: SessionRow[]) {
  return rows.map((r) => ({
    starts_at: new Date(r.starts_at).toISOString(),
    ends_at: new Date(r.ends_at).toISOString(),
    location: r.location || undefined,
    is_virtual: r.is_virtual || false,
    title: r.title || undefined,
  }));
}


// ── Flyer Uploader (shared by Create + Edit dialogs) ────────────────────────

function FlyerUploader({
  value,
  onChange,
}: {
  value?: string | null;
  onChange: (next: string | null) => void;
}) {
  const inputId = "flyer-upload";
  return (
    <div>
      <label className="block text-sm font-medium text-gray-700">
        Workshop flyer{" "}
        <span className="text-xs font-normal text-gray-500">
          (optional — shows on the public Events page)
        </span>
      </label>
      {value ? (
        <div className="mt-1 flex items-start gap-3">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={value}
            alt="Flyer preview"
            className="h-28 w-28 rounded border border-gray-200 object-cover"
          />
          <div className="flex flex-col gap-2">
            <label
              htmlFor={inputId}
              className="cursor-pointer rounded-md border border-gray-300 bg-white px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50"
            >
              Replace
            </label>
            <button
              type="button"
              onClick={() => onChange("")}
              className="text-xs font-medium text-red-600 hover:text-red-800"
            >
              Remove flyer
            </button>
          </div>
        </div>
      ) : (
        <label
          htmlFor={inputId}
          className="mt-1 flex cursor-pointer items-center justify-center rounded-md border-2 border-dashed border-gray-300 px-3 py-6 text-sm text-gray-500 hover:border-indigo-400 hover:text-indigo-600"
        >
          Click to upload (JPG, PNG, WebP — under 5 MB)
        </label>
      )}
      <input
        id={inputId}
        type="file"
        accept="image/jpeg,image/png,image/webp"
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (!f) return;
          if (!/^image\/(jpeg|png|webp)$/.test(f.type)) {
            toast.error("Use a JPG, PNG, or WebP image");
            return;
          }
          if (f.size > 5 * 1024 * 1024) {
            toast.error("Flyer must be under 5 MB");
            return;
          }
          const reader = new FileReader();
          reader.onload = () => {
            const result = reader.result;
            if (typeof result === "string") onChange(result);
          };
          reader.readAsDataURL(f);
          // Reset so picking the same file twice still fires.
          e.target.value = "";
        }}
      />
    </div>
  );
}

// ── Create Course Dialog ────────────────────────────────────────────────────

function CreateCourseDialog({
  instructors,
  guestInstructors,
  onClose,
  onCreated,
}: {
  instructors: Instructor[];
  guestInstructors: GuestInstructor[];
  onClose: () => void;
  onCreated: () => void;
}) {
  const [form, setForm] = useState<CourseCreate>({
    title: "",
    description: "",
    type: "workshop",
    instructor_id: instructors[0]?.id ?? "",
    price_cents: 0,
    capacity: undefined,
    is_virtual: false,
  });
  const [sessionRows, setSessionRows] = useState<SessionRow[]>([
    { starts_at: "", ends_at: "" },
  ]);
  const [flyer, setFlyer] = useState<string | null>(null);
  const [priceDisplay, setPriceDisplay] = useState("");
  // Workshops can be taught by a 1099 guest instructor instead of a
  // staff instructor. The guest dropdown only shows for type='workshop'
  // — non-workshop course types (course, teacher_training, retreat)
  // are staff-instructor only because California labor law forbids
  // 1099 contractors from teaching them. The backend rejects guest
  // assignment to non-workshop types as a 400, and the DB has a
  // CHECK constraint as the final backstop.
  const [instructorKind, setInstructorKind] = useState<"staff" | "guest">("staff");

  const isWorkshop = form.type === "workshop";

  const createMutation = useMutation({
    mutationFn: async (data: CourseCreate) => {
      const created = await coursesApi.createCourse(data).then((r) => r.data.data);
      // Create one course_sessions row per session.
      const payload = rowsToSessionsPayload(sessionRows);
      for (const s of payload) {
        await coursesApi.addSession(created.id, s);
      }
      return created;
    },
    onSuccess: () => {
      toast.success(
        sessionRows.length > 1
          ? `Course created with ${sessionRows.length} sessions`
          : "Course created"
      );
      onCreated();
    },
    onError: () => toast.error("Failed to create course"),
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    // Validate sessions: every row must have valid datetimes and end > start.
    if (!sessionRows.length) {
      toast.error("Add at least one session");
      return;
    }
    for (let i = 0; i < sessionRows.length; i++) {
      const r = sessionRows[i];
      if (!r.starts_at || !r.ends_at) {
        toast.error(`Session ${i + 1}: start and end are required`);
        return;
      }
      if (new Date(r.ends_at) <= new Date(r.starts_at)) {
        toast.error(`Session ${i + 1}: end must be after start`);
        return;
      }
    }
    const sorted = [...sessionRows].sort(
      (a, b) => new Date(a.starts_at).getTime() - new Date(b.starts_at).getTime()
    );
    const useGuest = isWorkshop && instructorKind === "guest";
    const data: CourseCreate = {
      ...form,
      price_cents: form.price_cents || 0,
      // Course-level start/end span the full series so existing list/filter
      // queries work without knowing about sessions.
      starts_at: new Date(sorted[0].starts_at).toISOString(),
      ends_at: new Date(sorted[sorted.length - 1].ends_at).toISOString(),
      capacity: form.capacity || undefined,
      instructor_id: useGuest ? undefined : (form.instructor_id || undefined),
      guest_instructor_id: useGuest ? (form.guest_instructor_id || undefined) : undefined,
      flyer_data_url: flyer || undefined,
    };
    createMutation.mutate(data);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="w-full max-w-lg rounded-lg bg-white p-6 shadow-xl max-h-[92vh] overflow-y-auto">
        <h2 className="text-lg font-semibold text-gray-900">Create Course</h2>
        <form onSubmit={handleSubmit} className="mt-4 space-y-4">
          {/* Title */}
          <div>
            <label className="block text-sm font-medium text-gray-700">
              Title
            </label>
            <input
              type="text"
              required
              value={form.title}
              onChange={(e) => setForm({ ...form, title: e.target.value })}
              className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              placeholder="e.g. Weekend Yoga Immersion"
            />
          </div>

          {/* Type + Instructor row */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700">
                Type
              </label>
              <select
                value={form.type}
                onChange={(e) => {
                  const next = e.target.value;
                  // Switching off workshop wipes guest selection — guests
                  // are workshop-only, so we never carry one over to a
                  // course/training/retreat.
                  if (next !== "workshop") {
                    setInstructorKind("staff");
                    setForm({ ...form, type: next, guest_instructor_id: undefined });
                  } else {
                    setForm({ ...form, type: next });
                  }
                }}
                className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:ring-indigo-500"
              >
                <option value="workshop">Workshop</option>
                <option value="course">Course</option>
                <option value="teacher_training">Teacher Training</option>
                <option value="retreat">Retreat</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700">
                Instructor
              </label>
              {isWorkshop && (
                <div className="mt-1 mb-1 flex gap-1 rounded-md border border-gray-200 bg-gray-50 p-0.5 w-fit">
                  <button
                    type="button"
                    className={`rounded px-2 py-0.5 text-xs font-medium transition ${
                      instructorKind === "staff"
                        ? "bg-white text-indigo-700 shadow-sm"
                        : "text-gray-500 hover:text-gray-700"
                    }`}
                    onClick={() => setInstructorKind("staff")}
                  >
                    Staff
                  </button>
                  <button
                    type="button"
                    className={`rounded px-2 py-0.5 text-xs font-medium transition ${
                      instructorKind === "guest"
                        ? "bg-white text-amber-700 shadow-sm"
                        : "text-gray-500 hover:text-gray-700"
                    }`}
                    onClick={() => setInstructorKind("guest")}
                  >
                    Guest (1099)
                  </button>
                </div>
              )}
              {instructorKind === "guest" && isWorkshop ? (
                <select
                  value={form.guest_instructor_id ?? ""}
                  onChange={(e) =>
                    setForm({ ...form, guest_instructor_id: e.target.value })
                  }
                  className="mt-1 block w-full rounded-md border border-amber-300 px-3 py-2 text-sm shadow-sm focus:border-amber-500 focus:ring-amber-500"
                >
                  <option value="">-- Select guest --</option>
                  {guestInstructors.map((g) => (
                    <option key={g.id} value={g.id}>
                      {g.name} ({g.revenue_share_percent_to_guest}%)
                    </option>
                  ))}
                </select>
              ) : (
                <select
                  value={form.instructor_id ?? ""}
                  onChange={(e) =>
                    setForm({ ...form, instructor_id: e.target.value })
                  }
                  className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:ring-indigo-500"
                >
                  <option value="">-- None --</option>
                  {instructors.map((inst) => (
                    <option key={inst.id} value={inst.id}>
                      {inst.display_name}
                    </option>
                  ))}
                </select>
              )}
            </div>
          </div>

          {/* Description */}
          <div>
            <label className="block text-sm font-medium text-gray-700">
              Description
            </label>
            <textarea
              value={form.description}
              onChange={(e) =>
                setForm({ ...form, description: e.target.value })
              }
              rows={2}
              className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              placeholder="Describe the course..."
            />
          </div>

          {/* Price + Capacity row */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700">
                Price ($)
              </label>
              <input
                type="number"
                min={0}
                step={0.01}
                value={priceDisplay}
                onChange={(e) => {
                  setPriceDisplay(e.target.value);
                  setForm({
                    ...form,
                    price_cents: Math.round(
                      parseFloat(e.target.value || "0") * 100
                    ),
                  });
                }}
                placeholder="0.00"
                className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:ring-indigo-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700">
                Capacity
              </label>
              <input
                type="number"
                min={1}
                placeholder="20 (default)"
                value={form.capacity || ""}
                onChange={(e) =>
                  setForm({
                    ...form,
                    capacity: e.target.value
                      ? parseInt(e.target.value)
                      : undefined,
                  })
                }
                className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:ring-indigo-500"
              />
            </div>
          </div>

          {/* Sessions */}
          <SessionsEditor rows={sessionRows} setRows={setSessionRows} />

          {/* Flyer upload */}
          <FlyerUploader value={flyer} onChange={(v) => setFlyer(v)} />

          {/* Virtual checkbox */}
          <label className="flex items-center gap-2 text-sm text-gray-700">
            <input
              type="checkbox"
              checked={form.is_virtual || false}
              onChange={(e) =>
                setForm({ ...form, is_virtual: e.target.checked })
              }
              className="rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
            />
            Virtual / Online
          </label>

          {createMutation.isError && (
            <p className="text-sm text-red-600">
              Failed to create course. Please try again.
            </p>
          )}

          {/* Actions */}
          <div className="flex justify-end gap-3 pt-2">
            <Button
              type="button"
              variant="outline"
              onClick={onClose}
              disabled={createMutation.isPending}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={createMutation.isPending}>
              {createMutation.isPending && (
                <Loader2 className="mr-1 h-4 w-4 animate-spin" />
              )}
              Create Course
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ── Edit Course Dialog ──────────────────────────────────────────────────────

/** Convert an ISO-8601 timestamp (from the server, UTC) to the value format
 * a native <input type="datetime-local"> expects: YYYY-MM-DDTHH:MM in LOCAL
 * time. The browser already displays datetime-local in local time, so we
 * format using local components, not UTC. */
function toLocalInput(iso?: string): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const pad = (n: number) => n.toString().padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(
    d.getHours()
  )}:${pad(d.getMinutes())}`;
}

function EditCourseDialog({
  course,
  instructors,
  guestInstructors,
  onClose,
  onUpdated,
}: {
  course: Course;
  instructors: Instructor[];
  guestInstructors: GuestInstructor[];
  onClose: () => void;
  onUpdated: () => void;
}) {
  const [form, setForm] = useState<CourseUpdate>({
    title: course.title,
    description: course.description ?? "",
    type: course.type,
    instructor_id: course.instructor_id ?? "",
    guest_instructor_id: course.guest_instructor_id ?? "",
    price_cents: course.price_cents,
    capacity: course.capacity ?? undefined,
    is_virtual: course.is_virtual,
  });
  // Track the original sessions returned by the API + the working state so we
  // can diff on save (deletes for removed rows, updates for changed rows).
  // Flyer state. undefined = unchanged, "" = remove, data:URL = replace.
  const [flyer, setFlyer] = useState<string | null>(course.flyer_data_url ?? null);
  const [flyerDirty, setFlyerDirty] = useState(false);
  const [originalSessions, setOriginalSessions] = useState<CourseSession[]>([]);
  const [sessionRows, setSessionRows] = useState<SessionRow[]>([
    { starts_at: toLocalInput(course.starts_at), ends_at: toLocalInput(course.ends_at) },
  ]);
  const [sessionsLoading, setSessionsLoading] = useState(true);

  // Load sessions on mount.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => {
    let cancelled = false;
    coursesApi.listSessions(course.id).then((r) => {
      if (cancelled) return;
      const sessions = r.data.data ?? [];
      setOriginalSessions(sessions);
      if (sessions.length) {
        setSessionRows(
          sessions.map((s) => ({
            id: s.id,
            starts_at: toLocalInput(s.starts_at),
            ends_at: toLocalInput(s.ends_at),
            location: s.location,
            is_virtual: s.is_virtual,
            title: s.title,
          }))
        );
      }
      setSessionsLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, [course.id]);
  const [priceDisplay, setPriceDisplay] = useState(
    (course.price_cents / 100).toFixed(2)
  );
  const [instructorKind, setInstructorKind] = useState<"staff" | "guest">(
    course.guest_instructor_id ? "guest" : "staff"
  );
  const isWorkshop = (form.type ?? "workshop") === "workshop";

  const updateMutation = useMutation({
    mutationFn: async (data: CourseUpdate) => {
      const updated = await coursesApi
        .updateCourse(course.id, data)
        .then((r) => r.data.data);
      // Diff sessions: delete originals not present, update kept rows, add new rows.
      const keptIds = new Set(
        sessionRows.filter((r) => r.id).map((r) => r.id as string)
      );
      const toDelete = originalSessions.filter((s) => !keptIds.has(s.id));
      for (const s of toDelete) {
        await coursesApi.deleteSession(s.id);
      }
      for (const r of sessionRows) {
        const payload = {
          starts_at: new Date(r.starts_at).toISOString(),
          ends_at: new Date(r.ends_at).toISOString(),
          location: r.location || undefined,
          is_virtual: r.is_virtual || false,
          title: r.title || undefined,
        };
        if (r.id) {
          await coursesApi.updateSession(r.id, payload);
        } else {
          await coursesApi.addSession(course.id, payload);
        }
      }
      return updated;
    },
    onSuccess: () => {
      toast.success(
        sessionRows.length > 1
          ? `Workshop updated (${sessionRows.length} sessions)`
          : "Workshop updated"
      );
      onUpdated();
    },
    onError: () => toast.error("Failed to update workshop"),
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!sessionRows.length) {
      toast.error("Keep at least one session");
      return;
    }
    for (let i = 0; i < sessionRows.length; i++) {
      const r = sessionRows[i];
      if (!r.starts_at || !r.ends_at) {
        toast.error(`Session ${i + 1}: start and end are required`);
        return;
      }
      if (new Date(r.ends_at) <= new Date(r.starts_at)) {
        toast.error(`Session ${i + 1}: end must be after start`);
        return;
      }
    }
    const sorted = [...sessionRows].sort(
      (a, b) => new Date(a.starts_at).getTime() - new Date(b.starts_at).getTime()
    );
    const useGuest = isWorkshop && instructorKind === "guest";
    const data: CourseUpdate = {
      ...form,
      price_cents: form.price_cents ?? 0,
      starts_at: new Date(sorted[0].starts_at).toISOString(),
      ends_at: new Date(sorted[sorted.length - 1].ends_at).toISOString(),
      capacity: form.capacity || undefined,
      instructor_id: useGuest ? undefined : (form.instructor_id || undefined),
      guest_instructor_id: useGuest ? (form.guest_instructor_id || undefined) : undefined,
      // undefined = no change, "" = clear, data: URL = replace.
      flyer_data_url: flyerDirty ? (flyer ?? "") : undefined,
    };
    updateMutation.mutate(data);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="w-full max-w-lg rounded-lg bg-white p-6 shadow-xl max-h-[92vh] overflow-y-auto">
        <h2 className="text-lg font-semibold text-gray-900">Edit Workshop</h2>
        <form onSubmit={handleSubmit} className="mt-4 space-y-4">
          {/* Title */}
          <div>
            <label className="block text-sm font-medium text-gray-700">Title</label>
            <input
              type="text"
              required
              value={form.title ?? ""}
              onChange={(e) => setForm({ ...form, title: e.target.value })}
              className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            />
          </div>

          {/* Type + Instructor */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700">Type</label>
              <select
                value={form.type ?? "workshop"}
                onChange={(e) => {
                  const next = e.target.value;
                  if (next !== "workshop") {
                    setInstructorKind("staff");
                    setForm({ ...form, type: next, guest_instructor_id: undefined });
                  } else {
                    setForm({ ...form, type: next });
                  }
                }}
                className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:ring-indigo-500"
              >
                <option value="workshop">Workshop</option>
                <option value="course">Course</option>
                <option value="teacher_training">Teacher Training</option>
                <option value="retreat">Retreat</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700">Instructor</label>
              {isWorkshop && (
                <div className="mt-1 mb-1 flex gap-1 rounded-md border border-gray-200 bg-gray-50 p-0.5 w-fit">
                  <button
                    type="button"
                    className={`rounded px-2 py-0.5 text-xs font-medium transition ${
                      instructorKind === "staff"
                        ? "bg-white text-indigo-700 shadow-sm"
                        : "text-gray-500 hover:text-gray-700"
                    }`}
                    onClick={() => setInstructorKind("staff")}
                  >
                    Staff
                  </button>
                  <button
                    type="button"
                    className={`rounded px-2 py-0.5 text-xs font-medium transition ${
                      instructorKind === "guest"
                        ? "bg-white text-amber-700 shadow-sm"
                        : "text-gray-500 hover:text-gray-700"
                    }`}
                    onClick={() => setInstructorKind("guest")}
                  >
                    Guest (1099)
                  </button>
                </div>
              )}
              {instructorKind === "guest" && isWorkshop ? (
                <select
                  value={form.guest_instructor_id ?? ""}
                  onChange={(e) =>
                    setForm({ ...form, guest_instructor_id: e.target.value })
                  }
                  className="mt-1 block w-full rounded-md border border-amber-300 px-3 py-2 text-sm shadow-sm focus:border-amber-500 focus:ring-amber-500"
                >
                  <option value="">-- Select guest --</option>
                  {guestInstructors.map((g) => (
                    <option key={g.id} value={g.id}>
                      {g.name} ({g.revenue_share_percent_to_guest}%)
                    </option>
                  ))}
                </select>
              ) : (
                <select
                  value={form.instructor_id ?? ""}
                  onChange={(e) =>
                    setForm({ ...form, instructor_id: e.target.value })
                  }
                  className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:ring-indigo-500"
                >
                  <option value="">-- None --</option>
                  {instructors.map((inst) => (
                    <option key={inst.id} value={inst.id}>
                      {inst.display_name}
                    </option>
                  ))}
                </select>
              )}
            </div>
          </div>

          {/* Description */}
          <div>
            <label className="block text-sm font-medium text-gray-700">Description</label>
            <textarea
              value={form.description ?? ""}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
              rows={2}
              className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            />
          </div>

          {/* Price + Capacity */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700">Price ($)</label>
              <input
                type="number"
                min={0}
                step={0.01}
                value={priceDisplay}
                onChange={(e) => {
                  setPriceDisplay(e.target.value);
                  setForm({
                    ...form,
                    price_cents: Math.round(
                      parseFloat(e.target.value || "0") * 100
                    ),
                  });
                }}
                className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:ring-indigo-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700">Capacity</label>
              <input
                type="number"
                min={1}
                value={form.capacity || ""}
                onChange={(e) =>
                  setForm({
                    ...form,
                    capacity: e.target.value ? parseInt(e.target.value) : undefined,
                  })
                }
                className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:ring-indigo-500"
                placeholder="20 (default)"
              />
            </div>
          </div>

          {/* Sessions */}
          {sessionsLoading ? (
            <p className="text-sm text-gray-500">Loading sessions…</p>
          ) : (
            <SessionsEditor rows={sessionRows} setRows={setSessionRows} />
          )}

          {/* Flyer upload */}
          <FlyerUploader
            value={flyer}
            onChange={(v) => {
              setFlyer(v);
              setFlyerDirty(true);
            }}
          />

          {/* Virtual */}
          <label className="flex items-center gap-2 text-sm text-gray-700">
            <input
              type="checkbox"
              checked={form.is_virtual ?? false}
              onChange={(e) => setForm({ ...form, is_virtual: e.target.checked })}
              className="rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
            />
            Virtual / Online
          </label>

          {updateMutation.isError && (
            <p className="text-sm text-red-600">
              Failed to update workshop. Please try again.
            </p>
          )}

          <div className="flex justify-end gap-3 pt-2">
            <Button
              type="button"
              variant="outline"
              onClick={onClose}
              disabled={updateMutation.isPending}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={updateMutation.isPending}>
              {updateMutation.isPending && (
                <Loader2 className="mr-1 h-4 w-4 animate-spin" />
              )}
              Save Changes
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ── Main Page ───────────────────────────────────────────────────────────────

export default function CoursesPage() {
  const queryClient = useQueryClient();
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [showGuestDialog, setShowGuestDialog] = useState(false);
  const [editingCourse, setEditingCourse] = useState<Course | null>(null);
  const [rosterCourse, setRosterCourse] = useState<Course | null>(null);
  const [statusFilter, setStatusFilter] = useState<string>("");

  // ── Queries ─────────────────────────────────────────────────────────────

  const { data: courses, isLoading: coursesLoading } = useQuery({
    queryKey: ["courses", statusFilter],
    queryFn: () =>
      coursesApi
        .listCourses(statusFilter ? { status: statusFilter } : undefined)
        .then((r) => r.data.data),
  });

  const { data: instructors } = useQuery({
    queryKey: ["instructors"],
    queryFn: () => instructorsApi.list().then((r) => r.data),
  });

  const { data: guestInstructors } = useQuery({
    queryKey: ["guest-instructors", "active"],
    queryFn: () =>
      guestInstructorsApi.list({ active_only: true }).then((r) => r.data),
  });

  // ── Mutations ─────────────────────────────────────────────────────────

  const publishMutation = useMutation({
    mutationFn: (id: string) =>
      coursesApi.publishCourse(id).then((r) => r.data.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["courses"] });
      toast.success("Course published");
    },
    onError: () => toast.error("Failed to publish course"),
  });

  const cancelMutation = useMutation({
    mutationFn: (id: string) =>
      coursesApi.cancelCourse(id).then((r) => r.data.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["courses"] });
      toast.success("Course cancelled");
    },
    onError: () => toast.error("Failed to cancel course"),
  });

  const completeMutation = useMutation({
    mutationFn: (id: string) =>
      coursesApi.completeCourse(id).then((r) => r.data.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["courses"] });
      toast.success("Course completed");
    },
    onError: () => toast.error("Failed to complete course"),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) =>
      coursesApi.deleteCourse(id).then((r) => r.data.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["courses"] });
      toast.success("Course deleted");
    },
    onError: () => toast.error("Failed to delete course"),
  });

  // ── Helpers ───────────────────────────────────────────────────────────

  const fmt = (cents: number) => `$${(cents / 100).toFixed(2)}`;

  const instructorName = (id?: string) => {
    if (!id) return "--";
    const inst = instructors?.find((i: Instructor) => i.id === id);
    return inst?.display_name || "--";
  };

  // Summary stats
  const draftCount = courses?.filter((c) => c.status === "draft").length ?? 0;
  const publishedCount =
    courses?.filter((c) => c.status === "published").length ?? 0;
  const inProgressCount =
    courses?.filter(
      (c) => c.status === "in_progress" || c.status === "published"
    ).length ?? 0;
  const totalEnrolled =
    courses?.reduce((sum, c) => sum + (c.enrolled_count ?? 0), 0) ?? 0;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Workshops</h1>
          <p className="text-sm text-gray-500">
            Manage workshops, courses, teacher trainings, and retreats
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => setShowGuestDialog(true)}>
            <Plus className="mr-1 h-4 w-4" />
            Create Guest Workshop
          </Button>
          <Button onClick={() => setShowCreateDialog(true)}>
            <Plus className="mr-1 h-4 w-4" />
            Create Course
          </Button>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-gray-500">
                  Total Courses
                </p>
                <p className="mt-1 text-2xl font-bold text-gray-900">
                  {coursesLoading ? (
                    <Loader2 className="h-5 w-5 animate-spin" />
                  ) : (
                    courses?.length ?? 0
                  )}
                </p>
              </div>
              <div className="rounded-full bg-indigo-100 p-2">
                <BookOpen className="h-5 w-5 text-indigo-600" />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-gray-500">Active</p>
                <p className="mt-1 text-2xl font-bold text-blue-600">
                  {coursesLoading ? (
                    <Loader2 className="h-5 w-5 animate-spin" />
                  ) : (
                    inProgressCount
                  )}
                </p>
              </div>
              <div className="rounded-full bg-blue-100 p-2">
                <BookOpen className="h-5 w-5 text-blue-600" />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-gray-500">Drafts</p>
                <p className="mt-1 text-2xl font-bold text-gray-600">
                  {coursesLoading ? (
                    <Loader2 className="h-5 w-5 animate-spin" />
                  ) : (
                    draftCount
                  )}
                </p>
              </div>
              <div className="rounded-full bg-gray-100 p-2">
                <BookOpen className="h-5 w-5 text-gray-500" />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-gray-500">
                  Total Enrolled
                </p>
                <p className="mt-1 text-2xl font-bold text-green-600">
                  {coursesLoading ? (
                    <Loader2 className="h-5 w-5 animate-spin" />
                  ) : (
                    totalEnrolled
                  )}
                </p>
              </div>
              <div className="rounded-full bg-green-100 p-2">
                <Users className="h-5 w-5 text-green-600" />
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Status Filter */}
      <div className="flex items-center gap-3">
        <span className="text-sm font-medium text-gray-500">Filter:</span>
        {[
          { key: "", label: "All" },
          { key: "draft", label: "Draft" },
          { key: "published", label: "Published" },
          { key: "in_progress", label: "In Progress" },
          { key: "completed", label: "Completed" },
          { key: "cancelled", label: "Cancelled" },
        ].map((f) => (
          <button
            key={f.key}
            onClick={() => setStatusFilter(f.key)}
            className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
              statusFilter === f.key
                ? "bg-indigo-100 text-indigo-700"
                : "bg-gray-100 text-gray-600 hover:bg-gray-200"
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      {/* Course Cards Grid */}
      {coursesLoading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="h-8 w-8 animate-spin text-indigo-600" />
        </div>
      ) : !courses?.length ? (
        <div className="rounded-lg border border-dashed border-gray-300 py-12 text-center">
          <BookOpen className="mx-auto h-10 w-10 text-gray-300" />
          <p className="mt-2 text-sm text-gray-500">
            {statusFilter
              ? `No ${statusFilter.replace("_", " ")} courses found.`
              : "No courses yet. Create your first course to get started."}
          </p>
          {!statusFilter && (
            <Button
              className="mt-4"
              variant="outline"
              onClick={() => setShowCreateDialog(true)}
            >
              <Plus className="mr-1 h-4 w-4" />
              Create Course
            </Button>
          )}
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {courses.map((course) => (
            <Card
              key={course.id}
              className="overflow-hidden transition-shadow hover:shadow-md"
            >
              <CardContent className="p-5">
                {/* Badges Row */}
                <div className="mb-3 flex items-center gap-2">
                  <TypeBadge type={course.type} />
                  <StatusBadge status={course.status} />
                  {course.is_virtual && (
                    <span className="rounded-full bg-blue-50 px-2 py-0.5 text-xs font-medium text-blue-600">
                      Virtual
                    </span>
                  )}
                </div>

                {/* Title */}
                <h3 className="text-base font-semibold text-gray-900 line-clamp-1">
                  {course.title}
                </h3>

                {/* Description */}
                {course.description && (
                  <p className="mt-1 text-sm text-gray-500 line-clamp-2">
                    {course.description}
                  </p>
                )}

                {/* Details */}
                <div className="mt-3 space-y-1.5 text-sm text-gray-600">
                  <div className="flex items-center justify-between">
                    <span className="text-gray-500">Instructor</span>
                    <span className="font-medium flex items-center gap-1.5">
                      {course.guest_instructor_name ? (
                        <>
                          {course.guest_instructor_name}
                          <span className="rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-amber-700">
                            Guest
                          </span>
                        </>
                      ) : (
                        course.instructor_name ||
                        instructorName(course.instructor_id)
                      )}
                    </span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-gray-500">Price</span>
                    <span className="font-medium">
                      <DollarSign className="mr-0.5 inline h-3.5 w-3.5 text-gray-400" />
                      {fmt(course.price_cents)}
                    </span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-gray-500">Enrolled</span>
                    <span className="font-medium">
                      <Users className="mr-0.5 inline h-3.5 w-3.5 text-gray-400" />
                      {course.enrolled_count ?? 0}
                      {course.capacity
                        ? ` / ${course.capacity}`
                        : ""}
                    </span>
                  </div>
                  {course.starts_at && (
                    <div className="flex items-center justify-between">
                      <span className="text-gray-500">Starts</span>
                      <span className="font-medium">
                        {format(new Date(course.starts_at), "MMM d, yyyy")}
                      </span>
                    </div>
                  )}
                </div>

                {/* Action Buttons */}
                <div className="mt-4 flex items-center gap-2 border-t border-gray-100 pt-3">
                  <Button
                    size="sm"
                    variant="outline"
                    className="text-indigo-600 hover:bg-indigo-50 hover:text-indigo-700"
                    onClick={() => setRosterCourse(course)}
                    aria-label="View roster"
                  >
                    <ClipboardList className="h-4 w-4" />
                  </Button>
                  {course.status !== "completed" &&
                    course.status !== "cancelled" && (
                      <Button
                        size="sm"
                        variant="outline"
                        className="text-gray-600 hover:bg-gray-50 hover:text-gray-900"
                        onClick={() => setEditingCourse(course)}
                        aria-label="Edit workshop"
                      >
                        <Pencil className="h-4 w-4" />
                      </Button>
                    )}
                  {course.status === "draft" && (
                    <Button
                      size="sm"
                      variant="outline"
                      className="flex-1 text-blue-600 hover:bg-blue-50 hover:text-blue-700"
                      onClick={() => publishMutation.mutate(course.id)}
                      disabled={publishMutation.isPending}
                    >
                      Publish
                    </Button>
                  )}
                  {(course.status === "published" ||
                    course.status === "in_progress") && (
                    <Button
                      size="sm"
                      variant="outline"
                      className="flex-1 text-green-600 hover:bg-green-50 hover:text-green-700"
                      onClick={() => completeMutation.mutate(course.id)}
                      disabled={completeMutation.isPending}
                    >
                      Complete
                    </Button>
                  )}
                  {course.status !== "cancelled" &&
                    course.status !== "completed" && (
                      <Button
                        size="sm"
                        variant="outline"
                        className="flex-1 text-red-600 hover:bg-red-50 hover:text-red-700"
                        onClick={() => cancelMutation.mutate(course.id)}
                        disabled={cancelMutation.isPending}
                      >
                        Cancel
                      </Button>
                    )}
                  <Button
                    size="sm"
                    variant="outline"
                    className="text-gray-400 hover:bg-red-50 hover:text-red-600"
                    onClick={() => {
                      if (confirm("Permanently delete this course? This cannot be undone."))
                        deleteMutation.mutate(course.id);
                    }}
                    disabled={deleteMutation.isPending}
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Create Course Dialog */}
      {showCreateDialog && (
        <CreateCourseDialog
          instructors={instructors ?? []}
          guestInstructors={guestInstructors ?? []}
          onClose={() => setShowCreateDialog(false)}
          onCreated={() => {
            setShowCreateDialog(false);
            queryClient.invalidateQueries({ queryKey: ["courses"] });
          }}
        />
      )}

      {/* Create Guest Workshop Dialog (one-shot: course + guest + contract + email) */}
      <CreateGuestWorkshopDialog
        open={showGuestDialog}
        onClose={() => setShowGuestDialog(false)}
        onCreated={() => {
          queryClient.invalidateQueries({ queryKey: ["courses"] });
          queryClient.invalidateQueries({ queryKey: ["guest-instructors", "active"] });
        }}
      />

      {/* Edit Course Dialog */}
      {editingCourse && (
        <EditCourseDialog
          course={editingCourse}
          instructors={instructors ?? []}
          guestInstructors={guestInstructors ?? []}
          onClose={() => setEditingCourse(null)}
          onUpdated={() => {
            setEditingCourse(null);
            queryClient.invalidateQueries({ queryKey: ["courses"] });
          }}
        />
      )}

      {/* Workshop Roster */}
      {rosterCourse && (
        <WorkshopRosterModal
          course={rosterCourse}
          onClose={() => setRosterCourse(null)}
        />
      )}
    </div>
  );
}
