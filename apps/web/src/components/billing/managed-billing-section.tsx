"use client";

/**
 * AuraFlow — Managed Billing Section (open-core / self-host).
 *
 * Shown only when the instance runs AURAFLOW_BILLING_MODE=managed. Lets the
 * operator connect their Square account through the AuraFlow managed billing
 * broker (a 1% platform fee applies, handled server-side). The broker API key
 * never reaches the browser — this talks to the local /managed-billing proxy.
 */
import { useEffect, useState } from "react";
import { CheckCircle2, ExternalLink, Loader2, AlertTriangle } from "lucide-react";
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

interface ManagedStatus {
  enabled: boolean;
  mode?: string;
  status?: string;
  square_connected?: boolean;
  square_merchant_id?: string | null;
  client_id?: string;
  name?: string;
}

export function ManagedBillingSection() {
  const [status, setStatus] = useState<ManagedStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [connecting, setConnecting] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const r = await apiClient.get<{ data: ManagedStatus }>("/managed-billing/status");
      setStatus(r.data?.data ?? null);
    } catch {
      setStatus({ enabled: false });
    }
    setLoading(false);
  };

  useEffect(() => {
    load();
  }, []);

  // OAuth callback feedback — the broker redirects back here with these params.
  useEffect(() => {
    if (typeof window === "undefined") return;
    const params = new URLSearchParams(window.location.search);
    if (params.get("square_connected") === "true") {
      toast.success("Square connected — managed billing is active.");
      load();
      const url = new URL(window.location.href);
      url.searchParams.delete("square_connected");
      url.searchParams.delete("merchant_id");
      window.history.replaceState({}, "", url.toString());
    } else if (params.get("square_error")) {
      toast.error(`Connection failed: ${params.get("square_error")}`);
      const url = new URL(window.location.href);
      url.searchParams.delete("square_error");
      window.history.replaceState({}, "", url.toString());
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const connect = async () => {
    setConnecting(true);
    try {
      const returnUrl = window.location.origin + window.location.pathname;
      const r = await apiClient.get<{ data?: { authorize_url?: string } }>(
        `/managed-billing/connect?return_url=${encodeURIComponent(returnUrl)}`,
      );
      const url = r.data?.data?.authorize_url;
      if (!url) {
        toast.error("No authorize URL returned");
        setConnecting(false);
        return;
      }
      window.location.href = url;
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: { error?: string } } } })
        ?.response?.data?.detail?.error;
      toast.error(detail || "Failed to start managed billing connect");
      setConnecting(false);
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

  // Not running in managed mode — render nothing.
  if (!status?.enabled) return null;

  const connected = !!status.square_connected;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <span>Managed Billing</span>
          {connected ? (
            <span className="rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-700">
              Connected
            </span>
          ) : (
            <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-700">
              Setup needed
            </span>
          )}
        </CardTitle>
        <CardDescription>
          Payments run through AuraFlow managed billing on your own Square
          account. A 1% platform fee applies to each charge.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {connected ? (
          <div className="rounded-md border border-green-200 bg-green-50 p-3 text-sm text-green-900">
            <div className="flex items-start gap-2">
              <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />
              <div>
                <div className="font-medium">Square connected via managed billing</div>
                {status.square_merchant_id && (
                  <div className="mt-1 text-xs">
                    Merchant ID:{" "}
                    <code className="rounded bg-white/60 px-1">
                      {status.square_merchant_id}
                    </code>
                  </div>
                )}
              </div>
            </div>
          </div>
        ) : (
          <>
            <div className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
              <div className="flex items-start gap-2">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                <div>
                  Connect your Square account to start taking member payments
                  through managed billing. You&apos;ll be sent to Square to
                  authorize, then returned here.
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
  );
}
