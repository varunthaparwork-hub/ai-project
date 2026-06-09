# api/main.py
# FastAPI application entry point.
# Run with: uvicorn api.main:app --reload --port 8000
# Swagger UI: http://localhost:8000/docs

from contextlib import asynccontextmanager
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env", encoding="utf-8-sig")

# ── LangSmith / LangChain tracing ────────────────────────────────────────────
import os as _os
_ls_key = _os.getenv("LANGSMITH_API_KEY", "")
if _ls_key:
    _os.environ.setdefault("LANGCHAIN_TRACING_V2", _os.getenv("LANGSMITH_TRACING", "false"))
    _os.environ.setdefault("LANGCHAIN_API_KEY",    _ls_key)
    _os.environ.setdefault("LANGCHAIN_PROJECT",    _os.getenv("LANGSMITH_PROJECT", "default"))
    print(f"[LANGSMITH] Tracing ON  project={_os.getenv('LANGSMITH_PROJECT')}")
else:
    print("[LANGSMITH] No API key found — tracing disabled.")

# ── Patch HITL BEFORE graph.workflow is imported anywhere ─────────────────────
# workflow.py binds hitl_node at import time (line: from graph.hitl import hitl_node).
# We must replace graph.hitl.hitl_node BEFORE any router triggers that import.
# In API mode there is no stdin — proposed actions are returned to the client
# for approval via POST /api/actions/approve instead.
import graph.hitl as _hitl_mod


def _api_hitl(state):
    """API-mode HITL: skip stdin, return proposed actions to the client."""
    proposed = state.get("proposed_actions") or []
    if not proposed or state.get("skip_execution"):
        return {**state, "approved_actions": [], "skip_execution": True}
    # Don't execute yet — client will call /api/actions/approve
    return {**state, "approved_actions": [], "skip_execution": True}


_hitl_mod.hitl_node = _api_hitl

# ── Routers (imported AFTER patch so workflow compiles with patched HITL) ─────
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.router import analysis, actions, history, obs, chats


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Apply DB migrations (idempotent — safe to run on every startup)
    from data.db import get_pool
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("ALTER TABLE inventory ADD COLUMN IF NOT EXISTS discount_pct NUMERIC(5,2) NOT NULL DEFAULT 0")
        await conn.execute("ALTER TABLE inventory ADD COLUMN IF NOT EXISTS discount_expires_at TIMESTAMPTZ")
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS support_tickets (
                id TEXT PRIMARY KEY, issue_type TEXT NOT NULL, description TEXT,
                priority TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'open',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)

    # Seed Qdrant memory on startup
    from memory.long_term import seed_memory_from_db
    await seed_memory_from_db()
    yield
    # Close asyncpg pool on shutdown
    from data.db import _pool
    if _pool:
        await _pool.close()


app = FastAPI(
    title="AI E-Commerce Ops API",
    version="1.0.0",
    description="Multi-agent AI system for e-commerce operations analysis.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(analysis.router, prefix="/api", tags=["Analysis"])
app.include_router(actions.router,  prefix="/api", tags=["Actions"])
app.include_router(history.router,  prefix="/api", tags=["History"])
app.include_router(obs.router,      prefix="/api", tags=["Observability"])
app.include_router(chats.router,    prefix="/api", tags=["Chats"])


@app.get("/health", tags=["Health"])
def health():
    return {"status": "ok", "service": "ai-ecommerce-ops"}
