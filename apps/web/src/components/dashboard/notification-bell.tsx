"use client";

import { useState, useRef, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Bell,
  Check,
  CheckCheck,
  Calendar,
  CreditCard,
  Users,
  Star,
  MessageSquare,
  AlertCircle,
  X,
} from "lucide-react";
import { notificationsApi } from "@/lib/notifications-api";

interface Notification {
  id: string;
  type: string;
  title: string;
  body: string;
  action_url?: string;
  is_read: boolean;
  created_at: string;
}

const typeIcons: Record<string, typeof Bell> = {
  booking: Calendar,
  waitlist: Calendar,
  payment: CreditCard,
  member: Users,
  membership: Users,
  milestone: Star,
  message: MessageSquare,
  alert: AlertCircle,
};

const typeColors: Record<string, string> = {
  booking: "text-blue-500",
  waitlist: "text-blue-500",
  payment: "text-green-500",
  member: "text-indigo-500",
  membership: "text-indigo-500",
  milestone: "text-pink-500",
  message: "text-purple-500",
  alert: "text-orange-500",
};

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d ago`;
  return new Date(dateStr).toLocaleDateString();
}

export function NotificationBell() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Poll unread count every 30 seconds
  const { data: countData } = useQuery({
    queryKey: ["notifications-unread-count"],
    queryFn: () => notificationsApi.unreadCount().then((r) => r.data),
    refetchInterval: 30000,
  });

  const unreadCount = countData?.data?.count ?? 0;

  // Fetch notification list when dropdown is open
  const { data: listData } = useQuery({
    queryKey: ["notifications-list"],
    queryFn: () => notificationsApi.list(50).then((r) => r.data),
    enabled: open,
  });

  const notifications: Notification[] = listData?.data ?? [];

  const markReadMutation = useMutation({
    mutationFn: (id: string) => notificationsApi.markRead(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["notifications-unread-count"] });
      queryClient.invalidateQueries({ queryKey: ["notifications-list"] });
    },
  });

  const markAllReadMutation = useMutation({
    mutationFn: () => notificationsApi.markAllRead(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["notifications-unread-count"] });
      queryClient.invalidateQueries({ queryKey: ["notifications-list"] });
    },
  });

  // Close on click outside
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    if (open) {
      document.addEventListener("mousedown", handleClickOutside);
    }
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [open]);

  const handleNotificationClick = (n: Notification) => {
    if (!n.is_read) {
      markReadMutation.mutate(n.id);
    }
    if (n.action_url) {
      router.push(n.action_url);
      setOpen(false);
    }
  };

  return (
    <div className="relative" ref={dropdownRef}>
      {/* Bell button */}
      <button
        onClick={() => setOpen((prev) => !prev)}
        className="relative rounded-md p-2 text-gray-500 hover:bg-gray-100 hover:text-gray-700"
        aria-label="Notifications"
      >
        <Bell className="h-5 w-5" />
        {unreadCount > 0 && (
          <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-[1rem] items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-bold text-white">
            {unreadCount > 99 ? "99+" : unreadCount}
          </span>
        )}
      </button>

      {/* Dropdown */}
      {open && (
        <div className="absolute right-0 top-full z-50 mt-2 w-80 overflow-hidden rounded-lg border border-gray-200 bg-white shadow-lg sm:w-96">
          {/* Header */}
          <div className="flex items-center justify-between border-b border-gray-100 px-4 py-3">
            <h3 className="text-sm font-semibold text-gray-900">Notifications</h3>
            <div className="flex items-center gap-2">
              {unreadCount > 0 && (
                <button
                  onClick={() => markAllReadMutation.mutate()}
                  disabled={markAllReadMutation.isPending}
                  className="flex items-center gap-1 rounded px-2 py-1 text-xs text-indigo-600 hover:bg-indigo-50"
                >
                  <CheckCheck className="h-3 w-3" />
                  Mark all read
                </button>
              )}
              <button
                onClick={() => setOpen(false)}
                className="rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          </div>

          {/* Notification list */}
          <div className="max-h-96 overflow-y-auto">
            {notifications.length === 0 ? (
              <div className="flex flex-col items-center py-8 text-gray-400">
                <Bell className="mb-2 h-8 w-8" />
                <p className="text-sm">No notifications yet</p>
              </div>
            ) : (
              notifications.map((n) => {
                const typePrefix = n.type.split(".")[0];
                const Icon = typeIcons[typePrefix] ?? Bell;
                const color = typeColors[typePrefix] ?? "text-gray-400";
                return (
                  <button
                    key={n.id}
                    onClick={() => handleNotificationClick(n)}
                    className={`flex w-full items-start gap-3 border-b border-gray-50 px-4 py-3 text-left transition-colors hover:bg-gray-50 ${
                      !n.is_read ? "bg-indigo-50/40" : ""
                    }`}
                  >
                    <div className={`mt-0.5 flex-shrink-0 ${color}`}>
                      <Icon className="h-4 w-4" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <p
                        className={`text-sm ${
                          n.is_read ? "text-gray-600" : "font-medium text-gray-900"
                        }`}
                      >
                        {n.title}
                      </p>
                      <p className="mt-0.5 truncate text-xs text-gray-400">
                        {n.body}
                      </p>
                      <p className="mt-1 text-xs text-gray-300">
                        {timeAgo(n.created_at)}
                      </p>
                    </div>
                    {!n.is_read && (
                      <div className="mt-1.5 flex-shrink-0">
                        <span className="block h-2 w-2 rounded-full bg-indigo-500" />
                      </div>
                    )}
                  </button>
                );
              })
            )}
          </div>
        </div>
      )}
    </div>
  );
}
