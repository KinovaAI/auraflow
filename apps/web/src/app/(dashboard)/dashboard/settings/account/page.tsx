"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2, AlertTriangle, CheckCircle2, XCircle } from "lucide-react";
import toast from "react-hot-toast";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { organizationsApi } from "@/lib/organizations-api";
import { useAuthStore } from "@/stores/auth-store";

const CANCELLATION_REASONS = [
  { value: "", label: "Select a reason (optional)" },
  { value: "too_expensive", label: "Too expensive" },
  { value: "missing_features", label: "Missing features" },
  { value: "switching_competitor", label: "Switching to a competitor" },
  { value: "closing_business", label: "Closing my business" },
  { value: "not_using", label: "Not using it enough" },
  { value: "other", label: "Other" },
];

export default function AccountSettingsPage() {
  const queryClient = useQueryClient();
  const user = useAuthStore((s) => s.user);
  const isOwner = user?.active_org_role === "owner";

  const [showCancelModal, setShowCancelModal] = useState(false);
  const [reason, setReason] = useState("");
  const [feedback, setFeedback] = useState("");

  const { data: cancellationStatus, isLoading } = useQuery({
    queryKey: ["cancellation-status"],
    queryFn: () => organizationsApi.getCancellationStatus().then((r) => r.data),
    enabled: isOwner,
  });

  const cancelMutation = useMutation({
    mutationFn: () =>
      organizationsApi.cancelAccount({
        reason: reason || undefined,
        feedback: feedback || undefined,
      }),
    onSuccess: (resp) => {
      toast.success(resp.data.message);
      setShowCancelModal(false);
      setReason("");
      setFeedback("");
      queryClient.invalidateQueries({ queryKey: ["cancellation-status"] });
    },
    onError: (err: unknown) => {
      const message =
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail || "Failed to cancel account";
      toast.error(message);
    },
  });

  const reactivateMutation = useMutation({
    mutationFn: () => organizationsApi.reactivateAccount(),
    onSuccess: (resp) => {
      toast.success(resp.data.message);
      queryClient.invalidateQueries({ queryKey: ["cancellation-status"] });
    },
    onError: (err: unknown) => {
      const message =
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail || "Failed to reactivate account";
      toast.error(message);
    },
  });

  if (!isOwner) {
    return (
      <div className="mx-auto max-w-2xl py-10 text-center text-gray-500">
        Only the account owner can manage account cancellation.
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="h-8 w-8 animate-spin text-indigo-600" />
      </div>
    );
  }

  const isCancelling = cancellationStatus?.status === "cancelling";
  const isCancelled = cancellationStatus?.status === "cancelled";
  const effectiveDate = cancellationStatus?.cancellation_effective_at
    ? new Date(cancellationStatus.cancellation_effective_at)
    : null;

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      {/* Cancellation in progress banner */}
      {isCancelling && (
        <Card className="border-yellow-300 bg-yellow-50">
          <CardContent className="py-5">
            <div className="flex items-start gap-3">
              <AlertTriangle className="mt-0.5 h-5 w-5 flex-shrink-0 text-yellow-600" />
              <div className="flex-1">
                <h3 className="text-sm font-semibold text-yellow-800">
                  Cancellation Scheduled
                </h3>
                <p className="mt-1 text-sm text-yellow-700">
                  Your account will be cancelled on{" "}
                  <strong>
                    {effectiveDate
                      ? effectiveDate.toLocaleDateString("en-US", {
                          year: "numeric",
                          month: "long",
                          day: "numeric",
                        })
                      : "the end of your billing period"}
                  </strong>
                  . Your data will be retained for 30 days after that date.
                </p>
                <p className="mt-2 text-sm text-yellow-700">
                  You can continue using all features until then.
                </p>
                <Button
                  className="mt-3"
                  variant="outline"
                  onClick={() => reactivateMutation.mutate()}
                  disabled={reactivateMutation.isPending}
                >
                  {reactivateMutation.isPending && (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  )}
                  Reactivate Account
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Already cancelled banner */}
      {isCancelled && (
        <Card className="border-red-300 bg-red-50">
          <CardContent className="py-5">
            <div className="flex items-start gap-3">
              <XCircle className="mt-0.5 h-5 w-5 flex-shrink-0 text-red-600" />
              <div>
                <h3 className="text-sm font-semibold text-red-800">
                  Account Cancelled
                </h3>
                <p className="mt-1 text-sm text-red-700">
                  Your account has been cancelled. Your data will be retained
                  for 30 days. Contact support if you need to recover your
                  account.
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Account Status */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Account Status</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="rounded-md bg-gray-50 p-3 text-sm">
            <div className="flex justify-between">
              <span className="text-gray-500">Status</span>
              <span
                className={`font-medium ${
                  isCancelling
                    ? "text-yellow-600"
                    : isCancelled
                    ? "text-red-600"
                    : "text-green-600"
                }`}
              >
                {isCancelling
                  ? "Cancelling"
                  : isCancelled
                  ? "Cancelled"
                  : cancellationStatus?.status === "trial"
                  ? "Trial"
                  : "Active"}
              </span>
            </div>
            {effectiveDate && isCancelling && (
              <div className="mt-1 flex justify-between">
                <span className="text-gray-500">Cancels on</span>
                <span className="text-yellow-600">
                  {effectiveDate.toLocaleDateString("en-US", {
                    year: "numeric",
                    month: "long",
                    day: "numeric",
                  })}
                </span>
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Cancel Account Section */}
      {!isCancelling && !isCancelled && (
        <Card className="border-red-200">
          <CardHeader>
            <CardTitle className="text-base text-red-700">
              Cancel Account
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <p className="text-sm text-gray-600">
              Cancelling your account will end your subscription at the end of
              the current billing period. Your data will be retained for 30 days
              after cancellation.
            </p>
            <p className="text-sm text-gray-500">
              This action can be reversed before the cancellation takes effect.
            </p>
            <Button
              variant="outline"
              className="border-red-300 text-red-700 hover:bg-red-50 hover:text-red-800"
              onClick={() => setShowCancelModal(true)}
            >
              Cancel Account...
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Cancellation Confirmation Modal */}
      {showCancelModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          {/* Backdrop */}
          <div
            className="absolute inset-0 bg-black/50"
            onClick={() => setShowCancelModal(false)}
          />
          {/* Modal */}
          <div className="relative z-10 mx-4 w-full max-w-md rounded-lg bg-white p-6 shadow-xl">
            <div className="mb-4 flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-full bg-red-100">
                <AlertTriangle className="h-5 w-5 text-red-600" />
              </div>
              <div>
                <h2 className="text-lg font-semibold text-gray-900">
                  Cancel Your Account
                </h2>
                <p className="text-sm text-gray-500">
                  This will end your subscription
                </p>
              </div>
            </div>

            <div className="mb-5 rounded-md bg-red-50 p-3">
              <h3 className="text-sm font-medium text-red-800">
                What happens when you cancel:
              </h3>
              <ul className="mt-2 space-y-1 text-sm text-red-700">
                <li className="flex items-start gap-2">
                  <span className="mt-1.5 block h-1 w-1 flex-shrink-0 rounded-full bg-red-400" />
                  Your subscription will end at the end of the current billing
                  period
                </li>
                <li className="flex items-start gap-2">
                  <span className="mt-1.5 block h-1 w-1 flex-shrink-0 rounded-full bg-red-400" />
                  All features will remain accessible until then
                </li>
                <li className="flex items-start gap-2">
                  <span className="mt-1.5 block h-1 w-1 flex-shrink-0 rounded-full bg-red-400" />
                  Your data will be retained for 30 days after cancellation
                </li>
                <li className="flex items-start gap-2">
                  <span className="mt-1.5 block h-1 w-1 flex-shrink-0 rounded-full bg-red-400" />
                  You can reactivate anytime before the cancellation date
                </li>
              </ul>
            </div>

            <div className="space-y-4">
              <div>
                <Label htmlFor="cancel-reason" className="text-sm text-gray-700">
                  Why are you cancelling?
                </Label>
                <select
                  id="cancel-reason"
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  className="mt-1 block w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                >
                  {CANCELLATION_REASONS.map((r) => (
                    <option key={r.value} value={r.value}>
                      {r.label}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <Label htmlFor="cancel-feedback" className="text-sm text-gray-700">
                  Any additional feedback? (optional)
                </Label>
                <textarea
                  id="cancel-feedback"
                  value={feedback}
                  onChange={(e) => setFeedback(e.target.value)}
                  rows={3}
                  placeholder="Tell us how we could improve..."
                  className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm placeholder:text-gray-400 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                />
              </div>
            </div>

            <div className="mt-6 flex justify-end gap-3">
              <Button
                variant="outline"
                onClick={() => {
                  setShowCancelModal(false);
                  setReason("");
                  setFeedback("");
                }}
              >
                Never mind
              </Button>
              <Button
                className="bg-red-600 text-white hover:bg-red-700"
                onClick={() => cancelMutation.mutate()}
                disabled={cancelMutation.isPending}
              >
                {cancelMutation.isPending && (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                )}
                Cancel My Account
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
