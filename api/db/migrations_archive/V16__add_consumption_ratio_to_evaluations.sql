-- Migration V16: Add Consumption Ratio metric to strategy evaluations
-- Adds: consumption_ratio_score (key metric for "Die With Zero" strategies)
-- This measures pure withdrawal efficiency without counting legacy

ALTER TABLE STRATEGY_EVALUATIONS ADD COLUMN consumption_ratio_score REAL DEFAULT 0;
