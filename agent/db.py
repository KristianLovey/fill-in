import os
import sqlite3
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(ROOT, "data", "fillin.db")
SCHEMA_PATH = os.path.join(ROOT, "data", "schema.sql")


def now():
    """Single source of truth for time, so tests and demos stay reproducible."""
    return datetime.now(timezone.utc).replace(microsecond=0)


def iso(dt):
    return dt.isoformat()


def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        schema = f.read()
    conn = connect()
    conn.executescript(schema)
    conn.commit()
    conn.close()


def query(sql, params=()):
    conn = connect()
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def execute(sql, params=()):
    conn = connect()
    cur = conn.execute(sql, params)
    conn.commit()
    last_id = cur.lastrowid
    conn.close()
    return last_id


def log_event(kind, detail, shift_id=None):
    """Every autonomous action lands here. The dashboard reads this table."""
    execute(
        "INSERT INTO events (ts, shift_id, kind, detail) VALUES (?, ?, ?, ?)",
        (iso(now()), shift_id, kind, detail),
    )