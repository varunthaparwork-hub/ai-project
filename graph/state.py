#This defines the shared memory of the graph - What data flows between nodes

# State is a typed dictionary that gets apsses between every node.
# Each node reads from it and writes back to it
# Think of it as a shared whiteboard the shole team can read and write on


from typing import TypedDict, Optional, List

# OpsState is the shared state
class OpsState(TypedDict):
    # The original question from the user
    user_question: str

    # Planner fills these -> which agents should run
    needs_sales: bool
    needs_inventory: bool
    needs_marketing: bool
    needs_support: bool

    # Each agent writes its findings here
    sales_analysis: Optional[str]
    inventory_analysis: Optional[str]
    marketing_analysis: Optional[str]
    support_analysis: Optional[str]

    # Synthesis node writes the combined answer here (draft)
    synthesis_draft: Optional[str]

    # Critic node writes its evaluation here
    critic_feedback: Optional[str]

    # Whether the critic flagged the answer as needing revision
    needs_revision: bool

    # Tracks how many times critic has sent back for revision (prevents infinite loop)
    revision_count: int

    # Final approved answer after critic passes it
    final_answer: Optional[str]

    # Date context extracted by planner
    target_date: str
    comparison_date: str

    # Stores the full conversation history for this thread
    # Each entry is a dict with keys "role" (user/assistant) and "content" (the text)
    conversation_history: List[dict]

    # Action Planner fills this — each dict has: action_id, description,
    # tool_name, tool_args, priority, estimated_impact
    proposed_actions: Optional[List[dict]]

    # The overall reasoning behind the action plan (why these actions together)
    action_plan_reasoning: Optional[str]

    # HITL node fills this with only the user-approved subset of proposed_actions
    approved_actions: Optional[List[dict]]

    # True if user rejected all actions in HITL — tells executor to skip
    skip_execution: bool

    # Executor writes a human-readable summary of what ran and what succeeded/failed
    execution_report: Optional[str]

    # Raw per-action results list from executor (for programmatic use e.g. Streamlit)
    execution_results: Optional[List[dict]]

    # Memory node fills this with similar past incidents from Qdrant.
    # Each dict has: date, description, root_causes, actions_taken, outcome, similarity_score
    # Synthesis reads this to include historical context in its answer.
    past_incidents: Optional[List[dict]]

    # Formatter node writes the fully structured OpsResponse here (as a dict).
    # Streamlit, REST API, and evaluator consume this instead of the raw markdown.
    structured_output: Optional[dict]