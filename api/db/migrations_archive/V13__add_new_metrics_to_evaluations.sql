-- Migration V13: Add new granular scoring metrics to strategy evaluations
-- Adds: pv_score, purchasing_power_score, stability_score, adequacy_score, usability_score, legacy_score

ALTER TABLE STRATEGY_EVALUATIONS ADD COLUMN pv_score REAL DEFAULT 0;
ALTER TABLE STRATEGY_EVALUATIONS ADD COLUMN purchasing_power_score REAL DEFAULT 0;
ALTER TABLE STRATEGY_EVALUATIONS ADD COLUMN stability_score REAL DEFAULT 0;
ALTER TABLE STRATEGY_EVALUATIONS ADD COLUMN adequacy_score REAL DEFAULT 0;
ALTER TABLE STRATEGY_EVALUATIONS ADD COLUMN usability_score REAL DEFAULT 0;
ALTER TABLE STRATEGY_EVALUATIONS ADD COLUMN legacy_score REAL DEFAULT 0;
