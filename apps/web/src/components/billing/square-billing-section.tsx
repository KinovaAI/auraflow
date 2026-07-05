"use client";

/**
 * AuraFlow — Square Billing Section
 *
 * Drop-in card for /dashboard/settings/billing. Shows the studio's
 * current billing_provider, the Square connect/disconnect controls,
 * and (if connected) the last 12 platform invoices from KinovaAI.
 *
 * Wire-up:
 *   <SquareBillingSection orgId={user.active_org_id} />
 *
 * The component does its own fetches — no props except orgId. Keeps
 * the change to the existing billing page small (one import + one
 * component placement).
 */
import { useEffect, useState } from "react";
import {
  CheckCircle2,
  XCircle,
  ExternalLink,
  Loader2,
  Receipt,
  AlertTriangle,
} from "lucide-react";
import toast from "react-hot-toast";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { apiClient } from "@/lib/api-client";

interface SquareStatus {
  connected: boolean;
  merchant_id?: string;
  location_id?: string;
  token_expires_at?: string | null;
  billing_provider?: "stripe" | "square";
}

interface PlatformInvoice {
  id: string;
  square_invoice_id: string | null;
  period_start: string;
  period_end: string;
  plan_fee_cents: number;
  token_overage_cents: number;
  token_count: number;
  total_cents: number;
  status: "pending" | "sent" | "paid" | "failed" | "canceled" | "refunded";
  created_at: string;
  paid_at: string | null;
}

function fmt(cents: number): string {
  return `$${(cents / 100).toFixed(2)}`;
}

export function SquareBillingSection() {
  const [status, setStatus] = useState<SquareStatus | null>(null);
  const [invoices, setInvoices] = useState<PlatformInvoice[]>([]);
  const [loading, setLoading] = useState(true);
  const [connecting, setConnecting] = useState(false);
  const [disconnecting, setDisconnecting] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const statusResp = await apiClient.get<{ data: SquareStatus }>(
        "/payments/square/connect/status",
      );
      setStatus(statusResp.data?.data ?? statusResp.data);
    } catch {
      // No Square at all yet is fine — show the connect CTA.
      setStatus({ connected: false });
    }

    // Fetch invoice history. Endpoint shipped in Phase 11 wire-up.
    try {
      const invResp = await apiClient.get<{ data: PlatformInvoice[] }>(
        "/payments/square/platform/invoices",
      );
      setInvoices(invResp.data?.data ?? []);
    } catch {
      setInvoices([]);
    }

    setLoading(false);
  };

  useEffect(() => {
    load();
  }, []);

  // Read query params for OAuth callback feedback.
  useEffect(() => {
    if (typeof window === "undefined") return;
    const params = new URLSearchParams(window.location.search);
    if (params.get("square_connected") === "true") {
      toast.success("Square account connected!");
      load();
      // Clear the query
      const url = new URL(window.location.href);
      url.searchParams.delete("square_connected");
      url.searchParams.delete("merchant_id");
      window.history.replaceState({}, "", url.toString());
    } else if (params.get("square_error")) {
      toast.error(`Square connection failed: ${params.get("square_error")}`);
      const url = new URL(window.location.href);
      url.searchParams.delete("square_error");
      window.history.replaceState({}, "", url.toString());
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const connect = async () => {
    setConnecting(true);
    try {
      const resp = await apiClient.post<{ data?: { authorize_url?: string }; authorize_url?: string }>(
        "/payments/square/connect/start",
      );
      const url = resp.data?.data?.authorize_url ?? resp.data?.authorize_url;
      if (!url) {
        toast.error("No authorize URL returned");
        setConnecting(false);
        return;
      }
      window.location.href = url;
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: unknown } } })?.response
        ?.data?.detail;
      toast.error(typeof detail === "string" ? detail : "Failed to start Square connect");
      setConnecting(false);
    }
  };

  const disconnect = async () => {
    if (
      !window.confirm(
        "Disconnect Square?\n\nThis reverts your studio to Stripe for any new payments. " +
          "Existing Square subscriptions for members will be cancelled at their next " +
          "billing cycle. Your existing Stripe Connect setup stays intact.",
      )
    ) {
      return;
    }
    setDisconnecting(true);
    try {
      await apiClient.post("/payments/square/connect/disconnect");
      toast.success("Square disconnected");
      load();
    } catch {
      toast.error("Disconnect failed");
    } finally {
      setDisconnecting(false);
    }
  };

  if (loading) {
    return (
      <Card>
        <CardContent className="flex items-center justify-center py-12">
          <Loader2 className="h-5 w-5 animate-spin text-gray-400" />
        </CardContent>
      </Card>
    );
  }

  const isSquare = status?.billing_provider === "square" || status?.connected;

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <span>Payment Processing</span>
            {isSquare ? (
              <span className="rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-700">
                Square
              </span>
            ) : (
              <span className="rounded-full bg-blue-100 px-2 py-0.5 text-xs font-medium text-blue-700">
                Stripe (legacy)
              </span>
            )}
          </CardTitle>
          <CardDescription>
            {isSquare
              ? "Member payments route through your Square merchant account."
              : "Your studio is currently using Stripe."}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {isSquare ? (
            <>
              <div className="rounded-md border border-green-200 bg-green-50 p-3 text-sm">
                <div className="flex items-start gap-2 text-green-900">
                  <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />
                  <div>
                    <div className="font-medium">Square connected</div>
                    {status?.merchant_id && (
                      <div className="mt-1 text-xs">
                        Merchant ID:{" "}
                        <code className="rounded bg-white/60 px-1">
                          {status.merchant_id}
                        </code>
                      </div>
                    )}
                    {status?.location_id && (
                      <div className="text-xs">
                        Location ID:{" "}
                        <code className="rounded bg-white/60 px-1">
                          {status.location_id}
                        </code>
                      </div>
                    )}
                    {status?.token_expires_at && (
                      <div className="text-xs">
                        Token refreshes automatically (next:{" "}
                        {new Date(status.token_expires_at).toLocaleDateString()})
                      </div>
                    )}
                  </div>
                </div>
              </div>
              <Button
                variant="outline"
                onClick={disconnect}
                disabled={disconnecting}
              >
                {disconnecting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                <XCircle className="mr-2 h-4 w-4" />
                Disconnect Square
              </Button>
            </>
          ) : (
            <>
              <div className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
                <div className="flex items-start gap-2">
                  <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                  <div>
                    <div className="font-medium">Heads up before you switch</div>
                    <div className="mt-1 text-xs">
                      Your existing Stripe-tied member memberships keep running on
                      Stripe until they naturally cancel or renew. Only NEW
                      member memberships and one-off payments will use Square.
                    </div>
                  </div>
                </div>
              </div>
              <Button
                onClick={connect}
                disabled={connecting}
                className="bg-indigo-600 hover:bg-indigo-700"
              >
                {connecting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                <ExternalLink className="mr-2 h-4 w-4" />
                Connect Square
              </Button>
            </>
          )}
        </CardContent>
      </Card>

      {isSquare && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Receipt className="h-5 w-5 text-indigo-600" />
              Monthly Platform Invoices
            </CardTitle>
            <CardDescription>
              Your $99 platform fee plus any AI token overage, billed by KinovaAI
              on the 1st of each month.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {invoices.length === 0 ? (
              <p className="text-sm text-gray-500">No invoices yet.</p>
            ) : (
              <div className="divide-y">
                {invoices.map((inv) => (
                  <div
                    key={inv.id}
                    className="flex items-center justify-between py-3"
                  >
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-gray-900">
                          {new Date(inv.period_start).toLocaleDateString("en-US", {
                            month: "long",
                            year: "numeric",
                          })}
                        </span>
                        <span
                          className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                            inv.status === "paid"
                              ? "bg-green-100 text-green-700"
                              : inv.status === "failed"
                              ? "bg-red-100 text-red-700"
                              : "bg-gray-100 text-gray-600"
                          }`}
                        >
                          {inv.status}
                        </span>
                      </div>
                      <div className="mt-1 text-xs text-gray-500">
                        Plan {fmt(inv.plan_fee_cents)}
                        {inv.token_overage_cents > 0 && (
                          <>
                            {" "}+ AI Tokens {fmt(inv.token_overage_cents)} (
                            {inv.token_count.toLocaleString()} tokens)
                          </>
                        )}
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="font-semibold text-gray-900">
                        {fmt(inv.total_cents)}
                      </div>
                      {inv.paid_at && (
                        <div className="text-xs text-gray-500">
                          Paid {new Date(inv.paid_at).toLocaleDateString()}
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
