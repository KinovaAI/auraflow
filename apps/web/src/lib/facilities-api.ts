import { apiClient } from "./api-client";

// ── Types ────────────────────────────────────────────────────────────────────

export interface RoomDetail {
  id: string;
  studio_id: string;
  name: string;
  capacity: number | null;
  color: string;
  sort_order: number;
  is_active: boolean;
  description: string | null;
  room_type: string;
  amenities: string[];
  photo_url: string | null;
  hourly_rate_cents: number | null;
  max_classes_per_day: number | null;
  floor_area_sqft: number | null;
  setup_instructions: string | null;
  is_bookable: boolean;
  equipment_count: number;
  sessions_today: number;
  created_at: string;
  updated_at: string;
}

export interface RoomAvailabilitySlot {
  session_id: string;
  title: string;
  starts_at: string;
  ends_at: string;
  instructor_name: string | null;
}

export interface Equipment {
  id: string;
  studio_id: string;
  room_id: string | null;
  room_name?: string;
  name: string;
  category: string;
  description: string | null;
  quantity: number;
  purchase_date: string | null;
  purchase_cost_cents: number | null;
  condition: string;
  warranty_expiry: string | null;
  serial_number: string | null;
  photo_url: string | null;
  notes: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface MaintenanceRequest {
  id: string;
  studio_id: string;
  room_id: string | null;
  room_name?: string;
  equipment_id: string | null;
  equipment_name?: string;
  title: string;
  description: string | null;
  priority: string;
  status: string;
  category: string;
  requested_by: string | null;
  assigned_to: string | null;
  estimated_cost_cents: number | null;
  actual_cost_cents: number | null;
  scheduled_date: string | null;
  completed_at: string | null;
  completion_notes: string | null;
  photos: string[];
  created_at: string;
  updated_at: string;
}

export interface MaintenanceStats {
  open: number;
  in_progress: number;
  completed_this_month: number;
  overdue_schedules: number;
}

export interface FacilitySchedule {
  id: string;
  studio_id: string;
  room_id: string | null;
  room_name?: string;
  equipment_id: string | null;
  equipment_name?: string;
  schedule_type: string;
  title: string;
  description: string | null;
  rrule: string | null;
  assigned_to: string | null;
  last_completed_at: string | null;
  next_due_at: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface ScheduleCompletion {
  id: string;
  schedule_id: string;
  completed_by: string | null;
  completed_at: string;
  notes: string | null;
  photos: string[];
}

// ── API ──────────────────────────────────────────────────────────────────────

export const facilitiesApi = {
  // Enhanced Rooms
  listRooms: (studioId: string) =>
    apiClient.get<{ data: RoomDetail[] }>(
      `/facilities/rooms/studio/${studioId}`
    ),

  getRoomDetail: (roomId: string) =>
    apiClient.get<{ data: RoomDetail }>(`/facilities/rooms/${roomId}/detail`),

  updateRoomExtended: (roomId: string, data: Partial<RoomDetail>) =>
    apiClient.put<{ data: RoomDetail }>(
      `/facilities/rooms/${roomId}/extended`,
      data
    ),

  getRoomAvailability: (roomId: string, date: string) =>
    apiClient.get<{ data: RoomAvailabilitySlot[] }>(
      `/facilities/rooms/${roomId}/availability`,
      { params: { date } }
    ),

  // Equipment
  listEquipment: (params: {
    studio_id: string;
    room_id?: string;
    category?: string;
    condition?: string;
  }) => apiClient.get<{ data: Equipment[] }>("/facilities/equipment", { params }),

  getEquipment: (id: string) =>
    apiClient.get<{ data: Equipment }>(`/facilities/equipment/${id}`),

  createEquipment: (data: {
    studio_id: string;
    room_id?: string;
    name: string;
    category?: string;
    description?: string;
    quantity?: number;
    purchase_date?: string;
    purchase_cost_cents?: number;
    condition?: string;
    warranty_expiry?: string;
    serial_number?: string;
    photo_url?: string;
    notes?: string;
  }) => apiClient.post<{ data: Equipment }>("/facilities/equipment", data),

  updateEquipment: (id: string, data: Partial<Equipment>) =>
    apiClient.put<{ data: Equipment }>(`/facilities/equipment/${id}`, data),

  deleteEquipment: (id: string) =>
    apiClient.delete(`/facilities/equipment/${id}`),

  // Maintenance Requests
  listMaintenance: (params: {
    studio_id: string;
    status?: string;
    priority?: string;
  }) =>
    apiClient.get<{ data: MaintenanceRequest[] }>("/facilities/maintenance", {
      params,
    }),

  getMaintenanceStats: (studioId: string) =>
    apiClient.get<{ data: MaintenanceStats }>("/facilities/maintenance/stats", {
      params: { studio_id: studioId },
    }),

  getMaintenance: (id: string) =>
    apiClient.get<{ data: MaintenanceRequest }>(
      `/facilities/maintenance/${id}`
    ),

  createMaintenance: (data: {
    studio_id: string;
    room_id?: string;
    equipment_id?: string;
    title: string;
    description?: string;
    priority?: string;
    category?: string;
    assigned_to?: string;
    estimated_cost_cents?: number;
    scheduled_date?: string;
  }) =>
    apiClient.post<{ data: MaintenanceRequest }>(
      "/facilities/maintenance",
      data
    ),

  updateMaintenance: (id: string, data: Partial<MaintenanceRequest>) =>
    apiClient.put<{ data: MaintenanceRequest }>(
      `/facilities/maintenance/${id}`,
      data
    ),

  // Schedules
  listSchedules: (params: {
    studio_id: string;
    type?: string;
    overdue_only?: boolean;
  }) =>
    apiClient.get<{ data: FacilitySchedule[] }>("/facilities/schedules", {
      params,
    }),

  getOverdueTasks: (studioId: string) =>
    apiClient.get<{ data: FacilitySchedule[] }>(
      "/facilities/schedules/overdue",
      { params: { studio_id: studioId } }
    ),

  getSchedule: (id: string) =>
    apiClient.get<{ data: FacilitySchedule }>(`/facilities/schedules/${id}`),

  createSchedule: (data: {
    studio_id: string;
    room_id?: string;
    equipment_id?: string;
    schedule_type?: string;
    title: string;
    description?: string;
    rrule?: string;
    assigned_to?: string;
    next_due_at?: string;
  }) =>
    apiClient.post<{ data: FacilitySchedule }>(
      "/facilities/schedules",
      data
    ),

  updateSchedule: (id: string, data: Partial<FacilitySchedule>) =>
    apiClient.put<{ data: FacilitySchedule }>(
      `/facilities/schedules/${id}`,
      data
    ),

  deleteSchedule: (id: string) =>
    apiClient.delete(`/facilities/schedules/${id}`),

  completeSchedule: (
    id: string,
    data?: { notes?: string; photos?: string[] }
  ) =>
    apiClient.post<{ data: FacilitySchedule }>(
      `/facilities/schedules/${id}/complete`,
      data || {}
    ),

  getScheduleHistory: (id: string) =>
    apiClient.get<{ data: ScheduleCompletion[] }>(
      `/facilities/schedules/${id}/history`
    ),
};
