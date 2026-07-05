"use client";

import { useState, useEffect, useCallback } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useAuthStore } from "@/stores/auth-store";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Clock,
  Play,
  Square,
  Check,
  X,
  Loader2,
  DollarSign,
  FileText,
  Lock,
  Download,
  Upload,
  CheckCircle,
} from "lucide-react";
import {
  timeClockApi,
  type TimeEntry,
  type PayrollRun,
} from "@/lib/time-clock-api";
import { payrollExportApi, type PayrollExportStatus } from "@/lib/payroll-export-api";
import { instructorsApi, type Instructor } from "@/lib/instructors-api";
import toast from "react-hot-toast";
import { usePermission } from "@/hooks/use-permission";

// ── Helpers ──────────────────────────────────────────────────────────────────

function fmtTime(iso: string | null) {
  if (!iso) return "—";
  return new Date(iso).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });
}

function fmtDate(iso: string) {
  return new Date(iso).toLocaleDateString([], {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function fmtDuration(minutes: number | null) {
  if (!minutes) return "—";
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return `${h}h ${m}m`;
}

function fmtCents(cents: number) {
  return `$${(cents / 100).toFixed(2)}`;
}

function todayISO() {
  return new Date().toISOString().slice(0, 10);
}

function weekAgoISO() {
  const d = new Date();
  d.setDate(d.getDate() - 7);
  return d.toISOString().slice(0, 10);
}

// ── Status Badge ─────────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    pending: "bg-yellow-100 text-yellow-800",
    approved: "bg-green-100 text-green-800",
    rejected: "bg-red-100 text-red-800",
    draft: "bg-gray-100 text-gray-800",
    finalized: "bg-blue-100 text-blue-800",
    exported: "bg-purple-100 text-purple-800",
  };
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${colors[status] || "bg-gray-100 text-gray-800"}`}
    >
      {status}
    </span>
  );
}

// ── Tab Selector ─────────────────────────────────────────────────────────────

const tabs = [
  { key: "clock", label: "Clock", icon: Clock },
  { key: "timesheets", label: "Timesheets", icon: FileText },
  { key: "payroll", label: "Payroll", icon: DollarSign },
] as const;

type TabKey = (typeof tabs)[number]["key"];

// ── Main Page ────────────────────────────────────────────────────────────────

export default function TimeClockPage() {
  const [activeTab, setActiveTab] = useState<TabKey>("clock");
  const hasPayroll = usePermission("payroll.view_runs", "payroll.compile", "payroll.view_timesheets");

  // Only show tabs the user has permission for
  const visibleTabs = hasPayroll
    ? tabs
    : tabs.filter((tab) => tab.key === "clock");

  // If user is on a restricted tab and loses permission, reset to clock
  const effectiveTab = hasPayroll ? activeTab : "clock";

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">
          Time Clock{hasPayroll ? " & Payroll" : ""}
        </h1>
        <p className="text-gray-500">
          {hasPayroll
            ? "Track instructor hours, approve timesheets, and compile payroll"
            : "Track your hours and clock in/out"}
        </p>
      </div>

      {/* Tab bar */}
      <div className="flex gap-1 rounded-lg bg-gray-100 p-1">
        {visibleTabs.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`flex items-center gap-2 rounded-md px-4 py-2 text-sm font-medium transition-colors ${
              effectiveTab === tab.key
                ? "bg-white text-gray-900 shadow-sm"
                : "text-gray-600 hover:text-gray-900"
            }`}
          >
            <tab.icon className="h-4 w-4" />
            {tab.label}
          </button>
        ))}
      </div>

      {effectiveTab === "clock" && <ClockTab />}
      {effectiveTab === "timesheets" && hasPayroll && <TimesheetsTab />}
      {effectiveTab === "payroll" && hasPayroll && <PayrollTab />}
    </div>
  );
}

// ── Clock Tab ────────────────────────────────────────────────────────────────

function ClockTab() {
  const queryClient = useQueryClient();
  const [selectedInstructorId, setSelectedInstructorId] = useState("");
  const [shiftType, setShiftType] = useState("regular");
  const [notes, setNotes] = useState("");
  const [elapsed, setElapsed] = useState("");

  // Fetch instructors list for selection
  const { data: instructors } = useQuery({
    queryKey: ["instructors"],
    queryFn: () => instructorsApi.list().then((r) => r.data),
  });

  // Auto-select first instructor
  useEffect(() => {
    if (instructors && instructors.length > 0 && !selectedInstructorId) {
      setSelectedInstructorId(instructors[0].id);
    }
  }, [instructors, selectedInstructorId]);

  const instructorId = selectedInstructorId;

  const { data: status, isLoading: statusLoading } = useQuery({
    queryKey: ["clock-status", instructorId],
    queryFn: () =>
      timeClockApi.getStatus(instructorId).then((r) => r.data.data),
    enabled: !!instructorId,
    refetchInterval: 30000,
  });

  const isClockedIn = !!status;

  // Live elapsed timer
  useEffect(() => {
    if (!status?.clock_in) {
      setElapsed("");
      return;
    }
    const update = () => {
      const diff = Date.now() - new Date(status.clock_in).getTime();
      const h = Math.floor(diff / 3600000);
      const m = Math.floor((diff % 3600000) / 60000);
      const s = Math.floor((diff % 60000) / 1000);
      setElapsed(
        `${h.toString().padStart(2, "0")}:${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`
      );
    };
    update();
    const interval = setInterval(update, 1000);
    return () => clearInterval(interval);
  }, [status?.clock_in]);

  const clockInMut = useMutation({
    mutationFn: () => timeClockApi.clockIn(instructorId, shiftType, notes || undefined),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["clock-status"] });
      queryClient.invalidateQueries({ queryKey: ["my-timesheet"] });
      setNotes("");
    },
  });

  const clockOutMut = useMutation({
    mutationFn: () => timeClockApi.clockOut(instructorId, 0, notes || undefined),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["clock-status"] });
      queryClient.invalidateQueries({ queryKey: ["my-timesheet"] });
      setNotes("");
    },
  });

  // Today's entries
  const { data: todayEntries } = useQuery({
    queryKey: ["my-timesheet", instructorId, todayISO()],
    queryFn: () =>
      timeClockApi
        .myTimesheet(instructorId, todayISO(), todayISO())
        .then((r) => r.data.data),
    enabled: !!instructorId,
  });

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      {/* Clock In/Out Card */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Clock className="h-5 w-5" />
            {isClockedIn ? "Currently Clocked In" : "Clock In"}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {statusLoading ? (
            <div className="flex justify-center py-8">
              <Loader2 className="h-8 w-8 animate-spin text-gray-300" />
            </div>
          ) : (
            <>
              {/* Elapsed timer */}
              {isClockedIn && (
                <div className="text-center">
                  <p className="font-mono text-4xl font-bold text-indigo-600">
                    {elapsed}
                  </p>
                  <p className="mt-1 text-sm text-gray-500">
                    Clocked in at {fmtTime(status!.clock_in)} &middot;{" "}
                    {status!.shift_type}
                  </p>
                </div>
              )}

              {/* Instructor selector + Shift type */}
              {!isClockedIn && (
                <>
                  <div>
                    <label className="mb-1 block text-sm font-medium text-gray-700">
                      Instructor
                    </label>
                    <select
                      value={selectedInstructorId}
                      onChange={(e) => setSelectedInstructorId(e.target.value)}
                      className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
                    >
                      {!instructors || instructors.length === 0 ? (
                        <option value="">No instructors found</option>
                      ) : (
                        instructors.map((inst) => (
                          <option key={inst.id} value={inst.id}>
                            {inst.display_name}
                          </option>
                        ))
                      )}
                    </select>
                  </div>
                  <div>
                    <label className="mb-1 block text-sm font-medium text-gray-700">
                      Shift Type
                    </label>
                    <select
                      value={shiftType}
                      onChange={(e) => setShiftType(e.target.value)}
                      className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
                    >
                      <option value="regular">Regular</option>
                      <option value="training">Training</option>
                      <option value="admin">Admin</option>
                      <option value="event">Event</option>
                    </select>
                  </div>
                </>
              )}

              {/* Notes */}
              <div>
                <label className="mb-1 block text-sm font-medium text-gray-700">
                  Notes
                </label>
                <input
                  type="text"
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  placeholder="Optional notes..."
                  className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
                />
              </div>

              {/* Clock button */}
              <button
                onClick={() =>
                  isClockedIn ? clockOutMut.mutate() : clockInMut.mutate()
                }
                disabled={clockInMut.isPending || clockOutMut.isPending}
                className={`flex w-full items-center justify-center gap-2 rounded-lg px-4 py-3 text-sm font-medium text-white transition-colors ${
                  isClockedIn
                    ? "bg-red-600 hover:bg-red-700"
                    : "bg-green-600 hover:bg-green-700"
                } disabled:opacity-50`}
              >
                {clockInMut.isPending || clockOutMut.isPending ? (
                  <Loader2 className="h-5 w-5 animate-spin" />
                ) : isClockedIn ? (
                  <>
                    <Square className="h-5 w-5" /> Clock Out
                  </>
                ) : (
                  <>
                    <Play className="h-5 w-5" /> Clock In
                  </>
                )}
              </button>

              {(clockInMut.isError || clockOutMut.isError) && (
                <p className="text-sm text-red-600">
                  {(clockInMut.error as Error)?.message ||
                    (clockOutMut.error as Error)?.message ||
                    "An error occurred"}
                </p>
              )}
            </>
          )}
        </CardContent>
      </Card>

      {/* Today's Entries */}
      <Card>
        <CardHeader>
          <CardTitle>Today&apos;s Entries</CardTitle>
        </CardHeader>
        <CardContent>
          {!todayEntries || todayEntries.length === 0 ? (
            <p className="py-4 text-center text-sm text-gray-400">
              No entries today
            </p>
          ) : (
            <div className="space-y-3">
              {todayEntries.map((entry) => (
                <div
                  key={entry.id}
                  className="flex items-center justify-between rounded-lg border border-gray-100 p-3"
                >
                  <div>
                    <p className="text-sm font-medium">
                      {fmtTime(entry.clock_in)} &rarr;{" "}
                      {fmtTime(entry.clock_out)}
                    </p>
                    <p className="text-xs text-gray-500">
                      {entry.shift_type} &middot;{" "}
                      {fmtDuration(entry.total_minutes)}
                      {entry.overtime_minutes > 0 &&
                        ` (${entry.overtime_minutes}m OT)`}
                    </p>
                  </div>
                  <StatusBadge status={entry.status} />
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

// ── Timesheets Tab ───────────────────────────────────────────────────────────

function TimesheetsTab() {
  const queryClient = useQueryClient();
  const [start, setStart] = useState(weekAgoISO());
  const [end, setEnd] = useState(todayISO());

  const { data: entries, isLoading } = useQuery({
    queryKey: ["all-timesheets", start, end],
    queryFn: () =>
      timeClockApi.allTimesheets(start, end).then((r) => r.data.data),
  });

  const approveMut = useMutation({
    mutationFn: (id: string) => timeClockApi.approveEntry(id),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["all-timesheets"] }),
  });

  const rejectMut = useMutation({
    mutationFn: (id: string) => timeClockApi.rejectEntry(id),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["all-timesheets"] }),
  });

  return (
    <div className="space-y-4">
      {/* Date range */}
      <div className="flex items-end gap-4">
        <div>
          <label className="mb-1 block text-xs font-medium text-gray-500">
            Start
          </label>
          <input
            type="date"
            value={start}
            onChange={(e) => setStart(e.target.value)}
            className="rounded-md border border-gray-300 px-3 py-2 text-sm"
          />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-gray-500">
            End
          </label>
          <input
            type="date"
            value={end}
            onChange={(e) => setEnd(e.target.value)}
            className="rounded-md border border-gray-300 px-3 py-2 text-sm"
          />
        </div>
      </div>

      {/* Table */}
      <Card>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="flex justify-center py-8">
              <Loader2 className="h-6 w-6 animate-spin text-gray-300" />
            </div>
          ) : !entries || entries.length === 0 ? (
            <p className="py-8 text-center text-sm text-gray-400">
              No timesheet entries for this period
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-gray-50 text-left text-xs font-medium uppercase text-gray-500">
                    <th className="px-4 py-3">Instructor</th>
                    <th className="px-4 py-3">Date</th>
                    <th className="px-4 py-3">In</th>
                    <th className="px-4 py-3">Out</th>
                    <th className="px-4 py-3">Hours</th>
                    <th className="px-4 py-3">Break</th>
                    <th className="px-4 py-3">OT</th>
                    <th className="px-4 py-3">Status</th>
                    <th className="px-4 py-3">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {entries.map((entry) => (
                    <tr key={entry.id} className="hover:bg-gray-50">
                      <td className="px-4 py-3 font-medium">
                        {entry.instructor_name || entry.instructor_id.slice(0, 8)}
                      </td>
                      <td className="px-4 py-3">{fmtDate(entry.clock_in)}</td>
                      <td className="px-4 py-3">{fmtTime(entry.clock_in)}</td>
                      <td className="px-4 py-3">
                        {fmtTime(entry.clock_out)}
                      </td>
                      <td className="px-4 py-3">
                        {fmtDuration(entry.total_minutes)}
                      </td>
                      <td className="px-4 py-3">{entry.break_minutes}m</td>
                      <td className="px-4 py-3">
                        {entry.overtime_minutes > 0
                          ? `${entry.overtime_minutes}m`
                          : "—"}
                      </td>
                      <td className="px-4 py-3">
                        <StatusBadge status={entry.status} />
                      </td>
                      <td className="px-4 py-3">
                        {entry.status === "pending" && (
                          <div className="flex gap-1">
                            <button
                              onClick={() => approveMut.mutate(entry.id)}
                              disabled={approveMut.isPending}
                              className="rounded p-1 text-green-600 hover:bg-green-50"
                              title="Approve"
                            >
                              <Check className="h-4 w-4" />
                            </button>
                            <button
                              onClick={() => rejectMut.mutate(entry.id)}
                              disabled={rejectMut.isPending}
                              className="rounded p-1 text-red-600 hover:bg-red-50"
                              title="Reject"
                            >
                              <X className="h-4 w-4" />
                            </button>
                          </div>
                        )}
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

// ── Payroll Tab ──────────────────────────────────────────────────────────────

function PayrollTab() {
  const queryClient = useQueryClient();
  const [periodStart, setPeriodStart] = useState("");
  const [periodEnd, setPeriodEnd] = useState("");
  const [selectedRun, setSelectedRun] = useState<PayrollRun | null>(null);

  const { data: runs, isLoading } = useQuery({
    queryKey: ["payroll-runs"],
    queryFn: () => timeClockApi.listPayrollRuns().then((r) => r.data.data),
  });

  const compileMut = useMutation({
    mutationFn: () => timeClockApi.compilePayroll(periodStart, periodEnd),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["payroll-runs"] });
      setPeriodStart("");
      setPeriodEnd("");
    },
  });

  const finalizeMut = useMutation({
    mutationFn: (id: string) => timeClockApi.finalizePayroll(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["payroll-runs"] });
      if (selectedRun) {
        loadRun(selectedRun.id);
      }
    },
  });

  const loadRun = useCallback(async (id: string) => {
    const resp = await timeClockApi.getPayrollRun(id);
    setSelectedRun(resp.data.data);
  }, []);

  return (
    <div className="space-y-6">
      {/* Compile payroll */}
      <Card>
        <CardHeader>
          <CardTitle>Compile Payroll</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-end gap-4">
            <div>
              <label className="mb-1 block text-xs font-medium text-gray-500">
                Period Start
              </label>
              <input
                type="date"
                value={periodStart}
                onChange={(e) => setPeriodStart(e.target.value)}
                className="rounded-md border border-gray-300 px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-gray-500">
                Period End
              </label>
              <input
                type="date"
                value={periodEnd}
                onChange={(e) => setPeriodEnd(e.target.value)}
                className="rounded-md border border-gray-300 px-3 py-2 text-sm"
              />
            </div>
            <button
              onClick={() => compileMut.mutate()}
              disabled={
                !periodStart || !periodEnd || compileMut.isPending
              }
              className="flex items-center gap-2 rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
            >
              {compileMut.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <DollarSign className="h-4 w-4" />
              )}
              Compile
            </button>
          </div>
          {compileMut.isError && (
            <p className="mt-2 text-sm text-red-600">
              {(compileMut.error as Error)?.message || "Failed to compile payroll"}
            </p>
          )}
        </CardContent>
      </Card>

      {/* Payroll runs list */}
      <Card>
        <CardHeader>
          <CardTitle>Payroll Runs</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="flex justify-center py-8">
              <Loader2 className="h-6 w-6 animate-spin text-gray-300" />
            </div>
          ) : !runs || runs.length === 0 ? (
            <p className="py-8 text-center text-sm text-gray-400">
              No payroll runs yet
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-gray-50 text-left text-xs font-medium uppercase text-gray-500">
                    <th className="px-4 py-3">Period</th>
                    <th className="px-4 py-3">Status</th>
                    <th className="px-4 py-3">Total Hours</th>
                    <th className="px-4 py-3">Total Gross</th>
                    <th className="px-4 py-3">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {runs.map((run) => (
                    <tr
                      key={run.id}
                      className={`cursor-pointer hover:bg-gray-50 ${selectedRun?.id === run.id ? "bg-indigo-50" : ""}`}
                      onClick={() => loadRun(run.id)}
                    >
                      <td className="px-4 py-3 font-medium">
                        {fmtDate(run.period_start)} &mdash;{" "}
                        {fmtDate(run.period_end)}
                      </td>
                      <td className="px-4 py-3">
                        <StatusBadge status={run.status} />
                      </td>
                      <td className="px-4 py-3">
                        {run.total_hours?.toFixed(1) || "0"}h
                      </td>
                      <td className="px-4 py-3 font-medium">
                        {fmtCents(run.total_gross_cents)}
                      </td>
                      <td className="px-4 py-3">
                        {run.status === "draft" && (
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              finalizeMut.mutate(run.id);
                            }}
                            disabled={finalizeMut.isPending}
                            className="flex items-center gap-1 rounded px-2 py-1 text-xs font-medium text-indigo-600 hover:bg-indigo-50"
                          >
                            <Lock className="h-3 w-3" />
                            Finalize
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Selected run detail */}
      {selectedRun?.line_items && selectedRun.line_items.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>
              Payroll Detail: {fmtDate(selectedRun.period_start)} &mdash;{" "}
              {fmtDate(selectedRun.period_end)}
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-gray-50 text-left text-xs font-medium uppercase text-gray-500">
                    <th className="px-4 py-3">Instructor</th>
                    <th className="px-4 py-3">Hours</th>
                    <th className="px-4 py-3">OT Hours</th>
                    <th className="px-4 py-3">Classes</th>
                    <th className="px-4 py-3">Hourly Pay</th>
                    <th className="px-4 py-3">OT Pay</th>
                    <th className="px-4 py-3">Class Pay</th>
                    <th className="px-4 py-3">Total</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {selectedRun.line_items.map((item) => (
                    <tr key={item.id} className="hover:bg-gray-50">
                      <td className="px-4 py-3 font-medium">
                        {item.instructor_name ||
                          item.instructor_id.slice(0, 8)}
                      </td>
                      <td className="px-4 py-3">
                        {item.hours_worked?.toFixed(1) || "0"}h
                      </td>
                      <td className="px-4 py-3">
                        {item.overtime_hours > 0
                          ? `${item.overtime_hours.toFixed(1)}h`
                          : "—"}
                      </td>
                      <td className="px-4 py-3">{item.classes_taught}</td>
                      <td className="px-4 py-3">
                        {fmtCents(item.hourly_pay_cents)}
                      </td>
                      <td className="px-4 py-3">
                        {item.overtime_pay_cents > 0
                          ? fmtCents(item.overtime_pay_cents)
                          : "—"}
                      </td>
                      <td className="px-4 py-3">
                        {fmtCents(item.class_pay_cents)}
                      </td>
                      <td className="px-4 py-3 font-bold">
                        {fmtCents(item.total_gross_cents)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Export Actions */}
      {selectedRun && (selectedRun.status === "finalized" || selectedRun.status === "exported") && (
        <PayrollExportActions run={selectedRun} onExported={() => {
          queryClient.invalidateQueries({ queryKey: ["payroll-runs"] });
          if (selectedRun) loadRun(selectedRun.id);
        }} />
      )}
    </div>
  );
}

// ── Payroll Export Actions ───────────────────────────────────────────────────

function PayrollExportActions({ run, onExported }: { run: PayrollRun; onExported: () => void }) {
  const [pushing, setPushing] = useState<string | null>(null);

  const { data: exportStatus } = useQuery({
    queryKey: ["payroll-export-status"],
    queryFn: () => payrollExportApi.getStatus().then((r) => r.data.data),
  });

  const handleCsvDownload = async () => {
    try {
      const resp = await payrollExportApi.downloadCsv(run.id);
      const url = window.URL.createObjectURL(new Blob([resp.data]));
      const link = document.createElement("a");
      link.href = url;
      link.download = `payroll_${run.period_start}_${run.period_end}.csv`;
      link.click();
      window.URL.revokeObjectURL(url);
      toast.success("CSV downloaded");
      onExported();
    } catch {
      toast.error("Failed to download CSV");
    }
  };

  const handleGustoPush = async () => {
    setPushing("gusto");
    try {
      const resp = await payrollExportApi.gustoPush(run.id);
      const result = resp.data.data;
      toast.success(`Sent to Gusto: ${result.submitted.length} employees`);
      onExported();
    } catch {
      toast.error("Failed to push to Gusto");
    } finally {
      setPushing(null);
    }
  };

  const handleQbPush = async () => {
    setPushing("quickbooks");
    try {
      const resp = await payrollExportApi.qbPush(run.id);
      const result = resp.data.data;
      toast.success(`Sent to QuickBooks: ${result.submitted.length} employees`);
      onExported();
    } catch {
      toast.error("Failed to push to QuickBooks");
    } finally {
      setPushing(null);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center justify-between">
          <span>Export Payroll</span>
          {run.exported_at && (
            <span className="flex items-center gap-1 text-sm font-normal text-green-600">
              <CheckCircle className="h-4 w-4" />
              Exported via {run.export_method} on{" "}
              {new Date(run.exported_at).toLocaleDateString()}
            </span>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="flex flex-wrap gap-3">
          <button
            onClick={handleCsvDownload}
            className="flex items-center gap-2 rounded-md border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
          >
            <Download className="h-4 w-4" />
            Download CSV
          </button>

          {exportStatus?.gusto?.connected && (
            <button
              onClick={handleGustoPush}
              disabled={pushing === "gusto"}
              className="flex items-center gap-2 rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
            >
              {pushing === "gusto" ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Upload className="h-4 w-4" />
              )}
              Send to Gusto
            </button>
          )}

          {exportStatus?.quickbooks?.connected && (
            <button
              onClick={handleQbPush}
              disabled={pushing === "quickbooks"}
              className="flex items-center gap-2 rounded-md bg-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-green-700 disabled:opacity-50"
            >
              {pushing === "quickbooks" ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Upload className="h-4 w-4" />
              )}
              Send to QuickBooks
            </button>
          )}
        </div>

        {!exportStatus?.gusto?.connected && !exportStatus?.quickbooks?.connected && (
          <p className="mt-3 text-xs text-gray-400">
            Connect Gusto or QuickBooks in{" "}
            <a href="/dashboard/integrations" className="text-indigo-600 underline">
              Integrations
            </a>{" "}
            to push payroll directly.
          </p>
        )}
      </CardContent>
    </Card>
  );
}
