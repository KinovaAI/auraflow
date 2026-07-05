"use client";

import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import {
  Loader2,
  DollarSign,
  Users,
  UserPlus,
  TrendingUp,
  TrendingDown,
  Calendar,
  CreditCard,
  XCircle,
  Clock,
  Target,
  AlertTriangle,
  BarChart3,
  ShoppingBag,
  Sparkles,
} from "lucide-react";
import {
  BarChart,
  Bar,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Legend,
} from "recharts";
import { format } from "date-fns";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  analyticsApi,
  type StudioHealth,
  type TopCanceller,
  type TopSellingMembership,
  type RoomUtilization,
} from "@/lib/analytics-api";

const COLORS = ["#6366f1", "#8b5cf6", "#a78bfa", "#c4b5fd", "#ddd6fe"];
const PIE_COLORS = ["#22c55e", "#3b82f6", "#ef4444", "#f59e0b"];

export default function AnalyticsPage() {
  const [days, setDays] = useState(30);

  const { data: kpis, isLoading } = useQuery({
    queryKey: ["analytics-kpis", days],
    queryFn: () => analyticsApi.dashboardKPIs(days).then((r) => r.data.data),
  });

  const { data: health } = useQuery({
    queryKey: ["analytics-health", days],
    queryFn: () => analyticsApi.studioHealth(days).then((r) => r.data.data),
  });

  const { data: revenueData } = useQuery({
    queryKey: ["analytics-revenue", days],
    queryFn: () =>
      analyticsApi.revenueOverTime(days, days > 60 ? "week" : "day").then((r) => r.data.data),
  });

  const { data: attendanceData } = useQuery({
    queryKey: ["analytics-attendance", days],
    queryFn: () =>
      analyticsApi.attendanceOverTime(days, days > 60 ? "week" : "day").then((r) => r.data.data),
  });

  const { data: newMembersData } = useQuery({
    queryKey: ["analytics-new-members", days],
    queryFn: () =>
      analyticsApi.newMembersOverTime(days, days > 60 ? "week" : "day").then((r) => r.data.data),
  });

  const { data: membershipSummary } = useQuery({
    queryKey: ["analytics-memberships"],
    queryFn: () => analyticsApi.membershipSummary().then((r) => r.data.data),
  });

  const { data: membershipTypes } = useQuery({
    queryKey: ["analytics-membership-types"],
    queryFn: () => analyticsApi.membershipByType().then((r) => r.data.data),
  });

  const { data: churn } = useQuery({
    queryKey: ["analytics-churn", days],
    queryFn: () => analyticsApi.churnRate(days).then((r) => r.data.data),
  });

  const { data: topCancellers } = useQuery({
    queryKey: ["analytics-top-cancellers", days],
    queryFn: () => analyticsApi.topCancellers(days, 10).then((r) => r.data.data),
  });

  const { data: topSelling } = useQuery({
    queryKey: ["analytics-top-selling", days],
    queryFn: () => analyticsApi.topSellingMemberships(days, 10).then((r) => r.data.data),
  });

  const { data: roomUtil } = useQuery({
    queryKey: ["analytics-room-util", days],
    queryFn: () => analyticsApi.roomUtilization(days).then((r) => r.data.data),
  });

  const { data: instructors } = useQuery({
    queryKey: ["analytics-instructors", days],
    queryFn: () =>
      analyticsApi.instructorSummary(days).then((r) => r.data.data),
  });

  const fmt = (cents: number) => `$${(cents / 100).toFixed(2)}`;

  const revenueChartData = (revenueData || []).map((d) => ({
    date: d.period ? format(new Date(d.period), days > 60 ? "MMM d" : "MMM d") : "",
    revenue: d.revenue / 100,
    net: d.net_revenue / 100,
  }));

  const attendanceChartData = (attendanceData || []).map((d) => ({
    date: d.period ? format(new Date(d.period), "MMM d") : "",
    attended: d.attended,
    noShows: d.no_shows,
    cancelled: d.cancelled,
  }));

  const newMembersChartData = (newMembersData || []).map((d) => ({
    date: d.period ? format(new Date(d.period), "MMM d") : "",
    count: d.count,
  }));

  const membershipPieData = membershipSummary
    ? [
        { name: "Active", value: membershipSummary.active },
        { name: "Frozen", value: membershipSummary.frozen },
        { name: "Cancelled", value: membershipSummary.cancelled },
        { name: "Expired", value: membershipSummary.expired },
      ].filter((d) => d.value > 0)
    : [];

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="h-8 w-8 animate-spin text-indigo-600" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Analytics</h1>
          <p className="text-sm text-gray-500">
            Studio performance and health insights
          </p>
        </div>
        <div className="flex gap-2">
          {[7, 30, 90].map((d) => (
            <button
              key={d}
              onClick={() => setDays(d)}
              className={`rounded-md px-3 py-1.5 text-sm font-medium ${
                days === d
                  ? "bg-indigo-100 text-indigo-700"
                  : "text-gray-500 hover:bg-gray-100"
              }`}
            >
              {d}d
            </button>
          ))}
        </div>
      </div>

      {/* ── Primary KPI Cards ─────────────────────────────────────────── */}
      <div className="grid gap-4 grid-cols-2 lg:grid-cols-4">
        {/* Revenue */}
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-gray-500">Revenue</p>
                <p className="mt-1 text-2xl font-bold text-gray-900">
                  {fmt(kpis?.revenue ?? 0)}
                </p>
              </div>
              <div className="rounded-full bg-green-100 p-2">
                <DollarSign className="h-5 w-5 text-green-600" />
              </div>
            </div>
            {kpis?.revenue_change_percent !== undefined && (
              <div className="mt-2 flex items-center gap-1 text-xs">
                {kpis.revenue_change_percent >= 0 ? (
                  <TrendingUp className="h-3 w-3 text-green-500" />
                ) : (
                  <TrendingDown className="h-3 w-3 text-red-500" />
                )}
                <span
                  className={
                    kpis.revenue_change_percent >= 0
                      ? "text-green-600"
                      : "text-red-600"
                  }
                >
                  {kpis.revenue_change_percent > 0 ? "+" : ""}
                  {kpis.revenue_change_percent}% vs prev period
                </span>
              </div>
            )}
          </CardContent>
        </Card>

        {/* New Members */}
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-gray-500">New Members</p>
                <p className="mt-1 text-2xl font-bold text-gray-900">
                  {health?.new_members ?? 0}
                </p>
              </div>
              <div className="rounded-full bg-indigo-100 p-2">
                <UserPlus className="h-5 w-5 text-indigo-600" />
              </div>
            </div>
            <p className="mt-2 text-xs text-gray-400">
              {kpis?.active_members ?? 0} active of {kpis?.total_members ?? 0} total
            </p>
          </CardContent>
        </Card>

        {/* Booked Spots / Booking Rate */}
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-gray-500">Booked Spots</p>
                <p className="mt-1 text-2xl font-bold text-gray-900">
                  {health?.total_booked_spots ?? 0}
                </p>
              </div>
              <div className="rounded-full bg-blue-100 p-2">
                <Target className="h-5 w-5 text-blue-600" />
              </div>
            </div>
            <p className="mt-2 text-xs text-gray-400">
              {health?.booking_rate_percent ?? 0}% booking rate ({health?.total_capacity ?? 0} capacity)
            </p>
          </CardContent>
        </Card>

        {/* Cancellations */}
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-gray-500">Cancellations</p>
                <p className="mt-1 text-2xl font-bold text-gray-900">
                  {health?.cancellations ?? 0}
                </p>
              </div>
              <div className="rounded-full bg-red-100 p-2">
                <XCircle className="h-5 w-5 text-red-600" />
              </div>
            </div>
            <p className="mt-2 text-xs text-gray-400">
              {health?.late_cancellations ?? 0} late cancels, {health?.no_shows ?? 0} no-shows
            </p>
          </CardContent>
        </Card>
      </div>

      {/* ── Secondary KPI Cards ───────────────────────────────────────── */}
      <div className="grid gap-4 grid-cols-2 lg:grid-cols-4">
        {/* Attendance */}
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-gray-500">Attendance</p>
                <p className="mt-1 text-2xl font-bold text-gray-900">
                  {kpis?.attendance ?? 0}
                </p>
              </div>
              <div className="rounded-full bg-emerald-100 p-2">
                <Calendar className="h-5 w-5 text-emerald-600" />
              </div>
            </div>
            <p className="mt-2 text-xs text-gray-400">
              {health?.attendance_rate_percent ?? 0}% attendance rate
            </p>
          </CardContent>
        </Card>

        {/* Waitlisted */}
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-gray-500">Waitlisted</p>
                <p className="mt-1 text-2xl font-bold text-gray-900">
                  {health?.waitlisted ?? 0}
                </p>
              </div>
              <div className="rounded-full bg-amber-100 p-2">
                <Clock className="h-5 w-5 text-amber-600" />
              </div>
            </div>
            <p className="mt-2 text-xs text-gray-400">
              people on waitlists
            </p>
          </CardContent>
        </Card>

        {/* Active Memberships */}
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-gray-500">Active Memberships</p>
                <p className="mt-1 text-2xl font-bold text-gray-900">
                  {kpis?.active_memberships ?? 0}
                </p>
              </div>
              <div className="rounded-full bg-purple-100 p-2">
                <CreditCard className="h-5 w-5 text-purple-600" />
              </div>
            </div>
            {churn && (
              <p className="mt-2 text-xs text-gray-400">
                {churn.churn_rate_percent}% churn rate ({days}d)
              </p>
            )}
          </CardContent>
        </Card>

        {/* Avg Class Size */}
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-gray-500">Avg Class Size</p>
                <p className="mt-1 text-2xl font-bold text-gray-900">
                  {health?.avg_class_size ?? 0}
                </p>
              </div>
              <div className="rounded-full bg-sky-100 p-2">
                <Users className="h-5 w-5 text-sky-600" />
              </div>
            </div>
            <p className="mt-2 text-xs text-gray-400">
              across {health?.sessions_held ?? 0} sessions
            </p>
          </CardContent>
        </Card>
      </div>

      {/* ── Charts Row 1: Revenue + Attendance ────────────────────────── */}
      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Revenue Over Time</CardTitle>
          </CardHeader>
          <CardContent>
            {revenueChartData.length > 0 ? (
              <ResponsiveContainer width="100%" height={250}>
                <BarChart data={revenueChartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                  <XAxis dataKey="date" tick={{ fontSize: 12 }} />
                  <YAxis tick={{ fontSize: 12 }} tickFormatter={(v) => `$${v}`} />
                  <Tooltip formatter={(v: number) => [`$${v.toFixed(2)}`, ""]} />
                  <Bar dataKey="revenue" fill="#6366f1" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <p className="py-12 text-center text-sm text-gray-400">
                No revenue data yet
              </p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Attendance Over Time</CardTitle>
          </CardHeader>
          <CardContent>
            {attendanceChartData.length > 0 ? (
              <ResponsiveContainer width="100%" height={250}>
                <LineChart data={attendanceChartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                  <XAxis dataKey="date" tick={{ fontSize: 12 }} />
                  <YAxis tick={{ fontSize: 12 }} />
                  <Tooltip />
                  <Line
                    type="monotone"
                    dataKey="attended"
                    stroke="#6366f1"
                    strokeWidth={2}
                    dot={false}
                    name="Attended"
                  />
                  <Line
                    type="monotone"
                    dataKey="noShows"
                    stroke="#ef4444"
                    strokeWidth={1}
                    dot={false}
                    name="No-shows"
                  />
                  <Line
                    type="monotone"
                    dataKey="cancelled"
                    stroke="#f59e0b"
                    strokeWidth={1}
                    dot={false}
                    name="Cancelled"
                  />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <p className="py-12 text-center text-sm text-gray-400">
                No attendance data yet
              </p>
            )}
          </CardContent>
        </Card>
      </div>

      {/* ── Charts Row 2: New Members + Membership Pie ────────────────── */}
      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">New Members Over Time</CardTitle>
          </CardHeader>
          <CardContent>
            {newMembersChartData.length > 0 ? (
              <ResponsiveContainer width="100%" height={250}>
                <BarChart data={newMembersChartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                  <XAxis dataKey="date" tick={{ fontSize: 12 }} />
                  <YAxis tick={{ fontSize: 12 }} allowDecimals={false} />
                  <Tooltip />
                  <Bar dataKey="count" fill="#22c55e" radius={[4, 4, 0, 0]} name="New Members" />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <p className="py-12 text-center text-sm text-gray-400">
                No new member data yet
              </p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Membership Status</CardTitle>
          </CardHeader>
          <CardContent>
            {membershipPieData.length > 0 ? (
              <ResponsiveContainer width="100%" height={250}>
                <PieChart>
                  <Pie
                    data={membershipPieData}
                    cx="50%"
                    cy="50%"
                    innerRadius={50}
                    outerRadius={80}
                    dataKey="value"
                    label={({ name, value }) => `${name}: ${value}`}
                  >
                    {membershipPieData.map((_, idx) => (
                      <Cell key={idx} fill={PIE_COLORS[idx % PIE_COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <p className="py-12 text-center text-sm text-gray-400">
                No memberships yet
              </p>
            )}
          </CardContent>
        </Card>
      </div>

      {/* ── Data Tables Row: Top Cancellers + Top Selling + Room Util ── */}
      <div className="grid gap-6 lg:grid-cols-3">
        {/* Top Cancellers */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <AlertTriangle className="h-4 w-4 text-red-500" />
              Most Cancellations
            </CardTitle>
          </CardHeader>
          <CardContent>
            {topCancellers?.length ? (
              <div className="space-y-3">
                {topCancellers.map((m) => (
                  <div key={m.id} className="flex items-center justify-between">
                    <div>
                      <p className="text-sm font-medium text-gray-900">
                        {m.first_name} {m.last_name}
                      </p>
                      <p className="text-xs text-gray-400">
                        {m.late_cancel_count > 0 && `${m.late_cancel_count} late`}
                        {m.late_cancel_count > 0 && m.no_show_count > 0 && ", "}
                        {m.no_show_count > 0 && `${m.no_show_count} no-show`}
                      </p>
                    </div>
                    <span className="rounded-full bg-red-100 px-2.5 py-0.5 text-xs font-medium text-red-700">
                      {m.cancel_count}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="py-8 text-center text-sm text-gray-400">
                No cancellations in period
              </p>
            )}
          </CardContent>
        </Card>

        {/* Most Sold Pricing Options */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <ShoppingBag className="h-4 w-4 text-green-500" />
              Top Selling Plans
            </CardTitle>
          </CardHeader>
          <CardContent>
            {topSelling?.length ? (
              <div className="space-y-3">
                {topSelling.map((mt) => (
                  <div key={mt.id} className="flex items-center justify-between">
                    <div>
                      <p className="text-sm font-medium text-gray-900">{mt.name}</p>
                      <p className="text-xs text-gray-400">
                        {mt.type} &middot; {fmt(mt.price_cents)}
                      </p>
                    </div>
                    <div className="text-right">
                      <span className="rounded-full bg-green-100 px-2.5 py-0.5 text-xs font-medium text-green-700">
                        {mt.sold_count} sold
                      </span>
                      <p className="mt-1 text-xs text-gray-400">
                        {fmt(mt.total_revenue_cents)}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="py-8 text-center text-sm text-gray-400">
                No memberships sold in period
              </p>
            )}
          </CardContent>
        </Card>

        {/* Room Utilization */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <BarChart3 className="h-4 w-4 text-indigo-500" />
              Room Utilization
            </CardTitle>
          </CardHeader>
          <CardContent>
            {roomUtil?.length ? (
              <div className="space-y-3">
                {roomUtil.map((r) => (
                  <div key={r.room_name}>
                    <div className="flex items-center justify-between text-sm">
                      <span className="font-medium text-gray-900">{r.room_name}</span>
                      <span className="text-gray-500">{r.utilization_percent}%</span>
                    </div>
                    <div className="mt-1 h-2 rounded-full bg-gray-100">
                      <div
                        className="h-2 rounded-full bg-indigo-500"
                        style={{ width: `${Math.min(r.utilization_percent, 100)}%` }}
                      />
                    </div>
                    <p className="mt-0.5 text-xs text-gray-400">
                      {r.total_bookings} bookings / {r.total_capacity} capacity &middot; {r.sessions} sessions
                    </p>
                  </div>
                ))}
              </div>
            ) : (
              <p className="py-8 text-center text-sm text-gray-400">
                No room data yet
              </p>
            )}
          </CardContent>
        </Card>
      </div>

      {/* ── Revenue Forecast ──────────────────────────────────────────── */}
      <RevenueForecastCard />

      {/* ── Bottom Row: Memberships by Type + Instructor Activity ─────── */}
      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Memberships by Type</CardTitle>
          </CardHeader>
          <CardContent>
            {membershipTypes?.length ? (
              <div className="space-y-3">
                {membershipTypes.map((mt) => (
                  <div key={mt.name} className="flex items-center justify-between">
                    <div>
                      <p className="text-sm font-medium text-gray-900">
                        {mt.name}
                      </p>
                      <p className="text-xs text-gray-400">{mt.type} &middot; {fmt(mt.price_cents)}/mo</p>
                    </div>
                    <div className="text-right">
                      <p className="text-sm font-medium text-gray-900">
                        {mt.active_count} active
                      </p>
                      {mt.frozen_count > 0 && (
                        <p className="text-xs text-blue-500">
                          {mt.frozen_count} frozen
                        </p>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="py-8 text-center text-sm text-gray-400">
                No membership types yet
              </p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Instructor Activity</CardTitle>
          </CardHeader>
          <CardContent>
            {instructors?.length ? (
              <div className="space-y-3">
                {instructors.map((inst) => (
                  <div
                    key={inst.id}
                    className="flex items-center justify-between"
                  >
                    <div>
                      <p className="text-sm font-medium text-gray-900">
                        {inst.display_name}
                      </p>
                      <p className="text-xs text-gray-400">
                        {inst.sessions_taught} sessions, {inst.total_attended}{" "}
                        attended
                      </p>
                    </div>
                    {inst.estimated_pay_cents > 0 && (
                      <p className="text-sm font-medium text-gray-600">
                        {fmt(inst.estimated_pay_cents)}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <p className="py-8 text-center text-sm text-gray-400">
                No instructor data yet
              </p>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

// ── Revenue Forecast Card ────────────────────────────────────────────────

function RevenueForecastCard() {
  const [forecast, setForecast] = useState<{
    projections: Array<{
      period_days: number;
      amount_cents: number;
      confidence: number;
    }>;
    summary: string;
  } | null>(null);

  const forecastMutation = useMutation({
    mutationFn: () =>
      analyticsApi
        .revenueForecast(90)
        .then((r) => r.data.data),
    onSuccess: (data) => setForecast(data),
  });

  const fmt = (cents: number) => `$${(cents / 100).toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`;

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2 text-base">
            <Sparkles className="h-4 w-4 text-indigo-500" />
            AI Revenue Forecast
          </CardTitle>
          <button
            onClick={() => forecastMutation.mutate()}
            disabled={forecastMutation.isPending}
            className="flex items-center gap-2 rounded-md bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
          >
            {forecastMutation.isPending ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <TrendingUp className="h-3.5 w-3.5" />
            )}
            {forecastMutation.isPending ? "Forecasting..." : "Generate Forecast"}
          </button>
        </div>
      </CardHeader>
      <CardContent>
        {forecast ? (
          <div className="space-y-4">
            {/* Projection cards */}
            <div className="grid gap-3 sm:grid-cols-3">
              {forecast.projections.map((p) => (
                <div
                  key={p.period_days}
                  className="rounded-lg border border-gray-200 p-3"
                >
                  <p className="text-xs font-medium text-gray-500">
                    {p.period_days}-Day Projection
                  </p>
                  <p className="mt-1 text-xl font-bold text-gray-900">
                    {fmt(p.amount_cents)}
                  </p>
                  <p className="mt-0.5 text-xs text-gray-400">
                    {Math.round(p.confidence * 100)}% confidence
                  </p>
                </div>
              ))}
            </div>
            {/* AI Summary */}
            {forecast.summary && (
              <div className="whitespace-pre-wrap rounded-lg bg-gray-50 p-4 text-sm text-gray-700">
                {forecast.summary}
              </div>
            )}
          </div>
        ) : (
          <div className="flex flex-col items-center py-8 text-gray-400">
            <TrendingUp className="mb-2 h-8 w-8" />
            <p className="text-sm">
              Click &quot;Generate Forecast&quot; for AI-powered 30/60/90-day revenue projections
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
