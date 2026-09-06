-- V17__add_ulcer_index_columns.sql
-- NO-OP: STATISTICS table was renamed to STATISTICS_OLD in V6.
-- Ulcer Index metrics are now stored in the stats JSON blob in SIMULATION_RESULTS.
-- This migration is kept for version tracking but does nothing.

SELECT 1; -- No-op query to make migration valid
