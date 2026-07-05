import { apiClient } from "./api-client";

export interface PayrollLine {
  instructor_id: string;
  instructor_name: string;
  tax_classification: string;
  pay_type: string;
  pay_rate_cents: number;
  group_classes_count: number;
  group_revenue_cents: number;
  group_class_pay_cents: number;
  private_sessions_count: number;
  private_session_revenue_cents: number;
  private_session_pay_cents: number;
  workshops_count: number;
  workshop_revenue_cents: number;
  workshop_pay_cents: number;
  training_pay_cents: number;
  total_owed_cents: number;
  paid_at: string | null;
}

export interface PayrollHistoryRecord {
  period_start: string;
  period_end: string;
  status: string;
  instructor_id: string;
  instructor_name: string;
  classes_taught: number;
  class_pay_cents: number;
  private_sessions_count: number;
  private_session_pay_cents: number;
  workshops_count: number;
  workshop_pay_cents: number;
  training_pay_cents: number;
  total_gross_cents: number;
  paid_at: string | null;
}

export const payrollApi = {
  getReport: (month: string, instructorId?: string) => {
    const params = new URLSearchParams({ month });
    if (instructorId) params.set("instructor_id", instructorId);
    return apiClient.get<PayrollLine[]>(`/payroll/report?${params}`);
  },

  markPaid: (instructorId: string, month: string) =>
    apiClient.post("/payroll/mark-paid", {
      instructor_id: instructorId,
      month,
    }),

  getHistory: (instructorId?: string, limit = 12) => {
    const params = new URLSearchParams({ limit: String(limit) });
    if (instructorId) params.set("instructor_id", instructorId);
    return apiClient.get<PayrollHistoryRecord[]>(`/payroll/history?${params}`);
  },
};
