import { apiClient } from "./api-client";

// ── Types ────────────────────────────────────────────────────────────────────

export interface Product {
  id: string;
  studio_id: string | null;
  name: string;
  description: string | null;
  sku: string | null;
  price_cents: number;
  cost_cents: number;
  category: string;
  tax_rate: number;
  image_url: string | null;
  active: boolean;
  quantity_on_hand: number | null;
  reorder_point: number | null;
  reorder_quantity: number | null;
  created_at: string;
  updated_at: string;
}

export interface InventoryItem {
  id: string;
  product_id: string;
  name: string;
  sku: string | null;
  category: string;
  price_cents: number;
  quantity_on_hand: number;
  reorder_point: number;
  reorder_quantity: number;
  last_counted_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface InventoryTransaction {
  id: string;
  product_id: string;
  quantity_change: number;
  reason: string;
  reference_id: string | null;
  notes: string | null;
  created_by: string | null;
  created_at: string;
}

export interface POSLineItem {
  id: string;
  transaction_id: string;
  product_id: string;
  product_name: string;
  sku: string | null;
  quantity: number;
  unit_price_cents: number;
  tax_cents: number;
  total_cents: number;
}

export interface POSTransaction {
  id: string;
  member_id: string | null;
  member_first_name?: string;
  member_last_name?: string;
  subtotal_cents: number;
  tax_cents: number;
  total_cents: number;
  payment_method: string;
  stripe_payment_id: string | null;
  status: string;
  notes: string | null;
  created_by: string | null;
  created_at: string;
  updated_at: string;
  line_items?: POSLineItem[];
  checkout_url?: string;
  payment_link_emailed?: boolean;
}

export interface DailySummary {
  date: string;
  by_method: Array<{
    payment_method: string;
    transaction_count: number;
    subtotal: number;
    tax: number;
    total: number;
  }>;
  grand_total_cents: number;
  top_products: Array<{
    name: string;
    units_sold: number;
    revenue: number;
  }>;
}

export interface SalesReport {
  period_start: string;
  period_end: string;
  by_category: Array<{
    category: string;
    transaction_count: number;
    units_sold: number;
    revenue: number;
  }>;
  by_product: Array<{
    name: string;
    category: string;
    sku: string | null;
    units_sold: number;
    revenue: number;
  }>;
}

export interface InventoryReport {
  total_inventory_value_cents: number;
  items: Array<{
    name: string;
    category: string;
    cost_cents: number;
    quantity_on_hand: number;
    inventory_value_cents: number;
  }>;
}

// ── API Methods ──────────────────────────────────────────────────────────────

export const retailApi = {
  // Products
  listProducts: (params?: { category?: string; active_only?: boolean; search?: string }) =>
    apiClient.get<{ data: Product[] }>("/retail/products", { params }),

  getProduct: (id: string) =>
    apiClient.get<{ data: Product }>(`/retail/products/${id}`),

  getProductBySku: (sku: string) =>
    apiClient.get<{ data: Product }>(`/retail/products/sku/${sku}`),

  createProduct: (data: {
    name: string;
    description?: string;
    sku?: string;
    price_cents: number;
    cost_cents?: number;
    category?: string;
    tax_rate?: number;
    image_url?: string;
    studio_id?: string;
    reorder_point?: number;
    reorder_quantity?: number;
  }) => apiClient.post<{ data: Product }>("/retail/products", data),

  updateProduct: (id: string, data: Partial<{
    name: string;
    description: string;
    sku: string;
    price_cents: number;
    cost_cents: number;
    category: string;
    tax_rate: number;
    image_url: string;
    active: boolean;
  }>) => apiClient.put<{ data: Product }>(`/retail/products/${id}`, data),

  deleteProduct: (id: string) =>
    apiClient.delete(`/retail/products/${id}`),

  // Inventory
  listInventory: (low_stock_only?: boolean) =>
    apiClient.get<{ data: InventoryItem[] }>("/retail/inventory", {
      params: { low_stock_only },
    }),

  lowStockAlerts: () =>
    apiClient.get<{ data: InventoryItem[] }>("/retail/inventory/alerts/low-stock"),

  adjustStock: (data: {
    product_id: string;
    quantity_change: number;
    reason: string;
    notes?: string;
  }) => apiClient.post<{ data: InventoryItem }>("/retail/inventory/adjust", data),

  inventoryHistory: (productId: string, limit?: number) =>
    apiClient.get<{ data: InventoryTransaction[] }>(
      `/retail/inventory/${productId}/history`,
      { params: { limit } }
    ),

  // POS Transactions
  createTransaction: (data: {
    items: Array<{ product_id: string; quantity: number }>;
    payment_method?: string;
    member_id?: string;
    notes?: string;
    gift_card_code?: string;
  }) => apiClient.post<{ data: POSTransaction }>("/retail/transactions", data),

  listTransactions: (params?: {
    member_id?: string;
    date_from?: string;
    date_to?: string;
    limit?: number;
    offset?: number;
  }) => apiClient.get<{ data: POSTransaction[] }>("/retail/transactions", { params }),

  getTransaction: (id: string) =>
    apiClient.get<{ data: POSTransaction }>(`/retail/transactions/${id}`),

  listPendingTransactions: () =>
    apiClient.get<{ data: POSTransaction[] }>("/retail/transactions/pending"),

  resendPaymentLink: (id: string) =>
    apiClient.post<{ data: { payment_url: string; emailed: boolean } }>(
      `/retail/transactions/${id}/resend-link`
    ),

  createCheckout: (id: string) =>
    apiClient.post<{ data: { checkout_url: string } }>(
      `/retail/transactions/${id}/checkout`
    ),

  refundTransaction: (id: string, reason?: string) =>
    apiClient.post<{ data: POSTransaction }>(
      `/retail/transactions/${id}/refund`,
      { reason: reason || "requested_by_customer" }
    ),

  // Reports
  dailySummary: (target_date?: string) =>
    apiClient.get<{ data: DailySummary }>("/retail/reports/daily", {
      params: { target_date },
    }),

  salesReport: (date_from: string, date_to: string) =>
    apiClient.get<{ data: SalesReport }>("/retail/reports/sales", {
      params: { date_from, date_to },
    }),

  inventoryReport: () =>
    apiClient.get<{ data: InventoryReport }>("/retail/reports/inventory"),
};
