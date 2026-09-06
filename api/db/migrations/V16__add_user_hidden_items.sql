-- V16__add_user_hidden_items.sql
-- Table to track items (simulations/strategies) hidden by users from their view

CREATE TABLE IF NOT EXISTS USER_HIDDEN_ITEMS (
    user_id INTEGER NOT NULL REFERENCES USERS(id),
    item_type TEXT NOT NULL, -- 'simulation' or 'strategy'
    item_id INTEGER NOT NULL,
    hidden_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, item_type, item_id)
);

CREATE INDEX IF NOT EXISTS idx_hidden_items_user ON USER_HIDDEN_ITEMS(user_id);
