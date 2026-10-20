"""
Production-quality SQLite database module for Inbox Insights.

Thread-safe via threading.local() — one connection per thread.
WAL mode enabled for concurrent reads.
All queries are parameterized.
"""
import sqlite3
import threading
from datetime import datetime, timezone, timedelta
from typing import Optional

from config.settings import DB_PATH, LOGIN_MAX_ATTEMPTS, LOGIN_LOCKOUT_MINUTES
from modules.logger import get_logger

log = get_logger(__name__)

_local = threading.local()

# ---------------------------------------------------------------------------
# Connection management
# ---------------------------------------------------------------------------

def get_connection() -> sqlite3.Connection:
    """Return a thread-local SQLite connection with WAL mode and row_factory."""
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        _local.conn = conn
    return conn


def _row_to_dict(row) -> Optional[dict]:
    """Convert a sqlite3.Row (or None) to a plain dict."""
    if row is None:
        return None
    return dict(row)


# ---------------------------------------------------------------------------
# Schema initialisation
# ---------------------------------------------------------------------------

def init_db() -> None:
    """Create all tables. Called once at application startup."""
    conn = get_connection()
    cur = conn.cursor()

    cur.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            whatsapp TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            delivery_time TEXT NOT NULL DEFAULT '08:00',
            timezone TEXT NOT NULL DEFAULT 'Asia/Kolkata',
            delivery_enabled INTEGER NOT NULL DEFAULT 1,
            last_report_date TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            login_attempts INTEGER NOT NULL DEFAULT 0,
            lockout_until TEXT
        );

        CREATE TABLE IF NOT EXISTS gmail_accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            label TEXT NOT NULL,
            email TEXT NOT NULL,
            token_encrypted BLOB,
            status TEXT NOT NULL DEFAULT 'ok',
            added_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(user_id, email)
        );

        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            report_date TEXT NOT NULL,
            email_count INTEGER NOT NULL DEFAULT 0,
            deadline_count INTEGER NOT NULL DEFAULT 0,
            pdf_path TEXT,
            pdf_token TEXT UNIQUE,
            pdf_token_expires TEXT,
            whatsapp_status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS oauth_states (
            state TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            code_verifier TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
    """)
    conn.commit()
    log.info("Database initialised at %s", DB_PATH)


# ---------------------------------------------------------------------------
# User CRUD
# ---------------------------------------------------------------------------

def create_user(
    name: str,
    whatsapp: str,
    password_hash: str,
    delivery_time: str = "08:00",
    timezone_str: str = "Asia/Kolkata",
) -> int:
    """Insert a new user and return the new user id."""
    conn = get_connection()
    cur = conn.execute(
        """INSERT INTO users (name, whatsapp, password_hash, delivery_time, timezone)
           VALUES (?, ?, ?, ?, ?)""",
        (name, whatsapp, password_hash, delivery_time, timezone_str),
    )
    conn.commit()
    return cur.lastrowid


def get_user_by_whatsapp(whatsapp: str) -> Optional[dict]:
    """Return user dict or None."""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM users WHERE whatsapp = ?", (whatsapp,)
    ).fetchone()
    return _row_to_dict(row)


def get_user_by_id(user_id: int) -> Optional[dict]:
    """Return user dict or None."""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    return _row_to_dict(row)


def update_delivery_settings(
    user_id: int,
    delivery_time: str,
    timezone_str: str,
    delivery_enabled: bool,
) -> None:
    """Update delivery preferences for a user."""
    conn = get_connection()
    conn.execute(
        """UPDATE users
           SET delivery_time = ?, timezone = ?, delivery_enabled = ?
           WHERE id = ?""",
        (delivery_time, timezone_str, int(delivery_enabled), user_id),
    )
    conn.commit()


def update_last_report_date(user_id: int, date_str: str) -> None:
    """Set last_report_date for a user (YYYY-MM-DD)."""
    conn = get_connection()
    conn.execute(
        "UPDATE users SET last_report_date = ? WHERE id = ?",
        (date_str, user_id),
    )
    conn.commit()


def delete_user(user_id: int) -> None:
    """Delete a user and cascade to gmail_accounts and reports."""
    conn = get_connection()
    conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()


# ---------------------------------------------------------------------------
# Login throttling
# ---------------------------------------------------------------------------

def record_login_attempt(whatsapp: str, success: bool) -> None:
    """
    On success: reset login_attempts and lockout_until.
    On failure: increment login_attempts; if >= LOGIN_MAX_ATTEMPTS, set lockout_until.
    """
    conn = get_connection()
    if success:
        conn.execute(
            "UPDATE users SET login_attempts = 0, lockout_until = NULL WHERE whatsapp = ?",
            (whatsapp,),
        )
        conn.commit()
        return

    user = get_user_by_whatsapp(whatsapp)
    if user is None:
        return

    new_attempts = user["login_attempts"] + 1
    lockout_until = user.get("lockout_until")

    if new_attempts >= LOGIN_MAX_ATTEMPTS:
        lockout_dt = datetime.now(timezone.utc) + timedelta(minutes=LOGIN_LOCKOUT_MINUTES)
        lockout_until = lockout_dt.isoformat()
        conn.execute(
            "UPDATE users SET login_attempts = ?, lockout_until = ? WHERE whatsapp = ?",
            (new_attempts, lockout_until, whatsapp),
        )
    else:
        conn.execute(
            "UPDATE users SET login_attempts = ? WHERE whatsapp = ?",
            (new_attempts, whatsapp),
        )

    conn.commit()


def is_locked_out(whatsapp: str) -> bool:
    """Return True if the user is currently locked out."""
    user = get_user_by_whatsapp(whatsapp)
    if user is None:
        return False
    lockout_until = user.get("lockout_until")
    if not lockout_until:
        return False
    try:
        lockout_dt = datetime.fromisoformat(lockout_until)
        if lockout_dt.tzinfo is None:
            lockout_dt = lockout_dt.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        if now < lockout_dt:
            return True
        # Lockout expired — reset
        conn = get_connection()
        conn.execute(
            "UPDATE users SET login_attempts = 0, lockout_until = NULL WHERE whatsapp = ?",
            (whatsapp,),
        )
        conn.commit()
        return False
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Gmail accounts
# ---------------------------------------------------------------------------

def add_gmail_account(
    user_id: int,
    label: str,
    email: str,
    token_encrypted: bytes,
) -> int:
    """Insert a gmail account and return its id."""
    conn = get_connection()
    cur = conn.execute(
        """INSERT INTO gmail_accounts (user_id, label, email, token_encrypted)
           VALUES (?, ?, ?, ?)""",
        (user_id, label, email, token_encrypted),
    )
    conn.commit()
    return cur.lastrowid


def update_gmail_token(account_id: int, token_encrypted: bytes) -> None:
    """Replace the encrypted token for an account."""
    conn = get_connection()
    conn.execute(
        "UPDATE gmail_accounts SET token_encrypted = ? WHERE id = ?",
        (token_encrypted, account_id),
    )
    conn.commit()


def set_gmail_status(account_id: int, status: str) -> None:
    """Set status for a gmail account ('ok' or 'reconnect_needed')."""
    conn = get_connection()
    conn.execute(
        "UPDATE gmail_accounts SET status = ? WHERE id = ?",
        (status, account_id),
    )
    conn.commit()


def get_gmail_accounts(user_id: int) -> list[dict]:
    """Return all gmail accounts for a user."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM gmail_accounts WHERE user_id = ? ORDER BY added_at ASC",
        (user_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_gmail_account_by_id(account_id: int) -> Optional[dict]:
    """Return a single gmail account dict or None."""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM gmail_accounts WHERE id = ?", (account_id,)
    ).fetchone()
    return _row_to_dict(row)


def remove_gmail_account(account_id: int) -> None:
    """Delete a gmail account by id."""
    conn = get_connection()
    conn.execute("DELETE FROM gmail_accounts WHERE id = ?", (account_id,))
    conn.commit()


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------

def create_report(
    user_id: int,
    report_date: str,
    email_count: int,
    deadline_count: int,
    pdf_path: Optional[str],
    pdf_token: Optional[str],
    pdf_token_expires: Optional[str],
) -> int:
    """Insert a report record and return its id."""
    conn = get_connection()
    cur = conn.execute(
        """INSERT INTO reports
               (user_id, report_date, email_count, deadline_count,
                pdf_path, pdf_token, pdf_token_expires)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (user_id, report_date, email_count, deadline_count,
         pdf_path, pdf_token, pdf_token_expires),
    )
    conn.commit()
    return cur.lastrowid


def update_report_status(report_id: int, whatsapp_status: str) -> None:
    """Update the whatsapp_status field of a report."""
    conn = get_connection()
    conn.execute(
        "UPDATE reports SET whatsapp_status = ? WHERE id = ?",
        (whatsapp_status, report_id),
    )
    conn.commit()


def get_reports(user_id: int, limit: int = 30) -> list[dict]:
    """Return the latest `limit` reports for a user, newest first."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT * FROM reports
           WHERE user_id = ?
           ORDER BY report_date DESC, created_at DESC
           LIMIT ?""",
        (user_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def get_report_by_token(pdf_token: str) -> Optional[dict]:
    """Return a report by its signed PDF token, or None."""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM reports WHERE pdf_token = ?", (pdf_token,)
    ).fetchone()
    return _row_to_dict(row)


# ---------------------------------------------------------------------------
# Scheduler queries
# ---------------------------------------------------------------------------

def get_users_for_delivery() -> list[dict]:
    """
    Return all users where:
    - delivery_enabled = 1
    - They have at least one gmail_account with status = 'ok'

    Fields returned: id, name, whatsapp, delivery_time, timezone, last_report_date
    """
    conn = get_connection()
    rows = conn.execute(
        """SELECT DISTINCT u.id, u.name, u.whatsapp, u.delivery_time,
                  u.timezone, u.last_report_date
           FROM users u
           INNER JOIN gmail_accounts ga ON ga.user_id = u.id AND ga.status = 'ok'
           WHERE u.delivery_enabled = 1"""
    ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# OAuth state (PKCE)
# ---------------------------------------------------------------------------

def save_oauth_state(state: str, user_id: int, code_verifier: str) -> None:
    """Persist an OAuth PKCE state entry."""
    conn = get_connection()
    conn.execute(
        """INSERT INTO oauth_states (state, user_id, code_verifier)
           VALUES (?, ?, ?)""",
        (state, user_id, code_verifier),
    )
    conn.commit()


def get_oauth_state(state: str) -> Optional[dict]:
    """Return an oauth_state dict or None."""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM oauth_states WHERE state = ?", (state,)
    ).fetchone()
    return _row_to_dict(row)


def delete_oauth_state(state: str) -> None:
    """Remove an oauth_state row after use."""
    conn = get_connection()
    conn.execute("DELETE FROM oauth_states WHERE state = ?", (state,))
    conn.commit()


def clean_old_oauth_states() -> None:
    """Delete OAuth states older than 10 minutes."""
    conn = get_connection()
    conn.execute(
        "DELETE FROM oauth_states WHERE created_at < datetime('now', '-10 minutes')"
    )
    conn.commit()
