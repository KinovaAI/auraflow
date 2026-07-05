"use client";

import { useEffect, useState } from "react";
import { Calendar, Clock, User, Loader2, X, Video } from "lucide-react";
import toast from "react-hot-toast";

import { portalApi } from "@/lib/portal-api";
import type { PortalSession, PortalMembership } from "@/lib/portal-api";
import { Button } from "@/components/ui/button";
import { trackConversion } from "@/lib/tracking";

interface BookClassModalProps {
  session: PortalSession;
  onClose: () => void;
  onBooked: () => void;
}

function formatTime(isoStr: string) {
  return new Date(isoStr).toLocaleTimeString("en-US", {
    hour: "numeric",
    minute: "2-digit",
  });
}

function formatDate(isoStr: string) {
  return new Date(isoStr).toLocaleDateString("en-US", {
    weekday: "long",
    month: "long",
    day: "numeric",
  });
}

export function BookClassModal({ session, onClose, onBooked }: BookClassModalProps) {
  const [memberships, setMemberships] = useState<PortalMembership[]>([]);
  const [selectedMembership, setSelectedMembership] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [booking, setBooking] = useState(false);

  useEffect(() => {
    const load = async () => {
      try {
        const { data } = await portalApi.getMemberships();
        const active = data.filter((m) => m.status === "active");
        setMemberships(active);
        if (active.length === 1) {
          setSelectedMembership(active[0].id);
        }
      } catch {
        // Non-fatal — member might not have a membership
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  const handleBook = async () => {
    setBooking(true);
    try {
      await portalApi.bookClass({
        session_id: session.id,
        membership_id: selectedMembership || undefined,
      });
      trackConversion("booking");
      onBooked();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
      const message = typeof detail === "string" ? detail
        : (detail as { message?: string })?.message || "Failed to book class";
      if (message.toLowerCase().includes("no active membership") || message.toLowerCase().includes("class pass") || message.toLowerCase().includes("please purchase")) {
        toast.error("You need a membership or class pass to book.");
        setTimeout(() => { window.location.href = "/portal/memberships"; }, 2000);
      } else {
        toast.error(message);
      }
    } finally {
      setBooking(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="w-full max-w-md rounded-lg bg-white shadow-xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b px-6 py-4">
          <h2 className="text-lg font-semibold text-gray-900">Book Class</h2>
          <button
            onClick={onClose}
            className="rounded-md p-1 text-gray-400 hover:text-gray-600"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Content */}
        <div className="px-6 py-4">
          <h3 className="text-lg font-medium text-gray-900">
            {session.title || session.class_type_name || "Class"}
          </h3>
          <div className="mt-2 space-y-1.5 text-sm text-gray-500">
            <div className="flex items-center gap-2">
              <Calendar className="h-4 w-4" />
              {formatDate(session.starts_at)}
            </div>
            <div className="flex items-center gap-2">
              <Clock className="h-4 w-4" />
              {formatTime(session.starts_at)}
              {session.ends_at && ` - ${formatTime(session.ends_at)}`}
            </div>
            {session.instructor_name && (
              <div className="flex items-center gap-2">
                <User className="h-4 w-4" />
                {session.instructor_name}
              </div>
            )}
          </div>

          {session.is_virtual && (
            <div className="mt-3 flex items-center gap-2 rounded-md bg-purple-50 px-3 py-2 text-sm text-purple-700">
              <Video className="h-4 w-4 shrink-0" />
              This is a virtual class. You&apos;ll receive a Zoom link after booking.
            </div>
          )}

          {session.is_community && (
            <div className="mt-3 flex items-center gap-2 rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-700">
              <span className="text-base">🏘️</span>
              Community class — requires a Community Class Pass or unlimited membership.
            </div>
          )}

          <div className="mt-3 text-sm">
            {session.is_full ? (
              <span className="font-medium text-amber-600">
                Class is full — you will be added to the waitlist
              </span>
            ) : (
              <span className="text-gray-500">
                {session.spots_remaining} spot{session.spots_remaining !== 1 ? "s" : ""} remaining
              </span>
            )}
          </div>

          {/* Membership Selector */}
          {loading ? (
            <div className="mt-4 flex items-center gap-2 text-sm text-gray-400">
              <Loader2 className="h-4 w-4 animate-spin" />
              Loading memberships...
            </div>
          ) : memberships.length > 1 ? (
            <div className="mt-4">
              <label className="mb-1 block text-sm font-medium text-gray-700">
                Use membership
              </label>
              <select
                value={selectedMembership}
                onChange={(e) => setSelectedMembership(e.target.value)}
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              >
                <option value="">Select a membership</option>
                {memberships.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.type_name}
                    {m.classes_remaining != null
                      ? ` (${m.classes_remaining} classes left)`
                      : ""}
                  </option>
                ))}
              </select>
            </div>
          ) : memberships.length === 1 ? (
            <div className="mt-4 rounded-md bg-gray-50 px-3 py-2 text-sm text-gray-600">
              Using: {memberships[0].type_name}
              {memberships[0].classes_remaining != null
                ? ` (${memberships[0].classes_remaining} classes left)`
                : ""}
            </div>
          ) : null}
        </div>

        {/* Footer */}
        <div className="flex justify-end gap-3 border-t px-6 py-4">
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={handleBook} disabled={booking}>
            {booking ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Booking...
              </>
            ) : session.is_full ? (
              "Join Waitlist"
            ) : (
              "Confirm Booking"
            )}
          </Button>
        </div>
      </div>
    </div>
  );
}
