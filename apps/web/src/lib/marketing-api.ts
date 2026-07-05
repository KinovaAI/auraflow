import { apiClient } from "./api-client";

// ── Campaign Types ──────────────────────────────────────────────────────────

export interface Campaign {
  id: string;
  name: string;
  subject: string;
  html_content?: string;
  audience_filter?: string;
  status: "draft" | "scheduled" | "sending" | "sent" | "cancelled";
  recipients?: number;
  delivered?: number;
  sent_at?: string;
  created_by?: string;
  created_at: string;
  updated_at?: string;
}

export interface CampaignCreate {
  name: string;
  subject: string;
  html_content?: string;
  audience_filter?: Record<string, unknown>;
}

export interface CampaignUpdate {
  name?: string;
  subject?: string;
  html_content?: string;
  audience_filter?: string;
}

export interface AudiencePreview {
  tags?: string[];
  membership_type_ids?: string[];
}

export interface CampaignStats {
  id: string;
  name: string;
  subject: string;
  status: string;
  recipients?: number;
  delivered?: number;
  sent_at?: string;
  send_stats: {
    total_sends: number;
    sent: number;
    delivered: number;
    opened: number;
    clicked: number;
    bounced: number;
    failed: number;
  };
}

// ── SMS Types ───────────────────────────────────────────────────────────────

export interface SmsMessage {
  id: string;
  member_id?: string;
  to_phone: string;
  body: string;
  type: string;
  status: string;
  twilio_sid?: string;
  error_message?: string;
  created_at: string;
}

export interface SmsSend {
  to_phone: string;
  body: string;
  member_id?: string;
  sms_type?: string;
}

// ── Campaigns API ───────────────────────────────────────────────────────────

export const marketingApi = {
  // Campaigns
  createCampaign: (data: CampaignCreate) =>
    apiClient.post<{ data: Campaign }>("/marketing/campaigns", data),

  listCampaigns: (status?: string) =>
    apiClient.get<{ data: Campaign[] }>("/marketing/campaigns", {
      params: status ? { status } : undefined,
    }),

  getCampaign: (id: string) =>
    apiClient.get<{ data: Campaign }>(`/marketing/campaigns/${id}`),

  updateCampaign: (id: string, data: CampaignUpdate) =>
    apiClient.put<{ data: Campaign }>(`/marketing/campaigns/${id}`, data),

  deleteCampaign: (id: string) =>
    apiClient.delete<{ data: { deleted: boolean } }>(
      `/marketing/campaigns/${id}`
    ),

  sendCampaign: (id: string) =>
    apiClient.post<{ data: { sent: number; total: number } }>(
      `/marketing/campaigns/${id}/send`
    ),

  previewAudience: (filter: AudiencePreview) =>
    apiClient.post<{ data: { count: number; filter: Record<string, unknown> } }>(
      "/marketing/campaigns/preview-audience",
      filter
    ),

  getCampaignStats: (id: string) =>
    apiClient.get<{ data: CampaignStats }>(
      `/marketing/campaigns/${id}/stats`
    ),

  // SMS
  sendSms: (data: SmsSend) =>
    apiClient.post<{ data: SmsMessage }>("/marketing/sms/send", data),

  listSms: (params?: { member_id?: string; limit?: number }) =>
    apiClient.get<{ data: SmsMessage[] }>("/marketing/sms", { params }),
};
