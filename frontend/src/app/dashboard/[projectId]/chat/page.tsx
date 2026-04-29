"use client";

import { useState, useRef, useEffect, use } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { queryProject, getProject, Project, QueryResponse } from "@/lib/api";

interface Message {
  role: "user" | "assistant";
  content: string;
  citations?: string[];
  confidence?: number;
  follow_ups?: string[];
  latency_ms?: number;
}

export default function ChatPage({
  params,
}: {
  params: Promise<{ projectId: string }>;
}) {
  const { projectId } = use(params);
  const { user, loading } = useAuth();
  const router = useRouter();

  const [project, setProject] = useState<Project | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [thinking, setThinking] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!loading && !user) router.replace("/");
  }, [user, loading, router]);

  useEffect(() => {
    if (user) {
      getProject(projectId)
        .then(setProject)
        .catch(() => router.replace("/dashboard"));
    }
  }, [user, projectId, router]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, thinking]);

  const send = async (query: string) => {
    if (!query.trim() || thinking) return;
    const userMsg: Message = { role: "user", content: query };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setThinking(true);
    try {
      const res: QueryResponse = await queryProject(projectId, query);
      const assistantMsg: Message = {
        role: "assistant",
        content: res.answer,
        citations: res.citations,
        confidence: res.confidence,
        follow_ups: res.follow_ups,
        latency_ms: res.latency_ms,
      };
      setMessages((prev) => [...prev, assistantMsg]);
    } catch (e: unknown) {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: `Error: ${e instanceof Error ? e.message : "Request failed"}`,
        },
      ]);
    } finally {
      setThinking(false);
    }
  };

  return (
    <div className="flex h-screen flex-col bg-gray-950">
      {/* Header */}
      <header className="flex items-center gap-4 border-b border-gray-800 px-6 py-4">
        <button
          onClick={() => router.push("/dashboard")}
          className="text-gray-400 hover:text-white transition"
        >
          ← Back
        </button>
        <div>
          <h1 className="font-semibold text-white">
            {project?.repo_name ?? "Loading…"}
          </h1>
          <p className="text-xs text-gray-500">{project?.repo_owner}</p>
        </div>
        {project && (
          <button
            onClick={() => router.push(`/dashboard/${projectId}/docs`)}
            className="ml-auto rounded-xl border border-gray-700 px-4 py-2 text-sm text-gray-300 hover:bg-gray-800 transition"
          >
            View docs
          </button>
        )}
      </header>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-6 py-6">
        {messages.length === 0 && (
          <div className="flex h-full flex-col items-center justify-center text-center">
            <div className="mb-4 text-4xl">💬</div>
            <p className="mb-2 text-lg font-medium text-gray-300">
              Ask anything about{" "}
              <span className="text-white">{project?.repo_name}</span>
            </p>
            <p className="text-sm text-gray-500">
              How does auth work? What does X function do? Where is Y configured?
            </p>
            <div className="mt-8 flex flex-wrap justify-center gap-2">
              {starters.map((s) => (
                <button
                  key={s}
                  onClick={() => send(s)}
                  className="rounded-full border border-gray-700 px-4 py-2 text-sm text-gray-300 hover:border-indigo-500 hover:text-white transition"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        <div className="mx-auto max-w-3xl space-y-6">
          {messages.map((msg, i) => (
            <MessageBubble key={i} message={msg} onFollowUp={send} />
          ))}
          {thinking && (
            <div className="flex items-start gap-3">
              <div className="flex h-8 w-8 items-center justify-center rounded-full bg-indigo-600 text-xs font-bold text-white">
                AI
              </div>
              <div className="rounded-2xl rounded-tl-none bg-gray-800 px-4 py-3">
                <div className="flex gap-1">
                  {[0, 1, 2].map((i) => (
                    <span
                      key={i}
                      className="inline-block h-2 w-2 animate-bounce rounded-full bg-gray-400"
                      style={{ animationDelay: `${i * 0.15}s` }}
                    />
                  ))}
                </div>
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>
      </div>

      {/* Input */}
      <div className="border-t border-gray-800 px-6 py-4">
        <div className="mx-auto flex max-w-3xl gap-3">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && send(input)}
            placeholder="Ask about your codebase…"
            className="flex-1 rounded-xl border border-gray-700 bg-gray-800 px-4 py-3 text-sm text-white placeholder-gray-500 focus:border-indigo-500 focus:outline-none"
          />
          <button
            onClick={() => send(input)}
            disabled={!input.trim() || thinking}
            className="rounded-xl bg-indigo-600 px-5 py-3 text-sm font-semibold text-white hover:bg-indigo-500 disabled:opacity-40 transition"
          >
            Send
          </button>
        </div>
      </div>
    </div>
  );
}

function MessageBubble({
  message,
  onFollowUp,
}: {
  message: Message;
  onFollowUp: (q: string) => void;
}) {
  const isUser = message.role === "user";
  return (
    <div className={`flex items-start gap-3 ${isUser ? "flex-row-reverse" : ""}`}>
      <div
        className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-xs font-bold ${
          isUser ? "bg-gray-700 text-gray-300" : "bg-indigo-600 text-white"
        }`}
      >
        {isUser ? "U" : "AI"}
      </div>
      <div className={`max-w-[80%] space-y-2 ${isUser ? "items-end" : ""}`}>
        <div
          className={`rounded-2xl px-4 py-3 text-sm leading-relaxed ${
            isUser
              ? "rounded-tr-none bg-indigo-600 text-white"
              : "rounded-tl-none bg-gray-800 text-gray-100"
          }`}
        >
          <pre className="whitespace-pre-wrap font-sans">{message.content}</pre>
        </div>

        {message.citations && message.citations.length > 0 && (
          <div className="rounded-xl border border-gray-700 bg-gray-900 px-3 py-2">
            <p className="mb-1 text-xs font-medium text-gray-400">Sources</p>
            <ul className="space-y-1">
              {message.citations.map((c, i) => (
                <li key={i} className="text-xs text-indigo-400">
                  · {c}
                </li>
              ))}
            </ul>
          </div>
        )}

        {message.confidence != null && (
          <div className="flex items-center gap-2 text-xs text-gray-500">
            <span>Confidence: {Math.round(message.confidence * 100)}%</span>
            {message.latency_ms && <span>· {message.latency_ms}ms</span>}
          </div>
        )}

        {message.follow_ups && message.follow_ups.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {message.follow_ups.map((q, i) => (
              <button
                key={i}
                onClick={() => onFollowUp(q)}
                className="rounded-full border border-gray-700 px-3 py-1 text-xs text-gray-400 hover:border-indigo-500 hover:text-white transition"
              >
                {q}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

const starters = [
  "How does authentication work?",
  "Explain the project structure",
  "What are the main API endpoints?",
  "How is data stored?",
];
