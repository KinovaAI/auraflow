"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import toast from "react-hot-toast";
import { Loader2 } from "lucide-react";

import { useAuthStore } from "@/stores/auth-store";
import { organizationsApi } from "@/lib/organizations-api";
import { PricingTable } from "@/components/marketing/pricing-table";

export default function PlanSelectionPage() {
  const router = useRouter();
  const user = useAuthStore((s) => s.user);
  const [selecting, setSelecting] = useState(false);

  const orgSlug = user?.active_org_slug;

  const handleSelectPlan = async (planId: string) => {
    if (!orgSlug) {
      router.push("/dashboard");
      return;
    }

    setSelecting(true);
    try {
      await organizationsApi.update(orgSlug, { plan_id: planId });
      toast.success("Plan selected! Welcome to AuraFlow.");
      router.push("/dashboard");
    } catch {
      toast.error("Failed to set plan. You can change it later in Settings.");
      router.push("/dashboard");
    } finally {
      setSelecting(false);
    }
  };

  const handleSkip = () => {
    router.push("/dashboard");
  };

  if (selecting) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-50">
        <Loader2 className="h-8 w-8 animate-spin text-indigo-600" />
      </div>
    );
  }

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-gray-50 px-4 py-12">
      <div className="mb-12 text-center">
        <h1 className="text-3xl font-bold text-gray-900">
          Choose your plan
        </h1>
        <p className="mt-3 text-gray-600">
          Start with a 14-day free trial. No credit card required.
        </p>
      </div>

      <div className="w-full max-w-6xl">
        <PricingTable onSelectPlan={handleSelectPlan} />
      </div>

      <button
        onClick={handleSkip}
        className="mt-8 text-sm text-gray-500 hover:text-gray-700"
      >
        Continue with free trial →
      </button>
    </div>
  );
}
