"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { format, addHours } from "date-fns";
import { X, Loader2, Plus, Video, Film, Users } from "lucide-react";
import toast from "react-hot-toast";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  classTypesApi,
  sessionsApi,
  roomsApi,
  type ClassType,
} from "@/lib/scheduling-api";
import { instructorsApi } from "@/lib/instructors-api";
import { videoApi } from "@/lib/video-api";
import { ClassTypeFormModal } from "./class-type-form-modal";

interface SingleSessionFormModalProps {
  studioId: string;
  onClose: () => void;
  onCreated: () => void;
}

export function SingleSessionFormModal({
  studioId,
  onClose,
  onCreated,
}: SingleSessionFormModalProps) {
  const queryClient = useQueryClient();
  const [title, setTitle] = useState("");
  const [classTypeId, setClassTypeId] = useState("");
  const [instructorId, setInstructorId] = useState("");
  const [roomId, setRoomId] = useState("");
  const [startsAt, setStartsAt] = useState("");
  const [duration, setDuration] = useState(60);
  const [capacity, setCapacity] = useState<number | "">(20);
  const [description, setDescription] = useState("");
  const [showClassTypeForm, setShowClassTypeForm] = useState(false);
  const [modality, setModality] = useState<"in_studio" | "virtual" | "hybrid">("in_studio");
  const [isCommunity, setIsCommunity] = useState(false);
  const [autoRecord, setAutoRecord] = useState(false);
  const isVirtual = modality === "virtual" || modality === "hybrid";

  const { data: connectionStatus } = useQuery({
    queryKey: ["video-connection-status"],
    queryFn: () => videoApi.getConnectionStatus().then((r) => r.data?.data),
  });

  const zoomConnected = connectionStatus?.zoom_connected ?? false;

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

  const createMutation = useMutation({
    mutationFn: () => {
      const start = new Date(startsAt);
      const end = new Date(start.getTime() + duration * 60 * 1000);
      return sessionsApi.create({
        studio_id: studioId,
        class_type_id: classTypeId,
        instructor_id: instructorId || undefined,
        room_id: modality === "virtual" ? undefined : (roomId || undefined),
        title,
        starts_at: start.toISOString(),
        ends_at: end.toISOString(),
        capacity: capacity || undefined,
        modality,
        is_community: isCommunity,
        auto_record: autoRecord,
      });
    },
    onSuccess: () => {
      onCreated();
    },
    onError: () => toast.error("Failed to create class"),
  });

  const canSubmit = title.trim() && classTypeId && startsAt;

  return (
    <>
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
        <div className="mx-4 w-full max-w-lg rounded-lg bg-white shadow-xl">
          <div className="flex items-center justify-between border-b border-gray-200 px-6 py-4">
            <h2 className="text-lg font-semibold text-gray-900">
              Create Single Class
            </h2>
            <button
              onClick={onClose}
              className="rounded-md p-1 text-gray-400 hover:bg-gray-100"
            >
              <X className="h-5 w-5" />
            </button>
          </div>

          <div className="max-h-[70vh] space-y-4 overflow-y-auto px-6 py-4">
            <div>
              <Label htmlFor="ssTitle">Class Title *</Label>
              <Input
                id="ssTitle"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="e.g. Saturday Morning Yoga"
              />
            </div>

            <div>
              <div className="flex items-center justify-between">
                <Label htmlFor="ssClassType">Class Type *</Label>
                <button
                  type="button"
                  onClick={() => setShowClassTypeForm(true)}
                  className="flex items-center gap-1 text-xs text-indigo-600 hover:text-indigo-700"
                >
                  <Plus className="h-3 w-3" />
                  New Type
                </button>
              </div>
              <select
                id="ssClassType"
                value={classTypeId}
                onChange={(e) => setClassTypeId(e.target.value)}
                className="flex h-10 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:border-transparent focus:outline-none focus:ring-2 focus:ring-indigo-500"
              >
                <option value="">Select class type...</option>
                {classTypes?.map((ct) => (
                  <option key={ct.id} value={ct.id}>
                    {ct.name}
                  </option>
                ))}
              </select>
              {classTypes?.length === 0 && (
                <p className="mt-1 text-xs text-amber-600">
                  No class types yet. Create one first.
                </p>
              )}
            </div>

            <div>
              <Label htmlFor="ssDesc">Description</Label>
              <textarea
                id="ssDesc"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows={2}
                className="flex w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm placeholder:text-gray-400 focus:border-transparent focus:outline-none focus:ring-2 focus:ring-indigo-500"
                placeholder="Optional description..."
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label htmlFor="ssInstructor">Instructor</Label>
                <select
                  id="ssInstructor"
                  value={instructorId}
                  onChange={(e) => setInstructorId(e.target.value)}
                  className="flex h-10 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:border-transparent focus:outline-none focus:ring-2 focus:ring-indigo-500"
                >
                  <option value="">No instructor</option>
                  {instructors?.map((inst) => (
                    <option key={inst.id} value={inst.id}>
                      {inst.display_name}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <Label htmlFor="ssRoom">Room</Label>
                <select
                  id="ssRoom"
                  value={roomId}
                  onChange={(e) => setRoomId(e.target.value)}
                  className="flex h-10 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:border-transparent focus:outline-none focus:ring-2 focus:ring-indigo-500"
                >
                  <option value="">No room</option>
                  {rooms?.map((r) => (
                    <option key={r.id} value={r.id}>
                      {r.name} {r.capacity ? `(${r.capacity})` : ""}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div>
              <Label htmlFor="ssStartsAt">Date & Time *</Label>
              <Input
                id="ssStartsAt"
                type="datetime-local"
                value={startsAt}
                onChange={(e) => setStartsAt(e.target.value)}
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label htmlFor="ssDuration">Duration (min)</Label>
                <Input
                  id="ssDuration"
                  type="number"
                  value={duration}
                  onChange={(e) => setDuration(Number(e.target.value))}
                  min={15}
                  max={240}
                />
              </div>
              <div>
                <Label htmlFor="ssCapacity">Capacity</Label>
                <Input
                  id="ssCapacity"
                  type="number"
                  value={capacity}
                  onChange={(e) =>
                    setCapacity(e.target.value ? Number(e.target.value) : "")
                  }
                  placeholder="Unlimited"
                />
              </div>
            </div>

            {/* Class Modality */}
            <div className="rounded-md border border-gray-200 p-3 space-y-2">
              <div className="flex items-center gap-2">
                <Video className="h-4 w-4 text-indigo-600" />
                <Label htmlFor="ssModality" className="mb-0">Class Modality</Label>
              </div>
              <select
                id="ssModality"
                value={modality}
                onChange={(e) => {
                  const next = e.target.value as typeof modality;
                  if (!zoomConnected && (next === "virtual" || next === "hybrid")) {
                    toast.error("Connect Zoom first in Video > Settings");
                    return;
                  }
                  setModality(next);
                }}
                className="flex h-10 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:border-transparent focus:outline-none focus:ring-2 focus:ring-indigo-500"
              >
                <option value="in_studio">In-Studio Only — no Zoom</option>
                <option value="virtual">Virtual Only — Zoom only, no studio</option>
                <option value="hybrid">Hybrid — both in-studio and Zoom</option>
              </select>
              <p className="text-xs text-gray-500">
                {modality === "in_studio" && "Only in-studio or all-access members can book. No Zoom link sent."}
                {modality === "virtual" && "Only online or all-access members can book. Zoom link sent to all attendees."}
                {modality === "hybrid" && "Any active member can book. Zoom link sent only to members with online or all-access plans."}
              </p>
            </div>

            {/* Community Class */}
            <div className="rounded-md border border-amber-200 bg-amber-50/50 p-3 space-y-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Users className="h-4 w-4 text-amber-600" />
                  <Label htmlFor="ssIsCommunity" className="mb-0 cursor-pointer">
                    Community Class
                  </Label>
                </div>
                <button
                  type="button"
                  id="ssIsCommunity"
                  role="switch"
                  aria-checked={isCommunity}
                  onClick={() => setIsCommunity(!isCommunity)}
                  className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors ${
                    isCommunity ? "bg-amber-500" : "bg-gray-200"
                  }`}
                >
                  <span
                    className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow-lg ring-0 transition-transform ${
                      isCommunity ? "translate-x-5" : "translate-x-0"
                    }`}
                  />
                </button>
              </div>
              {isCommunity && (
                <p className="text-xs text-amber-700">
                  This class requires a Community Class Pass or unlimited membership to book.
                </p>
              )}
            </div>

            {/* Record for On-Demand Library */}
            <div className="rounded-md border border-gray-200 p-3 space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Film className="h-4 w-4 text-emerald-600" />
                  <Label htmlFor="ssAutoRecord" className="mb-0 cursor-pointer">
                    Record for On-Demand Library
                  </Label>
                </div>
                <button
                  type="button"
                  id="ssAutoRecord"
                  role="switch"
                  aria-checked={autoRecord}
                  onClick={() => setAutoRecord(!autoRecord)}
                  className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors ${
                    autoRecord ? "bg-emerald-600" : "bg-gray-200"
                  }`}
                >
                  <span
                    className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow-lg ring-0 transition-transform ${
                      autoRecord ? "translate-x-5" : "translate-x-0"
                    }`}
                  />
                </button>
              </div>
              {autoRecord && (
                <p className="text-xs text-gray-500">
                  After this session, you can upload a clean recording to the on-demand video library.
                </p>
              )}
            </div>
          </div>

          <div className="flex items-center justify-end gap-2 border-t border-gray-200 px-6 py-4">
            <Button variant="ghost" onClick={onClose}>
              Cancel
            </Button>
            <Button
              onClick={() => createMutation.mutate()}
              disabled={!canSubmit || createMutation.isPending}
            >
              {createMutation.isPending && (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              )}
              Create Class
            </Button>
          </div>
        </div>
      </div>

      {showClassTypeForm && (
        <ClassTypeFormModal
          studioId={studioId}
          onClose={() => setShowClassTypeForm(false)}
          onCreated={() => {
            queryClient.invalidateQueries({ queryKey: ["classTypes", studioId] });
            setShowClassTypeForm(false);
          }}
        />
      )}
    </>
  );
}
