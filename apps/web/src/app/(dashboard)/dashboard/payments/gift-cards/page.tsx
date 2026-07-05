"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { format } from "date-fns";
import {
  Loader2,
  Gift,
  Plus,
  Copy,
  Check,
  Ban,
  Mail,
  ChevronDown,
  ChevronRight,
  ArrowLeft,
  DollarSign,
  X,
} from "lucide-react";
import toast from "react-hot-toast";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  giftCardsApi,
  type GiftCard,
  type CreateGiftCardRequest,
} from "@/lib/gift-cards-api";
import { membersApi, type Member } from "@/lib/members-api";

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

function defaultExpiry(): string {
  const d = new Date();
  d.setFullYear(d.getFullYear() + 1);
  return d.toISOString().slice(0, 10);
}

// ── Create Gift Card Modal ───────────────────────────────────────────────────

function CreateGiftCardModal({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: (gc: GiftCard) => void;
}) {
  const [amount, setAmount] = useState("");
  const [recipientEmail, setRecipientEmail] = useState("");
  const [recipientName, setRecipientName] = useState("");
  const [purchaserName, setPurchaserName] = useState("");
  const [purchaserMemberId, setPurchaserMemberId] = useState("");
  const [purchaserMemberName, setPurchaserMemberName] = useState("");
  const [memberSearch, setMemberSearch] = useState("");
  const [personalMessage, setPersonalMessage] = useState("");
  const [expiresAt, setExpiresAt] = useState(defaultExpiry());
  const [paymentMethod, setPaymentMethod] = useState("card");
  const [createdCard, setCreatedCard] = useState<GiftCard | null>(null);
  const [copied, setCopied] = useState(false);

  const stripeMethods = ["card", "stripe", "send_payment_link"];
  const requiresMember = stripeMethods.includes(paymentMethod);

  // Live member search — same pattern as POS / private sessions /
  // assign-membership. Two characters minimum to avoid hammering the
  // API while staff is still typing the first letters of a name.
  const { data: memberMatches } = useQuery({
    queryKey: ["member-search-gift-card", memberSearch],
    queryFn: () =>
      membersApi.list({ search: memberSearch, limit: 8 }).then((r) => r.data),
    enabled: memberSearch.length >= 2 && !purchaserMemberId,
  });

  const createMutation = useMutation({
    mutationFn: (data: CreateGiftCardRequest) =>
      giftCardsApi.create(data).then((r) => r.data),
    onSuccess: (resp) => {
      // Stripe paths return a checkout URL; immediate paths return the card
      if (resp.checkout_url) {
        // Open Stripe checkout in a new tab so the staff member's
        // dashboard session stays put. The actual gift card is created
        // by the webhook when the buyer completes payment.
        window.open(resp.checkout_url, "_blank");
        toast.success("Stripe checkout opened — card will be created after payment");
        onClose();
        return;
      }
      if (resp.gift_card) {
        setCreatedCard(resp.gift_card);
        onCreated(resp.gift_card);
        toast.success(`Gift card created (${resp.payment_method})`);
      }
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: unknown } } })
        ?.response?.data?.detail;
      toast.error(typeof detail === "string" ? detail : "Failed to create gift card");
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const cents = Math.round(parseFloat(amount) * 100);
    if (!cents || cents <= 0) {
      toast.error("Please enter a valid amount");
      return;
    }
    if (requiresMember && !purchaserMemberId.trim()) {
      toast.error(
        "Card / Stripe / Send Payment Link payments require a purchaser member ID. " +
        "Use Cash / Check / Comp for non-member buyers."
      );
      return;
    }
    createMutation.mutate({
      amount_cents: cents,
      recipient_email: recipientEmail || undefined,
      recipient_name: recipientName || undefined,
      purchaser_name: purchaserName || undefined,
      personal_message: personalMessage || undefined,
      expires_at: expiresAt || undefined,
      payment_method: paymentMethod,
      purchaser_member_id: purchaserMemberId.trim() || undefined,
      success_url: requiresMember
        ? `${window.location.origin}/dashboard/payments/gift-cards?paid=1`
        : undefined,
      cancel_url: requiresMember
        ? `${window.location.origin}/dashboard/payments/gift-cards`
        : undefined,
    });
  };

  const handleCopy = () => {
    if (createdCard) {
      navigator.clipboard.writeText(createdCard.code);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="mx-4 w-full max-w-md rounded-lg bg-white shadow-xl">
        <div className="flex items-center justify-between border-b px-6 py-4">
          <h2 className="text-lg font-semibold text-gray-900">
            {createdCard ? "Gift Card Created" : "Create Gift Card"}
          </h2>
          <button
            onClick={onClose}
            className="rounded-md p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {createdCard ? (
          <div className="space-y-4 p-6">
            <div className="rounded-lg border-2 border-indigo-200 bg-indigo-50 p-6 text-center">
              <p className="mb-2 text-sm font-medium text-gray-600">
                Gift Card Code
              </p>
              <p className="font-mono text-2xl font-bold tracking-wider text-indigo-700">
                {createdCard.code}
              </p>
              <p className="mt-2 text-sm text-gray-500">
                Value: {fmtCents(createdCard.initial_amount_cents)}
              </p>
            </div>
            <Button onClick={handleCopy} className="w-full" variant="outline">
              {copied ? (
                <>
                  <Check className="mr-2 h-4 w-4 text-green-600" />
                  Copied!
                </>
              ) : (
                <>
                  <Copy className="mr-2 h-4 w-4" />
                  Copy Code
                </>
              )}
            </Button>
            <Button onClick={onClose} className="w-full">
              Done
            </Button>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4 p-6">
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">
                Amount <span className="text-red-500">*</span>
              </label>
              <div className="relative">
                <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-gray-400">
                  $
                </span>
                <input
                  type="number"
                  min="1"
                  step="0.01"
                  required
                  placeholder="50.00"
                  value={amount}
                  onChange={(e) => setAmount(e.target.value)}
                  className="w-full rounded-md border border-gray-300 py-2 pl-7 pr-3 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                />
              </div>
            </div>

            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">
                Recipient Email <span className="text-red-500">*</span>
              </label>
              <input
                type="email"
                required
                placeholder="friend@example.com"
                value={recipientEmail}
                onChange={(e) => setRecipientEmail(e.target.value)}
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
              <p className="mt-1 text-xs text-gray-400">
                The gift card code is emailed here.
              </p>
            </div>

            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">
                Recipient Name
              </label>
              <input
                type="text"
                placeholder="Jane Doe"
                value={recipientName}
                onChange={(e) => setRecipientName(e.target.value)}
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
            </div>

            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">
                Purchaser Name
              </label>
              <input
                type="text"
                placeholder="Your name"
                value={purchaserName}
                onChange={(e) => setPurchaserName(e.target.value)}
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
            </div>

            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">
                Personal Message
              </label>
              <textarea
                rows={3}
                placeholder="Happy birthday! Enjoy a yoga class on me."
                value={personalMessage}
                onChange={(e) => setPersonalMessage(e.target.value)}
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
            </div>

            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">
                Expiration Date
              </label>
              <input
                type="date"
                value={expiresAt}
                onChange={(e) => setExpiresAt(e.target.value)}
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
            </div>

            {/* Payment method — required so the studio actually
                collects money instead of just minting cards.
                Stripe paths route to checkout in a new tab; cash/check/
                comp/venmo create the row immediately and record a
                transaction with that method. */}
            <div className="rounded-md border-2 border-amber-200 bg-amber-50 p-3 space-y-3">
              <div>
                <label className="mb-1 block text-sm font-medium text-gray-700">
                  Payment Method <span className="text-red-500">*</span>
                </label>
                <select
                  value={paymentMethod}
                  onChange={(e) => setPaymentMethod(e.target.value)}
                  className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
                >
                  <option value="card">Credit / Debit Card (Stripe)</option>
                  <option value="stripe">Stripe (In-Person)</option>
                  <option value="send_payment_link">Send Payment Link (Email)</option>
                  <option value="cash">Cash</option>
                  <option value="check">Check</option>
                  <option value="venmo">Venmo</option>
                  <option value="comp">Comp (free, studio absorbs)</option>
                </select>
              </div>
              {requiresMember && (
                <div>
                  <label className="mb-1 block text-xs font-medium text-gray-700">
                    Purchaser <span className="text-red-500">*</span>
                  </label>
                  {purchaserMemberId ? (
                    <div className="flex items-center justify-between rounded-md border border-gray-300 bg-white px-3 py-2 text-sm">
                      <span>{purchaserMemberName}</span>
                      <button
                        type="button"
                        onClick={() => {
                          setPurchaserMemberId("");
                          setPurchaserMemberName("");
                          setMemberSearch("");
                        }}
                        className="text-gray-400 hover:text-gray-600"
                      >
                        <X className="h-4 w-4" />
                      </button>
                    </div>
                  ) : (
                    <div className="relative">
                      <input
                        type="text"
                        placeholder="Search members by name or email…"
                        value={memberSearch}
                        onChange={(e) => setMemberSearch(e.target.value)}
                        className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm"
                      />
                      {memberMatches && memberMatches.length > 0 && memberSearch.length >= 2 && (
                        <div className="absolute z-20 mt-1 max-h-60 w-full overflow-auto rounded-md border border-gray-200 bg-white shadow-lg">
                          {memberMatches.map((m: Member) => (
                            <button
                              key={m.id}
                              type="button"
                              onClick={() => {
                                setPurchaserMemberId(m.id);
                                setPurchaserMemberName(`${m.first_name} ${m.last_name}`);
                                setMemberSearch("");
                              }}
                              className="block w-full px-3 py-2 text-left text-sm hover:bg-gray-50"
                            >
                              <span className="font-medium">{m.first_name} {m.last_name}</span>
                              {m.email && (
                                <span className="ml-2 text-xs text-gray-500">{m.email}</span>
                              )}
                            </button>
                          ))}
                        </div>
                      )}
                      {memberMatches && memberMatches.length === 0 && memberSearch.length >= 2 && (
                        <p className="mt-1 text-xs text-gray-500">
                          No members match "{memberSearch}". For non-member buyers, use Cash / Check / Comp.
                        </p>
                      )}
                    </div>
                  )}
                  <p className="mt-1 text-xs text-gray-500">
                    Required for Stripe payment — buyer must be an existing member.
                    For non-member buyers, use Cash / Check / Comp.
                  </p>
                </div>
              )}
            </div>

            <div className="flex justify-end gap-2 pt-2">
              <Button type="button" variant="outline" onClick={onClose}>
                Cancel
              </Button>
              <Button type="submit" disabled={createMutation.isPending}>
                {createMutation.isPending ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <Plus className="mr-2 h-4 w-4" />
                )}
                {requiresMember ? "Open Stripe Checkout" : "Create Gift Card"}
              </Button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}

// ── Adjust Balance Modal ─────────────────────────────────────────────────────

function AdjustBalanceModal({
  giftCard,
  onClose,
}: {
  giftCard: GiftCard;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [amount, setAmount] = useState("");
  const [reason, setReason] = useState("");

  const adjustMutation = useMutation({
    mutationFn: () =>
      giftCardsApi
        .adjust(giftCard.id, {
          amount_cents: Math.round(parseFloat(amount) * 100),
          reason: reason || undefined,
        })
        .then((r) => r.data.data),
    onSuccess: () => {
      toast.success("Balance adjusted");
      queryClient.invalidateQueries({ queryKey: ["gift-cards"] });
      queryClient.invalidateQueries({ queryKey: ["gift-card-stats"] });
      onClose();
    },
    onError: () => toast.error("Failed to adjust balance"),
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const cents = Math.round(parseFloat(amount) * 100);
    if (!cents) {
      toast.error("Enter a valid amount (positive to add, negative to subtract)");
      return;
    }
    adjustMutation.mutate();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="mx-4 w-full max-w-sm rounded-lg bg-white shadow-xl">
        <div className="flex items-center justify-between border-b px-6 py-4">
          <h2 className="text-lg font-semibold text-gray-900">
            Adjust Balance
          </h2>
          <button
            onClick={onClose}
            className="rounded-md p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
          >
            <X className="h-5 w-5" />
          </button>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4 p-6">
          <p className="text-sm text-gray-600">
            Current balance:{" "}
            <span className="font-medium">
              {fmtCents(giftCard.balance_cents)}
            </span>
          </p>
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">
              Adjustment Amount
            </label>
            <div className="relative">
              <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-gray-400">
                $
              </span>
              <input
                type="number"
                step="0.01"
                required
                placeholder="10.00 or -5.00"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                className="w-full rounded-md border border-gray-300 py-2 pl-7 pr-3 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
            </div>
            <p className="mt-1 text-xs text-gray-400">
              Positive to add, negative to subtract
            </p>
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">
              Reason
            </label>
            <input
              type="text"
              placeholder="Optional reason"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            />
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="outline" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={adjustMutation.isPending}>
              {adjustMutation.isPending && (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              )}
              Adjust
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ── Main Page ────────────────────────────────────────────────────────────────

export default function GiftCardsPage() {
  const queryClient = useQueryClient();
  const [showCreate, setShowCreate] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [adjustCard, setAdjustCard] = useState<GiftCard | null>(null);

  const { data: giftCards, isLoading } = useQuery({
    queryKey: ["gift-cards"],
    queryFn: () => giftCardsApi.list({ limit: 200 }).then((r) => r.data),
  });

  const { data: stats, isLoading: statsLoading } = useQuery({
    queryKey: ["gift-card-stats"],
    queryFn: () => giftCardsApi.getStats().then((r) => r.data),
  });

  const voidMutation = useMutation({
    mutationFn: (id: string) => giftCardsApi.void(id),
    onSuccess: () => {
      toast.success("Gift card voided");
      queryClient.invalidateQueries({ queryKey: ["gift-cards"] });
      queryClient.invalidateQueries({ queryKey: ["gift-card-stats"] });
    },
    onError: () => toast.error("Failed to void gift card"),
  });

  const resendMutation = useMutation({
    mutationFn: (id: string) => giftCardsApi.resend(id),
    onSuccess: () => toast.success("Gift card email resent"),
    onError: () => toast.error("Failed to resend email"),
  });

  const handleVoid = (gc: GiftCard) => {
    if (confirm(`Void gift card ${gc.code}? This cannot be undone.`)) {
      voidMutation.mutate(gc.id);
    }
  };

  const toggleExpand = (id: string) => {
    setExpandedId(expandedId === id ? null : id);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <Link
            href="/dashboard/payments"
            className="rounded-md p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
          >
            <ArrowLeft className="h-5 w-5" />
          </Link>
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Gift Cards</h1>
            <p className="text-sm text-gray-500">
              Issue and manage gift cards for your studio
            </p>
          </div>
        </div>
        <Button onClick={() => setShowCreate(true)}>
          <Plus className="mr-1 h-4 w-4" />
          Create Gift Card
        </Button>
      </div>

      {/* Stats */}
      <div className="grid gap-4 sm:grid-cols-3">
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-gray-500">
                  Total Issued
                </p>
                <p className="mt-1 text-2xl font-bold text-gray-900">
                  {statsLoading ? (
                    <Loader2 className="h-5 w-5 animate-spin" />
                  ) : (
                    fmtCents(stats?.total_issued_cents ?? 0)
                  )}
                </p>
              </div>
              <div className="rounded-full bg-indigo-100 p-2">
                <Gift className="h-5 w-5 text-indigo-600" />
              </div>
            </div>
            <p className="mt-2 text-xs text-gray-400">
              {stats?.total_count ?? 0} gift cards
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-gray-500">
                  Total Redeemed
                </p>
                <p className="mt-1 text-2xl font-bold text-gray-900">
                  {statsLoading ? (
                    <Loader2 className="h-5 w-5 animate-spin" />
                  ) : (
                    fmtCents(stats?.total_redeemed_cents ?? 0)
                  )}
                </p>
              </div>
              <div className="rounded-full bg-blue-100 p-2">
                <DollarSign className="h-5 w-5 text-blue-600" />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-gray-500">
                  Outstanding Balance
                </p>
                <p className="mt-1 text-2xl font-bold text-gray-900">
                  {statsLoading ? (
                    <Loader2 className="h-5 w-5 animate-spin" />
                  ) : (
                    fmtCents(stats?.outstanding_balance_cents ?? 0)
                  )}
                </p>
              </div>
              <div className="rounded-full bg-green-100 p-2">
                <Gift className="h-5 w-5 text-green-600" />
              </div>
            </div>
            <p className="mt-2 text-xs text-gray-400">
              {stats?.active_count ?? 0} active
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Gift Cards Table */}
      {isLoading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="h-8 w-8 animate-spin text-indigo-600" />
        </div>
      ) : !giftCards?.length ? (
        <Card>
          <CardContent className="py-12 text-center">
            <Gift className="mx-auto h-10 w-10 text-gray-300" />
            <p className="mt-3 text-sm text-gray-500">
              No gift cards yet. Create your first one!
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="w-8 px-4 py-3" />
                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                  Code
                </th>
                <th className="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-gray-500">
                  Amount
                </th>
                <th className="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-gray-500">
                  Balance
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                  Status
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                  Recipient
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                  Created
                </th>
                <th className="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-gray-500">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {giftCards.map((gc) => (
                <>
                  <tr
                    key={gc.id}
                    className="cursor-pointer hover:bg-gray-50"
                    onClick={() => toggleExpand(gc.id)}
                  >
                    <td className="px-4 py-3">
                      {expandedId === gc.id ? (
                        <ChevronDown className="h-4 w-4 text-gray-400" />
                      ) : (
                        <ChevronRight className="h-4 w-4 text-gray-400" />
                      )}
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 font-mono text-sm font-medium text-gray-900">
                      {gc.code}
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 text-right text-sm text-gray-600">
                      {fmtCents(gc.initial_amount_cents)}
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 text-right text-sm font-medium text-gray-900">
                      {fmtCents(gc.balance_cents)}
                    </td>
                    <td className="whitespace-nowrap px-4 py-3">
                      <StatusBadge status={gc.status} />
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 text-sm text-gray-600">
                      {gc.recipient_name || gc.recipient_email || "—"}
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 text-sm text-gray-500">
                      {format(new Date(gc.created_at), "MMM d, yyyy")}
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 text-right">
                      <div
                        className="flex items-center justify-end gap-1"
                        onClick={(e) => e.stopPropagation()}
                      >
                        {gc.status === "active" && (
                          <>
                            <button
                              onClick={() => setAdjustCard(gc)}
                              className="rounded p-1.5 text-gray-400 hover:bg-gray-100 hover:text-indigo-600"
                              title="Adjust balance"
                            >
                              <DollarSign className="h-4 w-4" />
                            </button>
                            <button
                              onClick={() => handleVoid(gc)}
                              className="rounded p-1.5 text-gray-400 hover:bg-gray-100 hover:text-red-600"
                              title="Void gift card"
                            >
                              <Ban className="h-4 w-4" />
                            </button>
                          </>
                        )}
                        {gc.recipient_email && (
                          <button
                            onClick={() => resendMutation.mutate(gc.id)}
                            className="rounded p-1.5 text-gray-400 hover:bg-gray-100 hover:text-indigo-600"
                            title="Resend email"
                          >
                            <Mail className="h-4 w-4" />
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                  {expandedId === gc.id && (
                    <tr key={`${gc.id}-details`}>
                      <td colSpan={8} className="bg-gray-50 px-8 py-4">
                        <div className="space-y-3">
                          <div className="grid gap-4 text-sm sm:grid-cols-3">
                            <div>
                              <p className="text-xs font-medium text-gray-400">
                                Purchaser
                              </p>
                              <p className="text-gray-700">
                                {gc.purchaser_name || "—"}
                              </p>
                            </div>
                            <div>
                              <p className="text-xs font-medium text-gray-400">
                                Recipient Email
                              </p>
                              <p className="text-gray-700">
                                {gc.recipient_email || "—"}
                              </p>
                            </div>
                            <div>
                              <p className="text-xs font-medium text-gray-400">
                                Expires
                              </p>
                              <p className="text-gray-700">
                                {gc.expires_at
                                  ? format(
                                      new Date(gc.expires_at),
                                      "MMM d, yyyy"
                                    )
                                  : "Never"}
                              </p>
                            </div>
                          </div>
                          {gc.personal_message && (
                            <div>
                              <p className="text-xs font-medium text-gray-400">
                                Message
                              </p>
                              <p className="text-sm italic text-gray-600">
                                &ldquo;{gc.personal_message}&rdquo;
                              </p>
                            </div>
                          )}
                          {gc.redemptions && gc.redemptions.length > 0 ? (
                            <div>
                              <p className="mb-2 text-xs font-medium text-gray-400">
                                Redemption History
                              </p>
                              <div className="space-y-1">
                                {gc.redemptions.map((r) => (
                                  <div
                                    key={r.id}
                                    className="flex items-center justify-between rounded bg-white px-3 py-2 text-sm"
                                  >
                                    <span className="text-gray-600">
                                      {r.redeemed_by_name || "Member"} redeemed{" "}
                                      {fmtCents(r.amount_cents)}
                                    </span>
                                    <span className="text-xs text-gray-400">
                                      {format(
                                        new Date(r.created_at),
                                        "MMM d, yyyy h:mm a"
                                      )}
                                    </span>
                                  </div>
                                ))}
                              </div>
                            </div>
                          ) : (
                            <p className="text-xs text-gray-400">
                              No redemptions yet
                            </p>
                          )}
                        </div>
                      </td>
                    </tr>
                  )}
                </>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Modals */}
      {showCreate && (
        <CreateGiftCardModal
          onClose={() => setShowCreate(false)}
          onCreated={() => {
            queryClient.invalidateQueries({ queryKey: ["gift-cards"] });
            queryClient.invalidateQueries({ queryKey: ["gift-card-stats"] });
          }}
        />
      )}

      {adjustCard && (
        <AdjustBalanceModal
          giftCard={adjustCard}
          onClose={() => setAdjustCard(null)}
        />
      )}
    </div>
  );
}
