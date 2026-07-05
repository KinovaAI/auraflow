"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { format } from "date-fns";
import toast from "react-hot-toast";
import {
  Loader2,
  Database,
  HardDrive,
  Activity,
  Shield,
  Download,
  Play,
  RefreshCw,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Clock,
  Server,
  Trash2,
  RotateCcw,
  Save,
  Cloud,
  CloudOff,
  Lock,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  platformInfraApi,
  type Backup,
  type BackupSchedule,
  type BackupStatus,
  type SecurityEvent,
} from "@/lib/platform-infra-api";

const TABS = [
  { id: "database", label: "Database", icon: Database },
  { id: "backups", label: "Backups", icon: HardDrive },
  { id: "traffic", label: "Traffic", icon: Activity },
  { id: "security", label: "Security", icon: Shield },
] as const;

type TabId = (typeof TABS)[number]["id"];

// ── Database Tab ──────────────────────────────────────────────────────

function DatabaseTab() {
  const { data: health, isLoading: healthLoading } = useQuery({
    queryKey: ["infra-db-health"],
    queryFn: () => platformInfraApi.dbHealth().then((r) => r.data.data),
    refetchInterval: 30000,
  });

  const { data: performance } = useQuery({
    queryKey: ["infra-db-performance"],
    queryFn: () => platformInfraApi.dbPerformance().then((r) => r.data.data),
    refetchInterval: 30000,
  });

  const { data: tables } = useQuery({
    queryKey: ["infra-db-tables"],
    queryFn: () => platformInfraApi.dbTables().then((r) => r.data.data),
  });

  const { data: connections } = useQuery({
    queryKey: ["infra-db-connections"],
    queryFn: () => platformInfraApi.dbConnections().then((r) => r.data.data),
    refetchInterval: 15000,
  });

  const integrityMutation = useMutation({
    mutationFn: () => platformInfraApi.dbIntegrityCheck().then((r) => r.data.data),
    onSuccess: (data) => {
      toast.success(
        `Integrity check: ${data.bloated_tables.length} bloated, ${data.invalid_indexes.length} invalid indexes`
      );
    },
    onError: () => toast.error("Integrity check failed"),
  });

  if (healthLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="h-8 w-8 animate-spin text-indigo-600" />
      </div>
    );
  }

  const connPct = health
    ? Math.round((health.connections.total / health.max_connections) * 100)
    : 0;

  return (
    <div className="space-y-6">
      {/* Health Cards */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardContent className="pt-6">
            <p className="text-sm font-medium text-gray-500">Database Size</p>
            <p className="mt-1 text-2xl font-bold text-gray-900">{health?.database_size || "—"}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <p className="text-sm font-medium text-gray-500">Connections</p>
            <p className="mt-1 text-2xl font-bold text-gray-900">
              {health?.connections.total || 0}{" "}
              <span className="text-sm font-normal text-gray-400">/ {health?.max_connections}</span>
            </p>
            <div className="mt-2 h-2 overflow-hidden rounded-full bg-gray-200">
              <div
                className={`h-full rounded-full ${connPct > 80 ? "bg-red-500" : connPct > 50 ? "bg-yellow-500" : "bg-green-500"}`}
                style={{ width: `${connPct}%` }}
              />
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <p className="text-sm font-medium text-gray-500">Cache Hit Ratio</p>
            <p className="mt-1 text-2xl font-bold text-gray-900">
              {performance?.cache_hit_ratio ?? "—"}%
            </p>
            <p className="mt-1 text-xs text-gray-400">
              {(performance?.cache_hit_ratio ?? 0) >= 99 ? "Excellent" : (performance?.cache_hit_ratio ?? 0) >= 95 ? "Good" : "Needs attention"}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <p className="text-sm font-medium text-gray-500">Uptime</p>
            <p className="mt-1 text-lg font-bold text-gray-900 truncate">
              {health?.uptime?.split(".")[0] || "—"}
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Transaction Stats */}
      {performance && (
        <div className="grid gap-4 sm:grid-cols-4">
          <div className="rounded-lg border border-gray-200 bg-white px-4 py-3">
            <p className="text-xs text-gray-500">Committed</p>
            <p className="text-lg font-semibold text-green-600">
              {performance.transactions.committed.toLocaleString()}
            </p>
          </div>
          <div className="rounded-lg border border-gray-200 bg-white px-4 py-3">
            <p className="text-xs text-gray-500">Rolled Back</p>
            <p className="text-lg font-semibold text-yellow-600">
              {performance.transactions.rolled_back.toLocaleString()}
            </p>
          </div>
          <div className="rounded-lg border border-gray-200 bg-white px-4 py-3">
            <p className="text-xs text-gray-500">Deadlocks</p>
            <p className="text-lg font-semibold text-red-600">
              {performance.transactions.deadlocks}
            </p>
          </div>
          <div className="rounded-lg border border-gray-200 bg-white px-4 py-3">
            <p className="text-xs text-gray-500">Temp Files</p>
            <p className="text-lg font-semibold text-gray-900">{performance.temp_files}</p>
          </div>
        </div>
      )}

      {/* Active Connections */}
      {connections && connections.length > 0 && (
        <div>
          <h3 className="mb-2 text-sm font-semibold text-gray-700">
            Active Connections ({connections.length})
          </h3>
          <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white">
            <table className="min-w-full divide-y divide-gray-200 text-sm">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-3 py-2 text-left text-xs font-medium uppercase text-gray-500">PID</th>
                  <th className="px-3 py-2 text-left text-xs font-medium uppercase text-gray-500">State</th>
                  <th className="px-3 py-2 text-left text-xs font-medium uppercase text-gray-500">Client</th>
                  <th className="px-3 py-2 text-left text-xs font-medium uppercase text-gray-500">Duration</th>
                  <th className="px-3 py-2 text-left text-xs font-medium uppercase text-gray-500">Query</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {connections.slice(0, 20).map((c) => (
                  <tr key={c.pid}>
                    <td className="whitespace-nowrap px-3 py-2 font-mono text-gray-600">{c.pid}</td>
                    <td className="whitespace-nowrap px-3 py-2">
                      <span
                        className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                          c.state === "active" ? "bg-green-50 text-green-700" : "bg-gray-100 text-gray-500"
                        }`}
                      >
                        {c.state}
                      </span>
                    </td>
                    <td className="whitespace-nowrap px-3 py-2 text-gray-500">{c.client_addr || "local"}</td>
                    <td className="whitespace-nowrap px-3 py-2 text-gray-500">{c.duration?.split(".")[0]}</td>
                    <td className="max-w-xs truncate px-3 py-2 font-mono text-xs text-gray-400">{c.query}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Table Sizes */}
      {tables && tables.length > 0 && (
        <div>
          <h3 className="mb-2 text-sm font-semibold text-gray-700">Largest Tables</h3>
          <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white">
            <table className="min-w-full divide-y divide-gray-200 text-sm">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-3 py-2 text-left text-xs font-medium uppercase text-gray-500">Schema</th>
                  <th className="px-3 py-2 text-left text-xs font-medium uppercase text-gray-500">Table</th>
                  <th className="px-3 py-2 text-right text-xs font-medium uppercase text-gray-500">Size</th>
                  <th className="px-3 py-2 text-right text-xs font-medium uppercase text-gray-500">Rows (est.)</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {tables.slice(0, 20).map((t, i) => (
                  <tr key={i}>
                    <td className="whitespace-nowrap px-3 py-2 font-mono text-xs text-indigo-600">{t.schemaname}</td>
                    <td className="whitespace-nowrap px-3 py-2 font-mono text-xs text-gray-900">{t.tablename}</td>
                    <td className="whitespace-nowrap px-3 py-2 text-right text-gray-600">{t.total_size}</td>
                    <td className="whitespace-nowrap px-3 py-2 text-right text-gray-500">{t.row_estimate?.toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Integrity Check */}
      <div className="flex items-center gap-3">
        <Button
          onClick={() => integrityMutation.mutate()}
          disabled={integrityMutation.isPending}
          variant="outline"
        >
          {integrityMutation.isPending ? (
            <Loader2 className="mr-1 h-4 w-4 animate-spin" />
          ) : (
            <RefreshCw className="mr-1 h-4 w-4" />
          )}
          Run Integrity Check
        </Button>
        {integrityMutation.data && (
          <span className="text-sm text-green-600">
            <CheckCircle2 className="mr-1 inline h-4 w-4" />
            Check completed — {integrityMutation.data.bloated_tables.length} bloated tables,{" "}
            {integrityMutation.data.invalid_indexes.length} invalid indexes
          </span>
        )}
      </div>
    </div>
  );
}

// ── Backups Tab ───────────────────────────────────────────────────────

function BackupsTab() {
  const queryClient = useQueryClient();
  const [restoreTarget, setRestoreTarget] = useState<Backup | null>(null);
  const [restoreToken, setRestoreToken] = useState<string | null>(null);
  const [editSchedule, setEditSchedule] = useState<{ id: string; cron: string; retention: number } | null>(null);

  const { data: status } = useQuery({
    queryKey: ["infra-backup-status"],
    queryFn: () => platformInfraApi.backupStatus().then((r) => r.data.data),
    refetchInterval: 15000,
  });

  const { data: backups, isLoading } = useQuery({
    queryKey: ["infra-backups"],
    queryFn: () => platformInfraApi.listBackups(undefined, 50).then((r) => r.data.data),
    refetchInterval: 10000,
  });

  const { data: schedules } = useQuery({
    queryKey: ["infra-backup-schedules"],
    queryFn: () => platformInfraApi.listSchedules().then((r) => r.data.data),
  });

  const invalidateAll = () => {
    queryClient.invalidateQueries({ queryKey: ["infra-backups"] });
    queryClient.invalidateQueries({ queryKey: ["infra-backup-status"] });
  };

  const dbBackupMutation = useMutation({
    mutationFn: () => platformInfraApi.triggerDbBackup().then((r) => r.data.data),
    onSuccess: () => { toast.success("Database backup started"); invalidateAll(); },
    onError: () => toast.error("Failed to start database backup"),
  });

  const filesBackupMutation = useMutation({
    mutationFn: () => platformInfraApi.triggerFilesBackup().then((r) => r.data.data),
    onSuccess: () => { toast.success("Files backup started"); invalidateAll(); },
    onError: () => toast.error("Failed to start files backup"),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => platformInfraApi.deleteBackup(id).then((r) => r.data.data),
    onSuccess: () => { toast.success("Backup deleted"); invalidateAll(); },
    onError: () => toast.error("Failed to delete backup"),
  });

  const requestRestoreMutation = useMutation({
    mutationFn: (id: string) => platformInfraApi.requestRestore(id).then((r) => r.data.data),
    onSuccess: (data) => setRestoreToken(data.token),
    onError: () => { toast.error("Failed to request restore"); setRestoreTarget(null); },
  });

  const confirmRestoreMutation = useMutation({
    mutationFn: (token: string) => platformInfraApi.confirmRestore(token).then((r) => r.data.data),
    onSuccess: () => {
      toast.success("Restore completed successfully");
      setRestoreTarget(null);
      setRestoreToken(null);
      invalidateAll();
    },
    onError: () => toast.error("Restore failed"),
  });

  const toggleScheduleMutation = useMutation({
    mutationFn: ({ id, is_active }: { id: string; is_active: boolean }) =>
      platformInfraApi.updateSchedule(id, { is_active }).then((r) => r.data.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["infra-backup-schedules"] });
      queryClient.invalidateQueries({ queryKey: ["infra-backup-status"] });
    },
  });

  const updateScheduleMutation = useMutation({
    mutationFn: ({ id, cron, retention }: { id: string; cron: string; retention: number }) =>
      platformInfraApi.updateSchedule(id, { cron_expression: cron, retention_days: retention }).then((r) => r.data.data),
    onSuccess: () => {
      toast.success("Schedule updated");
      setEditSchedule(null);
      queryClient.invalidateQueries({ queryKey: ["infra-backup-schedules"] });
      queryClient.invalidateQueries({ queryKey: ["infra-backup-status"] });
    },
    onError: () => toast.error("Failed to update schedule"),
  });

  const statusColors: Record<string, string> = {
    completed: "bg-green-50 text-green-700",
    running: "bg-blue-50 text-blue-700",
    pending: "bg-yellow-50 text-yellow-700",
    failed: "bg-red-50 text-red-600",
  };

  const formatBytes = (bytes: number | null | undefined) => {
    if (!bytes) return "—";
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`;
    if (bytes < 1073741824) return `${(bytes / 1048576).toFixed(1)} MB`;
    return `${(bytes / 1073741824).toFixed(2)} GB`;
  };

  return (
    <div className="space-y-6">
      {/* Status Cards */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardContent className="pt-6">
            <p className="text-sm font-medium text-gray-500">Last Backup</p>
            <p className="mt-1 text-lg font-bold text-gray-900">
              {status?.last_backup?.created_at
                ? format(new Date(status.last_backup.created_at), "MMM d, h:mm a")
                : "Never"}
            </p>
            {status?.last_backup && (
              <p className="mt-0.5 text-xs text-gray-400 capitalize">
                {status.last_backup.backup_type} - {status.last_backup.status}
              </p>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <p className="text-sm font-medium text-gray-500">Next Scheduled</p>
            <p className="mt-1 text-lg font-bold text-gray-900">
              {status?.next_scheduled?.next_run_at
                ? format(new Date(status.next_scheduled.next_run_at), "MMM d, h:mm a")
                : "Not set"}
            </p>
            {status?.next_scheduled && (
              <p className="mt-0.5 text-xs text-gray-400 capitalize">
                {status.next_scheduled.backup_type} backup
              </p>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <p className="text-sm font-medium text-gray-500">B2 Storage</p>
            <div className="mt-1 flex items-center gap-2">
              {status?.b2_connected ? (
                <Cloud className="h-5 w-5 text-green-500" />
              ) : (
                <CloudOff className="h-5 w-5 text-red-500" />
              )}
              <span className={`text-lg font-bold ${status?.b2_connected ? "text-green-600" : "text-red-600"}`}>
                {status?.b2_connected ? "Connected" : "Disconnected"}
              </span>
            </div>
            <div className="mt-0.5 flex items-center gap-1 text-xs text-gray-400">
              {status?.encryption_enabled && <Lock className="h-3 w-3" />}
              {status?.encryption_enabled ? "Encrypted" : "Unencrypted"}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <p className="text-sm font-medium text-gray-500">Total Backups</p>
            <p className="mt-1 text-2xl font-bold text-gray-900">
              {status?.total_count ?? 0}
            </p>
            <p className="mt-0.5 text-xs text-gray-400">
              {formatBytes(status?.total_size_bytes)} stored
              {(status?.running_count ?? 0) > 0 && (
                <span className="ml-2 text-blue-600">({status?.running_count} running)</span>
              )}
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Actions */}
      <div className="flex flex-wrap gap-3">
        <Button onClick={() => dbBackupMutation.mutate()} disabled={dbBackupMutation.isPending}>
          {dbBackupMutation.isPending ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <Database className="mr-1 h-4 w-4" />}
          Backup Database Now
        </Button>
        <Button onClick={() => filesBackupMutation.mutate()} disabled={filesBackupMutation.isPending} variant="outline">
          {filesBackupMutation.isPending ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <HardDrive className="mr-1 h-4 w-4" />}
          Backup Files Now
        </Button>
      </div>

      {/* Schedules */}
      {schedules && schedules.length > 0 && (
        <div>
          <h3 className="mb-2 text-sm font-semibold text-gray-700">Backup Schedules</h3>
          <div className="grid gap-3 sm:grid-cols-2">
            {schedules.map((s) => (
              <div key={s.id} className="rounded-lg border border-gray-200 bg-white p-4">
                <div className="flex items-center justify-between">
                  <div className="flex-1">
                    <p className="text-sm font-semibold text-gray-900 capitalize">{s.backup_type} Backup</p>
                    {editSchedule?.id === s.id ? (
                      <div className="mt-2 space-y-2">
                        <div>
                          <label className="text-xs text-gray-500">Cron Expression</label>
                          <input
                            type="text"
                            value={editSchedule.cron}
                            onChange={(e) => setEditSchedule({ ...editSchedule, cron: e.target.value })}
                            className="mt-0.5 w-full rounded border border-gray-300 px-2 py-1 font-mono text-xs"
                            placeholder="0 2 * * *"
                          />
                        </div>
                        <div>
                          <label className="text-xs text-gray-500">Retention (days)</label>
                          <input
                            type="number"
                            value={editSchedule.retention}
                            onChange={(e) => setEditSchedule({ ...editSchedule, retention: parseInt(e.target.value) || 7 })}
                            className="mt-0.5 w-full rounded border border-gray-300 px-2 py-1 text-xs"
                            min={1}
                            max={365}
                          />
                        </div>
                        <div className="flex gap-2">
                          <Button
                            size="sm"
                            onClick={() => updateScheduleMutation.mutate({
                              id: editSchedule.id,
                              cron: editSchedule.cron,
                              retention: editSchedule.retention,
                            })}
                            disabled={updateScheduleMutation.isPending}
                          >
                            <Save className="mr-1 h-3 w-3" />
                            Save
                          </Button>
                          <Button size="sm" variant="outline" onClick={() => setEditSchedule(null)}>
                            Cancel
                          </Button>
                        </div>
                      </div>
                    ) : (
                      <>
                        <p className="mt-1 text-xs text-gray-500 font-mono">{s.cron_expression}</p>
                        <p className="text-xs text-gray-400">Retention: {s.retention_days} days</p>
                        {s.last_run_at && (
                          <p className="text-xs text-gray-400">Last: {format(new Date(s.last_run_at), "MMM d, h:mm a")}</p>
                        )}
                        {s.next_run_at && (
                          <p className="text-xs text-gray-400">Next: {format(new Date(s.next_run_at), "MMM d, h:mm a")}</p>
                        )}
                        <button
                          type="button"
                          onClick={() => setEditSchedule({ id: s.id, cron: s.cron_expression, retention: s.retention_days })}
                          className="mt-1 text-xs text-indigo-600 hover:text-indigo-800"
                        >
                          Edit settings
                        </button>
                      </>
                    )}
                  </div>
                  <button
                    type="button"
                    onClick={() => toggleScheduleMutation.mutate({ id: s.id, is_active: !s.is_active })}
                    className={`relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors ${
                      s.is_active ? "bg-indigo-600" : "bg-gray-200"
                    }`}
                  >
                    <span
                      className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow transition ${
                        s.is_active ? "translate-x-5" : "translate-x-0"
                      }`}
                    />
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Backup History */}
      {isLoading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-8 w-8 animate-spin text-indigo-600" />
        </div>
      ) : !backups?.length ? (
        <div className="rounded-lg border border-dashed border-gray-300 py-12 text-center">
          <HardDrive className="mx-auto h-10 w-10 text-gray-300" />
          <p className="mt-2 text-sm text-gray-500">No backups yet. Click "Backup Database Now" to create your first backup.</p>
        </div>
      ) : (
        <div>
          <h3 className="mb-2 text-sm font-semibold text-gray-700">Backup History</h3>
          <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white">
            <table className="min-w-full divide-y divide-gray-200 text-sm">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-3 py-2 text-left text-xs font-medium uppercase text-gray-500">Type</th>
                  <th className="px-3 py-2 text-left text-xs font-medium uppercase text-gray-500">Status</th>
                  <th className="px-3 py-2 text-left text-xs font-medium uppercase text-gray-500">File</th>
                  <th className="px-3 py-2 text-right text-xs font-medium uppercase text-gray-500">Size</th>
                  <th className="px-3 py-2 text-right text-xs font-medium uppercase text-gray-500">Duration</th>
                  <th className="px-3 py-2 text-left text-xs font-medium uppercase text-gray-500">Trigger</th>
                  <th className="px-3 py-2 text-left text-xs font-medium uppercase text-gray-500">Created</th>
                  <th className="px-3 py-2 text-right text-xs font-medium uppercase text-gray-500">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {backups.map((b) => (
                  <tr key={b.id}>
                    <td className="whitespace-nowrap px-3 py-2 capitalize font-medium text-gray-900">{b.backup_type}</td>
                    <td className="whitespace-nowrap px-3 py-2">
                      <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${statusColors[b.status] || "bg-gray-100 text-gray-500"}`}>
                        {b.status}
                      </span>
                    </td>
                    <td className="whitespace-nowrap px-3 py-2 font-mono text-xs text-gray-500">{b.file_name || "—"}</td>
                    <td className="whitespace-nowrap px-3 py-2 text-right text-gray-500">{formatBytes(b.file_size_bytes)}</td>
                    <td className="whitespace-nowrap px-3 py-2 text-right text-gray-500">{b.duration_seconds ? `${b.duration_seconds}s` : "—"}</td>
                    <td className="whitespace-nowrap px-3 py-2 text-gray-400">{b.triggered_by}</td>
                    <td className="whitespace-nowrap px-3 py-2 text-gray-400">{format(new Date(b.created_at), "MMM d, h:mm a")}</td>
                    <td className="whitespace-nowrap px-3 py-2 text-right">
                      <div className="flex items-center justify-end gap-1">
                        {b.status === "completed" && (
                          <>
                            <Button
                              size="sm"
                              variant="outline"
                              title="Download"
                              onClick={async () => {
                                try {
                                  const res = await platformInfraApi.downloadBackup(b.id);
                                  window.open(res.data.data.download_url, "_blank");
                                } catch {
                                  toast.error("Failed to get download link");
                                }
                              }}
                            >
                              <Download className="h-3 w-3" />
                            </Button>
                            {b.backup_type === "database" && (
                              <Button
                                size="sm"
                                variant="outline"
                                title="Restore"
                                onClick={() => setRestoreTarget(b)}
                              >
                                <RotateCcw className="h-3 w-3" />
                              </Button>
                            )}
                          </>
                        )}
                        <Button
                          size="sm"
                          variant="outline"
                          title="Delete"
                          className="text-red-500 hover:text-red-700 hover:border-red-300"
                          onClick={() => {
                            if (confirm(`Delete backup ${b.file_name || b.id}?`)) {
                              deleteMutation.mutate(b.id);
                            }
                          }}
                          disabled={deleteMutation.isPending}
                        >
                          <Trash2 className="h-3 w-3" />
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Restore Confirmation Modal */}
      {restoreTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="mx-4 w-full max-w-md rounded-xl bg-white p-6 shadow-xl">
            <h3 className="text-lg font-bold text-gray-900">Restore Database</h3>
            <p className="mt-2 text-sm text-gray-600">
              You are about to restore the database from backup:
            </p>
            <div className="mt-3 rounded-lg bg-gray-50 p-3">
              <p className="font-mono text-sm text-gray-800">{restoreTarget.file_name}</p>
              <p className="mt-1 text-xs text-gray-500">
                Created: {format(new Date(restoreTarget.created_at), "MMM d, yyyy h:mm a")}
                {" | "}Size: {formatBytes(restoreTarget.file_size_bytes)}
              </p>
            </div>
            <div className="mt-3 rounded-lg border border-red-200 bg-red-50 p-3">
              <p className="text-sm font-medium text-red-800">
                Warning: This will overwrite the current database. This action cannot be undone.
              </p>
            </div>
            {!restoreToken ? (
              <div className="mt-4 flex gap-3">
                <Button
                  onClick={() => requestRestoreMutation.mutate(restoreTarget.id)}
                  disabled={requestRestoreMutation.isPending}
                  className="bg-red-600 hover:bg-red-700"
                >
                  {requestRestoreMutation.isPending ? (
                    <Loader2 className="mr-1 h-4 w-4 animate-spin" />
                  ) : (
                    <RotateCcw className="mr-1 h-4 w-4" />
                  )}
                  Request Restore Token
                </Button>
                <Button variant="outline" onClick={() => { setRestoreTarget(null); setRestoreToken(null); }}>
                  Cancel
                </Button>
              </div>
            ) : (
              <div className="mt-4">
                <p className="text-sm text-gray-600">
                  Restore token generated. Expires in 5 minutes. Click below to confirm.
                </p>
                <div className="mt-3 flex gap-3">
                  <Button
                    onClick={() => confirmRestoreMutation.mutate(restoreToken)}
                    disabled={confirmRestoreMutation.isPending}
                    className="bg-red-600 hover:bg-red-700"
                  >
                    {confirmRestoreMutation.isPending ? (
                      <Loader2 className="mr-1 h-4 w-4 animate-spin" />
                    ) : (
                      <RotateCcw className="mr-1 h-4 w-4" />
                    )}
                    Confirm Restore
                  </Button>
                  <Button variant="outline" onClick={() => { setRestoreTarget(null); setRestoreToken(null); }}>
                    Cancel
                  </Button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Traffic Tab ────────────────────────────────────────────────────────

function TrafficTab() {
  const { data: traffic } = useQuery({
    queryKey: ["infra-traffic"],
    queryFn: () => platformInfraApi.trafficOverview(24).then((r) => r.data.data),
    refetchInterval: 30000,
  });

  const { data: activeUsers } = useQuery({
    queryKey: ["infra-active-users"],
    queryFn: () => platformInfraApi.activeUsers().then((r) => r.data.data),
    refetchInterval: 15000,
  });

  const { data: topEndpoints } = useQuery({
    queryKey: ["infra-top-endpoints"],
    queryFn: () => platformInfraApi.topEndpoints(24).then((r) => r.data.data),
  });

  const totalRequests = traffic?.reduce((sum, t) => sum + t.total_requests, 0) || 0;
  const totalErrors = traffic?.reduce((sum, t) => sum + t.error_count, 0) || 0;
  const avgResponse = traffic?.length
    ? (traffic.reduce((sum, t) => sum + t.avg_response_ms, 0) / traffic.length).toFixed(1)
    : "0";

  return (
    <div className="space-y-6">
      {/* Summary Cards */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardContent className="pt-6">
            <p className="text-sm font-medium text-gray-500">Active Users (5m)</p>
            <p className="mt-1 text-2xl font-bold text-indigo-600">{activeUsers?.last_5_minutes ?? 0}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <p className="text-sm font-medium text-gray-500">Requests (24h)</p>
            <p className="mt-1 text-2xl font-bold text-gray-900">{totalRequests.toLocaleString()}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <p className="text-sm font-medium text-gray-500">Avg Response</p>
            <p className="mt-1 text-2xl font-bold text-gray-900">{avgResponse} ms</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <p className="text-sm font-medium text-gray-500">Errors (24h)</p>
            <p className={`mt-1 text-2xl font-bold ${totalErrors > 0 ? "text-red-600" : "text-green-600"}`}>
              {totalErrors}
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Active Users Breakdown */}
      {activeUsers && (
        <div className="grid gap-3 sm:grid-cols-3">
          <div className="rounded-lg border border-gray-200 bg-white px-4 py-3">
            <p className="text-xs text-gray-500">Last 5 Minutes</p>
            <p className="text-lg font-semibold text-gray-900">{activeUsers.last_5_minutes}</p>
          </div>
          <div className="rounded-lg border border-gray-200 bg-white px-4 py-3">
            <p className="text-xs text-gray-500">Last 1 Hour</p>
            <p className="text-lg font-semibold text-gray-900">{activeUsers.last_1_hour}</p>
          </div>
          <div className="rounded-lg border border-gray-200 bg-white px-4 py-3">
            <p className="text-xs text-gray-500">Last 24 Hours</p>
            <p className="text-lg font-semibold text-gray-900">{activeUsers.last_24_hours}</p>
          </div>
        </div>
      )}

      {/* Traffic Timeline (simple bar representation) */}
      {traffic && traffic.length > 0 && (
        <div>
          <h3 className="mb-2 text-sm font-semibold text-gray-700">Request Volume (24h)</h3>
          <div className="rounded-lg border border-gray-200 bg-white p-4">
            <div className="flex h-32 items-end gap-0.5">
              {traffic.map((t, i) => {
                const maxReqs = Math.max(...traffic.map((x) => x.total_requests), 1);
                const height = Math.max((t.total_requests / maxReqs) * 100, 2);
                return (
                  <div
                    key={i}
                    className="flex-1 rounded-t bg-indigo-500 hover:bg-indigo-600 transition-colors"
                    style={{ height: `${height}%` }}
                    title={`${format(new Date(t.period_start), "HH:mm")} — ${t.total_requests} requests`}
                  />
                );
              })}
            </div>
            <div className="mt-1 flex justify-between text-xs text-gray-400">
              {traffic.length > 0 && (
                <>
                  <span>{format(new Date(traffic[0].period_start), "HH:mm")}</span>
                  <span>{format(new Date(traffic[traffic.length - 1].period_start), "HH:mm")}</span>
                </>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Top Endpoints */}
      {topEndpoints && topEndpoints.length > 0 && (
        <div>
          <h3 className="mb-2 text-sm font-semibold text-gray-700">Top Endpoints (24h)</h3>
          <div className="space-y-1">
            {topEndpoints.slice(0, 15).map((ep, i) => {
              const maxReqs = topEndpoints[0].requests;
              const pct = (ep.requests / maxReqs) * 100;
              return (
                <div key={i} className="flex items-center gap-3">
                  <div className="w-64 truncate font-mono text-xs text-gray-600">{ep.endpoint}</div>
                  <div className="flex-1">
                    <div className="h-4 overflow-hidden rounded bg-gray-100">
                      <div className="h-full rounded bg-indigo-400" style={{ width: `${pct}%` }} />
                    </div>
                  </div>
                  <div className="w-16 text-right text-xs text-gray-500">{ep.requests.toLocaleString()}</div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Security Tab ──────────────────────────────────────────────────────

const severityColors: Record<string, string> = {
  low: "bg-gray-100 text-gray-600",
  medium: "bg-yellow-50 text-yellow-700",
  high: "bg-orange-50 text-orange-700",
  critical: "bg-red-50 text-red-600",
};

function SecurityTab() {
  const queryClient = useQueryClient();
  const [filterSeverity, setFilterSeverity] = useState<string>("");

  const { data: summary } = useQuery({
    queryKey: ["infra-security-summary"],
    queryFn: () => platformInfraApi.securitySummary(24).then((r) => r.data.data),
    refetchInterval: 30000,
  });

  const { data: events, isLoading } = useQuery({
    queryKey: ["infra-security-events", filterSeverity],
    queryFn: () =>
      platformInfraApi
        .securityEvents({
          severity: filterSeverity || undefined,
          limit: 100,
        })
        .then((r) => r.data.data),
    refetchInterval: 15000,
  });

  const acknowledgeMutation = useMutation({
    mutationFn: (id: string) => platformInfraApi.acknowledgeEvent(id).then((r) => r.data.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["infra-security-events"] });
      queryClient.invalidateQueries({ queryKey: ["infra-security-summary"] });
    },
  });

  const scanMutation = useMutation({
    mutationFn: () => platformInfraApi.triggerSecurityScan().then((r) => r.data.data),
    onSuccess: (data) => {
      toast.success(`Scan complete: ${data.total_new_events} new events`);
      queryClient.invalidateQueries({ queryKey: ["infra-security-events"] });
      queryClient.invalidateQueries({ queryKey: ["infra-security-summary"] });
    },
    onError: () => toast.error("Security scan failed"),
  });

  return (
    <div className="space-y-6">
      {/* Summary Cards */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardContent className="pt-6">
            <p className="text-sm font-medium text-gray-500">Total Events (24h)</p>
            <p className="mt-1 text-2xl font-bold text-gray-900">{summary?.total_events ?? 0}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <p className="text-sm font-medium text-gray-500">Unacknowledged</p>
            <p className={`mt-1 text-2xl font-bold ${(summary?.unacknowledged ?? 0) > 0 ? "text-red-600" : "text-green-600"}`}>
              {summary?.unacknowledged ?? 0}
            </p>
          </CardContent>
        </Card>
        {summary?.by_severity
          .filter((s) => s.severity === "high" || s.severity === "critical")
          .map((s) => (
            <Card key={s.severity}>
              <CardContent className="pt-6">
                <p className="text-sm font-medium text-gray-500 capitalize">{s.severity}</p>
                <p className={`mt-1 text-2xl font-bold ${s.severity === "critical" ? "text-red-600" : "text-orange-600"}`}>
                  {s.count}
                </p>
              </CardContent>
            </Card>
          ))}
      </div>

      {/* Actions */}
      <div className="flex flex-wrap items-center gap-3">
        <Button onClick={() => scanMutation.mutate()} disabled={scanMutation.isPending} variant="outline">
          {scanMutation.isPending ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <Shield className="mr-1 h-4 w-4" />}
          Run Security Scan
        </Button>
        <select
          value={filterSeverity}
          onChange={(e) => setFilterSeverity(e.target.value)}
          className="rounded-md border border-gray-300 px-3 py-2 text-sm"
        >
          <option value="">All severities</option>
          <option value="critical">Critical</option>
          <option value="high">High</option>
          <option value="medium">Medium</option>
          <option value="low">Low</option>
        </select>
      </div>

      {/* Events Feed */}
      {isLoading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-8 w-8 animate-spin text-indigo-600" />
        </div>
      ) : !events?.length ? (
        <div className="rounded-lg border border-dashed border-gray-300 py-12 text-center">
          <Shield className="mx-auto h-10 w-10 text-gray-300" />
          <p className="mt-2 text-sm text-gray-500">No security events</p>
        </div>
      ) : (
        <div className="space-y-2">
          {events.map((ev) => (
            <div
              key={ev.id}
              className={`rounded-lg border bg-white p-4 ${ev.acknowledged ? "border-gray-100 opacity-60" : "border-gray-200"}`}
            >
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    {ev.severity === "critical" ? (
                      <XCircle className="h-4 w-4 text-red-500" />
                    ) : ev.severity === "high" ? (
                      <AlertTriangle className="h-4 w-4 text-orange-500" />
                    ) : (
                      <Clock className="h-4 w-4 text-gray-400" />
                    )}
                    <span className="text-sm font-semibold text-gray-900">{ev.event_type.replace(/_/g, " ")}</span>
                    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${severityColors[ev.severity]}`}>
                      {ev.severity}
                    </span>
                    {ev.acknowledged && (
                      <span className="rounded-full bg-green-50 px-2 py-0.5 text-xs font-medium text-green-700">
                        acknowledged
                      </span>
                    )}
                  </div>
                  <div className="mt-1 flex flex-wrap gap-3 text-xs text-gray-500">
                    {ev.source_ip && <span>IP: {ev.source_ip}</span>}
                    {ev.endpoint && <span>Endpoint: {ev.endpoint}</span>}
                    <span>{format(new Date(ev.created_at), "MMM d, h:mm:ss a")}</span>
                  </div>
                  {ev.details && Object.keys(ev.details).length > 0 && (
                    <p className="mt-1 font-mono text-xs text-gray-400">
                      {JSON.stringify(ev.details)}
                    </p>
                  )}
                </div>
                {!ev.acknowledged && (
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => acknowledgeMutation.mutate(ev.id)}
                    disabled={acknowledgeMutation.isPending}
                  >
                    <CheckCircle2 className="mr-1 h-3 w-3" />
                    Ack
                  </Button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────

export default function PlatformInfrastructurePage() {
  const [activeTab, setActiveTab] = useState<TabId>("database");

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-900">Infrastructure</h1>

      {/* Tab Bar */}
      <div className="flex gap-1 rounded-lg border border-gray-200 bg-gray-50 p-1">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`flex items-center gap-1.5 rounded-md px-4 py-2 text-sm font-medium transition-colors ${
              activeTab === tab.id
                ? "bg-white text-indigo-700 shadow-sm"
                : "text-gray-500 hover:text-gray-700"
            }`}
          >
            <tab.icon className="h-4 w-4" />
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      {activeTab === "database" && <DatabaseTab />}
      {activeTab === "backups" && <BackupsTab />}
      {activeTab === "traffic" && <TrafficTab />}
      {activeTab === "security" && <SecurityTab />}
    </div>
  );
}
