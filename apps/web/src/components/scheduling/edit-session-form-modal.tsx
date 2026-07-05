"use client";

import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { format, parseISO } from "date-fns";
import { X, Loader2, Video, Film, Users } from "lucide-react";
import toast from "react-hot-toast";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  classTypesApi,
  roomsApi,
  sessionsApi,
  type Session,
} from "@/lib/scheduling-api";
import { instructorsApi } from "@/lib/instructors-api";

interface EditSessionFormModalProps {
  session: Session;
  studioId: string;
  onClose: () => void;
  onSaved: () => void;
}

/**
 * Edit a single class session — instructor swap (sub coverage),
 * title, time, duration, capacity, room, virtual/community/auto_record
 * toggles. Hits PUT /scheduling/sessions/{id}, which already handles
 * Zoom-meeting lifecycle on virtual toggle and on time/title change.
 *
 * Per-class sub coverage is the primary use case Don built this for —
 * the instructor dropdown is the first field after class type so it's
 * one click away.
 */
export function EditSessionFormModal({
  session,
  studioId,
  onClose,
  onSaved,
}: EditSessionFormModalProps) {
  // Pre-fill from the existing session
  const startsLocal = format(parseISO(session.starts_at), "yyyy-MM-dd'T'HH:mm");
  const durationMinutes = Math.max(
    15,
    Math.round(
      (parseISO(session.ends_at).getTime() - parseISO(session.starts_at).getTime()) /
        60000,
    ),
  );

  const [title, setTitle] = useState(session.title || "");
  const [classTypeId, setClassTypeId] = useState(session.class_type_id || "");
  const [instructorId, setInstructorId] = useState(session.instructor_id || "");
  const [roomId, setRoomId] = useState(session.room_id || "");
  const [startsAt, setStartsAt] = useState(startsLocal);
  const [duration, setDuration] = useState<number>(durationMinutes);
  const [capacity, setCapacity] = useState<number | "">(session.capacity ?? 20);
  const [modality, setModality] = useState<"in_studio" | "virtual" | "hybrid">(
    session.modality || (session.is_virtual ? "virtual" : "in_studio"),
  );
  const [isCommunity, setIsCommunity] = useState(!!session.is_community);
  const [autoRecord, setAutoRecord] = useState(!!session.auto_record);

  const isVirtual = modality === "virtual" || modality === "hybrid";

  const { data: classTypes } = useQuery({
    queryKey: ["classTypes", studioId],
    queryFn: () => classTypesApi.list(studioId).then((r) => r.data),
  });

  const { data: instructors } = useQuery({
    queryKey: ["instructors"],
    queryFn: () => instructorsApi.list().then((r) => r.data),
  });

  const { data: rooms } = useQuery({
    queryKey: ["rooms", studioId],
    queryFn: () => roomsApi.list(studioId).then((r) => r.data),
  });

  const saveMutation = useMutation({
    mutationFn: () => {
      const start = new Date(startsAt);
      const end = new Date(start.getTime() + duration * 60 * 1000);
      // Send only fields the backend SessionUpdate schema accepts.
      // Empty-string values for optional ids are normalized to undefined
      // so we don't blank out an existing instructor/room by accident.
      // The backend reconciles modality + is_virtual; we send modality
      // as the source of truth.
      return sessionsApi.update(session.id, {
        title: title.trim() || session.title,
        class_type_id: classTypeId || undefined,
        instructor_id: instructorId || undefined,
        room_id: modality === "virtual" ? undefined : (roomId || undefined),
        starts_at: start.toISOString(),
        ends_at: end.toISOString(),
        capacity: typeof capacity === "number" ? capacity : undefined,
        modality,
        is_community: isCommunity,
        auto_record: autoRecord,
      });
    },
    onSuccess: () => {
      toast.success("Class updated");
      onSaved();
    },
    onError: () => toast.error("Failed to update class"),
  });

  const canSubmit = (title.trim() || session.title) && classTypeId && startsAt;
  const instructorChanged = instructorId !== (session.instructor_id || "");

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="mx-4 w-full max-w-lg rounded-lg bg-white shadow-xl max-h-[90vh] flex flex-col">
        <div className="flex items-center justify-between border-b border-gray-200 px-6 py-4 shrink-0">
          <h2 className="text-lg font-semibold text-gray-900">Edit Class</h2>
          <button
            onClick={onClose}
            className="rounded-md p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
          {instructorChanged && (
            <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
              Instructor will change for this class only — the rest of the series
              is unaffected.
            </div>
          )}

          <div>
            <Label htmlFor="edit-class-type">Class Type</Label>
            <select
              id="edit-class-type"
              value={classTypeId}
              onChange={(e) => setClassTypeId(e.target.value)}
              className="flex h-10 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:border-transparent focus:outline-none focus:ring-2 focus:ring-indigo-500"
            >
              <option value="">Select…</option>
              {classTypes?.map((ct: ClassTypeOption) => (
                <option key={ct.id} value={ct.id}>
                  {ct.name}
                </option>
              ))}
            </select>
          </div>

          <div>
            <Label htmlFor="edit-instructor">Instructor</Label>
            <select
              id="edit-instructor"
              value={instructorId}
              onChange={(e) => setInstructorId(e.target.value)}
              className="flex h-10 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:border-transparent focus:outline-none focus:ring-2 focus:ring-indigo-500"
            >
              <option value="">Unassigned</option>
              {instructors?.map((i: InstructorOption) => (
                <option key={i.id} value={i.id}>
                  {i.display_name || `${i.first_name ?? ""} ${i.last_name ?? ""}`.trim()}
                </option>
              ))}
            </select>
          </div>

          <div>
            <Label htmlFor="edit-title">Title</Label>
            <Input
              id="edit-title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Class title"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label htmlFor="edit-starts-at">Starts at</Label>
              <Input
                id="edit-starts-at"
                type="datetime-local"
                value={startsAt}
                onChange={(e) => setStartsAt(e.target.value)}
              />
            </div>
            <div>
              <Label htmlFor="edit-duration">Duration (min)</Label>
              <Input
                id="edit-duration"
                type="number"
                min={15}
                step={5}
                value={duration}
                onChange={(e) => setDuration(parseInt(e.target.value, 10) || 60)}
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label htmlFor="edit-capacity">Capacity</Label>
              <Input
                id="edit-capacity"
                type="number"
                min={1}
                value={capacity}
                onChange={(e) => {
                  const v = e.target.value;
                  setCapacity(v === "" ? "" : parseInt(v, 10));
                }}
              />
            </div>
            {modality !== "virtual" && (
              <div>
                <Label htmlFor="edit-room">Room</Label>
                <select
                  id="edit-room"
                  value={roomId}
                  onChange={(e) => setRoomId(e.target.value)}
                  className="flex h-10 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:border-transparent focus:outline-none focus:ring-2 focus:ring-indigo-500"
                >
                  <option value="">No room</option>
                  {rooms?.map((r: RoomOption) => (
                    <option key={r.id} value={r.id}>
                      {r.name}
                    </option>
                  ))}
                </select>
              </div>
            )}
          </div>

          <div>
            <Label htmlFor="edit-modality">Class Modality</Label>
            <select
              id="edit-modality"
              value={modality}
              onChange={(e) => setModality(e.target.value as typeof modality)}
              className="flex h-10 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:border-transparent focus:outline-none focus:ring-2 focus:ring-indigo-500"
            >
              <option value="in_studio">In-Studio Only — no Zoom</option>
              <option value="virtual">Virtual Only — Zoom only, no studio</option>
              <option value="hybrid">Hybrid — both in-studio and Zoom</option>
            </select>
            <p className="mt-1 text-xs text-gray-500">
              {modality === "in_studio" && "Only in-studio or all-access members can book. No Zoom link sent."}
              {modality === "virtual" && "Only online or all-access members can book. Zoom link sent to all attendees."}
              {modality === "hybrid" && "Any active member can book. Zoom link sent only to members with online or all-access plans."}
            </p>
          </div>

          <div className="space-y-2">
            {isVirtual && (
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={autoRecord}
                  onChange={(e) => setAutoRecord(e.target.checked)}
                  className="h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                />
                <Film className="h-4 w-4 text-rose-500" />
                <span>Auto-record</span>
              </label>
            )}
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={isCommunity}
                onChange={(e) => setIsCommunity(e.target.checked)}
                className="h-4 w-4 rounded border-gray-300 text-amber-600 focus:ring-amber-500"
              />
              <Users className="h-4 w-4 text-amber-600" />
              <span>Community class</span>
            </label>
          </div>
        </div>

        <div className="flex items-center justify-end gap-2 border-t border-gray-200 px-6 py-4 shrink-0">
          <Button variant="ghost" size="sm" onClick={onClose}>
            Cancel
          </Button>
          <Button
            size="sm"
            disabled={!canSubmit || saveMutation.isPending}
            onClick={() => saveMutation.mutate()}
          >
            {saveMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Save Changes
          </Button>
        </div>
      </div>
    </div>
  );
}

// Local helper types — the api lib doesn't export these explicitly,
// and we only need the few fields the dropdowns render.
interface ClassTypeOption { id: string; name: string }
interface InstructorOption {
  id: string;
  display_name?: string;
  first_name?: string;
  last_name?: string;
}
interface RoomOption { id: string; name: string }
