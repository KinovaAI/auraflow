"use client";

import { useCallback, useEffect, useState } from "react";
import { Loader2, CreditCard, DollarSign, Smartphone, Gift } from "lucide-react";
import { Button } from "@/components/ui/button";
import { paymentsApi } from "@/lib/payments-api";

type PaymentMethod = "card" | "cash" | "square" | "comp";

interface SquareCard {
  attach: (selector: string) => Promise<void>;
  tokenize: () => Promise<{ status: string; token: string; errors?: { message: string }[] }>;
  destroy: () => void;
}

interface SquarePayments {
  payments: (appId: string, locationId: string) => { card: () => Promise<SquareCard> };
}

declare const __square_window: Window & { Square?: SquarePayments };

interface CollectPaymentProps {
  amountCents: number;
  memberId: string;
  description: string;
  onSuccess: (result: {
    payment_method: PaymentMethod;
    payment_intent_id?: string;
  }) => void;
  onCancel: () => void;
}

const TABS: { id: PaymentMethod; label: string; icon: React.ReactNode }[] = [
  { id: "card", label: "Card on File", icon: <CreditCard className="h-4 w-4" /> },
  { id: "cash", label: "Cash", icon: <DollarSign className="h-4 w-4" /> },
  { id: "square", label: "Square", icon: <Smartphone className="h-4 w-4" /> },
  { id: "comp", label: "Comp", icon: <Gift className="h-4 w-4" /> },
];

export function CollectPayment({
  amountCents,
  memberId,
  description,
  onSuccess,
  onCancel,
}: CollectPaymentProps) {
  // Default tab is card; cash is selectable but never pre-selected.
  const [tab, setTab] = useState<PaymentMethod>("card");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Square state
  const [squareLoading, setSquareLoading] = useState(false);
  const [squareReady, setSquareReady] = useState(false);
  const [squareCard, setSquareCard] = useState<SquareCard | null>(null);

  const amountFormatted = `$${(amountCents / 100).toFixed(2)}`;

  // Initialize Square when Square tab is selected
  useEffect(() => {
    if (tab !== "square") return;
    const appId = process.env.NEXT_PUBLIC_SQUARE_APPLICATION_ID;
    const locationId = process.env.NEXT_PUBLIC_SQUARE_LOCATION_ID;
    if (!appId || !locationId) {
      setError("Square is not configured");
      return;
    }

    let cancelled = false;

    const initSquare = async () => {
      try {
        if (!(window as unknown as { Square?: SquarePayments }).Square) {
          const script = document.createElement("script");
          script.src = process.env.NEXT_PUBLIC_SQUARE_ENVIRONMENT === "production"
            ? "https://web.squarecdn.com/v1/square.js"
            : "https://sandbox.web.squarecdn.com/v1/square.js";
          script.async = true;
          await new Promise<void>((resolve, reject) => {
            script.onload = () => resolve();
            script.onerror = () => reject(new Error("Failed to load Square SDK"));
            document.head.appendChild(script);
          });
        }

        if (cancelled) return;

        const squareGlobal = (window as unknown as { Square?: SquarePayments }).Square;
        if (!squareGlobal) throw new Error("Square SDK not loaded");
        const payments = squareGlobal.payments(appId, locationId);
        const card = await payments.card();
        await card.attach("#square-card-container");

        if (!cancelled) {
          setSquareCard(card);
          setSquareReady(true);
        }
      } catch (err: unknown) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to initialize Square");
        }
      }
    };

    initSquare();

    return () => {
      cancelled = true;
      if (squareCard) {
        try {
          squareCard.destroy();
        } catch {}
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab]);

  const handleCardPayment = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      // Create a payment intent and get the client secret
      const intentRes = await paymentsApi.createDropInIntent({
        member_id: memberId,
        amount_cents: amountCents,
        description,
      });
      const intentData = intentRes.data?.data || intentRes.data;
      const paymentIntentId = intentData.payment_intent_id;

      // For now, record the payment intent as the transaction
      // Full Stripe Elements card form requires additional setup
      await paymentsApi.recordDropInPayment({
        member_id: memberId,
        amount_cents: amountCents,
        payment_intent_id: paymentIntentId,
        description,
      });

      setLoading(false);
      onSuccess({ payment_method: "card", payment_intent_id: paymentIntentId });
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Card payment failed");
      setLoading(false);
    }
  }, [memberId, amountCents, description, onSuccess]);

  const handleCashPayment = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      await paymentsApi.recordTransaction({
        member_id: memberId,
        amount_cents: amountCents,
        type: "drop_in",
        description: `${description} (Cash)`,
      });
      setLoading(false);
      onSuccess({ payment_method: "cash" });
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to record payment");
      setLoading(false);
    }
  }, [memberId, amountCents, description, onSuccess]);

  const handleSquarePayment = useCallback(async () => {
    if (!squareCard) return;
    setSquareLoading(true);
    setError(null);

    try {
      const result = await squareCard.tokenize();
      if (result.status !== "OK") {
        throw new Error(result.errors?.[0]?.message || "Card tokenization failed");
      }

      const resp = await paymentsApi.squareCharge({
        member_id: memberId,
        amount_cents: amountCents,
        source_id: result.token,
        description,
      });

      setSquareLoading(false);
      const data = resp.data?.data || resp.data;
      onSuccess({
        payment_method: "square",
        payment_intent_id: (data as { square_payment?: { payment_id?: string } })?.square_payment?.payment_id,
      });
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Square payment failed");
      setSquareLoading(false);
    }
  }, [squareCard, memberId, amountCents, description, onSuccess]);

  const handleCompPayment = useCallback(() => {
    onSuccess({ payment_method: "comp" });
  }, [onSuccess]);

  return (
    <div className="space-y-4">
      {/* Amount display */}
      <div className="rounded-lg bg-gray-50 p-3 text-center">
        <p className="text-sm text-gray-500">Amount Due</p>
        <p className="text-2xl font-bold text-gray-900">{amountFormatted}</p>
      </div>

      {/* Payment method tabs */}
      <div className="flex gap-1 rounded-lg border border-gray-200 p-1">
        {TABS.map((t) => (
          <button
            key={t.id}
            className={`flex flex-1 items-center justify-center gap-1.5 rounded-md px-3 py-2 text-xs font-medium transition-colors ${
              tab === t.id
                ? "bg-indigo-100 text-indigo-700"
                : "text-gray-500 hover:text-gray-700"
            }`}
            onClick={() => {
              setTab(t.id);
              setError(null);
            }}
            disabled={loading || squareLoading}
          >
            {t.icon}
            {t.label}
          </button>
        ))}
      </div>

      {/* Error */}
      {error && (
        <div className="rounded-md bg-red-50 p-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {/* Card tab */}
      {tab === "card" && (
        <div className="space-y-3">
          <p className="text-sm text-gray-600">
            Charge <strong>{amountFormatted}</strong> to the client&apos;s card on file.
          </p>
          <div className="flex gap-2">
            <Button
              variant="outline"
              className="flex-1"
              onClick={onCancel}
              disabled={loading}
            >
              Cancel
            </Button>
            <Button
              className="flex-1"
              onClick={handleCardPayment}
              disabled={loading}
            >
              {loading ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <CreditCard className="mr-2 h-4 w-4" />
              )}
              Charge {amountFormatted}
            </Button>
          </div>
        </div>
      )}

      {/* Cash tab */}
      {tab === "cash" && (
        <div className="space-y-3">
          <p className="text-sm text-gray-600">
            Collect <strong>{amountFormatted}</strong> in cash from the client,
            then confirm below.
          </p>
          <div className="flex gap-2">
            <Button
              variant="outline"
              className="flex-1"
              onClick={onCancel}
              disabled={loading}
            >
              Cancel
            </Button>
            <Button
              className="flex-1"
              onClick={handleCashPayment}
              disabled={loading}
            >
              {loading ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : null}
              Record Cash Payment
            </Button>
          </div>
        </div>
      )}

      {/* Square tab */}
      {tab === "square" && (
        <div className="space-y-3">
          <div
            id="square-card-container"
            className="min-h-[80px] rounded-md border border-gray-200 p-2"
          />
          <div className="flex gap-2">
            <Button
              variant="outline"
              className="flex-1"
              onClick={onCancel}
              disabled={squareLoading}
            >
              Cancel
            </Button>
            <Button
              className="flex-1"
              onClick={handleSquarePayment}
              disabled={squareLoading || !squareReady}
            >
              {squareLoading ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : null}
              Pay {amountFormatted} (Square)
            </Button>
          </div>
        </div>
      )}

      {/* Comp tab */}
      {tab === "comp" && (
        <div className="space-y-3">
          <p className="text-sm text-gray-600">
            This will add the client to the class without any payment.
          </p>
          <div className="flex gap-2">
            <Button
              variant="outline"
              className="flex-1"
              onClick={onCancel}
            >
              Cancel
            </Button>
            <Button className="flex-1" onClick={handleCompPayment}>
              Comp (Free)
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
