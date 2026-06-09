# Streamlit-compatible HITL node.
#
# Unlike hitl.py (which calls input() and blocks), this version:
#   - Reads pre-approved actions that Streamlit already injected into state
#     via the "streamlit_approved_actions" and "streamlit_skip_execution" fields
#   - Does NOT call input() — non-blocking, safe for web UI
#   - Falls back to skip if nothing was pre-set (safety net)

from graph.state import OpsState


def hitl_streamlit_node(state: OpsState) -> OpsState:
    """
    Streamlit HITL node — reads approval decisions already stored in state.
    Streamlit sets 'streamlit_approved_actions' before resuming the graph.
    """
    proposed = state.get("proposed_actions") or []

    if not proposed:
        return {**state, "approved_actions": [], "skip_execution": True}

    # Streamlit injects the approval decision into state before calling invoke()
    # Keys used: "streamlit_approved_actions" (list) and "streamlit_skip_execution" (bool)
    if state.get("streamlit_skip_execution"):
        return {**state, "approved_actions": [], "skip_execution": True}

    approved = state.get("streamlit_approved_actions") or []
    if not approved:
        return {**state, "approved_actions": [], "skip_execution": True}

    return {**state, "approved_actions": approved, "skip_execution": False}
