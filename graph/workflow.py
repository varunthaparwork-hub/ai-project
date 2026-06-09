# graph/workflow.py
# Full graph with HITL loop added after the critic.
#
# Flow:
#   planner → sales → inventory → marketing → support
#          → synthesis → critic
#                    ↓ (approved or max revisions reached)
#          → action_planner → hitl → action_executor → END
#                                ↓ (rejected)
#                               END

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from graph.state import OpsState
from graph.planner import planner_node
from graph.agent_nodes import sales_node, inventory_node, marketing_node, support_node
from graph.synthesis import synthesis_node
from graph.critic import critic_node
from graph.action_planner import action_planner_node
from graph.hitl import hitl_node
from graph.action_executor import action_executor_node
from graph.memory_node import memory_node
from graph.formatter import formatter_node


def router_after_critic(state: OpsState) -> str:
    """
    After critic: revision_count==1 means first rejection — send back to synthesis.
    Anything else (approved or max revisions) — move to action planner.
    """
    if state.get("needs_revision") and state.get("revision_count", 0) == 1:
        return "synthesis"
    return "action_planner"


def router_after_hitl(state: OpsState) -> str:
    """
    After HITL: if user approved actions run the executor, otherwise skip to formatter.
    """
    if state.get("skip_execution") or not state.get("approved_actions"):
        return END
    return "action_executor"


def build_graph():
    graph = StateGraph(OpsState)

    # Register all nodes
    graph.add_node("planner",         planner_node)
    graph.add_node("sales",           sales_node)
    graph.add_node("inventory",       inventory_node)
    graph.add_node("marketing",       marketing_node)
    graph.add_node("support",         support_node)
    graph.add_node("synthesis",       synthesis_node)
    graph.add_node("memory",          memory_node)
    graph.add_node("critic",          critic_node)
    graph.add_node("action_planner",  action_planner_node)
    graph.add_node("hitl",            hitl_node)
    graph.add_node("action_executor", action_executor_node)
    graph.add_node("formatter",       formatter_node)

    # Main analysis pipeline — fixed edges
    graph.add_edge(START,       "planner")
    graph.add_edge("planner",   "sales")
    graph.add_edge("sales",     "inventory")
    graph.add_edge("inventory", "marketing")
    graph.add_edge("marketing", "support")
    graph.add_edge("support",   "memory")    # after all agents run, search long-term memory
    graph.add_edge("memory",    "synthesis") # synthesis gets both agent reports + past incidents
    graph.add_edge("synthesis", "critic")

    # After critic: revise once OR proceed to action planning
    graph.add_conditional_edges(
        "critic",
        router_after_critic,
        {"synthesis": "synthesis", "action_planner": "action_planner"},
    )

    # Action planner always feeds into HITL
    graph.add_edge("action_planner", "hitl")

    # After HITL: execute approved actions OR skip straight to formatter
    graph.add_conditional_edges(
        "hitl",
        router_after_hitl,
        {"action_executor": "action_executor", END: "formatter"},
    )

    # Executor feeds into formatter; formatter always ends
    graph.add_edge("action_executor", "formatter")
    graph.add_edge("formatter",       END)

    checkpointer = MemorySaver()  # enables short-term memory across conversation turns
    return graph.compile(checkpointer=checkpointer)


ops_app = build_graph()