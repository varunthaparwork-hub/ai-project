# Wraps ask() to capture per-run metrics: latency, severity, domains activated,
# action counts, revision cycles, and whether memory was used.
# Writes a JSONL append log to observability/runs.jsonl

import time
import json
from pathlib import Path
from datetime import datetime

LOG_FILE = Path(__file__).parent / "runs.jsonl"


def track(question: str, target_date: str = "", comparison_date: str = "",
          thread_id: str = "default", history: list = None) -> dict:
    """
    Drop-in replacement for ask() that records observability metrics.
    Returns the same dict as ask() plus a 'obs' key with metrics.
    """
    from main import ask  # late import to avoid circular deps

    start = time.perf_counter()
    result = ask(
        question=question,
        target_date=target_date,
        comparison_date=comparison_date,
        thread_id=thread_id,
        history=history or [],
    )
    latency_ms = round((time.perf_counter() - start) * 1000)

    structured = result.get("structured_output") or {}
    root_causes = structured.get("root_causes") or []
    actions = structured.get("recommended_actions") or []
    memory = structured.get("historical_references") or []

    domains_active = [
        d for d in ["sales", "inventory", "marketing", "support"]
        if result.get(f"{d}_analysis") is not None
    ]

    record = {
        "ts":             datetime.utcnow().isoformat(),
        "thread_id":      thread_id,
        "question":       question[:120],
        "target_date":    target_date,
        "latency_ms":     latency_ms,
        "severity":       structured.get("severity"),
        "domains_active": domains_active,
        "root_cause_count": len(root_causes),
        "action_count":   len(actions),
        "executable_actions": sum(1 for a in actions if a.get("is_executable")),
        "memory_hits":    len(memory),
        "revision_count": result.get("revision_count", 0),
        "had_execution":  bool(result.get("execution_report")),
    }

    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")

    return {**result, "obs": record}