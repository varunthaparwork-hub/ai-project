import json
import math
from pathlib import Path
from collections import Counter
from fastapi import APIRouter
from api.schemas import ObsStatsResponse

router = APIRouter()
LOG_FILE = Path(__file__).resolve().parent.parent.parent / "observability" / "runs.jsonl"


@router.get("/observability", response_model=ObsStatsResponse)
def get_observability():
    empty = ObsStatsResponse(
        total_runs=0, avg_latency_ms=0, p95_latency_ms=0,
        avg_revisions=0, memory_hit_rate=0, exec_rate=0,
        severity_distribution={}, domain_activation={}, recent_runs=[],
    )
    if not LOG_FILE.exists():
        return empty

    runs = [json.loads(l) for l in LOG_FILE.read_text(encoding="utf-8").splitlines() if l.strip()]
    if not runs:
        return empty

    total = len(runs)
    latencies = sorted(r["latency_ms"] for r in runs)

    # Correct p95 calculation: ceil(total * 0.95) - 1 gives the 95th percentile index
    p95_idx = min(math.ceil(total * 0.95) - 1, total - 1)

    return ObsStatsResponse(
        total_runs=total,
        avg_latency_ms=round(sum(latencies) / total, 1),
        p95_latency_ms=float(latencies[p95_idx]),
        avg_revisions=round(sum(r.get("revision_count", 0) for r in runs) / total, 2),
        memory_hit_rate=round(sum(1 for r in runs if r.get("memory_hits", 0) > 0) / total * 100, 1),
        exec_rate=round(sum(1 for r in runs if r.get("had_execution")) / total * 100, 1),
        severity_distribution=dict(Counter(r["severity"] for r in runs if r.get("severity"))),
        domain_activation=dict(Counter(d for r in runs for d in r.get("domains_active", []))),
        recent_runs=runs[-10:],
    )