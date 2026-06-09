# The synthesis node is the final node answer is returned.
# It recieves all agent findings and ask LLM to combine them 
# into one coherent explanation with root causes and recommendations. 

from langchain_core.messages import HumanMessage
from agents.base import llm
from graph.state import OpsState


SYNTHESIS_PROMPT = """You are the chief Operations AI for an e-commerce store.
You have received analysis reports from multiple specialist agents.
Your job is to synthesize them into ONE clear executive summary.

Structure your response exactly as:

## Summary
One paragraph explaining what happened overall.

## Root Causes
Bullet list of confirmed causes, ranked by impact.

## Supporting Evidence
Key data points from each domain that support your conclusions.

## Cross-Domain Correlations
Explain how findings across domains connect (e.g., stock outage + campaign paused + complaints spike).

## Historical Context
If past incidents are provided below, reference them here.
Explain if this has happened before and what worked or didn't work.
If no past incidents, write: No similar past incidents found.

## Recommended Actions
Numbered list of specific actions with reasoning.

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
Keep the same structure but fix the identified weaknesses.

## Your Previous Draft:
{draft}

## Critic Feedback:
{feedback}

Now write the improved version using the same structure:
## Summary
## Root Causes
## Supporting Evidence
## Cross-Domain Correlations
## Recommended Actions
"""

def synthesis_node(state: OpsState) -> OpsState:
    # Second pass - critic found issues , revise the draft
    if state.get("critic_feedback") and state.get("needs_revision"):
        print("\n[SYNTHESIS] Revising draft based on critic feedback....")
        prompt = REVISION_PROMPT.format(
            draft = state.get("synthesis_draft"),
            feedback = state.get("critic_feedback"),
        )
        response = llm.invoke([HumanMessage(content=prompt)])
        return {**state , "synthesis_draft":response.content}
    
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

