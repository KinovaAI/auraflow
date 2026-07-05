"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { formatDistanceToNow } from "date-fns";
import {
  Loader2,
  CheckCircle2,
  XCircle,
  Clock,
  Zap,
  AlertTriangle,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { googleAdsApi, type AIAction } from "@/lib/google-ads-api";

const statusIcons: Record<string, typeof CheckCircle2> = {
  executed: CheckCircle2,
  approved: CheckCircle2,
  proposed: Clock,
  rejected: XCircle,
  failed: AlertTriangle,
};

const statusColors: Record<string, string> = {
  executed: "text-green-500",
  approved: "text-green-500",
  proposed: "text-yellow-500",
  rejected: "text-red-400",
  failed: "text-red-500",
};

interface Props {
  actions: AIAction[];
  pendingActions: AIAction[];
}

export function GoogleAdsActionsFeed({ actions, pendingActions }: Props) {
  const queryClient = useQueryClient();

  const approveMutation = useMutation({
    mutationFn: (id: string) =>
      googleAdsApi.approveAction(id).then((r) => r.data.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["google-ads-actions"] });
      queryClient.invalidateQueries({ queryKey: ["google-ads-pending"] });
    },
  });

  const rejectMutation = useMutation({
    mutationFn: (id: string) =>
      googleAdsApi.rejectAction(id).then((r) => r.data.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["google-ads-actions"] });
      queryClient.invalidateQueries({ queryKey: ["google-ads-pending"] });
    },
  });

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="text-base">AI Activity</CardTitle>
          <span className="text-xs text-gray-500">
            {actions.length} action{actions.length !== 1 ? "s" : ""}
          </span>
        </div>
      </CardHeader>
      <CardContent>
        {/* Pending Approvals */}
        {pendingActions.length > 0 && (
          <div className="mb-4 space-y-3">
            <p className="text-xs font-medium uppercase tracking-wider text-yellow-700">
              Awaiting Your Approval
            </p>
            {pendingActions.map((action) => (
              <div
                key={action.id}
                className="rounded-lg border border-yellow-200 bg-yellow-50 p-3"
              >
                <div className="flex items-start gap-2">
                  <Clock className="mt-0.5 h-4 w-4 text-yellow-500" />
                  <div className="flex-1">
                    <p className="text-sm font-medium text-gray-900">
                      {action.description}
                    </p>
                    <p className="mt-1 text-xs text-gray-600">
                      {action.reasoning}
                    </p>
                    <div className="mt-2 flex gap-2">
                      <Button
                        size="sm"
                        onClick={() => approveMutation.mutate(action.id)}
                        disabled={
                          approveMutation.isPending || rejectMutation.isPending
                        }
                      >
                        {approveMutation.isPending ? (
                          <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                        ) : (
                          <CheckCircle2 className="mr-1 h-3 w-3" />
                        )}
                        Approve
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        className="text-red-600 hover:bg-red-50"
                        onClick={() => rejectMutation.mutate(action.id)}
                        disabled={
                          approveMutation.isPending || rejectMutation.isPending
                        }
                      >
                        <XCircle className="mr-1 h-3 w-3" />
                        Reject
                      </Button>
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Action History */}
        <div className="space-y-3">
          {actions
            .filter((a) => a.status !== "proposed")
            .slice(0, 10)
            .map((action) => {
              const Icon = statusIcons[action.status] || Zap;
              const color = statusColors[action.status] || "text-gray-400";
              return (
                <div key={action.id} className="flex items-start gap-2">
                  <Icon className={`mt-0.5 h-4 w-4 ${color}`} />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between gap-2">
                      <p className="truncate text-sm text-gray-900">
                        {action.description}
                      </p>
                      <span className="whitespace-nowrap text-xs text-gray-400">
                        {formatDistanceToNow(new Date(action.created_at), {
                          addSuffix: true,
                        })}
                      </span>
                    </div>
                    <p className="mt-0.5 text-xs text-gray-500">
                      {action.reasoning}
                    </p>
                  </div>
                </div>
              );
            })}
        </div>
      </CardContent>
    </Card>
  );
}
