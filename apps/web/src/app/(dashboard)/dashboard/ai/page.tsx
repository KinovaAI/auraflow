"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Sparkles,
  FileText,
  AlertTriangle,
  Loader2,
  Send,
  Check,
  X,
  Play,
  Mail,
  MessageSquare,
  BookOpen,
  ListOrdered,
  DollarSign,
  Star,
  RefreshCw,
  ThumbsUp,
  ThumbsDown,
  Minus,
  TrendingUp,
  Trash2,
  Plus,
  Flag,
  CalendarClock,
  Phone,
  Heart,
  ChevronRight,
} from "lucide-react";
import {
  aiApi,
  type MarketingDraft,
  type AtRiskMember,
  type WaitlistSession,
  type WaitlistScore,
  type PricingRule,
  type PriceSuggestion,
  type Review,
  type ReviewStats,
} from "@/lib/ai-api";

// ── Helpers ──────────────────────────────────────────────────────────────────

function fmtDate(iso: string | null) {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString([], {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function fmtCents(cents: number) {
  return `$${(cents / 100).toFixed(2)}`;
}

function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    draft: "bg-yellow-100 text-yellow-800",
    approved: "bg-green-100 text-green-800",
    rejected: "bg-red-100 text-red-800",
    sent: "bg-blue-100 text-blue-800",
    suggested: "bg-yellow-100 text-yellow-800",
    applied: "bg-green-100 text-green-800",
  };
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${colors[status] || "bg-gray-100 text-gray-800"}`}
    >
      {status}
    </span>
  );
}

function SentimentBadge({ sentiment }: { sentiment: string | null }) {
  if (!sentiment) return <span className="text-xs text-gray-400">—</span>;
  const cfg: Record<string, { color: string; icon: typeof ThumbsUp }> = {
    positive: { color: "bg-green-100 text-green-700", icon: ThumbsUp },
    neutral: { color: "bg-gray-100 text-gray-600", icon: Minus },
    negative: { color: "bg-red-100 text-red-700", icon: ThumbsDown },
  };
  const { color, icon: Icon } = cfg[sentiment] || cfg.neutral;
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${color}`}>
      <Icon className="h-3 w-3" />
      {sentiment}
    </span>
  );
}

function StarRating({ rating }: { rating: number }) {
  return (
    <div className="flex items-center gap-0.5">
      {[1, 2, 3, 4, 5].map((s) => (
        <Star
          key={s}
          className={`h-3.5 w-3.5 ${s <= rating ? "fill-yellow-400 text-yellow-400" : "text-gray-300"}`}
        />
      ))}
    </div>
  );
}

// ── Tab Config ───────────────────────────────────────────────────────────────

const tabs = [
  { key: "generate", label: "Content Generator", icon: Sparkles },
  { key: "drafts", label: "Drafts", icon: FileText },
  { key: "churn", label: "Churn Risk", icon: AlertTriangle },
  { key: "waitlist", label: "Waitlist Triage", icon: ListOrdered },
  { key: "pricing", label: "Dynamic Pricing", icon: DollarSign },
  { key: "reviews", label: "Reviews", icon: Star },
  { key: "schedule", label: "Schedule Insights", icon: CalendarClock },
] as const;

type TabKey = (typeof tabs)[number]["key"];

// ── Main Page ────────────────────────────────────────────────────────────────

export default function AIPage() {
  const [activeTab, setActiveTab] = useState<TabKey>("generate");

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">AI Assistant</h1>
        <p className="text-gray-500">
          Generate content, manage drafts, and leverage AI-powered tools
        </p>
      </div>

      {/* AI Office Manager Link */}
      <Link href="/dashboard/ai/office-manager" className="block">
        <Card className="border-indigo-200 bg-indigo-50/50 hover:bg-indigo-50 transition-colors cursor-pointer">
          <CardContent className="flex items-center gap-4 py-4">
            <div className="rounded-full bg-indigo-100 p-2.5">
              <Phone className="h-5 w-5 text-indigo-600" />
            </div>
            <div className="flex-1">
              <h3 className="font-semibold text-gray-900">AI Office Manager</h3>
              <p className="text-sm text-gray-500">
                Automated instructor substitution and inventory monitoring
              </p>
            </div>
            <ChevronRight className="h-5 w-5 text-gray-400" />
          </CardContent>
        </Card>
      </Link>

      {/* AI Email Inbox Link */}
      <Link href="/dashboard/email" className="block">
        <Card className="border-indigo-200 bg-indigo-50/50 hover:bg-indigo-50 transition-colors cursor-pointer">
          <CardContent className="flex items-center gap-4 py-4">
            <div className="rounded-full bg-indigo-100 p-2.5">
              <Mail className="h-5 w-5 text-indigo-600" />
            </div>
            <div className="flex-1">
              <h3 className="font-semibold text-gray-900">AI Email Inbox</h3>
              <p className="text-sm text-gray-500">
                AI-powered email classification, responses, and inbox management
              </p>
            </div>
            <ChevronRight className="h-5 w-5 text-gray-400" />
          </CardContent>
        </Card>
      </Link>

      {/* AI Engagement Autopilot Link */}
      <Link href="/dashboard/ai/engagement" className="block">
        <Card className="border-indigo-200 bg-indigo-50/50 hover:bg-indigo-50 transition-colors cursor-pointer">
          <CardContent className="flex items-center gap-4 py-4">
            <div className="rounded-full bg-indigo-100 p-2.5">
              <Heart className="h-5 w-5 text-indigo-600" />
            </div>
            <div className="flex-1">
              <h3 className="font-semibold text-gray-900">AI Engagement Autopilot</h3>
              <p className="text-sm text-gray-500">
                Automatically reach out to disengaged members and guide them back.
              </p>
            </div>
            <ChevronRight className="h-5 w-5 text-gray-400" />
          </CardContent>
        </Card>
      </Link>

      <div className="flex gap-1 overflow-x-auto rounded-lg bg-gray-100 p-1">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`flex items-center gap-2 whitespace-nowrap rounded-md px-4 py-2 text-sm font-medium transition-colors ${
              activeTab === tab.key
                ? "bg-white text-gray-900 shadow-sm"
                : "text-gray-600 hover:text-gray-900"
            }`}
          >
            <tab.icon className="h-4 w-4" />
            {tab.label}
          </button>
        ))}
      </div>

      {activeTab === "generate" && <GenerateTab />}
      {activeTab === "drafts" && <DraftsTab />}
      {activeTab === "churn" && <ChurnTab />}
      {activeTab === "waitlist" && <WaitlistTriageTab />}
      {activeTab === "pricing" && <DynamicPricingTab />}
      {activeTab === "reviews" && <ReviewsTab />}
      {activeTab === "schedule" && <ScheduleInsightsTab />}
    </div>
  );
}

// ── Content Generator Tab ────────────────────────────────────────────────────

function GenerateTab() {
  const queryClient = useQueryClient();
  const [draftType, setDraftType] = useState("email");
  const [prompt, setPrompt] = useState("");
  const [tone, setTone] = useState("friendly and professional");
  const [result, setResult] = useState<string | null>(null);

  const generateMut = useMutation({
    mutationFn: () =>
      aiApi.createDraft({
        prompt_context: prompt,
        draft_type: draftType,
        tone,
      }),
    onSuccess: (resp) => {
      const draft = resp.data.data;
      setResult(draft.body);
      setPrompt("");
      queryClient.invalidateQueries({ queryKey: ["ai-drafts"] });
    },
  });

  const typeIcons: Record<string, typeof Mail> = {
    email: Mail,
    social: MessageSquare,
    class_description: BookOpen,
    sms: MessageSquare,
  };

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Sparkles className="h-5 w-5" />
            Generate Content
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <label className="mb-1 block text-xs font-medium text-gray-500">Content Type</label>
            <div className="grid grid-cols-2 gap-2">
              {(["email", "social", "class_description", "sms"] as const).map((type) => {
                const Icon = typeIcons[type] || Sparkles;
                return (
                  <button
                    key={type}
                    onClick={() => setDraftType(type)}
                    className={`flex items-center gap-2 rounded-md border px-3 py-2 text-sm ${
                      draftType === type
                        ? "border-indigo-300 bg-indigo-50 text-indigo-700"
                        : "border-gray-200 text-gray-600 hover:bg-gray-50"
                    }`}
                  >
                    <Icon className="h-4 w-4" />
                    {type === "class_description" ? "Class Desc" : type.charAt(0).toUpperCase() + type.slice(1)}
                  </button>
                );
              })}
            </div>
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-gray-500">
              {draftType === "class_description" ? "Class Name" : "What should we write about?"}
            </label>
            <textarea
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder={
                draftType === "email"
                  ? "e.g. New year promotion, 20% off first month..."
                  : draftType === "social"
                    ? "e.g. Announce new hot yoga class starting next week..."
                    : draftType === "class_description"
                      ? "e.g. Vinyasa Flow"
                      : "e.g. Reminder about tomorrow's workshop..."
              }
              rows={3}
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-gray-500">Tone</label>
            <select
              value={tone}
              onChange={(e) => setTone(e.target.value)}
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
            >
              <option value="friendly and professional">Friendly & Professional</option>
              <option value="warm and inviting">Warm & Inviting</option>
              <option value="energetic and exciting">Energetic & Exciting</option>
              <option value="calm and mindful">Calm & Mindful</option>
            </select>
          </div>
          <button
            onClick={() => generateMut.mutate()}
            disabled={!prompt || generateMut.isPending}
            className="flex w-full items-center justify-center gap-2 rounded-lg bg-indigo-600 px-4 py-3 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
          >
            {generateMut.isPending ? (
              <Loader2 className="h-5 w-5 animate-spin" />
            ) : (
              <>
                <Sparkles className="h-5 w-5" />
                Generate & Save as Draft
              </>
            )}
          </button>
          {generateMut.isError && (
            <p className="text-sm text-red-600">
              {(generateMut.error as Error)?.message || "Generation failed"}
            </p>
          )}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Preview</CardTitle>
        </CardHeader>
        <CardContent>
          {result ? (
            <div className="whitespace-pre-wrap rounded-lg bg-gray-50 p-4 text-sm">{result}</div>
          ) : (
            <p className="py-8 text-center text-sm text-gray-400">Generated content will appear here</p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

// ── Drafts Tab ───────────────────────────────────────────────────────────────

function DraftsTab() {
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState("");
  const [selectedDraft, setSelectedDraft] = useState<MarketingDraft | null>(null);

  const { data: drafts, isLoading } = useQuery({
    queryKey: ["ai-drafts", statusFilter],
    queryFn: () => aiApi.listDrafts(statusFilter || undefined).then((r) => r.data.data),
  });

  const approveMut = useMutation({
    mutationFn: (id: string) => aiApi.approveDraft(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["ai-drafts"] });
      setSelectedDraft(null);
    },
  });

  const rejectMut = useMutation({
    mutationFn: (id: string) => aiApi.rejectDraft(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["ai-drafts"] });
      setSelectedDraft(null);
    },
  });

  return (
    <div className="space-y-4">
      <div className="flex gap-2">
        {["", "draft", "approved", "rejected"].map((s) => (
          <button
            key={s}
            onClick={() => setStatusFilter(s)}
            className={`rounded-md px-3 py-1.5 text-sm font-medium ${
              statusFilter === s ? "bg-indigo-100 text-indigo-700" : "text-gray-600 hover:bg-gray-100"
            }`}
          >
            {s ? s.charAt(0).toUpperCase() + s.slice(1) : "All"}
          </button>
        ))}
      </div>

      {selectedDraft && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="w-full max-w-lg rounded-lg bg-white p-6 shadow-xl">
            <div className="mb-4 flex items-center justify-between">
              <div>
                <h3 className="text-lg font-bold">Draft Detail</h3>
                <StatusBadge status={selectedDraft.status} />
              </div>
              <button onClick={() => setSelectedDraft(null)}>
                <X className="h-5 w-5 text-gray-400" />
              </button>
            </div>
            <div className="space-y-3">
              <div>
                <p className="text-xs font-medium text-gray-500">Type</p>
                <p className="text-sm">{selectedDraft.draft_type}</p>
              </div>
              <div>
                <p className="text-xs font-medium text-gray-500">Prompt</p>
                <p className="text-sm text-gray-600">{selectedDraft.prompt_context}</p>
              </div>
              {selectedDraft.subject && (
                <div>
                  <p className="text-xs font-medium text-gray-500">Subject</p>
                  <p className="text-sm font-medium">{selectedDraft.subject}</p>
                </div>
              )}
              <div>
                <p className="text-xs font-medium text-gray-500">Body</p>
                <div className="mt-1 whitespace-pre-wrap rounded-lg bg-gray-50 p-3 text-sm">
                  {selectedDraft.body}
                </div>
              </div>
            </div>
            {selectedDraft.status === "draft" && (
              <div className="mt-4 flex justify-end gap-2">
                <button
                  onClick={() => rejectMut.mutate(selectedDraft.id)}
                  disabled={rejectMut.isPending}
                  className="flex items-center gap-1 rounded-md border border-red-300 px-4 py-2 text-sm text-red-600 hover:bg-red-50"
                >
                  <X className="h-4 w-4" />
                  Reject
                </button>
                <button
                  onClick={() => approveMut.mutate(selectedDraft.id)}
                  disabled={approveMut.isPending}
                  className="flex items-center gap-1 rounded-md bg-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-green-700"
                >
                  <Check className="h-4 w-4" />
                  Approve
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      <Card>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="flex justify-center py-8">
              <Loader2 className="h-6 w-6 animate-spin text-gray-300" />
            </div>
          ) : !drafts || drafts.length === 0 ? (
            <p className="py-8 text-center text-sm text-gray-400">
              No drafts yet. Use the Content Generator to create some.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-gray-50 text-left text-xs font-medium uppercase text-gray-500">
                    <th className="px-4 py-3">Type</th>
                    <th className="px-4 py-3">Prompt</th>
                    <th className="px-4 py-3">Subject</th>
                    <th className="px-4 py-3">Status</th>
                    <th className="px-4 py-3">Created</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {drafts.map((d) => (
                    <tr key={d.id} onClick={() => setSelectedDraft(d)} className="cursor-pointer hover:bg-gray-50">
                      <td className="px-4 py-3">
                        <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs">{d.draft_type}</span>
                      </td>
                      <td className="max-w-xs truncate px-4 py-3 text-gray-600">{d.prompt_context}</td>
                      <td className="px-4 py-3">{d.subject || "—"}</td>
                      <td className="px-4 py-3">
                        <StatusBadge status={d.status} />
                      </td>
                      <td className="px-4 py-3 text-gray-500">{fmtDate(d.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

// ── Churn Risk Tab ───────────────────────────────────────────────────────────

function ChurnTab() {
  const queryClient = useQueryClient();
  const { data: atRisk, isLoading } = useQuery({
    queryKey: ["churn-risk"],
    queryFn: () => aiApi.listAtRiskMembers().then((r) => r.data.data),
  });

  const scanMut = useMutation({
    mutationFn: () => aiApi.triggerChurnScan(),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["churn-risk"] }),
  });
  const winbackMut = useMutation({
    mutationFn: (id: string) => aiApi.sendWinback(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["churn-risk"] }),
  });
  const dismissMut = useMutation({
    mutationFn: (id: string) => aiApi.dismissChurnFlag(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["churn-risk"] }),
  });

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-gray-500">Members flagged as at-risk based on attendance patterns</p>
        <button
          onClick={() => scanMut.mutate()}
          disabled={scanMut.isPending}
          className="flex items-center gap-2 rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
        >
          {scanMut.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
          Run Scan
        </button>
      </div>
      {scanMut.isSuccess && (
        <div className="rounded-lg border border-blue-200 bg-blue-50 p-3 text-sm text-blue-700">
          Scan complete: {scanMut.data?.data?.data?.newly_flagged ?? 0} newly flagged,{" "}
          {scanMut.data?.data?.data?.cleared ?? 0} cleared
        </div>
      )}
      <Card>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="flex justify-center py-8">
              <Loader2 className="h-6 w-6 animate-spin text-gray-300" />
            </div>
          ) : !atRisk || atRisk.length === 0 ? (
            <p className="py-8 text-center text-sm text-gray-400">No members currently at risk. Run a scan to check.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-gray-50 text-left text-xs font-medium uppercase text-gray-500">
                    <th className="px-4 py-3">Member</th>
                    <th className="px-4 py-3">Email</th>
                    <th className="px-4 py-3">Total Visits</th>
                    <th className="px-4 py-3">Last Visit</th>
                    <th className="px-4 py-3">Revenue</th>
                    <th className="px-4 py-3">Flagged</th>
                    <th className="px-4 py-3">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {atRisk.map((m) => (
                    <tr key={m.id} className="hover:bg-gray-50">
                      <td className="px-4 py-3 font-medium">
                        <div className="flex items-center gap-2">
                          <AlertTriangle className="h-4 w-4 text-red-500" />
                          {m.first_name} {m.last_name}
                        </div>
                      </td>
                      <td className="px-4 py-3 text-gray-500">{m.email}</td>
                      <td className="px-4 py-3">{m.total_visits}</td>
                      <td className="px-4 py-3 text-gray-500">{fmtDate(m.last_visit_at)}</td>
                      <td className="px-4 py-3">{fmtCents(m.lifetime_revenue_cents)}</td>
                      <td className="px-4 py-3 text-gray-500">{fmtDate(m.churn_risk_flagged_at)}</td>
                      <td className="px-4 py-3">
                        <div className="flex gap-1">
                          <button
                            onClick={() => winbackMut.mutate(m.id)}
                            disabled={winbackMut.isPending}
                            className="flex items-center gap-1 rounded px-2 py-1 text-xs font-medium text-indigo-600 hover:bg-indigo-50"
                          >
                            <Send className="h-3 w-3" />
                            Reach Out
                          </button>
                          <button
                            onClick={() => dismissMut.mutate(m.id)}
                            disabled={dismissMut.isPending}
                            className="rounded px-2 py-1 text-xs text-gray-500 hover:bg-gray-100"
                          >
                            Dismiss
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

// ── Waitlist Triage Tab ──────────────────────────────────────────────────────

function WaitlistTriageTab() {
  const queryClient = useQueryClient();
  const [selectedSession, setSelectedSession] = useState<string>("");

  const { data: sessions, isLoading: sessionsLoading } = useQuery({
    queryKey: ["waitlist-sessions"],
    queryFn: () => aiApi.getSessionsWithWaitlist().then((r) => r.data.data),
  });

  const { data: scores, isLoading: scoresLoading } = useQuery({
    queryKey: ["waitlist-scores", selectedSession],
    queryFn: () => aiApi.getWaitlistScores(selectedSession).then((r) => r.data.data),
    enabled: !!selectedSession,
  });

  const rerankMut = useMutation({
    mutationFn: () => aiApi.rerankWaitlist(selectedSession),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["waitlist-scores", selectedSession] }),
  });

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <label className="text-sm font-medium text-gray-700">Session:</label>
          <select
            value={selectedSession}
            onChange={(e) => setSelectedSession(e.target.value)}
            className="rounded-md border border-gray-300 px-3 py-2 text-sm"
          >
            <option value="">Select a session with waitlist...</option>
            {sessions?.map((s) => (
              <option key={s.id} value={s.id}>
                {s.title} — {new Date(s.starts_at).toLocaleDateString()} ({s.waitlist_count} waitlisted)
              </option>
            ))}
          </select>
          {sessionsLoading && <Loader2 className="h-4 w-4 animate-spin text-gray-400" />}
        </div>
        {selectedSession && (
          <button
            onClick={() => rerankMut.mutate()}
            disabled={rerankMut.isPending || !scores?.length}
            className="flex items-center gap-2 rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
          >
            {rerankMut.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
            Re-rank by Score
          </button>
        )}
      </div>

      {!selectedSession ? (
        <div className="rounded-lg border border-dashed border-gray-300 py-12 text-center">
          <ListOrdered className="mx-auto h-10 w-10 text-gray-300" />
          <p className="mt-2 text-sm text-gray-500">Select a session above to view its waitlist with AI priority scores</p>
        </div>
      ) : scoresLoading ? (
        <div className="flex justify-center py-12">
          <Loader2 className="h-6 w-6 animate-spin text-gray-300" />
        </div>
      ) : !scores || scores.length === 0 ? (
        <div className="rounded-lg border border-dashed border-gray-300 py-12 text-center">
          <p className="text-sm text-gray-500">No waitlisted members for this session</p>
        </div>
      ) : (
        <Card>
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-gray-50 text-left text-xs font-medium uppercase text-gray-500">
                    <th className="px-4 py-3">#</th>
                    <th className="px-4 py-3">Member</th>
                    <th className="px-4 py-3">Priority Score</th>
                    <th className="px-4 py-3">Membership</th>
                    <th className="px-4 py-3">Visits</th>
                    <th className="px-4 py-3">Revenue</th>
                    <th className="px-4 py-3">Position</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {scores.map((s, i) => (
                    <tr key={s.booking_id} className="hover:bg-gray-50">
                      <td className="px-4 py-3 text-gray-400">{i + 1}</td>
                      <td className="px-4 py-3 font-medium">
                        {s.first_name} {s.last_name}
                        <div className="text-xs text-gray-400">{s.email}</div>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <div className="h-2 w-20 overflow-hidden rounded-full bg-gray-100">
                            <div
                              className={`h-full rounded-full ${
                                s.priority_score >= 70 ? "bg-green-500" : s.priority_score >= 40 ? "bg-yellow-500" : "bg-red-400"
                              }`}
                              style={{ width: `${s.priority_score}%` }}
                            />
                          </div>
                          <span className="text-sm font-semibold">{s.priority_score}</span>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-gray-600">{s.membership_name}</td>
                      <td className="px-4 py-3">{s.total_visits}</td>
                      <td className="px-4 py-3">{fmtCents(s.lifetime_revenue_cents)}</td>
                      <td className="px-4 py-3 text-center">
                        <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium">
                          #{s.waitlist_position}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

// ── Dynamic Pricing Tab ──────────────────────────────────────────────────────

function DynamicPricingTab() {
  const queryClient = useQueryClient();
  const [studioId, setStudioId] = useState("");
  const [showAddRule, setShowAddRule] = useState(false);
  const [newRule, setNewRule] = useState({ name: "", rule_type: "peak_hour", config: "{}" });

  // We need a studio ID — fetch from current user's org
  const { data: studios } = useQuery({
    queryKey: ["studios-list"],
    queryFn: async () => {
      const { apiClient } = await import("@/lib/api-client");
      const res = await apiClient.get<{ data: Array<{ id: string; name: string }> }>("/studios");
      return res.data.data;
    },
  });

  const effectiveStudioId = studioId || studios?.[0]?.id || "";

  const { data: rules, isLoading: rulesLoading } = useQuery({
    queryKey: ["pricing-rules", effectiveStudioId],
    queryFn: () => aiApi.getPricingRules(effectiveStudioId).then((r) => r.data.data),
    enabled: !!effectiveStudioId,
  });

  const { data: suggestions, isLoading: suggestionsLoading } = useQuery({
    queryKey: ["pricing-suggestions", effectiveStudioId],
    queryFn: () => aiApi.getPriceSuggestions(effectiveStudioId).then((r) => r.data.data),
    enabled: !!effectiveStudioId,
  });

  const createRuleMut = useMutation({
    mutationFn: () => {
      let config = {};
      try { config = JSON.parse(newRule.config); } catch { /* use empty */ }
      return aiApi.createPricingRule({
        studio_id: effectiveStudioId,
        name: newRule.name,
        rule_type: newRule.rule_type,
        config,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["pricing-rules"] });
      setShowAddRule(false);
      setNewRule({ name: "", rule_type: "peak_hour", config: "{}" });
    },
  });

  const deleteRuleMut = useMutation({
    mutationFn: (ruleId: string) => aiApi.deletePricingRule(ruleId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["pricing-rules"] }),
  });

  const suggestMut = useMutation({
    mutationFn: () => aiApi.triggerPriceSuggestions(effectiveStudioId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["pricing-suggestions"] }),
  });

  const approveMut = useMutation({
    mutationFn: (id: string) => aiApi.approvePriceSuggestion(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["pricing-suggestions"] }),
  });

  const rejectMut = useMutation({
    mutationFn: (id: string) => aiApi.rejectPriceSuggestion(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["pricing-suggestions"] }),
  });

  const ruleTypeLabels: Record<string, string> = {
    peak_hour: "Peak Hour",
    fill_rate: "Fill Rate",
    day_of_week: "Day of Week",
    seasonal: "Seasonal",
    last_minute: "Last Minute",
  };

  const ruleTypeColors: Record<string, string> = {
    peak_hour: "bg-orange-100 text-orange-700",
    fill_rate: "bg-blue-100 text-blue-700",
    day_of_week: "bg-purple-100 text-purple-700",
    seasonal: "bg-green-100 text-green-700",
    last_minute: "bg-red-100 text-red-700",
  };

  return (
    <div className="space-y-4">
      {studios && studios.length > 1 && (
        <select
          value={studioId}
          onChange={(e) => setStudioId(e.target.value)}
          className="rounded-md border border-gray-300 px-3 py-2 text-sm"
        >
          {studios.map((s) => (
            <option key={s.id} value={s.id}>{s.name}</option>
          ))}
        </select>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Pricing Rules */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="flex items-center gap-2">
                <DollarSign className="h-5 w-5" />
                Pricing Rules
              </CardTitle>
              <button
                onClick={() => setShowAddRule(!showAddRule)}
                className="flex items-center gap-1 rounded-md bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-700"
              >
                <Plus className="h-3.5 w-3.5" />
                Add Rule
              </button>
            </div>
          </CardHeader>
          <CardContent className="space-y-3">
            {showAddRule && (
              <div className="space-y-2 rounded-lg border border-indigo-200 bg-indigo-50/50 p-3">
                <input
                  type="text"
                  value={newRule.name}
                  onChange={(e) => setNewRule({ ...newRule, name: e.target.value })}
                  placeholder="Rule name"
                  className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
                />
                <select
                  value={newRule.rule_type}
                  onChange={(e) => setNewRule({ ...newRule, rule_type: e.target.value })}
                  className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
                >
                  {Object.entries(ruleTypeLabels).map(([k, v]) => (
                    <option key={k} value={k}>{v}</option>
                  ))}
                </select>
                <textarea
                  value={newRule.config}
                  onChange={(e) => setNewRule({ ...newRule, config: e.target.value })}
                  placeholder='{"peak_hours": [17,18,19], "multiplier": 1.3}'
                  rows={2}
                  className="w-full rounded-md border border-gray-300 px-3 py-2 font-mono text-xs"
                />
                <button
                  onClick={() => createRuleMut.mutate()}
                  disabled={!newRule.name || createRuleMut.isPending}
                  className="w-full rounded-md bg-indigo-600 px-3 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
                >
                  {createRuleMut.isPending ? "Creating..." : "Create Rule"}
                </button>
              </div>
            )}

            {rulesLoading ? (
              <div className="flex justify-center py-4">
                <Loader2 className="h-5 w-5 animate-spin text-gray-300" />
              </div>
            ) : !rules || rules.length === 0 ? (
              <p className="py-4 text-center text-sm text-gray-400">No pricing rules configured</p>
            ) : (
              rules.map((rule) => (
                <div key={rule.id} className="flex items-center justify-between rounded-lg border border-gray-200 p-3">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${ruleTypeColors[rule.rule_type] || "bg-gray-100"}`}>
                        {ruleTypeLabels[rule.rule_type] || rule.rule_type}
                      </span>
                      <span className="text-sm font-medium">{rule.name}</span>
                    </div>
                    <p className="mt-1 text-xs text-gray-400 font-mono">
                      {JSON.stringify(rule.config)}
                    </p>
                  </div>
                  <button
                    onClick={() => deleteRuleMut.mutate(rule.id)}
                    className="text-gray-400 hover:text-red-500"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              ))
            )}
          </CardContent>
        </Card>

        {/* AI Suggestions */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="flex items-center gap-2">
                <TrendingUp className="h-5 w-5" />
                AI Suggestions
              </CardTitle>
              <button
                onClick={() => suggestMut.mutate()}
                disabled={suggestMut.isPending || !effectiveStudioId}
                className="flex items-center gap-1 rounded-md bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
              >
                {suggestMut.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />}
                Generate
              </button>
            </div>
          </CardHeader>
          <CardContent>
            {suggestionsLoading ? (
              <div className="flex justify-center py-4">
                <Loader2 className="h-5 w-5 animate-spin text-gray-300" />
              </div>
            ) : !suggestions || suggestions.length === 0 ? (
              <p className="py-4 text-center text-sm text-gray-400">
                No pending suggestions. Click Generate to create AI pricing recommendations.
              </p>
            ) : (
              <div className="space-y-3">
                {suggestions.map((s) => (
                  <div key={s.id} className="rounded-lg border border-gray-200 p-3">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-sm font-medium">{s.session_title || "Session"}</p>
                        <p className="text-xs text-gray-400">{s.starts_at ? fmtDate(s.starts_at) : ""}</p>
                      </div>
                      <StatusBadge status={s.status} />
                    </div>
                    <div className="mt-2 flex items-center gap-3">
                      <span className="text-sm text-gray-500 line-through">{fmtCents(s.original_price_cents)}</span>
                      <span className="text-sm font-bold text-green-600">{fmtCents(s.adjusted_price_cents)}</span>
                    </div>
                    {s.reason && <p className="mt-1 text-xs text-gray-500">{s.reason}</p>}
                    {s.status === "suggested" && (
                      <div className="mt-2 flex gap-2">
                        <button
                          onClick={() => approveMut.mutate(s.id)}
                          disabled={approveMut.isPending}
                          className="flex items-center gap-1 rounded px-2 py-1 text-xs font-medium text-green-600 hover:bg-green-50"
                        >
                          <Check className="h-3 w-3" />
                          Approve
                        </button>
                        <button
                          onClick={() => rejectMut.mutate(s.id)}
                          disabled={rejectMut.isPending}
                          className="flex items-center gap-1 rounded px-2 py-1 text-xs text-red-500 hover:bg-red-50"
                        >
                          <X className="h-3 w-3" />
                          Reject
                        </button>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

// ── Reviews Tab ──────────────────────────────────────────────────────────────

function ReviewsTab() {
  const queryClient = useQueryClient();
  const [sentimentFilter, setSentimentFilter] = useState("");
  const [respondingTo, setRespondingTo] = useState<string | null>(null);
  const [responseText, setResponseText] = useState("");

  const { data: stats } = useQuery({
    queryKey: ["review-stats"],
    queryFn: () => aiApi.getReviewStats().then((r) => r.data.data),
  });

  const { data: reviews, isLoading } = useQuery({
    queryKey: ["reviews", sentimentFilter],
    queryFn: () =>
      aiApi.listReviews(sentimentFilter ? { sentiment: sentimentFilter } : undefined).then((r) => r.data.data),
  });

  const respondMut = useMutation({
    mutationFn: ({ reviewId, text }: { reviewId: string; text: string }) =>
      aiApi.respondToReview(reviewId, { response_text: text }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["reviews"] });
      queryClient.invalidateQueries({ queryKey: ["review-stats"] });
      setRespondingTo(null);
      setResponseText("");
    },
  });

  const flagMut = useMutation({
    mutationFn: (reviewId: string) => aiApi.flagReview(reviewId, { reason: "Flagged for review" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["reviews"] }),
  });

  return (
    <div className="space-y-4">
      {/* Stats Bar */}
      {stats && (
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-6">
          <div className="rounded-lg border border-gray-200 bg-white p-3 text-center">
            <p className="text-2xl font-bold text-gray-900">{stats.avg_rating.toFixed(1)}</p>
            <div className="mt-1 flex justify-center">
              <StarRating rating={Math.round(stats.avg_rating)} />
            </div>
            <p className="mt-1 text-xs text-gray-500">Avg Rating</p>
          </div>
          <div className="rounded-lg border border-gray-200 bg-white p-3 text-center">
            <p className="text-2xl font-bold text-gray-900">{stats.total_reviews}</p>
            <p className="text-xs text-gray-500">Total Reviews</p>
          </div>
          <div className="rounded-lg border border-gray-200 bg-white p-3 text-center">
            <p className="text-2xl font-bold text-green-600">{stats.positive_count}</p>
            <p className="text-xs text-gray-500">Positive</p>
          </div>
          <div className="rounded-lg border border-gray-200 bg-white p-3 text-center">
            <p className="text-2xl font-bold text-gray-600">{stats.neutral_count}</p>
            <p className="text-xs text-gray-500">Neutral</p>
          </div>
          <div className="rounded-lg border border-gray-200 bg-white p-3 text-center">
            <p className="text-2xl font-bold text-red-600">{stats.negative_count}</p>
            <p className="text-xs text-gray-500">Negative</p>
          </div>
          <div className="rounded-lg border border-gray-200 bg-white p-3 text-center">
            <p className="text-2xl font-bold text-indigo-600">{stats.response_rate}%</p>
            <p className="text-xs text-gray-500">Response Rate</p>
          </div>
        </div>
      )}

      {/* Sentiment Filter */}
      <div className="flex gap-2">
        {["", "positive", "neutral", "negative"].map((s) => (
          <button
            key={s}
            onClick={() => setSentimentFilter(s)}
            className={`rounded-md px-3 py-1.5 text-sm font-medium ${
              sentimentFilter === s ? "bg-indigo-100 text-indigo-700" : "text-gray-600 hover:bg-gray-100"
            }`}
          >
            {s ? s.charAt(0).toUpperCase() + s.slice(1) : "All"}
          </button>
        ))}
      </div>

      {/* Reviews List */}
      {isLoading ? (
        <div className="flex justify-center py-12">
          <Loader2 className="h-6 w-6 animate-spin text-gray-300" />
        </div>
      ) : !reviews || reviews.length === 0 ? (
        <div className="rounded-lg border border-dashed border-gray-300 py-12 text-center">
          <Star className="mx-auto h-10 w-10 text-gray-300" />
          <p className="mt-2 text-sm text-gray-500">No reviews yet</p>
        </div>
      ) : (
        <div className="space-y-3">
          {reviews.map((review) => (
            <Card key={review.id}>
              <CardContent className="p-4">
                <div className="flex items-start justify-between">
                  <div>
                    <div className="flex items-center gap-3">
                      <p className="text-sm font-semibold">{review.member_name || "Member"}</p>
                      <StarRating rating={review.rating} />
                      <SentimentBadge sentiment={review.sentiment} />
                      {review.is_flagged && (
                        <span className="rounded-full bg-red-100 px-2 py-0.5 text-xs font-medium text-red-700">
                          Flagged
                        </span>
                      )}
                    </div>
                    <p className="mt-0.5 text-xs text-gray-400">
                      {review.session_title} — {fmtDate(review.session_date || review.created_at)}
                    </p>
                  </div>
                  {!review.is_flagged && (
                    <button
                      onClick={() => flagMut.mutate(review.id)}
                      className="text-gray-400 hover:text-red-500"
                      title="Flag review"
                    >
                      <Flag className="h-4 w-4" />
                    </button>
                  )}
                </div>

                {review.review_text && (
                  <p className="mt-2 text-sm text-gray-700">{review.review_text}</p>
                )}

                {review.ai_analysis && (
                  <p className="mt-1 text-xs italic text-gray-400">AI: {review.ai_analysis}</p>
                )}

                {/* Response Section */}
                <div className="mt-3 border-t border-gray-100 pt-3">
                  {review.response_text ? (
                    <div className="rounded-lg bg-indigo-50 p-3">
                      <p className="text-xs font-medium text-indigo-600">Staff Response</p>
                      <p className="mt-1 text-sm text-gray-700">{review.response_text}</p>
                    </div>
                  ) : respondingTo === review.id ? (
                    <div className="space-y-2">
                      <textarea
                        value={responseText}
                        onChange={(e) => setResponseText(e.target.value)}
                        placeholder={review.response_draft || "Write a response..."}
                        rows={3}
                        className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
                      />
                      {review.response_draft && !responseText && (
                        <button
                          onClick={() => setResponseText(review.response_draft || "")}
                          className="text-xs text-indigo-600 hover:underline"
                        >
                          Use AI-drafted response
                        </button>
                      )}
                      <div className="flex gap-2">
                        <button
                          onClick={() => respondMut.mutate({ reviewId: review.id, text: responseText })}
                          disabled={!responseText || respondMut.isPending}
                          className="flex items-center gap-1 rounded-md bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
                        >
                          {respondMut.isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : <Send className="h-3 w-3" />}
                          Send Response
                        </button>
                        <button
                          onClick={() => { setRespondingTo(null); setResponseText(""); }}
                          className="rounded-md px-3 py-1.5 text-xs text-gray-500 hover:bg-gray-100"
                        >
                          Cancel
                        </button>
                      </div>
                    </div>
                  ) : (
                    <button
                      onClick={() => {
                        setRespondingTo(review.id);
                        setResponseText(review.response_draft || "");
                      }}
                      className="flex items-center gap-1 text-xs font-medium text-indigo-600 hover:underline"
                    >
                      <MessageSquare className="h-3 w-3" />
                      {review.response_draft ? "Review AI Draft & Respond" : "Write Response"}
                    </button>
                  )}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Schedule Insights Tab ──────────────────────────────────────────────────

function ScheduleInsightsTab() {
  const queryClient = useQueryClient();
  const [analysis, setAnalysis] = useState<string | null>(null);

  const analyzeMutation = useMutation({
    mutationFn: () => aiApi.analyzeSchedule().then((r) => r.data.data),
    onSuccess: (data) => {
      setAnalysis(data.analysis || "No analysis available");
    },
    onError: () => {
      setAnalysis("Failed to generate analysis. Make sure the Anthropic API key is configured.");
    },
  });

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="text-base">AI Schedule Analysis</CardTitle>
            <button
              onClick={() => analyzeMutation.mutate()}
              disabled={analyzeMutation.isPending}
              className="flex items-center gap-2 rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
            >
              {analyzeMutation.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Sparkles className="h-4 w-4" />
              )}
              {analyzeMutation.isPending ? "Analyzing..." : "Analyze Schedule"}
            </button>
          </div>
          <p className="text-sm text-gray-500">
            AI analyzes 90 days of attendance data to recommend optimal class times and instructor pairings.
          </p>
        </CardHeader>
        <CardContent>
          {analysis ? (
            <div className="prose prose-sm max-w-none whitespace-pre-wrap rounded-lg bg-gray-50 p-4 text-sm text-gray-700">
              {analysis}
            </div>
          ) : (
            <div className="flex flex-col items-center py-12 text-gray-400">
              <CalendarClock className="mb-3 h-10 w-10" />
              <p className="text-sm">Click &quot;Analyze Schedule&quot; to get AI-powered recommendations</p>
              <p className="mt-1 text-xs">This analyzes attendance patterns, time slots, and instructor performance</p>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
