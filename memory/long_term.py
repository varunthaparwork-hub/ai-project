# Long-term memory using Qdrant vector database.
# Stores past incidents as vector embeddings so the AI can search
# by MEANING, not just keywords.
#
# Example:
#   Query: "sales dropped because products were unavailable"
#   Finds: "March 15 — Nike stockout caused 35% revenue drop"
#   Even though the words are different — the meaning matches.
#
# Two operations:
#   save_incident()  — stores a resolved incident into Qdrant
#   search_similar() — finds past incidents similar to current situation

import os
import json
import uuid
import hashlib
from datetime import datetime
from typing import Optional
from pathlib import Path

from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
)

load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env", override=True, encoding="utf-8-sig")

# ── Configuration ────────────────────────────────────────────
COLLECTION_NAME    = "incidents"   # name of the Qdrant collection
VECTOR_SIZE        = 384           # output dim of BAAI/bge-small-en-v1.5 (fastembed default)
EMBEDDING_MODEL    = "BAAI/bge-small-en-v1.5"  # ~50MB, no torch required
TOP_K              = 3             # how many similar incidents to return by default

# ── Singleton setup ──────────────────────────────────────────
_client: Optional[QdrantClient] = None


def get_client() -> QdrantClient:
    """Returns the shared Qdrant client, creating it on first call.
    
    - Local dev:  uses in-memory Qdrant (QDRANT_URL not set)
    - Docker:     uses persistent Qdrant (QDRANT_URL=http://qdrant:6333)
    """
    global _client
    if _client is None:
        qdrant_url = os.getenv("QDRANT_URL", "").strip()
        qdrant_api_key = os.getenv("QDRANT_API_KEY", "").strip()
        if qdrant_url:
            _client = QdrantClient(url=qdrant_url, api_key=qdrant_api_key or None)
            print(f"[MEMORY] Qdrant client initialised (persistent: {qdrant_url}).")
        else:
            _client = QdrantClient(":memory:")
            print("[MEMORY] Qdrant client initialised (in-memory).")
    return _client


def ensure_collection() -> None:
    """Creates the Qdrant collection if it doesn't already exist."""
    client = get_client()
    existing = [c.name for c in client.get_collections().collections]

    if COLLECTION_NAME not in existing:
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(
                size=VECTOR_SIZE,
                distance=Distance.COSINE,
            ),
        )
        print(f"[MEMORY] Collection '{COLLECTION_NAME}' created.")


def _embed(text: str) -> list[float]:
    """Converts text to a vector using fastembed (no torch, ~50MB model)."""
    from fastembed import TextEmbedding
    embedder = TextEmbedding(model_name=EMBEDDING_MODEL)
    return list(list(embedder.embed([text]))[0])


def save_incident(
    date: str,
    description: str,
    root_causes: list[str],
    actions_taken: list[str],
    outcome: str,
    resolution_time_days: int = 0,
    incident_id: str = None,
) -> str:
    """
    Saves a resolved incident to BOTH Qdrant (for semantic search) and
    PostgreSQL past_incidents table (for persistence across restarts).
    The description is embedded into a vector for similarity search.
    All other fields are stored as metadata payload in Qdrant and as
    a row in PostgreSQL.

    Returns the incident_id that was saved.
    """
    import json as _json

    ensure_collection()
    client  = get_client()

    # Use provided ID or generate a new UUID
    inc_id  = incident_id or str(uuid.uuid4())

    # The text we embed = what gets matched during similarity search
    # Combining description + root causes gives richer semantic coverage
    embed_text = f"{description}. Root causes: {', '.join(root_causes)}."
    vector     = _embed(embed_text)

    # Store the full incident data as payload alongside the vector
    payload = {
        "incident_id":          inc_id,
        "date":                 date,
        "description":          description,
        "root_causes":          root_causes,
        "actions_taken":        actions_taken,
        "outcome":              outcome,
        "resolution_time_days": resolution_time_days,
        "saved_at":             datetime.now().isoformat(),
    }

    # ── 1. Save to Qdrant (semantic vector search) ────────────────
    # Use sha256 so the point ID is deterministic across process restarts.
    # (Python's built-in hash() is randomised per process via PYTHONHASHSEED,
    #  which caused a new duplicate Qdrant point on every uvicorn reload.)
    qdrant_id = int(hashlib.sha256(inc_id.encode()).hexdigest()[:16], 16)
    client.upsert(
        collection_name=COLLECTION_NAME,
        points=[PointStruct(
            id      = qdrant_id,
            vector  = vector,
            payload = payload,
        )],
    )

    # ── 2. Save to PostgreSQL (persistent storage across restarts) ─
    # Uses execute_sync (runs in the background _sync_loop) so this works
    # from ANY context: async FastAPI lifespan, sync tool threads, or bare scripts.
    try:
        from data.db import execute_sync as _execute_sync
        _execute_sync(
            """INSERT INTO past_incidents
                   (id, date, description, root_causes, actions_taken, outcome, resolution_time_days)
               VALUES ($1, $2, $3, $4::jsonb, $5::jsonb, $6, $7)
               ON CONFLICT (id) DO UPDATE SET
                   description          = EXCLUDED.description,
                   root_causes          = EXCLUDED.root_causes,
                   actions_taken        = EXCLUDED.actions_taken,
                   outcome              = EXCLUDED.outcome,
                   resolution_time_days = EXCLUDED.resolution_time_days""",
            inc_id,
            date,
            description,
            _json.dumps(root_causes),
            _json.dumps(actions_taken),
            outcome,
            resolution_time_days,
        )
        print(f"[MEMORY] Incident saved to Qdrant + PostgreSQL: {inc_id} ({date})")
    except Exception as e:
        # Qdrant write already succeeded — log the PG failure but don't crash
        print(f"[MEMORY] Qdrant save OK but PostgreSQL write failed: {e}")
        print(f"[MEMORY] Incident saved to Qdrant only: {inc_id} ({date})")

    return inc_id

# Minimum cosine similarity score to consider a past incident "relevant".
# all-MiniLM-L6-v2 cosine scores range from -1 to 1.
# 0.50 = meaningfully similar  |  < 0.40 = loosely related  |  < 0.30 = noise
MIN_SIMILARITY_SCORE = 0.50


def search_similar(query: str, top_k: int = TOP_K, min_score: float = MIN_SIMILARITY_SCORE) -> list[dict]:
    """
    Searches Qdrant for past incidents semantically similar to the query.
    Only returns incidents whose cosine similarity score >= min_score.

    Example query: "sales dropped due to stock outage"
    Returns: top-k most similar past incidents that clear the threshold.
             Returns empty list if nothing is similar enough.
    """
    ensure_collection()
    client = get_client()

    # Embed the query using the same model used during save
    query_vector = _embed(query)

    response = client.query_points(
        collection_name=COLLECTION_NAME,
        query=query_vector,
        limit=top_k,
        with_payload=True,   # return the full incident data, not just IDs
        score_threshold=min_score,  # Qdrant filters server-side — only returns hits above threshold
    )

    # Return list of payloads with similarity score attached.
    # Deduplicate by incident_id to guard against any legacy duplicates
    # that may have accumulated in a persistent Qdrant instance.
    incidents = []
    seen_ids: set[str] = set()
    for r in response.points:
        inc_id_val = r.payload.get("incident_id", "")
        if inc_id_val in seen_ids:
            continue
        seen_ids.add(inc_id_val)
        payload = dict(r.payload)
        payload["similarity_score"] = round(r.score, 3)
        incidents.append(payload)

    return incidents


async def seed_memory_from_db() -> None:
    """
    Seeds Qdrant with past incidents stored in the PostgreSQL past_incidents table.
    Called once on application startup so memory questions work immediately.
    Safe to call multiple times — upsert won't duplicate entries.
    """
    from data.db import fetchall

    incidents = await fetchall("SELECT * FROM past_incidents ORDER BY date")
    # fetchall returns RealDictRow; JSONB columns come back as dicts/lists already
    for row in incidents:
        if isinstance(row.get("root_causes"), str):
            row["root_causes"] = json.loads(row["root_causes"])
        if isinstance(row.get("actions_taken"), str):
            row["actions_taken"] = json.loads(row["actions_taken"])

    # Incremental seed: keep the existing collection. Point IDs are deterministic
    # (sha256 of incident_id) so we can ask Qdrant whether each incident is already
    # embedded and skip re-embedding when it is. Big restart-time win because
    # fastembed is the slow part, not Qdrant upsert.
    client = get_client()
    ensure_collection()

    skipped = 0
    embedded = 0
    for incident in incidents:
        inc_id    = incident["id"]
        qdrant_id = int(hashlib.sha256(inc_id.encode()).hexdigest()[:16], 16)

        try:
            existing = client.retrieve(
                collection_name=COLLECTION_NAME,
                ids=[qdrant_id],
                with_vectors=False,
            )
        except Exception:
            existing = []

        if existing:
            skipped += 1
            continue

        save_incident(
            incident_id          = inc_id,
            date                 = str(incident["date"]),
            description          = incident["description"],
            root_causes          = incident["root_causes"],
            actions_taken        = incident["actions_taken"],
            outcome              = incident["outcome"],
            resolution_time_days = incident["resolution_time_days"],
        )
        embedded += 1

    print(f"[MEMORY] Seeding complete. Skipped {skipped} (already embedded) / Embedded {embedded} (new).")