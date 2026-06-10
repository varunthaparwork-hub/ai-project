# graph/formatter.py
# The formatter node runs AFTER action_executor (or after HITL if execution was skipped).
#
# Responsibility:
#   Take the free-text synthesis_draft + execution results already in state
#   and ask the LLM to produce a fully structured OpsResponse Pydantic object.
#
# Why a separate node instead of doing this inside synthesis?
#   - Synthesis is already doing heavy reasoning. Asking it to also
#     produce a strict JSON schema at the same time increases errors.
#   - Formatter is a cheap extraction pass: it reads finished text → structured data.
#   - Execution results are only available AFTER the executor runs,
#     so the formatter must come last anyway.

from datetime import date

from agents.base import llm
from graph.state import OpsState
from schemas.outputs import OpsResponse, ExecutionSummary


# ──────────────────────────────────────────────────────────────────
# Formatter node
# ──────────────────────────────────────────────────────────────────

def formatter_node(state: OpsState) -> OpsState:
    """
    Extracts structured OpsResponse from the completed state.

    Reads:  synthesis_draft, final_answer, execution_results, past_incidents,
            target_date, comparison_date, proposed_actions, approved_actions
    Writes: structured_output (serialised OpsResponse as dict)
    """
    print("\n[FORMATTER] Building structured output...")

    # ── Build execution summary from state ────────────────────────
    if not state.get("skip_execution"):
        proposed  = state.get("proposed_actions") or []
        approved  = state.get("approved_actions") or []
        results   = state.get("execution_results") or []
        succeeded = [r for r in results if r.get("status") == "success"]
        failed    = [r for r in results if r.get("status") == "error"]

        execution_summary_dict = {
            "total_proposed": len(proposed),
            "total_approved": len(approved),
            "total_executed": len(succeeded),
            "total_failed":   len(failed),
            "report":         state.get("execution_report"),
        }
    else:
        execution_summary_dict = None

    # ── Past incidents for prompt ─────────────────────────────────
    raw_incidents = state.get("past_incidents") or []
    if raw_incidents:
        incidents_text = "\n".join([
            f"- Date: {inc['date']}, Score: {inc.get('similarity_score', '?')}, "
            f"What happened: {inc['description']}, "
            f"Outcome: {inc['outcome']}"
            for inc in raw_incidents
        ])
    else:
        incidents_text = "None"

    # ── Execution text for prompt ─────────────────────────────────
    if execution_summary_dict:
        exec_text = (
            f"Proposed: {execution_summary_dict['total_proposed']}, "
            f"Approved: {execution_summary_dict['total_approved']}, "
            f"Executed: {execution_summary_dict['total_executed']}, "
            f"Failed: {execution_summary_dict['total_failed']}. "
            f"Report: {execution_summary_dict.get('report') or 'N/A'}"
        )
    else:
        exec_text = "Execution was skipped (user rejected all actions or no actions proposed)."

    # ── Build LLM extraction prompt ───────────────────────────────
    prompt = f"""You are a data extraction assistant. 
Read the operations analysis below and extract ALL fields into the required JSON schema.
Do not invent data — only use what is present in the analysis text.

TODAY'S DATE: {date.today().isoformat()}
TARGET DATE ANALYSED: {state.get("target_date") or "not specified"}
COMPARISON DATE: {state.get("comparison_date") or "not specified"}

ANALYSIS TEXT:
{state.get("final_answer") or state.get("synthesis_draft") or "No analysis available."}

PAST INCIDENTS RETRIEVED FROM MEMORY:
{incidents_text}

EXECUTION SUMMARY:
{exec_text}

ORIGINAL USER QUESTION: {state["user_question"]}

Instructions:
- one_liner: single sentence capturing the single most important finding
- severity: one of critical / high / medium / low
- root_causes: list each root cause with rank (1=highest impact), domain, evidence
- recommended_actions: extract every numbered action; set is_executable=true only for 
  actions that mention restocking, applying a discount, resuming/pausing a campaign, 
  or creating a support ticket
- historical_references: ONLY include past incidents that are DIRECTLY relevant to the
  current situation AND have similarity >= 0.50. If an incident is about a completely
  different problem (e.g. current issue is overstock but incident is about a campaign
  budget), leave historical_references empty. Quality over quantity — 0 is better than
  3 irrelevant entries.
- execution_summary: populate from the EXECUTION SUMMARY section above (null if skipped)
- full_analysis_markdown: copy the ANALYSIS TEXT verbatim
"""

    # ── Call LLM with structured output ──────────────────────────
    structured_llm = llm.with_structured_output(OpsResponse, method="function_calling")

    try:
        ops_response: OpsResponse = structured_llm.invoke(prompt)
        # Inject fields that the LLM can't reliably fill from text
        ops_response.session_date     = date.today().isoformat()
        ops_response.target_date      = state.get("target_date") or date.today().isoformat()
        ops_response.comparison_date  = state.get("comparison_date") or None
        ops_response.full_analysis_markdown = (
            state.get("final_answer") or state.get("synthesis_draft")
        )
        if execution_summary_dict:
            ops_response.execution_summary = ExecutionSummary(**execution_summary_dict)

        print(f"[FORMATTER] Structured output built. "
              f"Severity={ops_response.severity.value}, "
              f"RootCauses={len(ops_response.root_causes)}, "
              f"Actions={len(ops_response.recommended_actions)}")

        return {**state, "structured_output": ops_response.model_dump(mode="json")}

    except Exception as e:
        print(f"[FORMATTER] ERROR: Structured output extraction failed ({type(e).__name__}: {e}). Retrying with simplified prompt...")

        # Log formatter failure for observability
        try:
            from observability.tracker import tracker
            tracker.log_formatter_error(exception=str(e), attempt="first_pass", retry_planned=True)
        except Exception:
            pass  # tracker may not be available in all contexts

        # RETRY ONCE with simplified prompt focusing on critical fields only
        simplified_prompt = f"""Extract ONLY the most critical fields from this analysis:
- one_liner: single sentence, most important finding
- severity: critical / high / medium / low
- root_causes: list each as "{{rank}}: {{domain}}: {{cause}}"
- recommended_actions: list each as "{{action description}}"

ANALYSIS:
{state.get("final_answer") or state.get("synthesis_draft") or "No analysis available."}

If you cannot extract structured data, return empty lists for root_causes and recommended_actions."""

        try:
            ops_response_retry: OpsResponse = structured_llm.invoke(simplified_prompt)
            ops_response_retry.session_date = date.today().isoformat()
            ops_response_retry.target_date = state.get("target_date") or date.today().isoformat()
            ops_response_retry.comparison_date = state.get("comparison_date") or None
            ops_response_retry.full_analysis_markdown = (
                state.get("final_answer") or state.get("synthesis_draft")
            )
            if execution_summary_dict:
                ops_response_retry.execution_summary = ExecutionSummary(**execution_summary_dict)

            print(f"[FORMATTER] Retry succeeded. Severity={ops_response_retry.severity.value}, "
                  f"RootCauses={len(ops_response_retry.root_causes)}")

            # Log retry success for observability
            try:
                from observability.tracker import tracker
                tracker.log_formatter_error(exception=None, attempt="retry", fallback_used=False)
            except Exception:
                pass

            return {**state, "structured_output": ops_response_retry.model_dump(mode="json")}

        except Exception as retry_error:
            print(f"[FORMATTER] Retry also failed ({type(retry_error).__name__}). Using fallback with extracted summary.")

            # Log retry failure for observability
            try:
                from observability.tracker import tracker
                tracker.log_formatter_error(exception=str(retry_error), attempt="retry", fallback_used=True)
            except Exception:
                pass

            # Extract first line of analysis as one_liner if available
            analysis_text = state.get("final_answer") or state.get("synthesis_draft") or ""
            first_line = (analysis_text.split("\n")[0] or "No analysis available.")[:200]

            fallback = {
                "session_date":             date.today().isoformat(),
                "target_date":              state.get("target_date") or "",
                "comparison_date":          state.get("comparison_date"),
                "one_liner":                first_line,
                "severity":                 "high",  # default to high to flag for manual review
                "summary":                  state.get("final_answer") or state.get("synthesis_draft") or "",
                "root_causes":              [],
                "recommended_actions":      [],
                "cross_domain_correlations": None,
                "historical_references":    [],
                "execution_summary":        execution_summary_dict,
                "full_analysis_markdown":   state.get("final_answer") or state.get("synthesis_draft"),
            }
            return {**state, "structured_output": fallback}
