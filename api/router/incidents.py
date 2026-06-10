# api/router/incidents.py
# Manage past incidents: resolve drafts and embed them into semantic memory.

import json
import hashlib
from datetime import date
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/incidents", tags=["incidents"])


@router.patch("/{incident_id}/resolve")
async def resolve_incident(incident_id: str, outcome: str, resolution_time_days: int = 0):
    """
    Mark a draft incident as resolved and embed it into Qdrant.
    - incident_id: e.g., "AI-abc12345"
    - outcome: human-verified outcome description
    - resolution_time_days: how many days to resolution (for analytics)

    Returns: updated incident record
    """
    try:
        from data.db import fetchone_sync, execute_sync

        # 1. Fetch the draft from PostgreSQL
        row = fetchone_sync(
            "SELECT id, date, description, root_causes, actions_taken FROM past_incidents WHERE id = $1 AND status = $2",
            incident_id, "draft"
        )
        if not row:
            raise HTTPException(status_code=404, detail=f"Draft incident {incident_id} not found")

        # 2. Update status to 'resolved' with outcome
        execute_sync(
            "UPDATE past_incidents SET status = $1, outcome = $2, resolution_time_days = $3 WHERE id = $4",
            "resolved", outcome, resolution_time_days, incident_id
        )

        # 3. Embed into Qdrant now that it's been verified
        from memory.long_term import get_client, ensure_collection, _embed, COLLECTION_NAME
        from qdrant_client.models import PointStruct

        ensure_collection()
        desc = row["description"]
        causes = json.loads(row["root_causes"]) if isinstance(row["root_causes"], str) else row["root_causes"]
        vector = _embed(f"{desc}. Root causes: {', '.join(causes)}.")
        qdrant_id = int(hashlib.sha256(incident_id.encode()).hexdigest()[:16], 16)

        get_client().upsert(
            collection_name=COLLECTION_NAME,
            points=[PointStruct(id=qdrant_id, vector=vector, payload={
                "incident_id": incident_id,
                "date": row["date"],
                "description": desc,
                "root_causes": causes,
                "actions_taken": json.loads(row["actions_taken"]) if isinstance(row["actions_taken"], str) else row["actions_taken"],
                "outcome": outcome,
                "resolution_time_days": resolution_time_days,
            })],
        )

        return {
            "incident_id": incident_id,
            "status": "resolved",
            "outcome": outcome,
            "resolution_time_days": resolution_time_days,
            "message": f"Incident {incident_id} resolved and embedded to memory"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Resolution failed: {str(e)}")
