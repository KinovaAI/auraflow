"use client";

import { useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import {
  Mic,
  MicOff,
  Loader2,
  X,
  ArrowRight,
  AlertTriangle,
  User,
} from "lucide-react";
import { useMutation } from "@tanstack/react-query";
import toast from "react-hot-toast";
import { useMicrophone } from "@/hooks/use-microphone";
import { voiceApi, type VoiceCommandResult } from "@/lib/voice-api";

const NAV_TARGETS: Record<string, string> = {
  dashboard: "/dashboard",
  schedule: "/dashboard/schedule",
  members: "/dashboard/members",
  instructors: "/dashboard/instructors",
  staff: "/dashboard/staff",
  payments: "/dashboard/payments",
  billing: "/dashboard/payments",
  analytics: "/dashboard/analytics",
  settings: "/dashboard/settings",
  marketing: "/dashboard/marketing",
  ai: "/dashboard/ai",
  video: "/dashboard/video",
  memberships: "/dashboard/memberships",
  inventory: "/dashboard/inventory",
  pos: "/dashboard/pos",
  facilities: "/dashboard/facilities",
  "check-in": "/dashboard/check-in",
  checkin: "/dashboard/check-in",
};

type Phase = "idle" | "recording" | "processing" | "result";

export function VoiceCommandButton() {
  const router = useRouter();
  const { isRecording, startRecording, stopRecording, error: micError } = useMicrophone();
  const [phase, setPhase] = useState<Phase>("idle");
  const [result, setResult] = useState<VoiceCommandResult | null>(null);
  const [showPanel, setShowPanel] = useState(false);

  const commandMutation = useMutation({
    mutationFn: (audio: Blob) => voiceApi.command(audio).then((r) => r.data),
    onSuccess: (data) => {
      setResult(data);
      setPhase("result");

      // Auto-navigate on confident results
      if (data.action === "navigate" && data.target) {
        const path = NAV_TARGETS[data.target.toLowerCase()];
        if (path) {
          toast.success(`Navigating to ${data.target}`);
          router.push(path);
          setTimeout(() => {
            setShowPanel(false);
            setPhase("idle");
            setResult(null);
          }, 800);
          return;
        }
      }

      if (data.action === "open_member" && data.path) {
        const dashPath = `/dashboard${data.path}`;
        toast.success(`Opening ${data.member_resolved || "member"}`);
        router.push(dashPath);
        setTimeout(() => {
          setShowPanel(false);
          setPhase("idle");
          setResult(null);
        }, 800);
        return;
      }

      if (data.action === "search_member" && data.member_id) {
        const section = data.section || "profile";
        toast.success(`Found ${data.member_resolved || data.member_name}`);
        router.push(`/dashboard/members/${data.member_id}/${section}`);
        setTimeout(() => {
          setShowPanel(false);
          setPhase("idle");
          setResult(null);
        }, 800);
        return;
      }
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setResult({
        action: "error",
        transcript: "",
        message: detail || "Voice command failed",
      });
      setPhase("result");
    },
  });

  const handleStart = useCallback(async () => {
    setResult(null);
    setShowPanel(true);
    setPhase("recording");
    await startRecording();
  }, [startRecording]);

  const handleStop = useCallback(async () => {
    const blob = await stopRecording();
    if (blob && blob.size > 0) {
      setPhase("processing");
      commandMutation.mutate(blob);
    } else {
      setPhase("idle");
    }
  }, [stopRecording, commandMutation]);

  const handleClose = useCallback(() => {
    if (isRecording) {
      stopRecording();
    }
    setShowPanel(false);
    setPhase("idle");
    setResult(null);
  }, [isRecording, stopRecording]);

  // Floating button (visible when panel is closed)
  if (!showPanel) {
    return (
      <button
        onClick={handleStart}
        className="fixed bottom-6 right-6 z-40 flex h-14 w-14 items-center justify-center rounded-full bg-indigo-600 text-white shadow-lg transition-all hover:bg-indigo-700 hover:shadow-xl active:scale-95 focus:outline-none focus:ring-4 focus:ring-indigo-300"
        title="Voice command"
      >
        <Mic className="h-6 w-6" />
      </button>
    );
  }

  // Panel
  return (
    <div className="fixed bottom-6 right-6 z-40 w-80 rounded-2xl bg-white shadow-2xl border border-gray-200 overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between bg-indigo-600 px-4 py-3">
        <span className="text-sm font-semibold text-white">Voice Command</span>
        <button
          onClick={handleClose}
          className="rounded p-1 text-indigo-200 hover:bg-indigo-700 hover:text-white"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="p-4">
        {/* Recording state */}
        {phase === "recording" && (
          <div className="flex flex-col items-center py-4">
            <button
              onClick={handleStop}
              className="relative flex h-20 w-20 items-center justify-center rounded-full bg-red-500"
            >
              <span className="absolute inset-0 animate-ping rounded-full bg-red-400 opacity-30" />
              <MicOff className="relative h-8 w-8 text-white" />
            </button>
            <p className="mt-3 flex items-center gap-2 text-sm text-red-600">
              <span className="h-2 w-2 animate-pulse rounded-full bg-red-500" />
              Listening... tap to stop
            </p>
          </div>
        )}

        {/* Processing */}
        {phase === "processing" && (
          <div className="flex flex-col items-center py-6">
            <Loader2 className="h-10 w-10 animate-spin text-indigo-600" />
            <p className="mt-3 text-sm text-gray-500">Processing command...</p>
          </div>
        )}

        {/* Result */}
        {phase === "result" && result && (
          <div className="space-y-3">
            {result.transcript && (
              <div className="rounded-lg bg-gray-50 px-3 py-2">
                <p className="text-xs text-gray-400">You said:</p>
                <p className="text-sm text-gray-700">
                  &quot;{result.transcript}&quot;
                </p>
              </div>
            )}

            {result.action === "error" || result.action === "unknown" ? (
              <div className="flex items-start gap-2 rounded-lg bg-red-50 p-3">
                <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0 text-red-500" />
                <p className="text-sm text-red-700">
                  {result.message || "Could not understand the command"}
                </p>
              </div>
            ) : result.member_candidates && result.member_candidates.length > 0 ? (
              <div>
                <p className="text-xs text-gray-500 mb-2">
                  Multiple members found:
                </p>
                {result.member_candidates.map((c) => (
                  <button
                    key={c.id}
                    onClick={() => {
                      router.push(`/dashboard/members/${c.id}`);
                      handleClose();
                    }}
                    className="flex w-full items-center gap-2 rounded-lg border border-gray-200 px-3 py-2 text-left text-sm hover:bg-gray-50 mb-1"
                  >
                    <User className="h-4 w-4 text-gray-400" />
                    <span className="font-medium text-gray-700">{c.name}</span>
                    <ArrowRight className="ml-auto h-3 w-3 text-gray-300" />
                  </button>
                ))}
              </div>
            ) : (
              <div className="flex items-center gap-2 rounded-lg bg-green-50 p-3">
                <ArrowRight className="h-4 w-4 text-green-600" />
                <p className="text-sm text-green-700">
                  {result.description || "Navigating..."}
                </p>
              </div>
            )}

            <button
              onClick={handleStart}
              className="flex w-full items-center justify-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700"
            >
              <Mic className="h-4 w-4" />
              New Command
            </button>
          </div>
        )}

        {/* Idle (shouldn't normally show, but just in case) */}
        {phase === "idle" && (
          <div className="flex flex-col items-center py-4">
            <button
              onClick={handleStart}
              className="flex h-20 w-20 items-center justify-center rounded-full bg-indigo-600 text-white hover:bg-indigo-700 active:scale-95"
            >
              <Mic className="h-8 w-8" />
            </button>
            <p className="mt-3 text-xs text-gray-400">
              Tap to speak a command
            </p>
          </div>
        )}

        {/* Mic error */}
        {micError && (
          <p className="mt-2 text-xs text-red-500">{micError}</p>
        )}
      </div>
    </div>
  );
}
