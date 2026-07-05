"use client";

import { useState, useRef, useCallback } from "react";

interface UseMicrophoneReturn {
  isRecording: boolean;
  startRecording: () => Promise<void>;
  stopRecording: () => Promise<Blob | null>;
  error: string | null;
  duration: number;
}

export function useMicrophone(): UseMicrophoneReturn {
  const [isRecording, setIsRecording] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [duration, setDuration] = useState(0);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const resolveRef = useRef<((blob: Blob | null) => void) | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const startTimeRef = useRef(0);

  const startRecording = useCallback(async () => {
    setError(null);
    chunksRef.current = [];
    setDuration(0);

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          sampleRate: 16000,
        },
      });

      // Prefer webm/opus, fall back to whatever is available
      const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
        ? "audio/webm;codecs=opus"
        : MediaRecorder.isTypeSupported("audio/webm")
          ? "audio/webm"
          : "";

      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : {});

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) {
          chunksRef.current.push(e.data);
        }
      };

      recorder.onstop = () => {
        // Stop all tracks to release the microphone
        stream.getTracks().forEach((t) => t.stop());

        if (timerRef.current) {
          clearInterval(timerRef.current);
          timerRef.current = null;
        }

        const blob =
          chunksRef.current.length > 0
            ? new Blob(chunksRef.current, { type: mimeType || "audio/webm" })
            : null;

        if (resolveRef.current) {
          resolveRef.current(blob);
          resolveRef.current = null;
        }
      };

      mediaRecorderRef.current = recorder;
      recorder.start(250); // Collect data every 250ms
      setIsRecording(true);
      startTimeRef.current = Date.now();

      // Duration timer
      timerRef.current = setInterval(() => {
        setDuration(Math.floor((Date.now() - startTimeRef.current) / 1000));
      }, 500);
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === "NotAllowedError") {
        setError("Microphone permission denied. Please allow microphone access.");
      } else if (err instanceof DOMException && err.name === "NotFoundError") {
        setError("No microphone found. Please connect a microphone.");
      } else {
        setError(err instanceof Error ? err.message : "Failed to access microphone");
      }
    }
  }, []);

  const stopRecording = useCallback(async (): Promise<Blob | null> => {
    return new Promise((resolve) => {
      const recorder = mediaRecorderRef.current;
      if (!recorder || recorder.state === "inactive") {
        setIsRecording(false);
        resolve(null);
        return;
      }

      resolveRef.current = resolve;
      recorder.stop();
      setIsRecording(false);
    });
  }, []);

  return { isRecording, startRecording, stopRecording, error, duration };
}
