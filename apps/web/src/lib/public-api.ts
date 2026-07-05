import axios from "axios";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// Public API client — no auth token needed
const publicClient = axios.create({
  baseURL: `${API_BASE_URL}/api/v1/public`,
  headers: { "Content-Type": "application/json" },
});

export interface PublicSession {
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
}

export interface PublicClassType {
  id: string;
  name: string;
  description?: string;
  duration_minutes: number;
  category?: string;
  level?: string;
  color?: string;
  image_url?: string;
}

export interface PublicInstructor {
  id: string;
  display_name: string;
  bio?: string;
  photo_url?: string;
  specialties?: string[];
}

export const publicApi = {
  getSchedule: (
    orgSlug: string,
    params?: {
      start?: string;
      end?: string;
      class_type_id?: string;
      instructor_id?: string;
      limit?: number;
    }
  ) => {
    const qs = new URLSearchParams();
    if (params?.start) qs.set("start", params.start);
    if (params?.end) qs.set("end", params.end);
    if (params?.class_type_id) qs.set("class_type_id", params.class_type_id);
    if (params?.instructor_id) qs.set("instructor_id", params.instructor_id);
    if (params?.limit) qs.set("limit", String(params.limit));
    return publicClient.get<PublicSession[]>(`/${orgSlug}/schedule?${qs}`);
  },

  getClassTypes: (orgSlug: string) =>
    publicClient.get<PublicClassType[]>(`/${orgSlug}/class-types`),

  getInstructors: (orgSlug: string) =>
    publicClient.get<PublicInstructor[]>(`/${orgSlug}/instructors`),
};
