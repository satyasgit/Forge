"""
Persistent memory store for all agents.
Uses SQLite locally; swap the connection string for PostgreSQL in production.

v2 changes:
  - WAL mode for concurrent reads during parallel agent execution
  - uuid4 instead of MD5 for IDs
  - datetime.now(timezone.utc) instead of deprecated utcnow()
  - _summarise() cost is tracked in cost_log
  - Connection reuse with WAL journal mode
  - Checkpoint persistence for pause/resume (Phase 3)
"""
from __future__ import annotations

import json
import uuid
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import anthropic

from config.settings import settings
from config.database import is_postgres, Base, engine, SessionLocal

logger = logging.getLogger(__name__)

# ── Database Selection ────────────────────────────────────────────────────────
# Use PostgreSQL if configured, otherwise SQLite for memory store operations
# Note: Memory store is being phased out in favor of repository pattern,
# but still used for agent messages, artifacts, decisions (legacy)

_use_postgres = is_postgres if 'is_postgres' in globals() else False


# ═══════════════════════════════════════════════════════════════════════════════
# LEGACY SQLITE IMPLEMENTATION (still used for agent memory)
# ═══════════════════════════════════════════════════════════════════════════════

if not _use_postgres:
    # SQLite path (legacy)
    DB_PATH = Path(settings.memory_db_path)
    _conn: sqlite3.Connection | None = None

    def _get_conn() -> sqlite3.Connection:
        global _conn
        if _conn is None:
            DB_PATH.parent.mkdir(parents=True, exist_ok=True)
            _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
            _conn.row_factory = sqlite3.Row
            _conn.execute("PRAGMA journal_mode=WAL")
            _conn.execute("PRAGMA busy_timeout=5000")
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
        CREATE TABLE IF NOT EXISTS checkpoints (
            id              TEXT PRIMARY KEY,
            project_id      TEXT NOT NULL,
            pipeline_run_id TEXT NOT NULL,
            agent_name      TEXT NOT NULL,
            status          TEXT NOT NULL,  -- pending, approved, rejected, timeout
            checkpoint_type TEXT NOT NULL,  -- human_approval, manual_qa, budget_approval, data_input
            approver        TEXT,
            decision_at     TEXT,
            message         TEXT,
            metadata        TEXT,  -- JSON blob for extra data
            created_at      TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS pipeline_state (
            run_id          TEXT PRIMARY KEY,
            project_id      TEXT NOT NULL,
            state_json      TEXT NOT NULL,  -- Serialized orchestrator state
            paused_at       TEXT NOT NULL,
            checkpoint_id   TEXT,  -- Which checkpoint caused pause
            FOREIGN KEY (checkpoint_id) REFERENCES checkpoints(id)
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

    # ── Checkpoint Management (Phase 3) ─────────────────────────────────────────

    def create_checkpoint(self, pipeline_run_id: str, agent_name: str, checkpoint_type: str,
                          message: str = "", metadata: dict | None = None) -> str:
        """
        Create a checkpoint record.

        Args:
            pipeline_run_id: The pipeline run ID
            agent_name: Which agent triggered the checkpoint
            checkpoint_type: Type of checkpoint (human_approval, etc.)
            message: Human-readable message for approvers
            metadata: Extra data to store with checkpoint

        Returns:
            checkpoint_id (UUID)
        """
        checkpoint_id = str(uuid.uuid4())
        conn = _get_conn()
        conn.execute(
            "INSERT INTO checkpoints VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                checkpoint_id,
                self.project_id,
                pipeline_run_id,
                agent_name,
                "pending",  # status
                checkpoint_type,
                None,  # approver
                None,  # decision_at
                message,
                json.dumps(metadata) if metadata else None,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()
        logger.info("[memory] created checkpoint %s (%s) for run %s",
                    checkpoint_id[:8], checkpoint_type, pipeline_run_id)
        return checkpoint_id

    def get_checkpoint(self, checkpoint_id: str) -> dict | None:
        """Retrieve a checkpoint by ID."""
        conn = _get_conn()
        row = conn.execute(
            "SELECT * FROM checkpoints WHERE id = ?",
            (checkpoint_id,)
        ).fetchone()
        if not row:
            return None
        return dict(row)

    def get_pending_checkpoints(self, pipeline_run_id: str | None = None) -> list[dict]:
        """Get all pending checkpoints, optionally filtered by run_id."""
        conn = _get_conn()
        if pipeline_run_id:
            rows = conn.execute(
                "SELECT * FROM checkpoints WHERE pipeline_run_id = ? AND status = 'pending' "
                "ORDER BY created_at ASC",
                (pipeline_run_id,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM checkpoints WHERE status = 'pending' "
                "ORDER BY created_at ASC"
            ).fetchall()
        return [dict(row) for row in rows]

    def update_checkpoint_decision(self, checkpoint_id: str, status: str,
                                   approver: str | None = None, reason: str | None = None) -> bool:
        """
        Update checkpoint with approval decision.

        Args:
            checkpoint_id: Checkpoint ID
            status: 'approved' or 'rejected'
            approver: Who made the decision
            reason: Optional reason note

        Returns:
            True if updated, False if not found or already processed
        """
        conn = _get_conn()
        # Only update if still pending
        row = conn.execute(
            "SELECT status FROM checkpoints WHERE id = ?",
            (checkpoint_id,)
        ).fetchone()
        if not row:
            return False
        if row["status"] != "pending":
            return False

        conn.execute(
            "UPDATE checkpoints SET status = ?, approver = ?, decision_at = ?, metadata = ? "
            "WHERE id = ?",
            (
                status,
                approver,
                datetime.now(timezone.utc).isoformat() if status in ("approved", "rejected") else None,
                json.dumps({"reason": reason}) if reason else None,
                checkpoint_id,
            ),
        )
        conn.commit()
        logger.info("[memory] checkpoint %s set to %s by %s", checkpoint_id[:8], status, approver)
        return True

    def list_run_checkpoints(self, pipeline_run_id: str) -> list[dict]:
        """Get all checkpoints associated with a pipeline run."""
        conn = _get_conn()
        rows = conn.execute(
            "SELECT * FROM checkpoints WHERE pipeline_run_id = ? "
            "ORDER BY created_at ASC",
            (pipeline_run_id,)
        ).fetchall()
        return [dict(row) for row in rows]

    # ── Pipeline State Persistence (for pause/resume) ────────────────────────────

    def save_pipeline_state(self, run_id: str, state_dict: dict, checkpoint_id: str | None = None):
        """Save orchestrator state for later resume."""
        conn = _get_conn()
        conn.execute(
            "INSERT OR REPLACE INTO pipeline_state VALUES (?,?,?,?,?)",
            (
                run_id,
                self.project_id,
                json.dumps(state_dict, default=str),
                datetime.now(timezone.utc).isoformat(),
                checkpoint_id,
            ),
        )
        conn.commit()
        logger.info("[memory] saved pipeline state for run %s (checkpoint: %s)",
                    run_id, checkpoint_id[:8] if checkpoint_id else "none")

    def load_pipeline_state(self, run_id: str) -> dict | None:
        """Load saved orchestrator state."""
        conn = _get_conn()
        row = conn.execute(
            "SELECT state_json FROM pipeline_state WHERE run_id = ?",
            (run_id,)
        ).fetchone()
        if not row:
            return None
        return json.loads(row["state_json"])

    def delete_pipeline_state(self, run_id: str):
        """Remove saved pipeline state (after completion)."""
        conn = _get_conn()
        conn.execute("DELETE FROM pipeline_state WHERE run_id = ?", (run_id,))
        conn.commit()

    def get_paused_runs(self) -> list[dict]:
        """Get all runs that are currently paused."""
        conn = _get_conn()
        rows = conn.execute(
            "SELECT * FROM pipeline_state ORDER BY paused_at ASC"
        ).fetchall()
        return [dict(row) for row in rows]

    def get_checkpoint_id_for_run(self, run_id: str) -> str | None:
        """Get the checkpoint_id associated with a paused pipeline run."""
        conn = _get_conn()
        row = conn.execute(
            "SELECT checkpoint_id FROM pipeline_state WHERE run_id = ?",
            (run_id,)
        ).fetchone()
        return row["checkpoint_id"] if row and row["checkpoint_id"] else None

    def get_project_id_for_run(self, run_id: str) -> str | None:
        """Get the project_id associated with a pipeline run."""
        conn = _get_conn()
        row = conn.execute(
            "SELECT project_id FROM pipeline_state WHERE run_id = ?",
            (run_id,)
        ).fetchone()
        return row["project_id"] if row else None

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
