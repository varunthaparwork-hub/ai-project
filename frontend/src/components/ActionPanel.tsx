import { useState } from "react";
import type { ProposedAction } from "../types/ops";
import { approveActions } from "../api/client";

interface Props {
  threadId: string;
  actions: ProposedAction[];
  onDone: (report: string) => void;
}

export default function ActionPanel({ threadId, actions, onDone }: Props) {
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [loading, setLoading] = useState(false);

  const toggle = (id: number) =>
    setSelected((prev) => {
      const s = new Set(prev);
      s.has(id) ? s.delete(id) : s.add(id);
      return s;
    });

  const submit = async () => {
    if (!selected.size) return;
    setLoading(true);
    try {
      const res = await approveActions(threadId, [...selected]);
      onDone(res.execution_report ?? "Done.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="border border-amber-800 bg-amber-950/40 rounded-xl p-4 space-y-3">
      <h3 className="font-semibold text-amber-300 flex items-center gap-2 text-sm">
        <span>⚠️</span>
        Action Approval Required
      </h3>

      <ul className="space-y-2">
        {actions.map((a) => (
          <li
            key={a.action_id}
            onClick={() => toggle(a.action_id)}
            className={`flex items-start gap-3 rounded-lg p-3 cursor-pointer transition-colors border ${
              selected.has(a.action_id)
                ? "bg-amber-900/50 border-amber-700"
                : "bg-gray-900 border-gray-700 hover:border-amber-800 hover:bg-gray-800"
            }`}
          >
            {/* custom checkbox */}
            <div
              className={`mt-0.5 w-4 h-4 rounded border-2 flex items-center justify-center shrink-0 transition-colors ${
                selected.has(a.action_id)
                  ? "bg-amber-500 border-amber-500"
                  : "border-gray-600"
              }`}
            >
              {selected.has(a.action_id) && (
                <span className="text-white text-xs leading-none font-bold">✓</span>
              )}
            </div>
            <div>
              <p className="text-sm font-medium text-gray-200">{a.description}</p>
              <p className="text-xs text-gray-500 mt-0.5">
                Tool: {a.tool_name} &middot; Impact: {a.estimated_impact}
              </p>
            </div>
          </li>
        ))}
      </ul>

      <div className="flex gap-2 pt-1">
        <button
          onClick={() => setSelected(new Set(actions.map((a) => a.action_id)))}
          className="text-xs px-3 py-1.5 rounded-lg bg-gray-800 text-gray-300 hover:bg-gray-700 border border-gray-700 transition-colors"
        >
          Select All
        </button>
        <button
          onClick={submit}
          disabled={!selected.size || loading}
          className="text-xs px-4 py-1.5 rounded-lg bg-green-700 text-white hover:bg-green-600 disabled:opacity-40 transition-colors font-medium"
        >
          {loading
            ? "Executing…"
            : `Approve ${selected.size} action${selected.size !== 1 ? "s" : ""}`}
        </button>
      </div>
    </div>
  );
}
