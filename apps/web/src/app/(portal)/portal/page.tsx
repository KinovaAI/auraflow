"use client";

import { useEffect, useState } from "react";
import { Calendar, Clock, MapPin, User, Loader2, Video } from "lucide-react";
import toast from "react-hot-toast";

import { portalApi } from "@/lib/portal-api";
import type { PortalSession } from "@/lib/portal-api";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { BookClassModal } from "@/components/portal/book-class-modal";

type DateFilter = "today" | "week" | "next_week";

function getDateRange(filter: DateFilter) {
  const now = new Date();
  const start = new Date(now);
  start.setHours(0, 0, 0, 0);

  const end = new Date(start);

  switch (filter) {
    case "today":
      end.setDate(end.getDate() + 1);
      break;
    case "week":
      end.setDate(end.getDate() + 7);
      break;
    case "next_week":
      start.setDate(start.getDate() + 7);
      end.setDate(end.getDate() + 14);
      break;
  }

  return {
    start: start.toISOString().split("T")[0],
    end: end.toISOString().split("T")[0],
  };
}

function formatTime(isoStr: string) {
  return new Date(isoStr).toLocaleTimeString("en-US", {
    hour: "numeric",
    minute: "2-digit",
  });
}

function formatDate(isoStr: string) {
  return new Date(isoStr).toLocaleDateString("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
  });
}

export default function PortalSchedulePage() {
  const [sessions, setSessions] = useState<PortalSession[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<DateFilter>("week");
  const [bookingSession, setBookingSession] = useState<PortalSession | null>(null);

  const fetchSchedule = async () => {
    setLoading(true);
    try {
      const range = getDateRange(filter);
      const { data } = await portalApi.getSchedule({
        start: range.start,
        end: range.end,
        limit: 50,
      });
      setSessions(data);
    } catch {
      toast.error("Failed to load schedule");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSchedule();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filter]);

  const handleBooked = () => {
    setBookingSession(null);
    fetchSchedule();
    toast.success("Class booked!");
  };

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">Class Schedule</h1>
        <div className="flex gap-1 rounded-lg bg-white p-1 shadow-sm">
          {(
            [
              { key: "today", label: "Today" },
              { key: "week", label: "This Week" },
              { key: "next_week", label: "Next Week" },
            ] as const
          ).map((opt) => (
            <button
              key={opt.key}
              onClick={() => setFilter(opt.key)}
              className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                filter === opt.key
                  ? "bg-indigo-600 text-white"
                  : "text-gray-600 hover:text-gray-900"
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-16">
          <Loader2 className="h-6 w-6 animate-spin text-indigo-600" />
        </div>
      ) : sessions.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center">
            <Calendar className="mx-auto mb-3 h-10 w-10 text-gray-300" />
            <p className="text-gray-500">No classes scheduled for this period</p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {sessions.map((session) => (
            <Card key={session.id} className="transition-shadow hover:shadow-md">
              <CardContent className="flex items-center justify-between p-4">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <h3 className="font-semibold text-gray-900">
                      {session.title || session.class_type_name || "Class"}
                    </h3>
                    {session.class_category && (
                      <span className="rounded-full bg-indigo-50 px-2 py-0.5 text-xs font-medium text-indigo-700">
                        {session.class_category}
                      </span>
                    )}
                    {session.is_virtual && (
                      <span className="inline-flex items-center gap-1 rounded-full bg-purple-50 px-2 py-0.5 text-xs font-medium text-purple-700">
                        <Video className="h-3 w-3" />
                        Virtual
                      </span>
                    )}
                    {session.level && (
                      <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-600">
                        {session.level}
                      </span>
                    )}
                  </div>
                  <div className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1 text-sm text-gray-500">
                    <span className="flex items-center gap-1">
                      <Calendar className="h-3.5 w-3.5" />
                      {formatDate(session.starts_at)}
                    </span>
                    <span className="flex items-center gap-1">
                      <Clock className="h-3.5 w-3.5" />
                      {formatTime(session.starts_at)}
                      {session.ends_at && ` - ${formatTime(session.ends_at)}`}
                    </span>
                    {session.instructor_name && (
                      <span className="flex items-center gap-1">
                        <User className="h-3.5 w-3.5" />
                        {session.instructor_name}
                      </span>
                    )}
                    {session.is_virtual ? (
                      <span className="flex items-center gap-1 text-purple-600">
                        <Video className="h-3.5 w-3.5" />
                        Online
                      </span>
                    ) : session.room_name ? (
                      <span className="flex items-center gap-1">
                        <MapPin className="h-3.5 w-3.5" />
                        {session.room_name}
                      </span>
                    ) : null}
                  </div>
                </div>
                <div className="ml-4 flex flex-col items-end gap-1">
                  {session.is_full ? (
                    <span className="text-sm font-medium text-red-600">Full</span>
                  ) : (
                    <span className="text-sm text-gray-500">
                      {session.spots_remaining} spot{session.spots_remaining !== 1 ? "s" : ""} left
                    </span>
                  )}
                  <Button
                    size="sm"
                    onClick={() => setBookingSession(session)}
                    disabled={session.is_full && !session.waitlist_available}
                  >
                    {session.is_full ? "Waitlist" : "Book"}
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {bookingSession && (
        <BookClassModal
          session={bookingSession}
          onClose={() => setBookingSession(null)}
          onBooked={handleBooked}
        />
      )}
    </div>
  );
}
