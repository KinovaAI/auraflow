"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { useInfiniteQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import {
  Plus,
  Loader2,
  Search,
  Mail,
  Phone,
  AlertTriangle,
  SlidersHorizontal,
  X,
} from "lucide-react";
import toast from "react-hot-toast";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { MemberFormModal } from "@/components/members/member-form-modal";
import { membersApi, type Member, type MemberFilterParams } from "@/lib/members-api";

const PAGE_SIZE = 50;

interface MemberFilters {
  membership_status: string;
  has_failed_payments: string;
  churn_risk: string;
  has_coupon: string;
  min_visits: string;
  max_visits: string;
  inactive_weeks: string;
  joined_after: string;
  joined_before: string;
  min_revenue: string;
  sort_by: string;
  sort_dir: string;
}

const EMPTY_FILTERS: MemberFilters = {
  membership_status: "",
  has_failed_payments: "",
  churn_risk: "",
  has_coupon: "",
  min_visits: "",
  max_visits: "",
  inactive_weeks: "",
  joined_after: "",
  joined_before: "",
  min_revenue: "",
  sort_by: "",
  sort_dir: "desc",
};

export default function MembersPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [filters, setFilters] = useState<MemberFilters>(EMPTY_FILTERS);
  const [appliedFilters, setAppliedFilters] = useState<MemberFilters>(EMPTY_FILTERS);
  const debounceRef = useRef<NodeJS.Timeout | null>(null);
  const filterDebounceRef = useRef<NodeJS.Timeout | null>(null);
  const sentinelRef = useRef<HTMLDivElement>(null);

  const handleSearch = (value: string) => {
    setSearch(value);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => setDebouncedSearch(value), 300);
  };

  // Debounce filter changes
  useEffect(() => {
    if (filterDebounceRef.current) clearTimeout(filterDebounceRef.current);
    filterDebounceRef.current = setTimeout(() => setAppliedFilters(filters), 300);
    return () => {
      if (filterDebounceRef.current) clearTimeout(filterDebounceRef.current);
    };
  }, [filters]);

  useEffect(() => {
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, []);

  const activeFilterCount = Object.entries(appliedFilters).filter(
    ([k, v]) => k !== "sort_dir" && v !== ""
  ).length;

  const buildParams = useCallback(
    (offset: number): MemberFilterParams => {
      const p: MemberFilterParams = {
        search: debouncedSearch || undefined,
        limit: PAGE_SIZE,
        offset,
      };
      if (appliedFilters.membership_status)
        p.membership_status = appliedFilters.membership_status;
      if (appliedFilters.has_failed_payments === "true")
        p.has_failed_payments = true;
      if (appliedFilters.churn_risk === "true") p.churn_risk = true;
      if (appliedFilters.min_visits)
        p.min_visits = parseInt(appliedFilters.min_visits);
      if (appliedFilters.max_visits)
        p.max_visits = parseInt(appliedFilters.max_visits);
      if (appliedFilters.inactive_weeks)
        p.inactive_weeks = parseInt(appliedFilters.inactive_weeks);
      if (appliedFilters.joined_after)
        p.joined_after = appliedFilters.joined_after;
      if (appliedFilters.joined_before)
        p.joined_before = appliedFilters.joined_before;
      if (appliedFilters.min_revenue)
        p.min_revenue = Math.round(parseFloat(appliedFilters.min_revenue) * 100);
      if (appliedFilters.has_coupon === "true") p.has_coupon = true;
      if (appliedFilters.sort_by) {
        p.sort_by = appliedFilters.sort_by;
        p.sort_dir = appliedFilters.sort_dir;
      }
      // When advanced filters active, show all members (not just active)
      if (activeFilterCount > 0) p.active_only = false;
      return p;
    },
    [debouncedSearch, appliedFilters, activeFilterCount]
  );

  const { data, isLoading, fetchNextPage, hasNextPage, isFetchingNextPage } =
    useInfiniteQuery({
      queryKey: ["members", debouncedSearch, appliedFilters],
      queryFn: ({ pageParam = 0 }) =>
        membersApi.list(buildParams(pageParam)).then((r) => r.data),
      initialPageParam: 0,
      getNextPageParam: (lastPage, allPages) => {
        if (lastPage.length < PAGE_SIZE) return undefined;
        return allPages.reduce((sum, page) => sum + page.length, 0);
      },
    });

  const members = data?.pages.flat() ?? [];

  // Auto-load more when scrolling to bottom
  useEffect(() => {
    if (!sentinelRef.current || !hasNextPage) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && hasNextPage && !isFetchingNextPage) {
          fetchNextPage();
        }
      },
      { threshold: 0.1 }
    );
    observer.observe(sentinelRef.current);
    return () => observer.disconnect();
  }, [hasNextPage, isFetchingNextPage, fetchNextPage]);

  const updateFilter = (key: keyof MemberFilters, value: string) => {
    setFilters((f) => ({ ...f, [key]: value }));
  };

  const selectClass =
    "flex h-9 w-full rounded-md border border-gray-300 bg-white px-3 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500";

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Members</h1>
          <p className="text-sm text-gray-500">
            {members.length}
            {hasNextPage ? "+" : ""} members
            {activeFilterCount > 0 && " (filtered)"}
          </p>
        </div>
        <Button onClick={() => setShowForm(true)}>
          <Plus className="mr-2 h-4 w-4" />
          Add Member
        </Button>
      </div>

      {/* Search bar + Advanced toggle */}
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
        <div className="relative flex-1 sm:max-w-sm">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
          <Input
            placeholder="Search by name, email, or phone..."
            value={search}
            onChange={(e) => handleSearch(e.target.value)}
            className="pl-9"
          />
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => setShowAdvanced(!showAdvanced)}
          className={showAdvanced ? "border-indigo-300 bg-indigo-50" : ""}
        >
          <SlidersHorizontal className="mr-1.5 h-4 w-4" />
          Advanced
          {activeFilterCount > 0 && (
            <span className="ml-1.5 rounded-full bg-indigo-100 px-1.5 py-0.5 text-xs font-medium text-indigo-700">
              {activeFilterCount}
            </span>
          )}
        </Button>
      </div>

      {/* Advanced filter panel */}
      {showAdvanced && (
        <div className="rounded-lg border border-gray-200 bg-gray-50 p-4 space-y-3">
          {/* Row 1: Dropdowns */}
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <div>
              <label className="text-xs font-medium text-gray-500">
                Membership Status
              </label>
              <select
                value={filters.membership_status}
                onChange={(e) =>
                  updateFilter("membership_status", e.target.value)
                }
                className={`mt-1 ${selectClass}`}
              >
                <option value="">Any</option>
                <option value="active">Active</option>
                <option value="frozen">Frozen</option>
                <option value="cancelled">Cancelled</option>
                <option value="expired">Expired</option>
                <option value="none">No Membership</option>
              </select>
            </div>
            <div>
              <label className="text-xs font-medium text-gray-500">
                Sort By
              </label>
              <select
                value={filters.sort_by}
                onChange={(e) => updateFilter("sort_by", e.target.value)}
                className={`mt-1 ${selectClass}`}
              >
                <option value="">Name (default)</option>
                <option value="total_visits">Total Visits</option>
                <option value="lifetime_revenue_cents">Revenue</option>
                <option value="last_visit_at">Last Visit</option>
                <option value="joined_at">Join Date</option>
              </select>
            </div>
            <div>
              <label className="text-xs font-medium text-gray-500">
                Direction
              </label>
              <select
                value={filters.sort_dir}
                onChange={(e) => updateFilter("sort_dir", e.target.value)}
                className={`mt-1 ${selectClass}`}
              >
                <option value="desc">Highest / Newest First</option>
                <option value="asc">Lowest / Oldest First</option>
              </select>
            </div>
          </div>

          {/* Row 2: Visits / Inactivity */}
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <div>
              <label className="text-xs font-medium text-gray-500">
                Min Visits
              </label>
              <Input
                type="number"
                min={0}
                value={filters.min_visits}
                onChange={(e) => updateFilter("min_visits", e.target.value)}
                placeholder="0"
                className="mt-1 h-9"
              />
            </div>
            <div>
              <label className="text-xs font-medium text-gray-500">
                Max Visits
              </label>
              <Input
                type="number"
                min={0}
                value={filters.max_visits}
                onChange={(e) => updateFilter("max_visits", e.target.value)}
                placeholder="No max"
                className="mt-1 h-9"
              />
            </div>
            <div>
              <label className="text-xs font-medium text-gray-500">
                Inactive For
              </label>
              <div className="mt-1 flex items-center gap-2">
                <Input
                  type="number"
                  min={1}
                  value={filters.inactive_weeks}
                  onChange={(e) =>
                    updateFilter("inactive_weeks", e.target.value)
                  }
                  placeholder="e.g. 4"
                  className="h-9"
                />
                <span className="whitespace-nowrap text-xs text-gray-500">
                  weeks
                </span>
              </div>
            </div>
          </div>

          {/* Row 3: Dates / Revenue */}
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <div>
              <label className="text-xs font-medium text-gray-500">
                Joined After
              </label>
              <Input
                type="date"
                value={filters.joined_after}
                onChange={(e) => updateFilter("joined_after", e.target.value)}
                className="mt-1 h-9"
              />
            </div>
            <div>
              <label className="text-xs font-medium text-gray-500">
                Joined Before
              </label>
              <Input
                type="date"
                value={filters.joined_before}
                onChange={(e) => updateFilter("joined_before", e.target.value)}
                className="mt-1 h-9"
              />
            </div>
            <div>
              <label className="text-xs font-medium text-gray-500">
                Min Revenue ($)
              </label>
              <Input
                type="number"
                min={0}
                step="0.01"
                value={filters.min_revenue}
                onChange={(e) => updateFilter("min_revenue", e.target.value)}
                placeholder="0.00"
                className="mt-1 h-9"
              />
            </div>
          </div>

          {/* Row 4: Checkboxes + Clear */}
          <div className="flex flex-wrap items-center gap-4 pt-1">
            <label className="flex items-center gap-2 text-sm text-gray-700">
              <input
                type="checkbox"
                checked={filters.churn_risk === "true"}
                onChange={(e) =>
                  updateFilter("churn_risk", e.target.checked ? "true" : "")
                }
                className="h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
              />
              Churn Risk
            </label>
            <label className="flex items-center gap-2 text-sm text-gray-700">
              <input
                type="checkbox"
                checked={filters.has_failed_payments === "true"}
                onChange={(e) =>
                  updateFilter(
                    "has_failed_payments",
                    e.target.checked ? "true" : ""
                  )
                }
                className="h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
              />
              Failed Payments
            </label>
            <label className="flex items-center gap-2 text-sm text-gray-700">
              <input
                type="checkbox"
                checked={filters.has_coupon === "true"}
                onChange={(e) =>
                  updateFilter("has_coupon", e.target.checked ? "true" : "")
                }
                className="h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
              />
              Has Coupon
            </label>
            <div className="ml-auto">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setFilters(EMPTY_FILTERS)}
                disabled={activeFilterCount === 0}
              >
                <X className="mr-1 h-3.5 w-3.5" />
                Clear All
              </Button>
            </div>
          </div>
        </div>
      )}

      {isLoading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="h-8 w-8 animate-spin text-indigo-600" />
        </div>
      ) : !members.length ? (
        <div className="rounded-lg border border-dashed border-gray-300 py-12 text-center">
          <p className="text-sm text-gray-500">
            {debouncedSearch || activeFilterCount > 0
              ? "No members match your search or filters"
              : "No members yet"}
          </p>
          {!debouncedSearch && activeFilterCount === 0 && (
            <Button
              variant="link"
              className="mt-2"
              onClick={() => setShowForm(true)}
            >
              Add your first member
            </Button>
          )}
        </div>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                  Name
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                  Contact
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                  Visits
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                  Status
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {members.map((member) => (
                <tr
                  key={member.id}
                  className="cursor-pointer hover:bg-gray-50"
                  onClick={() =>
                    router.push(`/dashboard/members/${member.id}`)
                  }
                >
                  <td className="whitespace-nowrap px-4 py-3">
                    <div className="flex items-center gap-3">
                      <div className="flex h-8 w-8 items-center justify-center rounded-full bg-indigo-100 text-xs font-medium text-indigo-700">
                        {(member.first_name || "?")[0]}
                        {(member.last_name || "?")[0]}
                      </div>
                      <div>
                        <p className="text-sm font-medium text-gray-900">
                          {member.first_name} {member.last_name}
                        </p>
                        {member.member_number && (
                          <p className="text-xs text-gray-400">
                            #{member.member_number}
                          </p>
                        )}
                      </div>
                    </div>
                  </td>
                  <td className="whitespace-nowrap px-4 py-3">
                    <div className="space-y-0.5">
                      <div className="flex items-center gap-1 text-xs text-gray-500">
                        <Mail className="h-3 w-3" />
                        {member.email}
                      </div>
                      {member.phone && (
                        <div className="flex items-center gap-1 text-xs text-gray-500">
                          <Phone className="h-3 w-3" />
                          {member.phone}
                        </div>
                      )}
                    </div>
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-sm text-gray-600">
                    {member.total_visits}
                  </td>
                  <td className="whitespace-nowrap px-4 py-3">
                    <div className="flex items-center gap-2">
                      <span
                        className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${
                          member.is_active
                            ? "bg-green-50 text-green-700"
                            : "bg-gray-100 text-gray-500"
                        }`}
                      >
                        {member.is_active ? "Active" : "Inactive"}
                      </span>
                      {member.stripe_coupon_id && (
                        <span className="inline-flex items-center gap-1 rounded-full bg-purple-50 px-2 py-0.5 text-xs font-medium text-purple-700">
                          {member.stripe_coupon_id}
                        </span>
                      )}
                      {member.churn_risk_flagged_at && (
                        <span className="inline-flex items-center gap-1 rounded-full bg-red-50 px-2 py-0.5 text-xs font-medium text-red-700">
                          <AlertTriangle className="h-3 w-3" />
                          At Risk
                        </span>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {/* Infinite scroll sentinel */}
          <div ref={sentinelRef} className="h-1" />
          {isFetchingNextPage && (
            <div className="flex justify-center py-4">
              <Loader2 className="h-5 w-5 animate-spin text-gray-400" />
            </div>
          )}
        </div>
      )}

      {showForm && (
        <MemberFormModal
          onClose={() => setShowForm(false)}
          onCreated={() => {
            queryClient.invalidateQueries({ queryKey: ["members"] });
            setShowForm(false);
            toast.success("Member added");
          }}
        />
      )}
    </div>
  );
}
