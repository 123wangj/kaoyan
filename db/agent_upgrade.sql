-- Safe additive migration for the Agent runtime. This file intentionally
-- contains no DROP statements and can be applied to an existing deployment.

CREATE TABLE IF NOT EXISTS agent_runs (
    run_id          VARCHAR(64) PRIMARY KEY,
    user_id         INTEGER REFERENCES users(id) ON DELETE CASCADE,
    goal            TEXT NOT NULL,
    status          VARCHAR(24) NOT NULL,
    confidence      REAL DEFAULT 0,
    iteration_count INTEGER DEFAULT 0,
    plan            JSONB NOT NULL DEFAULT '[]'::jsonb,
    validation      JSONB NOT NULL DEFAULT '{}'::jsonb,
    started_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    finished_at     TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_agent_runs_user_time
    ON agent_runs(user_id, started_at DESC);

CREATE TABLE IF NOT EXISTS tool_invocations (
    call_id       VARCHAR(64) PRIMARY KEY,
    run_id        VARCHAR(64) REFERENCES agent_runs(run_id) ON DELETE CASCADE,
    tool_name     VARCHAR(96) NOT NULL,
    arguments     JSONB NOT NULL DEFAULT '{}'::jsonb,
    success       BOOLEAN NOT NULL,
    duration_ms   INTEGER DEFAULT 0,
    error_message TEXT,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_tool_invocations_run ON tool_invocations(run_id);

CREATE TABLE IF NOT EXISTS semantic_memories (
    id          BIGSERIAL PRIMARY KEY,
    user_id     INTEGER REFERENCES users(id) ON DELETE CASCADE,
    category    VARCHAR(48) NOT NULL,
    memory_key  VARCHAR(160) NOT NULL,
    value       JSONB NOT NULL,
    source      VARCHAR(160) NOT NULL,
    confidence  REAL DEFAULT 0.5,
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (user_id, category, memory_key)
);

CREATE TABLE IF NOT EXISTS plan_adaptations (
    id               BIGSERIAL PRIMARY KEY,
    user_id          INTEGER REFERENCES users(id) ON DELETE CASCADE,
    question_id      INTEGER REFERENCES questions(id) ON DELETE SET NULL,
    knowledge_points JSONB NOT NULL DEFAULT '[]'::jsonb,
    affected_tasks   JSONB NOT NULL DEFAULT '[]'::jsonb,
    reason           VARCHAR(96) NOT NULL,
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
