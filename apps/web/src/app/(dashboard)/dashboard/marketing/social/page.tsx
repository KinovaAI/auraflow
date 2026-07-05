"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { format } from "date-fns";
import toast from "react-hot-toast";
import Link from "next/link";
import {
  Loader2,
  Share2,
  Plus,
  Send,
  Sparkles,
  Trash2,
  MessageSquare,
  ThumbsUp,
  MessageCircle,
  Facebook,
  Instagram,
  AlertCircle,
  CheckCircle2,
  Unplug,
  Bot,
  BarChart3,
  ArrowLeft,
  Clock,
  Flag,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  studioSocialApi,
  type SocialPost,
  type SocialMessage,
} from "@/lib/studio-social-api";

// ── Helpers ─────────────────────────────────────────────────────────────

const statusColors: Record<string, string> = {
  draft: "bg-gray-100 text-gray-600",
  scheduled: "bg-blue-50 text-blue-700",
  published: "bg-green-50 text-green-700",
  failed: "bg-red-50 text-red-600",
};

const aiStatusColors: Record<string, string> = {
  pending: "bg-yellow-50 text-yellow-700",
  resolved: "bg-green-50 text-green-700",
  flagged: "bg-red-50 text-red-600",
  ignored: "bg-gray-100 text-gray-500",
};

// ── Connect Facebook Dialog ─────────────────────────────────────────────

function ConnectFacebookDialog({
  onClose,
  onConnected,
}: {
  onClose: () => void;
  onConnected: () => void;
}) {
  const [accessToken, setAccessToken] = useState("");
  const [pageId, setPageId] = useState("");

  const connectMutation = useMutation({
    mutationFn: () =>
      studioSocialApi
        .connectFacebook({ access_token: accessToken, page_id: pageId })
        .then((r) => r.data.data),
    onSuccess: () => {
      toast.success("Facebook connected!");
      onConnected();
    },
    onError: () => toast.error("Failed to connect Facebook"),
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="w-full max-w-md rounded-lg bg-white p-6 shadow-xl">
        <h2 className="text-lg font-semibold text-gray-900">
          Connect Facebook Page
        </h2>
        <p className="mt-1 text-sm text-gray-500">
          Enter your Facebook Page access token and Page ID from the Meta
          Developer portal.
        </p>
        <div className="mt-4 space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700">
              Page Access Token
            </label>
            <input
              type="password"
              value={accessToken}
              onChange={(e) => setAccessToken(e.target.value)}
              className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              placeholder="EAAx..."
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700">
              Page ID
            </label>
            <input
              type="text"
              value={pageId}
              onChange={(e) => setPageId(e.target.value)}
              className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              placeholder="123456789..."
            />
          </div>
          <div className="flex justify-end gap-3 pt-2">
            <Button variant="outline" onClick={onClose}>
              Cancel
            </Button>
            <Button
              onClick={() => connectMutation.mutate()}
              disabled={
                !accessToken.trim() ||
                !pageId.trim() ||
                connectMutation.isPending
              }
            >
              {connectMutation.isPending && (
                <Loader2 className="mr-1 h-4 w-4 animate-spin" />
              )}
              Connect
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Connect Instagram Dialog ────────────────────────────────────────────

function ConnectInstagramDialog({
  onClose,
  onConnected,
}: {
  onClose: () => void;
  onConnected: () => void;
}) {
  const [igId, setIgId] = useState("");

  const connectMutation = useMutation({
    mutationFn: () =>
      studioSocialApi
        .connectInstagram({ instagram_business_id: igId })
        .then((r) => r.data.data),
    onSuccess: () => {
      toast.success("Instagram connected!");
      onConnected();
    },
    onError: (err: any) =>
      toast.error(
        err?.response?.data?.detail || "Failed to connect Instagram"
      ),
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="w-full max-w-md rounded-lg bg-white p-6 shadow-xl">
        <h2 className="text-lg font-semibold text-gray-900">
          Connect Instagram
        </h2>
        <p className="mt-1 text-sm text-gray-500">
          Enter your Instagram Business Account ID. This requires an active
          Facebook Page connection.
        </p>
        <div className="mt-4 space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700">
              Instagram Business ID
            </label>
            <input
              type="text"
              value={igId}
              onChange={(e) => setIgId(e.target.value)}
              className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              placeholder="17841400..."
            />
          </div>
          <div className="flex justify-end gap-3 pt-2">
            <Button variant="outline" onClick={onClose}>
              Cancel
            </Button>
            <Button
              onClick={() => connectMutation.mutate()}
              disabled={!igId.trim() || connectMutation.isPending}
            >
              {connectMutation.isPending && (
                <Loader2 className="mr-1 h-4 w-4 animate-spin" />
              )}
              Connect
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Create Post Dialog ──────────────────────────────────────────────────

function CreatePostDialog({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: () => void;
}) {
  const [platform, setPlatform] = useState<string>("facebook");
  const [content, setContent] = useState("");
  const [scheduledAt, setScheduledAt] = useState("");

  const createMutation = useMutation({
    mutationFn: () =>
      studioSocialApi
        .createPost({
          platform,
          content,
          scheduled_at: scheduledAt || undefined,
        })
        .then((r) => r.data.data),
    onSuccess: () => {
      toast.success(scheduledAt ? "Post scheduled" : "Draft created");
      onCreated();
    },
    onError: (err: any) =>
      toast.error(err?.response?.data?.detail || "Failed to create post"),
  });

  const generateMutation = useMutation({
    mutationFn: () =>
      studioSocialApi.generateAiPost().then((r) => r.data.data),
    onSuccess: (data) => {
      setContent(data.content);
      toast.success("AI content generated");
    },
    onError: () => toast.error("AI generation failed"),
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="w-full max-w-lg rounded-lg bg-white p-6 shadow-xl">
        <h2 className="text-lg font-semibold text-gray-900">Create Post</h2>
        <div className="mt-4 space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700">
              Platform
            </label>
            <select
              value={platform}
              onChange={(e) => setPlatform(e.target.value)}
              className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
            >
              <option value="facebook">Facebook</option>
              <option value="instagram">Instagram</option>
            </select>
          </div>

          {/* AI Generator */}
          <div className="rounded-lg bg-indigo-50 p-3">
            <p className="mb-2 text-xs font-medium text-indigo-700">
              AI Post Generator
            </p>
            <p className="mb-2 text-xs text-indigo-600">
              Generate a post based on today&apos;s schedule, events, and studio
              vibe.
            </p>
            <Button
              size="sm"
              onClick={() => generateMutation.mutate()}
              disabled={generateMutation.isPending}
            >
              {generateMutation.isPending ? (
                <Loader2 className="mr-1 h-3 w-3 animate-spin" />
              ) : (
                <Sparkles className="mr-1 h-3 w-3" />
              )}
              Generate with AI
            </Button>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700">
              Content
            </label>
            <textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              rows={6}
              className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
              placeholder="Write your post content..."
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700">
              Schedule (optional)
            </label>
            <input
              type="datetime-local"
              value={scheduledAt}
              onChange={(e) => setScheduledAt(e.target.value)}
              className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
            />
          </div>

          <div className="flex justify-end gap-3 pt-2">
            <Button type="button" variant="outline" onClick={onClose}>
              Cancel
            </Button>
            <Button
              onClick={() => createMutation.mutate()}
              disabled={!content.trim() || createMutation.isPending}
            >
              {createMutation.isPending && (
                <Loader2 className="mr-1 h-4 w-4 animate-spin" />
              )}
              {scheduledAt ? "Schedule Post" : "Create Draft"}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Reply Dialog ────────────────────────────────────────────────────────

function ReplyDialog({
  message,
  onClose,
  onReplied,
}: {
  message: SocialMessage;
  onClose: () => void;
  onReplied: () => void;
}) {
  const [reply, setReply] = useState(message.ai_response || "");

  const replyMutation = useMutation({
    mutationFn: () =>
      studioSocialApi
        .respondToMessage(message.id, reply)
        .then((r) => r.data.data),
    onSuccess: () => {
      toast.success("Reply sent");
      onReplied();
    },
    onError: () => toast.error("Failed to send reply"),
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="w-full max-w-md rounded-lg bg-white p-6 shadow-xl">
        <h2 className="text-lg font-semibold text-gray-900">
          Reply to {message.sender_name || "message"}
        </h2>
        <div className="mt-2 rounded bg-gray-50 p-3 text-sm text-gray-700">
          {message.message_text}
        </div>
        <div className="mt-4">
          <textarea
            value={reply}
            onChange={(e) => setReply(e.target.value)}
            rows={4}
            className="block w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
            placeholder="Type your reply..."
          />
        </div>
        <div className="mt-4 flex justify-end gap-3">
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button
            onClick={() => replyMutation.mutate()}
            disabled={!reply.trim() || replyMutation.isPending}
          >
            {replyMutation.isPending && (
              <Loader2 className="mr-1 h-4 w-4 animate-spin" />
            )}
            <Send className="mr-1 h-3 w-3" />
            Send Reply
          </Button>
        </div>
      </div>
    </div>
  );
}

// ── Main Page ───────────────────────────────────────────────────────────

export default function StudioSocialPage() {
  const queryClient = useQueryClient();
  const [activeSection, setActiveSection] = useState<
    "posts" | "messages" | "stats"
  >("posts");
  const [showCreate, setShowCreate] = useState(false);
  const [showConnectFb, setShowConnectFb] = useState(false);
  const [showConnectIg, setShowConnectIg] = useState(false);
  const [replyMessage, setReplyMessage] = useState<SocialMessage | null>(null);

  // ── Queries ──────────────────────────────────────────────────────────

  const { data: status, isLoading: statusLoading } = useQuery({
    queryKey: ["social-status"],
    queryFn: () => studioSocialApi.getStatus().then((r) => r.data.data),
  });

  const { data: posts, isLoading: postsLoading } = useQuery({
    queryKey: ["social-posts"],
    queryFn: () =>
      studioSocialApi.listPosts({ limit: 50 }).then((r) => r.data.data),
  });

  const { data: messages, isLoading: msgsLoading } = useQuery({
    queryKey: ["social-messages"],
    queryFn: () =>
      studioSocialApi.listMessages({ limit: 50 }).then((r) => r.data.data),
    refetchInterval: 30000,
  });

  const { data: stats } = useQuery({
    queryKey: ["social-stats"],
    queryFn: () => studioSocialApi.getStats().then((r) => r.data.data),
  });

  // ── Mutations ────────────────────────────────────────────────────────

  const publishMutation = useMutation({
    mutationFn: (id: string) =>
      studioSocialApi.publishPost(id).then((r) => r.data.data),
    onSuccess: () => {
      toast.success("Post published");
      queryClient.invalidateQueries({ queryKey: ["social-posts"] });
      queryClient.invalidateQueries({ queryKey: ["social-stats"] });
    },
    onError: (err: any) =>
      toast.error(err?.response?.data?.detail || "Publish failed"),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => studioSocialApi.deletePost(id),
    onSuccess: () => {
      toast.success("Post deleted");
      queryClient.invalidateQueries({ queryKey: ["social-posts"] });
    },
  });

  const disconnectMutation = useMutation({
    mutationFn: (id: string) => studioSocialApi.disconnect(id),
    onSuccess: () => {
      toast.success("Account disconnected");
      queryClient.invalidateQueries({ queryKey: ["social-status"] });
    },
  });

  const aiRespondMutation = useMutation({
    mutationFn: (id: string) =>
      studioSocialApi.aiRespondToMessage(id).then((r) => r.data.data),
    onSuccess: () => {
      toast.success("AI response sent");
      queryClient.invalidateQueries({ queryKey: ["social-messages"] });
    },
    onError: () => toast.error("AI response failed"),
  });

  const invalidateAll = () => {
    queryClient.invalidateQueries({ queryKey: ["social-status"] });
    queryClient.invalidateQueries({ queryKey: ["social-posts"] });
    queryClient.invalidateQueries({ queryKey: ["social-messages"] });
    queryClient.invalidateQueries({ queryKey: ["social-stats"] });
  };

  const fbConnected = !!status?.facebook;
  const igConnected = !!status?.instagram;
  const pendingMessages =
    messages?.filter((m) => m.ai_status === "pending").length || 0;
  const flaggedMessages =
    messages?.filter((m) => m.ai_status === "flagged").length || 0;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <Link
            href="/dashboard/marketing"
            className="rounded-md p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
          >
            <ArrowLeft className="h-5 w-5" />
          </Link>
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Social Media</h1>
            <p className="text-sm text-gray-500">
              AI-powered Facebook &amp; Instagram management
            </p>
          </div>
        </div>
        <Button onClick={() => setShowCreate(true)}>
          <Plus className="mr-1 h-4 w-4" />
          Create Post
        </Button>
      </div>

      {/* Connection Cards */}
      <div className="grid gap-4 sm:grid-cols-2">
        {/* Facebook */}
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="rounded-full bg-blue-100 p-2">
                  <Facebook className="h-5 w-5 text-blue-600" />
                </div>
                <div>
                  <p className="font-medium text-gray-900">Facebook Page</p>
                  {fbConnected ? (
                    <p className="text-sm text-gray-500">
                      {status?.facebook?.page_name || "Connected"}
                    </p>
                  ) : (
                    <p className="text-sm text-gray-400">Not connected</p>
                  )}
                </div>
              </div>
              {fbConnected ? (
                <div className="flex items-center gap-2">
                  <span className="flex items-center gap-1 rounded-full bg-green-50 px-2 py-0.5 text-xs font-medium text-green-700">
                    <CheckCircle2 className="h-3 w-3" />
                    Connected
                  </span>
                  <Button
                    size="sm"
                    variant="outline"
                    className="text-red-600"
                    onClick={() =>
                      disconnectMutation.mutate(status!.facebook!.id)
                    }
                  >
                    <Unplug className="h-3 w-3" />
                  </Button>
                </div>
              ) : (
                <Button size="sm" onClick={() => setShowConnectFb(true)}>
                  Connect
                </Button>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Instagram */}
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="rounded-full bg-pink-100 p-2">
                  <Instagram className="h-5 w-5 text-pink-600" />
                </div>
                <div>
                  <p className="font-medium text-gray-900">Instagram</p>
                  {igConnected ? (
                    <p className="text-sm text-gray-500">
                      {status?.instagram?.page_name || "Connected"}
                    </p>
                  ) : (
                    <p className="text-sm text-gray-400">
                      {fbConnected
                        ? "Not connected"
                        : "Connect Facebook first"}
                    </p>
                  )}
                </div>
              </div>
              {igConnected ? (
                <div className="flex items-center gap-2">
                  <span className="flex items-center gap-1 rounded-full bg-green-50 px-2 py-0.5 text-xs font-medium text-green-700">
                    <CheckCircle2 className="h-3 w-3" />
                    Connected
                  </span>
                  <Button
                    size="sm"
                    variant="outline"
                    className="text-red-600"
                    onClick={() =>
                      disconnectMutation.mutate(status!.instagram!.id)
                    }
                  >
                    <Unplug className="h-3 w-3" />
                  </Button>
                </div>
              ) : (
                <Button
                  size="sm"
                  onClick={() => setShowConnectIg(true)}
                  disabled={!fbConnected}
                >
                  Connect
                </Button>
              )}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Stats Cards */}
      {stats && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Card>
            <CardContent className="pt-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-gray-500">
                    Published Posts
                  </p>
                  <p className="mt-1 text-2xl font-bold text-gray-900">
                    {stats.posts.published}
                  </p>
                </div>
                <div className="rounded-full bg-green-100 p-2">
                  <Share2 className="h-5 w-5 text-green-600" />
                </div>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-gray-500">
                    Total Likes
                  </p>
                  <p className="mt-1 text-2xl font-bold text-gray-900">
                    {stats.engagement.likes}
                  </p>
                </div>
                <div className="rounded-full bg-blue-100 p-2">
                  <ThumbsUp className="h-5 w-5 text-blue-600" />
                </div>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-gray-500">
                    Total Comments
                  </p>
                  <p className="mt-1 text-2xl font-bold text-gray-900">
                    {stats.engagement.comments}
                  </p>
                </div>
                <div className="rounded-full bg-indigo-100 p-2">
                  <MessageCircle className="h-5 w-5 text-indigo-600" />
                </div>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-gray-500">
                    Messages
                  </p>
                  <p className="mt-1 text-2xl font-bold text-gray-900">
                    {stats.messages.total_messages}
                  </p>
                  {stats.messages.pending > 0 && (
                    <p className="text-xs text-yellow-600">
                      {stats.messages.pending} pending
                    </p>
                  )}
                </div>
                <div className="rounded-full bg-yellow-100 p-2">
                  <MessageSquare className="h-5 w-5 text-yellow-600" />
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Section Toggle */}
      <div className="flex gap-1 rounded-lg border border-gray-200 bg-gray-50 p-1">
        <button
          onClick={() => setActiveSection("posts")}
          className={`flex items-center gap-1.5 rounded-md px-4 py-2 text-sm font-medium transition-colors ${
            activeSection === "posts"
              ? "bg-white text-indigo-700 shadow-sm"
              : "text-gray-500 hover:text-gray-700"
          }`}
        >
          <Share2 className="h-4 w-4" />
          Posts
          {posts && posts.length > 0 && (
            <span className="rounded-full bg-gray-100 px-1.5 py-0.5 text-xs text-gray-600">
              {posts.length}
            </span>
          )}
        </button>
        <button
          onClick={() => setActiveSection("messages")}
          className={`flex items-center gap-1.5 rounded-md px-4 py-2 text-sm font-medium transition-colors ${
            activeSection === "messages"
              ? "bg-white text-indigo-700 shadow-sm"
              : "text-gray-500 hover:text-gray-700"
          }`}
        >
          <MessageSquare className="h-4 w-4" />
          Inbox
          {pendingMessages > 0 && (
            <span className="rounded-full bg-yellow-500 px-1.5 py-0.5 text-xs text-white">
              {pendingMessages}
            </span>
          )}
          {flaggedMessages > 0 && (
            <span className="rounded-full bg-red-500 px-1.5 py-0.5 text-xs text-white">
              {flaggedMessages}
            </span>
          )}
        </button>
        <button
          onClick={() => setActiveSection("stats")}
          className={`flex items-center gap-1.5 rounded-md px-4 py-2 text-sm font-medium transition-colors ${
            activeSection === "stats"
              ? "bg-white text-indigo-700 shadow-sm"
              : "text-gray-500 hover:text-gray-700"
          }`}
        >
          <BarChart3 className="h-4 w-4" />
          Stats
        </button>
      </div>

      {/* ── Posts Section ─────────────────────────────────────────────── */}
      {activeSection === "posts" && (
        <>
          {postsLoading ? (
            <div className="flex items-center justify-center py-20">
              <Loader2 className="h-8 w-8 animate-spin text-indigo-600" />
            </div>
          ) : !posts?.length ? (
            <div className="rounded-lg border border-dashed border-gray-300 py-12 text-center">
              <Share2 className="mx-auto h-10 w-10 text-gray-300" />
              <p className="mt-2 text-sm text-gray-500">
                No posts yet. Create your first social media post.
              </p>
              <Button
                className="mt-4"
                variant="outline"
                onClick={() => setShowCreate(true)}
              >
                <Plus className="mr-1 h-4 w-4" />
                Create Post
              </Button>
            </div>
          ) : (
            <div className="space-y-3">
              {posts.map((post) => (
                <div
                  key={post.id}
                  className="rounded-lg border border-gray-200 bg-white p-4"
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        {post.platform === "facebook" ? (
                          <Facebook className="h-4 w-4 text-blue-600" />
                        ) : (
                          <Instagram className="h-4 w-4 text-pink-600" />
                        )}
                        <span className="text-sm font-medium capitalize text-gray-900">
                          {post.platform}
                        </span>
                        <span
                          className={`rounded-full px-2 py-0.5 text-xs font-medium ${statusColors[post.status]}`}
                        >
                          {post.status}
                        </span>
                        {post.ai_generated && (
                          <span className="rounded-full bg-indigo-50 px-2 py-0.5 text-xs font-medium text-indigo-600">
                            AI
                          </span>
                        )}
                        {post.scheduled_at && post.status === "scheduled" && (
                          <span className="flex items-center gap-1 text-xs text-blue-600">
                            <Clock className="h-3 w-3" />
                            {format(
                              new Date(post.scheduled_at),
                              "MMM d, h:mm a"
                            )}
                          </span>
                        )}
                      </div>
                      <p className="mt-2 line-clamp-3 whitespace-pre-wrap text-sm text-gray-700">
                        {post.content}
                      </p>
                      <div className="mt-2 flex items-center gap-4 text-xs text-gray-400">
                        <span>
                          {format(
                            new Date(post.created_at),
                            "MMM d, h:mm a"
                          )}
                        </span>
                        {post.engagement &&
                          (post.engagement.likes ||
                            post.engagement.comments) && (
                            <div className="flex items-center gap-3">
                              <span className="flex items-center gap-1">
                                <ThumbsUp className="h-3 w-3" />
                                {post.engagement.likes || 0}
                              </span>
                              <span className="flex items-center gap-1">
                                <MessageCircle className="h-3 w-3" />
                                {post.engagement.comments || 0}
                              </span>
                            </div>
                          )}
                      </div>
                    </div>
                    <div className="flex gap-2">
                      {post.status === "draft" && (
                        <Button
                          size="sm"
                          onClick={() => publishMutation.mutate(post.id)}
                          disabled={publishMutation.isPending}
                        >
                          <Send className="mr-1 h-3 w-3" />
                          Publish
                        </Button>
                      )}
                      {post.status !== "published" && (
                        <Button
                          size="sm"
                          variant="outline"
                          className="text-red-600"
                          onClick={() => deleteMutation.mutate(post.id)}
                        >
                          <Trash2 className="h-3 w-3" />
                        </Button>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </>
      )}

      {/* ── Messages Section ─────────────────────────────────────────── */}
      {activeSection === "messages" && (
        <>
          {msgsLoading ? (
            <div className="flex items-center justify-center py-20">
              <Loader2 className="h-8 w-8 animate-spin text-indigo-600" />
            </div>
          ) : !messages?.length ? (
            <div className="rounded-lg border border-dashed border-gray-300 py-12 text-center">
              <MessageSquare className="mx-auto h-10 w-10 text-gray-300" />
              <p className="mt-2 text-sm text-gray-500">
                No messages yet. Messages and comments from Facebook &amp;
                Instagram will appear here.
              </p>
            </div>
          ) : (
            <div className="space-y-2">
              {messages.map((msg) => (
                <div
                  key={msg.id}
                  className={`rounded-lg border bg-white p-4 ${
                    msg.ai_status === "flagged"
                      ? "border-red-200"
                      : "border-gray-200"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      {msg.platform === "facebook" ? (
                        <Facebook className="h-4 w-4 text-blue-600" />
                      ) : (
                        <Instagram className="h-4 w-4 text-pink-600" />
                      )}
                      <span className="text-sm font-medium text-gray-900">
                        {msg.sender_name || "Unknown"}
                      </span>
                      <span className="rounded bg-gray-100 px-1.5 py-0.5 text-xs text-gray-500">
                        {msg.message_type}
                      </span>
                      <span
                        className={`rounded-full px-2 py-0.5 text-xs font-medium ${aiStatusColors[msg.ai_status]}`}
                      >
                        {msg.ai_status === "flagged" && (
                          <Flag className="mr-0.5 inline h-3 w-3" />
                        )}
                        {msg.ai_status}
                      </span>
                    </div>
                    <div className="flex gap-2">
                      {msg.ai_status === "pending" && (
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => aiRespondMutation.mutate(msg.id)}
                          disabled={aiRespondMutation.isPending}
                        >
                          <Bot className="mr-1 h-3 w-3" />
                          AI Reply
                        </Button>
                      )}
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => setReplyMessage(msg)}
                      >
                        <Send className="mr-1 h-3 w-3" />
                        Reply
                      </Button>
                    </div>
                  </div>
                  <p className="mt-1 text-sm text-gray-700">
                    {msg.message_text}
                  </p>
                  {msg.ai_response && (
                    <div className="mt-2 rounded bg-indigo-50 px-3 py-2 text-sm text-gray-600">
                      <span className="text-xs font-medium text-indigo-600">
                        AI Reply:{" "}
                      </span>
                      {msg.ai_response}
                    </div>
                  )}
                  <p className="mt-1 text-xs text-gray-400">
                    {msg.received_at
                      ? format(new Date(msg.received_at), "MMM d, h:mm a")
                      : format(new Date(msg.created_at), "MMM d, h:mm a")}
                  </p>
                </div>
              ))}
            </div>
          )}
        </>
      )}

      {/* ── Stats Section ────────────────────────────────────────────── */}
      {activeSection === "stats" && stats && (
        <div className="space-y-6">
          <div className="grid gap-4 sm:grid-cols-3">
            <Card>
              <CardHeader>
                <CardTitle className="text-sm font-medium text-gray-500">
                  Post Summary
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-2 text-sm">
                  <div className="flex justify-between">
                    <span className="text-gray-600">Total</span>
                    <span className="font-medium">{stats.posts.total_posts}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-600">Published</span>
                    <span className="font-medium text-green-600">
                      {stats.posts.published}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-600">Drafts</span>
                    <span className="font-medium">{stats.posts.drafts}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-600">Scheduled</span>
                    <span className="font-medium text-blue-600">
                      {stats.posts.scheduled}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-600">AI Generated</span>
                    <span className="font-medium text-indigo-600">
                      {stats.posts.ai_generated}
                    </span>
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-sm font-medium text-gray-500">
                  Engagement
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-2 text-sm">
                  <div className="flex justify-between">
                    <span className="flex items-center gap-1 text-gray-600">
                      <ThumbsUp className="h-3.5 w-3.5" /> Likes
                    </span>
                    <span className="font-medium">
                      {stats.engagement.likes}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="flex items-center gap-1 text-gray-600">
                      <MessageCircle className="h-3.5 w-3.5" /> Comments
                    </span>
                    <span className="font-medium">
                      {stats.engagement.comments}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="flex items-center gap-1 text-gray-600">
                      <Share2 className="h-3.5 w-3.5" /> Shares
                    </span>
                    <span className="font-medium">
                      {stats.engagement.shares}
                    </span>
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-sm font-medium text-gray-500">
                  Message Inbox
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-2 text-sm">
                  <div className="flex justify-between">
                    <span className="text-gray-600">Total</span>
                    <span className="font-medium">
                      {stats.messages.total_messages}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-600">Pending</span>
                    <span className="font-medium text-yellow-600">
                      {stats.messages.pending}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-600">Resolved</span>
                    <span className="font-medium text-green-600">
                      {stats.messages.resolved}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-600">Flagged</span>
                    <span className="font-medium text-red-600">
                      {stats.messages.flagged}
                    </span>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
      )}

      {/* ── Dialogs ──────────────────────────────────────────────────── */}
      {showCreate && (
        <CreatePostDialog
          onClose={() => setShowCreate(false)}
          onCreated={() => {
            setShowCreate(false);
            invalidateAll();
          }}
        />
      )}
      {showConnectFb && (
        <ConnectFacebookDialog
          onClose={() => setShowConnectFb(false)}
          onConnected={() => {
            setShowConnectFb(false);
            queryClient.invalidateQueries({ queryKey: ["social-status"] });
          }}
        />
      )}
      {showConnectIg && (
        <ConnectInstagramDialog
          onClose={() => setShowConnectIg(false)}
          onConnected={() => {
            setShowConnectIg(false);
            queryClient.invalidateQueries({ queryKey: ["social-status"] });
          }}
        />
      )}
      {replyMessage && (
        <ReplyDialog
          message={replyMessage}
          onClose={() => setReplyMessage(null)}
          onReplied={() => {
            setReplyMessage(null);
            queryClient.invalidateQueries({ queryKey: ["social-messages"] });
          }}
        />
      )}
    </div>
  );
}
