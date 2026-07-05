"use client";

import { useState } from "react";
import { AlertCircle, CheckCircle2 } from "lucide-react";

import { Button } from "@/components/ui/button";

export type CancelRole = "instructor" | "member" | "staff";

interface Props {
  bookingMemberName?: string;
  pricePaid?: number; // cents
  paymentStatus?: string;
  onClose: () => void;
  onConfirm: (role: CancelRole, reason: string) => void;
  submitting?: boolean;
}

export function CancelBookingModal({
  bookingMemberName,
  pricePaid = 0,
  paymentStatus,
  onClose,
  onConfirm,
  submitting,
}: Props) {
  const [role, setRole] = useState<CancelRole>("instructor");
  const [reason, setReason] = useState("");

  const willGrantCredit =
    role === "instructor" &&
    pricePaid > 0 &&
    (paymentStatus === "paid" || paymentStatus === "comp");

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
      onClick={onClose}
    >
      <div
        className="w-full max-w-md rounded-lg bg-white p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-lg font-bold text-gray-900">Cancel session</h2>
        {bookingMemberName && (
          <p className="mt-1 text-sm text-slate-600">
            for{" "}
            <span className="font-medium text-slate-900">
              {bookingMemberName}
            </span>
          </p>
        )}

        <div className="mt-4">
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Who is cancelling?
          </label>
          <div className="space-y-2">
            {(
              [
                {
                  value: "instructor",
                  label: "Instructor",
                  hint: "Studio is cancelling — credit is preserved",
                },
                {
                  value: "member",
                  label: "Member",
                  hint: "Member-initiated cancellation",
                },
                {
                  value: "staff",
                  label: "Staff (administrative)",
                  hint: "Reschedule, mistake, etc. — no credit grant",
                },
              ] as { value: CancelRole; label: string; hint: string }[]
            ).map((opt) => (
              <label
                key={opt.value}
                className={`flex items-start gap-3 rounded-md border px-3 py-2 cursor-pointer ${
                  role === opt.value
                    ? "border-indigo-400 bg-indigo-50"
                    : "border-slate-200 hover:bg-slate-50"
                }`}
              >
                <input
                  type="radio"
                  name="cancel-role"
                  className="mt-0.5"
                  checked={role === opt.value}
                  onChange={() => setRole(opt.value)}
                />
                <div className="flex-1">
                  <div className="text-sm font-medium text-slate-900">
                    {opt.label}
                  </div>
                  <div className="text-xs text-slate-500">{opt.hint}</div>
                </div>
              </label>
            ))}
          </div>
        </div>

        <div className="mt-4">
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Reason (optional)
          </label>
          <textarea
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            rows={2}
            placeholder="e.g. instructor sick, member rescheduling"
            className="block w-full rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:ring-indigo-500"
          />
        </div>

        {willGrantCredit && (
          <div className="mt-4 flex gap-2 rounded-md border border-emerald-200 bg-emerald-50 p-3 text-sm">
            <CheckCircle2 className="h-4 w-4 text-emerald-600 mt-0.5" />
            <div className="text-emerald-800">
              A <strong>${(pricePaid / 100).toFixed(2)}</strong> credit will be
              preserved for this member and can be applied to a future private
              session (good for 180 days).
            </div>
          </div>
        )}
        {role === "member" && pricePaid > 0 && paymentStatus === "paid" && (
          <div className="mt-4 flex gap-2 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm">
            <AlertCircle className="h-4 w-4 text-amber-600 mt-0.5" />
            <div className="text-amber-800">
              Member-initiated cancellation forfeits the paid credit per policy.
              If you want to preserve it anyway, choose <em>Staff</em> and grant
              a courtesy credit afterwards.
            </div>
          </div>
        )}

        <div className="mt-5 flex justify-end gap-2">
          <Button variant="outline" size="sm" onClick={onClose}>
            Don't cancel
          </Button>
          <Button
            size="sm"
            onClick={() => onConfirm(role, reason)}
            disabled={submitting}
          >
            {submitting ? "Cancelling…" : "Cancel session"}
          </Button>
        </div>
      </div>
    </div>
  );
}
