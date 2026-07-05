"use client";

import { useState, useEffect, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  Loader2,
  Save,
  RotateCcw,
  Shield,
} from "lucide-react";
import toast from "react-hot-toast";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PermissionMatrix } from "@/components/staff/permission-matrix";
import { staffApi } from "@/lib/staff-api";
import { usePermission } from "@/hooks/use-permission";
import { useAuthStore } from "@/stores/auth-store";
import { cn } from "@/lib/utils";

const ROLE_OPTIONS = [
  { value: "admin", label: "Admin" },
  { value: "instructor", label: "Instructor" },
  { value: "front_desk", label: "Front Desk" },
];

export default function StaffDetailPage() {
  const params = useParams();
  const router = useRouter();
  const queryClient = useQueryClient();
  const userId = params.userId as string;
  const hasAccess = usePermission("staff.view");
  const user = useAuthStore((s) => s.user);
  const currentOrgRole = user?.active_org_role ?? user?.organizations?.[0]?.role;
  const isOwner = currentOrgRole === "owner" || user?.is_platform_admin;

  const [editedPermissions, setEditedPermissions] = useState<string[]>([]);
  const [hasPermChanges, setHasPermChanges] = useState(false);

  // Profile form state
  const [title, setTitle] = useState("");
  const [department, setDepartment] = useState("");
  const [hireDate, setHireDate] = useState("");
  const [notes, setNotes] = useState("");
  const [selectedRole, setSelectedRole] = useState("");

  const { data: member, isLoading } = useQuery({
    queryKey: ["staff", userId],
    queryFn: () => staffApi.get(userId).then((r) => r.data),
    enabled: hasAccess,
  });

  const { data: defaults } = useQuery({
    queryKey: ["staff-permission-defaults"],
    queryFn: () => staffApi.getDefaults().then((r) => r.data),
    enabled: hasAccess && isOwner,
  });

  // Sync form state when data loads
  useEffect(() => {
    if (member) {
      setEditedPermissions(member.permissions);
      setTitle(member.title || "");
      setDepartment(member.department || "");
      setHireDate(member.hire_date || "");
      setSelectedRole(member.role);
    }
  }, [member]);

  const profileMutation = useMutation({
    mutationFn: (data: { title?: string; department?: string; hire_date?: string; notes?: string }) =>
      staffApi.updateProfile(userId, data).then((r) => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["staff", userId] });
      queryClient.invalidateQueries({ queryKey: ["staff"] });
      toast.success("Profile updated");
    },
    onError: () => toast.error("Failed to update profile"),
  });

  const roleMutation = useMutation({
    mutationFn: (role: string) =>
      staffApi.updateRole(userId, role).then((r) => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["staff", userId] });
      queryClient.invalidateQueries({ queryKey: ["staff"] });
      toast.success("Role updated");
    },
    onError: () => toast.error("Failed to update role"),
  });

  const permissionMutation = useMutation({
    mutationFn: (permissions: Record<string, boolean>) =>
      staffApi.updatePermissions(userId, { permissions }).then((r) => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["staff", userId] });
      queryClient.invalidateQueries({ queryKey: ["staff"] });
      setHasPermChanges(false);
      toast.success("Permissions updated");
    },
    onError: () => toast.error("Failed to update permissions"),
  });

  const authLoading = useAuthStore((s) => s.isLoading);

  useEffect(() => {
    if (!authLoading && !hasAccess) {
      router.push("/dashboard");
    }
  }, [authLoading, hasAccess, router]);

  if (!hasAccess) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 className="h-8 w-8 animate-spin text-indigo-600" />
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 className="h-8 w-8 animate-spin text-indigo-600" />
      </div>
    );
  }

  if (!member) {
    return (
      <div className="py-16 text-center text-gray-500">
        Staff member not found
      </div>
    );
  }

  const fullName =
    [member.first_name, member.last_name].filter(Boolean).join(" ") ||
    member.email;

  const handlePermissionChange = (key: string, granted: boolean) => {
    setEditedPermissions((prev) =>
      granted ? [...prev, key] : prev.filter((p) => p !== key)
    );
    setHasPermChanges(true);
  };

  const handleSavePermissions = () => {
    if (!defaults) return;
    // Build a full permission map: granted vs revoked
    const permMap: Record<string, boolean> = {};
    for (const key of defaults.all_permissions) {
      permMap[key] = editedPermissions.includes(key);
    }
    permissionMutation.mutate(permMap);
  };

  const handleResetToDefaults = () => {
    if (!defaults) return;
    const roleDefaults = defaults.defaults[selectedRole] || [];
    setEditedPermissions(roleDefaults);
    setHasPermChanges(true);
  };

  const handleSaveProfile = () => {
    const data: Record<string, string> = {};
    if (title !== (member.title || "")) data.title = title;
    if (department !== (member.department || "")) data.department = department;
    if (hireDate !== (member.hire_date || "")) data.hire_date = hireDate;
    if (notes) data.notes = notes;
    if (Object.keys(data).length > 0) {
      profileMutation.mutate(data);
    }
  };

  const handleRoleChange = (newRole: string) => {
    setSelectedRole(newRole);
    if (newRole !== member.role) {
      roleMutation.mutate(newRole);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <Link
          href="/dashboard/staff"
          className="rounded-md p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
        >
          <ArrowLeft className="h-5 w-5" />
        </Link>
        <div>
          <h1 className="text-2xl font-bold text-gray-900">{fullName}</h1>
          <p className="text-sm text-gray-500">{member.email}</p>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Left Column: Profile & Role */}
        <div className="space-y-6 lg:col-span-1">
          {/* Profile Card */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Profile</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700">
                  Title
                </label>
                <Input
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="e.g. Lead Instructor"
                  className="mt-1"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700">
                  Department
                </label>
                <Input
                  value={department}
                  onChange={(e) => setDepartment(e.target.value)}
                  placeholder="e.g. Teaching"
                  className="mt-1"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700">
                  Hire Date
                </label>
                <Input
                  type="date"
                  value={hireDate}
                  onChange={(e) => setHireDate(e.target.value)}
                  className="mt-1"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700">
                  Notes
                </label>
                <textarea
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  rows={3}
                  placeholder="Internal notes..."
                  className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                />
              </div>
              <Button
                onClick={handleSaveProfile}
                disabled={profileMutation.isPending}
                className="w-full"
              >
                {profileMutation.isPending ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <Save className="mr-2 h-4 w-4" />
                )}
                Save Profile
              </Button>
            </CardContent>
          </Card>

          {/* Role Card */}
          {isOwner && member.role !== "owner" && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Role</CardTitle>
              </CardHeader>
              <CardContent>
                <select
                  value={selectedRole}
                  onChange={(e) => handleRoleChange(e.target.value)}
                  disabled={roleMutation.isPending}
                  className="block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                >
                  {ROLE_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
                <p className="mt-2 text-xs text-gray-500">
                  Changing the role does not automatically reset permissions.
                  Use &ldquo;Reset to Defaults&rdquo; to apply the new
                  role&apos;s default permissions.
                </p>
              </CardContent>
            </Card>
          )}
        </div>

        {/* Right Column: Permissions */}
        <div className="lg:col-span-2">
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Shield className="h-5 w-5 text-indigo-600" />
                  <CardTitle className="text-base">Module Permissions</CardTitle>
                </div>
                <div className="flex gap-2">
                  {isOwner && member.role !== "owner" && (
                    <>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={handleResetToDefaults}
                        disabled={!defaults}
                      >
                        <RotateCcw className="mr-1 h-3 w-3" />
                        Reset to Defaults
                      </Button>
                      <Button
                        size="sm"
                        onClick={handleSavePermissions}
                        disabled={
                          !hasPermChanges || permissionMutation.isPending
                        }
                      >
                        {permissionMutation.isPending ? (
                          <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                        ) : (
                          <Save className="mr-1 h-3 w-3" />
                        )}
                        Save Permissions
                      </Button>
                    </>
                  )}
                </div>
              </div>
            </CardHeader>
            <CardContent>
              {member.role === "owner" ? (
                <div className="rounded-md bg-purple-50 p-4 text-center">
                  <p className="text-sm text-purple-800">
                    Owners always have access to all modules. Permissions
                    cannot be restricted for the owner role.
                  </p>
                </div>
              ) : (
                <>
                  <p className="mb-4 text-sm text-gray-500">
                    Toggle each individual action this staff member is
                    allowed to perform. Roles are starter templates only —
                    every box can be ticked or unticked here regardless of
                    the user's role.
                  </p>
                  <PermissionMatrix
                    allPermissions={defaults?.all_permissions || []}
                    permissions={editedPermissions}
                    onChange={handlePermissionChange}
                    disabled={!isOwner}
                  />
                </>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
