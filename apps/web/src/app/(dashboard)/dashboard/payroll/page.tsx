"use client";

import { useState, useMemo, useCallback } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Loader2,
  Download,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  ChevronDown,
  ChevronUp,
  FileText,
  Play,
  Link2,
  History,
  Settings,
  AlertCircle,
  ExternalLink,
  Trash2,
  RefreshCw,
  Clock,
  DollarSign,
  Users,
} from "lucide-react";
import toast from "react-hot-toast";
import { format } from "date-fns";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { payrollApi, type PayrollLine, type PayrollHistoryRecord } from "@/lib/payroll-api";
import {
  payrollExportApi,
  type PayrollExportStatus,
  type ExternalEmployee,
  type EmployeeMapping,
} from "@/lib/payroll-export-api";
import {
  timeClockApi,
  type PayrollRun,
  type PayrollLineItem,
} from "@/lib/time-clock-api";

// ── Helpers ────────────────────────────────────────────────────────────────────

function fmt(cents: number): string {
  return `$${(cents / 100).toFixed(2)}`;
}

function fmtHours(minutes: number): string {
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return m > 0 ? `${h}h ${m}m` : `${h}h`;
}

function getMonthStr(date: Date): string {
  return format(date, "yyyy-MM");
}

function getMonthLabel(date: Date): string {
  return format(date, "MMMM yyyy");
}

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function fmtDateTime(iso: string): string {
  return new Date(iso).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

// ── Status Badges ──────────────────────────────────────────────────────────────

const runStatusColors: Record<string, string> = {
  draft: "bg-gray-100 text-gray-700",
  compiled: "bg-blue-50 text-blue-700",
  finalized: "bg-green-50 text-green-700",
  exported: "bg-purple-50 text-purple-700",
};

function RunStatusBadge({ status }: { status: string }) {
  return (
    <span
      className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${
        runStatusColors[status] || "bg-gray-100 text-gray-500"
      }`}
    >
      {status}
    </span>
  );
}

function ConnectionBadge({ connected }: { connected: boolean }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ${
        connected
          ? "bg-green-50 text-green-700"
          : "bg-gray-100 text-gray-500"
      }`}
    >
      <span
        className={`h-2 w-2 rounded-full ${
          connected ? "bg-green-500" : "bg-gray-400"
        }`}
      />
      {connected ? "Connected" : "Not Connected"}
    </span>
  );
}

// ── Tab Config ─────────────────────────────────────────────────────────────────

const tabs = [
  { key: "report", label: "Payroll Report", icon: FileText },
  { key: "process", label: "Process Payroll", icon: Play },
  { key: "integrations", label: "Integrations", icon: Link2 },
  { key: "history", label: "Pay History", icon: History },
  { key: "settings", label: "Settings", icon: Settings },
] as const;

type TabKey = (typeof tabs)[number]["key"];

// ── Main Page ──────────────────────────────────────────────────────────────────

export default function PayrollPage() {
  const [activeTab, setActiveTab] = useState<TabKey>("report");

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Payroll</h1>
        <p className="text-sm text-gray-500">
          Compensation reports, payroll processing, integrations, and history
        </p>
      </div>

      <div className="flex gap-1 overflow-x-auto rounded-lg bg-gray-100 p-1">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`flex items-center gap-2 whitespace-nowrap rounded-md px-4 py-2 text-sm font-medium transition-colors ${
              activeTab === tab.key
                ? "bg-white text-gray-900 shadow-sm"
                : "text-gray-600 hover:text-gray-900"
            }`}
          >
            <tab.icon className="h-4 w-4" />
            {tab.label}
          </button>
        ))}
      </div>

      {activeTab === "report" && <PayrollReportTab />}
      {activeTab === "process" && <ProcessPayrollTab />}
      {activeTab === "integrations" && <IntegrationsTab />}
      {activeTab === "history" && <PayHistoryTab />}
      {activeTab === "settings" && <SettingsTab />}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// TAB 1: Payroll Report
// ═══════════════════════════════════════════════════════════════════════════════

function PayrollReportTab() {
  const queryClient = useQueryClient();

  const now = new Date();
  const [monthDate, setMonthDate] = useState(
    new Date(now.getFullYear(), now.getMonth(), 1)
  );
  const monthStr = getMonthStr(monthDate);

  const { data: report, isLoading } = useQuery({
    queryKey: ["payroll-report", monthStr],
    queryFn: () => payrollApi.getReport(monthStr).then((r) => r.data),
  });

  const markPaidMutation = useMutation({
    mutationFn: (instructorId: string) =>
      payrollApi.markPaid(instructorId, monthStr),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["payroll-report", monthStr] });
      toast.success("Marked as paid");
    },
    onError: () => toast.error("Failed to mark as paid"),
  });

  const prevMonth = () =>
    setMonthDate(new Date(monthDate.getFullYear(), monthDate.getMonth() - 1, 1));
  const nextMonth = () =>
    setMonthDate(new Date(monthDate.getFullYear(), monthDate.getMonth() + 1, 1));

  const totals = useMemo(() => {
    if (!report?.length) return null;
    return {
      group_classes: report.reduce((s, r) => s + r.group_classes_count, 0),
      private_sessions: report.reduce((s, r) => s + r.private_sessions_count, 0),
      private_revenue: report.reduce((s, r) => s + r.private_session_revenue_cents, 0),
      workshops: report.reduce((s, r) => s + r.workshops_count, 0),
      workshop_revenue: report.reduce((s, r) => s + r.workshop_revenue_cents, 0),
      group_pay: report.reduce((s, r) => s + r.group_class_pay_cents, 0),
      private_pay: report.reduce((s, r) => s + r.private_session_pay_cents, 0),
      workshop_pay: report.reduce((s, r) => s + r.workshop_pay_cents, 0),
      training_pay: report.reduce((s, r) => s + r.training_pay_cents, 0),
      total: report.reduce((s, r) => s + r.total_owed_cents, 0),
    };
  }, [report]);

  const exportCSV = () => {
    if (!report?.length) return;
    const headers = [
      "Instructor",
      "Tax Class",
      "Pay Type",
      "Pay Rate",
      "Group Classes",
      "Group Pay",
      "Private Sessions",
      "Private Revenue",
      "Private Pay",
      "Workshops",
      "Workshop Revenue",
      "Workshop Pay",
      "Training Pay",
      "Total Owed",
      "Paid",
    ];
    const rows = report.map((r) => [
      r.instructor_name,
      r.tax_classification,
      r.pay_type,
      (r.pay_rate_cents / 100).toFixed(2),
      r.group_classes_count,
      (r.group_class_pay_cents / 100).toFixed(2),
      r.private_sessions_count,
      (r.private_session_revenue_cents / 100).toFixed(2),
      (r.private_session_pay_cents / 100).toFixed(2),
      r.workshops_count,
      (r.workshop_revenue_cents / 100).toFixed(2),
      (r.workshop_pay_cents / 100).toFixed(2),
      (r.training_pay_cents / 100).toFixed(2),
      (r.total_owed_cents / 100).toFixed(2),
      r.paid_at ? "Yes" : "No",
    ]);
    const csv = [headers, ...rows].map((r) => r.join(",")).join("\n");
    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `payroll-${monthStr}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-lg font-semibold text-gray-900">
            Monthly Payroll Report
          </h2>
          <p className="text-sm text-gray-500">
            Per-instructor breakdown of compensation
          </p>
        </div>
        <Button variant="outline" onClick={exportCSV} disabled={!report?.length}>
          <Download className="mr-2 h-4 w-4" />
          Export CSV
        </Button>
      </div>

      {/* Month Selector */}
      <Card>
        <CardContent className="flex items-center justify-center gap-4 py-3">
          <Button variant="ghost" size="sm" onClick={prevMonth}>
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <span className="min-w-[160px] text-center text-lg font-semibold text-gray-900">
            {getMonthLabel(monthDate)}
          </span>
          <Button variant="ghost" size="sm" onClick={nextMonth}>
            <ChevronRight className="h-4 w-4" />
          </Button>
        </CardContent>
      </Card>

      {/* Summary Cards */}
      {totals && (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <Card>
            <CardContent className="py-3">
              <p className="text-xs text-gray-500">Total Owed</p>
              <p className="text-xl font-bold text-gray-900">{fmt(totals.total)}</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="py-3">
              <p className="text-xs text-gray-500">Group Class Pay</p>
              <p className="text-xl font-bold text-gray-900">{fmt(totals.group_pay)}</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="py-3">
              <p className="text-xs text-gray-500">Private Session Pay</p>
              <p className="text-xl font-bold text-gray-900">{fmt(totals.private_pay)}</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="py-3">
              <p className="text-xs text-gray-500">Workshop + Training Pay</p>
              <p className="text-xl font-bold text-gray-900">
                {fmt(totals.workshop_pay + totals.training_pay)}
              </p>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Report Table */}
      {isLoading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="h-8 w-8 animate-spin text-indigo-600" />
        </div>
      ) : !report?.length ? (
        <div className="rounded-lg border border-dashed border-gray-300 py-12 text-center">
          <p className="text-sm text-gray-500">
            No payroll data for {getMonthLabel(monthDate)}
          </p>
        </div>
      ) : (
        <Card>
          <CardContent className="overflow-x-auto p-0">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b bg-gray-50 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                  <th className="px-4 py-3">Instructor</th>
                  <th className="px-4 py-3 text-center">Group Classes</th>
                  <th className="px-4 py-3 text-center">Private Sessions</th>
                  <th className="px-4 py-3 text-center">Workshops</th>
                  <th className="px-4 py-3 text-right">Group Pay</th>
                  <th className="px-4 py-3 text-right">Private Pay</th>
                  <th className="px-4 py-3 text-right">Workshop Pay</th>
                  <th className="px-4 py-3 text-right">Total Owed</th>
                  <th className="px-4 py-3 text-center">Tax</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {report.map((row) => (
                  <tr key={row.instructor_id} className="hover:bg-gray-50">
                    <td className="px-4 py-3 font-medium text-gray-900">
                      {row.instructor_name}
                    </td>
                    <td className="px-4 py-3 text-center text-gray-600">
                      {row.group_classes_count}
                    </td>
                    <td className="px-4 py-3 text-center text-gray-600">
                      <div>{row.private_sessions_count}</div>
                      {row.private_session_revenue_cents > 0 && (
                        <div className="text-xs text-gray-400">
                          {fmt(row.private_session_revenue_cents)} rev
                        </div>
                      )}
                    </td>
                    <td className="px-4 py-3 text-center text-gray-600">
                      <div>{row.workshops_count}</div>
                      {row.workshop_revenue_cents > 0 && (
                        <div className="text-xs text-gray-400">
                          {fmt(row.workshop_revenue_cents)} rev
                        </div>
                      )}
                    </td>
                    <td className="px-4 py-3 text-right text-gray-600">
                      {fmt(row.group_class_pay_cents)}
                    </td>
                    <td className="px-4 py-3 text-right text-gray-600">
                      {fmt(row.private_session_pay_cents)}
                    </td>
                    <td className="px-4 py-3 text-right text-gray-600">
                      {fmt(row.workshop_pay_cents + row.training_pay_cents)}
                    </td>
                    <td className="px-4 py-3 text-right font-semibold text-gray-900">
                      {fmt(row.total_owed_cents)}
                    </td>
                    <td className="px-4 py-3 text-center">
                      <span
                        className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${
                          row.tax_classification === "W2"
                            ? "bg-blue-50 text-blue-700"
                            : "bg-amber-50 text-amber-700"
                        }`}
                      >
                        {row.tax_classification}
                      </span>
                    </td>
                  </tr>
                ))}

                {/* Totals Row */}
                {totals && (
                  <tr className="border-t-2 border-gray-200 bg-gray-50 font-semibold">
                    <td className="px-4 py-3 text-gray-900">Totals</td>
                    <td className="px-4 py-3 text-center text-gray-700">
                      {totals.group_classes}
                    </td>
                    <td className="px-4 py-3 text-center text-gray-700">
                      {totals.private_sessions}
                    </td>
                    <td className="px-4 py-3 text-center text-gray-700">
                      {totals.workshops}
                    </td>
                    <td className="px-4 py-3 text-right text-gray-700">
                      {fmt(totals.group_pay)}
                    </td>
                    <td className="px-4 py-3 text-right text-gray-700">
                      {fmt(totals.private_pay)}
                    </td>
                    <td className="px-4 py-3 text-right text-gray-700">
                      {fmt(totals.workshop_pay + totals.training_pay)}
                    </td>
                    <td className="px-4 py-3 text-right text-gray-900">
                      {fmt(totals.total)}
                    </td>
                    <td className="px-4 py-3" />
                  </tr>
                )}
              </tbody>
            </table>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// TAB 2: Process Payroll
// ═══════════════════════════════════════════════════════════════════════════════

function ProcessPayrollTab() {
  const queryClient = useQueryClient();
  const [periodStart, setPeriodStart] = useState(() => {
    const d = new Date();
    d.setDate(1);
    return format(d, "yyyy-MM-dd");
  });
  const [periodEnd, setPeriodEnd] = useState(() => {
    const d = new Date();
    return format(d, "yyyy-MM-dd");
  });
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [exportMethod, setExportMethod] = useState<"csv" | "gusto" | "quickbooks">("csv");
  const [showExportModal, setShowExportModal] = useState(false);

  // Fetch existing payroll runs
  const { data: payrollRuns, isLoading: runsLoading } = useQuery({
    queryKey: ["payroll-runs"],
    queryFn: () => timeClockApi.listPayrollRuns().then((r) => r.data.data),
  });

  // Fetch integration status for export options
  const { data: integrationStatus } = useQuery({
    queryKey: ["payroll-export-status"],
    queryFn: () => payrollExportApi.getStatus().then((r) => r.data.data),
  });

  // Fetch selected run details
  const { data: selectedRun, isLoading: runDetailLoading } = useQuery({
    queryKey: ["payroll-run", selectedRunId],
    queryFn: () =>
      selectedRunId
        ? timeClockApi.getPayrollRun(selectedRunId).then((r) => r.data.data)
        : null,
    enabled: !!selectedRunId,
  });

  // Compile payroll
  const compileMutation = useMutation({
    mutationFn: () => timeClockApi.compilePayroll(periodStart, periodEnd),
    onSuccess: (res) => {
      const run = res.data.data;
      queryClient.invalidateQueries({ queryKey: ["payroll-runs"] });
      setSelectedRunId(run.id);
      toast.success("Payroll compiled successfully");
    },
    onError: (err: any) =>
      toast.error(err?.response?.data?.detail || "Failed to compile payroll"),
  });

  // Finalize payroll
  const finalizeMutation = useMutation({
    mutationFn: (runId: string) => timeClockApi.finalizePayroll(runId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["payroll-runs"] });
      if (selectedRunId)
        queryClient.invalidateQueries({ queryKey: ["payroll-run", selectedRunId] });
      toast.success("Payroll finalized");
    },
    onError: (err: any) =>
      toast.error(err?.response?.data?.detail || "Failed to finalize"),
  });

  // Export mutations
  const gustoPushMutation = useMutation({
    mutationFn: (runId: string) => payrollExportApi.gustoPush(runId),
    onSuccess: (res) => {
      const result = res.data.data;
      queryClient.invalidateQueries({ queryKey: ["payroll-runs"] });
      toast.success(
        `Pushed to Gusto: ${result.submitted.length} submitted, ${result.skipped.length} skipped`
      );
      setShowExportModal(false);
    },
    onError: (err: any) =>
      toast.error(err?.response?.data?.detail || "Gusto push failed"),
  });

  const qbPushMutation = useMutation({
    mutationFn: (runId: string) => payrollExportApi.qbPush(runId),
    onSuccess: (res) => {
      const result = res.data.data;
      queryClient.invalidateQueries({ queryKey: ["payroll-runs"] });
      toast.success(
        `Pushed to QuickBooks: ${result.submitted.length} submitted, ${result.skipped.length} skipped`
      );
      setShowExportModal(false);
    },
    onError: (err: any) =>
      toast.error(err?.response?.data?.detail || "QuickBooks push failed"),
  });

  const handleExport = async () => {
    if (!selectedRunId) return;
    if (exportMethod === "csv") {
      try {
        const res = await payrollExportApi.downloadCsv(selectedRunId);
        const blob = new Blob([res.data], { type: "text/csv" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `payroll-${selectedRunId}.csv`;
        a.click();
        URL.revokeObjectURL(url);
        toast.success("CSV downloaded");
        setShowExportModal(false);
      } catch {
        toast.error("Failed to download CSV");
      }
    } else if (exportMethod === "gusto") {
      gustoPushMutation.mutate(selectedRunId);
    } else if (exportMethod === "quickbooks") {
      qbPushMutation.mutate(selectedRunId);
    }
  };

  /**
   * One-click Approve & Export. Don's workflow is "everyone gets paid
   * at the same time" — there's no per-instructor mark-paid flow. So
   * the button:
   *   1. Finalizes the run (backend transactionally sets paid_at on
   *      every line item too — see finalize_payroll).
   *   2. Auto-routes the export by what the studio has connected:
   *      Gusto > QuickBooks > CSV download.
   *
   * Idempotent: re-clicking on an already-finalized run skips the
   * finalize step server-side and goes straight to the export.
   */
  const approveAndExportMutation = useMutation({
    mutationFn: async (runId: string) => {
      // 1. Finalize first if not already (idempotent server-side; the
      //    backend SET paid_at WHERE paid_at IS NULL, so a re-finalize
      //    is harmless).
      const currentRun = selectedRun;
      if (currentRun && currentRun.status === "draft") {
        await timeClockApi.finalizePayroll(runId);
      }

      // 2. Pick provider by what's connected.
      const gustoConnected = integrationStatus?.gusto?.connected;
      const qbConnected = integrationStatus?.quickbooks?.connected;

      if (gustoConnected) {
        await payrollExportApi.gustoPush(runId);
        return "gusto" as const;
      }
      if (qbConnected) {
        await payrollExportApi.qbPush(runId);
        return "quickbooks" as const;
      }
      // Default: CSV
      const res = await payrollExportApi.downloadCsv(runId);
      const blob = new Blob([res.data], { type: "text/csv" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `payroll-${runId}.csv`;
      a.click();
      URL.revokeObjectURL(url);
      return "csv" as const;
    },
    onSuccess: (method) => {
      queryClient.invalidateQueries({ queryKey: ["payroll-runs"] });
      if (selectedRunId)
        queryClient.invalidateQueries({ queryKey: ["payroll-run", selectedRunId] });
      const label =
        method === "gusto" ? "pushed to Gusto"
        : method === "quickbooks" ? "pushed to QuickBooks"
        : "CSV downloaded";
      toast.success(`Approved & ${label}`);
    },
    onError: (err: any) =>
      toast.error(err?.response?.data?.detail || "Approve & Export failed"),
  });

  const isExporting =
    gustoPushMutation.isPending ||
    qbPushMutation.isPending ||
    approveAndExportMutation.isPending;

  return (
    <div className="space-y-6">
      {/* Compile New Payroll */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Compile New Payroll Run</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-col gap-4 sm:flex-row sm:items-end">
            <div className="flex-1">
              <label className="mb-1 block text-sm font-medium text-gray-700">
                Period Start
              </label>
              <Input
                type="date"
                value={periodStart}
                onChange={(e) => setPeriodStart(e.target.value)}
              />
            </div>
            <div className="flex-1">
              <label className="mb-1 block text-sm font-medium text-gray-700">
                Period End
              </label>
              <Input
                type="date"
                value={periodEnd}
                onChange={(e) => setPeriodEnd(e.target.value)}
              />
            </div>
            <Button
              onClick={() => compileMutation.mutate()}
              disabled={compileMutation.isPending || !periodStart || !periodEnd}
            >
              {compileMutation.isPending ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Play className="mr-2 h-4 w-4" />
              )}
              Compile Payroll
            </Button>
          </div>
          <p className="mt-2 text-xs text-gray-500">
            Compiles time clock hours, classes taught, private sessions, and workshops for all
            employees in the selected period.
          </p>
        </CardContent>
      </Card>

      {/* Existing Payroll Runs */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Payroll Runs</CardTitle>
        </CardHeader>
        <CardContent>
          {runsLoading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-6 w-6 animate-spin text-indigo-600" />
            </div>
          ) : !payrollRuns?.length ? (
            <p className="py-4 text-center text-sm text-gray-500">
              No payroll runs yet. Compile your first payroll above.
            </p>
          ) : (
            <div className="space-y-2">
              {payrollRuns.map((run) => (
                <button
                  key={run.id}
                  onClick={() => setSelectedRunId(run.id)}
                  className={`flex w-full items-center justify-between rounded-lg border p-3 text-left transition-colors ${
                    selectedRunId === run.id
                      ? "border-indigo-300 bg-indigo-50"
                      : "border-gray-200 hover:bg-gray-50"
                  }`}
                >
                  <div>
                    <span className="text-sm font-medium text-gray-900">
                      {fmtDate(run.period_start)} - {fmtDate(run.period_end)}
                    </span>
                    <div className="mt-0.5 flex items-center gap-3 text-xs text-gray-500">
                      <span>{fmt(run.total_gross_cents)} total</span>
                      <span>{run.total_hours.toFixed(1)}h logged</span>
                      {run.export_method && (
                        <span>Exported via {run.export_method}</span>
                      )}
                    </div>
                  </div>
                  <RunStatusBadge status={run.status} />
                </button>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Selected Run Detail */}
      {selectedRunId && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="text-base">
                Payroll Run Detail
              </CardTitle>
              <div className="flex items-center gap-2">
                {selectedRun && selectedRunId && (
                  <Button
                    size="sm"
                    onClick={() => approveAndExportMutation.mutate(selectedRunId)}
                    disabled={approveAndExportMutation.isPending}
                  >
                    {approveAndExportMutation.isPending ? (
                      <Loader2 className="mr-2 h-3 w-3 animate-spin" />
                    ) : (
                      <Download className="mr-2 h-3 w-3" />
                    )}
                    Approve & Export
                  </Button>
                )}
              </div>
            </div>
          </CardHeader>
          <CardContent>
            {runDetailLoading ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="h-6 w-6 animate-spin text-indigo-600" />
              </div>
            ) : !selectedRun ? (
              <p className="py-4 text-center text-sm text-gray-500">
                Run not found
              </p>
            ) : (
              <>
                {/* Summary */}
                <div className="mb-4 grid grid-cols-2 gap-4 sm:grid-cols-4">
                  <div>
                    <p className="text-xs text-gray-500">Period</p>
                    <p className="text-sm font-medium text-gray-900">
                      {fmtDate(selectedRun.period_start)} -{" "}
                      {fmtDate(selectedRun.period_end)}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs text-gray-500">Total Gross</p>
                    <p className="text-sm font-medium text-gray-900">
                      {fmt(selectedRun.total_gross_cents)}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs text-gray-500">Total Hours</p>
                    <p className="text-sm font-medium text-gray-900">
                      {selectedRun.total_hours.toFixed(1)}h
                    </p>
                  </div>
                  <div>
                    <p className="text-xs text-gray-500">Status</p>
                    <RunStatusBadge status={selectedRun.status} />
                  </div>
                </div>

                {/* Line Items */}
                {selectedRun.line_items && selectedRun.line_items.length > 0 ? (
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b bg-gray-50 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                          <th className="px-3 py-2">Employee</th>
                          <th className="px-3 py-2 text-right">Salary</th>
                          <th className="px-3 py-2 text-right">Hours</th>
                          <th className="px-3 py-2 text-right">Overtime</th>
                          <th className="px-3 py-2 text-center">Classes</th>
                          <th className="px-3 py-2 text-right">Hourly Pay</th>
                          <th className="px-3 py-2 text-right">OT Pay</th>
                          <th className="px-3 py-2 text-right">Class Pay</th>
                          <th className="px-3 py-2 text-center">Privates</th>
                          <th className="px-3 py-2 text-right">Private Pay</th>
                          <th className="px-3 py-2 text-center">Workshops</th>
                          <th className="px-3 py-2 text-right">Workshop Pay</th>
                          <th className="px-3 py-2 text-right">Total</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-100">
                        {selectedRun.line_items.map((item) => {
                          const privCount = item.private_sessions_count ?? 0;
                          const privPay = item.private_session_pay_cents ?? 0;
                          const wsCount = item.workshops_count ?? 0;
                          // Workshop column rolls in training pay (also a
                          // 1099-style cut, just at a different percent)
                          const wsPay =
                            (item.workshop_pay_cents ?? 0) +
                            (item.training_pay_cents ?? 0);
                          // Salary = total - everything else (no salary
                          // column on the line item; derived for display).
                          const salaryCents =
                            item.total_gross_cents -
                            item.hourly_pay_cents -
                            item.overtime_pay_cents -
                            item.class_pay_cents -
                            privPay -
                            wsPay;
                          return (
                            <tr key={item.id} className="hover:bg-gray-50">
                              <td className="px-3 py-2 font-medium text-gray-900">
                                {item.instructor_name || item.instructor_id}
                              </td>
                              <td className="px-3 py-2 text-right text-gray-600">
                                {salaryCents > 0 ? fmt(salaryCents) : "-"}
                              </td>
                              <td className="px-3 py-2 text-right text-gray-600">
                                {item.hours_worked > 0
                                  ? `${item.hours_worked.toFixed(1)}h`
                                  : "-"}
                              </td>
                              <td className="px-3 py-2 text-right text-gray-600">
                                {item.overtime_hours > 0
                                  ? `${item.overtime_hours.toFixed(1)}h`
                                  : "-"}
                              </td>
                              <td className="px-3 py-2 text-center text-gray-600">
                                {item.classes_taught || "-"}
                              </td>
                              <td className="px-3 py-2 text-right text-gray-600">
                                {item.hourly_pay_cents > 0
                                  ? fmt(item.hourly_pay_cents)
                                  : "-"}
                              </td>
                              <td className="px-3 py-2 text-right text-gray-600">
                                {item.overtime_pay_cents > 0
                                  ? fmt(item.overtime_pay_cents)
                                  : "-"}
                              </td>
                              <td className="px-3 py-2 text-right text-gray-600">
                                {item.class_pay_cents > 0
                                  ? fmt(item.class_pay_cents)
                                  : "-"}
                              </td>
                              <td className="px-3 py-2 text-center text-gray-600">
                                {privCount || "-"}
                              </td>
                              <td className="px-3 py-2 text-right text-gray-600">
                                {privPay > 0 ? fmt(privPay) : "-"}
                              </td>
                              <td className="px-3 py-2 text-center text-gray-600">
                                {wsCount || "-"}
                              </td>
                              <td className="px-3 py-2 text-right text-gray-600">
                                {wsPay > 0 ? fmt(wsPay) : "-"}
                              </td>
                              <td className="px-3 py-2 text-right font-semibold text-gray-900">
                                {fmt(item.total_gross_cents)}
                              </td>
                            </tr>
                          );
                        })}
                        {/* Totals row */}
                        <tr className="border-t-2 border-gray-200 bg-gray-50 font-semibold">
                          <td className="px-3 py-2 text-gray-900">Totals</td>
                          <td className="px-3 py-2 text-right text-gray-700">
                            {fmt(
                              selectedRun.line_items.reduce((s, i) => {
                                const wsPay =
                                  (i.workshop_pay_cents ?? 0) +
                                  (i.training_pay_cents ?? 0);
                                const salary =
                                  i.total_gross_cents -
                                  i.hourly_pay_cents -
                                  i.overtime_pay_cents -
                                  i.class_pay_cents -
                                  (i.private_session_pay_cents ?? 0) -
                                  wsPay;
                                return s + Math.max(0, salary);
                              }, 0)
                            )}
                          </td>
                          <td className="px-3 py-2 text-right text-gray-700">
                            {selectedRun.line_items
                              .reduce((s, i) => s + i.hours_worked, 0)
                              .toFixed(1)}
                            h
                          </td>
                          <td className="px-3 py-2 text-right text-gray-700">
                            {selectedRun.line_items
                              .reduce((s, i) => s + i.overtime_hours, 0)
                              .toFixed(1)}
                            h
                          </td>
                          <td className="px-3 py-2 text-center text-gray-700">
                            {selectedRun.line_items.reduce(
                              (s, i) => s + i.classes_taught,
                              0
                            )}
                          </td>
                          <td className="px-3 py-2 text-right text-gray-700">
                            {fmt(
                              selectedRun.line_items.reduce(
                                (s, i) => s + i.hourly_pay_cents,
                                0
                              )
                            )}
                          </td>
                          <td className="px-3 py-2 text-right text-gray-700">
                            {fmt(
                              selectedRun.line_items.reduce(
                                (s, i) => s + i.overtime_pay_cents,
                                0
                              )
                            )}
                          </td>
                          <td className="px-3 py-2 text-right text-gray-700">
                            {fmt(
                              selectedRun.line_items.reduce(
                                (s, i) => s + i.class_pay_cents,
                                0
                              )
                            )}
                          </td>
                          <td className="px-3 py-2 text-center text-gray-700">
                            {selectedRun.line_items.reduce(
                              (s, i) => s + (i.private_sessions_count ?? 0),
                              0
                            )}
                          </td>
                          <td className="px-3 py-2 text-right text-gray-700">
                            {fmt(
                              selectedRun.line_items.reduce(
                                (s, i) =>
                                  s + (i.private_session_pay_cents ?? 0),
                                0
                              )
                            )}
                          </td>
                          <td className="px-3 py-2 text-center text-gray-700">
                            {selectedRun.line_items.reduce(
                              (s, i) => s + (i.workshops_count ?? 0),
                              0
                            )}
                          </td>
                          <td className="px-3 py-2 text-right text-gray-700">
                            {fmt(
                              selectedRun.line_items.reduce(
                                (s, i) =>
                                  s +
                                  (i.workshop_pay_cents ?? 0) +
                                  (i.training_pay_cents ?? 0),
                                0
                              )
                            )}
                          </td>
                          <td className="px-3 py-2 text-right text-gray-900">
                            {fmt(selectedRun.total_gross_cents)}
                          </td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <p className="py-4 text-center text-sm text-gray-500">
                    No line items in this run. The payroll may still be compiling.
                  </p>
                )}
              </>
            )}
          </CardContent>
        </Card>
      )}

      {/* Export Modal */}
      {showExportModal && selectedRunId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="mx-4 w-full max-w-md rounded-lg bg-white p-6 shadow-xl">
            <h3 className="mb-4 text-lg font-semibold text-gray-900">
              Approve & Export Payroll
            </h3>
            <p className="mb-4 text-sm text-gray-600">
              Choose how to export this payroll run:
            </p>
            <div className="space-y-2">
              <label
                className={`flex cursor-pointer items-center gap-3 rounded-lg border p-3 transition-colors ${
                  exportMethod === "csv"
                    ? "border-indigo-300 bg-indigo-50"
                    : "border-gray-200 hover:bg-gray-50"
                }`}
              >
                <input
                  type="radio"
                  name="exportMethod"
                  value="csv"
                  checked={exportMethod === "csv"}
                  onChange={() => setExportMethod("csv")}
                  className="text-indigo-600"
                />
                <div>
                  <div className="text-sm font-medium text-gray-900">
                    Download CSV
                  </div>
                  <div className="text-xs text-gray-500">
                    Export as a CSV file for manual processing
                  </div>
                </div>
              </label>

              <label
                className={`flex cursor-pointer items-center gap-3 rounded-lg border p-3 transition-colors ${
                  exportMethod === "gusto"
                    ? "border-indigo-300 bg-indigo-50"
                    : "border-gray-200 hover:bg-gray-50"
                } ${!integrationStatus?.gusto?.connected ? "opacity-50" : ""}`}
              >
                <input
                  type="radio"
                  name="exportMethod"
                  value="gusto"
                  checked={exportMethod === "gusto"}
                  onChange={() => setExportMethod("gusto")}
                  disabled={!integrationStatus?.gusto?.connected}
                  className="text-indigo-600"
                />
                <div>
                  <div className="text-sm font-medium text-gray-900">
                    Push to Gusto
                  </div>
                  <div className="text-xs text-gray-500">
                    {integrationStatus?.gusto?.connected
                      ? "Send payroll directly to Gusto"
                      : "Not connected - go to Integrations tab to connect"}
                  </div>
                </div>
              </label>

              <label
                className={`flex cursor-pointer items-center gap-3 rounded-lg border p-3 transition-colors ${
                  exportMethod === "quickbooks"
                    ? "border-indigo-300 bg-indigo-50"
                    : "border-gray-200 hover:bg-gray-50"
                } ${!integrationStatus?.quickbooks?.connected ? "opacity-50" : ""}`}
              >
                <input
                  type="radio"
                  name="exportMethod"
                  value="quickbooks"
                  checked={exportMethod === "quickbooks"}
                  onChange={() => setExportMethod("quickbooks")}
                  disabled={!integrationStatus?.quickbooks?.connected}
                  className="text-indigo-600"
                />
                <div>
                  <div className="text-sm font-medium text-gray-900">
                    Push to QuickBooks
                  </div>
                  <div className="text-xs text-gray-500">
                    {integrationStatus?.quickbooks?.connected
                      ? "Send time activities to QuickBooks"
                      : "Not connected - go to Integrations tab to connect"}
                  </div>
                </div>
              </label>
            </div>

            <div className="mt-6 flex justify-end gap-3">
              <Button
                variant="outline"
                onClick={() => setShowExportModal(false)}
                disabled={isExporting}
              >
                Cancel
              </Button>
              <Button onClick={handleExport} disabled={isExporting}>
                {isExporting ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <Download className="mr-2 h-4 w-4" />
                )}
                Export
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// TAB 3: Integrations
// ═══════════════════════════════════════════════════════════════════════════════

function IntegrationsTab() {
  const queryClient = useQueryClient();
  const [mappingProvider, setMappingProvider] = useState<"gusto" | "quickbooks">(
    "gusto"
  );

  // Integration status
  const {
    data: status,
    isLoading: statusLoading,
    error: statusError,
  } = useQuery({
    queryKey: ["payroll-export-status"],
    queryFn: () => payrollExportApi.getStatus().then((r) => r.data.data),
  });

  // Employee mappings
  const { data: mappings, isLoading: mappingsLoading } = useQuery({
    queryKey: ["payroll-mappings", mappingProvider],
    queryFn: () =>
      payrollExportApi.listMappings(mappingProvider).then((r) => r.data.data),
  });

  // External employees for mapping
  const {
    data: externalEmployees,
    isLoading: extLoading,
    refetch: refetchExtEmployees,
  } = useQuery({
    queryKey: ["external-employees", mappingProvider],
    queryFn: () => {
      if (mappingProvider === "gusto")
        return payrollExportApi.gustoEmployees().then((r) => r.data.data);
      return payrollExportApi.qbEmployees().then((r) => r.data.data);
    },
    enabled:
      (mappingProvider === "gusto" && !!status?.gusto?.connected) ||
      (mappingProvider === "quickbooks" && !!status?.quickbooks?.connected),
  });

  // Payroll report for instructor list (current month)
  const currentMonth = getMonthStr(new Date());
  const { data: reportForMapping } = useQuery({
    queryKey: ["payroll-report", currentMonth],
    queryFn: () => payrollApi.getReport(currentMonth).then((r) => r.data),
  });

  // Gusto OAuth
  const gustoAuthMutation = useMutation({
    mutationFn: () => payrollExportApi.gustoAuthorize(),
    onSuccess: (res) => {
      const url = res.data.data.authorize_url;
      window.open(url, "_blank");
    },
    onError: () => toast.error("Failed to get Gusto authorization URL"),
  });

  const gustoDisconnectMutation = useMutation({
    mutationFn: () => payrollExportApi.gustoDisconnect(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["payroll-export-status"] });
      toast.success("Gusto disconnected");
    },
    onError: () => toast.error("Failed to disconnect Gusto"),
  });

  // QuickBooks OAuth
  const qbAuthMutation = useMutation({
    mutationFn: () => payrollExportApi.qbAuthorize(),
    onSuccess: (res) => {
      const url = res.data.data.authorize_url;
      window.open(url, "_blank");
    },
    onError: () => toast.error("Failed to get QuickBooks authorization URL"),
  });

  const qbDisconnectMutation = useMutation({
    mutationFn: () => payrollExportApi.qbDisconnect(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["payroll-export-status"] });
      toast.success("QuickBooks disconnected");
    },
    onError: () => toast.error("Failed to disconnect QuickBooks"),
  });

  // Create mapping
  const createMappingMutation = useMutation({
    mutationFn: (data: {
      instructor_id: string;
      external_employee_id: string;
      external_employee_name?: string;
    }) => payrollExportApi.createMapping(mappingProvider, data),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ["payroll-mappings", mappingProvider],
      });
      toast.success("Mapping saved");
    },
    onError: () => toast.error("Failed to create mapping"),
  });

  // Delete mapping
  const deleteMappingMutation = useMutation({
    mutationFn: (instructorId: string) =>
      payrollExportApi.deleteMapping(mappingProvider, instructorId),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ["payroll-mappings", mappingProvider],
      });
      toast.success("Mapping removed");
    },
    onError: () => toast.error("Failed to remove mapping"),
  });

  if (statusLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="h-8 w-8 animate-spin text-indigo-600" />
      </div>
    );
  }

  if (statusError) {
    return (
      <Card>
        <CardContent className="py-8 text-center">
          <AlertCircle className="mx-auto mb-2 h-8 w-8 text-red-400" />
          <p className="text-sm text-gray-500">
            Failed to load integration status. Please try again.
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      {/* Provider Cards */}
      <div className="grid gap-6 sm:grid-cols-2">
        {/* Gusto */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="text-base">Gusto</CardTitle>
              <ConnectionBadge connected={!!status?.gusto?.connected} />
            </div>
          </CardHeader>
          <CardContent>
            {status?.gusto?.connected ? (
              <div className="space-y-3">
                {status.gusto.connected_at && (
                  <p className="text-xs text-gray-500">
                    Connected {fmtDate(status.gusto.connected_at)}
                  </p>
                )}
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    className="text-red-600 hover:bg-red-50 hover:text-red-700"
                    onClick={() => gustoDisconnectMutation.mutate()}
                    disabled={gustoDisconnectMutation.isPending}
                  >
                    {gustoDisconnectMutation.isPending ? (
                      <Loader2 className="mr-2 h-3 w-3 animate-spin" />
                    ) : (
                      <Trash2 className="mr-2 h-3 w-3" />
                    )}
                    Disconnect
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() =>
                      queryClient.invalidateQueries({
                        queryKey: ["payroll-export-status"],
                      })
                    }
                  >
                    <RefreshCw className="mr-2 h-3 w-3" />
                    Refresh
                  </Button>
                </div>
              </div>
            ) : (
              <div className="space-y-3">
                <p className="text-sm text-gray-600">
                  Connect your Gusto account to push payroll directly.
                </p>
                <Button
                  size="sm"
                  onClick={() => gustoAuthMutation.mutate()}
                  disabled={gustoAuthMutation.isPending}
                >
                  {gustoAuthMutation.isPending ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : (
                    <ExternalLink className="mr-2 h-4 w-4" />
                  )}
                  Connect Gusto
                </Button>
              </div>
            )}
          </CardContent>
        </Card>

        {/* QuickBooks */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="text-base">QuickBooks</CardTitle>
              <ConnectionBadge connected={!!status?.quickbooks?.connected} />
            </div>
          </CardHeader>
          <CardContent>
            {status?.quickbooks?.connected ? (
              <div className="space-y-3">
                {status.quickbooks.connected_at && (
                  <p className="text-xs text-gray-500">
                    Connected {fmtDate(status.quickbooks.connected_at)}
                  </p>
                )}
                {status.quickbooks.realm_id && (
                  <p className="text-xs text-gray-500">
                    Realm ID: {status.quickbooks.realm_id}
                  </p>
                )}
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    className="text-red-600 hover:bg-red-50 hover:text-red-700"
                    onClick={() => qbDisconnectMutation.mutate()}
                    disabled={qbDisconnectMutation.isPending}
                  >
                    {qbDisconnectMutation.isPending ? (
                      <Loader2 className="mr-2 h-3 w-3 animate-spin" />
                    ) : (
                      <Trash2 className="mr-2 h-3 w-3" />
                    )}
                    Disconnect
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() =>
                      queryClient.invalidateQueries({
                        queryKey: ["payroll-export-status"],
                      })
                    }
                  >
                    <RefreshCw className="mr-2 h-3 w-3" />
                    Refresh
                  </Button>
                </div>
              </div>
            ) : (
              <div className="space-y-3">
                <p className="text-sm text-gray-600">
                  Connect your QuickBooks account to export time activities.
                </p>
                <Button
                  size="sm"
                  onClick={() => qbAuthMutation.mutate()}
                  disabled={qbAuthMutation.isPending}
                >
                  {qbAuthMutation.isPending ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : (
                    <ExternalLink className="mr-2 h-4 w-4" />
                  )}
                  Connect QuickBooks
                </Button>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Employee Mapping */}
      <Card>
        <CardHeader>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <CardTitle className="text-base">Employee Mapping</CardTitle>
            <div className="flex gap-1 rounded-lg bg-gray-100 p-1">
              {(["gusto", "quickbooks"] as const).map((provider) => (
                <button
                  key={provider}
                  onClick={() => setMappingProvider(provider)}
                  className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
                    mappingProvider === provider
                      ? "bg-white text-gray-900 shadow-sm"
                      : "text-gray-600 hover:text-gray-900"
                  }`}
                >
                  {provider === "gusto" ? "Gusto" : "QuickBooks"}
                </button>
              ))}
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {(mappingProvider === "gusto" && !status?.gusto?.connected) ||
          (mappingProvider === "quickbooks" &&
            !status?.quickbooks?.connected) ? (
            <div className="rounded-lg border border-dashed border-gray-300 py-8 text-center">
              <Link2 className="mx-auto mb-2 h-8 w-8 text-gray-400" />
              <p className="text-sm text-gray-500">
                Connect{" "}
                {mappingProvider === "gusto" ? "Gusto" : "QuickBooks"} above to
                map employees.
              </p>
            </div>
          ) : mappingsLoading || extLoading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-6 w-6 animate-spin text-indigo-600" />
            </div>
          ) : (
            <div className="space-y-4">
              <p className="text-xs text-gray-500">
                Map your AuraFlow instructors/staff to their corresponding{" "}
                {mappingProvider === "gusto" ? "Gusto" : "QuickBooks"} employee
                records so payroll pushes correctly.
              </p>

              {/* Existing mappings */}
              {mappings && mappings.length > 0 && (
                <div className="space-y-2">
                  <h4 className="text-xs font-medium uppercase tracking-wider text-gray-500">
                    Current Mappings
                  </h4>
                  {mappings.map((m) => (
                    <div
                      key={m.id}
                      className="flex items-center justify-between rounded-lg border border-gray-200 p-3"
                    >
                      <div>
                        <span className="text-sm font-medium text-gray-900">
                          {m.instructor_name || m.instructor_id}
                        </span>
                        <span className="mx-2 text-gray-400">&rarr;</span>
                        <span className="text-sm text-gray-600">
                          {m.external_employee_name || m.external_employee_id}
                        </span>
                      </div>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-7 text-red-500 hover:bg-red-50 hover:text-red-700"
                        onClick={() =>
                          deleteMappingMutation.mutate(m.instructor_id)
                        }
                        disabled={deleteMappingMutation.isPending}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  ))}
                </div>
              )}

              {/* Add new mapping */}
              {reportForMapping && externalEmployees && (
                <MappingForm
                  instructors={reportForMapping}
                  externalEmployees={externalEmployees}
                  existingMappings={mappings || []}
                  onSave={(instructorId, extId, extName) =>
                    createMappingMutation.mutate({
                      instructor_id: instructorId,
                      external_employee_id: extId,
                      external_employee_name: extName,
                    })
                  }
                  isSaving={createMappingMutation.isPending}
                />
              )}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

// ── Mapping Form ───────────────────────────────────────────────────────────────

function MappingForm({
  instructors,
  externalEmployees,
  existingMappings,
  onSave,
  isSaving,
}: {
  instructors: PayrollLine[];
  externalEmployees: ExternalEmployee[];
  existingMappings: EmployeeMapping[];
  onSave: (instructorId: string, extId: string, extName?: string) => void;
  isSaving: boolean;
}) {
  const [selectedInstructor, setSelectedInstructor] = useState("");
  const [selectedExternal, setSelectedExternal] = useState("");

  const mappedInstructorIds = new Set(existingMappings.map((m) => m.instructor_id));
  const unmappedInstructors = instructors.filter(
    (i) => !mappedInstructorIds.has(i.instructor_id)
  );

  const handleSave = () => {
    if (!selectedInstructor || !selectedExternal) return;
    const ext = externalEmployees.find((e) => e.id === selectedExternal);
    onSave(
      selectedInstructor,
      selectedExternal,
      ext ? `${ext.first_name} ${ext.last_name}` : undefined
    );
    setSelectedInstructor("");
    setSelectedExternal("");
  };

  if (unmappedInstructors.length === 0) {
    return (
      <p className="text-xs text-gray-500">
        All instructors/staff are mapped.
      </p>
    );
  }

  return (
    <div className="rounded-lg border border-gray-200 p-4">
      <h4 className="mb-3 text-xs font-medium uppercase tracking-wider text-gray-500">
        Add New Mapping
      </h4>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
        <div className="flex-1">
          <label className="mb-1 block text-xs text-gray-600">
            AuraFlow Employee
          </label>
          <select
            value={selectedInstructor}
            onChange={(e) => setSelectedInstructor(e.target.value)}
            className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          >
            <option value="">Select employee...</option>
            {unmappedInstructors.map((i) => (
              <option key={i.instructor_id} value={i.instructor_id}>
                {i.instructor_name}
              </option>
            ))}
          </select>
        </div>
        <div className="flex-1">
          <label className="mb-1 block text-xs text-gray-600">
            External Employee
          </label>
          <select
            value={selectedExternal}
            onChange={(e) => setSelectedExternal(e.target.value)}
            className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          >
            <option value="">Select employee...</option>
            {externalEmployees.map((e) => (
              <option key={e.id} value={e.id}>
                {e.first_name} {e.last_name}
                {e.email ? ` (${e.email})` : ""}
              </option>
            ))}
          </select>
        </div>
        <Button
          size="sm"
          onClick={handleSave}
          disabled={!selectedInstructor || !selectedExternal || isSaving}
        >
          {isSaving ? (
            <Loader2 className="mr-2 h-3 w-3 animate-spin" />
          ) : (
            <Link2 className="mr-2 h-3 w-3" />
          )}
          Map
        </Button>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// TAB 4: Pay History
// ═══════════════════════════════════════════════════════════════════════════════

function PayHistoryTab() {
  const [expandedRun, setExpandedRun] = useState<string | null>(null);

  // Payroll runs from time clock (processed payrolls)
  const { data: payrollRuns, isLoading: runsLoading } = useQuery({
    queryKey: ["payroll-runs"],
    queryFn: () => timeClockApi.listPayrollRuns().then((r) => r.data.data),
  });

  // Historical records from payroll API
  const { data: historyRecords, isLoading: historyLoading } = useQuery({
    queryKey: ["payroll-history"],
    queryFn: () => payrollApi.getHistory(undefined, 50).then((r) => r.data),
  });

  // Fetch details for expanded run
  const { data: expandedRunDetail, isLoading: detailLoading } = useQuery({
    queryKey: ["payroll-run", expandedRun],
    queryFn: () =>
      expandedRun
        ? timeClockApi.getPayrollRun(expandedRun).then((r) => r.data.data)
        : null,
    enabled: !!expandedRun,
  });

  const isLoading = runsLoading || historyLoading;

  const handleDownloadCsv = async (runId: string) => {
    try {
      const res = await payrollExportApi.downloadCsv(runId);
      const blob = new Blob([res.data], { type: "text/csv" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `payroll-${runId}.csv`;
      a.click();
      URL.revokeObjectURL(url);
      toast.success("CSV downloaded");
    } catch {
      toast.error("Failed to download CSV");
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="h-8 w-8 animate-spin text-indigo-600" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Processed Payroll Runs */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Processed Payroll Runs</CardTitle>
        </CardHeader>
        <CardContent>
          {!payrollRuns?.length ? (
            <p className="py-4 text-center text-sm text-gray-500">
              No payroll runs found.
            </p>
          ) : (
            <div className="space-y-2">
              {payrollRuns.map((run) => (
                <div key={run.id} className="rounded-lg border border-gray-200">
                  <button
                    onClick={() =>
                      setExpandedRun(expandedRun === run.id ? null : run.id)
                    }
                    className="flex w-full items-center justify-between p-4 text-left hover:bg-gray-50"
                  >
                    <div className="flex items-center gap-4">
                      <div>
                        <span className="text-sm font-medium text-gray-900">
                          {fmtDate(run.period_start)} -{" "}
                          {fmtDate(run.period_end)}
                        </span>
                        <div className="mt-0.5 flex items-center gap-3 text-xs text-gray-500">
                          <span className="flex items-center gap-1">
                            <DollarSign className="h-3 w-3" />
                            {fmt(run.total_gross_cents)}
                          </span>
                          <span className="flex items-center gap-1">
                            <Clock className="h-3 w-3" />
                            {run.total_hours.toFixed(1)}h
                          </span>
                          {run.export_method && (
                            <span>via {run.export_method}</span>
                          )}
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      <RunStatusBadge status={run.status} />
                      {expandedRun === run.id ? (
                        <ChevronUp className="h-4 w-4 text-gray-400" />
                      ) : (
                        <ChevronDown className="h-4 w-4 text-gray-400" />
                      )}
                    </div>
                  </button>

                  {expandedRun === run.id && (
                    <div className="border-t border-gray-200 bg-gray-50 p-4">
                      {detailLoading ? (
                        <div className="flex items-center justify-center py-4">
                          <Loader2 className="h-5 w-5 animate-spin text-indigo-600" />
                        </div>
                      ) : expandedRunDetail?.line_items &&
                        expandedRunDetail.line_items.length > 0 ? (
                        <>
                          <div className="overflow-x-auto">
                            <table className="w-full text-sm">
                              <thead>
                                <tr className="text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                                  <th className="px-3 py-2">Employee</th>
                                  <th className="px-3 py-2 text-right">Hours</th>
                                  <th className="px-3 py-2 text-right">OT Hours</th>
                                  <th className="px-3 py-2 text-center">Classes</th>
                                  <th className="px-3 py-2 text-right">Total</th>
                                </tr>
                              </thead>
                              <tbody className="divide-y divide-gray-200">
                                {expandedRunDetail.line_items.map((item) => (
                                  <tr key={item.id}>
                                    <td className="px-3 py-2 font-medium text-gray-900">
                                      {item.instructor_name || item.instructor_id}
                                    </td>
                                    <td className="px-3 py-2 text-right text-gray-600">
                                      {item.hours_worked.toFixed(1)}h
                                    </td>
                                    <td className="px-3 py-2 text-right text-gray-600">
                                      {item.overtime_hours > 0
                                        ? `${item.overtime_hours.toFixed(1)}h`
                                        : "-"}
                                    </td>
                                    <td className="px-3 py-2 text-center text-gray-600">
                                      {item.classes_taught}
                                    </td>
                                    <td className="px-3 py-2 text-right font-medium text-gray-900">
                                      {fmt(item.total_gross_cents)}
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                          <div className="mt-3 flex justify-end">
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => handleDownloadCsv(run.id)}
                            >
                              <Download className="mr-2 h-3 w-3" />
                              Download CSV
                            </Button>
                          </div>
                        </>
                      ) : (
                        <p className="py-2 text-center text-sm text-gray-500">
                          No line item details available for this run.
                        </p>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Payment History (mark-as-paid records) */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Payment Records</CardTitle>
        </CardHeader>
        <CardContent>
          {!historyRecords?.length ? (
            <p className="py-4 text-center text-sm text-gray-500">
              No payment history found.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-gray-50 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                    <th className="px-4 py-3">Period</th>
                    <th className="px-4 py-3">Instructor</th>
                    <th className="px-4 py-3 text-center">Classes</th>
                    <th className="px-4 py-3 text-center">Privates</th>
                    <th className="px-4 py-3 text-center">Workshops</th>
                    <th className="px-4 py-3 text-right">Total Gross</th>
                    <th className="px-4 py-3 text-center">Status</th>
                    <th className="px-4 py-3">Paid</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {historyRecords.map((rec, idx) => (
                    <tr key={`${rec.instructor_id}-${rec.period_start}-${idx}`} className="hover:bg-gray-50">
                      <td className="px-4 py-2 text-sm text-gray-900">
                        {fmtDate(rec.period_start)} - {fmtDate(rec.period_end)}
                      </td>
                      <td className="px-4 py-2 text-sm font-medium text-gray-900">
                        {rec.instructor_name}
                      </td>
                      <td className="px-4 py-2 text-center text-gray-600">
                        {rec.classes_taught}
                      </td>
                      <td className="px-4 py-2 text-center text-gray-600">
                        {rec.private_sessions_count}
                      </td>
                      <td className="px-4 py-2 text-center text-gray-600">
                        {rec.workshops_count}
                      </td>
                      <td className="px-4 py-2 text-right font-medium text-gray-900">
                        {fmt(rec.total_gross_cents)}
                      </td>
                      <td className="px-4 py-2 text-center">
                        <span
                          className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${
                            rec.status === "paid"
                              ? "bg-green-50 text-green-700"
                              : "bg-gray-100 text-gray-600"
                          }`}
                        >
                          {rec.status}
                        </span>
                      </td>
                      <td className="px-4 py-2 text-xs text-gray-500">
                        {rec.paid_at ? fmtDateTime(rec.paid_at) : "-"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// TAB 5: Settings
// ═══════════════════════════════════════════════════════════════════════════════

function SettingsTab() {
  // Settings are stored locally and would be persisted via a settings API
  // For now, render the form with localStorage persistence
  const [payPeriod, setPayPeriod] = useState(() =>
    typeof window !== "undefined"
      ? localStorage.getItem("payroll_pay_period") || "biweekly"
      : "biweekly"
  );
  const [defaultGroupRate, setDefaultGroupRate] = useState(() =>
    typeof window !== "undefined"
      ? localStorage.getItem("payroll_default_group_rate") || "50.00"
      : "50.00"
  );
  const [defaultPrivateRate, setDefaultPrivateRate] = useState(() =>
    typeof window !== "undefined"
      ? localStorage.getItem("payroll_default_private_pct") || "60"
      : "60"
  );
  const [defaultWorkshopPct, setDefaultWorkshopPct] = useState(() =>
    typeof window !== "undefined"
      ? localStorage.getItem("payroll_default_workshop_pct") || "50"
      : "50"
  );
  const [defaultTrainingRate, setDefaultTrainingRate] = useState(() =>
    typeof window !== "undefined"
      ? localStorage.getItem("payroll_default_training_rate") || "25.00"
      : "25.00"
  );
  const [overtimeThreshold, setOvertimeThreshold] = useState(() =>
    typeof window !== "undefined"
      ? localStorage.getItem("payroll_overtime_threshold") || "40"
      : "40"
  );
  const [overtimeMultiplier, setOvertimeMultiplier] = useState(() =>
    typeof window !== "undefined"
      ? localStorage.getItem("payroll_overtime_multiplier") || "1.5"
      : "1.5"
  );
  const [saved, setSaved] = useState(false);

  const handleSave = () => {
    if (typeof window !== "undefined") {
      localStorage.setItem("payroll_pay_period", payPeriod);
      localStorage.setItem("payroll_default_group_rate", defaultGroupRate);
      localStorage.setItem("payroll_default_private_pct", defaultPrivateRate);
      localStorage.setItem("payroll_default_workshop_pct", defaultWorkshopPct);
      localStorage.setItem("payroll_default_training_rate", defaultTrainingRate);
      localStorage.setItem("payroll_overtime_threshold", overtimeThreshold);
      localStorage.setItem("payroll_overtime_multiplier", overtimeMultiplier);
    }
    setSaved(true);
    toast.success("Settings saved");
    setTimeout(() => setSaved(false), 2000);
  };

  return (
    <div className="space-y-6">
      {/* Pay Period */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Pay Period</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="max-w-sm">
            <label className="mb-1 block text-sm font-medium text-gray-700">
              Pay Frequency
            </label>
            <select
              value={payPeriod}
              onChange={(e) => setPayPeriod(e.target.value)}
              className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            >
              <option value="weekly">Weekly</option>
              <option value="biweekly">Biweekly</option>
              <option value="semimonthly">Semi-Monthly (1st & 15th)</option>
              <option value="monthly">Monthly</option>
            </select>
            <p className="mt-1 text-xs text-gray-500">
              How often payroll is processed. This sets the default period when
              compiling payroll runs.
            </p>
          </div>
        </CardContent>
      </Card>

      {/* Default Pay Rates */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Default Pay Rates</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="mb-4 text-sm text-gray-600">
            Default rates applied to new instructors/staff. Individual rates can
            be overridden per person.
          </p>
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">
                Group Class Rate (per class)
              </label>
              <div className="relative">
                <span className="absolute left-3 top-1/2 -translate-y-1/2 text-sm text-gray-500">
                  $
                </span>
                <Input
                  type="number"
                  step="0.01"
                  min="0"
                  value={defaultGroupRate}
                  onChange={(e) => setDefaultGroupRate(e.target.value)}
                  className="pl-7"
                />
              </div>
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">
                Private Session Pay (% of revenue)
              </label>
              <div className="relative">
                <Input
                  type="number"
                  step="1"
                  min="0"
                  max="100"
                  value={defaultPrivateRate}
                  onChange={(e) => setDefaultPrivateRate(e.target.value)}
                />
                <span className="absolute right-3 top-1/2 -translate-y-1/2 text-sm text-gray-500">
                  %
                </span>
              </div>
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">
                Workshop Pay (% of revenue)
              </label>
              <div className="relative">
                <Input
                  type="number"
                  step="1"
                  min="0"
                  max="100"
                  value={defaultWorkshopPct}
                  onChange={(e) => setDefaultWorkshopPct(e.target.value)}
                />
                <span className="absolute right-3 top-1/2 -translate-y-1/2 text-sm text-gray-500">
                  %
                </span>
              </div>
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">
                Training Rate (per hour)
              </label>
              <div className="relative">
                <span className="absolute left-3 top-1/2 -translate-y-1/2 text-sm text-gray-500">
                  $
                </span>
                <Input
                  type="number"
                  step="0.01"
                  min="0"
                  value={defaultTrainingRate}
                  onChange={(e) => setDefaultTrainingRate(e.target.value)}
                  className="pl-7"
                />
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Overtime Rules */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Overtime Rules</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="mb-4 text-sm text-gray-600">
            Configure overtime thresholds and pay multipliers for W2 employees.
          </p>
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">
                Weekly Hours Threshold
              </label>
              <div className="relative">
                <Input
                  type="number"
                  step="1"
                  min="0"
                  value={overtimeThreshold}
                  onChange={(e) => setOvertimeThreshold(e.target.value)}
                />
                <span className="absolute right-3 top-1/2 -translate-y-1/2 text-sm text-gray-500">
                  hours
                </span>
              </div>
              <p className="mt-1 text-xs text-gray-500">
                Hours per week before overtime kicks in (typically 40).
              </p>
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">
                Overtime Multiplier
              </label>
              <div className="relative">
                <Input
                  type="number"
                  step="0.1"
                  min="1"
                  value={overtimeMultiplier}
                  onChange={(e) => setOvertimeMultiplier(e.target.value)}
                />
                <span className="absolute right-3 top-1/2 -translate-y-1/2 text-sm text-gray-500">
                  x
                </span>
              </div>
              <p className="mt-1 text-xs text-gray-500">
                Pay multiplier for overtime hours (typically 1.5x).
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Save Button */}
      <div className="flex justify-end">
        <Button onClick={handleSave}>
          {saved ? (
            <>
              <CheckCircle2 className="mr-2 h-4 w-4" />
              Saved
            </>
          ) : (
            <>
              <Settings className="mr-2 h-4 w-4" />
              Save Settings
            </>
          )}
        </Button>
      </div>
    </div>
  );
}
