"use client";

import { useEffect } from "react";
import Image from "next/image";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { X, LogOut, Shield } from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/stores/auth-store";
import { useStudioStore } from "@/stores/studio-store";
import { navigationGroups } from "./sidebar";

interface MobileSidebarProps {
  open: boolean;
  onClose: () => void;
}

export function MobileSidebar({ open, onClose }: MobileSidebarProps) {
  const pathname = usePathname();
  const router = useRouter();
  const user = useAuthStore((s) => s.user);
  const permissions = useAuthStore((s) => s.permissions);
  const isLoading = useAuthStore((s) => s.isLoading);
  const { logout } = useAuthStore();
  const getEffectivePermissions = useStudioStore((s) => s.getEffectivePermissions);

  const currentOrgRole = user?.active_org_role ?? user?.organizations?.[0]?.role;
  const isOwnerOrAdmin = currentOrgRole === "owner" || user?.is_platform_admin;
  const effectivePermissions = getEffectivePermissions(permissions);

  // Longest-prefix active link — same logic as desktop sidebar.
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

  // Close on Escape
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    if (open) document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [open, onClose]);

  // Prevent body scroll when open
  useEffect(() => {
    if (open) {
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "";
    }
    return () => { document.body.style.overflow = ""; };
  }, [open]);

  const handleLogout = async () => {
    onClose();
    await logout();
    router.push("/login");
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-40 md:hidden">
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/50"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Drawer */}
      <aside className="fixed inset-y-0 left-0 z-50 flex w-72 flex-col bg-white shadow-xl">
        {/* Header */}
        <div className="flex h-16 items-center justify-between border-b border-gray-200 px-4">
          <Link href="/dashboard" onClick={onClose}>
            <Image src="/dashboard-logo.png" alt="AuraFlow" width={200} height={200} className="h-[100px] w-auto" priority />
          </Link>
          <button
            onClick={onClose}
            className="rounded-md p-2 text-gray-500 hover:bg-gray-100"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Navigation */}
        <nav className="flex-1 overflow-y-auto px-3 py-4">
          <div>
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
                        onClick={onClose}
                        className={cn(
                          "flex items-center gap-3 rounded-md px-3 py-2.5 text-sm font-medium transition-colors",
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

          {/* Platform Admin */}
          {user?.is_platform_admin && (
            <div className="border-t border-gray-200 pt-3 mt-3">
              <Link
                href="/dashboard/platform"
                onClick={onClose}
                className={cn(
                  "flex items-center gap-3 rounded-md px-3 py-2.5 text-sm font-medium transition-colors",
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

        {/* Footer */}
        <div className="border-t border-gray-200 p-4">
          <div className="mb-3 text-sm text-gray-500">
            {user?.first_name} {user?.last_name}
          </div>
          <button
            onClick={handleLogout}
            className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm font-medium text-gray-600 hover:bg-gray-50"
          >
            <LogOut className="h-4 w-4" />
            Sign out
          </button>
        </div>
      </aside>
    </div>
  );
}
