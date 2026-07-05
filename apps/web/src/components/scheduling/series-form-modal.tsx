"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { format } from "date-fns";
import { X, Loader2, Video, Film, Plus, Users } from "lucide-react";
import toast from "react-hot-toast";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  classTypesApi,
  seriesApi,
  roomsApi,
  type ClassType,
  type Room,
} from "@/lib/scheduling-api";
import { instructorsApi, type Instructor } from "@/lib/instructors-api";
import { videoApi } from "@/lib/video-api";
import { ClassTypeFormModal } from "./class-type-form-modal";

interface SeriesFormModalProps {
  studioId: string;
  onClose: () => void;
  onCreated: () => void;
}

const DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const RRULE_DAYS = ["SU", "MO", "TU", "WE", "TH", "FR", "SA"];

export function SeriesFormModal({
  studioId,
  onClose,
  onCreated,
}: SeriesFormModalProps) {
  const queryClient = useQueryClient();
  const [title, setTitle] = useState("");
  const [showClassTypeForm, setShowClassTypeForm] = useState(false);
  const [classTypeId, setClassTypeId] = useState("");
  const [instructorId, setInstructorId] = useState("");
  const [roomId, setRoomId] = useState("");
  const [selectedDays, setSelectedDays] = useState<number[]>([]);
  const [startTime, setStartTime] = useState("09:00");
  const [duration, setDuration] = useState(60);
  const [capacity, setCapacity] = useState<number | "">("");
  const [expandWeeks, setExpandWeeks] = useState(4);
  const [isVirtual, setIsVirtual] = useState(false);
  const [isCommunity, setIsCommunity] = useState(false);
  const [autoRecord, setAutoRecord] = useState(false);

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
      const byDay = selectedDays.map((d) => RRULE_DAYS[d]).join(",");
      const rrule = selectedDays.length > 0
        ? `FREQ=WEEKLY;BYDAY=${byDay}`
        : "FREQ=DAILY";

      return seriesApi.create({
        studio_id: studioId,
        class_type_id: classTypeId,
        instructor_id: instructorId || undefined,
        room_id: isVirtual ? undefined : (roomId || undefined),
        title,
        rrule,
        start_time: startTime,
        duration_minutes: duration,
        capacity: capacity || undefined,
        effective_from: format(new Date(), "yyyy-MM-dd"),
        expand_weeks: expandWeeks,
        is_virtual: isVirtual,
        is_community: isCommunity,
        auto_record: autoRecord,
      });
    },
    onSuccess: (res) => {
      onCreated();
    },
    onError: () => toast.error("Failed to create series"),
  });

  const toggleDay = (day: number) => {
    setSelectedDays((prev) =>
      prev.includes(day) ? prev.filter((d) => d !== day) : [...prev, day].sort()
    );
  };

  const canSubmit = title.trim() && classTypeId && selectedDays.length > 0;

  return (
    <>
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="mx-4 w-full max-w-lg rounded-lg bg-white shadow-xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-gray-200 px-6 py-4">
          <h2 className="text-lg font-semibold text-gray-900">
            Create Recurring Series
          </h2>
          <button
            onClick={onClose}
            className="rounded-md p-1 text-gray-400 hover:bg-gray-100"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Form */}
        <div className="max-h-[70vh] space-y-4 overflow-y-auto px-6 py-4">
          <div>
            <Label htmlFor="title">Series Title</Label>
            <Input
              id="title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. Morning Vinyasa"
            />
          </div>

          <div>
            <div className="flex items-center justify-between">
              <Label htmlFor="classType">Class Type</Label>
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
              id="classType"
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
            <Label htmlFor="instructor">Instructor</Label>
            <select
              id="instructor"
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
            <Label htmlFor="room">Room</Label>
            <select
              id="room"
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

          {/* Virtual Class Toggle */}
          <div className="rounded-md border border-gray-200 p-3 space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Video className="h-4 w-4 text-indigo-600" />
                <Label htmlFor="isVirtual" className="mb-0 cursor-pointer">
                  Virtual Class (Zoom)
                </Label>
              </div>
              <button
                type="button"
                id="isVirtual"
                role="switch"
                aria-checked={isVirtual}
                onClick={() => {
                  if (!zoomConnected && !isVirtual) {
                    toast.error("Connect Zoom first in Video > Settings");
                    return;
                  }
                  setIsVirtual(!isVirtual);
                }}
                className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors ${
                  isVirtual ? "bg-indigo-600" : "bg-gray-200"
                }`}
              >
                <span
                  className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow-lg ring-0 transition-transform ${
                    isVirtual ? "translate-x-5" : "translate-x-0"
                  }`}
                />
              </button>
            </div>
            {isVirtual && (
              <p className="text-xs text-gray-500">
                A Zoom meeting will be auto-created for each session in this series.
              </p>
            )}
          </div>

          {/* Community Class */}
          <div className="rounded-md border border-amber-200 bg-amber-50/50 p-3 space-y-2">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Users className="h-4 w-4 text-amber-600" />
                <Label htmlFor="seriesIsCommunity" className="mb-0 cursor-pointer">
                  Community Class
                </Label>
              </div>
              <button
                type="button"
                id="seriesIsCommunity"
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
                Requires a Community Class Pass or unlimited membership to book.
              </p>
            )}
          </div>

          {/* Record for On-Demand Library */}
          <div className="rounded-md border border-gray-200 p-3 space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Film className="h-4 w-4 text-emerald-600" />
                <Label htmlFor="autoRecord" className="mb-0 cursor-pointer">
                  Record for On-Demand Library
                </Label>
              </div>
              <button
                type="button"
                id="autoRecord"
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
                After each session, you can upload a clean recording to the on-demand video library.
              </p>
            )}
          </div>

          <div>
            <Label>Days of Week</Label>
            <div className="mt-1 flex gap-1">
              {DAYS.map((day, idx) => (
                <button
                  key={day}
                  type="button"
                  onClick={() => toggleDay(idx)}
                  className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
                    selectedDays.includes(idx)
                      ? "bg-indigo-600 text-white"
                      : "border border-gray-300 text-gray-600 hover:bg-gray-50"
                  }`}
                >
                  {day}
                </button>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label htmlFor="startTime">Start Time</Label>
              <Input
                id="startTime"
                type="time"
                value={startTime}
                onChange={(e) => setStartTime(e.target.value)}
                className="max-w-[160px]"
              />
            </div>
            <div>
              <Label htmlFor="duration">Duration (min)</Label>
              <Input
                id="duration"
                type="number"
                value={duration}
                onChange={(e) => setDuration(Number(e.target.value))}
                min={15}
                max={240}
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label htmlFor="capacity">Capacity</Label>
              <Input
                id="capacity"
                type="number"
                value={capacity}
                onChange={(e) =>
                  setCapacity(e.target.value ? Number(e.target.value) : "")
                }
                placeholder="Unlimited"
              />
            </div>
            <div>
              <Label htmlFor="expandWeeks">Expand Weeks</Label>
              <Input
                id="expandWeeks"
                type="number"
                value={expandWeeks}
                onChange={(e) => setExpandWeeks(Number(e.target.value))}
                min={1}
                max={52}
              />
            </div>
          </div>
        </div>

        {/* Footer */}
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
            Create Series
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
