-- V21__protect_public_content_from_deletion.sql
-- Add database-level triggers to prevent deletion of public content
-- This ensures public content cannot be deleted even if the application layer fails

-- Function to protect public simulations from deletion
CREATE OR REPLACE FUNCTION prevent_public_simulation_deletion()
RETURNS TRIGGER AS $$
BEGIN
    IF OLD.is_public = TRUE THEN
        RAISE EXCEPTION 'Cannot delete public simulation (simulation_hash: %)', OLD.simulation_hash;
    END IF;
    RETURN OLD;
END;
$$ LANGUAGE plpgsql;

-- Trigger on CACHED_SIMULATIONS
DROP TRIGGER IF EXISTS protect_public_simulations_trigger ON CACHED_SIMULATIONS;
CREATE TRIGGER protect_public_simulations_trigger
    BEFORE DELETE ON CACHED_SIMULATIONS
    FOR EACH ROW
    EXECUTE FUNCTION prevent_public_simulation_deletion();

-- Function to protect public strategies from deletion
CREATE OR REPLACE FUNCTION prevent_public_strategy_deletion()
RETURNS TRIGGER AS $$
BEGIN
    IF OLD.is_public = TRUE OR OLD.is_published_to_leaderboard = TRUE THEN
        RAISE EXCEPTION 'Cannot delete public or published strategy (id: %, name: %)', OLD.id, OLD.strategy_name;
    END IF;
    RETURN OLD;
END;
$$ LANGUAGE plpgsql;

-- Trigger on CUSTOM_STRATEGIES
DROP TRIGGER IF EXISTS protect_public_strategies_trigger ON CUSTOM_STRATEGIES;
CREATE TRIGGER protect_public_strategies_trigger
    BEFORE DELETE ON CUSTOM_STRATEGIES
    FOR EACH ROW
    EXECUTE FUNCTION prevent_public_strategy_deletion();

-- Add helpful comments
COMMENT ON FUNCTION prevent_public_simulation_deletion() IS 'Prevents deletion of simulations marked as public (is_public=TRUE)';
COMMENT ON FUNCTION prevent_public_strategy_deletion() IS 'Prevents deletion of strategies marked as public or published to leaderboard';
