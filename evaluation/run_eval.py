# evaluation/run_eval.py
# Evaluation harness for the AI E-Commerce Operations Manager.
#
# What this does:
#   1. Iterates every scenario in test_scenarios.py
#   2. Calls ask() from main.py for each one (full pipeline, with HITL auto-skipped)
#   3. Runs three DeepEval LLM-as-judge metrics on the result
#   4. Checks structural assertions (domains, severity, root cause keywords, actions)
#   5. Logs each trace + scores to LangSmith (already configured in .env)
#   6. Prints a colour-coded pass/fail table + overall score
#   7. Saves full results to evaluation/results/eval_YYYYMMDD_HHMMSS.json
#
# Usage:
#   python -m evaluation.run_eval
#   python -m evaluation.run_eval --fast          # skip DeepEval LLM metrics
#   python -m evaluation.run_eval --id FP-001     # run one specific scenario
#
# NOTE: HITL is automatically bypassed during evaluation (no stdin prompts).
#       We monkey-patch hitl_node to auto-approve 0 actions (analysis-only).

import sys
import os
import json
import time
import argparse
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── LangSmith tracing (already enabled via .env) ─────────────────────────────
# LANGSMITH_TRACING=true and LANGSMITH_API_KEY are already in .env.
# LangChain reads them automatically — every ask() call will appear as a
# run in your LangSmith project "ai-ecommerce-ops".
# We also tag each eval run so you can filter by run in the LangSmith UI.
os.environ.setdefault("LANGCHAIN_TAGS", "eval")


# ── Import the streamlit-compatible graph (no HITL blocking) ──────────────────
# workflow_streamlit.py uses hitl_streamlit_node, which reads
# streamlit_approved_actions from state instead of calling input().
# Because eval never sets streamlit_approved_actions, hitl_streamlit_node
# automatically returns skip_execution=True — HITL is a no-op in eval.
# No monkey-patching or importlib.reload needed.
from graph.workflow_streamlit import streamlit_app_graph as ops_app

from graph.state import OpsState
from memory.long_term import seed_memory_from_db
import asyncio
from evaluation.test_scenarios import SCENARIOS, Scenario


# ── Conditionally import DeepEval ─────────────────────────────────────────────
try:
    from deepeval.test_case import LLMTestCase
    from evaluation.metrics import ALL_METRICS, answer_relevancy, faithfulness, ops_diagnosis_quality
    DEEPEVAL_AVAILABLE = True
except ImportError:
    DEEPEVAL_AVAILABLE = False
    print("[EVAL] DeepEval not installed — skipping LLM judge metrics.")
    print("[EVAL] Install with: pip install deepeval")


# ─────────────────────────────────────────────────────────────────────────────
# Structural assertion scorer
# ─────────────────────────────────────────────────────────────────────────────

def score_structural(scenario: Scenario, structured: dict, state_result: dict) -> dict:
    """
    Checks rule-based assertions against structured_output.
    Returns a dict of {check_name: pass/fail/skip} and a 0-1 score.
    """
    expected = scenario["expected"]
    checks   = {}

    # 1. Domain coverage — did the right agents run?
    expected_domains = expected.get("domains", [])
    if expected_domains:
        domain_map = {
            "sales":     state_result.get("sales_analysis"),
            "inventory": state_result.get("inventory_analysis"),
            "marketing": state_result.get("marketing_analysis"),
            "support":   state_result.get("support_analysis"),
        }
        domains_hit = [d for d in expected_domains if domain_map.get(d)]
        checks["domain_coverage"] = len(domains_hit) == len(expected_domains)
    else:
        checks["domain_coverage"] = None  # skip

    # 2. Severity match
    expected_sev = expected.get("severity")
    if expected_sev and structured:
        actual_sev = structured.get("severity", "").lower()
        checks["severity_match"] = actual_sev == expected_sev.lower()
    else:
        checks["severity_match"] = None  # skip

    # 3. Root cause keyword presence
    keywords = expected.get("root_cause_keywords", [])
    if keywords and structured:
        causes_text = " ".join(
            rc.get("description", "") for rc in (structured.get("root_causes") or [])
        ).lower()
        # Also check full markdown
        full_text = (structured.get("full_analysis_markdown") or "").lower()
        combined  = causes_text + " " + full_text
        found     = any(kw.lower() in combined for kw in keywords)
        checks["root_cause_keywords"] = found
    else:
        checks["root_cause_keywords"] = None  # skip

    # 4. Minimum action count
    min_actions = expected.get("min_actions", 0)
    if min_actions > 0 and structured:
        actual_actions = len(structured.get("recommended_actions") or [])
        checks["min_actions"] = actual_actions >= min_actions
    else:
        checks["min_actions"] = None  # skip

    # 5. Executable action present
    if expected.get("executable_expected") and structured:
        executable = [a for a in (structured.get("recommended_actions") or []) if a.get("is_executable")]
        checks["executable_action"] = len(executable) > 0
    else:
        checks["executable_action"] = None  # skip

    # 6. Memory / historical reference
    if expected.get("memory_expected") and structured:
        refs = structured.get("historical_references") or []
        checks["memory_retrieved"] = len(refs) > 0
    else:
        checks["memory_retrieved"] = None  # skip

    # Score = passed / (non-skipped checks)
    actual_checks = {k: v for k, v in checks.items() if v is not None}
    score = sum(actual_checks.values()) / len(actual_checks) if actual_checks else 1.0

    return {"checks": checks, "score": round(score, 3)}


# ─────────────────────────────────────────────────────────────────────────────
# DeepEval scorer
# ─────────────────────────────────────────────────────────────────────────────

def score_deepeval(scenario: Scenario, answer: str, agent_analyses: dict) -> dict:
    """
    Runs DeepEval LLM-as-judge metrics on the answer.
    Returns dict of {metric_name: score} and an average.
    """
    if not DEEPEVAL_AVAILABLE:
        return {"scores": {}, "average": None}

    # Build retrieval context from agent analyses (what synthesis had access to)
    context = [v for v in agent_analyses.values() if v]

    test_case = LLMTestCase(
        input          = scenario["question"],
        actual_output  = answer,
        retrieval_context = context if context else ["No context available."],
    )

    scores = {}
    for metric in ALL_METRICS:
        try:
            metric.measure(test_case)
            scores[metric.__class__.__name__] = round(metric.score, 3)
        except Exception as e:
            scores[metric.__class__.__name__] = f"ERROR: {e}"

    numeric = [v for v in scores.values() if isinstance(v, float)]
    average = round(sum(numeric) / len(numeric), 3) if numeric else None

    return {"scores": scores, "average": average}


# ─────────────────────────────────────────────────────────────────────────────
# Single scenario runner
# ─────────────────────────────────────────────────────────────────────────────

def run_scenario(scenario: Scenario, fast: bool = False) -> dict:
    """Runs one scenario end-to-end and returns a full result dict."""
    print(f"\n{'─'*70}")
    print(f"[{scenario['id']}] {scenario['question'][:80]}")
    print(f"  Category: {scenario['category']} | "
          f"Target: {scenario['target_date'] or 'inferred'} | "
          f"Compare: {scenario['comparison_date'] or 'none'}")

    start = time.time()

    # Build initial state directly (bypass main.py's input() prompts)
    initial_state: OpsState = {
        "user_question":    scenario["question"],
        "needs_sales":      False,
        "needs_inventory":  False,
        "needs_marketing":  False,
        "needs_support":    False,
        "sales_analysis":   None,
        "inventory_analysis": None,
        "marketing_analysis": None,
        "support_analysis": None,
        "synthesis_draft":  None,
        "critic_feedback":  None,
        "needs_revision":   False,
        "revision_count":   0,
        "final_answer":     None,
        "target_date":      scenario["target_date"],
        "comparison_date":  scenario["comparison_date"],
        "conversation_history": [],
        "proposed_actions": None,
        "action_plan_reasoning": None,
        "approved_actions": None,
        "skip_execution":   False,
        "execution_report": None,
        "execution_results": None,
        "past_incidents":   None,
        "structured_output": None,
        "streamlit_approved_actions": None,
        "streamlit_skip_execution":   False,
    }

    config = {"configurable": {"thread_id": f"eval-{scenario['id']}"}}

    try:
        result      = ops_app.invoke(initial_state, config=config)
        elapsed     = round(time.time() - start, 1)
        answer      = result.get("final_answer") or result.get("synthesis_draft") or ""
        structured  = result.get("structured_output") or {}

        # Structural checks
        structural_result = score_structural(scenario, structured, result)

        # DeepEval checks
        agent_analyses = {
            "sales":     result.get("sales_analysis"),
            "inventory": result.get("inventory_analysis"),
            "marketing": result.get("marketing_analysis"),
            "support":   result.get("support_analysis"),
        }
        deepeval_result = {} if fast else score_deepeval(scenario, answer, agent_analyses)

        # Overall pass = structural score >= 0.75
        passed = structural_result["score"] >= 0.75

        print(f"  ✅ PASS" if passed else f"  ❌ FAIL",
              f"| Structural: {structural_result['score']:.0%}",
              f"| DeepEval avg: {deepeval_result.get('average', 'skipped')}",
              f"| {elapsed}s")

        return {
            "id":          scenario["id"],
            "category":    scenario["category"],
            "question":    scenario["question"],
            "passed":      passed,
            "elapsed_s":   elapsed,
            "structural":  structural_result,
            "deepeval":    deepeval_result,
            "severity":    structured.get("severity"),
            "one_liner":   structured.get("one_liner"),
            "error":       None,
        }

    except Exception as e:
        elapsed = round(time.time() - start, 1)
        print(f"  💥 ERROR after {elapsed}s: {e}")
        return {
            "id":        scenario["id"],
            "category":  scenario["category"],
            "question":  scenario["question"],
            "passed":    False,
            "elapsed_s": elapsed,
            "structural": {},
            "deepeval":   {},
            "severity":   None,
            "one_liner":  None,
            "error":      str(e),
        }


# ─────────────────────────────────────────────────────────────────────────────
# Report printer
# ─────────────────────────────────────────────────────────────────────────────

def print_report(results: list[dict]) -> None:
    total   = len(results)
    passed  = sum(1 for r in results if r["passed"])
    failed  = total - passed
    avg_lat = round(sum(r["elapsed_s"] for r in results) / total, 1) if total else 0

    print(f"\n{'═'*70}")
    print(f"  EVALUATION REPORT  —  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'═'*70}")
    print(f"  {'ID':<12} {'Cat':<14} {'Struct':>7} {'DeepEval':>9} {'Time':>6}  {'Result'}")
    print(f"  {'─'*12} {'─'*14} {'─'*7} {'─'*9} {'─'*6}  {'─'*6}")

    for r in results:
        struct_score = r.get("structural", {}).get("score")
        de_avg       = r.get("deepeval", {}).get("average")
        struct_str   = f"{struct_score:.0%}" if struct_score is not None else "N/A"
        de_str       = f"{de_avg:.2f}"       if de_avg       is not None else "skip"
        result_str   = "✅ PASS" if r["passed"] else ("💥 ERR" if r["error"] else "❌ FAIL")
        print(f"  {r['id']:<12} {r['category']:<14} {struct_str:>7} {de_str:>9} {r['elapsed_s']:>5.1f}s  {result_str}")

    print(f"{'─'*70}")
    print(f"  TOTAL: {passed}/{total} passed ({passed/total:.0%})  |  "
          f"Failed: {failed}  |  Avg latency: {avg_lat}s")
    print(f"{'═'*70}\n")

    # Per-category breakdown
    categories = sorted({r["category"] for r in results})
    print("  By category:")
    for cat in categories:
        cat_results = [r for r in results if r["category"] == cat]
        cat_pass    = sum(1 for r in cat_results if r["passed"])
        print(f"    {cat:<18}  {cat_pass}/{len(cat_results)} passed")
    print()


# ─────────────────────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Run evaluation suite")
    parser.add_argument("--fast",  action="store_true",
                        help="Skip DeepEval LLM judge metrics (structural checks only)")
    parser.add_argument("--id",    type=str, default=None,
                        help="Run only the scenario with this ID (e.g. FP-001)")
    parser.add_argument("--category", type=str, default=None,
                        help="Run only scenarios in this category (e.g. full_pipeline)")
    args = parser.parse_args()

    # Seed long-term memory
    print("[EVAL] Seeding long-term memory...")
    asyncio.run(seed_memory_from_db())

    # Filter scenarios
    scenarios = SCENARIOS
    if args.id:
        scenarios = [s for s in scenarios if s["id"] == args.id]
    elif args.category:
        scenarios = [s for s in scenarios if s["category"] == args.category]

    if not scenarios:
        print(f"[EVAL] No scenarios matched. Available IDs: {[s['id'] for s in SCENARIOS]}")
        sys.exit(1)

    print(f"[EVAL] Running {len(scenarios)} scenario(s)"
          f"{' (fast mode — no DeepEval)' if args.fast else ''}")
    print(f"[EVAL] LangSmith project: {os.getenv('LANGSMITH_PROJECT', 'not set')}\n")

    results = []
    for scenario in scenarios:
        result = run_scenario(scenario, fast=args.fast)
        results.append(result)

    print_report(results)

    # Save JSON results
    out_dir  = Path(__file__).parent / "results"
    out_dir.mkdir(exist_ok=True)
    out_file = out_dir / f"eval_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(out_file, "w") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "total": len(results),
            "passed": sum(1 for r in results if r["passed"]),
            "results": results,
        }, f, indent=2)
    print(f"[EVAL] Results saved to {out_file}")


if __name__ == "__main__":
    main()
