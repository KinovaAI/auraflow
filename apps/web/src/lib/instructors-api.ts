import { apiClient } from "./api-client";

export interface Instructor {
  id: string;
  user_id?: string;
  display_name: string;
  bio?: string;
  photo_url?: string;
  specialties?: string[];
  certifications?: string[];
  email?: string;
  phone?: string;
  pay_rate_cents?: number;
  pay_type?: string;
  salary_cents?: number;
  tax_classification?: string;
  workshop_pay_percent?: number;
  private_session_pay_percent?: number;
  training_pay_percent?: number;
  color?: string;
  is_active: boolean;
}

export interface AvailabilitySlot {
  id?: string;
  day_of_week: number;
  start_time: string;
  end_time: string;
  is_recurring?: boolean;
  specific_date?: string;
  is_blocked?: boolean;
}

export const instructorsApi = {
  list: () => apiClient.get<Instructor[]>("/instructors"),

  get: (id: string) => apiClient.get<Instructor>(`/instructors/${id}`),

  create: (data: Partial<Instructor>) =>
    apiClient.post<Instructor>("/instructors", data),

  update: (id: string, data: Partial<Instructor>) =>
    apiClient.put<Instructor>(`/instructors/${id}`, data),

  deactivate: (id: string) => apiClient.delete(`/instructors/${id}`),

  getAvailability: (id: string) =>
    apiClient.get<AvailabilitySlot[]>(`/instructors/${id}/availability`),

  setAvailability: (id: string, slots: AvailabilitySlot[]) =>
    apiClient.put<AvailabilitySlot[]>(`/instructors/${id}/availability`, slots),

  getSchedule: (id: string, start: string, end: string) =>
    apiClient.get(`/instructors/${id}/schedule?start=${start}&end=${end}`),
};
