-- V43__llm_usage.sql
-- One row per LLM (Gemini) call, recorded at the single chokepoint
-- core.llm.call_gemini_safe so nothing can bypass it: the strategy designer
-- (create + evolve), strategy Q&A, and simulation-report analysis.
--
-- A user-facing "operation" (one strategy creation, one evolution, one Q&A
-- answer, one report analysis) spans several calls; they share (operation,
-- ref_id) so cost-per-operation is a GROUP BY. cost_usd is computed at insert
-- time from core.llm_pricing at that day's list price, so history doesn't
-- shift when Google reprices; the token columns let it be recomputed.

CREATE TABLE IF NOT EXISTS LLM_USAGE (
    id BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    user_id INTEGER REFERENCES USERS(id) ON DELETE SET NULL,
    -- strategy_create | strategy_evolve | strategy_qa | report_analysis | unknown
    operation TEXT NOT NULL,
    -- generation run id / Q&A message id / simulation hash: groups the
    -- calls of one operation
    ref_id TEXT,
    -- graph node (extract_spec, plan, generate, ...) or caller-defined label
    step TEXT,
    tier TEXT,
    model TEXT NOT NULL,
    prompt_tokens INTEGER NOT NULL DEFAULT 0,
    cached_tokens INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    thinking_tokens INTEGER NOT NULL DEFAULT 0,
    -- NULL when the model has no entry in core.llm_pricing (surfaced in admin)
    cost_usd NUMERIC(12, 8),
    latency_ms INTEGER,
    ok BOOLEAN NOT NULL DEFAULT TRUE,
    error TEXT
);

CREATE INDEX IF NOT EXISTS idx_llm_usage_created ON LLM_USAGE(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_llm_usage_user_created ON LLM_USAGE(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_llm_usage_op_ref ON LLM_USAGE(operation, ref_id);
