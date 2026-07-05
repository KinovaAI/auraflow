"use client";

import { useState, useEffect } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useSearchParams, useRouter } from "next/navigation";
import Link from "next/link";
import { format } from "date-fns";
import {
  Loader2,
  DollarSign,
  TrendingUp,
  AlertTriangle,
  ArrowDownRight,
  CreditCard,
  Mail,
  ExternalLink,
  CheckCircle,
  Gift,
} from "lucide-react";
import toast from "react-hot-toast";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  paymentsApi,
  type Transaction,
  type RevenueSummary,
} from "@/lib/payments-api";
import { RecordPaymentModal } from "@/components/payments/record-payment-modal";

export default function PaymentsPage() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const queryClient = useQueryClient();
  const [showRecordPayment, setShowRecordPayment] = useState(false);
  const [days, setDays] = useState(30);
  const [activeTab, setActiveTab] = useState<
    "transactions" | "failed" | "communications"
  >("transactions");
  const [connectLoading, setConnectLoading] = useState(false);

  const { data: revenue, isLoading: revenueLoading } = useQuery({
    queryKey: ["revenue-summary", days],
    queryFn: () => paymentsApi.getRevenueSummary(days).then((r) => r.data.data),
  });

  const { data: transactions, isLoading: txnLoading } = useQuery({
    queryKey: ["transactions"],
    queryFn: () =>
      paymentsApi.listTransactions({ limit: 100 }).then((r) => r.data.data),
  });

  const { data: failedPayments } = useQuery({
    queryKey: ["failed-payments"],
    queryFn: () => paymentsApi.listFailedPayments().then((r) => r.data.data),
  });

  const { data: communications } = useQuery({
    queryKey: ["communications"],
    queryFn: () =>
      paymentsApi
        .listCommunications({ limit: 50 })
        .then((r) => r.data.data),
  });

  const { data: connectStatus } = useQuery({
    queryKey: ["connect-status"],
    queryFn: () => paymentsApi.getConnectStatus().then((r) => r.data),
  });

  // Handle Stripe Connect return
  useEffect(() => {
    const stripe = searchParams.get("stripe");
    if (stripe === "connected") {
      toast.success("Stripe account setup in progress!");
      queryClient.invalidateQueries({ queryKey: ["connect-status"] });
      router.replace("/dashboard/payments");
    } else if (stripe === "refresh") {
      toast("Stripe setup needs to be completed", { icon: "info" });
      router.replace("/dashboard/payments");
    }
  }, [searchParams, queryClient, router]);

  const fmt = (cents: number) => `$${(cents / 100).toFixed(2)}`;

  const handleStartOnboarding = async () => {
    setConnectLoading(true);
    try {
      const returnUrl = `${window.location.origin}/dashboard/payments?stripe=connected`;
      const refreshUrl = `${window.location.origin}/dashboard/payments?stripe=refresh`;
      const res = await paymentsApi.startOnboarding(returnUrl, refreshUrl);
      window.location.href = res.data.url;
    } catch {
      toast.error("Failed to start Stripe setup");
      setConnectLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Payments</h1>
          <p className="text-sm text-gray-500">
            Revenue, transactions, and payment management
          </p>
        </div>
        <div className="flex items-center gap-2">
          {connectStatus && !connectStatus.connected && (
            <Button
              variant="outline"
              size="sm"
              disabled={connectLoading}
              onClick={handleStartOnboarding}
            >
              {connectLoading ? (
                <Loader2 className="mr-1 h-4 w-4 animate-spin" />
              ) : (
                <CreditCard className="mr-1 h-4 w-4" />
              )}
              Set Up Stripe
            </Button>
          )}
          {connectStatus?.connected && (
            <span className="flex items-center gap-1 rounded-full bg-green-50 px-2 py-1 text-xs font-medium text-green-700">
              <CheckCircle className="h-3 w-3" />
              Stripe Connected
            </span>
          )}
          <Link href="/dashboard/payments/gift-cards">
            <Button variant="outline">
              <Gift className="mr-1 h-4 w-4" />
              Gift Cards
            </Button>
          </Link>
          <Button onClick={() => setShowRecordPayment(true)}>
            <DollarSign className="mr-1 h-4 w-4" />
            Record Payment
          </Button>
        </div>
      </div>

      {/* Connect Setup Banner */}
      {connectStatus && !connectStatus.connected && (
        <Card className="border-indigo-200 bg-indigo-50">
          <CardContent className="flex items-center justify-between py-4">
            <div className="flex items-center gap-3">
              <div className="rounded-full bg-indigo-100 p-2">
                <CreditCard className="h-5 w-5 text-indigo-600" />
              </div>
              <div>
                <p className="text-sm font-medium text-gray-900">
                  Connect Stripe to accept online payments
                </p>
                <p className="text-xs text-gray-500">
                  Accept credit cards, set up recurring memberships, and manage payouts
                </p>
              </div>
            </div>
            <Button size="sm" disabled={connectLoading} onClick={handleStartOnboarding}>
              {connectLoading ? (
                <Loader2 className="mr-1 h-4 w-4 animate-spin" />
              ) : (
                <ExternalLink className="mr-1 h-4 w-4" />
              )}
              Get Started
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Connect: pending details */}
      {connectStatus?.connected && !connectStatus.details_submitted && (
        <Card className="border-yellow-200 bg-yellow-50">
          <CardContent className="flex items-center justify-between py-4">
            <div className="flex items-center gap-3">
              <div className="rounded-full bg-yellow-100 p-2">
                <AlertTriangle className="h-5 w-5 text-yellow-600" />
              </div>
              <div>
                <p className="text-sm font-medium text-gray-900">
                  Finish setting up your Stripe account
                </p>
                <p className="text-xs text-gray-500">
                  Complete your account details to enable charges and payouts
                </p>
              </div>
            </div>
            <Button
              variant="outline"
              size="sm"
              disabled={connectLoading}
              onClick={handleStartOnboarding}
            >
              Continue Setup
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Revenue Cards */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-gray-500">
                  Total Revenue
                </p>
                <p className="mt-1 text-2xl font-bold text-gray-900">
                  {revenueLoading ? (
                    <Loader2 className="h-5 w-5 animate-spin" />
                  ) : (
                    fmt(revenue?.total_revenue ?? 0)
                  )}
                </p>
              </div>
              <div className="rounded-full bg-green-100 p-2">
                <DollarSign className="h-5 w-5 text-green-600" />
              </div>
            </div>
            <p className="mt-2 text-xs text-gray-400">Last {days} days</p>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-gray-500">
                  Net Revenue
                </p>
                <p className="mt-1 text-2xl font-bold text-gray-900">
                  {revenueLoading ? (
                    <Loader2 className="h-5 w-5 animate-spin" />
                  ) : (
                    fmt(revenue?.net_revenue ?? 0)
                  )}
                </p>
              </div>
              <div className="rounded-full bg-indigo-100 p-2">
                <TrendingUp className="h-5 w-5 text-indigo-600" />
              </div>
            </div>
            <p className="mt-2 text-xs text-gray-400">After fees</p>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-gray-500">
                  Transactions
                </p>
                <p className="mt-1 text-2xl font-bold text-gray-900">
                  {revenueLoading ? (
                    <Loader2 className="h-5 w-5 animate-spin" />
                  ) : (
                    revenue?.transaction_count ?? 0
                  )}
                </p>
              </div>
              <div className="rounded-full bg-blue-100 p-2">
                <CreditCard className="h-5 w-5 text-blue-600" />
              </div>
            </div>
            <p className="mt-2 text-xs text-gray-400">Last {days} days</p>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-gray-500">Refunds</p>
                <p className="mt-1 text-2xl font-bold text-gray-900">
                  {revenueLoading ? (
                    <Loader2 className="h-5 w-5 animate-spin" />
                  ) : (
                    fmt(revenue?.total_refunds ?? 0)
                  )}
                </p>
              </div>
              <div className="rounded-full bg-red-100 p-2">
                <ArrowDownRight className="h-5 w-5 text-red-600" />
              </div>
            </div>
            <p className="mt-2 text-xs text-gray-400">Last {days} days</p>
          </CardContent>
        </Card>
      </div>

      {/* Period selector */}
      <div className="flex gap-2">
        {[7, 30, 90].map((d) => (
          <button
            key={d}
            onClick={() => setDays(d)}
            className={`rounded-md px-3 py-1.5 text-sm font-medium ${
              days === d
                ? "bg-indigo-100 text-indigo-700"
                : "text-gray-500 hover:bg-gray-100"
            }`}
          >
            {d}d
          </button>
        ))}
      </div>

      {/* Tabs */}
      <div className="flex gap-4 overflow-x-auto border-b border-gray-200">
        {(
          [
            { key: "transactions", label: "Transactions", count: transactions?.length },
            { key: "failed", label: "Failed Payments", count: failedPayments?.length },
            { key: "communications", label: "Emails Sent", count: communications?.length },
          ] as const
        ).map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`border-b-2 px-1 pb-3 text-sm font-medium ${
              activeTab === tab.key
                ? "border-indigo-500 text-indigo-600"
                : "border-transparent text-gray-500 hover:text-gray-700"
            }`}
          >
            {tab.label}
            {tab.count ? (
              <span className="ml-1.5 rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-600">
                {tab.count}
              </span>
            ) : null}
          </button>
        ))}
      </div>

      {/* Transactions Table */}
      {activeTab === "transactions" && (
        <>
          {txnLoading ? (
            <div className="flex items-center justify-center py-20">
              <Loader2 className="h-8 w-8 animate-spin text-indigo-600" />
            </div>
          ) : !transactions?.length ? (
            <div className="rounded-lg border border-dashed border-gray-300 py-12 text-center">
              <p className="text-sm text-gray-500">No transactions yet</p>
            </div>
          ) : (
            <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                      Date
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                      Member
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                      Description
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                      Type
                    </th>
                    <th className="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-gray-500">
                      Amount
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                      Status
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200">
                  {transactions.map((txn) => (
                    <tr key={txn.id} className="hover:bg-gray-50">
                      <td className="whitespace-nowrap px-4 py-3 text-sm text-gray-500">
                        {format(new Date(txn.created_at), "MMM d, h:mm a")}
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 text-sm text-gray-900">
                        {txn.first_name} {txn.last_name}
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-600">
                        {txn.description || "—"}
                      </td>
                      <td className="whitespace-nowrap px-4 py-3">
                        <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-600">
                          {txn.type}
                        </span>
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 text-right text-sm font-medium">
                        <span
                          className={
                            txn.status === "refunded"
                              ? "text-red-600"
                              : "text-gray-900"
                          }
                        >
                          {txn.status === "refunded" && "−"}
                          {fmt(txn.amount_cents)}
                        </span>
                        {txn.refund_amount_cents ? (
                          <span className="ml-1 text-xs text-red-500">
                            (−{fmt(txn.refund_amount_cents)} refund)
                          </span>
                        ) : null}
                      </td>
                      <td className="whitespace-nowrap px-4 py-3">
                        <span
                          className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                            txn.status === "completed"
                              ? "bg-green-50 text-green-700"
                              : txn.status === "refunded"
                                ? "bg-red-50 text-red-600"
                                : txn.status === "partially_refunded"
                                  ? "bg-yellow-50 text-yellow-700"
                                  : "bg-gray-100 text-gray-500"
                          }`}
                        >
                          {txn.status}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {/* Failed Payments */}
      {activeTab === "failed" && (
        <>
          {!failedPayments?.length ? (
            <div className="rounded-lg border border-dashed border-gray-300 py-12 text-center">
              <p className="text-sm text-gray-500">No failed payments</p>
            </div>
          ) : (
            <div className="space-y-3">
              {failedPayments.map((fp) => (
                <div
                  key={fp.id}
                  className="flex items-center justify-between rounded-lg border border-red-100 bg-red-50 p-4"
                >
                  <div className="flex items-center gap-3">
                    <AlertTriangle className="h-5 w-5 text-red-500" />
                    <div>
                      <p className="text-sm font-medium text-gray-900">
                        {fp.first_name} {fp.last_name}
                      </p>
                      <p className="text-xs text-gray-500">
                        {fp.failure_reason} — Attempt #{fp.attempt_number}
                      </p>
                    </div>
                  </div>
                  <div className="text-right">
                    <p className="text-sm font-medium text-red-600">
                      {fmt(fp.amount_cents)}
                    </p>
                    <p className="text-xs text-gray-400">
                      {format(new Date(fp.created_at), "MMM d, h:mm a")}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </>
      )}

      {/* Communications */}
      {activeTab === "communications" && (
        <>
          {!communications?.length ? (
            <div className="rounded-lg border border-dashed border-gray-300 py-12 text-center">
              <p className="text-sm text-gray-500">No emails sent yet</p>
            </div>
          ) : (
            <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                      Date
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                      Recipient
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                      Subject
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                      Type
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                      Status
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200">
                  {communications.map((comm) => (
                    <tr key={comm.id} className="hover:bg-gray-50">
                      <td className="whitespace-nowrap px-4 py-3 text-sm text-gray-500">
                        {format(new Date(comm.created_at), "MMM d, h:mm a")}
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 text-sm text-gray-900">
                        {comm.recipient}
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-600">
                        {comm.subject || "—"}
                      </td>
                      <td className="whitespace-nowrap px-4 py-3">
                        <span className="flex items-center gap-1 text-xs text-gray-500">
                          <Mail className="h-3 w-3" />
                          {comm.type}
                        </span>
                      </td>
                      <td className="whitespace-nowrap px-4 py-3">
                        <span
                          className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                            comm.status === "sent"
                              ? "bg-green-50 text-green-700"
                              : comm.status === "skipped"
                                ? "bg-gray-100 text-gray-500"
                                : "bg-red-50 text-red-600"
                          }`}
                        >
                          {comm.status}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {showRecordPayment && (
        <RecordPaymentModal
          onClose={() => setShowRecordPayment(false)}
          onRecorded={() => {
            setShowRecordPayment(false);
          }}
        />
      )}
    </div>
  );
}
