"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { format, isAfter, parseISO } from "date-fns";
import { CreditCard, Plus, Trash2, AlertCircle, CheckCircle2 } from "lucide-react";
import toast from "react-hot-toast";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { membersApi, type MemberCredit } from "@/lib/members-api";

const SOURCE_LABEL: Record<MemberCredit["source"], string> = {
  instructor_cancellation: "Instructor cancel",
  courtesy: "Courtesy",
  refund_to_credit: "Refunded to credit",
  gift: "Gift",
  manual_grant: "Manual grant",
};

const SOURCE_STYLE: Record<MemberCredit["source"], string> = {
  instructor_cancellation: "bg-blue-50 text-blue-700",
  courtesy: "bg-emerald-50 text-emerald-700",
  refund_to_credit: "bg-amber-50 text-amber-700",
  gift: "bg-pink-50 text-pink-700",
  manual_grant: "bg-slate-50 text-slate-700",
};

function dollars(cents: number) {
  return `$${(cents / 100).toFixed(2)}`;
}

function isExpired(credit: MemberCredit) {
  if (!credit.expires_at) return false;
  return isAfter(new Date(), parseISO(credit.expires_at));
}

export function MemberCreditsTab({ memberId }: { memberId: string }) {
  const qc = useQueryClient();
  const [showHistory, setShowHistory] = useState(false);
  const [showGrantForm, setShowGrantForm] = useState(false);

  const { data: credits, isLoading } = useQuery({
    queryKey: ["member-credits", memberId, showHistory],
    queryFn: () =>
      membersApi.getCredits(memberId, showHistory).then((r) => r.data),
  });

  const grantMutation = useMutation({
    mutationFn: (body: {
      amount_cents: number;
      source: "courtesy" | "manual_grant" | "refund_to_credit" | "gift";
      service_filter?: "private_session" | "class" | "workshop" | null;
      notes?: string;
    }) => membersApi.grantCredit(memberId, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["member-credits", memberId] });
      toast.success("Credit granted");
      setShowGrantForm(false);
    },
    onError: (e: Error) => toast.error(e.message || "Failed to grant credit"),
  });

  const revokeMutation = useMutation({
    mutationFn: ({ creditId, reason }: { creditId: string; reason?: string }) =>
      membersApi.revokeCredit(memberId, creditId, reason),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["member-credits", memberId] });
      toast.success("Credit revoked");
    },
    onError: (e: Error) => toast.error(e.message || "Failed to revoke credit"),
  });

  const available = (credits || []).filter((c) => !c.used_at && !isExpired(c));
  const availableTotal = available.reduce((sum, c) => sum + c.amount_cents, 0);

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between gap-2">
        <CardTitle className="flex items-center gap-2 text-base font-semibold">
          <CreditCard className="h-4 w-4 text-slate-500" />
          Banked Credits
          {available.length > 0 && (
            <span className="ml-2 inline-flex items-center rounded bg-emerald-50 px-2 py-0.5 text-xs font-medium text-emerald-700">
              {available.length} available · {dollars(availableTotal)}
            </span>
          )}
        </CardTitle>
        <div className="flex items-center gap-2">
          <button
            className="text-xs text-slate-500 hover:text-slate-700 underline"
            onClick={() => setShowHistory((v) => !v)}
          >
            {showHistory ? "Hide history" : "Show history"}
          </button>
          <Button
            size="sm"
            variant="outline"
            onClick={() => setShowGrantForm((v) => !v)}
          >
            <Plus className="mr-1 h-3 w-3" />
            Grant credit
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        {showGrantForm && (
          <GrantCreditForm
            onCancel={() => setShowGrantForm(false)}
            onSubmit={(body) => grantMutation.mutate(body)}
            submitting={grantMutation.isPending}
          />
        )}

        {isLoading ? (
          <div className="py-6 text-center text-sm text-slate-500">Loading…</div>
        ) : !credits || credits.length === 0 ? (
          <div className="py-6 text-center text-sm text-slate-500">
            {showHistory ? "No credit history yet." : "No available credits."}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-xs uppercase text-slate-500">
                <tr className="border-b border-slate-200">
                  <th className="px-2 py-2 text-left font-medium">Source</th>
                  <th className="px-2 py-2 text-right font-medium">Amount</th>
                  <th className="px-2 py-2 text-left font-medium">For</th>
                  <th className="px-2 py-2 text-left font-medium">Granted</th>
                  <th className="px-2 py-2 text-left font-medium">Expires</th>
                  <th className="px-2 py-2 text-left font-medium">Status</th>
                  <th className="px-2 py-2 text-left font-medium">Notes</th>
                  <th className="px-2 py-2 text-right font-medium" />
                </tr>
              </thead>
              <tbody>
                {credits.map((c) => {
                  const expired = isExpired(c);
                  const used = !!c.used_at;
                  const revoked = c.used_booking_table === "revoked";
                  let statusLabel = "Available";
                  let statusStyle = "bg-emerald-50 text-emerald-700";
                  if (revoked) {
                    statusLabel = "Revoked";
                    statusStyle = "bg-red-50 text-red-600";
                  } else if (used) {
                    statusLabel = "Used";
                    statusStyle = "bg-slate-100 text-slate-600";
                  } else if (expired) {
                    statusLabel = "Expired";
                    statusStyle = "bg-yellow-50 text-yellow-700";
                  }
                  return (
                    <tr
                      key={c.id}
                      className="border-b border-slate-100 last:border-b-0"
                    >
                      <td className="px-2 py-2">
                        <span
                          className={`inline-flex rounded px-2 py-0.5 text-xs font-medium ${SOURCE_STYLE[c.source]}`}
                        >
                          {SOURCE_LABEL[c.source]}
                        </span>
                      </td>
                      <td className="px-2 py-2 text-right font-medium tabular-nums">
                        {dollars(c.amount_cents)}
                      </td>
                      <td className="px-2 py-2 text-slate-600">
                        {c.service_filter === "private_session"
                          ? "Private sessions"
                          : c.service_filter === "class"
                            ? "Classes"
                            : c.service_filter === "workshop"
                              ? "Workshops"
                              : "Any"}
                      </td>
                      <td className="px-2 py-2 text-slate-600 whitespace-nowrap">
                        {format(parseISO(c.created_at), "MMM d, yyyy")}
                      </td>
                      <td className="px-2 py-2 text-slate-600 whitespace-nowrap">
                        {c.expires_at
                          ? format(parseISO(c.expires_at), "MMM d, yyyy")
                          : "—"}
                      </td>
                      <td className="px-2 py-2">
                        <span
                          className={`inline-flex rounded px-2 py-0.5 text-xs font-medium ${statusStyle}`}
                        >
                          {statusLabel}
                        </span>
                      </td>
                      <td className="px-2 py-2 text-slate-600 max-w-xs truncate">
                        {c.notes || ""}
                      </td>
                      <td className="px-2 py-2 text-right">
                        {!used && !expired && (
                          <button
                            className="text-xs text-red-600 hover:text-red-800"
                            onClick={() => {
                              if (confirm("Revoke this credit? This can't be undone.")) {
                                revokeMutation.mutate({ creditId: c.id });
                              }
                            }}
                          >
                            <Trash2 className="h-3 w-3" />
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function GrantCreditForm({
  onCancel,
  onSubmit,
  submitting,
}: {
  onCancel: () => void;
  onSubmit: (body: {
    amount_cents: number;
    source: "courtesy" | "manual_grant" | "refund_to_credit" | "gift";
    service_filter?: "private_session" | "class" | "workshop" | null;
    notes?: string;
  }) => void;
  submitting: boolean;
}) {
  const [amount, setAmount] = useState("");
  const [source, setSource] = useState<
    "courtesy" | "manual_grant" | "refund_to_credit" | "gift"
  >("courtesy");
  const [serviceFilter, setServiceFilter] = useState<
    "private_session" | "class" | "workshop" | ""
  >("private_session");
  const [notes, setNotes] = useState("");

  const handleSubmit = () => {
    const cents = Math.round(parseFloat(amount) * 100);
    if (!cents || cents <= 0) {
      toast.error("Enter a dollar amount");
      return;
    }
    onSubmit({
      amount_cents: cents,
      source,
      service_filter: serviceFilter || null,
      notes: notes.trim() || undefined,
    });
  };

  return (
    <div className="mb-4 rounded-lg border border-slate-200 bg-slate-50 p-3 space-y-3">
      <div className="grid grid-cols-1 sm:grid-cols-4 gap-2 text-sm">
        <label className="flex flex-col gap-1">
          <span className="text-xs font-medium text-slate-600">Amount ($)</span>
          <input
            type="number"
            min="0"
            step="0.01"
            className="rounded border border-slate-300 px-2 py-1.5"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            placeholder="50.00"
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-xs font-medium text-slate-600">Reason</span>
          <select
            className="rounded border border-slate-300 px-2 py-1.5"
            value={source}
            onChange={(e) => setSource(e.target.value as typeof source)}
          >
            <option value="courtesy">Courtesy</option>
            <option value="manual_grant">Manual grant</option>
            <option value="refund_to_credit">Refund to credit</option>
            <option value="gift">Gift</option>
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-xs font-medium text-slate-600">Applies to</span>
          <select
            className="rounded border border-slate-300 px-2 py-1.5"
            value={serviceFilter}
            onChange={(e) =>
              setServiceFilter(e.target.value as typeof serviceFilter)
            }
          >
            <option value="private_session">Private sessions</option>
            <option value="class">Classes</option>
            <option value="workshop">Workshops</option>
            <option value="">Any</option>
          </select>
        </label>
        <label className="flex flex-col gap-1 sm:col-span-1">
          <span className="text-xs font-medium text-slate-600">Note (optional)</span>
          <input
            type="text"
            className="rounded border border-slate-300 px-2 py-1.5"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="why this credit was issued"
          />
        </label>
      </div>
      <div className="flex justify-end gap-2">
        <Button size="sm" variant="ghost" onClick={onCancel}>
          Cancel
        </Button>
        <Button size="sm" onClick={handleSubmit} disabled={submitting}>
          {submitting ? "Granting…" : "Grant credit"}
        </Button>
      </div>
    </div>
  );
}
