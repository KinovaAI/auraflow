import { apiClient } from "./api-client";

// ── Types ────────────────────────────────────────────────────────────────────

export interface TimeEntry {
  id: string;
  instructor_id: string;
  instructor_name?: string;
  clock_in: string;
  clock_out: string | null;
  break_minutes: number;
  shift_type: string;
  notes: string | null;
  status: string;
  approved_by: string | null;
  approved_at: string | null;
  total_minutes: number | null;
  overtime_minutes: number;
  created_at: string;
  updated_at: string;
}

export interface PayrollRun {
  id: string;
  period_start: string;
  period_end: string;
  status: string;
  total_gross_cents: number;
  total_hours: number;
  created_by: string | null;
  finalized_at: string | null;
  exported_at: string | null;
  export_method: string | null;
  created_at: string;
  updated_at: string;
  line_items?: PayrollLineItem[];
}

export interface PayrollLineItem {
  id: string;
  payroll_run_id: string;
  instructor_id: string;
  instructor_name?: string;
  hours_worked: number;
  overtime_hours: number;
  classes_taught: number;
  class_pay_cents: number;
  hourly_pay_cents: number;
  overtime_pay_cents: number;
  // Privates / workshops / trainings — written by compile_payroll.
  private_sessions_count?: number;
  private_session_revenue_cents?: number;
  private_session_pay_cents?: number;
  workshops_count?: number;
  workshop_revenue_cents?: number;
  workshop_pay_cents?: number;
  training_pay_cents?: number;
  total_gross_cents: number;
  created_at: string;
}

// ── API ──────────────────────────────────────────────────────────────────────

export const timeClockApi = {
  // Clock operations
  clockIn: (instructor_id: string, shift_type = "regular", notes?: string) =>
    apiClient.post<{ data: TimeEntry }>("/time-clock/clock-in", {
      instructor_id,
      shift_type,
      notes,
    }),

  clockOut: (instructor_id: string, break_minutes = 0, notes?: string) =>
    apiClient.post<{ data: TimeEntry }>("/time-clock/clock-out", {
      instructor_id,
      break_minutes,
      notes,
    }),

  getStatus: (instructor_id: string) =>
    apiClient.get<{ data: TimeEntry | null }>(
      `/time-clock/status/${instructor_id}`
    ),

  // Timesheets
  myTimesheet: (instructor_id: string, start?: string, end?: string) =>
    apiClient.get<{ data: TimeEntry[] }>("/time-clock/my-timesheet", {
      params: { instructor_id, start, end },
    }),

  allTimesheets: (start?: string, end?: string) =>
    apiClient.get<{ data: TimeEntry[] }>("/time-clock/timesheets", {
      params: { start, end },
    }),

  // Approval
  approveEntry: (entry_id: string) =>
    apiClient.put<{ data: TimeEntry }>(
      `/time-clock/entries/${entry_id}/approve`
    ),

  rejectEntry: (entry_id: string, reason?: string) =>
    apiClient.put<{ data: TimeEntry }>(
      `/time-clock/entries/${entry_id}/reject`,
      { reason }
    ),

  // Payroll
  compilePayroll: (period_start: string, period_end: string) =>
    apiClient.post<{ data: PayrollRun }>("/time-clock/payroll/compile", {
      period_start,
      period_end,
    }),

  listPayrollRuns: () =>
    apiClient.get<{ data: PayrollRun[] }>("/time-clock/payroll"),

  getPayrollRun: (run_id: string) =>
    apiClient.get<{ data: PayrollRun }>(`/time-clock/payroll/${run_id}`),

  finalizePayroll: (run_id: string) =>
    apiClient.put<{ data: PayrollRun }>(
      `/time-clock/payroll/${run_id}/finalize`
    ),
};
