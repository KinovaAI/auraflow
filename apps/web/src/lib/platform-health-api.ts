import { apiClient } from "./api-client";

export interface SystemHealth {
  database: {
    version: string;
    started_at: string;
    uptime: string;
    connections: { total: number; active: number; idle: number; idle_in_tx: number };
    max_connections: number;
    connection_utilization_pct: number;
    database_size: string;
    database_size_bytes: number;
    cache_hit_ratio: number;
    transactions: { committed: number; rolled_back: number; conflicts: number; deadlocks: number };
    temp_files: number;
    replication: { client_addr: string; state: string }[];
  };
  server: {
    hostname: string;
    platform: string;
    python_version: string;
    cpu_count: number;
    cpu_usage_pct: number;
    memory: { total_gb: number; used_gb: number; available_gb: number; usage_pct: number };
    disk: { total_gb: number; used_gb: number; free_gb: number; usage_pct: number };
    load_average: number[];
    process_uptime: string;
    process_uptime_seconds: number;
  };
  redis: {
    connected: boolean;
    version: string;
    memory_used_mb: number;
    memory_max_mb: number | null;
    connected_clients: number;
    uptime_seconds: number;
  };
  services: {
    api: string;
    database: string;
    redis: string;
    celery: string;
  };
  collected_at: string;
}

export interface ActiveQuery {
  pid: number;
  usename: string;
  application_name: string;
  client_addr: string;
  state: string;
  query: string;
  duration: string;
  duration_secs: number;
  severity: "healthy" | "warning" | "critical";
  wait_event_type: string | null;
  wait_event: string | null;
}

export const platformHealthApi = {
  getSystemHealth: () =>
    apiClient.get<{ data: SystemHealth }>("/platform/health/system"),

  getActiveQueries: () =>
    apiClient.get<{ data: ActiveQuery[] }>("/platform/health/queries"),
};
