-- ============================================================================
-- ARCHITECTURE OVERHAUL: SCHEMA UPDATES
-- ============================================================================

-- 1. Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- 2. Agent Personas (Persistent Identity)
CREATE TABLE IF NOT EXISTS agent_personas (
    name VARCHAR(100) PRIMARY KEY,
    title VARCHAR(200),
    seniority VARCHAR(50),
    specializations JSONB DEFAULT '[]',
    working_style TEXT,
    communication_preferences TEXT,
    decision_log JSONB DEFAULT '[]',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 3. Sprints
CREATE TABLE IF NOT EXISTS sprints (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id VARCHAR(100) NOT NULL,
    name VARCHAR(200),
    goal TEXT,
    start_date TIMESTAMPTZ,
    end_date TIMESTAMPTZ,
    capacity_points INTEGER,
    status VARCHAR(50) DEFAULT 'planning', -- 'planning', 'active', 'review', 'closed'
    velocity_actual INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 4. User Stories
CREATE TABLE IF NOT EXISTS user_stories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sprint_id UUID REFERENCES sprints(id),
    title VARCHAR(500),
    description TEXT,
    acceptance_criteria JSONB DEFAULT '[]',
    story_points INTEGER,
    assigned_to VARCHAR(100), -- References agent_personas(name)
    status VARCHAR(50) DEFAULT 'todo', -- 'todo', 'in_progress', 'in_review', 'done', 'blocked'
    depends_on JSONB DEFAULT '[]', -- List of story UUIDs
    created_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

-- 5. Standup Reports
CREATE TABLE IF NOT EXISTS standup_reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sprint_id UUID REFERENCES sprints(id),
    agent_name VARCHAR(100),
    report_date DATE DEFAULT CURRENT_DATE,
    completed_yesterday JSONB DEFAULT '[]',
    working_on_today JSONB DEFAULT '[]',
    blockers JSONB DEFAULT '[]',
    mood VARCHAR(50), -- 'on_track', 'at_risk', 'blocked'
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 6. Agent Messages (Communication Bus Persistence)
CREATE TABLE IF NOT EXISTS agent_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sender VARCHAR(100) NOT NULL,
    channel VARCHAR(100) NOT NULL,
    content TEXT NOT NULL,
    message_type VARCHAR(50), -- 'question', 'answer', 'status', 'blocker', 'decision', etc.
    reply_to UUID, -- Self-reference
    priority VARCHAR(20) DEFAULT 'normal',
    sprint_id UUID REFERENCES sprints(id),
    story_id UUID REFERENCES user_stories(id),
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 7. Agent Memory Vectors (Semantic Memory)
CREATE TABLE IF NOT EXISTS agent_memory_vectors (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_name VARCHAR(100) NOT NULL,
    memory_type VARCHAR(50) NOT NULL, -- 'lesson', 'pattern', 'decision', 'mistake'
    content TEXT NOT NULL,
    embedding VECTOR(1536) NOT NULL, -- For OpenAI ada-002 or similar
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 8. Indexes for performance
CREATE INDEX IF NOT EXISTS idx_stories_sprint ON user_stories(sprint_id);
CREATE INDEX IF NOT EXISTS idx_messages_channel ON agent_messages(channel);
CREATE INDEX IF NOT EXISTS idx_memory_vectors_agent_type ON agent_memory_vectors(agent_name, memory_type);
CREATE INDEX IF NOT EXISTS idx_memory_vectors_embedding ON agent_memory_vectors USING hnsw (embedding vector_cosine_ops);
