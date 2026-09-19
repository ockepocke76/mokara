-- Q&A about a strategy's observed behavior: one thread per user per subject.
-- A subject is either a strategy-generation run (the designer's build, whose
-- events already hold the code and test-flight results) or a completed
-- simulation (its hash). Messages are the conversation; assistant messages
-- keep the triage verdict and any change the answer proposed.

CREATE TABLE IF NOT EXISTS QA_THREADS (
    id UUID PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES USERS(id) ON DELETE CASCADE,
    subject_type TEXT NOT NULL CHECK (subject_type IN ('generation_run', 'simulation')),
    subject_id TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (user_id, subject_type, subject_id)
);

CREATE TABLE IF NOT EXISTS QA_MESSAGES (
    id SERIAL PRIMARY KEY,
    thread_id UUID NOT NULL REFERENCES QA_THREADS(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    -- Triage verdict for the user turn that produced this assistant turn;
    -- NULL on user messages.
    on_topic BOOLEAN,
    -- {summary, refine_feedback} when the answer proposed a concrete change.
    suggested_change JSONB,
    llm_calls INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_qa_messages_thread
    ON QA_MESSAGES(thread_id, id);
