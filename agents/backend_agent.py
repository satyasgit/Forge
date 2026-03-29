"""
Backend Agent — fully working FastAPI/SQLAlchemy builder.
Pre-scans for: missing response_model, N+1 queries, bare except,
direct DB in routes, blocking I/O, and mutable defaults.
"""
from __future__ import annotations
import re, textwrap
from dataclasses import dataclass
from agents.base import BaseAgent, AgentResult
from skills.backend.api_patterns import API_GAP_PATTERNS, API_ANTIPATTERN_PATTERNS, SCHEMA_DESIGN_RULES, ASYNC_DB_PATTERNS
from skills.backend.fastapi_patterns import REPOSITORY_PATTERN, SERVICE_PATTERN, FASTAPI_ROUTE_PATTERN, PYDANTIC_V2_PATTERNS, SQLALCHEMY_MODEL_PATTERN, JWT_AUTH_PATTERN

@dataclass
class APIGap:
    pattern_name: str; severity: str; category: str; location: str; evidence: str; fix: str; why: str
    def to_summary(self): return f"[{self.severity.upper()}] {self.pattern_name} at {self.location} ({self.category})"

@dataclass
class APIAntiPattern:
    pattern_name: str; severity: str; category: str; location: str; evidence: str; fix: str; impact: str
    def to_summary(self): return f"[{self.severity.upper()}] {self.pattern_name} at {self.location}"

from agents.agent_config import register_agent

@register_agent
class BackendAgent(BaseAgent):
    name = "backend"
    role = "Senior Backend Engineer"
    enabled_tools = ["github_create_file", "write_file", "run_command"]

    @property
    def system_prompt(self) -> str:
        schema_rules = "\n".join(f"- {k}: {v['rule']} — {v['reason']}" for k, v in SCHEMA_DESIGN_RULES.items())
        return textwrap.dedent(f"""
            You are a senior backend engineer (FastAPI, SQLAlchemy 2.0, PostgreSQL).

            ## Architecture: always use repository → service → route layers.
            {REPOSITORY_PATTERN}
            {SERVICE_PATTERN}
            {FASTAPI_ROUTE_PATTERN}
            {PYDANTIC_V2_PATTERNS}
            {SQLALCHEMY_MODEL_PATTERN}
            {JWT_AUTH_PATTERN}
            {ASYNC_DB_PATTERNS}

            ## Schema design rules:
            {schema_rules}

            ## Output for every task:
            1. app/api/routes/{{feature}}.py  — routes with response_model + status_code
            2. app/models/{{feature}}.py      — SQLAlchemy model (UUID PK, timestamps)
            3. app/schemas/{{feature}}.py     — Pydantic v2 schemas
            4. app/services/{{feature}}_service.py
            5. app/repositories/{{feature}}_repo.py
            6. migrations/versions/{{date}}_{{feature}}.py — Alembic stub

            ## Non-negotiable:
            - UUID PKs, created_at/updated_at on every model
            - response_model on every route, status_code=201 on POST
            - Paginated list endpoints (skip+limit, max 200)
            - Rate limiting on auth endpoints
            - No direct DB in route handlers
            - No bare except: pass
            - All function params and returns typed

            Produce complete runnable Python — no pseudocode.
        """).strip()

    def build_feature(self, feature: str, existing_code: dict[str, str] | None = None, context: str = "", async_mode: bool = False) -> AgentResult:
        gaps = self._scan_for_api_gaps(existing_code or {})
        antipatterns = self._scan_for_antipatterns(existing_code or {})
        existing_block = ""
        if existing_code:
            existing_block = "\n\n## Existing code (extend, do not rewrite):\n" + "\n\n".join(
                f"### {f}\n```python\n{c}\n```" for f, c in existing_code.items()
            )
        task = textwrap.dedent(f"""
            Build complete FastAPI backend for: {feature}
            Context: {context or "Standard FastAPI + PostgreSQL SaaS."}
            {"Use async SQLAlchemy." if async_mode else "Use sync SQLAlchemy."}
            {existing_block}
            Pre-detected API gaps (fix ALL): {self._format_gaps(gaps)}
            Pre-detected anti-patterns (avoid): {self._format_antipatterns(antipatterns)}
            Output all files listed in your instructions, complete and runnable.
        """).strip()
        return self.run(task)

    def design_schema(self, entities: list[str], relationships: str = "") -> AgentResult:
        task = f"Design PostgreSQL schema for: {', '.join(entities)}\nRelationships: {relationships or 'Infer from names.'}\nApply all schema design rules. Output: SQLAlchemy models + Alembic migration + index rationale."
        return self.run(task)

    def _scan_for_api_gaps(self, code: dict[str, str]) -> list[APIGap]:
        gaps = []
        for filename, content in code.items():
            if not filename.endswith(".py"): continue
            for i, line in enumerate(content.split("\n"), 1):
                for p in API_GAP_PATTERNS:
                    if re.search(p["regex"], line, re.IGNORECASE):
                        gaps.append(APIGap(p["name"], p["severity"], p["category"], f"{filename}:{i}", line.strip(), p["fix"], p["why"]))
        return gaps

    def _scan_for_antipatterns(self, code: dict[str, str]) -> list[APIAntiPattern]:
        findings = []
        for filename, content in code.items():
            if not filename.endswith(".py"): continue
            for i, line in enumerate(content.split("\n"), 1):
                for p in API_ANTIPATTERN_PATTERNS:
                    if re.search(p["regex"], line, re.IGNORECASE):
                        findings.append(APIAntiPattern(p["name"], p["severity"], p["category"], f"{filename}:{i}", line.strip(), p["fix"], p["impact"]))
        return findings

    def _format_gaps(self, gaps): 
        if not gaps: return "No API gaps detected."
        lines = [f"Found {len(gaps)} gaps:"] + [f"  {g.to_summary()}" for g in sorted(gaps, key=lambda x: ["critical","high","medium","low"].index(x.severity))]
        return "\n".join(lines)

    def _format_antipatterns(self, aps):
        if not aps: return "No anti-patterns detected."
        return "\n".join([f"Found {len(aps)} anti-patterns:"] + [f"  {a.to_summary()}" for a in aps])
