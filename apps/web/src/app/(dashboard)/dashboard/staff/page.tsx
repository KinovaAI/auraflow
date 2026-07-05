"use client";

import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2, Search, Users2, UserPlus, X } from "lucide-react";
import toast from "react-hot-toast";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { StaffTable } from "@/components/staff/staff-table";
import { staffApi } from "@/lib/staff-api";
import { usePermission } from "@/hooks/use-permission";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/stores/auth-store";

const STAFF_ROLES = [
  { value: "admin", label: "Admin", description: "Full access to all modules" },
  { value: "instructor", label: "Instructor", description: "Schedule, classes, video, time clock" },
  { value: "front_desk", label: "Front Desk", description: "Members, payments, POS, schedule" },
];

export default function StaffPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const hasAccess = usePermission("staff.view");
  const isLoading_ = useAuthStore((s) => s.isLoading);
  const user = useAuthStore((s) => s.user);
  const [search, setSearch] = useState("");
  const [showInvite, setShowInvite] = useState(false);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState("front_desk");

  const activeOrgSlug = user?.active_org_slug ?? user?.organizations?.[0]?.slug;

  const { data: staff, isLoading } = useQuery({
    queryKey: ["staff"],
    queryFn: () => staffApi.list().then((r) => r.data),
    enabled: hasAccess,
  });

  const inviteMutation = useMutation({
    mutationFn: (data: { email: string; role: string }) =>
      staffApi.invite(activeOrgSlug!, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["staff"] });
      toast.success(`Invited ${inviteEmail} as ${inviteRole}`);
      setShowInvite(false);
      setInviteEmail("");
      setInviteRole("front_desk");
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      toast.error(typeof detail === "string" ? detail : "Failed to invite staff member");
    },
  });

  useEffect(() => {
    if (!isLoading_ && !hasAccess) {
      router.push("/dashboard");
    }
  }, [isLoading_, hasAccess, router]);

  if (!hasAccess) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 className="h-8 w-8 animate-spin text-indigo-600" />
      </div>
    );
  }

  const filtered = staff?.filter((member) => {
    if (!search) return true;
    const q = search.toLowerCase();
    const name = [member.first_name, member.last_name]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
    return (
      name.includes(q) ||
      member.email.toLowerCase().includes(q) ||
      member.role.includes(q) ||
      member.title?.toLowerCase().includes(q) ||
      member.department?.toLowerCase().includes(q)
    );
  });

  const handleInvite = (e: React.FormEvent) => {
    e.preventDefault();
    if (!inviteEmail.trim() || !activeOrgSlug) return;
    inviteMutation.mutate({ email: inviteEmail.trim().toLowerCase(), role: inviteRole });
  };

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Staff Management</h1>
          <p className="text-sm text-gray-500">
            Manage your team members, roles, and permissions
          </p>
        </div>
        <Button onClick={() => setShowInvite(true)}>
          <UserPlus className="mr-2 h-4 w-4" />
          Add Staff Member
        </Button>
      </div>

      {/* Invite Modal */}
      {showInvite && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="w-full max-w-md rounded-lg bg-white p-6 shadow-xl">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-lg font-semibold text-gray-900">Add Staff Member</h2>
              <button
                onClick={() => setShowInvite(false)}
                className="rounded-md p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <form onSubmit={handleInvite} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700">
                  Email Address
                </label>
                <Input
                  type="email"
                  required
                  value={inviteEmail}
                  onChange={(e) => setInviteEmail(e.target.value)}
                  placeholder="staff@example.com"
                  className="mt-1"
                />
                <p className="mt-1 text-xs text-gray-500">
                  If this person doesn&apos;t have an account, one will be created automatically.
                </p>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700">
                  Role
                </label>
                <div className="mt-2 space-y-2">
                  {STAFF_ROLES.map((role) => (
                    <label
                      key={role.value}
                      className={`flex cursor-pointer items-start gap-3 rounded-lg border p-3 transition-colors ${
                        inviteRole === role.value
                          ? "border-indigo-500 bg-indigo-50"
                          : "border-gray-200 hover:bg-gray-50"
                      }`}
                    >
                      <input
                        type="radio"
                        name="role"
                        value={role.value}
                        checked={inviteRole === role.value}
                        onChange={(e) => setInviteRole(e.target.value)}
                        className="mt-0.5"
                      />
                      <div>
                        <div className="text-sm font-medium text-gray-900">{role.label}</div>
                        <div className="text-xs text-gray-500">{role.description}</div>
                      </div>
                    </label>
                  ))}
                </div>
              </div>

              <div className="flex gap-3 pt-2">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setShowInvite(false)}
                  className="flex-1"
                >
                  Cancel
                </Button>
                <Button
                  type="submit"
                  disabled={inviteMutation.isPending || !inviteEmail.trim()}
                  className="flex-1"
                >
                  {inviteMutation.isPending ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : (
                    <UserPlus className="mr-2 h-4 w-4" />
                  )}
                  Add Staff
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Search */}
      <div className="relative w-full sm:max-w-sm">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
        <Input
          placeholder="Search staff..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="pl-9"
        />
      </div>

      {/* Loading */}
      {isLoading && (
        <div className="flex items-center justify-center py-16">
          <Loader2 className="h-8 w-8 animate-spin text-indigo-600" />
        </div>
      )}

      {/* Empty State */}
      {!isLoading && filtered && filtered.length === 0 && (
        <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-gray-300 py-16">
          <Users2 className="mb-4 h-12 w-12 text-gray-300" />
          <p className="mb-4 text-sm text-gray-500">
            {search ? "No staff members match your search" : "No staff members yet"}
          </p>
          {!search && (
            <Button variant="outline" onClick={() => setShowInvite(true)}>
              <UserPlus className="mr-2 h-4 w-4" />
              Add your first staff member
            </Button>
          )}
        </div>
      )}

      {/* Staff Table */}
      {!isLoading && filtered && filtered.length > 0 && (
        <StaffTable staff={filtered} />
      )}
    </div>
  );
}
