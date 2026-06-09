# Reads observability/runs.jsonl and prints a summary dashboard.
# Run: python -m observability.dashboard

import json
from pathlib import Path
from collections import Counter

LOG_FILE = Path(__file__).parent / "runs.jsonl"


def load_runs() -> list[dict]:
    if not LOG_FILE.exists():
        return []
    return [json.loads(l) for l in LOG_FILE.read_text(encoding="utf-8").splitlines() if l.strip()]


def print_dashboard():
    runs = load_runs()
    if not runs:
        print("No runs recorded yet. Use observability.tracker.track() instead of ask().")
        return

    total = len(runs)
    avg_latency = round(sum(r["latency_ms"] for r in runs) / total)
    p95_latency = sorted(r["latency_ms"] for r in runs)[int(total * 0.95)]
    severity_counts = Counter(r["severity"] for r in runs if r["severity"])
    domain_counts   = Counter(d for r in runs for d in r["domains_active"])
    avg_revisions   = round(sum(r["revision_count"] for r in runs) / total, 2)
    memory_hit_rate = round(sum(1 for r in runs if r["memory_hits"] > 0) / total * 100, 1)
    exec_rate       = round(sum(1 for r in runs if r["had_execution"]) / total * 100, 1)

    print("\n" + "=" * 55)
    print(f"  OBSERVABILITY DASHBOARD  ({total} runs)")
    print("=" * 55)
    print(f"  Avg latency        : {avg_latency} ms")
    print(f"  P95 latency        : {p95_latency} ms")
    print(f"  Avg critic revisions: {avg_revisions}")
    print(f"  Memory hit rate    : {memory_hit_rate}%")
    print(f"  Action exec rate   : {exec_rate}%")
    print()
    print("  Severity distribution:")
    for sev, cnt in severity_counts.most_common():
        print(f"    {sev:<10} {cnt:>4}  {'█' * cnt}")
    print()
    print("  Domain activation:")
    for dom, cnt in domain_counts.most_common():
        print(f"    {dom:<12} {cnt:>4}  ({round(cnt/total*100)}%)")
    print("=" * 55 + "\n")

    # Last 5 runs
    print("  Recent runs:")
    print(f"  {'Time':<20} {'Severity':<10} {'Latency':>8}  {'Domains'}")
    print("  " + "-" * 53)
    for r in runs[-5:]:
        ts = r["ts"][:19].replace("T", " ")
        domains = ",".join(r["domains_active"])
        print(f"  {ts:<20} {str(r['severity']):<10} {r['latency_ms']:>6}ms  {domains}")
    print()


if __name__ == "__main__":
    print_dashboard()