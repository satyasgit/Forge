"""
Centralised configuration. All settings come from environment variables.
Never hardcode secrets — use .env file locally, secrets manager in production.

v2 changes:
  - Per-agent retry config
  - Workspace path (absolute, not relative)
  - Removed lru_cache (prevents test overrides)
"""
from __future__ import annotations

import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # ── Anthropic ─────────────────────────────────────────────────────────────
    anthropic_api_key: str = ""
    model: str = "claude-opus-4-5"
    fast_model: str = "claude-haiku-4-5-20251001"   # for cheap tasks (summaries, routing)
    max_tokens: int = 4096

    # ── Project defaults ──────────────────────────────────────────────────────
    default_project_id: str = "default"
    memory_db_path: str = "data/agent_memory.db"

    # ── Workspace (absolute path for safe file operations) ────────────────────
    workspace_root: str = ""   # set to absolute path; defaults to {cwd}/workspace

    @property
    def workspace_path(self) -> Path:
        if self.workspace_root:
            return Path(self.workspace_root).resolve()
        return Path.cwd() / "workspace"

    # ── GitHub ────────────────────────────────────────────────────────────────
    github_token: str = ""
    github_default_repo: str = ""

    # ── Jira ──────────────────────────────────────────────────────────────────
    jira_token: str = ""
    jira_email: str = ""
    jira_base_url: str = ""
    jira_project_key: str = ""

    # ── Figma ─────────────────────────────────────────────────────────────────
    figma_token: str = ""
    figma_file_key: str = ""

    # ── Slack ─────────────────────────────────────────────────────────────────
    slack_bot_token: str = ""
    slack_channel: str = "#dev-agents"

    # ── API server ────────────────────────────────────────────────────────────
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_secret_key: str = "change-me-in-production"

    # ── Agent retry defaults ──────────────────────────────────────────────────
    agent_max_retries: int = 3
    agent_retry_backoff_base: float = 2.0

    # ── Feature flags ─────────────────────────────────────────────────────────
    enable_cost_tracking: bool = True
    enable_slack_notifications: bool = False
    enable_jira_integration: bool = False
    enable_github_integration: bool = False
    max_pipeline_cost_usd: float = 5.0   # abort if pipeline exceeds this

    @property
    def has_github(self) -> bool:
        return bool(self.github_token and self.github_default_repo)

    @property
    def has_jira(self) -> bool:
        return bool(self.jira_token and self.jira_base_url)

    @property
    def has_figma(self) -> bool:
        return bool(self.figma_token and self.figma_file_key)


def get_settings() -> Settings:
    """Create settings. No cache — allows test overrides."""
    return Settings()


# Module-level instance for backward compatibility
settings = get_settings()
