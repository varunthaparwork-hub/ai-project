import asyncio
import json
import time
import queue
import threading
from concurrent.futures import ThreadPoolExecutor
import hashlib
from datetime import datetime, date
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from api.schemas import AnalyzeRequest, AnalyzeResponse
from api.guardrails import validate_question
from graph.state import OpsState

router = APIRouter()
_executor = ThreadPoolExecutor(max_workers=4)

# Server-side session store: thread_id → { history, proposed_actions }
# Limited to 100 entries to prevent unbounded memory growth on long-running servers
# Least-recently-used sessions are evicted when size exceeds 100
_sessions: dict = {}
_SESSIONS_MAX = 100

OBS_LOG = Path(__file__).resolve().parent.parent.parent / "observability" / "runs.jsonl"

# ── Node label mapping for the UI ─────────────────────────────────────────────
_NODE_LABELS = {
    "planner":         {"label": "Planning",          "icon": "🧠"},
    "sales":           {"label": "Sales Analysis",    "icon": "📈"},
    "inventory":       {"label": "Inventory Check",   "icon": "📦"},
    "marketing":       {"label": "Marketing Review",  "icon": "📣"},
    "support":         {"label": "Support Analysis",  "icon": "🎧"},
    "memory":          {"label": "Memory Retrieval",  "icon": "🔍"},
    "synthesis":       {"label": "Synthesising",      "icon": "✍️"},
    "critic":          {"label": "Critic Review",     "icon": "🔬"},
    "action_planner":  {"label": "Planning Actions",  "icon": "⚡"},
    "hitl":            {"label": "Awaiting Approval", "icon": "⚠️"},
    "action_executor": {"label": "Executing Actions", "icon": "🚀"},
    "formatter":       {"label": "Formatting Output", "icon": "📋"},
}


def _build_initial_state(req: AnalyzeRequest, history: list) -> OpsState:
    """Constructs a fresh initial state dict for a pipeline run."""
    return {
        "user_question":         req.question,
        "needs_sales":           False,
        "needs_inventory":       False,
        "needs_marketing":       False,
        "needs_support":         False,
        "sales_analysis":        None,
        "inventory_analysis":    None,
        "marketing_analysis":    None,
        "support_analysis":      None,
        "synthesis_draft":       None,
        "critic_feedback":       None,
        "needs_revision":        False,
        "revision_count":        0,
        "final_answer":          None,
        "target_date":           req.target_date,
        "comparison_date":       req.comparison_date,
        "conversation_history":  history,
        "proposed_actions":      None,
        "action_plan_reasoning": None,
        "approved_actions":      None,
        "skip_execution":        False,
        "execution_report":      None,
        "execution_results":     None,
        "past_incidents":        None,
        "structured_output":     None,
        "streamlit_approved_actions": None,
        "streamlit_skip_execution":   False,
    }


def _evict_lru_session():
    """Evicts the least-recently-used session when _sessions exceeds _SESSIONS_MAX."""
    if len(_sessions) > _SESSIONS_MAX:
        # Remove the oldest key (first inserted) — simple LRU without timestamps
        oldest_key = next(iter(_sessions))
        del _sessions[oldest_key]


# ── Helpers ──────────────────────────────────────────────────────────────────

def _get_history(thread_id: str) -> list:
    """
    Returns accumulated conversation history for a thread.
    Uses in-memory cache first; falls back to DB after server restarts.
    """
    session = _sessions.get(thread_id)
    if session:
        return session.get("history", [])
    try:
        from data.db import fetchall_sync
        rows = fetchall_sync(
            "SELECT role, content FROM chat_messages WHERE thread_id = $1 ORDER BY created_at ASC, id ASC",
            thread_id,
        )
        return [{"role": r["role"], "content": r["content"]} for r in rows]
    except Exception:
        return []


def _persist_chat(thread_id: str, question: str, answer: str, structured: dict | None) -> None:
    """Persist a single conversation turn (user + assistant) to the database."""
    from data.db import execute_sync
    title   = (question[:57] + "\u2026") if len(question) > 60 else question
    so_json = json.dumps(structured) if structured else None
    try:
        execute_sync(
            "INSERT INTO chat_threads (id, title, created_at, updated_at) VALUES ($1, $2, NOW(), NOW()) "
            "ON CONFLICT (id) DO UPDATE SET updated_at = NOW()",
            thread_id, title,
        )
        execute_sync(
            "INSERT INTO chat_messages (thread_id, role, content) VALUES ($1, 'user', $2)",
            thread_id, question,
        )
        if so_json:
            execute_sync(
                "INSERT INTO chat_messages (thread_id, role, content, structured_output) "
                "VALUES ($1, 'assistant', $2, $3::jsonb)",
                thread_id, answer, so_json,
            )
        else:
            execute_sync(
                "INSERT INTO chat_messages (thread_id, role, content) VALUES ($1, 'assistant', $2)",
                thread_id, answer,
            )
    except Exception as e:
        print(f"[CHAT-PERSIST] Failed: {e}")


def _try_save_incident(thread_id: str, structured: dict, target_date_str: str) -> None:
    """
    If the analysis produced a high/critical result, save it as a DRAFT in PostgreSQL only.
    Do NOT embed to Qdrant yet — user must verify and resolve via PATCH endpoint first.
    This prevents "Pending resolution" from polluting semantic memory.
    """
    severity = structured.get("severity", "")
    if severity not in ("high", "critical"):
        return
    inc_id = f"AI-{thread_id[:8].upper()}"
    try:
        from data.db import fetchone_sync, execute_sync
        if fetchone_sync("SELECT id FROM past_incidents WHERE id = $1", inc_id):
            return   # already saved
        desc    = (structured.get("one_liner") or structured.get("summary") or "")[:200]
        causes  = [rc.get("description", "") for rc in (structured.get("root_causes") or [])]
        actions = [a.get("title", "")        for a in  (structured.get("recommended_actions") or [])]
        date_str = target_date_str or date.today().isoformat()
        if not desc:
            return
        # PostgreSQL only — status='draft' prevents auto-embedding to Qdrant
        execute_sync(
            "INSERT INTO past_incidents "
            "(id, date, description, root_causes, actions_taken, outcome, resolution_time_days, status) "
            "VALUES ($1, $2, $3, $4::jsonb, $5::jsonb, $6, 0, $7) ON CONFLICT (id) DO NOTHING",
            inc_id, date_str, desc, json.dumps(causes), json.dumps(actions), "Pending resolution", "draft",
        )
        print(f"[AUTO-INCIDENT] Saved {inc_id} ({severity}) to DB as DRAFT (awaiting resolution)")
    except Exception as e:
        print(f"[AUTO-INCIDENT] Failed: {e}")


# ── Streaming pipeline ────────────────────────────────────────────────────────

def _invoke_pipeline_streaming(req: AnalyzeRequest, event_queue: queue.Queue) -> dict:
    """
    Runs the LangGraph pipeline with multi-mode streaming. Emits:
      • 'node'  SSE events — one per completed graph node (existing behaviour)
      • 'token' SSE events — one per LLM token produced inside the synthesis node
      • 'done'  SSE event  — final answer + structured output + proposed actions
      • 'error' SSE event  — on any exception
    """
    def _emit(event_type: str, **kwargs):
        event_queue.put({"type": event_type, **kwargs})

    history = _get_history(req.thread_id)
    # Cap history to last 20 turns (40 messages) to prevent token explosion
    if len(history) > 40:
        history = history[-40:]
    history = history + [{"role": "user", "content": req.question}]

    initial_state = _build_initial_state(req, history)
    start  = time.perf_counter()
    config = {"configurable": {"thread_id": req.thread_id}}

    from graph.workflow_streamlit import streamlit_app_graph as ops_app

    try:
        # Multi-mode streaming:
        #   "updates"  → one dict per completed node — drives existing node-level events
        #   "messages" → one (message_chunk, metadata) per LLM token — used to stream
        #                synthesis tokens to the UI in real time
        # In multi-mode, each yielded item is a tuple (mode_name, payload).
        accumulated: dict = {}
        for mode, chunk in ops_app.stream(
            initial_state, config=config, stream_mode=["updates", "messages"]
        ):
            if mode == "messages":
                msg_chunk, metadata = chunk
                # Only stream tokens from the synthesis node — every other LLM call
                # (planner, agents, critic, formatter) stays internal.
                if metadata.get("langgraph_node") == "synthesis":
                    content = getattr(msg_chunk, "content", "")
                    if content:
                        _emit("token", content=content)
                continue

            # mode == "updates" — existing node-event path
            for node_name, node_output in chunk.items():
                if isinstance(node_output, dict):
                    accumulated.update(node_output)

                meta    = _NODE_LABELS.get(node_name, {"label": node_name.title(), "icon": "⚙️"})
                preview = ""

                if node_name == "planner":
                    preview = "Routing to: " + ", ".join(
                        d for d in ["sales", "inventory", "marketing", "support"]
                        if node_output.get(f"needs_{d}")
                    )
                elif node_name == "critic":
                    preview = f"Revision needed: {node_output.get('needs_revision', False)}"
                elif node_name in ("sales", "inventory", "marketing", "support"):
                    analysis = node_output.get(f"{node_name}_analysis") or ""
                    preview  = analysis[:120] + ("…" if len(analysis) > 120 else "")
                elif node_name == "memory":
                    incidents = node_output.get("past_incidents") or []
                    preview   = f"Found {len(incidents)} similar past incident(s)"
                elif node_name == "action_planner":
                    actions = node_output.get("proposed_actions") or []
                    preview = f"{len(actions)} action(s) proposed" if actions else "No actions needed"
                elif node_name == "formatter":
                    so  = node_output.get("structured_output") or {}
                    sev = so.get("severity", "")
                    rc  = len(so.get("root_causes") or [])
                    preview = f"Severity: {sev} · {rc} root cause(s)"

                _emit("node", name=node_name, label=meta["label"], icon=meta["icon"], preview=preview)

        result = accumulated

    except Exception as e:
        import traceback
        print(f"[STREAM ERROR]\n{traceback.format_exc()}")
        _emit("error", message=str(e))
        event_queue.put(None)
        return {}

    latency_ms = round((time.perf_counter() - start) * 1000)
    final    = result.get("final_answer") or result.get("synthesis_draft") or "No answer generated."
    history  = history + [{"role": "assistant", "content": final}]
    proposed = result.get("proposed_actions") or []

    _evict_lru_session()
    _sessions[req.thread_id] = {"history": history, "proposed_actions": proposed}
    _log_obs(req, result, latency_ms)
    _persist_chat(req.thread_id, req.question, final, result.get("structured_output"))
    _try_save_incident(req.thread_id, result.get("structured_output") or {}, req.target_date)

    payload = {
        "final":             final,
        "history":           history,
        "structured_output": result.get("structured_output"),
        "proposed_actions":  proposed,
        "thread_id":         req.thread_id,
    }
    _emit("done", **payload)
    event_queue.put(None)   # sentinel — tells the SSE generator to stop
    return payload


# ── Non-streaming pipeline ────────────────────────────────────────────────────

def _invoke_pipeline(req: AnalyzeRequest) -> dict:
    """Runs the pipeline synchronously (used by POST /analyze)."""
    from graph.workflow_streamlit import streamlit_app_graph as ops_app

    history = _get_history(req.thread_id)
    history = history + [{"role": "user", "content": req.question}]

    initial_state = _build_initial_state(req, history)
    start  = time.perf_counter()
    config = {"configurable": {"thread_id": req.thread_id}}
    result = ops_app.invoke(initial_state, config=config)
    latency_ms = round((time.perf_counter() - start) * 1000)

    final    = result.get("final_answer") or result.get("synthesis_draft") or "No answer generated."
    history  = history + [{"role": "assistant", "content": final}]
    proposed = result.get("proposed_actions") or []

    _evict_lru_session()
    _sessions[req.thread_id] = {"history": history, "proposed_actions": proposed}
    _log_obs(req, result, latency_ms)
    _persist_chat(req.thread_id, req.question, final, result.get("structured_output"))
    _try_save_incident(req.thread_id, result.get("structured_output") or {}, req.target_date)

    return {
        "final":             final,
        "history":           history,
        "structured_output": result.get("structured_output"),
        "proposed_actions":  proposed,
    }


# ── Observability logger ──────────────────────────────────────────────────────

def _log_obs(req: AnalyzeRequest, result: dict, latency_ms: int):
    structured = result.get("structured_output") or {}
    record = {
        "ts":                 datetime.utcnow().isoformat(),
        "thread_id":          req.thread_id,
        "question":           req.question[:120],
        "target_date":        req.target_date,
        "latency_ms":         latency_ms,
        "severity":           structured.get("severity"),
        "domains_active":     [d for d in ["sales", "inventory", "marketing", "support"]
                               if result.get(f"{d}_analysis") is not None],
        "root_cause_count":   len(structured.get("root_causes") or []),
        "action_count":       len(structured.get("recommended_actions") or []),
        "executable_actions": sum(1 for a in (structured.get("recommended_actions") or [])
                                  if a.get("is_executable")),
        "memory_hits":        len(structured.get("historical_references") or []),
        "revision_count":     result.get("revision_count", 0),
        "had_execution":      bool(result.get("execution_report")),
    }
    OBS_LOG.parent.mkdir(exist_ok=True)
    with OBS_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
    # Also print a one-line summary to the uvicorn console
    domains = ", ".join(record["domains_active"]) or "none"
    print(
        f"[OBS] {record['ts'][:19]}  "
        f"latency={latency_ms}ms  severity={record['severity'] or '?'}  "
        f"domains={domains}  roots={record['root_cause_count']}  "
        f"actions={record['action_count']}  memory_hits={record['memory_hits']}"
    )


# ── API endpoints ─────────────────────────────────────────────────────────────

@router.post("/analyze/stream")
async def analyze_stream(req: AnalyzeRequest):
    """SSE endpoint — emits node progress events then a final 'done' event."""
    req.question = validate_question(req.question)
    event_queue: queue.Queue = queue.Queue()
    loop = asyncio.get_event_loop()

    thread = threading.Thread(
        target=_invoke_pipeline_streaming,
        args=(req, event_queue),
        daemon=True,
    )
    thread.start()

    async def event_generator():
        while True:
            try:
                item = await loop.run_in_executor(None, lambda: event_queue.get(timeout=120))
            except Exception:
                break
            if item is None:
                break
            yield f"data: {json.dumps(item)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":     "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(req: AnalyzeRequest):
    """Non-streaming analysis endpoint."""
    req.question = validate_question(req.question)
    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(_executor, lambda: _invoke_pipeline(req))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return AnalyzeResponse(
        thread_id=req.thread_id,
        final_answer=result["final"],
        structured_output=result["structured_output"],
        proposed_actions=result["proposed_actions"],
        history=result["history"],
    )
