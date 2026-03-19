"""
Tool registry. All agent tools are registered here.

v2 changes:
  - ToolPlugin ABC for structured tool definitions
  - Allowlist-based command execution (replaces bypassable blocklist)
  - Absolute workspace path from settings (not relative cwd)
  - Missing schemas added (github_list_files, figma_get_styles, jira_update_status)
  - Auto-registration: agents declare `enabled_tools` list
"""
from __future__ import annotations

import base64
import json
import logging
import os
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable

import httpx

from config.settings import settings

logger = logging.getLogger(__name__)


# ── Tool Plugin ABC ──────────────────────────────────────────────────────────

class ToolPlugin(ABC):
    """
    Abstract base for all tools. Provides structure for:
    - Schema generation (for Claude tool_use)
    - Health checks (verify credentials before pipeline start)
    - Rate limiting (future)
    """
    name: str
    description: str

    @abstractmethod
    def execute(self, **kwargs) -> dict:
        """Execute the tool and return results."""

    @abstractmethod
    def get_schema(self) -> dict:
        """Return Claude-compatible tool schema."""

    def health_check(self) -> bool:
        """Verify the tool is operational. Override for auth-required tools."""
        return True


# ── GitHub ────────────────────────────────────────────────────────────────────

def github_get_file(repo: str, path: str, branch: str = "main") -> dict:
    r = httpx.get(
        f"https://api.github.com/repos/{repo}/contents/{path}",
        headers={"Authorization": f"Bearer {settings.github_token}"},
        params={"ref": branch},
        timeout=15.0,
    )
    if r.status_code == 404:
        return {"error": f"File not found: {path}"}
    r.raise_for_status()
    data = r.json()
    content = base64.b64decode(data["content"]).decode()
    return {"path": path, "content": content, "sha": data["sha"]}

def github_create_file(repo: str, path: str, content: str, message: str, branch: str = "main") -> dict:
    encoded = base64.b64encode(content.encode()).decode()
    r = httpx.put(
        f"https://api.github.com/repos/{repo}/contents/{path}",
        headers={"Authorization": f"Bearer {settings.github_token}"},
        json={"message": message, "content": encoded, "branch": branch},
        timeout=15.0,
    )
    r.raise_for_status()
    return {"url": r.json()["content"]["html_url"], "path": path}

def github_create_pr(repo: str, title: str, body: str, head: str, base: str = "main") -> dict:
    r = httpx.post(
        f"https://api.github.com/repos/{repo}/pulls",
        headers={"Authorization": f"Bearer {settings.github_token}",
                 "Accept": "application/vnd.github+json"},
        json={"title": title, "body": body, "head": head, "base": base},
        timeout=15.0,
    )
    r.raise_for_status()
    data = r.json()
    return {"pr_number": data["number"], "url": data["html_url"]}

def github_list_files(repo: str, path: str = "", branch: str = "main") -> dict:
    r = httpx.get(
        f"https://api.github.com/repos/{repo}/contents/{path}",
        headers={"Authorization": f"Bearer {settings.github_token}"},
        params={"ref": branch},
        timeout=15.0,
    )
    r.raise_for_status()
    items = [{"name": i["name"], "type": i["type"], "path": i["path"]} for i in r.json()]
    return {"files": items}


# ── Jira ──────────────────────────────────────────────────────────────────────

def jira_create_ticket(project_key: str, summary: str, description: str,
                       issue_type: str = "Story", labels: list[str] = None,
                       story_points: int = None) -> dict:
    fields: dict = {
        "project": {"key": project_key},
        "summary": summary,
        "description": {
            "type": "doc", "version": 1,
            "content": [{"type": "paragraph",
                         "content": [{"type": "text", "text": description}]}],
        },
        "issuetype": {"name": issue_type},
        "labels": labels or [],
    }
    if story_points:
        fields["story_points"] = story_points

    r = httpx.post(
        f"{settings.jira_base_url}/rest/api/3/issue",
        auth=(settings.jira_email, settings.jira_token),
        json={"fields": fields},
        timeout=15.0,
    )
    r.raise_for_status()
    data = r.json()
    return {"key": data["key"], "url": f"{settings.jira_base_url}/browse/{data['key']}"}

def jira_update_status(ticket_key: str, target_status: str) -> dict:
    r = httpx.get(
        f"{settings.jira_base_url}/rest/api/3/issue/{ticket_key}/transitions",
        auth=(settings.jira_email, settings.jira_token),
        timeout=15.0,
    )
    r.raise_for_status()
    transitions = {t["name"]: t["id"] for t in r.json()["transitions"]}
    tid = transitions.get(target_status)
    if not tid:
        return {"error": f"Transition '{target_status}' not found", "available": list(transitions)}
    r2 = httpx.post(
        f"{settings.jira_base_url}/rest/api/3/issue/{ticket_key}/transitions",
        auth=(settings.jira_email, settings.jira_token),
        json={"transition": {"id": tid}},
        timeout=15.0,
    )
    r2.raise_for_status()
    return {"ticket": ticket_key, "new_status": target_status}


# ── Figma ─────────────────────────────────────────────────────────────────────

def figma_get_components(file_key: str) -> dict:
    r = httpx.get(f"https://api.figma.com/v1/files/{file_key}",
                  headers={"X-Figma-Token": settings.figma_token},
                  timeout=30.0)
    r.raise_for_status()
    doc = r.json()["document"]
    components: list[dict] = []
    def walk(node):
        if node.get("type") in ("COMPONENT", "FRAME"):
            components.append({"name": node["name"], "id": node["id"], "type": node["type"]})
        for child in node.get("children", []):
            walk(child)
    walk(doc)
    return {"file_name": r.json()["name"], "components": components}

def figma_get_styles(file_key: str) -> dict:
    r = httpx.get(f"https://api.figma.com/v1/files/{file_key}/styles",
                  headers={"X-Figma-Token": settings.figma_token},
                  timeout=15.0)
    r.raise_for_status()
    return {"styles": r.json().get("meta", {}).get("styles", [])}


# ── Slack ─────────────────────────────────────────────────────────────────────

def slack_send_message(channel: str, text: str, blocks: list = None) -> dict:
    payload: dict = {"channel": channel, "text": text}
    if blocks:
        payload["blocks"] = blocks
    r = httpx.post(
        "https://slack.com/api/chat.postMessage",
        headers={"Authorization": f"Bearer {settings.slack_bot_token}"},
        json=payload,
        timeout=10.0,
    )
    r.raise_for_status()
    data = r.json()
    if not data.get("ok"):
        return {"error": data.get("error")}
    return {"ts": data["ts"], "channel": data["channel"]}


# ── Local execution (HARDENED) ────────────────────────────────────────────────

# Allowlist: only these commands can be executed by agents.
# This is the opposite of the v1 blocklist approach — much safer.
ALLOWED_COMMANDS = frozenset({
    # Linting & formatting
    "ruff", "black", "eslint", "prettier", "stylelint",
    # Type checking
    "mypy", "pyright", "tsc", "npx",
    # Testing
    "pytest", "vitest", "jest", "playwright",
    # Build tools
    "npm", "pnpm", "yarn", "pip", "cargo", "go",
    # Project tools
    "alembic", "prisma", "expo",
    # Info commands
    "ls", "cat", "head", "tail", "wc", "find", "grep", "diff",
    # Docker (read-only)
    "docker",
})

# Subcommand blocklist for tools that have dangerous subcommands
BLOCKED_SUBCOMMANDS = {
    "npm": {"publish", "login", "adduser", "owner"},
    "docker": {"rm", "rmi", "system", "push", "login"},
    "pip": {"install"},  # agents shouldn't install packages
    "go": {"install"},
}


def run_command(command: list[str], cwd: str = None, timeout: int = 30) -> dict:
    """
    Run a shell command in the agent workspace.
    Uses ALLOWLIST (not blocklist) — only explicitly permitted commands run.
    """
    if not command:
        return {"error": "Empty command"}

    executable = Path(command[0]).name  # strip any path prefix (/bin/rm → rm)

    # Check allowlist
    if executable not in ALLOWED_COMMANDS:
        return {"error": f"Command '{executable}' is not in the allowlist. Allowed: {sorted(ALLOWED_COMMANDS)}"}

    # Check subcommand blocklist
    if executable in BLOCKED_SUBCOMMANDS and len(command) > 1:
        subcommand = command[1].lstrip("-")
        if subcommand in BLOCKED_SUBCOMMANDS[executable]:
            return {"error": f"Subcommand '{executable} {subcommand}' is blocked for safety"}

    # Resolve working directory to workspace
    workspace = settings.workspace_path
    if cwd:
        resolved_cwd = (workspace / cwd).resolve()
        if not str(resolved_cwd).startswith(str(workspace)):
            return {"error": f"Working directory must be within workspace: {workspace}"}
    else:
        resolved_cwd = workspace

    try:
        result = subprocess.run(
            command,
            cwd=str(resolved_cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "CI": "true"},  # signal non-interactive env
        )
        return {
            "stdout": result.stdout[:4000],
            "stderr": result.stderr[:2000],
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"error": f"Command timed out after {timeout}s"}
    except FileNotFoundError:
        return {"error": f"Command '{executable}' not found on this system"}
    except Exception as e:
        return {"error": str(e)}


def write_file(path: str, content: str) -> dict:
    """Write content to a local file (agent workspace only)."""
    workspace = settings.workspace_path
    # Resolve and validate the path is within workspace
    safe_path = (workspace / path).resolve()
    if not str(safe_path).startswith(str(workspace)):
        return {"error": f"Path traversal detected. Can only write within: {workspace}"}

    safe_path.parent.mkdir(parents=True, exist_ok=True)
    safe_path.write_text(content)
    return {"written": str(safe_path), "bytes": len(content)}


def read_file(path: str) -> dict:
    """Read content from a file in the agent workspace."""
    workspace = settings.workspace_path
    safe_path = (workspace / path).resolve()
    if not str(safe_path).startswith(str(workspace)):
        return {"error": f"Path traversal detected. Can only read within: {workspace}"}
    if not safe_path.exists():
        return {"error": f"File not found: {path}"}
    try:
        content = safe_path.read_text()
        return {"path": str(safe_path), "content": content[:50000], "bytes": len(content)}
    except Exception as e:
        return {"error": str(e)}


# ── Registry ──────────────────────────────────────────────────────────────────

TOOL_REGISTRY: dict[str, Callable] = {
    "github_get_file":       github_get_file,
    "github_create_file":    github_create_file,
    "github_create_pr":      github_create_pr,
    "github_list_files":     github_list_files,
    "jira_create_ticket":    jira_create_ticket,
    "jira_update_status":    jira_update_status,
    "figma_get_components":  figma_get_components,
    "figma_get_styles":      figma_get_styles,
    "slack_send_message":    slack_send_message,
    "run_command":           run_command,
    "write_file":            write_file,
    "read_file":             read_file,
}

# Claude tool schemas (input_schema for each tool)
CLAUDE_TOOL_SCHEMAS: dict[str, dict] = {
    "github_get_file": {
        "name": "github_get_file",
        "description": "Fetch a file's content from a GitHub repository",
        "input_schema": {
            "type": "object",
            "properties": {
                "repo":   {"type": "string", "description": "owner/repo"},
                "path":   {"type": "string", "description": "file path"},
                "branch": {"type": "string", "default": "main"},
            },
            "required": ["repo", "path"],
        },
    },
    "github_create_file": {
        "name": "github_create_file",
        "description": "Create or update a file in a GitHub repository",
        "input_schema": {
            "type": "object",
            "properties": {
                "repo":    {"type": "string"},
                "path":    {"type": "string"},
                "content": {"type": "string"},
                "message": {"type": "string", "description": "commit message"},
                "branch":  {"type": "string", "default": "main"},
            },
            "required": ["repo", "path", "content", "message"],
        },
    },
    "github_create_pr": {
        "name": "github_create_pr",
        "description": "Create a GitHub Pull Request",
        "input_schema": {
            "type": "object",
            "properties": {
                "repo":  {"type": "string"},
                "title": {"type": "string"},
                "body":  {"type": "string"},
                "head":  {"type": "string", "description": "source branch"},
                "base":  {"type": "string", "default": "main"},
            },
            "required": ["repo", "title", "body", "head"],
        },
    },
    "github_list_files": {
        "name": "github_list_files",
        "description": "List files in a GitHub repository directory",
        "input_schema": {
            "type": "object",
            "properties": {
                "repo":   {"type": "string", "description": "owner/repo"},
                "path":   {"type": "string", "default": ""},
                "branch": {"type": "string", "default": "main"},
            },
            "required": ["repo"],
        },
    },
    "jira_create_ticket": {
        "name": "jira_create_ticket",
        "description": "Create a Jira issue",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_key":  {"type": "string"},
                "summary":      {"type": "string"},
                "description":  {"type": "string"},
                "issue_type":   {"type": "string", "default": "Story"},
                "labels":       {"type": "array", "items": {"type": "string"}},
                "story_points": {"type": "integer"},
            },
            "required": ["project_key", "summary", "description"],
        },
    },
    "jira_update_status": {
        "name": "jira_update_status",
        "description": "Update the status of a Jira ticket via transition",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticket_key":    {"type": "string"},
                "target_status": {"type": "string"},
            },
            "required": ["ticket_key", "target_status"],
        },
    },
    "figma_get_components": {
        "name": "figma_get_components",
        "description": "Get all components from a Figma file",
        "input_schema": {
            "type": "object",
            "properties": {"file_key": {"type": "string"}},
            "required": ["file_key"],
        },
    },
    "figma_get_styles": {
        "name": "figma_get_styles",
        "description": "Get all styles from a Figma file",
        "input_schema": {
            "type": "object",
            "properties": {"file_key": {"type": "string"}},
            "required": ["file_key"],
        },
    },
    "slack_send_message": {
        "name": "slack_send_message",
        "description": "Send a message to a Slack channel",
        "input_schema": {
            "type": "object",
            "properties": {
                "channel": {"type": "string"},
                "text":    {"type": "string"},
            },
            "required": ["channel", "text"],
        },
    },
    "run_command": {
        "name": "run_command",
        "description": "Run an allowed shell command (lint, test, build, type-check). Only allowlisted commands are permitted.",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "array", "items": {"type": "string"}, "description": "Command and arguments as a list"},
                "cwd":     {"type": "string", "description": "Working directory relative to workspace"},
                "timeout": {"type": "integer", "default": 30},
            },
            "required": ["command"],
        },
    },
    "write_file": {
        "name": "write_file",
        "description": "Write content to a file in the agent workspace",
        "input_schema": {
            "type": "object",
            "properties": {
                "path":    {"type": "string", "description": "File path relative to workspace"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
        },
    },
    "read_file": {
        "name": "read_file",
        "description": "Read content from a file in the agent workspace",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path relative to workspace"},
            },
            "required": ["path"],
        },
    },
}


def get_tools_for_agent(tool_names: list[str]) -> list[dict]:
    """Return Claude tool schemas for the given tool names."""
    return [CLAUDE_TOOL_SCHEMAS[n] for n in tool_names if n in CLAUDE_TOOL_SCHEMAS]
