"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { format } from "date-fns";
import Link from "next/link";
import {
  Loader2,
  Plus,
  Send,
  Trash2,
  BarChart3,
  MessageSquare,
  Target,
  Share2,
  ArrowRight,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  marketingApi,
  type Campaign,
  type CampaignCreate,
  type SmsMessage,
} from "@/lib/marketing-api";
import { GoogleAdsPanel } from "@/components/marketing/google-ads-panel";
import { MetaAdsPanel } from "@/components/marketing/meta-ads-panel";

// ── Status Badge ────────────────────────────────────────────────────────────

const statusColors: Record<string, string> = {
  draft: "bg-gray-100 text-gray-700",
  scheduled: "bg-blue-50 text-blue-700",
  sending: "bg-yellow-50 text-yellow-700",
  sent: "bg-green-50 text-green-700",
  cancelled: "bg-red-50 text-red-600",
};

function StatusBadge({ status }: { status: string }) {
  return (
    <span
      className={`rounded-full px-2 py-0.5 text-xs font-medium ${
        statusColors[status] || "bg-gray-100 text-gray-500"
      }`}
    >
      {status}
    </span>
  );
}

// ── Create Campaign Dialog ──────────────────────────────────────────────────

function CreateCampaignDialog({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: () => void;
}) {
  const [name, setName] = useState("");
  const [subject, setSubject] = useState("");
  const [htmlContent, setHtmlContent] = useState("");

  const createMutation = useMutation({
    mutationFn: (data: CampaignCreate) =>
      marketingApi.createCampaign(data).then((r) => r.data.data),
    onSuccess: () => {
      onCreated();
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    createMutation.mutate({
      name,
      subject,
      html_content: htmlContent || undefined,
    });
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="w-full max-w-lg rounded-lg bg-white p-6 shadow-xl">
        <h2 className="text-lg font-semibold text-gray-900">
          Create Campaign
        </h2>
        <form onSubmit={handleSubmit} className="mt-4 space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700">
              Campaign Name
            </label>
            <input
              type="text"
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              placeholder="e.g. March Newsletter"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700">
              Subject Line
            </label>
            <input
              type="text"
              required
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              placeholder="e.g. New classes this month!"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700">
              HTML Content (optional)
            </label>
            <textarea
              value={htmlContent}
              onChange={(e) => setHtmlContent(e.target.value)}
              rows={4}
              className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              placeholder="<p>Your email content here...</p>"
            />
          </div>
          {createMutation.isError && (
            <p className="text-sm text-red-600">
              Failed to create campaign. Please try again.
            </p>
          )}
          <div className="flex justify-end gap-3 pt-2">
            <Button
              type="button"
              variant="outline"
              onClick={onClose}
              disabled={createMutation.isPending}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={createMutation.isPending}>
              {createMutation.isPending && (
                <Loader2 className="mr-1 h-4 w-4 animate-spin" />
              )}
              Create Campaign
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ── Main Page ───────────────────────────────────────────────────────────────

export default function MarketingPage() {
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<"campaigns" | "sms" | "google-ads" | "facebook-ads">("campaigns");
  const [showCreateDialog, setShowCreateDialog] = useState(false);

  // ── Queries ─────────────────────────────────────────────────────────────

  const { data: campaigns, isLoading: campaignsLoading } = useQuery({
    queryKey: ["campaigns"],
    queryFn: () => marketingApi.listCampaigns().then((r) => r.data.data),
  });

  const { data: smsMessages, isLoading: smsLoading } = useQuery({
    queryKey: ["sms-messages"],
    queryFn: () => marketingApi.listSms({ limit: 100 }).then((r) => r.data.data),
  });

  // ── Mutations ───────────────────────────────────────────────────────────

  const sendMutation = useMutation({
    mutationFn: (id: string) =>
      marketingApi.sendCampaign(id).then((r) => r.data.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["campaigns"] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) =>
      marketingApi.deleteCampaign(id).then((r) => r.data.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["campaigns"] });
    },
  });

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Marketing</h1>
          <p className="text-sm text-gray-500">
            Email campaigns, SMS messaging, Google Ads, and Facebook Ads
          </p>
        </div>
        {activeTab === "campaigns" && (
          <Button onClick={() => setShowCreateDialog(true)}>
            <Plus className="mr-1 h-4 w-4" />
            Create Campaign
          </Button>
        )}
      </div>

      {/* Summary Cards */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-gray-500">
                  Total Campaigns
                </p>
                <p className="mt-1 text-2xl font-bold text-gray-900">
                  {campaignsLoading ? (
                    <Loader2 className="h-5 w-5 animate-spin" />
                  ) : (
                    campaigns?.length ?? 0
                  )}
                </p>
              </div>
              <div className="rounded-full bg-indigo-100 p-2">
                <Send className="h-5 w-5 text-indigo-600" />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-gray-500">Sent</p>
                <p className="mt-1 text-2xl font-bold text-gray-900">
                  {campaignsLoading ? (
                    <Loader2 className="h-5 w-5 animate-spin" />
                  ) : (
                    campaigns?.filter((c) => c.status === "sent").length ?? 0
                  )}
                </p>
              </div>
              <div className="rounded-full bg-green-100 p-2">
                <BarChart3 className="h-5 w-5 text-green-600" />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-gray-500">Drafts</p>
                <p className="mt-1 text-2xl font-bold text-gray-900">
                  {campaignsLoading ? (
                    <Loader2 className="h-5 w-5 animate-spin" />
                  ) : (
                    campaigns?.filter((c) => c.status === "draft").length ?? 0
                  )}
                </p>
              </div>
              <div className="rounded-full bg-gray-100 p-2">
                <Send className="h-5 w-5 text-gray-500" />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-gray-500">
                  SMS Messages
                </p>
                <p className="mt-1 text-2xl font-bold text-gray-900">
                  {smsLoading ? (
                    <Loader2 className="h-5 w-5 animate-spin" />
                  ) : (
                    smsMessages?.length ?? 0
                  )}
                </p>
              </div>
              <div className="rounded-full bg-blue-100 p-2">
                <MessageSquare className="h-5 w-5 text-blue-600" />
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Social Media Link */}
      <Link
        href="/dashboard/marketing/social"
        className="flex items-center justify-between rounded-lg border border-indigo-200 bg-indigo-50 p-4 transition-colors hover:bg-indigo-100"
      >
        <div className="flex items-center gap-3">
          <div className="rounded-full bg-indigo-100 p-2">
            <Share2 className="h-5 w-5 text-indigo-600" />
          </div>
          <div>
            <p className="font-medium text-gray-900">Social Media</p>
            <p className="text-sm text-gray-500">
              AI-powered Facebook &amp; Instagram management
            </p>
          </div>
        </div>
        <ArrowRight className="h-5 w-5 text-indigo-400" />
      </Link>

      {/* Tabs */}
      <div className="flex gap-4 overflow-x-auto border-b border-gray-200">
        {(
          [
            { key: "campaigns", label: "Campaigns", count: campaigns?.length },
            { key: "sms", label: "SMS", count: smsMessages?.length },
            { key: "google-ads", label: "Google Ads", count: undefined },
            { key: "facebook-ads", label: "Facebook Ads", count: undefined },
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
            {tab.count !== undefined && tab.count > 0 ? (
              <span className="ml-1.5 rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-600">
                {tab.count}
              </span>
            ) : null}
          </button>
        ))}
      </div>

      {/* Campaigns Tab */}
      {activeTab === "campaigns" && (
        <>
          {campaignsLoading ? (
            <div className="flex items-center justify-center py-20">
              <Loader2 className="h-8 w-8 animate-spin text-indigo-600" />
            </div>
          ) : !campaigns?.length ? (
            <div className="rounded-lg border border-dashed border-gray-300 py-12 text-center">
              <Send className="mx-auto h-10 w-10 text-gray-300" />
              <p className="mt-2 text-sm text-gray-500">
                No campaigns yet. Create your first campaign to get started.
              </p>
              <Button
                className="mt-4"
                variant="outline"
                onClick={() => setShowCreateDialog(true)}
              >
                <Plus className="mr-1 h-4 w-4" />
                Create Campaign
              </Button>
            </div>
          ) : (
            <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                      Name
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                      Subject
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                      Status
                    </th>
                    <th className="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-gray-500">
                      Recipients
                    </th>
                    <th className="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-gray-500">
                      Delivered
                    </th>
                    <th className="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-gray-500">
                      Actions
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200">
                  {campaigns.map((campaign) => (
                    <tr key={campaign.id} className="hover:bg-gray-50">
                      <td className="whitespace-nowrap px-4 py-3 text-sm font-medium text-gray-900">
                        {campaign.name}
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-600">
                        {campaign.subject}
                      </td>
                      <td className="whitespace-nowrap px-4 py-3">
                        <StatusBadge status={campaign.status} />
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 text-right text-sm text-gray-500">
                        {campaign.recipients ?? "--"}
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 text-right text-sm text-gray-500">
                        {campaign.delivered ?? "--"}
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 text-right">
                        <div className="flex items-center justify-end gap-2">
                          {campaign.status === "draft" && (
                            <>
                              <Button
                                size="sm"
                                variant="outline"
                                onClick={() => sendMutation.mutate(campaign.id)}
                                disabled={sendMutation.isPending}
                              >
                                <Send className="mr-1 h-3 w-3" />
                                Send
                              </Button>
                              <Button
                                size="sm"
                                variant="outline"
                                className="text-red-600 hover:bg-red-50 hover:text-red-700"
                                onClick={() =>
                                  deleteMutation.mutate(campaign.id)
                                }
                                disabled={deleteMutation.isPending}
                              >
                                <Trash2 className="h-3 w-3" />
                              </Button>
                            </>
                          )}
                          {campaign.status === "sent" && (
                            <span className="text-xs text-gray-400">
                              Sent{" "}
                              {campaign.sent_at
                                ? format(
                                    new Date(campaign.sent_at),
                                    "MMM d, h:mm a"
                                  )
                                : ""}
                            </span>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {/* SMS Tab */}
      {activeTab === "sms" && (
        <>
          {smsLoading ? (
            <div className="flex items-center justify-center py-20">
              <Loader2 className="h-8 w-8 animate-spin text-indigo-600" />
            </div>
          ) : !smsMessages?.length ? (
            <div className="rounded-lg border border-dashed border-gray-300 py-12 text-center">
              <MessageSquare className="mx-auto h-10 w-10 text-gray-300" />
              <p className="mt-2 text-sm text-gray-500">
                No SMS messages sent yet
              </p>
            </div>
          ) : (
            <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                      To
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                      Body
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                      Type
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                      Status
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                      Sent At
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200">
                  {smsMessages.map((msg) => (
                    <tr key={msg.id} className="hover:bg-gray-50">
                      <td className="whitespace-nowrap px-4 py-3 text-sm text-gray-900">
                        {msg.to_phone}
                      </td>
                      <td className="max-w-xs truncate px-4 py-3 text-sm text-gray-600">
                        {msg.body}
                      </td>
                      <td className="whitespace-nowrap px-4 py-3">
                        <span className="flex items-center gap-1 text-xs text-gray-500">
                          <MessageSquare className="h-3 w-3" />
                          {msg.type}
                        </span>
                      </td>
                      <td className="whitespace-nowrap px-4 py-3">
                        <span
                          className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                            msg.status === "sent"
                              ? "bg-green-50 text-green-700"
                              : msg.status === "failed"
                                ? "bg-red-50 text-red-600"
                                : "bg-gray-100 text-gray-500"
                          }`}
                        >
                          {msg.status}
                        </span>
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 text-sm text-gray-500">
                        {format(new Date(msg.created_at), "MMM d, h:mm a")}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {/* Google Ads Tab */}
      {activeTab === "google-ads" && <GoogleAdsPanel />}

      {/* Facebook Ads Tab */}
      {activeTab === "facebook-ads" && <MetaAdsPanel />}

      {/* Create Campaign Dialog */}
      {showCreateDialog && (
        <CreateCampaignDialog
          onClose={() => setShowCreateDialog(false)}
          onCreated={() => {
            setShowCreateDialog(false);
            queryClient.invalidateQueries({ queryKey: ["campaigns"] });
          }}
        />
      )}
    </div>
  );
}
