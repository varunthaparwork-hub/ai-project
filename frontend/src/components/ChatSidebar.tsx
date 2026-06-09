import { useEffect, useState } from "react";
import { listChats, deleteChat } from "../api/client";
import type { ChatThread } from "../types/ops";

interface Props {
  activeThreadId: string;
  onSelect: (threadId: string) => void;
  onNew: () => void;
  refreshTrigger: number;
}

function formatAge(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  if (diff < 60_000)        return "just now";
  if (diff < 3_600_000)     return `${Math.floor(diff / 60_000)}m ago`;
  if (diff < 86_400_000)    return `${Math.floor(diff / 3_600_000)}h ago`;
  if (diff < 604_800_000)   return `${Math.floor(diff / 86_400_000)}d ago`;
  return new Date(iso).toLocaleDateString();
}

export default function ChatSidebar({ activeThreadId, onSelect, onNew, refreshTrigger }: Props) {
  const [chats, setChats] = useState<ChatThread[]>([]);

  const load = () => listChats().then(setChats).catch(() => {});

  useEffect(() => { load(); }, [refreshTrigger]);

  const handleDelete = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    await deleteChat(id);
    load();
    if (id === activeThreadId) onNew();
  };

  return (
    <div className="flex flex-col flex-1 overflow-hidden">
      {/* New chat button */}
      <div className="p-3 shrink-0">
        <button
          onClick={onNew}
          className="w-full flex items-center justify-center gap-1.5 px-3 py-2
            bg-blue-600 hover:bg-blue-500 text-white rounded-xl text-xs font-semibold transition-colors"
        >
          <span className="text-sm font-light leading-none">+</span>
          New Chat
        </button>
      </div>

      {/* Thread list */}
      <div className="flex-1 overflow-y-auto px-2 pb-4 space-y-0.5">
        {chats.length === 0 && (
          <p className="text-xs text-gray-600 text-center py-6 italic">No conversations yet</p>
        )}
        {chats.map((chat) => {
          const turns = Math.floor(chat.message_count / 2);
          const active = chat.id === activeThreadId;
          return (
            <div
              key={chat.id}
              onClick={() => onSelect(chat.id)}
              className={`group flex items-start gap-2 px-3 py-2.5 rounded-lg cursor-pointer
                transition-colors ${active
                  ? "bg-gray-800 text-gray-100"
                  : "text-gray-400 hover:bg-gray-800/60 hover:text-gray-200"
                }`}
            >
              <span className="text-gray-600 mt-0.5 shrink-0 text-sm">&#128172;</span>
              <div className="flex-1 min-w-0">
                <p className="truncate text-xs font-medium leading-snug">{chat.title}</p>
                <p className="text-[10px] text-gray-600 mt-0.5">
                  {formatAge(chat.updated_at)}&nbsp;&middot;&nbsp;{turns} turn{turns !== 1 ? "s" : ""}
                </p>
              </div>
              <button
                onClick={(e) => handleDelete(e, chat.id)}
                className="opacity-0 group-hover:opacity-100 text-gray-600 hover:text-red-400
                  transition-all text-xs shrink-0 mt-0.5 px-0.5"
                title="Delete"
              >
                &#10005;
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}
