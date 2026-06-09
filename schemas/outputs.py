# schemas/outputs.py
# Pydantic models that define the structured output of a completed ops analysis.
#
# Why structured output?
#   - Terminal: humans read the markdown synthesis_draft
#   - Streamlit: UI renders cards/badges from OpsResponse fields
#   - API / downstream systems: JSON-serialisable, schema-validated
#   - Evaluation: compare OpsResponse objects instead of free text strings
#
# Flow: synthesis_draft (markdown) → formatter_node → OpsResponse (Pydantic)

from __future__ import annotations

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


# ──────────────────────────────────────────────
# Enums
# ──────────────────────────────────────────────

class Severity(str, Enum):
    """Overall severity of the detected ops issue."""
    CRITICAL = "critical"    # Revenue is actively bleeding right now
    HIGH     = "high"        # Significant impact, same-day action required
    MEDIUM   = "medium"      # Noticeable impact, action within 48 h
    LOW      = "low"         # Minor issue, monitor only


class ActionPriority(str, Enum):
    """Urgency level of a single recommended action."""
    IMMEDIATE = "immediate"   # Do it now (< 1 hour)
    HIGH      = "high"        # Today
    MEDIUM    = "medium"      # This week
    LOW       = "low"         # Next sprint / nice-to-have


class ActionCategory(str, Enum):
    """Which business domain owns this action."""
    INVENTORY  = "inventory"
    MARKETING  = "marketing"
    PRICING    = "pricing"
    SUPPORT    = "support"
    OPERATIONS = "operations"
    ANALYTICS  = "analytics"


# ──────────────────────────────────────────────
# Sub-models
# ──────────────────────────────────────────────

class RootCause(BaseModel):
    """One confirmed root cause extracted from the analysis."""
    rank: int = Field(
        description="Rank by impact — 1 is the highest-impact cause."
    )
    description: str = Field(
        description="Clear one-sentence statement of the root cause."
    )
    domain: str = Field(
        description="Business domain this cause belongs to: sales, inventory, marketing, or support."
    )
    evidence: str = Field(
        description="Key data point or observation that confirms this cause."
    )


class RecommendedAction(BaseModel):
    """One concrete action the ops team should take."""
    action_id: str = Field(
        description="Short unique identifier, e.g. ACT-001."
    )
    title: str = Field(
        description="Short imperative title, e.g. 'Restock Nike Air Max immediately'."
    )
    description: str = Field(
        description="Full explanation of what to do and why."
    )
    category: ActionCategory = Field(
        description="Business domain that owns this action."
    )
    priority: ActionPriority = Field(
        description="Urgency level of this action."
    )
    estimated_impact: str = Field(
        description="Expected business outcome if this action is taken, e.g. '+$8k revenue recovery'."
    )
    is_executable: bool = Field(
        default=False,
        description="True if this action maps to an available tool (restock, discount, campaign resume/pause, ticket)."
    )


class HistoricalReference(BaseModel):
    """Reference to a past incident retrieved from long-term memory."""
    incident_date: str = Field(description="Date of the past incident, YYYY-MM-DD.")
    description: str   = Field(description="What happened in that incident.")
    similarity_score: float = Field(description="Semantic similarity to current situation, 0-1.")
    what_worked: str   = Field(description="Actions from that incident that helped resolve it.")
    outcome: str       = Field(description="How that incident was resolved.")


class ExecutionSummary(BaseModel):
    """Summary of actions that were actually executed in this session."""
    total_proposed: int  = Field(description="Number of actions the action planner proposed.")
    total_approved: int  = Field(description="Number of actions the human approved.")
    total_executed: int  = Field(description="Number of actions that ran successfully.")
    total_failed: int    = Field(description="Number of actions that raised an error.")
    report: Optional[str] = Field(
        default=None,
        description="Human-readable execution report from the executor node."
    )


# ──────────────────────────────────────────────
# Top-level response model
# ──────────────────────────────────────────────

class OpsResponse(BaseModel):
    """
    Complete structured output for one ops analysis session.

    This is the single object the Streamlit UI, REST API, and evaluator
    consume. Every field is optional except the core identifiers so that
    partial results (e.g. analysis-only, no execution) are still valid.
    """

    # ── Identifiers ──────────────────────────────
    session_date: str = Field(
        description="Date the analysis was run, YYYY-MM-DD."
    )
    target_date: str = Field(
        description="Business date being analysed, YYYY-MM-DD."
    )
    comparison_date: Optional[str] = Field(
        default=None,
        description="Comparison date if provided, YYYY-MM-DD."
    )

    # ── High-level verdict ────────────────────────
    one_liner: str = Field(
        description="Single sentence that captures the most important finding."
    )
    severity: Severity = Field(
        description="Overall severity of the situation."
    )

    # ── Detailed findings ─────────────────────────
    summary: str = Field(
        description="One paragraph executive summary of what happened."
    )
    root_causes: List[RootCause] = Field(
        default_factory=list,
        description="Confirmed root causes ranked by business impact."
    )
    recommended_actions: List[RecommendedAction] = Field(
        default_factory=list,
        description="Ordered list of actions to take."
    )

    # ── Cross-domain context ──────────────────────
    cross_domain_correlations: Optional[str] = Field(
        default=None,
        description="Explanation of how findings across domains connect."
    )

    # ── Historical context ────────────────────────
    historical_references: List[HistoricalReference] = Field(
        default_factory=list,
        description="Similar past incidents retrieved from long-term memory."
    )

    # ── Execution results ─────────────────────────
    execution_summary: Optional[ExecutionSummary] = Field(
        default=None,
        description="Summary of what actions were executed in this session. None if execution was skipped."
    )

    # ── Raw markdown (kept for terminal / debugging) ──
    full_analysis_markdown: Optional[str] = Field(
        default=None,
        description="The raw synthesis_draft markdown. Kept for terminal display and debugging."
    )
