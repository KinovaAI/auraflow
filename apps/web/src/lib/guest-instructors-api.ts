import { apiClient } from "./api-client";

/**
 * Guest Instructors — 1099 contractors who teach WORKSHOPS only.
 * Fully separate from staff `instructors`. CA labor law forbids them
 * from teaching regular classes; the backend enforces this with a
 * CHECK constraint, and the workshop UI is the only surface where
 * a guest_instructor can be assigned.
 */
export interface GuestInstructor {
  id: string;
  studio_id?: string | null;
  name: string;
  bio?: string | null;
  photo_url?: string | null;
  email?: string | null;
  phone?: string | null;
  address_line1?: string | null;
  city?: string | null;
  state?: string | null;
  postal_code?: string | null;
  /** SSN/EIN for 1099 reporting. Encrypted at rest. */
  tax_id?: string | null;
  /** Default 60. Per-guest negotiable; the 1099 report uses
   *  whatever value is on the row. */
  revenue_share_percent_to_guest: number;
  notes?: string | null;
  is_active: boolean;
}

export const guestInstructorsApi = {
  list: (params: { active_only?: boolean; studio_id?: string } = {}) => {
    const qs = new URLSearchParams();
    if (params.active_only !== undefined) qs.set("active_only", String(params.active_only));
    if (params.studio_id) qs.set("studio_id", params.studio_id);
    const suffix = qs.toString() ? `?${qs}` : "";
    return apiClient.get<GuestInstructor[]>(`/guest-instructors${suffix}`);
  },

  get: (id: string) =>
    apiClient.get<GuestInstructor>(`/guest-instructors/${id}`),

  create: (data: {
    studio_id?: string;
    name: string;
    bio?: string;
    photo_url?: string;
    email?: string;
    phone?: string;
    address_line1?: string;
    city?: string;
    state?: string;
    postal_code?: string;
    tax_id?: string;
    revenue_share_percent_to_guest?: number;
    notes?: string;
  }) => apiClient.post<GuestInstructor>("/guest-instructors", data),

  update: (id: string, data: Partial<GuestInstructor>) =>
    apiClient.patch<GuestInstructor>(`/guest-instructors/${id}`, data),

  archive: (id: string) =>
    apiClient.delete(`/guest-instructors/${id}`),
};
