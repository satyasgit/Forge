"""
PM Skill: PRD structure and section definitions.
Mirrors skills/security/owasp.py — structured reference data
injected into PMAgent's system prompt so it produces consistent,
complete PRDs every time.
"""

PRD_SECTIONS: dict[str, dict] = {
    "problem_statement": {
        "title": "Problem statement",
        "required": True,
        "description": "The user pain being solved, backed by evidence.",
        "questions_to_answer": [
            "Who exactly experiences this problem? (be specific — not 'all users')",
            "How do they solve it today? (workaround, competitor, nothing)",
            "What does it cost them? (time, money, frustration, churn)",
            "What's our evidence this is real? (interviews, support tickets, data)",
        ],
        "anti_patterns": [
            "Vague persona: 'users want X' — specify which segment",
            "Solution masquerading as problem: 'users want a dashboard' is a solution, not a problem",
            "No evidence: opinions without data",
        ],
    },
    "success_metrics": {
        "title": "Success metrics",
        "required": True,
        "description": "Measurable KPIs with baselines, targets, and measurement method.",
        "metric_types": {
            "primary": "The one metric that defines success (North Star)",
            "secondary": "Supporting metrics that should improve",
            "guardrail": "Metrics that must NOT regress (latency, error rate, churn)",
        },
        "good_metric_template": "{metric_name}: from {baseline} to {target} within {timeframe}, measured via {tool}",
        "examples": [
            "Trial-to-paid conversion: from 8% to 12% within 90 days, measured via Stripe",
            "Time-to-first-value: from 4 days to 1 day within 60 days, measured via Mixpanel",
            "Support tickets about X: from 40/week to <10/week within 30 days, measured via Zendesk",
        ],
    },
    "user_stories": {
        "title": "User stories",
        "required": True,
        "description": "Structured stories with Gherkin acceptance criteria.",
        "format": "As a [specific persona], I want [specific action] so that [measurable benefit]",
        "acceptance_criteria_format": "Given [precondition] / When [action] / Then [observable outcome]",
        "story_sizing": {
            "XS": "< 2 hours — a single UI change, config update",
            "S":  "0.5–1 day — one endpoint + UI",
            "M":  "2–3 days — a feature with DB + API + UI",
            "L":  "1 week — a feature with integrations",
            "XL": "2+ weeks — must be broken down",
        },
        "definition_of_done": [
            "All acceptance criteria pass",
            "Unit + integration tests written and passing",
            "PR reviewed and approved",
            "Deployed to staging and smoke-tested",
            "Analytics events firing correctly",
            "Error states handled and tested",
            "Mobile-responsive (if web feature)",
        ],
    },
    "technical_requirements": {
        "title": "Technical requirements",
        "required": True,
        "description": "Non-functional requirements, constraints, and SLAs.",
        "categories": {
            "performance": "p99 latency, throughput, payload size limits",
            "scale": "Concurrent users, data volume, growth projections",
            "availability": "Uptime SLA (99.9% = 8.7h downtime/year)",
            "compatibility": "Browser versions, OS versions, screen sizes",
            "compliance": "GDPR, SOC 2, HIPAA, PCI-DSS applicability",
            "accessibility": "WCAG 2.1 AA minimum",
        },
    },
    "out_of_scope": {
        "title": "Out of scope (MVP)",
        "required": True,
        "description": "Explicit list of what is NOT being built. Forces prioritisation.",
        "why_important": "Prevents scope creep. If it's not listed here, stakeholders assume it's included.",
        "format": "NOT included in v1: [feature]. Rationale: [why deferred]. Target: [v2/never/separate epic]",
    },
    "launch_plan": {
        "title": "Launch plan",
        "required": True,
        "description": "Phased rollout with rollback triggers.",
        "phases": {
            "internal": "Team only — dogfooding, no feature flag needed",
            "beta": "5–10% of users via feature flag, invite-only, or opt-in",
            "ga": "100% of users — monitor dashboards for 48h before removing flag",
        },
        "rollback_triggers": [
            "Error rate increases > 2x baseline",
            "p99 latency increases > 50%",
            "Conversion rate drops > 10%",
            "Any P0/P1 bug reported",
        ],
        "feature_flag_template": "feature_{name}_{date}  # e.g. feature_new_checkout_2024_03",
    },
}

# ── Persona library ───────────────────────────────────────────────────────────
# Re-used across user stories to avoid inventing vague personas.

PERSONA_TEMPLATES: dict[str, dict] = {
    "new_user": {
        "label": "New user (0–7 days)",
        "context": "Just signed up, hasn't completed onboarding, uncertain about value",
        "primary_goal": "Reach first value moment as fast as possible",
        "pain_points": ["Overwhelmed by options", "Unclear next step", "Doubts about ROI"],
    },
    "power_user": {
        "label": "Power user (30+ days, daily active)",
        "context": "Knows the product well, has integrated it into their workflow",
        "primary_goal": "Get more done faster, automate repetitive tasks",
        "pain_points": ["Missing advanced features", "Slow on complex tasks", "No API access on free plan"],
    },
    "admin": {
        "label": "Team admin / workspace owner",
        "context": "Manages seats, billing, and permissions for their team",
        "primary_goal": "Control access, manage spend, see team usage",
        "pain_points": ["No visibility into team usage", "Manual seat management", "Surprise invoices"],
    },
    "trial_user": {
        "label": "Trial user (actively evaluating)",
        "context": "14-day trial, comparing against competitors, needs to justify to stakeholder",
        "primary_goal": "Build a business case for purchasing",
        "pain_points": ["Can't test full feature set", "No clear upgrade prompt at right moment"],
    },
    "mobile_user": {
        "label": "Mobile-first user",
        "context": "Primarily uses app on phone, on-the-go use cases",
        "primary_goal": "Quick actions, push notifications, offline access",
        "pain_points": ["Web-only features", "Desktop-only settings", "No offline mode"],
    },
}

# ── Analytics event schema ────────────────────────────────────────────────────

ANALYTICS_EVENT_TEMPLATE = {
    "structure": {
        "event_name": "snake_case verb_noun (e.g. subscription_upgraded, feature_used)",
        "required_properties": ["user_id", "timestamp", "session_id"],
        "optional_properties": "Context-specific (plan, feature_name, source, etc.)",
    },
    "standard_events": [
        "signed_up", "onboarding_completed", "feature_first_used",
        "trial_started", "upgrade_modal_viewed", "upgrade_clicked",
        "subscription_upgraded", "subscription_downgraded", "subscription_cancelled",
        "payment_succeeded", "payment_failed",
        "invite_sent", "invite_accepted",
        "export_completed", "api_key_created",
    ],
    "tool": "PostHog or Mixpanel — choose one, use consistently",
}
