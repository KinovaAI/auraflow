import { apiClient } from "./api-client";

// ── ClassPass Types ────────────────────────────────────────────────────────

export interface ClassPassConfig {
  id: string;
  studio_id: string;
  venue_id: string;
  is_active: boolean;
  credit_rate: number;
  auto_confirm: boolean;
  max_spots_per_class: number;
  blackout_class_types: string[];
  created_at: string;
  updated_at: string;
}

export interface ClassPassReservation {
  id: string;
  classpass_reservation_id: string;
  class_session_id: string;
  customer_name: string;
  customer_email: string;
  credits: number;
  status: string;
  created_at: string;
}

export interface ClassPassConfigUpdate {
  credit_rate?: number;
  auto_confirm?: boolean;
  max_spots_per_class?: number;
  blackout_class_types?: string[];
}

// ── ClassPass API ──────────────────────────────────────────────────────────

export const integrationsApi = {
  // ClassPass
  connectClassPass: (studioId: string, venueId: string) =>
    apiClient.post<{ data: ClassPassConfig }>(
      "/integrations/classpass/connect",
      { studio_id: studioId, venue_id: venueId }
    ),

  getClassPassConfig: (studioId: string) =>
    apiClient.get<{ data: ClassPassConfig }>(
      `/integrations/classpass/config/${studioId}`
    ),

  updateClassPassConfig: (studioId: string, data: ClassPassConfigUpdate) =>
    apiClient.put<{ data: ClassPassConfig }>(
      `/integrations/classpass/config/${studioId}`,
      data
    ),

  disconnectClassPass: (studioId: string) =>
    apiClient.post<{ data: { disconnected: boolean } }>(
      `/integrations/classpass/disconnect/${studioId}`
    ),

  listClassPassReservations: (params?: {
    status?: string;
    limit?: number;
  }) =>
    apiClient.get<{ data: ClassPassReservation[] }>(
      "/integrations/classpass/reservations",
      { params }
    ),

  // EMR Integration
  emrConnect: (data: EmrConnectRequest) =>
    apiClient.post<{ data: { status: string; protocol: string } }>(
      "/integrations/emr/connect",
      data
    ),

  emrStatus: () =>
    apiClient.get<{ data: EmrStatus }>("/integrations/emr/status"),

  emrTest: () =>
    apiClient.post<{ data: { success: boolean; message: string } }>(
      "/integrations/emr/test"
    ),

  emrDisconnect: () =>
    apiClient.post<{ data: { status: string } }>(
      "/integrations/emr/disconnect"
    ),

  emrSyncLog: (params?: { direction?: string; limit?: number }) =>
    apiClient.get<{ data: EmrSyncLogEntry[] }>(
      "/integrations/emr/sync-log",
      { params }
    ),

  emrSyncMember: (memberId: string) =>
    apiClient.post<{ data: { emr_patient_id: string; status: string } }>(
      `/integrations/emr/sync-member/${memberId}`
    ),
};

// ── EMR Types ─────────────────────────────────────────────────────────────

export interface EmrConnectRequest {
  protocol: "fhir_r4" | "hl7v2";
  base_url?: string;
  client_id?: string;
  client_secret?: string;
  token_url?: string;
  host?: string;
  port?: number;
}

export interface EmrStatus {
  connected: boolean;
  protocol: string | null;
  endpoint?: string;
  connected_at?: string;
  sync_enabled: boolean;
}

export interface EmrSyncLogEntry {
  id: string;
  direction: string;
  resource_type: string;
  operation: string;
  emr_resource_id?: string;
  auraflow_resource_id?: string;
  status: string;
  error_message?: string;
  created_at: string;
}
