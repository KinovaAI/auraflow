"use client";

import { useState, useEffect, useRef } from "react";
import { format, parseISO } from "date-fns";
import {
  X,
  Clock,
  MapPin,
  User,
  Users,
  AlertTriangle,
  Video,
  ExternalLink,
  Circle,
  Film,
  Upload,
  CheckCircle2,
  XCircle,
  Loader2,
  UserPlus,
  Search,
  DollarSign,
  Pencil,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { membersApi, type Member } from "@/lib/members-api";
import { memberMembershipsApi } from "@/lib/memberships-api";
import type { Session, RosterEntry } from "@/lib/scheduling-api";
import { sessionsApi } from "@/lib/scheduling-api";
import { CollectPayment } from "@/components/payments/collect-payment";
import toast from "react-hot-toast";

export interface AddClientData {
  member_id: string;
  class_session_id: string;
  source: string;
  guest_name?: string;
  guest_email?: string;
  /** If true, member needs a single-class membership assigned */
  needs_membership: boolean;
  /** Set after real payment is collected (card/square), or omitted for cash/comp */
  payment_intent_id?: string;
  /** How the payment was collected */
  payment_method?: "card" | "cash" | "square" | "comp";
}

interface SessionDetailModalProps {
  session: Session;
  onClose: () => void;
  onCancel: (id: string, reason?: string) => void;
  onEdit?: (session: Session) => void;
  onUploadRecording?: (session: Session) => void;
  roster?: RosterEntry[];
  rosterLoading?: boolean;
  onCheckIn?: (bookingId: string) => void;
  onNoShow?: (bookingId: string) => void;
  onCancelBooking?: (bookingId: string, lateCancel: boolean) => void;
  cancellingBookingId?: string | null;
  onAddClient?: (data: AddClientData) => void;
  addingClient?: boolean;
  dropInPriceCents?: number;
}

const statusBadge: Record<string, { bg: string; text: string; label: string }> = {
  confirmed: { bg: "bg-blue-100", text: "text-blue-700", label: "Confirmed" },
  attended: { bg: "bg-green-100", text: "text-green-700", label: "Checked In" },
  waitlisted: { bg: "bg-yellow-100", text: "text-yellow-700", label: "Waitlisted" },
  no_show: { bg: "bg-red-100", text: "text-red-700", label: "No Show" },
};

export function SessionDetailModal({
  session,
  onClose,
  onCancel,
  onEdit,
  onUploadRecording,
  roster,
  rosterLoading,
  onCheckIn,
  onNoShow,
  onCancelBooking,
  cancellingBookingId,
  onAddClient,
  addingClient,
  dropInPriceCents,
}: SessionDetailModalProps) {
  const [showCancelConfirm, setShowCancelConfirm] = useState(false);
  const [cancelReason, setCancelReason] = useState("");
  // Per-booking cancel dialog state. Null when closed; otherwise holds the
  // booking we're cancelling and which mode the staff picked.
  const [bookingCancelDialog, setBookingCancelDialog] = useState<
    { bookingId: string; displayName: string } | null
  >(null);

  // Close on Escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  // Add Client state
  const [showAddClient, setShowAddClient] = useState(false);
  const [addMode, setAddMode] = useState<"member" | "walkin">("member");
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<Member[]>([]);
  const [searching, setSearching] = useState(false);
  const [walkInName, setWalkInName] = useState("");
  const [walkInEmail, setWalkInEmail] = useState("");
  const searchTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Payment step state
  const [showPaymentStep, setShowPaymentStep] = useState(false);
  const [pendingMember, setPendingMember] = useState<{
    member_id: string;
    guest_name?: string;
    guest_email?: string;
  } | null>(null);
  const [checkingEligibility, setCheckingEligibility] = useState(false);

  const startsAt = parseISO(session.starts_at);
  const endsAt = parseISO(session.ends_at);
  const isCancelled = session.status === "cancelled";

  const confirmedCount = roster?.filter(
    (r) => r.status === "confirmed" || r.status === "attended"
  ).length ?? 0;

  const dropInPrice = dropInPriceCents ?? 0;

  // Debounced member search
  useEffect(() => {
    if (searchQuery.length < 2) {
      setSearchResults([]);
      return;
    }
    if (searchTimeout.current) clearTimeout(searchTimeout.current);
    searchTimeout.current = setTimeout(async () => {
      setSearching(true);
      try {
        const res = await membersApi.list({ search: searchQuery, limit: 8 });
        setSearchResults(res.data);
      } catch {
        setSearchResults([]);
      } finally {
        setSearching(false);
      }
    }, 300);
    return () => {
      if (searchTimeout.current) clearTimeout(searchTimeout.current);
    };
  }, [searchQuery]);

  const handleSelectMember = async (member: Member) => {
    // Check eligibility first
    setCheckingEligibility(true);
    try {
      const res = await memberMembershipsApi.checkEligibility(member.id);
      const eligibility = res.data;
      if (eligibility.eligible) {
        // Has active membership — book directly
        onAddClient?.({
          member_id: member.id,
          class_session_id: session.id,
          source: "walk_in",
          needs_membership: false,
        });
        setShowAddClient(false);
        setSearchQuery("");
        setSearchResults([]);
      } else {
        // No membership — show payment step
        setPendingMember({ member_id: member.id });
        setShowPaymentStep(true);
        setSearchQuery("");
        setSearchResults([]);
      }
    } catch {
      // On error, default to payment step
      setPendingMember({ member_id: member.id });
      setShowPaymentStep(true);
    } finally {
      setCheckingEligibility(false);
    }
  };

  const handleWalkInNext = () => {
    if (!walkInName.trim()) return;
    // Walk-ins always need payment
    setPendingMember({
      member_id: "",
      guest_name: walkInName.trim(),
      guest_email: walkInEmail.trim() || undefined,
    });
    setShowPaymentStep(true);
  };

  const handlePaymentSuccess = (result: {
    payment_method: "card" | "cash" | "square" | "comp";
    payment_intent_id?: string;
  }) => {
    if (!pendingMember) return;
    onAddClient?.({
      member_id: pendingMember.member_id,
      class_session_id: session.id,
      source: "walk_in",
      guest_name: pendingMember.guest_name,
      guest_email: pendingMember.guest_email,
      needs_membership: true,
      payment_intent_id: result.payment_intent_id,
      payment_method: result.payment_method,
    });
  };

  const handleBackFromPayment = () => {
    setShowPaymentStep(false);
    setPendingMember(null);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="mx-4 w-full max-w-2xl rounded-lg bg-white shadow-xl max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-gray-200 px-6 py-4 shrink-0">
          <h2 className="text-lg font-semibold text-gray-900">
            {session.title}
          </h2>
          <button
            onClick={onClose}
            className="rounded-md p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Body — scrollable */}
        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
          {isCancelled && (
            <div className="flex items-center gap-2 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">
              <AlertTriangle className="h-4 w-4" />
              This session has been cancelled
            </div>
          )}

          <div className="flex items-start gap-3">
            <Clock className="mt-0.5 h-4 w-4 text-gray-400" />
            <div>
              <p className="text-sm font-medium text-gray-900">
                {format(startsAt, "EEEE, MMM d, yyyy")}
              </p>
              <p className="text-sm text-gray-500">
                {format(startsAt, "h:mm a")} - {format(endsAt, "h:mm a")}
              </p>
            </div>
          </div>

          {session.class_type_name && (
            <div className="flex items-center gap-3">
              <div className="h-4 w-4 rounded-full bg-indigo-500" />
              <p className="text-sm text-gray-700">{session.class_type_name}</p>
            </div>
          )}

          {session.instructor_name && (
            <div className="flex items-center gap-3">
              <User className="h-4 w-4 text-gray-400" />
              <p className="text-sm text-gray-700">
                {session.instructor_name}
              </p>
            </div>
          )}

          {session.room_name && (
            <div className="flex items-center gap-3">
              <MapPin className="h-4 w-4 text-gray-400" />
              <p className="text-sm text-gray-700">{session.room_name}</p>
            </div>
          )}

          <div className="flex items-center gap-3">
            <Users className="h-4 w-4 text-gray-400" />
            <p className="text-sm text-gray-700">
              {session.booked_count ?? 0} booked
              {session.capacity ? ` / ${session.capacity} capacity` : ""}
              {session.waitlist_count
                ? ` (${session.waitlist_count} waitlisted)`
                : ""}
            </p>
          </div>

          {/* Virtual / Zoom Toggle */}
          <div className="rounded-md border border-indigo-200 bg-indigo-50/50 p-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Video className="h-4 w-4 text-indigo-600" />
                <span className="text-sm font-medium text-indigo-900">Virtual Class (Zoom)</span>
              </div>
              <button
                type="button"
                role="switch"
                aria-checked={session.is_virtual || false}
                onClick={async () => {
                  try {
                    await sessionsApi.update(session.id, { is_virtual: !session.is_virtual });
                    toast.success(session.is_virtual ? "Zoom disabled for this class" : "Zoom enabled — meeting will be created");
                    onClose();
                  } catch { toast.error("Failed to update"); }
                }}
                className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors ${
                  session.is_virtual ? "bg-indigo-600" : "bg-gray-200"
                }`}
              >
                <span className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow-lg transition-transform ${
                  session.is_virtual ? "translate-x-5" : "translate-x-0"
                }`} />
              </button>
            </div>
          </div>

          {/* Zoom Details (when virtual) */}
          {session.is_virtual && (
            <div className="rounded-md border border-indigo-200 bg-indigo-50 p-3 space-y-2">
              <div className="flex items-center gap-2">
                <Video className="h-4 w-4 text-indigo-600" />
                <span className="text-sm font-medium text-indigo-900">
                  Virtual Class
                </span>
              </div>
              {session.zoom_join_url && (
                <a
                  href={session.zoom_join_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1.5 rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 transition-colors"
                >
                  <ExternalLink className="h-3.5 w-3.5" />
                  Join Zoom Meeting
                </a>
              )}
              {session.zoom_password && (
                <p className="text-xs text-indigo-700">
                  Password: <code className="rounded bg-indigo-100 px-1">{session.zoom_password}</code>
                </p>
              )}
            </div>
          )}

          {/* Community Class Toggle */}
          <div className="rounded-md border border-amber-200 bg-amber-50/50 p-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="text-base">🏘️</span>
                <span className="text-sm font-medium text-amber-900">Community Class</span>
              </div>
              <button
                type="button"
                role="switch"
                aria-checked={session.is_community || false}
                onClick={async () => {
                  try {
                    await sessionsApi.update(session.id, { is_community: !session.is_community });
                    toast.success(session.is_community ? "Removed community flag" : "Marked as community class");
                    onClose();
                  } catch { toast.error("Failed to update"); }
                }}
                className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors ${
                  session.is_community ? "bg-amber-500" : "bg-gray-200"
                }`}
              >
                <span className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow-lg transition-transform ${
                  session.is_community ? "translate-x-5" : "translate-x-0"
                }`} />
              </button>
            </div>
            {session.is_community && (
              <p className="mt-1 text-xs text-amber-700">Requires Community Class Pass or unlimited membership</p>
            )}
          </div>

          {/* On-Demand Recording */}
          {session.auto_record && (
            <div className="rounded-md border border-emerald-200 bg-emerald-50 p-3 space-y-2">
              <div className="flex items-center gap-2">
                <Film className="h-4 w-4 text-emerald-600" />
                <span className="text-sm font-medium text-emerald-900">
                  On-Demand Recording
                </span>
                {session.video_id ? (
                  <span className="inline-flex items-center gap-1 rounded-full bg-blue-100 px-2 py-0.5 text-xs font-medium text-blue-700">
                    <Circle className="h-2 w-2 fill-current" />
                    published
                  </span>
                ) : session.recording_status && session.recording_status !== "none" ? (
                  <span
                    className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${
                      session.recording_status === "processing"
                        ? "bg-yellow-100 text-yellow-700"
                        : session.recording_status === "ready"
                        ? "bg-green-100 text-green-700"
                        : "bg-gray-100 text-gray-700"
                    }`}
                  >
                    <Circle className="h-2 w-2 fill-current" />
                    {session.recording_status}
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1 rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-500">
                    awaiting upload
                  </span>
                )}
              </div>
              {session.video_id ? (
                <p className="text-xs text-emerald-700">
                  Recording available in Video Library
                </p>
              ) : (
                <Button
                  size="sm"
                  variant="outline"
                  className="border-emerald-300 text-emerald-700 hover:bg-emerald-100"
                  onClick={() => onUploadRecording?.(session)}
                >
                  <Upload className="mr-1.5 h-3.5 w-3.5" />
                  Upload Recording
                </Button>
              )}
            </div>
          )}

          {/* ── Roster Section ───────────────────────────────────────── */}
          <div className="border-t border-gray-200 pt-4">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-semibold text-gray-900">Roster</h3>
              <div className="flex items-center gap-2">
                <span className="text-xs text-gray-500">
                  {confirmedCount}{session.capacity ? ` / ${session.capacity}` : ""} checked in / booked
                </span>
                {!isCancelled && (
                  <Button
                    size="sm"
                    variant="outline"
                    className="h-7 text-xs"
                    onClick={() => {
                      setShowAddClient(!showAddClient);
                      setShowPaymentStep(false);
                      setPendingMember(null);
                    }}
                  >
                    <UserPlus className="h-3.5 w-3.5 mr-1" />
                    Add Client
                  </Button>
                )}
              </div>
            </div>

            {/* ── Add Client Form ─────────────────────────────────── */}
            {showAddClient && !showPaymentStep && (
              <div className="mb-3 rounded-md border border-indigo-200 bg-indigo-50/50 p-3 space-y-3">
                <div className="flex gap-1 rounded-md border border-gray-200 bg-white p-0.5 w-fit">
                  <button
                    className={`rounded px-3 py-1 text-xs font-medium ${
                      addMode === "member"
                        ? "bg-indigo-100 text-indigo-700"
                        : "text-gray-500 hover:text-gray-700"
                    }`}
                    onClick={() => setAddMode("member")}
                  >
                    Existing Member
                  </button>
                  <button
                    className={`rounded px-3 py-1 text-xs font-medium ${
                      addMode === "walkin"
                        ? "bg-indigo-100 text-indigo-700"
                        : "text-gray-500 hover:text-gray-700"
                    }`}
                    onClick={() => setAddMode("walkin")}
                  >
                    Walk-in Guest
                  </button>
                </div>

                {addMode === "member" ? (
                  <div>
                    <div className="relative">
                      <Search className="absolute left-2.5 top-2 h-4 w-4 text-gray-400" />
                      <input
                        type="text"
                        placeholder="Search by name or email..."
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                        className="w-full rounded-md border border-gray-300 bg-white py-1.5 pl-8 pr-3 text-sm focus:border-transparent focus:outline-none focus:ring-2 focus:ring-indigo-500"
                        autoFocus
                      />
                      {(searching || checkingEligibility) && (
                        <Loader2 className="absolute right-2.5 top-2 h-4 w-4 animate-spin text-gray-400" />
                      )}
                    </div>
                    {searchResults.length > 0 && (
                      <div className="mt-1 max-h-40 overflow-y-auto rounded-md border border-gray-200 bg-white">
                        {searchResults.map((m) => {
                          const alreadyBooked = roster?.some(
                            (r) => r.member_id === m.id && r.status !== "cancelled"
                          );
                          return (
                            <button
                              key={m.id}
                              disabled={alreadyBooked || checkingEligibility}
                              onClick={() => handleSelectMember(m)}
                              className={`flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-gray-50 border-b border-gray-100 last:border-0 ${
                                alreadyBooked ? "opacity-50 cursor-not-allowed" : ""
                              }`}
                            >
                              <div className="flex h-7 w-7 items-center justify-center rounded-full bg-gray-100 text-xs font-medium text-gray-600 shrink-0">
                                {m.first_name?.[0]}{m.last_name?.[0]}
                              </div>
                              <div className="min-w-0 flex-1">
                                <p className="font-medium text-gray-900 truncate">
                                  {m.first_name} {m.last_name}
                                </p>
                                <p className="text-xs text-gray-500 truncate">{m.email}</p>
                              </div>
                              {alreadyBooked && (
                                <span className="text-xs text-gray-400">Already booked</span>
                              )}
                            </button>
                          );
                        })}
                      </div>
                    )}
                    {searchQuery.length >= 2 && !searching && searchResults.length === 0 && (
                      <p className="mt-1 text-xs text-gray-500 text-center py-2">
                        No members found
                      </p>
                    )}
                  </div>
                ) : (
                  <div className="space-y-2">
                    <input
                      type="text"
                      placeholder="Guest name *"
                      value={walkInName}
                      onChange={(e) => setWalkInName(e.target.value)}
                      className="w-full rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm focus:border-transparent focus:outline-none focus:ring-2 focus:ring-indigo-500"
                      autoFocus
                    />
                    <input
                      type="email"
                      placeholder="Guest email (optional)"
                      value={walkInEmail}
                      onChange={(e) => setWalkInEmail(e.target.value)}
                      className="w-full rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm focus:border-transparent focus:outline-none focus:ring-2 focus:ring-indigo-500"
                    />
                    <Button
                      size="sm"
                      onClick={handleWalkInNext}
                      disabled={!walkInName.trim()}
                      className="w-full"
                    >
                      Next: Payment
                    </Button>
                  </div>
                )}
              </div>
            )}

            {/* ── Drop-in Payment Step (Real Processing) ─────────── */}
            {showAddClient && showPaymentStep && pendingMember && (
              <div className="mb-3 rounded-md border border-green-200 bg-green-50/50 p-3 space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <DollarSign className="h-4 w-4 text-green-600" />
                    <h4 className="text-sm font-semibold text-gray-900">
                      Drop-in Payment
                    </h4>
                  </div>
                  <button
                    onClick={handleBackFromPayment}
                    className="text-xs text-gray-500 hover:text-gray-700"
                  >
                    Back
                  </button>
                </div>

                {pendingMember.guest_name && (
                  <p className="text-xs text-gray-600">
                    Guest: <span className="font-medium">{pendingMember.guest_name}</span>
                  </p>
                )}

                <CollectPayment
                  amountCents={dropInPrice}
                  memberId={pendingMember.member_id}
                  description={`Drop-in: ${session.title}`}
                  onSuccess={handlePaymentSuccess}
                  onCancel={handleBackFromPayment}
                />
              </div>
            )}

            {rosterLoading ? (
              <div className="flex items-center justify-center py-6">
                <Loader2 className="h-5 w-5 animate-spin text-gray-400" />
                <span className="ml-2 text-sm text-gray-500">Loading roster...</span>
              </div>
            ) : roster && roster.length > 0 ? (
              <div className="space-y-2">
                {roster.map((entry) => {
                  const badge = statusBadge[entry.status] || {
                    bg: "bg-gray-100",
                    text: "text-gray-700",
                    label: entry.status,
                  };
                  const displayName = entry.guest_name
                    ? entry.guest_name
                    : `${entry.first_name} ${entry.last_name}`;
                  const initials = entry.guest_name
                    ? entry.guest_name.split(" ").map((w) => w[0]).join("").slice(0, 2)
                    : `${entry.first_name?.[0] ?? ""}${entry.last_name?.[0] ?? ""}`;
                  return (
                    <div
                      key={entry.id}
                      className="flex items-center justify-between rounded-md border border-gray-200 px-3 py-2"
                    >
                      <div className="flex items-center gap-3 min-w-0">
                        <div className="flex h-8 w-8 items-center justify-center rounded-full bg-gray-100 text-xs font-medium text-gray-600 shrink-0">
                          {initials}
                        </div>
                        <div className="min-w-0">
                          <p className="text-sm font-medium text-gray-900 truncate">
                            {displayName}
                            {entry.guest_name && (
                              <span className="ml-1.5 text-xs font-normal text-gray-400">(guest)</span>
                            )}
                          </p>
                          {(entry.member_email || entry.guest_email) && (
                            <p className="text-xs text-gray-500 truncate">
                              {entry.member_email || entry.guest_email}
                            </p>
                          )}
                        </div>
                      </div>

                      <div className="flex items-center gap-2 shrink-0 ml-2">
                        {entry.status === "waitlisted" && entry.waitlist_position && (
                          <span className="text-xs text-gray-500 mr-1">
                            #{entry.waitlist_position}
                          </span>
                        )}
                        <span
                          className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${badge.bg} ${badge.text}`}
                        >
                          {badge.label}
                        </span>

                        {entry.status === "attended" && entry.checked_in_at && (
                          <span className="text-xs text-gray-400">
                            {format(parseISO(entry.checked_in_at), "h:mm a")}
                          </span>
                        )}

                        {entry.status === "confirmed" && (
                          <div className="flex gap-1">
                            <Button
                              size="sm"
                              variant="ghost"
                              className="h-7 px-2 text-green-600 hover:bg-green-50 hover:text-green-700"
                              onClick={() => onCheckIn?.(entry.id)}
                            >
                              <CheckCircle2 className="h-4 w-4 mr-1" />
                              Check In
                            </Button>
                            <Button
                              size="sm"
                              variant="ghost"
                              className="h-7 px-2 text-red-500 hover:bg-red-50 hover:text-red-600"
                              onClick={() => onNoShow?.(entry.id)}
                            >
                              <XCircle className="h-4 w-4 mr-1" />
                              No Show
                            </Button>
                            {onCancelBooking && (
                              <Button
                                size="sm"
                                variant="ghost"
                                className="h-7 px-2 text-gray-600 hover:bg-gray-50 hover:text-gray-700"
                                onClick={() =>
                                  setBookingCancelDialog({
                                    bookingId: entry.id,
                                    displayName,
                                  })
                                }
                                disabled={cancellingBookingId === entry.id}
                                title="Cancel booking"
                              >
                                {cancellingBookingId === entry.id
                                  ? "Cancelling…"
                                  : "Cancel"}
                              </Button>
                            )}
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <p className="text-sm text-gray-500 py-4 text-center">
                No bookings yet for this session.
              </p>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-2 border-t border-gray-200 px-6 py-4 shrink-0">
          {!isCancelled && !showCancelConfirm && onEdit && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => onEdit(session)}
            >
              <Pencil className="mr-1.5 h-3.5 w-3.5" />
              Edit Class
            </Button>
          )}

          {!isCancelled && !showCancelConfirm && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => setShowCancelConfirm(true)}
              className="text-red-600 hover:bg-red-50 hover:text-red-700"
            >
              Cancel Session
            </Button>
          )}

          {showCancelConfirm && (
            <div className="flex w-full flex-col gap-2">
              <input
                type="text"
                placeholder="Cancellation reason (optional)"
                value={cancelReason}
                onChange={(e) => setCancelReason(e.target.value)}
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-transparent focus:outline-none focus:ring-2 focus:ring-indigo-500"
              />
              <div className="flex justify-end gap-2">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setShowCancelConfirm(false)}
                >
                  Back
                </Button>
                <Button
                  size="sm"
                  className="bg-red-600 hover:bg-red-700"
                  onClick={() => onCancel(session.id, cancelReason || undefined)}
                >
                  Confirm Cancel
                </Button>
              </div>
            </div>
          )}

          {!showCancelConfirm && (
            <Button variant="ghost" size="sm" onClick={onClose}>
              Close
            </Button>
          )}
        </div>

        {/* Per-booking cancel / late-cancel dialog. Replaces window.confirm()
             so the prompt renders consistently on touchscreen kiosks (where
             native confirms can be tiny or hard to dismiss) and so the
             two destinations (refund vs late-cancel) are visible side-by-side
             without sequential prompts. */}
        {bookingCancelDialog && onCancelBooking && (
          <div
            className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 p-4"
            onClick={() => setBookingCancelDialog(null)}
          >
            <div
              className="w-full max-w-md rounded-lg bg-white shadow-xl"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="border-b border-gray-200 px-5 py-3">
                <h3 className="text-base font-semibold text-gray-900">
                  Cancel {bookingCancelDialog.displayName}'s booking
                </h3>
              </div>
              <div className="px-5 py-4 space-y-3 text-sm text-gray-700">
                <p>Pick which kind of cancellation this is:</p>
                <ul className="list-disc pl-5 space-y-1 text-xs text-gray-500">
                  <li>
                    <span className="font-medium text-gray-700">Cancel</span> —
                    refunds the class-pack credit (regular cancellation).
                  </li>
                  <li>
                    <span className="font-medium text-gray-700">Late Cancel</span> —
                    keeps the credit deducted (late-window or no-show policy).
                  </li>
                </ul>
              </div>
              <div className="flex flex-col-reverse gap-2 border-t border-gray-200 px-5 py-3 sm:flex-row sm:justify-end">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setBookingCancelDialog(null)}
                >
                  Back
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  className="text-orange-600 border-orange-300 hover:bg-orange-50"
                  disabled={cancellingBookingId === bookingCancelDialog.bookingId}
                  onClick={() => {
                    onCancelBooking(bookingCancelDialog.bookingId, true);
                    setBookingCancelDialog(null);
                  }}
                >
                  Late Cancel
                </Button>
                <Button
                  size="sm"
                  className="bg-gray-700 hover:bg-gray-800"
                  disabled={cancellingBookingId === bookingCancelDialog.bookingId}
                  onClick={() => {
                    onCancelBooking(bookingCancelDialog.bookingId, false);
                    setBookingCancelDialog(null);
                  }}
                >
                  Cancel + refund credit
                </Button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
