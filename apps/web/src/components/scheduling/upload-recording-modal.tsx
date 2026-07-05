"use client";

import { useState, useRef } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { X, Loader2, Upload, Film, CheckCircle, Youtube, ExternalLink } from "lucide-react";
import toast from "react-hot-toast";

import { Button } from "@/components/ui/button";
import { videoApi } from "@/lib/video-api";
import { sessionsApi, type Session } from "@/lib/scheduling-api";

type Destination = "mux" | "youtube";

interface UploadRecordingModalProps {
  session: Session;
  onClose: () => void;
  onUploaded: () => void;
}

export function UploadRecordingModal({
  session,
  onClose,
  onUploaded,
}: UploadRecordingModalProps) {
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [destination, setDestination] = useState<Destination>("mux");
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [done, setDone] = useState(false);

  const { data: connectionStatus } = useQuery({
    queryKey: ["video-connection-status"],
    queryFn: () => videoApi.getConnectionStatus().then((r) => r.data?.data),
  });

  const muxConnected = connectionStatus?.mux_connected ?? false;
  const youtubeConnected = connectionStatus?.youtube_connected ?? false;
  const youtubeUploadAuthorized = connectionStatus?.youtube_upload_authorized ?? false;

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selected = e.target.files?.[0];
    if (selected) {
      if (!selected.type.startsWith("video/")) {
        toast.error("Please select a video file");
        return;
      }
      setFile(selected);
    }
  };

  const handleAuthorizeYouTube = async () => {
    try {
      const res = await videoApi.getYouTubeOAuthUrl();
      window.location.href = res.data.data.oauth_url;
    } catch {
      toast.error("Failed to start YouTube authorization");
    }
  };

  const uploadToMux = async () => {
    if (!file) return;

    const origin = window.location.origin;
    const uploadRes = await videoApi.createMuxUpload(origin);
    const { upload_url } = uploadRes.data.data;

    const xhr = new XMLHttpRequest();
    await new Promise<void>((resolve, reject) => {
      xhr.upload.addEventListener("progress", (e) => {
        if (e.lengthComputable) {
          setProgress(Math.round((e.loaded / e.total) * 100));
        }
      });
      xhr.addEventListener("load", () => {
        if (xhr.status >= 200 && xhr.status < 300) resolve();
        else reject(new Error(`Upload failed with status ${xhr.status}`));
      });
      xhr.addEventListener("error", () => reject(new Error("Upload failed")));
      xhr.open("PUT", upload_url);
      xhr.setRequestHeader("Content-Type", file.type);
      xhr.send(file);
    });

    await videoApi.syncMux();
  };

  const uploadToYouTube = async () => {
    if (!file) return;

    // YouTube upload goes through our backend (which handles OAuth + resumable upload)
    // We use XHR for progress tracking
    const formData = new FormData();
    formData.append("file", file);
    formData.append("title", session.title);
    formData.append("description", `Recorded class: ${session.title}`);
    formData.append("privacy", "unlisted");

    const xhr = new XMLHttpRequest();
    await new Promise<void>((resolve, reject) => {
      xhr.upload.addEventListener("progress", (e) => {
        if (e.lengthComputable) {
          setProgress(Math.round((e.loaded / e.total) * 100));
        }
      });
      xhr.addEventListener("load", () => {
        if (xhr.status >= 200 && xhr.status < 300) resolve();
        else reject(new Error(`Upload failed with status ${xhr.status}`));
      });
      xhr.addEventListener("error", () => reject(new Error("Upload failed")));
      xhr.open("POST", "/api/v1/video/upload/youtube");
      // Let the browser add the auth header via cookie/interceptor
      const token = localStorage.getItem("access_token");
      if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);
      xhr.send(formData);
    });
  };

  const handleUpload = async () => {
    if (!file) return;
    setUploading(true);
    setProgress(0);

    try {
      if (destination === "mux") {
        await uploadToMux();
      } else {
        await uploadToYouTube();
      }

      await sessionsApi.update(session.id, {
        recording_status: "published",
      });

      queryClient.invalidateQueries({ queryKey: ["sessions"] });
      queryClient.invalidateQueries({ queryKey: ["videos"] });

      setDone(true);
      toast.success(
        destination === "mux"
          ? "Recording uploaded to Mux"
          : "Recording uploaded to YouTube"
      );
    } catch (err) {
      console.error("Upload error:", err);
      toast.error("Failed to upload recording");
    } finally {
      setUploading(false);
    }
  };

  const formatSize = (bytes: number) => {
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
    if (bytes < 1024 * 1024 * 1024)
      return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
  };

  const canUpload =
    file &&
    !uploading &&
    ((destination === "mux" && muxConnected) ||
      (destination === "youtube" && youtubeUploadAuthorized));

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="mx-4 w-full max-w-md rounded-lg bg-white shadow-xl">
        <div className="flex items-center justify-between border-b border-gray-200 px-6 py-4">
          <h2 className="text-lg font-semibold text-gray-900">
            Upload Recording
          </h2>
          <button
            onClick={onClose}
            className="rounded-md p-1 text-gray-400 hover:bg-gray-100"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="space-y-4 px-6 py-4">
          <p className="text-sm text-gray-500">
            Upload a recording of{" "}
            <strong>{session.title}</strong> to the on-demand video library.
          </p>

          {done ? (
            <div className="flex flex-col items-center gap-3 py-6">
              <CheckCircle className="h-12 w-12 text-emerald-500" />
              <p className="text-sm font-medium text-gray-900">
                Recording uploaded successfully
              </p>
              <p className="text-xs text-gray-500">
                {destination === "mux"
                  ? "It will appear in the Video Library after Mux finishes processing."
                  : "It will appear in the Video Library and on your YouTube channel."}
              </p>
            </div>
          ) : (
            <>
              {/* Destination picker */}
              <div>
                <label className="mb-1.5 block text-sm font-medium text-gray-700">
                  Upload to
                </label>
                <div className="flex gap-2">
                  {/* Mux option */}
                  <button
                    type="button"
                    onClick={() => setDestination("mux")}
                    disabled={!muxConnected || uploading}
                    className={`flex flex-1 items-center gap-2 rounded-lg border-2 p-3 text-left transition-colors ${
                      destination === "mux"
                        ? "border-emerald-500 bg-emerald-50"
                        : "border-gray-200 hover:border-gray-300"
                    } ${!muxConnected ? "cursor-not-allowed opacity-50" : ""}`}
                  >
                    <div className="rounded-md bg-pink-100 p-1.5">
                      <Film className="h-4 w-4 text-pink-600" />
                    </div>
                    <div>
                      <p className="text-sm font-medium text-gray-900">Mux</p>
                      <p className="text-xs text-gray-500">
                        {muxConnected ? "Stream via Mux" : "Not connected"}
                      </p>
                    </div>
                  </button>

                  {/* YouTube option */}
                  <button
                    type="button"
                    onClick={() => setDestination("youtube")}
                    disabled={!youtubeConnected || uploading}
                    className={`flex flex-1 items-center gap-2 rounded-lg border-2 p-3 text-left transition-colors ${
                      destination === "youtube"
                        ? "border-emerald-500 bg-emerald-50"
                        : "border-gray-200 hover:border-gray-300"
                    } ${!youtubeConnected ? "cursor-not-allowed opacity-50" : ""}`}
                  >
                    <div className="rounded-md bg-red-100 p-1.5">
                      <Youtube className="h-4 w-4 text-red-600" />
                    </div>
                    <div>
                      <p className="text-sm font-medium text-gray-900">
                        YouTube
                      </p>
                      <p className="text-xs text-gray-500">
                        {youtubeConnected
                          ? youtubeUploadAuthorized
                            ? "Upload to channel"
                            : "Needs authorization"
                          : "Not connected"}
                      </p>
                    </div>
                  </button>
                </div>
              </div>

              {/* YouTube auth prompt */}
              {destination === "youtube" &&
                youtubeConnected &&
                !youtubeUploadAuthorized && (
                  <div className="rounded-md border border-amber-200 bg-amber-50 p-3">
                    <p className="text-sm text-amber-800">
                      YouTube uploads require additional authorization. Click
                      below to authorize AuraFlow to upload to your channel.
                    </p>
                    <Button
                      size="sm"
                      variant="outline"
                      className="mt-2 border-amber-300 text-amber-700 hover:bg-amber-100"
                      onClick={handleAuthorizeYouTube}
                    >
                      <ExternalLink className="mr-1.5 h-3.5 w-3.5" />
                      Authorize YouTube Uploads
                    </Button>
                  </div>
                )}

              {/* File picker */}
              <div>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="video/*"
                  onChange={handleFileChange}
                  className="hidden"
                />
                {file ? (
                  <div className="flex items-center gap-3 rounded-md border border-gray-200 p-3">
                    <Film className="h-8 w-8 text-emerald-500" />
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium text-gray-900">
                        {file.name}
                      </p>
                      <p className="text-xs text-gray-500">
                        {formatSize(file.size)}
                      </p>
                    </div>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => {
                        setFile(null);
                        if (fileInputRef.current)
                          fileInputRef.current.value = "";
                      }}
                      disabled={uploading}
                    >
                      <X className="h-4 w-4" />
                    </Button>
                  </div>
                ) : (
                  <button
                    type="button"
                    onClick={() => fileInputRef.current?.click()}
                    className="flex w-full flex-col items-center gap-2 rounded-lg border-2 border-dashed border-gray-300 p-8 text-gray-500 transition-colors hover:border-emerald-400 hover:text-emerald-600"
                  >
                    <Upload className="h-8 w-8" />
                    <span className="text-sm font-medium">
                      Click to select video file
                    </span>
                    <span className="text-xs">
                      MP4, MOV, or other video formats
                    </span>
                  </button>
                )}
              </div>

              {/* Progress bar */}
              {uploading && (
                <div className="space-y-1">
                  <div className="flex justify-between text-xs text-gray-500">
                    <span>
                      Uploading to{" "}
                      {destination === "mux" ? "Mux" : "YouTube"}...
                    </span>
                    <span>{progress}%</span>
                  </div>
                  <div className="h-2 overflow-hidden rounded-full bg-gray-200">
                    <div
                      className="h-full rounded-full bg-emerald-500 transition-all duration-300"
                      style={{ width: `${progress}%` }}
                    />
                  </div>
                </div>
              )}
            </>
          )}
        </div>

        <div className="flex items-center justify-end gap-2 border-t border-gray-200 px-6 py-4">
          {done ? (
            <Button
              onClick={() => {
                onUploaded();
                onClose();
              }}
            >
              Done
            </Button>
          ) : (
            <>
              <Button variant="ghost" onClick={onClose} disabled={uploading}>
                Cancel
              </Button>
              <Button
                onClick={handleUpload}
                disabled={!canUpload}
                className="bg-emerald-600 hover:bg-emerald-700"
              >
                {uploading ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <Upload className="mr-2 h-4 w-4" />
                )}
                Upload to {destination === "mux" ? "Mux" : "YouTube"}
              </Button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
