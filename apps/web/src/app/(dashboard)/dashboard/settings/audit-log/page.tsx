"use client";

import { useState, useEffect, useCallback } from "react";
import { Loader2, Search, Clock, User, FileText } from "lucide-react";
import toast from "react-hot-toast";

import { activityApi } from "@/lib/activity-api";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

interface AuditEntry {
  id: string;
  actor_name?: string;
  action: string;
  resource_type?: string;
  resource_id?: string;
  details?: string;
  created_at: string;
}

const ACTION_FILTERS = [
  "All",
  "create",
  "update",
  "delete",
  "login",
  "import",
  "export",
] as const;

function formatTimestamp(iso: string) {
  return new Date(iso).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function actionBadge(action: string) {
  let classes = "bg-gray-100 text-gray-700";
  if (action.includes("create") || action.includes("add")) {
    classes = "bg-green-50 text-green-700";
  } else if (action.includes("update") || action.includes("edit")) {
    classes = "bg-blue-50 text-blue-700";
  } else if (action.includes("delete") || action.includes("remove")) {
    classes = "bg-red-50 text-red-700";
  } else if (action.includes("login") || action.includes("auth")) {
    classes = "bg-purple-50 text-purple-700";
  }
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${classes}`}
    >
      {action}
    </span>
  );
}

export default function AuditLogPage() {
  const [entries, setEntries] = useState<AuditEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [actionFilter, setActionFilter] = useState<string>("All");
  const [page, setPage] = useState(1);
  const pageSize = 25;

  const fetchEntries = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await activityApi.feed(200);
      setEntries(resp.data?.data ?? resp.data ?? []);
    } catch {
      toast.error("Failed to load audit log");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchEntries();
  }, [fetchEntries]);

  const filtered = entries.filter((e) => {
    if (
      actionFilter !== "All" &&
      !e.action.toLowerCase().includes(actionFilter.toLowerCase())
    ) {
      return false;
    }
    if (search) {
      const q = search.toLowerCase();
      return (
        e.action.toLowerCase().includes(q) ||
        e.actor_name?.toLowerCase().includes(q) ||
        e.resource_type?.toLowerCase().includes(q) ||
        e.details?.toLowerCase().includes(q)
      );
    }
    return true;
  });

  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const safePage = Math.min(page, totalPages);
  const paginated = filtered.slice(
    (safePage - 1) * pageSize,
    safePage * pageSize,
  );

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="relative max-w-sm flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
          <Input
            className="pl-9"
            placeholder="Search audit log..."
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(1);
            }}
          />
        </div>
        <div className="flex gap-1 rounded-lg bg-white p-1 shadow-sm">
          {ACTION_FILTERS.map((f) => (
            <button
              key={f}
              onClick={() => {
                setActionFilter(f);
                setPage(1);
              }}
              className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
                actionFilter === f
                  ? "bg-indigo-600 text-white"
                  : "text-gray-600 hover:text-gray-900"
              }`}
            >
              {f}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-16">
          <Loader2 className="h-6 w-6 animate-spin text-indigo-600" />
        </div>
      ) : paginated.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center">
            <FileText className="mx-auto mb-3 h-10 w-10 text-gray-300" />
            <p className="text-gray-500">No audit log entries found.</p>
          </CardContent>
        </Card>
      ) : (
        <>
          <Card>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-200 text-left">
                    <th className="px-4 py-3 font-medium text-gray-500">
                      <span className="flex items-center gap-1">
                        <Clock className="h-3.5 w-3.5" />
                        Timestamp
                      </span>
                    </th>
                    <th className="px-4 py-3 font-medium text-gray-500">
                      <span className="flex items-center gap-1">
                        <User className="h-3.5 w-3.5" />
                        Actor
                      </span>
                    </th>
                    <th className="px-4 py-3 font-medium text-gray-500">
                      Action
                    </th>
                    <th className="px-4 py-3 font-medium text-gray-500">
                      Resource
                    </th>
                    <th className="px-4 py-3 font-medium text-gray-500">
                      Details
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {paginated.map((entry) => (
                    <tr key={entry.id} className="hover:bg-gray-50">
                      <td className="whitespace-nowrap px-4 py-3 text-gray-600">
                        {formatTimestamp(entry.created_at)}
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 text-gray-900">
                        {entry.actor_name || "--"}
                      </td>
                      <td className="px-4 py-3">{actionBadge(entry.action)}</td>
                      <td className="whitespace-nowrap px-4 py-3 text-gray-600">
                        {entry.resource_type || "--"}
                        {entry.resource_id && (
                          <span className="ml-1 font-mono text-xs text-gray-400">
                            {entry.resource_id.slice(0, 8)}
                          </span>
                        )}
                      </td>
                      <td className="max-w-xs truncate px-4 py-3 text-gray-500">
                        {entry.details || "--"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>

          {totalPages > 1 && (
            <div className="flex items-center justify-between">
              <p className="text-sm text-gray-500">
                Showing {(safePage - 1) * pageSize + 1}-
                {Math.min(safePage * pageSize, filtered.length)} of{" "}
                {filtered.length} entries
              </p>
              <div className="flex gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  disabled={safePage <= 1}
                  onClick={() => setPage((p) => p - 1)}
                >
                  Previous
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={safePage >= totalPages}
                  onClick={() => setPage((p) => p + 1)}
                >
                  Next
                </Button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
