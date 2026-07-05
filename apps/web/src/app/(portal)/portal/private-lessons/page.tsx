"use client";

import { useEffect, useState, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import {
  User,
  Loader2,
  Clock,
  Calendar,
  Video,
  X,
} from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { portalApi } from "@/lib/portal-api";
import type { PortalInstructor, PortalPrivateBooking } from "@/lib/portal-api";
import { InstructorDetailModal } from "@/components/portal/instructor-detail-modal";
import toast from "react-hot-toast";

const STATUS_CONFIG: Record<string, { color: string; label: string }> = {
  pending: { color: "bg-amber-50 text-amber-700", label: "Pending" },
  confirmed: { color: "bg-green-50 text-green-700", label: "Confirmed" },
  cancelled: { color: "bg-gray-100 text-gray-500", label: "Cancelled" },
  completed: { color: "bg-blue-50 text-blue-700", label: "Completed" },
  no_show: { color: "bg-red-50 text-red-600", label: "No Show" },
};

function formatDateTime(iso?: string): string {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleDateString("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
  }) + " at " + d.toLocaleTimeString("en-US", {
    hour: "numeric",
    minute: "2-digit",
  });
}

function formatPrice(cents: number): string {
  return `$${(cents / 100).toFixed(cents % 100 === 0 ? 0 : 2)}`;
}

function PrivateLessonsContent() {
  const searchParams = useSearchParams();
  const [instructors, setInstructors] = useState<PortalInstructor[]>([]);
  const [bookings, setBookings] = useState<PortalPrivateBooking[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedInstructor, setSelectedInstructor] = useState<PortalInstructor | null>(null);

  const loadData = async () => {
    setLoading(true);
    try {
      const [instrRes, bookRes] = await Promise.all([
        portalApi.getInstructors(),
        portalApi.getMyPrivateBookings(),
      ]);
      setInstructors(instrRes.data);
      setBookings(bookRes.data);
    } catch {
      toast.error("Failed to load data");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  useEffect(() => {
    if (searchParams.get("booked") === "1") {
      toast.success("Session booked successfully!");
      window.history.replaceState({}, "", "/portal/private-lessons");
    }
    if (searchParams.get("cancelled") === "1") {
      window.history.replaceState({}, "", "/portal/private-lessons");
    }
  }, [searchParams]);

  const handleCancel = async (bookingId: string) => {
    if (!confirm("Are you sure you want to cancel this session?")) return;
    try {
      await portalApi.cancelPrivateBooking(bookingId);
      toast.success("Session cancelled");
      loadData();
    } catch {
      toast.error("Failed to cancel session");
    }
  };

  const now = new Date();
  const upcomingBookings = bookings.filter(
    (b) =>
      ["pending", "confirmed"].includes(b.status) &&
      b.starts_at &&
      new Date(b.starts_at) > now,
  );
  const pastBookings = bookings.filter(
    (b) =>
      !["pending", "confirmed"].includes(b.status) ||
      (b.starts_at && new Date(b.starts_at) <= now),
  );

  if (loading) {
    return (
      <div className="flex justify-center py-12">
        <Loader2 className="h-6 w-6 animate-spin text-indigo-600" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Private Lessons</h1>
        <p className="mt-1 text-sm text-gray-500">
          Book 1-on-1 sessions with our instructors
        </p>
      </div>

      {/* My Sessions — Upcoming */}
      {upcomingBookings.length > 0 && (
        <div>
          <h2 className="mb-3 text-lg font-semibold text-gray-900">Upcoming Sessions</h2>
          <div className="space-y-3">
            {upcomingBookings.map((b) => {
              const status = STATUS_CONFIG[b.status] || STATUS_CONFIG.pending;
              return (
                <Card key={b.id} className="transition-shadow hover:shadow-md">
                  <CardContent className="flex items-center justify-between p-4">
                    <div className="flex items-center gap-3">
                      {b.instructor_photo ? (
                        <img
                          src={b.instructor_photo}
                          alt={b.instructor_name || ""}
                          className="h-10 w-10 rounded-full object-cover"
                        />
                      ) : (
                        <div className="flex h-10 w-10 items-center justify-center rounded-full bg-indigo-100 text-sm font-medium text-indigo-600">
                          {(b.instructor_name || "?")[0]}
                        </div>
                      )}
                      <div className="space-y-0.5">
                        <div className="flex items-center gap-2">
                          <span className="font-medium text-gray-900">
                            {b.service_name}
                          </span>
                          <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${status.color}`}>
                            {status.label}
                          </span>
                          {b.is_virtual && (
                            <span className="flex items-center gap-1 rounded-full bg-purple-50 px-2 py-0.5 text-xs font-medium text-purple-700">
                              <Video className="h-3 w-3" /> Virtual
                            </span>
                          )}
                        </div>
                        <div className="flex items-center gap-3 text-sm text-gray-500">
                          <span className="flex items-center gap-1">
                            <User className="h-3.5 w-3.5" /> {b.instructor_name}
                          </span>
                          <span className="flex items-center gap-1">
                            <Calendar className="h-3.5 w-3.5" /> {formatDateTime(b.starts_at)}
                          </span>
                          {b.duration_minutes && (
                            <span className="flex items-center gap-1">
                              <Clock className="h-3.5 w-3.5" /> {b.duration_minutes}min
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      {b.payment_url && b.status === "pending" && (b.price_cents ?? 0) > 0 && (
                        <Button
                          size="sm"
                          onClick={() => window.location.href = b.payment_url!}
                        >
                          Pay ${((b.price_cents ?? 0) / 100).toFixed(2)}
                        </Button>
                      )}
                      {b.is_virtual && b.zoom_join_url && (
                        <Button
                          size="sm"
                          onClick={() => window.open(b.zoom_join_url!, "_blank")}
                        >
                          Join
                        </Button>
                      )}
                      {["pending", "confirmed"].includes(b.status) && (
                        <Button
                          variant="ghost"
                          size="sm"
                          className="text-red-600 hover:bg-red-50 hover:text-red-700"
                          onClick={() => handleCancel(b.id)}
                        >
                          Cancel
                        </Button>
                      )}
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        </div>
      )}

      {/* Past Sessions */}
      {pastBookings.length > 0 && (
        <div>
          <h2 className="mb-3 text-lg font-semibold text-gray-900">Past Sessions</h2>
          <div className="space-y-2">
            {pastBookings.slice(0, 10).map((b) => {
              const status = STATUS_CONFIG[b.status] || STATUS_CONFIG.completed;
              return (
                <Card key={b.id} className="opacity-70">
                  <CardContent className="flex items-center justify-between p-3">
                    <div className="flex items-center gap-3">
                      <div className="flex h-8 w-8 items-center justify-center rounded-full bg-gray-100 text-xs font-medium text-gray-500">
                        {(b.instructor_name || "?")[0]}
                      </div>
                      <div>
                        <span className="text-sm font-medium text-gray-700">
                          {b.service_name}
                        </span>
                        <span className="ml-2 text-xs text-gray-400">
                          {b.instructor_name} · {formatDateTime(b.starts_at)}
                        </span>
                      </div>
                    </div>
                    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${status.color}`}>
                      {status.label}
                    </span>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        </div>
      )}

      {/* Browse Instructors */}
      <div>
        <h2 className="mb-3 text-lg font-semibold text-gray-900">Browse Instructors</h2>
        {instructors.length === 0 ? (
          <div className="py-12 text-center">
            <User className="mx-auto h-10 w-10 text-gray-300" />
            <p className="mt-3 text-sm text-gray-500">
              No instructors offering private sessions right now
            </p>
          </div>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2">
            {instructors.map((instructor) => (
              <Card
                key={instructor.id}
                className="transition-shadow hover:shadow-md"
              >
                <CardContent className="p-4">
                  <div className="flex items-start gap-3">
                    {instructor.photo_url ? (
                      <img
                        src={instructor.photo_url}
                        alt={instructor.display_name}
                        className="h-14 w-14 rounded-full object-cover"
                      />
                    ) : (
                      <div className="flex h-14 w-14 items-center justify-center rounded-full bg-indigo-100 text-lg font-semibold text-indigo-600">
                        {instructor.display_name[0]}
                      </div>
                    )}
                    <div className="flex-1 space-y-1">
                      <h3 className="font-semibold text-gray-900">
                        {instructor.display_name}
                      </h3>
                      {instructor.specialties.length > 0 && (
                        <div className="flex flex-wrap gap-1">
                          {instructor.specialties.slice(0, 3).map((s) => (
                            <span
                              key={s}
                              className="rounded-full bg-indigo-50 px-2 py-0.5 text-xs text-indigo-600"
                            >
                              {s}
                            </span>
                          ))}
                        </div>
                      )}
                      {instructor.bio && (
                        <p className="line-clamp-2 text-sm text-gray-500">
                          {instructor.bio}
                        </p>
                      )}
                    </div>
                  </div>
                  <Button
                    className="mt-3 w-full"
                    onClick={() => setSelectedInstructor(instructor)}
                  >
                    Book Session
                  </Button>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </div>

      {/* Instructor Detail Modal */}
      {selectedInstructor && (
        <InstructorDetailModal
          instructor={selectedInstructor}
          onClose={() => setSelectedInstructor(null)}
          onBooked={() => {
            setSelectedInstructor(null);
            loadData();
          }}
        />
      )}
    </div>
  );
}

export default function PrivateLessonsPage() {
  return (
    <Suspense
      fallback={
        <div className="flex justify-center py-12">
          <Loader2 className="h-6 w-6 animate-spin text-indigo-600" />
        </div>
      }
    >
      <PrivateLessonsContent />
    </Suspense>
  );
}
