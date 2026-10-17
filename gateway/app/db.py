"""SQLite storage. One connection, guarded by a lock.

SQLite on a PersistentVolume is enough for a single gateway replica. Running several
replicas would mean moving to Postgres (documented tradeoff).
"""
import sqlite3
import threading
import time

from . import config

_lock = threading.Lock()
_conn: sqlite3.Connection | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('admin', 'member')),
    disabled      INTEGER NOT NULL DEFAULT 0,
    created_at    REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS api_keys (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id),
    name       TEXT NOT NULL,
    prefix     TEXT NOT NULL,
    key_hash   TEXT NOT NULL UNIQUE,
    created_at REAL NOT NULL,
    revoked_at REAL
);
CREATE TABLE IF NOT EXISTS servers (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    slug             TEXT NOT NULL UNIQUE,
    url              TEXT NOT NULL,
    auth_type        TEXT NOT NULL DEFAULT 'none' CHECK (auth_type IN ('none', 'bearer', 'header')),
    auth_header_name TEXT,
    credential       TEXT,
    enabled          INTEGER NOT NULL DEFAULT 1,
    status           TEXT NOT NULL DEFAULT 'unknown',
    status_detail    TEXT,
    last_checked     REAL,
    tools_json       TEXT NOT NULL DEFAULT '[]',
    created_at       REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS audit (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          REAL NOT NULL,
    user_id     INTEGER,
    user_email  TEXT NOT NULL,
    server      TEXT NOT NULL,
    tool        TEXT NOT NULL,
    duration_ms INTEGER NOT NULL,
    outcome     TEXT NOT NULL,
    detail      TEXT
);
CREATE INDEX IF NOT EXISTS audit_ts ON audit(ts DESC);
"""


def init() -> None:
    global _conn
    _conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
    _conn.row_factory = sqlite3.Row
    with _lock:
        _conn.executescript(SCHEMA)
        _conn.commit()


def query(sql: str, args: tuple = ()) -> list[dict]:
    with _lock:
        return [dict(r) for r in _conn.execute(sql, args).fetchall()]


def one(sql: str, args: tuple = ()) -> dict | None:
    rows = query(sql, args)
    return rows[0] if rows else None


def execute(sql: str, args: tuple = ()) -> int:
    """Run a write and return the new row id (or 0)."""
    with _lock:
        cur = _conn.execute(sql, args)
        _conn.commit()
        return cur.lastrowid or 0


def now() -> float:
    return time.time()