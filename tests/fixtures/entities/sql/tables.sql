CREATE TABLE invoices (
    id INTEGER PRIMARY KEY,
    number TEXT NOT NULL,
    amount NUMERIC,
    customer_id INTEGER
);

CREATE TABLE IF NOT EXISTS customers (
    id INTEGER PRIMARY KEY,
    name TEXT,
    email TEXT
);
