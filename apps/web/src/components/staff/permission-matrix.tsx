"use client";

import { useMemo } from "react";
import { cn } from "@/lib/utils";

// Human-readable labels for the <area>.<verb> permission keys. Anything
// not in this map falls back to a title-cased verb. The matrix renders
// every key from the API's `allPermissions` list — no hardcoded key
// names here, so when the backend's ALL_PERMISSIONS catalog grows we
// don't need a UI change.

const AREA_LABELS: Record<string, string> = {
  ai: "AI Assistant",
  analytics: "Analytics & Reports",
  audit: "Audit Log",
  billing: "Billing & Subscription",
  communications: "Communications (Email / SMS / Social)",
  contracts: "Contracts",
  engagement: "Engagement Campaigns",
  facilities: "Facilities",
  gift_cards: "Gift Cards",
  import: "Import / Export",
  instructors: "Instructors",
  integrations: "Integrations",
  marketing: "Marketing Campaigns",
  members: "Members",
  memberships: "Memberships",
  office_management: "Office Manager",
  payments: "Payments",
  payroll: "Payroll & Time Clock",
  privacy: "Privacy / GDPR",
  private_sessions: "Private Sessions",
  retail: "Retail / POS",
  schedule: "Class Schedule",
  settings: "Organization Settings",
  staff: "Staff Management",
  studios: "Studios",
  video: "Video Library",
  voice: "Voice / Kiosk",
  waivers: "Waivers",
  workshops: "Workshops & Courses",
};

const AREA_ORDER = Object.keys(AREA_LABELS);

// Member-portal "own actions" — these belong to every member by
// definition (auto-granted on signup), not toggleable per-staff. Hide
// them from the matrix so the staff page isn't cluttered with keys the
// owner can't meaningfully modify.
const MEMBER_OWN_ACTION_SUFFIXES = [
  "_self",
  "_own",
  "_own_profile",
  "_own_bookings",
  "_own_reviews",
  "_own_enrollments",
  "_for_signing",
  "_reviewable",
  "_public",
  "manage_own",
  "view_own",
  "browse",
  "record_view",
  "sign",
  "view_deletion_status",
  "request_deletion",
  "cancel_deletion",
  "export_data",
  "manage_preferences",
];

function humanizeKey(key: string): string {
  const verb = key.split(".").slice(1).join(".");
  return verb
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function isMemberOwnAction(key: string): boolean {
  return MEMBER_OWN_ACTION_SUFFIXES.some((s) => key.endsWith(s));
}

interface Props {
  allPermissions: string[];          // full catalog from API
  permissions: string[];             // currently granted to this user
  onChange: (key: string, granted: boolean) => void;
  disabled?: boolean;
}

export function PermissionMatrix({
  allPermissions,
  permissions,
  onChange,
  disabled,
}: Props) {
  const grouped = useMemo(() => {
    const byArea: Record<string, string[]> = {};
    for (const key of allPermissions) {
      if (isMemberOwnAction(key)) continue; // hide member-portal keys
      const area = key.split(".")[0];
      (byArea[area] ||= []).push(key);
    }
    // Sort each area's keys alphabetically by verb
    for (const area of Object.keys(byArea)) {
      byArea[area].sort();
    }
    // Order areas by the AREA_ORDER list, then any unknown areas at the end
    const ordered: { area: string; label: string; keys: string[] }[] = [];
    const seen = new Set<string>();
    for (const a of AREA_ORDER) {
      if (byArea[a]) {
        ordered.push({ area: a, label: AREA_LABELS[a], keys: byArea[a] });
        seen.add(a);
      }
    }
    for (const a of Object.keys(byArea).sort()) {
      if (!seen.has(a)) {
        ordered.push({ area: a, label: a, keys: byArea[a] });
      }
    }
    return ordered;
  }, [allPermissions]);

  return (
    <div className="space-y-6">
      {grouped.map((group) => (
        <div key={group.area}>
          <h4 className="mb-3 text-sm font-semibold uppercase tracking-wider text-gray-500">
            {group.label}
          </h4>
          <div className="grid gap-2 sm:grid-cols-2">
            {group.keys.map((key) => {
              const isGranted = permissions.includes(key);
              return (
                <label
                  key={key}
                  className={cn(
                    "flex cursor-pointer items-center justify-between rounded-md border px-3 py-2 transition-colors",
                    isGranted
                      ? "border-indigo-200 bg-indigo-50"
                      : "border-gray-200 bg-white",
                    disabled && "cursor-not-allowed opacity-60"
                  )}
                  title={key}
                >
                  <div className="flex-1 min-w-0 mr-2">
                    <p className="truncate text-sm font-medium text-gray-900">
                      {humanizeKey(key)}
                    </p>
                    <p className="truncate text-xs text-gray-500">{key}</p>
                  </div>
                  <button
                    type="button"
                    role="switch"
                    aria-checked={isGranted}
                    disabled={disabled}
                    onClick={() => onChange(key, !isGranted)}
                    className={cn(
                      "relative inline-flex h-5 w-9 shrink-0 rounded-full border-2 border-transparent transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500",
                      isGranted ? "bg-indigo-600" : "bg-gray-200",
                      disabled && "cursor-not-allowed"
                    )}
                  >
                    <span
                      className={cn(
                        "pointer-events-none inline-block h-4 w-4 rounded-full bg-white shadow ring-0 transition-transform",
                        isGranted ? "translate-x-4" : "translate-x-0"
                      )}
                    />
                  </button>
                </label>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}
