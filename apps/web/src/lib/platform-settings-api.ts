import { apiClient } from "./api-client";

export interface PlatformConfig {
  id: string;
  sendgrid_api_key: string | null;
  sendgrid_from_email: string;
  sendgrid_from_name: string;
  sendgrid_inbound_webhook_secret: string | null;
  platform_admin_alert_email: string;
  support_escalation_email: string;
  google_ads_developer_token: string | null;
  google_ads_login_customer_id: string | null;
  google_client_id: string | null;
  google_client_secret: string | null;
  meta_app_id: string | null;
  meta_app_secret: string | null;
  meta_page_access_token: string | null;
  meta_page_id: string | null;
  instagram_business_account_id: string | null;
  created_at: string;
  updated_at: string;
}

export const platformSettingsApi = {
  getConfig: () =>
    apiClient.get<{ data: PlatformConfig }>("/platform/settings/config"),

  updateConfig: (data: Partial<PlatformConfig>) =>
    apiClient.put<{ data: PlatformConfig }>("/platform/settings/config", data),

  testEmail: () =>
    apiClient.post<{ data: { valid: boolean; error?: string; scopes?: string[] } }>(
      "/platform/settings/config/test-email"
    ),
};
