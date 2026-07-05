"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle2,
  Circle,
  Loader2,
  Sparkles,
  X,
  ChevronRight,
} from "lucide-react";
import toast from "react-hot-toast";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { onboardingApi } from "@/lib/onboarding-api";

interface ChecklistStep {
  step_key: string;
  title: string;
  is_completed: boolean;
}

const navigationMap: Record<string, string> = {
  create_studio: "/dashboard/settings/studio",
  add_location: "/dashboard/settings/locations",
  add_class_type: "/dashboard/schedule",
  create_schedule: "/dashboard/schedule",
  add_instructor: "/dashboard/instructors",
  invite_instructor: "/dashboard/instructors",
  add_member: "/dashboard/members",
  invite_member: "/dashboard/members",
  add_membership: "/dashboard/memberships",
  create_membership: "/dashboard/memberships",
  setup_payments: "/dashboard/settings/billing",
  configure_payments: "/dashboard/settings/billing",
  send_first_email: "/dashboard/marketing",
  customize_branding: "/dashboard/settings/studio",
  explore_ai: "/dashboard/ai",
  publish_portal: "/dashboard/settings/studio",
};

export function OnboardingChecklist() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [dismissed, setDismissed] = useState(() => {
    if (typeof window !== "undefined") {
      return localStorage.getItem("dismiss_onboarding") === "1";
    }
    return false;
  });

  const { data, isLoading } = useQuery({
    queryKey: ["onboarding-checklist"],
    queryFn: () => onboardingApi.checklist().then((r) => r.data),
    enabled: !dismissed,
  });

  const detectMutation = useMutation({
    mutationFn: () => onboardingApi.detect(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["onboarding-checklist"] });
      toast.success("Checklist updated based on current setup");
    },
    onError: () => toast.error("Failed to auto-detect progress"),
  });

  const steps: ChecklistStep[] = data?.data ?? [];
  const completedCount = steps.filter((s) => s.is_completed).length;
  const totalSteps = steps.length || 10;
  const progressPercent = Math.round((completedCount / totalSteps) * 100);

  if (dismissed) return null;

  // Hide if all steps complete
  if (steps.length > 0 && completedCount === totalSteps) return null;

  const handleDismiss = () => {
    setDismissed(true);
    localStorage.setItem("dismiss_onboarding", "1");
  };

  const handleStepClick = (step: ChecklistStep) => {
    if (step.is_completed) return;
    const path = navigationMap[step.step_key];
    if (path) {
      router.push(path);
    }
  };

  if (isLoading) {
    return (
      <Card>
        <CardContent className="flex items-center justify-center py-8">
          <Loader2 className="h-5 w-5 animate-spin text-indigo-600" />
        </CardContent>
      </Card>
    );
  }

  if (steps.length === 0) return null;

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Sparkles className="h-5 w-5 text-indigo-600" />
            <CardTitle className="text-base">Setup Checklist</CardTitle>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => detectMutation.mutate()}
              disabled={detectMutation.isPending}
              className="text-xs"
            >
              {detectMutation.isPending ? (
                <Loader2 className="mr-1 h-3 w-3 animate-spin" />
              ) : null}
              Auto-detect
            </Button>
            <button
              onClick={handleDismiss}
              className="rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
              aria-label="Dismiss checklist"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Progress bar */}
        <div>
          <div className="mb-1 flex items-center justify-between text-xs text-gray-500">
            <span>
              {completedCount} of {totalSteps} steps completed
            </span>
            <span>{progressPercent}%</span>
          </div>
          <div className="h-2 w-full overflow-hidden rounded-full bg-gray-100">
            <div
              className="h-full rounded-full bg-indigo-600 transition-all duration-300"
              style={{ width: `${progressPercent}%` }}
            />
          </div>
        </div>

        {/* Steps list */}
        <ul className="space-y-1">
          {steps.map((step) => (
            <li key={step.step_key}>
              <button
                onClick={() => handleStepClick(step)}
                disabled={step.is_completed}
                className={`flex w-full items-center gap-3 rounded-md px-3 py-2 text-left text-sm transition-colors ${
                  step.is_completed
                    ? "cursor-default text-gray-400"
                    : "text-gray-700 hover:bg-gray-50"
                }`}
              >
                {step.is_completed ? (
                  <CheckCircle2 className="h-4 w-4 flex-shrink-0 text-green-500" />
                ) : (
                  <Circle className="h-4 w-4 flex-shrink-0 text-gray-300" />
                )}
                <span
                  className={step.is_completed ? "line-through" : "font-medium"}
                >
                  {step.title}
                </span>
                {!step.is_completed && (
                  <ChevronRight className="ml-auto h-3 w-3 text-gray-300" />
                )}
              </button>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}
