"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { format } from "date-fns";
import {
  Loader2,
  Video,
  Search,
  Settings,
  FolderOpen,
  Film,
  Eye,
  Users,
  BarChart3,
  Youtube,
  Unlink,
} from "lucide-react";
import toast from "react-hot-toast";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import {
  videoApi,
  type Video as VideoType,
  type VideoConnectionStatus,
} from "@/lib/video-api";
import { apiClient } from "@/lib/api-client";
import { VideoGrid } from "@/components/video/video-grid";
import { EditVideoModal } from "@/components/video/edit-video-modal";
import { ConnectYouTubeModal } from "@/components/video/connect-youtube-modal";
import { ConnectMuxModal } from "@/components/video/connect-mux-modal";
import { ConnectZoomModal } from "@/components/video/connect-zoom-modal";
import { CategoryManager } from "@/components/video/category-manager";
import { SyncButton } from "@/components/video/sync-button";
import { VideoPlayer } from "@/components/video/video-player";

type Tab = "library" | "categories" | "settings";

export default function VideoPage() {
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<Tab>("library");
  const [sourceFilter, setSourceFilter] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [editingVideo, setEditingVideo] = useState<VideoType | null>(null);
  const [playingVideo, setPlayingVideo] = useState<VideoType | null>(null);
  const [showYouTubeConnect, setShowYouTubeConnect] = useState(false);
  const [showMuxConnect, setShowMuxConnect] = useState(false);
  const [showZoomConnect, setShowZoomConnect] = useState(false);

  // ── Queries ──────────────────────────────────────────────────────────────

  const { data: connectionStatus, isLoading: connectionLoading } = useQuery({
    queryKey: ["video-connection-status"],
    queryFn: () => videoApi.getConnectionStatus().then((r) => r.data.data),
  });

  const { data: videos, isLoading: videosLoading } = useQuery({
    queryKey: ["videos", sourceFilter, searchQuery],
    queryFn: () =>
      videoApi
        .listVideos({
          source: sourceFilter || undefined,
          search: searchQuery || undefined,
          limit: 200,
        })
        .then((r) => r.data.data),
  });

  const { data: stats } = useQuery({
    queryKey: ["video-stats"],
    queryFn: () => videoApi.getStats().then((r) => r.data.data),
  });

  const { data: categories } = useQuery({
    queryKey: ["video-categories"],
    queryFn: () => videoApi.listCategories().then((r) => r.data.data),
  });

  // ── Mutations ────────────────────────────────────────────────────────────

  const deleteMutation = useMutation({
    mutationFn: (videoId: string) => videoApi.deleteVideo(videoId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["videos"] });
      queryClient.invalidateQueries({ queryKey: ["video-stats"] });
      toast.success("Video deleted");
    },
    onError: () => toast.error("Failed to delete video"),
  });

  const disconnectYouTubeMutation = useMutation({
    mutationFn: () => videoApi.disconnectYouTube(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["video-connection-status"] });
      toast.success("YouTube disconnected");
    },
    onError: () => toast.error("Failed to disconnect YouTube"),
  });

  const disconnectMuxMutation = useMutation({
    mutationFn: () => videoApi.disconnectMux(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["video-connection-status"] });
      toast.success("Mux disconnected");
    },
    onError: () => toast.error("Failed to disconnect Mux"),
  });

  const disconnectZoomMutation = useMutation({
    mutationFn: () => videoApi.disconnectZoom(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["video-connection-status"] });
      toast.success("Zoom disconnected");
    },
    onError: () => toast.error("Failed to disconnect Zoom"),
  });

  const updateZoomSettingsMutation = useMutation({
    mutationFn: (data: { auto_record?: boolean; auto_publish?: boolean }) =>
      videoApi.updateZoomSettings(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["video-connection-status"] });
    },
    onError: () => toast.error("Failed to update Zoom settings"),
  });

  // ── Handlers ─────────────────────────────────────────────────────────────

  function handleDelete(video: VideoType) {
    if (!window.confirm(`Delete "${video.title}"? This cannot be undone.`)) {
      return;
    }
    deleteMutation.mutate(video.id);
  }

  const hasAnyProvider =
    connectionStatus?.youtube_connected || connectionStatus?.mux_connected || connectionStatus?.zoom_connected;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Video Library</h1>
          <p className="text-sm text-gray-500">
            On-demand classes and recorded content
          </p>
        </div>
      </div>

      {/* Stats cards */}
      {stats && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Card>
            <CardContent className="pt-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-gray-500">
                    Total Videos
                  </p>
                  <p className="mt-1 text-2xl font-bold text-gray-900">
                    {stats.total_videos}
                  </p>
                </div>
                <div className="rounded-full bg-indigo-100 p-2">
                  <Film className="h-5 w-5 text-indigo-600" />
                </div>
              </div>
              <p className="mt-2 text-xs text-gray-400">
                {stats.published_videos} published
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="pt-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-gray-500">
                    Total Views
                  </p>
                  <p className="mt-1 text-2xl font-bold text-gray-900">
                    {stats.total_views}
                  </p>
                </div>
                <div className="rounded-full bg-green-100 p-2">
                  <Eye className="h-5 w-5 text-green-600" />
                </div>
              </div>
              <p className="mt-2 text-xs text-gray-400">All time</p>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="pt-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-gray-500">
                    Unique Viewers
                  </p>
                  <p className="mt-1 text-2xl font-bold text-gray-900">
                    {stats.unique_viewers}
                  </p>
                </div>
                <div className="rounded-full bg-blue-100 p-2">
                  <Users className="h-5 w-5 text-blue-600" />
                </div>
              </div>
              <p className="mt-2 text-xs text-gray-400">All time</p>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="pt-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-gray-500">Sources</p>
                  <p className="mt-1 text-2xl font-bold text-gray-900">
                    {(stats.youtube_videos > 0 ? 1 : 0) +
                      (stats.mux_videos > 0 ? 1 : 0) +
                      ((stats.zoom_videos ?? 0) > 0 ? 1 : 0)}
                  </p>
                </div>
                <div className="rounded-full bg-purple-100 p-2">
                  <BarChart3 className="h-5 w-5 text-purple-600" />
                </div>
              </div>
              <p className="mt-2 text-xs text-gray-400">
                {stats.youtube_videos} YouTube, {stats.mux_videos} Mux{(stats.zoom_videos ?? 0) > 0 ? `, ${stats.zoom_videos} Zoom` : ""}
              </p>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-4 overflow-x-auto border-b border-gray-200">
        {(
          [
            {
              key: "library" as const,
              label: "Library",
              count: videos?.length,
            },
            {
              key: "categories" as const,
              label: "Categories",
              count: categories?.length,
            },
            { key: "settings" as const, label: "Settings" },
          ] as const
        ).map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`whitespace-nowrap border-b-2 px-1 pb-3 text-sm font-medium ${
              activeTab === tab.key
                ? "border-indigo-500 text-indigo-600"
                : "border-transparent text-gray-500 hover:text-gray-700"
            }`}
          >
            {tab.label}
            {"count" in tab && tab.count != null ? (
              <span className="ml-1.5 rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-600">
                {tab.count}
              </span>
            ) : null}
          </button>
        ))}
      </div>

      {/* ── Library Tab ──────────────────────────────────────────────────── */}
      {activeTab === "library" && (
        <>
          {/* Toolbar */}
          <div className="flex flex-wrap items-center gap-3">
            <div className="relative flex-1 sm:max-w-xs">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
              <Input
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search videos..."
                className="pl-9"
              />
            </div>

            <select
              value={sourceFilter}
              onChange={(e) => setSourceFilter(e.target.value)}
              className="flex h-10 rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:border-transparent focus:outline-none focus:ring-2 focus:ring-indigo-500"
            >
              <option value="">All Sources</option>
              <option value="youtube">YouTube</option>
              <option value="mux">Mux</option>
              <option value="zoom_recording">Zoom Recording</option>
              <option value="manual">Manual Upload</option>
            </select>

            <SyncButton />
          </div>

          {/* Video grid or empty state */}
          {videosLoading ? (
            <div className="flex items-center justify-center py-20">
              <Loader2 className="h-8 w-8 animate-spin text-indigo-600" />
            </div>
          ) : !videos?.length ? (
            <Card>
              <CardContent className="flex flex-col items-center py-16">
                <div className="rounded-full bg-indigo-50 p-4">
                  <Video className="h-8 w-8 text-indigo-400" />
                </div>
                <h2 className="mt-4 text-lg font-medium text-gray-900">
                  No videos yet
                </h2>
                <p className="mt-1 max-w-sm text-center text-sm text-gray-500">
                  {hasAnyProvider
                    ? 'Click "Sync" to import videos from your connected providers.'
                    : "Connect a video provider in the Settings tab to get started."}
                </p>
                {!hasAnyProvider && (
                  <Button
                    className="mt-4"
                    variant="outline"
                    onClick={() => setActiveTab("settings")}
                  >
                    <Settings className="mr-1 h-4 w-4" />
                    Go to Settings
                  </Button>
                )}
              </CardContent>
            </Card>
          ) : (
            <VideoGrid
              videos={videos}
              onEdit={(v) => setEditingVideo(v)}
              onDelete={handleDelete}
              onClick={(v) => setPlayingVideo(v)}
            />
          )}
        </>
      )}

      {/* ── Categories Tab ───────────────────────────────────────────────── */}
      {activeTab === "categories" && <CategoryManager />}

      {/* ── Settings Tab ─────────────────────────────────────────────────── */}
      {activeTab === "settings" && (
        <div className="space-y-6">
          <div>
            <h3 className="text-base font-semibold text-gray-900">
              Video Providers
            </h3>
            <p className="text-sm text-gray-500">
              Connect your own video accounts. AuraFlow uses your API keys to
              sync and display videos -- we never host or stream content
              ourselves.
            </p>
          </div>

          {connectionLoading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-6 w-6 animate-spin text-indigo-600" />
            </div>
          ) : (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {/* YouTube */}
              <Card>
                <CardContent className="pt-6">
                  <div className="flex items-start justify-between">
                    <div className="flex items-center gap-3">
                      <div className="rounded-lg bg-red-100 p-2">
                        <Youtube className="h-5 w-5 text-red-600" />
                      </div>
                      <div>
                        <p className="text-sm font-semibold text-gray-900">
                          YouTube
                        </p>
                        <p className="text-xs text-gray-500">
                          Import videos from your channel
                        </p>
                      </div>
                    </div>
                    {connectionStatus?.youtube_connected ? (
                      <span className="rounded-full bg-green-50 px-2 py-0.5 text-xs font-medium text-green-700">
                        Connected
                      </span>
                    ) : (
                      <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-500">
                        Not connected
                      </span>
                    )}
                  </div>

                  {connectionStatus?.youtube_connected && (
                    <div className="mt-3 space-y-1 rounded-md bg-gray-50 px-3 py-2">
                      {connectionStatus.youtube_channel_id && (
                        <p className="text-xs text-gray-600">
                          Channel:{" "}
                          <span className="font-mono">
                            {connectionStatus.youtube_channel_id}
                          </span>
                        </p>
                      )}
                      {connectionStatus.youtube_connected_at && (
                        <p className="text-xs text-gray-400">
                          Connected{" "}
                          {format(
                            new Date(connectionStatus.youtube_connected_at),
                            "MMM d, yyyy"
                          )}
                        </p>
                      )}
                    </div>
                  )}

                  <div className="mt-4 flex flex-wrap gap-2">
                    {connectionStatus?.youtube_connected ? (
                      <>
                        <Button
                          size="sm"
                          onClick={async () => {
                            try {
                              const r = await apiClient.get("/video/connect/youtube/oauth");
                              const url = (r as any).data?.data?.oauth_url;
                              if (url) window.location.href = url;
                              else toast.error("Google OAuth not configured on this server. Add GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET.");
                            } catch (e: any) {
                              toast.error(e?.response?.data?.detail || "OAuth not available");
                            }
                          }}
                        >
                          Authorize Unlisted Videos
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => {
                            if (
                              window.confirm(
                                "Disconnect YouTube? Your synced videos will remain but new syncs will stop."
                              )
                            ) {
                              disconnectYouTubeMutation.mutate();
                            }
                          }}
                          disabled={disconnectYouTubeMutation.isPending}
                        >
                          {disconnectYouTubeMutation.isPending ? (
                            <Loader2 className="mr-1 h-4 w-4 animate-spin" />
                          ) : (
                            <Unlink className="mr-1 h-4 w-4" />
                          )}
                          Disconnect
                        </Button>
                      </>
                    ) : (
                      <Button
                        size="sm"
                        onClick={() => setShowYouTubeConnect(true)}
                      >
                        Connect YouTube
                      </Button>
                    )}
                  </div>
                </CardContent>
              </Card>

              {/* Mux */}
              <Card>
                <CardContent className="pt-6">
                  <div className="flex items-start justify-between">
                    <div className="flex items-center gap-3">
                      <div className="rounded-lg bg-pink-100 p-2">
                        <Film className="h-5 w-5 text-pink-600" />
                      </div>
                      <div>
                        <p className="text-sm font-semibold text-gray-900">
                          Mux
                        </p>
                        <p className="text-xs text-gray-500">
                          Stream and upload via Mux
                        </p>
                      </div>
                    </div>
                    {connectionStatus?.mux_connected ? (
                      <span className="rounded-full bg-green-50 px-2 py-0.5 text-xs font-medium text-green-700">
                        Connected
                      </span>
                    ) : (
                      <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-500">
                        Not connected
                      </span>
                    )}
                  </div>

                  {connectionStatus?.mux_connected && (
                    <div className="mt-3 space-y-1 rounded-md bg-gray-50 px-3 py-2">
                      {connectionStatus.mux_connected_at && (
                        <p className="text-xs text-gray-400">
                          Connected{" "}
                          {format(
                            new Date(connectionStatus.mux_connected_at),
                            "MMM d, yyyy"
                          )}
                        </p>
                      )}
                    </div>
                  )}

                  <div className="mt-4">
                    {connectionStatus?.mux_connected ? (
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => {
                          if (
                            window.confirm(
                              "Disconnect Mux? Your synced videos will remain but new syncs will stop."
                            )
                          ) {
                            disconnectMuxMutation.mutate();
                          }
                        }}
                        disabled={disconnectMuxMutation.isPending}
                      >
                        {disconnectMuxMutation.isPending ? (
                          <Loader2 className="mr-1 h-4 w-4 animate-spin" />
                        ) : (
                          <Unlink className="mr-1 h-4 w-4" />
                        )}
                        Disconnect
                      </Button>
                    ) : (
                      <Button
                        size="sm"
                        onClick={() => setShowMuxConnect(true)}
                      >
                        Connect Mux
                      </Button>
                    )}
                  </div>
                </CardContent>
              </Card>

              {/* Zoom */}
              <Card>
                <CardContent className="pt-6">
                  <div className="flex items-start justify-between">
                    <div className="flex items-center gap-3">
                      <div className="rounded-lg bg-blue-100 p-2">
                        <Video className="h-5 w-5 text-blue-600" />
                      </div>
                      <div>
                        <p className="text-sm font-semibold text-gray-900">
                          Zoom
                        </p>
                        <p className="text-xs text-gray-500">
                          Virtual classes &amp; recordings
                        </p>
                      </div>
                    </div>
                    {connectionStatus?.zoom_connected ? (
                      <span className="rounded-full bg-green-50 px-2 py-0.5 text-xs font-medium text-green-700">
                        Connected
                      </span>
                    ) : (
                      <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-500">
                        Not connected
                      </span>
                    )}
                  </div>

                  {connectionStatus?.zoom_connected && (
                    <div className="mt-3 space-y-3">
                      <div className="space-y-1 rounded-md bg-gray-50 px-3 py-2">
                        {connectionStatus.zoom_account_id && (
                          <p className="text-xs text-gray-600">
                            Account:{" "}
                            <span className="font-mono">
                              {connectionStatus.zoom_account_id}
                            </span>
                          </p>
                        )}
                        {connectionStatus.zoom_connected_at && (
                          <p className="text-xs text-gray-400">
                            Connected{" "}
                            {format(
                              new Date(connectionStatus.zoom_connected_at),
                              "MMM d, yyyy"
                            )}
                          </p>
                        )}
                      </div>

                      {/* Zoom Settings Toggles */}
                      <div className="space-y-2">
                        <div className="flex items-center justify-between">
                          <span className="text-xs text-gray-600">Auto-record classes</span>
                          <button
                            type="button"
                            role="switch"
                            aria-checked={connectionStatus.zoom_auto_record ?? false}
                            onClick={() =>
                              updateZoomSettingsMutation.mutate({
                                auto_record: !connectionStatus.zoom_auto_record,
                              })
                            }
                            className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors ${
                              connectionStatus.zoom_auto_record ? "bg-indigo-600" : "bg-gray-200"
                            }`}
                          >
                            <span
                              className={`pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow ring-0 transition-transform ${
                                connectionStatus.zoom_auto_record ? "translate-x-4" : "translate-x-0"
                              }`}
                            />
                          </button>
                        </div>
                        <div className="flex items-center justify-between">
                          <span className="text-xs text-gray-600">Auto-publish to library</span>
                          <button
                            type="button"
                            role="switch"
                            aria-checked={connectionStatus.zoom_auto_publish ?? false}
                            onClick={() =>
                              updateZoomSettingsMutation.mutate({
                                auto_publish: !connectionStatus.zoom_auto_publish,
                              })
                            }
                            className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors ${
                              connectionStatus.zoom_auto_publish ? "bg-indigo-600" : "bg-gray-200"
                            }`}
                          >
                            <span
                              className={`pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow ring-0 transition-transform ${
                                connectionStatus.zoom_auto_publish ? "translate-x-4" : "translate-x-0"
                              }`}
                            />
                          </button>
                        </div>
                      </div>
                    </div>
                  )}

                  <div className="mt-4">
                    {connectionStatus?.zoom_connected ? (
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => {
                          if (
                            window.confirm(
                              "Disconnect Zoom? Virtual class creation will stop working."
                            )
                          ) {
                            disconnectZoomMutation.mutate();
                          }
                        }}
                        disabled={disconnectZoomMutation.isPending}
                      >
                        {disconnectZoomMutation.isPending ? (
                          <Loader2 className="mr-1 h-4 w-4 animate-spin" />
                        ) : (
                          <Unlink className="mr-1 h-4 w-4" />
                        )}
                        Disconnect
                      </Button>
                    ) : (
                      <Button
                        size="sm"
                        onClick={() => setShowZoomConnect(true)}
                      >
                        Connect Zoom
                      </Button>
                    )}
                  </div>
                </CardContent>
              </Card>
            </div>
          )}
        </div>
      )}

      {/* ── Modals ───────────────────────────────────────────────────────── */}

      {editingVideo && (
        <EditVideoModal
          video={editingVideo}
          onClose={() => setEditingVideo(null)}
          onSaved={() => setEditingVideo(null)}
        />
      )}

      {playingVideo && (
        <VideoPlayer
          video={playingVideo}
          onClose={() => setPlayingVideo(null)}
        />
      )}

      {showYouTubeConnect && (
        <ConnectYouTubeModal
          onClose={() => setShowYouTubeConnect(false)}
          onConnected={() => setShowYouTubeConnect(false)}
        />
      )}

      {showMuxConnect && (
        <ConnectMuxModal
          onClose={() => setShowMuxConnect(false)}
          onConnected={() => setShowMuxConnect(false)}
        />
      )}

      {showZoomConnect && (
        <ConnectZoomModal
          onClose={() => setShowZoomConnect(false)}
          onConnected={() => setShowZoomConnect(false)}
        />
      )}
    </div>
  );
}
