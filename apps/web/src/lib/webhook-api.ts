import { apiClient } from "./api-client";

export const webhookApi = {
  listConfigs: () => apiClient.get("/webhook-configs"),
  createConfig: (data: Record<string, unknown>) => apiClient.post("/webhook-configs", data),
  updateConfig: (id: string, data: Record<string, unknown>) =>
    apiClient.put(`/webhook-configs/${id}`, data),
  deleteConfig: (id: string) => apiClient.delete(`/webhook-configs/${id}`),
  listDeliveries: (params?: Record<string, unknown>) =>
    apiClient.get("/webhook-configs/deliveries", { params }),
  retryDelivery: (id: string) =>
    apiClient.post(`/webhook-configs/deliveries/${id}/retry`),
};
