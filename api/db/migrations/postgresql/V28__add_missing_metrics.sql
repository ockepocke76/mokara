-- V29__add_missing_metrics.sql
-- Add Sharpe and Sortino ratios which are expected by the application but missing from schema

ALTER TABLE STRATEGY_EVALUATIONS ADD COLUMN sharpe_ratio REAL;
ALTER TABLE STRATEGY_EVALUATIONS ADD COLUMN sortino_ratio REAL;

CREATE INDEX idx_eval_sharpe ON STRATEGY_EVALUATIONS(sharpe_ratio DESC);
CREATE INDEX idx_eval_sortino ON STRATEGY_EVALUATIONS(sortino_ratio DESC);
