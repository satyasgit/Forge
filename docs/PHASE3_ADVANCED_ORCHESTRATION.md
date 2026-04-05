# Phase 3: Advanced Orchestration - Design & Implementation

**Start Date**: 2026-04-04
**Status**: ✅ Complete (All Steps Done)
**Goal**: Add conditional routing, subgraphs, checkpoints, and human approvals

## ✅ All Steps Complete

- ✅ Step 1: Conditional Edges (Backend + Tests)
- ✅ Step 2: Subgraphs (Backend + Tests)
- ✅ Step 3: Checkpoints (Backend: Agent + Orchestrator + API + Persistence)
- ✅ Step 4: UI Integration (Checkpoint nodes + Panel + Polling + API)

## ✅ Completed Steps

### Step 1: Conditional Edges ✅
- Edge condition evaluation in orchestrator
- Safe Python expression evaluation
- Tests: `tests/pipeline/test_conditional_execution.py`

### Step 2: Subgraphs ✅
- Subgraph expansion with recursive support
- Dependency preservation during expansion
- Tests: `tests/pipeline/test_subgraph_expansion.py`

### Step 3: Checkpoints & Human Approval ✅
- `CheckpointAgent` class with multiple checkpoint types
- Pipeline pause/resume orchestration
- Database persistence for checkpoints and state
- API endpoints: `/api/pipelines/{run_id}/checkpoints`, `/api/pipelines/resume/{run_id}`
- Tests: In progress (to be created)

## ⏳ Next: Step 4 - UI Integration
- Visual checkpoint nodes (octagon shape) with pause indicators
- Checkpoint approval panel with Approve/Reject buttons
- Real-time execution status updates
- API integration for checkpoint control

---

## Overview

Phase 3 builds on the solid Phase 1+2 foundation to add intelligence and flexibility to pipeline execution:

1. **Conditional Edges**: Route execution based on runtime conditions (e.g., "if security score < 80, stop")
2. **Subgraphs**: Encapsulate reusable pipeline segments as single nodes
3. **Checkpoints**: Pause execution and wait for external input (human approval, data input, etc.)
4. **Human Approval Agent**: Built-in checkpoint type that sends notifications and waits for approval

---

## 1. Conditional Edges

### Problem
Currently edges are static dependencies. All upstream agents must complete before downstream agents run, even if some results might make downstream work unnecessary.

### Solution
Add conditional logic to edges:

```yaml
agents:
  - agent: backend
  - agent: security
  - agent: deploy

edges:
  - source: backend
    target: security
  - source: security
    target: deploy
    condition: "result.security_score >= 80"  # Only deploy if security score >= 80
```

### Implementation

**New types in `pipeline/models.py` (or `config_loader.py`):**

```python
@dataclass
class ConditionalEdge:
    source: str
    target: str
    condition: str | None = None  # Python expression string to evaluate

    def should_execute(self, context: dict) -> bool:
        """Evaluate condition against execution context."""
        if not self.condition:
            return True
        try:
            # Safe evaluation using limited context
            return eval(self.condition, {"__builtins__": {}}, context)
        except Exception:
            return False
```

**Changes to `build_from_config()` in `orchestrator.py`:**
- Instead of building a static topological order, we need a dynamic executor that:
  1. Starts with root nodes (no dependencies or all deps satisfied)
  2. After each agent completes, evaluates conditional edges
  3. Only schedules downstream agents whose conditions evaluate to True
  4. Tracks completed agents in execution context

**New execution algorithm:**
```python
async def execute_with_conditions(self, tasks: list[PipelineTask], config: PipelineConfig):
    completed = set()
    running = set()
    context = {}

    while len(completed) < len(tasks):
        # Find ready tasks (deps satisfied)
        ready = [
            t for t in tasks
            if t.name not in completed and t.name not in running
            and all(dep in completed for dep in t.depends_on)
            and self._check_conditions(t, completed, context)
        ]

        if not ready:
            # Check for deadlock or remaining conditions not met
            break

        # Execute ready tasks in parallel (as before)
        ...
```

---

## 2. Subgraphs

### Problem
Complex pipelines may have reusable patterns. Instead of copy-pasting agent groups, we should define subgraphs as reusable components.

### Solution
Allow `agent` field to reference a subgraph definition:

```yaml
subgraphs:
  ci_cd_pipeline:
    description: "Complete CI/CD pipeline"
    agents:
      - agent: code_review
      - agent: security
      - agent: qa
      - agent: devops
    edges:
      - source: code_review
        target: security
      - source: security
        target: qa
      - source: qa
        target: devops

agents:
  - agent: backend
  - agent: ci_cd_pipeline  # This expands to the subgraph
  - agent: monetisation
```

### Implementation

**New models:**
```python
@dataclass
class SubgraphDefinition:
    name: str
    agents: list[AgentTaskConfig]
    edges: list[dict] = field(default_factory=list)
    description: str = ""

@dataclass
class PipelineConfig:
    version: str
    name: str
    agents: list[AgentTaskConfig]
    subgraphs: dict[str, SubgraphDefinition] = field(default_factory=dict)
    edges: list[dict] = field(default_factory=list)
```

**Expansion logic in `build_from_config()`:**
1. Build a lookup of subgraph definitions
2. When encountering an agent name that matches a subgraph key:
   - Replace with all agents from that subgraph
   - Preserve dependencies: the agent that referenced the subgraph becomes implicit dependency
   - Flatten edges from subgraph into main pipeline edges
3. Return fully expanded task list

**Example expansion:**
```
agents: [backend, ci_cd_pipeline, monetisation]
edges: [backend->ci_cd_pipeline, ci_cd_pipeline->monetisation]

After expansion:
agents: [backend, code_review, security, qa, devops, monetisation]
edges: [
  backend->code_review,
  code_review->security,
  security->qa,
  qa->devops,
  devops->monetisation,
  backend->monetisation  (if explicit edge existed)
]
```

---

## 3. Checkpoints & Human Approval

### Problem
Some pipelines need human intervention:
- Security audit results need review before deployment
- Budget approval for expensive runs
- Manual QA before production

### Solution
Introduce a special `checkpoint` agent type that pauses execution and waits for external signal.

**Checkpoint types:**
- `human_approval` - Send notification, wait for approval/rejection
- `manual_qa` - Wait for QA tester to mark complete
- `budget_approval` - Wait for cost threshold approval
- `data_input` - Wait for external data to be provided

**Example:**
```yaml
agents:
  - agent: backend
  - agent: security
  - agent: checkpoint:human_approval  # Special checkpoint agent
    config:
      checkpoint_type: human_approval
      message: "Security audit complete. Approve deployment?"
      timeout_minutes: 1440  # 24 hours
      approvers: ["team-lead@company.com"]
  - agent: devops
```

**Implementation**

**New `CheckpointAgent` class** (`agents/checkpoint_agent.py`):
```python
@register_agent
class CheckpointAgent(BaseAgent):
    name = "checkpoint"

    async def run(self, task: str, context: dict = None) -> AgentResult:
        # Extract checkpoint config from self.config
        checkpoint_type = self.config.checkpoint_type
        approvers = self.config.approvers

        # Create checkpoint record in database
        checkpoint_id = await self._create_checkpoint_record()

        # Send notifications (email, Slack, etc.)
        await self._notify_approvers(checkpoint_id, approvers)

        # Wait for approval (poll database or listen for webhook)
        result = await self._wait_for_approval(checkpoint_id, timeout=self.config.timeout_minutes * 60)

        if result.approved:
            return AgentResult(
                output=f"Checkpoint approved by {result.approver}. Proceeding.",
                ...
            )
        else:
            raise PipelinePausedException(f"Checkpoint rejected: {result.reason}")
```

**Orchestrator changes:**
- When a checkpoint agent runs, execution enters "paused" state
- `Orchestrator.run()` returns special `PipelinePaused` status with checkpoint_id
- Client can later resume by calling `/api/pipelines/resume/{checkpoint_id}` with approval decision
- Checkpoint also exposed in UI for manual approval

**Checkpoint persistence:**
```python
class CheckpointRecord(Base):
    id: str (UUID)
    pipeline_run_id: str
    agent_name: str
    status: str  # "pending", "approved", "rejected", "timeout"
    approver: str | None
    decision_at: datetime | None
    metadata: JSON
```

---

## 4. UI Support (pipeline-ui)

Update the visual pipeline builder to support:

### Conditional Edges
- Click edge → show condition editor
- Enter Python-like expression: `security_score >= 80`
- Highlight edges that are conditional (different color)
- Preview mode: show which branches would be taken given sample context

### Subgraphs
- Select multiple nodes → "Group into subgraph"
- Subgraph appears as single grouped node (collapsible)
- Can expand/collapse to see internals
- Save subgraph to template library for reuse

### Checkpoints
- New node type: `checkpoint` (octagon shape)
- Config panel: select checkpoint type, set timeout, add approvers
- Visual indicator: ⏸️ icon on node
- Checkpoint status visible in node (pending/approved/rejected)

### Execution Status
- During pipeline run:
  - Nodes change color: running (blue), completed (green), failed (red), paused (orange)
  - Checkpoint nodes show "Waiting for approval"
  - Click checkpoint → show approval panel with "Approve"/"Reject" buttons
- API endpoint for `/api/pipelines/{run_id}/checkpoints` to list pending checkpoints
- WebSocket support for real-time updates (bonus)

---

## Implementation Plan

### Step 1: Conditional Edges (Priority: High)

**Files to modify/create:**
1. `pipeline/models.py` (or extend `config_loader.py`):
   - Add `ConditionalEdge` model
   - Add `condition` field to edge definitions
2. `pipeline/orchestrator.py`:
   - Modify `build_from_config()` to handle conditional edges
   - Create new executor that evaluates conditions at runtime
   - Update `run()` to accept/use context for condition evaluation
3. `config/pipelines/templates.yaml`:
   - Add example template with conditional edge (e.g., "staging_deploy_with_approval")
4. `tests/pipeline/test_conditional_execution.py`:
   - Test condition evaluation
   - Test that conditional edges skip appropriately
   - Test deadlock detection when conditions never met

**Checkpoint**: Conditional edges working in tests, one template updated

### Step 2: Subgraphs (Priority: Medium)

**Files to modify/create:**
1. `pipeline/models.py`:
   - Add `SubgraphDefinition` model
   - Update `PipelineConfig` to include `subgraphs: dict`
   - Add `is_subgraph: bool` flag to `AgentTaskConfig`?
2. `pipeline/config_loader.py`:
   - Update `build_from_config()` to expand subgraphs recursively
   - Preserve dependencies during expansion
   - Handle nested subgraphs (subgraph inside subgraph)
3. `tests/pipeline/test_subgraph_expansion.py`:
   - Test simple subgraph expansion
   - Test nested subgraphs
   - Test dependency preservation

**Checkpoint**: Subgraph expansion working, test template with nested subgraphs

### Step 3: Checkpoints (Priority: Medium)

**Files to create/modify:**
1. `agents/checkpoint_agent.py` (new):
   - Implement `CheckpointAgent`
   - Support multiple checkpoint types (human_approval, manual_qa, budget_approval, data_input)
   - Notification system (email placeholder)
   - Persistence to database/JSON file
2. `pipeline/orchestrator.py`:
   - Detect when checkpoint agent completes with "paused" status
   - Return `PipelinePaused` response with checkpoint details
   - Implement `resume()` method to continue after approval
3. `api/main.py`:
   - Add `POST /api/pipelines/resume/{run_id}` endpoint
   - Add `GET /api/pipelines/{run_id}/checkpoints` endpoint
4. `api/pipelines_schemas.py`:
   - Add `CheckpointRequest`, `CheckpointResponse`, `PipelinePausedResponse` models
5. `tests/agents/test_checkpoint_agent.py`:
   - Test checkpoint creation
   - Test timeout behavior
   - Test resume flow
6. `tests/api/test_checkpoints.py`:
   - Test pause/resume endpoints

**Checkpoint**: Checkpoint agent fully functional, pause/resume API working

### Step 4: UI Integration

**Update `pipeline-ui/`:**
1. Add edge condition editor component
2. Update sidebar to support subgraph creation
3. Add checkpoint node type
4. Show real-time execution status (colors, icons)
5. Add approval panel for checkpoints
6. Update API calls to handle conditions, subgraphs, checkpoints

**Checkpoint**: UI fully supports all Phase 3 features

---

## Testing Strategy

For each feature:

1. **Unit tests**: Individual components (condition evaluator, subgraph expander, checkpoint agent)
2. **Integration tests**: End-to-end execution with sample pipelines
3. **Template tests**: Each new template exercises one Phase 3 feature
4. **UI tests** (if time): Component tests with React Testing Library

**Phase 3 Test Target:**
- 4 new test files
- 20+ new tests
- All passing

---

## Success Criteria

✅ Conditional edges evaluate correctly at runtime
✅ Subgraphs expand recursively with proper dependency preservation
✅ Checkpoint agent pauses and resumes correctly
✅ API endpoints for pause/resume working
✅ UI supports editing conditions, grouping subgraphs, approving checkpoints
✅ All new tests passing (20+)

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Condition evaluation unsafe (eval) | Security | Use restricted eval context, or implement DSL |
| Subgraph name collisions | Medium | Namespace subgraphs by pipeline |
| Checkpoint state lost on restart | High | Persist checkpoint records to DB (introduce PostgreSQL in Phase 4) |
| Complex UI for conditional edges | Medium | Keep condition editor simple (single-line expression) |

---

## Next Steps

1. Implement **Conditional Edges** first (foundational)
2. Then **Subgraphs** (composite structure)
3. Then **Checkpoints** (requires async approval flow)
4. Finally **UI integration** (tie it all together)

Let's start with Step 1: Conditional Edges Implementation.
