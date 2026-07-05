"use client";

import { useQuery } from "@tanstack/react-query";
import {
  Loader2,
  Server,
  Database,
  Cpu,
  HardDrive,
  MemoryStick,
  Activity,
  Wifi,
  CheckCircle2,
  XCircle,
  AlertCircle,
} from "lucide-react";
import { platformHealthApi, type SystemHealth, type ActiveQuery } from "@/lib/platform-health-api";

function StatusPill({ label, status }: { label: string; status: string }) {
  const colors: Record<string, string> = {
    healthy: "bg-green-100 text-green-700",
    unhealthy: "bg-red-100 text-red-700",
    unknown: "bg-gray-100 text-gray-500",
  };
  const icons: Record<string, typeof CheckCircle2> = {
    healthy: CheckCircle2,
    unhealthy: XCircle,
    unknown: AlertCircle,
  };
  const Icon = icons[status] || AlertCircle;
  return (
    <div className={`flex items-center gap-1.5 rounded-full px-3 py-1.5 text-sm font-medium ${colors[status] || colors.unknown}`}>
      <Icon className="h-3.5 w-3.5" />
      {label}
    </div>
  );
}

function StatCard({ label, value, sub, icon: Icon, color = "text-gray-600" }: {
  label: string; value: string | number; sub?: string; icon: typeof Server; color?: string;
}) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4">
      <div className="flex items-center gap-2">
        <Icon className={`h-4 w-4 ${color}`} />
        <span className="text-sm text-gray-500">{label}</span>
      </div>
      <p className="mt-1 text-xl font-bold text-gray-900">{value}</p>
      {sub && <p className="text-xs text-gray-400">{sub}</p>}
    </div>
  );
}

function UsageBar({ pct, label }: { pct: number; label: string }) {
  const color = pct > 90 ? "bg-red-500" : pct > 70 ? "bg-yellow-500" : "bg-green-500";
  return (
    <div>
      <div className="flex items-center justify-between text-xs text-gray-500">
        <span>{label}</span>
        <span className="font-medium">{pct.toFixed(1)}%</span>
      </div>
      <div className="mt-1 h-2 w-full overflow-hidden rounded-full bg-gray-100">
        <div className={`h-full rounded-full transition-all ${color}`} style={{ width: `${Math.min(pct, 100)}%` }} />
      </div>
    </div>
  );
}

function SeverityBadge({ severity }: { severity: string }) {
  const colors: Record<string, string> = {
    healthy: "bg-green-100 text-green-700",
    warning: "bg-yellow-100 text-yellow-700",
    critical: "bg-red-100 text-red-700",
  };
  return (
    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${colors[severity] || "bg-gray-100 text-gray-600"}`}>
      {severity}
    </span>
  );
}

export default function PlatformHealthPage() {
  const { data: health, isLoading } = useQuery({
    queryKey: ["platform-system-health"],
    queryFn: () => platformHealthApi.getSystemHealth().then((r) => r.data.data),
    refetchInterval: 30000,
  });

  const { data: queries } = useQuery({
    queryKey: ["platform-active-queries"],
    queryFn: () => platformHealthApi.getActiveQueries().then((r) => r.data.data),
    refetchInterval: 15000,
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="h-8 w-8 animate-spin text-indigo-600" />
      </div>
    );
  }

  if (!health) return null;
  const { database: db, server, redis, services } = health;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-900">System Health</h1>

      {/* Service Status */}
      <div className="flex flex-wrap gap-3">
        <StatusPill label="API" status={services.api} />
        <StatusPill label="Database" status={services.database} />
        <StatusPill label="Redis" status={services.redis} />
        <StatusPill label="Celery" status={services.celery} />
      </div>

      {/* Server Metrics */}
      <div>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-gray-400">Server</h2>
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-3">
          <div className="rounded-lg border border-gray-200 bg-white p-4">
            <div className="flex items-center gap-2">
              <Cpu className="h-4 w-4 text-blue-600" />
              <span className="text-sm text-gray-500">CPU</span>
            </div>
            <p className="mt-1 text-xl font-bold text-gray-900">{server.cpu_usage_pct}%</p>
            <p className="text-xs text-gray-400">{server.cpu_count} cores</p>
            <div className="mt-2">
              <UsageBar pct={server.cpu_usage_pct} label="Utilization" />
            </div>
          </div>

          <div className="rounded-lg border border-gray-200 bg-white p-4">
            <div className="flex items-center gap-2">
              <MemoryStick className="h-4 w-4 text-purple-600" />
              <span className="text-sm text-gray-500">Memory</span>
            </div>
            <p className="mt-1 text-xl font-bold text-gray-900">{server.memory.used_gb} GB</p>
            <p className="text-xs text-gray-400">of {server.memory.total_gb} GB total</p>
            <div className="mt-2">
              <UsageBar pct={server.memory.usage_pct} label="Usage" />
            </div>
          </div>

          <div className="rounded-lg border border-gray-200 bg-white p-4">
            <div className="flex items-center gap-2">
              <HardDrive className="h-4 w-4 text-orange-600" />
              <span className="text-sm text-gray-500">Disk</span>
            </div>
            <p className="mt-1 text-xl font-bold text-gray-900">{server.disk.used_gb} GB</p>
            <p className="text-xs text-gray-400">of {server.disk.total_gb} GB total ({server.disk.free_gb} GB free)</p>
            <div className="mt-2">
              <UsageBar pct={server.disk.usage_pct} label="Usage" />
            </div>
          </div>

          <StatCard label="Load Average" value={server.load_average.map((v) => v.toFixed(2)).join(" / ")} sub="1m / 5m / 15m" icon={Activity} color="text-indigo-600" />
          <StatCard label="Platform" value={server.platform} sub={`Python ${server.python_version}`} icon={Server} color="text-gray-600" />
          <StatCard label="Process Uptime" value={server.process_uptime} sub={server.hostname} icon={Activity} color="text-green-600" />
        </div>
      </div>

      {/* Database Metrics */}
      <div>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-gray-400">Database</h2>
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          <StatCard label="PostgreSQL" value={db.version?.split(",")[0]?.replace("PostgreSQL ", "PG ") || "?"} icon={Database} color="text-blue-600" />
          <StatCard label="Uptime" value={db.uptime?.split(".")[0] || "?"} icon={Activity} color="text-green-600" />

          <div className="rounded-lg border border-gray-200 bg-white p-4">
            <div className="flex items-center gap-2">
              <Wifi className="h-4 w-4 text-indigo-600" />
              <span className="text-sm text-gray-500">Connections</span>
            </div>
            <p className="mt-1 text-xl font-bold text-gray-900">{db.connections?.total || 0} <span className="text-sm font-normal text-gray-400">/ {db.max_connections}</span></p>
            <div className="mt-2">
              <UsageBar pct={db.connection_utilization_pct || 0} label="Utilization" />
            </div>
          </div>

          <div className="rounded-lg border border-gray-200 bg-white p-4">
            <div className="flex items-center gap-2">
              <Database className="h-4 w-4 text-green-600" />
              <span className="text-sm text-gray-500">Cache Hit Ratio</span>
            </div>
            <p className="mt-1 text-xl font-bold text-gray-900">{db.cache_hit_ratio}%</p>
            <p className={`text-xs ${db.cache_hit_ratio >= 99 ? "text-green-500" : db.cache_hit_ratio >= 95 ? "text-yellow-500" : "text-red-500"}`}>
              {db.cache_hit_ratio >= 99 ? "Excellent" : db.cache_hit_ratio >= 95 ? "Good" : "Needs attention"}
            </p>
          </div>

          <StatCard label="Database Size" value={db.database_size || "?"} icon={HardDrive} color="text-orange-600" />
          <StatCard label="Transactions" value={(db.transactions?.committed || 0).toLocaleString()} sub={`${db.transactions?.rolled_back || 0} rolled back, ${db.transactions?.deadlocks || 0} deadlocks`} icon={Activity} color="text-blue-600" />
          <StatCard label="Temp Files" value={db.temp_files || 0} icon={HardDrive} color="text-gray-500" />
          <StatCard label="Replication" value={db.replication?.length ? `${db.replication.length} replica(s)` : "None"} icon={Database} color="text-purple-600" />
        </div>
      </div>

      {/* Redis Metrics */}
      <div>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-gray-400">Redis</h2>
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          <StatCard label="Version" value={redis.version || "?"} icon={Server} color="text-red-600" />
          <StatCard label="Memory Used" value={`${redis.memory_used_mb} MB`} sub={redis.memory_max_mb ? `of ${redis.memory_max_mb} MB max` : undefined} icon={MemoryStick} color="text-red-500" />
          <StatCard label="Connected Clients" value={redis.connected_clients || 0} icon={Wifi} color="text-red-600" />
          <StatCard label="Uptime" value={redis.uptime_seconds ? `${Math.floor(redis.uptime_seconds / 3600)}h ${Math.floor((redis.uptime_seconds % 3600) / 60)}m` : "?"} icon={Activity} color="text-red-500" />
        </div>
      </div>

      {/* Active Queries */}
      <div>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-gray-400">Active Queries</h2>
        {!queries?.length ? (
          <div className="rounded-lg border border-dashed border-gray-300 py-8 text-center">
            <p className="text-sm text-gray-500">No active queries</p>
          </div>
        ) : (
          <div className="overflow-hidden rounded-lg border border-gray-200">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">PID</th>
                  <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">State</th>
                  <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Client</th>
                  <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Duration</th>
                  <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Query</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200 bg-white">
                {queries.map((q) => (
                  <tr key={q.pid} className="hover:bg-gray-50">
                    <td className="px-3 py-2 text-sm text-gray-700 font-mono">{q.pid}</td>
                    <td className="px-3 py-2">
                      <span className={`rounded px-1.5 py-0.5 text-xs font-medium ${
                        q.state === "active" ? "bg-green-100 text-green-700" :
                        q.state === "idle" ? "bg-gray-100 text-gray-600" :
                        "bg-yellow-100 text-yellow-700"
                      }`}>
                        {q.state}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-sm text-gray-500">{q.client_addr || "local"}</td>
                    <td className="px-3 py-2">
                      <SeverityBadge severity={q.severity} />
                      <span className="ml-1 text-xs text-gray-400">{q.duration_secs}s</span>
                    </td>
                    <td className="max-w-md truncate px-3 py-2 text-xs font-mono text-gray-600">{q.query?.slice(0, 120)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <p className="text-xs text-gray-400">
        Last updated: {health.collected_at ? new Date(health.collected_at).toLocaleString() : "—"}
      </p>
    </div>
  );
}
