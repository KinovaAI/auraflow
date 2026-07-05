import { apiClient } from "./api-client";

export interface ChatConversation {
  id: string;
  title: string | null;
  message_count: number;
  last_message_at: string | null;
  created_at: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  tool_calls: Record<string, unknown>[] | null;
  created_at: string;
}

export const chatbotApi = {
  listConversations: () =>
    apiClient.get<{ data: ChatConversation[] }>("/chatbot/conversations"),

  getConversation: (id: string) =>
    apiClient.get<{
      data: { conversation: ChatConversation; messages: ChatMessage[] };
    }>(`/chatbot/conversations/${id}`),

  deleteConversation: (id: string) =>
    apiClient.delete(`/chatbot/conversations/${id}`),

  createConversation: () =>
    apiClient.post<{ data: ChatConversation }>("/chatbot/conversations"),
};
