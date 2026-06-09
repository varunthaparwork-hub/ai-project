# Reads the final analysis and proposes specific executable actions.
# Does NOT execute anything — only proposes.
# Execution only happens after human approval in the HITL node.
#
# Uses structured output so the response is always a clean list of actions,
# never freeform text that would be hard to parse.

from pydantic import BaseModel, Field
from typing import List
from agents.base import llm
from graph.state import OpsState


class ProposedAction(BaseModel):
    # One single proposed action with everything the executor needs to run it
    action_id: int = Field(description="Sequential number starting from 1")
    description: str = Field(description="Plain English: what this action does and why")
    tool_name: str = Field(description="Exact tool name. Must be one of: restock_product, apply_discount, resume_campaign, pause_campaign, create_support_ticket")
    tool_args: dict = Field(description="Exact keyword arguments to pass to the tool as a flat dictionary")
    priority: str = Field(description="high, medium, or low based on urgency")
    estimated_impact: str = Field(description="One sentence on expected business outcome")


class ActionPlan(BaseModel):
    is_action_needed: bool = Field(description="False if the question is analytical only and no actions are needed")
    overall_reasoning: str = Field(description="Why these actions together will fix the problem")
    proposed_actions: List[ProposedAction] = Field(description="Ordered list of proposed actions, highest priority first")

ACTION_PLANNER_PROMPT = """You are the Action Planning Agent for an e-commerce operations team.
Based on the analysis report below, propose specific actions to fix the identified problems.

AVAILABLE TOOLS (only use these exact tool names):
- restock_product(product_name: str, quantity: int)
- apply_discount(product_name: str, discount_pct: float, duration_hours: int)
- resume_campaign(campaign_name: str)
- pause_campaign(campaign_name: str, reason: str)
- create_support_ticket(issue_type: str, description: str, priority: str)

AVAILABLE PRODUCT NAMES (use exactly as shown):
Nike Running Shoes, Sony Headphones, Apple Watch, Samsung TV, Levi Jeans

AVAILABLE CAMPAIGN NAMES (use exactly as shown):
Facebook Summer Sale, Google Shopping, Instagram Influencer

RULES:
- Only propose actions directly supported by evidence in the analysis
- If the user question is purely analytical (e.g. "why did sales drop") set is_action_needed=False
- If the analysis identifies OVERSTOCKED products, propose apply_discount to clear excess inventory
- If the analysis identifies OUT-OF-STOCK products, propose restock_product
- If the user asks to "fix", "restock", "run a discount", "pause", or "create a ticket" set is_action_needed=True
- Match product and campaign names EXACTLY from the lists above — do not invent or paraphrase names

Analysis:
{analysis}

User request: {user_question}"""

def action_planner_node(state: OpsState) -> OpsState:
    """
    Reads the final_answer and proposes a structured list of actions.
    Writes proposed_actions into state for the HITL node to display.
    Sets is_action_needed=False for analytical questions — skips HITL entirely.
    """

    analysis = state.get("final_answer") or state.get("synthesis_draft") or ""
    user_question = state.get("user_question" , "")

    print("\n[ACTION PLANNER] Analysing whether actions are needed...")

    structured_llm = llm.with_structured_output(ActionPlan, method="function_calling")
    plan: ActionPlan = structured_llm.invoke(
        ACTION_PLANNER_PROMPT.format(
            analysis=analysis,
            user_question=user_question,
        )
    )

    # File is for Analysis
    if not plan.is_action_needed or not plan.proposed_actions:
        print("[ACTION PLANNER] No actions required for this question.")
        return {
            **state,
            "proposed_actions": [],
            "action_plan_reasoning": "",
            "skip_execution": True,   # tells HITL and executor to skip
        }

    print(f"[ACTION PLANNER] Proposed {len(plan.proposed_actions)} action(s).")
    return {
        **state,
        "proposed_actions": [a.model_dump() for a in plan.proposed_actions],
        "action_plan_reasoning": plan.overall_reasoning,
        "skip_execution": False,
    }



