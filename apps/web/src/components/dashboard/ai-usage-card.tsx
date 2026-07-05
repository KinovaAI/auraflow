"use client";

import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Cpu, Loader2 } from "lucide-react";
import { analyticsApi, AITokenUsage } from "@/lib/analytics-api";

export function AIUsageCard() {
  const { data: usage, isLoading } = useQuery({
    queryKey: ["ai-token-usage"],
    queryFn: () =>
      analyticsApi.aiTokenUsage().then((r) => r.data.data as AITokenUsage),
    refetchInterval: 60_000,
  });

  const pct = usage
    ? Math.min(
        100,
        Math.round(
          (usage.total_tokens / Math.max(usage.free_tier_limit, 1)) * 100
        )
      )
    : 0;

  const barColor =
    pct < 70 ? "bg-emerald-500" : pct < 90 ? "bg-amber-500" : "bg-red-500";

  const fmtTokens = (n: number) =>
    n >= 1_000_000
      ? `${(n / 1_000_000).toFixed(1)}M`
      : n >= 1_000
        ? `${(n / 1_000).toFixed(1)}K`
        : `${n}`;

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-sm font-medium text-gray-500">
          AI Usage (this month)
        </CardTitle>
        <Cpu className="h-4 w-4 text-gray-400" />
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <Loader2 className="h-5 w-5 animate-spin text-gray-300" />
        ) : usage ? (
          <>
            <p className="text-2xl font-bold">
              {fmtTokens(usage.total_tokens)}
            </p>

            {/* Progress bar */}
            <div className="mt-2 h-2 w-full overflow-hidden rounded-full bg-gray-100">
              <div
                className={`h-full rounded-full transition-all ${barColor}`}
                style={{ width: `${pct}%` }}
              />
            </div>

            <div className="mt-1.5 flex items-center justify-between text-xs text-gray-400">
              <span>
                {fmtTokens(usage.free_tier_remaining)} free remaining
              </span>
              <span>{usage.estimated_cost_display}</span>
            </div>

            <p className="mt-1 text-xs text-gray-400">
              {usage.api_call_count} API calls
            </p>
          </>
        ) : (
          <p className="text-sm text-gray-400">No usage data</p>
        )}
      </CardContent>
    </Card>
  );
}
