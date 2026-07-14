import { apiClient } from "./api-client";

// ── Types ────────────────────────────────────────────────────────────────────

export interface AccountingSettings {
  llc_name: string | null;
  llc_ein: string | null;
  llc_state: string | null;
  llc_tax_class: string | null;
  mercury_api_key: string | null; // masked
  mercury_connected: boolean;
  mercury_accounts: unknown;
  last_sync_at: string | null;
}

export interface AccountingCategory {
  code: string;
  label: string;
  kind: "income" | "expense" | "distribution" | "transfer";
  schedule_c_line: string | null;
  txf_ref: string | null;
  is_custom: boolean;
}

export interface AccountingMember {
  id: string;
  name: string;
  email: string | null;
  ownership_pct: number;
  capital_cents: number;
  updated_at?: string;
}

export interface AccountingTransaction {
  id: string;
  txn_date: string;
  description: string;
  type: "income" | "expense" | "distribution" | "transfer";
  category: string | null;
  amount_cents: number;
  source: "bank" | "auraflow" | "manual";
  external_id: string | null;
  auraflow_txn_id: string | null;
  payout_id: string | null;
  member_id: string | null;
  status: "pending" | "reconciled";
  notes: string | null;
}

export interface AccountingPayout {
  id: string;
  provider: "stripe" | "square";
  provider_payout_id: string;
  payout_date: string | null;
  gross_cents: number;
  fee_cents: number;
  net_cents: number;
  status: string | null;
  bank_txn_id: string | null;
  reconciled: boolean;
  discrepancy_cents: number;
}

export interface PnlSummary {
  year: number | null;
  income: Record<string, number>;
  expense: Record<string, number>;
  distribution: Record<string, number>;
  total_income_cents: number;
  total_expenses_cents: number;
  total_distributions_cents: number;
  net_profit_cents: number;
}

export interface ScheduleCLine {
  line: string;
  label: string;
  code: string | null;
  txf_ref: string | null;
  amount_cents: number;
}

export interface ScheduleCReport {
  year: number | null;
  income_lines: ScheduleCLine[];
  expense_lines: ScheduleCLine[];
  gross_receipts_cents: number;
  total_expenses_cents: number;
  net_profit_cents: number;
}

export interface MemberAllocation {
  id: string;
  name: string;
  email: string | null;
  ownership_pct: number;
  capital_cents: number;
  share_income_cents: number;
  share_expenses_cents: number;
  net_allocation_cents: number;
  distributions_cents: number;
}

export interface K1Report {
  year: number | null;
  total_income_cents: number;
  total_expenses_cents: number;
  total_distributions_cents: number;
  net_profit_cents: number;
  allocations: MemberAllocation[];
}

export interface ReconcileResult {
  bank_income_count: number;
  bank_income_cents: number;
  bank_expense_count: number;
  bank_transfer_count: number;
  auraflow_sales_count: number;
  auraflow_sales_cents: number;
  // back-compat / unused in bank-authoritative mode
  newly_matched: number;
  cash_settled: number;
  unmatched_payout_count: number;
  unmatched_deposit_count: number;
  unsettled_card_sales_count: number;
}

export interface IncomeSyncResult {
  income_booked?: number;
  returns_booked?: number;
  pos_booked?: number;
  error?: string;
}

export interface SyncResult {
  income: IncomeSyncResult;
  bank: { imported?: number; skipped?: number; error?: string; warnings?: string[] };
  payouts: Record<string, unknown>;
  reconciliation: ReconcileResult;
}

// ── Client ───────────────────────────────────────────────────────────────────

function download(blob: Blob, filename: string) {
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(url);
}

export interface OwnerDraw {
  id: string;
  owner_pattern: string;
  monthly_cents: number;
  effective_from: string;
  effective_to: string | null;
  is_active: boolean;
}

export const accountingApi = {
  getOwnerDraws: () => apiClient.get<OwnerDraw[]>("/accounting/owner-draws"),
  createOwnerDraw: (data: {
    owner_pattern: string;
    monthly_cents: number;
    effective_from: string;
    effective_to?: string | null;
  }) => apiClient.post<OwnerDraw>("/accounting/owner-draws", data),
  deleteOwnerDraw: (id: string) => apiClient.delete(`/accounting/owner-draws/${id}`),

  getSettings: () => apiClient.get<AccountingSettings>("/accounting/settings"),
  updateSettings: (patch: Partial<AccountingSettings>) =>
    apiClient.put<AccountingSettings>("/accounting/settings", patch),

  getCategories: () => apiClient.get<AccountingCategory[]>("/accounting/categories"),

  getMembers: () => apiClient.get<AccountingMember[]>("/accounting/members"),
  createMember: (data: Partial<AccountingMember> & { tin?: string }) =>
    apiClient.post<AccountingMember>("/accounting/members", data),
  updateMember: (id: string, data: Partial<AccountingMember> & { tin?: string }) =>
    apiClient.put<AccountingMember>(`/accounting/members/${id}`, data),
  deleteMember: (id: string) => apiClient.delete(`/accounting/members/${id}`),

  getTransactions: (params: Record<string, string | number> = {}) => {
    const q = new URLSearchParams(
      Object.entries(params).map(([k, v]) => [k, String(v)]),
    );
    return apiClient.get<AccountingTransaction[]>(`/accounting/transactions?${q}`);
  },
  createTransaction: (data: Partial<AccountingTransaction>) =>
    apiClient.post<AccountingTransaction>("/accounting/transactions", data),
  updateTransaction: (id: string, patch: Partial<AccountingTransaction>) =>
    apiClient.put<AccountingTransaction>(`/accounting/transactions/${id}`, patch),
  deleteTransaction: (id: string) =>
    apiClient.delete(`/accounting/transactions/${id}`),

  getPayouts: (reconciled?: boolean) => {
    const q = reconciled === undefined ? "" : `?reconciled=${reconciled}`;
    return apiClient.get<AccountingPayout[]>(`/accounting/payouts${q}`);
  },

  sync: () => apiClient.post<SyncResult>("/accounting/sync"),
  reconcile: () => apiClient.post<ReconcileResult>("/accounting/reconcile"),

  summary: (year?: number) =>
    apiClient.get<PnlSummary>(`/accounting/reports/summary${year ? `?year=${year}` : ""}`),
  scheduleC: (year?: number) =>
    apiClient.get<ScheduleCReport>(
      `/accounting/reports/schedule-c${year ? `?year=${year}` : ""}`,
    ),
  memberAllocation: (year?: number) =>
    apiClient.get<K1Report>(
      `/accounting/reports/member-allocation${year ? `?year=${year}` : ""}`,
    ),

  exportTxf: async (year: number) => {
    const res = await apiClient.get(`/accounting/export/txf?year=${year}`, {
      responseType: "blob",
    });
    download(res.data as Blob, `schedule-c-${year}.txf`);
  },
  exportPdf: async (year: number) => {
    const res = await apiClient.get(`/accounting/export/pdf?year=${year}`, {
      responseType: "blob",
    });
    download(res.data as Blob, `accounting-${year}.pdf`);
  },
};
