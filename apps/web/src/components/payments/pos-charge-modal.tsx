"use client";

/**
 * AuraFlow — POS Charge Modal (Square Terminal API)
 *
 * Mounted by the membership purchase wizard and member detail "Charge"
 * button. Initiates a Square Terminal checkout and polls until the
 * paired device reports completion / cancel / failure.
 *
 * HARD invariants:
 *   - NO discount / override / comp fields. Ever. (feedback_no_staff_discounts)
 *   - Card is ALWAYS saved on file post-completion (server-side; no UI
 *     toggle, no hardware prompt). See feedback_always_save_card.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { Loader2, CheckCircle, XCircle, Smartphone } from "lucide-react";
import toast from "react-hot-toast";

import { Button } from "@/components/ui/button";
import { paymentsApi, type POSCheckoutStatus } from "@/lib/payments-api";

interface POSChargeModalProps {
  open: boolean;
  member: { id: string; first_name?: string; last_name?: string };
  amountCents: number;
  description: string;
  membershipTypeId?: string;       // when initiating a recurring sub
  classSessionId?: string;          // when paying for a specific drop-in
  // Workshop walk-in: pass the course so the SERVER enrolls the member
  // automatically when payment confirms (the deeplink callback
  // navigates the browser away from this modal, so the post-success
  // client-side enroll never fires).
  courseId?: string;
  onClose: () => void;
  onSuccess: (result: POSCheckoutStatus) => void;
}

export function POSChargeModal({
  open,
  member,
  amountCents,
  description,
  membershipTypeId,
  classSessionId,
  courseId,
  onClose,
  onSuccess,
}: POSChargeModalProps) {
  const [phase, setPhase] = useState<"idle" | "starting" | "in_progress" | "completed" | "failed" | "cancelled" | "no_device">("idle");
  const [error, setError] = useState<string | null>(null);
  const [checkoutId, setCheckoutId] = useState<string | null>(null);
  const [deviceId, setDeviceId] = useState<string | null>(null);
  const [deeplinkLoading, setDeeplinkLoading] = useState(false);
  const pollRef = useRef<NodeJS.Timeout | null>(null);
  // Track latest onSuccess so the polling closure doesn't fire a stale
  // version after a parent re-render (was a real bug — auditor caught
  // it during the 2026-06-07 review pass).
  const onSuccessRef = useRef(onSuccess);
  useEffect(() => { onSuccessRef.current = onSuccess; }, [onSuccess]);

  const startCharge = useCallback(async () => {
    setPhase("starting");
    setError(null);
    try {
      const resp = await paymentsApi.posCharge({
        member_id: member.id,
        amount_cents: amountCents,
        description,
        membership_type_id: membershipTypeId,
        class_session_id: classSessionId,
      });
      const data = resp.data.data;
      setCheckoutId(data.checkout_id);
      setDeviceId(data.device_id ?? null);
      setPhase("in_progress");
    } catch (err: unknown) {
      const d = (err as { response?: { data?: { detail?: { error?: string; code?: string } | string } } })
        ?.response?.data?.detail;
      const msg = typeof d === "string" ? d : d?.error || "Could not start the charge";
      const code = typeof d === "object" ? d?.code : undefined;
      setError(msg);
      // No paired Terminal device? Offer the phone deep-link path instead.
      if (code === "NO_POS_DEVICE") {
        setPhase("no_device");
      } else {
        setPhase("failed");
      }
    }
  }, [member.id, amountCents, description, membershipTypeId, classSessionId]);

  const chargeViaPhone = useCallback(async () => {
    setDeeplinkLoading(true);
    try {
      const resp = await paymentsApi.posDeeplinkCharge({
        member_id: member.id,
        amount_cents: amountCents,
        description,
        membership_type_id: membershipTypeId,
        class_session_id: classSessionId,
        course_id: courseId,
      });
      const data = resp.data.data;
      setCheckoutId(data.checkout_id);
      // Pick iOS or Android URL by UA
      const ua = navigator.userAgent || "";
      const isAndroid = /Android/i.test(ua);
      const url = isAndroid ? data.android_url : data.ios_url;
      setPhase("in_progress");
      // Opens Square POS app on the same phone
      window.location.href = url;
    } catch (err: unknown) {
      const d = (err as { response?: { data?: { detail?: { error?: string } | string } } })
        ?.response?.data?.detail;
      const msg = typeof d === "string" ? d : d?.error || "Could not open Square POS";
      setError(msg);
      setPhase("failed");
    } finally {
      setDeeplinkLoading(false);
    }
  }, [member.id, amountCents, description, membershipTypeId, classSessionId, courseId]);

  // Poll for completion once we have a checkout_id
  useEffect(() => {
    if (!checkoutId || phase !== "in_progress") return;
    let cancelled = false;
    const poll = async () => {
      if (cancelled) return;
      try {
        const resp = await paymentsApi.getPOSCheckout(checkoutId);
        const s = resp.data.data.status;
        if (s === "completed") {
          setPhase("completed");
          onSuccessRef.current(resp.data.data);
          return;
        }
        if (s === "cancelled") {
          setPhase("cancelled");
          return;
        }
        if (s === "failed" || s === "expired") {
          setPhase("failed");
          setError(resp.data.data.failure_reason || `Checkout ${s}`);
          return;
        }
      } catch {
        /* keep polling */
      }
      pollRef.current = setTimeout(poll, 1500);
    };
    poll();
    return () => {
      cancelled = true;
      if (pollRef.current) clearTimeout(pollRef.current);
    };
  }, [checkoutId, phase]);

  const cancelCheckout = useCallback(async () => {
    if (!checkoutId) {
      onClose();
      return;
    }
    try {
      await paymentsApi.cancelPOSCheckout(checkoutId);
    } catch {
      /* server may have already won the race; poll to find out */
    }
    // Don't trust the cancel result blindly — the customer may have
    // tapped at the same moment. Poll the checkout for 3 seconds; if
    // Square reports COMPLETED, switch to the completed UI so staff
    // know the charge actually went through. Otherwise mark cancelled.
    const start = Date.now();
    const winnerCheck = async () => {
      while (Date.now() - start < 3000) {
        try {
          const resp = await paymentsApi.getPOSCheckout(checkoutId);
          const s = resp.data.data.status;
          if (s === "completed") {
            setPhase("completed");
            onSuccessRef.current(resp.data.data);
            return;
          }
          if (s === "cancelled" || s === "failed" || s === "expired") {
            setPhase("cancelled");
            toast.success("Checkout cancelled");
            return;
          }
        } catch {
          /* keep trying */
        }
        await new Promise((r) => setTimeout(r, 500));
      }
      setPhase("cancelled");
      toast.success("Checkout cancelled");
    };
    winnerCheck();
  }, [checkoutId, onClose]);

  // Reset state when the modal opens (vs re-mount on each open)
  useEffect(() => {
    if (open && phase === "idle") {
      startCharge();
    }
    if (!open) {
      setPhase("idle");
      setCheckoutId(null);
      setDeviceId(null);
      setError(null);
    }
  }, [open, phase, startCharge]);

  // Escape key closes when nothing's in flight (a11y); ignored while
  // a charge is mid-tap so staff don't accidentally lose state.
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      if (phase === "in_progress" || phase === "starting") return;
      onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, phase, onClose]);

  if (!open) return null;

  const memberName = `${member.first_name || ""} ${member.last_name || ""}`.trim() || "Member";
  const amountFmt = `$${(amountCents / 100).toFixed(2)}`;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-2 sm:p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="pos-charge-title"
      onClick={(e) => {
        // Backdrop click closes only when nothing's mid-flight
        if (
          e.target === e.currentTarget &&
          phase !== "in_progress" &&
          phase !== "starting"
        ) {
          onClose();
        }
      }}
    >
      <div className="max-h-[95vh] w-full max-w-md overflow-y-auto rounded-lg bg-white p-4 shadow-xl sm:p-6">
        <h3 id="pos-charge-title" className="text-lg font-semibold text-gray-900">
          Charge {memberName}
        </h3>
        <p className="mt-1 text-sm text-gray-600">
          <span className="font-medium">{amountFmt}</span> — {description}
        </p>

        {phase === "starting" && (
          <div className="mt-6 flex flex-col items-center gap-3 text-sm text-gray-600" role="status">
            <Loader2 className="h-8 w-8 animate-spin text-indigo-600" />
            <span>Starting checkout…</span>
          </div>
        )}

        {phase === "in_progress" && (
          <div className="mt-6 flex flex-col items-center gap-3 text-center" role="status">
            <div className="rounded-full bg-indigo-50 p-4">
              <Smartphone className="h-10 w-10 text-indigo-600" />
            </div>
            <div className="font-medium text-gray-900">Tap or insert card on the terminal</div>
            <div className="text-sm text-gray-500">
              {deviceId ? `Device: ${deviceId.slice(0, 12)}…` : "Connected to your Square device"}
            </div>
            <Loader2 className="h-5 w-5 animate-spin text-indigo-600" />
          </div>
        )}

        {phase === "completed" && (
          <div className="mt-6 flex flex-col items-center gap-3 text-center">
            <CheckCircle className="h-10 w-10 text-green-600" />
            <div className="font-semibold text-gray-900">Charge completed</div>
            <div className="text-sm text-gray-500">
              {amountFmt} captured. Card saved on file for future automatic charges.
            </div>
          </div>
        )}

        {phase === "no_device" && (() => {
          const ua = typeof navigator !== "undefined" ? navigator.userAgent : "";
          const isMobile = /Android|iPhone|iPad|iPod/i.test(ua);
          return (
            <div className="mt-6 flex flex-col items-center gap-3 text-center">
              <div className="rounded-full bg-indigo-50 p-4">
                <Smartphone className="h-10 w-10 text-indigo-600" />
              </div>
              <div className="font-semibold text-gray-900">
                {isMobile ? "Charge via your phone" : "No Square Terminal paired"}
              </div>
              <div className="text-sm text-gray-500 max-w-xs">
                {isMobile
                  ? "No Square Terminal hardware is paired with this studio. Use the Square POS app on this phone to take this payment — tap below and Square POS will open with the amount pre-filled."
                  : "No Square Terminal hardware is paired with this studio. Take this charge from a phone or tablet running the Square POS app (the deep-link only works on mobile), or pair a Square Reader/Terminal in Settings → Square POS."}
              </div>
            </div>
          );
        })()}

        {(phase === "failed" || phase === "cancelled") && (
          <div className="mt-6 flex flex-col items-center gap-3 text-center">
            <XCircle className="h-10 w-10 text-red-600" />
            <div className="font-semibold text-gray-900">
              {phase === "cancelled" ? "Checkout cancelled" : "Charge failed"}
            </div>
            {error && <div className="text-sm text-gray-600">{error}</div>}
          </div>
        )}

        <div className="mt-6 flex justify-end gap-3">
          {phase === "in_progress" && (
            <Button variant="outline" onClick={cancelCheckout}>
              Cancel checkout
            </Button>
          )}
          {phase === "no_device" && (() => {
            const ua = typeof navigator !== "undefined" ? navigator.userAgent : "";
            const isMobile = /Android|iPhone|iPad|iPod/i.test(ua);
            return (
              <>
                <Button variant="outline" onClick={onClose}>Cancel</Button>
                {isMobile && (
                  <Button onClick={chargeViaPhone} disabled={deeplinkLoading} autoFocus>
                    {deeplinkLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                    <Smartphone className="mr-2 h-4 w-4" />
                    Open Square POS on phone
                  </Button>
                )}
              </>
            );
          })()}
          {phase === "completed" && (
            <Button onClick={onClose} autoFocus>Done</Button>
          )}
          {(phase === "failed" || phase === "cancelled") && (
            <>
              <Button variant="outline" onClick={onClose}>Close</Button>
              <Button onClick={startCharge}>Try again</Button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
