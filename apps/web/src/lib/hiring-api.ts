import { apiClient } from "./api-client";

export type ApplicationStatus =
  | "new" | "reviewed" | "shortlisted" | "interviewed" | "offer" | "hired" | "rejected";

export interface JobApplicationListItem {
  id: string;
  first_name: string;
  last_name: string;
  email: string;
  phone?: string | null;
  position_type: string;
  position_title?: string | null;
  status: ApplicationStatus;
  rating?: number | null;
  assigned_reviewer_id?: string | null;
  reviewed_at?: string | null;
  hired_at?: string | null;
  created_at: string;
  document_count: number;
}

export interface JobApplicationDocument {
  id: string;
  doc_type: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  uploaded_at: string;
}

export interface JobApplicationEvent {
  id: string;
  event_type: string;
  from_status?: string | null;
  to_status?: string | null;
  note?: string | null;
  actor_user_id?: string | null;
  created_at: string;
}

export interface CertificationItem {
  name?: string; issuer?: string; issued_on?: string; expires_on?: string;
}
export interface WorkHistoryItem {
  employer?: string; title?: string; dates?: string; contact?: string;
}
export interface ReferenceItem {
  name?: string; relationship?: string; phone?: string; email?: string;
}

export interface JobApplicationDetail extends JobApplicationListItem {
  address_line1?: string | null;
  address_line2?: string | null;
  city?: string | null;
  state?: string | null;
  postal_code?: string | null;
  employment_type?: string | null;
  availability?: string | null;
  earliest_start_date?: string | null;
  desired_pay_text?: string | null;
  authorized_to_work: boolean;
  over_18: boolean;
  years_experience?: number | null;
  experience_seniors?: string | null;
  experience_injuries?: string | null;
  experience_pain?: string | null;
  specialties: string[];
  work_history: WorkHistoryItem[];
  certifications: CertificationItem[];
  yoga_alliance_number?: string | null;
  yoga_alliance_level?: string | null;
  cpr_first_aid: boolean;
  liability_insurance: boolean;
  references: ReferenceItem[];
  cover_letter?: string | null;
  hear_about_us?: string | null;
  rejection_reason?: string | null;
  hired_user_id?: string | null;
  hired_studio_id?: string | null;
  hired_role?: string | null;
  documents: JobApplicationDocument[];
  events: JobApplicationEvent[];
}

export interface HireRequest {
  role: "instructor" | "front_desk" | "admin";
  studio_id?: string;
  pay_rate_cents?: number;
  pay_type?: string;
  tax_classification?: string;
  title?: string;
  department?: string;
  hire_date?: string;
  send_w4_email?: boolean;
}

export interface HireResult {
  user_id: string;
  instructor_id?: string | null;
  role: string;
  studio_id?: string | null;
  w4_token: string;
  w4_status: string;
  w4_email_sent?: boolean;
}

export interface OnboardingDocument {
  id: string;
  doc_type: string;
  kind: "form_fillable" | "acknowledgment";
  title: string;
  status: "pending" | "completed";
  signed_at?: string | null;
  has_pdf: boolean;
}

export interface OnboardingPacket {
  id: string;
  status: "pending" | "completed";
  documents: OnboardingDocument[];
}

export interface De34Pending {
  user_id: string;
  name: string;
  role?: string | null;
  start_date?: string | null;
  due_date?: string | null;
  days_remaining?: number | null;
  overdue: boolean;
}

export interface ApplicationFilters {
  status?: string;
  q?: string;
  reviewer_id?: string;
}

export interface EmployerProfile {
  legal_name?: string | null;
  dba_name?: string | null;
  ein?: string | null;
  edd_account_number?: string | null;
  address_line1?: string | null;
  address_line2?: string | null;
  city?: string | null;
  state?: string | null;
  postal_code?: string | null;
  phone?: string | null;
  wc_carrier_name?: string | null;
  wc_policy_number?: string | null;
  wc_carrier_phone?: string | null;
  wc_policy_effective?: string | null;
  pay_schedule?: string | null;
  regular_payday?: string | null;
  overtime_basis?: string | null;
  sick_leave_policy?: string | null;
}

export const hiringApi = {
  list: (params?: ApplicationFilters) => {
    const qs = new URLSearchParams();
    if (params?.status) qs.set("status", params.status);
    if (params?.q) qs.set("q", params.q);
    if (params?.reviewer_id) qs.set("reviewer_id", params.reviewer_id);
    return apiClient
      .get<{ data: JobApplicationListItem[]; count: number }>(`/hiring?${qs}`)
      .then((r) => r.data.data);
  },

  get: (id: string) =>
    apiClient
      .get<{ data: JobApplicationDetail }>(`/hiring/${id}`)
      .then((r) => r.data.data),

  update: (
    id: string,
    data: { status?: string; rating?: number; assigned_reviewer_id?: string; rejection_reason?: string },
  ) =>
    apiClient
      .patch<{ data: JobApplicationDetail }>(`/hiring/${id}`, data)
      .then((r) => r.data.data),

  addNote: (id: string, note: string) =>
    apiClient.post(`/hiring/${id}/notes`, { note }),

  hire: (id: string, data: HireRequest) =>
    apiClient
      .post<{ data: HireResult }>(`/hiring/${id}/hire`, data)
      .then((r) => r.data.data),

  getEmployeeOnboarding: (userId: string) =>
    apiClient
      .get<{ data: OnboardingPacket }>(`/hiring/employees/${userId}/onboarding`)
      .then((r) => r.data.data),

  openOnboardingDocPdf: async (userId: string, docId: string) => {
    const res = await apiClient.get(
      `/hiring/employees/${userId}/onboarding/documents/${docId}.pdf`,
      { responseType: "blob" },
    );
    const url = URL.createObjectURL(res.data as Blob);
    window.open(url, "_blank");
  },

  getDe34Pending: () =>
    apiClient
      .get<{ data: De34Pending[] }>("/hiring/de34/pending")
      .then((r) => r.data.data),

  markDe34Filed: (userId: string) =>
    apiClient.post(`/hiring/employees/${userId}/de34/mark-filed`, {}),

  openDe34Pdf: async (userId: string) => {
    const res = await apiClient.get(`/hiring/employees/${userId}/de34.pdf`, {
      responseType: "blob",
    });
    const url = URL.createObjectURL(res.data as Blob);
    window.open(url, "_blank");
  },

  getEmployerProfile: () =>
    apiClient
      .get<{ data: EmployerProfile | null }>("/hiring/employer-profile")
      .then((r) => r.data.data),

  updateEmployerProfile: (data: EmployerProfile) =>
    apiClient
      .put<{ data: EmployerProfile }>("/hiring/employer-profile", data)
      .then((r) => r.data.data),

  // Authed blob fetches — open in a new tab via an object URL (a bare <a href>
  // wouldn't carry the JWT the apiClient interceptor injects).
  openDocument: async (applicationId: string, docId: string) => {
    const res = await apiClient.get(
      `/hiring/${applicationId}/documents/${docId}`, { responseType: "blob" },
    );
    const url = URL.createObjectURL(res.data as Blob);
    window.open(url, "_blank");
  },
};
