"""
Frontend Agent — fully working React/TypeScript component builder.

Capabilities:
  - Local pre-scan: detects interactive elements, loading/error states,
    forms, useEffects, and a11y issues in existing components (no API call)
  - Generates React/TypeScript components with full test coverage hints
  - Vitest + RTL test files for every component
  - MSW handler stubs for API mocking
  - Accessibility audit on provided HTML/JSX
  - Tailwind + shadcn/ui component output

Usage:
    from agents.frontend_agent import FrontendAgent

    agent = FrontendAgent(project_id="my-project")
    result = agent.build_components(
        design_spec="User profile page with avatar, name, plan badge, edit form",
        api_routes={"GET /api/users/:id": "returns user object", "PATCH /api/users/:id": "updates user"},
        context="SaaS dashboard — React 18, Tailwind, React Query"
    )
    print(result.output)
"""
from __future__ import annotations

import re
import textwrap
from dataclasses import dataclass

from agents.base import BaseAgent, AgentResult
from skills.frontend.react_patterns import (
    REACT_COMPONENT_TEMPLATE,
    REACT_FORM_TEMPLATE,
    REACT_QUERY_KEYS,
    TAILWIND_CONVENTIONS,
    ACCESSIBILITY_CHECKLIST,
)
from skills.frontend.vitest_patterns import (
    COMPONENT_TEST_PATTERNS,
    A11Y_PATTERNS,
    VITEST_SETUP,
    MSW_SERVER_TEMPLATE,
    VITEST_CONFIG,
)


@dataclass
class ComponentGap:
    """A missing test or a11y issue found in a component file."""
    pattern_name: str
    severity: str
    category: str          # interaction | states | validation | a11y | navigation | ...
    location: str          # file:line
    evidence: str
    test_template: str
    example: str

    def to_summary(self) -> str:
        return f"[{self.severity.upper()}] {self.pattern_name} at {self.location} (category: {self.category})"


@dataclass
class A11yIssue:
    """An accessibility violation found in component source."""
    pattern_name: str
    severity: str
    wcag: str
    location: str
    evidence: str
    fix: str
    test: str

    def to_summary(self) -> str:
        return f"[{self.severity.upper()}] WCAG {self.wcag} — {self.pattern_name} at {self.location}"


from agents.agent_config import register_agent

@register_agent
class FrontendAgent(BaseAgent):
    name = "frontend"
    role = "Senior Frontend Engineer"
    enabled_tools = ["github_get_file", "github_create_file", "write_file", "run_command"]

    @property
    def system_prompt(self) -> str:
        tailwind_rules = "\n".join(
            f"  - {k}: {v}" for k, v in TAILWIND_CONVENTIONS.items()
        )
        a11y_rules = "\n".join(
            f"  - {rule}" for rule in ACCESSIBILITY_CHECKLIST
        )

        return textwrap.dedent(f"""
            You are a senior React/TypeScript engineer who writes production-quality
            components that are accessible, testable, and maintainable.

            ## Stack:
            React 18, TypeScript 5, Tailwind CSS, React Query v5,
            React Hook Form + Zod, Zustand, Vite, Vitest + RTL, MSW

            ## Component template (always follow this structure):
            {REACT_COMPONENT_TEMPLATE}

            ## Form template (for any form component):
            {REACT_FORM_TEMPLATE}

            ## Query key factory (always use this pattern):
            {REACT_QUERY_KEYS}

            ## Tailwind conventions:
            {tailwind_rules}

            ## Accessibility checklist (every component must pass):
            {a11y_rules}

            ## Vitest setup:
            {VITEST_SETUP}

            ## MSW server + handlers:
            {MSW_SERVER_TEMPLATE}

            ## Vitest config:
            {VITEST_CONFIG}

            ## Output structure for every task:

            ### COMPONENT FILES
            For each component:
              - ComponentName.tsx (component + types in same file, or .types.ts if > 5 interfaces)
              - ComponentName.test.tsx (Vitest + RTL tests)
              - index.ts (barrel export)

            ### MSW HANDLERS
            Add handlers to tests/mocks/handlers.ts for every API call made.

            ### STORYBOOK STORY (if relevant)
            ComponentName.stories.tsx with Default, Loading, Error, Empty stories.

            ### ACCESSIBILITY NOTES
            For each component: confirm WCAG 2.1 AA compliance or flag issues.

            ## Non-negotiable rules:
            - TypeScript strict mode — no `any`, no `!` non-null assertions
            - Every prop has a type — no implicit any in function signatures
            - Loading + error + empty states for every data-fetching component
            - aria-label on every icon button
            - form inputs linked to labels via htmlFor/id
            - React Query for all server state — no useState for async data
            - Zod schema is source of truth for form validation
            - Tests use getByRole/getByLabelText — never getByTestId as first choice

            Write complete, runnable TypeScript — not pseudocode.
        """).strip()

    # ──────────────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────────────

    def build_components(
        self,
        design_spec: str,
        api_routes: dict[str, str] | None = None,
        existing_components: dict[str, str] | None = None,
        context: str = "",
    ) -> AgentResult:
        """
        Full component build with local pre-scan.
        Mirrors SecurityAgent.run_full_audit() exactly.
        """
        # Step 1 — local scan (no API call)
        component_gaps = self._scan_components(existing_components or {})
        a11y_issues = self._scan_a11y(existing_components or {})

        # Step 2 — build enriched prompt
        routes_block = ""
        if api_routes:
            routes_block = "\n## API routes to integrate:\n" + "\n".join(
                f"  {method}: {desc}" for method, desc in api_routes.items()
            )

        existing_block = ""
        if existing_components:
            existing_block = "\n\n## Existing components (extend, do not duplicate):\n" + "\n\n".join(
                f"### {fname}\n```tsx\n{content}\n```"
                for fname, content in existing_components.items()
            )

        task = textwrap.dedent(f"""
            Build React/TypeScript components for this design spec.

            ## Design spec
            {design_spec}

            ## Application context
            {context or 'No additional context provided.'}
            {routes_block}
            {existing_block}

            ## Pre-detected component gaps (write tests covering all of these):
            {self._format_gap_summary(component_gaps)}

            ## Pre-detected accessibility issues (fix all):
            {self._format_a11y_summary(a11y_issues)}

            Produce complete component files + test files + MSW handlers.
            Every component must pass: tsc --noEmit && vitest run
        """).strip()

        return self.run(task)

    def audit_components(self, components: dict[str, str]) -> AgentResult:
        """Review existing components for test gaps and a11y issues."""
        gaps = self._scan_components(components)
        a11y = self._scan_a11y(components)

        comp_block = "\n\n".join(
            f"### {fname}\n```tsx\n{content}\n```"
            for fname, content in components.items()
        )

        task = textwrap.dedent(f"""
            Audit these React components for test coverage gaps and accessibility issues.

            {comp_block}

            Pre-detected test gaps:
            {self._format_gap_summary(gaps)}

            Pre-detected a11y issues:
            {self._format_a11y_summary(a11y)}

            For each issue: file:line, what's wrong, exact fix, and test to verify.
            Prioritise: a11y critical > test coverage critical > medium > low.
        """)
        return self.run(task)

    def write_tests_for_component(
        self,
        component_name: str,
        component_code: str,
        api_routes: dict[str, str] | None = None,
    ) -> AgentResult:
        """Write a complete test file for a single component."""
        gaps = self._scan_components({f"{component_name}.tsx": component_code})
        a11y = self._scan_a11y({f"{component_name}.tsx": component_code})

        task = textwrap.dedent(f"""
            Write a complete Vitest + RTL test file for this component.

            ## Component: {component_name}.tsx
            ```tsx
            {component_code}
            ```

            ## API routes (create MSW handlers for these):
            {api_routes or 'Infer from component code.'}

            ## Pre-detected gaps to cover:
            {self._format_gap_summary(gaps)}

            ## A11y issues to test for:
            {self._format_a11y_summary(a11y)}

            Write: {component_name}.test.tsx + MSW handlers for tests/mocks/handlers.ts
            Every gap must have at least one test. Every a11y issue must have a failing test.
        """)
        return self.run(task)

    # ──────────────────────────────────────────────────────────────────────────
    # Internal pre-scanners (no API cost)
    # Mirrors SecurityAgent._run_sast() / _scan_secrets() exactly
    # ──────────────────────────────────────────────────────────────────────────

    def _scan_components(self, components: dict[str, str]) -> list[ComponentGap]:
        """
        Scan component source for interaction/state/form patterns needing tests.
        Runs locally — zero API cost.
        """
        gaps: list[ComponentGap] = []
        for filename, content in components.items():
            if ".test." in filename or ".stories." in filename:
                continue
            lines = content.split("\n")
            for i, line in enumerate(lines, 1):
                for pattern in COMPONENT_TEST_PATTERNS:
                    if re.search(pattern["regex"], line, re.IGNORECASE):
                        gaps.append(ComponentGap(
                            pattern_name=pattern["name"],
                            severity=pattern["severity"],
                            category=pattern["category"],
                            location=f"{filename}:{i}",
                            evidence=line.strip(),
                            test_template=pattern["test_template"],
                            example=pattern["example"],
                        ))
        return gaps

    def _scan_a11y(self, components: dict[str, str]) -> list[A11yIssue]:
        """
        Scan for accessibility violations in JSX/TSX.
        Mirrors SecurityAgent._scan_secrets() exactly.
        """
        issues: list[A11yIssue] = []
        for filename, content in components.items():
            if ".test." in filename or ".stories." in filename:
                continue
            lines = content.split("\n")
            for i, line in enumerate(lines, 1):
                # Skip comments
                if line.strip().startswith("//") or line.strip().startswith("*"):
                    continue
                for pattern in A11Y_PATTERNS:
                    if re.search(pattern["regex"], line, re.IGNORECASE):
                        issues.append(A11yIssue(
                            pattern_name=pattern["name"],
                            severity=pattern["severity"],
                            wcag=pattern["wcag"],
                            location=f"{filename}:{i}",
                            evidence=line.strip(),
                            fix=pattern["fix"],
                            test=pattern["test"],
                        ))
        return issues

    def _format_gap_summary(self, gaps: list[ComponentGap]) -> str:
        if not gaps:
            return "No component test gaps detected by local scan."
        lines = [f"Found {len(gaps)} component test gaps:"]
        for sev in ("high", "medium", "low"):
            for g in [x for x in gaps if x.severity == sev]:
                lines.append(f"  {g.to_summary()}")
        return "\n".join(lines)

    def _format_a11y_summary(self, issues: list[A11yIssue]) -> str:
        if not issues:
            return "No accessibility issues detected by local scan."
        lines = [f"Found {len(issues)} accessibility issues:"]
        for sev in ("high", "medium", "low"):
            for issue in [x for x in issues if x.severity == sev]:
                lines.append(f"  {issue.to_summary()}")
        return "\n".join(lines)


if __name__ == "__main__":
    SAMPLE_COMPONENT = {
        "UserProfile.tsx": '''
import { useState } from "react";

export function UserProfile({ userId }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleSave = () => {
    setLoading(true);
    // save logic
  };

  if (loading) return <div>Loading...</div>;
  if (error) return <div>{error}</div>;

  return (
    <div>
      <img src="/avatar.jpg" />
      <input placeholder="Name" />
      <button onClick={handleSave}>Save</button>
    </div>
  );
}
''',
    }

    agent = FrontendAgent(project_id="demo")
    result = agent.build_components(
        design_spec="User profile page with avatar, name field, and save button",
        existing_components=SAMPLE_COMPONENT,
        api_routes={"PATCH /api/users/:id": "Update user name and avatar"},
        context="React 18 SaaS dashboard",
    )
    print(result.output)
    print(f"\n--- Cost: ${result.cost_usd:.4f} | {result.duration_seconds:.1f}s ---")
