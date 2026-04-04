# Pipeline Templates

This directory contains YAML configuration files that define reusable agent pipelines.

## Quick Start

**Run a template**:
```bash
python -m pipeline run --template api_only --feature "User authentication API" --project my-project
```

**List all templates**:
```bash
python -c "from pipeline.config_loader import load_all_templates; import json; print(json.dumps(load_all_templates(), indent=2))"
```

**Validate a template**:
```python
from pipeline.config_loader import load_template, validate_pipeline

config = load_template("full_stack_web")
result = validate_pipeline(config)
if result.errors:
    print("Errors:", result.errors)
if result.warnings:
    print("Warnings:", result.warnings)
```

## Schema Reference

```yaml
version: "1.0"                    # Schema version (currently "1.0")
name: "template_name"             # Identifier used in --template flag
description: "Human readable"     # Shown in UI
project_types:                    # List of project categories this template suits
  - "web"
  - "saas"

agents:                           # List of agents in execution order (or use depends_on)
  - agent: "pm"                   # Agent name (must match registered agent)
    enabled: true                 # Can be false to skip agent
    model: "claude-opus-4-5"      # Override default model (optional)
    task: "Prompt: {feature}"     # Override default task. {feature} will be substituted
    max_tokens: 8192              # Override token limit (optional)
    depends_on:                   # Additional dependencies beyond global deps
      - "some_other_agent"
    meta:                         # Custom metadata (ignored by system)
      priority: "high"

auto_resolve: true                # Auto-add missing deps from global deps? (default true)
strict_validation: false          # Fail on warnings? (default false)

settings:                         # Pipeline-level settings
  max_cost_usd: 5.0               # Global cost cap override
  timeout_minutes: 60             # Timeout override

metadata:                         # Any extra info for UI/documentation
  estimated_cost_usd: 2.50
  estimated_duration_minutes: 10
```

## Available Agents

| Agent | Role | Purpose |
|-------|------|---------|
| `pm` | Product Manager | Creates PRD, user stories, acceptance criteria |
| `ui_ux` | Product Designer | Component specs, design tokens, user flows |
| `frontend` | Frontend Engineer | React/TypeScript components, Vitest tests |
| `mobile` | Mobile Engineer | React Native/Expo screens |
| `backend` | Backend Engineer | FastAPI, SQLAlchemy, database models |
| `security` | Security Engineer | OWASP audit, SAST, threat modeling |
| `code_review` | Principal Engineer | Code quality, anti-patterns, best practices |
| `qa` | QA / SDET | pytest, Playwright, Locust tests |
| `devops` | DevOps Engineer | Docker, GitHub Actions, Terraform |
| `monetisation` | Growth Engineer | Stripe integration, billing, entitlements |

## Template Variables

The following placeholders are available in `task` prompts:

- `{feature}` - The feature description (from CLI `--feature`)
- `{project_id}` - The project ID (from CLI `--project`)

Example:
```yaml
task: "Build API for: {feature}"
# Renders as: "Build API for: User authentication"
```

## Dependencies

### Global Dependencies
Default agent dependencies are defined in `config/agent_deps.yaml`:

```yaml
dependencies:
  frontend: ["ui_ux"]       # Frontend needs UI/UX first
  backend: ["pm"]           # Backend needs PRD
  security: ["backend"]     # Security audits backend
  qa: ["backend", "code_review"]  # QA tests reviewed code
  # ... see full file
```

### Per-Agent Overrides
You can add or override dependencies in the template:

```yaml
agents:
  - agent: qa
    depends_on:
      - backend
      - code_review
      - security  # Additional dep not in global config
```

## Auto-Resolve

If `auto_resolve: true` (default), the pipeline builder will automatically enable agents that are required by dependencies but missing from the template.

**Example**: Your template lists only `[backend, qa]` but `agent_deps.yaml` says `qa` requires `code_review`. With `auto_resolve: true`, `code_review` will be automatically added at runtime.

**Best practice**: Set `auto_resolve: true` for full-featured templates (like `full_stack_web`) that should include all dependencies. Set `auto_resolve: false` for minimal/custom templates where you want explicit control.

## Creating Custom Templates

### Option 1: Copy and Modify
```bash
cp config/pipelines/mvp.yaml config/pipelines/my_template.yaml
# Edit my_template.yaml with your agents and settings
```

### Option 2: Write from Scratch
Follow the schema above. Keep YAML valid (use spaces, not tabs).

### Option 3: Save from UI (Phase 2)
The visual pipeline builder will have a "Save as Template" button that creates a YAML file.

## Validating Templates

Run validation before committing:

```python
from pipeline.config_loader import load_template, validate_pipeline

config = load_template("my_template")
result = validate_pipeline(config)

if result.errors:
    print("VALIDATION FAILED:")
    for err in result.errors:
        print(f"  - {err}")
    exit(1)

if result.warnings:
    print("WARNINGS:")
    for warn in result.warnings:
        print(f"  - {warn}")

print("✓ Template valid")
```

## Tips

1. **Order matters**: Agents are executed in topological order based on `depends_on`. If you want parallel execution, ensure dependencies allow it.
2. **Cost estimation**: Rough estimates use 2k input + 1k output tokens per agent. Real usage varies.
3. **Model selection**:
   - `claude-opus-4-5`: Complex reasoning, planning (PM, Security) - expensive ($15/$75 per 1M tokens)
   - `claude-sonnet-4-5`: Code generation, balanced ($3/$15 per 1M tokens)
4. **Skip agents**: Set `enabled: false` to exclude an agent without deleting config.
5. **Documentation**: Add extensive `description` fields; they show up in UI tooltips.

## Examples

### Minimal Backend API
```yaml
name: "simple_backend"
agents:
  - agent: backend
    task: "Build REST API for: {feature}"
  - agent: qa
    depends_on: ["backend"]
auto_resolve: true
```

### Security-Focused
```yaml
name: "secure_first"
agents:
  - agent: backend
  - agent: security
    depends_on: ["backend"]
  - agent: qa
    depends_on: ["backend"]
auto_resolve: false  # Be explicit about deps
```

## Troubleshooting

**"Unknown agent" error**:
- Check spelling against the agent roster in README.md
- Did you forget to register the agent with `@register_agent`?

**"Circular dependency" error**:
- Review `depends_on` fields. Ensure no agent A → B → C → A cycle.
- Consider if you really need that dependency or if it can be removed.

**Template not found**:
- File must be in `config/pipelines/` or subdirectory
- Template name is the key in YAML `name:` field, not filename
- Run `python -c "from pipeline.config_loader import load_all_templates; print([t['name'] for t in load_all_templates()])"` to see available

## Contributing

Found a great template configuration? Consider contributing it to the built-in templates!

1. Test it thoroughly: `pytest tests/pipeline/`
2. Add `estimated_cost_usd` and `estimated_duration_minutes` based on actual runs
3. Submit PR with `config/pipelines/your_template.yaml` and update this README

---

*See also: `docs/IMPLEMENTATION_PLAN_CONFIGURABLE_AGENTS.md` for the full roadmap.*
