"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { RefreshCw, Loader2 } from "lucide-react";
import toast from "react-hot-toast";

import { Button } from "@/components/ui/button";
import { videoApi } from "@/lib/video-api";

interface SyncButtonProps {
  size?: "default" | "sm" | "lg";
}

export function SyncButton({ size = "sm" }: SyncButtonProps) {
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: () => videoApi.syncAll(),
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ["videos"] });

      const results = res.data.data;
      if (Array.isArray(results)) {
        const totalNew = results.reduce(
          (sum: number, r: { new?: number; updated?: number }) => sum + (r.new ?? 0),
          0
        );
        const totalUpdated = results.reduce(
          (sum: number, r: { new?: number; updated?: number }) => sum + (r.updated ?? 0),
          0
        );
        toast.success(
          `Sync complete: ${totalNew} new, ${totalUpdated} updated`
        );
      } else {
        toast.success("Sync complete");
      }
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      toast.error(detail || "Sync failed");
    },
  });

  return (
    <Button
      variant="outline"
      size={size}
      onClick={() => mutation.mutate()}
      disabled={mutation.isPending}
    >
      {mutation.isPending ? (
        <Loader2 className="mr-1 h-4 w-4 animate-spin" />
      ) : (
        <RefreshCw className="mr-1 h-4 w-4" />
      )}
      {mutation.isPending ? "Syncing..." : "Sync"}
    </Button>
  );
}
