"use client";

import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { Loader2, Search, Briefcase, Star, Building2 } from "lucide-react";
import Link from "next/link";

import { hiringApi, type ApplicationStatus } from "@/lib/hiring-api";
import { usePermission } from "@/hooks/use-permission";

const STATUSES: { key: ApplicationStatus; label: string }[] = [
  { key: "new", label: "New" },
  { key: "reviewed", label: "Reviewed" },
  { key: "shortlisted", label: "Shortlisted" },
  { key: "interviewed", label: "Interviewed" },
  { key: "offer", label: "Offer" },
  { key: "hired", label: "Hired" },
  { key: "rejected", label: "Rejected" },
];

const STATUS_STYLES: Record<string, string> = {
  new: "bg-blue-50 text-blue-700",
  reviewed: "bg-slate-100 text-slate-700",
  shortlisted: "bg-amber-50 text-amber-700",
  interviewed: "bg-purple-50 text-purple-700",
  offer: "bg-teal-50 text-teal-700",
  hired: "bg-green-50 text-green-700",
  rejected: "bg-gray-100 text-gray-500",
};

function StatusBadge({ status }: { status: string }) {
  return (
    <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${STATUS_STYLES[status] || STATUS_STYLES.reviewed}`}>
      {STATUSES.find((s) => s.key === status)?.label || status}
    </span>
  );
}

export default function HiringPipelinePage() {
  const hasAccess = usePermission("hiring.view");
  const canManageEmployer = usePermission("hiring.manage_employer");
  const router = useRouter();
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [search, setSearch] = useState("");
  const [debounced, setDebounced] = useState("");

  useEffect(() => {
    const t = setTimeout(() => setDebounced(search), 300);
    return () => clearTimeout(t);
  }, [search]);

  useEffect(() => {
    if (!hasAccess) router.push("/dashboard");
  }, [hasAccess, router]);

  const { data: applications, isLoading } = useQuery({
    queryKey: ["hiring-applications", statusFilter, debounced],
    queryFn: () =>
      hiringApi.list({ status: statusFilter || undefined, q: debounced || undefined }),
    enabled: hasAccess,
  });

  if (!hasAccess) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 className="h-8 w-8 animate-spin text-indigo-600" />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-semibold text-gray-900">
            <Briefcase className="h-6 w-6 text-indigo-600" /> Hiring
          </h1>
          <p className="text-sm text-gray-500">Review job applications and hire new staff.</p>
        </div>
        {canManageEmployer && (
          <Link
            href="/dashboard/hiring/employer"
            className="inline-flex items-center gap-2 rounded-md border border-gray-300 bg-white px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
          >
            <Building2 className="h-4 w-4" /> Employer Profile
          </Link>
        )}
      </div>

      {/* Filters */}
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search name, email, position…"
            className="h-9 w-full rounded-md border border-gray-300 bg-white pl-9 pr-3 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          />
        </div>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="h-9 rounded-md border border-gray-300 bg-white px-3 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
        >
          <option value="">All statuses</option>
          {STATUSES.map((s) => (
            <option key={s.key} value={s.key}>{s.label}</option>
          ))}
        </select>
      </div>

      {/* List */}
      {isLoading ? (
        <div className="flex items-center justify-center py-16">
          <Loader2 className="h-8 w-8 animate-spin text-indigo-600" />
        </div>
      ) : !applications || applications.length === 0 ? (
        <div className="rounded-lg border border-gray-200 bg-white py-16 text-center">
          <Briefcase className="mx-auto mb-3 h-10 w-10 text-gray-300" />
          <p className="text-sm text-gray-500">No applications{statusFilter ? " in this stage" : " yet"}.</p>
        </div>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                {["Applicant", "Position", "Status", "Rating", "Docs", "Applied"].map((h) => (
                  <th key={h} className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {applications.map((a) => (
                <tr
                  key={a.id}
                  className="cursor-pointer hover:bg-gray-50"
                  onClick={() => router.push(`/dashboard/hiring/${a.id}`)}
                >
                  <td className="px-4 py-3">
                    <div className="text-sm font-medium text-gray-900">{a.first_name} {a.last_name}</div>
                    <div className="text-xs text-gray-500">{a.email}</div>
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-700">
                    {a.position_title || a.position_type.replace("_", " ")}
                  </td>
                  <td className="px-4 py-3"><StatusBadge status={a.status} /></td>
                  <td className="px-4 py-3">
                    {a.rating ? (
                      <span className="inline-flex items-center gap-0.5 text-amber-500">
                        <Star className="h-3.5 w-3.5 fill-amber-400" /> {a.rating}
                      </span>
                    ) : <span className="text-gray-300">—</span>}
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-500">{a.document_count}</td>
                  <td className="px-4 py-3 text-sm text-gray-500">
                    {new Date(a.created_at).toLocaleDateString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
