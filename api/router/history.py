from fastapi import APIRouter, HTTPException
from api.schemas import HistoryResponse
from api.router.analysis import _sessions

router = APIRouter()


@router.get("/history/{thread_id}", response_model=HistoryResponse)
def get_history(thread_id: str):
    session = _sessions.get(thread_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Thread '{thread_id}' not found.")
    return HistoryResponse(thread_id=thread_id, messages=session.get("history", []))