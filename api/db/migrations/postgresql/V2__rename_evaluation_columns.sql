-- Rename STRATEGY_EVALUATIONS columns to match metric registry keys
-- This eliminates the need for bidirectional mappings between DB and code

ALTER TABLE STRATEGY_EVALUATIONS
    RENAME COLUMN withdrawal_adequacy_score TO pv_score;

ALTER TABLE STRATEGY_EVALUATIONS
    RENAME COLUMN wealth_building_score TO purchasing_power_score;

ALTER TABLE STRATEGY_EVALUATIONS
    RENAME COLUMN ulcer_management_score TO stability_score;

ALTER TABLE STRATEGY_EVALUATIONS
    RENAME COLUMN risk_management_score TO risk_score;

ALTER TABLE STRATEGY_EVALUATIONS
    RENAME COLUMN drawdown_resilience_score TO robustness_score;

ALTER TABLE STRATEGY_EVALUATIONS
    RENAME COLUMN psychological_resilience_score TO legacy_score;

-- capital_efficiency_score, consumption_ratio_score, and usability_score already match
