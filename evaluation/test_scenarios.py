# evaluation/test_scenarios.py
# Curated test scenarios for the AI E-Commerce Operations Manager.
#
# Each scenario is a dict with:
#   id              : unique identifier
#   category        : type of test (full_pipeline / single_domain / memory / comparison / edge_case)
#   question        : the exact string passed to ask()
#   target_date     : date context (empty = let planner infer)
#   comparison_date : comparison date context (empty = let planner infer)
#   expected        : what we assert against the structured_output
#     - severity        : one of critical/high/medium/low (or None = don't check)
#     - domains         : list of agent domains that MUST have produced analysis
#                         (e.g. ["sales","inventory"] means both must be non-None)
#     - root_cause_keywords : at least ONE of these strings must appear in any
#                         root_cause.description (case-insensitive)
#     - min_actions     : minimum number of recommended_actions expected
#     - executable_expected : True = at least one is_executable action expected
#     - memory_expected : True = at least one historical_reference expected
#
# NOTE: DeepEval metrics (faithfulness, answer relevancy) use the LLM as judge
#       so they don't require expected fields — they score from the text itself.

from typing import TypedDict, Optional, List


class Expected(TypedDict, total=False):
    severity: Optional[str]
    domains: List[str]
    root_cause_keywords: List[str]
    min_actions: int
    executable_expected: bool
    memory_expected: bool


class Scenario(TypedDict):
    id: str
    category: str
    question: str
    target_date: str
    comparison_date: str
    expected: Expected


SCENARIOS: List[Scenario] = [

    # ── FULL PIPELINE ─────────────────────────────────────────────────────────

    {
        "id": "FP-001",
        "category": "full_pipeline",
        "question": "Why did revenue drop so much yesterday? Give me a full diagnosis.",
        "target_date": "2026-06-01",
        "comparison_date": "2026-05-31",
        "expected": {
            "severity": "critical",
            "domains": ["sales", "inventory", "marketing", "support"],
            "root_cause_keywords": ["stock", "out of stock", "nike", "facebook", "campaign"],
            "min_actions": 3,
            "executable_expected": True,
            "memory_expected": True,
        },
    },
    {
        "id": "FP-002",
        "category": "full_pipeline",
        "question": "What went wrong with the business on June 1 2026? What should we do?",
        "target_date": "2026-06-01",
        "comparison_date": "2026-05-31",
        "expected": {
            "severity": "critical",
            "domains": ["sales", "inventory", "marketing", "support"],
            "root_cause_keywords": ["stock", "campaign", "complaint", "sony"],
            "min_actions": 3,
            "executable_expected": True,
            "memory_expected": True,
        },
    },
    {
        "id": "FP-003",
        "category": "full_pipeline",
        "question": "Give me a complete operations report comparing June 1 to May 31.",
        "target_date": "2026-06-01",
        "comparison_date": "2026-05-31",
        "expected": {
            "severity": "critical",
            "domains": ["sales", "inventory", "marketing", "support"],
            "root_cause_keywords": ["revenue", "stock", "campaign"],
            "min_actions": 2,
            "executable_expected": True,
            "memory_expected": False,
        },
    },

    # ── SINGLE DOMAIN ─────────────────────────────────────────────────────────

    {
        "id": "SD-001",
        "category": "single_domain",
        "question": "Which products are currently out of stock?",
        "target_date": "2026-06-01",
        "comparison_date": "",
        "expected": {
            "severity": None,
            "domains": ["inventory"],
            "root_cause_keywords": ["nike", "sony", "stock"],
            "min_actions": 1,
            "executable_expected": True,
            "memory_expected": False,
        },
    },
    {
        "id": "SD-002",
        "category": "single_domain",
        "question": "What is the current status of our marketing campaigns?",
        "target_date": "2026-06-01",
        "comparison_date": "",
        "expected": {
            "severity": None,
            "domains": ["marketing"],
            "root_cause_keywords": ["facebook", "paused", "budget"],
            "min_actions": 1,
            "executable_expected": True,
            "memory_expected": False,
        },
    },
    {
        "id": "SD-003",
        "category": "single_domain",
        "question": "How are our customer support metrics looking? Are complaints high?",
        "target_date": "2026-06-01",
        "comparison_date": "",
        "expected": {
            "severity": None,
            "domains": ["support"],
            "root_cause_keywords": ["ticket", "complaint", "csat", "out of stock"],
            "min_actions": 1,
            "executable_expected": False,
            "memory_expected": False,
        },
    },
    {
        "id": "SD-004",
        "category": "single_domain",
        "question": "What were our sales numbers on June 1?",
        "target_date": "2026-06-01",
        "comparison_date": "",
        "expected": {
            "severity": None,
            "domains": ["sales"],
            "root_cause_keywords": ["revenue", "order", "8200"],
            "min_actions": 0,
            "executable_expected": False,
            "memory_expected": False,
        },
    },

    # ── COMPARISON ────────────────────────────────────────────────────────────

    {
        "id": "CMP-001",
        "category": "comparison",
        "question": "How does revenue on June 1 compare to May 31? What changed?",
        "target_date": "2026-06-01",
        "comparison_date": "2026-05-31",
        "expected": {
            "severity": "critical",
            "domains": ["sales"],
            "root_cause_keywords": ["revenue", "drop", "decline"],
            "min_actions": 1,
            "executable_expected": False,
            "memory_expected": False,
        },
    },
    {
        "id": "CMP-002",
        "category": "comparison",
        "question": "Did inventory levels change between May 31 and June 1?",
        "target_date": "2026-06-01",
        "comparison_date": "2026-05-31",
        "expected": {
            "severity": None,
            "domains": ["inventory"],
            "root_cause_keywords": ["stock", "nike", "sony"],
            "min_actions": 1,
            "executable_expected": True,
            "memory_expected": False,
        },
    },
    {
        "id": "CMP-003",
        "category": "comparison",
        "question": "Compare campaign performance on June 1 vs May 31.",
        "target_date": "2026-06-01",
        "comparison_date": "2026-05-31",
        "expected": {
            "severity": None,
            "domains": ["marketing"],
            "root_cause_keywords": ["facebook", "paused", "roas"],
            "min_actions": 1,
            "executable_expected": True,
            "memory_expected": False,
        },
    },

    # ── MEMORY / HISTORICAL ───────────────────────────────────────────────────

    {
        "id": "MEM-001",
        "category": "memory",
        "question": "Has this kind of stock outage happened before? What did we do last time?",
        "target_date": "2026-06-01",
        "comparison_date": "",
        "expected": {
            "severity": None,
            "domains": ["inventory"],
            "root_cause_keywords": ["stock", "outage", "restock"],
            "min_actions": 1,
            "executable_expected": True,
            "memory_expected": True,
        },
    },
    {
        "id": "MEM-002",
        "category": "memory",
        "question": "Have we ever had a campaign budget run out like this before? What was the outcome?",
        "target_date": "2026-06-01",
        "comparison_date": "",
        "expected": {
            "severity": None,
            "domains": ["marketing"],
            "root_cause_keywords": ["campaign", "budget", "facebook"],
            "min_actions": 1,
            "executable_expected": True,
            "memory_expected": True,
        },
    },

    # ── EDGE CASES ────────────────────────────────────────────────────────────

    {
        "id": "EDGE-001",
        "category": "edge_case",
        "question": "Everything looks fine today right?",  # vague positive question
        "target_date": "2026-06-01",
        "comparison_date": "",
        "expected": {
            "severity": None,   # should NOT say everything is fine — problems exist
            "domains": ["sales"],
            "root_cause_keywords": [],   # just check it runs without crashing
            "min_actions": 0,
            "executable_expected": False,
            "memory_expected": False,
        },
    },
    {
        "id": "EDGE-002",
        "category": "edge_case",
        "question": "What products should we discount right now?",
        "target_date": "2026-06-01",
        "comparison_date": "",
        "expected": {
            "severity": None,
            "domains": ["inventory", "sales"],
            "root_cause_keywords": ["discount", "available", "adidas", "yeti"],
            "min_actions": 1,
            "executable_expected": True,
            "memory_expected": False,
        },
    },
    {
        "id": "EDGE-003",
        "category": "edge_case",
        "question": "Should we pause any campaigns today?",
        "target_date": "2026-06-01",
        "comparison_date": "",
        "expected": {
            "severity": None,
            "domains": ["marketing"],
            "root_cause_keywords": ["facebook", "paused", "campaign"],
            "min_actions": 1,
            "executable_expected": True,
            "memory_expected": False,
        },
    },
]
