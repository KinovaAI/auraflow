"use client";

import { useRouter } from "next/navigation";
import { LogOut, User, ChevronRight, Menu } from "lucide-react";
import { useAuthStore } from "@/stores/auth-store";
import { LocationSwitcher } from "@/components/dashboard/location-switcher";
import { NotificationBell } from "@/components/dashboard/notification-bell";
import { useStudioStore } from "@/stores/studio-store";

interface TopBarProps {
  onMenuClick?: () => void;
}

export function TopBar({ onMenuClick }: TopBarProps) {
  const router = useRouter();
  const { user, logout } = useAuthStore();
  const studios = useStudioStore((s) => s.studios);

  const handleLogout = async () => {
    await logout();
    router.push("/login");
  };

  const orgName =
    user?.organizations?.find((o) => o.slug === user.active_org_slug)?.name ??
    user?.organizations?.[0]?.name;

  return (
    <header className="flex h-16 items-center justify-between border-b border-gray-200 bg-white px-4 md:px-6">
      <div className="flex items-center gap-2 text-sm">
        {/* Hamburger — mobile only */}
        <button
          onClick={onMenuClick}
          className="rounded-md p-2 text-gray-600 hover:bg-gray-100 md:hidden"
        >
          <Menu className="h-5 w-5" />
        </button>

        <span className="hidden font-medium text-gray-700 sm:inline">{orgName}</span>
        {studios.length > 0 && (
          <span className="hidden items-center gap-2 sm:flex">
            <ChevronRight className="h-3.5 w-3.5 text-gray-400" />
            <LocationSwitcher />
          </span>
        )}
      </div>
      <div className="flex items-center gap-4">
        <NotificationBell />
        <div className="flex items-center gap-2 text-sm text-gray-600">
          <User className="h-4 w-4" />
          <span className="hidden sm:inline">
            {user?.first_name} {user?.last_name}
          </span>
        </div>
        <button
          onClick={handleLogout}
          className="flex items-center gap-1 rounded-md px-3 py-1.5 text-sm text-gray-500 hover:bg-gray-100 hover:text-gray-700"
        >
          <LogOut className="h-4 w-4" />
          <span className="hidden sm:inline">Sign out</span>
        </button>
      </div>
    </header>
  );
}
