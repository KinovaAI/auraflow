"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";
import { Calendar, BookOpen, CreditCard, User, LogOut, Menu, X, History, GraduationCap, UserCheck, Video, FileCheck, Bell, Settings, Gift } from "lucide-react";
import { useAuthStore } from "@/stores/auth-store";
import { Button } from "@/components/ui/button";

export function PortalHeader() {
  const pathname = usePathname();
  const router = useRouter();
  const { user, logout } = useAuthStore();
  const [mobileOpen, setMobileOpen] = useState(false);

  const navItems = [
    { href: "/portal", label: "Schedule", icon: Calendar },
    { href: "/portal/bookings", label: "My Bookings", icon: BookOpen },
    { href: "/portal/workshops", label: "Workshops", icon: GraduationCap },
    { href: "/portal/private-lessons", label: "Private Lessons", icon: UserCheck },
    ...(user?.has_video_access
      ? [{ href: "/portal/videos", label: "Videos", icon: Video }]
      : []),
    { href: "/portal/memberships", label: "Memberships", icon: CreditCard },
    { href: "/portal/gift-cards", label: "Gift Cards", icon: Gift },
    { href: "/portal/waiver", label: "Waiver", icon: FileCheck },
    { href: "/portal/history", label: "History", icon: History },
    { href: "/portal/notifications", label: "Notifications", icon: Bell },
    { href: "/portal/profile", label: "Profile", icon: User },
    { href: "/portal/settings", label: "Settings", icon: Settings },
  ];

  const handleLogout = async () => {
    await logout();
    router.push("/login");
  };

  const studioName = user?.organizations?.[0]?.name || "AuraFlow";
  const userName = user?.first_name || "Member";

  return (
    <header className="border-b bg-white">
      <div className="mx-auto flex max-w-4xl items-center justify-between px-4 py-3">
        {/* Logo / Studio Name */}
        <Link href="/portal">
          <Image src="/logo.png" alt={studioName} width={120} height={36} priority />
        </Link>

        {/* Desktop Nav */}
        <nav className="hidden items-center gap-1 md:flex">
          {navItems.map((item) => {
            const isActive =
              item.href === "/portal"
                ? pathname === "/portal"
                : pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`flex items-center gap-1.5 rounded-md px-3 py-2 text-sm font-medium transition-colors ${
                  isActive
                    ? "bg-indigo-50 text-indigo-700"
                    : "text-gray-600 hover:bg-gray-50 hover:text-gray-900"
                }`}
              >
                <item.icon className="h-4 w-4" />
                {item.label}
              </Link>
            );
          })}
        </nav>

        {/* Desktop User Menu */}
        <div className="hidden items-center gap-3 md:flex">
          <span className="text-sm text-gray-500">Hi, {userName}</span>
          <Button variant="ghost" size="sm" onClick={handleLogout}>
            <LogOut className="mr-1.5 h-4 w-4" />
            Sign out
          </Button>
        </div>

        {/* Mobile Menu Toggle */}
        <button
          className="rounded-md p-2 text-gray-600 hover:bg-gray-100 md:hidden"
          onClick={() => setMobileOpen(!mobileOpen)}
        >
          {mobileOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
        </button>
      </div>

      {/* Mobile Nav */}
      {mobileOpen && (
        <nav className="border-t px-4 py-2 md:hidden">
          {navItems.map((item) => {
            const isActive =
              item.href === "/portal"
                ? pathname === "/portal"
                : pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={() => setMobileOpen(false)}
                className={`flex items-center gap-2 rounded-md px-3 py-2.5 text-sm font-medium ${
                  isActive
                    ? "bg-indigo-50 text-indigo-700"
                    : "text-gray-600 hover:bg-gray-50"
                }`}
              >
                <item.icon className="h-4 w-4" />
                {item.label}
              </Link>
            );
          })}
          <button
            onClick={handleLogout}
            className="flex w-full items-center gap-2 rounded-md px-3 py-2.5 text-sm font-medium text-gray-600 hover:bg-gray-50"
          >
            <LogOut className="h-4 w-4" />
            Sign out
          </button>
        </nav>
      )}
    </header>
  );
}
