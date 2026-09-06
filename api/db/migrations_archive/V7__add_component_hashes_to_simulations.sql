-- Adds the component_hashes column to the new CACHED_SIMULATIONS table for version tracking.
ALTER TABLE CACHED_SIMULATIONS ADD COLUMN component_hashes TEXT;