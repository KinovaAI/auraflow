import { apiClient } from "./api-client";

export interface SocialAccount {
  id: string;
  platform: "facebook" | "instagram";
  page_id: string | null;
  page_name: string | null;
  instagram_business_id: string | null;
  is_active: boolean;
  connected_at: string;
}

export interface SocialStatus {
  facebook: SocialAccount | null;
  instagram: SocialAccount | null;
}

export interface SocialPost {
  id: string;
  account_id: string;
  platform: "facebook" | "instagram";
  content: string;
  media_urls: string[] | null;
  post_type: string;
  status: "draft" | "scheduled" | "published" | "failed";
  platform_post_id: string | null;
  scheduled_at: string | null;
  published_at: string | null;
  engagement: { likes?: number; comments?: number; shares?: number };
  ai_generated: boolean;
  created_at: string;
}

export interface SocialMessage {
  id: string;
  account_id: string;
  platform: "facebook" | "instagram";
  conversation_id: string | null;
  sender_id: string | null;
  sender_name: string | null;
  message_text: string | null;
  message_type: "message" | "comment" | "mention";
  post_id: string | null;
  ai_status: "pending" | "resolved" | "flagged" | "ignored";
  ai_response: string | null;
  responded_at: string | null;
  received_at: string | null;
  created_at: string;
}

export interface EngagementStats {
  engagement: { likes: number; comments: number; shares: number };
  messages: {
    total_messages: number;
    pending: number;
    resolved: number;
    flagged: number;
  };
  posts: {
    total_posts: number;
    published: number;
    drafts: number;
    scheduled: number;
    ai_generated: number;
  };
}

export interface AiPostResult {
  content: string;
  image_prompt: string | null;
  ai_generated: boolean;
}

export const studioSocialApi = {
  // Account
  connectFacebook: (data: { access_token: string; page_id: string }) =>
    apiClient.post<{ data: SocialAccount }>("/social/connect/facebook", data),

  connectInstagram: (data: { instagram_business_id: string }) =>
    apiClient.post<{ data: SocialAccount }>("/social/connect/instagram", data),

  getStatus: () =>
    apiClient.get<{ data: SocialStatus }>("/social/status"),

  disconnect: (account_id: string) =>
    apiClient.post<{ data: { disconnected: boolean } }>("/social/disconnect", { account_id }),

  // Posts
  listPosts: (params?: { status?: string; limit?: number }) =>
    apiClient.get<{ data: SocialPost[] }>("/social/posts", { params }),

  createPost: (data: { content: string; platform?: string; media_urls?: string[]; scheduled_at?: string }) =>
    apiClient.post<{ data: SocialPost }>("/social/posts", data),

  generateAiPost: () =>
    apiClient.post<{ data: AiPostResult }>("/social/posts/generate"),

  publishPost: (id: string) =>
    apiClient.post<{ data: SocialPost }>(`/social/posts/${id}/publish`),

  deletePost: (id: string) =>
    apiClient.delete(`/social/posts/${id}`),

  // Messages
  listMessages: (params?: { status?: string; limit?: number }) =>
    apiClient.get<{ data: SocialMessage[] }>("/social/messages", { params }),

  respondToMessage: (id: string, response: string) =>
    apiClient.post<{ data: SocialMessage }>(`/social/messages/${id}/respond`, { response }),

  aiRespondToMessage: (id: string) =>
    apiClient.post<{ data: SocialMessage }>(`/social/messages/${id}/ai-respond`),

  // Stats
  getStats: () =>
    apiClient.get<{ data: EngagementStats }>("/social/stats"),
};
