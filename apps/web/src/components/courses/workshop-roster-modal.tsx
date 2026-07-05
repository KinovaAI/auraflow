"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { format, parseISO } from "date-fns";
import {
  X,
  Loader2,
  CheckCircle2,
  XCircle,
  Circle,
  UserMinus,
  Mail,
  Phone,
} from "lucide-react";
import toast from "react-hot-toast";

import { Button } from "@/components/ui/button";
import {
  coursesApi,
  type Course,
  type Enrollment,
  type CourseSession,
  type AttendanceRecord,
} from "@/lib/courses-api";
import { POSChargeModal } from "@/components/payments/pos-charge-modal";
import { CreditCard, UserPlus, Search } from "lucide-react";
import { membersApi, type Member } from "@/lib/members-api";

type AttendanceStatus = "attended" | "no_show" | null;

interface Props {
  course: Course;
  onClose: () => void;
}

export function WorkshopRosterModal({ course, onClose }: Props) {
  const queryClient = useQueryClient();
  const [view, setView] = useState<"roster" | "attendance">("roster");
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
  const [walkInPicker, setWalkInPicker] = useState(false);
  const [walkInTarget, setWalkInTarget] = useState<{
    member: Member;
    amount_cents: number;
  } | null>(null);

  const { data: enrollments, isLoading: enrollmentsLoading } = useQuery({
    queryKey: ["course-enrollments", course.id],
    queryFn: () =>
      coursesApi.listEnrollments(course.id).then((r) => r.data.data),
  });

  const { data: sessions } = useQuery({
    queryKey: ["course-sessions", course.id],
    queryFn: () =>
      coursesApi.listSessions(course.id).then((r) => r.data.data),
  });

  const { data: attendanceForSession } = useQuery({
    queryKey: ["course-session-attendance", selectedSessionId],
    queryFn: () =>
      coursesApi
        .getSessionAttendance(selectedSessionId!)
        .then((r) => r.data.data),
    enabled: !!selectedSessionId,
  });

  // Build a quick lookup: member_id -> attendance status for the selected session
  const attendanceMap = new Map<string, AttendanceStatus>();
  (attendanceForSession || []).forEach((a: AttendanceRecord) => {
    attendanceMap.set(a.member_id, (a.status as AttendanceStatus) ?? null);
  });

  const recordMutation = useMutation({
    mutationFn: (vars: { memberId: string; status: AttendanceStatus }) =>
      coursesApi.recordAttendance(
        selectedSessionId!,
        vars.memberId,
        vars.status ?? "attended",
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ["course-session-attendance", selectedSessionId],
      });
    },
    onError: () => toast.error("Failed to update attendance"),
  });

  const withdrawMutation = useMutation({
    mutationFn: (enrollmentId: string) =>
      coursesApi.withdrawEnrollment(enrollmentId),
    onSuccess: () => {
      toast.success("Member withdrawn from workshop");
      queryClient.invalidateQueries({
        queryKey: ["course-enrollments", course.id],
      });
    },
    onError: () => toast.error("Failed to withdraw member"),
  });

  const activeEnrollments = (enrollments || []).filter(
    (e: Enrollment) => e.status === "enrolled",
  );

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={onClose}
    >
      <div
        className="flex max-h-[90vh] w-full max-w-4xl flex-col rounded-lg bg-white shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between border-b border-gray-200 px-6 py-4">
          <div>
            <h2 className="text-lg font-semibold text-gray-900">
              {course.title}
            </h2>
            <p className="mt-0.5 text-sm text-gray-500">
              {activeEnrollments.length} enrolled
              {course.capacity ? ` of ${course.capacity}` : ""}
              {sessions?.length
                ? ` · ${sessions.length} session${sessions.length === 1 ? "" : "s"}`
                : ""}
            </p>
          </div>
          <button
            onClick={onClose}
            className="rounded-md p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 border-b border-gray-200 px-4 pt-2">
          <button
            type="button"
            onClick={() => setView("roster")}
            className={`rounded-t-md px-4 py-2 text-sm font-medium ${
              view === "roster"
                ? "border-b-2 border-indigo-600 text-indigo-600"
                : "text-gray-500 hover:text-gray-700"
            }`}
          >
            Roster
          </button>
          <button
            type="button"
            onClick={() => {
              setView("attendance");
              if (!selectedSessionId && sessions?.length) {
                setSelectedSessionId(sessions[0].id);
              }
            }}
            className={`rounded-t-md px-4 py-2 text-sm font-medium ${
              view === "attendance"
                ? "border-b-2 border-indigo-600 text-indigo-600"
                : "text-gray-500 hover:text-gray-700"
            }`}
          >
            Attendance
          </button>
        </div>

        <div className="flex-1 overflow-auto">
          {enrollmentsLoading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="h-6 w-6 animate-spin text-indigo-600" />
            </div>
          ) : view === "roster" ? (
            <RosterView
              enrollments={activeEnrollments}
              course={course}
              onAddWalkIn={() => setWalkInPicker(true)}
              onWithdraw={(id) => {
                if (window.confirm("Withdraw this member from the workshop?")) {
                  withdrawMutation.mutate(id);
                }
              }}
              withdrawing={withdrawMutation.isPending}
            />
          ) : (
            <AttendanceView
              sessions={sessions || []}
              selectedSessionId={selectedSessionId}
              onSelectSession={setSelectedSessionId}
              enrollments={activeEnrollments}
              attendanceMap={attendanceMap}
              onMark={(memberId, status) =>
                recordMutation.mutate({ memberId, status })
              }
              isRecording={recordMutation.isPending}
            />
          )}
        </div>
      </div>

      {walkInPicker && (
        <WalkInMemberPicker
          course={course}
          enrolledMemberIds={new Set(activeEnrollments.map((e) => e.member_id))}
          onClose={() => setWalkInPicker(false)}
          onPick={(member, amount_cents) => {
            setWalkInPicker(false);
            setWalkInTarget({ member, amount_cents });
          }}
        />
      )}

      {walkInTarget && (
        <POSChargeModal
          open={true}
          member={{
            id: walkInTarget.member.id,
            first_name: walkInTarget.member.first_name,
            last_name: walkInTarget.member.last_name,
          }}
          amountCents={walkInTarget.amount_cents}
          description={`Workshop drop-in: ${course.title}`}
          // Server enrolls automatically when the deeplink callback (or
          // the expiry-sweep reconciler) confirms payment — passing
          // course.id is what makes that happen. The Terminal API path
          // also benefits, since the client-side enrollMember below is
          // now belt-and-suspenders rather than load-bearing.
          courseId={course.id}
          onClose={() => setWalkInTarget(null)}
          onSuccess={async () => {
            // Server-side enroll is the authoritative path (deeplink
            // callback or pos_checkout_expiry sweeper). This client-side
            // call is a fast-path for the Terminal API case where the
            // modal is still mounted when payment completes. Idempotent
            // on the DB side via UNIQUE (course_id, member_id).
            try {
              await coursesApi.enrollMember(course.id, walkInTarget.member.id);
            } catch {
              // If client-side enroll lost the race, server already did it.
            }
            toast.success("Charged & enrolled");
            setWalkInTarget(null);
            queryClient.invalidateQueries({ queryKey: ["course-enrollments", course.id] });
          }}
        />
      )}
    </div>
  );
}

// ── Roster view ─────────────────────────────────────────────────────────────

function RosterView({
  enrollments,
  course,
  onAddWalkIn,
  onWithdraw,
  withdrawing,
}: {
  enrollments: Enrollment[];
  course: Course;
  onAddWalkIn: () => void;
  onWithdraw: (enrollmentId: string) => void;
  withdrawing: boolean;
}) {
  const isPaid = (course.price_cents ?? 0) > 0;
  return (
    <div>
      {isPaid && (
        <div className="flex items-center justify-between border-b border-gray-100 bg-gray-50 px-6 py-3">
          <p className="text-xs text-gray-500">
            Walk-in? Add them here — they&apos;ll be charged on Square POS and enrolled.
          </p>
          <Button size="sm" onClick={onAddWalkIn}>
            <UserPlus className="mr-1.5 h-4 w-4" />
            Add walk-in
          </Button>
        </div>
      )}
      {!enrollments.length ? (
        <div className="px-6 py-12 text-center text-sm text-gray-500">
          No one is enrolled yet.
        </div>
      ) : (
        <div className="divide-y divide-gray-100">
      {enrollments.map((e) => {
        const name = e.member_name ||
          [e.first_name, e.last_name].filter(Boolean).join(" ") ||
          "Member";
        return (
          <div key={e.id} className="flex items-start justify-between px-6 py-3">
            <div className="min-w-0 flex-1">
              <p className="font-medium text-gray-900">{name}</p>
              <div className="mt-0.5 flex flex-wrap items-center gap-3 text-xs text-gray-500">
                {e.email && (
                  <a
                    href={`mailto:${e.email}`}
                    className="inline-flex items-center gap-1 hover:text-indigo-600"
                  >
                    <Mail className="h-3 w-3" />
                    {e.email}
                  </a>
                )}
                {e.phone && (
                  <a
                    href={`tel:${e.phone}`}
                    className="inline-flex items-center gap-1 hover:text-indigo-600"
                  >
                    <Phone className="h-3 w-3" />
                    {e.phone}
                  </a>
                )}
                <span className="text-gray-400">
                  Enrolled {format(parseISO(e.enrolled_at), "MMM d")}
                </span>
              </div>
            </div>
            <Button
              size="sm"
              variant="ghost"
              className="text-red-500 hover:bg-red-50 hover:text-red-600"
              onClick={() => onWithdraw(e.id)}
              disabled={withdrawing}
              title="Withdraw member"
            >
              <UserMinus className="h-4 w-4" />
            </Button>
          </div>
        );
      })}
        </div>
      )}
    </div>
  );
}

// ── Walk-in member picker ───────────────────────────────────────────────────
// Searches members. Pick → opens POSChargeModal pre-filled with the workshop's
// current price (early-bird if before deadline).

function WalkInMemberPicker({
  course,
  enrolledMemberIds,
  onClose,
  onPick,
}: {
  course: Course;
  enrolledMemberIds: Set<string>;
  onClose: () => void;
  onPick: (member: Member, amount_cents: number) => void;
}) {
  const [search, setSearch] = useState("");
  const { data: members, isLoading } = useQuery({
    queryKey: ["walkin-member-search", search],
    queryFn: () => membersApi.list({ search, limit: 10 }).then((r) => r.data),
    enabled: search.length >= 2,
  });

  const now = Date.now();
  const ebDeadline = course.early_bird_deadline ? new Date(course.early_bird_deadline).getTime() : 0;
  const price = (course.early_bird_price_cents && ebDeadline && now < ebDeadline)
    ? course.early_bird_price_cents
    : course.price_cents;
  const priceLabel = `$${((price ?? 0) / 100).toFixed(2)}`;

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 p-4"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
    >
      <div
        className="flex max-h-[85vh] w-full max-w-md flex-col rounded-lg bg-white shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="border-b border-gray-200 px-5 py-4">
          <h3 className="text-base font-semibold text-gray-900">Add walk-in</h3>
          <p className="mt-0.5 text-xs text-gray-500">
            Pick a member to charge {priceLabel} on Square POS and enroll in the workshop.
          </p>
        </div>
        <div className="border-b border-gray-100 px-5 py-3">
          <div className="relative">
            <Search className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-gray-400" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search name or email…"
              className="w-full rounded-md border border-gray-300 py-2 pl-8 pr-3 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              autoFocus
            />
          </div>
        </div>
        <div className="flex-1 overflow-y-auto">
          {search.length < 2 ? (
            <p className="px-5 py-8 text-center text-sm text-gray-500">
              Type at least 2 characters to search.
            </p>
          ) : isLoading ? (
            <div className="flex justify-center py-8">
              <Loader2 className="h-5 w-5 animate-spin text-indigo-600" />
            </div>
          ) : !members?.length ? (
            <p className="px-5 py-8 text-center text-sm text-gray-500">No members match.</p>
          ) : (
            <ul className="divide-y divide-gray-100">
              {members.map((m) => {
                const already = enrolledMemberIds.has(m.id);
                return (
                  <li key={m.id}>
                    <button
                      type="button"
                      disabled={already || !price}
                      onClick={() => onPick(m, price!)}
                      className="flex w-full items-center justify-between px-5 py-3 text-left hover:bg-indigo-50 disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:bg-transparent"
                    >
                      <div>
                        <p className="text-sm font-medium text-gray-900">
                          {m.first_name} {m.last_name}
                        </p>
                        <p className="text-xs text-gray-500">{m.email}</p>
                      </div>
                      {already && <span className="text-xs text-gray-400">already enrolled</span>}
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
        <div className="border-t border-gray-100 px-5 py-3 text-right">
          <Button variant="outline" size="sm" onClick={onClose}>Close</Button>
        </div>
      </div>
    </div>
  );
}

// ── Attendance view ─────────────────────────────────────────────────────────

function AttendanceView({
  sessions,
  selectedSessionId,
  onSelectSession,
  enrollments,
  attendanceMap,
  onMark,
  isRecording,
}: {
  sessions: CourseSession[];
  selectedSessionId: string | null;
  onSelectSession: (id: string) => void;
  enrollments: Enrollment[];
  attendanceMap: Map<string, AttendanceStatus>;
  onMark: (memberId: string, status: AttendanceStatus) => void;
  isRecording: boolean;
}) {
  if (!sessions.length) {
    return (
      <div className="px-6 py-12 text-center text-sm text-gray-500">
        No sessions scheduled.
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-3 p-4">
      <div className="flex gap-1 overflow-x-auto pb-1">
        {sessions.map((s) => {
          const isActive = selectedSessionId === s.id;
          return (
            <button
              key={s.id}
              type="button"
              onClick={() => onSelectSession(s.id)}
              className={`whitespace-nowrap rounded-md border px-3 py-1.5 text-xs font-medium ${
                isActive
                  ? "border-indigo-600 bg-indigo-50 text-indigo-700"
                  : "border-gray-200 bg-white text-gray-700 hover:bg-gray-50"
              }`}
            >
              {format(parseISO(s.starts_at), "EEE MMM d · h:mm a")}
            </button>
          );
        })}
      </div>

      {!selectedSessionId ? (
        <p className="px-2 py-6 text-center text-sm text-gray-500">
          Pick a session above to record attendance.
        </p>
      ) : !enrollments.length ? (
        <p className="px-2 py-6 text-center text-sm text-gray-500">
          No one is enrolled yet.
        </p>
      ) : (
        <div className="divide-y divide-gray-100 rounded-md border border-gray-200">
          {enrollments.map((e) => {
            const name = e.member_name ||
              [e.first_name, e.last_name].filter(Boolean).join(" ") ||
              "Member";
            const status = attendanceMap.get(e.member_id) ?? null;
            return (
              <div key={e.member_id} className="flex items-center justify-between px-4 py-2">
                <span className="text-sm text-gray-900">{name}</span>
                <div className="flex items-center gap-1">
                  <Button
                    size="sm"
                    variant="ghost"
                    className={`h-7 px-2 ${
                      status === "attended"
                        ? "bg-green-100 text-green-700 hover:bg-green-200"
                        : "text-gray-400 hover:bg-green-50 hover:text-green-700"
                    }`}
                    onClick={() => onMark(e.member_id, "attended")}
                    disabled={isRecording}
                    title="Mark attended"
                  >
                    <CheckCircle2 className="h-4 w-4" />
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    className={`h-7 px-2 ${
                      status === "no_show"
                        ? "bg-red-100 text-red-700 hover:bg-red-200"
                        : "text-gray-400 hover:bg-red-50 hover:text-red-700"
                    }`}
                    onClick={() => onMark(e.member_id, "no_show")}
                    disabled={isRecording}
                    title="Mark no-show"
                  >
                    <XCircle className="h-4 w-4" />
                  </Button>
                  {status === null && (
                    <Circle className="ml-1 h-3 w-3 text-gray-300" />
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
