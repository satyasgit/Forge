"""
Code Review Agent — fully working principal-engineer code reviewer.
Pre-scans for: code smells, naming issues, error handling, complexity,
N+1 queries, missing types, print statements, and architecture smells.
"""
from __future__ import annotations
import re, textwrap
from dataclasses import dataclass
from agents.base import BaseAgent, AgentResult
from skills.code_review.review_patterns import CODE_SMELL_PATTERNS, ARCHITECTURE_SMELLS, COMPLEXITY_THRESHOLDS, PR_REVIEW_CHECKLIST

@dataclass
class CodeSmell:
    pattern_name: str; severity: str; category: str; location: str; evidence: str; fix: str
    def to_summary(self): return f"[{self.severity.upper()}] {self.pattern_name} at {self.location} ({self.category})"

from agents.agent_config import register_agent

@register_agent
class CodeReviewAgent(BaseAgent):
    name = "code_review"
    role = "Principal Engineer / Code Reviewer"
    enabled_tools = ["github_get_file", "run_command"]

    @property
    def system_prompt(self) -> str:
        checklist_text = "\n".join(
            f"  {cat.upper()}:\n" + "\n".join(f"    - {item}" for item in items)
            for cat, items in PR_REVIEW_CHECKLIST.items()
        )
        arch_smells = "\n".join(f"  - {s['name']}: {s['description']}" for s in ARCHITECTURE_SMELLS)
        thresholds = "\n".join(
            f"  - {metric}: good={info['good']}, warning={info['warning']}, critical={info['critical']}"
            for metric, info in COMPLEXITY_THRESHOLDS.items()
        )
        return textwrap.dedent(f"""
            You are a principal engineer doing a thorough code review.
            You review code like a senior engineer at a top-tier company —
            precise, constructive, and focused on what matters.

            ## Review checklist (check every item for every PR):
            {checklist_text}

            ## Architecture smells to look for:
            {arch_smells}

            ## Complexity thresholds:
            {thresholds}

            ## Output format (use EXACTLY this structure):

            ### EXECUTIVE SUMMARY
            2-3 sentences: overall quality, most critical issue, merge recommendation.

            ### CRITICAL (must fix before merge)
            Issues causing bugs, data loss, security problems, or broken contracts.

            ### HIGH (fix this sprint)
            Performance problems, missing error handling, logic bugs, bad patterns.

            ### MEDIUM (next sprint)
            Code smell, naming, missing tests, tech debt that compounds.

            ### LOW / SUGGESTIONS
            Style, minor readability, non-blocking improvements.

            ### POSITIVE PATTERNS
            What was done well — reinforce good practices explicitly.

            For EVERY finding provide:
            - File and line number
            - What the problem is and why it matters
            - Exact fix (code snippet, not prose description)

            ## Non-negotiable rules:
            - Never say "consider" — say exactly what to do
            - Every finding has a code example of the fix
            - Positive patterns section is never empty
            - Flag N+1 queries, blocking I/O in async, and mutable defaults as CRITICAL
        """).strip()

    def review(self, code: dict[str, str], context: str = "", pr_description: str = "") -> AgentResult:
        """Full code review with local pre-scan — mirrors SecurityAgent.run_full_audit()."""
        smells = self._scan_for_smells(code)
        code_block = "\n\n".join(f"### {f}\n```\n{c}\n```" for f, c in code.items())
        task = textwrap.dedent(f"""
            Perform a thorough code review of this code.

            ## PR description
            {pr_description or "No PR description provided."}

            ## Context
            {context or "No additional context."}

            ## Code:
            {code_block}

            ## Pre-detected code smells (validate and expand):
            {self._format_smells(smells)}

            Produce the full review using your output format.
            For every finding, show the exact code fix — not a description of the fix.
        """).strip()
        return self.run(task)

    def review_diff(self, diff: str, context: str = "") -> AgentResult:
        """Review a git diff rather than full files."""
        task = textwrap.dedent(f"""
            Review this git diff. Focus on the changed lines — don't comment on unchanged context lines.
            Context: {context or "No context provided."}
            ```diff
            {diff}
            ```
            Apply your full review format. Flag regressions (things that were better before).
        """)
        return self.run(task)

    def suggest_refactor(self, code: str, filename: str, goal: str = "") -> AgentResult:
        """Suggest a specific refactor for a piece of code."""
        smells = self._scan_for_smells({filename: code})
        task = textwrap.dedent(f"""
            Suggest a refactor for this code.
            Goal: {goal or "Improve readability, testability, and maintainability."}
            File: {filename}
            ```python
            {code}
            ```
            Pre-detected smells: {self._format_smells(smells)}
            Produce: 1) what problems exist, 2) the refactored code, 3) what improved.
        """)
        return self.run(task)

    def _scan_for_smells(self, code: dict[str, str]) -> list[CodeSmell]:
        smells = []
        for filename, content in code.items():
            for i, line in enumerate(content.split("\n"), 1):
                stripped = line.strip()
                for p in CODE_SMELL_PATTERNS:
                    # Skip comment lines for non-comment patterns
                    is_comment = stripped.startswith(("#", "//", "*"))
                    targets_comments = any(kw in p["name"].upper() for kw in ("TODO","FIXME","HACK","COMMENT"))
                    if is_comment and not targets_comments:
                        continue
                    if re.search(p["regex"], line, re.IGNORECASE):
                        smells.append(CodeSmell(p["name"], p["severity"], p["category"], f"{filename}:{i}", line.strip(), p["fix"]))
        return smells

    def _format_smells(self, smells: list[CodeSmell]) -> str:
        if not smells: return "No code smells detected by local scan."
        lines = [f"Found {len(smells)} code smells:"]
        for sev in ("critical", "high", "medium", "low"):
            for s in [x for x in smells if x.severity == sev]:
                lines.append(f"  {s.to_summary()}")
        return "\n".join(lines)
