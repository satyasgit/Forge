# Configurable Agent System - Implementation Plan

**Created**: 2026-04-04
**Last Updated**: 2026-04-04
**Status**: In Progress - Phase 1 (Not Started)
**Owner**: AI Agent Org Team

---

## 📋 Executive Summary

Transform the current hardcoded pipeline into a flexible, configurable system where users can:
- Select which agents to run for a given project
- Choose from predefined templates based on project type
- Customize agent configurations (model, task prompt, cost limits)
- Visualize the execution pipeline before running
- Save and share custom pipeline configurations

**Primary Goal**: Make the agent system adaptable to different project needs while maintaining ease of use.

**Market Research**: This plan incorporates patterns from LangGraph, CrewAI, Dify, Haystack, and other leading multi-agent frameworks. See `docs/RESEARCH_MULTI_AGENT_PATTERNS.md` for detailed analysis.

---

## 1. Current State Analysis

### What We Have
- **10 specialist agents**: pm, ui_ux, frontend, mobile, backend, security, code_review, qa, devops, monetisation
- **Hardcoded pipeline**: `make_full_app_pipeline()` runs ALL agents in fixed order with predefined dependencies
- **Dependency-based orchestration**: Already supports parallel execution based on `depends_on`
- **Pre-scanner pattern**: Each agent has local (free) pre-scanners before Claude API call
- **Agent registry**: `@register_agent` decorator + `create_agent()` factory

### Pain Points
- ❌ No flexibility: Must run all 10 agents even if you only need 3
- ❌ No project-type optimization: Mobile app still runs UI/UX, Web app runs Mobile agent
- ❌ No customization: Can't adjust agent prompts or model selection per project
- ❌ No templates: Every project is "full pipeline"
- ❌ CLI/API only: No visual understanding of what will run

---

## 2. Design Goals

### Must-Have (MVP)
1. **Agent selection**: Choose which agents to include
2. **Template system**: Pre-defined pipelines for common scenarios
3. **Dependency resolution**: Auto-calculate execution order
4. **Backward compatibility**: Existing `run_full_pipeline()` continues to work
5. **API endpoints**: New `/api/pipelines/*` routes for template management

### Nice-to-Have (Phase 2)
6. **Web UI**: Visual pipeline builder with agent toggles
7. **Per-agent configuration**: Override model, task prompt, cost limits
8. **Pipeline visualization**: DAG graph showing execution flow
9. **Save custom templates**: User-defined templates persisted to disk/database
10. **Cost/duration estimation**: Real-time preview before execution

### Future (Phase 3)
11. **Project type detection**: Auto-suggest templates based on codebase analysis
12. **Pipeline history & analytics**: Track success rates, costs per template
13. **Team templates**: Shared templates across organization
14. **Conditional execution**: "Run security only if backend changed"
15. **Agent composition**: "Run qa agent twice with different focus"

---

## 3. Solution Options Considered

[Original options analysis kept for context...]

---

## 4. Recommended Hybrid Architecture

[Architecture diagram and explanation...]

---

## 5. Implementation Plan (Phased)

### **Guiding Principle**: Incremental & Recoverable
- All artifacts stored in repository as files
- Each phase builds on previous, can resume after interruption
- No work-in-progress in memory only - commit frequently
- Backward compatibility maintained throughout

---

### **Phase 1: Core Config System** (Week 1-2)
**Status**: Not Started | **Files to create**: 8-9
**Goal**: Make pipeline construction data-driven using YAML (Haystack-inspired)

**Tasks**:
1. Create `pipeline/config_loader.py`:
   - `load_pipeline_from_yaml(path) -> PipelineConfig`
   - `load_pipeline_from_dict(data) -> PipelineConfig`
   - `validate_pipeline(config) -> ValidationResult`
   - **Store artifact**: `pipeline/config_loader.py`

2. Create `pipeline/models.py` (or inline in config_loader):
   - Pydantic models: `PipelineConfig`, `AgentTaskConfig`, `Edge`
   - **Store artifact**: `pipeline/models.py`

3. Create `config/pipelines/templates.yaml`:
   - Define 4 initial templates:
     - `full_stack_web` (all agents)
     - `mvp` (minimal: pm, frontend, backend, qa)
     - `api_only` (backend + security + qa + devops)
     - `security_audit_only` (security + code_review + qa)
   - Use Haystack-style YAML format (see Appendix)
   - **Store artifact**: `config/pipelines/templates.yaml`

4. Create `config/pipelines/README.md`:
   - Document template schema (version, name, agents, edges, auto_resolve)
   - Example templates with explanations
   - Template variables: `{feature}`, `{project_id}`
   - **Store artifact**: `config/pipelines/README.md`

5. Create `config/agent_deps.yaml`:
   - Centralized dependency metadata
   ```yaml
   dependencies:
     frontend: ["ui_ux"]
     backend: ["pm"]
     security: ["backend"]
     code_review: ["frontend", "backend"]
     qa: ["backend", "code_review"]
     devops: ["backend", "security"]
     monetisation: ["backend", "pm"]
     mobile: ["ui_ux"]
   ```
   - **Store artifact**: `config/agent_deps.yaml`

6. Refactor `pipeline/orchestrator.py`:
   - Rename `make_full_app_pipeline()` → `build_from_config(config: PipelineConfig) -> list[PipelineTask]`
   - Keep `make_full_app_pipeline()` as wrapper for backward compat
   - Add `resolve_dependencies(agent_names: list[str], deps: dict) -> list[PipelineTask]`
   - Load `agent_deps.yaml` on init
   - **Store artifact**: Modified `pipeline/orchestrator.py`

7. Update `orchestrator.run_full_pipeline()`:
   - Accept optional `config: PipelineConfig | None = None` param
   - If config provided: `tasks = self.build_from_config(config)`
   - Else: `tasks = self.make_full_app_pipeline()` (backward compat)
   - **Store artifact**: Further modified `pipeline/orchestrator.py`

8. Create tests for Phase 1:
   - `tests/pipeline/test_config_loader.py` - Test YAML loading, validation
   - `tests/pipeline/test_dependency_resolution.py` - Test topological sort, circular dep detection
   - **Store artifacts**: Test files

9. Update `README.md`:
   - Add section: "Custom Pipelines with YAML"
   - Document `--template` flag (if CLI exists) or new API
   - Show example: `python -m pipeline run --template api_only --feature "User API"`
   - **Store artifact**: Modified `README.md`

**Deliverable**: Can define and run pipelines via YAML config
```bash
# Example usage
python -m pipeline run --config config/pipelines/templates.yaml --template api_only --feature "User API"
```

**Checkpoint**: Create `docs/PHASE1_COMPLETE.md` when all 9 tasks done. Include:
- All files created and committed
- Tests passing (`pytest tests/pipeline/ -v`)
- Example pipeline run successful
- Backward compatibility verified (existing `run_full_pipeline()` still works)

---

### **Phase 2: API + Visual UI** (Week 3-4) 🚀 ACCELERATED
**Status**: Not Started | **Files to create**: 15-20
**Why accelerated**: Market research (Dify) proves visual builder is 10x adoption driver.

#### Part A: Backend API

**Tasks**:
1. Create `api/pipelines_schemas.py`:
   - Pydantic models: `PipelineConfigAPI`, `AgentConfigAPI`, `PipelinePreview`, `PipelineRunResponse`
   - **Store artifact**: `api/pipelines_schemas.py`

2. Update `api/main.py`:
   - Add router: `api.include_router(pipelines_router)`
   - Or add directly to main.py:
     ```python
     @app.get("/api/pipelines/templates")
     async def list_templates():
         return load_all_templates()

     @app.get("/api/pipelines/templates/{name}")
     async def get_template(name: str):
         return load_template(name)

     @app.post("/api/pipelines/validate")
     async def validate_pipeline(config: PipelineConfigAPI):
         return validate_pipeline(config)

     @app.post("/api/pipelines/preview")
     async def preview_pipeline(config: PipelineConfigAPI):
         tasks = build_from_config(config)
         return {
             "agents": [t.name for t in tasks],
             "estimated_cost": estimate_cost(tasks),
             "estimated_duration_minutes": estimate_duration(tasks),
             "dag": build_dag_dict(tasks),
             "validation": validate_pipeline(config)
         }

     @app.post("/api/pipelines/run")
     async def run_custom_pipeline(
         config: PipelineConfigAPI,
         feature: str,
         project_id: str
     ):
         tasks = build_from_config(config)
         # Substitute template variables
         for t in tasks:
             if t.task:
                 t.task = t.task.format(feature=feature, project_id=project_id)
         orch = Orchestrator(project_id)
         result = await orch.run(tasks)
         return result.to_dict()
     ```
   - **Store artifact**: Updated `api/main.py`

3. Create `tests/api/test_pipelines.py`:
   - Test all 5 endpoints
   - Mock orchestrator for run tests
   - **Store artifact**: `tests/api/test_pipelines.py`

4. (Optional) Create `docs/api-pipelines.yaml`:
   - Export OpenAPI/Swagger spec
   - **Store artifact**: `docs/api-pipelines.yaml`

**Checkpoint**: API endpoints working, tested, documented

---

#### Part B: Frontend Visual Builder (React + React Flow)

**Decision**: Integrate into existing `dashboard/src/` if present, else create standalone `pipeline-ui/`

**Tasks**:
1. Setup:
   - If `dashboard/` exists: `cd dashboard && npm install reactflow zustand @tanstack/react-query`
   - Else: `mkdir pipeline-ui && cd pipeline-ui && npm init -y && npm install react react-dom reactflow zustand @tanstack/react-query vite @vitejs/plugin-react`
   - Create `pipeline-ui/package.json`, `vite.config.ts`, `tsconfig.json`

2. Create directory structure:
   ```
   pipeline-ui/src/
     components/
       ProjectTypeSelector.tsx
       TemplatePicker.tsx
       AgentPalette.tsx
       PipelineCanvas.tsx
       PropertiesPanel.tsx
       ValidationPanel.tsx
       PipelinePreview.tsx
       NodeTypes.tsx
     hooks/
       usePipelineState.ts
       useTemplates.ts
       usePipelineApi.ts
     pages/
       PipelineBuilder.tsx
     styles/
       pipelines.css
     __tests__/
       PipelineCanvas.test.tsx
     types/
       index.ts
     utils/
       dagHelpers.ts
       costEstimator.ts
   ```

3. Create `types/index.ts`:
   - TypeScript interfaces: `PipelineState`, `AgentNode`, `PipelineTemplate`, etc.
   - **Store artifact**: `pipeline-ui/src/types/index.ts`

4. Create `hooks/usePipelineState.ts`:
   - Zustand store with state: nodes, edges, selectedAgent, validation
   - Actions: addNode, removeNode, updateNode, validatePipeline
   - **Store artifact**: `pipeline-ui/src/hooks/usePipelineState.ts`

5. Create `hooks/useTemplates.ts`:
   - Fetch templates from `/api/pipelines/templates`
   - Select template, apply to canvas
   - **Store artifact**: `pipeline-ui/src/hooks/useTemplates.ts`

6. Create `hooks/usePipelineApi.ts`:
   - `runPipeline(config)` → POST to `/api/pipelines/run`
   - `previewPipeline(config)` → POST to `/api/pipelines/preview`
   - `validatePipeline(config)` → POST to `/api/pipelines/validate`
   - **Store artifact**: `pipeline-ui/src/hooks/usePipelineApi.ts`

7. Create `components/NodeTypes.tsx`:
   - Custom React Flow node: `AgentNode` (with toggle, icon, status)
   - Different node colors per agent type (frontend=blue, security=red, etc.)
   - **Store artifact**: `pipeline-ui/src/components/NodeTypes.tsx`

8. Create `components/AgentPalette.tsx`:
   - Draggable list of all available agents (from `/api/agents`)
   - Each item has agent icon, name, role
   - On drag start: set data transfer with agent name
   - **Store artifact**: `pipeline-ui/src/components/AgentPalette.tsx`

9. Create `components/PipelineCanvas.tsx`:
   - React Flow canvas with:
     - `onDrop` handler: create agent node from palette
     - `onConnect` handler: create edge (with optional condition)
     - `nodeTypes` custom nodes
     - `onNodeClick` → update selectedAgent in store
     - `onEdgeClick` → edit edge condition
   - **Store artifact**: `pipeline-ui/src/components/PipelineCanvas.tsx`

10. Create `components/ProjectTypeSelector.tsx`:
    - Radio card grid: Web, Mobile, API, SaaS, Security Audit, Custom
    - On select: filter templates by `project_types`, update store
    - **Store artifact**: `pipeline-ui/src/components/ProjectTypeSelector.tsx`

11. Create `components/TemplatePicker.tsx`:
    - Grid of template cards (from API)
    - Each card: name, description, agent count, estimated cost, duration
    - Click: "Apply" → load template into canvas
    - **Store artifact**: `pipeline-ui/src/components/TemplatePicker.tsx`

12. Create `components/PropertiesPanel.tsx`:
    - Shows when node selected
    - Fields: Enabled toggle, Model select (Opus/Sonnet/Haiku), Task textarea, Cost limit
    - Save: update node in store
    - **Store artifact**: `pipeline-ui/src/components/PropertiesPanel.tsx`

13. Create `components/ValidationPanel.tsx`:
    - Shows validation errors/warnings from store
    - Real-time updates as user edits
    - Missing dependency: "Security needs Backend - add it?"
    - **Store artifact**: `pipeline-ui/src/components/ValidationPanel.tsx`

14. Create `components/PipelinePreview.tsx`:
    - Summary: "7 agents, ~$2.30, 8-12 minutes"
    - "Save as Template" button
    - "Run Pipeline" button (triggers API, shows progress)
    - **Store artifact**: `pipeline-ui/src/components/PipelinePreview.tsx`

15. Create main page `pages/PipelineBuilder.tsx`:
    - Layout: left sidebar (palette), center (canvas), right (properties)
    - Integrate all components
    - Fetch templates on mount
    - **Store artifact**: `pipeline-ui/src/pages/PipelineBuilder.tsx`

16. Create `pipeline-ui/src/index.tsx` and `App.tsx`:
    - Main app wrapper with QueryClientProvider
    - **Store artifacts**: `index.tsx`, `App.tsx`

17. Create `pipeline-ui/index.html` and `vite.config.ts` (if standalone):
    - **Store artifacts**: `index.html`, `vite.config.ts`

18. Styles:
    - `pipeline-ui/src/styles/pipelines.css` - Custom styles
    - Or use Tailwind classes throughout
    - **Store artifact**: CSS file

19. Tests:
    - `pipeline-ui/src/__tests__/PipelineCanvas.test.tsx` - Test node/edge operations
    - `pipeline-ui/src/__tests__/usePipelineState.test.ts` - Test Zustand store
    - **Store artifacts**: Test files

20. README for UI:
    - `pipeline-ui/README.md` - How to run, develop
    - **Store artifact**: `pipeline-ui/README.md`

**Deliverable**: Functional web UI where users can:
- Select project type → see filtered templates
- Pick template OR build custom via drag-drop
- Toggle agents, configure per-agent settings in right panel
- See real-time cost estimate and validation warnings
- Click "Run" → see execution progress (polling `/api/pipelines/run`)
- Save custom template to local

**Checkpoint**:
- UI runs on `http://localhost:3000`
- Can build a pipeline with 5 agents, run successfully
- Screenshot/GIF saved to `docs/ui-demo.gif`
- API integration documented in `docs/UI_API_INTEGRATION.md`

---

### **Phase 3: Advanced Orchestration** (Week 5-6)
**Status**: Not Started | **Files to create**: 4-6
**Goal**: Conditional routing (LangGraph-style), subgraphs, checkpoints, human approvals

**Tasks**:

1. **Conditional Edges**:
   - Create `pipeline/conditions.py`:
     - `evaluate_condition(condition_expr: str, context: dict) -> bool`
     - Support simple expressions: `"security.critical_count == 0"`, `"backend.success == true"`
     - Use `asteval` or write simple parser (avoid eval security risk)
   - Update `pipeline/models.py`: Add `Edge.condition: str | None`
   - Update `pipeline/orchestrator.py`: After agent completes, check outgoing edges, evaluate conditions to determine next agent(s)
   - **Store artifacts**: `conditions.py`, updated models/orchestrator
   - Tests: `tests/pipeline/test_conditions.py`

2. **Subgraph Composition**:
   - Create `pipeline/subgraph.py`:
     - `SubgraphNode` that references another pipeline YAML file
     - Load subgraph, inline its tasks into parent task list
     - Treat subgraph as single logical unit (but executes inner agents)
   - Update `pipeline/models.py`: Add `AgentTaskConfig.type: "agent" | "subgraph"`
   - Update `pipeline/config_loader.py`: Load subgraph references
   - **Store artifacts**: `subgraph.py`, updated config loader
   - Tests: `tests/pipeline/test_subgraphs.py` - nested pipeline execution

3. **Checkpoint & Resume**:
   - Create `pipeline/checkpoint.py`:
     - `save_checkpoint(run_id: str, completed_agents: list[str], state: dict)`
     - `load_checkpoint(run_id: str) -> PipelineCheckpoint | None`
     - Store in `ProjectMemory` (new table `pipeline_checkpoints`)
   - Update `pipeline/orchestrator.py`:
     - After each agent completes: `checkpoint.save(agent_name, context)`
     - On start: if `--resume-from` flag, load checkpoint, skip already-done agents
     - On failure: prompt "Resume from X?" (CLI) or UI button
   - **Store artifacts**: `checkpoint.py`, updated orchestrator, memory schema
   - Tests: `tests/pipeline/test_checkpoint.py`

4. **Human Approval Nodes**:
   - Create `agents/approval_agent.py`:
     ```python
     class ApprovalAgent(BaseAgent):
         name = "human_approval"
         system_prompt = "You are a gatekeeper. Wait for human approval."
         def run(self, task, context):
             # Send notification (Slack/email if configured)
             # Save to ProjectMemory: awaiting_approval[run_id] = {task, context}
             # Return state = AWAITING_APPROVAL, output = "Waiting for approval"
     ```
   - UI component: `components/ApprovalModal.tsx` - Shows task, context, Approve/Reject buttons
   - Backend: `POST /api/approvals/{run_id}/approve` and `/reject`
   - **Store artifacts**: `agents/approval_agent.py`, approval modal, API endpoints
   - Tests: `tests/agents/test_approval_agent.py`

5. **Enhanced Agent Metadata**:
   - Update `agents/agent_config.py`:
     - Add optional metadata fields to `@register_agent`: `dependencies`, `recommended_for`, `conflicts_with`
   - Update 3-4 agents as examples:
     - `agents/security_agent.py`: add `dependencies = ["backend"]`, `recommended_for = ["web", "saas", "api"]`
     - `agents/mobile_agent.py`: add `dependencies = ["ui_ux"]`, `recommended_for = ["mobile"]`
     - `agents/frontend_agent.py`: similar
   - Use metadata in template suggestions (future)
   - **Store artifacts**: Updated `agent_config.py`, 3 agent classes

6. **Documentation**:
   - Create `docs/advanced-orchestration.md`:
     - Conditional edges: syntax, examples
     - Subgraphs: how to compose
     - Checkpoints: resume after failure
     - Human approvals: setup, usage
   - **Store artifact**: `docs/advanced-orchestration.md`

**Deliverable**: Smart pipelines with conditional logic, subgraph nesting, checkpoint resume, human approvals

**Checkpoint**:
- Demo video (2 min) showing:
  1. Pipeline with conditional edge (if security finds critical → run extra scan)
  2. Subgraph (security_audit subgraph nested in full pipeline)
  3. Checkpoint: kill process, resume from last agent
  4. Human approval: pipeline pauses, Slack notification, approve in UI
- Save demo to `docs/demos/phase3-demo.gif` or video link

---

### **Phase 4: Polish + Marketplace** (Week 7-8)
**Status**: Not Started | **Files to create**: 8-10
**Goal**: Production-ready with community features and full documentation

**Tasks**:

1. **Template Persistence**:
   - Create `pipeline/template_store.py`:
     - `list_templates()` - scan `config/pipelines/builtin/`, `config/pipelines/user/`, `~/.aiagent/pipelines/`
     - `save_template(name, config, user=True)` - save to user dir or project `.aiagent.yaml`
     - `load_template(name)` - union of all sources, later overrides earlier
   - Update config loader to use template store
   - Add CLI: `aiagent template list`, `aiagent template save <name>`, `aiagent template install <path-or-url>`
   - **Store artifacts**: `template_store.py`, CLI updates

2. **Pipeline History**:
   - Extend `memory/store.py`:
     - New table: `pipeline_runs` (run_id, config_hash, start_time, end_time, status, cost, duration, agents_used)
     - New table: `agent_outputs` (agent_name, run_id, output_summary, artifact_paths)
   - Create `memory/pipeline_history.py`:
     - `save_run(run_id, result, config)`
     - `list_runs(project_id, limit=20)`
     - `get_run(run_id)` - full details
     - `compare_runs(run_id1, run_id2)` - diff cost, duration, outputs
   - UI: Add "History" tab in pipeline builder, show past runs, "Rerun" button
   - CLI: `aiagent history`, `aiagent history rerun <run_id>`
   - **Store artifacts**: Extended memory schema, `pipeline_history.py`, UI history tab

3. **Cost Optimization Wizard**:
   - Create `pipeline/optimizer.py`:
     - `optimize_for_cost(config: PipelineConfig, target_cost: float) -> PipelineConfig`
       - Algorithm:
         1. Replace Opus agents with Sonnet (unless critical)
         2. Disable expensive non-critical agents (monetisation, mobile?)
         3. Reduce max_tokens for agents
         4. If still over budget, suggest removing lowest-priority agents
     - `optimize_for_speed(config) -> PipelineConfig`
       - Increase parallel agents (adjust dependencies)
       - Use faster models (Haiku for simple tasks)
     - Returns optimized config + suggestions (what changed)
   - UI: "Optimize" button with options: "Cheaper (-30%)", "Faster (-40% time)", "Production-ready (add security)"
     - Dialog: "This will change X, Y, Z. Apply?"
   - **Store artifacts**: `optimizer.py`, UI optimization modal

4. **Template Registry / Community Features**:
   - Create `pipeline/template_registry.py`:
     - `list_community_templates()` - fetch from GitHub repo/URL or local index
     - `install_template(name, source)` - download and save to `~/.aiagent/pipelines/`
     - `rate_template(name, rating)` - save rating locally
     - `template_metadata(name)` - returns: author, downloads, rating, tags
   - CLI: `aiagent templates search <query>`, `aiagent templates install <name>`
   - UI: "Community Templates" tab in TemplatePicker
   - **Store artifacts**: `template_registry.py`, CLI commands, UI integration

5. **CLI Enhancement** (if not done earlier):
   - Create `pipeline/cli.py` (or update existing):
     ```bash
     aiagent pipeline run --template api_only --feature "User auth"
     aiagent pipeline validate config.yaml
     aiagent pipeline preview config.yaml
     aiagent pipeline templates list
     aiagent pipeline templates save my_template
     aiagent history
     aiagent history rerun <run_id>
     ```
   - **Store artifact**: `pipeline/cli.py`

6. **Documentation** (Critical):
   - `docs/pipeline-builder.md` - Complete user guide:
     - Quickstart: Build your first pipeline in 5 min
     - Template authoring guide
     - Cost optimization wizard
     - Conditional routing examples
     - Debugging pipeline failures
   - `docs/template-authoring.md` - Reference:
     - YAML schema reference
     - Best practices for templates
     - Sharing templates
   - `docs/tutorial-video.md` - Script for 5-minute tutorial video
   - Update `README.md` - Add "New Configurable Pipeline System" section with quick links
   - Create `docs/GETTING_STARTED.md` - For new users (step-by-step, screenshots)
   - **Store artifacts**: 3-4 markdown files

7. **Beta Testing**:
   - Recruit 2-3 users (friends, colleagues)
   - Provide `FEEDBACK.md` template
   - Collect feedback on:
     - Ease of use (1-10)
     - Missing features
     - Confusions/bugs
     - Template suggestions
   - Iterate based on feedback
   - **Store artifact**: `FEEDBACK.md` (with template), summary of changes based on feedback

8. **Production Polish**:
   - Error handling: Better error messages when agent missing, YAML syntax error
   - Logging: Structured logs for pipeline runs (JSON, for debugging)
   - Monitoring: Emit metrics (pipeline_success_rate, agent_duration_avg)
   - Performance: Cache template loading, dependency resolution
   - **Store artifacts**: Various small fixes

**Deliverable**: Production-ready configurable agent system with:
- Visual builder (React UI)
- Multiple template sources (builtin, user, project, community)
- Advanced orchestration (conditionals, subgraphs, checkpoints, approvals)
- Full documentation and examples
- Beta-tested and refined

**Checkpoint**:
- All Phase 1-4 features working
- Documentation complete (no "TODO" in docs)
- Beta feedback incorporated
- Ready for `v1.0.0` release tag

---

## 6. Technical Decisions (Post-Research)

### **Configuration Format**: YAML (Haystack-inspired)
```yaml
version: "1.0"
name: "full_stack_web"
description: "Complete web application"
project_types: ["web", "saas"]

agents:
  pm:
    enabled: true
    model: "opus"
    task: "Create detailed PRD for: {feature}"
    max_tokens: 8192

  backend:
    enabled: true
    depends_on: ["pm"]  # Optional: override global deps
    model: "sonnet"

  security:
    enabled: true
    depends_on: ["backend"]

auto_resolve: true  # Auto-add missing deps? (default from template)
strict_validation: false  # Fail on warnings?

settings:
  max_cost_usd: 5.0
  timeout_minutes: 30
```

**Why YAML**: Human-editable, supports comments, widely supported (Haystack, CrewAI)

---

### **Dependency Resolution**
- **Global deps**: `config/agent_deps.yaml` (centralized, editable without code)
- **Per-agent override**: `depends_on` in template can add/remove deps
- **Auto-resolve**: Controlled by `auto_resolve` flag in template
- **Validation**: Circular dependency check (topological sort validation)
- **Algorithm**: Kahn's algorithm for topological sort (standard)

---

### **Agent Metadata Enhancement** (Phased)
```python
@register_agent
class SecurityAgent(BaseAgent):
    name = "security"
    role = "Application Security Engineer"
    goal = "Find and fix security vulnerabilities"  # Phase 3+
    backstory = "15 years in appsec..."  # Phase 3+
    dependencies = ["backend"]  # Phase 1: central, Phase 3+: move here
    recommended_for = ["web", "saas", "api"]  # Phase 3+
    conflicts_with = ["monetisation"]  # Phase 3+ (warning only)
```

Phasing:
- Phase 1: Use `config/agent_deps.yaml` (centralized)
- Phase 3: Add optional `dependencies` to agent class, migrate 3-4 agents
- Phase 4: Allow templates to use agent metadata for suggestions

---

### **State Management for UI** (Phase 2)
- **Zustand** store: `usePipelineStore` (lightweight, simple)
- **React Query**: For API caching (templates, runs)
- State shape:
```typescript
{
  projectType: 'web' | 'mobile' | 'api' | 'custom',
  template: null | { name: string; config: PipelineConfig },
  nodes: PipelineNode[],  // React Flow nodes {id, type, data: {agentName, config}}
  edges: Edge[],          // {id, source, target, condition?}
  selectedNode: string | null,
  validation: { errors: ValidationError[], warnings: ValidationWarning[] },
  costEstimate: { cost: number; durationMinutes: number },
  isDirty: boolean,
  execution: { status: 'idle' | 'running' | 'completed' | 'failed'; currentAgent?: string }
}
```

---

### **API Response Format** (Standardized)
```json
{
  "success": true,
  "data": { ... },
  "errors": [],
  "warnings": ["qa agent recommends code_review - auto-adding"],
  "metadata": {
    "estimated_cost": 2.34,
    "estimated_duration_minutes": 8.5,
    "agent_count": 7
  }
}
```

---

## 7. Decisions Made (2026-04-04)

### **Auto-dependencies**: Configurable per template ✅
- Templates set `auto_resolve: true/false`
- Full_stack templates: `auto_resolve=true` (ensure dependencies met)
- Custom templates: `auto_resolve=false` (strict validation)
- CLI flag: `--skip-dep-check` overrides

---

### **Agent conflicts**: Warn only, allow override ✅
- Show validation warning in UI/API
- Don't block execution (advanced users may have valid reasons)
- Example: `mobile` + `frontend` allowed (React Native + web)

---

### **Task overrides**: Yes, with template placeholders ✅
- Show default task as editable textarea
- Preserve `{feature}`, `{project_id}` placeholders
- Validate placeholder syntax before run

---

### **Configuration storage**: Start local → add project ✅
- Phase 1: Save user templates to `config/pipelines/user/` (git-ignored)
- Phase 4: Support `.aiagent.yaml` in project root (committed)
- Long-term: Database if dashboard adds user accounts

---

### **UI Location & Priority**: Existing dashboard, Phase 2 accelerated ✅
- Integrate into `dashboard/src/pipelines/` if exists
- **MOVED UP**: Build UI in Phase 2 (not Phase 3) based on Dify research
- Reason: Visual builder is 10x adoption driver
- CLI-only insufficient in 2025 market

---

### **Conditional routing**: Phase 3 ✅
- Phase 1-2: Static DAG via `depends_on`
- Phase 3: Add `condition` field to edges (LangGraph-inspired)
- Example: `if security.critical_count > 0 → security_expert`

---

## 8. Open Questions (Remaining)

1. **Template discovery**: Scan `config/pipelines/*.yaml` or hardcoded index?
   - **Recommendation**: Auto-scan `config/pipelines/builtin/` + `config/pipelines/user/` + `~/.aiagent/pipelines/`
   - No hardcoded list - just load all valid YAMLs

2. **Agent dependency metadata**: Central `config/agent_deps.yaml` or per-agent class?
   - **Current**: Central (Phase 1)
   - **Phase 3**: Add `dependencies` to agent class, deprecate central file gradually

3. **Pipeline failure handling**: Fail fast or continue partial execution?
   - **Recommendation**: Fail fast with clear error message + suggestion to add missing agents
   - Example: "QA requires code_review. Add it or use `--skip-missing-deps`"

---

## 9. Success Metrics

- **Adoption**: % of users using non-full pipelines (target: >40%)
- **Time saved**: Average pipeline duration reduction (target: -30% for selective runs)
- **Cost saved**: Average cost per run (target: -25% by skipping unnecessary agents)
- **User satisfaction**: Survey rating of pipeline builder (target: >4/5)
- **Templates**: Number of active templates (target: 10+ within 3 months)
- **UI adoption**: % of users using visual builder vs CLI (target: >70%)

---

## 10. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Templates become too complex | High | Start with 3-4 simple templates, add features gradually |
| Dependency graph incomplete | Medium | Central deps file, validation warns, allow override |
| UI complexity overwhelms users | Medium | Progressive disclosure: template picker → customize → advanced editor |
| Cost estimates inaccurate | Low | Show ranges (±20%), track actual vs estimate for calibration |
| Breaking changes to existing API | High | Maintain backward compat, deprecate slowly (keep `run_full_pipeline()`) |
| Token limits interrupt implementation | Medium | Store all work in repo, use `IMPLEMENTATION_STATUS.md` to track |
| React UI learning curve | Medium | Use proven patterns (React Flow), copy examples, keep simple |

---

## 11. Implementation Status Tracking

**CRITICAL**: Update after each work session. This enables recovery if tokens/session interrupted.

### Phase 1: Core Config System
- **Start Date**: TBD
- **Files Created**: 0/9
- **Tests**: 0/2 (passing)
- **Last Completed Task**: None
- **Blockers**: None
- **Notes**:
- **Checkpoint**: None

### Phase 2: API + Visual UI
- **Start Date**: TBD (after Phase 1 complete)
- **Files Created**: 0/15-20
- **Tests**: 0/1 (passing)
- **Last Completed Task**: None
- **Blockers**: Phase 1 incomplete? (list if any)
- **Notes**:
- **Checkpoint**: None

### Phase 3: Advanced Orchestration
- **Start Date**: TBD (after Phase 2 complete)
- **Files Created**: 0/4-6
- **Tests**: 0/2 (passing)
- **Last Completed Task**: None
- **Blockers**: Phase 2 incomplete?
- **Notes**:
- **Checkpoint**: None

### Phase 4: Polish + Marketplace
- **Start Date**: TBD (after Phase 3 complete)
- **Files Created**: 0/8-10
- **Last Completed Task**: None
- **Blockers**: Previous phases?
- **Notes**:
- **Checkpoint**: None

---

## 12. File Inventory (What We'll Create)

### Phase 1 Files:
```
pipeline/config_loader.py
pipeline/models.py
pipeline/dependency_resolver.py (or in orchestrator)
config/pipelines/templates.yaml
config/pipelines/README.md
config/agent_deps.yaml
tests/pipeline/test_config_loader.py
tests/pipeline/test_dependency_resolution.py
docs/PHASE1_COMPLETE.md
docs/IMPLEMENTATION_STATUS.md (this tracking file - create now)
```

### Phase 2 Files:
```
api/pipelines_schemas.py
api/routes/pipelines.py (or update main.py)
tests/api/test_pipelines.py
docs/api-pipelines.yaml

# UI (if dashboard exists):
dashboard/src/pipelines/components/*.tsx (7-8 files)
dashboard/src/pipelines/hooks/*.ts (3 files)
dashboard/src/pipelines/pages/*.tsx (1-2 files)
dashboard/src/pipelines/styles/*.css
dashboard/src/pipelines/types/index.ts
dashboard/src/pipelines/utils/*.ts
dashboard/src/pipelines/__tests__/*.test.tsx
dashboard/package.json (update)
dashboard/src/pipelines/README.md

# Or standalone:
pipeline-ui/package.json
pipeline-ui/vite.config.ts
pipeline-ui/tsconfig.json
pipeline-ui/index.html
pipeline-ui/src/ (all above structure)
pipeline-ui/README.md
```

### Phase 3 Files:
```
pipeline/conditions.py
pipeline/subgraph.py
pipeline/checkpoint.py
agents/approval_agent.py
docs/advanced-orchestration.md
tests/pipeline/test_conditions.py
tests/pipeline/test_subgraphs.py
tests/pipeline/test_checkpoint.py
tests/agents/test_approval_agent.py
docs/PHASE3_COMPLETE.md
```

### Phase 4 Files:
```
pipeline/template_store.py
memory/pipeline_history.py (extend ProjectMemory)
pipeline/optimizer.py
pipeline/template_registry.py
pipeline/cli.py (or update)
docs/pipeline-builder.md
docs/template-authoring.md
docs/tutorial-video.md
tests/pipeline/test_template_store.py
tests/pipeline/test_optimizer.py
FEEDBACK.md (template)
docs/PHASE4_COMPLETE.md
```

---

## 13. Recovery from Interruption

**If tokens run out or session interrupted**:

1. Open `docs/IMPLEMENTATION_STATUS.md` → Check "Last Completed Task" for each phase
2. Read this plan's relevant phase section (Section 5)
3. Continue from next unchecked `[ ]` task in the current phase
4. After completing task: update `IMPLEMENTATION_STATUS.md` with:
   - Files created
   - Tests added/passing
   - Checkpoint: brief note on what works

**No work lost principle**: All code is stored in repository files immediately after creation. Nothing remains only in conversation memory.

**To resume workflow**:
```bash
# 1. Check status
cat docs/IMPLEMENTATION_STATUS.md

# 2. Find next task (look for unchecked [ ] in current phase)
# 3. Implement it following this plan
# 4. Commit changes with message: "feat(configurable-agents): [task description]"
# 5. Update IMPLEMENTATION_STATUS.md with completion note
```

**If stuck**: Reread this implementation plan, check research doc `docs/RESEARCH_MULTI_AGENT_PATTERNS.md`, review market leader patterns.

---

## 14. Related Documentation

- Existing: `README.md` (agent roster, quick start)
- Existing: `agents/agent_config.py` (per-agent configuration)
- Existing: `pipeline/orchestrator.py` (current pipeline logic)
- Research: `docs/RESEARCH_MULTI_AGENT_PATTERNS.md` (market analysis)
- This: `docs/IMPLEMENTATION_PLAN_CONFIGURABLE_AGENTS.md` (current plan)
- To Create: `config/pipelines/README.md` (template authoring)
- To Create: `docs/pipeline-builder.md` (user guide for visual UI)
- To Create: `docs/template-authoring.md` (detailed template reference)
- To Create: `docs/advanced-orchestration.md` (conditionals, subgraphs, checkpoints)

---

## 15. Appendix: Example Templates

### Template: `full_stack_web.yaml`
```yaml
version: "1.0"
name: "full_stack_web"
description: "Complete web application with all specialist agents"
project_types: ["web", "saas"]

agents:
  - agent: pm
    enabled: true
    model: "opus"
    task: "Create a comprehensive PRD with user stories and acceptance criteria for: {feature}"
    max_tokens: 8192

  - agent: ui_ux
    enabled: true
    model: "sonnet"
    task: "Design the complete UI/UX including component specs and design tokens for: {feature}"

  - agent: frontend
    enabled: true
    model: "sonnet"
    task: "Build React/TypeScript components with Vitest tests for: {feature}"
    depends_on: ["ui_ux"]

  - agent: backend
    enabled: true
    model: "sonnet"
    task: "Build FastAPI backend with SQLAlchemy models for: {feature}"
    depends_on: ["pm"]

  - agent: security
    enabled: true
    model: "opus"
    task: "Perform full OWASP Top 10 security audit of the backend API"

  - agent: code_review
    enabled: true
    model: "sonnet"
    task: "Review frontend and backend code for best practices and anti-patterns"
    depends_on: ["frontend", "backend"]

  - agent: qa
    enabled: true
    model: "sonnet"
    task: "Write comprehensive pytest + Playwright test suite for: {feature}"
    depends_on: ["backend", "code_review"]

  - agent: devops
    enabled: true
    model: "sonnet"
    task: "Create Docker configuration and GitHub Actions CI/CD pipeline"
    depends_on: ["backend", "security"]

  - agent: monetisation
    enabled: true
    model: "sonnet"
    task: "Design monetisation strategy with Stripe integration"
    depends_on: ["backend", "pm"]

auto_resolve: true
strict_validation: false

settings:
  max_cost_usd: 10.0
  timeout_minutes: 120
```

---

### Template: `api_only.yaml`
```yaml
version: "1.0"
name: "api_only"
description: "Backend API with security and tests (no UI)"
project_types: ["api", "saas", "backend", "microservice"]

agents:
  - agent: pm
    enabled: true
    model: "opus"
    task: "Create API specification with OpenAPI/Swagger for: {feature}"

  - agent: backend
    enabled: true
    model: "sonnet"
    task: "Build production-ready FastAPI backend with pydantic models, SQLAlchemy, and Alembic migrations for: {feature}"

  - agent: security
    enabled: true
    model: "opus"
    task: "Comprehensive security audit: OWASP Top 10, SAST, dependency scanning, JWT validation"

  - agent: code_review
    enabled: true
    model: "sonnet"
    task: "Code review focused on API design, error handling, and performance"

  - agent: qa
    enabled: true
    model: "sonnet"
    task: "Write pytest suite with FastAPI TestClient, test all endpoints, auth, and edge cases"

  - agent: devops
    enabled: true
    model: "sonnet"
    task: "Dockerize with multi-stage build, configure GitHub Actions for CI/CD, add health checks"

auto_resolve: true
strict_validation: false

settings:
  max_cost_usd: 5.0
  timeout_minutes: 60
```

---

### Template: `security_audit_only.yaml`
```yaml
version: "1.0"
name: "security_audit_only"
description: "Deep security review of existing codebase (requires code files)"
project_types: ["security", "audit", "compliance", "penetration-test"]

agents:
  - agent: security
    enabled: true
    model: "opus"
    task: |
      Perform comprehensive security audit including:
      - OWASP Top 10 (2021) analysis
      - SAST pattern matching (SQLi, XSS, path traversal, SSRF)
      - Secret/credential leak detection
      - JWT and authentication flow review
      - Infrastructure-as-code security (Docker, GitHub Actions, Terraform)
      Provide remediation recommendations with code examples

  - agent: code_review
    enabled: true
    model: "opus"
    task: "Deep code review focusing on security anti-patterns, input validation, and secure coding practices"

  - agent: qa
    enabled: true
    model: "sonnet"
    task: "Write security-focused tests: auth bypass attempts, injection attacks, privilege escalation scenarios"

auto_resolve: false  # User must ensure code files exist
strict_validation: true

settings:
  max_cost_usd: 3.0
  timeout_minutes: 45
```

---

### Template: `mvp.yaml`
```yaml
version: "1.0"
name: "mvp"
description: "Minimum Viable Product - fast and cost-effective"
project_types: ["web", "mobile", "saas", "startup"]

agents:
  - agent: pm
    enabled: true
    model: "opus"
    task: "Create lean PRD with core features only for: {feature}"

  - agent: ui_ux  # Optional - if skipped, frontend uses basic UI
    enabled: false  # Skip UI/UX to save time/cost
    model: "sonnet"

  - agent: frontend
    enabled: true
    model: "sonnet"
    task: "Build basic but functional React components for core user flows"
    depends_on: ["pm"]  # Will also depend on ui_ux if enabled

  - agent: backend
    enabled: true
    model: "sonnet"
    task: "Build minimal FastAPI backend with essential endpoints and basic auth"
    depends_on: ["pm"]

  - agent: code_review
    enabled: false  # Skip to save time, accept risk
    model: "sonnet"

  - agent: qa
    enabled: true
    model: "sonnet"
    task: "Critical path tests only - happy path and main error scenarios"
    depends_on: ["backend"]

  - agent: devops
    enabled: false  # Manual deployment for MVP
    model: "sonnet"

auto_resolve: true
strict_validation: false

settings:
  max_cost_usd: 2.0
  timeout_minutes: 30
```

---

### Personal Template: `my_web_app.yaml` (User-created)
```yaml
version: "1.0"
name: "my_web_app"
description: "My custom web app template"
project_types: ["web"]

agents:
  - agent: pm
    enabled: true
    task: "PRD for: {feature}"

  - agent: backend
    enabled: true
    task: "FastAPI backend with PostgreSQL"
    depends_on: ["pm"]

  - agent: frontend
    enabled: true
    task: "React + TypeScript with shadcn/ui components"
    depends_on: ["pm"]

# Skip security and monetisation for now
auto_resolve: true
strict_validation: false

settings:
  max_cost_usd: 3.0
  timeout_minutes: 45
```

---

## 16. Change Log

| Date | Version | Changes |
|------|---------|---------|
| 2026-04-04 | 0.2 | Updated with market research; UI moved to Phase 2 (was Phase 3); conditional routing Phase 3; added file inventory; added status tracking; prioritized visual builder |
| 2026-04-04 | 0.1 | Initial draft created |

---

**Next Steps**:
1. Create `docs/IMPLEMENTATION_STATUS.md` (start tracking now)
2. Begin Phase 1, Task 1: `pipeline/config_loader.py`
3. Commit each file immediately after creation
4. Update `IMPLEMENTATION_STATUS.md` after each task

**Remember**: Build incrementally, store everything in repo, never keep work only in conversation. No work lost.

---

**Implementation Ready** 🚀
