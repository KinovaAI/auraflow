import { apiClient } from "./api-client";

export interface Member {
  id: string;
  first_name: string;
  last_name: string;
  email: string;
  phone?: string;
  date_of_birth?: string;
  gender?: string;
  address_line1?: string;
  city?: string;
  state?: string;
  postal_code?: string;
  emergency_contact_name?: string;
  emergency_contact_phone?: string;
  notes?: string;
  tags?: string[];
  photo_url?: string;
  source?: string;
  referral_source?: string;
  total_visits: number;
  lifetime_revenue_cents: number;
  is_active: boolean;
  member_number?: string;
  email_opt_in?: boolean;
  sms_opt_in?: boolean;
  stripe_coupon_id?: string | null;
  churn_risk_flagged_at?: string | null;
  // Square saved card-on-file (populated by POS sale or switch-to-square)
  square_customer_id?: string | null;
  square_card_on_file_id?: string | null;
  square_card_on_file_brand?: string | null;
  square_card_on_file_last4?: string | null;
  square_card_on_file_exp_month?: number | null;
  square_card_on_file_exp_year?: number | null;
  square_card_on_file_saved_at?: string | null;
}

export interface MemberNote {
  id: string;
  member_id: string;
  author_id: string;
  note: string;
  is_pinned: boolean;
  created_at: string;
}

export interface BookingHistory {
  id: string;
  class_session_id: string;
  session_title?: string;
  class_type_name?: string;
  class_category?: string;
  starts_at: string;
  ends_at?: string;
  status: string;
  booked_at: string;
  cancelled_at?: string;
  checked_in_at?: string;
  cancellation_reason?: string;
  late_cancel: boolean;
}

export interface MemberFilterParams {
  search?: string;
  active_only?: boolean;
  membership_status?: string;
  has_failed_payments?: boolean;
  churn_risk?: boolean;
  min_visits?: number;
  max_visits?: number;
  inactive_weeks?: number;
  joined_after?: string;
  joined_before?: string;
  min_revenue?: number;
  has_coupon?: boolean;
  sort_by?: string;
  sort_dir?: string;
  limit?: number;
  offset?: number;
}

export const membersApi = {
  list: (params?: MemberFilterParams) => {
    const qs = new URLSearchParams();
    if (params?.search) qs.set("search", params.search);
    if (params?.active_only !== undefined) qs.set("active_only", String(params.active_only));
    if (params?.membership_status) qs.set("membership_status", params.membership_status);
    if (params?.has_failed_payments !== undefined) qs.set("has_failed_payments", String(params.has_failed_payments));
    if (params?.churn_risk !== undefined) qs.set("churn_risk", String(params.churn_risk));
    if (params?.min_visits !== undefined) qs.set("min_visits", String(params.min_visits));
    if (params?.max_visits !== undefined) qs.set("max_visits", String(params.max_visits));
    if (params?.inactive_weeks !== undefined) qs.set("inactive_weeks", String(params.inactive_weeks));
    if (params?.joined_after) qs.set("joined_after", params.joined_after);
    if (params?.joined_before) qs.set("joined_before", params.joined_before);
    if (params?.min_revenue !== undefined) qs.set("min_revenue", String(params.min_revenue));
    if (params?.has_coupon !== undefined) qs.set("has_coupon", String(params.has_coupon));
    if (params?.sort_by) qs.set("sort_by", params.sort_by);
    if (params?.sort_dir) qs.set("sort_dir", params.sort_dir);
    if (params?.limit) qs.set("limit", String(params.limit));
    if (params?.offset) qs.set("offset", String(params.offset));
    return apiClient.get<Member[]>(`/members?${qs}`);
  },

  get: (id: string) => apiClient.get<Member>(`/members/${id}`),

  create: (data: Partial<Member>) =>
    apiClient.post<Member>("/members", data),

  update: (id: string, data: Partial<Member>) =>
    apiClient.put<Member>(`/members/${id}`, data),

  deactivate: (id: string) => apiClient.delete(`/members/${id}`),

  // Notes
  listNotes: (memberId: string) =>
    apiClient.get<MemberNote[]>(`/members/${memberId}/notes`),

  addNote: (memberId: string, note: string, isPinned: boolean = false) =>
    apiClient.post<MemberNote>(`/members/${memberId}/notes`, {
      note,
      is_pinned: isPinned,
    }),

  deleteNote: (memberId: string, noteId: string) =>
    apiClient.delete(`/members/${memberId}/notes/${noteId}`),

  // Booking history
  getBookings: (memberId: string) =>
    apiClient.get<BookingHistory[]>(`/members/${memberId}/bookings`),

  // Health data
  getHealthData: (memberId: string) =>
    apiClient.get(`/members/${memberId}/health-data`),

  setHealthData: (memberId: string, data: Record<string, string | null>) =>
    apiClient.put(`/members/${memberId}/health-data`, data),

  // ── Dashboard slices ──
  getCredits: (memberId: string, includeUsed = false) =>
    apiClient.get<MemberCredit[]>(
      `/members/${memberId}/credits?include_used=${includeUsed}`,
    ),

  grantCredit: (memberId: string, body: CreditGrantRequest) =>
    apiClient.post<MemberCredit>(`/members/${memberId}/credits`, body),

  revokeCredit: (memberId: string, creditId: string, reason?: string) =>
    apiClient.post(
      `/members/${memberId}/credits/${creditId}/revoke${
        reason ? `?reason=${encodeURIComponent(reason)}` : ""
      }`,
      {},
    ),

  getPayments: (memberId: string) =>
    apiClient.get<PaymentRecord[]>(`/members/${memberId}/payments`),

  getPrivateSessions: (memberId: string) =>
    apiClient.get<PrivateSessionRecord[]>(
      `/members/${memberId}/private-sessions`,
    ),

  getMemberships: (memberId: string) =>
    apiClient.get<MemberMembershipRecord[]>(`/members/${memberId}/memberships`),
};

// ── Dashboard types ──

export interface MemberCredit {
  id: string;
  source:
    | "instructor_cancellation"
    | "courtesy"
    | "refund_to_credit"
    | "gift"
    | "manual_grant";
  source_ref_id?: string | null;
  service_filter?: "private_session" | "class" | "workshop" | null;
  amount_cents: number;
  expires_at?: string | null;
  used_at?: string | null;
  used_booking_id?: string | null;
  used_booking_table?: string | null;
  notes?: string | null;
  granted_by_user_id?: string | null;
  created_at: string;
}

export interface CreditGrantRequest {
  amount_cents: number;
  source: "courtesy" | "manual_grant" | "refund_to_credit" | "gift";
  service_filter?: "private_session" | "class" | "workshop" | null;
  expiry_days?: number | null;
  notes?: string | null;
}

export interface PaymentRecord {
  id: string;
  type?: string;
  amount_cents?: number;
  fee_cents?: number;
  net_amount_cents?: number;
  status?: string;
  description?: string;
  stripe_payment_intent_id?: string;
  stripe_charge_id?: string;
  membership_type_name?: string;
  created_at: string;
}

export interface PrivateSessionRecord {
  id: string;
  service_name?: string;
  duration_minutes?: number;
  instructor_name?: string;
  starts_at: string;
  ends_at?: string;
  status: string;
  is_virtual?: boolean;
  price_cents?: number;
  payment_status?: string;
  cancelled_at?: string | null;
  cancellation_reason?: string | null;
  cancelled_by_role?: "instructor" | "member" | "staff" | null;
  transaction_id?: string | null;
  created_at: string;
}

export interface MemberMembershipRecord {
  id: string;
  type_name?: string;
  type_category?: string;
  type_price_cents?: number;
  status: string;
  classes_remaining?: number | null;
  starts_at?: string;
  ends_at?: string;
  cancelled_at?: string | null;
  frozen_at?: string | null;
  stripe_subscription_id?: string | null;
  created_at: string;
}
