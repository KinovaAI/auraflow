"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Plus,
  Trash2,
  Pencil,
  Loader2,
  CheckCircle2,
  XCircle,
  RefreshCw,
  Webhook,
  AlertCircle,
  Clock,
  X,
} from "lucide-react";
import toast from "react-hot-toast";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { webhookApi } from "@/lib/webhook-api";

const AVAILABLE_EVENTS = [
  "booking.created",
  "booking.cancelled",
  "payment.completed",
  "member.created",
  "membership.purchased",
  "checkin.completed",
];

interface WebhookConfig {
  id: string;
  url: string;
  events: string[];
  secret?: string;
  is_active: boolean;
  created_at: string;
}

interface WebhookDelivery {
  id: string;
  config_id: string;
  event_type: string;
  status: "success" | "failed" | "pending";
  attempts: number;
  last_attempt_at: string;
  response_code?: number;
  created_at: string;
}

const statusBadge: Record<string, { bg: string; text: string; label: string }> = {
  success: { bg: "bg-green-50", text: "text-green-700", label: "Success" },
  failed: { bg: "bg-red-50", text: "text-red-700", label: "Failed" },
  pending: { bg: "bg-yellow-50", text: "text-yellow-700", label: "Pending" },
};

export default function WebhooksSettingsPage() {
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [formUrl, setFormUrl] = useState("");
  const [formSecret, setFormSecret] = useState("");
  const [formEvents, setFormEvents] = useState<string[]>([]);

  // Fetch configs
  const { data: configsData, isLoading: configsLoading } = useQuery({
    queryKey: ["webhook-configs"],
    queryFn: () => webhookApi.listConfigs().then((r) => r.data),
  });

  // Fetch deliveries
  const { data: deliveriesData, isLoading: deliveriesLoading } = useQuery({
    queryKey: ["webhook-deliveries"],
    queryFn: () => webhookApi.listDeliveries({ limit: 50 }).then((r) => r.data),
  });

  const configs: WebhookConfig[] = configsData?.data ?? [];
  const deliveries: WebhookDelivery[] = deliveriesData?.data ?? [];

  // Create config
  const createMutation = useMutation({
    mutationFn: (data: { url: string; events: string[]; secret?: string }) =>
      webhookApi.createConfig(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["webhook-configs"] });
      toast.success("Webhook created");
      resetForm();
    },
    onError: () => toast.error("Failed to create webhook"),
  });

  // Update config
  const updateMutation = useMutation({
    mutationFn: ({
      id,
      data,
    }: {
      id: string;
      data: { url: string; events: string[]; secret?: string };
    }) => webhookApi.updateConfig(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["webhook-configs"] });
      toast.success("Webhook updated");
      resetForm();
    },
    onError: () => toast.error("Failed to update webhook"),
  });

  // Delete config
  const deleteMutation = useMutation({
    mutationFn: (id: string) => webhookApi.deleteConfig(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["webhook-configs"] });
      queryClient.invalidateQueries({ queryKey: ["webhook-deliveries"] });
      toast.success("Webhook deleted");
    },
    onError: () => toast.error("Failed to delete webhook"),
  });

  // Retry delivery
  const retryMutation = useMutation({
    mutationFn: (id: string) => webhookApi.retryDelivery(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["webhook-deliveries"] });
      toast.success("Retry queued");
    },
    onError: () => toast.error("Retry failed"),
  });

  const resetForm = () => {
    setShowForm(false);
    setEditingId(null);
    setFormUrl("");
    setFormSecret("");
    setFormEvents([]);
  };

  const handleEdit = (config: WebhookConfig) => {
    setEditingId(config.id);
    setFormUrl(config.url);
    setFormSecret("");
    setFormEvents(config.events);
    setShowForm(true);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!formUrl.trim()) {
      toast.error("URL is required");
      return;
    }
    if (formEvents.length === 0) {
      toast.error("Select at least one event");
      return;
    }
    const payload = {
      url: formUrl.trim(),
      events: formEvents,
      ...(formSecret.trim() ? { secret: formSecret.trim() } : {}),
    };
    if (editingId) {
      updateMutation.mutate({ id: editingId, data: payload });
    } else {
      createMutation.mutate(payload);
    }
  };

  const toggleEvent = (event: string) => {
    setFormEvents((prev) =>
      prev.includes(event) ? prev.filter((e) => e !== event) : [...prev, event]
    );
  };

  const isSaving = createMutation.isPending || updateMutation.isPending;

  return (
    <div className="space-y-6">
      {/* Webhook Configs */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Webhook className="h-5 w-5 text-indigo-600" />
              <CardTitle className="text-base">Webhook Endpoints</CardTitle>
            </div>
            {!showForm && (
              <Button
                size="sm"
                onClick={() => {
                  resetForm();
                  setShowForm(true);
                }}
              >
                <Plus className="mr-1 h-4 w-4" />
                Add Webhook
              </Button>
            )}
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Inline form */}
          {showForm && (
            <form
              onSubmit={handleSubmit}
              className="space-y-4 rounded-lg border border-gray-200 bg-gray-50 p-4"
            >
              <div className="flex items-center justify-between">
                <h4 className="text-sm font-medium text-gray-900">
                  {editingId ? "Edit Webhook" : "New Webhook"}
                </h4>
                <button
                  type="button"
                  onClick={resetForm}
                  className="rounded p-1 text-gray-400 hover:bg-gray-200 hover:text-gray-600"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>

              <div className="space-y-3">
                <div>
                  <Label htmlFor="webhook-url">Endpoint URL</Label>
                  <Input
                    id="webhook-url"
                    type="url"
                    placeholder="https://example.com/webhooks"
                    value={formUrl}
                    onChange={(e) => setFormUrl(e.target.value)}
                    required
                    className="mt-1"
                  />
                </div>

                <div>
                  <Label htmlFor="webhook-secret">
                    Signing Secret{" "}
                    <span className="font-normal text-gray-400">(optional)</span>
                  </Label>
                  <Input
                    id="webhook-secret"
                    type="text"
                    placeholder={editingId ? "Leave blank to keep existing" : "whsec_..."}
                    value={formSecret}
                    onChange={(e) => setFormSecret(e.target.value)}
                    className="mt-1"
                  />
                </div>

                <div>
                  <Label>Events</Label>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {AVAILABLE_EVENTS.map((event) => {
                      const selected = formEvents.includes(event);
                      return (
                        <button
                          key={event}
                          type="button"
                          onClick={() => toggleEvent(event)}
                          className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
                            selected
                              ? "bg-indigo-100 text-indigo-700 ring-1 ring-indigo-300"
                              : "bg-gray-100 text-gray-600 hover:bg-gray-200"
                          }`}
                        >
                          {event}
                        </button>
                      );
                    })}
                  </div>
                </div>
              </div>

              <div className="flex items-center gap-2">
                <Button type="submit" size="sm" disabled={isSaving}>
                  {isSaving && <Loader2 className="mr-1 h-3 w-3 animate-spin" />}
                  {editingId ? "Update" : "Create"}
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={resetForm}
                >
                  Cancel
                </Button>
              </div>
            </form>
          )}

          {/* Configs table */}
          {configsLoading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-5 w-5 animate-spin text-indigo-600" />
            </div>
          ) : configs.length === 0 ? (
            <div className="py-8 text-center text-sm text-gray-400">
              No webhook endpoints configured yet.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-200 text-left text-xs font-medium uppercase text-gray-500">
                    <th className="pb-2 pr-4">URL</th>
                    <th className="pb-2 pr-4">Events</th>
                    <th className="pb-2 pr-4">Status</th>
                    <th className="pb-2 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {configs.map((config) => (
                    <tr key={config.id} className="group">
                      <td className="py-3 pr-4">
                        <span className="font-mono text-xs text-gray-700">
                          {config.url}
                        </span>
                      </td>
                      <td className="py-3 pr-4">
                        <div className="flex flex-wrap gap-1">
                          {config.events.map((evt) => (
                            <span
                              key={evt}
                              className="inline-block rounded bg-gray-100 px-1.5 py-0.5 text-xs text-gray-600"
                            >
                              {evt}
                            </span>
                          ))}
                        </div>
                      </td>
                      <td className="py-3 pr-4">
                        {config.is_active ? (
                          <span className="flex items-center gap-1 text-xs text-green-600">
                            <CheckCircle2 className="h-3 w-3" />
                            Active
                          </span>
                        ) : (
                          <span className="flex items-center gap-1 text-xs text-gray-400">
                            <XCircle className="h-3 w-3" />
                            Inactive
                          </span>
                        )}
                      </td>
                      <td className="py-3 text-right">
                        <div className="flex items-center justify-end gap-1 opacity-0 transition-opacity group-hover:opacity-100">
                          <button
                            onClick={() => handleEdit(config)}
                            className="rounded p-1.5 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
                            title="Edit"
                          >
                            <Pencil className="h-3.5 w-3.5" />
                          </button>
                          <button
                            onClick={() => {
                              if (confirm("Delete this webhook endpoint?")) {
                                deleteMutation.mutate(config.id);
                              }
                            }}
                            disabled={deleteMutation.isPending}
                            className="rounded p-1.5 text-gray-400 hover:bg-red-50 hover:text-red-600"
                            title="Delete"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
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

      {/* Delivery Log */}
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Clock className="h-5 w-5 text-indigo-600" />
            <CardTitle className="text-base">Recent Deliveries</CardTitle>
          </div>
        </CardHeader>
        <CardContent>
          {deliveriesLoading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-5 w-5 animate-spin text-indigo-600" />
            </div>
          ) : deliveries.length === 0 ? (
            <div className="py-8 text-center text-sm text-gray-400">
              No deliveries recorded yet.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-200 text-left text-xs font-medium uppercase text-gray-500">
                    <th className="pb-2 pr-4">Event</th>
                    <th className="pb-2 pr-4">Status</th>
                    <th className="pb-2 pr-4">Response</th>
                    <th className="pb-2 pr-4">Attempts</th>
                    <th className="pb-2 pr-4">Timestamp</th>
                    <th className="pb-2 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {deliveries.map((delivery) => {
                    const badge = statusBadge[delivery.status] ?? statusBadge.pending;
                    return (
                      <tr key={delivery.id} className="group">
                        <td className="py-3 pr-4">
                          <span className="rounded bg-gray-100 px-1.5 py-0.5 font-mono text-xs text-gray-700">
                            {delivery.event_type}
                          </span>
                        </td>
                        <td className="py-3 pr-4">
                          <span
                            className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${badge.bg} ${badge.text}`}
                          >
                            {delivery.status === "success" ? (
                              <CheckCircle2 className="h-3 w-3" />
                            ) : delivery.status === "failed" ? (
                              <AlertCircle className="h-3 w-3" />
                            ) : (
                              <Clock className="h-3 w-3" />
                            )}
                            {badge.label}
                          </span>
                        </td>
                        <td className="py-3 pr-4 text-xs text-gray-500">
                          {delivery.response_code ?? "-"}
                        </td>
                        <td className="py-3 pr-4 text-xs text-gray-500">
                          {delivery.attempts}
                        </td>
                        <td className="py-3 pr-4 text-xs text-gray-500">
                          {new Date(delivery.created_at).toLocaleString()}
                        </td>
                        <td className="py-3 text-right">
                          {delivery.status === "failed" && (
                            <button
                              onClick={() => retryMutation.mutate(delivery.id)}
                              disabled={retryMutation.isPending}
                              className="inline-flex items-center gap-1 rounded px-2 py-1 text-xs text-indigo-600 opacity-0 transition-opacity hover:bg-indigo-50 group-hover:opacity-100"
                            >
                              <RefreshCw className="h-3 w-3" />
                              Retry
                            </button>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
