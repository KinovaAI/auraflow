"use client";

import { useQuery } from "@tanstack/react-query";
import {
  Calendar,
  CreditCard,
  LogIn,
  Award,
  Star,
  Loader2,
  AlertCircle,
} from "lucide-react";
import { activityApi } from "@/lib/activity-api";

interface ActivityEntry {
  id: string;
  action_type: string;
  description: string;
  created_at: string;
  metadata?: Record<string, unknown>;
}

interface ActivityTimelineProps {
  memberId: string;
}

const actionConfig: Record<
  string,
  { icon: typeof Calendar; color: string; bgColor: string }
> = {
  booking: {
    icon: Calendar,
    color: "text-blue-500",
    bgColor: "bg-blue-100",
  },
  payment: {
    icon: CreditCard,
    color: "text-green-500",
    bgColor: "bg-green-100",
  },
  checkin: {
    icon: LogIn,
    color: "text-purple-500",
    bgColor: "bg-purple-100",
  },
  membership: {
    icon: Award,
    color: "text-yellow-500",
    bgColor: "bg-yellow-100",
  },
  milestone: {
    icon: Star,
    color: "text-pink-500",
    bgColor: "bg-pink-100",
  },
};

const defaultConfig = {
  icon: Calendar,
  color: "text-gray-400",
  bgColor: "bg-gray-100",
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
  if (days < 30) return `${Math.floor(days / 7)}w ago`;
  return new Date(dateStr).toLocaleDateString();
}

export function ActivityTimeline({ memberId }: ActivityTimelineProps) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["member-activity", memberId],
    queryFn: () =>
      activityApi.memberTimeline(memberId, 50).then((r) => r.data),
    enabled: !!memberId,
  });

  const entries: ActivityEntry[] = data?.data ?? [];

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-6 w-6 animate-spin text-indigo-600" />
      </div>
    );
  }

  if (isError) {
    return (
      <div className="flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
        <AlertCircle className="h-4 w-4" />
        Failed to load activity timeline.
      </div>
    );
  }

  if (entries.length === 0) {
    return (
      <div className="py-8 text-center text-sm text-gray-400">
        No activity recorded yet.
      </div>
    );
  }

  return (
    <div className="relative">
      {/* Vertical line */}
      <div className="absolute left-4 top-0 h-full w-px bg-gray-200" />

      <div className="space-y-4">
        {entries.map((entry, idx) => {
          const config = actionConfig[entry.action_type] ?? defaultConfig;
          const Icon = config.icon;
          const isLast = idx === entries.length - 1;

          return (
            <div key={entry.id} className="relative flex items-start gap-3 pl-0">
              {/* Dot */}
              <div
                className={`relative z-10 flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full ${config.bgColor}`}
              >
                <Icon className={`h-4 w-4 ${config.color}`} />
              </div>

              {/* Content */}
              <div className={`flex-1 pb-4 ${isLast ? "" : ""}`}>
                <p className="text-sm text-gray-700">{entry.description}</p>
                <p className="mt-0.5 text-xs text-gray-400">
                  {timeAgo(entry.created_at)}
                </p>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
