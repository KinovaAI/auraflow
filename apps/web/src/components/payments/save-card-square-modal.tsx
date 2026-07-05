"use client";

/**
 * SaveCardViaSquareModal
 *
 * Inline Square Web Payments SDK card-entry popup. Same shape as the
 * PurchaseViaSquareModal already used on the memberships page, but
 * without a charge — just tokenizes the card and POSTs the nonce to
 * `/portal/payment-methods/save-square` so the studio can save it on
 * the member's Square customer for future renewals.
 *
 * Mounted in place by both:
 *   - /portal/memberships    (the "Manage Billing" button)
 *   - /portal/payment-methods (the "Manage Payment Methods" button)
 *
 * No redirect, no new tab, no external URL.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { CheckCircle, Loader2 } from "lucide-react";
import toast from "react-hot-toast";

import { portalApi } from "@/lib/portal-api";
import { Button } from "@/components/ui/button";

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

export function SaveCardViaSquareModal({
  onClose,
  onSuccess,
}: {
  onClose: () => void;
  onSuccess?: () => void;
}) {
  const [phase, setPhase] = useState<
    "loading_sdk" | "loading_card" | "ready" | "tokenizing" | "submitting" | "done" | "blocked"
  >("loading_sdk");
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
        await card.attach("#save-card-square-card");
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
      await portalApi.saveCardSquare({
        source_id: tokenized.token,
        cardholder_name: cardholderName.trim() || undefined,
      });
      setPhase("done");
      toast.success("Card saved");
    } catch (err: unknown) {
      setError(extractApiError(err, "Could not save the card. Please try again."));
      setPhase("ready");
    }
  }, [cardholderName]);

  const isWorking = phase === "tokenizing" || phase === "submitting";
  const loadingMessage =
    phase === "loading_sdk" ? "Loading Square…" :
    phase === "loading_card" ? "Setting up card field…" :
    phase === "tokenizing" ? "Securing your card…" :
    phase === "submitting" ? "Saving your card…" : null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-2 sm:p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="save-card-square-title"
    >
      <div className="max-h-[95vh] w-full max-w-md overflow-y-auto rounded-lg bg-white p-4 shadow-xl sm:p-6">
        {phase === "done" ? (
          <>
            <div className="mb-3 flex items-center gap-2 text-green-700">
              <CheckCircle className="h-5 w-5" aria-hidden="true" />
              <h3 id="save-card-square-title" className="text-lg font-semibold">Card saved</h3>
            </div>
            <p className="text-sm text-gray-700">Your card is on file for future renewals and purchases.</p>
            <div className="mt-5 flex justify-end">
              <Button onClick={() => { onSuccess?.(); onClose(); }} autoFocus>Done</Button>
            </div>
          </>
        ) : (
          <>
            <h3 id="save-card-square-title" className="text-lg font-semibold text-gray-900">Save card on file</h3>
            <p className="mt-2 text-sm text-gray-600">
              Your card is tokenized and stored by Square. The studio never sees your full card number.
            </p>
            <div className="mt-5 space-y-3">
              <label className="block text-xs font-medium text-gray-500" htmlFor="save-card-square-cardholder">
                Cardholder name <span className="text-gray-400">(optional)</span>
              </label>
              <input
                id="save-card-square-cardholder"
                ref={cardholderRef}
                type="text"
                value={cardholderName}
                onChange={(e) => setCardholderName(e.target.value)}
                placeholder="Name on card"
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 disabled:opacity-50"
                disabled={phase !== "ready"}
                autoComplete="cc-name"
              />
              <div id="save-card-square-card" aria-label="Card number, expiration, and CVV"
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
                Save card
              </Button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
