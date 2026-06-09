interface NodeEvent {
  name: string;
  label: string;
  icon: string;
  preview: string;
  status: "done" | "running";
}

export default function PipelineProgress({ nodes }: { nodes: NodeEvent[] }) {
  if (nodes.length === 0) return null;
  return (
    <div className="space-y-1.5">
      {nodes.map((n, i) => (
        <div
          key={i}
          className={`flex items-start gap-3 px-4 py-2.5 rounded-lg text-sm transition-all duration-300 ${
            n.status === "running"
              ? "bg-blue-950 border border-blue-700"
              : "bg-gray-900 border border-gray-800"
          }`}
        >
          <span className="text-base mt-0.5 shrink-0">{n.icon}</span>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <span
                className={`font-semibold text-sm ${
                  n.status === "running" ? "text-blue-300" : "text-gray-300"
                }`}
              >
                {n.label}
              </span>
              {n.status === "done" && (
                <span className="text-green-400 text-xs font-bold">✓</span>
              )}
              {n.status === "running" && (
                <span className="flex gap-0.5 items-center">
                  <span className="w-1 h-1 bg-blue-400 rounded-full animate-bounce [animation-delay:0ms]" />
                  <span className="w-1 h-1 bg-blue-400 rounded-full animate-bounce [animation-delay:150ms]" />
                  <span className="w-1 h-1 bg-blue-400 rounded-full animate-bounce [animation-delay:300ms]" />
                </span>
              )}
            </div>
            {n.preview && (
              <p className="text-gray-500 text-xs mt-0.5 truncate">{n.preview}</p>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
