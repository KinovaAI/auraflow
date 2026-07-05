"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { X, Loader2, CheckCircle } from "lucide-react";
import toast from "react-hot-toast";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { videoApi } from "@/lib/video-api";

interface ConnectYouTubeModalProps {
  onClose: () => void;
  onConnected: () => void;
}

export function ConnectYouTubeModal({
  onClose,
  onConnected,
}: ConnectYouTubeModalProps) {
  const queryClient = useQueryClient();
  const [apiKey, setApiKey] = useState("");
  const [channelId, setChannelId] = useState("");
  const [testSuccess, setTestSuccess] = useState(false);

  const testMutation = useMutation({
    mutationFn: () => videoApi.testYouTube(apiKey, channelId),
    onSuccess: () => {
      setTestSuccess(true);
      toast.success("YouTube connection test passed");
    },
    onError: (err: unknown) => {
      setTestSuccess(false);
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      toast.error(detail || "Connection test failed");
    },
  });

  const connectMutation = useMutation({
    mutationFn: () => videoApi.connectYouTube(apiKey, channelId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["video-connection-status"] });
      toast.success("YouTube connected successfully");
      onConnected();
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      toast.error(detail || "Failed to connect YouTube");
    },
  });

  const canTest = apiKey.trim().length > 0 && channelId.trim().length > 0;
  const isPending = testMutation.isPending || connectMutation.isPending;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="mx-4 w-full max-w-md rounded-lg bg-white shadow-xl">
        <div className="flex items-center justify-between border-b border-gray-200 px-6 py-4">
          <h2 className="text-lg font-semibold text-gray-900">
            Connect YouTube
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
            Enter your YouTube Data API key and channel ID. AuraFlow uses your
            own API quota -- we never store or stream your videos.
          </p>

          <div>
            <Label htmlFor="yt-api-key">YouTube API Key</Label>
            <Input
              id="yt-api-key"
              type="password"
              value={apiKey}
              onChange={(e) => {
                setApiKey(e.target.value);
                setTestSuccess(false);
              }}
              placeholder="AIza..."
            />
          </div>

          <div>
            <Label htmlFor="yt-channel-id">Channel ID</Label>
            <Input
              id="yt-channel-id"
              value={channelId}
              onChange={(e) => {
                setChannelId(e.target.value);
                setTestSuccess(false);
              }}
              placeholder="UC..."
            />
            <p className="mt-1 text-xs text-gray-400">
              Found in your YouTube channel URL or Studio settings.
            </p>
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
