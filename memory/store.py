"""
Persistent memory store for all agents.
Uses SQLite locally; swap the connection string for PostgreSQL in production.

v2 changes:
  - WAL mode for concurrent reads during parallel agent execution
  - uuid4 instead of MD5 for IDs
  - datetime.now(timezone.utc) instead of deprecated utcnow()
  - _summarise() cost is tracked in cost_log
  - Connection reuse with WAL journal mode
"""
from __future__ import annotations

import json
import uuid
import sqlite3
import logging
from datetime import datetime, timezone
from pathlib import Path

import anthropic

from config.settings import settings

logger = logging.getLogger(__name__)

DB_PATH = Path(settings.memory_db_path)

# Module-level connection with WAL mode for concurrent reads
_conn: sqlite3.Connection | None = None


def _get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        # WAL mode allows concurrent reads during writes
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA busy_timeout=5000")  # wait 5s on lock
        _init_schema(_conn)
    return _conn


def _init_schema(conn: sqlite3.Connection):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS projects (
            id          TEXT PRIMARY KEY,
            name        TEXT,
            description TEXT,
            created_at  TEXT,
            updated_at  TEXT
        );
        CREATE TABLE IF NOT EXISTS artifacts (
            id            TEXT PRIMARY KEY,
            project_id    TEXT NOT NULL,
            agent         TEXT NOT NULL,
            artifact_type TEXT NOT NULL,
            content       TEXT,
            summary       TEXT,
            created_at    TEXT
        );
        CREATE TABLE IF NOT EXISTS decisions (
            id          TEXT PRIMARY KEY,
            project_id  TEXT NOT NULL,
            agent       TEXT NOT NULL,
            decision    TEXT,
            rationale   TEXT,
            created_at  TEXT
        );
        CREATE TABLE IF NOT EXISTS agent_messages (
            id         TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            agent      TEXT NOT NULL,
            messages   TEXT,
            updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS cost_log (
            id            TEXT PRIMARY KEY,
            project_id    TEXT,
            agent         TEXT,
            model         TEXT DEFAULT '',
            input_tokens  INTEGER,
            output_tokens INTEGER,
            cost_usd      REAL,
            created_at    TEXT
        );
    """)
    conn.commit()


class ProjectMemory:
    """Thread-safe project memory with WAL mode. One instance per (project_id)."""

    def __init__(self, project_id: str):
        self.project_id = project_id

    # ── Artifacts ─────────────────────────────────────────────────────────────

    def save_artifact(self, agent: str, artifact_type: str, content: str) -> str:
        summary = self._summarise(content)
        aid = str(uuid.uuid4())
        conn = _get_conn()
        conn.execute(
            "INSERT OR REPLACE INTO artifacts VALUES (?,?,?,?,?,?,?)",
            (aid, self.project_id, agent, artifact_type, content, summary,
             datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        logger.debug("[memory] saved artifact %s (%s/%s)", aid[:8], agent, artifact_type)
        return aid

    def get_artifact(self, agent: str, artifact_type: str) -> str | None:
        conn = _get_conn()
        row = conn.execute(
            "SELECT content FROM artifacts WHERE project_id=? AND agent=? AND artifact_type=? "
            "ORDER BY created_at DESC LIMIT 1",
            (self.project_id, agent, artifact_type),
        ).fetchone()
        return row["content"] if row else None

    # ── Decisions ─────────────────────────────────────────────────────────────

    def save_decision(self, agent: str, decision: str, rationale: str = ""):
        did = str(uuid.uuid4())
        conn = _get_conn()
        conn.execute(
            "INSERT OR REPLACE INTO decisions VALUES (?,?,?,?,?,?)",
            (did, self.project_id, agent, decision, rationale,
             datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()

    # ── Agent message history ─────────────────────────────────────────────────

    def restore_agent_messages(self, agent: str) -> list[dict]:
        conn = _get_conn()
        row = conn.execute(
            "SELECT messages FROM agent_messages WHERE project_id=? AND agent=?",
            (self.project_id, agent),
        ).fetchone()
        if not row:
            return []
        return json.loads(row["messages"])

    def save_agent_messages(self, agent: str, messages: list[dict]):
        mid = f"{self.project_id}:{agent}"
        conn = _get_conn()
        conn.execute(
            "INSERT OR REPLACE INTO agent_messages VALUES (?,?,?,?,?)",
            (mid, self.project_id, agent,
             json.dumps(messages, default=str),
             datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()

    # ── Context builder ───────────────────────────────────────────────────────

    def get_context_for_agent(self, agent: str) -> str:
        """Compact context string injected at the top of each agent task."""
        conn = _get_conn()
        artifacts = conn.execute(
            "SELECT agent, artifact_type, summary FROM artifacts "
            "WHERE project_id=? ORDER BY created_at DESC LIMIT 12",
            (self.project_id,),
        ).fetchall()
        decisions = conn.execute(
            "SELECT agent, decision FROM decisions "
            "WHERE project_id=? ORDER BY created_at DESC LIMIT 8",
            (self.project_id,),
        ).fetchall()

        if not artifacts and not decisions:
            return ""

        parts = [f"## Project context (project_id={self.project_id})\n"]
        if decisions:
            parts.append("### Key decisions")
            for row in decisions:
                parts.append(f"- [{row['agent']}] {row['decision']}")
        if artifacts:
            parts.append("\n### Completed work")
            for row in artifacts:
                parts.append(f"- [{row['agent']} / {row['artifact_type']}] {row['summary']}")
        return "\n".join(parts)

    # ── Cost tracking ─────────────────────────────────────────────────────────

    def log_cost(self, agent: str, model: str, input_tokens: int, output_tokens: int):
        from agents.agent_config import calculate_cost
        cost = calculate_cost(model, input_tokens, output_tokens)
        cid = str(uuid.uuid4())
        conn = _get_conn()
        conn.execute(
            "INSERT INTO cost_log VALUES (?,?,?,?,?,?,?,?)",
            (cid, self.project_id, agent, model, input_tokens, output_tokens,
             cost, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()

    def total_cost(self) -> float:
        conn = _get_conn()
        row = conn.execute(
            "SELECT COALESCE(SUM(cost_usd), 0) as total FROM cost_log WHERE project_id=?",
            (self.project_id,),
        ).fetchone()
        return row["total"]

    def cost_by_agent(self) -> dict[str, float]:
        conn = _get_conn()
        rows = conn.execute(
            "SELECT agent, SUM(cost_usd) as total FROM cost_log WHERE project_id=? GROUP BY agent",
            (self.project_id,),
        ).fetchall()
        return {row["agent"]: row["total"] for row in rows}

    # ── Internal ──────────────────────────────────────────────────────────────

    def _summarise(self, content: str) -> str:
        if len(content) <= 300:
            return content
        try:
            api_key = settings.anthropic_api_key
            if not api_key:
                return content[:200] + "..."
            llm = anthropic.Anthropic(api_key=api_key)
            resp = llm.messages.create(
                model=settings.fast_model,
                max_tokens=100,
                messages=[{
                    "role": "user",
                    "content": f"Summarise in ONE sentence what this agent output contains:\n\n{content[:1500]}",
                }],
            )
            summary = resp.content[0].text.strip()

            # Track the summarisation cost
            self.log_cost(
                agent="_summariser",
                model=settings.fast_model,
                input_tokens=resp.usage.input_tokens,
                output_tokens=resp.usage.output_tokens,
            )
            return summary
        except Exception:
            return content[:200] + "..."
