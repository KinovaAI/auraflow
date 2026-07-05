"use client";

import { useState, useCallback, useEffect, useRef, useMemo } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { format, startOfDay, endOfDay, isWithinInterval, addMinutes } from "date-fns";
import {
  Mic,
  MicOff,
  CheckCircle2,
  XCircle,
  ChevronDown,
  UserPlus,
  ArrowLeft,
  Search,
  X,
  Loader2,
  Clock,
  Users,
  CreditCard,
  Gift,
  DollarSign,
  Ticket,
} from "lucide-react";
import toast from "react-hot-toast";
import { sessionsApi, bookingsApi, type Session, type RosterEntry } from "@/lib/scheduling-api";
import { membersApi, type Member } from "@/lib/members-api";
import { voiceApi, type VoiceCheckinResult } from "@/lib/voice-api";
import { useMicrophone } from "@/hooks/use-microphone";
import { useStudioStore } from "@/stores/studio-store";

// ── Types ───────────────────────────────────────────────────────────────────

type KioskView = "roster" | "voice" | "drop-in";

type PaymentMethod = "membership" | "drop_in_pass" | "cash" | "comp";

const PAYMENT_OPTIONS: { value: PaymentMethod; label: string; icon: typeof CreditCard }[] = [
  { value: "membership", label: "Membership", icon: CreditCard },
  { value: "drop_in_pass", label: "Drop-In Pass", icon: Ticket },
  { value: "cash", label: "Cash", icon: DollarSign },
  { value: "comp", label: "Comp", icon: Gift },
];

// Browser SpeechRecognition
const SpeechRecognition =
  typeof window !== "undefined"
    ? (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
    : null;

// ── Kiosk Page ──────────────────────────────────────────────────────────────

export default function KioskPage() {
  // Kiosk disabled at this URL — must be accessed via studio-specific route
  return (
    <div className="flex min-h-screen items-center justify-center bg-white">
      <p className="text-lg text-gray-500">Kiosk not available at this URL.</p>
    </div>
  );
}

function KioskPageDisabled() {
  const studioId = useStudioStore((s) => s.activeStudioId);
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(() => {
    if (typeof window !== "undefined") {
      return sessionStorage.getItem("kiosk_session_id");
    }
    return null;
  });
  const [view, setView] = useState<KioskView>("roster");
  const [currentTime, setCurrentTime] = useState(new Date());
  const [showSessionPicker, setShowSessionPicker] = useState(false);

  // Persist selected session
  useEffect(() => {
    if (selectedSessionId) {
      sessionStorage.setItem("kiosk_session_id", selectedSessionId);
    }
  }, [selectedSessionId]);

  // Live clock
  useEffect(() => {
    const timer = setInterval(() => setCurrentTime(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  // Hide sidebar for kiosk mode
  useEffect(() => {
    const sidebar = document.querySelector("[data-sidebar]") as HTMLElement | null;
    const header = document.querySelector("[data-dashboard-header]") as HTMLElement | null;
    const main = document.querySelector("[data-dashboard-main]") as HTMLElement | null;

    if (sidebar) sidebar.style.display = "none";
    if (header) header.style.display = "none";
    if (main) {
      main.style.marginLeft = "0";
      main.style.maxWidth = "100%";
      main.style.padding = "0";
    }

    document.body.style.overflow = "hidden";

    return () => {
      if (sidebar) sidebar.style.display = "";
      if (header) header.style.display = "";
      if (main) {
        main.style.marginLeft = "";
        main.style.maxWidth = "";
        main.style.padding = "";
      }
      document.body.style.overflow = "";
    };
  }, []);

  // Fetch today's sessions
  const today = format(new Date(), "yyyy-MM-dd");
  const { data: sessions = [], isLoading: sessionsLoading } = useQuery({
    queryKey: ["kiosk-sessions", studioId, today],
    queryFn: async () => {
      if (!studioId) return [];
      const res = await sessionsApi.list({
        studio_id: studioId,
        start: today,
        end: today,
      });
      return res.data;
    },
    enabled: !!studioId,
    refetchInterval: 60_000,
  });

  // Auto-detect current or upcoming session
  useEffect(() => {
    if (!sessions.length || selectedSessionId) return;

    const now = new Date();
    const threshold = addMinutes(now, 30);

    // Find session happening now
    const current = sessions.find((s) =>
      isWithinInterval(now, { start: new Date(s.starts_at), end: new Date(s.ends_at) })
    );
    if (current) {
      setSelectedSessionId(current.id);
      return;
    }

    // Find session starting within 30 minutes
    const upcoming = sessions.find((s) => {
      const start = new Date(s.starts_at);
      return start > now && start <= threshold;
    });
    if (upcoming) {
      setSelectedSessionId(upcoming.id);
      return;
    }

    // If only one session today, select it
    if (sessions.length === 1) {
      setSelectedSessionId(sessions[0].id);
    }
  }, [sessions, selectedSessionId]);

  const selectedSession = sessions.find((s) => s.id === selectedSessionId) ?? null;

  // Fetch roster for selected session
  const {
    data: roster = [],
    isLoading: rosterLoading,
    refetch: refetchRoster,
  } = useQuery({
    queryKey: ["kiosk-roster", selectedSessionId],
    queryFn: async () => {
      if (!selectedSessionId) return [];
      const res = await sessionsApi.getRoster(selectedSessionId);
      return res.data;
    },
    enabled: !!selectedSessionId,
    refetchInterval: 10_000,
  });

  const checkedInCount = roster.filter((r) => r.status === "checked_in" || r.status === "attended").length;

  if (view === "voice" && selectedSession) {
    return (
      <VoiceCheckinView
        session={selectedSession}
        roster={roster}
        onBack={() => setView("roster")}
        onCheckedIn={() => refetchRoster()}
      />
    );
  }

  if (view === "drop-in" && selectedSession) {
    return (
      <DropInModal
        session={selectedSession}
        roster={roster}
        onClose={() => setView("roster")}
        onSuccess={() => {
          refetchRoster();
          setView("roster");
        }}
      />
    );
  }

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-white">
      {/* Top bar */}
      <div className="flex items-center justify-between border-b border-gray-200 bg-white px-6 py-3">
        <div className="flex items-center gap-4">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-indigo-600">
            <span className="text-lg font-bold text-white">A</span>
          </div>
          <span className="text-xl font-semibold text-gray-900">AuraFlow</span>
        </div>
        <div className="text-right">
          <div className="text-2xl font-semibold tabular-nums text-gray-900">
            {format(currentTime, "h:mm:ss a")}
          </div>
          <div className="text-sm text-gray-500">
            {format(currentTime, "EEEE, MMMM d, yyyy")}
          </div>
        </div>
      </div>

      {/* No session state */}
      {!selectedSession && !sessionsLoading && (
        <div className="flex flex-1 flex-col items-center justify-center gap-6 p-8">
          <Clock className="h-16 w-16 text-gray-300" />
          <h2 className="text-2xl font-semibold text-gray-600">No class scheduled right now</h2>
          <p className="text-gray-400">Select a class below to begin check-in</p>
          {sessions.length > 0 && (
            <SessionPickerInline
              sessions={sessions}
              onSelect={(id) => setSelectedSessionId(id)}
            />
          )}
          {sessions.length === 0 && (
            <p className="text-gray-400">No sessions scheduled for today.</p>
          )}
          <a
            href="/dashboard"
            className="mt-4 text-sm text-indigo-600 hover:text-indigo-800"
          >
            Back to Dashboard
          </a>
        </div>
      )}

      {sessionsLoading && (
        <div className="flex flex-1 items-center justify-center">
          <Loader2 className="h-12 w-12 animate-spin text-indigo-600" />
        </div>
      )}

      {/* Main content when session selected */}
      {selectedSession && (
        <>
          {/* Session header */}
          <div className="flex items-center justify-between border-b border-gray-100 bg-gray-50 px-6 py-4">
            <div className="flex items-center gap-6">
              <div>
                <h1 className="text-2xl font-bold text-gray-900">
                  {selectedSession.title}
                </h1>
                <div className="mt-1 flex items-center gap-3 text-sm text-gray-500">
                  {selectedSession.instructor_name && (
                    <span>{selectedSession.instructor_name}</span>
                  )}
                  <span className="text-gray-300">|</span>
                  <span>
                    {format(new Date(selectedSession.starts_at), "h:mm a")} &ndash;{" "}
                    {format(new Date(selectedSession.ends_at), "h:mm a")}
                  </span>
                </div>
              </div>
              <div className="flex items-center gap-2 rounded-full bg-indigo-50 px-4 py-2">
                <Users className="h-5 w-5 text-indigo-600" />
                <span className="text-lg font-semibold text-indigo-700">
                  {checkedInCount}/{roster.length} checked in
                </span>
                {selectedSession.capacity && (
                  <span className="text-sm text-indigo-400">
                    ({selectedSession.capacity} capacity)
                  </span>
                )}
              </div>
            </div>

            {/* Session switcher */}
            <div className="relative">
              <button
                onClick={() => setShowSessionPicker(!showSessionPicker)}
                className="flex items-center gap-2 rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 shadow-sm active:bg-gray-50"
              >
                Switch Class
                <ChevronDown className="h-4 w-4" />
              </button>
              {showSessionPicker && (
                <>
                  <div
                    className="fixed inset-0 z-10"
                    onClick={() => setShowSessionPicker(false)}
                  />
                  <div className="absolute right-0 top-full z-20 mt-2 w-80 rounded-xl border border-gray-200 bg-white shadow-xl">
                    {sessions.map((s) => (
                      <button
                        key={s.id}
                        onClick={() => {
                          setSelectedSessionId(s.id);
                          setShowSessionPicker(false);
                        }}
                        className={`flex w-full items-center gap-3 px-4 py-3 text-left first:rounded-t-xl last:rounded-b-xl ${
                          s.id === selectedSessionId
                            ? "bg-indigo-50 text-indigo-700"
                            : "text-gray-700 hover:bg-gray-50 active:bg-gray-100"
                        }`}
                      >
                        <div className="flex-1">
                          <div className="font-medium">{s.title}</div>
                          <div className="text-xs text-gray-500">
                            {format(new Date(s.starts_at), "h:mm a")} &ndash;{" "}
                            {format(new Date(s.ends_at), "h:mm a")}
                            {s.instructor_name && ` \u00b7 ${s.instructor_name}`}
                          </div>
                        </div>
                        {s.id === selectedSessionId && (
                          <CheckCircle2 className="h-5 w-5 text-indigo-600" />
                        )}
                      </button>
                    ))}
                  </div>
                </>
              )}
            </div>
          </div>

          {/* Roster grid */}
          <div className="flex-1 overflow-y-auto p-6">
            {rosterLoading ? (
              <div className="flex h-full items-center justify-center">
                <Loader2 className="h-10 w-10 animate-spin text-indigo-400" />
              </div>
            ) : roster.length === 0 ? (
              <div className="flex h-full flex-col items-center justify-center gap-4 text-gray-400">
                <Users className="h-16 w-16" />
                <p className="text-lg">No bookings for this class yet</p>
                <p className="text-sm">Use Drop-In to add walk-in members</p>
              </div>
            ) : (
              <RosterGrid
                roster={roster}
                sessionId={selectedSession.id}
                onCheckedIn={() => refetchRoster()}
              />
            )}
          </div>

          {/* Bottom action bar */}
          <div className="flex items-center justify-between border-t border-gray-200 bg-white px-6 py-4">
            <a
              href="/dashboard"
              className="text-sm text-gray-400 hover:text-gray-600"
            >
              Back to Dashboard
            </a>
            <div className="flex items-center gap-4">
              <button
                onClick={() => setView("voice")}
                className="flex items-center gap-3 rounded-xl bg-indigo-600 px-8 py-4 text-lg font-semibold text-white shadow-lg transition-transform active:scale-95"
              >
                <Mic className="h-6 w-6" />
                Voice Check-In
              </button>
              <button
                onClick={() => setView("drop-in")}
                className="flex items-center gap-3 rounded-xl border-2 border-indigo-600 bg-white px-8 py-4 text-lg font-semibold text-indigo-600 shadow-lg transition-transform active:scale-95"
              >
                <UserPlus className="h-6 w-6" />
                Drop-In
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

// ── Roster Grid ─────────────────────────────────────────────────────────────

function RosterGrid({
  roster,
  sessionId,
  onCheckedIn,
}: {
  roster: RosterEntry[];
  sessionId: string;
  onCheckedIn: () => void;
}) {
  const queryClient = useQueryClient();

  const checkInMutation = useMutation({
    mutationFn: (bookingId: string) => bookingsApi.checkIn(bookingId),
    onSuccess: (_data, bookingId) => {
      const entry = roster.find((r) => r.id === bookingId);
      const name = entry
        ? `${entry.first_name || ""} ${entry.last_name || ""}`.trim() || entry.guest_name || "Member"
        : "Member";
      toast.success(`${name} checked in!`);
      onCheckedIn();
    },
    onError: () => {
      toast.error("Check-in failed. Please try again.");
    },
  });

  // Sort: not checked in first, then checked in, then no-show
  const sortedRoster = useMemo(() => {
    const order: Record<string, number> = {
      booked: 0,
      confirmed: 0,
      waitlisted: 1,
      checked_in: 2,
      attended: 2,
      no_show: 3,
      cancelled: 4,
    };
    return [...roster]
      .filter((r) => r.status !== "cancelled")
      .sort((a, b) => (order[a.status] ?? 1) - (order[b.status] ?? 1));
  }, [roster]);

  return (
    <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
      {sortedRoster.map((entry) => {
        const name =
          `${entry.first_name || ""} ${entry.last_name || ""}`.trim() ||
          entry.guest_name ||
          "Unknown";
        const isCheckedIn = entry.status === "checked_in" || entry.status === "attended";
        const isNoShow = entry.status === "no_show";
        const canCheckIn = !isCheckedIn && !isNoShow && entry.status !== "cancelled";
        const isChecking = checkInMutation.isPending && checkInMutation.variables === entry.id;

        return (
          <button
            key={entry.id}
            disabled={!canCheckIn || isChecking}
            onClick={() => canCheckIn && checkInMutation.mutate(entry.id)}
            className={`relative flex flex-col items-center rounded-2xl border-2 p-6 text-center transition-all ${
              isCheckedIn
                ? "border-green-300 bg-green-50 cursor-default"
                : isNoShow
                ? "border-red-300 bg-red-50 cursor-default"
                : "border-gray-200 bg-white shadow-sm cursor-pointer active:scale-[0.97] active:border-indigo-400 active:bg-indigo-50"
            }`}
          >
            {/* Check-in animation overlay */}
            {isChecking && (
              <div className="absolute inset-0 flex items-center justify-center rounded-2xl bg-white/80">
                <Loader2 className="h-8 w-8 animate-spin text-indigo-600" />
              </div>
            )}

            {/* Status icon */}
            {isCheckedIn && (
              <div className="absolute right-3 top-3">
                <CheckCircle2 className="h-7 w-7 text-green-500" />
              </div>
            )}
            {isNoShow && (
              <div className="absolute right-3 top-3">
                <XCircle className="h-7 w-7 text-red-400" />
              </div>
            )}

            {/* Avatar */}
            <div
              className={`flex h-14 w-14 items-center justify-center rounded-full text-xl font-bold ${
                isCheckedIn
                  ? "bg-green-200 text-green-700"
                  : isNoShow
                  ? "bg-red-200 text-red-700"
                  : "bg-indigo-100 text-indigo-700"
              }`}
            >
              {name.charAt(0).toUpperCase()}
            </div>

            {/* Name */}
            <span
              className={`mt-3 text-lg font-semibold leading-tight ${
                isCheckedIn
                  ? "text-green-800"
                  : isNoShow
                  ? "text-red-700"
                  : "text-gray-900"
              }`}
            >
              {name}
            </span>

            {/* Status label */}
            <span
              className={`mt-1 text-xs font-medium uppercase tracking-wide ${
                isCheckedIn
                  ? "text-green-600"
                  : isNoShow
                  ? "text-red-500"
                  : "text-gray-400"
              }`}
            >
              {isCheckedIn
                ? entry.checked_in_at
                  ? `Checked in ${format(new Date(entry.checked_in_at), "h:mm a")}`
                  : "Checked In"
                : isNoShow
                ? "No Show"
                : entry.status === "waitlisted"
                ? "Waitlisted"
                : entry.status === "cancelled"
                ? "Cancelled"
                : "Tap to check in"}
            </span>

            {/* Source badge for drop-ins */}
            {entry.source === "walk_in" && (
              <span className="mt-2 rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-700">
                Drop-In
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}

// ── Session Picker (inline, for no-session state) ───────────────────────────

function SessionPickerInline({
  sessions,
  onSelect,
}: {
  sessions: Session[];
  onSelect: (id: string) => void;
}) {
  return (
    <div className="w-full max-w-lg space-y-2">
      {sessions.map((s) => (
        <button
          key={s.id}
          onClick={() => onSelect(s.id)}
          className="flex w-full items-center gap-4 rounded-xl border border-gray-200 bg-white p-4 text-left shadow-sm transition-all active:scale-[0.98] active:border-indigo-400"
        >
          <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-indigo-100">
            <Clock className="h-6 w-6 text-indigo-600" />
          </div>
          <div className="flex-1">
            <div className="text-lg font-semibold text-gray-900">{s.title}</div>
            <div className="text-sm text-gray-500">
              {format(new Date(s.starts_at), "h:mm a")} &ndash;{" "}
              {format(new Date(s.ends_at), "h:mm a")}
              {s.instructor_name && ` \u00b7 ${s.instructor_name}`}
            </div>
          </div>
          <ChevronDown className="h-5 w-5 -rotate-90 text-gray-400" />
        </button>
      ))}
    </div>
  );
}

// ── Voice Check-In View ─────────────────────────────────────────────────────

function VoiceCheckinView({
  session,
  roster,
  onBack,
  onCheckedIn,
}: {
  session: Session;
  roster: RosterEntry[];
  onBack: () => void;
  onCheckedIn: () => void;
}) {
  const { isRecording, startRecording, stopRecording, error: micError, duration } = useMicrophone();
  const [phase, setPhase] = useState<"idle" | "recording" | "processing" | "result">("idle");
  const [result, setResult] = useState<VoiceCheckinResult | null>(null);
  const [liveTranscript, setLiveTranscript] = useState("");
  const recognitionRef = useRef<any>(null);

  const useBrowserSpeech = !!SpeechRecognition;

  const textCheckinMutation = useMutation({
    mutationFn: (transcript: string) => voiceApi.checkinText(transcript).then((r) => r.data),
    onSuccess: (data) => {
      setResult(data);
      setPhase("result");
      if (data.status === "checked_in") {
        toast.success(`Welcome, ${data.member?.name}!`);
        onCheckedIn();
      }
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setResult({
        status: "no_match",
        transcript: liveTranscript,
        message: detail || "Could not identify member. Please try again.",
      });
      setPhase("result");
    },
  });

  const checkinMutation = useMutation({
    mutationFn: (audio: Blob) => voiceApi.checkin(audio).then((r) => r.data),
    onSuccess: (data) => {
      setResult(data);
      setPhase("result");
      if (data.status === "checked_in") {
        toast.success(`Welcome, ${data.member?.name}!`);
        onCheckedIn();
      }
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

  const handlePushStart = useCallback(async () => {
    setResult(null);
    setLiveTranscript("");
    setPhase("recording");

    if (useBrowserSpeech) {
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
      await startRecording();
    }
  }, [startRecording, useBrowserSpeech]);

  const handlePushEnd = useCallback(async () => {
    if (useBrowserSpeech) {
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
      const blob = await stopRecording();
      if (blob && blob.size > 0) {
        setPhase("processing");
        checkinMutation.mutate(blob);
      } else {
        setPhase("idle");
      }
    }
  }, [stopRecording, checkinMutation, textCheckinMutation, useBrowserSpeech, liveTranscript]);

  // Auto-return to roster view after successful check-in, reset to idle for failures
  useEffect(() => {
    if (phase === "result") {
      const timer = setTimeout(() => {
        if (result?.status === "checked_in") {
          onBack(); // Return to roster view
        } else {
          setPhase("idle");
          setResult(null);
          setLiveTranscript("");
        }
      }, 3000);
      return () => clearTimeout(timer);
    }
  }, [phase, result, onBack]);

  const formatDuration = (s: number) => {
    const mins = Math.floor(s / 60);
    const secs = s % 60;
    return `${mins}:${secs.toString().padStart(2, "0")}`;
  };

  return (
    <div className="fixed inset-0 z-50 flex flex-col items-center justify-center bg-white">
      {/* Back button */}
      <button
        onClick={onBack}
        className="absolute left-6 top-6 flex items-center gap-2 rounded-xl border border-gray-200 bg-white px-5 py-3 text-base font-medium text-gray-600 shadow-sm active:bg-gray-50"
      >
        <ArrowLeft className="h-5 w-5" />
        Back to Roster
      </button>

      {/* Session info */}
      <div className="absolute right-6 top-6 text-right">
        <div className="text-sm text-gray-500">{session.title}</div>
        <div className="text-xs text-gray-400">
          {format(new Date(session.starts_at), "h:mm a")} &ndash;{" "}
          {format(new Date(session.ends_at), "h:mm a")}
        </div>
      </div>

      <div className="flex flex-col items-center gap-6">
        <h1 className="text-3xl font-bold text-gray-900">Voice Check-In</h1>
        <p className="text-lg text-gray-500">
          Press and hold, then say your name
        </p>

        {/* Microphone button */}
        {phase === "idle" && (
          <button
            onMouseDown={handlePushStart}
            onMouseUp={handlePushEnd}
            onTouchStart={(e) => { e.preventDefault(); handlePushStart(); }}
            onTouchEnd={(e) => { e.preventDefault(); handlePushEnd(); }}
            className="mt-4 flex h-44 w-44 items-center justify-center rounded-full bg-indigo-600 shadow-xl transition-all active:scale-95 active:bg-indigo-800 focus:outline-none focus:ring-4 focus:ring-indigo-300"
          >
            <Mic className="h-20 w-20 text-white" />
          </button>
        )}

        {phase === "recording" && (
          <>
            <button
              onMouseUp={handlePushEnd}
              onTouchEnd={(e) => { e.preventDefault(); handlePushEnd(); }}
              className="relative mt-4 flex h-44 w-44 items-center justify-center rounded-full bg-red-500 shadow-xl"
            >
              <span className="absolute inset-0 animate-ping rounded-full bg-red-400 opacity-30" />
              <span className="absolute inset-3 animate-pulse rounded-full bg-red-400 opacity-20" />
              <MicOff className="relative h-20 w-20 text-white" />
            </button>
            <div className="flex items-center gap-2 text-red-600">
              <span className="h-3 w-3 animate-pulse rounded-full bg-red-500" />
              <span className="text-xl font-semibold">
                Listening... {formatDuration(duration)}
              </span>
            </div>
            {liveTranscript && (
              <p className="text-2xl font-medium text-gray-700">
                &ldquo;{liveTranscript}&rdquo;
              </p>
            )}
          </>
        )}

        {phase === "processing" && (
          <>
            <div className="mt-4 flex h-44 w-44 items-center justify-center rounded-full bg-gray-100">
              <Loader2 className="h-20 w-20 animate-spin text-indigo-600" />
            </div>
            <p className="text-xl font-medium text-gray-500">Processing...</p>
          </>
        )}

        {phase === "result" && result && (
          <div className="mt-4 flex flex-col items-center gap-4">
            {result.status === "checked_in" ? (
              <>
                <div className="flex h-44 w-44 items-center justify-center rounded-full bg-green-100">
                  <CheckCircle2 className="h-24 w-24 text-green-500" />
                </div>
                <p className="text-3xl font-bold text-green-700">
                  Welcome, {result.member?.name}!
                </p>
                <p className="text-lg text-green-500">You&apos;re checked in</p>
              </>
            ) : (
              <>
                <div className="flex h-44 w-44 items-center justify-center rounded-full bg-red-100">
                  <XCircle className="h-24 w-24 text-red-400" />
                </div>
                <p className="text-2xl font-semibold text-red-700">
                  {result.message || "Not found"}
                </p>
                {result.transcript && (
                  <p className="text-base text-gray-400">
                    We heard: &quot;{result.transcript}&quot;
                  </p>
                )}
              </>
            )}
            <p className="text-sm text-gray-400">Returning to roster...</p>
            <button
              onClick={onBack}
              className="mt-4 rounded-xl border border-gray-200 bg-white px-6 py-3 text-base font-medium text-gray-600 shadow-sm active:bg-gray-50"
            >
              Back to Roster
            </button>
          </div>
        )}

        {phase === "idle" && (
          <p className="mt-2 text-sm text-gray-400">
            Hold to record &middot; Release to check in
          </p>
        )}
      </div>

      {micError && (
        <div className="absolute bottom-6 left-1/2 -translate-x-1/2 rounded-lg bg-red-50 px-6 py-3 text-red-600">
          {micError}
        </div>
      )}
    </div>
  );
}

// ── Drop-In Modal ───────────────────────────────────────────────────────────

function DropInModal({
  session,
  roster,
  onClose,
  onSuccess,
}: {
  session: Session;
  roster: RosterEntry[];
  onClose: () => void;
  onSuccess: () => void;
}) {
  const [searchQuery, setSearchQuery] = useState("");
  const [mode, setMode] = useState<"search" | "guest">("search");
  const [guestName, setGuestName] = useState("");
  const [guestEmail, setGuestEmail] = useState("");
  const [selectedMember, setSelectedMember] = useState<Member | null>(null);
  const [paymentMethod, setPaymentMethod] = useState<PaymentMethod>("membership");

  // Search members
  const { data: searchResults = [], isFetching: searching } = useQuery({
    queryKey: ["kiosk-member-search", searchQuery],
    queryFn: async () => {
      if (!searchQuery || searchQuery.length < 2) return [];
      const res = await membersApi.list({ search: searchQuery, limit: 10, active_only: true });
      return res.data;
    },
    enabled: searchQuery.length >= 2,
  });

  // Filter out members already on the roster
  const rosterMemberIds = useMemo(
    () => new Set(roster.map((r) => r.member_id)),
    [roster]
  );
  const filteredResults = searchResults.filter((m) => !rosterMemberIds.has(m.id));

  // Create booking + check in
  const dropInMutation = useMutation({
    mutationFn: async () => {
      if (mode === "guest" && !selectedMember) {
        // Guest booking
        const bookingRes = await bookingsApi.create({
          member_id: "guest",
          class_session_id: session.id,
          source: "walk_in",
          guest_name: guestName.trim(),
          guest_email: guestEmail.trim() || undefined,
          notes: `Drop-in: ${paymentMethod}`,
        });
        await bookingsApi.checkIn(bookingRes.data.id);
        return guestName.trim();
      } else if (selectedMember) {
        const bookingRes = await bookingsApi.create({
          member_id: selectedMember.id,
          class_session_id: session.id,
          source: "walk_in",
          notes: `Drop-in: ${paymentMethod}`,
        });
        await bookingsApi.checkIn(bookingRes.data.id);
        return `${selectedMember.first_name} ${selectedMember.last_name}`.trim();
      }
      throw new Error("No member or guest info provided");
    },
    onSuccess: (name) => {
      toast.success(`${name} added and checked in!`);
      onSuccess();
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      toast.error(detail || "Failed to add drop-in. Please try again.");
    },
  });

  const canSubmit =
    mode === "guest"
      ? guestName.trim().length > 0
      : selectedMember !== null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="relative mx-4 flex w-full max-w-2xl flex-col rounded-2xl bg-white shadow-2xl" style={{ maxHeight: "90vh" }}>
        {/* Header */}
        <div className="flex items-center justify-between border-b border-gray-200 px-6 py-4">
          <h2 className="text-2xl font-bold text-gray-900">Drop-In Check-In</h2>
          <button
            onClick={onClose}
            className="flex h-10 w-10 items-center justify-center rounded-full text-gray-400 active:bg-gray-100"
          >
            <X className="h-6 w-6" />
          </button>
        </div>

        {/* Mode tabs */}
        <div className="flex border-b border-gray-200">
          <button
            onClick={() => { setMode("search"); setSelectedMember(null); }}
            className={`flex-1 py-3 text-center text-base font-medium ${
              mode === "search"
                ? "border-b-2 border-indigo-600 text-indigo-600"
                : "text-gray-500"
            }`}
          >
            <Search className="mr-2 inline h-5 w-5" />
            Find Member
          </button>
          <button
            onClick={() => { setMode("guest"); setSelectedMember(null); }}
            className={`flex-1 py-3 text-center text-base font-medium ${
              mode === "guest"
                ? "border-b-2 border-indigo-600 text-indigo-600"
                : "text-gray-500"
            }`}
          >
            <UserPlus className="mr-2 inline h-5 w-5" />
            Add as Guest
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6">
          {mode === "search" && (
            <div className="space-y-4">
              {/* Search input */}
              <div className="relative">
                <Search className="absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 text-gray-400" />
                <input
                  type="text"
                  autoFocus
                  placeholder="Search by name or email..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="w-full rounded-xl border border-gray-300 py-4 pl-12 pr-4 text-lg focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-200"
                />
              </div>

              {/* Results */}
              {searching && (
                <div className="flex justify-center py-8">
                  <Loader2 className="h-8 w-8 animate-spin text-indigo-400" />
                </div>
              )}

              {!searching && filteredResults.length > 0 && (
                <div className="space-y-2">
                  {filteredResults.map((member) => (
                    <button
                      key={member.id}
                      onClick={() => setSelectedMember(member)}
                      className={`flex w-full items-center gap-4 rounded-xl border-2 p-4 text-left transition-all active:scale-[0.98] ${
                        selectedMember?.id === member.id
                          ? "border-indigo-500 bg-indigo-50"
                          : "border-gray-200 bg-white"
                      }`}
                    >
                      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-indigo-100 text-lg font-bold text-indigo-700">
                        {member.first_name?.charAt(0)?.toUpperCase() || "?"}
                      </div>
                      <div className="flex-1">
                        <div className="text-lg font-semibold text-gray-900">
                          {member.first_name} {member.last_name}
                        </div>
                        <div className="text-sm text-gray-500">{member.email}</div>
                      </div>
                      {selectedMember?.id === member.id && (
                        <CheckCircle2 className="h-6 w-6 text-indigo-600" />
                      )}
                    </button>
                  ))}
                </div>
              )}

              {!searching && searchQuery.length >= 2 && filteredResults.length === 0 && (
                <div className="py-8 text-center text-gray-400">
                  <p className="text-lg">No members found</p>
                  <button
                    onClick={() => { setMode("guest"); setGuestName(searchQuery); }}
                    className="mt-2 text-indigo-600 underline"
                  >
                    Add as guest instead
                  </button>
                </div>
              )}
            </div>
          )}

          {mode === "guest" && (
            <div className="space-y-4">
              <div>
                <label className="mb-1 block text-sm font-medium text-gray-700">
                  Name <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  autoFocus
                  placeholder="Guest name"
                  value={guestName}
                  onChange={(e) => setGuestName(e.target.value)}
                  className="w-full rounded-xl border border-gray-300 px-4 py-4 text-lg focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-200"
                />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium text-gray-700">
                  Email (optional)
                </label>
                <input
                  type="email"
                  placeholder="guest@example.com"
                  value={guestEmail}
                  onChange={(e) => setGuestEmail(e.target.value)}
                  className="w-full rounded-xl border border-gray-300 px-4 py-4 text-lg focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-200"
                />
              </div>
            </div>
          )}

          {/* Payment method (shared) */}
          {(selectedMember || (mode === "guest" && guestName.trim())) && (
            <div className="mt-6">
              <label className="mb-2 block text-sm font-medium text-gray-700">
                Payment Method
              </label>
              <div className="grid grid-cols-2 gap-3">
                {PAYMENT_OPTIONS.map((opt) => {
                  const Icon = opt.icon;
                  return (
                    <button
                      key={opt.value}
                      onClick={() => setPaymentMethod(opt.value)}
                      className={`flex items-center gap-3 rounded-xl border-2 p-4 text-left transition-all active:scale-[0.98] ${
                        paymentMethod === opt.value
                          ? "border-indigo-500 bg-indigo-50 text-indigo-700"
                          : "border-gray-200 bg-white text-gray-700"
                      }`}
                    >
                      <Icon className="h-5 w-5" />
                      <span className="font-medium">{opt.label}</span>
                    </button>
                  );
                })}
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 border-t border-gray-200 px-6 py-4">
          <button
            onClick={onClose}
            className="rounded-xl border border-gray-300 px-6 py-3 text-base font-medium text-gray-700 active:bg-gray-50"
          >
            Cancel
          </button>
          <button
            disabled={!canSubmit || dropInMutation.isPending}
            onClick={() => dropInMutation.mutate()}
            className="flex items-center gap-2 rounded-xl bg-indigo-600 px-8 py-3 text-base font-semibold text-white shadow-sm transition-all disabled:opacity-50 active:scale-95 active:bg-indigo-700"
          >
            {dropInMutation.isPending ? (
              <Loader2 className="h-5 w-5 animate-spin" />
            ) : (
              <CheckCircle2 className="h-5 w-5" />
            )}
            Add &amp; Check In
          </button>
        </div>
      </div>
    </div>
  );
}
