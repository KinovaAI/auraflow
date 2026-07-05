"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Search,
  CheckCircle2,
  AlertTriangle,
  Package,
  Clock,
  ChevronDown,
  ChevronRight,
  XCircle,
  ArrowLeft,
  UserCheck,
  Phone,
  MessageSquare,
  RefreshCw,
  Loader2,
} from "lucide-react";
import { apiClient } from "@/lib/api-client";
import toast from "react-hot-toast";
import Link from "next/link";

// ── Types ────────────────────────────────────────────────────────────────────

interface SubRequest {
  id: string;
  class_title: string;
  class_time: string | null;
  original_instructor_name: string | null;
  sub_instructor_name: string | null;
  status: string;
  reason: string | null;
  attempt_count: number;
  created_at: string | null;
  resolved_at: string | null;
}

interface SubRequestDetail extends SubRequest {
  class_session_id: string;
  escalated_at: string | null;
  timeline: {
    attempt_number: number;
    instructor_id: string;
    instructor_name: string;
    status: string;
  }[];
  sms_log: {
    body: string;
    type: string;
    status: string;
    created_at: string | null;
  }[];
}

interface InventoryAlert {
  name: string;
  sku: string | null;
  quantity_on_hand: number;
  reorder_point: number;
  category: string;
}

interface ActivityEntry {
  timestamp: string | null;
  action_type: string;
  description: string;
  status: string;
}

interface Stats {
  active_searches: number;
  subs_found_this_month: number;
  escalated: number;
  inventory_alerts: number;
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function fmtDate(iso: string | null) {
  if (!iso) return "\u2014";
  return new Date(iso).toLocaleDateString([], {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function fmtTime(iso: string | null) {
  if (!iso) return "\u2014";
  return new Date(iso).toLocaleTimeString([], {
    hour: "numeric",
    minute: "2-digit",
  });
}

function fmtDateTime(iso: string | null) {
  if (!iso) return "\u2014";
  const d = new Date(iso);
  return d.toLocaleDateString([], { month: "short", day: "numeric" }) +
    " " +
    d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

function fmtRelative(iso: string | null) {
  if (!iso) return "";
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
}

// ── Status Badges ────────────────────────────────────────────────────────────

function SubStatusBadge({ status }: { status: string }) {
  const cfg: Record<string, { color: string; pulse?: boolean }> = {
    searching: { color: "bg-yellow-100 text-yellow-800", pulse: true },
    sub_found: { color: "bg-green-100 text-green-800" },
    escalated: { color: "bg-red-100 text-red-800" },
    cancelled: { color: "bg-gray-100 text-gray-600" },
  };
  const { color, pulse } = cfg[status] || { color: "bg-gray-100 text-gray-600" };

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${color}`}
    >
      {pulse && (
        <span className="relative flex h-2 w-2">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-yellow-400 opacity-75" />
          <span className="relative inline-flex h-2 w-2 rounded-full bg-yellow-500" />
        </span>
      )}
      {status === "sub_found" ? "Sub Found" : status.charAt(0).toUpperCase() + status.slice(1)}
    </span>
  );
}

function InventoryStatusBadge({ onHand, reorderPoint }: { onHand: number; reorderPoint: number }) {
  const ratio = onHand / Math.max(reorderPoint, 1);
  if (onHand === 0) {
    return (
      <span className="inline-flex items-center rounded-full bg-red-100 px-2.5 py-0.5 text-xs font-medium text-red-800">
        Out of Stock
      </span>
    );
  }
  if (ratio <= 0.5) {
    return (
      <span className="inline-flex items-center rounded-full bg-red-100 px-2.5 py-0.5 text-xs font-medium text-red-800">
        Critical
      </span>
    );
  }
  return (
    <span className="inline-flex items-center rounded-full bg-orange-100 px-2.5 py-0.5 text-xs font-medium text-orange-800">
      Low Stock
    </span>
  );
}

function ActivityIcon({ actionType }: { actionType: string }) {
  const iconMap: Record<string, { icon: typeof Search; color: string }> = {
    sub_search_started: { icon: Search, color: "text-yellow-600 bg-yellow-100" },
    sub_found: { icon: UserCheck, color: "text-green-600 bg-green-100" },
    escalated: { icon: AlertTriangle, color: "text-red-600 bg-red-100" },
    cancelled: { icon: XCircle, color: "text-gray-500 bg-gray-100" },
    sms_sent: { icon: MessageSquare, color: "text-indigo-600 bg-indigo-100" },
    resolved: { icon: CheckCircle2, color: "text-green-600 bg-green-100" },
  };
  const { icon: Icon, color } = iconMap[actionType] || { icon: Clock, color: "text-gray-500 bg-gray-100" };

  return (
    <div className={`flex h-8 w-8 items-center justify-center rounded-full ${color}`}>
      <Icon className="h-4 w-4" />
    </div>
  );
}

// ── Main Page ────────────────────────────────────────────────────────────────

export default function OfficeManagerPage() {
  const queryClient = useQueryClient();
  const [expandedRow, setExpandedRow] = useState<string | null>(null);

  // ── Data Fetching ──────────────────────────────────────────────────────────

  const statsQuery = useQuery({
    queryKey: ["office-manager", "stats"],
    queryFn: () => apiClient.get("/office-manager/stats").then((r) => r.data.data as Stats),
  });

  const subRequestsQuery = useQuery({
    queryKey: ["office-manager", "sub-requests"],
    queryFn: () =>
      apiClient.get("/office-manager/sub-requests?limit=50").then((r) => r.data.data as SubRequest[]),
  });

  const inventoryQuery = useQuery({
    queryKey: ["office-manager", "inventory-alerts"],
    queryFn: () =>
      apiClient.get("/office-manager/inventory-alerts").then((r) => r.data.data as InventoryAlert[]),
  });

  const activityQuery = useQuery({
    queryKey: ["office-manager", "activity-log"],
    queryFn: () =>
      apiClient.get("/office-manager/activity-log?limit=20").then((r) => r.data.data as ActivityEntry[]),
  });

  const detailQuery = useQuery({
    queryKey: ["office-manager", "sub-request-detail", expandedRow],
    queryFn: () =>
      apiClient
        .get(`/office-manager/sub-requests/${expandedRow}`)
        .then((r) => r.data.data as SubRequestDetail),
    enabled: !!expandedRow,
  });

  const cancelMut = useMutation({
    mutationFn: (id: string) => apiClient.post(`/office-manager/sub-requests/${id}/cancel`),
    onSuccess: () => {
      toast.success("Sub search cancelled");
      queryClient.invalidateQueries({ queryKey: ["office-manager"] });
    },
    onError: () => toast.error("Failed to cancel sub search"),
  });

  const stats = statsQuery.data;
  const subRequests = subRequestsQuery.data || [];
  const inventoryAlerts = inventoryQuery.data || [];
  const activityLog = activityQuery.data || [];

  // ── Render ─────────────────────────────────────────────────────────────────

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
            <h1 className="text-2xl font-bold text-gray-900">AI Office Manager</h1>
          </div>
          <p className="text-gray-500 ml-7">
            Automated instructor substitution and inventory monitoring
          </p>
        </div>
        <button
          onClick={() => queryClient.invalidateQueries({ queryKey: ["office-manager"] })}
          className="flex items-center gap-2 rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 transition-colors"
        >
          <RefreshCw className={`h-4 w-4 ${statsQuery.isFetching ? "animate-spin" : ""}`} />
          Refresh
        </button>
      </div>

      {/* Stats Row */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-gray-500">Active Searches</p>
                <p className={`mt-1 text-3xl font-bold ${stats && stats.active_searches > 0 ? "text-yellow-600" : "text-gray-900"}`}>
                  {stats?.active_searches ?? "\u2014"}
                </p>
              </div>
              <div className={`rounded-full p-3 ${stats && stats.active_searches > 0 ? "bg-yellow-100" : "bg-gray-100"}`}>
                <Search className={`h-6 w-6 ${stats && stats.active_searches > 0 ? "text-yellow-600" : "text-gray-400"}`} />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-gray-500">Subs Found This Month</p>
                <p className="mt-1 text-3xl font-bold text-green-600">
                  {stats?.subs_found_this_month ?? "\u2014"}
                </p>
              </div>
              <div className="rounded-full bg-green-100 p-3">
                <CheckCircle2 className="h-6 w-6 text-green-600" />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-gray-500">Escalated</p>
                <p className={`mt-1 text-3xl font-bold ${stats && stats.escalated > 0 ? "text-red-600" : "text-gray-900"}`}>
                  {stats?.escalated ?? "\u2014"}
                </p>
              </div>
              <div className={`rounded-full p-3 ${stats && stats.escalated > 0 ? "bg-red-100" : "bg-gray-100"}`}>
                <AlertTriangle className={`h-6 w-6 ${stats && stats.escalated > 0 ? "text-red-600" : "text-gray-400"}`} />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-gray-500">Low Stock Items</p>
                <p className={`mt-1 text-3xl font-bold ${stats && stats.inventory_alerts > 0 ? "text-orange-600" : "text-gray-900"}`}>
                  {stats?.inventory_alerts ?? "\u2014"}
                </p>
              </div>
              <div className={`rounded-full p-3 ${stats && stats.inventory_alerts > 0 ? "bg-orange-100" : "bg-gray-100"}`}>
                <Package className={`h-6 w-6 ${stats && stats.inventory_alerts > 0 ? "text-orange-600" : "text-gray-400"}`} />
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Substitution Requests */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-lg">
            <Phone className="h-5 w-5 text-indigo-600" />
            Substitution Requests
          </CardTitle>
        </CardHeader>
        <CardContent>
          {subRequestsQuery.isLoading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="h-6 w-6 animate-spin text-gray-400" />
            </div>
          ) : subRequests.length === 0 ? (
            <div className="rounded-lg border border-dashed border-gray-300 py-12 text-center">
              <Phone className="mx-auto h-10 w-10 text-gray-300" />
              <p className="mt-3 text-sm font-medium text-gray-600">No substitution requests yet</p>
              <p className="mt-1 text-sm text-gray-400">
                When an instructor texts in sick, the AI Office Manager will handle finding a sub.
              </p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-200 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                    <th className="w-8 pb-3" />
                    <th className="pb-3">Date</th>
                    <th className="pb-3">Class</th>
                    <th className="pb-3">Original Instructor</th>
                    <th className="pb-3">Sub Found</th>
                    <th className="pb-3">Status</th>
                    <th className="pb-3 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {subRequests.map((sr) => (
                    <SubRequestRow
                      key={sr.id}
                      sr={sr}
                      isExpanded={expandedRow === sr.id}
                      onToggle={() => setExpandedRow(expandedRow === sr.id ? null : sr.id)}
                      detail={expandedRow === sr.id ? detailQuery.data : undefined}
                      detailLoading={expandedRow === sr.id && detailQuery.isLoading}
                      onCancel={() => cancelMut.mutate(sr.id)}
                      cancelling={cancelMut.isPending}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Inventory Alerts */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-lg">
            <Package className="h-5 w-5 text-orange-600" />
            Inventory Alerts
          </CardTitle>
        </CardHeader>
        <CardContent>
          {inventoryQuery.isLoading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="h-6 w-6 animate-spin text-gray-400" />
            </div>
          ) : inventoryAlerts.length === 0 ? (
            <div className="rounded-lg border border-dashed border-gray-300 py-12 text-center">
              <CheckCircle2 className="mx-auto h-10 w-10 text-green-300" />
              <p className="mt-3 text-sm font-medium text-gray-600">All inventory levels are healthy</p>
              <p className="mt-1 text-sm text-gray-400">
                No products are currently below their reorder point.
              </p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-200 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                    <th className="pb-3">Product</th>
                    <th className="pb-3">SKU</th>
                    <th className="pb-3 text-right">In Stock</th>
                    <th className="pb-3 text-right">Reorder Point</th>
                    <th className="pb-3">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {inventoryAlerts.map((item, i) => (
                    <tr
                      key={i}
                      className={item.quantity_on_hand === 0 ? "bg-red-50" : item.quantity_on_hand <= item.reorder_point * 0.5 ? "bg-orange-50" : ""}
                    >
                      <td className="py-3 font-medium text-gray-900">{item.name}</td>
                      <td className="py-3 text-gray-500">{item.sku || "\u2014"}</td>
                      <td className="py-3 text-right font-mono font-medium text-gray-900">
                        {item.quantity_on_hand}
                      </td>
                      <td className="py-3 text-right font-mono text-gray-500">
                        {item.reorder_point}
                      </td>
                      <td className="py-3">
                        <InventoryStatusBadge
                          onHand={item.quantity_on_hand}
                          reorderPoint={item.reorder_point}
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Recent Activity */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-lg">
            <Clock className="h-5 w-5 text-indigo-600" />
            Recent Activity
          </CardTitle>
        </CardHeader>
        <CardContent>
          {activityQuery.isLoading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="h-6 w-6 animate-spin text-gray-400" />
            </div>
          ) : activityLog.length === 0 ? (
            <div className="rounded-lg border border-dashed border-gray-300 py-12 text-center">
              <Clock className="mx-auto h-10 w-10 text-gray-300" />
              <p className="mt-3 text-sm font-medium text-gray-600">No recent activity</p>
              <p className="mt-1 text-sm text-gray-400">
                AI Office Manager actions will appear here as they happen.
              </p>
            </div>
          ) : (
            <div className="space-y-1">
              {activityLog.map((entry, i) => (
                <div
                  key={i}
                  className="flex items-start gap-3 rounded-lg px-3 py-2.5 hover:bg-gray-50 transition-colors"
                >
                  <ActivityIcon actionType={entry.action_type} />
                  <div className="min-w-0 flex-1">
                    <p className="text-sm text-gray-900">{entry.description}</p>
                    <p className="text-xs text-gray-400">{fmtRelative(entry.timestamp)}</p>
                  </div>
                  {entry.timestamp && (
                    <span className="shrink-0 text-xs text-gray-400">
                      {fmtDateTime(entry.timestamp)}
                    </span>
                  )}
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

// ── Sub Request Row Component ────────────────────────────────────────────────

function SubRequestRow({
  sr,
  isExpanded,
  onToggle,
  detail,
  detailLoading,
  onCancel,
  cancelling,
}: {
  sr: SubRequest;
  isExpanded: boolean;
  onToggle: () => void;
  detail?: SubRequestDetail;
  detailLoading: boolean;
  onCancel: () => void;
  cancelling: boolean;
}) {
  return (
    <>
      <tr className="cursor-pointer hover:bg-gray-50 transition-colors" onClick={onToggle}>
        <td className="py-3">
          {isExpanded ? (
            <ChevronDown className="h-4 w-4 text-gray-400" />
          ) : (
            <ChevronRight className="h-4 w-4 text-gray-400" />
          )}
        </td>
        <td className="py-3 text-gray-500">
          <div>{fmtDate(sr.created_at)}</div>
          <div className="text-xs text-gray-400">{fmtTime(sr.class_time)}</div>
        </td>
        <td className="py-3 font-medium text-gray-900">{sr.class_title}</td>
        <td className="py-3 text-gray-700">{sr.original_instructor_name || "\u2014"}</td>
        <td className="py-3 text-gray-700">{sr.sub_instructor_name || "\u2014"}</td>
        <td className="py-3">
          <SubStatusBadge status={sr.status} />
        </td>
        <td className="py-3 text-right">
          {sr.status === "searching" && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                onCancel();
              }}
              disabled={cancelling}
              className="rounded-md border border-red-200 bg-white px-2.5 py-1 text-xs font-medium text-red-600 hover:bg-red-50 disabled:opacity-50 transition-colors"
            >
              {cancelling ? "Cancelling..." : "Cancel"}
            </button>
          )}
        </td>
      </tr>
      {isExpanded && (
        <tr>
          <td colSpan={7} className="bg-gray-50 px-6 py-4">
            {detailLoading ? (
              <div className="flex items-center justify-center py-4">
                <Loader2 className="h-5 w-5 animate-spin text-gray-400" />
              </div>
            ) : detail ? (
              <div className="space-y-4">
                {/* Reason */}
                {detail.reason && (
                  <div>
                    <span className="text-xs font-medium uppercase tracking-wider text-gray-500">
                      Reason
                    </span>
                    <p className="mt-1 text-sm text-gray-700">{detail.reason}</p>
                  </div>
                )}

                {/* Attempt Timeline */}
                {detail.timeline.length > 0 && (
                  <div>
                    <span className="text-xs font-medium uppercase tracking-wider text-gray-500">
                      Attempt Timeline
                    </span>
                    <div className="mt-2 space-y-2">
                      {detail.timeline.map((attempt) => (
                        <div
                          key={attempt.attempt_number}
                          className="flex items-center gap-3 rounded-md bg-white px-3 py-2 border border-gray-200"
                        >
                          <span className="flex h-6 w-6 items-center justify-center rounded-full bg-indigo-100 text-xs font-medium text-indigo-700">
                            {attempt.attempt_number}
                          </span>
                          <span className="text-sm font-medium text-gray-900">
                            {attempt.instructor_name}
                          </span>
                          <span className="ml-auto">
                            {attempt.status === "accepted" && (
                              <span className="inline-flex items-center gap-1 rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-800">
                                <CheckCircle2 className="h-3 w-3" />
                                Accepted
                              </span>
                            )}
                            {attempt.status === "waiting" && (
                              <span className="inline-flex items-center gap-1 rounded-full bg-yellow-100 px-2 py-0.5 text-xs font-medium text-yellow-800">
                                <Clock className="h-3 w-3" />
                                Waiting
                              </span>
                            )}
                            {attempt.status === "declined" && (
                              <span className="inline-flex items-center gap-1 rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-600">
                                <XCircle className="h-3 w-3" />
                                Declined
                              </span>
                            )}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Meta */}
                <div className="flex flex-wrap gap-4 text-xs text-gray-500">
                  <span>Attempts: {detail.attempt_count}</span>
                  {detail.escalated_at && (
                    <span>Escalated: {fmtDateTime(detail.escalated_at)}</span>
                  )}
                  {detail.resolved_at && (
                    <span>Resolved: {fmtDateTime(detail.resolved_at)}</span>
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
