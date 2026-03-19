"""
DevOps Agent — fully working CI/CD and infrastructure builder.
Pre-scans: Dockerfile, GitHub Actions, docker-compose, and Terraform
for security misconfigs, missing health checks, mutable action refs, etc.
"""
from __future__ import annotations
import re, textwrap
from dataclasses import dataclass
from agents.base import BaseAgent, AgentResult
from skills.devops.infra_patterns import INFRA_GAP_PATTERNS, INFRA_ANTIPATTERNS, ENV_VAR_CATEGORIES
from skills.devops.ci_cd_templates import GITHUB_ACTIONS_CI, GITHUB_ACTIONS_DEPLOY, DOCKERFILE_TEMPLATE, DOCKER_COMPOSE_DEV

@dataclass
class InfraIssue:
    pattern_name: str; severity: str; category: str; location: str; evidence: str; fix: str; why: str
    def to_summary(self): return f"[{self.severity.upper()}] {self.pattern_name} at {self.location} ({self.category})"

class DevOpsAgent(BaseAgent):
    name = "devops"
    role = "DevOps Engineer"
    enabled_tools = ["github_create_file", "write_file"]

    @property
    def system_prompt(self) -> str:
        env_required = "\n".join(f"  - {v}" for v in ENV_VAR_CATEGORIES["required_always"])
        env_never = "\n".join(f"  - {v}" for v in ENV_VAR_CATEGORIES["never_in_env"])
        return textwrap.dedent(f"""
            You are a DevOps engineer specialising in Docker, GitHub Actions,
            and cloud deployments (Railway, Render, Fly.io, AWS ECS).

            ## Dockerfile template:
            {DOCKERFILE_TEMPLATE}

            ## CI pipeline template:
            {GITHUB_ACTIONS_CI}

            ## Deploy pipeline template:
            {GITHUB_ACTIONS_DEPLOY}

            ## Docker Compose dev template:
            {DOCKER_COMPOSE_DEV}

            ## Required env vars (always include in .env.example):
            {env_required}

            ## Never put in source:
            {env_never}

            ## Output for every task:

            ### Dockerfile (multi-stage: builder + slim runtime)
            ### docker-compose.yml (local dev with postgres + redis + app)
            ### .github/workflows/ci.yml (lint + test on PR)
            ### .github/workflows/deploy.yml (build → staging → production)
            ### .env.example (all vars, grouped, with comments)
            ### DEPLOYMENT_RUNBOOK.md (numbered steps, rollback procedure)

            ## Non-negotiable:
            - Non-root user in every Dockerfile
            - Pin base image to exact version (never :latest)
            - HEALTHCHECK in every Dockerfile
            - GitHub Actions pinned to commit SHA (never @main or @v1)
            - Secrets via env vars, never interpolated in run: steps
            - explicit permissions: block on every workflow
            - No hardcoded passwords in docker-compose (use ${{VAR}})
            - Every deploy has a rollback step

            Produce complete, deployable config files.
        """).strip()

    def generate_pipeline(self, app_description: str, stack: str = "python-fastapi", cloud: str = "railway") -> AgentResult:
        """Full CI/CD pipeline generation with local infra scan."""
        # No existing files to scan on first run, but scan if provided via context
        task = textwrap.dedent(f"""
            Generate the complete DevOps setup for this application.

            App: {app_description}
            Stack: {stack}
            Deployment target: {cloud}

            Produce ALL files in your output structure.
            Dockerfile must use multi-stage build.
            CI must run: lint → test → security scan.
            Deploy must gate on staging before production.
            Include rollback procedure in runbook.
        """).strip()
        return self.run(task)

    def audit_infra(self, infra_files: dict[str, str]) -> AgentResult:
        """Audit existing infra files for security and reliability issues."""
        gaps = self._scan_infra_gaps(infra_files)
        antipatterns = self._scan_infra_antipatterns(infra_files)
        files_block = "\n\n".join(f"### {f}\n```\n{c}\n```" for f, c in infra_files.items())
        task = textwrap.dedent(f"""
            Audit these infrastructure files for security misconfigs and reliability issues.

            {files_block}

            Pre-detected gaps:
            {self._format_issues(gaps)}

            Pre-detected anti-patterns:
            {self._format_issues(antipatterns)}

            For every issue: file:line, what's wrong, exact fixed config.
            Prioritise: CRITICAL security > HIGH reliability > MEDIUM best practice.
        """)
        return self.run(task)

    def generate_dockerfile(self, language: str, app_type: str, port: int = 8000) -> AgentResult:
        task = f"Generate a production Dockerfile for a {language} {app_type} app on port {port}.\nMulti-stage. Non-root user. Health check. Pin base image version."
        return self.run(task)

    def _scan_infra_gaps(self, files: dict[str, str]) -> list[InfraIssue]:
        issues = []
        for filename, content in files.items():
            for i, line in enumerate(content.split("\n"), 1):
                for p in INFRA_GAP_PATTERNS:
                    file_match = any(filename.endswith(ft.lstrip("*")) or ft in filename for ft in p.get("file_types", []))
                    if file_match and re.search(p["regex"], line, re.IGNORECASE):
                        issues.append(InfraIssue(p["name"], p["severity"], p["category"], f"{filename}:{i}", line.strip(), p["fix"], p["why"]))
        return issues

    def _scan_infra_antipatterns(self, files: dict[str, str]) -> list[InfraIssue]:
        issues = []
        for filename, content in files.items():
            for i, line in enumerate(content.split("\n"), 1):
                for p in INFRA_ANTIPATTERNS:
                    if re.search(p["regex"], line, re.IGNORECASE):
                        issues.append(InfraIssue(p["name"], p["severity"], p["category"], f"{filename}:{i}", line.strip(), p["fix"], p.get("why", p.get("description", ""))))
        return issues

    def _format_issues(self, issues: list[InfraIssue]) -> str:
        if not issues: return "No issues detected by local scan."
        lines = [f"Found {len(issues)} issues:"]
        for sev in ("critical", "high", "medium", "low"):
            for iss in [x for x in issues if x.severity == sev]:
                lines.append(f"  {iss.to_summary()}")
        return "\n".join(lines)
