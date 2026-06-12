# graph/critic.py
# The Critic node evaluates the synthesis draft before it becomes the final answer.
# 
# It checks the for 4 things:
#   1. Are root causes backed by actual data from the agents?
#   2. Are any important signals missing or ignored?
#   3. Do the recommendations logically follow from the causes
#   4. Are there contradictions between agent reports
# 
# The critic acts as a quality gate — it either:
# If issues found  → needs_revision=True, writes feedback, synthesis runs again
# If looks good    → promotes draft to final_answer, needs_revision=False


from pydantic import BaseModel, Field
from langchain_core.messages import HumanMessage
from agents.base import llm_fast as llm  # critic grades a short draft — cheaper tier is sufficient
from graph.state import OpsState


class CriticDecision(BaseModel):
    needs_revision: bool = Field(
        description="True if the draft has significant issues that need fixing."
    )
    feedback: str = Field(
        description="Specific feedback on what is wrong or missing. Empty string if no issues."
    )
    confidence_score: float = Field(
        default=0.8,
        description="Your confidence in the draft's accuracy from 0.0 to 1.0. Must be included."
    )


CRITIC_PROMPT = """You are a critical reviewer of business analysis reports.
A synthesis draft has been produced from multiple data sources.
Your job is to evaluate its quality strictly.

Check for ALL of the following:
1. EVIDENCE: Are all stated root causes backed by specific numbers from the agent reports?
2. COMPLETENESS: Were any important signals from the agent reports ignored in the draft?
3. LOGIC: Do the recommended actions directly address the identified root causes?
4. CONSISTENCY: Are there any contradictions between what different agents reported?

Available agent reports:
SALES: {sales}
INVENTORY: {inventory}  
MARKETING: {marketing}
SUPPORT: {support}

Draft to evaluate:
{draft}

Be strict. If the draft makes claims without data, misses key findings, 
or recommends actions unrelated to causes — flag it for revision.
Only approve if the draft is accurate, complete, and logical.
Always return needs_revision, feedback, AND confidence_score (0.0–1.0)."""


def critic_node(state: OpsState) -> OpsState:
    """
    Evaluates the synthesis draft.
    If approved  → copies draft to final_answer, sets needs_revision=False
    If rejected  → sets needs_revision=True with feedback for synthesis to fix
    """
    # Auto-approve direct action commands — no analytical review needed
    draft = state.get("synthesis_draft", "")
    if "Direct operational command received" in draft:
        print("\n[CRITIC] Direct command — auto-approving, skipping LLM review.")
        return {
            **state,
            "needs_revision":  False,
            "critic_feedback": "",
            "final_answer":    draft,
        }

    print("\n[CRITIC] Evaluating synthesis draft...")

    structured_llm = llm.with_structured_output(CriticDecision, method="function_calling")

    decision: CriticDecision = structured_llm.invoke(
        CRITIC_PROMPT.format(
            sales=state.get("sales_analysis") or "Not analyzed",
            inventory=state.get("inventory_analysis") or "Not analyzed",
            marketing=state.get("marketing_analysis") or "Not analyzed",
            support=state.get("support_analysis") or "Not analyzed",
            draft=state.get("synthesis_draft"),
        )
    )

    print(f"  Needs revision: {decision.needs_revision}")
    print(f"  Confidence: {decision.confidence_score:.2f}")
    if decision.feedback:
        print(f"  Feedback: {decision.feedback}")

    current_revision_count = state.get("revision_count", 0)

    # Confidence threshold: if confidence < 0.70 and we haven't hit revision limit,
    # always send for revision regardless of needs_revision flag
    low_confidence = decision.confidence_score < 0.70
    should_revise = (decision.needs_revision or low_confidence) and current_revision_count < 2

    if should_revise:
        reason = "low confidence" if low_confidence else "identified issues"
        print(f"[CRITIC] Sending back for revision (reason: {reason}, confidence: {decision.confidence_score:.2f})...")
        return {
            **state,
            "needs_revision": True,
            "critic_feedback": decision.feedback,
            "revision_count": current_revision_count + 1,
        }

    # Draft approved (or max revisions reached) — promote to final answer
    if current_revision_count >= 2:
        if low_confidence:
            print(f"[CRITIC] ⚠️  Max revisions reached. Accepting draft despite LOW confidence ({decision.confidence_score:.2f}). Manual review recommended.")
        else:
            print(f"[CRITIC] Max revisions (2) reached — accepting revised draft (confidence: {decision.confidence_score:.2f}).")
    elif current_revision_count == 1:
        print(f"[CRITIC] Revised draft approved (confidence: {decision.confidence_score:.2f}).")
    else:
        print(f"[CRITIC] Draft approved (confidence: {decision.confidence_score:.2f}).")
    return {
        **state,
        "needs_revision": False,
        "critic_feedback": decision.feedback,
        "final_answer": state["synthesis_draft"],
    }