import type { Severity } from "../types/ops";

const MAP: Record<Severity, { ring: string; text: string; dot: string }> = {
  critical: { ring: "border-red-700 bg-red-950",       text: "text-red-400",    dot: "bg-red-500"    },
  high:     { ring: "border-orange-700 bg-orange-950", text: "text-orange-400", dot: "bg-orange-500" },
  medium:   { ring: "border-yellow-700 bg-yellow-950", text: "text-yellow-400", dot: "bg-yellow-500" },
  low:      { ring: "border-green-700 bg-green-950",   text: "text-green-400",  dot: "bg-green-500"  },
};

export default function SeverityBadge({ severity }: { severity: Severity }) {
  const c = MAP[severity] ?? MAP.low;
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full border
        text-xs font-semibold uppercase tracking-wide ${c.ring} ${c.text}`}
    >
      <span className={`w-1.5 h-1.5 rounded-full ${c.dot}`} />
      {severity}
    </span>
  );
}
