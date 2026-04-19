# Agent Self-Evolution: How AI Coworkers Learn, Upskill, and Get Smarter

> **Goal**: Agents should not remain static tools. Like real employees, they should learn from every sprint, improve from every review, acquire new skills, and become measurably better over time — without explicit retraining or prompt rewriting.

---

## 1. The Problem: Agents Start Fresh Every Time

Today, your agents are **stateless** and **amnesiac**:

```python
# Current: Every run is a blank slate
agent = create_agent("backend", project_id="my-project")
result = agent.run("Build a REST API for user auth")
# Agent does the work... then forgets everything.
# Next run: "Build a REST API for payments"
# Agent has ZERO memory of the auth API it just built.
```

A human developer improves across three dimensions:

| Dimension | How Humans Learn | Agents Today |
|-----------|-----------------|--------------|
| **Experience** | "Last time I used JWT, I made a token refresh mistake. I'll avoid that now." | ❌ No memory |
| **Skill** | "I read the Stripe docs, now I know webhooks." | ❌ Static prompt |
| **Judgment** | "My code reviews keep failing on error handling — I'll be more careful." | ❌ No feedback loop |

---

## 2. The Five Pillars of Agent Self-Evolution

```
┌────────────────────────────────────────────────────────────┐
│                 Agent Self-Evolution Engine                  │
├──────────┬──────────┬──────────┬──────────┬───────────────┤
│    1     │    2     │    3     │    4     │      5        │
│ Outcome  │ Self-    │ Skill    │ Prompt   │ Cross-Agent   │
│ Learning │ Reflect  │ Acquisi  │ Evolu    │ Knowledge     │
│          │ -ion     │ -tion    │ -tion    │ Transfer      │
├──────────┼──────────┼──────────┼──────────┼───────────────┤
│ Learn    │ Critique │ Read     │ Auto-    │ Learn from    │
│ from QA  │ own      │ docs,    │ refine   │ other agents' │
│ results  │ output   │ learn    │ system   │ successes and │
│ & review │ before   │ new      │ prompts  │ failures      │
│ feedback │ submit   │ patterns │ over time│               │
└──────────┴──────────┴──────────┴──────────┴───────────────┘
          │                                        │
          ▼                                        ▼
    ┌───────────┐                         ┌───────────────┐
    │ pgvector  │                         │ Performance   │
    │ Semantic  │                         │ Scorecard     │
    │ Memory    │                         │ (per agent)   │
    └───────────┘                         └───────────────┘
```

---

### Pillar 1: Outcome-Based Learning

**What**: After every task, the agent records *what it did* and *how it went* — not just the output, but the **outcome** (did it pass review? did tests pass? were there security issues?).

**How it works**:

```python
# evolution/outcome_tracker.py — NEW

@dataclass
class TaskOutcome:
    """Records what happened AFTER an agent's output was produced."""
    agent_name: str
    task_summary: str
    output_summary: str          # What the agent produced (truncated)
    
    # Outcome signals (filled in post-execution)
    review_passed: bool | None = None       # Did code review approve?
    review_feedback: str = ""               # What did the reviewer say?
    tests_passed: bool | None = None        # Did QA tests pass?
    test_failures: list[str] = field(default_factory=list)
    security_issues: list[str] = field(default_factory=list)
    human_feedback: str = ""                # Did a human give feedback?
    cost_usd: float = 0.0
    revision_count: int = 0                 # How many revision rounds?
    
    # Derived learning
    lesson_learned: str = ""                # Auto-generated reflection
    patterns_to_repeat: list[str] = field(default_factory=list)
    patterns_to_avoid: list[str] = field(default_factory=list)

class OutcomeTracker:
    """Tracks outcomes and extracts learnings for agent evolution."""
    
    async def record_outcome(self, outcome: TaskOutcome):
        """Record an outcome and generate a learning."""
        
        # 1. Use a cheap LLM to extract the lesson
        lesson = await self.llm.create_message(
            model="anthropic/claude-haiku-4-5-20251001",
            messages=[{
                "role": "user",
                "content": f"""Analyze this task outcome and extract a concise lesson 
                for the {outcome.agent_name} agent to remember for future tasks.

                Task: {outcome.task_summary}
                Output: {outcome.output_summary[:500]}
                Review passed: {outcome.review_passed}
                Review feedback: {outcome.review_feedback}
                Tests passed: {outcome.tests_passed}
                Test failures: {outcome.test_failures}
                Revisions needed: {outcome.revision_count}

                Extract:
                1. ONE key lesson (1-2 sentences)
                2. Patterns to REPEAT (what went well)
                3. Patterns to AVOID (what failed)
                """
            }],
            max_tokens=500,
        )
        
        outcome.lesson_learned = lesson.content
        
        # 2. Store as a vector embedding for future semantic recall
        await self.vector_store.store(
            agent_name=outcome.agent_name,
            content=f"Lesson: {outcome.lesson_learned}\n"
                    f"Context: {outcome.task_summary}\n"
                    f"Outcome: {'PASS' if outcome.review_passed else 'FAIL'}",
            memory_type="lesson",
            metadata={
                "review_passed": outcome.review_passed,
                "tests_passed": outcome.tests_passed,
                "revision_count": outcome.revision_count,
            },
        )
        
        # 3. Update the agent's performance scorecard
        await self.scorecard.update(outcome)
```

**Example in action**:

```
Sprint 12, Story: "Build Stripe webhook endpoint"
─────────────────────────────────────────────────
  BE Agent output:   POST /webhooks/stripe endpoint
  Code Review:       ❌ FAILED — "No idempotency check. Missing signature verification."
  Revision 1:        Added signature check, still no idempotency
  Code Review:       ❌ FAILED — "Idempotency still missing"
  Revision 2:        Added Redis-based idempotency key store
  Code Review:       ✅ PASSED

  ┌──────────────────────────────────────────────────────────────────┐
  │ LESSON STORED (Vector Memory):                                   │
  │                                                                   │
  │ "When building webhook endpoints, ALWAYS include:                 │
  │  1. Request signature verification (e.g., Stripe-Signature)       │
  │  2. Idempotency key check (store event IDs in Redis with TTL)     │
  │  3. Return 200 immediately, process async                         │
  │  Pattern took 2 revisions to learn — prioritize these checks."    │
  └──────────────────────────────────────────────────────────────────┘

Sprint 15, Story: "Build PayPal IPN handler"
─────────────────────────────────────────────────
  BE Agent recalls: "Similar to Stripe webhooks in Sprint 12..."
  → Includes idempotency + signature verification from the start
  Code Review:      ✅ PASSED (first try!)
  Revisions:        0 (down from 2)
```

---

### Pillar 2: Self-Reflection (Pre-Submission Critique)

**What**: Before an agent submits its output, it runs a **self-critique step** — asking itself "Could I be wrong? What did I miss?" This catches issues *before* they reach code review, reducing revision rounds.

**How it works**:

```python
# evolution/self_reflection.py — NEW

class SelfReflector:
    """Post-generation self-critique to improve quality before submission."""
    
    async def reflect(
        self,
        agent_name: str,
        task: str,
        output: str,
        past_mistakes: list[str],  # Retrieved from vector memory
    ) -> ReflectionResult:
        """
        Agent reviews its own output before submitting.
        Uses past mistakes to focus the critique.
        """
        
        prompt = f"""You are the {agent_name} agent reviewing your OWN output before submission.

## Your Task
{task}

## Your Output
{output}

## Past Mistakes You've Made (learn from these!)
{chr(10).join(f'- {m}' for m in past_mistakes)}

## Self-Critique Checklist
1. Does this output fully address the task requirements?
2. Are there any of my PAST MISTAKES being repeated here?
3. Edge cases: What inputs/scenarios would break this?
4. Security: Any hardcoded secrets, SQL injection, XSS risks?
5. Error handling: What happens when things fail?
6. Performance: Any N+1 queries, missing indexes, unbounded loops?

## Your Response
- List specific issues found (or "none" if clean)
- For each issue, provide the fix
- Rate your confidence: HIGH / MEDIUM / LOW
"""
        
        critique = await self.llm.create_message(
            model="anthropic/claude-haiku-4-5-20251001",  # Cheap model for reflection
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1000,
        )
        
        if critique.issues_found:
            # Agent fixes its own issues before submitting
            revised_output = await self.revise(agent_name, task, output, critique)
            return ReflectionResult(
                original_output=output,
                revised_output=revised_output,
                issues_found=critique.issues,
                self_fixed=True,
            )
        
        return ReflectionResult(original_output=output, revised_output=output, self_fixed=False)
```

**Integration into BaseAgent**:

```python
# agents/base.py — Enhanced run() method

class BaseAgent(ABC):
    async def run(self, task: str, context: str = "") -> AgentResult:
        # 1. Recall relevant past lessons
        past_lessons = await self.recall_similar(task, memory_type="lesson")
        past_mistakes = await self.recall_similar(task, memory_type="mistake")
        
        # 2. Inject lessons into context
        enriched_context = self._build_context(context, past_lessons)
        
        # 3. Generate output (existing logic)
        output = await self._execute(task, enriched_context)
        
        # 4. NEW: Self-reflection before submission
        reflection = await self.reflector.reflect(
            agent_name=self.name,
            task=task,
            output=output,
            past_mistakes=past_mistakes,
        )
        
        # 5. Use reflected output (may have self-corrections)
        final_output = reflection.revised_output
        
        # 6. Return result
        return AgentResult(
            agent_name=self.name,
            output=final_output,
            self_reflection_applied=reflection.self_fixed,
            issues_self_corrected=len(reflection.issues_found),
        )
```

---

### Pillar 3: Skill Acquisition (Active Learning)

**What**: Agents can actively learn new skills by reading documentation, studying codebases, and adding knowledge to their skills library — just like a developer reading docs on a new framework before using it.

**How it works**:

```python
# evolution/skill_acquisition.py — NEW

class SkillAcquisition:
    """Agents learn new skills by studying documentation and patterns."""
    
    async def study_documentation(
        self,
        agent_name: str,
        topic: str,
        sources: list[str],  # URLs or file paths
    ) -> SkillSheet:
        """
        Agent reads documentation and creates a structured skill sheet.
        Stored as a new skill file that gets injected into future prompts.
        """
        
        # 1. Fetch and read the docs
        raw_content = await self._fetch_sources(sources)
        
        # 2. Have the agent distill key patterns, APIs, and gotchas
        skill_sheet = await self.llm.create_message(
            model="anthropic/claude-sonnet-4-5",
            messages=[{
                "role": "user",
                "content": f"""You are the {agent_name} agent studying a new topic: {topic}

## Source Material
{raw_content[:30000]}

## Create a Skill Sheet
Extract the following in a structured format:
1. **Key Concepts**: Core ideas in 2-3 sentences each
2. **API Patterns**: Common usage patterns with code examples
3. **Best Practices**: The "right way" to use this
4. **Common Pitfalls**: What to avoid (with examples)
5. **Quick Reference**: Cheat sheet for common operations
"""
            }],
            max_tokens=4000,
        )
        
        # 3. Save as a skill file (similar to existing skills/ directory)
        skill_path = f"skills/learned/{agent_name}/{topic.replace(' ', '_')}.md"
        await self.file_store.write(skill_path, skill_sheet.content)
        
        # 4. Store embeddings for semantic recall
        await self.vector_store.store(
            agent_name=agent_name,
            content=skill_sheet.content,
            memory_type="skill",
            metadata={"topic": topic, "source_count": len(sources)},
        )
        
        return SkillSheet(topic=topic, content=skill_sheet.content, path=skill_path)
    
    async def learn_from_codebase(
        self,
        agent_name: str,
        repo: str,
        focus_areas: list[str],
    ) -> list[str]:
        """
        Agent studies an existing codebase to learn patterns.
        E.g., FE agent studies the existing component library to maintain consistency.
        """
        
        # 1. List files in the repo
        files = await self.github.list_files(repo)
        
        # 2. Focus on relevant files
        relevant = [f for f in files if any(area in f['path'] for area in focus_areas)]
        
        # 3. Read and learn patterns
        patterns = []
        for f in relevant[:20]:  # Limit to avoid cost explosion
            content = await self.github.get_file(repo, f['path'])
            pattern = await self._extract_pattern(agent_name, content)
            patterns.append(pattern)
        
        # 4. Store learned patterns
        for pattern in patterns:
            await self.vector_store.store(
                agent_name=agent_name,
                content=pattern,
                memory_type="codebase_pattern",
                metadata={"repo": repo},
            )
        
        return patterns
```

**Example: Agent Upskilling Flow**

```
VP Eng:     "Next sprint uses Supabase Edge Functions. BE Agent, please 
             study the Supabase Edge Functions docs before the sprint starts."

BE Agent:   (Reads Supabase docs → Creates skill sheet → Stores in vector memory)
            "Skill acquired: Supabase Edge Functions
             - Deno-based serverless functions
             - Use serve() handler pattern
             - Environment variables via Deno.env.get()
             - Connect to DB via supabase-js client, not direct PG
             - Gotcha: 60-second execution limit, no filesystem access"

Sprint 16:  BE Agent uses Supabase Edge Functions correctly on first attempt.
            Zero revisions needed (vs. 2-3 without the upskilling step).
```

---

### Pillar 4: Prompt Self-Evolution (DSPy-Inspired)

**What**: The agent's system prompt is not static — it evolves based on performance data. If an agent consistently fails on error handling, its prompt gets automatically updated to emphasize error handling.

**How it works**:

```python
# evolution/prompt_evolution.py — NEW

class PromptEvolver:
    """
    Automatically evolves agent system prompts based on performance data.
    Inspired by DSPy's approach of treating prompts as optimizable parameters.
    """
    
    async def evolve_prompt(
        self,
        agent_name: str,
        current_prompt: str,
        performance_data: PerformanceData,
    ) -> EvolvedPrompt:
        """
        Analyze performance trends and evolve the system prompt.
        Called at the end of each sprint (not after every task).
        """
        
        # 1. Identify recurring weakness patterns
        weaknesses = performance_data.get_recurring_failures(min_count=2)
        strengths = performance_data.get_consistent_successes()
        
        if not weaknesses:
            return EvolvedPrompt(prompt=current_prompt, changed=False, reason="No recurring issues")
        
        # 2. Generate prompt improvement suggestions
        evolution = await self.llm.create_message(
            model="anthropic/claude-sonnet-4-5",
            messages=[{
                "role": "user",
                "content": f"""You are optimizing the system prompt for the {agent_name} agent.

## Current System Prompt
{current_prompt}

## Performance Data (Last 3 Sprints)
- Tasks completed: {performance_data.tasks_completed}
- First-pass review rate: {performance_data.first_pass_rate}%
- Average revisions needed: {performance_data.avg_revisions}
- Most common review feedback: {performance_data.top_feedback}

## Recurring Weaknesses (appeared 2+ times)
{chr(10).join(f'- {w.description} (occurred {w.count} times)' for w in weaknesses)}

## Consistent Strengths
{chr(10).join(f'- {s}' for s in strengths)}

## Task
Suggest specific ADDITIONS or MODIFICATIONS to the system prompt that would 
address the recurring weaknesses. Do NOT remove existing content that supports 
the strengths. Be surgical — small, targeted changes only.

Output format:
1. What to ADD (new instructions targeting weaknesses)
2. What to EMPHASIZE (existing instructions that need stronger wording)
3. What to KEEP (strengths - do not touch)
4. The evolved system prompt (full text)
"""
            }],
            max_tokens=4000,
        )
        
        # 3. A/B test: Run the next sprint with the evolved prompt
        #    If performance improves → adopt. If not → revert.
        return EvolvedPrompt(
            prompt=evolution.evolved_prompt,
            changed=True,
            reason=f"Addressing: {', '.join(w.description for w in weaknesses[:3])}",
            a_b_test=True,  # Run both prompts in parallel next sprint
        )
```

**Example: Prompt Evolution Over 3 Sprints**

```
Sprint 10 Prompt (original):
  "You are a backend engineer. Write clean, well-tested FastAPI code."

Sprint 10 Performance:
  Reviews passed first try: 40%
  Top failure: "Missing error handling" (5 stories)
  Top failure: "No input validation" (3 stories)

  ┌─ EVOLUTION ─────────────────────────────────────────────────────┐
  │ Adding: "CRITICAL: Every endpoint MUST include:                │
  │   1. Input validation with Pydantic models                     │
  │   2. try/except with specific error types                      │
  │   3. Proper HTTP status codes (400 for validation, 500 for     │
  │      unexpected errors)                                         │
  │   4. Error response schema: {error: str, code: str, details: } │
  │ These are NON-NEGOTIABLE. Missing any will fail code review."   │
  └─────────────────────────────────────────────────────────────────┘

Sprint 11 Performance (after evolution):
  Reviews passed first try: 65% (↑ 25%)
  "Missing error handling" failures: 1 (↓ from 5)

Sprint 12 Performance:
  Reviews passed first try: 80% (↑ 15%)
  New weakness detected: "Missing pagination on list endpoints"

  ┌─ EVOLUTION ─────────────────────────────────────────────────────┐
  │ Adding: "For any list/search endpoint, ALWAYS implement:        │
  │   - Cursor-based pagination (not offset-based)                  │
  │   - Default limit: 20, max limit: 100                           │
  │   - Include total_count in response metadata"                   │
  └─────────────────────────────────────────────────────────────────┘

Sprint 13 Performance:
  Reviews passed first try: 88% (↑ 8%)
  Agent is measurably better than Sprint 10.
```

---

### Pillar 5: Cross-Agent Knowledge Transfer

**What**: When one agent learns something valuable, it can be shared across the team. The BE agent's lesson about webhook idempotency should be available to any agent that encounters a similar pattern.

**How it works**:

```python
# evolution/knowledge_transfer.py — NEW

class KnowledgeTransfer:
    """Share learnings across agents to accelerate team-wide improvement."""
    
    async def broadcast_learning(
        self,
        source_agent: str,
        lesson: str,
        applicable_to: list[str],  # List of agent names that might benefit
    ):
        """
        Share a lesson learned by one agent with others.
        Stored in a shared knowledge base accessible by all agents.
        """
        
        # 1. Store in shared vector memory (no agent_name filter)
        await self.vector_store.store(
            agent_name="shared",  # Accessible by all
            content=f"[Learned by {source_agent}]: {lesson}",
            memory_type="team_lesson",
            metadata={
                "source_agent": source_agent,
                "applicable_to": applicable_to,
            },
        )
        
        # 2. Notify relevant agents via message bus
        for agent in applicable_to:
            await self.bus.publish(AgentMessage(
                sender="evolution_engine",
                channel=f"direct:{agent}",
                message_type=MessageType.BROADCAST,
                content=f"📚 New team learning from {source_agent}: {lesson}",
            ))
    
    async def get_team_knowledge(
        self,
        agent_name: str,
        task: str,
        top_k: int = 5,
    ) -> list[str]:
        """
        Retrieve relevant team learnings for a task.
        Combines agent-specific + shared knowledge.
        """
        
        # Agent's own memories
        own = await self.vector_store.search(
            agent_name=agent_name,
            query=task,
            top_k=top_k,
        )
        
        # Shared team knowledge
        shared = await self.vector_store.search(
            agent_name="shared",
            query=task,
            top_k=top_k,
        )
        
        return own + shared
```

**Example: Knowledge Transfer in Action**

```
Sprint 14: Security Agent discovers that the team's JWT implementation
           uses HS256 (symmetric) instead of RS256 (asymmetric).

Security Agent → Knowledge Transfer Engine:
  "JWT tokens should use RS256 (asymmetric) for production APIs.
   HS256 shares the signing secret with all services that verify,
   creating a single point of compromise. RS256 uses a private key
   for signing and a public key for verification."

Knowledge Transfer Engine:
  → Broadcasts to: [backend, frontend, devops]
  → Stores in shared vector memory

Sprint 15: BE Agent is asked to build a new microservice with auth.
  → Recalls team lesson: "Use RS256 for JWT, not HS256"
  → Implements RS256 from the start
  → Zero security review findings
```

---

## 3. Performance Scorecard: Measuring Evolution

Each agent gets a **performance scorecard** that tracks improvement over time:

```python
# evolution/scorecard.py — NEW

@dataclass
class AgentScorecard:
    """Track agent performance across sprints to measure evolution."""
    agent_name: str
    
    # Quality metrics
    first_pass_review_rate: float = 0.0      # % of outputs that pass review first try
    avg_revision_rounds: float = 0.0          # Average revisions per task
    security_issue_rate: float = 0.0          # % of outputs with security issues
    test_pass_rate: float = 0.0               # % of generated tests that pass
    
    # Efficiency metrics
    avg_cost_per_task: float = 0.0            # Average LLM cost per task
    avg_time_per_task: float = 0.0            # Average execution time
    self_correction_rate: float = 0.0         # % of issues caught by self-reflection
    
    # Growth metrics
    skills_acquired: int = 0                  # Number of skill sheets created
    lessons_learned: int = 0                  # Number of outcome lessons stored
    knowledge_shared: int = 0                 # Number of team learnings contributed
    
    # Trend (sprint-over-sprint)
    quality_trend: str = "stable"             # "improving" | "stable" | "declining"
    efficiency_trend: str = "stable"
```

### Dashboard View (Proposed UI)

```
┌─────────────────────────────────────────────────────────────────┐
│  🤖 Backend Agent — Performance Evolution                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  First-Pass Review Rate           Avg Revisions Per Task         │
│  100%│          ╱──●              3│                              │
│   80%│      ╱──●                  2│ ●                            │
│   60%│  ╱──●                      1│   ●──●──●                    │
│   40%│ ●                          0│            ●──●              │
│      └──────────────              └──────────────                │
│      S10 S11 S12 S13              S10 S11 S12 S13                │
│                                                                  │
│  Skills: 12 acquired  │  Lessons: 34 stored  │  Shared: 8       │
│                                                                  │
│  ┌──────────────────────────────────────────────────────┐       │
│  │ Top 3 Most Impactful Learnings:                       │       │
│  │ 1. "Always use RS256 for JWT" (saved 3 review rounds)  │       │
│  │ 2. "Webhook idempotency pattern" (saved 2 rounds)      │       │
│  │ 3. "Cursor-based pagination default" (saved 4 rounds)  │       │
│  └──────────────────────────────────────────────────────┘       │
└─────────────────────────────────────────────────────────────────┘
```

---

## 4. The Self-Evolution Loop (Complete Cycle)

```
                    ┌──────────────┐
                    │  SPRINT N    │
                    │  Begins      │
                    └──────┬───────┘
                           │
                    ┌──────▼───────┐
                    │  1. RECALL   │ ← Agent loads: persona + lessons +
                    │              │   skills + team knowledge
                    └──────┬───────┘
                           │
                    ┌──────▼───────┐
                    │  2. EXECUTE  │ ← Task execution with enriched context
                    │              │
                    └──────┬───────┘
                           │
                    ┌──────▼───────┐
                    │ 3. REFLECT   │ ← Self-critique before submission
                    │ "Did I miss  │   Checks against past mistakes
                    │  anything?"  │
                    └──────┬───────┘
                           │
                    ┌──────▼───────┐
                    │  4. SUBMIT   │ → Output sent to review/QA
                    │              │
                    └──────┬───────┘
                           │
              ┌────────────▼────────────┐
              │  5. RECEIVE FEEDBACK    │ ← Code review result, QA result,
              │  (Pass / Fail / Notes)  │   security findings, human notes
              └────────────┬────────────┘
                           │
              ┌────────────▼────────────┐
              │  6. EXTRACT LESSON      │ ← "What did I learn from this?"
              │  Store in vector memory  │   Patterns to repeat/avoid
              └────────────┬────────────┘
                           │
              ┌────────────▼────────────┐
              │  7. SHARE (if valuable) │ ← Broadcast to team if broadly
              │  Knowledge Transfer      │   applicable
              └────────────┬────────────┘
                           │
                    ┌──────▼───────┐
                    │ SPRINT ENDS  │
                    └──────┬───────┘
                           │
              ┌────────────▼────────────┐
              │  8. EVOLVE PROMPT       │ ← Analyze sprint performance
              │  (End of Sprint)        │   Surgically update system prompt
              └────────────┬────────────┘
                           │
              ┌────────────▼────────────┐
              │  9. UPSKILL             │ ← Study docs for next sprint's
              │  (Between Sprints)      │   technologies
              └────────────┬────────────┘
                           │
                    ┌──────▼───────┐
                    │  SPRINT N+1  │ ← Agent is measurably smarter
                    │  Begins      │
                    └──────────────┘
```

---

## 5. Database Schema for Evolution

```sql
-- Agent performance metrics (per sprint)
CREATE TABLE agent_performance (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_name VARCHAR(100) NOT NULL,
    sprint_id UUID REFERENCES sprints(id),
    tasks_completed INTEGER DEFAULT 0,
    tasks_failed INTEGER DEFAULT 0,
    first_pass_rate FLOAT DEFAULT 0.0,
    avg_revisions FLOAT DEFAULT 0.0,
    total_cost_usd FLOAT DEFAULT 0.0,
    self_corrections INTEGER DEFAULT 0,     -- Issues caught by self-reflection
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Learned lessons (searchable via pgvector)
CREATE TABLE agent_lessons (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_name VARCHAR(100) NOT NULL,
    lesson TEXT NOT NULL,
    task_context TEXT,                       -- What task triggered this lesson
    outcome VARCHAR(20),                    -- "success" | "failure" | "partial"
    impact_score FLOAT DEFAULT 0.0,         -- How much this lesson improved performance
    times_recalled INTEGER DEFAULT 0,       -- How often this lesson has been used
    embedding VECTOR(1536),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Acquired skills
CREATE TABLE agent_skills (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_name VARCHAR(100) NOT NULL,
    topic VARCHAR(200) NOT NULL,
    skill_content TEXT NOT NULL,
    source_urls JSONB DEFAULT '[]',
    confidence_level VARCHAR(20) DEFAULT 'learned',  -- "learning" | "learned" | "mastered"
    times_used INTEGER DEFAULT 0,
    last_used_at TIMESTAMPTZ,
    embedding VECTOR(1536),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Prompt evolution history (audit trail)
CREATE TABLE prompt_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_name VARCHAR(100) NOT NULL,
    version INTEGER NOT NULL,
    prompt_text TEXT NOT NULL,
    reason TEXT,                             -- Why was this change made?
    performance_before JSONB,               -- Metrics before this version
    performance_after JSONB,                -- Metrics after (filled in next sprint)
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_perf_agent_sprint ON agent_performance(agent_name, sprint_id);
CREATE INDEX idx_lessons_embedding ON agent_lessons USING hnsw (embedding vector_cosine_ops);
CREATE INDEX idx_skills_embedding ON agent_skills USING hnsw (embedding vector_cosine_ops);
CREATE INDEX idx_lessons_agent ON agent_lessons(agent_name);
CREATE INDEX idx_skills_agent ON agent_skills(agent_name);
CREATE INDEX idx_prompt_agent_active ON prompt_versions(agent_name, active);
```

---

## 6. Safety Guardrails for Self-Evolution

| Risk | Guardrail |
|------|-----------|
| **Prompt drift** — evolved prompt diverges from intended behavior | Version control + A/B testing: never auto-adopt without performance comparison |
| **False lessons** — agent learns the wrong conclusion from a fluke | Minimum threshold: lesson must be confirmed by 2+ similar outcomes |
| **Runaway costs** — self-reflection and upskilling use extra API calls | Budget cap per sprint for evolution activities (max 10% of sprint budget) |
| **Echo chamber** — agent only reinforces its own biases | Cross-agent knowledge transfer + periodic human review of lesson database |
| **Skill rot** — outdated skills persist and cause issues | Confidence decay: skills unused for 5+ sprints get flagged for review |
| **Prompt explosion** — system prompt grows too large over time | Max prompt size (8000 tokens). New additions must replace low-impact sections |

---

## 7. Implementation Priority

| Phase | Component | Effort | Dependencies |
|-------|-----------|--------|-------------|
| **5D.1** | Outcome Tracking (record what happened after each task) | Low | pgvector (Phase 0) |
| **5D.2** | Self-Reflection (critique before submitting) | Low | None (works today) |
| **5D.3** | Performance Scorecard (metrics per agent per sprint) | Low | Outcome Tracking |
| **5D.4** | Skill Acquisition (read docs, create skill sheets) | Medium | Vector memory |
| **5D.5** | Prompt Evolution (auto-improve system prompts) | Medium | Scorecard + 3 sprints of data |
| **5D.6** | Cross-Agent Knowledge Transfer | Medium | Message bus (Phase 2) |
| **5D.7** | Evolution Dashboard UI | Medium | Scorecard + all above |

> [!TIP]
> **Self-Reflection (5D.2) is the fastest win.** It requires zero infrastructure changes — just add a self-critique step before the agent returns its output. This alone can reduce revision rounds by 30-40%.

---

## 8. How This Fits Into the Overall Architecture

```
ARCHITECTURE_OVERHAUL.md           AI_COWORKERS_VISION.md
─────────────────────────          ──────────────────────
Phase 0: Redis + pgvector    ←─── Enables: Vector Memory for Lessons
Phase 1: LiteLLM             ←─── Enables: Cheap models for reflection
Phase 2: Agent Bus            ←─── Enables: Knowledge Transfer broadcasts
Phase 3: Temporal             ←─── Enables: Sprint-scoped evolution cycles
Phase 4: New Agents + UI     ←─── Enables: Evolution Dashboard
Phase 5D: Self-Evolution     ←─── THIS DOCUMENT
```

The self-evolution system is **layered on top** of the infrastructure from the Architecture Overhaul. It doesn't require changing the base architecture — it uses the same stores (pgvector, Redis) and workflows (Temporal) already planned.

---

*Created: 2026-04-11 | Status: Architecture Addendum — Agent Self-Evolution*
*Companion docs: [AI_COWORKERS_VISION.md](./AI_COWORKERS_VISION.md) | [ARCHITECTURE_OVERHAUL.md](./ARCHITECTURE_OVERHAUL.md)*
