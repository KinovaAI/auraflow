"use client";

import { useEffect, useState } from "react";
import { Calendar, Clock, User, Loader2, BookOpen, X, Video, ExternalLink } from "lucide-react";
import toast from "react-hot-toast";

import { portalApi } from "@/lib/portal-api";
import type { PortalBooking } from "@/lib/portal-api";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

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

const statusStyles: Record<string, string> = {
  confirmed: "bg-green-50 text-green-700",
  waitlisted: "bg-amber-50 text-amber-700",
  checked_in: "bg-blue-50 text-blue-700",
  cancelled: "bg-gray-100 text-gray-500",
  no_show: "bg-red-50 text-red-700",
};

export default function PortalBookingsPage() {
  const [bookings, setBookings] = useState<PortalBooking[]>([]);
  const [loading, setLoading] = useState(true);
  const [cancellingId, setCancellingId] = useState<string | null>(null);

  const fetchBookings = async () => {
    setLoading(true);
    try {
      const { data } = await portalApi.getBookings({ limit: 50 });
      setBookings(data);
    } catch {
      toast.error("Failed to load bookings");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchBookings();
  }, []);

  const handleCancel = async (bookingId: string) => {
    if (!confirm("Are you sure you want to cancel this booking?")) return;

    setCancellingId(bookingId);
    try {
      await portalApi.cancelBooking(bookingId);
      toast.success("Booking cancelled");
      fetchBookings();
    } catch (err: unknown) {
      const message =
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail || "Failed to cancel booking";
      toast.error(message);
    } finally {
      setCancellingId(null);
    }
  };

  const now = new Date();
  const upcoming = bookings.filter(
    (b) =>
      b.starts_at &&
      new Date(b.starts_at) >= now &&
      b.status !== "cancelled"
  );
  const past = bookings.filter(
    (b) =>
      (b.starts_at && new Date(b.starts_at) < now) ||
      b.status === "cancelled"
  );

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 className="h-6 w-6 animate-spin text-indigo-600" />
      </div>
    );
  }

  return (
    <div>
      <h1 className="mb-6 text-2xl font-bold text-gray-900">My Bookings</h1>

      {/* Upcoming */}
      <section className="mb-8">
        <h2 className="mb-3 text-lg font-semibold text-gray-800">Upcoming</h2>
        {upcoming.length === 0 ? (
          <Card>
            <CardContent className="py-8 text-center">
              <BookOpen className="mx-auto mb-2 h-8 w-8 text-gray-300" />
              <p className="text-gray-500">No upcoming bookings</p>
              <p className="mt-1 text-sm text-gray-400">
                Browse the schedule to book a class
              </p>
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-3">
            {upcoming.map((booking) => (
              <Card key={booking.id}>
                <CardContent className="flex items-center justify-between p-4">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <h3 className="font-semibold text-gray-900">
                        {booking.session_title || booking.class_type_name || "Class"}
                      </h3>
                      <span
                        className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                          statusStyles[booking.status] || "bg-gray-100 text-gray-600"
                        }`}
                      >
                        {booking.status.replace("_", " ")}
                      </span>
                      {booking.is_virtual && (
                        <span className="inline-flex items-center gap-1 rounded-full bg-purple-50 px-2 py-0.5 text-xs font-medium text-purple-700">
                          <Video className="h-3 w-3" />
                          Virtual
                        </span>
                      )}
                    </div>
                    <div className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1 text-sm text-gray-500">
                      {booking.starts_at && (
                        <>
                          <span className="flex items-center gap-1">
                            <Calendar className="h-3.5 w-3.5" />
                            {formatDate(booking.starts_at)}
                          </span>
                          <span className="flex items-center gap-1">
                            <Clock className="h-3.5 w-3.5" />
                            {formatTime(booking.starts_at)}
                            {booking.ends_at && ` - ${formatTime(booking.ends_at)}`}
                          </span>
                        </>
                      )}
                      {booking.instructor_name && (
                        <span className="flex items-center gap-1">
                          <User className="h-3.5 w-3.5" />
                          {booking.instructor_name}
                        </span>
                      )}
                    </div>
                    {booking.waitlist_position != null && (
                      <p className="mt-1 text-sm text-amber-600">
                        Waitlist position: #{booking.waitlist_position}
                      </p>
                    )}
                  </div>
                  <div className="ml-4 flex flex-col items-end gap-2">
                    {booking.is_virtual &&
                      booking.zoom_join_url &&
                      booking.status === "confirmed" &&
                      booking.starts_at &&
                      (() => {
                        const start = new Date(booking.starts_at!).getTime();
                        const end = booking.ends_at
                          ? new Date(booking.ends_at).getTime()
                          : start + 60 * 60 * 1000;
                        const now = Date.now();
                        return now >= start - 30 * 60 * 1000 && now <= end;
                      })() && (
                        <div className="flex flex-col items-end gap-1">
                          <a
                            href={booking.zoom_join_url}
                            target="_blank"
                            rel="noopener noreferrer"
                          >
                            <Button size="sm">
                              <Video className="mr-1.5 h-4 w-4" />
                              Join Class
                              <ExternalLink className="ml-1.5 h-3 w-3" />
                            </Button>
                          </a>
                          {booking.zoom_password && (
                            <span className="text-xs text-gray-400">
                              Password: {booking.zoom_password}
                            </span>
                          )}
                        </div>
                      )}
                    {(booking.status === "confirmed" || booking.status === "waitlisted") && (
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-red-600 hover:bg-red-50 hover:text-red-700"
                        onClick={() => handleCancel(booking.id)}
                        disabled={cancellingId === booking.id}
                      >
                        {cancellingId === booking.id ? (
                          <Loader2 className="h-4 w-4 animate-spin" />
                        ) : (
                          <>
                            <X className="mr-1 h-4 w-4" />
                            Cancel
                          </>
                        )}
                      </Button>
                    )}
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </section>

      {/* Past */}
      {past.length > 0 && (
        <section>
          <h2 className="mb-3 text-lg font-semibold text-gray-800">Past</h2>
          <div className="space-y-3">
            {past.map((booking) => (
              <Card key={booking.id} className="opacity-70">
                <CardContent className="flex items-center justify-between p-4">
                  <div>
                    <div className="flex items-center gap-2">
                      <h3 className="font-medium text-gray-700">
                        {booking.session_title || booking.class_type_name || "Class"}
                      </h3>
                      <span
                        className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                          statusStyles[booking.status] || "bg-gray-100 text-gray-600"
                        }`}
                      >
                        {booking.status.replace("_", " ")}
                      </span>
                    </div>
                    <div className="mt-1 flex gap-4 text-sm text-gray-400">
                      {booking.starts_at && (
                        <span>
                          {formatDate(booking.starts_at)} at {formatTime(booking.starts_at)}
                        </span>
                      )}
                      {booking.instructor_name && (
                        <span>{booking.instructor_name}</span>
                      )}
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
