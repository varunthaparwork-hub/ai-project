import json as _json
from fastapi import APIRouter, HTTPException
from api.schemas import ChatThread, ChatMessage, ChatMessagesResponse
from data.db import fetchall_sync, execute_sync

router = APIRouter()


@router.get("/chats", response_model=list[ChatThread])
def list_chats():
    rows = fetchall_sync("""
        SELECT ct.id, ct.title, ct.created_at, ct.updated_at,
               COUNT(cm.id) AS message_count
        FROM chat_threads ct
        LEFT JOIN chat_messages cm ON cm.thread_id = ct.id
        GROUP BY ct.id
        ORDER BY ct.updated_at DESC
    """)
    return [
        ChatThread(
            id=r["id"],
            title=r["title"],
            created_at=r["created_at"].isoformat() if hasattr(r["created_at"], "isoformat") else str(r["created_at"]),
            updated_at=r["updated_at"].isoformat() if hasattr(r["updated_at"], "isoformat") else str(r["updated_at"]),
            message_count=int(r["message_count"]),
        )
        for r in rows
    ]


@router.get("/chats/{thread_id}/messages", response_model=ChatMessagesResponse)
def get_chat_messages(thread_id: str):
    thread = fetchall_sync("SELECT id FROM chat_threads WHERE id = $1", thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail=f"Thread '{thread_id}' not found.")
    msgs = fetchall_sync("""
        SELECT role, content, structured_output
        FROM chat_messages
        WHERE thread_id = $1
        ORDER BY created_at ASC, id ASC
    """, thread_id)
    return ChatMessagesResponse(
        thread_id=thread_id,
        messages=[
            ChatMessage(
                role=m["role"],
                content=m["content"],
                structured_output=(
                    _json.loads(m["structured_output"])
                    if isinstance(m.get("structured_output"), str)
                    else m.get("structured_output")
                ),
            )
            for m in msgs
        ],
    )


@router.delete("/chats/{thread_id}")
def delete_chat(thread_id: str):
    execute_sync("DELETE FROM chat_threads WHERE id = $1", thread_id)
    return {"ok": True}
