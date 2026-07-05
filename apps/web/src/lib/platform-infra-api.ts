import { apiClient } from "./api-client";

// ── Database Types ───────────────────────────────────────────────────────

export interface DBHealth {
  version: string;
  started_at: string;
  uptime: string;
  connections: {
    total: number;
    active: number;
    idle: number;
    idle_in_tx: number;
  };
  max_connections: number;
  database_size: string;
}

export interface DBPerformance {
  cache_hit_ratio: number;
  block_hits: number;
  block_reads: number;
  transactions: {
    committed: number;
    rolled_back: number;
    conflicts: number;
    deadlocks: number;
  };
  temp_files: number;
  temp_bytes: number;
}

export interface TableSize {
  schemaname: string;
  tablename: string;
  total_size: string;
  total_bytes: number;
  row_estimate: number;
}

export interface ActiveConnection {
  pid: number;
  usename: string;
  application_name: string;
  client_addr: string;
  state: string;
  query: string;
  duration: string;
  wait_event_type: string | null;
  wait_event: string | null;
}

export interface IntegrityCheck {
  analyzed: boolean;
  bloated_tables: Array<{
    schemaname: string;
    relname: string;
    n_dead_tup: number;
    n_live_tup: number;
    dead_ratio_pct: number;
  }>;
  invalid_indexes: Array<{
    schemaname: string;
    tablename: string;
    indexname: string;
  }>;
  sequence_health: Array<{
    sequencename: string;
    last_value: number;
    max_value: number;
    usage_pct: number;
  }>;
}

// ── Backup Types ─────────────────────────────────────────────────────────

export interface Backup {
  id: string;
  backup_type: "database" | "files";
  status: "pending" | "running" | "completed" | "failed";
  file_name: string | null;
  file_size_bytes: number | null;
  duration_seconds: number | null;
  error_message: string | null;
  triggered_by: "manual" | "scheduled";
  created_at: string;
}

export interface BackupSchedule {
  id: string;
  backup_type: "database" | "files";
  cron_expression: string;
  retention_days: number;
  is_active: boolean;
  last_run_at: string | null;
  next_run_at: string | null;
}

export interface BackupStatus {
  last_backup: Backup | null;
  running_count: number;
  total_size_bytes: number;
  total_count: number;
  next_scheduled: BackupSchedule | null;
  b2_connected: boolean;
  b2_bucket: string;
  encryption_enabled: boolean;
}

// ── Traffic Types ────────────────────────────────────────────────────────

export interface TrafficMetric {
  period_start: string;
  total_requests: number;
  avg_response_ms: number;
  p95_response_ms: number;
  error_count: number;
  unique_ips: number;
}

export interface ActiveUsers {
  last_5_minutes: number;
  last_1_hour: number;
  last_24_hours: number;
}

export interface TopEndpoint {
  endpoint: string;
  requests: number;
}

export interface GeoEntry {
  region: string;
  requests: number;
}

// ── Security Types ───────────────────────────────────────────────────────

export interface SecurityEvent {
  id: string;
  event_type: string;
  severity: "low" | "medium" | "high" | "critical";
  source_ip: string | null;
  user_agent: string | null;
  endpoint: string | null;
  details: Record<string, unknown>;
  acknowledged: boolean;
  acknowledged_at: string | null;
  created_at: string;
}

export interface SecuritySummary {
  total_events: number;
  unacknowledged: number;
  by_type: Array<{ event_type: string; count: number }>;
  by_severity: Array<{ severity: string; count: number }>;
  period_hours: number;
}

// ── Infrastructure API ───────────────────────────────────────────────────

export const platformInfraApi = {
  // Database
  dbHealth: () =>
    apiClient.get<{ data: DBHealth }>("/platform/infrastructure/db/health"),
  dbPerformance: () =>
    apiClient.get<{ data: DBPerformance }>("/platform/infrastructure/db/performance"),
  dbTables: () =>
    apiClient.get<{ data: TableSize[] }>("/platform/infrastructure/db/tables"),
  dbConnections: () =>
    apiClient.get<{ data: ActiveConnection[] }>("/platform/infrastructure/db/connections"),
  dbSlowQueries: () =>
    apiClient.get<{ data: Array<Record<string, unknown>> }>("/platform/infrastructure/db/slow-queries"),
  dbIntegrityCheck: () =>
    apiClient.post<{ data: IntegrityCheck }>("/platform/infrastructure/db/integrity-check"),

  // Backups
  listBackups: (type?: string, limit?: number) =>
    apiClient.get<{ data: Backup[] }>("/platform/infrastructure/backups", {
      params: { backup_type: type, limit },
    }),
  backupStatus: () =>
    apiClient.get<{ data: BackupStatus }>("/platform/infrastructure/backups/status"),
  triggerBackup: (backup_type: "database" | "files" = "database") =>
    apiClient.post<{ data: Backup }>("/platform/infrastructure/backups/trigger", null, {
      params: { backup_type },
    }),
  triggerDbBackup: () =>
    apiClient.post<{ data: Backup }>("/platform/infrastructure/backups/database"),
  triggerFilesBackup: () =>
    apiClient.post<{ data: Backup }>("/platform/infrastructure/backups/files"),
  deleteBackup: (id: string) =>
    apiClient.delete<{ data: { deleted: boolean } }>(`/platform/infrastructure/backups/${id}`),
  downloadBackup: (id: string) =>
    apiClient.get<{ data: { download_url: string } }>(`/platform/infrastructure/backups/${id}/download`),
  requestRestore: (id: string) =>
    apiClient.post<{ data: { token: string; expires_in_seconds: number } }>(`/platform/infrastructure/backups/${id}/restore`),
  confirmRestore: (token: string) =>
    apiClient.post<{ data: { restored: boolean } }>("/platform/infrastructure/backups/restore/confirm", { token }),

  // Backup Schedules
  listSchedules: () =>
    apiClient.get<{ data: BackupSchedule[] }>("/platform/infrastructure/backup-schedules"),
  updateSchedule: (id: string, data: Partial<Pick<BackupSchedule, "cron_expression" | "retention_days" | "is_active">>) =>
    apiClient.put<{ data: BackupSchedule }>(`/platform/infrastructure/backup-schedules/${id}`, data),

  // Traffic
  trafficOverview: (hours?: number) =>
    apiClient.get<{ data: TrafficMetric[] }>("/platform/infrastructure/traffic/overview", {
      params: hours ? { hours } : undefined,
    }),
  activeUsers: () =>
    apiClient.get<{ data: ActiveUsers }>("/platform/infrastructure/traffic/active-users"),
  topEndpoints: (hours?: number) =>
    apiClient.get<{ data: TopEndpoint[] }>("/platform/infrastructure/traffic/top-endpoints", {
      params: hours ? { hours } : undefined,
    }),
  geoBreakdown: (hours?: number) =>
    apiClient.get<{ data: GeoEntry[] }>("/platform/infrastructure/traffic/geo", {
      params: hours ? { hours } : undefined,
    }),

  // Security
  securityEvents: (params?: { event_type?: string; severity?: string; acknowledged?: boolean; limit?: number }) =>
    apiClient.get<{ data: SecurityEvent[] }>("/platform/infrastructure/security/events", { params }),
  securitySummary: (hours?: number) =>
    apiClient.get<{ data: SecuritySummary }>("/platform/infrastructure/security/summary", {
      params: hours ? { hours } : undefined,
    }),
  acknowledgeEvent: (id: string) =>
    apiClient.put<{ data: SecurityEvent }>(`/platform/infrastructure/security/events/${id}/acknowledge`),
  triggerSecurityScan: () =>
    apiClient.post<{ data: Record<string, number> }>("/platform/infrastructure/security/scan"),
};
