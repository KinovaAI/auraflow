import { apiClient } from "./api-client";

// ── Types ───────────────────────────────────────────────────────────────────

export interface GoogleAdsConnectionStatus {
  connected: boolean;
  customer_id?: string;
  connected_at?: string;
}

export interface GoogleAdsConfig {
  id: string;
  max_monthly_spend_cents: number;
  target_latitude?: number;
  target_longitude?: number;
  target_radius_miles: number;
  target_locations?: string[];
  class_focus?: string[];
  brand_voice?: string;
  negative_keywords?: string[];
  approval_threshold_cents: number;
  is_active: boolean;
  created_at: string;
  updated_at?: string;
}

export interface GoogleAdsConfigUpdate {
  max_monthly_spend_cents?: number;
  target_latitude?: number;
  target_longitude?: number;
  target_radius_miles?: number;
  target_locations?: string[];
  class_focus?: string[];
  brand_voice?: string;
  negative_keywords?: string[];
  approval_threshold_cents?: number;
}

export interface GoogleAdsCampaign {
  id: string;
  google_campaign_id: string;
  campaign_type: string;
  name: string;
  status: string;
  daily_budget_cents: number;
  bidding_strategy?: string;
  target_roas?: number;
  latest_impressions?: number;
  latest_clicks?: number;
  latest_conversions?: number;
  latest_cost_micros?: number;
  latest_roas?: number;
  created_at: string;
}

export interface PerformanceSummary {
  days: number;
  impressions: number;
  clicks: number;
  conversions: number;
  spend_cents: number;
  conversion_value_cents: number;
  roas: number;
  ctr: number;
  cost_per_lead_cents: number;
}

export interface DailyPerformance {
  date: string;
  impressions: number;
  clicks: number;
  conversions: number;
  spend_cents: number;
  roas: number;
}

export interface BudgetStatus {
  max_monthly_cents: number;
  spent_cents: number;
  remaining_cents: number;
  utilization_pct: number;
  over_budget: boolean;
}

export interface AIAction {
  id: string;
  action_type: string;
  description: string;
  reasoning: string;
  changes_json?: Record<string, unknown>;
  status: "proposed" | "approved" | "executed" | "rejected" | "failed";
  requires_approval: boolean;
  created_at: string;
}

// ── API Client ──────────────────────────────────────────────────────────────

export const googleAdsApi = {
  // Connection
  getConnectionStatus: () =>
    apiClient.get<{ data: GoogleAdsConnectionStatus }>("/google-ads/connect/status"),

  getOAuthUrl: () =>
    apiClient.get<{ data: { url: string } }>("/google-ads/connect/oauth"),

  setCustomerId: (customer_id: string) =>
    apiClient.post<{ data: { customer_id: string } }>("/google-ads/connect", { customer_id }),

  disconnect: () =>
    apiClient.delete<{ data: { disconnected: boolean } }>("/google-ads/connect"),

  // Config
  getConfig: () =>
    apiClient.get<{ data: GoogleAdsConfig | null }>("/google-ads/config"),

  updateConfig: (data: GoogleAdsConfigUpdate) =>
    apiClient.put<{ data: GoogleAdsConfig }>("/google-ads/config", data),

  enable: () =>
    apiClient.post<{ data: { enabled: boolean; setup: Record<string, unknown> } }>("/google-ads/config/enable"),

  disable: () =>
    apiClient.post<{ data: { disabled: boolean; campaigns_paused: number } }>("/google-ads/config/disable"),

  // Dashboard
  listCampaigns: () =>
    apiClient.get<{ data: GoogleAdsCampaign[] }>("/google-ads/campaigns"),

  getPerformanceSummary: (days?: number) =>
    apiClient.get<{ data: PerformanceSummary }>("/google-ads/performance/summary", {
      params: days ? { days } : undefined,
    }),

  getDailyPerformance: (days?: number) =>
    apiClient.get<{ data: DailyPerformance[] }>("/google-ads/performance/daily", {
      params: days ? { days } : undefined,
    }),

  getBudgetStatus: () =>
    apiClient.get<{ data: BudgetStatus }>("/google-ads/budget"),

  // AI Actions
  listActions: (params?: { status?: string; limit?: number }) =>
    apiClient.get<{ data: AIAction[] }>("/google-ads/actions", { params }),

  listPendingActions: () =>
    apiClient.get<{ data: AIAction[] }>("/google-ads/actions/pending"),

  approveAction: (id: string) =>
    apiClient.post<{ data: { id: string; status: string } }>(`/google-ads/actions/${id}/approve`),

  rejectAction: (id: string) =>
    apiClient.post<{ data: { id: string; status: string } }>(`/google-ads/actions/${id}/reject`),

  // Manual controls
  pauseCampaign: (campaignId: string) =>
    apiClient.post<{ data: { google_campaign_id: string; status: string } }>(
      `/google-ads/campaigns/${campaignId}/pause`
    ),

  enableCampaign: (campaignId: string) =>
    apiClient.post<{ data: { google_campaign_id: string; status: string } }>(
      `/google-ads/campaigns/${campaignId}/enable`
    ),

  triggerOptimization: () =>
    apiClient.post<{ data: Record<string, unknown> }>("/google-ads/optimize/trigger"),

  getReport: (days?: number) =>
    apiClient.get<{ data: { summary: string } }>("/google-ads/report", {
      params: days ? { days } : undefined,
    }),
};
