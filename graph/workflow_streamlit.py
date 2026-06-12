# graph/workflow_streamlit.py
# Streamlit-compatible graph — identical to workflow.py except:
#   - Uses hitl_streamlit_node instead of hitl_node (no input() blocking)
#   - router_after_hitl always goes to formatter (Streamlit handles skip via state)

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from graph.state import OpsState
from graph.planner import planner_node
from graph.agent_nodes import sales_node, inventory_node, marketing_node, support_node
from graph.synthesis import synthesis_node
from graph.critic import critic_node
from graph.action_planner import action_planner_node
from graph.hitl_streamlit import hitl_streamlit_node
from graph.action_executor import action_executor_node
from graph.memory_node import memory_node
from graph.formatter import formatter_node


def router_after_critic(state: OpsState) -> str:
    if state.get("needs_revision") and state.get("revision_count", 0) < 2:
        return "synthesis"
    return "action_planner"


def router_after_hitl(state: OpsState) -> str:
    if state.get("skip_execution") or not state.get("approved_actions"):
        return "formatter"
    return "action_executor"


def build_streamlit_graph():
    graph = StateGraph(OpsState)

    graph.add_node("planner",         planner_node)
    graph.add_node("sales",           sales_node)
    graph.add_node("inventory",       inventory_node)
    graph.add_node("marketing",       marketing_node)
    graph.add_node("support",         support_node)
    graph.add_node("memory",          memory_node)
    graph.add_node("synthesis",       synthesis_node)
    graph.add_node("critic",          critic_node)
    graph.add_node("action_planner",  action_planner_node)
    graph.add_node("hitl",            hitl_streamlit_node)
    graph.add_node("action_executor", action_executor_node)
    graph.add_node("formatter",       formatter_node)

    graph.add_edge(START,       "planner")
    # Parallel agent execution (same as main workflow)
    graph.add_edge("planner",   "sales")
    graph.add_edge("planner",   "inventory")
    graph.add_edge("planner",   "marketing")
    graph.add_edge("planner",   "support")
    # All agents converge to memory
    graph.add_edge("sales",     "memory")
    graph.add_edge("inventory", "memory")
    graph.add_edge("marketing", "memory")
    graph.add_edge("support",   "memory")
    graph.add_edge("memory",    "synthesis")
    graph.add_edge("synthesis", "critic")

    graph.add_conditional_edges(
        "critic",
        router_after_critic,
        {"synthesis": "synthesis", "action_planner": "action_planner"},
    )

    graph.add_edge("action_planner", "hitl")

    graph.add_conditional_edges(
        "hitl",
        router_after_hitl,
        {"action_executor": "action_executor", "formatter": "formatter"},
    )

    graph.add_edge("action_executor", "formatter")
    graph.add_edge("formatter",       END)

    checkpointer = MemorySaver()
    return graph.compile(checkpointer=checkpointer)


streamlit_app_graph = build_streamlit_graph()
