import { apiClient } from "./api-client";

export interface Organization {
  id: string;
  slug: string;
  name: string;
  schema_name: string;
  status: string;
  plan_id: string | null;
  timezone: string;
  country: string;
  currency: string;
  primary_color: string | null;
  logo_url: string | null;
  custom_domain: string | null;
  stripe_account_id: string | null;
}

export const organizationsApi = {
  list: () => apiClient.get<Organization[]>("/organizations"),

  get: (slug: string) =>
    apiClient.get<Organization>(`/organizations/${slug}`),

  create: (data: { name: string; slug: string; timezone?: string }) =>
    apiClient.post<Organization>("/organizations", data),

  update: (orgSlug: string, data: { name?: string; timezone?: string; plan_id?: string }) =>
    apiClient.put<Organization>(`/organizations/${orgSlug}`, data),

  switchOrg: (orgSlug: string) =>
    apiClient.post<{
      access_token: string;
      refresh_token: string;
      token_type: string;
      expires_in: number;
    }>(`/auth/switch-org?org_slug=${encodeURIComponent(orgSlug)}`),

  inviteMember: (orgSlug: string, data: { email: string; role: string }) =>
    apiClient.post(`/organizations/${orgSlug}/members`, data),

  cancelAccount: (data: { reason?: string; feedback?: string }) =>
    apiClient.post<{
      status: string;
      message: string;
      cancellation_effective_at: string | null;
    }>("/organizations/cancel", data),

  reactivateAccount: () =>
    apiClient.post<{
      status: string;
      message: string;
      cancellation_effective_at: string | null;
    }>("/organizations/reactivate"),

  getCancellationStatus: () =>
    apiClient.get<{
      status: string;
      cancellation_reason: string | null;
      cancellation_feedback: string | null;
      cancellation_requested_at: string | null;
      cancellation_effective_at: string | null;
    }>("/organizations/cancellation-status"),
};
