-- Schema rules fixture: io constraints in SQL DDL.

CREATE TABLE accounts (
  id INTEGER PRIMARY KEY,
  email VARCHAR(255) NOT NULL,
  balance NUMERIC DEFAULT 0 CHECK (balance >= 0)
);
