export type Severity = "critical" | "high" | "medium" | "low";
export type ActionPriority = "immediate" | "high" | "medium" | "low";
export type ActionCategory = "inventory" | "marketing" | "pricing" | "support" | "operations" | "analytics";

export interface RootCause {
  rank: number;
  description: string;
  domain: string;
  evidence: string;
}

export interface RecommendedAction {
  action_id: string;
  title: string;
  description: string;
  category: ActionCategory;
  priority: ActionPriority;
  estimated_impact: string;
  is_executable: boolean;
}

export interface HistoricalReference {
  incident_date: string;
  description: string;
  similarity_score: number;
  what_worked: string;
  outcome: string;
}

export interface StructuredOutput {
  session_date: string;
  target_date: string;
  comparison_date?: string;
  one_liner: string;
  severity: Severity;
  summary: string;
  root_causes: RootCause[];
  recommended_actions: RecommendedAction[];
  cross_domain_correlations?: string;
  historical_references: HistoricalReference[];
  full_analysis_markdown?: string;
}

export interface AnalyzeResponse {
  thread_id: string;
  final_answer: string;
  structured_output: StructuredOutput | null;
  proposed_actions: ProposedAction[];
  history: { role: string; content: string }[];
}

export interface ProposedAction {
  action_id: number;
  description: string;
  tool_name: string;
  tool_args: Record<string, unknown>;
  priority: string;
  estimated_impact: string;
}

export interface ObsStats {
  total_runs: number;
  avg_latency_ms: number;
  p95_latency_ms: number;
  avg_revisions: number;
  memory_hit_rate: number;
  exec_rate: number;
  severity_distribution: Record<string, number>;
  domain_activation: Record<string, number>;
  recent_runs: Record<string, unknown>[];
}

export interface ChatThread {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export interface ChatMessageRecord {
  role: string;
  content: string;
  structured_output?: StructuredOutput | null;
}

export interface ChatMessagesResponse {
  thread_id: string;
  messages: ChatMessageRecord[];
}