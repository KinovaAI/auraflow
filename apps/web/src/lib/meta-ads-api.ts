import { apiClient } from "./api-client";

// ── Types ───────────────────────────────────────────────────────────────────

export interface MetaAdsConnectionStatus {
  connected: boolean;
  ad_account_id?: string;
  connected_at?: string;
}

export interface MetaAdsConfig {
  id: string;
  max_monthly_spend_cents: number;
  target_latitude?: number;
  target_longitude?: number;
  target_radius_miles: number;
  target_age_min: number;
  target_age_max: number;
  target_genders?: string[];
  target_interests?: string[];
  class_focus?: string[];
  brand_voice?: string;
  excluded_interests?: string[];
  approval_threshold_cents: number;
  is_active: boolean;
  meta_pixel_id?: string;
  default_page_id?: string;
  instagram_account_id?: string;
  created_at: string;
  updated_at?: string;
}

export interface MetaAdsConfigUpdate {
  max_monthly_spend_cents?: number;
  target_latitude?: number;
  target_longitude?: number;
  target_radius_miles?: number;
  target_age_min?: number;
  target_age_max?: number;
  target_genders?: string[];
  target_interests?: string[];
  class_focus?: string[];
  brand_voice?: string;
  excluded_interests?: string[];
  approval_threshold_cents?: number;
  meta_pixel_id?: string;
  default_page_id?: string;
  instagram_account_id?: string;
}

export interface MetaAdsCampaign {
  id: string;
  meta_campaign_id: string;
  campaign_objective: string;
  name: string;
  status: string;
  daily_budget_cents?: number;
  lifetime_budget_cents?: number;
  latest_impressions?: number;
  latest_reach?: number;
  latest_clicks?: number;
  latest_conversions?: number;
  latest_spend_cents?: number;
  latest_frequency?: number;
  latest_roas?: number;
  created_at: string;
}

export interface MetaPerformanceSummary {
  days: number;
  impressions: number;
  reach: number;
  clicks: number;
  conversions: number;
  spend_cents: number;
  ctr: number;
  cost_per_lead_cents: number;
  roas: number;
}

export interface MetaDailyPerformance {
  date: string;
  impressions: number;
  reach: number;
  clicks: number;
  conversions: number;
  spend_cents: number;
  frequency: number;
  roas: number;
}

export interface MetaBudgetStatus {
  max_monthly_cents: number;
  spent_cents: number;
  remaining_cents: number;
  utilization_pct: number;
  over_budget: boolean;
}

export interface MetaAIAction {
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

export const metaAdsApi = {
  // Connection
  getConnectionStatus: () =>
    apiClient.get<{ data: MetaAdsConnectionStatus }>("/meta-ads/connect/status"),

  getOAuthUrl: () =>
    apiClient.get<{ data: { url: string } }>("/meta-ads/connect/oauth"),

  setAdAccountId: (ad_account_id: string) =>
    apiClient.post<{ data: { ad_account_id: string } }>("/meta-ads/connect", { ad_account_id }),

  disconnect: () =>
    apiClient.delete<{ data: { disconnected: boolean } }>("/meta-ads/connect"),

  // Config
  getConfig: () =>
    apiClient.get<{ data: MetaAdsConfig | null }>("/meta-ads/config"),

  updateConfig: (data: MetaAdsConfigUpdate) =>
    apiClient.put<{ data: MetaAdsConfig }>("/meta-ads/config", data),

  enable: () =>
    apiClient.post<{ data: { enabled: boolean; setup: Record<string, unknown> } }>("/meta-ads/config/enable"),

  disable: () =>
    apiClient.post<{ data: { disabled: boolean; campaigns_paused: number } }>("/meta-ads/config/disable"),

  // Dashboard
  listCampaigns: () =>
    apiClient.get<{ data: MetaAdsCampaign[] }>("/meta-ads/campaigns"),

  getPerformanceSummary: (days?: number) =>
    apiClient.get<{ data: MetaPerformanceSummary }>("/meta-ads/performance/summary", {
      params: days ? { days } : undefined,
    }),

  getDailyPerformance: (days?: number) =>
    apiClient.get<{ data: MetaDailyPerformance[] }>("/meta-ads/performance/daily", {
      params: days ? { days } : undefined,
    }),

  getBudgetStatus: () =>
    apiClient.get<{ data: MetaBudgetStatus }>("/meta-ads/budget"),

  // AI Actions
  listActions: (params?: { status?: string; limit?: number }) =>
    apiClient.get<{ data: MetaAIAction[] }>("/meta-ads/actions", { params }),

  listPendingActions: () =>
    apiClient.get<{ data: MetaAIAction[] }>("/meta-ads/actions/pending"),

  approveAction: (id: string) =>
    apiClient.post<{ data: { id: string; status: string } }>(`/meta-ads/actions/${id}/approve`),

  rejectAction: (id: string) =>
    apiClient.post<{ data: { id: string; status: string } }>(`/meta-ads/actions/${id}/reject`),

  // Manual controls
  pauseCampaign: (campaignId: string) =>
    apiClient.post<{ data: { meta_campaign_id: string; status: string } }>(
      `/meta-ads/campaigns/${campaignId}/pause`
    ),

  enableCampaign: (campaignId: string) =>
    apiClient.post<{ data: { meta_campaign_id: string; status: string } }>(
      `/meta-ads/campaigns/${campaignId}/enable`
    ),

  triggerOptimization: () =>
    apiClient.post<{ data: Record<string, unknown> }>("/meta-ads/optimize/trigger"),

  getReport: (days?: number) =>
    apiClient.get<{ data: { summary: string } }>("/meta-ads/report", {
      params: days ? { days } : undefined,
    }),
};
