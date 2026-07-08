"""Game Update Bot - SQLite Database"""

import sqlite3
import json
import time
import threading
from contextlib import contextmanager

from config import DB_PATH

_local = threading.local()


def get_db() -> sqlite3.Connection:
    if not hasattr(_local, "conn") or _local.conn is None:
        _local.conn = sqlite3.connect(DB_PATH)
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute("PRAGMA journal_mode=WAL")
        _local.conn.execute("PRAGMA busy_timeout=5000")
    return _local.conn


def init_db():
    db = get_db()
    db.executescript("""
        CREATE TABLE IF NOT EXISTS cache (
            key TEXT PRIMARY KEY,
            data TEXT NOT NULL,
            ts REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS build_versions (
            appid TEXT PRIMARY KEY,
            version INTEGER NOT NULL,
            message TEXT DEFAULT '',
            last_seen_ts REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS bot_config (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS game_tags (
            game_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            tag TEXT DEFAULT 'other',
            is_steam INTEGER DEFAULT 1
        );
        CREATE INDEX IF NOT EXISTS idx_cache_ts ON cache(ts);
    """)
    db.commit()


def cache_get(key: str, ttl: float) -> dict | None:
    db = get_db()
    row = db.execute("SELECT data, ts FROM cache WHERE key = ?", (key,)).fetchone()
    if row and time.time() - row["ts"] < ttl:
        return json.loads(row["data"])
    return None


def cache_set(key: str, data: dict) -> None:
    db = get_db()
    db.execute(
        "INSERT OR REPLACE INTO cache (key, data, ts) VALUES (?, ?, ?)",
        (key, json.dumps(data), time.time()),
    )
    db.commit()


def cache_clear() -> None:
    db = get_db()
    db.execute("DELETE FROM cache")
    db.commit()


def build_version_get(appid: str) -> dict | None:
    db = get_db()
    row = db.execute("SELECT * FROM build_versions WHERE appid = ?", (appid,)).fetchone()
    if row:
        return {"version": row["version"], "message": row["message"], "ts": row["last_seen_ts"]}
    return None


def build_version_set(appid: str, version: int, message: str) -> None:
    db = get_db()
    db.execute(
        "INSERT OR REPLACE INTO build_versions (appid, version, message, last_seen_ts) VALUES (?, ?, ?, ?)",
        (appid, version, message, time.time()),
    )
    db.commit()


def config_get(key: str, default=None):
    db = get_db()
    row = db.execute("SELECT value FROM bot_config WHERE key = ?", (key,)).fetchone()
    if row:
        try:
            return json.loads(row["value"])
        except Exception:
            return row["value"]
    return default


def config_set(key: str, value) -> None:
    db = get_db()
    if not isinstance(value, str):
        value = json.dumps(value)
    db.execute("INSERT OR REPLACE INTO bot_config (key, value) VALUES (?, ?)", (key, value))
    db.commit()


def init_game_tags():
    """Seed game tags from config defaults if table is empty."""
    db = get_db()
    count = db.execute("SELECT COUNT(*) FROM game_tags").fetchone()[0]
    if count > 0:
        return

    from config import load_games
    games = load_games()
    for appid, name in games.get("steam", {}).items():
        db.execute(
            "INSERT OR IGNORE INTO game_tags (game_id, name, tag, is_steam) VALUES (?, ?, ?, 1)",
            (appid, name, "fps"),
        )
    for key, name in games.get("non_steam", {}).items():
        db.execute(
            "INSERT OR IGNORE INTO game_tags (game_id, name, tag, is_steam) VALUES (?, ?, ?, 0)",
            (key, name, "fps"),
        )
    db.commit()
