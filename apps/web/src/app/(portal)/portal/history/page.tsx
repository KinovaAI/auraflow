"use client";

import { useEffect, useState } from "react";
import {
  Loader2, Calendar, TrendingUp, Clock, Award, Sparkles, ArrowRight,
} from "lucide-react";
import toast from "react-hot-toast";

import { portalApi } from "@/lib/portal-api";
import type { PortalProfile, PortalBooking, PortalMembership } from "@/lib/portal-api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

interface Suggestion {
  session_id: string;
  title: string;
  starts_at: string;
  instructor_name?: string;
  reason: string;
}

function formatDate(isoStr: string) {
  return new Date(isoStr).toLocaleDateString("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function formatTime(isoStr: string) {
  return new Date(isoStr).toLocaleTimeString("en-US", {
    hour: "numeric",
    minute: "2-digit",
  });
}

function formatMonthYear(isoStr: string) {
  return new Date(isoStr).toLocaleDateString("en-US", {
    month: "long",
    year: "numeric",
  });
}

function memberSinceLabel(isoStr: string) {
  const joinDate = new Date(isoStr);
  const now = new Date();
  const months = (now.getFullYear() - joinDate.getFullYear()) * 12 +
    (now.getMonth() - joinDate.getMonth());
  if (months < 1) return "Less than a month";
  if (months < 12) return `${months} month${months !== 1 ? "s" : ""}`;
  const years = Math.floor(months / 12);
  const rem = months % 12;
  if (rem === 0) return `${years} year${years !== 1 ? "s" : ""}`;
  return `${years}y ${rem}mo`;
}

function groupByMonth(bookings: PortalBooking[]): Record<string, PortalBooking[]> {
  const groups: Record<string, PortalBooking[]> = {};
  for (const b of bookings) {
    if (!b.starts_at) continue;
    const key = formatMonthYear(b.starts_at);
    if (!groups[key]) groups[key] = [];
    groups[key].push(b);
  }
  return groups;
}

export default function PortalHistoryPage() {
  const [profile, setProfile] = useState<PortalProfile | null>(null);
  const [bookings, setBookings] = useState<PortalBooking[]>([]);
  const [memberships, setMemberships] = useState<PortalMembership[]>([]);
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [loading, setLoading] = useState(true);
  const [suggestionsLoading, setSuggestionsLoading] = useState(false);

  useEffect(() => {
    const load = async () => {
      try {
        const [profileRes, bookingsRes, membershipsRes] = await Promise.all([
          portalApi.getProfile(),
          portalApi.getBookings({ upcoming_only: false, limit: 200 }),
          portalApi.getMemberships(),
        ]);
        setProfile(profileRes.data);
        setBookings(bookingsRes.data);
        setMemberships(membershipsRes.data);
      } catch {
        toast.error("Failed to load history");
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  // Load AI suggestions after main data loads
  useEffect(() => {
    if (!profile || bookings.length === 0) return;

    const loadSuggestions = async () => {
      setSuggestionsLoading(true);
      try {
        const res = await portalApi.getSuggestions();
        setSuggestions(res.data);
      } catch {
        // Non-fatal — AI might not be configured
      } finally {
        setSuggestionsLoading(false);
      }
    };
    loadSuggestions();
  }, [profile, bookings.length]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 className="h-6 w-6 animate-spin text-indigo-600" />
      </div>
    );
  }

  // Filter to past/attended bookings
  const pastBookings = bookings.filter((b) => {
    if (b.status === "attended") return true;
    if (b.status === "confirmed" && b.starts_at && new Date(b.starts_at) < new Date()) return true;
    return false;
  });

  const grouped = groupByMonth(pastBookings);
  const monthKeys = Object.keys(grouped);

  // Compute streak: consecutive weeks with at least one class
  const lastVisitDate = pastBookings.length > 0 && pastBookings[0].starts_at
    ? pastBookings[0].starts_at
    : null;

  // Find active membership name
  const activeMembership = memberships.find((m) => m.status === "active");

  return (
    <div>
      <h1 className="mb-6 text-2xl font-bold text-gray-900">My Journey</h1>

      {/* Stats Cards */}
      <div className="mb-8 grid grid-cols-2 gap-4 sm:grid-cols-4">
        <Card>
          <CardContent className="p-4 text-center">
            <Calendar className="mx-auto mb-1.5 h-5 w-5 text-indigo-500" />
            <p className="text-2xl font-bold text-gray-900">
              {profile?.total_visits || 0}
            </p>
            <p className="text-xs text-gray-500">Total Classes</p>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-4 text-center">
            <Clock className="mx-auto mb-1.5 h-5 w-5 text-indigo-500" />
            <p className="text-lg font-bold text-gray-900">
              {profile?.created_at
                ? memberSinceLabel(profile.created_at)
                : "—"}
            </p>
            <p className="text-xs text-gray-500">Member For</p>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-4 text-center">
            <TrendingUp className="mx-auto mb-1.5 h-5 w-5 text-indigo-500" />
            <p className="text-lg font-bold text-gray-900">
              {lastVisitDate ? formatDate(lastVisitDate) : "—"}
            </p>
            <p className="text-xs text-gray-500">Last Class</p>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-4 text-center">
            <Award className="mx-auto mb-1.5 h-5 w-5 text-indigo-500" />
            <p className="text-lg font-bold text-gray-900 truncate">
              {activeMembership?.type_name || "None"}
            </p>
            <p className="text-xs text-gray-500">Membership</p>
          </CardContent>
        </Card>
      </div>

      {/* AI Suggestions */}
      {(suggestionsLoading || suggestions.length > 0) && (
        <section className="mb-8">
          <h2 className="mb-3 flex items-center gap-2 text-lg font-semibold text-gray-800">
            <Sparkles className="h-5 w-5 text-amber-500" />
            Recommended for You
          </h2>
          {suggestionsLoading ? (
            <Card>
              <CardContent className="flex items-center gap-3 py-8">
                <Loader2 className="h-5 w-5 animate-spin text-indigo-500" />
                <span className="text-sm text-gray-500">
                  Finding classes you might enjoy...
                </span>
              </CardContent>
            </Card>
          ) : (
            <div className="space-y-3">
              {suggestions.map((s) => (
                <Card key={s.session_id} className="transition-shadow hover:shadow-md">
                  <CardContent className="flex items-center justify-between p-4">
                    <div className="min-w-0 flex-1">
                      <h3 className="font-semibold text-gray-900">{s.title}</h3>
                      <p className="text-sm text-gray-500">
                        {s.starts_at && formatDate(s.starts_at)}
                        {s.starts_at && ` at ${formatTime(s.starts_at)}`}
                        {s.instructor_name && ` · ${s.instructor_name}`}
                      </p>
                      <p className="mt-1 text-sm italic text-indigo-600">
                        {s.reason}
                      </p>
                    </div>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => {
                        window.location.href = `/portal?book=${s.session_id}`;
                      }}
                    >
                      Book
                      <ArrowRight className="ml-1 h-3.5 w-3.5" />
                    </Button>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </section>
      )}

      {/* Class History */}
      <section>
        <h2 className="mb-3 text-lg font-semibold text-gray-800">Class History</h2>
        {pastBookings.length === 0 ? (
          <Card>
            <CardContent className="py-8 text-center">
              <Calendar className="mx-auto mb-2 h-8 w-8 text-gray-300" />
              <p className="text-gray-500">No classes attended yet</p>
              <p className="mt-1 text-sm text-gray-400">
                Book your first class from the schedule!
              </p>
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-6">
            {monthKeys.map((month) => (
              <div key={month}>
                <h3 className="mb-2 text-sm font-medium text-gray-400 uppercase tracking-wider">
                  {month}
                  <span className="ml-2 text-xs font-normal normal-case text-gray-300">
                    ({grouped[month].length} class{grouped[month].length !== 1 ? "es" : ""})
                  </span>
                </h3>
                <Card>
                  <CardContent className="divide-y p-0">
                    {grouped[month].map((booking) => (
                      <div key={booking.id} className="flex items-center gap-4 px-4 py-3">
                        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-indigo-50 text-sm font-bold text-indigo-600">
                          {booking.starts_at
                            ? new Date(booking.starts_at).getDate()
                            : "?"}
                        </div>
                        <div className="min-w-0 flex-1">
                          <p className="font-medium text-gray-900 truncate">
                            {booking.class_type_name || booking.session_title || "Class"}
                          </p>
                          <p className="text-sm text-gray-500">
                            {booking.starts_at && formatTime(booking.starts_at)}
                            {booking.instructor_name && ` · ${booking.instructor_name}`}
                            {booking.class_category && (
                              <span className="ml-2 inline-flex rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-500">
                                {booking.class_category}
                              </span>
                            )}
                          </p>
                        </div>
                      </div>
                    ))}
                  </CardContent>
                </Card>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
