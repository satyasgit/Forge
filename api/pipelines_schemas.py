"""
Pydantic schemas for pipeline configuration API endpoints.

These schemas extend/adapt the core PipelineConfig for API use.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# ============================================================================
# Request/Response for Templates
# ============================================================================

class TemplateMetadata(BaseModel):
    """Lightweight template info for listing."""
    name: str
    description: str = ""
    project_types: list[str] = []
    agent_count: int
    file: str | None = None
    estimated_cost_usd: float | None = None
    estimated_duration_minutes: float | None = None


class TemplateListResponse(BaseModel):
    """Response for listing all templates."""
    templates: list[TemplateMetadata]


class TemplateDetailResponse(BaseModel):
    """Response for a single template."""
    template: dict  # Full PipelineConfig dict


# ============================================================================
# Request/Response for Pipeline Execution
# ============================================================================

class AgentConfigAPI(BaseModel):
    """API representation of agent config (subset of core AgentTaskConfig)."""
    agent: str
    enabled: bool = True
    task: str | None = None
    model: str | None = None
    max_tokens: int | None = None
    depends_on: list[str] = []
    meta: dict[str, str] = {}


class PipelineConfigAPI(BaseModel):
    """API representation of full pipeline config (used in requests)."""
    version: str = "1.0"
    name: str
    description: str = ""
    project_types: list[str] = []
    agents: list[AgentConfigAPI]
    edges: list[dict[str, str]] = []
    auto_resolve: bool = True
    strict_validation: bool = False
    settings: dict[str, Any] = {}
    metadata: dict[str, Any] = {}


class PipelinePreviewResponse(BaseModel):
    """Response for pipeline preview (before running)."""
    agents: list[str]
    agent_count: int
    estimated_cost_usd: float
    estimated_duration_minutes: float
    dag: dict[str, list[dict]]  # {"nodes": [...], "edges": [...]}
    validation: "ValidationResponse | None" = None


class ValidationResponse(BaseModel):
    """Validation result."""
    valid: bool
    errors: list[str] = []
    warnings: list[str] = []


class ValidationRequest(BaseModel):
    """Request to validate a pipeline config."""
    config: PipelineConfigAPI


class PipelineRunRequest(BaseModel):
    """Request to run a custom pipeline."""
    config: PipelineConfigAPI
    feature: str = Field(..., min_length=5, description="Feature description")
    project_id: str = Field(default="default")


class PipelineRunResponse(BaseModel):
    """Response from running a pipeline."""
    success: bool
    run: dict  # PipelineRun.to_dict()
    message: str | None = None


class PipelineHistoryItem(BaseModel):
    """Single pipeline run in history."""
    run_id: str
    timestamp: str
    config_name: str
    status: str  # "done", "failed", "aborted"
    cost_usd: float
    duration_seconds: float
    agent_count: int


class PipelineHistoryResponse(BaseModel):
    """Pipeline history list."""
    project_id: str
    runs: list[PipelineHistoryItem]
    total_cost_usd: float