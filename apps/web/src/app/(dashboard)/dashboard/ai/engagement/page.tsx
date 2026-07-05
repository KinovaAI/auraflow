"use client";

import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Heart,
  Mail,
  MessageSquare,
  CheckCircle2,
  AlertTriangle,
  Loader2,
  ArrowLeft,
  RefreshCw,
  ChevronDown,
  ChevronRight,
  Pause,
  Flag,
  Eye,
  Send,
  Inbox,
  Settings,
  Users,
  TrendingUp,
  Save,
} from "lucide-react";
import { apiClient } from "@/lib/api-client";
import toast from "react-hot-toast";
import Link from "next/link";

// ── Types ────────────────────────────────────────────────────────────────────

interface EngagementStats {
  active_campaigns: number;
  replies_this_month: number;
  conversions_this_month: number;
  emails_sent_this_month: number;
}

interface Campaign {
  id: string;
  member_name: string;
  member_email: string;
  engagement_type: string;
  status: string;
  outcome: string | null;
  followup_count: number;
  reply_count: number;
  initial_email_sent_at: string | null;
  last_email_sent_at: string | null;
  created_at: string | null;
}

interface Message {
  id: string;
  direction: string;
  subject: string | null;
  body: string | null;
  sent_at: string | null;
  created_at: string | null;
}

interface CampaignDetail extends Campaign {
  messages: Message[];
}

interface EngagementSettings {
  enabled: boolean;
  max_per_day: number;
  follow_up_days: number;
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function fmtDateTime(iso: string | null) {
  if (!iso) return "\u2014";
  const d = new Date(iso);
  return (
    d.toLocaleDateString([], { month: "short", day: "numeric" }) +
    " " +
    d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })
  );
}

function fmtRelative(iso: string | null) {
  if (!iso) return "\u2014";
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
}

// ── Badges ───────────────────────────────────────────────────────────────────

function TypeBadge({ type }: { type: string }) {
  const cfg: Record<string, { color: string; label: string }> = {
    new_dormant: { color: "bg-blue-100 text-blue-800", label: "New Dormant" },
    lapsing: { color: "bg-yellow-100 text-yellow-800", label: "Lapsing" },
    at_risk: { color: "bg-red-100 text-red-800", label: "At Risk" },
  };
  const { color, label } = cfg[type] || {
    color: "bg-gray-100 text-gray-600",
    label: type,
  };

  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${color}`}
    >
      {label}
    </span>
  );
}

function StatusBadge({ status }: { status: string }) {
  const cfg: Record<
    string,
    { color: string; label: string; pulse?: boolean; icon?: typeof CheckCircle2 }
  > = {
    active: {
      color: "bg-green-100 text-green-800",
      label: "Active",
      pulse: true,
    },
    replied: { color: "bg-blue-100 text-blue-800", label: "Replied" },
    converted: {
      color: "bg-green-100 text-green-800",
      label: "Converted",
      icon: CheckCircle2,
    },
    completed: { color: "bg-gray-100 text-gray-600", label: "Completed" },
    escalated: { color: "bg-red-100 text-red-800", label: "Escalated" },
  };
  const { color, label, pulse, icon: Icon } = cfg[status] || {
    color: "bg-gray-100 text-gray-600",
    label: status,
  };

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${color}`}
    >
      {pulse && (
        <span className="relative flex h-2 w-2">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-green-400 opacity-75" />
          <span className="relative inline-flex h-2 w-2 rounded-full bg-green-500" />
        </span>
      )}
      {Icon && <Icon className="h-3 w-3" />}
      {label}
    </span>
  );
}

// ── Main Page ────────────────────────────────────────────────────────────────

function RecentWinbackEmails() {
  const { data: emails, isLoading } = useQuery({
    queryKey: ["winback-emails"],
    queryFn: async () => {
      const r = await apiClient.get("/engagement/winback-log");
      const d = (r as any)?.data?.data || (r as any)?.data || [];
      return Array.isArray(d) ? d : [];
    },
    retry: 1,
  });

  if (isLoading) return <div className="flex justify-center py-4"><Loader2 className="h-5 w-5 animate-spin text-gray-400" /></div>;

  if (!emails || emails.length === 0) {
    return <p className="text-sm text-gray-400 py-4 text-center">No winback emails sent yet. The AI sends these automatically to members who haven&apos;t visited recently.</p>;
  }

  return (
    <div className="max-h-80 overflow-y-auto">
      <table className="min-w-full divide-y divide-gray-200 text-sm">
        <thead className="bg-gray-50">
          <tr>
            <th className="px-3 py-2 text-left text-xs font-medium uppercase text-gray-500">Member</th>
            <th className="px-3 py-2 text-left text-xs font-medium uppercase text-gray-500">Email</th>
            <th className="px-3 py-2 text-left text-xs font-medium uppercase text-gray-500">Subject</th>
            <th className="px-3 py-2 text-left text-xs font-medium uppercase text-gray-500">Sent</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {emails.map((e: any, i: number) => (
            <tr key={i} className="hover:bg-gray-50">
              <td className="px-3 py-2 font-medium text-gray-900">{e.member_name || "—"}</td>
              <td className="px-3 py-2 text-gray-500">{e.recipient}</td>
              <td className="px-3 py-2 text-gray-700">{e.subject}</td>
              <td className="px-3 py-2 text-gray-400 whitespace-nowrap">
                {e.created_at ? new Date(e.created_at).toLocaleString() : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function EngagementPage() {
  const queryClient = useQueryClient();
  const [expandedRow, setExpandedRow] = useState<string | null>(null);
  const [showSettings, setShowSettings] = useState(false);
  const [settingsForm, setSettingsForm] = useState<EngagementSettings | null>(
    null,
  );

  // ── Data Fetching ────────────────────────────────────────────────────────

  const statsQuery = useQuery({
    queryKey: ["engagement", "stats"],
    queryFn: () =>
      apiClient
        .get("/engagement/stats")
        .then((r) => r.data.data as EngagementStats),
  });

  const campaignsQuery = useQuery({
    queryKey: ["engagement", "campaigns"],
    queryFn: () =>
      apiClient
        .get("/engagement/campaigns?limit=50")
        .then((r) => r.data.data as Campaign[]),
  });

  const detailQuery = useQuery({
    queryKey: ["engagement", "campaign-detail", expandedRow],
    queryFn: () =>
      apiClient
        .get(`/engagement/campaigns/${expandedRow}`)
        .then((r) => r.data.data as CampaignDetail),
    enabled: !!expandedRow,
  });

  const settingsQuery = useQuery({
    queryKey: ["engagement", "settings"],
    queryFn: async () => {
      const res = await apiClient.get("/engagement/settings");
      const data = res.data.data as EngagementSettings;
      return data;
    },
  });

  // Sync settings form when data loads
  useEffect(() => {
    if (settingsQuery.data && !settingsForm) {
      setSettingsForm(settingsQuery.data);
    }
  }, [settingsQuery.data, settingsForm]);

  // ── Mutations ────────────────────────────────────────────────────────────

  const pauseMut = useMutation({
    mutationFn: (id: string) =>
      apiClient.post(`/engagement/campaigns/${id}/pause`),
    onSuccess: () => {
      toast.success("Campaign paused");
      queryClient.invalidateQueries({ queryKey: ["engagement"] });
    },
    onError: () => toast.error("Failed to pause campaign"),
  });

  const escalateMut = useMutation({
    mutationFn: (id: string) =>
      apiClient.post(`/engagement/campaigns/${id}/escalate`),
    onSuccess: () => {
      toast.success("Campaign escalated to owner");
      queryClient.invalidateQueries({ queryKey: ["engagement"] });
    },
    onError: () => toast.error("Failed to escalate campaign"),
  });

  const scanMut = useMutation({
    mutationFn: () => apiClient.post("/engagement/scan"),
    onSuccess: () => {
      toast.success("Engagement scan queued");
      queryClient.invalidateQueries({ queryKey: ["engagement"] });
    },
    onError: () => toast.error("Failed to trigger scan"),
  });

  const settingsMut = useMutation({
    mutationFn: (data: EngagementSettings) =>
      apiClient.put("/engagement/settings", data),
    onSuccess: () => {
      toast.success("Settings saved");
      queryClient.invalidateQueries({ queryKey: ["engagement", "settings"] });
    },
    onError: () => toast.error("Failed to save settings"),
  });

  const stats = statsQuery.data;
  const campaigns = campaignsQuery.data || [];

  // ── Render ───────────────────────────────────────────────────────────────

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <div className="mb-1 flex items-center gap-2">
            <Link
              href="/dashboard/ai"
              className="text-gray-400 hover:text-gray-600 transition-colors"
            >
              <ArrowLeft className="h-5 w-5" />
            </Link>
            <h1 className="text-2xl font-bold text-gray-900">
              AI Engagement Autopilot
            </h1>
          </div>
          <p className="text-gray-500 ml-7">
            Automated member outreach and re-engagement
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => scanMut.mutate()}
            disabled={scanMut.isPending}
            className="flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50 transition-colors"
          >
            {scanMut.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <RefreshCw className="h-4 w-4" />
            )}
            Run Scan Now
          </button>
        </div>
      </div>

      {/* Stats Row */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-gray-500">
                  Active Campaigns
                </p>
                <p
                  className={`mt-1 text-3xl font-bold ${stats && stats.active_campaigns > 0 ? "text-indigo-600" : "text-gray-900"}`}
                >
                  {stats?.active_campaigns ?? "\u2014"}
                </p>
              </div>
              <div
                className={`rounded-full p-3 ${stats && stats.active_campaigns > 0 ? "bg-indigo-100" : "bg-gray-100"}`}
              >
                <Users
                  className={`h-6 w-6 ${stats && stats.active_campaigns > 0 ? "text-indigo-600" : "text-gray-400"}`}
                />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-gray-500">
                  Replies Received
                </p>
                <p className="mt-1 text-3xl font-bold text-blue-600">
                  {stats?.replies_this_month ?? "\u2014"}
                </p>
              </div>
              <div className="rounded-full bg-blue-100 p-3">
                <MessageSquare className="h-6 w-6 text-blue-600" />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-gray-500">
                  Members Converted
                </p>
                <p className="mt-1 text-3xl font-bold text-green-600">
                  {stats?.conversions_this_month ?? "\u2014"}
                </p>
              </div>
              <div className="rounded-full bg-green-100 p-3">
                <TrendingUp className="h-6 w-6 text-green-600" />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-gray-500">
                  Emails Sent
                </p>
                <p className="mt-1 text-3xl font-bold text-gray-900">
                  {stats?.emails_sent_this_month ?? "\u2014"}
                </p>
              </div>
              <div className="rounded-full bg-indigo-100 p-3">
                <Mail className="h-6 w-6 text-indigo-600" />
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Recent AI Outreach Activity */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-lg">
            <Mail className="h-5 w-5 text-green-600" />
            Recent Winback Emails Sent
          </CardTitle>
        </CardHeader>
        <CardContent>
          <RecentWinbackEmails />
        </CardContent>
      </Card>

      {/* Campaigns Table */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-lg">
            <Heart className="h-5 w-5 text-indigo-600" />
            Engagement Campaigns
          </CardTitle>
        </CardHeader>
        <CardContent>
          {campaignsQuery.isLoading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="h-6 w-6 animate-spin text-gray-400" />
            </div>
          ) : campaigns.length === 0 ? (
            <div className="rounded-lg border border-dashed border-gray-300 py-12 text-center">
              <Heart className="mx-auto h-10 w-10 text-gray-300" />
              <p className="mt-3 text-sm font-medium text-gray-600">
                No engagement campaigns yet
              </p>
              <p className="mt-1 text-sm text-gray-400">
                Run a scan to detect disengaged members and start automated
                outreach.
              </p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-200 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                    <th className="w-8 pb-3" />
                    <th className="pb-3">Member</th>
                    <th className="pb-3">Type</th>
                    <th className="pb-3">Status</th>
                    <th className="pb-3 text-center">Emails</th>
                    <th className="pb-3 text-center">Replies</th>
                    <th className="pb-3">Last Activity</th>
                    <th className="pb-3 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {campaigns.map((c) => (
                    <CampaignRow
                      key={c.id}
                      campaign={c}
                      isExpanded={expandedRow === c.id}
                      onToggle={() =>
                        setExpandedRow(expandedRow === c.id ? null : c.id)
                      }
                      detail={
                        expandedRow === c.id ? detailQuery.data : undefined
                      }
                      detailLoading={
                        expandedRow === c.id && detailQuery.isLoading
                      }
                      onPause={() => pauseMut.mutate(c.id)}
                      onEscalate={() => escalateMut.mutate(c.id)}
                      pausing={pauseMut.isPending}
                      escalating={escalateMut.isPending}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Settings Section */}
      <Card>
        <CardHeader>
          <button
            onClick={() => {
              setShowSettings(!showSettings);
              if (!settingsForm && settingsQuery.data) {
                setSettingsForm(settingsQuery.data);
              }
            }}
            className="flex w-full items-center justify-between"
          >
            <CardTitle className="flex items-center gap-2 text-lg">
              <Settings className="h-5 w-5 text-indigo-600" />
              Autopilot Settings
            </CardTitle>
            {showSettings ? (
              <ChevronDown className="h-5 w-5 text-gray-400" />
            ) : (
              <ChevronRight className="h-5 w-5 text-gray-400" />
            )}
          </button>
        </CardHeader>
        {showSettings && (
          <CardContent>
            {settingsQuery.isLoading ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="h-6 w-6 animate-spin text-gray-400" />
              </div>
            ) : (
              <div className="space-y-6">
                {/* Enable/Disable Toggle */}
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium text-gray-900">
                      Enable Autopilot
                    </p>
                    <p className="text-sm text-gray-500">
                      Automatically scan for and reach out to disengaged members
                    </p>
                  </div>
                  <button
                    onClick={() =>
                      setSettingsForm((prev) =>
                        prev ? { ...prev, enabled: !prev.enabled } : prev,
                      )
                    }
                    className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                      settingsForm?.enabled ? "bg-indigo-600" : "bg-gray-200"
                    }`}
                  >
                    <span
                      className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                        settingsForm?.enabled
                          ? "translate-x-6"
                          : "translate-x-1"
                      }`}
                    />
                  </button>
                </div>

                {/* Max per day */}
                <div>
                  <label className="block text-sm font-medium text-gray-900">
                    Max campaigns per day
                  </label>
                  <p className="text-sm text-gray-500 mb-2">
                    Maximum number of new outreach campaigns to start each day
                  </p>
                  <input
                    type="number"
                    min={1}
                    max={50}
                    value={settingsForm?.max_per_day ?? 5}
                    onChange={(e) =>
                      setSettingsForm((prev) =>
                        prev
                          ? {
                              ...prev,
                              max_per_day: parseInt(e.target.value) || 1,
                            }
                          : prev,
                      )
                    }
                    className="w-24 rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                  />
                </div>

                {/* Follow-up interval */}
                <div>
                  <label className="block text-sm font-medium text-gray-900">
                    Follow-up interval (days)
                  </label>
                  <p className="text-sm text-gray-500 mb-2">
                    Number of days to wait between follow-up emails
                  </p>
                  <input
                    type="number"
                    min={1}
                    max={30}
                    value={settingsForm?.follow_up_days ?? 7}
                    onChange={(e) =>
                      setSettingsForm((prev) =>
                        prev
                          ? {
                              ...prev,
                              follow_up_days: parseInt(e.target.value) || 1,
                            }
                          : prev,
                      )
                    }
                    className="w-24 rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                  />
                </div>

                {/* Save Button */}
                <div>
                  <button
                    onClick={() => {
                      if (settingsForm) settingsMut.mutate(settingsForm);
                    }}
                    disabled={settingsMut.isPending}
                    className="flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50 transition-colors"
                  >
                    {settingsMut.isPending ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <Save className="h-4 w-4" />
                    )}
                    Save Settings
                  </button>
                </div>
              </div>
            )}
          </CardContent>
        )}
      </Card>
    </div>
  );
}

// ── Campaign Row Component ──────────────────────────────────────────────────

function CampaignRow({
  campaign,
  isExpanded,
  onToggle,
  detail,
  detailLoading,
  onPause,
  onEscalate,
  pausing,
  escalating,
}: {
  campaign: Campaign;
  isExpanded: boolean;
  onToggle: () => void;
  detail?: CampaignDetail;
  detailLoading: boolean;
  onPause: () => void;
  onEscalate: () => void;
  pausing: boolean;
  escalating: boolean;
}) {
  const canAct = campaign.status === "active" || campaign.status === "replied";

  return (
    <>
      <tr
        className="cursor-pointer hover:bg-gray-50 transition-colors"
        onClick={onToggle}
      >
        <td className="py-3">
          {isExpanded ? (
            <ChevronDown className="h-4 w-4 text-gray-400" />
          ) : (
            <ChevronRight className="h-4 w-4 text-gray-400" />
          )}
        </td>
        <td className="py-3">
          <div className="font-medium text-gray-900">
            {campaign.member_name}
          </div>
          <div className="text-xs text-gray-400">{campaign.member_email}</div>
        </td>
        <td className="py-3">
          <TypeBadge type={campaign.engagement_type} />
        </td>
        <td className="py-3">
          <StatusBadge status={campaign.status} />
        </td>
        <td className="py-3 text-center font-mono text-gray-700">
          {campaign.followup_count + 1}
        </td>
        <td className="py-3 text-center font-mono text-gray-700">
          {campaign.reply_count}
        </td>
        <td className="py-3 text-gray-500 text-sm">
          {fmtRelative(campaign.last_email_sent_at || campaign.created_at)}
        </td>
        <td className="py-3 text-right">
          <div className="flex items-center justify-end gap-1">
            {canAct && (
              <>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    onPause();
                  }}
                  disabled={pausing}
                  title="Pause"
                  className="rounded-md border border-gray-200 bg-white p-1.5 text-gray-500 hover:bg-gray-50 hover:text-gray-700 disabled:opacity-50 transition-colors"
                >
                  <Pause className="h-3.5 w-3.5" />
                </button>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    onEscalate();
                  }}
                  disabled={escalating}
                  title="Escalate"
                  className="rounded-md border border-red-200 bg-white p-1.5 text-red-500 hover:bg-red-50 hover:text-red-700 disabled:opacity-50 transition-colors"
                >
                  <Flag className="h-3.5 w-3.5" />
                </button>
              </>
            )}
            <button
              onClick={(e) => {
                e.stopPropagation();
                onToggle();
              }}
              title="View"
              className="rounded-md border border-indigo-200 bg-white p-1.5 text-indigo-500 hover:bg-indigo-50 hover:text-indigo-700 transition-colors"
            >
              <Eye className="h-3.5 w-3.5" />
            </button>
          </div>
        </td>
      </tr>

      {/* Expanded Detail: Conversation Thread */}
      {isExpanded && (
        <tr>
          <td colSpan={8} className="bg-gray-50 px-6 py-4">
            {detailLoading ? (
              <div className="flex items-center justify-center py-6">
                <Loader2 className="h-5 w-5 animate-spin text-gray-400" />
              </div>
            ) : detail ? (
              <div className="space-y-4">
                {/* Escalation Notice */}
                {detail.status === "escalated" && (
                  <div className="flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-4 py-3">
                    <AlertTriangle className="h-4 w-4 text-red-600" />
                    <span className="text-sm font-medium text-red-800">
                      This campaign has been escalated to the studio owner for
                      personal follow-up.
                    </span>
                  </div>
                )}

                {/* Message Thread */}
                {detail.messages.length === 0 ? (
                  <div className="rounded-lg border border-dashed border-gray-300 py-8 text-center">
                    <Mail className="mx-auto h-8 w-8 text-gray-300" />
                    <p className="mt-2 text-sm text-gray-500">
                      No messages yet
                    </p>
                  </div>
                ) : (
                  <div className="space-y-3">
                    <span className="text-xs font-medium uppercase tracking-wider text-gray-500">
                      Conversation Thread
                    </span>
                    {detail.messages.map((msg) => (
                      <div
                        key={msg.id}
                        className={`flex ${msg.direction === "outbound" ? "justify-end" : "justify-start"}`}
                      >
                        <div
                          className={`max-w-lg rounded-lg px-4 py-3 ${
                            msg.direction === "outbound"
                              ? "bg-indigo-600 text-white"
                              : "bg-white border border-gray-200 text-gray-900"
                          }`}
                        >
                          <div className="mb-1 flex items-center gap-2">
                            {msg.direction === "outbound" ? (
                              <Send className="h-3.5 w-3.5 opacity-70" />
                            ) : (
                              <Inbox className="h-3.5 w-3.5 text-gray-400" />
                            )}
                            <span
                              className={`text-xs font-medium ${msg.direction === "outbound" ? "text-indigo-200" : "text-gray-500"}`}
                            >
                              {msg.direction === "outbound"
                                ? "Sent"
                                : "Reply"}
                            </span>
                          </div>
                          {msg.subject && (
                            <p
                              className={`text-sm font-medium mb-1 ${msg.direction === "outbound" ? "text-white" : "text-gray-900"}`}
                            >
                              {msg.subject}
                            </p>
                          )}
                          {msg.body && (
                            <p
                              className={`text-sm whitespace-pre-wrap ${msg.direction === "outbound" ? "text-indigo-100" : "text-gray-700"}`}
                            >
                              {msg.body.length > 300
                                ? msg.body.slice(0, 300) + "..."
                                : msg.body}
                            </p>
                          )}
                          <p
                            className={`mt-2 text-xs ${msg.direction === "outbound" ? "text-indigo-300" : "text-gray-400"}`}
                          >
                            {fmtDateTime(msg.sent_at || msg.created_at)}
                          </p>
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                {/* Campaign Meta */}
                <div className="flex flex-wrap gap-4 text-xs text-gray-500 pt-2 border-t border-gray-200">
                  <span>
                    Created: {fmtDateTime(detail.created_at)}
                  </span>
                  <span>
                    First email:{" "}
                    {fmtDateTime(detail.initial_email_sent_at)}
                  </span>
                  <span>
                    Last email:{" "}
                    {fmtDateTime(detail.last_email_sent_at)}
                  </span>
                  {detail.outcome && (
                    <span>Outcome: {detail.outcome}</span>
                  )}
                </div>
              </div>
            ) : null}
          </td>
        </tr>
      )}
    </>
  );
}
