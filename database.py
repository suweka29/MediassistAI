"""
MediAssistAI - SQLite session storage
Stores chat sessions: extracted symptoms, asked follow-ups, predictions.
"""
import json
import os
import sqlite3
import time
import uuid

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "mediassist.db")


def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _conn() as c:
        c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            username     TEXT PRIMARY KEY,
            password_hash TEXT,
            salt         TEXT,
            display_name TEXT,
            created_at   REAL
        )""")
        c.execute("""
        CREATE TABLE IF NOT EXISTS auth_tokens (
            token        TEXT PRIMARY KEY,
            username     TEXT,
            created_at   REAL
        )""")
        c.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            session_id   TEXT PRIMARY KEY,
            username     TEXT,
            created_at   REAL,
            updated_at   REAL,
            age          INTEGER,
            gender       TEXT,
            duration_days INTEGER,
            severity     INTEGER,
            symptoms     TEXT,   -- JSON list of canonical symptoms
            asked        TEXT,   -- JSON list of symptoms already asked
            followups    INTEGER DEFAULT 0,
            last_result  TEXT    -- JSON of last engine result
        )""")
        c.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            role TEXT,
            content TEXT,
            created_at REAL
        )""")
        # lightweight migration for DBs created before the `username` column existed
        cols = [r["name"] for r in c.execute("PRAGMA table_info(sessions)")]
        if "username" not in cols:
            c.execute("ALTER TABLE sessions ADD COLUMN username TEXT")


# --------------------------------------------------------------------- users
def create_user(username, password_hash, salt, display_name):
    with _conn() as c:
        c.execute("""INSERT INTO users
                     (username, password_hash, salt, display_name, created_at)
                     VALUES (?,?,?,?,?)""",
                  (username, password_hash, salt, display_name, time.time()))


def get_user(username):
    with _conn() as c:
        row = c.execute("SELECT * FROM users WHERE username=?",
                        (username,)).fetchone()
    return dict(row) if row else None


def create_token(username):
    token = uuid.uuid4().hex + uuid.uuid4().hex
    with _conn() as c:
        c.execute("INSERT INTO auth_tokens (token, username, created_at) "
                  "VALUES (?,?,?)", (token, username, time.time()))
    return token


def get_username_from_token(token):
    with _conn() as c:
        row = c.execute("SELECT username FROM auth_tokens WHERE token=?",
                        (token,)).fetchone()
    return row["username"] if row else None


def delete_token(token):
    with _conn() as c:
        c.execute("DELETE FROM auth_tokens WHERE token=?", (token,))


def list_user_sessions(username):
    with _conn() as c:
        rows = c.execute("SELECT session_id, created_at, updated_at FROM "
                         "sessions WHERE username=? ORDER BY updated_at DESC",
                         (username,)).fetchall()
    return [dict(r) for r in rows]


def create_session(age=35, gender="male", duration_days=3, severity=5,
                   username=None):
    sid = uuid.uuid4().hex[:12]
    now = time.time()
    with _conn() as c:
        c.execute("""INSERT INTO sessions
                     (session_id, username, created_at, updated_at, age, gender,
                      duration_days, severity, symptoms, asked)
                     VALUES (?,?,?,?,?,?,?,?,?,?)""",
                  (sid, username, now, now, age, gender, duration_days,
                   severity, "[]", "[]"))
    return sid


def get_session(sid):
    with _conn() as c:
        row = c.execute("SELECT * FROM sessions WHERE session_id=?",
                        (sid,)).fetchone()
    if not row:
        return None
    d = dict(row)
    d["symptoms"] = json.loads(d["symptoms"])
    d["asked"] = json.loads(d["asked"])
    d["last_result"] = json.loads(d["last_result"]) if d["last_result"] else None
    return d


def update_session(sid, **fields):
    fields["updated_at"] = time.time()
    for k in ("symptoms", "asked", "last_result"):
        if k in fields and not isinstance(fields[k], str):
            fields[k] = json.dumps(fields[k])
    cols = ", ".join(f"{k}=?" for k in fields)
    with _conn() as c:
        c.execute(f"UPDATE sessions SET {cols} WHERE session_id=?",
                  (*fields.values(), sid))


def log_message(sid, role, content):
    with _conn() as c:
        c.execute("INSERT INTO messages (session_id, role, content, created_at)"
                  " VALUES (?,?,?,?)", (sid, role, content, time.time()))


def get_history(sid):
    with _conn() as c:
        rows = c.execute("SELECT role, content, created_at FROM messages "
                         "WHERE session_id=? ORDER BY id", (sid,)).fetchall()
    return [dict(r) for r in rows]
