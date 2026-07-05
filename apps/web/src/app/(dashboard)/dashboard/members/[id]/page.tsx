"use client";

import { useState, useEffect, useMemo } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter, useSearchParams } from "next/navigation";
import { format } from "date-fns";
import {
  ArrowLeft,
  Award,
  CheckCircle2,
  XCircle,
  Clock,
  AlertTriangle,
  Loader2,
  Mail,
  Phone,
  MapPin,
  Edit2,
  Trash2,
  Plus,
  Pin,
  Calendar,
  CreditCard,
  FileCheck,
  Smartphone,
  Zap,
} from "lucide-react";
import toast from "react-hot-toast";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { MemberFormModal } from "@/components/members/member-form-modal";
import { AssignMembershipModal } from "@/components/members/assign-membership-modal";
import { POSChargeModal } from "@/components/payments/pos-charge-modal";
import { POSTypePickerModal } from "@/components/payments/pos-type-picker-modal";
import { SavedCardChargeModal } from "@/components/payments/saved-card-charge-modal";
import { paymentsApi } from "@/lib/payments-api";
import { membersApi, type Member, type BookingHistory } from "@/lib/members-api";
import { apiClient } from "@/lib/api-client";
import {
  memberMembershipsApi,
  type MemberMembership,
} from "@/lib/memberships-api";
import { aiApi, type MemberMilestone } from "@/lib/ai-api";
import { ActivityTimeline } from "@/components/members/activity-timeline";
import { MemberCreditsTab } from "@/components/members/member-credits-tab";
import { MemberPaymentsTab } from "@/components/members/member-payments-tab";
import { MemberPrivateSessionsTab } from "@/components/members/member-private-sessions-tab";

const MILESTONE_BADGES: Record<string, { label: string; color: string }> = {
  visit_1: { label: "First Class", color: "bg-green-50 text-green-700" },
  visit_10: { label: "10 Classes", color: "bg-blue-50 text-blue-700" },
  visit_25: { label: "25 Classes", color: "bg-indigo-50 text-indigo-700" },
  visit_50: { label: "50 Classes", color: "bg-purple-50 text-purple-700" },
  visit_100: { label: "Century Club", color: "bg-yellow-50 text-yellow-700" },
  anniversary_1yr: { label: "1 Year Anniversary", color: "bg-pink-50 text-pink-700" },
  anniversary_2yr: { label: "2 Year Anniversary", color: "bg-pink-50 text-pink-700" },
};

function milestoneBadge(type: string) {
  return MILESTONE_BADGES[type] || { label: type.replace(/_/g, " "), color: "bg-gray-50 text-gray-700" };
}

type StatusFilter = "all" | "attended" | "cancelled" | "no_show" | "late_cancel" | "booked";

const STATUS_FILTERS: { key: StatusFilter; label: string; icon: typeof CheckCircle2 }[] = [
  { key: "all", label: "All", icon: Calendar },
  { key: "attended", label: "Attended", icon: CheckCircle2 },
  { key: "booked", label: "Upcoming", icon: Clock },
  { key: "cancelled", label: "Cancelled", icon: XCircle },
  { key: "no_show", label: "No-Shows", icon: AlertTriangle },
  { key: "late_cancel", label: "Late Cancels", icon: XCircle },
];

const STATUS_STYLES: Record<string, string> = {
  attended: "bg-green-50 text-green-700",
  checked_in: "bg-green-50 text-green-700",
  confirmed: "bg-blue-50 text-blue-700",
  booked: "bg-blue-50 text-blue-700",
  waitlisted: "bg-purple-50 text-purple-700",
  cancelled: "bg-red-50 text-red-600",
  late_cancel: "bg-orange-50 text-orange-700",
  no_show: "bg-yellow-50 text-yellow-700",
};

function ActivityHistory({ bookings }: { bookings?: BookingHistory[] }) {
  const [filter, setFilter] = useState<StatusFilter>("all");

  const stats = useMemo(() => {
    if (!bookings) return { attended: 0, cancelled: 0, no_show: 0, late_cancel: 0, booked: 0, total: 0 };
    return {
      attended: bookings.filter((b) => b.status === "attended" || b.status === "checked_in").length,
      cancelled: bookings.filter((b) => b.status === "cancelled" && !b.late_cancel).length,
      no_show: bookings.filter((b) => b.status === "no_show").length,
      late_cancel: bookings.filter((b) => b.late_cancel || b.status === "late_cancel").length,
      booked: bookings.filter((b) => b.status === "confirmed" || b.status === "booked" || b.status === "waitlisted").length,
      total: bookings.length,
    };
  }, [bookings]);

  const filtered = useMemo(() => {
    if (!bookings) return [];
    if (filter === "all") return bookings;
    if (filter === "attended") return bookings.filter((b) => b.status === "attended" || b.status === "checked_in");
    if (filter === "booked") return bookings.filter((b) => b.status === "confirmed" || b.status === "booked" || b.status === "waitlisted");
    if (filter === "cancelled") return bookings.filter((b) => (b.status === "cancelled" && !b.late_cancel));
    if (filter === "late_cancel") return bookings.filter((b) => b.late_cancel || b.status === "late_cancel");
    if (filter === "no_show") return bookings.filter((b) => b.status === "no_show");
    return bookings;
  }, [bookings, filter]);

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="text-base">Activity History</CardTitle>
          <span className="text-xs text-gray-400">{stats.total} total</span>
        </div>

        {/* Stats row */}
        {stats.total > 0 && (
          <div className="flex gap-4 pt-2 text-xs">
            <span className="text-green-600">{stats.attended} attended</span>
            <span className="text-blue-600">{stats.booked} upcoming</span>
            <span className="text-red-600">{stats.cancelled} cancelled</span>
            <span className="text-yellow-600">{stats.no_show} no-shows</span>
            {stats.late_cancel > 0 && (
              <span className="text-orange-600">{stats.late_cancel} late cancels</span>
            )}
          </div>
        )}
      </CardHeader>
      <CardContent>
        {!bookings?.length ? (
          <p className="text-sm text-gray-400">No activity history</p>
        ) : (
          <>
            {/* Filter tabs */}
            <div className="mb-4 flex flex-wrap gap-1">
              {STATUS_FILTERS.map((f) => {
                const count =
                  f.key === "all" ? stats.total : stats[f.key] ?? 0;
                if (f.key !== "all" && count === 0) return null;
                return (
                  <button
                    key={f.key}
                    onClick={() => setFilter(f.key)}
                    className={`flex items-center gap-1 rounded-full px-3 py-1 text-xs font-medium transition-colors ${
                      filter === f.key
                        ? "bg-indigo-100 text-indigo-700"
                        : "bg-gray-100 text-gray-600 hover:bg-gray-200"
                    }`}
                  >
                    {f.label}
                    <span className="ml-0.5 text-[10px] opacity-70">{count}</span>
                  </button>
                );
              })}
            </div>

            {/* Booking list */}
            <div className="space-y-2">
              {filtered.map((b) => {
                const displayStatus = b.late_cancel ? "late_cancel" : b.status;
                return (
                  <div
                    key={b.id}
                    className="flex items-center justify-between rounded-md border border-gray-100 px-3 py-2 text-sm"
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      <Calendar className="h-3.5 w-3.5 shrink-0 text-gray-400" />
                      <div className="min-w-0">
                        <span className="font-medium text-gray-700 truncate block">
                          {b.session_title || b.class_type_name || "Class"}
                        </span>
                        {b.class_category && (
                          <span className="text-[10px] uppercase text-gray-400">
                            {b.class_category}
                          </span>
                        )}
                      </div>
                    </div>
                    <div className="flex items-center gap-3 shrink-0">
                      <span className="text-xs text-gray-500">
                        {b.starts_at
                          ? format(new Date(b.starts_at), "MMM d, h:mm a")
                          : "—"}
                      </span>
                      <span
                        className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                          STATUS_STYLES[displayStatus] || "bg-gray-50 text-gray-600"
                        }`}
                      >
                        {displayStatus === "late_cancel"
                          ? "late cancel"
                          : displayStatus === "checked_in"
                            ? "attended"
                            : displayStatus.replace(/_/g, " ")}
                      </span>
                    </div>
                  </div>
                );
              })}
              {filtered.length === 0 && (
                <p className="py-4 text-center text-sm text-gray-400">
                  No {filter.replace(/_/g, " ")} bookings
                </p>
              )}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}

export default function MemberDetailPage({
  params,
}: {
  params: { id: string };
}) {
  const { id } = params;
  const router = useRouter();
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();
  const [showEditForm, setShowEditForm] = useState(false);
  const [showAssignMembership, setShowAssignMembership] = useState(false);
  const [posChargeOpen, setPOSChargeOpen] = useState<{
    amount_cents: number;
    description: string;
    membership_type_id?: string;
  } | null>(null);
  const [posTypePicker, setPosTypePicker] = useState(false);
  const [savedCardCharge, setSavedCardCharge] = useState<{ amount: string; description: string } | null>(null);
  const [newNote, setNewNote] = useState("");
  const [activeTab, setActiveTab] = useState<
    "overview" | "credits" | "payments" | "private_sessions"
  >("overview");

  // Handle Stripe Checkout return
  useEffect(() => {
    const checkout = searchParams.get("checkout");
    if (checkout === "success") {
      toast.success("Payment successful! Membership will be activated shortly.");
      queryClient.invalidateQueries({ queryKey: ["member-memberships", id] });
      router.replace(`/dashboard/members/${id}`);
    } else if (checkout === "cancelled") {
      toast("Checkout cancelled", { icon: "info" });
      router.replace(`/dashboard/members/${id}`);
    }
  }, [searchParams, id, queryClient, router]);

  const { data: member, isLoading } = useQuery({
    queryKey: ["member", id],
    queryFn: () => membersApi.get(id).then((r) => r.data),
  });

  const { data: notes } = useQuery({
    queryKey: ["member-notes", id],
    queryFn: () => membersApi.listNotes(id).then((r) => r.data),
  });

  const { data: memberships } = useQuery({
    queryKey: ["member-memberships", id],
    queryFn: () =>
      memberMembershipsApi.listForMember(id, false).then((r) => r.data),
  });

  const { data: bookings } = useQuery({
    queryKey: ["member-bookings", id],
    queryFn: () => membersApi.getBookings(id).then((r) => r.data),
  });

  const { data: milestones } = useQuery({
    queryKey: ["member-milestones", id],
    queryFn: () => aiApi.getMemberMilestones(id).then((r) => r.data.data),
  });

  const { data: waiverSigs } = useQuery({
    queryKey: ["member-waiver-sigs", id],
    queryFn: () =>
      apiClient
        .get<{ data: { id: string; template_title: string; template_version: number; signed_at: string; expires_at: string | null }[] }>(`/waivers/members/${id}/signatures`)
        .then((r) => r.data.data),
  });

  const { data: aiInsight } = useQuery({
    queryKey: ["member-insight", id],
    queryFn: () => aiApi.getMemberInsight(id).then((r) => r.data.data),
    retry: false,
  });

  const addNoteMutation = useMutation({
    mutationFn: () => membersApi.addNote(id, newNote),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["member-notes", id] });
      setNewNote("");
    },
  });

  const deleteNoteMutation = useMutation({
    mutationFn: (noteId: string) => membersApi.deleteNote(id, noteId),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["member-notes", id] }),
  });

  const freezeMutation = useMutation({
    mutationFn: (mmId: string) => memberMembershipsApi.freeze(mmId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["member-memberships", id] });
      toast.success("Membership frozen");
    },
  });

  const unfreezeMutation = useMutation({
    mutationFn: (mmId: string) => memberMembershipsApi.unfreeze(mmId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["member-memberships", id] });
      toast.success("Membership unfrozen");
    },
  });

  const cancelMembershipMutation = useMutation({
    mutationFn: (mmId: string) => memberMembershipsApi.cancel(mmId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["member-memberships", id] });
      toast.success("Membership cancelled");
    },
  });

  const deleteMemberMutation = useMutation({
    mutationFn: () => membersApi.deactivate(id),
    onSuccess: () => {
      toast.success("Member deleted");
      router.push("/dashboard/members");
    },
    onError: () => toast.error("Failed to delete member"),
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="h-8 w-8 animate-spin text-indigo-600" />
      </div>
    );
  }

  if (!member) {
    return (
      <div className="py-20 text-center text-gray-500">Member not found</div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => router.push("/dashboard/members")}
        >
          <ArrowLeft className="mr-1 h-4 w-4" />
          Back
        </Button>
      </div>

      {/* Header */}
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-4">
          <div className="flex h-14 w-14 items-center justify-center rounded-full bg-indigo-100 text-lg font-semibold text-indigo-700">
            {member.first_name[0]}
            {member.last_name[0]}
          </div>
          <div>
            <h1 className="text-2xl font-bold text-gray-900">
              {member.first_name} {member.last_name}
            </h1>
            <div className="flex items-center gap-4 text-sm text-gray-500">
              <span>{member.total_visits ?? 0} visits</span>
              <span>${((member.lifetime_revenue_cents ?? 0) / 100).toFixed(2)} lifetime</span>
              {member.member_number && <span>#{member.member_number}</span>}
            </div>
          </div>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setShowEditForm(true)}
          >
            <Edit2 className="mr-1 h-4 w-4" />
            Edit
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="text-red-600 hover:bg-red-50 hover:text-red-700"
            onClick={() => {
              if (confirm(`Delete ${member.first_name} ${member.last_name}? This will deactivate their account.`))
                deleteMemberMutation.mutate();
            }}
            disabled={deleteMemberMutation.isPending}
          >
            <Trash2 className="mr-1 h-4 w-4" />
            Delete
          </Button>
        </div>
      </div>

      {/* Tab strip */}
      <div className="flex flex-wrap gap-1 border-b border-slate-200">
        {[
          { key: "overview", label: "Overview" },
          { key: "credits", label: "Credits" },
          { key: "payments", label: "Payments" },
          { key: "private_sessions", label: "Private Sessions" },
        ].map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key as typeof activeTab)}
            className={`px-3 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
              activeTab === tab.key
                ? "border-indigo-600 text-indigo-700"
                : "border-transparent text-slate-600 hover:text-slate-900 hover:border-slate-300"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {activeTab === "credits" && <MemberCreditsTab memberId={id} />}
      {activeTab === "payments" && <MemberPaymentsTab memberId={id} />}
      {activeTab === "private_sessions" && (
        <MemberPrivateSessionsTab memberId={id} />
      )}

      {activeTab === "overview" && (
        <>
      <div className="grid gap-6 lg:grid-cols-3">
        {/* Contact Info */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Contact</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            <div className="flex items-center gap-2 text-sm text-gray-600">
              <Mail className="h-4 w-4 text-gray-400" />
              {member.email}
            </div>
            {member.phone && (
              <div className="flex items-center gap-2 text-sm text-gray-600">
                <Phone className="h-4 w-4 text-gray-400" />
                {member.phone}
              </div>
            )}
            {(member.city || member.state) && (
              <div className="flex items-center gap-2 text-sm text-gray-600">
                <MapPin className="h-4 w-4 text-gray-400" />
                {[member.address_line1, member.city, member.state, member.postal_code]
                  .filter(Boolean)
                  .join(", ")}
              </div>
            )}
            {member.emergency_contact_name && (
              <div className="mt-3 border-t pt-2 text-xs text-gray-400">
                Emergency: {member.emergency_contact_name}{" "}
                {member.emergency_contact_phone}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Memberships */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="text-base">Memberships</CardTitle>
            <div className="flex items-center gap-1">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setShowAssignMembership(true)}
                title="Assign manually"
              >
                <Plus className="h-4 w-4" />
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            {!memberships?.length ? (
              <p className="text-sm text-gray-400">No memberships</p>
            ) : (
              <div className="space-y-3">
                {memberships.map((mm) => (
                  <div
                    key={mm.id}
                    className="rounded-md border border-gray-200 p-3"
                  >
                    <div className="flex items-center justify-between">
                      <p className="text-sm font-medium text-gray-900">
                        {mm.type_name}
                      </p>
                      <span
                        className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                          mm.status === "active"
                            ? "bg-green-50 text-green-700"
                            : mm.status === "frozen"
                              ? "bg-blue-50 text-blue-700"
                              : "bg-gray-100 text-gray-500"
                        }`}
                      >
                        {mm.status}
                      </span>
                    </div>
                    {mm.classes_remaining != null && (
                      <p className="text-xs text-gray-500">
                        {mm.classes_remaining}/{mm.total_classes} classes
                        remaining
                      </p>
                    )}
                    {mm.status === "active" && (
                      <div className="mt-2 flex gap-1">
                        <button
                          className="text-xs text-blue-600 hover:underline disabled:opacity-50"
                          disabled={freezeMutation.isPending}
                          onClick={() => freezeMutation.mutate(mm.id)}
                        >
                          {freezeMutation.isPending ? "Freezing..." : "Freeze"}
                        </button>
                        <span className="text-xs text-gray-300">|</span>
                        <button
                          className="text-xs text-red-600 hover:underline disabled:opacity-50"
                          disabled={cancelMembershipMutation.isPending}
                          onClick={() => {
                            if (confirm("Cancel this membership?"))
                              cancelMembershipMutation.mutate(mm.id);
                          }}
                        >
                          {cancelMembershipMutation.isPending ? "Cancelling..." : "Cancel"}
                        </button>
                      </div>
                    )}
                    {mm.status === "frozen" && (
                      <button
                        className="mt-2 text-xs text-blue-600 hover:underline"
                        onClick={() => unfreezeMutation.mutate(mm.id)}
                      >
                        Unfreeze
                      </button>
                    )}
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Square POS + Card on file */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="text-base">Square POS</CardTitle>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setPosTypePicker(true)}
              title="Sell a membership / class pack via Square POS terminal"
            >
              <Smartphone className="h-4 w-4" />
            </Button>
          </CardHeader>
          <CardContent className="space-y-3">
            {member?.square_card_on_file_last4 ? (
              <div className="rounded-md border border-gray-200 bg-gray-50 px-3 py-2 text-sm">
                <div className="flex items-center justify-between">
                  <div>
                    <span className="font-medium text-gray-900">
                      {member.square_card_on_file_brand || "Card"} ••{member.square_card_on_file_last4}
                    </span>
                    {member.square_card_on_file_exp_month && member.square_card_on_file_exp_year && (
                      <span className="ml-2 text-xs text-gray-500">
                        exp {String(member.square_card_on_file_exp_month).padStart(2, "0")}/
                        {String(member.square_card_on_file_exp_year).slice(-2)}
                      </span>
                    )}
                  </div>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => setSavedCardCharge({ amount: "", description: "" })}
                  >
                    <Zap className="mr-1.5 h-3.5 w-3.5" />
                    Charge
                  </Button>
                </div>
                {member.square_card_on_file_saved_at && (
                  <div className="mt-1 text-xs text-gray-400">
                    Saved {format(new Date(member.square_card_on_file_saved_at), "MMM d, yyyy")}
                  </div>
                )}
              </div>
            ) : (
              <p className="text-xs text-gray-400">
                No card on file. The next Square POS sale will save the card automatically.
              </p>
            )}
            <Button
              variant="outline"
              size="sm"
              className="w-full"
              onClick={() => setPosTypePicker(true)}
            >
              <Smartphone className="mr-2 h-4 w-4 text-indigo-600" />
              Sell via Square POS
            </Button>
          </CardContent>
        </Card>

        {/* Notes */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Notes</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {notes?.map((note) => (
                <div
                  key={note.id}
                  className="group flex items-start gap-2 rounded-md border border-gray-100 p-2"
                >
                  {note.is_pinned && (
                    <Pin className="mt-0.5 h-3 w-3 text-indigo-500" />
                  )}
                  <p className="flex-1 text-sm text-gray-700">{note.note}</p>
                  <button
                    className="hidden text-gray-300 hover:text-red-500 group-hover:block"
                    onClick={() => deleteNoteMutation.mutate(note.id)}
                  >
                    <Trash2 className="h-3 w-3" />
                  </button>
                </div>
              ))}
            </div>
            <div className="mt-3 flex gap-2">
              <Input
                placeholder="Add a note..."
                value={newNote}
                onChange={(e) => setNewNote(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && newNote.trim()) {
                    addNoteMutation.mutate();
                  }
                }}
                className="text-sm"
              />
              <Button
                variant="outline"
                size="sm"
                onClick={() => addNoteMutation.mutate()}
                disabled={!newNote.trim()}
              >
                Add
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* AI Insight */}
      {aiInsight && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <span className="inline-flex h-5 w-5 items-center justify-center rounded bg-indigo-100 text-[10px] font-bold text-indigo-700">AI</span>
              Member Insight
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <p className="text-sm text-gray-700">{aiInsight.summary}</p>
            {aiInsight.highlights?.length > 0 && (
              <div>
                <p className="text-xs font-medium text-gray-500 mb-1">Highlights</p>
                <ul className="space-y-1">
                  {aiInsight.highlights.map((h: string, i: number) => (
                    <li key={i} className="flex items-start gap-2 text-sm text-gray-600">
                      <span className="mt-1.5 h-1.5 w-1.5 rounded-full bg-indigo-400 shrink-0" />
                      {h}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {aiInsight.recommendations?.length > 0 && (
              <div>
                <p className="text-xs font-medium text-gray-500 mb-1">Recommendations</p>
                <ul className="space-y-1">
                  {aiInsight.recommendations.map((r: string, i: number) => (
                    <li key={i} className="flex items-start gap-2 text-sm text-green-700">
                      <span className="mt-1.5 h-1.5 w-1.5 rounded-full bg-green-400 shrink-0" />
                      {r}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Waiver Status */}
      {waiverSigs && waiverSigs.length > 0 && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="text-base">Waiver Signatures</CardTitle>
              <FileCheck className="h-4 w-4 text-gray-400" />
            </div>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {waiverSigs.map((sig) => {
                const expired = sig.expires_at && new Date(sig.expires_at) < new Date();
                return (
                  <div key={sig.id} className="flex items-center justify-between rounded border px-3 py-2 text-sm">
                    <div>
                      <span className="font-medium text-gray-700">
                        v{sig.template_version} — {sig.template_title}
                      </span>
                      <p className="text-xs text-gray-400">
                        Signed {new Date(sig.signed_at).toLocaleDateString()}
                        {sig.expires_at && <> · Expires {new Date(sig.expires_at).toLocaleDateString()}</>}
                      </p>
                    </div>
                    <span className={`rounded px-2 py-0.5 text-xs font-medium ${expired ? "bg-red-50 text-red-700" : "bg-emerald-50 text-emerald-700"}`}>
                      {expired ? "Expired" : "Valid"}
                    </span>
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Activity Timeline */}
      <ActivityTimeline memberId={id} />

      {/* Activity History */}
      <ActivityHistory bookings={bookings} />

      {/* Milestones */}
      {milestones && milestones.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Milestones</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-2">
              {milestones.map((m) => {
                const badge = milestoneBadge(m.milestone_type);
                return (
                  <div
                    key={m.id}
                    className={`flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium ${badge.color}`}
                  >
                    <Award className="h-3.5 w-3.5" />
                    {badge.label}
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>
      )}
        </>
      )}

      {showEditForm && (
        <MemberFormModal
          member={member}
          onClose={() => setShowEditForm(false)}
          onCreated={() => {
            queryClient.invalidateQueries({ queryKey: ["member", id] });
            setShowEditForm(false);
            toast.success("Member updated");
          }}
        />
      )}

      {showAssignMembership && (
        <AssignMembershipModal
          memberId={id}
          onClose={() => setShowAssignMembership(false)}
          onAssigned={() => {
            queryClient.invalidateQueries({
              queryKey: ["member-memberships", id],
            });
            setShowAssignMembership(false);
            toast.success("Membership assigned");
          }}
        />
      )}

      {posTypePicker && member && (
        <POSTypePickerModal
          memberId={id}
          onClose={() => setPosTypePicker(false)}
          onPick={(args) => {
            setPosTypePicker(false);
            setPOSChargeOpen(args);
          }}
        />
      )}

      {posChargeOpen && member && (
        <POSChargeModal
          open={true}
          member={{ id, first_name: member.first_name, last_name: member.last_name }}
          amountCents={posChargeOpen.amount_cents}
          description={posChargeOpen.description}
          membershipTypeId={posChargeOpen.membership_type_id}
          onClose={() => setPOSChargeOpen(null)}
          onSuccess={() => {
            setPOSChargeOpen(null);
            queryClient.invalidateQueries({ queryKey: ["member", id] });
            queryClient.invalidateQueries({ queryKey: ["member-memberships", id] });
            toast.success("POS sale completed");
          }}
        />
      )}

      {savedCardCharge && member && member.square_card_on_file_id && (
        <SavedCardChargeModal
          memberId={id}
          memberName={`${member.first_name} ${member.last_name}`}
          last4={member.square_card_on_file_last4 || ""}
          initialAmount={savedCardCharge.amount}
          initialDescription={savedCardCharge.description}
          onClose={() => setSavedCardCharge(null)}
          onSuccess={() => {
            setSavedCardCharge(null);
            queryClient.invalidateQueries({ queryKey: ["member", id] });
            toast.success("Saved card charged");
          }}
        />
      )}
    </div>
  );
}

