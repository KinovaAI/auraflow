"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  DoorOpen,
  Wrench,
  AlertTriangle,
  CalendarCheck,
  Plus,
  Loader2,
  Pencil,
  Trash2,
  CheckCircle,
  Clock,
  ChevronDown,
  ChevronRight,
} from "lucide-react";
import {
  facilitiesApi,
  type RoomDetail,
  type Equipment,
  type MaintenanceRequest,
  type MaintenanceStats,
  type FacilitySchedule,
  type ScheduleCompletion,
  type RoomAvailabilitySlot,
} from "@/lib/facilities-api";
import toast from "react-hot-toast";

// ── Helpers ──────────────────────────────────────────────────────────────────

function fmtDate(iso: string | null) {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString([], {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function fmtTime(iso: string | null) {
  if (!iso) return "—";
  return new Date(iso).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });
}

function fmtDateTime(iso: string | null) {
  if (!iso) return "—";
  return `${fmtDate(iso)} ${fmtTime(iso)}`;
}

function fmtCents(cents: number | null) {
  if (cents == null) return "—";
  return `$${(cents / 100).toFixed(2)}`;
}

function todayISO() {
  return new Date().toISOString().slice(0, 10);
}

// ── Status Badges ────────────────────────────────────────────────────────────

const priorityColors: Record<string, string> = {
  urgent: "bg-red-100 text-red-800",
  high: "bg-orange-100 text-orange-800",
  medium: "bg-yellow-100 text-yellow-800",
  low: "bg-blue-100 text-blue-800",
};

const statusColors: Record<string, string> = {
  open: "bg-blue-100 text-blue-800",
  in_progress: "bg-yellow-100 text-yellow-800",
  completed: "bg-green-100 text-green-800",
  cancelled: "bg-gray-100 text-gray-500",
};

const conditionColors: Record<string, string> = {
  new: "bg-green-100 text-green-800",
  good: "bg-blue-100 text-blue-800",
  fair: "bg-yellow-100 text-yellow-800",
  poor: "bg-orange-100 text-orange-800",
  retired: "bg-gray-100 text-gray-500",
};

const typeColors: Record<string, string> = {
  cleaning: "bg-cyan-100 text-cyan-800",
  inspection: "bg-purple-100 text-purple-800",
  maintenance: "bg-amber-100 text-amber-800",
};

const roomTypeColors: Record<string, string> = {
  studio: "bg-indigo-100 text-indigo-800",
  meeting: "bg-teal-100 text-teal-800",
  outdoor: "bg-green-100 text-green-800",
  virtual: "bg-violet-100 text-violet-800",
  therapy: "bg-pink-100 text-pink-800",
  storage: "bg-gray-100 text-gray-600",
};

function Badge({
  label,
  colorMap,
}: {
  label: string;
  colorMap: Record<string, string>;
}) {
  const cls = colorMap[label] || "bg-gray-100 text-gray-600";
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${cls}`}
    >
      {label.replace(/_/g, " ")}
    </span>
  );
}

// ── Temporary studio ID (first studio) ──────────────────────────────────────
// In production, this comes from studio context. Here we fetch the first studio.

function useStudioId() {
  const { data } = useQuery({
    queryKey: ["studios-for-facilities"],
    queryFn: async () => {
      const { default: axios } = await import("axios");
      const token =
        typeof window !== "undefined"
          ? localStorage.getItem("access_token")
          : null;
      const base =
        process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
      const res = await axios.get(`${base}/api/v1/studios`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      return res.data as Array<{ id: string; name: string }>;
    },
  });
  return data?.[0]?.id || "";
}

// ── Tab Definitions ──────────────────────────────────────────────────────────

const tabs = [
  { key: "rooms", label: "Rooms", icon: DoorOpen },
  { key: "equipment", label: "Equipment", icon: Wrench },
  { key: "maintenance", label: "Maintenance", icon: AlertTriangle },
  { key: "schedules", label: "Schedules", icon: CalendarCheck },
] as const;

type TabKey = (typeof tabs)[number]["key"];

// ═════════════════════════════════════════════════════════════════════════════
// Main Page
// ═════════════════════════════════════════════════════════════════════════════

export default function FacilitiesPage() {
  const [tab, setTab] = useState<TabKey>("rooms");
  const studioId = useStudioId();

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">
          Facility Management
        </h1>
        <p className="text-sm text-gray-500">
          Rooms, equipment, maintenance, and cleaning schedules
        </p>
      </div>

      {/* Tab Bar */}
      <div className="flex gap-1 rounded-lg bg-gray-100 p-1">
        {tabs.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`flex items-center gap-2 rounded-md px-4 py-2 text-sm font-medium transition-colors ${
              tab === t.key
                ? "bg-white text-gray-900 shadow-sm"
                : "text-gray-500 hover:text-gray-700"
            }`}
          >
            <t.icon className="h-4 w-4" />
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      {!studioId ? (
        <div className="flex justify-center py-12">
          <Loader2 className="h-6 w-6 animate-spin text-gray-300" />
        </div>
      ) : (
        <>
          {tab === "rooms" && <RoomsTab studioId={studioId} />}
          {tab === "equipment" && <EquipmentTab studioId={studioId} />}
          {tab === "maintenance" && <MaintenanceTab studioId={studioId} />}
          {tab === "schedules" && <SchedulesTab studioId={studioId} />}
        </>
      )}
    </div>
  );
}

// ═════════════════════════════════════════════════════════════════════════════
// Rooms Tab
// ═════════════════════════════════════════════════════════════════════════════

function RoomsTab({ studioId }: { studioId: string }) {
  const queryClient = useQueryClient();
  const [expandedRoom, setExpandedRoom] = useState<string | null>(null);
  const [editingRoom, setEditingRoom] = useState<string | null>(null);
  const [availDate, setAvailDate] = useState(todayISO());

  const { data: rooms, isLoading } = useQuery({
    queryKey: ["facility-rooms", studioId],
    queryFn: () =>
      facilitiesApi.listRooms(studioId).then((r) => r.data.data),
    enabled: !!studioId,
  });

  const { data: availability } = useQuery({
    queryKey: ["room-availability", expandedRoom, availDate],
    queryFn: () =>
      facilitiesApi
        .getRoomAvailability(expandedRoom!, availDate)
        .then((r) => r.data.data),
    enabled: !!expandedRoom,
  });

  const [editForm, setEditForm] = useState<Record<string, string>>({});

  const updateMut = useMutation({
    mutationFn: (roomId: string) =>
      facilitiesApi.updateRoomExtended(roomId, {
        description: editForm.description || undefined,
        room_type: editForm.room_type || undefined,
        amenities: editForm.amenities
          ? editForm.amenities.split(",").map((s) => s.trim())
          : undefined,
        hourly_rate_cents: editForm.hourly_rate_cents
          ? parseInt(editForm.hourly_rate_cents)
          : undefined,
        setup_instructions: editForm.setup_instructions || undefined,
      } as Partial<import("@/lib/facilities-api").RoomDetail>),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["facility-rooms"] });
      setEditingRoom(null);
      toast.success("Room updated");
    },
    onError: () => toast.error("Failed to update room"),
  });

  if (isLoading)
    return (
      <div className="flex justify-center py-12">
        <Loader2 className="h-6 w-6 animate-spin text-gray-300" />
      </div>
    );

  if (!rooms?.length)
    return (
      <p className="py-8 text-center text-sm text-gray-400">
        No rooms configured. Add rooms in Settings → Studio.
      </p>
    );

  return (
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
      {rooms.map((room: RoomDetail) => (
        <Card key={room.id} className="overflow-hidden">
          <CardHeader className="pb-2">
            <div className="flex items-start justify-between">
              <div>
                <CardTitle className="text-base">{room.name}</CardTitle>
                <div className="mt-1 flex flex-wrap gap-1">
                  <Badge
                    label={room.room_type || "studio"}
                    colorMap={roomTypeColors}
                  />
                  {room.capacity && (
                    <span className="text-xs text-gray-500">
                      {room.capacity} cap
                    </span>
                  )}
                </div>
              </div>
              <button
                onClick={() => setEditingRoom(editingRoom === room.id ? null : room.id)}
                className="rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
              >
                <Pencil className="h-4 w-4" />
              </button>
            </div>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            {room.description && (
              <p className="text-gray-600">{room.description}</p>
            )}

            {/* Amenities */}
            {room.amenities && room.amenities.length > 0 && (
              <div className="flex flex-wrap gap-1">
                {room.amenities.map((a: string) => (
                  <span
                    key={a}
                    className="rounded bg-gray-100 px-2 py-0.5 text-xs text-gray-600"
                  >
                    {a}
                  </span>
                ))}
              </div>
            )}

            {/* Stats */}
            <div className="flex gap-4 text-xs text-gray-500">
              <span>{room.sessions_today} classes today</span>
              <span>{room.equipment_count} equipment</span>
              {room.floor_area_sqft && <span>{room.floor_area_sqft} sqft</span>}
            </div>

            {/* Expand for availability */}
            <button
              onClick={() =>
                setExpandedRoom(expandedRoom === room.id ? null : room.id)
              }
              className="flex items-center gap-1 text-xs font-medium text-indigo-600 hover:text-indigo-700"
            >
              {expandedRoom === room.id ? (
                <ChevronDown className="h-3 w-3" />
              ) : (
                <ChevronRight className="h-3 w-3" />
              )}
              View Schedule
            </button>

            {expandedRoom === room.id && (
              <div className="rounded-md border border-gray-200 p-3">
                <div className="mb-2 flex items-center gap-2">
                  <input
                    type="date"
                    value={availDate}
                    onChange={(e) => setAvailDate(e.target.value)}
                    className="rounded border border-gray-300 px-2 py-1 text-xs"
                  />
                </div>
                {availability && availability.length > 0 ? (
                  <div className="space-y-1">
                    {availability.map((slot: RoomAvailabilitySlot) => (
                      <div
                        key={slot.session_id}
                        className="flex justify-between text-xs"
                      >
                        <span className="font-medium">{slot.title}</span>
                        <span className="text-gray-500">
                          {fmtTime(slot.starts_at)}–{fmtTime(slot.ends_at)}
                          {slot.instructor_name && ` · ${slot.instructor_name}`}
                        </span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-xs text-gray-400">No classes scheduled</p>
                )}
              </div>
            )}

            {/* Edit form */}
            {editingRoom === room.id && (
              <div className="space-y-2 rounded-md border border-gray-200 p-3">
                <input
                  placeholder="Description"
                  defaultValue={room.description || ""}
                  onChange={(e) =>
                    setEditForm({ ...editForm, description: e.target.value })
                  }
                  className="w-full rounded border border-gray-300 px-2 py-1 text-xs"
                />
                <select
                  defaultValue={room.room_type || "studio"}
                  onChange={(e) =>
                    setEditForm({ ...editForm, room_type: e.target.value })
                  }
                  className="w-full rounded border border-gray-300 px-2 py-1 text-xs"
                >
                  {["studio", "meeting", "outdoor", "virtual", "therapy", "storage"].map(
                    (t) => (
                      <option key={t} value={t}>
                        {t}
                      </option>
                    )
                  )}
                </select>
                <input
                  placeholder="Amenities (comma-separated)"
                  defaultValue={(room.amenities || []).join(", ")}
                  onChange={(e) =>
                    setEditForm({ ...editForm, amenities: e.target.value })
                  }
                  className="w-full rounded border border-gray-300 px-2 py-1 text-xs"
                />
                <input
                  placeholder="Setup instructions"
                  defaultValue={room.setup_instructions || ""}
                  onChange={(e) =>
                    setEditForm({
                      ...editForm,
                      setup_instructions: e.target.value,
                    })
                  }
                  className="w-full rounded border border-gray-300 px-2 py-1 text-xs"
                />
                <div className="flex justify-end gap-2">
                  <button
                    onClick={() => setEditingRoom(null)}
                    className="rounded px-3 py-1 text-xs text-gray-500 hover:bg-gray-100"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={() => updateMut.mutate(room.id)}
                    disabled={updateMut.isPending}
                    className="rounded bg-indigo-600 px-3 py-1 text-xs text-white hover:bg-indigo-700 disabled:opacity-50"
                  >
                    {updateMut.isPending ? "Saving..." : "Save"}
                  </button>
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

// ═════════════════════════════════════════════════════════════════════════════
// Equipment Tab
// ═════════════════════════════════════════════════════════════════════════════

function EquipmentTab({ studioId }: { studioId: string }) {
  const queryClient = useQueryClient();
  const [categoryFilter, setCategoryFilter] = useState("");
  const [conditionFilter, setConditionFilter] = useState("");
  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState<Record<string, string>>({});

  const { data: equipment, isLoading } = useQuery({
    queryKey: ["facility-equipment", studioId, categoryFilter, conditionFilter],
    queryFn: () =>
      facilitiesApi
        .listEquipment({
          studio_id: studioId,
          category: categoryFilter || undefined,
          condition: conditionFilter || undefined,
        })
        .then((r) => r.data.data),
    enabled: !!studioId,
  });

  const createMut = useMutation({
    mutationFn: () =>
      facilitiesApi.createEquipment({
        studio_id: studioId,
        name: form.name,
        category: form.category || "props",
        description: form.description || undefined,
        quantity: form.quantity ? parseInt(form.quantity) : 1,
        condition: form.condition || "good",
        serial_number: form.serial_number || undefined,
        notes: form.notes || undefined,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["facility-equipment"] });
      setShowAdd(false);
      setForm({});
      toast.success("Equipment added");
    },
    onError: () => toast.error("Failed to add equipment"),
  });

  const deleteMut = useMutation({
    mutationFn: (id: string) => facilitiesApi.deleteEquipment(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["facility-equipment"] });
      toast.success("Equipment removed");
    },
  });

  const categories = [
    "props",
    "mats",
    "weights",
    "machines",
    "audio_visual",
    "furniture",
    "cleaning",
    "other",
  ];
  const conditions = ["new", "good", "fair", "poor", "retired"];

  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-3">
        <select
          value={categoryFilter}
          onChange={(e) => setCategoryFilter(e.target.value)}
          className="rounded-md border border-gray-300 px-3 py-2 text-sm"
        >
          <option value="">All Categories</option>
          {categories.map((c) => (
            <option key={c} value={c}>
              {c.replace(/_/g, " ")}
            </option>
          ))}
        </select>
        <select
          value={conditionFilter}
          onChange={(e) => setConditionFilter(e.target.value)}
          className="rounded-md border border-gray-300 px-3 py-2 text-sm"
        >
          <option value="">All Conditions</option>
          {conditions.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
        <div className="flex-1" />
        <button
          onClick={() => setShowAdd(!showAdd)}
          className="flex items-center gap-2 rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700"
        >
          <Plus className="h-4 w-4" /> Add Equipment
        </button>
      </div>

      {/* Add form */}
      {showAdd && (
        <Card>
          <CardContent className="grid gap-3 p-4 sm:grid-cols-3">
            <input
              placeholder="Name *"
              value={form.name || ""}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              className="rounded-md border border-gray-300 px-3 py-2 text-sm"
            />
            <select
              value={form.category || "props"}
              onChange={(e) => setForm({ ...form, category: e.target.value })}
              className="rounded-md border border-gray-300 px-3 py-2 text-sm"
            >
              {categories.map((c) => (
                <option key={c} value={c}>
                  {c.replace(/_/g, " ")}
                </option>
              ))}
            </select>
            <input
              placeholder="Quantity"
              type="number"
              value={form.quantity || ""}
              onChange={(e) => setForm({ ...form, quantity: e.target.value })}
              className="rounded-md border border-gray-300 px-3 py-2 text-sm"
            />
            <select
              value={form.condition || "good"}
              onChange={(e) => setForm({ ...form, condition: e.target.value })}
              className="rounded-md border border-gray-300 px-3 py-2 text-sm"
            >
              {conditions.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
            <input
              placeholder="Serial number"
              value={form.serial_number || ""}
              onChange={(e) =>
                setForm({ ...form, serial_number: e.target.value })
              }
              className="rounded-md border border-gray-300 px-3 py-2 text-sm"
            />
            <input
              placeholder="Notes"
              value={form.notes || ""}
              onChange={(e) => setForm({ ...form, notes: e.target.value })}
              className="rounded-md border border-gray-300 px-3 py-2 text-sm"
            />
            <div className="flex gap-2 sm:col-span-3">
              <button
                onClick={() => {
                  setShowAdd(false);
                  setForm({});
                }}
                className="rounded-md border border-gray-300 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                onClick={() => createMut.mutate()}
                disabled={!form.name || createMut.isPending}
                className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
              >
                {createMut.isPending ? "Adding..." : "Add"}
              </button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Table */}
      {isLoading ? (
        <div className="flex justify-center py-12">
          <Loader2 className="h-6 w-6 animate-spin text-gray-300" />
        </div>
      ) : !equipment?.length ? (
        <p className="py-8 text-center text-sm text-gray-400">
          No equipment tracked yet
        </p>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-left text-xs font-medium uppercase text-gray-500">
              <tr>
                <th className="px-4 py-3">Name</th>
                <th className="px-4 py-3">Category</th>
                <th className="px-4 py-3">Room</th>
                <th className="px-4 py-3 text-center">Qty</th>
                <th className="px-4 py-3">Condition</th>
                <th className="px-4 py-3">Purchase Date</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {equipment.map((e: Equipment) => (
                <tr key={e.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 font-medium text-gray-900">
                    {e.name}
                    {e.serial_number && (
                      <span className="ml-2 text-xs text-gray-400">
                        SN: {e.serial_number}
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <span className="text-gray-600">
                      {e.category.replace(/_/g, " ")}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-gray-600">
                    {e.room_name || "Unassigned"}
                  </td>
                  <td className="px-4 py-3 text-center">{e.quantity}</td>
                  <td className="px-4 py-3">
                    <Badge label={e.condition} colorMap={conditionColors} />
                  </td>
                  <td className="px-4 py-3 text-gray-500">
                    {fmtDate(e.purchase_date)}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button
                      onClick={() => {
                        if (confirm("Remove this equipment?"))
                          deleteMut.mutate(e.id);
                      }}
                      className="rounded p-1 text-gray-400 hover:bg-red-50 hover:text-red-600"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
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

// ═════════════════════════════════════════════════════════════════════════════
// Maintenance Tab
// ═════════════════════════════════════════════════════════════════════════════

function MaintenanceTab({ studioId }: { studioId: string }) {
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState("");
  const [priorityFilter, setPriorityFilter] = useState("");
  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState<Record<string, string>>({});

  const { data: stats } = useQuery({
    queryKey: ["facility-maintenance-stats", studioId],
    queryFn: () =>
      facilitiesApi.getMaintenanceStats(studioId).then((r) => r.data.data),
    enabled: !!studioId,
  });

  const { data: requests, isLoading } = useQuery({
    queryKey: [
      "facility-maintenance",
      studioId,
      statusFilter,
      priorityFilter,
    ],
    queryFn: () =>
      facilitiesApi
        .listMaintenance({
          studio_id: studioId,
          status: statusFilter || undefined,
          priority: priorityFilter || undefined,
        })
        .then((r) => r.data.data),
    enabled: !!studioId,
  });

  const createMut = useMutation({
    mutationFn: () =>
      facilitiesApi.createMaintenance({
        studio_id: studioId,
        title: form.title,
        description: form.description || undefined,
        priority: form.priority || "medium",
        category: form.category || "repair",
        assigned_to: form.assigned_to || undefined,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["facility-maintenance"] });
      queryClient.invalidateQueries({
        queryKey: ["facility-maintenance-stats"],
      });
      setShowAdd(false);
      setForm({});
      toast.success("Request created");
    },
    onError: () => toast.error("Failed to create request"),
  });

  const updateMut = useMutation({
    mutationFn: ({
      id,
      status,
    }: {
      id: string;
      status: string;
    }) => facilitiesApi.updateMaintenance(id, { status }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["facility-maintenance"] });
      queryClient.invalidateQueries({
        queryKey: ["facility-maintenance-stats"],
      });
      toast.success("Status updated");
    },
  });

  return (
    <div className="space-y-4">
      {/* Stats Cards */}
      {stats && (
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          {[
            { label: "Open", value: stats.open, color: "text-blue-600" },
            {
              label: "In Progress",
              value: stats.in_progress,
              color: "text-yellow-600",
            },
            {
              label: "Completed (Month)",
              value: stats.completed_this_month,
              color: "text-green-600",
            },
            {
              label: "Overdue Schedules",
              value: stats.overdue_schedules,
              color: "text-red-600",
            },
          ].map((s) => (
            <Card key={s.label}>
              <CardContent className="p-4">
                <p className="text-xs font-medium text-gray-500">{s.label}</p>
                <p className={`text-2xl font-bold ${s.color}`}>{s.value}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-3">
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="rounded-md border border-gray-300 px-3 py-2 text-sm"
        >
          <option value="">All Statuses</option>
          {["open", "in_progress", "completed", "cancelled"].map((s) => (
            <option key={s} value={s}>
              {s.replace(/_/g, " ")}
            </option>
          ))}
        </select>
        <select
          value={priorityFilter}
          onChange={(e) => setPriorityFilter(e.target.value)}
          className="rounded-md border border-gray-300 px-3 py-2 text-sm"
        >
          <option value="">All Priorities</option>
          {["urgent", "high", "medium", "low"].map((p) => (
            <option key={p} value={p}>
              {p}
            </option>
          ))}
        </select>
        <div className="flex-1" />
        <button
          onClick={() => setShowAdd(!showAdd)}
          className="flex items-center gap-2 rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700"
        >
          <Plus className="h-4 w-4" /> New Request
        </button>
      </div>

      {/* Add form */}
      {showAdd && (
        <Card>
          <CardContent className="grid gap-3 p-4 sm:grid-cols-2">
            <input
              placeholder="Title *"
              value={form.title || ""}
              onChange={(e) => setForm({ ...form, title: e.target.value })}
              className="rounded-md border border-gray-300 px-3 py-2 text-sm sm:col-span-2"
            />
            <textarea
              placeholder="Description"
              value={form.description || ""}
              onChange={(e) =>
                setForm({ ...form, description: e.target.value })
              }
              className="rounded-md border border-gray-300 px-3 py-2 text-sm sm:col-span-2"
              rows={2}
            />
            <select
              value={form.priority || "medium"}
              onChange={(e) => setForm({ ...form, priority: e.target.value })}
              className="rounded-md border border-gray-300 px-3 py-2 text-sm"
            >
              {["low", "medium", "high", "urgent"].map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
            <select
              value={form.category || "repair"}
              onChange={(e) => setForm({ ...form, category: e.target.value })}
              className="rounded-md border border-gray-300 px-3 py-2 text-sm"
            >
              {["repair", "cleaning", "replacement", "inspection", "safety"].map(
                (c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                )
              )}
            </select>
            <input
              placeholder="Assigned to"
              value={form.assigned_to || ""}
              onChange={(e) =>
                setForm({ ...form, assigned_to: e.target.value })
              }
              className="rounded-md border border-gray-300 px-3 py-2 text-sm sm:col-span-2"
            />
            <div className="flex gap-2 sm:col-span-2">
              <button
                onClick={() => {
                  setShowAdd(false);
                  setForm({});
                }}
                className="rounded-md border border-gray-300 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                onClick={() => createMut.mutate()}
                disabled={!form.title || createMut.isPending}
                className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
              >
                {createMut.isPending ? "Creating..." : "Create Request"}
              </button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* List */}
      {isLoading ? (
        <div className="flex justify-center py-12">
          <Loader2 className="h-6 w-6 animate-spin text-gray-300" />
        </div>
      ) : !requests?.length ? (
        <p className="py-8 text-center text-sm text-gray-400">
          No maintenance requests
        </p>
      ) : (
        <div className="space-y-2">
          {requests.map((req: MaintenanceRequest) => (
            <Card key={req.id}>
              <CardContent className="flex items-start gap-4 p-4">
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <h3 className="font-medium text-gray-900">{req.title}</h3>
                    <Badge label={req.priority} colorMap={priorityColors} />
                    <Badge label={req.status} colorMap={statusColors} />
                    <Badge
                      label={req.category}
                      colorMap={{
                        repair: "bg-orange-100 text-orange-800",
                        cleaning: "bg-cyan-100 text-cyan-800",
                        replacement: "bg-red-100 text-red-800",
                        inspection: "bg-purple-100 text-purple-800",
                        safety: "bg-red-100 text-red-800",
                      }}
                    />
                  </div>
                  {req.description && (
                    <p className="mt-1 text-sm text-gray-600">
                      {req.description}
                    </p>
                  )}
                  <div className="mt-1 flex gap-4 text-xs text-gray-500">
                    {req.room_name && <span>Room: {req.room_name}</span>}
                    {req.equipment_name && (
                      <span>Equipment: {req.equipment_name}</span>
                    )}
                    {req.assigned_to && (
                      <span>Assigned: {req.assigned_to}</span>
                    )}
                    <span>Created: {fmtDate(req.created_at)}</span>
                    {req.estimated_cost_cents != null && (
                      <span>
                        Est: {fmtCents(req.estimated_cost_cents)}
                      </span>
                    )}
                  </div>
                </div>
                {/* Status actions */}
                <div className="flex gap-1">
                  {req.status === "open" && (
                    <button
                      onClick={() =>
                        updateMut.mutate({
                          id: req.id,
                          status: "in_progress",
                        })
                      }
                      className="rounded bg-yellow-100 px-2 py-1 text-xs font-medium text-yellow-800 hover:bg-yellow-200"
                    >
                      Start
                    </button>
                  )}
                  {req.status === "in_progress" && (
                    <button
                      onClick={() =>
                        updateMut.mutate({
                          id: req.id,
                          status: "completed",
                        })
                      }
                      className="rounded bg-green-100 px-2 py-1 text-xs font-medium text-green-800 hover:bg-green-200"
                    >
                      Complete
                    </button>
                  )}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

// ═════════════════════════════════════════════════════════════════════════════
// Schedules Tab
// ═════════════════════════════════════════════════════════════════════════════

function SchedulesTab({ studioId }: { studioId: string }) {
  const queryClient = useQueryClient();
  const [typeFilter, setTypeFilter] = useState("");
  const [overdueOnly, setOverdueOnly] = useState(false);
  const [showAdd, setShowAdd] = useState(false);
  const [expandedHistory, setExpandedHistory] = useState<string | null>(null);
  const [form, setForm] = useState<Record<string, string>>({});

  const { data: schedules, isLoading } = useQuery({
    queryKey: ["facility-schedules", studioId, typeFilter, overdueOnly],
    queryFn: () =>
      facilitiesApi
        .listSchedules({
          studio_id: studioId,
          type: typeFilter || undefined,
          overdue_only: overdueOnly || undefined,
        })
        .then((r) => r.data.data),
    enabled: !!studioId,
  });

  const { data: history } = useQuery({
    queryKey: ["schedule-history", expandedHistory],
    queryFn: () =>
      facilitiesApi
        .getScheduleHistory(expandedHistory!)
        .then((r) => r.data.data),
    enabled: !!expandedHistory,
  });

  const createMut = useMutation({
    mutationFn: () =>
      facilitiesApi.createSchedule({
        studio_id: studioId,
        title: form.title,
        schedule_type: form.schedule_type || "cleaning",
        description: form.description || undefined,
        rrule: form.rrule || undefined,
        assigned_to: form.assigned_to || undefined,
        next_due_at: form.next_due_at || undefined,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["facility-schedules"] });
      setShowAdd(false);
      setForm({});
      toast.success("Schedule created");
    },
    onError: () => toast.error("Failed to create schedule"),
  });

  const completeMut = useMutation({
    mutationFn: (id: string) => facilitiesApi.completeSchedule(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["facility-schedules"] });
      queryClient.invalidateQueries({
        queryKey: ["facility-maintenance-stats"],
      });
      toast.success("Marked complete");
    },
  });

  const isOverdue = (due: string | null) => {
    if (!due) return false;
    return new Date(due) < new Date();
  };

  const rrulePresets = [
    { label: "Daily", value: "FREQ=DAILY;INTERVAL=1" },
    { label: "Weekly", value: "FREQ=WEEKLY;INTERVAL=1" },
    { label: "Bi-weekly", value: "FREQ=WEEKLY;INTERVAL=2" },
    { label: "Monthly", value: "FREQ=MONTHLY;INTERVAL=1" },
  ];

  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-3">
        <select
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value)}
          className="rounded-md border border-gray-300 px-3 py-2 text-sm"
        >
          <option value="">All Types</option>
          {["cleaning", "inspection", "maintenance"].map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
        <label className="flex items-center gap-2 text-sm text-gray-600">
          <input
            type="checkbox"
            checked={overdueOnly}
            onChange={(e) => setOverdueOnly(e.target.checked)}
            className="rounded border-gray-300"
          />
          Overdue only
        </label>
        <div className="flex-1" />
        <button
          onClick={() => setShowAdd(!showAdd)}
          className="flex items-center gap-2 rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700"
        >
          <Plus className="h-4 w-4" /> Add Schedule
        </button>
      </div>

      {/* Add form */}
      {showAdd && (
        <Card>
          <CardContent className="grid gap-3 p-4 sm:grid-cols-2">
            <input
              placeholder="Title *"
              value={form.title || ""}
              onChange={(e) => setForm({ ...form, title: e.target.value })}
              className="rounded-md border border-gray-300 px-3 py-2 text-sm sm:col-span-2"
            />
            <select
              value={form.schedule_type || "cleaning"}
              onChange={(e) =>
                setForm({ ...form, schedule_type: e.target.value })
              }
              className="rounded-md border border-gray-300 px-3 py-2 text-sm"
            >
              {["cleaning", "inspection", "maintenance"].map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
            <select
              value={form.rrule || ""}
              onChange={(e) => setForm({ ...form, rrule: e.target.value })}
              className="rounded-md border border-gray-300 px-3 py-2 text-sm"
            >
              <option value="">No recurrence</option>
              {rrulePresets.map((p) => (
                <option key={p.value} value={p.value}>
                  {p.label}
                </option>
              ))}
            </select>
            <input
              placeholder="Assigned to"
              value={form.assigned_to || ""}
              onChange={(e) =>
                setForm({ ...form, assigned_to: e.target.value })
              }
              className="rounded-md border border-gray-300 px-3 py-2 text-sm"
            />
            <div>
              <label className="text-xs text-gray-500">Next due</label>
              <input
                type="datetime-local"
                value={form.next_due_at || ""}
                onChange={(e) =>
                  setForm({ ...form, next_due_at: e.target.value })
                }
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
              />
            </div>
            <div className="flex gap-2 sm:col-span-2">
              <button
                onClick={() => {
                  setShowAdd(false);
                  setForm({});
                }}
                className="rounded-md border border-gray-300 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                onClick={() => createMut.mutate()}
                disabled={!form.title || createMut.isPending}
                className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
              >
                {createMut.isPending ? "Creating..." : "Create Schedule"}
              </button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* List */}
      {isLoading ? (
        <div className="flex justify-center py-12">
          <Loader2 className="h-6 w-6 animate-spin text-gray-300" />
        </div>
      ) : !schedules?.length ? (
        <p className="py-8 text-center text-sm text-gray-400">
          No schedules configured
        </p>
      ) : (
        <div className="space-y-2">
          {schedules.map((sched: FacilitySchedule) => (
            <Card
              key={sched.id}
              className={
                isOverdue(sched.next_due_at)
                  ? "border-red-200 bg-red-50/30"
                  : ""
              }
            >
              <CardContent className="p-4">
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <h3 className="font-medium text-gray-900">
                        {sched.title}
                      </h3>
                      <Badge
                        label={sched.schedule_type}
                        colorMap={typeColors}
                      />
                      {isOverdue(sched.next_due_at) && (
                        <span className="rounded-full bg-red-100 px-2 py-0.5 text-xs font-medium text-red-800">
                          OVERDUE
                        </span>
                      )}
                    </div>
                    <div className="mt-1 flex gap-4 text-xs text-gray-500">
                      {sched.room_name && <span>Room: {sched.room_name}</span>}
                      {sched.equipment_name && (
                        <span>Equipment: {sched.equipment_name}</span>
                      )}
                      {sched.assigned_to && (
                        <span>Assigned: {sched.assigned_to}</span>
                      )}
                      <span>
                        Next due:{" "}
                        <span
                          className={
                            isOverdue(sched.next_due_at)
                              ? "font-medium text-red-600"
                              : ""
                          }
                        >
                          {fmtDateTime(sched.next_due_at)}
                        </span>
                      </span>
                      <span>
                        Last done: {fmtDateTime(sched.last_completed_at)}
                      </span>
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <button
                      onClick={() => completeMut.mutate(sched.id)}
                      disabled={completeMut.isPending}
                      className="flex items-center gap-1 rounded bg-green-100 px-3 py-1.5 text-xs font-medium text-green-800 hover:bg-green-200"
                    >
                      <CheckCircle className="h-3.5 w-3.5" /> Complete
                    </button>
                    <button
                      onClick={() =>
                        setExpandedHistory(
                          expandedHistory === sched.id ? null : sched.id
                        )
                      }
                      className="flex items-center gap-1 rounded border border-gray-200 px-3 py-1.5 text-xs text-gray-600 hover:bg-gray-50"
                    >
                      <Clock className="h-3.5 w-3.5" /> History
                    </button>
                  </div>
                </div>

                {/* History */}
                {expandedHistory === sched.id && (
                  <div className="mt-3 rounded-md border border-gray-200 p-3">
                    <h4 className="mb-2 text-xs font-medium text-gray-700">
                      Completion History
                    </h4>
                    {history && history.length > 0 ? (
                      <div className="space-y-1">
                        {history.map((c: ScheduleCompletion) => (
                          <div
                            key={c.id}
                            className="flex justify-between text-xs"
                          >
                            <span className="text-gray-600">
                              {fmtDateTime(c.completed_at)}
                            </span>
                            <span className="text-gray-500">
                              {c.notes || "No notes"}
                            </span>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="text-xs text-gray-400">
                        No completions yet
                      </p>
                    )}
                  </div>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
