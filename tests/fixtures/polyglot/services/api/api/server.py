"""API server for the polyglot fixture.

Binds a port and talks to Postgres so the scanner emits http and database
relationships.
"""

import os

import psycopg2
from fastapi import FastAPI

app = FastAPI()

DATABASE_URL = os.environ.get("DATABASE_URL", "postgres://db:5432/app")
PORT = 8000


class UserRepository:
    """Reads and writes user rows in Postgres."""

    def __init__(self, dsn: str) -> None:
        self.conn = psycopg2.connect(dsn)

    def get_user(self, user_id: int) -> dict:
        """Fetch a single user by id."""
        cur = self.conn.cursor()
        cur.execute("SELECT id, name FROM users WHERE id = %s", (user_id,))
        row = cur.fetchone()
        return {"id": row[0], "name": row[1]}


@app.get("/users/{user_id}")
def read_user(user_id: int) -> dict:
    """HTTP endpoint returning a user."""
    repo = UserRepository(DATABASE_URL)
    return repo.get_user(user_id)


def serve() -> None:
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=PORT)
