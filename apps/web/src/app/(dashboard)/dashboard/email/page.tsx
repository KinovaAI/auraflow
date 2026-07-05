"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  Mail,
  Inbox,
  Bot,
  AlertTriangle,
  Check,
  Clock,
  Send,
  User,
  Settings,
  Loader2,
  CheckCircle2,
  ChevronRight,
  X,
  Tag,
} from "lucide-react";
import { apiClient } from "@/lib/api-client";
import toast from "react-hot-toast";
import Link from "next/link";

// ── Types ────────────────────────────────────────────────────────────────────

interface InboxStats {
  unread: number;
  ai_resolved: number;
  needs_attention: number;
  this_week: number;
}

interface EmailMessage {
  id: string;
  from_name: string;
  from_email: string;
  to_email: string;
  subject: string;
  body?: string;
  body_text?: string;
  body_html?: string;
  received_at: string;
  classification: string;
  classification_confidence: number;
  status: "new" | "ai_resolved" | "needs_attention" | "in_progress" | "resolved";
  ai_response: string | null;
  thread?: ThreadMessage[];
  thread_history?: ThreadMessage[];
  replies?: ThreadMessage[];
}

interface ThreadMessage {
  id: string;
  sender_type: "ai" | "manual" | "inbound";
  from_name: string;
  body: string;
  sent_at: string;
}

interface TeamMember {
  id: string;
  name: string;
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

const CLASSIFICATION_COLORS: Record<string, string> = {
  booking: "bg-blue-100 text-blue-800",
  pricing: "bg-green-100 text-green-800",
  schedule: "bg-purple-100 text-purple-800",
  complaint: "bg-red-100 text-red-800",
  feedback: "bg-yellow-100 text-yellow-800",
  general: "bg-gray-100 text-gray-800",
  spam: "bg-gray-200 text-gray-600",
};

const STATUS_CONFIG: Record<string, { icon: typeof Check; color: string; label: string }> = {
  new: { icon: Mail, color: "text-blue-500", label: "New" },
  ai_resolved: { icon: CheckCircle2, color: "text-green-500", label: "AI Resolved" },
  needs_attention: { icon: AlertTriangle, color: "text-orange-500", label: "Needs Attention" },
  in_progress: { icon: Clock, color: "text-blue-500", label: "In Progress" },
  resolved: { icon: Check, color: "text-gray-400", label: "Resolved" },
};

function ClassificationBadge({ classification }: { classification: string }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
        CLASSIFICATION_COLORS[classification] || CLASSIFICATION_COLORS.general
      }`}
    >
      {classification}
    </span>
  );
}

function StatusIcon({ status }: { status: string }) {
  const config = STATUS_CONFIG[status] || STATUS_CONFIG.new;
  const Icon = config.icon;
  return <Icon className={`h-4 w-4 ${config.color}`} />;
}

// ── Not Connected Prompt ─────────────────────────────────────────────────────

function SetupPrompt() {
  return (
    <div className="flex flex-col items-center justify-center py-20">
      <div className="rounded-full bg-indigo-100 p-4 mb-4">
        <Mail className="h-8 w-8 text-indigo-600" />
      </div>
      <h2 className="text-xl font-semibold text-gray-900 mb-2">Connect Your Email</h2>
      <p className="text-gray-500 mb-6 text-center max-w-md">
        Connect your studio email account to enable AI-powered inbox management.
        The AI will classify, respond to, and route incoming emails automatically.
      </p>
      <Link href="/dashboard/settings/email-inbox">
        <Button className="bg-indigo-600 hover:bg-indigo-700">
          <Settings className="mr-2 h-4 w-4" />
          Set Up Email Connection
        </Button>
      </Link>
    </div>
  );
}

// ── Email Detail Panel ───────────────────────────────────────────────────────

function EmailDetail({
  email,
  onReply,
  onResolve,
  onRefresh,
}: {
  email: EmailMessage;
  onReply: (body: string) => void;
  onResolve: () => void;
  onRefresh?: () => void;
}) {
  const [replyOpen, setReplyOpen] = useState(false);
  const [replyText, setReplyText] = useState("");
  const [assignOpen, setAssignOpen] = useState(false);
  const [reclassifyOpen, setReclassifyOpen] = useState(false);

  const reclassifyMutation = useMutation({
    mutationFn: (classification: string) =>
      apiClient.post(`/studio-email/inbox/${email.id}/reclassify`, { classification }),
    onSuccess: () => {
      toast.success("Classification updated");
      setReclassifyOpen(false);
      onRefresh?.();
    },
    onError: () => toast.error("Failed to reclassify"),
  });

  const { data: team } = useQuery({
    queryKey: ["team-members"],
    queryFn: () => apiClient.get<TeamMember[]>("/studio-email/team").then((r) => r.data),
  });

  const assignMutation = useMutation({
    mutationFn: (memberId: string) =>
      apiClient.post(`/studio-email/messages/${email.id}/assign`, {
        team_member_id: memberId,
      }),
    onSuccess: () => {
      toast.success("Email assigned");
      setAssignOpen(false);
    },
    onError: () => toast.error("Failed to assign"),
  });

  return (
    <div className="flex h-full flex-col overflow-y-auto">
      {/* Header */}
      <div className="border-b border-gray-200 p-4 space-y-3">
        <h2 className="text-lg font-semibold text-gray-900">{email.subject}</h2>
        <div className="grid grid-cols-2 gap-2 text-sm">
          <div>
            <span className="font-medium text-gray-500">From:</span>{" "}
            <span className="text-gray-900">
              {email.from_name} &lt;{email.from_email}&gt;
            </span>
          </div>
          <div>
            <span className="font-medium text-gray-500">To:</span>{" "}
            <span className="text-gray-900">{email.to_email}</span>
          </div>
          <div>
            <span className="font-medium text-gray-500">Date:</span>{" "}
            <span className="text-gray-900">
              {new Date(email.received_at).toLocaleString()}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <ClassificationBadge classification={email.classification} />
            <span className="text-xs text-gray-400">
              {Math.round(email.classification_confidence * 100)}% confidence
            </span>
          </div>
        </div>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        <div className="rounded-lg border border-gray-200 bg-white p-4">
          {email.body_html ? (
            <div className="prose prose-sm max-w-none text-gray-800" dangerouslySetInnerHTML={{ __html: email.body_html }} />
          ) : (
            <p className="whitespace-pre-wrap text-sm text-gray-800">{email.body_text || email.body || "No content"}</p>
          )}
        </div>

        {/* AI Response */}
        {email.ai_response && (
          <div className="rounded-lg border border-indigo-200 bg-indigo-50/50 p-4">
            <div className="mb-2 flex items-center gap-2">
              <Bot className="h-4 w-4 text-indigo-600" />
              <span className="text-xs font-semibold text-indigo-700">AI Response</span>
            </div>
            <p className="whitespace-pre-wrap text-sm text-gray-800">{email.ai_response}</p>
          </div>
        )}

        {/* Thread */}
        {(email.thread || email.thread_history || email.replies || []).length > 0 && (
          <div className="space-y-3">
            <h3 className="text-sm font-semibold text-gray-700">Conversation Thread</h3>
            {(email.thread || email.thread_history || email.replies || []).map((msg) => (
              <div
                key={msg.id}
                className={`rounded-lg border p-3 ${
                  msg.sender_type === "ai"
                    ? "border-indigo-200 bg-indigo-50/50"
                    : msg.sender_type === "manual"
                      ? "border-gray-200 bg-gray-50"
                      : "border-gray-200 bg-white"
                }`}
              >
                <div className="mb-1 flex items-center gap-2 text-xs text-gray-500">
                  {msg.sender_type === "ai" ? (
                    <Bot className="h-3 w-3 text-indigo-600" />
                  ) : (
                    <User className="h-3 w-3 text-gray-500" />
                  )}
                  <span className="font-medium">{msg.from_name}</span>
                  <span>{timeAgo(msg.sent_at)}</span>
                </div>
                <p className="whitespace-pre-wrap text-sm text-gray-800">{msg.body}</p>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Actions */}
      <div className="border-t border-gray-200 p-4 space-y-3">
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setReplyOpen(!replyOpen)}
          >
            <Send className="mr-1 h-4 w-4" />
            Reply
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={onResolve}
            className="text-green-700 border-green-300 hover:bg-green-50"
          >
            <Check className="mr-1 h-4 w-4" />
            Resolve
          </Button>
          <div className="relative">
            <Button
              variant="outline"
              size="sm"
              onClick={() => { setAssignOpen(!assignOpen); setReclassifyOpen(false); }}
            >
              <User className="mr-1 h-4 w-4" />
              Assign
            </Button>
            {assignOpen && team && (
              <div className="absolute bottom-full left-0 mb-1 w-48 rounded-lg border border-gray-200 bg-white shadow-lg z-10">
                {team.map((member) => (
                  <button
                    key={member.id}
                    onClick={() => assignMutation.mutate(member.id)}
                    className="w-full px-3 py-2 text-left text-sm hover:bg-gray-50"
                  >
                    {member.name}
                  </button>
                ))}
                {team.length === 0 && (
                  <p className="px-3 py-2 text-sm text-gray-500">No team members</p>
                )}
              </div>
            )}
          </div>
          <div className="relative">
            <Button
              variant="outline"
              size="sm"
              onClick={() => { setReclassifyOpen(!reclassifyOpen); setAssignOpen(false); }}
            >
              <Tag className="mr-1 h-4 w-4" />
              Reclassify
            </Button>
            {reclassifyOpen && (
              <div className="absolute bottom-full left-0 mb-1 w-52 rounded-lg border border-gray-200 bg-white shadow-lg z-10 max-h-64 overflow-y-auto">
                {[
                  { key: "general_question", label: "General Question" },
                  { key: "booking_inquiry", label: "Booking Inquiry" },
                  { key: "pricing_question", label: "Pricing Question" },
                  { key: "schedule_question", label: "Schedule Question" },
                  { key: "engagement_reply", label: "Engagement Reply" },
                  { key: "complaint", label: "Complaint" },
                  { key: "feedback", label: "Feedback" },
                  { key: "cancellation", label: "Cancellation" },
                  { key: "spam", label: "Spam" },
                ].map((c) => (
                  <button
                    key={c.key}
                    onClick={() => reclassifyMutation.mutate(c.key)}
                    className={`w-full px-3 py-2 text-left text-sm hover:bg-gray-50 ${
                      email.classification === c.key ? "bg-indigo-50 font-medium text-indigo-700" : ""
                    }`}
                  >
                    {c.label}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        {replyOpen && (
          <div className="space-y-2">
            <textarea
              value={replyText}
              onChange={(e) => setReplyText(e.target.value)}
              placeholder="Type your reply..."
              rows={4}
              className="w-full rounded-lg border border-gray-300 p-3 text-sm focus:border-indigo-500 focus:ring-indigo-500"
            />
            <Button
              size="sm"
              className="bg-indigo-600 hover:bg-indigo-700"
              onClick={() => {
                if (replyText.trim()) {
                  onReply(replyText);
                  setReplyText("");
                  setReplyOpen(false);
                }
              }}
            >
              <Send className="mr-1 h-4 w-4" />
              Send Reply
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Main Page ────────────────────────────────────────────────────────────────

type FilterTab = "all" | "needs_attention" | "ai_resolved" | "in_progress";

const FILTER_TABS: { key: FilterTab; label: string }[] = [
  { key: "all", label: "All" },
  { key: "needs_attention", label: "Needs Attention" },
  { key: "ai_resolved", label: "AI Resolved" },
  { key: "in_progress", label: "In Progress" },
];

export default function AIInboxPage() {
  const queryClient = useQueryClient();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [filter, setFilter] = useState<FilterTab>("all");

  // Check connection status
  const { data: connectionStatus, isLoading: statusLoading } = useQuery({
    queryKey: ["studio-email-status"],
    queryFn: () =>
      apiClient.get("/studio-email/status").then((r) => {
        const d = (r as any).data?.data || (r as any).data;
        return { connected: !!(d?.connected || d?.is_active), email_address: d?.email_address };
      }),
    staleTime: 60000,
  });

  // Inbox stats
  const { data: stats } = useQuery({
    queryKey: ["inbox-stats"],
    queryFn: () =>
      apiClient.get("/studio-email/stats").then((r) => (r as any).data?.data || (r as any).data),
    enabled: !!connectionStatus?.connected,
  });

  // Email list
  const { data: emails, isLoading: emailsLoading } = useQuery({
    queryKey: ["inbox-emails", filter],
    queryFn: () =>
      apiClient
        .get("/studio-email/inbox", {
          params: { filter: filter === "all" ? undefined : filter },
        })
        .then((r) => {
          const d = (r as any).data?.data || (r as any).data;
          return Array.isArray(d) ? d : [];
        }),
    enabled: !!connectionStatus?.connected,
  });

  // Selected email detail
  const { data: selectedEmail } = useQuery({
    queryKey: ["inbox-email", selectedId],
    queryFn: () =>
      apiClient.get(`/studio-email/inbox/${selectedId}`).then((r) => (r as any).data?.data || (r as any).data),
    enabled: !!selectedId,
  });

  // Reply mutation
  const replyMutation = useMutation({
    mutationFn: ({ id, body }: { id: string; body: string }) =>
      apiClient.post(`/studio-email/inbox/${id}/reply`, { body }),
    onSuccess: () => {
      toast.success("Reply sent");
      queryClient.invalidateQueries({ queryKey: ["inbox-email", selectedId] });
      queryClient.invalidateQueries({ queryKey: ["inbox-emails"] });
    },
    onError: () => toast.error("Failed to send reply"),
  });

  // Resolve mutation
  const resolveMutation = useMutation({
    mutationFn: (id: string) =>
      apiClient.post(`/studio-email/inbox/${id}/resolve`),
    onSuccess: () => {
      toast.success("Email resolved");
      queryClient.invalidateQueries({ queryKey: ["inbox-emails"] });
      queryClient.invalidateQueries({ queryKey: ["inbox-stats"] });
      queryClient.invalidateQueries({ queryKey: ["inbox-email", selectedId] });
    },
    onError: () => toast.error("Failed to resolve"),
  });

  if (statusLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="h-8 w-8 animate-spin text-indigo-600" />
      </div>
    );
  }

  if (!connectionStatus?.connected) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">AI Email Inbox</h1>
          <p className="text-sm text-gray-500">
            AI-powered email management for your studio
          </p>
        </div>
        <SetupPrompt />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">AI Email Inbox</h1>
        <p className="text-sm text-gray-500">
          AI-powered email management for your studio
        </p>
      </div>

      {/* Stats Row */}
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <Card>
          <CardContent className="pt-4 pb-4">
            <div className="flex items-center gap-3">
              <div className="rounded-full bg-blue-100 p-2">
                <Mail className="h-4 w-4 text-blue-600" />
              </div>
              <div>
                <p className="text-2xl font-bold text-gray-900">{stats?.unread ?? 0}</p>
                <p className="text-xs text-gray-500">Unread</p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4 pb-4">
            <div className="flex items-center gap-3">
              <div className="rounded-full bg-green-100 p-2">
                <Bot className="h-4 w-4 text-green-600" />
              </div>
              <div>
                <p className="text-2xl font-bold text-gray-900">{stats?.ai_resolved ?? 0}</p>
                <p className="text-xs text-gray-500">AI Resolved</p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4 pb-4">
            <div className="flex items-center gap-3">
              <div className="rounded-full bg-orange-100 p-2">
                <AlertTriangle className="h-4 w-4 text-orange-600" />
              </div>
              <div>
                <p className="text-2xl font-bold text-gray-900">
                  {stats?.needs_attention ?? 0}
                </p>
                <p className="text-xs text-gray-500">Needs Attention</p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4 pb-4">
            <div className="flex items-center gap-3">
              <div className="rounded-full bg-gray-100 p-2">
                <Inbox className="h-4 w-4 text-gray-600" />
              </div>
              <div>
                <p className="text-2xl font-bold text-gray-900">{stats?.this_week ?? 0}</p>
                <p className="text-xs text-gray-500">This Week</p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Two-column layout */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-5" style={{ minHeight: "600px" }}>
        {/* Left panel — email list */}
        <Card className="lg:col-span-2 flex flex-col overflow-hidden">
          <div className="border-b border-gray-200 p-2">
            <div className="flex gap-1 overflow-x-auto">
              {FILTER_TABS.map((tab) => (
                <button
                  key={tab.key}
                  onClick={() => {
                    setFilter(tab.key);
                    setSelectedId(null);
                  }}
                  className={`whitespace-nowrap rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
                    filter === tab.key
                      ? "bg-indigo-100 text-indigo-700"
                      : "text-gray-500 hover:bg-gray-100 hover:text-gray-700"
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </div>
          </div>

          <div className="flex-1 overflow-y-auto">
            {emailsLoading ? (
              <div className="flex items-center justify-center py-10">
                <Loader2 className="h-6 w-6 animate-spin text-indigo-600" />
              </div>
            ) : !emails || emails.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-10 text-gray-400">
                <Inbox className="h-8 w-8 mb-2" />
                <p className="text-sm">No emails found</p>
              </div>
            ) : (
              emails.map((email) => (
                <button
                  key={email.id}
                  onClick={() => setSelectedId(email.id)}
                  className={`w-full border-b border-gray-100 px-4 py-3 text-left transition-colors hover:bg-gray-50 ${
                    selectedId === email.id ? "bg-indigo-50" : ""
                  } ${email.status === "new" ? "bg-blue-50/50" : ""}`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span
                          className={`truncate text-sm font-medium ${
                            email.status === "new" ? "text-gray-900" : "text-gray-700"
                          }`}
                        >
                          {email.from_name}
                        </span>
                        <StatusIcon status={email.status} />
                      </div>
                      <p className="truncate text-sm text-gray-600">{email.subject}</p>
                    </div>
                    <div className="flex flex-col items-end gap-1">
                      <span className="whitespace-nowrap text-xs text-gray-400">
                        {timeAgo(email.received_at)}
                      </span>
                      <ClassificationBadge classification={email.classification} />
                    </div>
                  </div>
                </button>
              ))
            )}
          </div>
        </Card>

        {/* Right panel — email detail */}
        <Card className="lg:col-span-3 flex flex-col overflow-hidden">
          {selectedEmail ? (
            <EmailDetail
              email={selectedEmail}
              onReply={(body) => replyMutation.mutate({ id: selectedEmail.id, body })}
              onResolve={() => resolveMutation.mutate(selectedEmail.id)}
              onRefresh={() => queryClient.invalidateQueries({ queryKey: ["studio-emails"] })}
            />
          ) : (
            <div className="flex flex-1 flex-col items-center justify-center text-gray-400">
              <Mail className="h-12 w-12 mb-3" />
              <p className="text-sm">Select an email to view details</p>
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
