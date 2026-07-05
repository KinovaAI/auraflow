"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { X, Plus, Trash2, Loader2 } from "lucide-react";
import toast from "react-hot-toast";

import { Button } from "@/components/ui/button";
import { instructorsApi, type AvailabilitySlot } from "@/lib/instructors-api";

interface AvailabilityEditorProps {
  instructorId: string;
  currentSlots: AvailabilitySlot[];
  onClose: () => void;
  onSaved: () => void;
}

const DAYS = [
  "Sunday",
  "Monday",
  "Tuesday",
  "Wednesday",
  "Thursday",
  "Friday",
  "Saturday",
];

export function AvailabilityEditor({
  instructorId,
  currentSlots,
  onClose,
  onSaved,
}: AvailabilityEditorProps) {
  const [slots, setSlots] = useState<AvailabilitySlot[]>(
    currentSlots.length > 0
      ? currentSlots.map((s) => ({
          day_of_week: s.day_of_week,
          start_time: s.start_time,
          end_time: s.end_time,
        }))
      : [{ day_of_week: 1, start_time: "09:00", end_time: "17:00" }]
  );

  const saveMutation = useMutation({
    mutationFn: () => instructorsApi.setAvailability(instructorId, slots),
    onSuccess: () => onSaved(),
    onError: () => toast.error("Failed to save availability"),
  });

  const addSlot = () => {
    setSlots((prev) => [
      ...prev,
      { day_of_week: 1, start_time: "09:00", end_time: "17:00" },
    ]);
  };

  const removeSlot = (index: number) => {
    setSlots((prev) => prev.filter((_, i) => i !== index));
  };

  const updateSlot = (
    index: number,
    field: keyof AvailabilitySlot,
    value: string | number
  ) => {
    setSlots((prev) =>
      prev.map((s, i) => (i === index ? { ...s, [field]: value } : s))
    );
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="mx-4 w-full max-w-lg rounded-lg bg-white shadow-xl">
        <div className="flex items-center justify-between border-b border-gray-200 px-6 py-4">
          <h2 className="text-lg font-semibold text-gray-900">
            Edit Availability
          </h2>
          <button
            onClick={onClose}
            className="rounded-md p-1 text-gray-400 hover:bg-gray-100"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="max-h-[60vh] space-y-3 overflow-y-auto px-6 py-4">
          {slots.map((slot, idx) => (
            <div
              key={idx}
              className="flex items-center gap-2 rounded-md border border-gray-200 p-3"
            >
              <select
                value={slot.day_of_week}
                onChange={(e) =>
                  updateSlot(idx, "day_of_week", Number(e.target.value))
                }
                className="rounded-md border border-gray-300 px-2 py-1.5 text-sm"
              >
                {DAYS.map((d, i) => (
                  <option key={i} value={i}>
                    {d}
                  </option>
                ))}
              </select>
              <input
                type="time"
                value={slot.start_time}
                onChange={(e) => updateSlot(idx, "start_time", e.target.value)}
                className="rounded-md border border-gray-300 px-2 py-1.5 text-sm"
              />
              <span className="text-sm text-gray-400">to</span>
              <input
                type="time"
                value={slot.end_time}
                onChange={(e) => updateSlot(idx, "end_time", e.target.value)}
                className="rounded-md border border-gray-300 px-2 py-1.5 text-sm"
              />
              <button
                onClick={() => removeSlot(idx)}
                className="ml-auto rounded-md p-1 text-gray-400 hover:bg-red-50 hover:text-red-500"
              >
                <Trash2 className="h-4 w-4" />
              </button>
            </div>
          ))}

          <Button variant="outline" size="sm" onClick={addSlot} className="w-full">
            <Plus className="mr-1 h-4 w-4" />
            Add Time Slot
          </Button>
        </div>

        <div className="flex items-center justify-end gap-2 border-t border-gray-200 px-6 py-4">
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button
            onClick={() => saveMutation.mutate()}
            disabled={slots.length === 0 || saveMutation.isPending}
          >
            {saveMutation.isPending && (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            )}
            Save Availability
          </Button>
        </div>
      </div>
    </div>
  );
}
