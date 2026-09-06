-- V3: Creates the table for storing user-generated custom strategies.
CREATE TABLE IF NOT EXISTS CUSTOM_STRATEGIES (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INT NOT NULL,
    strategy_name VARCHAR(255) NOT NULL,
    class_name VARCHAR(255) NOT NULL,
    description TEXT,
    code TEXT NOT NULL,
    is_shared BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES USERS(id)
);