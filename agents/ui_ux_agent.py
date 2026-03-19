"""
UI/UX Agent — fully working product designer.
Pre-scans feature descriptions for screen count, component types,
user personas, and usability risks before calling Claude.
"""
from __future__ import annotations
import re, textwrap
from dataclasses import dataclass
from agents.base import BaseAgent, AgentResult
from skills.ui_ux.design_patterns import USABILITY_HEURISTICS, COMPONENT_SPEC_REQUIREMENTS, SCREEN_SPEC_TEMPLATE, DESIGN_TOKEN_SPEC

@dataclass
class DesignSignal:
    signal_type: str; description: str; implication: str
    def to_summary(self): return f"[{self.signal_type.upper()}] {self.description} → {self.implication}"

class UIUXAgent(BaseAgent):
    name = "ui_ux"
    role = "Senior Product Designer"
    enabled_tools = ["figma_get_components", "figma_get_styles", "write_file"]

    @property
    def system_prompt(self) -> str:
        heuristics = "\n".join(f"  {k}: {v['name']} — {v['check']}" for k, v in USABILITY_HEURISTICS.items())
        component_states = "\n".join(
            f"  {comp}: states={info['required_states']}"
            for comp, info in list(COMPONENT_SPEC_REQUIREMENTS.items())[:4]
        )
        tokens_colors = "\n".join(f"  {k}: {v}" for k, v in DESIGN_TOKEN_SPEC["colors"].items())
        return textwrap.dedent(f"""
            You are a senior product designer who thinks in systems and ships designs
            that engineers can implement without follow-up questions.

            ## Usability heuristics (evaluate every screen against all 10):
            {heuristics}

            ## Component states (spec ALL states for every component):
            {component_states}

            ## Screen spec format (use for every screen):
            {SCREEN_SPEC_TEMPLATE}

            ## Design tokens — use these exact values:
            Colors: {tokens_colors}
            Typography: {", ".join(f"{k}: {v}" for k, v in DESIGN_TOKEN_SPEC["typography"].items())}
            Spacing: {", ".join(f"{k}={v}" for k, v in DESIGN_TOKEN_SPEC["spacing"].items())}

            ## Output for every task:

            ### SCREENS
            One spec per screen using the SCREEN_SPEC_TEMPLATE format.

            ### COMPONENT INVENTORY
            Every reusable component with all required states and props.

            ### USER FLOWS
            Numbered step-by-step for every primary and error path.

            ### DESIGN TOKENS
            Tailwind-compatible values for colors, typography, spacing.

            ### MOBILE ADAPTATION
            How each screen changes on mobile (< 768px).

            ### COPY GUIDE
            Exact text for every label, heading, CTA, error, and empty state.

            ### USABILITY AUDIT
            Rate each screen against Nielsen's 10 heuristics.
            Flag any heuristic violations with fix.

            ## Non-negotiable:
            - Every component spec includes ALL required states (loading, error, empty)
            - Every destructive action has a confirmation step
            - Every form has inline validation error messages
            - Every empty state has an actionable CTA
            - Copy is plain English — no jargon, no technical terms
            - All screens pass WCAG 2.1 AA contrast requirements
        """).strip()

    def design_feature(self, feature: str, user_type: str = "", context: str = "") -> AgentResult:
        signals = self._detect_design_signals(feature)
        task = textwrap.dedent(f"""
            Create a complete UI/UX spec for this feature.

            Feature: {feature}
            Primary user: {user_type or "Power user (daily active, 30+ days)"}
            App context: {context or "B2B SaaS web app + mobile."}

            Pre-detected design signals (address all):
            {self._format_signals(signals)}

            Produce full spec using your output structure.
            Every screen must use the SCREEN_SPEC_TEMPLATE format exactly.
        """).strip()
        return self.run(task)

    def audit_design(self, screen_descriptions: list[str]) -> AgentResult:
        screens_text = "\n".join(f"- {s}" for s in screen_descriptions)
        task = textwrap.dedent(f"""
            Audit these screens against Nielsen's 10 usability heuristics.
            Screens: {screens_text}
            For each heuristic violation: screen name, heuristic, problem, fix.
            Produce a prioritised remediation plan.
        """)
        return self.run(task)

    DESIGN_SIGNAL_PATTERNS = [
        (r"\bauth|login|sign.?up|register\b", "auth_flow", "Needs: login, register, forgot password, email verify screens"),
        (r"\bonboard\w*\b", "onboarding", "Needs: multi-step onboarding with progress indicator and skip option"),
        (r"\bdashboard|overview|home\b", "dashboard", "Needs: empty state (new user), populated state, and loading skeleton"),
        (r"\bpay|billing|subscri|stripe|plan\b", "billing", "Needs: pricing page, checkout, success, and billing settings screens"),
        (r"\bnotif|alert|email|push\b", "notifications", "Needs: notification center, settings, and empty state"),
        (r"\badmin|manage|settings\b", "settings", "Needs: settings grouped by category with unsaved changes warning"),
        (r"\bmobile|ios|android|native\b", "mobile", "Every screen needs explicit mobile layout spec"),
        (r"\bsearch|filter|sort\b", "search_filter", "Needs: empty results state, loading state, and filter UI spec"),
        (r"\berror|fail|404|500\b", "error_states", "Needs: 404, 500, network error, and permission denied screens"),
        (r"\bupload|import|file\b", "file_upload", "Needs: drag-drop zone, progress, success, and error states"),
    ]

    def _detect_design_signals(self, feature_text: str) -> list[DesignSignal]:
        signals = []
        for regex, signal_type, implication in self.DESIGN_SIGNAL_PATTERNS:
            if re.search(regex, feature_text, re.IGNORECASE):
                match = re.search(regex, feature_text, re.IGNORECASE)
                signals.append(DesignSignal(signal_type, f"Detected: '{match.group(0)}'", implication))
        return signals

    def _format_signals(self, signals: list[DesignSignal]) -> str:
        if not signals: return "No specific design signals detected."
        return "\n".join(["Detected signals:"] + [f"  {s.to_summary()}" for s in signals])
