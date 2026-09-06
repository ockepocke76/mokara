-- Migration V35: Add columns for new scoring metrics
-- Phase 2: Sharpe Ratio, Calmar Ratio, Downside Stability, Ulcer Index

ALTER TABLE STRATEGY_EVALUATIONS 
    ADD COLUMN IF NOT EXISTS sharpe_ratio_score FLOAT,
    ADD COLUMN IF NOT EXISTS calmar_ratio_score FLOAT,
    ADD COLUMN IF NOT EXISTS downside_stability_score FLOAT,
    ADD COLUMN IF NOT EXISTS ulcer_index_score FLOAT;

-- Also add to profile scores table for pre-calculated profile scores
ALTER TABLE STRATEGY_PROFILE_SCORES
    ADD COLUMN IF NOT EXISTS sharpe_ratio_score FLOAT,
    ADD COLUMN IF NOT EXISTS calmar_ratio_score FLOAT,
    ADD COLUMN IF NOT EXISTS downside_stability_score FLOAT,
    ADD COLUMN IF NOT EXISTS ulcer_index_score FLOAT;
