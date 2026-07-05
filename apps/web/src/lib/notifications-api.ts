import { apiClient } from "./api-client";

export const notificationsApi = {
  list: (limit = 50) => apiClient.get(`/notifications?limit=${limit}`),
  unreadCount: () => apiClient.get<{ data: { count: number } }>("/notifications/unread-count"),
  markRead: (id: string) => apiClient.put(`/notifications/${id}/read`),
  markAllRead: () => apiClient.put("/notifications/read-all"),
  remove: (id: string) => apiClient.delete(`/notifications/${id}`),
};
