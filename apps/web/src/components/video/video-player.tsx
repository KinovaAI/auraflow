"use client";

import { useEffect, useRef } from "react";
import { X } from "lucide-react";
import type { Video } from "@/lib/video-api";
import { videoApi } from "@/lib/video-api";

interface VideoPlayerProps {
  video: Video;
  onClose: () => void;
}

export function VideoPlayer({ video, onClose }: VideoPlayerProps) {
  const startTimeRef = useRef<number>(Date.now());

  useEffect(() => {
    // Record view on unmount
    return () => {
      const watchedSeconds = Math.round((Date.now() - startTimeRef.current) / 1000);
      videoApi.recordView(video.id, watchedSeconds, false).catch(() => {
        // Silently ignore view recording errors
      });
    };
  }, [video.id]);

  // Close on Escape
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80">
      <div className="relative mx-4 w-full max-w-4xl">
        {/* Close button */}
        <button
          onClick={onClose}
          className="absolute -top-10 right-0 rounded-md p-1 text-white/70 hover:text-white"
        >
          <X className="h-6 w-6" />
        </button>

        {/* Player */}
        <div className="aspect-video w-full overflow-hidden rounded-lg bg-black">
          {video.source === "youtube" && video.youtube_video_id ? (
            <iframe
              src={`https://www.youtube-nocookie.com/embed/${video.youtube_video_id}?autoplay=1&rel=0`}
              title={video.title}
              className="h-full w-full"
              allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
              allowFullScreen
            />
          ) : video.source === "mux" && video.mux_playback_id ? (
            <MuxPlayer playbackId={video.mux_playback_id} title={video.title} />
          ) : (
            <div className="flex h-full w-full items-center justify-center text-white/60">
              <p>Video unavailable</p>
            </div>
          )}
        </div>

        {/* Title bar */}
        <div className="mt-3 px-1">
          <h2 className="text-lg font-semibold text-white">{video.title}</h2>
          {video.description && (
            <p className="mt-1 text-sm text-white/70">{video.description}</p>
          )}
        </div>
      </div>
    </div>
  );
}

/**
 * Mux Player -- attempts dynamic import of @mux/mux-player-react.
 * Falls back to a native <video> tag with the HLS stream URL.
 */
function MuxPlayer({
  playbackId,
  title,
}: {
  playbackId: string;
  title: string;
}) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const hlsUrl = `https://stream.mux.com/${playbackId}.m3u8`;
  const posterUrl = `https://image.mux.com/${playbackId}/thumbnail.webp?time=0`;

  useEffect(() => {
    // Try to dynamically load HLS.js for browsers without native HLS support
    const video = videoRef.current;
    if (!video) return;

    if (video.canPlayType("application/vnd.apple.mpegurl")) {
      // Safari has native HLS support
      video.src = hlsUrl;
      return;
    }

    // For other browsers, try to load HLS.js dynamically
    let hlsInstance: { destroy: () => void } | null = null;

    import("hls.js")
      .then((HlsModule) => {
        const Hls = HlsModule.default;
        if (Hls.isSupported()) {
          hlsInstance = new Hls();
          (hlsInstance as InstanceType<typeof Hls>).loadSource(hlsUrl);
          (hlsInstance as InstanceType<typeof Hls>).attachMedia(video);
        } else {
          // Last resort: try direct assignment
          video.src = hlsUrl;
        }
      })
      .catch(() => {
        // HLS.js not available, try direct assignment
        video.src = hlsUrl;
      });

    return () => {
      if (hlsInstance) {
        hlsInstance.destroy();
      }
    };
  }, [hlsUrl]);

  return (
    <video
      ref={videoRef}
      className="h-full w-full"
      controls
      autoPlay
      poster={posterUrl}
      title={title}
    />
  );
}
