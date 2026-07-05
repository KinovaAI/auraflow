"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Loader2,
  ExternalLink,
  Settings,
  Play,
  Pause,
  Power,
  PowerOff,
  RefreshCw,
  CheckCircle2,
  AlertTriangle,
  TrendingUp,
  DollarSign,
  MousePointerClick,
  Eye,
  Users,
  Target,
  Zap,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  metaAdsApi,
  type MetaAdsConfig,
} from "@/lib/meta-ads-api";
import dynamic from "next/dynamic";
import { MetaAdsConfigForm } from "./meta-ads-config-form";
// recharts is ~80 KB; only load it when the chart actually renders.
const MetaAdsPerformanceChart = dynamic(
  () =>
    import("./meta-ads-performance-chart").then(
      (m) => m.MetaAdsPerformanceChart
    ),
  { ssr: false, loading: () => null }
);
import { MetaAdsActionsFeed } from "./meta-ads-actions-feed";

// ── Status Badge ────────────────────────────────────────────────────────────

const campaignStatusColors: Record<string, string> = {
  active: "bg-green-50 text-green-700",
  paused: "bg-yellow-50 text-yellow-700",
  removed: "bg-red-50 text-red-600",
};

function CampaignStatusBadge({ status }: { status: string }) {
  return (
    <span
      className={`rounded-full px-2 py-0.5 text-xs font-medium ${
        campaignStatusColors[status] || "bg-gray-100 text-gray-500"
      }`}
    >
      {status}
    </span>
  );
}

// ── Not Connected State ─────────────────────────────────────────────────────

function NotConnectedState() {
  const connectMutation = useMutation({
    mutationFn: () => metaAdsApi.getOAuthUrl().then((r) => r.data.data.url),
    onSuccess: (url) => {
      window.location.href = url;
    },
  });

  return (
    <div className="rounded-lg border border-dashed border-gray-300 py-16 text-center">
      <Users className="mx-auto h-12 w-12 text-gray-300" />
      <h3 className="mt-4 text-lg font-medium text-gray-900">
        Connect Facebook Ads
      </h3>
      <p className="mx-auto mt-2 max-w-md text-sm text-gray-500">
        Connect your Facebook Ads account and let our AI manage your advertising
        on Facebook & Instagram. Set your budget, location, and interests — the AI
        handles campaign creation, targeting, ad copy, and optimization.
      </p>
      <Button
        className="mt-6"
        onClick={() => connectMutation.mutate()}
        disabled={connectMutation.isPending}
      >
        {connectMutation.isPending && (
          <Loader2 className="mr-1 h-4 w-4 animate-spin" />
        )}
        <ExternalLink className="mr-1 h-4 w-4" />
        Connect Facebook Ads
      </Button>
    </div>
  );
}

// ── Setup State (connected but not enabled) ─────────────────────────────────

function SetupState({
  config,
  onEnabled,
}: {
  config: MetaAdsConfig | null;
  onEnabled: () => void;
}) {
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(!config);

  const enableMutation = useMutation({
    mutationFn: () => metaAdsApi.enable().then((r) => r.data.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["meta-ads-config"] });
      onEnabled();
    },
  });

  if (showForm || !config) {
    return (
      <MetaAdsConfigForm
        config={config}
        onSaved={() => {
          setShowForm(false);
          queryClient.invalidateQueries({ queryKey: ["meta-ads-config"] });
        }}
      />
    );
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardContent className="pt-6">
          <div className="text-center">
            <Zap className="mx-auto h-10 w-10 text-indigo-500" />
            <h3 className="mt-3 text-lg font-medium text-gray-900">
              Ready to Launch
            </h3>
            <p className="mx-auto mt-2 max-w-md text-sm text-gray-500">
              Your Facebook Ads is configured. When you enable it, our AI will
              create your initial campaign structure — interest targeting, ad creatives,
              and audiences — all based on your studio&apos;s classes and location.
            </p>
            <div className="mt-4 rounded-lg bg-gray-50 p-4 text-left text-sm">
              <p className="font-medium text-gray-700">Your settings:</p>
              <ul className="mt-2 space-y-1 text-gray-600">
                <li>
                  Max monthly spend: $
                  {((config.max_monthly_spend_cents || 0) / 100).toFixed(0)}
                </li>
                <li>
                  Target radius: {config.target_radius_miles || 15} miles
                </li>
                <li>
                  Age range: {config.target_age_min || 18} - {config.target_age_max || 65}
                </li>
                <li>
                  Approval threshold: $
                  {((config.approval_threshold_cents || 0) / 100).toFixed(0)}
                </li>
              </ul>
            </div>
            <div className="mt-6 flex items-center justify-center gap-3">
              <Button variant="outline" onClick={() => setShowForm(true)}>
                <Settings className="mr-1 h-4 w-4" />
                Edit Settings
              </Button>
              <Button
                onClick={() => enableMutation.mutate()}
                disabled={enableMutation.isPending}
              >
                {enableMutation.isPending ? (
                  <Loader2 className="mr-1 h-4 w-4 animate-spin" />
                ) : (
                  <Power className="mr-1 h-4 w-4" />
                )}
                Enable AI Ads
              </Button>
            </div>
            {enableMutation.isError && (
              <p className="mt-3 text-sm text-red-600">
                Failed to enable. Please check your connection and try again.
              </p>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

// ── Active Dashboard ────────────────────────────────────────────────────────

function ActiveDashboard() {
  const queryClient = useQueryClient();
  const [view, setView] = useState<"dashboard" | "settings">("dashboard");

  const { data: summary, isLoading: summaryLoading } = useQuery({
    queryKey: ["meta-ads-summary"],
    queryFn: () =>
      metaAdsApi.getPerformanceSummary(30).then((r) => r.data.data),
  });

  const { data: campaigns } = useQuery({
    queryKey: ["meta-ads-campaigns"],
    queryFn: () => metaAdsApi.listCampaigns().then((r) => r.data.data),
  });

  const { data: dailyData } = useQuery({
    queryKey: ["meta-ads-daily"],
    queryFn: () =>
      metaAdsApi.getDailyPerformance(30).then((r) => r.data.data),
  });

  const { data: pendingActions } = useQuery({
    queryKey: ["meta-ads-pending"],
    queryFn: () => metaAdsApi.listPendingActions().then((r) => r.data.data),
    refetchInterval: 30000,
  });

  const { data: actions } = useQuery({
    queryKey: ["meta-ads-actions"],
    queryFn: () => metaAdsApi.listActions({ limit: 20 }).then((r) => r.data.data),
  });

  const { data: budget } = useQuery({
    queryKey: ["meta-ads-budget"],
    queryFn: () => metaAdsApi.getBudgetStatus().then((r) => r.data.data),
  });

  const { data: config } = useQuery({
    queryKey: ["meta-ads-config"],
    queryFn: () => metaAdsApi.getConfig().then((r) => r.data.data),
  });

  const disableMutation = useMutation({
    mutationFn: () => metaAdsApi.disable().then((r) => r.data.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["meta-ads-config"] });
      queryClient.invalidateQueries({ queryKey: ["meta-ads-campaigns"] });
    },
  });

  const optimizeMutation = useMutation({
    mutationFn: () => metaAdsApi.triggerOptimization().then((r) => r.data.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["meta-ads-actions"] });
      queryClient.invalidateQueries({ queryKey: ["meta-ads-summary"] });
    },
  });

  const pauseCampaignMutation = useMutation({
    mutationFn: (id: string) =>
      metaAdsApi.pauseCampaign(id).then((r) => r.data.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["meta-ads-campaigns"] });
    },
  });

  const enableCampaignMutation = useMutation({
    mutationFn: (id: string) =>
      metaAdsApi.enableCampaign(id).then((r) => r.data.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["meta-ads-campaigns"] });
    },
  });

  if (view === "settings") {
    return (
      <div className="space-y-4">
        <Button variant="outline" onClick={() => setView("dashboard")}>
          Back to Dashboard
        </Button>
        <MetaAdsConfigForm
          config={config ?? null}
          onSaved={() => {
            setView("dashboard");
            queryClient.invalidateQueries({ queryKey: ["meta-ads-config"] });
          }}
        />
        <Card>
          <CardContent className="pt-6">
            <h3 className="text-sm font-medium text-red-700">Danger Zone</h3>
            <p className="mt-1 text-sm text-gray-500">
              Disable AI management and pause all campaigns immediately.
            </p>
            <Button
              variant="outline"
              className="mt-3 border-red-200 text-red-600 hover:bg-red-50"
              onClick={() => disableMutation.mutate()}
              disabled={disableMutation.isPending}
            >
              {disableMutation.isPending ? (
                <Loader2 className="mr-1 h-4 w-4 animate-spin" />
              ) : (
                <PowerOff className="mr-1 h-4 w-4" />
              )}
              Disable AI Ads
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Pending Approvals Banner */}
      {pendingActions && pendingActions.length > 0 && (
        <div className="rounded-lg border border-yellow-200 bg-yellow-50 p-4">
          <div className="flex items-center gap-2">
            <AlertTriangle className="h-5 w-5 text-yellow-600" />
            <span className="font-medium text-yellow-800">
              {pendingActions.length} action{pendingActions.length > 1 ? "s" : ""}{" "}
              awaiting your approval
            </span>
          </div>
        </div>
      )}

      {/* KPI Cards */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-6">
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-gray-500">Spend</p>
                <p className="mt-1 text-2xl font-bold text-gray-900">
                  {summaryLoading ? (
                    <Loader2 className="h-5 w-5 animate-spin" />
                  ) : (
                    `$${((summary?.spend_cents ?? 0) / 100).toFixed(0)}`
                  )}
                </p>
              </div>
              <div className="rounded-full bg-red-100 p-2">
                <DollarSign className="h-5 w-5 text-red-600" />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-gray-500">Clicks</p>
                <p className="mt-1 text-2xl font-bold text-gray-900">
                  {summaryLoading ? (
                    <Loader2 className="h-5 w-5 animate-spin" />
                  ) : (
                    (summary?.clicks ?? 0).toLocaleString()
                  )}
                </p>
              </div>
              <div className="rounded-full bg-blue-100 p-2">
                <MousePointerClick className="h-5 w-5 text-blue-600" />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-gray-500">Reach</p>
                <p className="mt-1 text-2xl font-bold text-gray-900">
                  {summaryLoading ? (
                    <Loader2 className="h-5 w-5 animate-spin" />
                  ) : (
                    (summary?.reach ?? 0).toLocaleString()
                  )}
                </p>
              </div>
              <div className="rounded-full bg-purple-100 p-2">
                <Eye className="h-5 w-5 text-purple-600" />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-gray-500">Conversions</p>
                <p className="mt-1 text-2xl font-bold text-gray-900">
                  {summaryLoading ? (
                    <Loader2 className="h-5 w-5 animate-spin" />
                  ) : (
                    (summary?.conversions ?? 0).toFixed(0)
                  )}
                </p>
              </div>
              <div className="rounded-full bg-green-100 p-2">
                <CheckCircle2 className="h-5 w-5 text-green-600" />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-gray-500">ROAS</p>
                <p className="mt-1 text-2xl font-bold text-gray-900">
                  {summaryLoading ? (
                    <Loader2 className="h-5 w-5 animate-spin" />
                  ) : (
                    `${(summary?.roas ?? 0).toFixed(1)}x`
                  )}
                </p>
              </div>
              <div className="rounded-full bg-yellow-100 p-2">
                <TrendingUp className="h-5 w-5 text-yellow-600" />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-gray-500">Cost/Lead</p>
                <p className="mt-1 text-2xl font-bold text-gray-900">
                  {summaryLoading ? (
                    <Loader2 className="h-5 w-5 animate-spin" />
                  ) : (
                    `$${((summary?.cost_per_lead_cents ?? 0) / 100).toFixed(0)}`
                  )}
                </p>
              </div>
              <div className="rounded-full bg-orange-100 p-2">
                <Target className="h-5 w-5 text-orange-600" />
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Budget Bar */}
      {budget && (
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between text-sm">
              <span className="font-medium text-gray-700">Monthly Budget</span>
              <span className="text-gray-500">
                ${(budget.spent_cents / 100).toFixed(0)} / $
                {(budget.max_monthly_cents / 100).toFixed(0)}
              </span>
            </div>
            <div className="mt-2 h-2 overflow-hidden rounded-full bg-gray-200">
              <div
                className={`h-full rounded-full transition-all ${
                  budget.utilization_pct >= 95
                    ? "bg-red-500"
                    : budget.utilization_pct >= 75
                      ? "bg-yellow-500"
                      : "bg-green-500"
                }`}
                style={{ width: `${Math.min(100, budget.utilization_pct)}%` }}
              />
            </div>
            <p className="mt-1 text-xs text-gray-500">
              {budget.utilization_pct.toFixed(0)}% used &middot; $
              {(budget.remaining_cents / 100).toFixed(0)} remaining
            </p>
          </CardContent>
        </Card>
      )}

      {/* Performance Chart */}
      {dailyData && dailyData.length > 0 && (
        <MetaAdsPerformanceChart data={dailyData} />
      )}

      {/* Campaigns Table */}
      {campaigns && campaigns.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Campaigns</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="overflow-hidden rounded-lg border border-gray-200">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                      Name
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                      Status
                    </th>
                    <th className="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-gray-500">
                      Reach
                    </th>
                    <th className="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-gray-500">
                      Clicks
                    </th>
                    <th className="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-gray-500">
                      Conversions
                    </th>
                    <th className="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-gray-500">
                      Actions
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200">
                  {campaigns.map((campaign) => (
                    <tr key={campaign.id} className="hover:bg-gray-50">
                      <td className="whitespace-nowrap px-4 py-3 text-sm font-medium text-gray-900">
                        {campaign.name}
                      </td>
                      <td className="whitespace-nowrap px-4 py-3">
                        <CampaignStatusBadge status={campaign.status} />
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 text-right text-sm text-gray-500">
                        {(campaign.latest_reach ?? 0).toLocaleString()}
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 text-right text-sm text-gray-500">
                        {(campaign.latest_clicks ?? 0).toLocaleString()}
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 text-right text-sm text-gray-500">
                        {(campaign.latest_conversions ?? 0).toFixed(0)}
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 text-right">
                        {campaign.status === "active" ? (
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() =>
                              pauseCampaignMutation.mutate(
                                campaign.meta_campaign_id
                              )
                            }
                            disabled={pauseCampaignMutation.isPending}
                          >
                            <Pause className="mr-1 h-3 w-3" />
                            Pause
                          </Button>
                        ) : campaign.status === "paused" ? (
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() =>
                              enableCampaignMutation.mutate(
                                campaign.meta_campaign_id
                              )
                            }
                            disabled={enableCampaignMutation.isPending}
                          >
                            <Play className="mr-1 h-3 w-3" />
                            Enable
                          </Button>
                        ) : null}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}

      {/* AI Actions Feed */}
      {actions && actions.length > 0 && (
        <MetaAdsActionsFeed
          actions={actions}
          pendingActions={pendingActions || []}
        />
      )}

      {/* Action Buttons */}
      <div className="flex items-center justify-between border-t border-gray-200 pt-4">
        <Button
          variant="outline"
          onClick={() => optimizeMutation.mutate()}
          disabled={optimizeMutation.isPending}
        >
          {optimizeMutation.isPending ? (
            <Loader2 className="mr-1 h-4 w-4 animate-spin" />
          ) : (
            <RefreshCw className="mr-1 h-4 w-4" />
          )}
          Run Optimization
        </Button>
        <Button variant="outline" onClick={() => setView("settings")}>
          <Settings className="mr-1 h-4 w-4" />
          Settings
        </Button>
      </div>
    </div>
  );
}

// ── Main Panel ──────────────────────────────────────────────────────────────

export function MetaAdsPanel() {
  const queryClient = useQueryClient();

  const { data: connectionStatus, isLoading: statusLoading } = useQuery({
    queryKey: ["meta-ads-status"],
    queryFn: () =>
      metaAdsApi.getConnectionStatus().then((r) => r.data.data),
  });

  const { data: config, isLoading: configLoading } = useQuery({
    queryKey: ["meta-ads-config"],
    queryFn: () => metaAdsApi.getConfig().then((r) => r.data.data),
    enabled: connectionStatus?.connected === true,
  });

  if (statusLoading || configLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="h-8 w-8 animate-spin text-indigo-600" />
      </div>
    );
  }

  // Not connected
  if (!connectionStatus?.connected) {
    return <NotConnectedState />;
  }

  // Connected but not active
  if (!config?.is_active) {
    return (
      <SetupState
        config={config ?? null}
        onEnabled={() => {
          queryClient.invalidateQueries({ queryKey: ["meta-ads-config"] });
        }}
      />
    );
  }

  // Active
  return <ActiveDashboard />;
}
