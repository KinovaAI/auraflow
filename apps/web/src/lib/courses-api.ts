import { apiClient } from "./api-client";

// ── Course Types ────────────────────────────────────────────────────────────

export interface Course {
  id: string;
  studio_id?: string;
  title: string;
  description?: string;
  type: "workshop" | "course" | "teacher_training" | "retreat";
  status: "draft" | "published" | "in_progress" | "completed" | "cancelled";
  instructor_id?: string;
  instructor_name?: string;
  /** 1099 contractor instructor — only valid on workshops. */
  guest_instructor_id?: string;
  guest_instructor_name?: string;
  guest_instructor_photo_url?: string;
  guest_instructor_bio?: string;
  /** Default 60. Per-guest negotiable. Used by the 1099 report. */
  revenue_share_percent_to_guest?: number;
  price_cents: number;
  early_bird_price_cents?: number;
  early_bird_deadline?: string;
  capacity?: number;
  min_enrollment?: number;
  enrolled_count?: number;
  location?: string;
  is_virtual: boolean;
  image_url?: string;
  prerequisites?: string;
  registration_opens?: string;
  registration_closes?: string;
  starts_at?: string;
  ends_at?: string;
  created_at: string;
  updated_at?: string;
  /** Embedded flyer (base64 data URL). */
  flyer_data_url?: string | null;
  flyer_image_mime?: string | null;
}

export interface CourseCreate {
  studio_id?: string;
  title: string;
  description?: string;
  type?: string;
  instructor_id?: string;
  /** Workshops only. Mutually exclusive with instructor_id. */
  guest_instructor_id?: string;
  price_cents?: number;
  early_bird_price_cents?: number;
  early_bird_deadline?: string;
  capacity?: number;
  min_enrollment?: number;
  location?: string;
  is_virtual?: boolean;
  image_url?: string;
  /** Set to data:image/...;base64,... to upload a flyer. */
  flyer_data_url?: string;
  prerequisites?: string;
  registration_opens?: string;
  registration_closes?: string;
  starts_at?: string;
  ends_at?: string;
}

export interface CourseUpdate {
  title?: string;
  description?: string;
  type?: string;
  instructor_id?: string;
  guest_instructor_id?: string;
  price_cents?: number;
  early_bird_price_cents?: number;
  early_bird_deadline?: string;
  capacity?: number;
  min_enrollment?: number;
  location?: string;
  is_virtual?: boolean;
  image_url?: string;
  /** Set to data:image/...;base64,... to upload, "" to clear, undefined = no change. */
  flyer_data_url?: string;
  prerequisites?: string;
  starts_at?: string;
  ends_at?: string;
}

// ── Session Types ───────────────────────────────────────────────────────────

export interface CourseSession {
  id: string;
  course_id: string;
  title?: string;
  starts_at: string;
  ends_at: string;
  location?: string;
  is_virtual: boolean;
  created_at: string;
}

export interface SessionCreate {
  title?: string;
  starts_at: string;
  ends_at: string;
  location?: string;
  is_virtual?: boolean;
}

export interface SessionUpdate {
  title?: string;
  starts_at?: string;
  ends_at?: string;
  location?: string;
  is_virtual?: boolean;
}

// ── Enrollment Types ────────────────────────────────────────────────────────

export interface Enrollment {
  id: string;
  course_id: string;
  member_id: string;
  member_name?: string;
  first_name?: string;
  last_name?: string;
  email?: string;
  phone?: string;
  status: string;
  enrolled_at: string;
  withdrawn_at?: string;
}

// ── Attendance Types ────────────────────────────────────────────────────────

export interface AttendanceRecord {
  id: string;
  session_id: string;
  member_id: string;
  member_name?: string;
  status: string;
  recorded_at: string;
}

// ── Courses API ─────────────────────────────────────────────────────────────

export const coursesApi = {
  // Course CRUD
  createCourse: (data: CourseCreate) =>
    apiClient.post<{ data: Course }>("/courses", data),

  listCourses: (params?: { status?: string; type?: string }) =>
    apiClient.get<{ data: Course[] }>("/courses", { params }),

  getCourse: (id: string) =>
    apiClient.get<{ data: Course }>(`/courses/${id}`),

  updateCourse: (id: string, data: CourseUpdate) =>
    apiClient.put<{ data: Course }>(`/courses/${id}`, data),

  deleteCourse: (id: string) =>
    apiClient.delete<{ data: { deleted: boolean } }>(`/courses/${id}`),

  // Course lifecycle
  publishCourse: (id: string) =>
    apiClient.post<{ data: Course }>(`/courses/${id}/publish`),

  cancelCourse: (id: string) =>
    apiClient.post<{ data: Course }>(`/courses/${id}/cancel`),

  completeCourse: (id: string) =>
    apiClient.post<{ data: Course }>(`/courses/${id}/complete`),

  // Sessions
  addSession: (courseId: string, data: SessionCreate) =>
    apiClient.post<{ data: CourseSession }>(
      `/courses/${courseId}/sessions`,
      data
    ),

  listSessions: (courseId: string) =>
    apiClient.get<{ data: CourseSession[] }>(
      `/courses/${courseId}/sessions`
    ),

  // All upcoming sessions across published courses with the course title
  // joined in. Used by the schedule page calendar so each workshop
  // session renders as its own time block (vs the course-level starts_at
  // /ends_at which span the whole series).
  listUpcomingSessions: (days: number = 30) =>
    apiClient.get<{ data: Array<CourseSession & { course_title?: string; course_type?: string; instructor_id?: string }> }>(
      "/courses/sessions/upcoming",
      { params: { days } }
    ),

  updateSession: (sessionId: string, data: SessionUpdate) =>
    apiClient.put<{ data: CourseSession }>(
      `/courses/sessions/${sessionId}`,
      data
    ),

  deleteSession: (sessionId: string) =>
    apiClient.delete<{ data: { deleted: boolean } }>(
      `/courses/sessions/${sessionId}`
    ),

  // Enrollment
  enrollMember: (courseId: string, memberId: string) =>
    apiClient.post<{ data: Enrollment }>(`/courses/${courseId}/enroll`, {
      member_id: memberId,
    }),

  listEnrollments: (courseId: string) =>
    apiClient.get<{ data: Enrollment[] }>(
      `/courses/${courseId}/enrollments`
    ),

  withdrawEnrollment: (enrollmentId: string) =>
    apiClient.post<{ data: Enrollment }>(
      `/courses/enrollments/${enrollmentId}/withdraw`
    ),

  // Attendance
  recordAttendance: (
    sessionId: string,
    memberId: string,
    status: string = "attended"
  ) =>
    apiClient.post<{ data: AttendanceRecord }>(
      `/courses/sessions/${sessionId}/attendance`,
      { member_id: memberId, status }
    ),

  getSessionAttendance: (sessionId: string) =>
    apiClient.get<{ data: AttendanceRecord[] }>(
      `/courses/sessions/${sessionId}/attendance`
    ),
};
