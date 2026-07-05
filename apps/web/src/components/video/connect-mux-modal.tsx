"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { X, Loader2, CheckCircle } from "lucide-react";
import toast from "react-hot-toast";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { videoApi } from "@/lib/video-api";

interface ConnectMuxModalProps {
  onClose: () => void;
  onConnected: () => void;
}

export function ConnectMuxModal({
  onClose,
  onConnected,
}: ConnectMuxModalProps) {
  const queryClient = useQueryClient();
  const [tokenId, setTokenId] = useState("");
  const [tokenSecret, setTokenSecret] = useState("");
  const [testSuccess, setTestSuccess] = useState(false);

  const testMutation = useMutation({
    mutationFn: () => videoApi.testMux(tokenId, tokenSecret),
    onSuccess: () => {
      setTestSuccess(true);
      toast.success("Mux connection test passed");
    },
    onError: (err: unknown) => {
      setTestSuccess(false);
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      toast.error(detail || "Connection test failed");
    },
  });

  const connectMutation = useMutation({
    mutationFn: () => videoApi.connectMux(tokenId, tokenSecret),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["video-connection-status"] });
      toast.success("Mux connected successfully");
      onConnected();
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      toast.error(detail || "Failed to connect Mux");
    },
  });

  const canTest = tokenId.trim().length > 0 && tokenSecret.trim().length > 0;
  const isPending = testMutation.isPending || connectMutation.isPending;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="mx-4 w-full max-w-md rounded-lg bg-white shadow-xl">
        <div className="flex items-center justify-between border-b border-gray-200 px-6 py-4">
          <h2 className="text-lg font-semibold text-gray-900">
            Connect Mux
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
            Enter your Mux access token credentials. You can create a new token
            in the Mux dashboard under Settings &gt; Access Tokens.
          </p>

          <div>
            <Label htmlFor="mux-token-id">Token ID</Label>
            <Input
              id="mux-token-id"
              value={tokenId}
              onChange={(e) => {
                setTokenId(e.target.value);
                setTestSuccess(false);
              }}
              placeholder="Enter Mux Token ID"
            />
          </div>

          <div>
            <Label htmlFor="mux-token-secret">Token Secret</Label>
            <Input
              id="mux-token-secret"
              type="password"
              value={tokenSecret}
              onChange={(e) => {
                setTokenSecret(e.target.value);
                setTestSuccess(false);
              }}
              placeholder="Enter Mux Token Secret"
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
