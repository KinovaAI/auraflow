"use client";

/**
 * AuraFlow — Saved Card Charge Modal
 *
 * Ad-hoc charge on a member's saved Square card on file. No hardware,
 * no Web Payments SDK — just amount + description, routed through
 * billing_dispatcher.charge_saved_card (1% app_fee applied server-side).
 *
 * Extracted from members/[id]/page.tsx in the 2026-06-07 audit pass.
 */
import { useState } from "react";
import { Loader2 } from "lucide-react";
import toast from "react-hot-toast";

import { Button } from "@/components/ui/button";
import { paymentsApi } from "@/lib/payments-api";

export function SavedCardChargeModal({
  memberId,
  memberName,
  last4,
  initialAmount,
  initialDescription,
  onClose,
  onSuccess,
}: {
  memberId: string;
  memberName: string;
  last4: string;
  initialAmount: string;
  initialDescription: string;
  onClose: () => void;
  onSuccess: () => void;
}) {
  const [amount, setAmount] = useState(initialAmount);
  const [description, setDescription] = useState(initialDescription);
  const [working, setWorking] = useState(false);

  const submit = async () => {
    const cents = Math.round(parseFloat(amount || "0") * 100);
    if (cents <= 0 || !description.trim()) {
      toast.error("Amount + description required");
      return;
    }
    setWorking(true);
    try {
      await paymentsApi.chargeSavedCard({
        member_id: memberId,
        amount_cents: cents,
        description: description.trim(),
      });
      onSuccess();
    } catch (err: unknown) {
      const d = (err as { response?: { data?: { detail?: { error?: string } | string } } })
        ?.response?.data?.detail;
      const msg = typeof d === "string" ? d : d?.error || "Charge failed";
      toast.error(msg);
      setWorking(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-2 sm:p-4"
      role="dialog"
      aria-modal="true"
      onClick={(e) => {
        if (e.target === e.currentTarget && !working) onClose();
      }}
    >
      <div className="w-full max-w-sm rounded-lg bg-white p-6 shadow-xl">
        <h3 className="text-lg font-semibold text-gray-900">Charge saved card</h3>
        <p className="mt-1 text-sm text-gray-500">
          {memberName} — card ••{last4}
        </p>
        <div className="mt-4 space-y-3">
          <input
            type="number"
            placeholder="$ amount"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none"
            autoFocus
          />
          <input
            type="text"
            placeholder="Description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none"
          />
        </div>
        <div className="mt-6 flex justify-end gap-3">
          <Button variant="outline" onClick={onClose} disabled={working}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={working}>
            {working && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Charge
          </Button>
        </div>
      </div>
    </div>
  );
}
