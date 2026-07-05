"use client";

import Link from "next/link";
import { AlertTriangle, XCircle } from "lucide-react";
import { useAuth } from "@/hooks/use-auth";

export function TrialExpirationBanner() {
  const { user } = useAuth();

  if (!user || user.organizations.length === 0) return null;

  // Find the active org (first one or the one matching active_org_slug)
  const activeOrg = user.active_org_slug
    ? user.organizations.find((o) => o.slug === user.active_org_slug)
    : user.organizations[0];

  if (!activeOrg) return null;

  const isExpired = activeOrg.status === "trial_expired";
  const isTrial = activeOrg.status === "trial";

  if (!isExpired && !isTrial) return null;

  // For active trials, check if < 5 days remaining
  let daysRemaining: number | null = null;
  if (isTrial && activeOrg.trial_ends_at) {
    const trialEnd = new Date(activeOrg.trial_ends_at);
    const now = new Date();
    daysRemaining = Math.ceil(
      (trialEnd.getTime() - now.getTime()) / (1000 * 60 * 60 * 24)
    );

    // Only show banner if 5 or fewer days remaining
    if (daysRemaining > 5) return null;
  } else if (isTrial) {
    // No trial_ends_at data available, don't show banner for active trials
    return null;
  }

  if (isExpired) {
    return (
      <div className="flex items-center gap-3 bg-red-50 px-4 py-2.5 text-sm text-red-800 border-b border-red-200">
        <XCircle className="h-4 w-4 flex-shrink-0" />
        <span>
          Your trial has expired. Upgrade to a paid plan to continue using
          AuraFlow.
        </span>
        <Link
          href="/dashboard/settings/billing"
          className="ml-auto whitespace-nowrap rounded-md bg-red-600 px-3 py-1 text-xs font-medium text-white hover:bg-red-700"
        >
          Upgrade Now
        </Link>
      </div>
    );
  }

  // Trial ending soon (daysRemaining <= 5)
  return (
    <div className="flex items-center gap-3 bg-yellow-50 px-4 py-2.5 text-sm text-yellow-800 border-b border-yellow-200">
      <AlertTriangle className="h-4 w-4 flex-shrink-0" />
      <span>
        Your trial expires in{" "}
        <strong>
          {daysRemaining} day{daysRemaining !== 1 ? "s" : ""}
        </strong>
        . Upgrade now to keep your studio running.
      </span>
      <Link
        href="/dashboard/settings/billing"
        className="ml-auto whitespace-nowrap rounded-md bg-yellow-600 px-3 py-1 text-xs font-medium text-white hover:bg-yellow-700"
      >
        Upgrade Now
      </Link>
    </div>
  );
}
