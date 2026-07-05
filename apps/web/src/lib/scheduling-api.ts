import { apiClient } from "./api-client";

// ── Class Types ─────────────────────────────────────────────────────────────

export interface ClassType {
  id: string;
  name: string;
  description?: string;
  duration_minutes?: number;
  color?: string;
  capacity?: number;
  level?: string;
  tags?: string[];
  category?: string;
  is_active: boolean;
}

export const classTypesApi = {
  list: (studioId: string) =>
    apiClient.get<ClassType[]>(`/scheduling/class-types?studio_id=${studioId}`),

  create: (data: {
    studio_id: string;
    name: string;
    description?: string;
    duration_minutes?: number;
    color?: string;
    capacity?: number;
    level?: string;
    tags?: string[];
    category?: string;
  }) => apiClient.post<ClassType>("/scheduling/class-types", data),

  update: (id: string, data: Partial<ClassType>) =>
    apiClient.put<ClassType>(`/scheduling/class-types/${id}`, data),

  deactivate: (id: string) =>
    apiClient.delete(`/scheduling/class-types/${id}`),
};

// ── Series ──────────────────────────────────────────────────────────────────

export interface Series {
  id: string;
  studio_id: string;
  class_type_id: string;
  instructor_id?: string;
  room_id?: string;
  title: string;
  rrule: string;
  start_time: string;
  duration_minutes: number;
  capacity?: number;
  effective_from: string;
  effective_until?: string;
  timezone: string;
  is_virtual: boolean;
  auto_record: boolean;
  is_active: boolean;
}

export const seriesApi = {
  list: (studioId: string) =>
    apiClient.get<Series[]>(`/scheduling/series?studio_id=${studioId}`),

  create: (data: {
    studio_id: string;
    class_type_id: string;
    instructor_id?: string;
    room_id?: string;
    title: string;
    rrule: string;
    start_time: string;
    duration_minutes: number;
    capacity?: number;
    effective_from: string;
    effective_until?: string;
    timezone?: string;
    expand_weeks?: number;
    is_virtual?: boolean;
    is_community?: boolean;
    auto_record?: boolean;
  }) =>
    apiClient.post<{ series: Series; sessions_created: number }>(
      "/scheduling/series",
      data
    ),

  expand: (id: string, weeks: number) =>
    apiClient.post<{ sessions_created: number }>(
      `/scheduling/series/${id}/expand?weeks=${weeks}`
    ),

  delete: (id: string) => apiClient.delete(`/scheduling/series/${id}`),
};

// ── Sessions ────────────────────────────────────────────────────────────────

export interface Session {
  id: string;
  studio_id: string;
  class_type_id: string;
  series_id?: string;
  instructor_id?: string;
  room_id?: string;
  title: string;
  description?: string;
  starts_at: string;
  ends_at: string;
  capacity?: number;
  status: string;
  class_type_name?: string;
  instructor_name?: string;
  room_name?: string;
  booked_count?: number;
  waitlist_count?: number;
  is_virtual?: boolean;
  /** Class modality: in_studio | virtual | hybrid. Drives eligibility. */
  modality?: "in_studio" | "virtual" | "hybrid";
  zoom_join_url?: string;
  zoom_password?: string;
  auto_record?: boolean;
  is_community?: boolean;
  recording_status?: string;
  video_id?: string;
}

export interface RosterEntry {
  id: string;
  member_id: string;
  class_session_id: string;
  status: string;
  source: string;
  booked_at?: string;
  checked_in_at?: string;
  waitlist_position?: number;
  membership_id?: string;
  notes?: string;
  guest_name?: string;
  guest_email?: string;
  first_name?: string;
  last_name?: string;
  member_email?: string;
  phone?: string;
}

export const sessionsApi = {
  list: (params: {
    studio_id: string;
    start: string;
    end: string;
    instructor_id?: string;
    class_type_id?: string;
  }) => {
    const qs = new URLSearchParams(params as Record<string, string>);
    return apiClient.get<Session[]>(`/scheduling/sessions?${qs}`);
  },

  get: (id: string) => apiClient.get<Session>(`/scheduling/sessions/${id}`),

  create: (data: {
    studio_id: string;
    class_type_id: string;
    instructor_id?: string;
    room_id?: string;
    title: string;
    starts_at: string;
    ends_at: string;
    capacity?: number;
    is_virtual?: boolean;
    is_community?: boolean;
    auto_record?: boolean;
    modality?: "in_studio" | "virtual" | "hybrid";
  }) => apiClient.post<Session>("/scheduling/sessions", data),

  update: (id: string, data: Partial<Session>) =>
    apiClient.put<Session>(`/scheduling/sessions/${id}`, data),

  cancel: (id: string, reason?: string) => {
    const qs = reason ? `?reason=${encodeURIComponent(reason)}` : "";
    return apiClient.delete(`/scheduling/sessions/${id}${qs}`);
  },

  getRoster: (sessionId: string) =>
    apiClient.get<RosterEntry[]>(
      `/scheduling/sessions/${sessionId}/roster`
    ),
};

export const bookingsApi = {
  create: (data: {
    member_id: string;
    class_session_id: string;
    source?: string;
    membership_id?: string;
    notes?: string;
    guest_name?: string;
    guest_email?: string;
  }) => apiClient.post<RosterEntry>("/scheduling/bookings", data),

  checkIn: (bookingId: string) =>
    apiClient.post<RosterEntry>(
      `/scheduling/bookings/${bookingId}/check-in`
    ),

  markNoShow: (bookingId: string) =>
    apiClient.post<RosterEntry>(
      `/scheduling/bookings/${bookingId}/no-show`
    ),

  cancel: (bookingId: string, opts?: { lateCancel?: boolean; reason?: string }) => {
    const params = new URLSearchParams();
    if (opts?.lateCancel) params.set("late_cancel", "true");
    if (opts?.reason) params.set("reason", opts.reason);
    const qs = params.toString();
    return apiClient.delete<void>(
      `/scheduling/bookings/${bookingId}${qs ? `?${qs}` : ""}`
    );
  },
};

// ── Rooms ───────────────────────────────────────────────────────────────────

export interface Room {
  id: string;
  studio_id: string;
  name: string;
  capacity?: number;
  color?: string;
  is_active: boolean;
}

export const roomsApi = {
  list: (studioId: string) =>
    apiClient.get<Room[]>(`/studios/${studioId}/rooms`),

  create: (studioId: string, data: { name: string; capacity?: number; color?: string }) =>
    apiClient.post<Room>(`/studios/${studioId}/rooms`, data),

  update: (studioId: string, id: string, data: Partial<Room>) =>
    apiClient.put<Room>(`/studios/${studioId}/rooms/${id}`, data),

  delete: (studioId: string, id: string) =>
    apiClient.delete(`/studios/${studioId}/rooms/${id}`),
};

// ── Studios ─────────────────────────────────────────────────────────────────

export interface Studio {
  id: string;
  name: string;
  slug: string;
  address_line1?: string;
  city?: string;
  state?: string;
  postal_code?: string;
  phone?: string;
  email?: string;
  timezone?: string;
  is_virtual?: boolean;
  cancellation_policy_hours?: number;
  late_cancel_fee_cents?: number;
  booking_window_days?: number;
  allow_guest_booking?: boolean;
  is_active: boolean;
}

export const studiosApi = {
  list: () => apiClient.get<Studio[]>("/studios"),

  get: (id: string) => apiClient.get<Studio>(`/studios/${id}`),

  create: (data: Partial<Studio>) =>
    apiClient.post<Studio>("/studios", data),

  update: (id: string, data: Partial<Studio>) =>
    apiClient.put<Studio>(`/studios/${id}`, data),

  deactivate: (id: string) => apiClient.delete(`/studios/${id}`),
};

// ── Studio Staff Assignments ───────────────────────────────────────────────

export interface StudioStaffMember {
  user_id: string;
  email: string;
  first_name: string;
  last_name: string;
  role: string;
  is_primary: boolean;
}

export const studioStaffApi = {
  list: (studioId: string) =>
    apiClient.get<{ data: StudioStaffMember[] }>(`/studios/${studioId}/staff`),

  assign: (studioId: string, data: { user_id: string; role: string }) =>
    apiClient.post(`/studios/${studioId}/staff`, data),

  updateRole: (studioId: string, userId: string, data: { role: string }) =>
    apiClient.put(`/studios/${studioId}/staff/${userId}`, data),

  remove: (studioId: string, userId: string) =>
    apiClient.delete(`/studios/${studioId}/staff/${userId}`),
};
