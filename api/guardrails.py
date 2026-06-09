# Lightweight input guardrails applied at the API boundary.
#
# This is NOT a defense against a determined attacker — that requires a model-
# based classifier (Llama Guard, Prompt Shield, etc.). The goal here is to
# catch the cheapest 90% of accidents and obvious prompt-injection attempts
# before they reach the planner LLM:
#
#   - cap question length (kills runaway pastes and DoS attempts)
#   - reject empty / whitespace-only questions
#   - flag the most common injection markers (system-prompt overrides,
#     "ignore previous instructions", role-play jailbreaks, raw role headers)
#
# Anything flagged returns HTTP 400 from the FastAPI layer.

import re
from fastapi import HTTPException

MAX_QUESTION_LEN = 2000

# Compiled once at import time. Patterns are intentionally loose — we accept
# some false positives over false negatives at this layer because the user can
# always rephrase, but a successful injection silently corrupts the analysis.
_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?(previous|prior|above)\s+(instructions?|prompts?|rules?)", re.I),
    re.compile(r"disregard\s+(all\s+)?(previous|prior|above)\s+(instructions?|prompts?|rules?)", re.I),
    re.compile(r"forget\s+(everything|all)\s+(you|i)\s+(have\s+)?(told|said|wrote)", re.I),
    re.compile(r"you\s+are\s+now\s+(a|an)\s+", re.I),
    re.compile(r"act\s+as\s+(a|an)\s+(?:dan|jailbroken|developer\s+mode)", re.I),
    re.compile(r"###\s*(system|assistant|user)\s*[:#]", re.I),
    re.compile(r"<\s*\|?\s*(system|im_start|im_end)\s*\|?\s*>", re.I),
    re.compile(r"reveal\s+(your|the)\s+(system\s+)?(prompt|instructions)", re.I),
]


def validate_question(question: str) -> str:
    """Validates a user question. Returns the trimmed question, or raises HTTP 400."""
    if not question or not question.strip():
        raise HTTPException(status_code=400, detail="Question must not be empty.")

    q = question.strip()

    if len(q) > MAX_QUESTION_LEN:
        raise HTTPException(
            status_code=400,
            detail=f"Question exceeds {MAX_QUESTION_LEN} characters (got {len(q)}).",
        )

    for pat in _INJECTION_PATTERNS:
        if pat.search(q):
            raise HTTPException(
                status_code=400,
                detail="Question rejected by input guardrail (suspected prompt injection).",
            )

    return q
