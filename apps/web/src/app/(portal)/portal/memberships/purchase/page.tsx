"use client";

import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { Loader2, ArrowLeft, Check, Sparkles, Gift } from "lucide-react";
import toast from "react-hot-toast";

import { portalApi } from "@/lib/portal-api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { trackConversion } from "@/lib/tracking";

function formatCents(cents: number) {
  return `$${(cents / 100).toFixed(2)}`;
}

function isRecurring(billingPeriod: string | undefined | null) {
  return billingPeriod === "monthly" || billingPeriod === "yearly" || billingPeriod === "weekly";
}

export default function PurchaseMembershipPage() {
  const router = useRouter();
  // Per-card gift-card state. Keyed by plan id so opening one card's
  // gift-card form doesn't toggle on the others.
  const [giftCardOpen, setGiftCardOpen] = useState<Record<string, boolean>>({});
  const [giftCardCode, setGiftCardCode] = useState<Record<string, string>>({});

  const { data: profile } = useQuery({
    queryKey: ["portal-profile"],
    queryFn: () => portalApi.getProfile().then((r) => r.data),
  });

  const { data: plans, isLoading } = useQuery({
    queryKey: ["available-memberships"],
    queryFn: () => portalApi.getAvailableMemberships().then((r) => r.data),
  });

  const purchaseMutation = useMutation({
    mutationFn: (membershipTypeId: string) =>
      portalApi.purchaseMembership({
        membership_type_id: membershipTypeId,
        success_url: `${window.location.origin}/portal/memberships?purchased=1`,
        cancel_url: `${window.location.origin}/portal/memberships/purchase`,
      }),
    onSuccess: (resp, membershipTypeId) => {
      // Fire purchase conversion — find the plan to get the price
      const plan = plans?.find((p) => p.id === membershipTypeId);
      trackConversion("purchase", plan?.price_cents);

      const url = resp.data?.data?.url;
      if (url) {
        window.location.href = url;
      } else {
        toast.success("Membership purchased!");
        router.push("/portal/memberships");
      }
    },
    onError: () => toast.error("Failed to start purchase"),
  });

  const giftCardPurchaseMutation = useMutation({
    mutationFn: (vars: { membershipTypeId: string; code: string }) => {
      if (!profile?.id) throw new Error("Profile not loaded");
      return portalApi.purchaseMembershipWithGiftCard({
        member_id: profile.id,
        membership_type_id: vars.membershipTypeId,
        gift_card_code: vars.code,
      });
    },
    onSuccess: (_resp, vars) => {
      const plan = plans?.find((p) => p.id === vars.membershipTypeId);
      trackConversion("purchase", plan?.price_cents);
      toast.success("Membership purchased with gift card");
      router.push("/portal/memberships?purchased=1");
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: unknown } } })
        ?.response?.data?.detail;
      toast.error(typeof detail === "string" ? detail : "Gift card payment failed");
    },
  });

  return (
    <div>
      <div className="mb-6">
        <button
          onClick={() => router.push("/portal/memberships")}
          className="mb-3 flex items-center gap-1 text-sm text-gray-500 hover:text-gray-700"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to My Memberships
        </button>
        <h1 className="text-2xl font-bold text-gray-900">Browse Plans</h1>
        <p className="mt-1 text-sm text-gray-500">
          Choose a membership plan that works for you.
        </p>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-16">
          <Loader2 className="h-6 w-6 animate-spin text-indigo-600" />
        </div>
      ) : !plans || plans.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center">
            <p className="text-gray-500">
              No membership plans are available right now.
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-6 sm:grid-cols-2">
          {plans.map((plan) => (
            <Card
              key={plan.id}
              className={`relative transition-shadow hover:shadow-md ${
                plan.is_founding_rate
                  ? "border-indigo-200 ring-2 ring-indigo-100"
                  : ""
              }`}
            >
              {plan.is_founding_rate && (
                <div className="absolute -top-3 left-4">
                  <span className="inline-flex items-center gap-1 rounded-full bg-indigo-600 px-3 py-0.5 text-xs font-medium text-white">
                    <Sparkles className="h-3 w-3" />
                    Founding Rate
                  </span>
                </div>
              )}
              <CardHeader>
                <CardTitle className="text-lg">{plan.name}</CardTitle>
                {plan.description && (
                  <p className="mt-1 text-sm text-gray-500">
                    {plan.description}
                  </p>
                )}
              </CardHeader>
              <CardContent className="space-y-4">
                <div>
                  <span className="text-3xl font-bold text-gray-900">
                    {formatCents(plan.price_cents)}
                  </span>
                  {plan.billing_period && (
                    <span className="text-sm text-gray-500">
                      /{plan.billing_period}
                    </span>
                  )}
                </div>

                <ul className="space-y-2 text-sm text-gray-600">
                  {plan.class_count && (
                    <li className="flex items-center gap-2">
                      <Check className="h-4 w-4 text-green-500" />
                      {plan.class_count} classes
                      {plan.billing_period ? ` per ${plan.billing_period}` : ""}
                    </li>
                  )}
                  {plan.duration_days && (
                    <li className="flex items-center gap-2">
                      <Check className="h-4 w-4 text-green-500" />
                      {plan.duration_days} day duration
                    </li>
                  )}
                  {plan.trial_days > 0 && (
                    <li className="flex items-center gap-2">
                      <Check className="h-4 w-4 text-green-500" />
                      {plan.trial_days}-day free trial
                    </li>
                  )}
                  {plan.freeze_allowed && (
                    <li className="flex items-center gap-2">
                      <Check className="h-4 w-4 text-green-500" />
                      Freeze/pause allowed
                    </li>
                  )}
                </ul>

                <Button
                  className="w-full"
                  onClick={() => purchaseMutation.mutate(plan.id)}
                  disabled={purchaseMutation.isPending}
                >
                  {purchaseMutation.isPending ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : null}
                  Purchase
                </Button>

                {/* Gift-card payment is one-time-only — recurring subs
                    need a card on file for renewals. */}
                {!isRecurring(plan.billing_period) && plan.price_cents > 0 && (
                  <div className="border-t border-gray-100 pt-3">
                    {!giftCardOpen[plan.id] ? (
                      <button
                        type="button"
                        onClick={() =>
                          setGiftCardOpen((o) => ({ ...o, [plan.id]: true }))
                        }
                        className="flex w-full items-center justify-center gap-1.5 text-xs text-gray-500 hover:text-indigo-600"
                      >
                        <Gift className="h-3.5 w-3.5" />
                        Have a gift card? Use it here
                      </button>
                    ) : (
                      <div className="space-y-2">
                        <input
                          type="text"
                          value={giftCardCode[plan.id] || ""}
                          onChange={(e) =>
                            setGiftCardCode((c) => ({
                              ...c,
                              [plan.id]: e.target.value.toUpperCase(),
                            }))
                          }
                          placeholder="Gift card code"
                          className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm font-mono tracking-wider focus:border-transparent focus:outline-none focus:ring-2 focus:ring-indigo-500"
                        />
                        <div className="flex gap-2">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() =>
                              setGiftCardOpen((o) => ({ ...o, [plan.id]: false }))
                            }
                          >
                            Cancel
                          </Button>
                          <Button
                            size="sm"
                            className="flex-1"
                            disabled={
                              !giftCardCode[plan.id]?.trim() ||
                              giftCardPurchaseMutation.isPending ||
                              !profile
                            }
                            onClick={() =>
                              giftCardPurchaseMutation.mutate({
                                membershipTypeId: plan.id,
                                code: (giftCardCode[plan.id] || "").trim(),
                              })
                            }
                          >
                            {giftCardPurchaseMutation.isPending && (
                              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                            )}
                            Redeem
                          </Button>
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
