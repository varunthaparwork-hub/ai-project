from fastapi import APIRouter, HTTPException
from api.schemas import HistoryResponse
from api.router.analysis import _sessions, _get_history

router = APIRouter()


@router.get("/history/{thread_id}", response_model=HistoryResponse)
def get_history(thread_id: str):
    # Try in-memory session cache first, fall back to database
    session = _sessions.get(thread_id)
    if session:
        return HistoryResponse(thread_id=thread_id, messages=session.get("history", []))

    # Fallback: query database
    history = _get_history(thread_id)
    if history:
        return HistoryResponse(thread_id=thread_id, messages=history)

    raise HTTPException(status_code=404, detail=f"Thread '{thread_id}' not found.")