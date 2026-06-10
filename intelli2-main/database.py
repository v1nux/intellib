"""
IntelliBreak — Database Module
SQLite persistence for users, sessions, breaks, and predictions.
"""

import sqlite3
import os
from datetime import datetime, timezone
from werkzeug.security import generate_password_hash, check_password_hash

DB_PATH = os.path.join(os.path.dirname(__file__), "intellibreak.db")


def _utcnow():
    """Get current UTC time (naive) without using deprecated utcnow()."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def get_connection():
    """Get a database connection with row_factory for dict-like access."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """Create all tables if they don't exist."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            full_name TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            activity_type TEXT NOT NULL,
            target_duration_minutes INTEGER NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT,
            total_duration_minutes REAL,
            focus_time_minutes REAL,
            break_count INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS breaks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT,
            duration_minutes REAL,
            is_active INTEGER DEFAULT 1,
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        );

        CREATE TABLE IF NOT EXISTS predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            prediction_type TEXT NOT NULL,
            rf_prediction TEXT,
            dt_prediction TEXT,
            knn_prediction TEXT,
            best_prediction TEXT,
            best_algorithm TEXT,
            avg_daily_work_hours REAL,
            break_frequency REAL,
            focus_time REAL,
            late_task_ratio REAL,
            feedback_score REAL,
            recommendation TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (session_id) REFERENCES sessions(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
    """)

    conn.commit()
    conn.close()
    print("[DB] Database initialized successfully.")


# =========================================
# User Operations
# =========================================

def create_user(username, password, full_name):
    """Create a new user. Returns user dict or None if username exists."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO users (username, password, full_name) VALUES (?, ?, ?)",
            (username, generate_password_hash(password), full_name)
        )
        conn.commit()
        user_id = cursor.lastrowid
        return get_user_by_id(user_id)
    except sqlite3.IntegrityError:
        return None
    finally:
        conn.close()


def get_user_by_username(username):
    """Find a user by username."""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM users WHERE username = ?", (username,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_by_id(user_id):
    """Find a user by ID."""
    conn = get_connection()
    row = conn.execute(
        "SELECT id, username, full_name, created_at FROM users WHERE id = ?",
        (user_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def verify_password(user, password):
    """Verify a password against the stored hash. Supports legacy plaintext for migration."""
    if not user or not user.get("password"):
        return False
    stored = user["password"]
    # Support hashed passwords (werkzeug format)
    if stored.startswith("scrypt:") or stored.startswith("pbkdf2:"):
        return check_password_hash(stored, password)
    # Legacy plaintext comparison (for existing accounts before hashing was added)
    return stored == password


# =========================================
# Session Operations
# =========================================

def create_session(user_id, activity_type, target_duration_minutes):
    """Start a new focus session."""
    conn = get_connection()
    now = _utcnow().isoformat()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO sessions
           (user_id, activity_type, target_duration_minutes, start_time)
           VALUES (?, ?, ?, ?)""",
        (user_id, activity_type, target_duration_minutes, now)
    )
    conn.commit()
    session_id = cursor.lastrowid
    conn.close()
    return get_session_by_id(session_id)


def get_session_by_id(session_id):
    """Get a session by its ID."""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM sessions WHERE id = ?", (session_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_active_session(user_id):
    """Get the currently active session for a user."""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM sessions WHERE user_id = ? AND is_active = 1 ORDER BY id DESC LIMIT 1",
        (user_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def end_session(session_id):
    """End an active session, computing total and focus durations."""
    conn = get_connection()
    session = conn.execute(
        "SELECT * FROM sessions WHERE id = ?", (session_id,)
    ).fetchone()

    if not session:
        conn.close()
        return None

    now = _utcnow()
    start = datetime.fromisoformat(session["start_time"])
    total_minutes = (now - start).total_seconds() / 60.0

    # Calculate total break time for this session
    break_rows = conn.execute(
        "SELECT * FROM breaks WHERE session_id = ? AND end_time IS NOT NULL",
        (session_id,)
    ).fetchall()

    total_break_minutes = 0.0
    for b in break_rows:
        if b["duration_minutes"]:
            total_break_minutes += b["duration_minutes"]

    # End any still-active break
    active_break = conn.execute(
        "SELECT * FROM breaks WHERE session_id = ? AND is_active = 1",
        (session_id,)
    ).fetchone()
    if active_break:
        b_start = datetime.fromisoformat(active_break["start_time"])
        b_dur = (now - b_start).total_seconds() / 60.0
        conn.execute(
            "UPDATE breaks SET end_time = ?, duration_minutes = ?, is_active = 0 WHERE id = ?",
            (now.isoformat(), b_dur, active_break["id"])
        )
        total_break_minutes += b_dur

    focus_minutes = max(0, total_minutes - total_break_minutes)
    break_count = conn.execute(
        "SELECT COUNT(*) as cnt FROM breaks WHERE session_id = ?",
        (session_id,)
    ).fetchone()["cnt"]

    conn.execute(
        """UPDATE sessions
           SET end_time = ?, total_duration_minutes = ?, focus_time_minutes = ?,
               break_count = ?, is_active = 0
           WHERE id = ?""",
        (now.isoformat(), round(total_minutes, 2), round(focus_minutes, 2),
         break_count, session_id)
    )
    conn.commit()
    result = get_session_by_id(session_id)
    conn.close()
    return result


def get_user_sessions(user_id, limit=50):
    """Get session history for a user, most recent first."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT s.*, p.best_prediction, p.best_algorithm, p.recommendation,
                  p.rf_prediction, p.dt_prediction, p.knn_prediction
           FROM sessions s
           LEFT JOIN predictions p ON p.session_id = s.id AND p.prediction_type = 'final'
           WHERE s.user_id = ?
           ORDER BY s.id DESC LIMIT ?""",
        (user_id, limit)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# =========================================
# Break Operations
# =========================================

def start_break(session_id):
    """Start a break within a session."""
    conn = get_connection()
    now = _utcnow().isoformat()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO breaks (session_id, start_time) VALUES (?, ?)",
        (session_id, now)
    )
    conn.commit()
    break_id = cursor.lastrowid
    row = conn.execute("SELECT * FROM breaks WHERE id = ?", (break_id,)).fetchone()
    conn.close()
    return dict(row)


def end_break(session_id):
    """End the active break in a session."""
    conn = get_connection()
    active = conn.execute(
        "SELECT * FROM breaks WHERE session_id = ? AND is_active = 1 ORDER BY id DESC LIMIT 1",
        (session_id,)
    ).fetchone()

    if not active:
        conn.close()
        return None

    now = _utcnow()
    b_start = datetime.fromisoformat(active["start_time"])
    duration = (now - b_start).total_seconds() / 60.0

    conn.execute(
        "UPDATE breaks SET end_time = ?, duration_minutes = ?, is_active = 0 WHERE id = ?",
        (now.isoformat(), round(duration, 2), active["id"])
    )
    conn.commit()
    row = conn.execute("SELECT * FROM breaks WHERE id = ?", (active["id"],)).fetchone()
    conn.close()
    return dict(row)


def get_session_breaks(session_id):
    """Get all breaks for a session."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM breaks WHERE session_id = ? ORDER BY id", (session_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def has_active_break(session_id):
    """Check if there's an active break in a session."""
    conn = get_connection()
    row = conn.execute(
        "SELECT COUNT(*) as cnt FROM breaks WHERE session_id = ? AND is_active = 1",
        (session_id,)
    ).fetchone()
    conn.close()
    return row["cnt"] > 0


# =========================================
# Prediction Operations
# =========================================

def save_prediction(session_id, user_id, prediction_type, rf_pred, dt_pred,
                    knn_pred, best_pred, best_algo, features, recommendation):
    """Save an ML prediction result."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO predictions
           (session_id, user_id, prediction_type,
            rf_prediction, dt_prediction, knn_prediction,
            best_prediction, best_algorithm,
            avg_daily_work_hours, break_frequency, focus_time,
            late_task_ratio, feedback_score, recommendation)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (session_id, user_id, prediction_type,
         rf_pred, dt_pred, knn_pred, best_pred, best_algo,
         features["average_daily_work_hours"],
         features["break_frequency_per_day"],
         features["focus_time_minutes"],
         features["late_task_ratio"],
         features["real_time_feedback_score"],
         recommendation)
    )
    conn.commit()
    pred_id = cursor.lastrowid
    conn.close()
    return pred_id


def get_session_predictions(session_id):
    """Get all predictions for a session."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM predictions WHERE session_id = ? ORDER BY id",
        (session_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_user_prediction_history(user_id, limit=50):
    """Get prediction history for a user."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT p.*, s.activity_type, s.target_duration_minutes
           FROM predictions p
           JOIN sessions s ON s.id = p.session_id
           WHERE p.user_id = ? AND p.prediction_type = 'final'
           ORDER BY p.id DESC LIMIT ?""",
        (user_id, limit)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# =========================================
# Dashboard / Stats
# =========================================

def get_user_stats(user_id):
    """Get aggregate stats for the dashboard."""
    conn = get_connection()

    total = conn.execute(
        "SELECT COUNT(*) as cnt FROM sessions WHERE user_id = ? AND is_active = 0",
        (user_id,)
    ).fetchone()["cnt"]

    avg_duration = conn.execute(
        "SELECT AVG(total_duration_minutes) as avg FROM sessions WHERE user_id = ? AND is_active = 0",
        (user_id,)
    ).fetchone()["avg"] or 0

    avg_focus = conn.execute(
        "SELECT AVG(focus_time_minutes) as avg FROM sessions WHERE user_id = ? AND is_active = 0",
        (user_id,)
    ).fetchone()["avg"] or 0

    # Productivity label distribution
    labels = conn.execute(
        """SELECT best_prediction, COUNT(*) as cnt
           FROM predictions
           WHERE user_id = ? AND prediction_type = 'final' AND best_prediction IS NOT NULL
           GROUP BY best_prediction""",
        (user_id,)
    ).fetchall()

    label_dist = {row["best_prediction"]: row["cnt"] for row in labels}

    conn.close()

    return {
        "total_sessions": total,
        "avg_duration_minutes": round(avg_duration, 2),
        "avg_focus_minutes": round(avg_focus, 2),
        "productivity_distribution": label_dist
    }


def get_daily_work_hours(user_id, exclude_session_id=None):
    """Get total work hours from completed sessions today (UTC), excluding a specific session."""
    conn = get_connection()
    today = _utcnow().strftime("%Y-%m-%d")

    if exclude_session_id:
        row = conn.execute(
            """SELECT COALESCE(SUM(total_duration_minutes), 0) as total
               FROM sessions
               WHERE user_id = ? AND is_active = 0 AND id != ?
               AND DATE(start_time) = ?""",
            (user_id, exclude_session_id, today)
        ).fetchone()
    else:
        row = conn.execute(
            """SELECT COALESCE(SUM(total_duration_minutes), 0) as total
               FROM sessions
               WHERE user_id = ? AND is_active = 0
               AND DATE(start_time) = ?""",
            (user_id, today)
        ).fetchone()

    conn.close()
    return round((row["total"] or 0) / 60.0, 2)


def has_recent_live_prediction(session_id, interval_seconds=30):
    """Check if a live prediction was saved recently for this session."""
    conn = get_connection()
    row = conn.execute(
        """SELECT created_at FROM predictions
           WHERE session_id = ? AND prediction_type = 'live'
           ORDER BY id DESC LIMIT 1""",
        (session_id,)
    ).fetchone()
    conn.close()

    if not row or not row["created_at"]:
        return False

    last_time = datetime.fromisoformat(row["created_at"])
    elapsed = (_utcnow() - last_time).total_seconds()
    return elapsed < interval_seconds


# Initialize on import
init_db()
