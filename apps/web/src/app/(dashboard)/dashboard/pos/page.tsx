"use client";

import { useState, useMemo } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  ShoppingCart,
  Plus,
  Minus,
  Trash2,
  Loader2,
  Receipt,
  DollarSign,
  X,
  Search,
  Clock,
  Send,
  CreditCard,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import toast from "react-hot-toast";
import {
  retailApi,
  type Product,
  type POSTransaction,
  type DailySummary,
} from "@/lib/retail-api";
import { membersApi, type Member } from "@/lib/members-api";
import { POSChargeModal } from "@/components/payments/pos-charge-modal";

// ── Helpers ──────────────────────────────────────────────────────────────────

function fmtCents(cents: number) {
  return `$${(cents / 100).toFixed(2)}`;
}

function fmtDate(iso: string) {
  return new Date(iso).toLocaleDateString([], {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function fmtTime(iso: string) {
  return new Date(iso).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });
}

function todayISO() {
  return new Date().toISOString().slice(0, 10);
}

function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    pending: "bg-yellow-100 text-yellow-800",
    completed: "bg-green-100 text-green-800",
    refunded: "bg-red-100 text-red-800",
    voided: "bg-gray-100 text-gray-800",
  };
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${colors[status] || "bg-gray-100 text-gray-800"}`}
    >
      {status}
    </span>
  );
}

// ── Types ────────────────────────────────────────────────────────────────────

interface CartItem {
  product: Product;
  quantity: number;
}

// ── Tab Config ───────────────────────────────────────────────────────────────

const tabs = [
  { key: "sales", label: "Sales", icon: ShoppingCart },
  { key: "pending", label: "Pending Orders", icon: Clock },
  { key: "summary", label: "Daily Summary", icon: DollarSign },
] as const;

type TabKey = (typeof tabs)[number]["key"];

// ── Main Page ────────────────────────────────────────────────────────────────

export default function POSPage() {
  const [activeTab, setActiveTab] = useState<TabKey>("sales");

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Point of Sale</h1>
        <p className="text-gray-500">Process sales and view daily summaries</p>
      </div>

      <div className="flex gap-1 rounded-lg bg-gray-100 p-1">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`flex items-center gap-2 rounded-md px-4 py-2 text-sm font-medium transition-colors ${
              activeTab === tab.key
                ? "bg-white text-gray-900 shadow-sm"
                : "text-gray-600 hover:text-gray-900"
            }`}
          >
            <tab.icon className="h-4 w-4" />
            {tab.label}
          </button>
        ))}
      </div>

      {activeTab === "sales" && <SalesTab />}
      {activeTab === "pending" && <PendingOrdersTab />}
      {activeTab === "summary" && <SummaryTab />}
    </div>
  );
}

// ── Sales Tab ────────────────────────────────────────────────────────────────

function SalesTab() {
  const queryClient = useQueryClient();
  const [cart, setCart] = useState<CartItem[]>([]);
  const [search, setSearch] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");
  // Default to "card" — cash is still selectable for studios that
  // accept it, but shouldn't be the pre-filled choice anywhere.
  const [paymentMethod, setPaymentMethod] = useState("card");
  const [memberSearch, setMemberSearch] = useState("");
  const [selectedMemberId, setSelectedMemberId] = useState<string | null>(null);
  const [selectedMemberName, setSelectedMemberName] = useState("");
  const [notes, setNotes] = useState("");
  const [giftCardCode, setGiftCardCode] = useState("");
  const [receiptTxn, setReceiptTxn] = useState<POSTransaction | null>(null);
  const [terminalCharge, setTerminalCharge] = useState<{
    amount_cents: number;
    description: string;
    member: { id: string; first_name?: string; last_name?: string };
    pos_txn_id: string;
  } | null>(null);

  const { data: products, isLoading: productsLoading } = useQuery({
    queryKey: ["retail-products", categoryFilter, search],
    queryFn: () =>
      retailApi
        .listProducts({
          category: categoryFilter || undefined,
          search: search || undefined,
        })
        .then((r) => r.data.data),
  });

  const { data: members } = useQuery({
    queryKey: ["member-search", memberSearch],
    queryFn: () =>
      membersApi.list({ search: memberSearch, limit: 5 }).then((r) => r.data),
    enabled: memberSearch.length >= 2,
  });

  const saleMut = useMutation({
    mutationFn: () =>
      retailApi.createTransaction({
        items: cart.map((c) => ({
          product_id: c.product.id,
          quantity: c.quantity,
        })),
        payment_method: paymentMethod,
        member_id: selectedMemberId || undefined,
        notes: notes || undefined,
        gift_card_code: paymentMethod === "gift_card" ? giftCardCode.trim() : undefined,
      }),
    onSuccess: (resp) => {
      const txn = resp.data.data;
      // Card / stripe payment methods → open Square Terminal modal so the
      // customer taps on a paired phone or device. The retail transaction
      // is already recorded (so inventory + the row exist); Terminal
      // captures the actual money.
      if ((paymentMethod === "card" || paymentMethod === "stripe") && selectedMemberId) {
        setTerminalCharge({
          amount_cents: cartTotals.total,
          description: cart.map((c) => `${c.product.name} x${c.quantity}`).join(", ").slice(0, 200) || "POS sale",
          member: {
            id: selectedMemberId,
            first_name: selectedMemberName.split(" ")[0],
            last_name: selectedMemberName.split(" ").slice(1).join(" "),
          },
          pos_txn_id: txn.id,
        });
      } else if (txn.checkout_url && paymentMethod !== "send_payment_link") {
        window.open(txn.checkout_url, "_blank");
      }
      setReceiptTxn(txn);
      setCart([]);
      setNotes("");
      setGiftCardCode("");
      setSelectedMemberId(null);
      setSelectedMemberName("");
      setMemberSearch("");
      queryClient.invalidateQueries({ queryKey: ["retail-products"] });
    },
  });

  const addToCart = (product: Product) => {
    setCart((prev) => {
      const existing = prev.find((c) => c.product.id === product.id);
      if (existing) {
        return prev.map((c) =>
          c.product.id === product.id
            ? { ...c, quantity: c.quantity + 1 }
            : c
        );
      }
      return [...prev, { product, quantity: 1 }];
    });
  };

  const updateQty = (productId: string, delta: number) => {
    setCart((prev) =>
      prev
        .map((c) =>
          c.product.id === productId
            ? { ...c, quantity: Math.max(0, c.quantity + delta) }
            : c
        )
        .filter((c) => c.quantity > 0)
    );
  };

  const removeFromCart = (productId: string) => {
    setCart((prev) => prev.filter((c) => c.product.id !== productId));
  };

  const cartTotals = useMemo(() => {
    let subtotal = 0;
    let tax = 0;
    for (const item of cart) {
      const lineSubtotal = item.product.price_cents * item.quantity;
      const lineTax = Math.round(lineSubtotal * item.product.tax_rate);
      subtotal += lineSubtotal;
      tax += lineTax;
    }
    return { subtotal, tax, total: subtotal + tax };
  }, [cart]);

  const categories = ["retail", "beverages", "rental", "merchandise"];

  return (
    <>
      {/* Receipt Modal */}
      {receiptTxn && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="w-full max-w-md rounded-lg bg-white p-6 shadow-xl">
            <div className="mb-4 flex items-center justify-between">
              <h3 className="text-lg font-bold">
                {receiptTxn.payment_link_emailed ? "Payment Link Sent" : "Sale Complete"}
              </h3>
              <button onClick={() => setReceiptTxn(null)}>
                <X className="h-5 w-5 text-gray-400" />
              </button>
            </div>
            <div className="space-y-2 border-b pb-4 text-sm">
              <p className="text-gray-500">
                {fmtDate(receiptTxn.created_at)} at{" "}
                {fmtTime(receiptTxn.created_at)}
              </p>
              <p>
                Payment: <span className="font-medium">{receiptTxn.payment_method === "send_payment_link" ? "Payment Link Emailed" : receiptTxn.payment_method}</span>
              </p>
              {receiptTxn.payment_link_emailed && (
                <p className="rounded bg-green-50 px-2 py-1 text-xs text-green-700">
                  Payment link sent to member's email. You'll be notified when they pay.
                </p>
              )}
              {receiptTxn.member_first_name && (
                <p>
                  Member:{" "}
                  <span className="font-medium">
                    {receiptTxn.member_first_name} {receiptTxn.member_last_name}
                  </span>
                </p>
              )}
            </div>
            {receiptTxn.line_items && (
              <div className="space-y-1 border-b py-3 text-sm">
                {receiptTxn.line_items.map((li) => (
                  <div key={li.id} className="flex justify-between">
                    <span>
                      {li.product_name} x{li.quantity}
                    </span>
                    <span>{fmtCents(li.total_cents)}</span>
                  </div>
                ))}
              </div>
            )}
            <div className="space-y-1 pt-3 text-sm">
              <div className="flex justify-between">
                <span>Subtotal</span>
                <span>{fmtCents(receiptTxn.subtotal_cents)}</span>
              </div>
              <div className="flex justify-between">
                <span>Tax</span>
                <span>{fmtCents(receiptTxn.tax_cents)}</span>
              </div>
              <div className="flex justify-between text-base font-bold">
                <span>Total</span>
                <span>{fmtCents(receiptTxn.total_cents)}</span>
              </div>
            </div>
            <button
              onClick={() => setReceiptTxn(null)}
              className="mt-4 w-full rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700"
            >
              Done
            </button>
          </div>
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Product Grid */}
        <div className="lg:col-span-2 space-y-4">
          {/* Search + Filter */}
          <div className="flex gap-3">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-2.5 h-4 w-4 text-gray-400" />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search products..."
                className="w-full rounded-md border border-gray-300 pl-9 pr-3 py-2 text-sm"
              />
            </div>
            <select
              value={categoryFilter}
              onChange={(e) => setCategoryFilter(e.target.value)}
              className="rounded-md border border-gray-300 px-3 py-2 text-sm"
            >
              <option value="">All Categories</option>
              {categories.map((cat) => (
                <option key={cat} value={cat}>
                  {cat.charAt(0).toUpperCase() + cat.slice(1)}
                </option>
              ))}
            </select>
          </div>

          {/* Products */}
          {productsLoading ? (
            <div className="flex justify-center py-12">
              <Loader2 className="h-8 w-8 animate-spin text-gray-300" />
            </div>
          ) : !products || products.length === 0 ? (
            <p className="py-12 text-center text-sm text-gray-400">
              No products found. Add products in the Inventory page.
            </p>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {products.map((product) => (
                <button
                  key={product.id}
                  onClick={() => addToCart(product)}
                  className="rounded-lg border border-gray-200 p-3 text-left transition-colors hover:border-indigo-300 hover:bg-indigo-50"
                >
                  <p className="font-medium text-gray-900">{product.name}</p>
                  <div className="mt-1 flex items-center justify-between">
                    <span className="text-sm font-semibold text-indigo-600">
                      {fmtCents(product.price_cents)}
                    </span>
                    <span className="text-xs text-gray-400">
                      {product.quantity_on_hand != null
                        ? `${product.quantity_on_hand} in stock`
                        : ""}
                    </span>
                  </div>
                  {product.sku && (
                    <p className="mt-0.5 text-xs text-gray-400">{product.sku}</p>
                  )}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Cart Sidebar */}
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <ShoppingCart className="h-5 w-5" />
                Cart ({cart.length})
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {cart.length === 0 ? (
                <p className="py-4 text-center text-sm text-gray-400">
                  Tap a product to add it
                </p>
              ) : (
                <div className="space-y-3">
                  {cart.map((item) => (
                    <div
                      key={item.product.id}
                      className="flex items-center gap-2 rounded-md border border-gray-100 p-2"
                    >
                      <div className="flex-1 min-w-0">
                        <p className="truncate text-sm font-medium">
                          {item.product.name}
                        </p>
                        <p className="text-xs text-gray-500">
                          {fmtCents(item.product.price_cents)} ea
                        </p>
                      </div>
                      <div className="flex items-center gap-1">
                        <button
                          onClick={() => updateQty(item.product.id, -1)}
                          className="rounded p-1 hover:bg-gray-100"
                        >
                          <Minus className="h-3 w-3" />
                        </button>
                        <span className="w-6 text-center text-sm font-medium">
                          {item.quantity}
                        </span>
                        <button
                          onClick={() => updateQty(item.product.id, 1)}
                          className="rounded p-1 hover:bg-gray-100"
                        >
                          <Plus className="h-3 w-3" />
                        </button>
                        <button
                          onClick={() => removeFromCart(item.product.id)}
                          className="ml-1 rounded p-1 text-red-400 hover:bg-red-50"
                        >
                          <Trash2 className="h-3 w-3" />
                        </button>
                      </div>
                      <p className="w-16 text-right text-sm font-medium">
                        {fmtCents(item.product.price_cents * item.quantity)}
                      </p>
                    </div>
                  ))}
                </div>
              )}

              {/* Totals */}
              {cart.length > 0 && (
                <div className="space-y-1 border-t pt-3 text-sm">
                  <div className="flex justify-between text-gray-600">
                    <span>Subtotal</span>
                    <span>{fmtCents(cartTotals.subtotal)}</span>
                  </div>
                  <div className="flex justify-between text-gray-600">
                    <span>Tax</span>
                    <span>{fmtCents(cartTotals.tax)}</span>
                  </div>
                  <div className="flex justify-between text-base font-bold">
                    <span>Total</span>
                    <span>{fmtCents(cartTotals.total)}</span>
                  </div>
                </div>
              )}

              {/* Member lookup */}
              <div>
                <label className="mb-1 block text-xs font-medium text-gray-500">
                  Member (optional)
                </label>
                {selectedMemberId ? (
                  <div className="flex items-center justify-between rounded-md border border-gray-200 px-3 py-2 text-sm">
                    <span>{selectedMemberName}</span>
                    <button
                      onClick={() => {
                        setSelectedMemberId(null);
                        setSelectedMemberName("");
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
                      value={memberSearch}
                      onChange={(e) => setMemberSearch(e.target.value)}
                      placeholder="Search members..."
                      className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
                    />
                    {members && members.length > 0 && memberSearch.length >= 2 && (
                      <div className="absolute z-10 mt-1 w-full rounded-md border border-gray-200 bg-white shadow-lg">
                        {members.map((m: Member) => (
                          <button
                            key={m.id}
                            onClick={() => {
                              setSelectedMemberId(m.id);
                              setSelectedMemberName(
                                `${m.first_name} ${m.last_name}`
                              );
                              setMemberSearch("");
                            }}
                            className="block w-full px-3 py-2 text-left text-sm hover:bg-gray-50"
                          >
                            {m.first_name} {m.last_name}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>

              {/* Payment method */}
              <div>
                <label className="mb-1 block text-xs font-medium text-gray-500">
                  Payment Method
                </label>
                <select
                  value={paymentMethod}
                  onChange={(e) => setPaymentMethod(e.target.value)}
                  className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
                >
                  <option value="cash">Cash</option>
                  <option value="card">Credit / Debit Card</option>
                  <option value="send_payment_link">Send Payment Link (Email)</option>
                  <option value="gift_card">Gift Card</option>
                  <option value="check">Check</option>
                  <option value="comp">Comp</option>
                </select>
              </div>

              {paymentMethod === "gift_card" && (
                <div>
                  <label className="mb-1 block text-xs font-medium text-gray-500">
                    Gift Card Code
                  </label>
                  <input
                    type="text"
                    value={giftCardCode}
                    onChange={(e) => setGiftCardCode(e.target.value.toUpperCase())}
                    placeholder="XXXX-XXXX-XXXX-XXXX"
                    className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm font-mono tracking-wider"
                  />
                  <p className="mt-1 text-xs text-gray-400">
                    Card balance must cover the full sale total. Member must be selected.
                  </p>
                </div>
              )}

              {/* Notes */}
              <div>
                <label className="mb-1 block text-xs font-medium text-gray-500">
                  Notes
                </label>
                <input
                  type="text"
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  placeholder="Optional notes..."
                  className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
                />
              </div>

              {/* Complete Sale */}
              {paymentMethod === "send_payment_link" && !selectedMemberId && (
                <p className="text-sm text-amber-600">Select a member to send payment link</p>
              )}
              {(paymentMethod === "card" || paymentMethod === "stripe") && !selectedMemberId && (
                <p className="text-sm text-amber-600">Select a member to charge on the Square terminal</p>
              )}
              <button
                onClick={() => saleMut.mutate()}
                disabled={
                  cart.length === 0 ||
                  saleMut.isPending ||
                  ((paymentMethod === "send_payment_link" ||
                    paymentMethod === "card" ||
                    paymentMethod === "stripe") &&
                    !selectedMemberId)
                }
                className="flex w-full items-center justify-center gap-2 rounded-lg bg-green-600 px-4 py-3 text-sm font-medium text-white transition-colors hover:bg-green-700 disabled:opacity-50"
              >
                {saleMut.isPending ? (
                  <Loader2 className="h-5 w-5 animate-spin" />
                ) : (
                  <>
                    <Receipt className="h-5 w-5" />
                    {paymentMethod === "send_payment_link"
                      ? `Send Payment Link — ${fmtCents(cartTotals.total)}`
                      : paymentMethod === "card" || paymentMethod === "stripe"
                        ? `Charge on Square Terminal — ${fmtCents(cartTotals.total)}`
                        : `Complete Sale — ${fmtCents(cartTotals.total)}`}
                  </>
                )}
              </button>

              {saleMut.isError && (
                <p className="text-sm text-red-600">
                  {(saleMut.error as any)?.response?.data?.detail || (saleMut.error as Error)?.message || "Sale failed"}
                </p>
              )}
            </CardContent>
          </Card>
        </div>
      </div>

      {terminalCharge && (
        <POSChargeModal
          open={true}
          member={terminalCharge.member}
          amountCents={terminalCharge.amount_cents}
          description={terminalCharge.description}
          onClose={() => setTerminalCharge(null)}
          onSuccess={() => {
            setTerminalCharge(null);
            toast.success("Card payment captured on Square");
            queryClient.invalidateQueries({ queryKey: ["retail-products"] });
          }}
        />
      )}
    </>
  );
}

// ── Pending Orders Tab ───────────────────────────────────────────────────────

function PendingOrdersTab() {
  const queryClient = useQueryClient();

  const { data: pending, isLoading } = useQuery({
    queryKey: ["pos-pending"],
    queryFn: () => retailApi.listPendingTransactions().then((r) => r.data.data),
    refetchInterval: 30_000,
  });

  const resendMutation = useMutation({
    mutationFn: (id: string) => retailApi.resendPaymentLink(id),
    onSuccess: () => {
      toast.success("Payment link resent to member's email");
      queryClient.invalidateQueries({ queryKey: ["pos-pending"] });
    },
    onError: (err: any) => toast.error(err?.response?.data?.detail || "Failed to resend"),
  });

  const checkoutMutation = useMutation({
    mutationFn: (id: string) => retailApi.createCheckout(id),
    onSuccess: (resp) => {
      const url = resp.data.data.checkout_url;
      window.open(url, "_blank");
    },
    onError: (err: any) => toast.error(err?.response?.data?.detail || "Failed to create checkout"),
  });

  if (isLoading) {
    return (
      <div className="flex justify-center py-12">
        <Loader2 className="h-8 w-8 animate-spin text-gray-300" />
      </div>
    );
  }

  if (!pending?.length) {
    return (
      <div className="rounded-lg border border-dashed border-gray-300 py-12 text-center">
        <Clock className="mx-auto h-10 w-10 text-gray-300" />
        <p className="mt-2 text-sm text-gray-500">No pending orders</p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {pending.map((txn) => (
        <Card key={txn.id}>
          <CardContent className="flex items-center justify-between p-4">
            <div>
              <div className="flex items-center gap-2">
                <span className="font-medium text-gray-900">
                  {txn.member_first_name
                    ? `${txn.member_first_name} ${txn.member_last_name || ""}`
                    : "Walk-in"}
                </span>
                <StatusBadge status={txn.status} />
              </div>
              <div className="mt-1 text-sm text-gray-500">
                {txn.line_items?.map((li) => `${li.product_name} x${li.quantity}`).join(", ") || "Items"}
                {" — "}
                <span className="font-medium text-gray-700">{fmtCents(txn.total_cents)}</span>
              </div>
              <div className="mt-0.5 text-xs text-gray-400">
                {fmtDate(txn.created_at)} at {fmtTime(txn.created_at)}
                {txn.payment_method === "send_payment_link" && " · Payment link sent"}
              </div>
            </div>
            <div className="flex items-center gap-2">
              {txn.member_id && (
                <Button
                  size="sm"
                  variant="outline"
                  className="text-indigo-600 hover:bg-indigo-50"
                  disabled={resendMutation.isPending}
                  onClick={() => resendMutation.mutate(txn.id)}
                >
                  <Send className="mr-1 h-3.5 w-3.5" />
                  Resend Link
                </Button>
              )}
              <Button
                size="sm"
                variant="outline"
                disabled={checkoutMutation.isPending}
                onClick={() => checkoutMutation.mutate(txn.id)}
              >
                <CreditCard className="mr-1 h-3.5 w-3.5" />
                Pay In Person
              </Button>
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}


// ── Daily Summary Tab ────────────────────────────────────────────────────────

function SummaryTab() {
  const [date, setDate] = useState(todayISO());

  const { data: summary, isLoading } = useQuery({
    queryKey: ["pos-daily-summary", date],
    queryFn: () => retailApi.dailySummary(date).then((r) => r.data.data),
  });

  return (
    <div className="space-y-6">
      <div className="flex items-end gap-4">
        <div>
          <label className="mb-1 block text-xs font-medium text-gray-500">
            Date
          </label>
          <input
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
            className="rounded-md border border-gray-300 px-3 py-2 text-sm"
          />
        </div>
      </div>

      {isLoading ? (
        <div className="flex justify-center py-12">
          <Loader2 className="h-8 w-8 animate-spin text-gray-300" />
        </div>
      ) : !summary ? (
        <p className="py-8 text-center text-gray-400">No data</p>
      ) : (
        <>
          {/* Summary Cards */}
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {summary.by_method.map((m) => (
              <Card key={m.payment_method}>
                <CardContent className="p-4">
                  <p className="text-xs font-medium uppercase text-gray-500">
                    {m.payment_method}
                  </p>
                  <p className="mt-1 text-2xl font-bold">
                    {fmtCents(m.total)}
                  </p>
                  <p className="text-xs text-gray-400">
                    {m.transaction_count} transaction
                    {m.transaction_count !== 1 ? "s" : ""}
                  </p>
                </CardContent>
              </Card>
            ))}
            <Card>
              <CardContent className="p-4">
                <p className="text-xs font-medium uppercase text-gray-500">
                  Grand Total
                </p>
                <p className="mt-1 text-2xl font-bold text-indigo-600">
                  {fmtCents(summary.grand_total_cents)}
                </p>
              </CardContent>
            </Card>
          </div>

          {/* Top Products */}
          {summary.top_products.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>Top Products</CardTitle>
              </CardHeader>
              <CardContent className="p-0">
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b bg-gray-50 text-left text-xs font-medium uppercase text-gray-500">
                        <th className="px-4 py-3">Product</th>
                        <th className="px-4 py-3">Units Sold</th>
                        <th className="px-4 py-3">Revenue</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y">
                      {summary.top_products.map((p, i) => (
                        <tr key={i} className="hover:bg-gray-50">
                          <td className="px-4 py-3 font-medium">{p.name}</td>
                          <td className="px-4 py-3">{p.units_sold}</td>
                          <td className="px-4 py-3 font-medium">
                            {fmtCents(p.revenue)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
          )}
        </>
      )}
    </div>
  );
}
