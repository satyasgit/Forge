"""
QA Agent — fully working test-generation agent.

Capabilities:
  - Local pre-scan: detects untested routes, validators, error paths, auth
    gates, and DB operations in source code (no API call, zero cost)
  - Anti-pattern scan: finds bad practices in existing test files
  - Generates pytest unit + integration + E2E + load tests
  - Produces conftest.py with correct fixtures
  - Coverage gap report with per-file requirements
  - Playwright E2E scripts for critical user journeys

Usage:
    from agents.qa_agent import QAAgent

    agent = QAAgent(project_id="my-project")
    result = agent.generate_tests(
        source_code={"routes/users.py": "...", "services/user.py": "..."},
        existing_tests={"tests/test_users.py": "..."},
        framework="fastapi",
        context="User auth + subscription management"
    )
    print(result.output)
"""
from __future__ import annotations

import re
import textwrap
from dataclasses import dataclass, field

from agents.base import BaseAgent, AgentResult
from skills.qa.pytest_patterns import (
    TEST_GAP_PATTERNS,
    TEST_ANTIPATTERN_PATTERNS,
    COVERAGE_REQUIREMENTS,
)
from skills.qa.fixture_library import (
    CONFTEST_TEMPLATE,
    PYTEST_INI,
    TEST_NAMING_RULES,
    LOCUST_TEMPLATE,
)


@dataclass
class TestGap:
    pattern_name: str
    severity: str
    category: str
    location: str
    evidence: str
    test_types_needed: list[str]
    template: str
    example: str

    def to_summary(self) -> str:
        types = ", ".join(self.test_types_needed)
        return f"[{self.severity.upper()}] {self.pattern_name} at {self.location} — needs: {types}"


@dataclass
class TestAntiPattern:
    pattern_name: str
    severity: str
    category: str
    location: str
    evidence: str
    fix: str

    def to_summary(self) -> str:
        return f"[{self.severity.upper()}] {self.pattern_name} at {self.location}"


from agents.agent_config import register_agent

@register_agent
class QAAgent(BaseAgent):
    name = "qa"
    role = "Senior QA Engineer / SDET"
    enabled_tools = ["write_file", "run_command", "github_create_file"]

    @property
    def system_prompt(self) -> str:
        gap_categories = ", ".join({p["category"] for p in TEST_GAP_PATTERNS})
        coverage_rules = "\n".join(
            f"- {layer}: {info['minimum_percent']}%+ ({info['rationale']})"
            for layer, info in COVERAGE_REQUIREMENTS.items()
        )
        naming_examples = "\n".join(
            f"  good: {ex}" for ex in TEST_NAMING_RULES["examples"]
        )
        return textwrap.dedent(f"""
            You are a senior QA engineer and SDET with 12+ years of experience
            in Python, FastAPI, React, and TypeScript testing.

            ## Coverage requirements by layer:
            {coverage_rules}

            ## Test gap categories you address:
            {gap_categories}

            ## Test naming pattern: {TEST_NAMING_RULES['pattern']}
            {naming_examples}

            ## conftest.py base to build on:
            {CONFTEST_TEMPLATE}

            ## pytest configuration:
            {PYTEST_INI}

            ## Your output structure for every task:

            ### COVERAGE ANALYSIS
            Table: file | target coverage | gap identified | priority

            ### CONFTEST.PY
            Full conftest.py with all fixtures. Extend existing ones — never duplicate.

            ### UNIT TESTS
            Pure function tests. Mock all I/O. Mark @pytest.mark.unit.

            ### INTEGRATION TESTS
            API endpoint tests with AsyncClient + test DB. Mark @pytest.mark.integration.

            ### E2E TESTS (PLAYWRIGHT)
            Critical user journeys: signup, upgrade, core feature.

            ### LOAD TEST
            Locust script for critical endpoints.

            ## Non-negotiable rules:
            - Every test name is a complete sentence describing scenario AND outcome
            - Each test has exactly ONE reason to fail
            - All external HTTP calls mocked (httpx_mock or respx)
            - Async tests use asyncio_mode = auto (no manual @pytest.mark.asyncio needed)
            - Never use time.sleep() — use freezegun
            - Fixtures provide setup — tests never call db.add() directly

            Produce complete, runnable code — not pseudocode.
        """).strip()

    def generate_tests(
        self,
        source_code: dict[str, str],
        existing_tests: dict[str, str] | None = None,
        framework: str = "fastapi",
        context: str = "",
    ) -> AgentResult:
        """Full test generation pipeline with local pre-scan."""
        gaps = self._scan_for_test_gaps(source_code)
        antipatterns = self._scan_existing_tests(existing_tests or {})

        source_block = "\n\n".join(
            f"### {fname}\n```python\n{content}\n```"
            for fname, content in source_code.items()
        )
        existing_block = ""
        if existing_tests:
            existing_block = "\n\n## Existing tests (extend, do not duplicate):\n" + "\n\n".join(
                f"### {fname}\n```python\n{content}\n```"
                for fname, content in existing_tests.items()
            )

        task = textwrap.dedent(f"""
            Generate a complete test suite for this {framework} codebase.

            ## Application context
            {context or 'No additional context provided.'}

            ## Source code to test:
            {source_block}
            {existing_block}

            ## Pre-computed test gaps (address ALL of these):
            {self._format_gap_summary(gaps)}

            ## Anti-patterns in existing tests (fix all):
            {self._format_antipattern_summary(antipatterns)}

            ## Locust load test template to adapt:
            {LOCUST_TEMPLATE}

            Every test must be immediately runnable with: pytest tests/ -v
        """).strip()

        return self.run(task)

    def generate_conftest(self, models: list[str], context: str = "") -> AgentResult:
        """Generate a project-specific conftest.py from model names."""
        task = textwrap.dedent(f"""
            Generate a complete conftest.py for a FastAPI project with these models:
            {', '.join(models)}

            Context: {context or 'Standard FastAPI + PostgreSQL app'}

            - One fixture per model, yields and rolls back on teardown
            - Async client fixture with test DB injected via dependency_overrides
            - Auth header helpers for each user role
            - Use base template from your instructions as starting point
        """)
        return self.run(task)

    def generate_e2e_tests(self, user_journeys: list[str], base_url: str = "http://localhost:3000") -> AgentResult:
        """Generate Playwright E2E tests for critical user journeys."""
        journeys_text = "\n".join(f"- {j}" for j in user_journeys)
        task = textwrap.dedent(f"""
            Write async Playwright tests for these user journeys:
            {journeys_text}

            Base URL: {base_url}
            Use page object pattern. Selectors: data-testid attributes.
            Produce: tests/pages/ page objects + tests/e2e/ test files.
        """)
        return self.run(task)

    def audit_test_quality(self, test_files: dict[str, str]) -> AgentResult:
        """Review existing tests and produce a prioritised fix plan."""
        antipatterns = self._scan_existing_tests(test_files)
        tests_block = "\n\n".join(
            f"### {fname}\n```python\n{content}\n```"
            for fname, content in test_files.items()
        )
        task = textwrap.dedent(f"""
            Audit these test files for quality issues.

            {tests_block}

            Pre-detected anti-patterns:
            {self._format_antipattern_summary(antipatterns)}

            For each issue: location, what's wrong, exact fix.
            Also check: implementation-testing, missing edge cases, flaky patterns.
            End with a prioritised fix list.
        """)
        return self.run(task)

    # ── Local scanners (no API cost) ──────────────────────────────────────────

    def _scan_for_test_gaps(self, source_code: dict[str, str]) -> list[TestGap]:
        gaps: list[TestGap] = []
        for filename, content in source_code.items():
            if any(s in filename for s in ("test_", "_test.", "conftest")):
                continue
            lines = content.split("\n")
            for i, line in enumerate(lines, 1):
                for pattern in TEST_GAP_PATTERNS:
                    if re.search(pattern["regex"], line, re.IGNORECASE):
                        gaps.append(TestGap(
                            pattern_name=pattern["name"],
                            severity=pattern["severity"],
                            category=pattern["category"],
                            location=f"{filename}:{i}",
                            evidence=line.strip(),
                            test_types_needed=pattern["test_types"],
                            template=pattern["template"],
                            example=pattern["example"],
                        ))
        return gaps

    def _scan_existing_tests(self, test_files: dict[str, str]) -> list[TestAntiPattern]:
        findings: list[TestAntiPattern] = []
        for filename, content in test_files.items():
            lines = content.split("\n")
            for i, line in enumerate(lines, 1):
                for pattern in TEST_ANTIPATTERN_PATTERNS:
                    if re.search(pattern["regex"], line, re.IGNORECASE):
                        findings.append(TestAntiPattern(
                            pattern_name=pattern["name"],
                            severity=pattern["severity"],
                            category=pattern["category"],
                            location=f"{filename}:{i}",
                            evidence=line.strip(),
                            fix=pattern["fix"],
                        ))
        return findings

    def _format_gap_summary(self, gaps: list[TestGap]) -> str:
        if not gaps:
            return "No test gaps detected by local scan."
        lines = [f"Found {len(gaps)} test gaps:"]
        for sev in ("high", "medium", "low"):
            for g in [x for x in gaps if x.severity == sev]:
                lines.append(f"  {g.to_summary()}")
        return "\n".join(lines)

    def _format_antipattern_summary(self, antipatterns: list[TestAntiPattern]) -> str:
        if not antipatterns:
            return "No anti-patterns found in existing tests."
        lines = [f"Found {len(antipatterns)} anti-patterns:"]
        for ap in antipatterns:
            lines.append(f"  {ap.to_summary()}")
        return "\n".join(lines)


if __name__ == "__main__":
    SAMPLE_SOURCE = {
        "api/routes/users.py": '''
from fastapi import APIRouter, Depends, HTTPException, status
from core.auth import get_current_user

router = APIRouter(prefix="/users")

@router.get("/{user_id}")
def get_user(user_id: str, _=Depends(get_current_user)):
    raise HTTPException(404, "User not found")

@router.post("/", status_code=201)
def create_user(data: dict):
    pass
''',
    }
    agent = QAAgent(project_id="demo")
    result = agent.generate_tests(SAMPLE_SOURCE, framework="fastapi", context="SaaS API")
    print(result.output)
    print(f"\n--- Cost: ${result.cost_usd:.4f} | {result.duration_seconds:.1f}s ---")
