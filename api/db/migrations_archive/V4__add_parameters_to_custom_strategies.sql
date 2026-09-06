-- V4: Adds a column to store detailed parameter configurations for custom strategies.
ALTER TABLE CUSTOM_STRATEGIES ADD COLUMN parameters_json TEXT;