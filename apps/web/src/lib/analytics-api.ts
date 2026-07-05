import { apiClient } from "./api-client";

// ── Types ────────────────────────────────────────────────────────────────────

export interface DashboardKPIs {
  revenue: number;
  revenue_change_percent: number;
  transaction_count: number;
  active_members: number;
  total_members: number;
  active_memberships: number;
  attendance: number;
  total_bookings: number;
  period_days: number;
}

export interface RevenuePeriod {
  period: string;
  revenue: number;
  net_revenue: number;
  refunds: number;
  count: number;
}

export interface RevenueByType {
  type: string;
  revenue: number;
  count: number;
}

export interface AttendancePeriod {
  period: string;
  attended: number;
  confirmed: number;
  no_shows: number;
  cancelled: number;
}

export interface AttendanceByClassType {
  class_type: string;
  attended: number;
  total_bookings: number;
  sessions: number;
}

export interface MembershipSummary {
  active: number;
  frozen: number;
  cancelled: number;
  expired: number;
  total: number;
}

export interface MembershipByType {
  name: string;
  type: string;
  price_cents: number;
  active_count: number;
  frozen_count: number;
  total_count: number;
}

export interface ChurnData {
  cancelled_in_period: number;
  currently_active: number;
  churn_rate_percent: number;
  period_days: number;
}

export interface InstructorReport {
  id: string;
  display_name: string;
  pay_rate_cents: number;
  pay_type: string;
  sessions_taught: number;
  total_attended: number;
  estimated_pay_cents: number;
}

export interface StudioHealth {
  new_members: number;
  total_booked_spots: number;
  total_capacity: number;
  booking_rate_percent: number;
  cancellations: number;
  late_cancellations: number;
  waitlisted: number;
  no_shows: number;
  attendance_rate_percent: number;
  sessions_held: number;
  avg_class_size: number;
  new_memberships_sold: number;
}

export interface TopCanceller {
  id: string;
  first_name: string;
  last_name: string;
  email: string;
  cancel_count: number;
  late_cancel_count: number;
  no_show_count: number;
}

export interface TopSellingMembership {
  id: string;
  name: string;
  type: string;
  price_cents: number;
  sold_count: number;
  total_revenue_cents: number;
}

export interface NewMembersPeriod {
  period: string;
  count: number;
}

export interface RoomUtilization {
  room_name: string;
  room_capacity: number;
  sessions: number;
  total_bookings: number;
  total_capacity: number;
  utilization_percent: number;
}

export interface AITokenUsage {
  period_start: string;
  total_tokens: number;
  input_tokens: number;
  output_tokens: number;
  api_call_count: number;
  free_tier_limit: number;
  free_tier_remaining: number;
  billable_tokens: number;
  rate_cents_per_1k: number;
  estimated_cost_cents: number;
  estimated_cost_display: string;
}

export interface AIUsageByService {
  service_name: string;
  total_tokens: number;
  input_tokens: number;
  output_tokens: number;
  call_count: number;
}

export interface AIUsageDaily {
  date: string;
  total_tokens: number;
  call_count: number;
}

// ── API ──────────────────────────────────────────────────────────────────────

export const analyticsApi = {
  dashboardKPIs: (days: number = 30) =>
    apiClient.get<{ data: DashboardKPIs }>("/analytics/dashboard", { params: { days } }),

  revenueOverTime: (days: number = 30, groupBy: string = "day") =>
    apiClient.get<{ data: RevenuePeriod[] }>("/analytics/revenue/over-time", {
      params: { days, group_by: groupBy },
    }),

  revenueByType: (days: number = 30) =>
    apiClient.get<{ data: RevenueByType[] }>("/analytics/revenue/by-type", { params: { days } }),

  attendanceOverTime: (days: number = 30, groupBy: string = "day") =>
    apiClient.get<{ data: AttendancePeriod[] }>("/analytics/attendance/over-time", {
      params: { days, group_by: groupBy },
    }),

  attendanceByClassType: (days: number = 30) =>
    apiClient.get<{ data: AttendanceByClassType[] }>("/analytics/attendance/by-class-type", {
      params: { days },
    }),

  membershipSummary: () =>
    apiClient.get<{ data: MembershipSummary }>("/analytics/memberships/summary"),

  membershipByType: () =>
    apiClient.get<{ data: MembershipByType[] }>("/analytics/memberships/by-type"),

  churnRate: (days: number = 30) =>
    apiClient.get<{ data: ChurnData }>("/analytics/memberships/churn", { params: { days } }),

  topSellingMemberships: (days: number = 30, limit: number = 10) =>
    apiClient.get<{ data: TopSellingMembership[] }>("/analytics/memberships/top-selling", {
      params: { days, limit },
    }),

  studioHealth: (days: number = 30) =>
    apiClient.get<{ data: StudioHealth }>("/analytics/studio-health", { params: { days } }),

  topCancellers: (days: number = 30, limit: number = 10) =>
    apiClient.get<{ data: TopCanceller[] }>("/analytics/members/top-cancellers", {
      params: { days, limit },
    }),

  newMembersOverTime: (days: number = 30, groupBy: string = "day") =>
    apiClient.get<{ data: NewMembersPeriod[] }>("/analytics/members/new-over-time", {
      params: { days, group_by: groupBy },
    }),

  roomUtilization: (days: number = 30) =>
    apiClient.get<{ data: RoomUtilization[] }>("/analytics/utilization/rooms", { params: { days } }),

  instructorSummary: (days: number = 30) =>
    apiClient.get<{ data: InstructorReport[] }>("/analytics/instructors", { params: { days } }),

  revenueForecast: (days: number = 90) =>
    apiClient.get(`/analytics/revenue-forecast?days=${days}`),

  aiTokenUsage: () =>
    apiClient.get<{ data: AITokenUsage }>("/ai/usage/current"),

  aiTokenUsageByService: (days: number = 30) =>
    apiClient.get<{ data: AIUsageByService[] }>("/ai/usage/by-service", { params: { days } }),

  aiTokenUsageDaily: (days: number = 30) =>
    apiClient.get<{ data: AIUsageDaily[] }>("/ai/usage/daily", { params: { days } }),
};
