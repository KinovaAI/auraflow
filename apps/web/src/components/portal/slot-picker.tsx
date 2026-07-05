"use client";

import { useEffect, useState } from "react";
import { Loader2, ChevronLeft, ChevronRight } from "lucide-react";
import { portalApi } from "@/lib/portal-api";
import type { PortalTimeSlot } from "@/lib/portal-api";

interface SlotPickerProps {
  instructorId: string;
  serviceId: string;
  onSlotSelected: (slot: PortalTimeSlot, dateStr: string) => void;
}

function formatDayLabel(date: Date): string {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const tomorrow = new Date(today);
  tomorrow.setDate(tomorrow.getDate() + 1);
  const d = new Date(date);
  d.setHours(0, 0, 0, 0);

  if (d.getTime() === today.getTime()) return "Today";
  if (d.getTime() === tomorrow.getTime()) return "Tomorrow";
  return date.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });
}

function formatSlotTime(timeStr: string): string {
  // timeStr is HH:MM:SS or HH:MM
  const [h, m] = timeStr.split(":");
  const hour = parseInt(h, 10);
  const ampm = hour >= 12 ? "PM" : "AM";
  const displayHour = hour === 0 ? 12 : hour > 12 ? hour - 12 : hour;
  return `${displayHour}:${m} ${ampm}`;
}

function getDateString(date: Date): string {
  return date.toISOString().split("T")[0];
}

export function SlotPicker({ instructorId, serviceId, onSlotSelected }: SlotPickerProps) {
  const [dates, setDates] = useState<Date[]>([]);
  const [startIdx, setStartIdx] = useState(0);
  const [selectedDate, setSelectedDate] = useState<Date | null>(null);
  const [slots, setSlots] = useState<PortalTimeSlot[]>([]);
  const [loadingSlots, setLoadingSlots] = useState(false);

  useEffect(() => {
    const d: Date[] = [];
    const today = new Date();
    for (let i = 0; i < 14; i++) {
      const dt = new Date(today);
      dt.setDate(dt.getDate() + i);
      d.push(dt);
    }
    setDates(d);
    setSelectedDate(d[0]);
  }, []);

  useEffect(() => {
    if (!selectedDate) return;
    const loadSlots = async () => {
      setLoadingSlots(true);
      setSlots([]);
      try {
        const dateStr = getDateString(selectedDate);
        const res = await portalApi.getAvailableSlots({
          instructor_id: instructorId,
          service_id: serviceId,
          date: dateStr,
        });
        setSlots(res.data);
      } catch {
        setSlots([]);
      } finally {
        setLoadingSlots(false);
      }
    };
    loadSlots();
  }, [selectedDate, instructorId, serviceId]);

  const visibleDates = dates.slice(startIdx, startIdx + 7);

  return (
    <div className="space-y-4">
      {/* Date Row */}
      <div>
        <div className="mb-2 flex items-center justify-between">
          <span className="text-sm font-medium text-gray-700">Select a date</span>
          <div className="flex gap-1">
            <button
              onClick={() => setStartIdx(Math.max(0, startIdx - 7))}
              disabled={startIdx === 0}
              className="rounded p-1 text-gray-400 hover:bg-gray-100 disabled:opacity-30"
            >
              <ChevronLeft className="h-4 w-4" />
            </button>
            <button
              onClick={() => setStartIdx(Math.min(dates.length - 7, startIdx + 7))}
              disabled={startIdx >= dates.length - 7}
              className="rounded p-1 text-gray-400 hover:bg-gray-100 disabled:opacity-30"
            >
              <ChevronRight className="h-4 w-4" />
            </button>
          </div>
        </div>
        <div className="grid grid-cols-7 gap-1">
          {visibleDates.map((d) => {
            const isSelected =
              selectedDate && getDateString(d) === getDateString(selectedDate);
            return (
              <button
                key={getDateString(d)}
                onClick={() => setSelectedDate(d)}
                className={`flex flex-col items-center rounded-lg px-1 py-2 text-xs transition-colors ${
                  isSelected
                    ? "bg-indigo-600 text-white"
                    : "bg-gray-50 text-gray-600 hover:bg-gray-100"
                }`}
              >
                <span className="font-medium">
                  {d.toLocaleDateString("en-US", { weekday: "short" })}
                </span>
                <span className={`text-lg font-bold ${isSelected ? "text-white" : "text-gray-900"}`}>
                  {d.getDate()}
                </span>
                <span>{d.toLocaleDateString("en-US", { month: "short" })}</span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Time Slots */}
      <div>
        <span className="mb-2 block text-sm font-medium text-gray-700">
          Available times
          {selectedDate && ` – ${formatDayLabel(selectedDate)}`}
        </span>
        {loadingSlots ? (
          <div className="flex justify-center py-6">
            <Loader2 className="h-5 w-5 animate-spin text-indigo-600" />
          </div>
        ) : slots.length === 0 ? (
          <p className="py-6 text-center text-sm text-gray-400">
            No available slots on this day
          </p>
        ) : (
          <div className="grid grid-cols-4 gap-2 sm:grid-cols-5">
            {slots.map((slot) => (
              <button
                key={slot.start_time}
                onClick={() =>
                  selectedDate && onSlotSelected(slot, getDateString(selectedDate))
                }
                className="rounded-lg border border-gray-200 px-2 py-2 text-sm font-medium text-gray-700 transition-colors hover:border-indigo-300 hover:bg-indigo-50 hover:text-indigo-700"
              >
                {formatSlotTime(slot.start_time)}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
