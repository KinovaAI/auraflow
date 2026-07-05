import { apiClient } from "./api-client";

// ── Wrapper type for API responses ─────────────────────────────────────────

interface ApiResponse<T> {
  data: T;
}

// ── Private Services ────────────────────────────────────────────────────────

export interface PrivateService {
  id: string;
  instructor_id: string;
  name: string;
  description?: string;
  duration_minutes: number;
  price_cents: number;
  buffer_before_minutes: number;
  buffer_after_minutes: number;
  max_per_day: number;
  visibility: "public" | "unlisted" | "private" | "members_only";
  is_virtual: boolean;
  is_active: boolean;
  package_sessions?: number;
  package_price_cents?: number;
  created_at: string;
  // Joined fields
  instructor_first_name?: string;
  instructor_last_name?: string;
  instructor_display_name?: string;
}

// ── Availability Slots ──────────────────────────────────────────────────────

export interface AvailabilitySlot {
  id: string;
  instructor_id: string;
  day_of_week: number;
  start_time: string;
  end_time: string;
  is_recurring: boolean;
  is_blocked: boolean;
  specific_date?: string;
}

// ── Private Bookings ────────────────────────────────────────────────────────

export interface PrivateBooking {
  id: string;
  member_id: string;
  instructor_id: string;
  private_service_id: string;
  starts_at: string;
  ends_at: string;
  status: "pending" | "confirmed" | "cancelled" | "completed" | "no_show";
  is_virtual: boolean;
  intake_notes?: string;
  instructor_notes?: string;
  price_cents: number;
  payment_status?: "unpaid" | "paid";
  payment_url?: string;
  cancelled_at?: string;
  cancellation_reason?: string;
  // Joined fields
  service_name?: string;
  member_first_name?: string;
  member_last_name?: string;
  instructor_first_name?: string;
  instructor_last_name?: string;
}

// ── Time Slots ──────────────────────────────────────────────────────────────

export interface TimeSlot {
  start_time: string;
  end_time: string;
  duration_minutes: number;
}

// ── Private Services API ────────────────────────────────────────────────────

export const privateServicesApi = {
  list: () =>
    apiClient.get<ApiResponse<PrivateService[]>>("/private-sessions/services"),

  get: (id: string) =>
    apiClient.get<ApiResponse<PrivateService>>(`/private-sessions/services/${id}`),

  create: (data: Partial<PrivateService> & { instructor_id: string; name: string; duration_minutes: number; price_cents: number }) =>
    apiClient.post<ApiResponse<PrivateService>>("/private-sessions/services", data),

  update: (id: string, data: Partial<PrivateService>) =>
    apiClient.put<ApiResponse<PrivateService>>(`/private-sessions/services/${id}`, data),

  deactivate: (id: string) =>
    apiClient.delete(`/private-sessions/services/${id}`),
};

// ── Availability API ────────────────────────────────────────────────────────

export const availabilityApi = {
  get: (instructorId: string) =>
    apiClient.get<ApiResponse<AvailabilitySlot[]>>(
      `/private-sessions/availability/${instructorId}`
    ),

  set: (instructorId: string, slots: Partial<AvailabilitySlot>[]) =>
    apiClient.post<ApiResponse<AvailabilitySlot[]>>(
      `/private-sessions/availability/${instructorId}`,
      { slots }
    ),

  blockTime: (instructorId: string, data: { specific_date: string; start_time: string; end_time: string }) =>
    apiClient.post<ApiResponse<AvailabilitySlot>>(
      `/private-sessions/availability/${instructorId}/block`,
      data
    ),
};

// ── Slots API ───────────────────────────────────────────────────────────────

export const slotsApi = {
  getSlots: (instructorId: string, serviceId: string, date: string) =>
    apiClient.get<ApiResponse<TimeSlot[]>>(
      `/private-sessions/slots?instructor_id=${instructorId}&service_id=${serviceId}&date=${date}`
    ),
};

// ── Private Bookings API ────────────────────────────────────────────────────

export const privateBookingsApi = {
  list: (params?: { payment_status?: string; status?: string; instructor_id?: string }) => {
    const qs = new URLSearchParams();
    if (params?.payment_status) qs.set("payment_status", params.payment_status);
    if (params?.status) qs.set("status", params.status);
    if (params?.instructor_id) qs.set("instructor_id", params.instructor_id);
    const query = qs.toString();
    return apiClient.get<ApiResponse<PrivateBooking[]>>(`/private-sessions/bookings${query ? `?${query}` : ""}`);
  },

  get: (id: string) =>
    apiClient.get<ApiResponse<PrivateBooking>>(`/private-sessions/bookings/${id}`),

  create: (data: {
    member_id: string;
    instructor_id: string;
    private_service_id: string;
    starts_at: string;
    is_virtual?: boolean;
    intake_notes?: string;
    as_package?: boolean;
    apply_credit_id?: string;
  }) => apiClient.post<ApiResponse<PrivateBooking>>("/private-sessions/bookings", data),

  confirm: (id: string) =>
    apiClient.post<ApiResponse<PrivateBooking>>(`/private-sessions/bookings/${id}/confirm`),

  cancel: (
    id: string,
    reason?: string,
    cancelledByRole?: "instructor" | "member" | "staff",
  ) =>
    apiClient.post<ApiResponse<PrivateBooking>>(
      `/private-sessions/bookings/${id}/cancel`,
      { reason, cancelled_by_role: cancelledByRole },
    ),

  complete: (id: string, instructorNotes?: string) =>
    apiClient.post<ApiResponse<PrivateBooking>>(`/private-sessions/bookings/${id}/complete`, {
      instructor_notes: instructorNotes,
    }),

  sendPaymentLink: (id: string) =>
    apiClient.post<ApiResponse<{ payment_url: string; emailed: boolean }>>(
      `/private-sessions/bookings/${id}/send-payment-link`
    ),
};
