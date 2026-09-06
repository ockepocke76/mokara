-- Add a new column to store the AI-generated description for a custom strategy.
ALTER TABLE CUSTOM_STRATEGIES ADD COLUMN ai_description TEXT;