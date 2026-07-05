"use client";

import { useEffect, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { format } from "date-fns";
import {
  Loader2,
  Plus,
  Download,
  Pencil,
  XCircle,
} from "lucide-react";
import toast from "react-hot-toast";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  membershipTypesApi,
  memberMembershipsApi,
  type MembershipType,
  type MemberMembership,
} from "@/lib/memberships-api";
import { studiosApi } from "@/lib/scheduling-api";
import { MembershipTypeModal } from "@/components/memberships/membership-type-modal";

// ── Badge helpers ────────────────────────────────────────────────────────────

function AccessScopeBadge({ scope }: { scope?: string }) {
  const styles: Record<string, string> = {
    in_studio: "bg-purple-50 text-purple-700",
    online: "bg-blue-50 text-blue-700",
    all_access: "bg-green-50 text-green-700",
  };
  const labels: Record<string, string> = {
    in_studio: "In-Studio",
    online: "Online",
    all_access: "All-Access",
  };
  const key = scope || "in_studio";
  return (
    <span
      className={`rounded-full px-2 py-0.5 text-xs font-medium ${styles[key] || "bg-gray-100 text-gray-600"}`}
    >
      {labels[key] || key}
    </span>
  );
}

function TypeBadge({ type }: { type: string }) {
  const styles: Record<string, string> = {
    unlimited: "bg-indigo-50 text-indigo-700",
    class_pack: "bg-orange-50 text-orange-700",
    single_class: "bg-gray-100 text-gray-600",
    intro_offer: "bg-pink-50 text-pink-700",
    day_pass: "bg-amber-50 text-amber-700",
  };
  const labels: Record<string, string> = {
    unlimited: "Unlimited",
    class_pack: "Class Pack",
    single_class: "Single Class",
    intro_offer: "Intro Offer",
    day_pass: "Day Pass",
  };
  return (
    <span
      className={`rounded-full px-2 py-0.5 text-xs font-medium ${styles[type] || "bg-gray-100 text-gray-600"}`}
    >
      {labels[type] || type}
    </span>
  );
}

function StatusBadge({ active }: { active: boolean }) {
  return (
    <span
      className={`rounded-full px-2 py-0.5 text-xs font-medium ${
        active
          ? "bg-green-50 text-green-700"
          : "bg-gray-100 text-gray-500"
      }`}
    >
      {active ? "Active" : "Inactive"}
    </span>
  );
}

function MembershipStatusBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    active: "bg-green-50 text-green-700",
    frozen: "bg-blue-50 text-blue-700",
    cancelled: "bg-red-50 text-red-600",
    expired: "bg-gray-100 text-gray-500",
    pending: "bg-yellow-50 text-yellow-700",
  };
  return (
    <span
      className={`rounded-full px-2 py-0.5 text-xs font-medium ${styles[status] || "bg-gray-100 text-gray-500"}`}
    >
      {status}
    </span>
  );
}

// ── Main Page ────────────────────────────────────────────────────────────────

export default function MembershipsPage() {
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<"types" | "active">("types");
  const [showModal, setShowModal] = useState(false);
  const [editingType, setEditingType] = useState<MembershipType | null>(null);
  const [studioId, setStudioId] = useState<string | null>(null);
  const [memberSearch, setMemberSearch] = useState("");

  // Fetch studios to get the first one
  const { data: studios } = useQuery({
    queryKey: ["studios"],
    queryFn: () => studiosApi.list().then((r) => r.data),
  });

  useEffect(() => {
    if (studios && studios.length > 0 && !studioId) {
      setStudioId(studios[0].id);
    }
  }, [studios, studioId]);

  // Membership types
  const { data: types, isLoading: typesLoading } = useQuery({
    queryKey: ["membership-types", studioId],
    queryFn: () =>
      membershipTypesApi.list(studioId!).then((r) => r.data),
    enabled: !!studioId,
  });

  // Active memberships
  const { data: activeMemberships, isLoading: membershipsLoading } = useQuery({
    queryKey: ["active-memberships"],
    queryFn: () =>
      memberMembershipsApi.listAll(true).then((r) => r.data),
  });

  // Seed defaults
  const seedMutation = useMutation({
    mutationFn: () => membershipTypesApi.seedDefaults(studioId!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["membership-types"] });
      toast.success("Default templates loaded");
    },
    onError: () => toast.error("Failed to load default templates"),
  });

  // Deactivate
  const deactivateMutation = useMutation({
    mutationFn: (id: string) => membershipTypesApi.deactivate(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["membership-types"] });
      toast.success("Membership type deactivated");
    },
    onError: () => toast.error("Failed to deactivate"),
  });

  // Reactivate (update is_active to true)
  const reactivateMutation = useMutation({
    mutationFn: (id: string) =>
      membershipTypesApi.update(id, { is_active: true }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["membership-types"] });
      toast.success("Membership type activated");
    },
    onError: () => toast.error("Failed to activate"),
  });

  const fmt = (cents: number) => `$${(cents / 100).toFixed(2)}`;

  const handleEdit = (mt: MembershipType) => {
    setEditingType(mt);
    setShowModal(true);
  };

  const handleCloseModal = () => {
    setShowModal(false);
    setEditingType(null);
    // Refresh membership types after modal close
    queryClient.invalidateQueries({ queryKey: ["membership-types"] });
  };

  // Summary stats
  const activeTypesCount = types?.filter((t) => t.is_active).length ?? 0;
  const totalMemberships = activeMemberships?.length ?? 0;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Memberships</h1>
          <p className="text-sm text-gray-500">
            Manage membership types and active member subscriptions
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => seedMutation.mutate()}
            disabled={!studioId || seedMutation.isPending}
          >
            {seedMutation.isPending ? (
              <Loader2 className="mr-1 h-4 w-4 animate-spin" />
            ) : (
              <Download className="mr-1 h-4 w-4" />
            )}
            Load Default Templates
          </Button>
          <Button onClick={() => setShowModal(true)}>
            <Plus className="mr-1 h-4 w-4" />
            Add Custom Type
          </Button>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardContent className="pt-6">
            <p className="text-sm font-medium text-gray-500">Active Types</p>
            <p className="mt-1 text-2xl font-bold text-gray-900">
              {typesLoading ? (
                <Loader2 className="h-5 w-5 animate-spin" />
              ) : (
                activeTypesCount
              )}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <p className="text-sm font-medium text-gray-500">
              Total Types
            </p>
            <p className="mt-1 text-2xl font-bold text-gray-900">
              {typesLoading ? (
                <Loader2 className="h-5 w-5 animate-spin" />
              ) : (
                types?.length ?? 0
              )}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <p className="text-sm font-medium text-gray-500">
              Active Memberships
            </p>
            <p className="mt-1 text-2xl font-bold text-gray-900">
              {membershipsLoading ? (
                <Loader2 className="h-5 w-5 animate-spin" />
              ) : (
                totalMemberships
              )}
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Tabs */}
      <div className="flex gap-4 overflow-x-auto border-b border-gray-200">
        {(
          [
            {
              key: "types" as const,
              label: "Membership Types",
              count: types?.length,
            },
            {
              key: "active" as const,
              label: "Active Memberships",
              count: activeMemberships?.length,
            },
          ]
        ).map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`whitespace-nowrap border-b-2 px-1 pb-3 text-sm font-medium ${
              activeTab === tab.key
                ? "border-indigo-500 text-indigo-600"
                : "border-transparent text-gray-500 hover:text-gray-700"
            }`}
          >
            {tab.label}
            {tab.count != null && tab.count > 0 ? (
              <span className="ml-1.5 rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-600">
                {tab.count}
              </span>
            ) : null}
          </button>
        ))}
      </div>

      {/* ── Membership Types Tab ─────────────────────────────────────────────── */}
      {activeTab === "types" && (
        <>
          {typesLoading ? (
            <div className="flex items-center justify-center py-20">
              <Loader2 className="h-8 w-8 animate-spin text-indigo-600" />
            </div>
          ) : !types?.length ? (
            <div className="rounded-lg border border-dashed border-gray-300 py-12 text-center">
              <p className="text-sm text-gray-500">
                No membership types yet. Add a custom type or load default
                templates to get started.
              </p>
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
                      Type
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                      Access Scope
                    </th>
                    <th className="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-gray-500">
                      Price
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                      Billing Period
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                      Status
                    </th>
                    <th className="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-gray-500">
                      Actions
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200">
                  {types.map((mt) => (
                    <tr key={mt.id} className="hover:bg-gray-50">
                      <td className="whitespace-nowrap px-4 py-3 text-sm font-medium text-gray-900">
                        {mt.name}
                        {mt.is_template && (
                          <span className="ml-2 rounded bg-gray-100 px-1.5 py-0.5 text-[10px] font-medium uppercase text-gray-400">
                            Template
                          </span>
                        )}
                      </td>
                      <td className="whitespace-nowrap px-4 py-3">
                        <TypeBadge type={mt.type} />
                      </td>
                      <td className="whitespace-nowrap px-4 py-3">
                        <AccessScopeBadge scope={mt.access_scope} />
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 text-right text-sm font-medium text-gray-900">
                        {fmt(mt.price_cents)}
                        {mt.type === "class_pack" && mt.class_count && (
                          <span className="ml-1 text-xs text-gray-400">
                            / {mt.class_count} classes
                          </span>
                        )}
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 text-sm text-gray-600">
                        {mt.billing_period
                          ? mt.billing_period.replace("_", "-")
                          : "--"}
                      </td>
                      <td className="whitespace-nowrap px-4 py-3">
                        <StatusBadge active={mt.is_active} />
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 text-right">
                        <div className="flex items-center justify-end gap-1">
                          <button
                            onClick={() => handleEdit(mt)}
                            className="rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
                            title="Edit"
                          >
                            <Pencil className="h-4 w-4" />
                          </button>
                          {mt.is_active ? (
                            <button
                              onClick={() => deactivateMutation.mutate(mt.id)}
                              className="rounded p-1 text-gray-400 hover:bg-red-50 hover:text-red-600"
                              title="Deactivate"
                            >
                              <XCircle className="h-4 w-4" />
                            </button>
                          ) : (
                            <button
                              onClick={() => reactivateMutation.mutate(mt.id)}
                              className="rounded px-2 py-0.5 text-xs font-medium text-indigo-600 hover:bg-indigo-50"
                              title="Activate"
                            >
                              Activate
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {/* ── Active Memberships Tab ───────────────────────────────────────────── */}
      {activeTab === "active" && (
        <>
          {membershipsLoading ? (
            <div className="flex items-center justify-center py-20">
              <Loader2 className="h-8 w-8 animate-spin text-indigo-600" />
            </div>
          ) : !activeMemberships?.length ? (
            <div className="rounded-lg border border-dashed border-gray-300 py-12 text-center">
              <p className="text-sm text-gray-500">
                No active memberships yet
              </p>
            </div>
          ) : (
            <>
            {/* Search */}
            <div className="mb-4">
              <input
                type="text"
                placeholder="Search by member name..."
                value={memberSearch}
                onChange={(e) => setMemberSearch(e.target.value)}
                className="w-full max-w-sm rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
            </div>
            <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                      Member Name
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                      Membership Type
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                      Access Scope
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                      Status
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                      Start Date
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                      Expires
                    </th>
                    <th className="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-gray-500">
                      Actions
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200">
                  {[...activeMemberships]
                    .filter((mm) => {
                      if (!memberSearch) return true;
                      const name = `${mm.member_first_name || ""} ${mm.member_last_name || ""}`.toLowerCase();
                      return name.includes(memberSearch.toLowerCase());
                    })
                    .sort((a, b) => {
                      const nameA = `${a.member_last_name || ""} ${a.member_first_name || ""}`.toLowerCase();
                      const nameB = `${b.member_last_name || ""} ${b.member_first_name || ""}`.toLowerCase();
                      return nameA.localeCompare(nameB);
                    })
                    .map((mm) => (
                    <tr key={mm.id} className="hover:bg-gray-50">
                      <td className="whitespace-nowrap px-4 py-3 text-sm font-medium text-gray-900">
                        {mm.member_first_name || ""}{" "}
                        {mm.member_last_name || ""}
                        {!mm.member_first_name &&
                          !mm.member_last_name &&
                          mm.member_id}
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 text-sm text-gray-600">
                        {mm.type_name || mm.membership_type || "--"}
                      </td>
                      <td className="whitespace-nowrap px-4 py-3">
                        <AccessScopeBadge scope={mm.access_scope} />
                      </td>
                      <td className="whitespace-nowrap px-4 py-3">
                        <MembershipStatusBadge status={mm.status} />
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 text-sm text-gray-500">
                        {mm.starts_at
                          ? format(new Date(mm.starts_at), "MMM d, yyyy")
                          : "--"}
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 text-sm text-gray-500">
                        {mm.ends_at
                          ? format(new Date(mm.ends_at), "MMM d, yyyy")
                          : "No expiry"}
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 text-right">
                        <div className="flex items-center justify-end gap-1">
                          {mm.status === "active" && (
                            <button
                              onClick={() => {
                                memberMembershipsApi
                                  .freeze(mm.id)
                                  .then(() => {
                                    queryClient.invalidateQueries({
                                      queryKey: ["active-memberships"],
                                    });
                                    toast.success("Membership frozen");
                                  })
                                  .catch(() =>
                                    toast.error("Failed to freeze")
                                  );
                              }}
                              className="rounded px-2 py-0.5 text-xs font-medium text-blue-600 hover:bg-blue-50"
                            >
                              Freeze
                            </button>
                          )}
                          {mm.status === "frozen" && (
                            <button
                              onClick={() => {
                                memberMembershipsApi
                                  .unfreeze(mm.id)
                                  .then(() => {
                                    queryClient.invalidateQueries({
                                      queryKey: ["active-memberships"],
                                    });
                                    toast.success("Membership unfrozen");
                                  })
                                  .catch(() =>
                                    toast.error("Failed to unfreeze")
                                  );
                              }}
                              className="rounded px-2 py-0.5 text-xs font-medium text-green-600 hover:bg-green-50"
                            >
                              Unfreeze
                            </button>
                          )}
                          {mm.status !== "cancelled" && (
                            <button
                              onClick={() => {
                                memberMembershipsApi
                                  .cancel(mm.id)
                                  .then(() => {
                                    queryClient.invalidateQueries({
                                      queryKey: ["active-memberships"],
                                    });
                                    toast.success("Membership cancelled");
                                  })
                                  .catch(() =>
                                    toast.error("Failed to cancel")
                                  );
                              }}
                              className="rounded px-2 py-0.5 text-xs font-medium text-red-600 hover:bg-red-50"
                            >
                              Cancel
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            </>
          )}
        </>
      )}

      {/* Modal */}
      {showModal && studioId && (
        <MembershipTypeModal
          studioId={studioId}
          membershipType={editingType}
          onClose={handleCloseModal}
        />
      )}
    </div>
  );
}
