"use client";

import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { X, Loader2, ExternalLink } from "lucide-react";
import toast from "react-hot-toast";

import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { membershipTypesApi, type MembershipType } from "@/lib/memberships-api";
import { paymentsApi } from "@/lib/payments-api";
import { studiosApi } from "@/lib/scheduling-api";
import { trackConversion } from "@/lib/tracking";

interface PurchaseMembershipModalProps {
  memberId: string;
  memberName: string;
  onClose: () => void;
}

export function PurchaseMembershipModal({
  memberId,
  memberName,
  onClose,
}: PurchaseMembershipModalProps) {
  const [studioId, setStudioId] = useState<string | null>(null);
  const [selectedTypeId, setSelectedTypeId] = useState("");
  const [loading, setLoading] = useState(false);

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
    queryFn: () => membershipTypesApi.list(studioId!).then((r) => r.data),
    enabled: !!studioId,
  });

  // Only show public, active membership types with a price
  const purchasableTypes = types?.filter(
    (t) => t.is_active && t.is_public && t.price_cents > 0
  );

  const selectedType = purchasableTypes?.find((t) => t.id === selectedTypeId);

  const handlePurchase = async () => {
    if (!selectedTypeId) return;
    setLoading(true);
    try {
      const baseUrl = window.location.origin;
      const res = await paymentsApi.createCheckoutSession({
        member_id: memberId,
        membership_type_id: selectedTypeId,
        success_url: `${baseUrl}/dashboard/members/${memberId}?checkout=success`,
        cancel_url: `${baseUrl}/dashboard/members/${memberId}?checkout=cancelled`,
      });
      trackConversion("purchase", selectedType?.price_cents);
      // Redirect to Stripe Checkout
      window.location.href = res.data.data.url;
    } catch {
      toast.error("Failed to create checkout session");
      setLoading(false);
    }
  };

  const fmt = (cents: number) => `$${(cents / 100).toFixed(2)}`;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="mx-4 w-full max-w-md rounded-lg bg-white shadow-xl">
        <div className="flex items-center justify-between border-b border-gray-200 px-6 py-4">
          <h2 className="text-lg font-semibold text-gray-900">
            Purchase Membership
          </h2>
          <button
            onClick={onClose}
            className="rounded-md p-1 text-gray-400 hover:bg-gray-100"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="space-y-4 px-6 py-4">
          <p className="text-sm text-gray-500">
            Purchase a membership for <span className="font-medium text-gray-900">{memberName}</span> via Stripe Checkout.
          </p>

          <div>
            <Label>Membership Type</Label>
            <select
              value={selectedTypeId}
              onChange={(e) => setSelectedTypeId(e.target.value)}
              className="flex h-10 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:border-transparent focus:outline-none focus:ring-2 focus:ring-indigo-500"
            >
              <option value="">Select a membership...</option>
              {purchasableTypes?.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name} - {fmt(t.price_cents)}
                  {t.billing_period === "monthly" ? "/mo" : t.billing_period === "yearly" ? "/yr" : ""}
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
                {" — "}
                {fmt(selectedType.price_cents)}
                {selectedType.billing_period === "monthly"
                  ? "/mo"
                  : selectedType.billing_period === "yearly"
                    ? "/yr"
                    : ""}
              </p>
              {selectedType.billing_period && (
                <p className="mt-1 text-xs text-indigo-600">
                  Recurring {selectedType.billing_period} subscription
                </p>
              )}
              {selectedType.duration_days && !selectedType.billing_period && (
                <p className="mt-1 text-xs text-gray-400">
                  Expires in {selectedType.duration_days} days
                </p>
              )}
              {selectedType.description && (
                <p className="mt-1 text-xs text-gray-400">{selectedType.description}</p>
              )}
            </div>
          )}

          {!purchasableTypes?.length && types !== undefined && (
            <p className="rounded-md bg-yellow-50 p-3 text-sm text-yellow-700">
              No purchasable membership types found. Make sure membership types are marked as active and public with a price.
            </p>
          )}
        </div>

        <div className="flex items-center justify-end gap-2 border-t border-gray-200 px-6 py-4">
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button
            onClick={handlePurchase}
            disabled={!selectedTypeId || loading}
          >
            {loading ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <ExternalLink className="mr-2 h-4 w-4" />
            )}
            Checkout with Stripe
          </Button>
        </div>
      </div>
    </div>
  );
}
