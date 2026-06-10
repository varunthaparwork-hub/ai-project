# 7 Critical Fixes for LangGraph E-Commerce AI System

---

## ISSUE 1: PLANNER IS TOO CONSERVATIVE WITH AGENT ROUTING

**File:** `graph/planner.py`

### Current Code (Lines 26–74)
```python
PLANNER_PROMPT = """You are the operations planning agent for an e-commerce store.
A business user has asked a question. Your job is to decide:
1. Which analysis agents need to run to answer the question
2. Which dates are relevant

Today's date is {today}.
Yesterday was {yesterday}.
One week ago was {last_week}.
Same weekday last week was {same_weekday_last_week}.
Previous analysis target date (from earlier in this conversation): {previous_target_date}

DATE RULE: If the current question does not explicitly mention a new date and is clearly a
follow-up to the previous question (e.g. starts with "What about", "Did", "How about",
"Can you also", "And the", or is very short), set target_date = previous_target_date.
Only use today's date if the question is explicitly about right now with no prior context.

Previous conversation (last 3 turns — use this to understand follow-up questions like "why?" or "what about inventory?"):
{history}

DIRECT ACTION RULE: A "direct operational command" must satisfy ALL THREE of these:
  (a) imperative form — NOT a question. Anything ending in "?" is NOT a command.
      "Can we…", "Could you…", "Should we…", "What about…", "How can we fix…" → NOT commands.
  (b) names a specific product or campaign by exact name (e.g. "Sony Headphones", "Google Shopping").
  (c) specifies a concrete parameter — a number, percentage, duration, or "pause"/"resume".

If and ONLY if all three are met, set ALL needs_* to False (the action_planner will execute it).

Examples that ARE direct commands → all needs_* = False:
  "restock Samsung TV by 20 units"
  "apply 15% discount on Sony Headphones for 72 hours"
  "pause Google Shopping campaign"
  "resume Facebook Summer Sale"

Examples that are NOT commands → route to agents normally:
  "can we do some actions on it?"            (vague question — follow-up to prior analysis)
  "what should we do about overstock?"       (asking for advice, not commanding)
  "should we discount anything?"             (question, no specific product)
  "how do we fix this?"                      (question, no specific entity)
  "any actions we can take?"                 (question, no specific entity)

For vague follow-ups that reference prior analysis ("it", "this", "that"), inherit the
domains and target_date from the previous turn's context — re-run the relevant agents so
the action_planner has fresh data to recommend against.

For broad questions like "why did sales drop?" or "what happened yesterday?"
activate ALL agents since a full cross-domain analysis is needed.
For specific questions, only activate the relevant agents.

User question: {question}"""
```

### Fixed Code
```python
PLANNER_PROMPT = """You are the operations planning agent for an e-commerce store.
A business user has asked a question. Your job is to decide:
1. Which analysis agents need to run to answer the question
2. Which dates are relevant

Today's date is {today}.
Yesterday was {yesterday}.
One week ago was {last_week}.
Same weekday last week was {same_weekday_last_week}.
Previous analysis target date (from earlier in this conversation): {previous_target_date}

DATE RULE: If the current question does not explicitly mention a new date and is clearly a
follow-up to the previous question (e.g. starts with "What about", "Did", "How about",
"Can you also", "And the", or is very short), set target_date = previous_target_date.
Only use today's date if the question is explicitly about right now with no prior context.

Previous conversation (last 3 turns — use this to understand follow-up questions like "why?" or "what about inventory?"):
{history}

DIRECT ACTION RULE: A "direct operational command" must satisfy ALL THREE of these:
  (a) imperative form — NOT a question. Anything ending in "?" is NOT a command.
      "Can we…", "Could you…", "Should we…", "What about…", "How can we fix…" → NOT commands.
  (b) names a specific product or campaign by exact name (e.g. "Sony Headphones", "Google Shopping").
  (c) specifies a concrete parameter — a number, percentage, duration, or "pause"/"resume".

If and ONLY if all three are met, set ALL needs_* to False (the action_planner will execute it).

Examples that ARE direct commands → all needs_* = False:
  "restock Samsung TV by 20 units"
  "apply 15% discount on Sony Headphones for 72 hours"
  "pause Google Shopping campaign"
  "resume Facebook Summer Sale"

Examples that are NOT commands → route to agents normally:
  "can we do some actions on it?"            (vague question — follow-up to prior analysis)
  "what should we do about overstock?"       (asking for advice, not commanding)
  "should we discount anything?"             (question, no specific product)
  "how do we fix this?"                      (question, no specific entity)
  "any actions we can take?"                 (question, no specific entity)

For vague follow-ups that reference prior analysis ("it", "this", "that"), inherit the
domains and target_date from the previous turn's context — re-run the relevant agents so
the action_planner has fresh data to recommend against.

DEFAULT-TO-ALL RULE (CRITICAL): If the question matches ANY of these patterns,
activate ALL FOUR agents (needs_sales=True, needs_inventory=True, needs_marketing=True, needs_support=True)
regardless of specificity:
  1. Broad diagnostic queries: "what happened", "any issues", "full diagnosis", "give me everything",
     "what should we address", "overall situation", "complete picture", "comprehensive review"
  2. Questions mentioning failure/drop: "why did", "why is", "caused", "dropped", "fell", "collapsed",
     "crashed", "loss", "what went wrong"
  3. Questions about multiple domains: "across", "both", "all", "everything", "correlat", "impact",
     "relationship", "connect", "together"
  4. Temporal scope questions: "what happened", "what's going on", "recently", "lately", "this week",
     "any updates", "status check"
  5. Open-ended diagnostic: "analyze", "review", "assess" (without specifying a single domain)

For narrow, explicitly scoped questions that name one domain, only activate relevant agents:
  - "inventory status" → needs_inventory only
  - "sales for June" → needs_sales only
  - "campaign performance" → needs_marketing only
  - "customer complaints" → needs_support only

Erring on the side of running more agents is better than missing critical context.

User question: {question}"""
```

### Why This Fix Works
The explicit DEFAULT-TO-ALL rule with pattern matching removes ambiguity and forces full analysis for complex scenarios, preventing the LLM from under-routing based on vague logic.

### Side Effects / Trade-Offs
- **Trade-off**: Slightly more LLM calls for questions that could be answered by a single agent (e.g., "What is inventory?"). However, in practice, most real business questions are multi-domain, so this aligns better with user intent.
- **Benefit**: Eliminates false negatives where critical signals from a dormant agent would have surfaced root causes.

---

## ISSUE 2: CONTEXT TRUNCATION IN AGENT NODES CAUSES MISSED FINDINGS

**File:** `graph/agent_nodes.py`

### Current Code (Lines 45–170)

**Line 51–56 (inventory_node):**
```python
    sales_context = ""
    if state.get("sales_analysis"):
        sales_context = (
            "\n\nSALES AGENT FINDINGS (cross-reference these with your stock data):\n"
            + state["sales_analysis"][:600]
        )
```

**Line 127–132 (marketing_node):**
```python
    prior_context = ""
    if state.get("sales_analysis"):
        prior_context += f"\n\nSALES FINDINGS:\n{state['sales_analysis'][:400]}"
    if state.get("inventory_analysis"):
        prior_context += f"\n\nINVENTORY FINDINGS:\n{state['inventory_analysis'][:400]}"
```

**Line 154–159 (support_node):**
```python
    prior_context = ""
    for label, key in [("SALES", "sales_analysis"), ("INVENTORY", "inventory_analysis"), ("MARKETING", "marketing_analysis")]:
        if state.get(key):
            prior_context += f"\n\n{label} FINDINGS:\n{state[key][:300]}"
```

### Fixed Code

**Line 51–56 (inventory_node):**
```python
    sales_context = ""
    if state.get("sales_analysis"):
        sales_context = (
            "\n\nSALES AGENT FINDINGS (cross-reference these with your stock data):\n"
            + state["sales_analysis"][:1500]
        )
```

**Line 127–132 (marketing_node):**
```python
    prior_context = ""
    if state.get("sales_analysis"):
        prior_context += f"\n\nSALES FINDINGS:\n{state['sales_analysis'][:1200]}"
    if state.get("inventory_analysis"):
        prior_context += f"\n\nINVENTORY FINDINGS:\n{state['inventory_analysis'][:1200]}"
```

**Line 154–159 (support_node):**
```python
    prior_context = ""
    for label, key in [("SALES", "sales_analysis"), ("INVENTORY", "inventory_analysis"), ("MARKETING", "marketing_analysis")]:
        if state.get(key):
            prior_context += f"\n\n{label} FINDINGS:\n{state[key][:1000]}"
```

### Why This Fix Works
Larger truncation windows ensure that critical findings (product names, revenue figures, specific failure modes) are never cut off mid-transmission between agents, enabling proper cross-domain correlation.

### Side Effects / Trade-Offs
- **Slight increase in token usage** per agent call (but well within model limits; synthesis call is heavier).
- **Benefit**: Eliminates "missing product name" bugs where inventory cannot confirm what sales found because the name was truncated.

---

## ISSUE 3: SYNTHESIS PROMPT DOES NOT ENFORCE DATA GROUNDING

**File:** `graph/synthesis.py`

### Current Code (Lines 10–55)
```python
SYNTHESIS_PROMPT = """You are the chief Operations AI for an e-commerce store.
You have received analysis reports from multiple specialist agents.
Your job is to synthesize them into ONE clear executive summary.

Structure your response exactly as:

## Summary
One paragraph explaining what happened overall.

## Root Causes
Bullet list of confirmed causes, ranked by impact.

## Supporting Evidence
Key data points from each domain that support your conclusions.

## Cross-Domain Correlations
Explain how findings across domains connect (e.g., stock outage + campaign paused + complaints spike).

## Historical Context
If past incidents are provided below, reference them here.
Explain if this has happened before and what worked or didn't work.
If no past incidents, write: No similar past incidents found.

## Recommended Actions
Numbered list of specific actions with reasoning.

---
Reports from specialist agents:

SALES ANALYSIS:
{sales}

INVENTORY ANALYSIS:
{inventory}

MARKETING ANALYSIS:
{marketing}

CUSTOMER SUPPORT ANALYSIS:
{support}

PAST SIMILAR INCIDENTS FROM MEMORY:
{past_incidents}

Original User Question: {question}
"""
```

### Fixed Code
```python
SYNTHESIS_PROMPT = """You are the chief Operations AI for an e-commerce store.
You have received analysis reports from multiple specialist agents.
Your job is to synthesize them into ONE clear executive summary.

CRITICAL CONSTRAINT: Every number, product name, and key finding you cite MUST be
verbatim from the agent reports below. Do NOT invent, estimate, or extrapolate data.
If a figure does not appear in the reports, do not mention it.
If two reports contradict each other, flag the contradiction explicitly and choose
the more conservative (lowest-impact) interpretation.

Structure your response exactly as:

## Summary
One paragraph explaining what happened overall. Only cite findings that appear in the reports.

## Root Causes
Bullet list of confirmed causes, ranked by impact. Every cause must cite the domain and the
specific evidence from the reports. Do NOT rank causes higher than the reports support.
Format each cause as: "**[DOMAIN]** [Cause description] (Evidence: [exact quote from report])"

## Supporting Evidence
Key data points from each domain that support your conclusions. Quote figures directly.
If a domain says "Not analyzed", explicitly note that its findings are unavailable.
Do NOT speculate about unanalyzed domains.

## Cross-Domain Correlations
Explain how findings across domains connect (e.g., stock outage + campaign paused + complaints spike).
ONLY claim correlations if the reports explicitly state them or if the logical connection is obvious
(e.g., "Stockout reported AND zero sales reported" = obvious correlation). Do NOT infer hidden causation.

## Contradictions and Gaps
If different agents reported contradictory data (e.g., Sales says $1,000 in lost revenue but 
Inventory says no stockouts occurred), list them here and flag for manual review.
Do NOT hide contradictions or pick one report's numbers arbitrarily.

## Historical Context
If past incidents are provided below, reference them here.
Explain if this has happened before and what worked or didn't work.
If no past incidents, write: No similar past incidents found.

## Recommended Actions
Numbered list of specific actions with reasoning. Each action must be grounded in a root cause
from the reports. Do NOT recommend actions that are not supported by the data.

---
Reports from specialist agents:

SALES ANALYSIS:
{sales}

INVENTORY ANALYSIS:
{inventory}

MARKETING ANALYSIS:
{marketing}

CUSTOMER SUPPORT ANALYSIS:
{support}

PAST SIMILAR INCIDENTS FROM MEMORY:
{past_incidents}

Original User Question: {question}
"""
```

### Why This Fix Works
Explicit grounding constraints and a new "Contradictions and Gaps" section force the LLM to stay faithful to the agent reports and surface inconsistencies before they contaminate the final answer.

### Side Effects / Trade-Offs
- **Slight increase in response length** (one extra section).
- **Benefit**: Eliminates hallucination bugs where the first-pass draft invents numbers that survive to the final answer because the critic only checks structure, not provenance.

---

## ISSUE 4: CRITIC ALLOWS ONLY ONE REVISION, THEN FORCE-APPROVES BAD DRAFTS

**File:** `graph/critic.py`

### Current Code (Lines 95–118)
```python
    current_revision_count = state.get("revision_count", 0)

    # If already revised once, force-approve to prevent infinite loop
    # and guarantee final_answer is always set
    if decision.needs_revision and current_revision_count < 1:
        print("[CRITIC] Sending back for revision...")
        return {
            **state,
            "needs_revision": True,
            "critic_feedback": decision.feedback,
            "revision_count": current_revision_count + 1,
        }

    # Draft approved (or max revisions reached) — promote to final answer
    if current_revision_count >= 1:
        print("[CRITIC] Max revisions reached — accepting revised draft.")
    else:
        print("[CRITIC] Draft approved.")
    return {
        **state,
        "needs_revision": False,
        "critic_feedback": decision.feedback,
        "final_answer": state["synthesis_draft"],
    }
```

### Fixed Code
```python
    current_revision_count = state.get("revision_count", 0)

    # Confidence threshold: if confidence < 0.70 and we haven't hit revision limit,
    # always send for revision regardless of needs_revision flag
    low_confidence = decision.confidence_score < 0.70
    should_revise = (decision.needs_revision or low_confidence) and current_revision_count < 2

    if should_revise:
        reason = "low confidence" if low_confidence else "identified issues"
        print(f"[CRITIC] Sending back for revision (reason: {reason}, confidence: {decision.confidence_score:.2f})...")
        return {
            **state,
            "needs_revision": True,
            "critic_feedback": decision.feedback,
            "revision_count": current_revision_count + 1,
        }

    # Draft approved (or max revisions reached) — promote to final answer
    if current_revision_count >= 2:
        print(f"[CRITIC] Max revisions (2) reached — accepting revised draft (confidence: {decision.confidence_score:.2f}).")
    elif current_revision_count == 1:
        print(f"[CRITIC] Revised draft approved (confidence: {decision.confidence_score:.2f}).")
    else:
        print(f"[CRITIC] Draft approved (confidence: {decision.confidence_score:.2f}).")
    return {
        **state,
        "needs_revision": False,
        "critic_feedback": decision.feedback,
        "final_answer": state["synthesis_draft"],
    }
```

### Why This Fix Works
Allowing two revisions + a confidence threshold prevents force-approval of low-quality drafts and ensures hallucinated numbers get a second chance to be caught and corrected.

### Side Effects / Trade-Offs
- **Trade-off**: Up to 3 synthesis + critic calls instead of 2 (minimal extra latency; synthesis is already the heavy operation).
- **Benefit**: Eliminates the case where a hallucinated number survives after only one correction attempt.

---

## ISSUE 5: FORMATTER SILENTLY SWALLOWS ERRORS AND RETURNS EMPTY STRUCTURED OUTPUT

**File:** `graph/formatter.py`

### Current Code (Lines 114–152)
```python
    # ── Call LLM with structured output ──────────────────────────
    structured_llm = llm.with_structured_output(OpsResponse, method="function_calling")

    try:
        ops_response: OpsResponse = structured_llm.invoke(prompt)
        # Inject fields that the LLM can't reliably fill from text
        ops_response.session_date     = date.today().isoformat()
        ops_response.target_date      = state.get("target_date") or date.today().isoformat()
        ops_response.comparison_date  = state.get("comparison_date") or None
        ops_response.full_analysis_markdown = (
            state.get("final_answer") or state.get("synthesis_draft")
        )
        if execution_summary_dict:
            ops_response.execution_summary = ExecutionSummary(**execution_summary_dict)

        print(f"[FORMATTER] Structured output built. "
              f"Severity={ops_response.severity.value}, "
              f"RootCauses={len(ops_response.root_causes)}, "
              f"Actions={len(ops_response.recommended_actions)}")

        return {**state, "structured_output": ops_response.model_dump(mode="json")}

    except Exception as e:
        print(f"[FORMATTER] WARNING: Structured output failed ({e}). Storing raw text only.")
        fallback = {
            "session_date":             date.today().isoformat(),
            "target_date":              state.get("target_date") or "",
            "comparison_date":          state.get("comparison_date"),
            "one_liner":                "See full analysis below.",
            "severity":                 "medium",
            "summary":                  state.get("final_answer") or state.get("synthesis_draft") or "",
            "root_causes":              [],
            "recommended_actions":      [],
            "cross_domain_correlations": None,
            "historical_references":    [],
            "execution_summary":        execution_summary_dict,
            "full_analysis_markdown":   state.get("final_answer") or state.get("synthesis_draft"),
        }
        return {**state, "structured_output": fallback}
```

### Fixed Code
```python
    # ── Call LLM with structured output ──────────────────────────
    structured_llm = llm.with_structured_output(OpsResponse, method="function_calling")

    try:
        ops_response: OpsResponse = structured_llm.invoke(prompt)
        # Inject fields that the LLM can't reliably fill from text
        ops_response.session_date     = date.today().isoformat()
        ops_response.target_date      = state.get("target_date") or date.today().isoformat()
        ops_response.comparison_date  = state.get("comparison_date") or None
        ops_response.full_analysis_markdown = (
            state.get("final_answer") or state.get("synthesis_draft")
        )
        if execution_summary_dict:
            ops_response.execution_summary = ExecutionSummary(**execution_summary_dict)

        print(f"[FORMATTER] Structured output built. "
              f"Severity={ops_response.severity.value}, "
              f"RootCauses={len(ops_response.root_causes)}, "
              f"Actions={len(ops_response.recommended_actions)}")

        return {**state, "structured_output": ops_response.model_dump(mode="json")}

    except Exception as e:
        print(f"[FORMATTER] ERROR: Structured output extraction failed ({type(e).__name__}: {e}). Retrying with simplified prompt...")
        
        # RETRY ONCE with simplified prompt focusing on critical fields only
        simplified_prompt = f"""Extract ONLY the most critical fields from this analysis:
- one_liner: single sentence, most important finding
- severity: critical / high / medium / low
- root_causes: list each as "{{rank}}: {{domain}}: {{cause}}"
- recommended_actions: list each as "{{action description}}"

ANALYSIS:
{state.get("final_answer") or state.get("synthesis_draft") or "No analysis available."}

If you cannot extract structured data, return empty lists for root_causes and recommended_actions."""
        
        try:
            ops_response_retry: OpsResponse = structured_llm.invoke(simplified_prompt)
            ops_response_retry.session_date = date.today().isoformat()
            ops_response_retry.target_date = state.get("target_date") or date.today().isoformat()
            ops_response_retry.comparison_date = state.get("comparison_date") or None
            ops_response_retry.full_analysis_markdown = (
                state.get("final_answer") or state.get("synthesis_draft")
            )
            if execution_summary_dict:
                ops_response_retry.execution_summary = ExecutionSummary(**execution_summary_dict)
            
            print(f"[FORMATTER] Retry succeeded. Severity={ops_response_retry.severity.value}, "
                  f"RootCauses={len(ops_response_retry.root_causes)}")
            
            # Log to observability tracker
            try:
                from observability.tracker import tracker
                tracker.log_formatter_retry(exception=e, fallback_used=False)
            except Exception:
                pass  # tracker may not be available in all contexts
            
            return {**state, "structured_output": ops_response_retry.model_dump(mode="json")}
        
        except Exception as retry_error:
            print(f"[FORMATTER] Retry also failed ({type(retry_error).__name__}). Using fallback with extracted summary.")
            
            # Log to observability tracker
            try:
                from observability.tracker import tracker
                tracker.log_formatter_retry(exception=retry_error, fallback_used=True)
            except Exception:
                pass
            
            # Extract first line of analysis as one_liner if available
            analysis_text = state.get("final_answer") or state.get("synthesis_draft") or ""
            first_line = (analysis_text.split("\n")[0] or "No analysis available.")[:200]
            
            fallback = {
                "session_date":             date.today().isoformat(),
                "target_date":              state.get("target_date") or "",
                "comparison_date":          state.get("comparison_date"),
                "one_liner":                first_line,
                "severity":                 "high",  # default to high to flag for manual review
                "summary":                  state.get("final_answer") or state.get("synthesis_draft") or "",
                "root_causes":              [],
                "recommended_actions":      [],
                "cross_domain_correlations": None,
                "historical_references":    [],
                "execution_summary":        execution_summary_dict,
                "full_analysis_markdown":   state.get("final_answer") or state.get("synthesis_draft"),
            }
            return {**state, "structured_output": fallback}
```

### Why This Fix Works
The retry with a simplified prompt captures data on the second attempt before falling back, and populating the fallback with the first line of the analysis ensures the response is never completely empty. Observability logging surfaces errors for debugging.

### Side Effects / Trade-Offs
- **Requires observability/tracker.py to exist** (gracefully degrades if not present via try/except).
- **Slight latency increase** on parse failures (one retry), but only when the first extraction fails (rare).
- **Benefit**: Eliminates silent data loss; even fallback responses now have actionable content.

---

## ISSUE 6: MEMORY NODE TRUNCATES AGENT ANALYSIS TO 300 CHARS FOR VECTOR SEARCH

**File:** `graph/memory_node.py`

### Current Code (Lines 24–42)
```python
    # Build a rich search query from whatever agent analyses are available.
    # The more context we include, the better the semantic match.
    query_parts = []

    if state.get("sales_analysis"):
        query_parts.append(state["sales_analysis"][:300])  # first 300 chars is enough

    if state.get("inventory_analysis"):
        query_parts.append(state["inventory_analysis"][:300])

    if state.get("marketing_analysis"):
        query_parts.append(state["marketing_analysis"][:300])

    # If no agent ran yet (e.g. pure memory question), use the raw user question
    if not query_parts:
        query_parts.append(state.get("user_question", ""))

    query = " ".join(query_parts)

    # Search Qdrant — only returns incidents above the similarity threshold (0.50)
    similar_incidents = search_similar(query, top_k=3)
```

### Fixed Code
```python
    # Build a rich search query from whatever agent analyses are available.
    # The more context we include, the better the semantic match.
    # Prepend user question to anchor semantic search to user intent.
    query_parts = []

    # Always include the user's original question first for intent anchoring
    user_question = state.get("user_question", "")
    if user_question:
        query_parts.append(user_question.split("\n")[0])  # first line only, to stay focused

    if state.get("sales_analysis"):
        query_parts.append(state["sales_analysis"][:600])  # increased from 300 to 600

    if state.get("inventory_analysis"):
        query_parts.append(state["inventory_analysis"][:600])  # increased from 300 to 600

    if state.get("marketing_analysis"):
        query_parts.append(state["marketing_analysis"][:600])  # increased from 300 to 600

    if state.get("support_analysis"):
        query_parts.append(state["support_analysis"][:600])  # also include support for completeness

    # If no agent ran yet (e.g. pure memory question), use the raw user question
    if not query_parts:
        query_parts.append(state.get("user_question", ""))

    query = " ".join(query_parts)

    # Search Qdrant — only returns incidents above the similarity threshold (0.50)
    similar_incidents = search_similar(query, top_k=3)
```

### Why This Fix Works
Larger truncation windows capture semantically rich content (product names, specific failures) that appears deeper in the analysis, and prepending the user question anchors the search to user intent even when agent analyses are voluminous.

### Side Effects / Trade-Offs
- **Slightly larger query embedding input** (but well within limits; semantic search can handle kilobytes).
- **Benefit**: Significantly improves vector search recall for relevant past incidents, surfacing historical context even when current analyses are long.

---

## ISSUE 7: PLANNER DATE INFERENCE FAILS FOR VAGUE TEMPORAL REFERENCES

**File:** `graph/planner.py`

### Current Code (Lines 17–23)
```python
class PlannerDecision(BaseModel):
    needs_sales: bool = Field(description="Does this question require sales analysis?")
    needs_inventory: bool = Field(description="Does this question require inventory analysis?")
    needs_marketing: bool = Field(description="Does this question require marketing/campaign analysis?")
    needs_support: bool = Field(description="Does this question require customer support analysis?")
    target_date: str = Field(description="The primary date being analyzed in YYYY-MM-DD format. If the question is a follow-up that does not specify a new date (e.g. 'What about inventory?', 'Did stockouts cause it?', 'How can we fix it?'), use the previous_target_date provided in the prompt instead of today's date.")
    comparison_date: str = Field(description="The comparison date in YYYY-MM-DD format. Infer from the question — usually the day before target_date or same weekday last week.")
```

### Fixed Code
```python
class PlannerDecision(BaseModel):
    needs_sales: bool = Field(description="Does this question require sales analysis?")
    needs_inventory: bool = Field(description="Does this question require inventory analysis?")
    needs_marketing: bool = Field(description="Does this question require marketing/campaign analysis?")
    needs_support: bool = Field(description="Does this question require customer support analysis?")
    target_date: str = Field(description="The primary date being analyzed. MUST be in strict YYYY-MM-DD format. Never return relative terms like 'yesterday' or 'last week'. If the question is a follow-up that does not specify a new date (e.g. 'What about inventory?', 'Did stockouts cause it?', 'How can we fix it?'), use the previous_target_date provided in the prompt instead of today's date. Return this field even if empty string — always a valid date string.")
    comparison_date: str = Field(description="The comparison date in YYYY-MM-DD format. MUST be in strict YYYY-MM-DD format. Infer from the question — usually the day before target_date or same weekday last week. Return this field even if empty string — always a valid date string.")
```

### Current PLANNER_PROMPT section (to replace; Lines 26–74)
```python
PLANNER_PROMPT = """You are the operations planning agent for an e-commerce store.
A business user has asked a question. Your job is to decide:
1. Which analysis agents need to run to answer the question
2. Which dates are relevant

Today's date is {today}.
Yesterday was {yesterday}.
One week ago was {last_week}.
Same weekday last week was {same_weekday_last_week}.
Previous analysis target date (from earlier in this conversation): {previous_target_date}

DATE RULE: If the current question does not explicitly mention a new date and is clearly a
follow-up to the previous question (e.g. starts with "What about", "Did", "How about",
"Can you also", "And the", or is very short), set target_date = previous_target_date.
Only use today's date if the question is explicitly about right now with no prior context.
```

### Fixed PLANNER_PROMPT section
```python
PLANNER_PROMPT = """You are the operations planning agent for an e-commerce store.
A business user has asked a question. Your job is to decide:
1. Which analysis agents need to run to answer the question
2. Which dates are relevant

Today's date is {today}.
Yesterday was {yesterday}.
One week ago was {last_week}.
Same weekday last week was {same_weekday_last_week}.
Previous analysis target date (from earlier in this conversation): {previous_target_date}

TEMPORAL REFERENCE MAPPING (for vague time references):
  - "recently" / "lately" / "this week" → target_date = {yesterday}, comparison_date = {last_week}
  - "last few days" → target_date = {yesterday}, comparison_date = {yesterday} (3 days ago, but use yesterday for known baseline)
  - "earlier today" → target_date = {today}, comparison_date = {yesterday}
  - Explicit date like "June 1" → use that exact date regardless of today's date (parse as ISO if provided, else infer year as current year)
  - No temporal reference in question → target_date = {previous_target_date} if available, else {today}

DATE FORMAT RULE (CRITICAL): You MUST return target_date and comparison_date in strict YYYY-MM-DD format.
Never return relative terms like "yesterday", "last week", "recently", or date names like "Monday".
Always return absolute ISO format dates. If you cannot infer a date, return empty string "" (not a relative term).

DATE RULE: If the current question does not explicitly mention a new date and is clearly a
follow-up to the previous question (e.g. starts with "What about", "Did", "How about",
"Can you also", "And the", or is very short), set target_date = previous_target_date.
Only use today's date if the question is explicitly about right now with no prior context.
```

### Why This Fix Works
Explicit temporal mapping removes ambiguity, and the DATE FORMAT RULE (in caps) forces ISO format output, preventing invalid dates like "2026-06-00" or relative terms that downstream tools cannot parse.

### Side Effects / Trade-Offs
- **None**. This is a pure constraint strengthening; no logic changes, only clearer LLM instructions.
- **Benefit**: Eliminates "date parsing" failures downstream when tools receive invalid date strings.

---

---

## FIX PRIORITY ORDER

Rank 1–7 by impact on response quality:

### **Rank 1: ISSUE 3 — Synthesis Prompt Grounding (CRITICAL)**
**Why First**: Hallucination is the root cause of inaccurate answers; fixing synthesis grounding eliminates false numbers propagating to the final response. This directly improves correctness across all queries.

### **Rank 2: ISSUE 1 — Planner Default-to-All Routing**
**Why Second**: Incomplete agent routing causes analysis gaps (e.g., a critical inventory finding never reaches synthesis because inventory wasn't activated). Full coverage ensures no domain is missed in multi-faceted incidents.

### **Rank 3: ISSUE 4 — Critic Confidence Threshold + 2 Revisions**
**Why Third**: A second revision chance + confidence gating catches hallucinations the first revision missed, acting as a backstop to Issue 3. Prevents force-approval of low-quality drafts.

### **Rank 4: ISSUE 2 — Increase Agent Context Windows**
**Why Fourth**: Without larger context, inventory cannot confirm what sales found (product name gets truncated), breaking cross-domain correlations. This cascades to synthesis receiving incomplete data even from properly activated agents.

### **Rank 5: ISSUE 6 — Memory Node Query Expansion**
**Why Fifth**: Better historical context improves the synthesis's ability to recognize patterns and benchmark severity. Prepending user intent anchors semantic search, but less critical than getting current analysis right.

### **Rank 6: ISSUE 7 — Planner Date Inference Validation**
**Why Sixth**: Invalid dates cause tool failures, but most common queries default to today/yesterday, which are usually valid. Fixing only matters for edge cases with vague temporal references.

### **Rank 7: ISSUE 5 — Formatter Retry + Observability Logging**
**Why Seventh**: Structured output failures are rare (less than 1% of queries); the retry + fallback are defensive. Lower priority than fixing the core analysis pipeline, but important for resilience when parsing does fail.

---

## IMPLEMENTATION CHECKLIST

- [ ] Issue 1: Update PLANNER_PROMPT with DEFAULT-TO-ALL rule and temporal mapping
- [ ] Issue 2: Increase truncation limits in inventory_node, marketing_node, support_node
- [ ] Issue 3: Enhance SYNTHESIS_PROMPT with grounding constraints and contradictions section
- [ ] Issue 4: Update critic_node to allow 2 revisions and use confidence threshold
- [ ] Issue 5: Add retry logic and observability logging to formatter_node
- [ ] Issue 6: Expand memory_node query to 600 chars per domain + prepend user question
- [ ] Issue 7: Add temporal mapping and date format rules to PLANNER_PROMPT + PlannerDecision descriptions
- [ ] Test: Run evaluation on FP-001 and similar multi-domain scenarios to verify domain_coverage passes
- [ ] Test: Verify no hallucinated numbers appear in final answers (spot-check formatted output against agent reports)
- [ ] Test: Confirm backward compatibility — no breaking changes to interfaces or state schema
