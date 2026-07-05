"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Loader2, Video, CreditCard } from "lucide-react";
import Link from "next/link";

import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { videoApi, type Video as VideoType } from "@/lib/video-api";
import { VideoGrid } from "@/components/video/video-grid";
import { VideoPlayer } from "@/components/video/video-player";
import { useAuthStore } from "@/stores/auth-store";

export default function PortalVideosPage() {
  const user = useAuthStore((s) => s.user);
  const hasAccess = !!user?.has_video_access;
  const [selectedCategoryId, setSelectedCategoryId] = useState("");
  const [playingVideo, setPlayingVideo] = useState<VideoType | null>(null);

  const { data: categories } = useQuery({
    queryKey: ["portal-video-categories"],
    queryFn: () => videoApi.listCategories().then((r) => r.data.data),
    enabled: hasAccess,
  });

  const { data: videos, isLoading } = useQuery({
    queryKey: ["portal-browse-videos", selectedCategoryId],
    queryFn: () =>
      videoApi
        .browseVideos({
          category_id: selectedCategoryId || undefined,
          limit: 200,
        })
        .then((r) => r.data.data),
    enabled: hasAccess,
  });

  // Member doesn't have video access — show upsell
  if (!hasAccess) {
    return (
      <div className="flex flex-col items-center justify-center py-20">
        <div className="rounded-full bg-indigo-50 p-4">
          <Video className="h-10 w-10 text-indigo-400" />
        </div>
        <h1 className="mt-4 text-xl font-semibold text-gray-900">
          On-Demand Videos
        </h1>
        <p className="mt-2 max-w-md text-center text-sm text-gray-500">
          Upgrade to an online or all-access membership to watch on-demand
          classes and recorded content.
        </p>
        <Link href="/portal/memberships">
          <Button className="mt-6">
            <CreditCard className="mr-2 h-4 w-4" />
            View Memberships
          </Button>
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">On-Demand Videos</h1>
        <p className="text-sm text-gray-500">
          Browse classes and recorded content available with your membership
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
