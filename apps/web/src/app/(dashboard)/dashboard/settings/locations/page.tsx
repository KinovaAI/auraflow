"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Loader2,
  Plus,
  MapPin,
  Pencil,
  Trash2,
  Users,
  ChevronDown,
  ChevronUp,
  X,
  Building2,
} from "lucide-react";
import toast from "react-hot-toast";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  studiosApi,
  studioStaffApi,
  type Studio,
  type StudioStaffMember,
} from "@/lib/scheduling-api";
import { useAuthStore } from "@/stores/auth-store";

const TIMEZONE_OPTIONS = [
  "America/New_York",
  "America/Chicago",
  "America/Denver",
  "America/Los_Angeles",
  "America/Anchorage",
  "Pacific/Honolulu",
];

const ROLE_OPTIONS = [
  { value: "admin", label: "Admin" },
  { value: "instructor", label: "Instructor" },
  { value: "front_desk", label: "Front Desk" },
];

interface StudioFormData {
  name: string;
  slug: string;
  address_line1: string;
  city: string;
  state: string;
  postal_code: string;
  phone: string;
  email: string;
  timezone: string;
}

const emptyForm: StudioFormData = {
  name: "",
  slug: "",
  address_line1: "",
  city: "",
  state: "",
  postal_code: "",
  phone: "",
  email: "",
  timezone: "America/Los_Angeles",
};

export default function LocationsPage() {
  const queryClient = useQueryClient();
  const user = useAuthStore((s) => s.user);
  const isOwner =
    user?.active_org_role === "owner" || user?.is_platform_admin;

  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<StudioFormData>(emptyForm);
  const [expandedStudio, setExpandedStudio] = useState<string | null>(null);

  const { data: studios, isLoading } = useQuery({
    queryKey: ["studios"],
    queryFn: () => studiosApi.list().then((r) => r.data),
  });

  // ── Create / Update Studio ────────────────────────────────────────────────

  const createMutation = useMutation({
    mutationFn: () => studiosApi.create(form),
    onSuccess: () => {
      toast.success("Location created");
      queryClient.invalidateQueries({ queryKey: ["studios"] });
      resetForm();
      // Refresh user to pick up new studios list
      useAuthStore.getState().loadUser();
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      toast.error(detail || "Failed to create location");
    },
  });

  const updateMutation = useMutation({
    mutationFn: () =>
      studiosApi.update(editingId!, {
        name: form.name,
        address_line1: form.address_line1 || undefined,
        city: form.city || undefined,
        state: form.state || undefined,
        phone: form.phone || undefined,
        email: form.email || undefined,
        timezone: form.timezone || undefined,
      }),
    onSuccess: () => {
      toast.success("Location updated");
      queryClient.invalidateQueries({ queryKey: ["studios"] });
      resetForm();
    },
    onError: () => toast.error("Failed to update location"),
  });

  const deactivateMutation = useMutation({
    mutationFn: (id: string) => studiosApi.deactivate(id),
    onSuccess: () => {
      toast.success("Location deactivated");
      queryClient.invalidateQueries({ queryKey: ["studios"] });
      useAuthStore.getState().loadUser();
    },
    onError: () => toast.error("Failed to deactivate location"),
  });

  function resetForm() {
    setShowForm(false);
    setEditingId(null);
    setForm(emptyForm);
  }

  function startEdit(studio: Studio) {
    setEditingId(studio.id);
    setForm({
      name: studio.name,
      slug: studio.slug,
      address_line1: studio.address_line1 || "",
      city: studio.city || "",
      state: studio.state || "",
      postal_code: studio.postal_code || "",
      phone: studio.phone || "",
      email: studio.email || "",
      timezone: studio.timezone || "America/Los_Angeles",
    });
    setShowForm(true);
  }

  function autoSlug(name: string) {
    return name
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-|-$/g, "");
  }

  // ── Render ────────────────────────────────────────────────────────────────

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="h-8 w-8 animate-spin text-indigo-600" />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-gray-900">Locations</h2>
          <p className="text-sm text-gray-500">
            Manage your studio locations and staff assignments
          </p>
        </div>
        {isOwner && !showForm && (
          <Button onClick={() => { resetForm(); setShowForm(true); }}>
            <Plus className="mr-2 h-4 w-4" />
            Add Location
          </Button>
        )}
      </div>

      {/* Create / Edit Form */}
      {showForm && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="text-base">
                {editingId ? "Edit Location" : "New Location"}
              </CardTitle>
              <button
                onClick={resetForm}
                className="rounded-md p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label htmlFor="locName">Location Name</Label>
                <Input
                  id="locName"
                  value={form.name}
                  onChange={(e) => {
                    const name = e.target.value;
                    setForm((f) => ({
                      ...f,
                      name,
                      ...(!editingId ? { slug: autoSlug(name) } : {}),
                    }));
                  }}
                  placeholder="e.g. Downtown Studio"
                />
              </div>
              {!editingId && (
                <div>
                  <Label htmlFor="locSlug">URL Slug</Label>
                  <Input
                    id="locSlug"
                    value={form.slug}
                    onChange={(e) =>
                      setForm((f) => ({ ...f, slug: e.target.value }))
                    }
                    placeholder="e.g. downtown"
                  />
                </div>
              )}
              {editingId && (
                <div>
                  <Label htmlFor="locTimezone">Timezone</Label>
                  <select
                    id="locTimezone"
                    value={form.timezone}
                    onChange={(e) =>
                      setForm((f) => ({ ...f, timezone: e.target.value }))
                    }
                    className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                  >
                    {TIMEZONE_OPTIONS.map((tz) => (
                      <option key={tz} value={tz}>
                        {tz.replace("_", " ")}
                      </option>
                    ))}
                  </select>
                </div>
              )}
            </div>

            <div>
              <Label htmlFor="locAddr">Address</Label>
              <Input
                id="locAddr"
                value={form.address_line1}
                onChange={(e) =>
                  setForm((f) => ({ ...f, address_line1: e.target.value }))
                }
                placeholder="123 Main St"
              />
            </div>

            <div className="grid grid-cols-3 gap-4">
              <div>
                <Label htmlFor="locCity">City</Label>
                <Input
                  id="locCity"
                  value={form.city}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, city: e.target.value }))
                  }
                />
              </div>
              <div>
                <Label htmlFor="locState">State</Label>
                <Input
                  id="locState"
                  value={form.state}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, state: e.target.value }))
                  }
                />
              </div>
              <div>
                <Label htmlFor="locZip">Zip</Label>
                <Input
                  id="locZip"
                  value={form.postal_code}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, postal_code: e.target.value }))
                  }
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label htmlFor="locPhone">Phone</Label>
                <Input
                  id="locPhone"
                  value={form.phone}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, phone: e.target.value }))
                  }
                />
              </div>
              <div>
                <Label htmlFor="locEmail">Email</Label>
                <Input
                  id="locEmail"
                  type="email"
                  value={form.email}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, email: e.target.value }))
                  }
                />
              </div>
            </div>

            {!editingId && (
              <div className="w-1/2">
                <Label htmlFor="locTimezoneNew">Timezone</Label>
                <select
                  id="locTimezoneNew"
                  value={form.timezone}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, timezone: e.target.value }))
                  }
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                >
                  {TIMEZONE_OPTIONS.map((tz) => (
                    <option key={tz} value={tz}>
                      {tz.replace("_", " ")}
                    </option>
                  ))}
                </select>
              </div>
            )}

            <div className="flex gap-2 pt-2">
              <Button
                onClick={() =>
                  editingId
                    ? updateMutation.mutate()
                    : createMutation.mutate()
                }
                disabled={
                  !form.name.trim() ||
                  (!editingId && !form.slug.trim()) ||
                  createMutation.isPending ||
                  updateMutation.isPending
                }
              >
                {(createMutation.isPending || updateMutation.isPending) && (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                )}
                {editingId ? "Save Changes" : "Create Location"}
              </Button>
              <Button variant="outline" onClick={resetForm}>
                Cancel
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Studio List */}
      {!studios?.length ? (
        <Card>
          <CardContent className="flex flex-col items-center py-16">
            <Building2 className="h-10 w-10 text-gray-300" />
            <p className="mt-3 text-sm text-gray-500">No locations found</p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {studios.map((studio) => (
            <StudioCard
              key={studio.id}
              studio={studio}
              isOwner={!!isOwner}
              isExpanded={expandedStudio === studio.id}
              onToggle={() =>
                setExpandedStudio(
                  expandedStudio === studio.id ? null : studio.id
                )
              }
              onEdit={() => startEdit(studio)}
              onDeactivate={() => {
                if (
                  confirm(
                    `Deactivate "${studio.name}"? This will hide it from the system.`
                  )
                ) {
                  deactivateMutation.mutate(studio.id);
                }
              }}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// ── Studio Card with Staff Panel ──────────────────────────────────────────────

function StudioCard({
  studio,
  isOwner,
  isExpanded,
  onToggle,
  onEdit,
  onDeactivate,
}: {
  studio: Studio;
  isOwner: boolean;
  isExpanded: boolean;
  onToggle: () => void;
  onEdit: () => void;
  onDeactivate: () => void;
}) {
  return (
    <Card>
      <div className="flex items-center justify-between px-6 py-4">
        <div className="flex items-center gap-3">
          <div className="rounded-lg bg-indigo-50 p-2">
            <MapPin className="h-5 w-5 text-indigo-600" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-gray-900">
              {studio.name}
            </h3>
            <p className="text-xs text-gray-500">
              {[studio.city, studio.state].filter(Boolean).join(", ") ||
                studio.slug}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {isOwner && (
            <>
              <button
                onClick={onEdit}
                className="rounded-md p-1.5 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
                title="Edit"
              >
                <Pencil className="h-4 w-4" />
              </button>
              <button
                onClick={onDeactivate}
                className="rounded-md p-1.5 text-gray-400 hover:bg-red-50 hover:text-red-500"
                title="Deactivate"
              >
                <Trash2 className="h-4 w-4" />
              </button>
            </>
          )}
          <button
            onClick={onToggle}
            className="flex items-center gap-1 rounded-md px-2 py-1.5 text-xs font-medium text-gray-500 hover:bg-gray-100"
          >
            <Users className="h-3.5 w-3.5" />
            Staff
            {isExpanded ? (
              <ChevronUp className="h-3.5 w-3.5" />
            ) : (
              <ChevronDown className="h-3.5 w-3.5" />
            )}
          </button>
        </div>
      </div>

      {isExpanded && (
        <StudioStaffPanel studioId={studio.id} isOwner={isOwner} />
      )}
    </Card>
  );
}

// ── Staff Panel ───────────────────────────────────────────────────────────────

function StudioStaffPanel({
  studioId,
  isOwner,
}: {
  studioId: string;
  isOwner: boolean;
}) {
  const queryClient = useQueryClient();
  const [showAssignForm, setShowAssignForm] = useState(false);
  const [assignEmail, setAssignEmail] = useState("");
  const [assignRole, setAssignRole] = useState("instructor");

  const { data, isLoading } = useQuery({
    queryKey: ["studio-staff", studioId],
    queryFn: () => studioStaffApi.list(studioId).then((r) => r.data.data),
  });

  const removeMutation = useMutation({
    mutationFn: (userId: string) => studioStaffApi.remove(studioId, userId),
    onSuccess: () => {
      toast.success("Staff member removed from location");
      queryClient.invalidateQueries({
        queryKey: ["studio-staff", studioId],
      });
    },
    onError: () => toast.error("Failed to remove staff"),
  });

  const updateRoleMutation = useMutation({
    mutationFn: ({ userId, role }: { userId: string; role: string }) =>
      studioStaffApi.updateRole(studioId, userId, { role }),
    onSuccess: () => {
      toast.success("Role updated");
      queryClient.invalidateQueries({
        queryKey: ["studio-staff", studioId],
      });
    },
    onError: () => toast.error("Failed to update role"),
  });

  const assignMutation = useMutation({
    mutationFn: async () => {
      // Look up user by email first
      const { apiClient } = await import("@/lib/api-client");
      const res = await apiClient.get(
        `/staff?search=${encodeURIComponent(assignEmail)}&limit=1`
      );
      const staff = res.data?.data;
      if (!staff?.length) {
        throw new Error("No staff member found with that email");
      }
      const userId = staff[0].user_id || staff[0].id;
      return studioStaffApi.assign(studioId, {
        user_id: userId,
        role: assignRole,
      });
    },
    onSuccess: () => {
      toast.success("Staff assigned to location");
      setShowAssignForm(false);
      setAssignEmail("");
      setAssignRole("instructor");
      queryClient.invalidateQueries({
        queryKey: ["studio-staff", studioId],
      });
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      const message = err instanceof Error ? err.message : undefined;
      toast.error(detail || message || "Failed to assign staff");
    },
  });

  return (
    <div className="border-t border-gray-100 px-6 py-4">
      {isLoading ? (
        <div className="flex justify-center py-4">
          <Loader2 className="h-5 w-5 animate-spin text-gray-400" />
        </div>
      ) : (
        <>
          {data && data.length > 0 ? (
            <div className="space-y-2">
              {data.map((member: StudioStaffMember) => (
                <div
                  key={member.user_id}
                  className="flex items-center justify-between rounded-md border border-gray-100 px-3 py-2"
                >
                  <div className="flex items-center gap-3">
                    <div>
                      <span className="text-sm font-medium text-gray-900">
                        {member.first_name} {member.last_name}
                      </span>
                      <span className="ml-2 text-xs text-gray-400">
                        {member.email}
                      </span>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    {isOwner ? (
                      <select
                        value={member.role}
                        onChange={(e) =>
                          updateRoleMutation.mutate({
                            userId: member.user_id,
                            role: e.target.value,
                          })
                        }
                        className="rounded-md border border-gray-200 px-2 py-1 text-xs"
                      >
                        {ROLE_OPTIONS.map((opt) => (
                          <option key={opt.value} value={opt.value}>
                            {opt.label}
                          </option>
                        ))}
                      </select>
                    ) : (
                      <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium capitalize text-gray-600">
                        {member.role.replace("_", " ")}
                      </span>
                    )}
                    {isOwner && (
                      <button
                        onClick={() => {
                          if (
                            confirm(
                              `Remove ${member.first_name} from this location?`
                            )
                          ) {
                            removeMutation.mutate(member.user_id);
                          }
                        }}
                        className="rounded-md p-1 text-gray-400 hover:bg-red-50 hover:text-red-500"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="py-2 text-center text-xs text-gray-400">
              No staff assigned to this location yet
            </p>
          )}

          {/* Assign staff form */}
          {isOwner && (
            <div className="mt-3">
              {showAssignForm ? (
                <div className="flex items-end gap-2">
                  <div className="flex-1">
                    <Label className="text-xs">Staff Email</Label>
                    <Input
                      value={assignEmail}
                      onChange={(e) => setAssignEmail(e.target.value)}
                      placeholder="staff@example.com"
                      className="h-8 text-sm"
                    />
                  </div>
                  <div className="w-32">
                    <Label className="text-xs">Role</Label>
                    <select
                      value={assignRole}
                      onChange={(e) => setAssignRole(e.target.value)}
                      className="flex h-8 w-full rounded-md border border-input bg-background px-2 py-1 text-sm"
                    >
                      {ROLE_OPTIONS.map((opt) => (
                        <option key={opt.value} value={opt.value}>
                          {opt.label}
                        </option>
                      ))}
                    </select>
                  </div>
                  <Button
                    size="sm"
                    className="h-8"
                    onClick={() => assignMutation.mutate()}
                    disabled={
                      !assignEmail.trim() || assignMutation.isPending
                    }
                  >
                    {assignMutation.isPending ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      "Assign"
                    )}
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-8"
                    onClick={() => {
                      setShowAssignForm(false);
                      setAssignEmail("");
                    }}
                  >
                    <X className="h-3.5 w-3.5" />
                  </Button>
                </div>
              ) : (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setShowAssignForm(true)}
                >
                  <Plus className="mr-1 h-3.5 w-3.5" />
                  Assign Staff
                </Button>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
