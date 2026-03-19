"""
PM Skill: Jira ticket templates.
Mirrors skills/security/threat_model.py — structured templates injected
into PMAgent prompts so every ticket it creates has consistent, complete
fields that engineers can act on immediately.
"""

# ── Epic template ─────────────────────────────────────────────────────────────

EPIC_TEMPLATE = """
## Epic: {epic_name}

**Goal:** {one_sentence_goal}
**Owner:** {pm_name}
**Target release:** {quarter_and_year}
**Success metric:** {primary_kpi}

### Why now
{urgency_rationale}

### Scope
Stories in this epic:
- [ ] {story_1_summary} ({estimate})
- [ ] {story_2_summary} ({estimate})

### Out of scope
- {explicitly_excluded_1}
- {explicitly_excluded_2}

### Dependencies
- Blocked by: {dependency_or_none}
- Blocks: {downstream_work_or_none}
"""

# ── Story template ────────────────────────────────────────────────────────────

STORY_TEMPLATE = """
## Story: {story_title}

**As a** {persona}
**I want** {action}
**So that** {measurable_benefit}

**Epic:** {parent_epic}
**Story points:** {fibonacci: 1|2|3|5|8|13}
**Priority:** {P0_critical|P1_high|P2_medium|P3_low}

### Acceptance criteria
```gherkin
Feature: {feature_name}

  Scenario: {happy_path_scenario}
    Given {user_state_precondition}
    When  {user_performs_action}
    Then  {observable_system_outcome}
    And   {additional_outcome_if_any}

  Scenario: {error_scenario}
    Given {error_precondition}
    When  {user_performs_action}
    Then  {error_response}
```

### Technical notes
{implementation_hints_for_engineers}

### Design
{figma_link_or_description}

### Analytics events
- `{event_name}` fired when: {trigger_condition}

### Definition of done
- [ ] All acceptance criteria pass
- [ ] Unit + integration tests written
- [ ] PR reviewed by at least 1 engineer
- [ ] Deployed to staging, smoke-tested
- [ ] Analytics events verified in PostHog
- [ ] Mobile-responsive verified (if web)
"""

# ── Task template (sub-task of a story) ──────────────────────────────────────

TASK_TEMPLATE = """
## Task: {task_title}

**Parent story:** {story_key}
**Assignee:** {engineer_name_or_unassigned}
**Estimate:** {hours}h

### What to build
{specific_technical_description}

### Files to touch
- `{file_path_1}` — {what_changes}
- `{file_path_2}` — {what_changes}

### Testing required
- [ ] {test_description_1}
- [ ] {test_description_2}

### Done when
{single_sentence_completion_criterion}
"""

# ── Bug template ──────────────────────────────────────────────────────────────

BUG_TEMPLATE = """
## Bug: {short_title}

**Severity:** {P0_data_loss|P1_broken_feature|P2_degraded|P3_cosmetic}
**Affects:** {feature_area}
**Reported by:** {source: user|monitoring|internal}
**Environment:** {production|staging|both}

### Steps to reproduce
1. {step_1}
2. {step_2}
3. {step_3}

### Expected behaviour
{what_should_happen}

### Actual behaviour
{what_actually_happens}

### Evidence
```
{error_message_or_screenshot_description}
```

### Root cause hypothesis
{engineer_initial_assessment_or_unknown}

### Fix approach
{proposed_fix_or_investigation_needed}
"""

# ── Sprint planning breakdown rules ──────────────────────────────────────────

SPRINT_RULES = {
    "velocity_buffer": 0.7,   # plan to 70% capacity to allow for bugs/interrupts
    "max_story_points_per_engineer": 10,   # per 2-week sprint
    "story_point_scale": {
        1: "Trivial change — < 2 hours, single file",
        2: "Small — half a day, one layer (e.g. one route)",
        3: "Medium — 1 day, one full vertical slice",
        5: "Large — 2–3 days, multiple layers + tests",
        8: "X-Large — 1 week, complex feature with integrations",
        13: "Too big — must be split before sprint planning",
    },
    "spike_rules": [
        "Spikes have a time-box (max 2 days)",
        "Spikes produce a written recommendation, not code",
        "If uncertainty > 50%, spike first",
    ],
}

# ── Ticket parser — extracts structured data from natural language ────────────
# Used by PMAgent._parse_feature() local pre-scan (no API call)

ENTITY_EXTRACTION_PATTERNS: list[dict] = [
    {
        "name": "API endpoint",
        "regex": r"\b(GET|POST|PUT|PATCH|DELETE)\s+/[\w/{}]+",
        "jira_label": "api",
        "creates": "task",
    },
    {
        "name": "Database model",
        "regex": r"\b(create|add|store|save|persist)\s+(?:a\s+)?(\w+)\s+(?:model|table|entity|record)",
        "jira_label": "database",
        "creates": "task",
    },
    {
        "name": "Auth requirement",
        "regex": r"\b(login|auth(?:entication)?|permission|role|admin|JWT|OAuth)\b",
        "jira_label": "auth",
        "creates": "story",
    },
    {
        "name": "Third-party integration",
        "regex": r"\b(Stripe|Twilio|SendGrid|Firebase|AWS|Sentry|PostHog|Mixpanel|Figma)\b",
        "jira_label": "integration",
        "creates": "story",
        "note": "Integrations need spike first if team is unfamiliar",
    },
    {
        "name": "UI screen",
        "regex": r"\b(page|screen|view|dashboard|modal|form|component)\b",
        "jira_label": "frontend",
        "creates": "story",
    },
    {
        "name": "Mobile requirement",
        "regex": r"\b(mobile|iOS|Android|React Native|Expo|push notification)\b",
        "jira_label": "mobile",
        "creates": "story",
    },
    {
        "name": "Email / notification",
        "regex": r"\b(email|notification|alert|webhook|SMS)\b",
        "jira_label": "notifications",
        "creates": "task",
    },
    {
        "name": "Analytics requirement",
        "regex": r"\b(track|analytics|event|funnel|conversion|retention)\b",
        "jira_label": "analytics",
        "creates": "task",
    },
]
