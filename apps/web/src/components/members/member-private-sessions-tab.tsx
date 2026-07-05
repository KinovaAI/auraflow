"use client";

import { useQuery } from "@tanstack/react-query";
import { format, parseISO } from "date-fns";
import { CalendarClock } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { membersApi } from "@/lib/members-api";

function dollars(cents?: number) {
  if (cents === undefined || cents === null) return "—";
  return `$${(cents / 100).toFixed(2)}`;
}

const STATUS_STYLE: Record<string, string> = {
  completed: "bg-emerald-50 text-emerald-700",
  confirmed: "bg-blue-50 text-blue-700",
  pending: "bg-amber-50 text-amber-700",
  cancelled: "bg-red-50 text-red-600",
  no_show: "bg-yellow-50 text-yellow-700",
};

const CANCEL_BY_LABEL: Record<string, string> = {
  instructor: "Instructor",
  member: "Member",
  staff: "Staff",
};

const CANCEL_BY_STYLE: Record<string, string> = {
  instructor: "bg-blue-50 text-blue-700",
  member: "bg-slate-50 text-slate-600",
  staff: "bg-purple-50 text-purple-700",
};

export function MemberPrivateSessionsTab({ memberId }: { memberId: string }) {
  const { data: sessions, isLoading } = useQuery({
    queryKey: ["member-private-sessions", memberId],
    queryFn: () =>
      membersApi.getPrivateSessions(memberId).then((r) => r.data),
  });

  const completed = (sessions || []).filter((s) => s.status === "completed").length;
  const cancelled = (sessions || []).filter((s) => s.status === "cancelled").length;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base font-semibold">
          <CalendarClock className="h-4 w-4 text-slate-500" />
          Private Sessions
          {sessions && sessions.length > 0 && (
            <span className="ml-2 inline-flex items-center rounded bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-700">
              {sessions.length} total · {completed} completed · {cancelled} cancelled
            </span>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="py-6 text-center text-sm text-slate-500">Loading…</div>
        ) : !sessions || sessions.length === 0 ? (
          <div className="py-6 text-center text-sm text-slate-500">
            No private sessions yet.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-xs uppercase text-slate-500">
                <tr className="border-b border-slate-200">
                  <th className="px-2 py-2 text-left font-medium">Date</th>
                  <th className="px-2 py-2 text-left font-medium">Service</th>
                  <th className="px-2 py-2 text-left font-medium">Instructor</th>
                  <th className="px-2 py-2 text-left font-medium">Status</th>
                  <th className="px-2 py-2 text-right font-medium">Price</th>
                  <th className="px-2 py-2 text-left font-medium">Payment</th>
                  <th className="px-2 py-2 text-left font-medium">Cancel info</th>
                </tr>
              </thead>
              <tbody>
                {sessions.map((s) => (
                  <tr
                    key={s.id}
                    className="border-b border-slate-100 last:border-b-0"
                  >
                    <td className="px-2 py-2 text-slate-600 whitespace-nowrap">
                      {format(parseISO(s.starts_at), "MMM d, yyyy · h:mm a")}
                    </td>
                    <td className="px-2 py-2 text-slate-700">
                      {s.service_name || "—"}
                      {s.duration_minutes && (
                        <span className="ml-1 text-xs text-slate-500">
                          ({s.duration_minutes}m)
                        </span>
                      )}
                    </td>
                    <td className="px-2 py-2 text-slate-600">
                      {s.instructor_name || "—"}
                    </td>
                    <td className="px-2 py-2">
                      <span
                        className={`inline-flex rounded px-2 py-0.5 text-xs font-medium ${
                          STATUS_STYLE[s.status] ||
                          "bg-slate-100 text-slate-600"
                        }`}
                      >
                        {s.status}
                      </span>
                    </td>
                    <td className="px-2 py-2 text-right tabular-nums">
                      {dollars(s.price_cents)}
                    </td>
                    <td className="px-2 py-2 text-slate-600 text-xs">
                      {s.payment_status || "—"}
                    </td>
                    <td className="px-2 py-2 text-xs">
                      {s.status === "cancelled" && s.cancelled_by_role ? (
                        <div className="flex flex-col gap-0.5">
                          <span
                            className={`inline-flex w-fit rounded px-2 py-0.5 font-medium ${CANCEL_BY_STYLE[s.cancelled_by_role]}`}
                          >
                            {CANCEL_BY_LABEL[s.cancelled_by_role]}
                          </span>
                          {s.cancellation_reason && (
                            <span className="text-slate-500">
                              {s.cancellation_reason}
                            </span>
                          )}
                        </div>
                      ) : (
                        ""
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
