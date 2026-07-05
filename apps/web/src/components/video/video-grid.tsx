"use client";

import type { Video } from "@/lib/video-api";
import { VideoCard } from "./video-card";

interface VideoGridProps {
  videos: Video[];
  onEdit?: (video: Video) => void;
  onDelete?: (video: Video) => void;
  onClick?: (video: Video) => void;
  showActions?: boolean;
}

export function VideoGrid({
  videos,
  onEdit,
  onDelete,
  onClick,
  showActions = true,
}: VideoGridProps) {
  if (videos.length === 0) {
    return null;
  }

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
      {videos.map((video) => (
        <VideoCard
          key={video.id}
          video={video}
          onEdit={onEdit}
          onDelete={onDelete}
          onClick={onClick}
          showActions={showActions}
        />
      ))}
    </div>
  );
}
