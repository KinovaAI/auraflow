"use client";

import { useMemo } from "react";
import FullCalendar from "@fullcalendar/react";
import dayGridPlugin from "@fullcalendar/daygrid";
import timeGridPlugin from "@fullcalendar/timegrid";
import interactionPlugin from "@fullcalendar/interaction";
import { Video, Film, Sparkles } from "lucide-react";
import type { Session } from "@/lib/scheduling-api";

interface Workshop {
  id: string;
  title: string;
  starts_at?: string;
  ends_at?: string;
  instructor_name?: string;
  type?: string;
}

interface WorkshopSession {
  id: string;
  course_id: string;
  title?: string;          // optional per-session label
  course_title?: string;   // the workshop's title (joined in)
  starts_at: string;
  ends_at: string;
  is_virtual?: boolean;
  location?: string;
}

interface PrivateBooking {
  id: string;
  starts_at?: string;
  ends_at?: string;
  service_name?: string;
  member_name?: string;
  instructor_name?: string;
  status?: string;
}

interface CalendarViewProps {
  sessions: Session[];
  workshops?: Workshop[];
  workshopSessions?: WorkshopSession[];
  privateBookings?: PrivateBooking[];
  currentDate: Date;
  viewMode: "week" | "day";
  onSessionClick: (session: Session) => void;
  onDateChange: (date: Date) => void;
}

export function CalendarView({
  sessions,
  workshops = [],
  workshopSessions = [],
  privateBookings = [],
  currentDate,
  viewMode,
  onSessionClick,
  onDateChange,
}: CalendarViewProps) {
  const events = useMemo(() => {
    const sessionEvents = sessions.map((s) => ({
      id: s.id,
      title: s.title,
      start: s.starts_at,
      end: s.ends_at,
      backgroundColor:
        s.status === "cancelled"
          ? "#EF4444"
          : s.status === "completed"
            ? "#6B7280"
            : s.is_community
              ? "#D97706"
              : s.is_virtual
                ? "#7C3AED"
                : "#6366F1",
      borderColor: "transparent",
      extendedProps: { session: s, isWorkshop: false },
    }));

    // Prefer per-session events (workshopSessions): each course_session
    // becomes its own 1-hour block on the calendar. Fall back to the
    // course-level workshops list only if no per-session data was
    // provided (legacy callers).
    const workshopEvents = workshopSessions.length > 0
      ? workshopSessions
          .filter((s) => s.starts_at && s.ends_at)
          .map((s) => ({
            id: `workshop-session-${s.id}`,
            title: `🎪 ${s.course_title || s.title || "Workshop"}`,
            start: s.starts_at,
            end: s.ends_at,
            backgroundColor: "#059669",
            borderColor: "#047857",
            extendedProps: { workshopSession: s, isWorkshop: true },
          }))
      : workshops.filter((w) => w.starts_at && w.ends_at).map((w) => ({
          id: `workshop-${w.id}`,
          title: `🎪 ${w.title}`,
          start: w.starts_at,
          end: w.ends_at,
          backgroundColor: "#059669",
          borderColor: "#047857",
          extendedProps: { workshop: w, isWorkshop: true },
        }));

    const privateEvents = privateBookings
      .filter((p) => p.starts_at && p.ends_at && p.status !== "cancelled")
      .map((p) => ({
        id: `private-${p.id}`,
        title: p.service_name || "Private Session",
        start: p.starts_at,
        end: p.ends_at,
        backgroundColor: "#EC4899",
        borderColor: "#DB2777",
        extendedProps: { privateBooking: p, isPrivate: true },
      }));

    return [...sessionEvents, ...workshopEvents, ...privateEvents];
  }, [sessions, workshops, workshopSessions, privateBookings]);

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4">
      <FullCalendar
        key={`${viewMode}-${currentDate.toISOString()}`}
        plugins={[dayGridPlugin, timeGridPlugin, interactionPlugin]}
        initialView={viewMode === "week" ? "timeGridWeek" : "timeGridDay"}
        initialDate={currentDate}
        headerToolbar={false}
        events={events}
        height="auto"
        contentHeight={600}
        slotMinTime="06:00:00"
        slotMaxTime="22:00:00"
        allDaySlot={false}
        nowIndicator
        slotDuration="00:30:00"
        eventClick={(info) => {
          if (info.event.extendedProps.isWorkshop || info.event.extendedProps.isPrivate) {
            return;
          }
          const session = info.event.extendedProps.session as Session;
          onSessionClick(session);
        }}
        eventContent={(arg) => {
          if (arg.event.extendedProps.isPrivate) {
            const p = arg.event.extendedProps.privateBooking as PrivateBooking;
            return (
              <div className="cursor-default overflow-hidden p-1 text-xs">
                <div className="font-semibold">{p.service_name || "Private Session"}</div>
                {p.member_name && <div className="opacity-80">{p.member_name}</div>}
                {p.instructor_name && <div className="opacity-60">{p.instructor_name}</div>}
                <div className="opacity-60 italic">Private</div>
              </div>
            );
          }

          if (arg.event.extendedProps.isWorkshop) {
            // Workshop events come from two sources: the new per-session
            // path (workshopSession) and the legacy course-level path
            // (workshop). Read both and prefer per-session when present.
            const ws = arg.event.extendedProps.workshopSession as
              | WorkshopSession
              | undefined;
            const w = arg.event.extendedProps.workshop as Workshop | undefined;
            const title = ws?.course_title || ws?.title || w?.title || "Workshop";
            const subtitle =
              w?.type === "retreat"
                ? "Retreat"
                : w?.type === "workshop" || ws
                  ? "Workshop"
                  : "Event";
            return (
              <div className="cursor-default overflow-hidden p-1 text-xs">
                <div className="flex items-center gap-1 font-semibold">
                  <Sparkles className="h-3 w-3 shrink-0" />
                  {title}
                </div>
                {w?.instructor_name && (
                  <div className="opacity-80">{w.instructor_name}</div>
                )}
                <div className="opacity-60 italic">{subtitle}</div>
              </div>
            );
          }

          const session = arg.event.extendedProps.session as Session;
          return (
            <div className="cursor-pointer overflow-hidden p-1 text-xs">
              <div className="flex items-center gap-1 font-semibold">
                {session.is_virtual && (
                  <Video className="h-3 w-3 shrink-0" />
                )}
                {!session.is_virtual && session.auto_record && (
                  <Film className="h-3 w-3 shrink-0" />
                )}
                {arg.event.title}
              </div>
              {session.instructor_name && (
                <div className="opacity-80">{session.instructor_name}</div>
              )}
              {session.room_name && (
                <div className="opacity-60">{session.room_name}</div>
              )}
              {session.booked_count !== undefined && (
                <div className="opacity-60">
                  {session.booked_count}
                  {session.capacity ? `/${session.capacity}` : ""} booked
                </div>
              )}
            </div>
          );
        }}
      />
    </div>
  );
}
