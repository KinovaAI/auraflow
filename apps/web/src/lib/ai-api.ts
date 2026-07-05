import { apiClient } from "./api-client";

// ── Types ────────────────────────────────────────────────────────────────────

export interface ChurnScanResult {
  newly_flagged: number;
  cleared: number;
  flagged_members: Array<{
    id: string;
    first_name: string;
    last_name: string;
    email: string;
  }>;
}

export interface AtRiskMember {
  id: string;
  first_name: string;
  last_name: string;
  email: string;
  phone: string | null;
  total_visits: number;
  last_visit_at: string | null;
  joined_at: string | null;
  lifetime_revenue_cents: number;
  churn_risk_flagged_at: string;
}

export interface MemberMilestone {
  id: string;
  member_id: string;
  milestone_type: string;
  achieved_at: string;
  notified_at: string | null;
}

export interface MarketingDraft {
  id: string;
  prompt_context: string;
  draft_type: string;
  subject: string | null;
  body: string;
  status: string;
  created_by: string | null;
  reviewed_by: string | null;
  reviewed_at: string | null;
  campaign_id: string | null;
  created_at: string;
  updated_at: string;
}

// ── Waitlist Triage Types ────────────────────────────────────────────────────

export interface WaitlistSession {
  id: string;
  title: string;
  starts_at: string;
  capacity: number;
  waitlist_capacity: number;
  booked_count: number;
  waitlist_count: number;
}

export interface WaitlistScore {
  booking_id: string;
  member_id: string;
  first_name: string;
  last_name: string;
  email: string;
  waitlist_position: number;
  booked_at: string | null;
  total_visits: number;
  lifetime_revenue_cents: number;
  membership_name: string;
  priority_score: number;
  factors: {
    membership_value: number;
    total_visits: number;
    lifetime_revenue: number;
    tenure: number;
    attendance_consistency: number;
    cancellation_penalty: number;
  };
}

// ── Dynamic Pricing Types ───────────────────────────────────────────────────

export interface PricingRule {
  id: string;
  studio_id: string;
  name: string;
  rule_type: string;
  config: Record<string, unknown>;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface PriceSuggestion {
  id: string;
  class_session_id: string;
  session_title?: string;
  starts_at?: string;
  original_price_cents: number;
  adjusted_price_cents: number;
  reason: string | null;
  ai_explanation: string | null;
  applied_by: string;
  status: string;
  created_at: string;
}

// ── Review Types ────────────────────────────────────────────────────────────

export interface Review {
  id: string;
  member_id: string;
  member_name?: string;
  class_session_id: string;
  session_title?: string;
  session_date?: string;
  rating: number;
  review_text: string | null;
  sentiment: string | null;
  sentiment_score: number | null;
  ai_analysis: string | null;
  response_text: string | null;
  response_draft: string | null;
  responded_by: string | null;
  responded_at: string | null;
  is_published: boolean;
  is_flagged: boolean;
  flag_reason: string | null;
  created_at: string;
}

export interface ReviewStats {
  total_reviews: number;
  avg_rating: number;
  positive_count: number;
  neutral_count: number;
  negative_count: number;
  responded_count: number;
  response_rate: number;
}

// ── API Methods ──────────────────────────────────────────────────────────────

export const aiApi = {
  // Content Generation
  generateClassDescription: (data: {
    class_name: string;
    class_type: string;
    level?: string;
    duration_minutes?: number;
    studio_name?: string;
    tone?: string;
  }) => apiClient.post<{ data: { description: string } }>("/ai/generate/class-description", data),

  generateMarketingEmail: (data: {
    subject_context: string;
    audience?: string;
    tone?: string;
    studio_name?: string;
  }) => apiClient.post<{ data: { subject: string; body: string; raw: string } }>("/ai/generate/marketing-email", data),

  generateSocialPost: (data: {
    topic: string;
    platform?: string;
    studio_name?: string;
  }) => apiClient.post<{ data: { post: string; platform: string } }>("/ai/generate/social-post", data),

  analyzeChurnRisk: (data: {
    total_visits: number;
    last_visit_at?: string;
    membership_status?: string;
    lifetime_revenue_cents?: number;
    days_since_visit?: number;
  }) => apiClient.post<{ data: { analysis: string } }>("/ai/analyze/churn-risk", data),

  // Churn Risk Management
  triggerChurnScan: () =>
    apiClient.post<{ data: ChurnScanResult }>("/ai/churn-scan"),

  listAtRiskMembers: () =>
    apiClient.get<{ data: AtRiskMember[] }>("/ai/churn-risk"),

  sendWinback: (memberId: string) =>
    apiClient.post<{ data: { member_id: string; name: string; channels: string[] } }>(
      `/ai/churn-risk/${memberId}/outreach`
    ),

  dismissChurnFlag: (memberId: string) =>
    apiClient.post(`/ai/churn-risk/${memberId}/dismiss`),

  // Milestones
  getMemberMilestones: (memberId: string) =>
    apiClient.get<{ data: MemberMilestone[] }>(`/ai/milestones/${memberId}`),

  // Marketing Drafts
  createDraft: (data: {
    prompt_context: string;
    draft_type?: string;
    tone?: string;
    studio_name?: string;
  }) => apiClient.post<{ data: MarketingDraft }>("/ai/drafts", data),

  listDrafts: (status?: string) =>
    apiClient.get<{ data: MarketingDraft[] }>("/ai/drafts", {
      params: status ? { status } : undefined,
    }),

  getDraft: (id: string) =>
    apiClient.get<{ data: MarketingDraft }>(`/ai/drafts/${id}`),

  updateDraft: (id: string, data: { subject?: string; body?: string }) =>
    apiClient.put<{ data: MarketingDraft }>(`/ai/drafts/${id}`, data),

  approveDraft: (id: string) =>
    apiClient.post<{ data: MarketingDraft }>(`/ai/drafts/${id}/approve`),

  rejectDraft: (id: string) =>
    apiClient.post<{ data: MarketingDraft }>(`/ai/drafts/${id}/reject`),

  // ── Waitlist Triage ─────────────────────────────────────────────────────

  getSessionsWithWaitlist: () =>
    apiClient.get<{ data: WaitlistSession[] }>("/ai/waitlist-triage/sessions"),

  getWaitlistScores: (sessionId: string) =>
    apiClient.get<{ data: WaitlistScore[] }>(`/ai/waitlist-triage/${sessionId}`),

  rerankWaitlist: (sessionId: string) =>
    apiClient.post<{ data: WaitlistScore[] }>(`/ai/waitlist-triage/${sessionId}/rerank`),

  setWaitlistMode: (data: { studio_id: string; mode: string }) =>
    apiClient.put<{ data: { studio_id: string; name: string; mode: string } }>(
      "/ai/waitlist-triage/mode", data,
    ),

  // ── Dynamic Pricing ─────────────────────────────────────────────────────

  getPricingRules: (studioId: string) =>
    apiClient.get<{ data: PricingRule[] }>(`/ai/pricing/rules/${studioId}`),

  createPricingRule: (data: {
    studio_id: string;
    name: string;
    rule_type: string;
    config?: Record<string, unknown>;
    is_active?: boolean;
  }) => apiClient.post<{ data: PricingRule }>("/ai/pricing/rules", data),

  updatePricingRule: (ruleId: string, data: Partial<PricingRule>) =>
    apiClient.put<{ data: PricingRule }>(`/ai/pricing/rules/${ruleId}`, data),

  deletePricingRule: (ruleId: string) =>
    apiClient.delete(`/ai/pricing/rules/${ruleId}`),

  triggerPriceSuggestions: (studioId: string) =>
    apiClient.post<{ data: PriceSuggestion[] }>(`/ai/pricing/suggest/${studioId}`),

  getPriceSuggestions: (studioId: string, status?: string) =>
    apiClient.get<{ data: PriceSuggestion[] }>(`/ai/pricing/suggestions/${studioId}`, {
      params: status ? { status } : undefined,
    }),

  approvePriceSuggestion: (adjustmentId: string) =>
    apiClient.post<{ data: PriceSuggestion }>(`/ai/pricing/suggestions/${adjustmentId}/approve`),

  rejectPriceSuggestion: (adjustmentId: string) =>
    apiClient.post<{ data: PriceSuggestion }>(`/ai/pricing/suggestions/${adjustmentId}/reject`),

  // ── Reviews ─────────────────────────────────────────────────────────────

  listReviews: (params?: { sentiment?: string; min_rating?: number }) =>
    apiClient.get<{ data: Review[] }>("/ai/reviews", { params }),

  getReviewStats: () =>
    apiClient.get<{ data: ReviewStats }>("/ai/reviews/stats"),

  getReview: (reviewId: string) =>
    apiClient.get<{ data: Review }>(`/ai/reviews/${reviewId}`),

  respondToReview: (reviewId: string, data: { response_text: string }) =>
    apiClient.post<{ data: Review }>(`/ai/reviews/${reviewId}/respond`, data),

  flagReview: (reviewId: string, data: { reason: string }) =>
    apiClient.post<{ data: Review }>(`/ai/reviews/${reviewId}/flag`, data),

  // ── Member Insights ─────────────────────────────────────────────────────

  getMemberInsight: (memberId: string) =>
    apiClient.get<{ data: { summary: string; highlights: string[]; recommendations: string[] } }>(
      `/ai/member-insight/${memberId}`
    ),

  // ── Schedule Analysis ─────────────────────────────────────────────────

  analyzeSchedule: () =>
    apiClient.post<{ data: { analysis: string; summary: Record<string, unknown> } }>(
      "/ai/schedule-analysis"
    ),
};
