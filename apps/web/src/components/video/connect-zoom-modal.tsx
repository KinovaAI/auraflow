"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { X, Loader2, CheckCircle } from "lucide-react";
import toast from "react-hot-toast";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { videoApi } from "@/lib/video-api";

interface ConnectZoomModalProps {
  onClose: () => void;
  onConnected: () => void;
}

export function ConnectZoomModal({
  onClose,
  onConnected,
}: ConnectZoomModalProps) {
  const queryClient = useQueryClient();
  const [accountId, setAccountId] = useState("");
  const [clientId, setClientId] = useState("");
  const [clientSecret, setClientSecret] = useState("");
  const [testSuccess, setTestSuccess] = useState(false);

  const testMutation = useMutation({
    mutationFn: () =>
      videoApi.testZoom({
        account_id: accountId,
        client_id: clientId,
        client_secret: clientSecret,
      }),
    onSuccess: (resp) => {
      setTestSuccess(true);
      const data = resp.data?.data;
      const name = data?.display_name || data?.email || "";
      toast.success(`Zoom connection verified${name ? ` — ${name}` : ""}`);
    },
    onError: (err: unknown) => {
      setTestSuccess(false);
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      toast.error(detail || "Zoom connection test failed");
    },
  });

  const connectMutation = useMutation({
    mutationFn: () =>
      videoApi.connectZoom({
        account_id: accountId,
        client_id: clientId,
        client_secret: clientSecret,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ["video-connection-status"],
      });
      toast.success("Zoom connected successfully");
      onConnected();
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      toast.error(detail || "Failed to connect Zoom");
    },
  });

  const canTest =
    accountId.trim().length > 0 &&
    clientId.trim().length > 0 &&
    clientSecret.trim().length > 0;
  const isPending = testMutation.isPending || connectMutation.isPending;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="mx-4 w-full max-w-md rounded-lg bg-white shadow-xl">
        <div className="flex items-center justify-between border-b border-gray-200 px-6 py-4">
          <h2 className="text-lg font-semibold text-gray-900">
            Connect Zoom
          </h2>
          <button
            onClick={onClose}
            className="rounded-md p-1 text-gray-400 hover:bg-gray-100"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="space-y-4 px-6 py-4">
          <p className="text-sm text-gray-500">
            Enter your Zoom Server-to-Server OAuth app credentials. Create one
            in the{" "}
            <a
              href="https://marketplace.zoom.us/"
              target="_blank"
              rel="noopener noreferrer"
              className="text-indigo-600 hover:underline"
            >
              Zoom Marketplace
            </a>{" "}
            under Develop &gt; Build App &gt; Server-to-Server OAuth.
          </p>

          <div>
            <Label htmlFor="zoom-account-id">Account ID</Label>
            <Input
              id="zoom-account-id"
              value={accountId}
              onChange={(e) => {
                setAccountId(e.target.value);
                setTestSuccess(false);
              }}
              placeholder="Enter Zoom Account ID"
            />
          </div>

          <div>
            <Label htmlFor="zoom-client-id">Client ID</Label>
            <Input
              id="zoom-client-id"
              value={clientId}
              onChange={(e) => {
                setClientId(e.target.value);
                setTestSuccess(false);
              }}
              placeholder="Enter Client ID"
            />
          </div>

          <div>
            <Label htmlFor="zoom-client-secret">Client Secret</Label>
            <Input
              id="zoom-client-secret"
              type="password"
              value={clientSecret}
              onChange={(e) => {
                setClientSecret(e.target.value);
                setTestSuccess(false);
              }}
              placeholder="Enter Client Secret"
            />
          </div>

          {testSuccess && (
            <div className="flex items-center gap-2 rounded-md bg-green-50 px-3 py-2 text-sm text-green-700">
              <CheckCircle className="h-4 w-4" />
              Connection test passed
            </div>
          )}
        </div>

        <div className="flex items-center justify-end gap-2 border-t border-gray-200 px-6 py-4">
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant="outline"
            onClick={() => testMutation.mutate()}
            disabled={!canTest || isPending}
          >
            {testMutation.isPending && (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            )}
            Test Connection
          </Button>
          <Button
            onClick={() => connectMutation.mutate()}
            disabled={!testSuccess || isPending}
          >
            {connectMutation.isPending && (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            )}
            Connect
          </Button>
        </div>
      </div>
    </div>
  );
}
