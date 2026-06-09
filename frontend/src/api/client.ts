import axios from "axios";
import type { AnalyzeResponse, ObsStats, ChatThread, ChatMessagesResponse } from "../types/ops";

const http = axios.create({ baseURL: "/" });

export async function analyze(
  question: string,
  targetDate: string,
  comparisonDate: string,
  threadId?: string
): Promise<AnalyzeResponse> {
  const { data } = await http.post<AnalyzeResponse>("/api/analyze", {
    question,
    target_date: targetDate,
    comparison_date: comparisonDate,
    ...(threadId ? { thread_id: threadId } : {}),
  });
  return data;
}

export type StreamEvent =
  | { type: "node"; name: string; label: string; icon: string; preview: string }
  | { type: "done"; final: string; structured_output: AnalyzeResponse["structured_output"]; proposed_actions: AnalyzeResponse["proposed_actions"]; thread_id: string; history: AnalyzeResponse["history"] }
  | { type: "error"; message: string };

export function analyzeStream(
  question: string,
  targetDate: string,
  comparisonDate: string,
  threadId: string | undefined,
  onEvent: (e: StreamEvent) => void
): () => void {
  const body = JSON.stringify({
    question,
    target_date: targetDate,
    comparison_date: comparisonDate,
    ...(threadId ? { thread_id: threadId } : {}),
  });

  let aborted = false;
  const controller = new AbortController();

  (async () => {
    try {
      const res = await fetch("/api/analyze/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body,
        signal: controller.signal,
      });

      const reader = res.body!.getReader();
      const decoder = new TextDecoder();
      let buf = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done || aborted) break;
        buf += decoder.decode(value, { stream: true });
        const lines = buf.split("\n");
        buf = lines.pop() ?? "";
        for (const line of lines) {
          if (line.startsWith("data: ")) {
            try {
              const event = JSON.parse(line.slice(6)) as StreamEvent;
              onEvent(event);
            } catch { /* ignore parse errors */ }
          }
        }
      }
    } catch (e) {
      if (!aborted) onEvent({ type: "error", message: String(e) });
    }
  })();

  return () => { aborted = true; controller.abort(); };
}

export async function approveActions(
  threadId: string,
  approvedActionIds: number[]
): Promise<{ execution_report: string | null }> {
  const { data } = await http.post("/api/actions/approve", {
    thread_id: threadId,
    approved_action_ids: approvedActionIds,
  });
  return data;
}

export async function getObsStats(): Promise<ObsStats> {
  const { data } = await http.get<ObsStats>("/api/observability");
  return data;
}

export async function listChats(): Promise<ChatThread[]> {
  const { data } = await http.get<ChatThread[]>("/api/chats");
  return data;
}

export async function loadChatMessages(threadId: string): Promise<ChatMessagesResponse> {
  const { data } = await http.get<ChatMessagesResponse>(`/api/chats/${threadId}/messages`);
  return data;
}

export async function deleteChat(threadId: string): Promise<void> {
  await http.delete(`/api/chats/${threadId}`);
}
