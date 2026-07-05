"use client";

import { useEffect } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Server, HeartPulse } from "lucide-react";
import { useAuthStore } from "@/stores/auth-store";

// Open-core self-host: only infrastructure + system health. The commercial
// multi-tenant platform console (orgs/users/sales/ads/social/plans/etc.) is not
// part of the open build.
const NAV_ITEMS = [
  { href: "/dashboard/platform/infrastructure", label: "Infrastructure", icon: Server },
  { href: "/dashboard/platform/health", label: "System Health", icon: HeartPulse },
];

export default function PlatformAdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const { user } = useAuthStore();
  const router = useRouter();

  useEffect(() => {
    if (user && !user.is_platform_admin) {
      router.push("/dashboard");
    }
  }, [user, router]);

  // Don't render children until we confirm the user is a platform admin
  if (!user || !user.is_platform_admin) {
    return null;
  }

  return (
    <div className="flex gap-6">
      {/* Sidebar nav */}
      <nav className="hidden w-48 flex-shrink-0 lg:block">
        <div className="sticky top-24 max-h-[calc(100vh-8rem)] overflow-y-auto space-y-1">
          <h2 className="mb-3 px-3 text-xs font-bold uppercase tracking-wider text-gray-400">
            Platform Admin
          </h2>
          {NAV_ITEMS.map((item) => {
            const isActive = pathname === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm transition-colors ${
                  isActive
                    ? "bg-indigo-50 font-semibold text-indigo-700"
                    : "text-gray-600 hover:bg-gray-50 hover:text-gray-900"
                }`}
              >
                <item.icon
                  className={`h-4 w-4 ${isActive ? "text-indigo-600" : "text-gray-400"}`}
                />
                {item.label}
              </Link>
            );
          })}
        </div>
      </nav>

      {/* Main content */}
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  );
}
