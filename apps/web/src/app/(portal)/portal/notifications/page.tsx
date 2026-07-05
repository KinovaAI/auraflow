"use client";

import { useEffect, useState, useCallback } from "react";
import {
  Bell,
  BellOff,
  CreditCard,
  CalendarCheck,
  IdCard,
  Info,
  Loader2,
  Trash2,
  CheckCheck,
} from "lucide-react";
import toast from "react-hot-toast";

import { notificationsApi } from "@/lib/notifications-api";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

interface Notification {
  id: string;
  type: string;
  title: string;
  message: string;
  is_read: boolean;
  created_at: string;
}

function formatRelativeTime(isoStr: string): string {
  const now = Date.now();
  const then = new Date(isoStr).getTime();
  const diffSeconds = Math.floor((now - then) / 1000);

  if (diffSeconds < 60) return "just now";
  const diffMinutes = Math.floor(diffSeconds / 60);
  if (diffMinutes < 60)
    return `${diffMinutes} minute${diffMinutes === 1 ? "" : "s"} ago`;
  const diffHours = Math.floor(diffMinutes / 60);
  if (diffHours < 24)
    return `${diffHours} hour${diffHours === 1 ? "" : "s"} ago`;
  const diffDays = Math.floor(diffHours / 24);
  if (diffDays < 30)
    return `${diffDays} day${diffDays === 1 ? "" : "s"} ago`;
  const diffMonths = Math.floor(diffDays / 30);
  if (diffMonths < 12)
    return `${diffMonths} month${diffMonths === 1 ? "" : "s"} ago`;
  const diffYears = Math.floor(diffMonths / 12);
  return `${diffYears} year${diffYears === 1 ? "" : "s"} ago`;
}

function notificationIcon(type: string) {
  switch (type) {
    case "payment":
      return <CreditCard className="h-5 w-5 text-green-600" />;
    case "booking":
      return <CalendarCheck className="h-5 w-5 text-blue-600" />;
    case "membership":
      return <IdCard className="h-5 w-5 text-purple-600" />;
    case "system":
    default:
      return <Info className="h-5 w-5 text-gray-500" />;
  }
}

function notificationIconBg(type: string) {
  switch (type) {
    case "payment":
      return "bg-green-50";
    case "booking":
      return "bg-blue-50";
    case "membership":
      return "bg-purple-50";
    case "system":
    default:
      return "bg-gray-100";
  }
}

export default function PortalNotificationsPage() {
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [markingAllRead, setMarkingAllRead] = useState(false);
  const [removingId, setRemovingId] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    try {
      const [listRes, countRes] = await Promise.all([
        notificationsApi.list(),
        notificationsApi.unreadCount(),
      ]);
      setNotifications(listRes.data?.data ?? listRes.data ?? []);
      setUnreadCount(countRes.data?.data?.count ?? 0);
    } catch {
      toast.error("Failed to load notifications");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleMarkRead = async (id: string) => {
    const n = notifications.find((n) => n.id === id);
    if (!n || n.is_read) return;

    try {
      await notificationsApi.markRead(id);
      setNotifications((prev) =>
        prev.map((n) => (n.id === id ? { ...n, is_read: true } : n))
      );
      setUnreadCount((c) => Math.max(0, c - 1));
    } catch {
      toast.error("Failed to mark notification as read");
    }
  };

  const handleMarkAllRead = async () => {
    setMarkingAllRead(true);
    try {
      await notificationsApi.markAllRead();
      setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })));
      setUnreadCount(0);
      toast.success("All notifications marked as read");
    } catch {
      toast.error("Failed to mark all as read");
    } finally {
      setMarkingAllRead(false);
    }
  };

  const handleRemove = async (id: string) => {
    setRemovingId(id);
    try {
      await notificationsApi.remove(id);
      const removed = notifications.find((n) => n.id === id);
      setNotifications((prev) => prev.filter((n) => n.id !== id));
      if (removed && !removed.is_read) {
        setUnreadCount((c) => Math.max(0, c - 1));
      }
    } catch {
      toast.error("Failed to delete notification");
    } finally {
      setRemovingId(null);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 className="h-6 w-6 animate-spin text-indigo-600" />
      </div>
    );
  }

  return (
    <div>
      {/* Header */}
      <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-bold text-gray-900">Notifications</h1>
          {unreadCount > 0 && (
            <span className="inline-flex items-center justify-center rounded-full bg-indigo-600 px-2.5 py-0.5 text-xs font-semibold text-white">
              {unreadCount} unread
            </span>
          )}
        </div>
        {unreadCount > 0 && (
          <Button
            variant="outline"
            size="sm"
            onClick={handleMarkAllRead}
            disabled={markingAllRead}
          >
            {markingAllRead ? (
              <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
            ) : (
              <CheckCheck className="mr-1.5 h-4 w-4" />
            )}
            Mark all as read
          </Button>
        )}
      </div>

      {/* Notification list */}
      {notifications.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center">
            <BellOff className="mx-auto mb-3 h-10 w-10 text-gray-300" />
            <p className="text-gray-500">No notifications yet</p>
            <p className="mt-1 text-sm text-gray-400">
              You&apos;ll see booking confirmations, payment receipts, and other
              updates here.
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-2">
          {notifications.map((notification) => (
            <Card
              key={notification.id}
              className={`cursor-pointer transition-colors hover:bg-gray-50 ${
                !notification.is_read ? "border-indigo-200 bg-indigo-50/30" : ""
              }`}
              onClick={() => handleMarkRead(notification.id)}
            >
              <CardContent className="flex items-start gap-3 p-4">
                {/* Icon */}
                <div
                  className={`mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-full ${notificationIconBg(
                    notification.type
                  )}`}
                >
                  {notificationIcon(notification.type)}
                </div>

                {/* Content */}
                <div className="min-w-0 flex-1">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        {!notification.is_read && (
                          <span className="h-2 w-2 shrink-0 rounded-full bg-indigo-600" />
                        )}
                        <h3
                          className={`text-sm ${
                            notification.is_read
                              ? "font-medium text-gray-700"
                              : "font-semibold text-gray-900"
                          }`}
                        >
                          {notification.title}
                        </h3>
                      </div>
                      <p className="mt-0.5 text-sm text-gray-500">
                        {notification.message}
                      </p>
                      <p className="mt-1 text-xs text-gray-400">
                        {formatRelativeTime(notification.created_at)}
                      </p>
                    </div>

                    {/* Delete button */}
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        handleRemove(notification.id);
                      }}
                      disabled={removingId === notification.id}
                      className="shrink-0 rounded-md p-1.5 text-gray-400 transition-colors hover:bg-red-50 hover:text-red-600"
                      aria-label="Delete notification"
                    >
                      {removingId === notification.id ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <Trash2 className="h-4 w-4" />
                      )}
                    </button>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
