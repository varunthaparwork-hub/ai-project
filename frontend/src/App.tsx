import { useEffect, useRef, useState } from "react";
import { analyzeStream, loadChatMessages } from "./api/client";
import type { StreamEvent } from "./api/client";
import type { StructuredOutput, ProposedAction } from "./types/ops";
import AnalysisCard from "./components/AnalysisCard";
import ActionPanel from "./components/ActionPanel";
import ChatSidebar from "./components/ChatSidebar";
import PipelineProgress from "./components/PipelineProgress";
import ReactMarkdown from "react-markdown";

type NodeState = {
  name: string; label: string; icon: string; preview: string;
  status: "done" | "running";
};

type ConvMessage =
  | { role: "user"; content: string }
  | { role: "assistant"; content: string; structured: StructuredOutput | null;
      proposed_actions: ProposedAction[]; thread_id: string };

const HINTS = [
  "Why did revenue drop on June 1?",
  "What\u2019s causing high support ticket volume?",
  "Which products are critically overstocked?",
];

export default function App() {
  const [activeThreadId, setActiveThreadId] = useState<string>(() => crypto.randomUUID());
  const [refreshChats, setRefreshChats]     = useState(0);
  const [question, setQuestion]             = useState("");
  const [streaming, setStreaming]           = useState(false);
  const [nodes, setNodes]                   = useState<NodeState[]>([]);
  const [messages, setMessages]             = useState<ConvMessage[]>([]);
  const [latestActions, setLatestActions]   = useState<{ threadId: string; actions: ProposedAction[] } | null>(null);
  const [execReport, setExecReport]         = useState<string | null>(null);
  const [error, setError]                   = useState<string | null>(null);  const [loadingChat, setLoadingChat]   = useState(false);  const cancelRef = useRef<(() => void) | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);

  // Auto-scroll to bottom when content changes
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length, nodes.length]);

  // ── New chat ──────────────────────────────────────────────────────────────
  const newChat = () => {
    cancelRef.current?.();
    setActiveThreadId(crypto.randomUUID());
    setMessages([]);
    setLatestActions(null);
    setExecReport(null);
    setNodes([]);
    setError(null);
    setQuestion("");
    setStreaming(false);
  };

  // ── Load a previous chat ──────────────────────────────────────────────────
  const selectChat = async (threadId: string) => {
    if (threadId === activeThreadId && messages.length > 0) return;
    cancelRef.current?.();
    setStreaming(false);
    setNodes([]);
    setError(null);
    setLatestActions(null);
    setExecReport(null);
    setMessages([]);           // clear immediately so UI shows loading state
    setActiveThreadId(threadId);
    setLoadingChat(true);
    try {
      const data = await loadChatMessages(threadId);
      console.log(`[selectChat] Loaded ${data.messages.length} message(s) for ${threadId}`);
      setMessages(
        data.messages.map((m) =>
          m.role === "user"
            ? { role: "user" as const, content: m.content }
            : {
                role: "assistant" as const,
                content: m.content,
                structured: (m.structured_output as StructuredOutput) ?? null,
                proposed_actions: [],
                thread_id: threadId,
              }
        )
      );
    } catch (err) {
      console.error("[selectChat] Failed to load messages:", err);
      setError("Could not load chat history. Check the API is running.");
      setMessages([]);
    } finally {
      setLoadingChat(false);
    }
  };

  // ── Submit question ───────────────────────────────────────────────────────
  const submit = () => {
    const q = question.trim();
    if (!q || streaming) return;
    setQuestion("");
    setError(null);
    setExecReport(null);
    setLatestActions(null);
    setStreaming(true);
    setNodes([]);
    // Append user bubble immediately
    setMessages((prev) => [...prev, { role: "user" as const, content: q }]);

    cancelRef.current = analyzeStream(q, "", "", activeThreadId, (e: StreamEvent) => {
      if (e.type === "node") {
        setNodes((prev) => [
          ...prev.map((n) => ({ ...n, status: "done" as const })),
          { name: e.name, label: e.label, icon: e.icon, preview: e.preview, status: "running" as const },
        ]);
      } else if (e.type === "done") {
        setNodes((prev) => prev.map((n) => ({ ...n, status: "done" as const })));
        setMessages((prev) => [
          ...prev,
          {
            role: "assistant" as const,
            content: e.final,
            structured: e.structured_output ?? null,
            proposed_actions: e.proposed_actions,
            thread_id: e.thread_id,
          },
        ]);
        if (e.proposed_actions.length > 0) {
          setLatestActions({ threadId: e.thread_id, actions: e.proposed_actions });
        }
        setStreaming(false);
        setTimeout(() => setNodes([]), 1500);
        setRefreshChats((n) => n + 1);   // trigger sidebar refresh
      } else if (e.type === "error") {
        setError(e.message);
        setStreaming(false);
        setNodes((prev) => prev.map((n) => ({ ...n, status: "done" as const })));
        setTimeout(() => setNodes([]), 1500);
      }
    });
  };

  const cancel = () => {
    cancelRef.current?.();
    setStreaming(false);
    setNodes([]);
  };

  return (
    <div className="flex h-screen bg-gray-950 text-gray-100 font-sans antialiased">

      {/* ── Sidebar ── */}
      <aside className="w-64 bg-gray-900 border-r border-gray-800 flex flex-col shrink-0">
        <div className="p-4 border-b border-gray-800 shrink-0">
          <div className="flex items-center gap-2 mb-0.5">
            <span className="text-base">&#128722;</span>
            <h1 className="font-bold text-gray-100 text-sm tracking-tight">AI Ops Manager</h1>
          </div>
          <p className="text-xs text-gray-500 pl-6">E-Commerce Intelligence</p>
        </div>
        <ChatSidebar
          activeThreadId={activeThreadId}
          onSelect={selectChat}
          onNew={newChat}
          refreshTrigger={refreshChats}
        />
      </aside>

      {/* ── Main ── */}
      <main className="flex-1 flex flex-col overflow-hidden">

        {/* Conversation area */}
        <div className="flex-1 overflow-y-auto">
          <div className="max-w-3xl mx-auto px-6 py-6 space-y-5">

            {/* Loading previous chat */}
            {loadingChat && (
              <div className="flex justify-center py-16">
                <span className="flex gap-1 items-center text-gray-600 text-xs">
                  <span className="w-1.5 h-1.5 bg-gray-500 rounded-full animate-bounce [animation-delay:0ms]" />
                  <span className="w-1.5 h-1.5 bg-gray-500 rounded-full animate-bounce [animation-delay:150ms]" />
                  <span className="w-1.5 h-1.5 bg-gray-500 rounded-full animate-bounce [animation-delay:300ms]" />
                </span>
              </div>
            )}

            {/* Empty state */}
            {messages.length === 0 && !streaming && !error && !loadingChat && (
              <div className="flex flex-col items-center justify-center mt-20 text-center select-none">
                <div className="text-6xl mb-5">&#128722;</div>
                <h2 className="text-gray-400 font-semibold text-lg mb-2">What would you like to analyse?</h2>
                <p className="text-gray-600 text-sm max-w-md leading-relaxed">
                  Ask about revenue drops, inventory shortfalls, marketing performance, or support trends.
                </p>
                <div className="mt-5 flex flex-wrap gap-2 justify-center max-w-lg">
                  {HINTS.map((hint) => (
                    <button
                      key={hint}
                      onClick={() => setQuestion(hint)}
                      className="text-xs bg-gray-800 hover:bg-gray-700 border border-gray-700
                        text-gray-400 hover:text-gray-200 rounded-full px-3 py-1.5 transition-colors"
                    >
                      {hint}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Error banner */}
            {error && (
              <div className="bg-red-950/60 border border-red-800 text-red-300 rounded-xl p-4 text-sm flex items-start gap-2">
                <span className="text-red-400 font-bold shrink-0">&#10005;</span>
                {error}
              </div>
            )}

            {/* Message thread */}
            {messages.map((msg, i) => {
              if (msg.role === "user") {
                return (
                  <div key={i} className="flex justify-end">
                    <div className="bg-blue-600 text-white rounded-2xl rounded-tr-sm
                      px-4 py-2.5 max-w-[80%] text-sm leading-relaxed whitespace-pre-wrap">
                      {msg.content}
                    </div>
                  </div>
                );
              }

              // Assistant message — show AnalysisCard or plain markdown
              const isLatest = i === messages.length - 1 && !streaming;
              return (
                <div key={i} className="space-y-3">
                  {msg.structured ? (
                    <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
                      <AnalysisCard data={msg.structured} markdown={msg.content} />
                    </div>
                  ) : (
                    <div className="bg-gray-900 border border-gray-800 rounded-xl p-5
                      text-sm text-gray-300 leading-relaxed">
                      <ReactMarkdown>{msg.content}</ReactMarkdown>
                    </div>
                  )}

                  {/* HITL approval — only shown for the latest message */}
                  {isLatest && latestActions && !execReport && (
                    <ActionPanel
                      threadId={latestActions.threadId}
                      actions={latestActions.actions}
                      onDone={setExecReport}
                    />
                  )}

                  {/* Execution report */}
                  {isLatest && execReport && (
                    <div className="bg-green-950 border border-green-800 rounded-xl p-4
                      text-sm text-green-300 whitespace-pre-wrap">
                      <p className="font-semibold text-green-400 mb-2">&#10003; Execution Report</p>
                      {execReport}
                    </div>
                  )}
                </div>
              );
            })}

            {/* Pipeline thinking panel (live during streaming) */}
            {nodes.length > 0 && (
              <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
                <div className="flex items-center justify-between px-4 py-2.5 border-b border-gray-800">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-semibold text-gray-500 uppercase tracking-widest">
                      Thinking
                    </span>
                    {streaming ? (
                      <span className="flex gap-0.5">
                        <span className="w-1 h-1 bg-blue-400 rounded-full animate-bounce [animation-delay:0ms]" />
                        <span className="w-1 h-1 bg-blue-400 rounded-full animate-bounce [animation-delay:150ms]" />
                        <span className="w-1 h-1 bg-blue-400 rounded-full animate-bounce [animation-delay:300ms]" />
                      </span>
                    ) : (
                      <span className="text-xs text-green-500 font-medium">&#10003; complete</span>
                    )}
                  </div>
                  <span className="text-xs text-gray-600">{nodes.length} steps</span>
                </div>
                <div className="p-3">
                  <PipelineProgress nodes={nodes} />
                </div>
              </div>
            )}

            <div ref={bottomRef} />
          </div>
        </div>

        {/* ── Input bar at bottom ── */}
        <div className="bg-gray-900/80 backdrop-blur border-t border-gray-800 px-4 py-3 shrink-0">
          <div className="max-w-3xl mx-auto flex gap-2 items-center">
            <input
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && submit()}
              placeholder="Ask a business question\u2026"
              disabled={streaming}
              className="flex-1 bg-gray-800 border border-gray-700 rounded-xl px-4 py-2.5 text-sm
                text-gray-100 placeholder-gray-500 focus:outline-none focus:ring-2
                focus:ring-blue-600 focus:border-transparent disabled:opacity-50 transition-all"
            />
            {streaming ? (
              <button
                onClick={cancel}
                className="px-4 py-2.5 bg-red-900 hover:bg-red-800 text-red-200 border border-red-800
                  rounded-xl text-sm font-medium transition-colors flex items-center gap-2 shrink-0"
              >
                <span className="w-2 h-2 bg-red-400 rounded-full animate-pulse" />
                Stop
              </button>
            ) : (
              <button
                onClick={submit}
                disabled={!question.trim()}
                className="px-5 py-2.5 bg-blue-600 hover:bg-blue-500 text-white rounded-xl text-sm
                  font-semibold disabled:opacity-30 disabled:cursor-not-allowed transition-colors shrink-0"
              >
                Ask
              </button>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
