"use client";

import { Play, Pencil, Trash2 } from "lucide-react";
import type { Video } from "@/lib/video-api";

interface VideoCardProps {
  video: Video;
  onEdit?: (video: Video) => void;
  onDelete?: (video: Video) => void;
  onClick?: (video: Video) => void;
  showActions?: boolean;
}

function formatDuration(seconds?: number): string {
  if (!seconds) return "";
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  if (h > 0) {
    return `${h}:${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
  }
  return `${m}:${s.toString().padStart(2, "0")}`;
}

export function VideoCard({
  video,
  onEdit,
  onDelete,
  onClick,
  showActions = true,
}: VideoCardProps) {
  const sourceBadgeClass =
    video.source === "youtube"
      ? "bg-red-100 text-red-700"
      : "bg-pink-100 text-pink-700";

  const visibilityBadgeClass =
    video.visibility === "public"
      ? "bg-green-50 text-green-700"
      : video.visibility === "members_only"
        ? "bg-blue-50 text-blue-700"
        : video.visibility === "specific_memberships"
          ? "bg-amber-50 text-amber-700"
          : "bg-gray-100 text-gray-600";

  return (
    <div className="group overflow-hidden rounded-lg border border-gray-200 bg-white shadow-sm transition-shadow hover:shadow-md">
      {/* Thumbnail */}
      <div
        className="relative aspect-video cursor-pointer bg-gray-100"
        onClick={() => onClick?.(video)}
      >
        {video.thumbnail_url ? (
          <img
            src={video.thumbnail_url}
            alt={video.title}
            className="h-full w-full object-cover"
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center bg-gray-200">
            <Play className="h-10 w-10 text-gray-400" />
          </div>
        )}

        {/* Play overlay */}
        <div className="absolute inset-0 flex items-center justify-center bg-black/0 transition-colors group-hover:bg-black/20">
          <div className="rounded-full bg-white/90 p-3 opacity-0 shadow-lg transition-opacity group-hover:opacity-100">
            <Play className="h-6 w-6 text-gray-900" fill="currentColor" />
          </div>
        </div>

        {/* Duration badge */}
        {video.duration_seconds ? (
          <span className="absolute bottom-2 right-2 rounded bg-black/75 px-1.5 py-0.5 text-xs font-medium text-white">
            {formatDuration(video.duration_seconds)}
          </span>
        ) : null}
      </div>

      {/* Info */}
      <div className="p-3">
        <h3
          className="line-clamp-2 cursor-pointer text-sm font-medium text-gray-900"
          title={video.title}
          onClick={() => onClick?.(video)}
        >
          {video.title}
        </h3>

        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          {/* Source badge */}
          <span
            className={`rounded-full px-2 py-0.5 text-xs font-medium ${sourceBadgeClass}`}
          >
            {video.source === "youtube" ? "YouTube" : "Mux"}
          </span>

          {/* Visibility badge */}
          <span
            className={`rounded-full px-2 py-0.5 text-xs font-medium ${visibilityBadgeClass}`}
          >
            {video.visibility.replace(/_/g, " ")}
          </span>

          {/* Category pill */}
          {video.category_name && (
            <span className="rounded-full bg-indigo-50 px-2 py-0.5 text-xs font-medium text-indigo-600">
              {video.category_name}
            </span>
          )}

          {/* Published indicator */}
          {!video.is_published && (
            <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-500">
              Draft
            </span>
          )}
        </div>

        {/* Action buttons */}
        {showActions && (onEdit || onDelete) && (
          <div className="mt-3 flex items-center gap-2 border-t border-gray-100 pt-2">
            {onEdit && (
              <button
                onClick={() => onEdit(video)}
                className="flex items-center gap-1 rounded-md px-2 py-1 text-xs text-gray-500 hover:bg-gray-100 hover:text-gray-700"
              >
                <Pencil className="h-3 w-3" />
                Edit
              </button>
            )}
            {onDelete && (
              <button
                onClick={() => onDelete(video)}
                className="flex items-center gap-1 rounded-md px-2 py-1 text-xs text-red-500 hover:bg-red-50 hover:text-red-700"
              >
                <Trash2 className="h-3 w-3" />
                Delete
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
