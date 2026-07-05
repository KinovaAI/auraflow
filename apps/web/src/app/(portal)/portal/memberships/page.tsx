"use client";

import { useCallback, useEffect, useRef, useState, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import {
  CreditCard, Loader2, CheckCircle, XCircle, AlertCircle, Sparkles,
  ArrowRight, ExternalLink, Receipt, PauseCircle, PlayCircle, RefreshCw,
} from "lucide-react";
import toast from "react-hot-toast";

import { portalApi } from "@/lib/portal-api";
import type { PortalMembership, PortalMembershipType, PortalTransaction } from "@/lib/portal-api";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { SaveCardViaSquareModal } from "@/components/payments/save-card-square-modal";

interface SquareCard {
  attach: (selector: string) => Promise<void>;
  tokenize: () => Promise<{ status: string; token: string; errors?: { message: string }[] }>;
  destroy: () => void;
}
interface SquarePayments {
  payments: (appId: string, locationId: string) => { card: () => Promise<SquareCard> };
}

function extractApiError(err: unknown, fallback: string): string {
  const detail = (err as { response?: { data?: { detail?: unknown } } })
    ?.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object") {
    const d = detail as { error?: string; message?: string };
    return d.error || d.message || fallback;
  }
  return fallback;
}

function SwitchToSquareModal({
  membership,
  onClose,
  onSuccess,
}: {
  membership: PortalMembership;
  onClose: () => void;
  onSuccess: () => void;
}) {
  const [phase, setPhase] = useState<"loading_sdk" | "loading_card" | "ready" | "tokenizing" | "submitting" | "done" | "blocked">("loading_sdk");
  const [error, setError] = useState<string | null>(null);
  const [cardholderName, setCardholderName] = useState("");
  const [result, setResult] = useState<{
    stripe_last_charge_date: string;
    square_first_charge_date: string;
    message: string;
  } | null>(null);
  const cardRef = useRef<SquareCard | null>(null);
  const cardholderRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const cfg = await portalApi.getSquareConfig();
        const { application_id, location_id, environment } = cfg.data.data;
        if (!application_id || !location_id) {
          setError(
            "This studio hasn't connected to Square yet. Please ask the front desk to finish Square setup.",
          );
          setPhase("blocked");
          return;
        }
        if (!(window as unknown as { Square?: SquarePayments }).Square) {
          const script = document.createElement("script");
          script.src = environment === "production"
            ? "https://web.squarecdn.com/v1/square.js"
            : "https://sandbox.web.squarecdn.com/v1/square.js";
          script.async = true;
          await new Promise<void>((resolve, reject) => {
            script.onload = () => resolve();
            script.onerror = () => reject(new Error("Could not load Square — check your internet connection."));
            document.head.appendChild(script);
          });
        }
        if (cancelled) return;
        setPhase("loading_card");
        const sq = (window as unknown as { Square?: SquarePayments }).Square;
        if (!sq) throw new Error("Square SDK not loaded");
        const payments = sq.payments(application_id, location_id);
        const card = await payments.card();
        await card.attach("#switch-to-square-card");
        if (cancelled) {
          try { card.destroy(); } catch { /* noop */ }
          return;
        }
        cardRef.current = card;
        setPhase("ready");
      } catch (err: unknown) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Could not initialize Square");
          setPhase("blocked");
        }
      }
    })();
    return () => {
      cancelled = true;
      if (cardRef.current) {
        try { cardRef.current.destroy(); } catch { /* noop */ }
      }
    };
  }, []);

  // Initial focus on cardholder input once card is ready (a11y).
  useEffect(() => {
    if (phase === "ready" && cardholderRef.current) {
      cardholderRef.current.focus();
    }
  }, [phase]);

  // Escape key closes when safe (a11y).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && phase !== "tokenizing" && phase !== "submitting") {
        onClose();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [phase, onClose]);

  const handleSubmit = useCallback(async () => {
    if (!cardRef.current) return;
    setPhase("tokenizing");
    setError(null);
    let tokenized: { status: string; token: string; errors?: { message: string }[] };
    try {
      tokenized = await cardRef.current.tokenize();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Card tokenization failed");
      setPhase("ready");
      return;
    }
    if (tokenized.status !== "OK") {
      setError(tokenized.errors?.[0]?.message || "Card details invalid");
      setPhase("ready");
      return;
    }
    setPhase("submitting");
    try {
      const res = await portalApi.switchMembershipToSquare({
        membership_id: membership.id,
        source_id: tokenized.token,
        cardholder_name: cardholderName.trim() || undefined,
      });
      setResult(res.data.data);
      setPhase("done");
      toast.success("Switched to Square — no interruption.");
    } catch (err: unknown) {
      setError(extractApiError(err, "Switch failed. Please try again."));
      setPhase("ready");
    }
  }, [membership.id, cardholderName]);

  const isWorking = phase === "tokenizing" || phase === "submitting";
  const loadingMessage =
    phase === "loading_sdk" ? "Loading Square…" :
    phase === "loading_card" ? "Setting up card field…" :
    phase === "tokenizing" ? "Securing your card…" :
    phase === "submitting" ? "Scheduling your switch…" : null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-2 sm:p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="switch-to-square-title"
    >
      <div className="max-h-[95vh] w-full max-w-md overflow-y-auto rounded-lg bg-white p-4 shadow-xl sm:p-6">
        {phase === "done" && result ? (
          <>
            <div className="mb-3 flex items-center gap-2 text-green-700">
              <CheckCircle className="h-5 w-5" aria-hidden="true" />
              <h3 id="switch-to-square-title" className="text-lg font-semibold">You&apos;re all set</h3>
            </div>
            <p className="text-sm text-gray-700">{result.message}</p>
            <div className="mt-5 flex justify-end">
              <Button onClick={onSuccess} autoFocus>Done</Button>
            </div>
          </>
        ) : (
          <>
            <h3 id="switch-to-square-title" className="text-lg font-semibold text-gray-900">
              Switch billing to Square
            </h3>
            <p className="mt-2 text-sm text-gray-600">
              Enter the card you&apos;d like to use going forward. Your current
              billing cycle finishes on its existing schedule and your next
              charge runs through Square — <span className="font-medium">no gap, no double charge.</span>
            </p>

            <div className="mt-5 space-y-3">
              <label className="block text-xs font-medium text-gray-500" htmlFor="switch-to-square-cardholder">
                Cardholder name <span className="text-gray-400">(optional)</span>
              </label>
              <input
                id="switch-to-square-cardholder"
                ref={cardholderRef}
                type="text"
                value={cardholderName}
                onChange={(e) => setCardholderName(e.target.value)}
                placeholder="Name on card"
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 disabled:opacity-50"
                disabled={phase !== "ready"}
                autoComplete="cc-name"
              />
              <div
                id="switch-to-square-card"
                aria-label="Card number, expiration, and CVV"
                className="min-h-[56px] rounded-md border border-gray-300 px-3 py-2"
              />
              {loadingMessage && (
                <div className="flex items-center gap-2 text-sm text-gray-500" role="status" aria-live="polite">
                  <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                  {loadingMessage}
                </div>
              )}
            </div>

            {error && (
              <div className="mt-3 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
                {error}
              </div>
            )}

            <div className="mt-6 flex justify-end gap-3">
              <Button variant="outline" onClick={onClose} disabled={isWorking}>
                Cancel
              </Button>
              <Button
                onClick={handleSubmit}
                disabled={phase !== "ready"}
              >
                {isWorking && <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" />}
                Save card &amp; switch
              </Button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

// ── Purchase a NEW membership via Square (Web Payments SDK + purchase-square)
// Mirrors SwitchToSquareModal but POSTs purchaseMembershipSquare.
function PurchaseViaSquareModal({
  membershipTypeId,
  onClose,
  onSuccess,
}: {
  membershipTypeId: string;
  onClose: () => void;
  onSuccess: () => void;
}) {
  const [phase, setPhase] = useState<"loading_sdk" | "loading_card" | "ready" | "tokenizing" | "submitting" | "done" | "blocked">("loading_sdk");
  const [error, setError] = useState<string | null>(null);
  const [cardholderName, setCardholderName] = useState("");
  const cardRef = useRef<SquareCard | null>(null);
  const cardholderRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const cfg = await portalApi.getSquareConfig();
        const { application_id, location_id, environment } = cfg.data.data;
        if (!application_id || !location_id) {
          setError("This studio hasn't connected to Square yet. Please ask the front desk to finish Square setup.");
          setPhase("blocked");
          return;
        }
        if (!(window as unknown as { Square?: SquarePayments }).Square) {
          const script = document.createElement("script");
          script.src = environment === "production"
            ? "https://web.squarecdn.com/v1/square.js"
            : "https://sandbox.web.squarecdn.com/v1/square.js";
          script.async = true;
          await new Promise<void>((resolve, reject) => {
            script.onload = () => resolve();
            script.onerror = () => reject(new Error("Could not load Square — check your internet connection."));
            document.head.appendChild(script);
          });
        }
        if (cancelled) return;
        setPhase("loading_card");
        const sq = (window as unknown as { Square?: SquarePayments }).Square;
        if (!sq) throw new Error("Square SDK not loaded");
        const payments = sq.payments(application_id, location_id);
        const card = await payments.card();
        await card.attach("#purchase-square-card");
        if (cancelled) { try { card.destroy(); } catch { /* noop */ } return; }
        cardRef.current = card;
        setPhase("ready");
      } catch (err: unknown) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Could not initialize Square");
          setPhase("blocked");
        }
      }
    })();
    return () => {
      cancelled = true;
      if (cardRef.current) { try { cardRef.current.destroy(); } catch { /* noop */ } }
    };
  }, []);

  useEffect(() => {
    if (phase === "ready" && cardholderRef.current) cardholderRef.current.focus();
  }, [phase]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && phase !== "tokenizing" && phase !== "submitting") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [phase, onClose]);

  const handleSubmit = useCallback(async () => {
    if (!cardRef.current) return;
    setPhase("tokenizing");
    setError(null);
    let tokenized: { status: string; token: string; errors?: { message: string }[] };
    try {
      tokenized = await cardRef.current.tokenize();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Card tokenization failed");
      setPhase("ready");
      return;
    }
    if (tokenized.status !== "OK") {
      setError(tokenized.errors?.[0]?.message || "Card details invalid");
      setPhase("ready");
      return;
    }
    setPhase("submitting");
    try {
      await portalApi.purchaseMembershipSquare({
        membership_type_id: membershipTypeId,
        source_id: tokenized.token,
        cardholder_name: cardholderName.trim() || undefined,
      });
      setPhase("done");
      toast.success("Membership purchased!");
    } catch (err: unknown) {
      setError(extractApiError(err, "Purchase failed. Please try again."));
      setPhase("ready");
    }
  }, [membershipTypeId, cardholderName]);

  const isWorking = phase === "tokenizing" || phase === "submitting";
  const loadingMessage =
    phase === "loading_sdk" ? "Loading Square…" :
    phase === "loading_card" ? "Setting up card field…" :
    phase === "tokenizing" ? "Securing your card…" :
    phase === "submitting" ? "Processing purchase…" : null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-2 sm:p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="purchase-square-title"
    >
      <div className="max-h-[95vh] w-full max-w-md overflow-y-auto rounded-lg bg-white p-4 shadow-xl sm:p-6">
        {phase === "done" ? (
          <>
            <div className="mb-3 flex items-center gap-2 text-green-700">
              <CheckCircle className="h-5 w-5" aria-hidden="true" />
              <h3 id="purchase-square-title" className="text-lg font-semibold">You&apos;re enrolled!</h3>
            </div>
            <p className="text-sm text-gray-700">Your membership is active. See you in class!</p>
            <div className="mt-5 flex justify-end">
              <Button onClick={onSuccess} autoFocus>Done</Button>
            </div>
          </>
        ) : (
          <>
            <h3 id="purchase-square-title" className="text-lg font-semibold text-gray-900">Complete your purchase</h3>
            <p className="mt-2 text-sm text-gray-600">Enter your card. We&apos;ll save it on file for your future renewals.</p>
            <div className="mt-5 space-y-3">
              <label className="block text-xs font-medium text-gray-500" htmlFor="purchase-square-cardholder">
                Cardholder name <span className="text-gray-400">(optional)</span>
              </label>
              <input
                id="purchase-square-cardholder"
                ref={cardholderRef}
                type="text"
                value={cardholderName}
                onChange={(e) => setCardholderName(e.target.value)}
                placeholder="Name on card"
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 disabled:opacity-50"
                disabled={phase !== "ready"}
                autoComplete="cc-name"
              />
              <div id="purchase-square-card" aria-label="Card number, expiration, and CVV"
                className="min-h-[56px] rounded-md border border-gray-300 px-3 py-2" />
              {loadingMessage && (
                <div className="flex items-center gap-2 text-sm text-gray-500" role="status" aria-live="polite">
                  <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                  {loadingMessage}
                </div>
              )}
            </div>
            {error && (
              <div className="mt-3 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">{error}</div>
            )}
            <div className="mt-6 flex justify-end gap-3">
              <Button variant="outline" onClick={onClose} disabled={isWorking}>Cancel</Button>
              <Button onClick={handleSubmit} disabled={phase !== "ready"}>
                {isWorking && <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" />}
                Pay &amp; enroll
              </Button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

const statusConfig: Record<string, { icon: typeof CheckCircle; style: string; label: string }> = {
  active: { icon: CheckCircle, style: "text-green-600 bg-green-50", label: "Active" },
  frozen: { icon: AlertCircle, style: "text-amber-600 bg-amber-50", label: "Frozen" },
  cancelled: { icon: XCircle, style: "text-gray-500 bg-gray-100", label: "Cancelled" },
  expired: { icon: XCircle, style: "text-red-600 bg-red-50", label: "Expired" },
};

const txStatusStyle: Record<string, string> = {
  completed: "text-green-600",
  pending: "text-amber-600",
  failed: "text-red-600",
  refunded: "text-gray-500",
};

function formatPrice(cents: number, period?: string) {
  const amount = `$${(cents / 100).toFixed(2)}`;
  if (!period || period === "one_time") return amount;
  const periodMap: Record<string, string> = {
    monthly: "/mo",
    annual: "/yr",
    yearly: "/yr",
    weekly: "/wk",
  };
  return `${amount}${periodMap[period] || `/${period}`}`;
}

function formatDate(isoStr: string) {
  return new Date(isoStr).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function typeLabel(type: string) {
  const labels: Record<string, string> = {
    unlimited: "Unlimited",
    class_pack: "Class Pack",
    intro_offer: "Intro Offer",
    day_pass: "Day Pass",
    single_class: "Single Class",
  };
  return labels[type] || type;
}

function ConfirmDialog({
  title,
  message,
  confirmLabel,
  onConfirm,
  onCancel,
  isPending,
}: {
  title: string;
  message: string;
  confirmLabel: string;
  onConfirm: () => void;
  onCancel: () => void;
  isPending: boolean;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-full max-w-sm rounded-lg bg-white p-6 shadow-xl">
        <h3 className="text-lg font-semibold text-gray-900">{title}</h3>
        <p className="mt-2 text-sm text-gray-600">{message}</p>
        <div className="mt-6 flex justify-end gap-3">
          <Button variant="outline" onClick={onCancel} disabled={isPending}>
            Go Back
          </Button>
          <Button onClick={onConfirm} disabled={isPending}>
            {isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}

function MembershipsContent() {
  const searchParams = useSearchParams();
  const [memberships, setMemberships] = useState<PortalMembership[]>([]);
  const [availableTypes, setAvailableTypes] = useState<PortalMembershipType[]>([]);
  const [transactions, setTransactions] = useState<PortalTransaction[]>([]);
  const [loading, setLoading] = useState(true);
  const [purchasingId, setPurchasingId] = useState<string | null>(null);
  const [billingLoading, setBillingLoading] = useState(false);
  const [showSaveCardModal, setShowSaveCardModal] = useState(false);
  const [confirmAction, setConfirmAction] = useState<{
    type: "pause" | "resume" | "cancel";
    membership: PortalMembership;
  } | null>(null);
  const [actionPending, setActionPending] = useState(false);
  const [switchTarget, setSwitchTarget] = useState<PortalMembership | null>(null);
  const [squareConnected, setSquareConnected] = useState<boolean>(false);

  useEffect(() => {
    if (searchParams.get("success") === "1") {
      toast.success("Payment successful! Your membership is being activated.");
    }
    if (searchParams.get("cancelled") === "1") {
      toast("Payment was cancelled.", { icon: "ℹ️" });
    }
  }, [searchParams]);

  const loadData = async () => {
    try {
      const [membershipsRes, typesRes, txRes, sqRes] = await Promise.all([
        portalApi.getMemberships(),
        portalApi.getAvailableMembershipTypes(),
        portalApi.getTransactions({ limit: 20 }),
        portalApi.getSquareConfig().catch(() => null),
      ]);
      setMemberships(membershipsRes.data);
      setAvailableTypes(typesRes.data);
      setTransactions(txRes.data);
      setSquareConnected(!!sqRes?.data?.data?.location_id);
    } catch {
      toast.error("Failed to load memberships");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleMembershipAction = async () => {
    if (!confirmAction) return;
    setActionPending(true);
    try {
      switch (confirmAction.type) {
        case "pause":
          await portalApi.pauseMembership(confirmAction.membership.id);
          toast.success("Membership paused");
          break;
        case "resume":
          await portalApi.resumeMembership(confirmAction.membership.id);
          toast.success("Membership resumed");
          break;
        case "cancel":
          await portalApi.cancelMembership(confirmAction.membership.id);
          toast.success("Membership cancelled");
          break;
      }
      setConfirmAction(null);
      loadData();
    } catch {
      toast.error(`Failed to ${confirmAction.type} membership`);
    } finally {
      setActionPending(false);
    }
  };

  const [squarePurchaseTypeId, setSquarePurchaseTypeId] = useState<string | null>(null);

  const handlePurchase = async (typeId: string) => {
    // Square-mode studios: open the Web Payments SDK modal to tokenize
    // a card and POST to /portal/memberships/purchase-square. The
    // legacy /portal/checkout endpoint refuses with WRONG_PROVIDER.
    if (squareConnected) {
      setSquarePurchaseTypeId(typeId);
      return;
    }
    setPurchasingId(typeId);
    try {
      const { data } = await portalApi.checkout({
        membership_type_id: typeId,
        success_url: `${window.location.origin}/portal/memberships?success=1`,
        cancel_url: `${window.location.origin}/portal/memberships?cancelled=1`,
      });
      window.location.href = data.data.url;
    } catch (err: unknown) {
      toast.error(extractApiError(err, "Failed to start checkout. Please try again."));
      setPurchasingId(null);
    }
  };

  const handleManageBilling = async () => {
    // Open the inline Square card-save modal — same pattern as the
    // membership-purchase Square modal already on this page. No
    // redirect, no new tab, no external URL. Don's standing rule:
    // members stay on the studio's website, never leave for payment.
    setShowSaveCardModal(true);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 className="h-6 w-6 animate-spin text-indigo-600" />
      </div>
    );
  }

  const activeMembershipTypeNames = new Set(
    memberships.filter((m) => m.status === "active").map((m) => m.type_name)
  );
  const purchasableTypes = availableTypes.filter(
    (t) => !activeMembershipTypeNames.has(t.name)
  );
  const hasActiveSubscription = memberships.some((m) => m.status === "active" && m.auto_renew);
  const stripeBilledCount = memberships.filter(
    (m) => m.status === "active" && m.stripe_subscription_id && !m.square_subscription_id
  ).length;

  return (
    <div>
      <h1 className="mb-6 text-2xl font-bold text-gray-900">Memberships</h1>

      {/* My Memberships */}
      <section className="mb-8">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-gray-800">My Memberships</h2>
          {hasActiveSubscription && (
            <Button
              variant="outline"
              size="sm"
              onClick={handleManageBilling}
              disabled={billingLoading}
            >
              {billingLoading ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <ExternalLink className="mr-2 h-4 w-4" />
              )}
              Manage Billing
            </Button>
          )}
        </div>
        {memberships.length === 0 ? (
          <Card>
            <CardContent className="py-8 text-center">
              <CreditCard className="mx-auto mb-2 h-8 w-8 text-gray-300" />
              <p className="text-gray-500">No active memberships</p>
              <p className="mt-1 text-sm text-gray-400">
                Browse the plans below to get started
              </p>
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-4">
            {memberships.map((membership) => {
              const config = statusConfig[membership.status] || statusConfig.expired;
              const StatusIcon = config.icon;
              return (
                <Card key={membership.id}>
                  <CardContent className="p-5">
                    <div className="flex items-start justify-between">
                      <div>
                        <h3 className="text-lg font-semibold text-gray-900">
                          {membership.type_name}
                        </h3>
                        <div className="mt-1 flex items-center gap-2">
                          <span
                            className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium ${config.style}`}
                          >
                            <StatusIcon className="h-3.5 w-3.5" />
                            {config.label}
                          </span>
                          {membership.membership_type && (
                            <span className="text-sm text-gray-400">
                              {typeLabel(membership.membership_type)}
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                    <div className="mt-3 grid grid-cols-2 gap-4 text-sm sm:grid-cols-3">
                      {membership.starts_at && (
                        <div>
                          <p className="text-gray-400">Started</p>
                          <p className="font-medium text-gray-700">
                            {formatDate(membership.starts_at)}
                          </p>
                        </div>
                      )}
                      {membership.ends_at && (
                        <div>
                          <p className="text-gray-400">
                            {membership.status === "active" ? "Renews" : "Ended"}
                          </p>
                          <p className="font-medium text-gray-700">
                            {formatDate(membership.ends_at)}
                          </p>
                        </div>
                      )}
                      {membership.classes_remaining != null && (
                        <div>
                          <p className="text-gray-400">Classes remaining</p>
                          <p className="text-xl font-bold text-indigo-600">
                            {membership.classes_remaining}
                          </p>
                        </div>
                      )}
                    </div>
                    {membership.status === "active" && (
                      <div className="mt-4 flex flex-wrap gap-2 border-t border-gray-100 pt-3">
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() =>
                            setConfirmAction({ type: "pause", membership })
                          }
                        >
                          <PauseCircle className="mr-1.5 h-4 w-4" />
                          Pause
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() =>
                            setConfirmAction({ type: "cancel", membership })
                          }
                        >
                          <XCircle className="mr-1.5 h-4 w-4 text-red-500" />
                          Cancel
                        </Button>
                        {squareConnected && membership.stripe_subscription_id && !membership.square_subscription_id && (
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => setSwitchTarget(membership)}
                            title={
                              stripeBilledCount > 1
                                ? "Switches only this membership. Your other Stripe membership(s) remain unchanged until you switch each separately."
                                : "Add a new card to Square. Your existing billing cycle isn't interrupted — the switch happens at your next renewal."
                            }
                          >
                            <RefreshCw className="mr-1.5 h-4 w-4 text-indigo-600" />
                            Switch to Square
                          </Button>
                        )}
                        {membership.square_subscription_id && membership.stripe_subscription_id && (
                          <span className="inline-flex items-center gap-1 self-center rounded-full bg-indigo-50 px-2.5 py-0.5 text-xs font-medium text-indigo-700">
                            <RefreshCw className="h-3 w-3" />
                            {membership.current_period_end
                              ? `Switching to Square on ${formatDate(membership.current_period_end)}`
                              : "Switching to Square at next renewal"}
                          </span>
                        )}
                      </div>
                    )}
                    {membership.status === "frozen" && (
                      <div className="mt-4 flex gap-2 border-t border-gray-100 pt-3">
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() =>
                            setConfirmAction({ type: "resume", membership })
                          }
                        >
                          <PlayCircle className="mr-1.5 h-4 w-4 text-green-600" />
                          Resume
                        </Button>
                      </div>
                    )}
                  </CardContent>
                </Card>
              );
            })}
          </div>
        )}
      </section>

      {/* Available Plans */}
      {purchasableTypes.length > 0 && (
        <section className="mb-8">
          <h2 className="mb-3 text-lg font-semibold text-gray-800">Available Plans</h2>
          <div className="grid gap-4 sm:grid-cols-2">
            {purchasableTypes.map((plan) => (
              <Card key={plan.id} className="transition-shadow hover:shadow-md">
                <CardContent className="p-5">
                  <div className="mb-3 flex items-start justify-between">
                    <div>
                      <h3 className="text-lg font-semibold text-gray-900">{plan.name}</h3>
                      <span className="text-sm text-gray-400">{typeLabel(plan.type)}</span>
                    </div>
                    {plan.is_founding_rate && (
                      <span className="flex items-center gap-1 rounded-full bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-700">
                        <Sparkles className="h-3 w-3" />
                        Founding Rate
                      </span>
                    )}
                  </div>

                  {plan.description && (
                    <p className="mb-3 text-sm text-gray-500">{plan.description}</p>
                  )}

                  <div className="mb-4 flex items-baseline gap-1">
                    <span className="text-2xl font-bold text-gray-900">
                      {formatPrice(plan.price_cents, plan.billing_period)}
                    </span>
                  </div>

                  <ul className="mb-4 space-y-1 text-sm text-gray-600">
                    {plan.type === "class_pack" && plan.class_count && (
                      <li>
                        {plan.class_count} classes included
                      </li>
                    )}
                    {plan.type === "unlimited" && <li>Unlimited classes</li>}
                    {plan.trial_days > 0 && (
                      <li>{plan.trial_days}-day free trial</li>
                    )}
                    {plan.freeze_allowed && <li>Freeze available</li>}
                    {plan.duration_days && (
                      <li>Valid for {plan.duration_days} days</li>
                    )}
                  </ul>

                  <Button
                    className="w-full"
                    onClick={() => handlePurchase(plan.id)}
                    disabled={purchasingId === plan.id}
                  >
                    {purchasingId === plan.id ? (
                      <>
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                        Redirecting...
                      </>
                    ) : (
                      <>
                        Get Started
                        <ArrowRight className="ml-2 h-4 w-4" />
                      </>
                    )}
                  </Button>
                </CardContent>
              </Card>
            ))}
          </div>
        </section>
      )}

      {/* Payment History */}
      {transactions.length > 0 && (
        <section>
          <h2 className="mb-3 text-lg font-semibold text-gray-800">Payment History</h2>
          <Card>
            <CardContent className="p-0">
              <div className="divide-y">
                {transactions.map((tx) => (
                  <div key={tx.id} className="flex items-center justify-between px-5 py-3">
                    <div className="flex items-center gap-3">
                      <Receipt className="h-4 w-4 text-gray-400" />
                      <div>
                        <p className="text-sm font-medium text-gray-900">
                          {tx.description || tx.type}
                        </p>
                        {tx.created_at && (
                          <p className="text-xs text-gray-400">{formatDate(tx.created_at)}</p>
                        )}
                      </div>
                    </div>
                    <div className="text-right">
                      <p className="text-sm font-semibold text-gray-900">
                        ${(tx.amount_cents / 100).toFixed(2)}
                      </p>
                      <p className={`text-xs capitalize ${txStatusStyle[tx.status] || "text-gray-500"}`}>
                        {tx.status}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </section>
      )}

      {switchTarget && (
        <SwitchToSquareModal
          membership={switchTarget}
          onClose={() => setSwitchTarget(null)}
          onSuccess={() => {
            setSwitchTarget(null);
            loadData();
          }}
        />
      )}

      {squarePurchaseTypeId && (
        <PurchaseViaSquareModal
          membershipTypeId={squarePurchaseTypeId}
          onClose={() => { setSquarePurchaseTypeId(null); setPurchasingId(null); }}
          onSuccess={() => {
            setSquarePurchaseTypeId(null);
            setPurchasingId(null);
            loadData();
          }}
        />
      )}

      {showSaveCardModal && (
        <SaveCardViaSquareModal
          onClose={() => setShowSaveCardModal(false)}
          onSuccess={() => {
            setShowSaveCardModal(false);
            loadData();
          }}
        />
      )}

      {confirmAction && (
        <ConfirmDialog
          title={
            confirmAction.type === "pause"
              ? "Pause Membership"
              : confirmAction.type === "resume"
                ? "Resume Membership"
                : "Cancel Membership"
          }
          message={
            confirmAction.type === "pause"
              ? `Are you sure you want to pause "${confirmAction.membership.type_name}"? You can resume it anytime.`
              : confirmAction.type === "resume"
                ? `Resume "${confirmAction.membership.type_name}"? Billing will restart.`
                : `Are you sure you want to cancel "${confirmAction.membership.type_name}"? This cannot be undone.`
          }
          confirmLabel={
            confirmAction.type === "pause"
              ? "Pause"
              : confirmAction.type === "resume"
                ? "Resume"
                : "Cancel Membership"
          }
          onConfirm={handleMembershipAction}
          onCancel={() => setConfirmAction(null)}
          isPending={actionPending}
        />
      )}
    </div>
  );
}

export default function PortalMembershipsPage() {
  return (
    <Suspense
      fallback={
        <div className="flex items-center justify-center py-16">
          <Loader2 className="h-6 w-6 animate-spin text-indigo-600" />
        </div>
      }
    >
      <MembershipsContent />
    </Suspense>
  );
}
