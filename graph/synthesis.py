# The synthesis node is the final node answer is returned.
# It recieves all agent findings and ask LLM to combine them 
# into one coherent explanation with root causes and recommendations. 

from langchain_core.messages import HumanMessage
from agents.base import llm
from graph.state import OpsState


SYNTHESIS_PROMPT = """You are the chief Operations AI for an e-commerce store.
You have received analysis reports from multiple specialist agents.
Your job is to synthesize them into ONE clear executive summary.

CRITICAL CONSTRAINT: Every number, product name, and key finding you cite MUST be
verbatim from the agent reports below. Do NOT invent, estimate, or extrapolate data.
If a figure does not appear in the reports, do not mention it.
If two reports contradict each other, flag the contradiction explicitly and choose
the more conservative (lowest-impact) interpretation.

GROUNDING RULES (enforce these strictly for LLM verification):
1. Every number must appear verbatim in an agent report below — never calculate or derive new numbers
2. Never invent data, fill in gaps, or estimate missing values
3. If a domain shows "Not analyzed", write that phrase exactly in your response
4. If two reports conflict on the same data point, quote both versions and flag the conflict
5. End every root cause bullet with [Source: AgentName, exact quote] — this enables the critic to verify citations

Structure your response exactly as:

## Summary
One paragraph explaining what happened overall. Only cite findings that appear in the reports.

## Root Causes
Bullet list of confirmed causes, ranked by impact. Every cause must cite the domain and the
specific evidence from the reports. Do NOT rank causes higher than the reports support.
Format each cause as: "**[DOMAIN]** [Cause description] (Evidence: [exact quote from report])"

## SOURCE CITATION RULES (CRITICAL)
For every root cause you list:
1. Cite the exact domain that reported it (SALES / INVENTORY / MARKETING / SUPPORT)
2. Include the exact quote or specific number from that domain's report
3. If you must paraphrase, wrap it in [paraphrased:...] and cite the original quote
4. If a finding appears in multiple domains, cite all of them
5. If a cause cannot be traced to any report, DO NOT include it — flag it under Contradictions instead

Example correct format:
- **[SALES]** Revenue dropped 40% (Evidence: "Q2 revenue fell from $50K to $30K")

Example WRONG format (DO NOT do this):
- Revenue appears to be down (no domain, no numbers, no source)
- It seems sales were affected (vague paraphrase without original quote)

## Supporting Evidence
Key data points from each domain that support your conclusions. Quote figures directly.
If a domain says "Not analyzed", explicitly note that its findings are unavailable.
Do NOT speculate about unanalyzed domains.

## Cross-Domain Correlations
Explain how findings across domains connect (e.g., stock outage + campaign paused + complaints spike).
ONLY claim correlations if the reports explicitly state them or if the logical connection is obvious
(e.g., "Stockout reported AND zero sales reported" = obvious correlation). Do NOT infer hidden causation.

## Contradictions and Gaps
If different agents reported contradictory data (e.g., Sales says $1,000 in lost revenue but
Inventory says no stockouts occurred), list them here and flag for manual review.
Do NOT hide contradictions or pick one report's numbers arbitrarily.

## Historical Context
If past incidents are provided below, reference them here.
Explain if this has happened before and what worked or didn't work.
If no past incidents, write: No similar past incidents found.

## Recommended Actions
Numbered list of specific actions with reasoning. Each action must be grounded in a root cause
from the reports. Do NOT recommend actions that are not supported by the data.

---
Reports from specialist agents:

SALES ANALYSIS:
{sales}

INVENTORY ANALYSIS:
{inventory}

MARKETING ANALYSIS:
{marketing}

CUSTOMER SUPPORT ANALYSIS:
{support}

PAST SIMILAR INCIDENTS FROM MEMORY:
{past_incidents}

Original User Question: {question}
"""

REVISION_PROMPT = """You are the Chief Operations AI for an e-commerce store.
You wrote an analysis draft that was reviewed by a critic.
Revise your draft by addressing every point in the critic's feedback.

ORIGINAL AGENT REPORTS — use these as your only source of truth for numbers and facts.
Do not cite any figure that does not appear in these reports:

SALES ANALYSIS:
{sales}

INVENTORY ANALYSIS:
{inventory}

MARKETING ANALYSIS:
{marketing}

CUSTOMER SUPPORT ANALYSIS:
{support}

PAST SIMILAR INCIDENTS FROM MEMORY:
{past_incidents}

## Your Previous Draft:
{draft}

## Critic Feedback:
{feedback}

Rewrite the analysis using ONLY data from the agent reports above.
Every root cause and number must be traceable to those reports.

REVISION CITATION RULES (CRITICAL):
For every root cause you revise:
1. Cite the exact domain (SALES / INVENTORY / MARKETING / SUPPORT)
2. Include the exact quote or specific number from that domain's report
3. Do NOT add new claims without evidence from the reports
4. If the critic flagged a claim as unsourced, remove it or cite a specific report line
5. If multiple domains support a cause, cite all of them

## Summary
## Root Causes
## Supporting Evidence
## Cross-Domain Correlations
## Historical Context
## Recommended Actions
"""

def synthesis_node(state: OpsState) -> OpsState:
    # Second pass - critic found issues , revise the draft
    if state.get("critic_feedback") and state.get("needs_revision"):
        print("\n[SYNTHESIS] Revising draft based on critic feedback....")
        raw_incidents = state.get("past_incidents") or []
        incidents_text = (
            "\n\n".join([
                f"Incident {i+1} ({inc['date']}):\n"
                f"  What happened: {inc['description']}\n"
                f"  Root causes: {', '.join(inc.get('root_causes', []))}\n"
                f"  Actions taken: {', '.join(inc.get('actions_taken', []))}\n"
                f"  Outcome: {inc['outcome']}"
                for i, inc in enumerate(raw_incidents)
            ])
            if raw_incidents else "No similar past incidents found."
        )
        prompt = REVISION_PROMPT.format(
            draft          = state.get("synthesis_draft"),
            feedback       = state.get("critic_feedback"),
            sales          = state.get("sales_analysis")     or "Not analyzed",
            inventory      = state.get("inventory_analysis") or "Not analyzed",
            marketing      = state.get("marketing_analysis") or "Not analyzed",
            support        = state.get("support_analysis")   or "Not analyzed",
            past_incidents = incidents_text,
        )
        response = llm.invoke([HumanMessage(content=prompt)])
        return {**state , "synthesis_draft":response.content}

    # Shortcut: if no agents ran this is a direct action command, not an analysis request.
    # Return a minimal acknowledged draft instead of hallucinating from empty reports.
    all_skipped = not any([
        state.get("sales_analysis"), state.get("inventory_analysis"),
        state.get("marketing_analysis"), state.get("support_analysis"),
    ])
    if all_skipped:
        user_q = state.get("user_question", "")
        print("\n[SYNTHESIS] No agent data — direct command, bypassing LLM synthesis.")
        return {**state, "synthesis_draft": (
            f"## Summary\nDirect operational command received: '{user_q}'. "
            f"No analysis required — proceeding to action execution.\n\n"
            f"## Root Causes\nN/A — this is a user-initiated operational command.\n\n"
            f"## Recommended Actions\n1. Execute as requested: {user_q}"
        )}

    # SIMPLE QUERY DETECTION: If user is just asking for current status/data (not analysis),
    # and only ONE agent ran, answer directly without the full synthesis framework
    agent_count = sum([
        bool(state.get("sales_analysis")),
        bool(state.get("inventory_analysis")),
        bool(state.get("marketing_analysis")),
        bool(state.get("support_analysis")),
    ])

    user_q = state.get("user_question", "").lower()
    is_simple_query = any(kw in user_q for kw in [
        "current", "status", "what is", "how many", "inventory", "stock",
        "how much", "list", "show", "get", "check", "what's", "what are"
    ]) and "?" in user_q and "why" not in user_q and "how did" not in user_q

    if is_simple_query and agent_count == 1:
        print(f"\n[SYNTHESIS] Simple query detected — answering directly without full analysis framework.")
        # Just return the agent's findings directly
        if state.get("inventory_analysis"):
            return {**state, "synthesis_draft": state["inventory_analysis"]}
        elif state.get("sales_analysis"):
            return {**state, "synthesis_draft": state["sales_analysis"]}
        elif state.get("marketing_analysis"):
            return {**state, "synthesis_draft": state["marketing_analysis"]}
        elif state.get("support_analysis"):
            return {**state, "synthesis_draft": state["support_analysis"]}

    # First pass - produce initial draft from agent reports
    print("\n[SYNTHESIS] Producing initial draft....")

    # Format past incidents into readable text for the prompt
    raw_incidents = state.get("past_incidents") or []
    if raw_incidents:
        incidents_text = "\n\n".join([
            f"Incident {i+1} ({inc['date']}, similarity: {inc.get('similarity_score', '?')}):\n"
            f"  What happened: {inc['description']}\n"
            f"  Root causes: {', '.join(inc.get('root_causes', []))}\n"
            f"  Actions taken: {', '.join(inc.get('actions_taken', []))}\n"
            f"  Outcome: {inc['outcome']}\n"
            f"  Resolved in: {inc.get('resolution_time_days', '?')} day(s)"
            for i, inc in enumerate(raw_incidents)
        ])
    else:
        incidents_text = "No similar past incidents found in memory."

    prompt = SYNTHESIS_PROMPT.format(
        sales          = state.get("sales_analysis")     or "Not analyzed",
        inventory      = state.get("inventory_analysis") or "Not analyzed",
        marketing      = state.get("marketing_analysis") or "Not analyzed",
        support        = state.get("support_analysis")   or "Not analyzed",
        past_incidents = incidents_text,
        question       = state["user_question"],
    )
    response = llm.invoke([HumanMessage(content=prompt)])
    return {**state, "synthesis_draft": response.content}

