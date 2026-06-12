import asyncio
from concurrent.futures import ThreadPoolExecutor
from fastapi import APIRouter, HTTPException
from api.schemas import ApproveRequest, ApproveResponse
from api.router.analysis import _sessions
from graph.state import OpsState

router = APIRouter()


@router.post("/actions/approve", response_model=ApproveResponse)
async def approve_actions(req: ApproveRequest):
    session = _sessions.get(req.thread_id)
    if not session:
        raise HTTPException(status_code=404,
                            detail=f"Thread '{req.thread_id}' not found. Call /api/analyze first.")

    proposed = session.get("proposed_actions", [])
    approved = [a for a in proposed if a.get("action_id") in req.approved_action_ids]

    if not approved:
        return ApproveResponse(
            thread_id=req.thread_id,
            execution_report="None of the provided action IDs matched proposed actions.",
        )

    from graph.action_executor import action_executor_node

    # Build a minimal state so the executor node can run standalone
    minimal_state: OpsState = {
        "user_question": "", "needs_sales": False, "needs_inventory": False,
        "needs_marketing": False, "needs_support": False,
        "sales_analysis": None, "inventory_analysis": None,
        "marketing_analysis": None, "support_analysis": None,
        "synthesis_draft": None, "critic_feedback": None,
        "needs_revision": False, "revision_count": 0, "final_answer": None,
        "target_date": "", "comparison_date": "", "conversation_history": [],
        "proposed_actions": approved, "action_plan_reasoning": None,
        "approved_actions": approved,
        "skip_execution": False,
        "execution_report": None, "execution_results": None,
        "past_incidents": None, "structured_output": None,
        "streamlit_approved_actions": None,
        "streamlit_skip_execution": False,
    }

    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor() as pool:
        updated = await loop.run_in_executor(pool, lambda: action_executor_node(minimal_state))

    return ApproveResponse(
        thread_id=req.thread_id,
        execution_report=updated.get("execution_report"),
        execution_results=updated.get("execution_results") or [],
    )