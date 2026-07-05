"use client";

import { useState, useRef, useEffect, useCallback, Fragment } from "react";
import { useRouter } from "next/navigation";
import {
  MessageSquare,
  X,
  Send,
  Loader2,
  ArrowLeft,
  List,
  Trash2,
  Plus,
  ExternalLink,
} from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { useAuthStore } from "@/stores/auth-store";
import {
  chatbotApi,
  type ChatConversation,
  type ChatMessage,
} from "@/lib/chatbot-api";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// ---------------------------------------------------------------------------
// Simple markdown renderer
// ---------------------------------------------------------------------------

function renderMarkdown(text: string): React.ReactNode[] {
  // Split by code blocks first
  const parts = text.split(/(```[\s\S]*?```)/g);
  const nodes: React.ReactNode[] = [];

  parts.forEach((part, pi) => {
    if (part.startsWith("```") && part.endsWith("```")) {
      const inner = part.slice(3, -3);
      const newlineIdx = inner.indexOf("\n");
      const code = newlineIdx >= 0 ? inner.slice(newlineIdx + 1) : inner;
      nodes.push(
        <pre
          key={pi}
          className="my-2 overflow-x-auto rounded-md bg-gray-800 p-3 text-xs text-gray-100"
        >
          <code>{code}</code>
        </pre>
      );
    } else {
      // Handle inline formatting line by line
      const lines = part.split("\n");
      lines.forEach((line, li) => {
        if (li > 0) nodes.push(<br key={`br-${pi}-${li}`} />);
        // Split by inline code, bold, italic
        const tokens = line.split(/(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)/g);
        tokens.forEach((tok, ti) => {
          if (tok.startsWith("**") && tok.endsWith("**")) {
            nodes.push(
              <strong key={`${pi}-${li}-${ti}`}>
                {tok.slice(2, -2)}
              </strong>
            );
          } else if (tok.startsWith("*") && tok.endsWith("*") && tok.length > 2) {
            nodes.push(
              <em key={`${pi}-${li}-${ti}`}>{tok.slice(1, -1)}</em>
            );
          } else if (tok.startsWith("`") && tok.endsWith("`")) {
            nodes.push(
              <code
                key={`${pi}-${li}-${ti}`}
                className="rounded bg-gray-200 px-1 py-0.5 text-xs text-pink-600"
              >
                {tok.slice(1, -1)}
              </code>
            );
          } else {
            nodes.push(<Fragment key={`${pi}-${li}-${ti}`}>{tok}</Fragment>);
          }
        });
      });
    }
  });

  return nodes;
}

// ---------------------------------------------------------------------------
// Typing indicator
// ---------------------------------------------------------------------------

function TypingDots() {
  return (
    <div className="flex items-center gap-1 px-4 py-3">
      <div className="h-2 w-2 animate-bounce rounded-full bg-gray-400 [animation-delay:0ms]" />
      <div className="h-2 w-2 animate-bounce rounded-full bg-gray-400 [animation-delay:150ms]" />
      <div className="h-2 w-2 animate-bounce rounded-full bg-gray-400 [animation-delay:300ms]" />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

type View = "chat" | "history";

interface DisplayMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  action?: { type: string; path?: string; label?: string };
}

export function AIChatbot() {
  const router = useRouter();
  const user = useAuthStore((s) => s.user);

  // Panel state
  const [open, setOpen] = useState(false);
  const [view, setView] = useState<View>("chat");

  // Chat state
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<DisplayMessage[]>([]);
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);

  // Refs
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Conversation list query
  const conversationsQuery = useQuery({
    queryKey: ["chatbot-conversations"],
    queryFn: () => chatbotApi.listConversations().then((r) => r.data.data),
    enabled: open && view === "history",
    staleTime: 30_000,
  });

  // Auto-scroll
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isStreaming]);

  // Focus input when panel opens
  useEffect(() => {
    if (open && view === "chat") {
      setTimeout(() => inputRef.current?.focus(), 100);
    }
  }, [open, view]);

  // ------- SSE message send -------
  const sendMessage = useCallback(async () => {
    const text = input.trim();
    if (!text || isStreaming) return;

    setInput("");
    const userMsg: DisplayMessage = {
      id: `user-${Date.now()}`,
      role: "user",
      content: text,
    };
    setMessages((prev) => [...prev, userMsg]);
    setIsStreaming(true);

    // Prepare assistant placeholder
    const assistantId = `assistant-${Date.now()}`;
    setMessages((prev) => [
      ...prev,
      { id: assistantId, role: "assistant", content: "" },
    ]);

    let activeConvId = conversationId;

    try {
      const res = await fetch(`${API_URL}/api/v1/chatbot/message`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${localStorage.getItem("access_token")}`,
        },
        body: JSON.stringify({
          conversation_id: activeConvId,
          message: text,
        }),
      });

      if (!res.ok) {
        const errText = await res.text();
        throw new Error(errText || `HTTP ${res.status}`);
      }

      const reader = res.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const events = buffer.split("\n\n");
        buffer = events.pop() || "";

        for (const event of events) {
          const dataLine = event
            .split("\n")
            .find((l) => l.startsWith("data: "));
          if (!dataLine) continue;

          const jsonStr = dataLine.slice(6);
          if (jsonStr === "[DONE]") continue;

          try {
            const payload = JSON.parse(jsonStr);

            switch (payload.type) {
              case "conversation_id":
                activeConvId = payload.conversation_id;
                setConversationId(payload.conversation_id);
                break;

              case "content_delta":
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === assistantId
                      ? { ...m, content: m.content + payload.content }
                      : m
                  )
                );
                break;

              case "tool_use":
                // Show tool usage as subtle info in the message
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === assistantId
                      ? {
                          ...m,
                          content:
                            m.content +
                            (m.content ? "\n" : "") +
                            `*Looking up ${payload.tool || "information"}...*\n`,
                        }
                      : m
                  )
                );
                break;

              case "action":
                if (payload.action === "navigate" && payload.path) {
                  setMessages((prev) =>
                    prev.map((m) =>
                      m.id === assistantId
                        ? {
                            ...m,
                            action: {
                              type: "navigate",
                              path: payload.path,
                              label: payload.label || payload.path,
                            },
                          }
                        : m
                    )
                  );
                }
                break;

              case "done":
                break;
            }
          } catch {
            // Ignore malformed JSON
          }
        }
      }
    } catch (err: unknown) {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId
            ? {
                ...m,
                content:
                  m.content ||
                  "Sorry, something went wrong. Please try again.",
              }
            : m
        )
      );
    } finally {
      setIsStreaming(false);
    }
  }, [input, isStreaming, conversationId]);

  // ------- Load conversation from history -------
  const loadConversation = useCallback(async (conv: ChatConversation) => {
    try {
      const { data } = await chatbotApi.getConversation(conv.id);
      const loaded: DisplayMessage[] = data.data.messages.map(
        (m: ChatMessage) => ({
          id: m.id,
          role: m.role,
          content: m.content,
        })
      );
      setConversationId(conv.id);
      setMessages(loaded);
      setView("chat");
    } catch {
      // Fail silently
    }
  }, []);

  // ------- Delete conversation -------
  const deleteConversation = useCallback(
    async (id: string, e: React.MouseEvent) => {
      e.stopPropagation();
      try {
        await chatbotApi.deleteConversation(id);
        conversationsQuery.refetch();
        if (conversationId === id) {
          setConversationId(null);
          setMessages([]);
        }
      } catch {
        // Fail silently
      }
    },
    [conversationId, conversationsQuery]
  );

  // ------- New conversation -------
  const startNewConversation = useCallback(() => {
    setConversationId(null);
    setMessages([]);
    setView("chat");
    setTimeout(() => inputRef.current?.focus(), 100);
  }, []);

  // ------- Handle enter key -------
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
      }
    },
    [sendMessage]
  );

  // ======== Render ========

  // Collapsed: floating button
  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="fixed bottom-6 right-24 z-40 flex h-14 w-14 items-center justify-center rounded-full bg-indigo-600 text-white shadow-lg transition-all hover:bg-indigo-700 hover:shadow-xl active:scale-95 focus:outline-none focus:ring-4 focus:ring-indigo-300"
        title="AI Assistant"
      >
        <MessageSquare className="h-6 w-6" />
      </button>
    );
  }

  // Expanded panel
  return (
    <div className="fixed bottom-6 right-24 z-40 flex h-[600px] w-[calc(100vw-2rem)] flex-col overflow-hidden rounded-2xl border border-gray-200 bg-white shadow-2xl transition-all duration-300 sm:w-96">
      {/* ---- Header ---- */}
      <div className="flex items-center justify-between bg-indigo-600 px-4 py-3">
        {view === "history" ? (
          <button
            onClick={() => setView("chat")}
            className="flex items-center gap-1.5 text-sm font-semibold text-white"
          >
            <ArrowLeft className="h-4 w-4" />
            Back
          </button>
        ) : (
          <span className="text-sm font-semibold text-white">
            AuraFlow Assistant
          </span>
        )}

        <div className="flex items-center gap-1">
          {view === "chat" && (
            <>
              <button
                onClick={startNewConversation}
                className="rounded p-1.5 text-indigo-200 hover:bg-indigo-700 hover:text-white"
                title="New conversation"
              >
                <Plus className="h-4 w-4" />
              </button>
              <button
                onClick={() => {
                  setView("history");
                  conversationsQuery.refetch();
                }}
                className="rounded p-1.5 text-indigo-200 hover:bg-indigo-700 hover:text-white"
                title="Conversation history"
              >
                <List className="h-4 w-4" />
              </button>
            </>
          )}
          <button
            onClick={() => setOpen(false)}
            className="rounded p-1.5 text-indigo-200 hover:bg-indigo-700 hover:text-white"
            title="Close"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* ---- History view ---- */}
      {view === "history" && (
        <div className="flex-1 overflow-y-auto">
          {conversationsQuery.isLoading && (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="h-6 w-6 animate-spin text-indigo-600" />
            </div>
          )}

          {conversationsQuery.data && conversationsQuery.data.length === 0 && (
            <div className="px-4 py-12 text-center text-sm text-gray-400">
              No conversations yet
            </div>
          )}

          {conversationsQuery.data?.map((conv) => (
            <button
              key={conv.id}
              onClick={() => loadConversation(conv)}
              className="flex w-full items-center gap-3 border-b border-gray-100 px-4 py-3 text-left transition-colors hover:bg-gray-50"
            >
              <MessageSquare className="h-4 w-4 flex-shrink-0 text-gray-400" />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-gray-700">
                  {conv.title || "Untitled conversation"}
                </p>
                <p className="text-xs text-gray-400">
                  {conv.message_count} message{conv.message_count !== 1 && "s"}
                  {conv.last_message_at &&
                    ` \u00b7 ${new Date(conv.last_message_at).toLocaleDateString()}`}
                </p>
              </div>
              <button
                onClick={(e) => deleteConversation(conv.id, e)}
                className="rounded p-1 text-gray-300 hover:bg-red-50 hover:text-red-500"
                title="Delete conversation"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </button>
          ))}
        </div>
      )}

      {/* ---- Chat view ---- */}
      {view === "chat" && (
        <>
          {/* Messages */}
          <div className="flex-1 overflow-y-auto px-4 py-3">
            {messages.length === 0 && (
              <div className="flex h-full flex-col items-center justify-center text-center">
                <MessageSquare className="mb-3 h-10 w-10 text-indigo-200" />
                <p className="text-sm font-medium text-gray-500">
                  Hi{user?.first_name ? `, ${user.first_name}` : ""}! How can I
                  help?
                </p>
                <p className="mt-1 text-xs text-gray-400">
                  Ask about scheduling, members, analytics, or anything else.
                </p>
              </div>
            )}

            {messages.map((msg) => (
              <div
                key={msg.id}
                className={`mb-3 flex ${
                  msg.role === "user" ? "justify-end" : "justify-start"
                }`}
              >
                <div
                  className={`max-w-[85%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
                    msg.role === "user"
                      ? "rounded-br-md bg-indigo-600 text-white"
                      : "rounded-bl-md bg-gray-100 text-gray-900"
                  }`}
                >
                  {msg.role === "assistant"
                    ? renderMarkdown(msg.content)
                    : msg.content}

                  {/* Navigation action link */}
                  {msg.action?.type === "navigate" && msg.action.path && (
                    <button
                      onClick={() => {
                        router.push(msg.action!.path!);
                        setOpen(false);
                      }}
                      className="mt-2 flex items-center gap-1.5 rounded-lg bg-white px-3 py-1.5 text-xs font-medium text-indigo-600 shadow-sm transition-colors hover:bg-indigo-50"
                    >
                      <ExternalLink className="h-3 w-3" />
                      {msg.action.label || "Go to page"}
                    </button>
                  )}
                </div>
              </div>
            ))}

            {isStreaming &&
              messages.length > 0 &&
              messages[messages.length - 1].content === "" && <TypingDots />}

            <div ref={messagesEndRef} />
          </div>

          {/* Input bar */}
          <div className="border-t border-gray-200 bg-white px-3 py-3">
            <div className="flex items-center gap-2">
              <input
                ref={inputRef}
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Type a message..."
                disabled={isStreaming}
                className="flex-1 rounded-xl border border-gray-300 bg-gray-50 px-4 py-2.5 text-sm text-gray-900 placeholder-gray-400 outline-none transition-colors focus:border-indigo-400 focus:bg-white focus:ring-2 focus:ring-indigo-100 disabled:opacity-50"
              />
              <button
                onClick={sendMessage}
                disabled={!input.trim() || isStreaming}
                className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-xl bg-indigo-600 text-white transition-all hover:bg-indigo-700 active:scale-95 disabled:opacity-40 disabled:hover:bg-indigo-600"
                title="Send message"
              >
                {isStreaming ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Send className="h-4 w-4" />
                )}
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
