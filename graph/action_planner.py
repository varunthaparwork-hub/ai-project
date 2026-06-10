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


def _get_product_names() -> str:
    """Fetch live product names from DB so the action planner always uses current data."""
    try:
        from data.db import fetchall_sync
        rows = fetchall_sync("SELECT DISTINCT product_name FROM inventory ORDER BY product_name")
        names = [r["product_name"] for r in rows]
        return ", ".join(names) if names else "Nike Running Shoes, Sony Headphones, Apple Watch, Samsung TV, Levi Jeans"
    except Exception:
        return "Nike Running Shoes, Sony Headphones, Apple Watch, Samsung TV, Levi Jeans"


def _get_campaign_names() -> str:
    """Fetch live campaign names from DB so the action planner always uses current data."""
    try:
        from data.db import fetchall_sync
        rows = fetchall_sync("SELECT DISTINCT name FROM campaigns ORDER BY name")
        names = [r["name"] for r in rows]
        return ", ".join(names) if names else "Facebook Summer Sale, Google Shopping, Instagram Influencer"
    except Exception:
        return "Facebook Summer Sale, Google Shopping, Instagram Influencer"


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

AVAILABLE PRODUCT NAMES (use exactly as shown — fetched live from database):
{product_names}

AVAILABLE CAMPAIGN NAMES (use exactly as shown — fetched live from database):
{campaign_names}

EXPLICIT COMMAND OVERRIDE (highest priority — beats everything else):
If the user's request directly names a product/campaign AND specifies an action and amount, you MUST
propose exactly that action — regardless of what the analysis says. The user's explicit command is authoritative.
Examples that trigger override:
  "restock Samsung TV by 20 units"         → restock_product("Samsung TV", 20), is_action_needed=True
  "apply 15% discount on Sony Headphones"  → apply_discount("Sony Headphones", 15, 72), is_action_needed=True
  "pause Google Shopping campaign"         → pause_campaign("Google Shopping", ...), is_action_needed=True
  "resume Facebook Summer Sale"            → resume_campaign("Facebook Summer Sale"), is_action_needed=True
  "create a high priority ticket for X"    → create_support_ticket(...), is_action_needed=True
Do NOT let an overstock or stockout analysis override an explicit restock/discount command from the user.

VAGUE-REQUEST RULE:
If the user request is a vague question like "can we do some actions on it?", "what should we do?",
"any fixes?" — and there is NO concrete product/quantity in the request — DO NOT echo the request
as an action. Instead, derive concrete actions from the analysis (e.g. discount specific overstocked
products named in the analysis). If the analysis is also empty, set is_action_needed=False and
return an empty proposed_actions list. NEVER produce an action whose description is just the user's
question with "Execute as requested:" prepended — that is meaningless and forbidden.

AUTOMATIC ACTION TRIGGERS (data-driven signals, apply regardless of question phrasing):
These triggers fire based on what the analysis reveals, not on question keywords:
- If ANY campaign status='paused': propose resume_campaign (recovery action — get campaign active again)
- If ANY product with stock=0: propose restock_product (prevent ongoing revenue loss)
- If ANY product with overstock_ratio > 2.0: propose apply_discount (clear excess, free up cash)
- If complaint volume is above baseline: propose create_support_ticket (escalate, prevent churn)
These are data-driven signals, not question-phrasing signals. Apply them whenever the analysis
contains the corresponding signal, regardless of whether the user asked for it.

ANALYSIS-DERIVED RULES (only apply when user question is NOT a direct command):
- If the user question is purely analytical (e.g. "why did sales drop") set is_action_needed=False
- If the analysis identifies OVERSTOCKED products, propose apply_discount to clear excess inventory
- If the analysis identifies OUT-OF-STOCK products, propose restock_product
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
            product_names=_get_product_names(),
            campaign_names=_get_campaign_names(),
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



