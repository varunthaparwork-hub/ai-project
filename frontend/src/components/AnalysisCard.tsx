import type { StructuredOutput } from "../types/ops";
import SeverityBadge from "./SeverityBadge";
import ReactMarkdown from "react-markdown";

export default function AnalysisCard({
  data,
  markdown,
}: {
  data: StructuredOutput;
  markdown: string;
}) {
  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-start gap-3 flex-wrap">
        <SeverityBadge severity={data.severity} />
        <p className="text-gray-200 font-medium leading-snug">{data.one_liner}</p>
      </div>

      {/* Root Causes */}
      {data.root_causes.length > 0 && (
        <section>
          <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-widest mb-2">
            Root Causes
          </h3>
          <ol className="space-y-2">
            {data.root_causes.map((rc) => (
              <li
                key={rc.rank}
                className="bg-gray-800 border border-gray-700 rounded-lg p-3"
              >
                <span className="text-xs font-bold text-blue-400 uppercase">{rc.domain}</span>
                <p className="text-sm text-gray-200 mt-1">{rc.description}</p>
                <p className="text-xs text-gray-500 mt-1">Evidence: {rc.evidence}</p>
              </li>
            ))}
          </ol>
        </section>
      )}

      {/* Recommended Actions */}
      {data.recommended_actions.length > 0 && (
        <section>
          <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-widest mb-2">
            Recommended Actions
          </h3>
          <ul className="space-y-2">
            {data.recommended_actions.map((a) => (
              <li
                key={a.action_id}
                className="bg-blue-950 border border-blue-800 rounded-lg p-3 flex justify-between items-start gap-2"
              >
                <div>
                  <p className="text-sm font-semibold text-blue-200">{a.title}</p>
                  <p className="text-xs text-blue-400 mt-0.5">{a.estimated_impact}</p>
                </div>
                <div className="flex flex-col items-end gap-1 shrink-0">
                  <span className="text-xs bg-blue-900 text-blue-300 px-2 py-0.5 rounded-full">
                    {a.priority}
                  </span>
                  {a.is_executable && (
                    <span className="text-xs bg-green-900 text-green-300 px-2 py-0.5 rounded-full">
                      executable
                    </span>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Historical References — only show if similarity >= 0.70 */}
      {(() => {
        const relevant = data.historical_references.filter(
          (h) => h.similarity_score >= 0.70
        );
        if (relevant.length === 0) return null;
        return (
          <section>
            <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-widest mb-2">
              Historical References
            </h3>
            <ul className="space-y-2">
              {relevant.map((h, i) => (
                <li
                  key={i}
                  className="bg-purple-950 border border-purple-800 rounded-lg p-3"
                >
                  <div className="flex justify-between">
                    <span className="text-xs font-semibold text-purple-300">{h.incident_date}</span>
                    <span className="text-xs text-purple-500">
                      similarity: {(h.similarity_score * 100).toFixed(0)}%
                    </span>
                  </div>
                  <p className="text-sm text-purple-100 mt-1">{h.description}</p>
                  <p className="text-xs text-purple-400 mt-1">What worked: {h.what_worked}</p>
                </li>
              ))}
            </ul>
          </section>
        );
      })()}

      {/* Full markdown */}
      <details className="text-sm">
        <summary className="cursor-pointer font-medium text-gray-500 select-none hover:text-gray-300 transition-colors">
          Full Analysis ↓
        </summary>
        <div className="mt-3 text-gray-300 leading-relaxed text-sm space-y-2">
          <ReactMarkdown>{markdown}</ReactMarkdown>
        </div>
      </details>
    </div>
  );
}
