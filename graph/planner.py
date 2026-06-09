# The planner node is the first node on the graph
# It reads the user's question and decides:
    # - Which date is being asked
    # - Which agents need to run

# Uses structured output(with_structured_output) to gurantee
# LLM returns a clean JSON object, not freeform text
# This is more reliable than parsing text responses

from datetime import date, timedelta
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field
from agents.base import llm_fast as llm  # routing is a short structured call — cheaper tier is sufficient
from graph.state import OpsState


class PlannerDecision(BaseModel):
    needs_sales: bool = Field(description="Does this question require sales analysis?")
    needs_inventory: bool = Field(description="Does this question require inventory analysis?")
    needs_marketing: bool = Field(description="Does this question require marketing/campaign analysis?")
    needs_support: bool = Field(description="Does this question require customer support analysis?")
    target_date: str = Field(description="The primary date being analyzed in YYYY-MM-DD format. If the question is a follow-up that does not specify a new date (e.g. 'What about inventory?', 'Did stockouts cause it?', 'How can we fix it?'), use the previous_target_date provided in the prompt instead of today's date.")
    comparison_date: str = Field(description="The comparison date in YYYY-MM-DD format. Infer from the question — usually the day before target_date or same weekday last week.")

# Prompt is a template — dates are injected at runtime inside planner_node
PLANNER_PROMPT = """You are the operations planning agent for an e-commerce store.
A business user has asked a question. Your job is to decide:
1. Which analysis agents need to run to answer the question
2. Which dates are relevant

Today's date is {today}.
Yesterday was {yesterday}.
One week ago was {last_week}.
Same weekday last week was {same_weekday_last_week}.
Previous analysis target date (from earlier in this conversation): {previous_target_date}

DATE RULE: If the current question does not explicitly mention a new date and is clearly a
follow-up to the previous question (e.g. starts with "What about", "Did", "How about",
"Can you also", "And the", or is very short), set target_date = previous_target_date.
Only use today's date if the question is explicitly about right now with no prior context.

Previous conversation (last 3 turns — use this to understand follow-up questions like "why?" or "what about inventory?"):
{history}

DIRECT ACTION RULE: A "direct operational command" must satisfy ALL THREE of these:
  (a) imperative form — NOT a question. Anything ending in "?" is NOT a command.
      "Can we…", "Could you…", "Should we…", "What about…", "How can we fix…" → NOT commands.
  (b) names a specific product or campaign by exact name (e.g. "Sony Headphones", "Google Shopping").
  (c) specifies a concrete parameter — a number, percentage, duration, or "pause"/"resume".

If and ONLY if all three are met, set ALL needs_* to False (the action_planner will execute it).

Examples that ARE direct commands → all needs_* = False:
  "restock Samsung TV by 20 units"
  "apply 15% discount on Sony Headphones for 72 hours"
  "pause Google Shopping campaign"
  "resume Facebook Summer Sale"

Examples that are NOT commands → route to agents normally:
  "can we do some actions on it?"            (vague question — follow-up to prior analysis)
  "what should we do about overstock?"       (asking for advice, not commanding)
  "should we discount anything?"             (question, no specific product)
  "how do we fix this?"                      (question, no specific entity)
  "any actions we can take?"                 (question, no specific entity)

For vague follow-ups that reference prior analysis ("it", "this", "that"), inherit the
domains and target_date from the previous turn's context — re-run the relevant agents so
the action_planner has fresh data to recommend against.

For broad questions like "why did sales drop?" or "what happened yesterday?"
activate ALL agents since a full cross-domain analysis is needed.
For specific questions, only activate the relevant agents.

User question: {question}"""


def planner_node(state: OpsState) -> OpsState:
    """
    First Node in the graph.
    Reads the user question, decides which agents to activate,
    writes those decisions back into state.
    Dates are computed fresh every time this runs — no hardcoding.
    """
    # Compute all date references at runtime
    today               = date.today()
    yesterday           = today - timedelta(days=1)
    last_week           = today - timedelta(days=7)
    same_weekday        = today - timedelta(weeks=1)

    structured_llm = llm.with_structured_output(PlannerDecision, method="function_calling")

    # Format Converation history for prompt
    history = state.get("conversation_history", [])

    history_text = "\n".join(
        f"{turn['role'].upper()}: {turn['content']}"
        for turn in history[-6:]  # last 3 turns (6 messages)
    ) or "No previous conversation."


    decision: PlannerDecision = structured_llm.invoke(
        PLANNER_PROMPT.format(
            history=history_text,
            today                  = today.isoformat(),
            yesterday              = yesterday.isoformat(),
            last_week              = last_week.isoformat(),
            same_weekday_last_week = same_weekday.isoformat(),
            previous_target_date   = state.get("target_date") or "none (first question in conversation)",
            question               = state["user_question"],
        )
    )

    print("\n[PLANNER] Routing decision:")
    print(f"  Sales: {decision.needs_sales}")
    print(f"  Inventory: {decision.needs_inventory}")
    print(f"  Marketing: {decision.needs_marketing}")
    print(f"  Support: {decision.needs_support}")
    print(f"  Target date: {decision.target_date}")

    return {
        **state,
        "needs_sales": decision.needs_sales,
        "needs_inventory": decision.needs_inventory,
        "needs_marketing": decision.needs_marketing,
        "needs_support": decision.needs_support,
        "target_date": decision.target_date,
        "comparison_date": decision.comparison_date,
    }
