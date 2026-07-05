"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Loader2, Video } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import { videoApi, type Video as VideoType } from "@/lib/video-api";
import { VideoGrid } from "@/components/video/video-grid";
import { VideoPlayer } from "@/components/video/video-player";

export default function BrowseVideosPage() {
  const [selectedCategoryId, setSelectedCategoryId] = useState("");
  const [playingVideo, setPlayingVideo] = useState<VideoType | null>(null);

  const { data: categories } = useQuery({
    queryKey: ["video-categories"],
    queryFn: () => videoApi.listCategories().then((r) => r.data.data),
  });

  const { data: videos, isLoading } = useQuery({
    queryKey: ["browse-videos", selectedCategoryId],
    queryFn: () =>
      videoApi
        .browseVideos({
          category_id: selectedCategoryId || undefined,
          limit: 200,
        })
        .then((r) => r.data.data),
  });

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">On-Demand Videos</h1>
        <p className="text-sm text-gray-500">
          Browse classes and recorded content available to you
        </p>
      </div>

      {/* Category filter pills */}
      {categories && categories.length > 0 && (
        <div className="flex flex-wrap gap-2">
          <button
            onClick={() => setSelectedCategoryId("")}
            className={`rounded-full px-3 py-1.5 text-sm font-medium transition-colors ${
              selectedCategoryId === ""
                ? "bg-indigo-600 text-white"
                : "bg-gray-100 text-gray-600 hover:bg-gray-200"
            }`}
          >
            All
          </button>
          {categories
            .filter((c) => c.is_active)
            .map((cat) => (
              <button
                key={cat.id}
                onClick={() => setSelectedCategoryId(cat.id)}
                className={`rounded-full px-3 py-1.5 text-sm font-medium transition-colors ${
                  selectedCategoryId === cat.id
                    ? "bg-indigo-600 text-white"
                    : "bg-gray-100 text-gray-600 hover:bg-gray-200"
                }`}
              >
                {cat.name}
                {cat.video_count > 0 && (
                  <span className="ml-1 text-xs opacity-70">
                    ({cat.video_count})
                  </span>
                )}
              </button>
            ))}
        </div>
      )}

      {/* Video grid */}
      {isLoading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="h-8 w-8 animate-spin text-indigo-600" />
        </div>
      ) : !videos?.length ? (
        <Card>
          <CardContent className="flex flex-col items-center py-16">
            <div className="rounded-full bg-indigo-50 p-4">
              <Video className="h-8 w-8 text-indigo-400" />
            </div>
            <h2 className="mt-4 text-lg font-medium text-gray-900">
              No videos available
            </h2>
            <p className="mt-1 max-w-sm text-center text-sm text-gray-500">
              {selectedCategoryId
                ? "No videos found in this category. Try selecting a different category."
                : "There are no videos available at this time. Check back later for new content."}
            </p>
          </CardContent>
        </Card>
      ) : (
        <VideoGrid
          videos={videos}
          onClick={(v) => setPlayingVideo(v)}
          showActions={false}
        />
      )}

      {/* Video player modal */}
      {playingVideo && (
        <VideoPlayer
          video={playingVideo}
          onClose={() => setPlayingVideo(null)}
        />
      )}
    </div>
  );
}
