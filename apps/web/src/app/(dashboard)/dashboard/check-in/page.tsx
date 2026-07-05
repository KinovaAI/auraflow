"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import { useMutation } from "@tanstack/react-query";
import { format } from "date-fns";
import {
  Mic,
  MicOff,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  User,
  Clock,
  Loader2,
  RotateCcw,
  Calendar,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { useMicrophone } from "@/hooks/use-microphone";
import { voiceApi, type VoiceCheckinResult } from "@/lib/voice-api";

type Phase = "idle" | "recording" | "processing" | "result";

// Check if browser supports SpeechRecognition
const SpeechRecognition =
  typeof window !== "undefined"
    ? (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
    : null;

export default function VoiceCheckinPage() {
  const { isRecording, startRecording, stopRecording, error: micError, duration } = useMicrophone();
  const [phase, setPhase] = useState<Phase>("idle");
  const [result, setResult] = useState<VoiceCheckinResult | null>(null);
  const [liveTranscript, setLiveTranscript] = useState("");
  const recognitionRef = useRef<any>(null);

  // Text-based check-in mutation (uses browser speech recognition → backend text matching)
  const textCheckinMutation = useMutation({
    mutationFn: (transcript: string) => voiceApi.checkinText(transcript).then((r) => r.data),
    onSuccess: (data) => {
      setResult(data);
      setPhase("result");
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setResult({
        status: "no_match",
        transcript: "",
        message: detail || "Check-in failed. Please try again.",
      });
      setPhase("result");
    },
  });

  // Audio-based check-in mutation (fallback to OpenAI Whisper)
  const checkinMutation = useMutation({
    mutationFn: (audio: Blob) => voiceApi.checkin(audio).then((r) => r.data),
    onSuccess: (data) => {
      setResult(data);
      setPhase("result");
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setResult({
        status: "no_match",
        transcript: "",
        message: detail || "Check-in failed. Please try again.",
      });
      setPhase("result");
    },
  });

  const useBrowserSpeech = !!SpeechRecognition;

  const handlePushStart = useCallback(async () => {
    setResult(null);
    setLiveTranscript("");
    setPhase("recording");

    if (useBrowserSpeech) {
      // Use browser SpeechRecognition (free, no rate limits)
      const recognition = new SpeechRecognition();
      recognition.lang = "en-US";
      recognition.interimResults = true;
      recognition.maxAlternatives = 1;

      recognition.onresult = (event: any) => {
        let transcript = "";
        for (let i = 0; i < event.results.length; i++) {
          transcript += event.results[i][0].transcript;
        }
        setLiveTranscript(transcript);
      };

      recognition.onerror = (event: any) => {
        if (event.error !== "aborted") {
          setResult({
            status: "no_match",
            transcript: "",
            message: `Speech recognition error: ${event.error}`,
          });
          setPhase("result");
        }
      };

      recognitionRef.current = recognition;
      recognition.start();
    } else {
      // Fallback to microphone recording → OpenAI Whisper
      await startRecording();
    }
  }, [startRecording, useBrowserSpeech]);

  const handlePushEnd = useCallback(async () => {
    if (useBrowserSpeech) {
      // Stop browser speech recognition and process the transcript
      if (recognitionRef.current) {
        recognitionRef.current.stop();
        recognitionRef.current = null;
      }
      if (liveTranscript.trim()) {
        setPhase("processing");
        textCheckinMutation.mutate(liveTranscript.trim());
      } else {
        setPhase("idle");
      }
    } else {
      // Stop recording and send audio to API
      const blob = await stopRecording();
      if (blob && blob.size > 0) {
        setPhase("processing");
        checkinMutation.mutate(blob);
      } else {
        setPhase("idle");
      }
    }
  }, [stopRecording, checkinMutation, textCheckinMutation, useBrowserSpeech, liveTranscript]);

  const handleReset = useCallback(() => {
    setPhase("idle");
    setResult(null);
  }, []);

  // Auto-reset after any result
  useEffect(() => {
    if (phase === "result") {
      const delay = result?.status === "checked_in" ? 4000 : 5000;
      const timer = setTimeout(handleReset, delay);
      return () => clearTimeout(timer);
    }
  }, [phase, result, handleReset]);

  const formatDuration = (s: number) => {
    const mins = Math.floor(s / 60);
    const secs = s % 60;
    return `${mins}:${secs.toString().padStart(2, "0")}`;
  };

  return (
    <div className="flex min-h-[calc(100vh-8rem)] flex-col items-center justify-center">
      <div className="w-full max-w-lg text-center">
        {/* Header */}
        <h1 className="text-3xl font-bold text-gray-900">Voice Check-In</h1>
        <p className="mt-2 text-gray-500">
          Press and hold the button, then say your name
        </p>

        {/* Main Button Area */}
        <div className="mt-10 flex flex-col items-center">
          {phase === "idle" && (
            <button
              onMouseDown={handlePushStart}
              onMouseUp={handlePushEnd}
              onTouchStart={(e) => {
                e.preventDefault();
                handlePushStart();
              }}
              onTouchEnd={(e) => {
                e.preventDefault();
                handlePushEnd();
              }}
              className="group flex h-40 w-40 items-center justify-center rounded-full bg-indigo-600 shadow-lg transition-all hover:bg-indigo-700 hover:shadow-xl active:scale-95 active:bg-indigo-800 focus:outline-none focus:ring-4 focus:ring-indigo-300"
            >
              <Mic className="h-16 w-16 text-white transition-transform group-active:scale-110" />
            </button>
          )}

          {phase === "recording" && (
            <button
              onMouseUp={handlePushEnd}
              onTouchEnd={(e) => {
                e.preventDefault();
                handlePushEnd();
              }}
              className="relative flex h-40 w-40 items-center justify-center rounded-full bg-red-500 shadow-lg"
            >
              {/* Pulsing ring */}
              <span className="absolute inset-0 animate-ping rounded-full bg-red-400 opacity-30" />
              <span className="absolute inset-2 animate-pulse rounded-full bg-red-400 opacity-20" />
              <MicOff className="relative h-16 w-16 text-white" />
            </button>
          )}

          {phase === "processing" && (
            <div className="flex h-40 w-40 items-center justify-center rounded-full bg-gray-100">
              <Loader2 className="h-16 w-16 animate-spin text-indigo-600" />
            </div>
          )}

          {phase === "result" && result && (
            <ResultDisplay result={result} onReset={handleReset} />
          )}

          {/* Recording indicator */}
          {phase === "recording" && (
            <div className="mt-6 space-y-2 text-center">
              <div className="flex items-center justify-center gap-2 text-red-600">
                <span className="h-3 w-3 animate-pulse rounded-full bg-red-500" />
                <span className="text-lg font-semibold">
                  Listening... {formatDuration(duration)}
                </span>
              </div>
              {liveTranscript && (
                <p className="text-lg font-medium text-gray-700">
                  &ldquo;{liveTranscript}&rdquo;
                </p>
              )}
            </div>
          )}

          {phase === "processing" && (
            <p className="mt-6 text-lg font-medium text-gray-500">
              Processing...
            </p>
          )}

          {phase === "idle" && (
            <p className="mt-6 text-sm text-gray-400">
              Hold to record &middot; Release to check in
            </p>
          )}
        </div>

        {/* Mic Error */}
        {micError && (
          <div className="mt-6 rounded-lg bg-red-50 p-4 text-sm text-red-600">
            <AlertTriangle className="mr-1 inline h-4 w-4" />
            {micError}
          </div>
        )}
      </div>
    </div>
  );
}

/* ── Result Display ─────────────────────────────────────────────────── */

function ResultDisplay({
  result,
  onReset,
}: {
  result: VoiceCheckinResult;
  onReset: () => void;
}) {
  if (result.status === "checked_in") {
    return (
      <div className="w-full">
        <div className="flex h-40 w-40 mx-auto items-center justify-center rounded-full bg-green-100">
          <CheckCircle2 className="h-20 w-20 text-green-600" />
        </div>
        <div className="mt-6 rounded-xl bg-green-50 border border-green-200 p-6">
          <p className="text-2xl font-bold text-green-800">
            Welcome, {result.member?.name}!
          </p>
          {result.booking && (
            <div className="mt-3 flex items-center justify-center gap-2 text-green-700">
              <Calendar className="h-5 w-5" />
              <span className="text-lg">{result.booking.class_title}</span>
              {result.booking.starts_at && (
                <>
                  <span className="text-green-400">&middot;</span>
                  <Clock className="h-4 w-4" />
                  <span>
                    {format(new Date(result.booking.starts_at), "h:mm a")}
                  </span>
                </>
              )}
            </div>
          )}
          <p className="mt-2 text-sm text-green-600">
            You&apos;re all checked in
          </p>
        </div>
        <p className="mt-4 text-xs text-gray-400">
          Resetting in a few seconds...
        </p>
        <Button onClick={onReset} variant="outline" className="mt-3" size="lg">
          <RotateCcw className="mr-2 h-5 w-5" />
          Ready for Next
        </Button>
      </div>
    );
  }

  if (result.status === "no_booking") {
    return (
      <div className="w-full">
        <div className="flex h-40 w-40 mx-auto items-center justify-center rounded-full bg-yellow-100">
          <AlertTriangle className="h-20 w-20 text-yellow-600" />
        </div>
        <div className="mt-6 rounded-xl bg-yellow-50 border border-yellow-200 p-6">
          <p className="text-xl font-bold text-yellow-800">
            {result.member?.name}
          </p>
          <p className="mt-2 text-yellow-700">
            {result.message || "No booking found for today"}
          </p>
        </div>
        <Button onClick={onReset} className="mt-6" size="lg">
          <RotateCcw className="mr-2 h-5 w-5" />
          Try Again
        </Button>
      </div>
    );
  }

  if (result.status === "ambiguous" && result.candidates) {
    return (
      <div className="w-full">
        <div className="flex h-40 w-40 mx-auto items-center justify-center rounded-full bg-blue-100">
          <User className="h-20 w-20 text-blue-600" />
        </div>
        <div className="mt-6 rounded-xl bg-blue-50 border border-blue-200 p-6">
          <p className="text-lg font-semibold text-blue-800">
            Multiple matches found
          </p>
          <p className="text-sm text-blue-600 mb-3">
            We heard: &quot;{result.transcript}&quot;
          </p>
          <div className="space-y-2">
            {result.candidates.map((c) => (
              <div
                key={c.id}
                className="flex items-center justify-between rounded-lg bg-white px-4 py-3 border border-blue-100"
              >
                <div className="flex items-center gap-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-full bg-blue-100">
                    <User className="h-5 w-5 text-blue-600" />
                  </div>
                  <span className="font-medium text-gray-900">{c.name}</span>
                </div>
                <span className="text-xs text-gray-400">
                  {Math.round(c.score * 100)}% match
                </span>
              </div>
            ))}
          </div>
        </div>
        <Button onClick={onReset} className="mt-6" size="lg">
          <RotateCcw className="mr-2 h-5 w-5" />
          Try Again
        </Button>
      </div>
    );
  }

  // no_match or error
  return (
    <div className="w-full">
      <div className="flex h-40 w-40 mx-auto items-center justify-center rounded-full bg-red-100">
        <XCircle className="h-20 w-20 text-red-500" />
      </div>
      <div className="mt-6 rounded-xl bg-red-50 border border-red-200 p-6">
        <p className="text-lg font-semibold text-red-800">
          {result.message || "Could not identify member"}
        </p>
        {result.transcript && (
          <p className="mt-2 text-sm text-red-600">
            We heard: &quot;{result.transcript}&quot;
          </p>
        )}
      </div>
      <Button onClick={onReset} className="mt-6" size="lg">
        <RotateCcw className="mr-2 h-5 w-5" />
        Try Again
      </Button>
    </div>
  );
}
