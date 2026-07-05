"use client";

import { useCallback, useMemo, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  format,
  startOfWeek,
  endOfWeek,
  addWeeks,
  subWeeks,
  startOfMonth,
  endOfMonth,
  addDays,
} from "date-fns";
import {
  Calendar as CalendarIcon,
  ChevronLeft,
  ChevronRight,
  Plus,
  Loader2,
} from "lucide-react";
import toast from "react-hot-toast";

import dynamic from "next/dynamic";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

// Dynamic-import CalendarView so fullcalendar (~200 KB) stays out of the
// initial bundle until the user actually navigates to /schedule.
const CalendarView = dynamic(
  () =>
    import("@/components/scheduling/calendar-view").then((m) => m.CalendarView),
  {
    ssr: false,
    loading: () => (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="h-6 w-6 animate-spin text-indigo-600" />
      </div>
    ),
  }
);
import { SessionDetailModal } from "@/components/scheduling/session-detail-modal";
import { SeriesFormModal } from "@/components/scheduling/series-form-modal";
import { SingleSessionFormModal } from "@/components/scheduling/single-session-form-modal";
import { EditSessionFormModal } from "@/components/scheduling/edit-session-form-modal";
import { UploadRecordingModal } from "@/components/scheduling/upload-recording-modal";
import {
  sessionsApi,
  bookingsApi,
  studiosApi,
  type Session,
  type RosterEntry,
} from "@/lib/scheduling-api";
import { apiClient } from "@/lib/api-client";
import { type AddClientData } from "@/components/scheduling/session-detail-modal";
import { membersApi } from "@/lib/members-api";
import { membershipTypesApi, memberMembershipsApi } from "@/lib/memberships-api";
import { coursesApi, type Course } from "@/lib/courses-api";
import { useStudioStore } from "@/stores/studio-store";
// paymentsApi is used within CollectPayment component for real payment processing

type ViewMode = "week" | "day";

export default function SchedulePage() {
  const queryClient = useQueryClient();
  const [currentDate, setCurrentDate] = useState(new Date());
  const [viewMode, setViewMode] = useState<ViewMode>("week");
  const [selectedSession, setSelectedSession] = useState<Session | null>(null);
  const [showSeriesForm, setShowSeriesForm] = useState(false);
  const [showSingleClassForm, setShowSingleClassForm] = useState(false);
  const [editSession, setEditSession] = useState<Session | null>(null);
  const [uploadSession, setUploadSession] = useState<Session | null>(null);

  // Use global studio store
  const studioId = useStudioStore((s) => s.activeStudioId);

  // Fetch studios (still needed for room/studio data in forms)
  const { data: studios } = useQuery({
    queryKey: ["studios"],
    queryFn: () => studiosApi.list().then((r) => r.data),
  });

  // Compute date range for query
  const dateRange = useMemo(() => {
    if (viewMode === "week") {
      const start = startOfWeek(currentDate, { weekStartsOn: 0 });
      const end = endOfWeek(currentDate, { weekStartsOn: 0 });
      return { start, end };
    }
    return { start: currentDate, end: addDays(currentDate, 1) };
  }, [currentDate, viewMode]);

  // Fetch sessions — refetchOnMount ensures classes load even if studioId
  // was null on initial render and populated shortly after
  const { data: sessions, isLoading } = useQuery({
    queryKey: [
      "sessions",
      studioId,
      format(dateRange.start, "yyyy-MM-dd"),
      format(dateRange.end, "yyyy-MM-dd"),
    ],
    queryFn: () =>
      sessionsApi
        .list({
          studio_id: studioId!,
          start: format(dateRange.start, "yyyy-MM-dd"),
          end: format(dateRange.end, "yyyy-MM-dd"),
        })
        .then((r) => r.data),
    enabled: !!studioId,
    refetchOnMount: "always",
  });

  // Fetch upcoming workshop SESSIONS (not courses) so each session
  // renders as its own time block. Using course-level starts_at/ends_at
  // produced a multi-week span that FullCalendar laid out as "all day
  // every day" across the whole series.
  const { data: workshopSessions } = useQuery({
    queryKey: ["workshop-sessions-calendar"],
    queryFn: () =>
      coursesApi
        .listUpcomingSessions(30)
        .then((r) => r.data.data || []),
  });

  // Fetch private session bookings to show on calendar
  const { data: privateBookings } = useQuery({
    queryKey: ["private-bookings-calendar"],
    queryFn: () => apiClient.get("/private-sessions/bookings").then((r) => (r as any).data?.data || []),
  });

  // Fetch roster when a session is selected
  const { data: roster, isLoading: rosterLoading } = useQuery({
    queryKey: ["roster", selectedSession?.id],
    queryFn: () =>
      sessionsApi.getRoster(selectedSession!.id).then((r) => r.data),
    enabled: !!selectedSession,
  });

  const cancelMutation = useMutation({
    mutationFn: ({ id, reason }: { id: string; reason?: string }) =>
      sessionsApi.cancel(id, reason),
    onSuccess: () => {
      toast.success("Session cancelled");
      queryClient.invalidateQueries({ queryKey: ["sessions"] });
      setSelectedSession(null);
    },
    onError: () => toast.error("Failed to cancel session"),
  });

  const checkInMutation = useMutation({
    mutationFn: (bookingId: string) => bookingsApi.checkIn(bookingId),
    onSuccess: () => {
      toast.success("Checked in");
      queryClient.invalidateQueries({ queryKey: ["roster", selectedSession?.id] });
      queryClient.invalidateQueries({ queryKey: ["sessions"] });
    },
    onError: () => toast.error("Failed to check in"),
  });

  const noShowMutation = useMutation({
    mutationFn: (bookingId: string) => bookingsApi.markNoShow(bookingId),
    onSuccess: () => {
      toast.success("Marked as no-show");
      queryClient.invalidateQueries({ queryKey: ["roster", selectedSession?.id] });
    },
    onError: () => toast.error("Failed to mark no-show"),
  });

  const cancelBookingMutation = useMutation({
    mutationFn: (vars: { bookingId: string; lateCancel: boolean }) =>
      bookingsApi.cancel(vars.bookingId, { lateCancel: vars.lateCancel }),
    onSuccess: (_data, vars) => {
      toast.success(
        vars.lateCancel
          ? "Late cancel — credit not refunded"
          : "Booking cancelled — credit refunded"
      );
      queryClient.invalidateQueries({ queryKey: ["roster", selectedSession?.id] });
      queryClient.invalidateQueries({ queryKey: ["sessions"] });
    },
    onError: () => toast.error("Failed to cancel booking"),
  });

  // Fetch drop-in price from membership types
  const { data: membershipTypes } = useQuery({
    queryKey: ["membership-types", studioId],
    queryFn: () =>
      membershipTypesApi.list(studioId!).then((r) => r.data),
    enabled: !!studioId,
  });

  // Community classes use Community Class Pass ($5), regular classes use Single Class Drop-In ($20)
  const isCommunityClass = selectedSession?.is_community ?? false;
  const dropInType = membershipTypes?.find(
    (mt) =>
      mt.is_active &&
      (mt.type === "single_class" || mt.type === "day_pass") &&
      (isCommunityClass
        ? mt.name.toLowerCase().includes("community")
        : !mt.name.toLowerCase().includes("community") && !mt.name.toLowerCase().includes("digital"))
  );
  const dropInPriceCents = dropInType?.price_cents ?? 0;

  const addClientMutation = useMutation({
    mutationFn: async (data: AddClientData) => {
      let memberId = data.member_id;

      // Step 1: Create member record for walk-in guests
      if (!memberId && data.guest_name) {
        const nameParts = data.guest_name.trim().split(/\s+/);
        const firstName = nameParts[0];
        const lastName = nameParts.slice(1).join(" ") || "Guest";
        const newMember = await membersApi.create({
          first_name: firstName,
          last_name: lastName,
          email: data.guest_email || `walkin-${Date.now()}@placeholder.local`,
          source: "walk_in",
        });
        memberId = newMember.data.id;
      }

      // Step 2: Payment already handled by CollectPayment component
      // Card and Square payments were processed in real-time via Stripe/Square APIs.
      // Cash payments were recorded via paymentsApi.recordTransaction() in CollectPayment.
      // Comp payments skip payment entirely.
      // No additional payment action needed here.

      // Step 3: Assign single-class membership if needed
      if (data.needs_membership && dropInType) {
        await memberMembershipsApi.assign(memberId, dropInType.id);
      }

      // Step 4: Create the booking
      return bookingsApi.create({
        member_id: memberId,
        class_session_id: data.class_session_id,
        source: data.source,
        guest_name: data.guest_name,
        guest_email: data.guest_email,
      });
    },
    onSuccess: () => {
      toast.success("Client added to class");
      queryClient.invalidateQueries({ queryKey: ["roster", selectedSession?.id] });
      queryClient.invalidateQueries({ queryKey: ["sessions"] });
    },
    onError: (err: Error) => toast.error(err.message || "Failed to add client"),
  });

  const navigateWeek = useCallback(
    (direction: "prev" | "next") => {
      setCurrentDate((d) =>
        direction === "next"
          ? viewMode === "week"
            ? addWeeks(d, 1)
            : addDays(d, 1)
          : viewMode === "week"
            ? subWeeks(d, 1)
            : addDays(d, -1)
      );
    },
    [viewMode]
  );

  const goToToday = useCallback(() => setCurrentDate(new Date()), []);

  if (studios && studios.length === 0) {
    return (
      <div className="space-y-4">
        <h1 className="text-2xl font-bold text-gray-900">Schedule</h1>
        <div className="rounded-lg border border-dashed border-gray-300 py-12 text-center">
          <p className="text-sm text-gray-500">
            No studios found. Create one in Settings to get started.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Schedule</h1>
          <p className="text-sm text-gray-500">
            Manage your class schedule and sessions
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => setShowSingleClassForm(true)}>
            <Plus className="mr-2 h-4 w-4" />
            New Class
          </Button>
          <Button onClick={() => setShowSeriesForm(true)}>
            <Plus className="mr-2 h-4 w-4" />
            New Series
          </Button>
        </div>
      </div>

      {/* Navigation */}
      <Card>
        <CardContent className="flex flex-col gap-3 py-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={goToToday}>
              Today
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => navigateWeek("prev")}
            >
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => navigateWeek("next")}
            >
              <ChevronRight className="h-4 w-4" />
            </Button>
            <span className="text-sm font-medium text-gray-700">
              {viewMode === "week"
                ? `${format(dateRange.start, "MMM d")} - ${format(dateRange.end, "MMM d, yyyy")}`
                : format(currentDate, "EEEE, MMM d, yyyy")}
            </span>
          </div>
          <div className="flex gap-1 rounded-md border border-gray-200 p-0.5">
            <button
              className={`rounded px-3 py-1 text-xs font-medium ${
                viewMode === "day"
                  ? "bg-indigo-100 text-indigo-700"
                  : "text-gray-500 hover:text-gray-700"
              }`}
              onClick={() => setViewMode("day")}
            >
              Day
            </button>
            <button
              className={`rounded px-3 py-1 text-xs font-medium ${
                viewMode === "week"
                  ? "bg-indigo-100 text-indigo-700"
                  : "text-gray-500 hover:text-gray-700"
              }`}
              onClick={() => setViewMode("week")}
            >
              Week
            </button>
          </div>
        </CardContent>
      </Card>

      {/* Calendar */}
      {isLoading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="h-8 w-8 animate-spin text-indigo-600" />
        </div>
      ) : (
        <CalendarView
          sessions={sessions || []}
          workshopSessions={workshopSessions || []}
          privateBookings={privateBookings || []}
          currentDate={currentDate}
          viewMode={viewMode}
          onSessionClick={setSelectedSession}
          onDateChange={setCurrentDate}
        />
      )}

      {/* Session Detail Modal */}
      {selectedSession && (
        <SessionDetailModal
          session={selectedSession}
          onClose={() => {
            setSelectedSession(null);
            queryClient.invalidateQueries({ queryKey: ["sessions"] });
          }}
          onCancel={(id, reason) => cancelMutation.mutate({ id, reason })}
          onEdit={(s) => {
            setSelectedSession(null);
            setEditSession(s);
          }}
          onUploadRecording={(s) => {
            setSelectedSession(null);
            setUploadSession(s);
          }}
          roster={roster}
          rosterLoading={rosterLoading}
          onCheckIn={(bookingId) => checkInMutation.mutate(bookingId)}
          onNoShow={(bookingId) => noShowMutation.mutate(bookingId)}
          onCancelBooking={(bookingId, lateCancel) =>
            cancelBookingMutation.mutate({ bookingId, lateCancel })
          }
          cancellingBookingId={
            cancelBookingMutation.isPending
              ? cancelBookingMutation.variables?.bookingId ?? null
              : null
          }
          onAddClient={(data) => addClientMutation.mutate(data)}
          addingClient={addClientMutation.isPending}
          dropInPriceCents={dropInPriceCents}
        />
      )}

      {/* Edit Class Modal */}
      {editSession && studioId && (
        <EditSessionFormModal
          session={editSession}
          studioId={studioId}
          onClose={() => setEditSession(null)}
          onSaved={() => {
            queryClient.invalidateQueries({ queryKey: ["sessions"] });
            setEditSession(null);
          }}
        />
      )}

      {/* Upload Recording Modal */}
      {uploadSession && (
        <UploadRecordingModal
          session={uploadSession}
          onClose={() => setUploadSession(null)}
          onUploaded={() => {
            queryClient.invalidateQueries({ queryKey: ["sessions"] });
            setUploadSession(null);
          }}
        />
      )}

      {/* Series Form Modal */}
      {showSeriesForm && studioId && (
        <SeriesFormModal
          studioId={studioId}
          onClose={() => setShowSeriesForm(false)}
          onCreated={() => {
            queryClient.invalidateQueries({ queryKey: ["sessions"] });
            setShowSeriesForm(false);
            toast.success("Series created with sessions expanded");
          }}
        />
      )}

      {showSingleClassForm && studioId && (
        <SingleSessionFormModal
          studioId={studioId}
          onClose={() => setShowSingleClassForm(false)}
          onCreated={() => {
            queryClient.invalidateQueries({ queryKey: ["sessions"] });
            setShowSingleClassForm(false);
            toast.success("Class created");
          }}
        />
      )}
    </div>
  );
}
