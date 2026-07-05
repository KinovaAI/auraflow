import { apiClient } from "./api-client";

export interface PortalProfile {
  id: string;
  first_name: string;
  last_name: string;
  email: string;
  phone?: string;
  date_of_birth?: string;
  gender?: string;
  emergency_contact_name?: string;
  emergency_contact_phone?: string;
  photo_url?: string;
  total_visits: number;
  member_number?: string;
  email_opt_in: boolean;
  sms_opt_in: boolean;
  payment_setup_required: boolean;
  waiver_required: boolean;
  created_at?: string;
}

export interface PortalProfileUpdate {
  phone?: string;
  emergency_contact_name?: string;
  emergency_contact_phone?: string;
  email_opt_in?: boolean;
  sms_opt_in?: boolean;
}

export interface PortalSession {
  id: string;
  title?: string;
  starts_at: string;
  ends_at?: string;
  class_type_name?: string;
  class_category?: string;
  class_description?: string;
  level?: string;
  instructor_name?: string;
  room_name?: string;
  spots_remaining: number;
  is_full: boolean;
  waitlist_available: boolean;
  is_virtual?: boolean;
  is_community?: boolean;
}

export interface PortalBooking {
  id: string;
  class_session_id: string;
  session_title?: string;
  class_type_name?: string;
  class_category?: string;
  instructor_name?: string;
  starts_at?: string;
  ends_at?: string;
  status: string;
  booked_at?: string;
  waitlist_position?: number;
  is_virtual?: boolean;
  zoom_join_url?: string;
  zoom_password?: string;
}

export interface PortalMembership {
  id: string;
  type_name: string;
  membership_type?: string;
  status: string;
  starts_at?: string;
  ends_at?: string;
  classes_remaining?: number;
  auto_renew?: boolean;
  price_cents?: number;
  billing_period?: string;
  stripe_subscription_id?: string | null;
  square_subscription_id?: string | null;
  current_period_end?: string | null;
}

export interface PortalSquareConfig {
  application_id: string | null;
  location_id: string | null;
  environment: "sandbox" | "production";
}

export interface PortalSwitchToSquareResult {
  membership_id: string;
  square_subscription_id: string;
  stripe_subscription_id: string;
  stripe_last_charge_date: string;
  square_first_charge_date: string;
  message: string;
}

export interface PortalMembershipType {
  id: string;
  name: string;
  description?: string;
  type: string;
  class_count?: number;
  price_cents: number;
  billing_period?: string;
  duration_days?: number;
  is_founding_rate: boolean;
  trial_days: number;
  freeze_allowed: boolean;
  is_public: boolean;
}

export interface PortalSuggestion {
  session_id: string;
  title: string;
  starts_at: string;
  instructor_name?: string;
  reason: string;
}

export interface PortalTransaction {
  id: string;
  amount_cents: number;
  type: string;
  status: string;
  description?: string;
  created_at?: string;
}

export interface PortalPayment {
  id: string;
  amount_cents: number;
  description?: string;
  status: string;
  payment_date: string;
  stripe_invoice_id?: string;
}

// ── Workshop / Course Types ─────────────────────────────────────────────────

export interface PortalCourse {
  id: string;
  title: string;
  description?: string;
  type: string;
  instructor_name?: string;
  /** Set when the workshop is led by a 1099 guest instructor. */
  guest_instructor_name?: string;
  guest_instructor_photo_url?: string;
  guest_instructor_bio?: string;
  price_cents: number;
  early_bird_price_cents?: number;
  early_bird_deadline?: string;
  is_early_bird_active: boolean;
  capacity?: number;
  enrolled_count: number;
  spots_remaining?: number;
  location?: string;
  is_virtual: boolean;
  image_url?: string;
  prerequisites?: string;
  starts_at?: string;
  ends_at?: string;
}

export interface PortalCourseSession {
  id: string;
  title?: string;
  session_number: number;
  starts_at?: string;
  ends_at?: string;
  location?: string;
  is_virtual: boolean;
}

export interface PortalCourseDetail extends PortalCourse {
  sessions: PortalCourseSession[];
}

export interface PortalEnrollment {
  id: string;
  course_id: string;
  course_title?: string;
  course_type?: string;
  status: string;
  paid_price_cents?: number;
  enrolled_at?: string;
  starts_at?: string;
  ends_at?: string;
  instructor_name?: string;
  is_virtual: boolean;
}

// ── Private Lessons Types ───────────────────────────────────────────────────

export interface PortalInstructor {
  id: string;
  display_name: string;
  bio?: string;
  photo_url?: string;
  specialties: string[];
  certifications: string[];
}

export interface PortalPrivateService {
  id: string;
  name: string;
  description?: string;
  duration_minutes: number;
  price_cents: number;
  is_virtual: boolean;
}

export interface PortalTimeSlot {
  start_time: string;
  end_time: string;
  duration_minutes: number;
}

export interface PortalPrivateBooking {
  id: string;
  starts_at?: string;
  ends_at?: string;
  status: string;
  is_virtual: boolean;
  zoom_join_url?: string;
  service_name?: string;
  duration_minutes?: number;
  instructor_name?: string;
  instructor_photo?: string;
  price_cents?: number;
  payment_status?: string;
  payment_url?: string;
  created_at?: string;
}

export const portalApi = {
  getProfile: () =>
    apiClient.get<PortalProfile>("/portal/me"),

  updateProfile: (data: PortalProfileUpdate) =>
    apiClient.put<PortalProfile>("/portal/me", data),

  getSchedule: (params?: {
    start?: string;
    end?: string;
    class_type_id?: string;
    instructor_id?: string;
    limit?: number;
  }) => {
    const qs = new URLSearchParams();
    if (params?.start) qs.set("start", params.start);
    if (params?.end) qs.set("end", params.end);
    if (params?.class_type_id) qs.set("class_type_id", params.class_type_id);
    if (params?.instructor_id) qs.set("instructor_id", params.instructor_id);
    if (params?.limit) qs.set("limit", String(params.limit));
    return apiClient.get<PortalSession[]>(`/portal/schedule?${qs}`);
  },

  getBookings: (params?: { upcoming_only?: boolean; limit?: number }) => {
    const qs = new URLSearchParams();
    if (params?.upcoming_only !== undefined)
      qs.set("upcoming_only", String(params.upcoming_only));
    if (params?.limit) qs.set("limit", String(params.limit));
    return apiClient.get<PortalBooking[]>(`/portal/bookings?${qs}`);
  },

  bookClass: (data: { session_id: string; membership_id?: string }) =>
    apiClient.post<PortalBooking>("/portal/bookings", data),

  cancelBooking: (bookingId: string) =>
    apiClient.delete(`/portal/bookings/${bookingId}`),

  getMemberships: () =>
    apiClient.get<PortalMembership[]>("/portal/memberships"),

  getAvailableMembershipTypes: () =>
    apiClient.get<PortalMembershipType[]>("/portal/membership-types"),

  getSuggestions: () =>
    apiClient.get<PortalSuggestion[]>("/portal/suggestions"),

  checkout: (data: { membership_type_id: string; success_url: string; cancel_url: string }) =>
    apiClient.post<{ data: { url: string; session_id: string } }>("/portal/checkout", data),

  getTransactions: (params?: { limit?: number }) => {
    const qs = new URLSearchParams();
    if (params?.limit) qs.set("limit", String(params.limit));
    return apiClient.get<PortalTransaction[]>(`/portal/transactions?${qs}`);
  },

  getBillingPortalUrl: (data: { return_url: string }) =>
    apiClient.post<{ data: { url: string } }>("/portal/billing-portal", data),

  // ── Workshops ─────────────────────────────────────────────────────────────

  getWorkshops: (params?: { type?: string }) => {
    const qs = new URLSearchParams();
    if (params?.type) qs.set("type", params.type);
    return apiClient.get<PortalCourse[]>(`/portal/workshops?${qs}`);
  },

  getWorkshopDetail: (courseId: string) =>
    apiClient.get<PortalCourseDetail>(`/portal/workshops/${courseId}`),

  getMyEnrollments: () =>
    apiClient.get<PortalEnrollment[]>("/portal/my-enrollments"),

  enrollInWorkshop: (courseId: string, data: { success_url: string; cancel_url: string }) =>
    apiClient.post<{ data: { enrolled?: boolean; enrollment_id?: string; url?: string; session_id?: string } }>(
      `/portal/workshops/${courseId}/enroll`,
      data,
    ),

  withdrawEnrollment: (enrollmentId: string) =>
    apiClient.delete(`/portal/workshops/enrollments/${enrollmentId}`),

  // ── Private Lessons ───────────────────────────────────────────────────────

  getInstructors: () =>
    apiClient.get<PortalInstructor[]>("/portal/private-lessons/instructors"),

  getInstructorServices: (instructorId: string) =>
    apiClient.get<PortalPrivateService[]>(`/portal/private-lessons/instructors/${instructorId}/services`),

  getAvailableSlots: (params: { instructor_id: string; service_id: string; date: string }) => {
    const qs = new URLSearchParams(params);
    return apiClient.get<PortalTimeSlot[]>(`/portal/private-lessons/slots?${qs}`);
  },

  bookPrivateSession: (data: {
    instructor_id: string;
    private_service_id: string;
    starts_at: string;
    intake_notes?: string;
    success_url: string;
    cancel_url: string;
  }) =>
    apiClient.post<{ data: { booked?: boolean; booking_id?: string; url?: string; session_id?: string } }>(
      "/portal/private-lessons/book",
      data,
    ),

  getMyPrivateBookings: (params?: { upcoming_only?: boolean }) => {
    const qs = new URLSearchParams();
    if (params?.upcoming_only !== undefined)
      qs.set("upcoming_only", String(params.upcoming_only));
    return apiClient.get<PortalPrivateBooking[]>(`/portal/private-lessons/my-bookings?${qs}`);
  },

  cancelPrivateBooking: (bookingId: string) =>
    apiClient.delete(`/portal/private-lessons/bookings/${bookingId}`),

  // ── Memberships (extended) ───────────────────────────────────────────────

  getMyMemberships: () =>
    apiClient.get<PortalMembership[]>("/portal/memberships"),

  getAvailableMemberships: () =>
    apiClient.get<PortalMembershipType[]>("/portal/memberships/available"),

  purchaseMembership: (data: {
    membership_type_id: string;
    success_url: string;
    cancel_url: string;
  }) =>
    apiClient.post<{ data: { url: string; session_id: string } }>(
      "/portal/memberships/purchase",
      data,
    ),

  purchaseMembershipWithGiftCard: (data: {
    member_id: string;
    membership_type_id: string;
    gift_card_code: string;
  }) =>
    apiClient.post<{ id: string }>(
      "/memberships/purchase-with-gift-card",
      data,
    ),

  pauseMembership: (membershipId: string) =>
    apiClient.post(`/portal/memberships/${membershipId}/pause`),

  resumeMembership: (membershipId: string) =>
    apiClient.post(`/portal/memberships/${membershipId}/resume`),

  cancelMembership: (membershipId: string) =>
    apiClient.post(`/portal/memberships/${membershipId}/cancel`),

  getSquareConfig: () =>
    apiClient.get<{ data: PortalSquareConfig }>("/portal/square-config"),

  purchaseMembershipSquare: (data: {
    membership_type_id: string;
    source_id: string;
    cardholder_name?: string;
  }) =>
    apiClient.post<{ data: { membership_id: string; subscription_id?: string; payment_id?: string; kind: "recurring" | "one_off" } }>(
      "/portal/memberships/purchase-square",
      data,
    ),

  switchMembershipToSquare: (data: {
    membership_id: string;
    source_id: string;
    cardholder_name?: string;
  }) =>
    apiClient.post<{ data: PortalSwitchToSquareResult }>(
      "/portal/memberships/switch-to-square",
      data,
    ),

  // ── Payments ────────────────────────────────────────────────────────────

  getPaymentHistory: () =>
    apiClient.get<PortalPayment[]>("/portal/payments"),

  getInvoicePdf: (invoiceId: string) =>
    apiClient.get<{ data: { url: string } }>(`/portal/invoices/${invoiceId}/pdf`),

  openPaymentMethodPortal: (data: { return_url: string }) =>
    apiClient.post<{ data: { url: string } }>("/portal/payment-methods/manage", data),

  saveCardSquare: (data: { source_id: string; cardholder_name?: string }) =>
    apiClient.post<{ data: { saved: boolean; card_id?: string; card_brand?: string; last_4?: string } }>(
      "/portal/payment-methods/save-square",
      data,
    ),

  // ── Waivers ─────────────────────────────────────────────────────────────────

  getWaiverStatus: () =>
    apiClient.get<{ data: PortalWaiverStatus }>("/portal/waiver"),

  signWaiver: (data: { template_id: string; signature_text: string }) =>
    apiClient.post("/portal/waiver/sign", data),
};

export interface PortalWaiverStatus {
  template: {
    id: string;
    title: string;
    content: string;
    version: number;
  } | null;
  status: {
    signed: boolean;
    expired: boolean;
    needs_resign: boolean;
    signed_at?: string;
    expires_at?: string;
  };
}
