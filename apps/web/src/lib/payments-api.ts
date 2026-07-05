import { apiClient } from "./api-client";

// ── Types ────────────────────────────────────────────────────────────────────

export interface Transaction {
  id: string;
  member_id: string;
  amount_cents: number;
  type: string;
  status: string;
  description?: string;
  stripe_payment_intent_id?: string;
  stripe_invoice_id?: string;
  membership_id?: string;
  booking_id?: string;
  refund_amount_cents?: number;
  refund_reason?: string;
  refunded_at?: string;
  fee_cents: number;
  net_amount_cents: number;
  created_at: string;
  updated_at?: string;
  // Joined fields
  first_name?: string;
  last_name?: string;
  member_email?: string;
}

export interface RevenueSummary {
  total_revenue: number;
  total_fees: number;
  net_revenue: number;
  total_refunds: number;
  transaction_count: number;
}

export interface FailedPayment {
  id: string;
  member_id: string;
  membership_id?: string;
  amount_cents: number;
  failure_reason: string;
  attempt_number: number;
  created_at: string;
  first_name?: string;
  last_name?: string;
  member_email?: string;
}

export interface CommunicationLog {
  id: string;
  member_id?: string;
  channel: string;
  type: string;
  recipient: string;
  subject?: string;
  status: string;
  created_at: string;
}

export interface PlatformInvoice {
  id: string;
  number: string | null;
  created: number;
  amount_due: number;
  amount_paid: number;
  currency: string;
  status: "draft" | "open" | "paid" | "void" | "uncollectible";
  invoice_pdf: string | null;
  hosted_invoice_url: string | null;
  period_start: number;
  period_end: number;
  description: string | null;
}

export interface ConnectStatus {
  connected: boolean;
  account_id?: string;
  charges_enabled?: boolean;
  payouts_enabled?: boolean;
  details_submitted?: boolean;
}

// ── API ──────────────────────────────────────────────────────────────────────

export const paymentsApi = {
  // Connect
  getConnectStatus: () =>
    apiClient.get<ConnectStatus>("/payments/connect/status"),

  startOnboarding: (returnUrl: string, refreshUrl: string) =>
    apiClient.post<{ url: string }>("/payments/connect/onboard", {
      return_url: returnUrl,
      refresh_url: refreshUrl,
    }),

  // Checkout
  createCheckoutSession: (data: {
    member_id: string;
    membership_type_id: string;
    success_url: string;
    cancel_url: string;
  }) => apiClient.post<{ data: { session_id: string; url: string } }>("/payments/checkout", data),

  createPortalSession: (data: { member_id: string; return_url: string }) =>
    apiClient.post<{ data: { url: string } }>("/payments/portal", data),

  // Transactions
  listTransactions: (params?: { member_id?: string; limit?: number; offset?: number }) =>
    apiClient.get<{ data: Transaction[] }>("/payments/transactions", { params }),

  getTransaction: (id: string) =>
    apiClient.get<{ data: Transaction }>(`/payments/transactions/${id}`),

  recordTransaction: (data: {
    member_id: string;
    amount_cents: number;
    type?: string;
    description?: string;
  }) => apiClient.post<{ data: Transaction }>("/payments/transactions", data),

  refundTransaction: (id: string, data?: { amount_cents?: number; reason?: string }) =>
    apiClient.post<{ data: Transaction }>(`/payments/transactions/${id}/refund`, data || {}),

  // Drop-in real payment
  createDropInIntent: (data: {
    member_id: string;
    amount_cents: number;
    description?: string;
  }) =>
    apiClient.post<{ data: { client_secret: string; payment_intent_id: string } }>(
      "/payments/drop-in-intent",
      data
    ),

  recordDropInPayment: (data: {
    member_id: string;
    amount_cents: number;
    payment_intent_id: string;
    description?: string;
  }) =>
    apiClient.post<{ data: Transaction }>("/payments/drop-in-intent/record", data),

  // Square
  squareCharge: (data: {
    member_id: string;
    amount_cents: number;
    source_id: string;
    description?: string;
  }) =>
    apiClient.post<{ data: Transaction & { square_payment: Record<string, unknown> } }>(
      "/payments/square/charge",
      data
    ),

  // Revenue
  getRevenueSummary: (days: number = 30) =>
    apiClient.get<{ data: RevenueSummary }>("/payments/revenue/summary", {
      params: { days },
    }),

  // Failed payments
  listFailedPayments: (limit: number = 50) =>
    apiClient.get<{ data: FailedPayment[] }>("/payments/failed-payments", {
      params: { limit },
    }),

  // Communications
  listCommunications: (params?: { member_id?: string; channel?: string; limit?: number }) =>
    apiClient.get<{ data: CommunicationLog[] }>("/payments/communications", { params }),

  // Platform billing invoices (what the studio pays AuraFlow)
  listBillingInvoices: (limit: number = 24) =>
    apiClient.get<{ data: PlatformInvoice[] }>("/organizations/billing/invoices", {
      params: { limit },
    }),

  // ── Square POS ──────────────────────────────────────────────────────

  pairPOSDevice: (name: string) =>
    apiClient.post<{ data: POSDeviceCode }>("/payments/pos/square/devices/pair", { name }),

  pollDeviceCode: (deviceCodeId: string) =>
    apiClient.get<{ data: POSDeviceCode }>(
      `/payments/pos/square/devices/codes/${deviceCodeId}`,
    ),

  listPOSDevices: () =>
    apiClient.get<{ data: POSDevice[] }>("/payments/pos/square/devices"),

  renamePOSDevice: (devicePk: string, body: { name?: string; set_as_default?: boolean }) =>
    apiClient.put<{ data: { id: string; renamed: boolean; set_as_default: boolean } }>(
      `/payments/pos/square/devices/${devicePk}`,
      body,
    ),

  unpairPOSDevice: (devicePk: string) =>
    apiClient.delete<{ data: { unpaired: boolean; device_id: string } }>(
      `/payments/pos/square/devices/${devicePk}`,
    ),

  posCharge: (body: {
    member_id: string;
    amount_cents: number;
    description?: string;
    device_id?: string;
    membership_type_id?: string;
    class_session_id?: string;
  }) =>
    apiClient.post<{ data: POSCheckoutResult }>("/payments/pos/charge", body),

  getPOSCheckout: (checkoutId: string) =>
    apiClient.get<{ data: POSCheckoutStatus }>(`/payments/pos/checkouts/${checkoutId}`),

  cancelPOSCheckout: (checkoutId: string) =>
    apiClient.post<{ data: { cancelled: boolean; status?: string; reason?: string } }>(
      `/payments/pos/checkouts/${checkoutId}/cancel`,
    ),

  posDeeplinkCharge: (body: {
    member_id: string;
    amount_cents: number;
    description?: string;
    membership_type_id?: string;
    class_session_id?: string;
    // For workshop walk-ins — server enrolls automatically after
    // payment is confirmed, so we don't depend on a client-side
    // post-success callback (which the deeplink navigation kills).
    course_id?: string;
  }) =>
    apiClient.post<{ data: {
      checkout_id: string;
      flow: "deeplink";
      status: "pending";
      amount_cents: number;
      ios_url: string;
      android_url: string;
      callback_url: string;
    }}>("/payments/pos/deeplink-charge", body),

  chargeSavedCard: (body: { member_id: string; amount_cents: number; description: string }) =>
    apiClient.post<{ data: Transaction & { payment_id: string } }>(
      "/payments/pos/charge-saved-card",
      body,
    ),
};

export interface POSDeviceCode {
  device_code_id: string;
  code: string;
  status: "UNPAIRED" | "PAIRED" | "EXPIRED";
  device_id?: string | null;
  pair_by?: string | null;
  name?: string;
}

export interface POSDevice {
  id: string;
  device_id: string;
  name: string;
  device_type?: string | null;
  status: "online" | "offline" | "paused" | "unknown" | "paired";
  paired_at?: string | null;
  last_seen_at?: string | null;
  is_default: boolean;
}

export interface POSCheckoutResult {
  checkout_id: string;
  square_checkout_id: string;
  status: "pending" | "in_progress" | "completed" | "cancelled" | "failed" | "expired";
  flow: "terminal" | "deeplink";
  device_id?: string;
  amount_cents: number;
  app_fee_cents: number;
}

export interface POSCheckoutStatus {
  checkout_id: string;
  square_checkout_id?: string;
  status: "pending" | "in_progress" | "completed" | "cancelled" | "failed" | "expired";
  amount_cents: number;
  device_id?: string;
  completed_at?: string;
  failure_reason?: string;
  square_payment_id?: string;
  square_card_id?: string;
  membership_type_id?: string;
}
