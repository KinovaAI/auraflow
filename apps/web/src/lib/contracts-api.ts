import { apiClient } from "./api-client";

export interface PreparedContract {
  id: string;
  status: string;
  signing_token: string;
  effective_date: string;
  view_count?: number;
  email_sent_at?: string | null;
  first_viewed_at?: string | null;
  signed_at?: string | null;
  reminder_sent_at?: string | null;
  voided_at?: string | null;
  void_reason?: string | null;
}

export interface WorkshopSessionIn {
  starts_at: string;
  ends_at: string;
  location?: string | null;
  is_virtual?: boolean;
  title?: string | null;
}

export interface CreateGuestWorkshopIn {
  workshop_name: string;
  // New shape: pass one entry per session.
  sessions?: WorkshopSessionIn[];
  allow_duplicate?: boolean;
  // Back-compat single-session shape — used if sessions is omitted.
  workshop_starts_at?: string;
  workshop_ends_at?: string;
  workshop_cost_cents: number;
  instructor_share_percent: number;
  location?: string | null;
  capacity?: number | null;
  min_enrollment?: number | null;
  guest_instructor_id?: string | null;
  new_guest_name?: string | null;
  new_guest_email?: string | null;
  new_guest_phone?: string | null;
}

export interface CreateGuestWorkshopResult {
  course_id: string;
  course_title: string;
  guest_instructor_id: string;
  guest_instructor_name: string;
  instructor_share_percent: number;
  studio_share_percent: number;
  contract: PreparedContract;
}

export const contractsApi = {
  createGuestWorkshop: (body: CreateGuestWorkshopIn) =>
    apiClient.post<{ data: CreateGuestWorkshopResult; signing_url: string }>(
      "/contracts/create-guest-workshop",
      body,
    ).then((r) => r.data),

  prepare: (body: { course_id: string; compensation: Record<string, unknown> }) =>
    apiClient.post<{ data: PreparedContract; signing_url: string }>(
      "/contracts/prepare",
      body,
    ).then((r) => r.data),

  get: (id: string) =>
    apiClient.get<{ data: PreparedContract }>(`/contracts/${id}`).then((r) => r.data.data),

  listByCourse: (courseId: string) =>
    apiClient.get<{ data: PreparedContract[] }>(`/contracts/by-course/${courseId}`)
      .then((r) => r.data.data),

  void: (id: string, reason: string) =>
    apiClient.post<{ data: { id: string; status: string } }>(`/contracts/${id}/void`, { reason })
      .then((r) => r.data.data),

  pdfUrl: (id: string): string =>
    `${apiClient.defaults.baseURL || ""}/contracts/${id}/pdf`,
};
