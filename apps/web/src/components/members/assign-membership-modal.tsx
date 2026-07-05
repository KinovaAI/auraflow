"use client";

import { useEffect, useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { X, Loader2, AlertTriangle } from "lucide-react";
import toast from "react-hot-toast";

import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  membershipTypesApi,
  memberMembershipsApi,
  type MembershipType,
} from "@/lib/memberships-api";
import { studiosApi } from "@/lib/scheduling-api";
import { apiClient } from "@/lib/api-client";

interface AssignMembershipModalProps {
  memberId: string;
  onClose: () => void;
  onAssigned: () => void;
}

export function AssignMembershipModal({
  memberId,
  onClose,
  onAssigned,
}: AssignMembershipModalProps) {
  const [studioId, setStudioId] = useState<string | null>(null);
  const [selectedTypeId, setSelectedTypeId] = useState("");
  const [payWithGiftCard, setPayWithGiftCard] = useState(false);
  const [giftCardCode, setGiftCardCode] = useState("");

  const { data: studios } = useQuery({
    queryKey: ["studios"],
    queryFn: () => studiosApi.list().then((r) => r.data),
  });

  useEffect(() => {
    if (studios?.length && !studioId) {
      setStudioId(studios[0].id);
    }
  }, [studios, studioId]);

  const { data: types } = useQuery({
    queryKey: ["membership-types", studioId],
    queryFn: () =>
      membershipTypesApi.list(studioId!).then((r) => r.data),
    enabled: !!studioId,
  });

  // Waiver status — fetched up front so we can block the whole flow
  // when the member hasn't signed. Backend also enforces this (409 with
  // code=waiver_required) but blocking in the UI means staff never even
  // see a membership type picker for a non-waivered member, which is
  // the clearer signal.
  const { data: waiverStatus, isLoading: waiverLoading } = useQuery({
    queryKey: ["member-waiver-status", memberId],
    queryFn: () =>
      apiClient
        .get<{ data: { signed: boolean; expired: boolean; needs_resign: boolean } }>(
          `/waivers/members/${memberId}/status`
        )
        .then((r) => r.data.data),
  });
  const waiverBlocked =
    waiverStatus && (!waiverStatus.signed || waiverStatus.expired || waiverStatus.needs_resign);

  const assignMutation = useMutation({
    mutationFn: () =>
      payWithGiftCard
        ? memberMembershipsApi.purchaseWithGiftCard(
            memberId, selectedTypeId, giftCardCode.trim(),
          )
        : memberMembershipsApi.assign(memberId, selectedTypeId),
    onSuccess: () => onAssigned(),
    onError: (err: any) => {
      // Surface the waiver-required error from the backend as the
      // shouty banner instead of a generic toast. Other ValueError
      // messages (insufficient gift-card balance, recurring sub
      // rejection, etc.) come back as 400 with detail=string.
      const detail = err?.response?.data?.detail;
      const msg =
        typeof detail === "object" && detail?.code === "waiver_required"
          ? detail.message
          : typeof detail === "string"
            ? detail
            : "Failed to assign membership";
      toast.error(msg);
    },
  });

  const selectedType = types?.find((t) => t.id === selectedTypeId);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="mx-4 w-full max-w-md rounded-lg bg-white shadow-xl">
        <div className="flex items-center justify-between border-b border-gray-200 px-6 py-4">
          <h2 className="text-lg font-semibold text-gray-900">
            Assign Membership
          </h2>
          <button
            onClick={onClose}
            className="rounded-md p-1 text-gray-400 hover:bg-gray-100"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="space-y-4 px-6 py-4">
          {waiverLoading ? (
            <div className="flex items-center gap-2 text-sm text-gray-500">
              <Loader2 className="h-4 w-4 animate-spin" />
              Checking waiver status…
            </div>
          ) : waiverBlocked ? (
            <div
              role="alert"
              className="rounded-md border-2 border-red-500 bg-red-50 p-4"
            >
              <div className="flex items-start gap-3">
                <AlertTriangle className="mt-0.5 h-6 w-6 shrink-0 text-red-600" />
                <div>
                  <p className="text-base font-bold uppercase tracking-wide text-red-700">
                    Waiver Not Completed
                  </p>
                  <p className="mt-1 text-sm font-semibold text-red-700">
                    Cannot participate without waiver.
                  </p>
                  <p className="mt-2 text-sm text-red-700">
                    This member must sign the liability waiver before any
                    membership or class pass can be added to their account.
                    Have them sign in the portal, then come back to this
                    screen.
                  </p>
                </div>
              </div>
            </div>
          ) : null}

          <div>
            <Label>Membership Type</Label>
            <select
              value={selectedTypeId}
              onChange={(e) => setSelectedTypeId(e.target.value)}
              className="flex h-10 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:border-transparent focus:outline-none focus:ring-2 focus:ring-indigo-500"
            >
              <option value="">Select a membership...</option>
              {types?.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name} - ${(t.price_cents / 100).toFixed(2)}/{t.billing_period || "one-time"}
                </option>
              ))}
            </select>
          </div>

          {selectedType && (
            <div className="rounded-md bg-gray-50 p-3 text-sm">
              <p className="font-medium text-gray-900">{selectedType.name}</p>
              <p className="text-gray-500">
                {selectedType.type === "class_pack"
                  ? `${selectedType.class_count} classes`
                  : selectedType.type === "unlimited"
                    ? "Unlimited classes"
                    : selectedType.type}
                {" - "}${(selectedType.price_cents / 100).toFixed(2)}
                {selectedType.billing_period === "monthly"
                  ? "/mo"
                  : selectedType.billing_period === "yearly"
                    ? "/yr"
                    : ""}
              </p>
              {selectedType.duration_days && (
                <p className="text-xs text-gray-400">
                  Expires in {selectedType.duration_days} days
                </p>
              )}
            </div>
          )}

          {/* Gift-card payment toggle. Default off — most assigns are
              comps / "already paid" where staff just needs the row
              created. Recurring memberships are blocked server-side. */}
          {selectedType && selectedType.price_cents > 0 &&
            !["monthly", "yearly", "weekly"].includes(selectedType.billing_period || "") && (
            <div className="rounded-md border border-gray-200 p-3">
              <label className="flex cursor-pointer items-center gap-2 text-sm font-medium text-gray-700">
                <input
                  type="checkbox"
                  checked={payWithGiftCard}
                  onChange={(e) => setPayWithGiftCard(e.target.checked)}
                  className="h-4 w-4 rounded border-gray-300"
                />
                Pay with gift card
              </label>
              {payWithGiftCard && (
                <div className="mt-3">
                  <Label className="text-xs">Gift Card Code</Label>
                  <input
                    type="text"
                    value={giftCardCode}
                    onChange={(e) => setGiftCardCode(e.target.value.toUpperCase())}
                    placeholder="XXXX-XXXX-XXXX-XXXX"
                    className="mt-1 flex h-10 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm font-mono tracking-wider focus:border-transparent focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  />
                  <p className="mt-1 text-xs text-gray-400">
                    Card balance must cover the full price (${(selectedType.price_cents / 100).toFixed(2)}).
                  </p>
                </div>
              )}
            </div>
          )}
        </div>

        <div className="flex items-center justify-end gap-2 border-t border-gray-200 px-6 py-4">
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button
            onClick={() => assignMutation.mutate()}
            disabled={
              !selectedTypeId ||
              assignMutation.isPending ||
              !!waiverBlocked ||
              waiverLoading ||
              (payWithGiftCard && !giftCardCode.trim())
            }
          >
            {assignMutation.isPending && (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            )}
            {waiverBlocked
              ? "Waiver Required"
              : payWithGiftCard
                ? "Charge Gift Card & Assign"
                : "Assign Membership"}
          </Button>
        </div>
      </div>
    </div>
  );
}
