"use client";

import { useQuery } from "@tanstack/react-query";
import { format, parseISO } from "date-fns";
import { Receipt, ExternalLink } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { membersApi } from "@/lib/members-api";

function dollars(cents?: number) {
  if (cents === undefined || cents === null) return "—";
  return `$${(cents / 100).toFixed(2)}`;
}

const TYPE_LABEL: Record<string, string> = {
  payment: "Payment",
  refund: "Refund",
  partial_refund: "Partial refund",
  setup: "Card setup",
};

const STATUS_STYLE: Record<string, string> = {
  completed: "bg-emerald-50 text-emerald-700",
  pending: "bg-amber-50 text-amber-700",
  failed: "bg-red-50 text-red-600",
  refunded: "bg-slate-100 text-slate-600",
};

export function MemberPaymentsTab({ memberId }: { memberId: string }) {
  const { data: payments, isLoading } = useQuery({
    queryKey: ["member-payments", memberId],
    queryFn: () => membersApi.getPayments(memberId).then((r) => r.data),
  });

  const totalSpent = (payments || [])
    .filter((p) => (p.type === "payment" || !p.type) && p.status === "completed")
    .reduce((sum, p) => sum + (p.net_amount_cents || p.amount_cents || 0), 0);

  const totalRefunded = (payments || [])
    .filter((p) => p.type === "refund" || p.type === "partial_refund")
    .reduce((sum, p) => sum + (p.amount_cents || 0), 0);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base font-semibold">
          <Receipt className="h-4 w-4 text-slate-500" />
          Payments
          {payments && payments.length > 0 && (
            <span className="ml-2 inline-flex items-center rounded bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-700">
              {payments.length} txns · net {dollars(totalSpent - totalRefunded)}
            </span>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="py-6 text-center text-sm text-slate-500">Loading…</div>
        ) : !payments || payments.length === 0 ? (
          <div className="py-6 text-center text-sm text-slate-500">
            No payment history yet.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-xs uppercase text-slate-500">
                <tr className="border-b border-slate-200">
                  <th className="px-2 py-2 text-left font-medium">Date</th>
                  <th className="px-2 py-2 text-left font-medium">Type</th>
                  <th className="px-2 py-2 text-left font-medium">Description</th>
                  <th className="px-2 py-2 text-right font-medium">Amount</th>
                  <th className="px-2 py-2 text-right font-medium">Fee</th>
                  <th className="px-2 py-2 text-right font-medium">Net</th>
                  <th className="px-2 py-2 text-left font-medium">Status</th>
                  <th className="px-2 py-2 text-left font-medium">Stripe</th>
                </tr>
              </thead>
              <tbody>
                {payments.map((p) => {
                  const isRefund =
                    p.type === "refund" || p.type === "partial_refund";
                  return (
                    <tr
                      key={p.id}
                      className="border-b border-slate-100 last:border-b-0"
                    >
                      <td className="px-2 py-2 text-slate-600 whitespace-nowrap">
                        {format(parseISO(p.created_at), "MMM d, yyyy")}
                      </td>
                      <td className="px-2 py-2 text-slate-600">
                        {TYPE_LABEL[p.type || ""] || p.type || "—"}
                      </td>
                      <td className="px-2 py-2 text-slate-700 max-w-md truncate">
                        {p.description || p.membership_type_name || "—"}
                      </td>
                      <td
                        className={`px-2 py-2 text-right tabular-nums font-medium ${isRefund ? "text-red-600" : ""}`}
                      >
                        {isRefund ? "-" : ""}
                        {dollars(p.amount_cents)}
                      </td>
                      <td className="px-2 py-2 text-right tabular-nums text-slate-500">
                        {dollars(p.fee_cents)}
                      </td>
                      <td className="px-2 py-2 text-right tabular-nums">
                        {dollars(p.net_amount_cents)}
                      </td>
                      <td className="px-2 py-2">
                        <span
                          className={`inline-flex rounded px-2 py-0.5 text-xs font-medium ${
                            STATUS_STYLE[p.status || ""] ||
                            "bg-slate-100 text-slate-600"
                          }`}
                        >
                          {p.status || "—"}
                        </span>
                      </td>
                      <td className="px-2 py-2 text-xs text-slate-500">
                        {p.stripe_payment_intent_id ? (
                          <span
                            className="font-mono"
                            title={p.stripe_payment_intent_id}
                          >
                            {p.stripe_payment_intent_id.slice(-8)}
                          </span>
                        ) : (
                          ""
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
