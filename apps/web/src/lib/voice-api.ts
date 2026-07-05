import { apiClient } from "./api-client";

export interface VoiceCheckinResult {
  status: "checked_in" | "no_booking" | "ambiguous" | "no_match";
  transcript: string;
  message?: string;
  name_extracted?: string;
  member?: {
    id: string;
    name: string;
    email?: string;
  };
  booking?: {
    id: string;
    class_title: string;
    starts_at: string | null;
  };
  candidates?: Array<{
    id: string;
    name: string;
    score: number;
  }>;
}

export interface VoiceCommandResult {
  action: "navigate" | "search_member" | "open_member" | "unknown" | "error";
  transcript: string;
  path?: string;
  target?: string;
  member_name?: string;
  member_id?: string;
  member_resolved?: string;
  section?: string;
  description?: string;
  message?: string;
  member_candidates?: Array<{ id: string; name: string }>;
}

export interface TranscribeResult {
  transcript: string;
}

function buildFormData(blob: Blob, filename = "audio.webm"): FormData {
  const fd = new FormData();
  fd.append("file", blob, filename);
  return fd;
}

export const voiceApi = {
  checkin: (audio: Blob) =>
    apiClient.post<VoiceCheckinResult>("/voice/checkin", buildFormData(audio), {
      headers: { "Content-Type": "multipart/form-data" },
    }),

  // Text-based check-in using browser speech recognition (no OpenAI needed)
  checkinText: (transcript: string) =>
    apiClient.post<VoiceCheckinResult>("/voice/checkin/text", { transcript }),

  command: (audio: Blob) =>
    apiClient.post<VoiceCommandResult>("/voice/command", buildFormData(audio), {
      headers: { "Content-Type": "multipart/form-data" },
    }),

  transcribe: (audio: Blob) =>
    apiClient.post<TranscribeResult>("/voice/transcribe", buildFormData(audio), {
      headers: { "Content-Type": "multipart/form-data" },
    }),
};
