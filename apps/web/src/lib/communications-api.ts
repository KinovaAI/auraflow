import { apiClient } from "./api-client";

export interface CommunicationsStatus {
  sendgrid_connected: boolean;
  sendgrid_from_email?: string;
  sendgrid_from_name?: string;
  sendgrid_connected_at?: string;
  twilio_connected: boolean;
  twilio_phone_number?: string;
  twilio_connected_at?: string;
}

export const communicationsApi = {
  getStatus: () =>
    apiClient.get<CommunicationsStatus>("/integrations/communications/status"),

  // SendGrid
  connectSendGrid: (data: { api_key: string; from_email?: string; from_name?: string }) =>
    apiClient.post("/integrations/communications/sendgrid/connect", data),

  testSendGrid: (data: { api_key: string; from_email?: string; from_name?: string }) =>
    apiClient.post<{ success: boolean; message: string }>(
      "/integrations/communications/sendgrid/test",
      data,
    ),

  disconnectSendGrid: () =>
    apiClient.delete("/integrations/communications/sendgrid/disconnect"),

  // Twilio
  connectTwilio: (data: { account_sid: string; auth_token: string; phone_number: string }) =>
    apiClient.post("/integrations/communications/twilio/connect", data),

  testTwilio: (data: { account_sid: string; auth_token: string; phone_number: string }) =>
    apiClient.post<{ success: boolean; message: string }>(
      "/integrations/communications/twilio/test",
      data,
    ),

  disconnectTwilio: () =>
    apiClient.delete("/integrations/communications/twilio/disconnect"),
};
