-- Migration V14: Add Capital Efficiency metric to strategy evaluations
-- Adds: capital_efficiency_score (replaces adequacy/usability in weighting)

ALTER TABLE STRATEGY_EVALUATIONS ADD COLUMN capital_efficiency_score REAL DEFAULT 0;
