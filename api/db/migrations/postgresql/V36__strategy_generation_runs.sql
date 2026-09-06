-- W5 agentic strategy generation: run tracking + build-log event trace.
-- Events are the authoritative build log (UI rehydration + prompt tuning);
-- the langgraph checkpointer owns graph resume state separately.

CREATE TABLE IF NOT EXISTS STRATEGY_GENERATION_RUNS (
    id UUID PRIMARY KEY,
    user_id INTEGER NOT NULL,
    thread_id TEXT NOT NULL,
    -- running | needs_input | completed | failed | discarded
    status TEXT NOT NULL DEFAULT 'running',
    user_request TEXT NOT NULL,
    strategy_name TEXT,
    seed_strategy_id INTEGER,
    spec JSONB,
    final_strategy_id INTEGER,
    failure_summary TEXT,
    llm_calls INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES USERS(id)
);

CREATE INDEX IF NOT EXISTS idx_sgr_user_created
    ON STRATEGY_GENERATION_RUNS(user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS STRATEGY_GENERATION_EVENTS (
    run_id UUID NOT NULL REFERENCES STRATEGY_GENERATION_RUNS(id) ON DELETE CASCADE,
    seq INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    payload JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (run_id, seq)
);
