-- Add the mean_final_net_worth column to the STATISTICS table
-- This is necessary for storing a key metric and was missed in the initial table creation.

ALTER TABLE STATISTICS ADD COLUMN mean_final_net_worth FLOAT;