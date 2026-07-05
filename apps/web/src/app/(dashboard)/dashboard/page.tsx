"use client";

import { useQuery } from "@tanstack/react-query";
import { useAuthStore } from "@/stores/auth-store";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Calendar,
  Users,
  CreditCard,
  TrendingUp,
  TrendingDown,
  Loader2,
  AlertCircle,
} from "lucide-react";
import { analyticsApi } from "@/lib/analytics-api";
import { OnboardingChecklist } from "@/components/dashboard/onboarding-checklist";
import { AIUsageCard } from "@/components/dashboard/ai-usage-card";

export default function DashboardPage() {
  const user = useAuthStore((s) => s.user);

  const orgSlug = user?.organizations?.[0]?.slug;

  const { data: kpis, isLoading, isError } = useQuery({
    queryKey: ["dashboard-kpis", orgSlug],
    queryFn: () => analyticsApi.dashboardKPIs(30).then((r) => r.data.data),
    retry: false,
  });
  // If user doesn't have analytics permission (403), just hide widgets — no error
  const showAnalytics = !isError;

  const attendanceRate =
    kpis && kpis.total_bookings > 0
      ? Math.round((kpis.attendance / kpis.total_bookings) * 100)
      : 0;

  const fmtRevenue = (cents: number) => {
    const dollars = cents / 100;
    return dollars >= 1000
      ? `$${(dollars / 1000).toFixed(1)}k`
      : `$${dollars.toFixed(0)}`;
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">
          Welcome back, {user?.first_name || "there"}
        </h1>
        <p className="text-gray-500">
          Here&apos;s what&apos;s happening at your studio
        </p>
      </div>

      <OnboardingChecklist />

      {showAnalytics && (
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-gray-500">
              Total Bookings (30d)
            </CardTitle>
            <Calendar className="h-4 w-4 text-gray-400" />
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <Loader2 className="h-5 w-5 animate-spin text-gray-300" />
            ) : (
              <p className="text-2xl font-bold">{kpis?.total_bookings ?? 0}</p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-gray-500">
              Active Members
            </CardTitle>
            <Users className="h-4 w-4 text-gray-400" />
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <Loader2 className="h-5 w-5 animate-spin text-gray-300" />
            ) : (
              <>
                <p className="text-2xl font-bold">
                  {kpis?.active_members ?? 0}
                </p>
                <p className="mt-1 text-xs text-gray-400">
                  of {kpis?.total_members ?? 0} total
                </p>
              </>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-gray-500">
              Revenue (30d)
            </CardTitle>
            <CreditCard className="h-4 w-4 text-gray-400" />
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <Loader2 className="h-5 w-5 animate-spin text-gray-300" />
            ) : (
              <>
                <p className="text-2xl font-bold">
                  {fmtRevenue(kpis?.revenue ?? 0)}
                </p>
                {kpis?.revenue_change_percent !== undefined && (
                  <div className="mt-1 flex items-center gap-1 text-xs">
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
                      {kpis.revenue_change_percent}% vs prior period
                    </span>
                  </div>
                )}
              </>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-gray-500">
              Attendance Rate
            </CardTitle>
            <TrendingUp className="h-4 w-4 text-gray-400" />
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <Loader2 className="h-5 w-5 animate-spin text-gray-300" />
            ) : (
              <>
                <p className="text-2xl font-bold">{attendanceRate}%</p>
                <p className="mt-1 text-xs text-gray-400">
                  {kpis?.attendance ?? 0} attended of{" "}
                  {kpis?.total_bookings ?? 0} bookings
                </p>
              </>
            )}
          </CardContent>
        </Card>

        <AIUsageCard />
      </div>
      )}
    </div>
  );
}
