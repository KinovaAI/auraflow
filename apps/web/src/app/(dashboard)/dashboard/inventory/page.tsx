"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Package,
  Boxes,
  History,
  Plus,
  Loader2,
  AlertTriangle,
  X,
} from "lucide-react";
import {
  retailApi,
  type Product,
  type InventoryItem,
  type InventoryTransaction,
} from "@/lib/retail-api";

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

// ── Tab Config ───────────────────────────────────────────────────────────────

const tabs = [
  { key: "products", label: "Products", icon: Package },
  { key: "stock", label: "Stock Levels", icon: Boxes },
  { key: "history", label: "History", icon: History },
] as const;

type TabKey = (typeof tabs)[number]["key"];

// ── Main Page ────────────────────────────────────────────────────────────────

export default function InventoryPage() {
  const [activeTab, setActiveTab] = useState<TabKey>("products");

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Inventory</h1>
        <p className="text-gray-500">
          Manage products, stock levels, and inventory history
        </p>
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

      {activeTab === "products" && <ProductsTab />}
      {activeTab === "stock" && <StockTab />}
      {activeTab === "history" && <HistoryTab />}
    </div>
  );
}

// ── Products Tab ─────────────────────────────────────────────────────────────

function ProductsTab() {
  const queryClient = useQueryClient();
  const [showAdd, setShowAdd] = useState(false);
  const [editProduct, setEditProduct] = useState<Product | null>(null);

  const { data: products, isLoading } = useQuery({
    queryKey: ["retail-products-all"],
    queryFn: () =>
      retailApi.listProducts({ active_only: false }).then((r) => r.data.data),
  });

  const deleteMut = useMutation({
    mutationFn: (id: string) => retailApi.deleteProduct(id),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["retail-products-all"] }),
  });

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <button
          onClick={() => setShowAdd(true)}
          className="flex items-center gap-2 rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700"
        >
          <Plus className="h-4 w-4" />
          Add Product
        </button>
      </div>

      {/* Add/Edit Modal */}
      {(showAdd || editProduct) && (
        <ProductModal
          product={editProduct}
          onClose={() => {
            setShowAdd(false);
            setEditProduct(null);
          }}
          onSaved={() => {
            setShowAdd(false);
            setEditProduct(null);
            queryClient.invalidateQueries({ queryKey: ["retail-products-all"] });
          }}
        />
      )}

      <Card>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="flex justify-center py-8">
              <Loader2 className="h-6 w-6 animate-spin text-gray-300" />
            </div>
          ) : !products || products.length === 0 ? (
            <p className="py-8 text-center text-sm text-gray-400">
              No products yet. Click &ldquo;Add Product&rdquo; to get started.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-gray-50 text-left text-xs font-medium uppercase text-gray-500">
                    <th className="px-4 py-3">Name</th>
                    <th className="px-4 py-3">SKU</th>
                    <th className="px-4 py-3">Category</th>
                    <th className="px-4 py-3">Price</th>
                    <th className="px-4 py-3">Cost</th>
                    <th className="px-4 py-3">Tax</th>
                    <th className="px-4 py-3">Stock</th>
                    <th className="px-4 py-3">Status</th>
                    <th className="px-4 py-3">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {products.map((p) => (
                    <tr key={p.id} className="hover:bg-gray-50">
                      <td className="px-4 py-3 font-medium">{p.name}</td>
                      <td className="px-4 py-3 text-gray-500">
                        {p.sku || "—"}
                      </td>
                      <td className="px-4 py-3">
                        <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs">
                          {p.category}
                        </span>
                      </td>
                      <td className="px-4 py-3">{fmtCents(p.price_cents)}</td>
                      <td className="px-4 py-3 text-gray-500">
                        {fmtCents(p.cost_cents)}
                      </td>
                      <td className="px-4 py-3 text-gray-500">
                        {(p.tax_rate * 100).toFixed(1)}%
                      </td>
                      <td className="px-4 py-3">
                        {p.quantity_on_hand != null ? (
                          <span
                            className={
                              p.reorder_point != null &&
                              p.quantity_on_hand <= p.reorder_point
                                ? "font-medium text-red-600"
                                : ""
                            }
                          >
                            {p.quantity_on_hand}
                          </span>
                        ) : (
                          "—"
                        )}
                      </td>
                      <td className="px-4 py-3">
                        <span
                          className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
                            p.active
                              ? "bg-green-100 text-green-800"
                              : "bg-gray-100 text-gray-500"
                          }`}
                        >
                          {p.active ? "Active" : "Inactive"}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex gap-1">
                          <button
                            onClick={() => setEditProduct(p)}
                            className="rounded px-2 py-1 text-xs text-indigo-600 hover:bg-indigo-50"
                          >
                            Edit
                          </button>
                          {p.active && (
                            <button
                              onClick={() => {
                                if (confirm(`Deactivate "${p.name}"?`))
                                  deleteMut.mutate(p.id);
                              }}
                              disabled={deleteMut.isPending}
                              className="rounded px-2 py-1 text-xs text-red-600 hover:bg-red-50"
                            >
                              Deactivate
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

// ── Product Modal ────────────────────────────────────────────────────────────

function ProductModal({
  product,
  onClose,
  onSaved,
}: {
  product: Product | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [name, setName] = useState(product?.name || "");
  const [description, setDescription] = useState(product?.description || "");
  const [sku, setSku] = useState(product?.sku || "");
  const [priceDollars, setPriceDollars] = useState(
    product ? (product.price_cents / 100).toFixed(2) : ""
  );
  const [costDollars, setCostDollars] = useState(
    product ? (product.cost_cents / 100).toFixed(2) : ""
  );
  const [category, setCategory] = useState(product?.category || "retail");
  const [taxPercent, setTaxPercent] = useState(
    product ? (product.tax_rate * 100).toFixed(2) : "0"
  );
  const [reorderPoint, setReorderPoint] = useState(
    product?.reorder_point?.toString() || "5"
  );
  const [reorderQty, setReorderQty] = useState(
    product?.reorder_quantity?.toString() || "20"
  );

  const createMut = useMutation({
    mutationFn: (data: Parameters<typeof retailApi.createProduct>[0]) =>
      retailApi.createProduct(data),
    onSuccess: onSaved,
  });

  const updateMut = useMutation({
    mutationFn: (data: Parameters<typeof retailApi.updateProduct>[1]) =>
      retailApi.updateProduct(product!.id, data),
    onSuccess: onSaved,
  });

  const handleSubmit = () => {
    const priceCents = Math.round(parseFloat(priceDollars || "0") * 100);
    const costCents = Math.round(parseFloat(costDollars || "0") * 100);
    const taxRate = parseFloat(taxPercent || "0") / 100;

    if (product) {
      updateMut.mutate({
        name,
        description: description || undefined,
        sku: sku || undefined,
        price_cents: priceCents,
        cost_cents: costCents,
        category,
        tax_rate: taxRate,
      });
    } else {
      createMut.mutate({
        name,
        description: description || undefined,
        sku: sku || undefined,
        price_cents: priceCents,
        cost_cents: costCents,
        category,
        tax_rate: taxRate,
        reorder_point: parseInt(reorderPoint) || 5,
        reorder_quantity: parseInt(reorderQty) || 20,
      });
    }
  };

  const isPending = createMut.isPending || updateMut.isPending;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="w-full max-w-lg rounded-lg bg-white p-6 shadow-xl">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-lg font-bold">
            {product ? "Edit Product" : "Add Product"}
          </h3>
          <button onClick={onClose}>
            <X className="h-5 w-5 text-gray-400" />
          </button>
        </div>

        <div className="space-y-3">
          <div>
            <label className="mb-1 block text-xs font-medium text-gray-500">
              Name *
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-gray-500">
              Description
            </label>
            <input
              type="text"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-xs font-medium text-gray-500">
                SKU / Barcode
              </label>
              <input
                type="text"
                value={sku}
                onChange={(e) => setSku(e.target.value)}
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-gray-500">
                Category
              </label>
              <select
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
              >
                <option value="retail">Retail</option>
                <option value="beverages">Beverages</option>
                <option value="rental">Rental</option>
                <option value="merchandise">Merchandise</option>
              </select>
            </div>
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="mb-1 block text-xs font-medium text-gray-500">
                Price ($)
              </label>
              <input
                type="number"
                step="0.01"
                min="0"
                value={priceDollars}
                onChange={(e) => setPriceDollars(e.target.value)}
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-gray-500">
                Cost ($)
              </label>
              <input
                type="number"
                step="0.01"
                min="0"
                value={costDollars}
                onChange={(e) => setCostDollars(e.target.value)}
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-gray-500">
                Tax Rate (%)
              </label>
              <input
                type="number"
                step="0.01"
                min="0"
                max="100"
                value={taxPercent}
                onChange={(e) => setTaxPercent(e.target.value)}
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
              />
            </div>
          </div>
          {!product && (
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="mb-1 block text-xs font-medium text-gray-500">
                  Reorder Point
                </label>
                <input
                  type="number"
                  min="0"
                  value={reorderPoint}
                  onChange={(e) => setReorderPoint(e.target.value)}
                  className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-gray-500">
                  Reorder Quantity
                </label>
                <input
                  type="number"
                  min="1"
                  value={reorderQty}
                  onChange={(e) => setReorderQty(e.target.value)}
                  className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
                />
              </div>
            </div>
          )}
        </div>

        <div className="mt-4 flex justify-end gap-2">
          <button
            onClick={onClose}
            className="rounded-md border border-gray-300 px-4 py-2 text-sm"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={!name || isPending}
            className="flex items-center gap-2 rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
          >
            {isPending && <Loader2 className="h-4 w-4 animate-spin" />}
            {product ? "Update" : "Create"}
          </button>
        </div>

        {(createMut.isError || updateMut.isError) && (
          <p className="mt-2 text-sm text-red-600">
            {((createMut.error || updateMut.error) as Error)?.message ||
              "An error occurred"}
          </p>
        )}
      </div>
    </div>
  );
}

// ── Stock Levels Tab ─────────────────────────────────────────────────────────

function StockTab() {
  const queryClient = useQueryClient();
  const [showAdjust, setShowAdjust] = useState(false);
  const [adjustProductId, setAdjustProductId] = useState("");
  const [adjustProductName, setAdjustProductName] = useState("");
  const [adjustQty, setAdjustQty] = useState("");
  const [adjustReason, setAdjustReason] = useState("restock");
  const [adjustNotes, setAdjustNotes] = useState("");

  const { data: inventory, isLoading } = useQuery({
    queryKey: ["retail-inventory"],
    queryFn: () => retailApi.listInventory().then((r) => r.data.data),
  });

  const { data: alerts } = useQuery({
    queryKey: ["retail-low-stock"],
    queryFn: () => retailApi.lowStockAlerts().then((r) => r.data.data),
  });

  const adjustMut = useMutation({
    mutationFn: () =>
      retailApi.adjustStock({
        product_id: adjustProductId,
        quantity_change: parseInt(adjustQty),
        reason: adjustReason,
        notes: adjustNotes || undefined,
      }),
    onSuccess: () => {
      setShowAdjust(false);
      setAdjustQty("");
      setAdjustNotes("");
      queryClient.invalidateQueries({ queryKey: ["retail-inventory"] });
      queryClient.invalidateQueries({ queryKey: ["retail-low-stock"] });
    },
  });

  const openAdjust = (item: InventoryItem) => {
    setAdjustProductId(item.product_id);
    setAdjustProductName(item.name);
    setAdjustQty("");
    setAdjustReason("restock");
    setAdjustNotes("");
    setShowAdjust(true);
  };

  return (
    <div className="space-y-4">
      {/* Low Stock Alert */}
      {alerts && alerts.length > 0 && (
        <div className="flex items-start gap-3 rounded-lg border border-yellow-200 bg-yellow-50 p-4">
          <AlertTriangle className="mt-0.5 h-5 w-5 text-yellow-600" />
          <div>
            <p className="text-sm font-medium text-yellow-800">
              {alerts.length} product{alerts.length > 1 ? "s" : ""} below
              reorder point
            </p>
            <p className="mt-1 text-xs text-yellow-700">
              {alerts.map((a) => a.name).join(", ")}
            </p>
          </div>
        </div>
      )}

      {/* Adjust Stock Modal */}
      {showAdjust && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="w-full max-w-sm rounded-lg bg-white p-6 shadow-xl">
            <div className="mb-4 flex items-center justify-between">
              <h3 className="text-lg font-bold">Adjust Stock</h3>
              <button onClick={() => setShowAdjust(false)}>
                <X className="h-5 w-5 text-gray-400" />
              </button>
            </div>
            <p className="mb-3 text-sm text-gray-600">{adjustProductName}</p>
            <div className="space-y-3">
              <div>
                <label className="mb-1 block text-xs font-medium text-gray-500">
                  Quantity Change (negative to reduce)
                </label>
                <input
                  type="number"
                  value={adjustQty}
                  onChange={(e) => setAdjustQty(e.target.value)}
                  placeholder="e.g. 10 or -3"
                  className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-gray-500">
                  Reason
                </label>
                <select
                  value={adjustReason}
                  onChange={(e) => setAdjustReason(e.target.value)}
                  className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
                >
                  <option value="restock">Restock</option>
                  <option value="adjustment">Adjustment</option>
                  <option value="shrinkage">Shrinkage</option>
                  <option value="opening_count">Opening Count</option>
                </select>
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-gray-500">
                  Notes
                </label>
                <input
                  type="text"
                  value={adjustNotes}
                  onChange={(e) => setAdjustNotes(e.target.value)}
                  placeholder="Optional notes..."
                  className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
                />
              </div>
            </div>
            <div className="mt-4 flex justify-end gap-2">
              <button
                onClick={() => setShowAdjust(false)}
                className="rounded-md border border-gray-300 px-4 py-2 text-sm"
              >
                Cancel
              </button>
              <button
                onClick={() => adjustMut.mutate()}
                disabled={!adjustQty || adjustMut.isPending}
                className="flex items-center gap-2 rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
              >
                {adjustMut.isPending && (
                  <Loader2 className="h-4 w-4 animate-spin" />
                )}
                Apply
              </button>
            </div>
            {adjustMut.isError && (
              <p className="mt-2 text-sm text-red-600">
                {(adjustMut.error as Error)?.message || "Adjustment failed"}
              </p>
            )}
          </div>
        </div>
      )}

      <Card>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="flex justify-center py-8">
              <Loader2 className="h-6 w-6 animate-spin text-gray-300" />
            </div>
          ) : !inventory || inventory.length === 0 ? (
            <p className="py-8 text-center text-sm text-gray-400">
              No inventory records
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-gray-50 text-left text-xs font-medium uppercase text-gray-500">
                    <th className="px-4 py-3">Product</th>
                    <th className="px-4 py-3">SKU</th>
                    <th className="px-4 py-3">Category</th>
                    <th className="px-4 py-3">On Hand</th>
                    <th className="px-4 py-3">Reorder At</th>
                    <th className="px-4 py-3">Reorder Qty</th>
                    <th className="px-4 py-3">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {inventory.map((item) => {
                    const isLow =
                      item.quantity_on_hand <= item.reorder_point;
                    return (
                      <tr
                        key={item.id}
                        className={`hover:bg-gray-50 ${isLow ? "bg-red-50" : ""}`}
                      >
                        <td className="px-4 py-3 font-medium">
                          {isLow && (
                            <AlertTriangle className="mr-1 inline h-3 w-3 text-red-500" />
                          )}
                          {item.name}
                        </td>
                        <td className="px-4 py-3 text-gray-500">
                          {item.sku || "—"}
                        </td>
                        <td className="px-4 py-3">
                          <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs">
                            {item.category}
                          </span>
                        </td>
                        <td
                          className={`px-4 py-3 font-medium ${isLow ? "text-red-600" : ""}`}
                        >
                          {item.quantity_on_hand}
                        </td>
                        <td className="px-4 py-3 text-gray-500">
                          {item.reorder_point}
                        </td>
                        <td className="px-4 py-3 text-gray-500">
                          {item.reorder_quantity}
                        </td>
                        <td className="px-4 py-3">
                          <button
                            onClick={() => openAdjust(item)}
                            className="rounded px-2 py-1 text-xs font-medium text-indigo-600 hover:bg-indigo-50"
                          >
                            Adjust
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

// ── History Tab ──────────────────────────────────────────────────────────────

function HistoryTab() {
  const [selectedProductId, setSelectedProductId] = useState("");

  const { data: products } = useQuery({
    queryKey: ["retail-products-for-history"],
    queryFn: () =>
      retailApi.listProducts().then((r) => r.data.data),
  });

  const { data: history, isLoading } = useQuery({
    queryKey: ["retail-inv-history", selectedProductId],
    queryFn: () =>
      retailApi.inventoryHistory(selectedProductId).then((r) => r.data.data),
    enabled: !!selectedProductId,
  });

  return (
    <div className="space-y-4">
      <div>
        <label className="mb-1 block text-xs font-medium text-gray-500">
          Select Product
        </label>
        <select
          value={selectedProductId}
          onChange={(e) => setSelectedProductId(e.target.value)}
          className="w-64 rounded-md border border-gray-300 px-3 py-2 text-sm"
        >
          <option value="">Choose a product...</option>
          {products?.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name} {p.sku ? `(${p.sku})` : ""}
            </option>
          ))}
        </select>
      </div>

      {selectedProductId && (
        <Card>
          <CardContent className="p-0">
            {isLoading ? (
              <div className="flex justify-center py-8">
                <Loader2 className="h-6 w-6 animate-spin text-gray-300" />
              </div>
            ) : !history || history.length === 0 ? (
              <p className="py-8 text-center text-sm text-gray-400">
                No history for this product
              </p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b bg-gray-50 text-left text-xs font-medium uppercase text-gray-500">
                      <th className="px-4 py-3">Date</th>
                      <th className="px-4 py-3">Change</th>
                      <th className="px-4 py-3">Reason</th>
                      <th className="px-4 py-3">Notes</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y">
                    {history.map((txn) => (
                      <tr key={txn.id} className="hover:bg-gray-50">
                        <td className="px-4 py-3 text-gray-600">
                          {fmtDate(txn.created_at)} {fmtTime(txn.created_at)}
                        </td>
                        <td className="px-4 py-3">
                          <span
                            className={`font-medium ${txn.quantity_change >= 0 ? "text-green-600" : "text-red-600"}`}
                          >
                            {txn.quantity_change > 0 ? "+" : ""}
                            {txn.quantity_change}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs">
                            {txn.reason}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-gray-500">
                          {txn.notes || "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
