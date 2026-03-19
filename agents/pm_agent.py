"""
PM Agent — fully working product manager agent.

Capabilities:
  - Local pre-scan: extracts entities, integrations, and complexity signals
    from the feature description (no API call, zero cost)
  - Generates complete PRDs with problem statement, metrics, user stories,
    Gherkin acceptance criteria, and launch plan
  - Breaks features into Jira-ready epics → stories → tasks with estimates
  - Creates Jira tickets via tool if integration is enabled
  - Produces analytics event schema
  - Surfaces risks and out-of-scope decisions

Usage:
    from agents.pm_agent import PMAgent

    agent = PMAgent(project_id="my-project")
    result = agent.write_prd(
        feature="Stripe subscription billing with team seats and admin portal",
        target_users="SaaS startups with 1-20 engineers",
        context="B2B SaaS, currently has 0 billing — this is v1"
    )
    print(result.output)
"""
from __future__ import annotations

import re
import textwrap
from dataclasses import dataclass, field

from agents.base import BaseAgent, AgentResult
from skills.pm.prd_structure import PRD_SECTIONS, PERSONA_TEMPLATES, ANALYTICS_EVENT_TEMPLATE
from skills.pm.jira_templates import (
    EPIC_TEMPLATE,
    STORY_TEMPLATE,
    TASK_TEMPLATE,
    BUG_TEMPLATE,
    SPRINT_RULES,
    ENTITY_EXTRACTION_PATTERNS,
)


@dataclass
class FeatureEntity:
    """A detected component/concern extracted from the feature description."""
    entity_type: str      # api_endpoint | db_model | auth | integration | ui_screen | ...
    name: str             # detected name or description
    jira_label: str
    creates: str          # story | task | spike
    note: str = ""

    def to_summary(self) -> str:
        note_part = f" ({self.note})" if self.note else ""
        return f"[{self.creates.upper()}] {self.entity_type}: {self.name}{note_part} — label: {self.jira_label}"


@dataclass
class ComplexitySignal:
    """A signal that affects scope, risk, or estimate."""
    signal: str
    impact: str           # scope | risk | estimate | dependency
    description: str


class PMAgent(BaseAgent):
    name = "pm"
    role = "Senior Product Manager"
    enabled_tools = ["jira_create_ticket", "slack_send_message"]

    @property
    def system_prompt(self) -> str:
        sections_summary = "\n".join(
            f"- {k}: {v['description']} (required: {v['required']})"
            for k, v in PRD_SECTIONS.items()
        )
        personas_summary = "\n".join(
            f"- {k}: {v['label']} — {v['primary_goal']}"
            for k, v in PERSONA_TEMPLATES.items()
        )
        story_points = "\n".join(
            f"  {pts}pts: {desc}"
            for pts, desc in SPRINT_RULES["story_point_scale"].items()
        )

        return textwrap.dedent(f"""
            You are a senior product manager with a strong technical background.
            You write PRDs that engineers can ship from, and tickets they can
            pick up without asking questions.

            ## PRD sections you always include:
            {sections_summary}

            ## Available personas (use these, don't invent vague ones):
            {personas_summary}

            ## Story point scale:
            {story_points}

            ## Epic template to use:
            {EPIC_TEMPLATE}

            ## Story template to use (including Gherkin AC):
            {STORY_TEMPLATE}

            ## Task template (sub-tasks):
            {TASK_TEMPLATE}

            ## Analytics event structure:
            {ANALYTICS_EVENT_TEMPLATE}

            ## Non-negotiable rules:
            - Every user story has Gherkin acceptance criteria (Given/When/Then)
            - Every story has a story point estimate using the scale above
            - Stories > 8pts MUST be split before putting in sprint
            - Acceptance criteria are testable — never "works correctly" or "looks good"
            - Every feature has explicit OUT OF SCOPE section
            - Success metrics have baseline, target, timeframe, and measurement tool
            - Launch plan has explicit rollback triggers (error rate, conversion drop)

            ## Output format:
            1. PRD (full document with all sections)
            2. EPIC breakdown (1 epic with child stories + tasks)
            3. JIRA TICKET DRAFTS (ready to create, formatted per templates)
            4. ANALYTICS EVENTS (event name + properties + trigger)
            5. RISKS AND OPEN QUESTIONS (blockers, unknowns, dependencies)

            Be specific. No "TBD". If you don't have enough info, state the
            assumption you're making and flag it as an open question.
        """).strip()

    # ──────────────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────────────

    def write_prd(
        self,
        feature: str,
        target_users: str = "",
        context: str = "",
        existing_features: str = "",
    ) -> AgentResult:
        """
        Full PRD generation with local entity extraction pre-scan.
        Mirrors SecurityAgent.run_full_audit() exactly.
        """
        # Step 1 — local scan (no API call)
        entities = self._extract_entities(feature)
        signals = self._detect_complexity_signals(feature)

        # Step 2 — build enriched prompt
        entities_summary = self._format_entities(entities)
        signals_summary = self._format_complexity_signals(signals)

        task = textwrap.dedent(f"""
            Write a complete PRD for this feature request.

            ## Feature request
            {feature}

            ## Target users
            {target_users or 'Not specified — infer from context and flag as assumption.'}

            ## Application context
            {context or 'Not specified — state your assumptions.'}

            ## Existing product context
            {existing_features or 'No existing features provided.'}

            ## Pre-extracted entities (produce Jira tickets for all of these):
            {entities_summary}

            ## Complexity signals detected (address in risk section):
            {signals_summary}

            Produce the full PRD + epic breakdown + Jira ticket drafts as
            described in your instructions. Flag every assumption you make.
        """).strip()

        return self.run(task)

    def break_down_epic(self, epic_description: str, sprint_capacity: int = 20) -> AgentResult:
        """Break an epic into sprint-ready stories and tasks."""
        task = textwrap.dedent(f"""
            Break down this epic into sprint-ready stories and tasks.

            Epic: {epic_description}

            Sprint capacity: {sprint_capacity} story points
            Sprint velocity buffer: {SPRINT_RULES['velocity_buffer']*100:.0f}%
            Effective capacity: {int(sprint_capacity * SPRINT_RULES['velocity_buffer'])} points

            Rules:
            - Any story > 8 points must be split
            - Technical tasks (migrations, config, setup) go as sub-tasks
            - Each story includes Gherkin AC
            - Output a sprint plan: which stories fit in sprint 1 vs sprint 2

            Use the story and task templates from your instructions.
        """)
        return self.run(task)

    def write_bug_report(self, description: str, severity: str = "P2") -> AgentResult:
        """Structure a bug report from a description."""
        task = textwrap.dedent(f"""
            Structure this bug report using the bug template format.

            Description: {description}
            Initial severity: {severity}

            Bug template:
            {BUG_TEMPLATE}

            Fill in all fields. If information is missing, mark as [NEEDS INFO].
            Add root cause hypothesis based on the description.
        """)
        return self.run(task)

    def create_jira_tickets(self, prd_output: str, project_key: str) -> AgentResult:
        """Parse a PRD output and create real Jira tickets via tool use."""
        task = textwrap.dedent(f"""
            Parse this PRD and create Jira tickets for each story and task.

            Project key: {project_key}

            PRD:
            {prd_output}

            For each story:
            1. Call jira_create_ticket with issue_type="Story"
            2. For each sub-task, call jira_create_ticket with issue_type="Sub-task"
            3. Report back the ticket keys and URLs created

            Use story point labels: SP-1, SP-2, SP-3, SP-5, SP-8, SP-13
            Use component labels from the PRD: api, frontend, backend, mobile, etc.
        """)
        return self.run(task)

    # ──────────────────────────────────────────────────────────────────────────
    # Internal pre-scanners (no API cost)
    # Mirrors SecurityAgent._run_sast() / _scan_secrets() exactly
    # ──────────────────────────────────────────────────────────────────────────

    def _extract_entities(self, feature_text: str) -> list[FeatureEntity]:
        """
        Extract structured components from a natural language feature description.
        Each entity becomes at least one Jira ticket.
        """
        entities: list[FeatureEntity] = []
        seen: set[str] = set()

        for pattern in ENTITY_EXTRACTION_PATTERNS:
            matches = re.findall(pattern["regex"], feature_text, re.IGNORECASE)
            for match in matches:
                name = match if isinstance(match, str) else " ".join(match)
                key = f"{pattern['name']}:{name.lower()}"
                if key in seen:
                    continue
                seen.add(key)
                entities.append(FeatureEntity(
                    entity_type=pattern["name"],
                    name=name,
                    jira_label=pattern["jira_label"],
                    creates=pattern["creates"],
                    note=pattern.get("note", ""),
                ))
        return entities

    def _detect_complexity_signals(self, feature_text: str) -> list[ComplexitySignal]:
        """Detect signals that increase scope, risk, or estimate."""
        signals: list[ComplexitySignal] = []
        SIGNAL_PATTERNS = [
            (r"\bmulti.?tenant\b",       "scope",      "Multi-tenancy requires row-level security on every query"),
            (r"\breal.?time\b",          "estimate",   "Real-time features need WebSocket or SSE — adds significant complexity"),
            (r"\boffline\b",             "estimate",   "Offline support requires sync logic and conflict resolution"),
            (r"\bmigrat\b",              "risk",       "Data migration — needs rollback plan and backfill script"),
            (r"\bGDPR|HIPAA|PCI.DSS\b",  "scope",      "Compliance requirement — adds audit logging, data residency, consent flows"),
            (r"\bthird.?party|integrat", "dependency", "Third-party integration — needs spike if team unfamiliar"),
            (r"\bpermission|RBAC|role",  "scope",      "Permission system — needs careful schema design upfront"),
            (r"\bscal\w+|high.?traffic", "estimate",   "Scale requirement — needs caching, queue, and load test plan"),
            (r"\bbackward.?compat",      "risk",       "Backward compatibility — versioned API or feature flag required"),
            (r"\bmobile\b",              "scope",      "Mobile requirement — double the UI work (web + native)"),
        ]
        for regex, impact, description in SIGNAL_PATTERNS:
            if re.search(regex, feature_text, re.IGNORECASE):
                signal_name = re.search(regex, feature_text, re.IGNORECASE).group(0)
                signals.append(ComplexitySignal(
                    signal=signal_name,
                    impact=impact,
                    description=description,
                ))
        return signals

    def _format_entities(self, entities: list[FeatureEntity]) -> str:
        if not entities:
            return "No specific entities detected — infer from feature description."
        lines = [f"Detected {len(entities)} entities requiring Jira tickets:"]
        for e in entities:
            lines.append(f"  {e.to_summary()}")
        return "\n".join(lines)

    def _format_complexity_signals(self, signals: list[ComplexitySignal]) -> str:
        if not signals:
            return "No complexity signals detected."
        lines = [f"Detected {len(signals)} complexity signals:"]
        for s in signals:
            lines.append(f"  [{s.impact.upper()}] '{s.signal}' — {s.description}")
        return "\n".join(lines)


if __name__ == "__main__":
    agent = PMAgent(project_id="demo")
    result = agent.write_prd(
        feature="""
        Stripe subscription billing with three tiers (Free, Pro $29/mo, Business $99/mo).
        Team seats on Business plan. Stripe customer portal for self-service.
        Webhook handling for payment failures and cancellations.
        Mobile IAP via RevenueCat for iOS/Android.
        GDPR-compliant data deletion on cancellation.
        """,
        target_users="Solo founders and small SaaS teams (1-10 people)",
        context="B2B SaaS web + mobile app, no billing currently, ~500 beta users",
    )
    print(result.output)
    print(f"\n--- Cost: ${result.cost_usd:.4f} | {result.duration_seconds:.1f}s ---")
