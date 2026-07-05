"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { format } from "date-fns";
import { Loader2, Gift, Search, Check, Send, Copy, ShoppingBag } from "lucide-react";
import toast from "react-hot-toast";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  giftCardsApi,
  type CheckBalanceResponse,
  type GiftCard,
} from "@/lib/gift-cards-api";
import { portalApi } from "@/lib/portal-api";

// ── Helpers ──────────────────────────────────────────────────────────────────

function fmtCents(cents: number) {
  return `$${(cents / 100).toFixed(2)}`;
}

function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    active: "bg-green-100 text-green-800",
    fully_redeemed: "bg-blue-100 text-blue-800",
    voided: "bg-red-100 text-red-800",
    expired: "bg-gray-100 text-gray-800",
  };
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${colors[status] || "bg-gray-100 text-gray-800"}`}
    >
      {status.replace("_", " ")}
    </span>
  );
}

// ── Main Page ────────────────────────────────────────────────────────────────

export default function PortalGiftCardsPage() {
  const queryClient = useQueryClient();
  const [balanceCode, setBalanceCode] = useState("");
  const [balanceResult, setBalanceResult] = useState<CheckBalanceResponse | null>(null);
  const [redeemCode, setRedeemCode] = useState("");
  const [redeemAmount, setRedeemAmount] = useState("");
  const [useFullBalance, setUseFullBalance] = useState(true);

  // Purchase state
  const [showPurchase, setShowPurchase] = useState(false);
  const [purchaseAmount, setPurchaseAmount] = useState("");
  const [recipientEmail, setRecipientEmail] = useState("");
  const [recipientName, setRecipientName] = useState("");
  const [personalMessage, setPersonalMessage] = useState("");
  const [newGiftCardCode, setNewGiftCardCode] = useState("");

  const { data: myGiftCards, isLoading: myCardsLoading } = useQuery({
    queryKey: ["my-gift-cards"],
    queryFn: () => giftCardsApi.listMyGiftCards().then((r) => r.data),
  });

  const checkBalanceMutation = useMutation({
    mutationFn: (code: string) =>
      giftCardsApi.checkBalance(code).then((r) => r.data.data),
    onSuccess: (data) => setBalanceResult(data),
    onError: () => {
      setBalanceResult(null);
      toast.error("Gift card not found. Please check the code and try again.");
    },
  });

  const redeemMutation = useMutation({
    mutationFn: (data: { code: string; amount_cents: number }) =>
      giftCardsApi.redeem(data).then((r) => r.data.data),
    onSuccess: () => {
      toast.success("Gift card redeemed successfully!");
      setRedeemCode("");
      setRedeemAmount("");
      setUseFullBalance(true);
    },
    onError: () => toast.error("Failed to redeem gift card. Please try again."),
  });

  // Members purchase gift cards via Stripe Checkout — the card is
  // only created server-side after payment confirms (webhook). Without
  // this, members could self-issue free $1000 gift cards.
  const { data: profile } = useQuery({
    queryKey: ["portal-profile"],
    queryFn: () => portalApi.getProfile().then((r) => r.data),
  });

  const purchaseMutation = useMutation({
    mutationFn: (data: {
      amount_cents: number;
      recipient_email?: string;
      recipient_name?: string;
      message?: string;
    }) => {
      if (!profile?.id) throw new Error("Profile not loaded");
      return giftCardsApi
        .create({
          amount_cents: data.amount_cents,
          recipient_email: data.recipient_email,
          recipient_name: data.recipient_name,
          personal_message: data.message,
          payment_method: "card",
          purchaser_member_id: profile.id,
          success_url: `${window.location.origin}/portal/gift-cards?purchased=1`,
          cancel_url: `${window.location.origin}/portal/gift-cards`,
        })
        .then((r) => r.data);
    },
    onSuccess: (data) => {
      // Server returns either a checkout_url (deferred) or a gift_card
      // (immediate). For member-portal purchases it's always Stripe,
      // so we always redirect.
      if (data.checkout_url) {
        window.location.href = data.checkout_url;
        return;
      }
      // Fallback path — shouldn't happen for portal flow but handle
      // it gracefully if a server-side change ever lands here.
      if (data.gift_card?.code) {
        setNewGiftCardCode(data.gift_card.code);
        toast.success("Gift card purchased!");
        queryClient.invalidateQueries({ queryKey: ["my-gift-cards"] });
        setPurchaseAmount("");
        setRecipientEmail("");
        setRecipientName("");
        setPersonalMessage("");
      }
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: unknown } } })
        ?.response?.data?.detail;
      toast.error(typeof detail === "string" ? detail : "Failed to purchase gift card");
    },
  });

  const handlePurchase = (e: React.FormEvent) => {
    e.preventDefault();
    const cents = Math.round((parseFloat(purchaseAmount) || 0) * 100);
    if (cents < 500) {
      toast.error("Minimum gift card amount is $5.00");
      return;
    }
    purchaseMutation.mutate({
      amount_cents: cents,
      recipient_email: recipientEmail.trim() || undefined,
      recipient_name: recipientName.trim() || undefined,
      message: personalMessage.trim() || undefined,
    });
  };

  const handleCheckBalance = (e: React.FormEvent) => {
    e.preventDefault();
    if (!balanceCode.trim()) {
      toast.error("Please enter a gift card code");
      return;
    }
    checkBalanceMutation.mutate(balanceCode.trim());
  };

  const handleRedeem = (e: React.FormEvent) => {
    e.preventDefault();
    if (!redeemCode.trim()) {
      toast.error("Please enter a gift card code");
      return;
    }
    const cents = useFullBalance
      ? 0 // Backend interprets 0 as full balance
      : Math.round(parseFloat(redeemAmount) * 100);
    if (!useFullBalance && (!cents || cents <= 0)) {
      toast.error("Please enter a valid amount");
      return;
    }
    redeemMutation.mutate({
      code: redeemCode.trim(),
      amount_cents: cents,
    });
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Gift Cards</h1>
          <p className="text-sm text-gray-500">
            Buy gift cards for friends, check balances, and redeem
          </p>
        </div>
        <Button onClick={() => { setShowPurchase(!showPurchase); setNewGiftCardCode(""); }}>
          <ShoppingBag className="mr-2 h-4 w-4" />
          Buy a Gift Card
        </Button>
      </div>

      {/* Purchase Gift Card */}
      {showPurchase && (
        <Card className="border-indigo-200 bg-indigo-50/30">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-lg">
              <Gift className="h-5 w-5 text-indigo-600" />
              Purchase a Gift Card
            </CardTitle>
          </CardHeader>
          <CardContent>
            {newGiftCardCode ? (
              <div className="space-y-4">
                <div className="rounded-lg border border-green-200 bg-green-50 p-6 text-center">
                  <Check className="mx-auto h-8 w-8 text-green-600" />
                  <p className="mt-2 text-lg font-semibold text-green-800">
                    Gift Card Purchased!
                  </p>
                  <p className="mt-1 text-sm text-green-600">
                    {recipientEmail
                      ? `A gift card email has been sent to the recipient.`
                      : `Share this code with the recipient.`}
                  </p>
                  <div className="mx-auto mt-4 flex max-w-xs items-center justify-center gap-2">
                    <code className="rounded-lg bg-white px-4 py-3 font-mono text-xl font-bold tracking-widest text-gray-900 shadow-sm">
                      {newGiftCardCode}
                    </code>
                    <button
                      onClick={() => {
                        navigator.clipboard.writeText(newGiftCardCode);
                        toast.success("Code copied!");
                      }}
                      className="rounded-lg bg-white p-2 text-gray-500 shadow-sm hover:text-indigo-600"
                    >
                      <Copy className="h-5 w-5" />
                    </button>
                  </div>
                </div>
                <div className="flex justify-center gap-3">
                  <Button
                    variant="outline"
                    onClick={() => {
                      setNewGiftCardCode("");
                    }}
                  >
                    Buy Another
                  </Button>
                  <Button
                    variant="outline"
                    onClick={() => {
                      setShowPurchase(false);
                      setNewGiftCardCode("");
                    }}
                  >
                    Done
                  </Button>
                </div>
              </div>
            ) : (
              <form onSubmit={handlePurchase} className="space-y-4">
                <div>
                  <Label htmlFor="gc-amount">Amount</Label>
                  <div className="relative mt-1">
                    <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-gray-400">
                      $
                    </span>
                    <Input
                      id="gc-amount"
                      type="number"
                      min="5"
                      step="0.01"
                      placeholder="25.00"
                      value={purchaseAmount}
                      onChange={(e) => setPurchaseAmount(e.target.value)}
                      className="pl-7"
                      required
                    />
                  </div>
                  <p className="mt-1 text-xs text-gray-400">Minimum $5.00</p>
                </div>

                <div className="grid gap-4 sm:grid-cols-2">
                  <div>
                    <Label htmlFor="gc-recipient-name">Recipient Name</Label>
                    <Input
                      id="gc-recipient-name"
                      placeholder="Jane Smith"
                      value={recipientName}
                      onChange={(e) => setRecipientName(e.target.value)}
                    />
                  </div>
                  <div>
                    <Label htmlFor="gc-recipient-email">
                      Recipient Email <span className="text-red-500">*</span>
                    </Label>
                    <Input
                      id="gc-recipient-email"
                      type="email"
                      required
                      placeholder="jane@example.com"
                      value={recipientEmail}
                      onChange={(e) => setRecipientEmail(e.target.value)}
                    />
                    <p className="mt-1 text-xs text-gray-400">
                      The gift card code is emailed here.
                    </p>
                  </div>
                </div>

                <div>
                  <Label htmlFor="gc-message">Personal Message (optional)</Label>
                  <textarea
                    id="gc-message"
                    rows={3}
                    placeholder="Happy birthday! Enjoy some yoga classes on me..."
                    value={personalMessage}
                    onChange={(e) => setPersonalMessage(e.target.value)}
                    className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                  />
                </div>

                <div className="flex gap-3">
                  <Button type="submit" disabled={purchaseMutation.isPending}>
                    {purchaseMutation.isPending ? (
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    ) : (
                      <Send className="mr-2 h-4 w-4" />
                    )}
                    Purchase Gift Card
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => setShowPurchase(false)}
                  >
                    Cancel
                  </Button>
                </div>
              </form>
            )}
          </CardContent>
        </Card>
      )}

      {/* Check Balance */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-lg">
            <Search className="h-5 w-5 text-indigo-600" />
            Check Gift Card Balance
          </CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleCheckBalance} className="flex gap-3">
            <input
              type="text"
              placeholder="Enter gift card code"
              value={balanceCode}
              onChange={(e) => {
                setBalanceCode(e.target.value.toUpperCase());
                setBalanceResult(null);
              }}
              className="flex-1 rounded-md border border-gray-300 px-3 py-2 font-mono text-sm uppercase tracking-wider focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            />
            <Button type="submit" disabled={checkBalanceMutation.isPending}>
              {checkBalanceMutation.isPending ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Search className="mr-2 h-4 w-4" />
              )}
              Check
            </Button>
          </form>

          {balanceResult && (
            <div className="mt-4 rounded-lg border border-indigo-200 bg-indigo-50 p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="font-mono text-sm font-medium text-gray-600">
                    {balanceResult.code}
                  </p>
                  <p className="mt-1 text-2xl font-bold text-indigo-700">
                    {fmtCents(balanceResult.balance_cents)}
                  </p>
                  <p className="text-xs text-gray-500">
                    Original value:{" "}
                    {fmtCents(balanceResult.initial_amount_cents)}
                  </p>
                </div>
                <div className="text-right">
                  <StatusBadge status={balanceResult.status} />
                  {balanceResult.expires_at && (
                    <p className="mt-1 text-xs text-gray-400">
                      Expires{" "}
                      {format(
                        new Date(balanceResult.expires_at),
                        "MMM d, yyyy"
                      )}
                    </p>
                  )}
                </div>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Redeem */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-lg">
            <Gift className="h-5 w-5 text-indigo-600" />
            Redeem Gift Card
          </CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleRedeem} className="space-y-4">
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">
                Gift Card Code
              </label>
              <input
                type="text"
                placeholder="Enter gift card code"
                value={redeemCode}
                onChange={(e) => setRedeemCode(e.target.value.toUpperCase())}
                className="w-full rounded-md border border-gray-300 px-3 py-2 font-mono text-sm uppercase tracking-wider focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
            </div>

            <div>
              <div className="mb-2 flex items-center gap-2">
                <input
                  type="checkbox"
                  id="useFullBalance"
                  checked={useFullBalance}
                  onChange={(e) => setUseFullBalance(e.target.checked)}
                  className="h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                />
                <label
                  htmlFor="useFullBalance"
                  className="text-sm font-medium text-gray-700"
                >
                  Use full balance
                </label>
              </div>
              {!useFullBalance && (
                <div className="relative">
                  <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-gray-400">
                    $
                  </span>
                  <input
                    type="number"
                    min="0.01"
                    step="0.01"
                    placeholder="25.00"
                    value={redeemAmount}
                    onChange={(e) => setRedeemAmount(e.target.value)}
                    className="w-full rounded-md border border-gray-300 py-2 pl-7 pr-3 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                  />
                </div>
              )}
            </div>

            <Button
              type="submit"
              disabled={redeemMutation.isPending}
              className="w-full sm:w-auto"
            >
              {redeemMutation.isPending ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Check className="mr-2 h-4 w-4" />
              )}
              Redeem Gift Card
            </Button>
          </form>
        </CardContent>
      </Card>

      {/* My Gift Cards */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">My Gift Cards</CardTitle>
        </CardHeader>
        <CardContent>
          {myCardsLoading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-6 w-6 animate-spin text-indigo-600" />
            </div>
          ) : !myGiftCards?.length ? (
            <div className="rounded-lg border border-dashed border-gray-300 py-8 text-center">
              <Gift className="mx-auto h-8 w-8 text-gray-300" />
              <p className="mt-2 text-sm text-gray-500">
                No gift cards to show — buy one above, or wait for one
                to be sent to your email.
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              {myGiftCards.map((gc: GiftCard) => (
                <div
                  key={gc.id}
                  className="flex items-center justify-between rounded-lg border border-gray-200 p-4"
                >
                  <div>
                    <div className="flex items-center gap-2">
                      <p className="font-mono text-sm font-medium text-gray-900">
                        {gc.code}
                      </p>
                      {gc.relationship === "received" && (
                        <span className="inline-flex items-center rounded-full bg-purple-100 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider text-purple-700">
                          Received
                        </span>
                      )}
                      {gc.relationship === "purchased" && (
                        <span className="inline-flex items-center rounded-full bg-blue-100 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider text-blue-700">
                          Purchased
                        </span>
                      )}
                      {gc.relationship === "purchased_and_received" && (
                        <span className="inline-flex items-center rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider text-emerald-700">
                          Self-purchase
                        </span>
                      )}
                    </div>
                    <p className="mt-0.5 text-xs text-gray-500">
                      {gc.relationship === "received"
                        ? `From: ${gc.purchaser_name || "a member"}`
                        : gc.recipient_name
                          ? `To: ${gc.recipient_name}`
                          : gc.recipient_email
                            ? `To: ${gc.recipient_email}`
                            : "No recipient"}
                      {" | "}
                      {format(new Date(gc.created_at), "MMM d, yyyy")}
                    </p>
                  </div>
                  <div className="text-right">
                    <p className="text-sm font-medium text-gray-900">
                      {fmtCents(gc.balance_cents)}
                    </p>
                    <p className="text-xs text-gray-400">
                      of {fmtCents(gc.initial_amount_cents ?? gc.amount_cents)}
                    </p>
                    <StatusBadge status={gc.status} />
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
