import { apiClient } from "./api-client";

export const activityApi = {
  feed: (limit = 50) => apiClient.get(`/activity/feed?limit=${limit}`),
  memberTimeline: (memberId: string, limit = 50) =>
    apiClient.get(`/activity/member/${memberId}?limit=${limit}`),
};
