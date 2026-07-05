"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  Loader2,
  Plus,
  FileCheck,
  AlertTriangle,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import toast from "react-hot-toast";

interface WaiverTemplate {
  id: string;
  version: number;
  title: string;
  content: string;
  require_resign: boolean;
  expiration_days: number | null;
  is_active: boolean;
  created_at: string;
}

interface UnsignedMember {
  id: string;
  first_name: string;
  last_name: string;
  email: string;
}

export default function WaiverSettingsPage() {
  const qc = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [showUnsigned, setShowUnsigned] = useState(false);
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [requireResign, setRequireResign] = useState(false);
  const [expirationDays, setExpirationDays] = useState("");

  const { data: templates, isLoading } = useQuery({
    queryKey: ["waiver-templates"],
    queryFn: () =>
      apiClient
        .get<{ data: WaiverTemplate[] }>("/waivers/templates")
        .then((r) => r.data.data),
  });

  const { data: unsignedMembers, isLoading: loadingUnsigned } = useQuery({
    queryKey: ["waiver-unsigned"],
    queryFn: () =>
      apiClient
        .get<{ data: UnsignedMember[] }>("/waivers/unsigned-members")
        .then((r) => r.data.data),
    enabled: showUnsigned,
  });

  const createMutation = useMutation({
    mutationFn: (body: {
      title: string;
      content: string;
      require_resign: boolean;
      expiration_days: number | null;
    }) => apiClient.post("/waivers/templates", body),
    onSuccess: () => {
      toast.success("Waiver template created");
      qc.invalidateQueries({ queryKey: ["waiver-templates"] });
      qc.invalidateQueries({ queryKey: ["waiver-unsigned"] });
      setShowForm(false);
      setTitle("");
      setContent("");
      setRequireResign(false);
      setExpirationDays("");
    },
    onError: () => {
      toast.error("Failed to create waiver template");
    },
  });

  const activeTemplate = templates?.find((t) => t.is_active);

  return (
    <div className="space-y-6">
      {/* Current Active Waiver */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="text-base">Active Waiver</CardTitle>
            <FileCheck className="h-4 w-4 text-gray-400" />
          </div>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <Loader2 className="h-5 w-5 animate-spin text-gray-300" />
          ) : activeTemplate ? (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <div>
                  <p className="font-medium text-gray-900">
                    {activeTemplate.title}
                  </p>
                  <p className="text-xs text-gray-400">
                    Version {activeTemplate.version} · Created{" "}
                    {new Date(activeTemplate.created_at).toLocaleDateString()}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  {activeTemplate.require_resign && (
                    <span className="rounded bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-700">
                      Re-sign Required
                    </span>
                  )}
                  {activeTemplate.expiration_days && (
                    <span className="rounded bg-blue-100 px-2 py-0.5 text-xs font-medium text-blue-700">
                      Expires in {activeTemplate.expiration_days}d
                    </span>
                  )}
                </div>
              </div>
              <div className="max-h-40 overflow-y-auto rounded border bg-gray-50 p-3 text-sm text-gray-600 whitespace-pre-wrap">
                {activeTemplate.content}
              </div>
            </div>
          ) : (
            <div className="text-center py-4">
              <AlertTriangle className="mx-auto h-8 w-8 text-amber-400" />
              <p className="mt-2 text-sm text-gray-500">
                No waiver template configured. Members can book without signing.
              </p>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Unsigned Members */}
      {activeTemplate && (
        <Card>
          <CardHeader>
            <button
              onClick={() => setShowUnsigned(!showUnsigned)}
              className="flex w-full items-center justify-between"
            >
              <CardTitle className="text-base">Unsigned Members</CardTitle>
              {showUnsigned ? (
                <ChevronUp className="h-4 w-4 text-gray-400" />
              ) : (
                <ChevronDown className="h-4 w-4 text-gray-400" />
              )}
            </button>
          </CardHeader>
          {showUnsigned && (
            <CardContent>
              {loadingUnsigned ? (
                <Loader2 className="h-5 w-5 animate-spin text-gray-300" />
              ) : unsignedMembers && unsignedMembers.length > 0 ? (
                <div className="space-y-1.5">
                  <p className="text-xs text-gray-400 mb-2">
                    {unsignedMembers.length} member
                    {unsignedMembers.length !== 1 ? "s" : ""} without a valid
                    signature
                  </p>
                  {unsignedMembers.map((m) => (
                    <div
                      key={m.id}
                      className="flex items-center justify-between rounded border px-3 py-2 text-sm"
                    >
                      <span className="font-medium text-gray-900">
                        {m.first_name} {m.last_name}
                      </span>
                      <span className="text-xs text-gray-400">{m.email}</span>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-gray-400">
                  All active members have signed the current waiver.
                </p>
              )}
            </CardContent>
          )}
        </Card>
      )}

      {/* Create New Version */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="text-base">
              {showForm ? "New Waiver Version" : "Create New Version"}
            </CardTitle>
            {!showForm && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => setShowForm(true)}
              >
                <Plus className="mr-1.5 h-3.5 w-3.5" />
                New Version
              </Button>
            )}
          </div>
        </CardHeader>
        {showForm && (
          <CardContent>
            <div className="space-y-4">
              <div>
                <label className="mb-1 block text-sm font-medium text-gray-700">
                  Title
                </label>
                <input
                  type="text"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="e.g. Liability Waiver & Release"
                  className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium text-gray-700">
                  Waiver Content
                </label>
                <textarea
                  rows={10}
                  value={content}
                  onChange={(e) => setContent(e.target.value)}
                  placeholder="Enter the full waiver text..."
                  className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                />
              </div>
              <div className="flex flex-wrap gap-6">
                <label className="flex items-center gap-2 text-sm text-gray-700">
                  <input
                    type="checkbox"
                    checked={requireResign}
                    onChange={(e) => setRequireResign(e.target.checked)}
                    className="rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                  />
                  Require existing members to re-sign
                </label>
                <div>
                  <label className="mb-1 block text-xs font-medium text-gray-500">
                    Expiration (days, blank = never)
                  </label>
                  <input
                    type="number"
                    value={expirationDays}
                    onChange={(e) => setExpirationDays(e.target.value)}
                    placeholder="365"
                    className="w-24 rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                  />
                </div>
              </div>
              <div className="flex gap-3">
                <Button
                  onClick={() =>
                    createMutation.mutate({
                      title,
                      content,
                      require_resign: requireResign,
                      expiration_days: expirationDays
                        ? parseInt(expirationDays, 10)
                        : null,
                    })
                  }
                  disabled={
                    !title.trim() ||
                    !content.trim() ||
                    createMutation.isPending
                  }
                >
                  {createMutation.isPending ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      Creating...
                    </>
                  ) : (
                    "Create Waiver"
                  )}
                </Button>
                <Button variant="ghost" onClick={() => setShowForm(false)}>
                  Cancel
                </Button>
              </div>
            </div>
          </CardContent>
        )}
      </Card>

      {/* Version History */}
      {templates && templates.length > 1 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Version History</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {templates
                .filter((t) => !t.is_active)
                .map((t) => (
                  <div
                    key={t.id}
                    className="flex items-center justify-between rounded border px-3 py-2 text-sm"
                  >
                    <div>
                      <span className="font-medium text-gray-700">
                        v{t.version} — {t.title}
                      </span>
                    </div>
                    <span className="text-xs text-gray-400">
                      {new Date(t.created_at).toLocaleDateString()}
                    </span>
                  </div>
                ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
