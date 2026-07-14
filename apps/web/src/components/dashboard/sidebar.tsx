"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Calendar,
  Users,
  Users2,
  UserCheck,
  UserRound,
  BookOpen,
  IdCard,
  Mail,
  CreditCard,
  Clock,
  ShoppingCart,
  Package,
  Building2,
  Video,
  Sparkles,
  BarChart3,
  Upload,
  Plug,
  Settings,
  Shield,
  Mic,
  Inbox,
  Banknote,
  Calculator,
  UserPlus,
  Briefcase,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/stores/auth-store";
import { useStudioStore } from "@/stores/studio-store";
import type { LucideIcon } from "lucide-react";

interface NavItem {
  name: string;
  href: string;
  icon: LucideIcon;
  // Item is visible if the user holds ANY of these action-level keys
  // (OR semantics). Sourced from app.services.permissions.ALL_PERMISSIONS.
  permissionKeys: string[];
}

interface NavGroup {
  label: string;
  items: NavItem[];
}

export const navigationGroups: NavGroup[] = [
  {
    label: "OPERATIONS",
    items: [
      { name: "Dashboard", href: "/dashboard", icon: LayoutDashboard, permissionKeys: ["analytics.view_dashboard"] },
      { name: "Check-In", href: "/dashboard/check-in", icon: Mic, permissionKeys: ["schedule.check_in", "voice.handle_voice_checkin"] },
      { name: "Schedule", href: "/dashboard/schedule", icon: Calendar, permissionKeys: ["schedule.view_public", "schedule.create_admin_booking", "schedule.edit_session", "schedule.create_session"] },
    ],
  },
  {
    label: "CLASSES & CONTENT",
    items: [
      { name: "Private Sessions", href: "/dashboard/private-sessions", icon: UserRound, permissionKeys: ["private_sessions.book", "private_sessions.create_service", "private_sessions.set_availability"] },
      { name: "Workshops", href: "/dashboard/courses", icon: BookOpen, permissionKeys: ["workshops.view_attendance", "workshops.view_enrollments", "workshops.create", "workshops.edit"] },
      { name: "Video", href: "/dashboard/video", icon: Video, permissionKeys: ["video.view_library", "video.browse"] },
    ],
  },
  {
    label: "PEOPLE",
    items: [
      { name: "Members", href: "/dashboard/members", icon: Users, permissionKeys: ["members.view", "members.view_all"] },
      { name: "Instructors", href: "/dashboard/instructors", icon: UserCheck, permissionKeys: ["instructors.view_schedule", "instructors.edit", "instructors.manage_availability"] },
      { name: "Staff", href: "/dashboard/staff", icon: Users2, permissionKeys: ["staff.view"] },
      { name: "Guest Instructors", href: "/dashboard/staff/guest-instructors", icon: UserPlus, permissionKeys: ["instructors.view_guest", "instructors.edit_guest"] },
      { name: "Hiring", href: "/dashboard/hiring", icon: Briefcase, permissionKeys: ["hiring.view"] },
    ],
  },
  {
    label: "BUSINESS",
    items: [
      { name: "Memberships", href: "/dashboard/memberships", icon: IdCard, permissionKeys: ["memberships.view_active", "memberships.view_templates", "memberships.assign"] },
      { name: "Payments", href: "/dashboard/payments", icon: CreditCard, permissionKeys: ["payments.view_transactions", "payments.view_log", "payments.view_revenue"] },
      { name: "Point of Sale", href: "/dashboard/pos", icon: ShoppingCart, permissionKeys: ["retail.checkout_transaction", "retail.view_products"] },
      { name: "Inventory", href: "/dashboard/inventory", icon: Package, permissionKeys: ["retail.view_inventory", "retail.adjust_inventory"] },
      { name: "Payroll", href: "/dashboard/payroll", icon: Banknote, permissionKeys: ["payroll.view_runs", "payroll.view_timesheets", "payroll.view_own_timesheet", "payroll.view_report"] },
      { name: "Accounting", href: "/dashboard/accounting", icon: Calculator, permissionKeys: ["accounting.view"] },
    ],
  },
  {
    label: "INSIGHTS",
    items: [
      { name: "Analytics", href: "/dashboard/analytics", icon: BarChart3, permissionKeys: ["analytics.view_dashboard", "analytics.view_revenue", "analytics.view_members", "analytics.view_memberships"] },
      { name: "AI Assistant", href: "/dashboard/ai", icon: Sparkles, permissionKeys: ["ai.view_draft", "ai.view_retention", "ai.view_resolutions", "ai.view_member_insight", "ai.view_reviews", "ai.view_pricing", "ai.view_waitlist"] },
    ],
  },
  {
    label: "STUDIO",
    items: [
      { name: "Email", href: "/dashboard/email", icon: Inbox, permissionKeys: ["communications.view_inbox", "communications.manage_inbox"] },
      { name: "Marketing", href: "/dashboard/marketing", icon: Mail, permissionKeys: ["marketing.view_campaigns", "marketing.view_sms", "marketing.view_sms_campaigns", "marketing.view_ads"] },
      { name: "Facilities", href: "/dashboard/facilities", icon: Building2, permissionKeys: ["facilities.view_schedules", "facilities.view_equipment", "facilities.view_maintenance"] },
      { name: "Time Clock", href: "/dashboard/time-clock", icon: Clock, permissionKeys: ["payroll.clock_in", "payroll.view_clock_status", "payroll.view_own_timesheet"] },
      { name: "Settings", href: "/dashboard/settings", icon: Settings, permissionKeys: ["settings.view_features", "settings.edit_organization", "settings.view_webhooks"] },
    ],
  },
];

export const navigation = navigationGroups.flatMap((g) => g.items);

export function Sidebar() {
  const pathname = usePathname();
  const user = useAuthStore((s) => s.user);
  const permissions = useAuthStore((s) => s.permissions);
  const isLoading = useAuthStore((s) => s.isLoading);

  const getEffectivePermissions = useStudioStore((s) => s.getEffectivePermissions);

  const currentOrgRole = user?.active_org_role ?? user?.organizations?.[0]?.role;
  const isOwnerOrAdmin = currentOrgRole === "owner" || user?.is_platform_admin;

  // Apply studio-role filtering: intersect org permissions with studio role defaults
  const effectivePermissions = getEffectivePermissions(permissions);

  // Members use the member portal, not the staff dashboard.
  // Show all items while loading or for owners/admins. Filter for other staff roles.
  // Pick the single longest sidebar href that matches the current pathname.
  // Without this, /dashboard/staff/guest-instructors would highlight BOTH
  // 'Staff' (/dashboard/staff) and 'Guest Instructors' because the prefix
  // check matches the parent too.
  const allHrefs = navigationGroups.flatMap((g) => g.items.map((i) => i.href));
  const activeHref = allHrefs
    .filter((h) => h === pathname || (h !== "/dashboard" && pathname.startsWith(h + "/")))
    .reduce<string | null>((best, h) => (best && best.length >= h.length ? best : h), null);

  const visibleGroups = navigationGroups.map((group) => ({
    ...group,
    items: (!user || isLoading || isOwnerOrAdmin)
      ? group.items
      : currentOrgRole === "member"
        ? []
        : group.items.filter((item) =>
            item.permissionKeys.some((k) => effectivePermissions.includes(k)),
          ),
  })).filter((group) => group.items.length > 0);

  return (
    <aside className="hidden md:flex h-full w-64 flex-col border-r border-gray-200 bg-white">
      <div className="flex items-center px-6 py-2">
        <Link href="/dashboard">
          <Image src="/dashboard-logo.png" alt="AuraFlow" width={200} height={200} className="h-[100px] w-auto" priority />
        </Link>
      </div>
      <nav className="flex-1 flex flex-col px-3 py-4 overflow-y-auto">
        <div className="flex-1">
          {visibleGroups.map((group, groupIndex) => (
            <div key={group.label}>
              <div
                className={cn(
                  "text-xs font-semibold uppercase tracking-wider text-gray-400 px-3 mb-1",
                  groupIndex === 0 ? "" : "mt-4"
                )}
              >
                {group.label}
              </div>
              <div className="space-y-1">
                {group.items.map((item) => {
                  const isActive = item.href === activeHref;
                  return (
                    <Link
                      key={item.name}
                      href={item.href}
                      className={cn(
                        "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                        isActive
                          ? "bg-indigo-50 text-indigo-700"
                          : "text-gray-600 hover:bg-gray-50 hover:text-gray-900"
                      )}
                    >
                      <item.icon className="h-5 w-5" />
                      {item.name}
                    </Link>
                  );
                })}
              </div>
            </div>
          ))}
        </div>

        {/* Admin Section — only visible to platform admins */}
        {user?.is_platform_admin && (
          <div className="border-t border-gray-200 pt-3 mt-3">
            <Link
              href="/dashboard/platform"
              className={cn(
                "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                pathname.startsWith("/dashboard/platform")
                  ? "bg-indigo-50 text-indigo-700"
                  : "text-gray-600 hover:bg-gray-50 hover:text-gray-900"
              )}
            >
              <Shield className="h-5 w-5" />
              Platform Admin
            </Link>
          </div>
        )}
      </nav>
    </aside>
  );
}
