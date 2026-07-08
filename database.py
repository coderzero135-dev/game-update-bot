"""Game Update Bot - SQLite Database"""

import sqlite3
import json
import time
import threading

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
        CREATE TABLE IF NOT EXISTS watches (
            user_id INTEGER NOT NULL,
            game_id TEXT NOT NULL,
            PRIMARY KEY (user_id, game_id)
        );
        CREATE TABLE IF NOT EXISTS role_pings (
            role_id INTEGER NOT NULL,
            game_id TEXT NOT NULL,
            channel_id INTEGER NOT NULL,
            PRIMARY KEY (role_id, game_id)
        );
        CREATE TABLE IF NOT EXISTS update_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id TEXT NOT NULL,
            ts REAL NOT NULL,
            title TEXT DEFAULT '',
            url TEXT DEFAULT '',
            src TEXT DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_cache_ts ON cache(ts);
        CREATE INDEX IF NOT EXISTS idx_history_game ON update_history(game_id, ts);
        CREATE INDEX IF NOT EXISTS idx_watches_user ON watches(user_id);
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
    get_db().execute("DELETE FROM cache").connection.commit()


def build_version_get(appid: str) -> dict | None:
    row = get_db().execute("SELECT * FROM build_versions WHERE appid = ?", (appid,)).fetchone()
    return {"version": row["version"], "message": row["message"], "ts": row["last_seen_ts"]} if row else None


def build_version_set(appid: str, version: int, message: str) -> None:
    db = get_db()
    db.execute(
        "INSERT OR REPLACE INTO build_versions (appid, version, message, last_seen_ts) VALUES (?, ?, ?, ?)",
        (appid, version, message, time.time()),
    )
    db.commit()


def config_get(key: str, default=None):
    row = get_db().execute("SELECT value FROM bot_config WHERE key = ?", (key,)).fetchone()
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


# --- Watches ---

def watch_add(user_id: int, game_id: str) -> bool:
    try:
        get_db().execute("INSERT OR IGNORE INTO watches VALUES (?, ?)", (user_id, game_id)).connection.commit()
        return True
    except:
        return False


def watch_remove(user_id: int, game_id: str) -> bool:
    get_db().execute("DELETE FROM watches WHERE user_id = ? AND game_id = ?", (user_id, game_id)).connection.commit()
    return True


def watch_get_users(game_id: str) -> list[int]:
    rows = get_db().execute("SELECT user_id FROM watches WHERE game_id = ?", (game_id,)).fetchall()
    return [r[0] for r in rows]


def watch_get_games(user_id: int) -> list[str]:
    rows = get_db().execute("SELECT game_id FROM watches WHERE user_id = ?", (user_id,)).fetchall()
    return [r[0] for r in rows]


# --- Role Pings ---

def role_add(role_id: int, game_id: str, channel_id: int) -> None:
    get_db().execute(
        "INSERT OR REPLACE INTO role_pings VALUES (?, ?, ?)", (role_id, game_id, channel_id)
    ).connection.commit()


def role_remove(role_id: int, game_id: str) -> None:
    get_db().execute("DELETE FROM role_pings WHERE role_id = ? AND game_id = ?", (role_id, game_id)).connection.commit()


def role_get_for_game(game_id: str) -> list[tuple[int, int]]:
    """Returns list of (role_id, channel_id) for a game."""
    rows = get_db().execute(
        "SELECT role_id, channel_id FROM role_pings WHERE game_id = ?", (game_id,)
    ).fetchall()
    return [(r[0], r[1]) for r in rows]


# --- Update History ---

def history_add(game_id: str, ts: int, title: str, url: str, src: str) -> None:
    db = get_db()
    # Keep max 10 entries per game
    count = db.execute("SELECT COUNT(*) FROM update_history WHERE game_id = ?", (game_id,)).fetchone()[0]
    if count >= 10:
        db.execute(
            "DELETE FROM update_history WHERE id = (SELECT MIN(id) FROM update_history WHERE game_id = ?)",
            (game_id,),
        )
    db.execute(
        "INSERT INTO update_history (game_id, ts, title, url, src) VALUES (?, ?, ?, ?, ?)",
        (game_id, ts, title, url, src),
    )
    db.commit()


def history_get(game_id: str, limit: int = 10) -> list[dict]:
    rows = get_db().execute(
        "SELECT ts, title, url, src FROM update_history WHERE game_id = ? ORDER BY ts DESC LIMIT ?",
        (game_id, limit),
    ).fetchall()
    return [{"ts": r["ts"], "title": r["title"], "url": r["url"], "src": r["src"]} for r in rows]
