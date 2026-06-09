from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Any
from uuid import uuid4

class AnalyzeRequest(BaseModel):
    question: str
    target_date: str = ""
    comparison_date: str = ""
    thread_id: str = Field(default_factory=lambda: str(uuid4()))

class AnalyzeResponse(BaseModel):
    thread_id: str
    final_answer: str
    structured_output: dict[str, Any] | None = None
    proposed_actions: list[dict[str, Any]] = []
    history: list[dict[str, str]] = []

class ApproveRequest(BaseModel):
    thread_id: str
    approved_action_ids: list[int]  # action_id values from proposed_actions

class ApproveResponse(BaseModel):
    thread_id: str
    execution_report: str | None = None
    execution_results: list[dict[str, Any]] = []

class HistoryResponse(BaseModel):
    thread_id: str
    messages: list[dict[str, str]] 

class ObsStatsResponse(BaseModel):
    total_runs: int
    avg_latency_ms: float
    p95_latency_ms: float
    avg_revisions: float
    memory_hit_rate: float
    exec_rate: float
    severity_distribution: dict[str, int]
    domain_activation: dict[str, int]
    recent_runs: list[dict[str, Any]]


class ChatMessage(BaseModel):
    role: str
    content: str
    structured_output: dict[str, Any] | None = None


class ChatThread(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str
    message_count: int = 0


class ChatMessagesResponse(BaseModel):
    thread_id: str
    messages: list[ChatMessage]