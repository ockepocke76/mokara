CREATE TABLE IF NOT EXISTS LOGS (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    level VARCHAR(50),
    logger_name VARCHAR(255),
    message TEXT,
    user_email VARCHAR(255),
    exception_details TEXT,
    is_reviewed BOOLEAN DEFAULT FALSE
);