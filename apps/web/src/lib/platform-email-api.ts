import { apiClient } from "./api-client";

export interface PlatformEmail {
  id: string;
  message_id: string | null;
  mailbox: "hello" | "support";
  from_email: string;
  from_name: string | null;
  to_email: string;
  subject: string | null;
  body_text: string | null;
  body_html: string | null;
  ai_status: "pending" | "processing" | "resolved" | "escalated" | "failed";
  ai_response: string | null;
  ai_summary: string | null;
  ai_actions: Array<{ tool: string; input: Record<string, unknown>; result_preview: string }> | null;
  escalated_to: string | null;
  escalation_reason: string | null;
  resolved_at: string | null;
  account_id: string | null;
  account_email: string | null;
  created_at: string;
  updated_at: string;
}

export interface EmailStats {
  total: number;
  pending: number;
  resolved_today: number;
  escalated: number;
  failed: number;
  avg_response_seconds: number;
}

export interface EmailAccount {
  id: string;
  email_address: string;
  display_name: string;
  imap_host: string;
  imap_port: number;
  smtp_host: string;
  smtp_port: number;
  is_active: boolean;
  last_checked_at: string | null;
  last_uid: number;
  created_at: string;
  updated_at: string;
}

export interface EmailAccountCreate {
  email_address: string;
  display_name?: string;
  imap_host?: string;
  imap_port?: number;
  imap_use_tls?: boolean;
  smtp_host?: string;
  smtp_port?: number;
  smtp_use_tls?: boolean;
  username?: string;
  password: string;
  is_active?: boolean;
}

export interface ConnectionTestResult {
  imap: boolean;
  smtp: boolean;
  imap_error: string | null;
  smtp_error: string | null;
}

export const platformEmailApi = {
  // Email accounts (IMAP/SMTP)
  listAccounts: () =>
    apiClient.get<{ data: EmailAccount[] }>("/platform/emails/accounts"),

  createAccount: (data: EmailAccountCreate) =>
    apiClient.post<{ data: EmailAccount }>("/platform/emails/accounts", data),

  updateAccount: (id: string, data: Partial<EmailAccountCreate>) =>
    apiClient.put<{ data: EmailAccount }>(`/platform/emails/accounts/${id}`, data),

  deleteAccount: (id: string) =>
    apiClient.delete(`/platform/emails/accounts/${id}`),

  testAccount: (id: string) =>
    apiClient.post<{ data: ConnectionTestResult }>(`/platform/emails/accounts/${id}/test`),

  checkMail: () =>
    apiClient.post<{ data: { accounts_checked: number; total_fetched: number; errors: Array<{ account_id: string; error: string }> } }>(
      "/platform/emails/check-mail"
    ),

  checkMailForAccount: (id: string) =>
    apiClient.post<{ data: { fetched: number } }>(`/platform/emails/accounts/${id}/check-mail`),

  // Email inbox
  list: (params?: { status?: string; mailbox?: string; limit?: number; offset?: number }) =>
    apiClient.get<{ data: PlatformEmail[] }>("/platform/emails", { params }),

  stats: () =>
    apiClient.get<{ data: EmailStats }>("/platform/emails/stats"),

  get: (id: string) =>
    apiClient.get<{ data: PlatformEmail }>(`/platform/emails/${id}`),

  process: (id: string) =>
    apiClient.post<{ data: PlatformEmail }>(`/platform/emails/${id}/process`),

  respond: (id: string, body: string) =>
    apiClient.post<{ data: PlatformEmail }>(`/platform/emails/${id}/respond`, { body }),

  escalate: (id: string, reason: string) =>
    apiClient.post<{ data: PlatformEmail }>(`/platform/emails/${id}/escalate`, { reason }),

  resolve: (id: string) =>
    apiClient.post<{ data: PlatformEmail }>(`/platform/emails/${id}/resolve`),
};
