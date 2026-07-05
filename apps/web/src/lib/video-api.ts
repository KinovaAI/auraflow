import { apiClient } from "./api-client";

// ── Types ────────────────────────────────────────────────────────────────────

export interface VideoConnectionStatus {
  youtube_connected: boolean;
  youtube_channel_id?: string;
  youtube_connected_at?: string;
  youtube_upload_authorized?: boolean;
  mux_connected: boolean;
  mux_connected_at?: string;
  zoom_connected: boolean;
  zoom_account_id?: string;
  zoom_connected_at?: string;
  zoom_auto_record?: boolean;
  zoom_auto_publish?: boolean;
}

export interface Video {
  id: string;
  source: "youtube" | "mux" | "zoom_recording" | "manual";
  title: string;
  description?: string;
  thumbnail_url?: string;
  duration_seconds?: number;
  category_id?: string;
  category_name?: string;
  visibility: string;
  is_published: boolean;
  tags: string[];
  youtube_video_id?: string;
  mux_playback_id?: string;
  created_at: string;
  updated_at?: string;
}

export interface VideoCategory {
  id: string;
  name: string;
  description?: string;
  slug: string;
  sort_order: number;
  is_active: boolean;
  video_count: number;
}

export interface VideoStats {
  total_videos: number;
  published_videos: number;
  youtube_videos: number;
  mux_videos: number;
  zoom_videos: number;
  total_views: number;
  unique_viewers: number;
  most_popular?: Video;
}

export interface SyncResult {
  synced: number;
  new: number;
  updated: number;
  source: string;
}

// ── API ──────────────────────────────────────────────────────────────────────

export const videoApi = {
  // ── Provider Connection ──────────────────────────────────────────────────

  getConnectionStatus: () =>
    apiClient.get<{ data: VideoConnectionStatus }>("/video/connect/status"),

  connectYouTube: (apiKey: string, channelId: string) =>
    apiClient.post<{ data: { connected: boolean } }>("/video/connect/youtube", {
      api_key: apiKey,
      channel_id: channelId,
    }),

  connectMux: (tokenId: string, tokenSecret: string) =>
    apiClient.post<{ data: { connected: boolean } }>("/video/connect/mux", {
      token_id: tokenId,
      token_secret: tokenSecret,
    }),

  testYouTube: (apiKey: string, channelId: string) =>
    apiClient.post<{ data: { success: boolean } }>("/video/connect/youtube/test", {
      api_key: apiKey,
      channel_id: channelId,
    }),

  testMux: (tokenId: string, tokenSecret: string) =>
    apiClient.post<{ data: { success: boolean } }>("/video/connect/mux/test", {
      token_id: tokenId,
      token_secret: tokenSecret,
    }),

  disconnectYouTube: () =>
    apiClient.delete<{ data: { disconnected: boolean } }>("/video/connect/youtube"),

  disconnectMux: () =>
    apiClient.delete<{ data: { disconnected: boolean } }>("/video/connect/mux"),

  // ── Video Library (Admin) ────────────────────────────────────────────────

  listVideos: (params?: {
    category_id?: string;
    source?: string;
    search?: string;
    limit?: number;
    offset?: number;
  }) => apiClient.get<{ data: Video[] }>("/video/library", { params }),

  getVideo: (videoId: string) =>
    apiClient.get<{ data: Video }>(`/video/library/${videoId}`),

  updateVideo: (
    videoId: string,
    data: {
      title?: string;
      description?: string;
      category_id?: string;
      visibility?: string;
      is_published?: boolean;
      tags?: string[];
      sort_order?: number;
      membership_type_ids?: string[];
    }
  ) => apiClient.put<{ data: Video }>(`/video/library/${videoId}`, data),

  deleteVideo: (videoId: string) =>
    apiClient.delete<{ data: { deleted: boolean } }>(`/video/library/${videoId}`),

  // ── Sync ─────────────────────────────────────────────────────────────────

  syncAll: () =>
    apiClient.post<{ data: SyncResult[] }>("/video/sync"),

  syncYouTube: () =>
    apiClient.post<{ data: SyncResult }>("/video/sync/youtube"),

  syncMux: () =>
    apiClient.post<{ data: SyncResult }>("/video/sync/mux"),

  // ── Categories ───────────────────────────────────────────────────────────

  listCategories: () =>
    apiClient.get<{ data: VideoCategory[] }>("/video/categories"),

  createCategory: (data: { name: string; description?: string; slug?: string }) =>
    apiClient.post<{ data: VideoCategory }>("/video/categories", data),

  updateCategory: (
    categoryId: string,
    data: {
      name?: string;
      description?: string;
      slug?: string;
      sort_order?: number;
      is_active?: boolean;
    }
  ) => apiClient.put<{ data: VideoCategory }>(`/video/categories/${categoryId}`, data),

  deleteCategory: (categoryId: string) =>
    apiClient.delete<{ data: { deleted: boolean } }>(`/video/categories/${categoryId}`),

  // ── Mux Upload ───────────────────────────────────────────────────────────

  createMuxUpload: (corsOrigin?: string) =>
    apiClient.post<{ data: { success: boolean; upload_url: string; upload_id: string } }>(
      "/video/upload/mux",
      { cors_origin: corsOrigin }
    ),

  // ── YouTube OAuth + Upload ───────────────────────────────────────────────

  getYouTubeOAuthUrl: () =>
    apiClient.get<{ data: { oauth_url: string } }>("/video/connect/youtube/oauth"),

  getYouTubeOAuthStatus: () =>
    apiClient.get<{ data: { upload_authorized: boolean } }>("/video/connect/youtube/oauth/status"),

  uploadToYouTube: (file: File, title: string, description: string = "", privacy: string = "unlisted") => {
    const formData = new FormData();
    formData.append("file", file);
    formData.append("title", title);
    formData.append("description", description);
    formData.append("privacy", privacy);
    return apiClient.post<{ data: { youtube_video_id: string; video_id: string; title: string } }>(
      "/video/upload/youtube",
      formData,
      { headers: { "Content-Type": "multipart/form-data" }, timeout: 600000 }
    );
  },

  // ── Member-Facing Browse ─────────────────────────────────────────────────

  browseVideos: (params?: {
    category_id?: string;
    limit?: number;
    offset?: number;
  }) => apiClient.get<{ data: Video[] }>("/video/browse", { params }),

  browseVideo: (videoId: string) =>
    apiClient.get<{ data: Video }>(`/video/browse/${videoId}`),

  recordView: (videoId: string, watchedSeconds: number = 0, completed: boolean = false) =>
    apiClient.post<{ data: { recorded: boolean } }>(`/video/browse/${videoId}/view`, {
      watched_seconds: watchedSeconds,
      completed,
    }),

  // ── Analytics ────────────────────────────────────────────────────────────

  getStats: () =>
    apiClient.get<{ data: VideoStats }>("/video/stats"),

  getVideoStats: (videoId: string) =>
    apiClient.get<{ data: Record<string, unknown> }>(`/video/stats/${videoId}`),

  // ── Zoom Integration ──────────────────────────────────────────────────

  connectZoom: (data: { account_id: string; client_id: string; client_secret: string; webhook_secret?: string }) =>
    apiClient.post<{ data: { connected: boolean } }>("/integrations/zoom/connect", data),

  testZoom: (data: { account_id: string; client_id: string; client_secret: string }) =>
    apiClient.post<{ data: { success: boolean; email?: string; display_name?: string } }>("/integrations/zoom/test", data),

  disconnectZoom: () =>
    apiClient.delete<{ data: { connected: boolean } }>("/integrations/zoom/disconnect"),

  getZoomStatus: () =>
    apiClient.get<{ data: { zoom_connected: boolean; zoom_account_id?: string; zoom_connected_at?: string; zoom_auto_record?: boolean; zoom_auto_publish?: boolean } }>("/integrations/zoom/status"),

  updateZoomSettings: (data: { auto_record?: boolean; auto_publish?: boolean }) =>
    apiClient.put<{ data: Record<string, unknown> }>("/integrations/zoom/settings", data),
};
