"""
Authentication and JWT session management for WalkSense.

Implements:
- Username/password login
- Access + refresh JWT issuance
- Refresh token rotation
- JWT-family blacklisting on refresh-token reuse/compromise
- Brute-force protection/rate limiting
- Auth audit logs
"""

from __future__ import annotations

import base64
from contextlib import contextmanager
import hashlib
import hmac
import os
import sqlite3
import threading
import time
import uuid
from typing import Any, Dict, Optional

import jwt
from fastapi import Header, HTTPException, status
from loguru import logger

from API.env_loader import bootstrap_environment

# Ensure environment/secrets are loaded before reading auth settings.
bootstrap_environment()


def _now_ts() -> int:
    return int(time.time())


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


APP_ENV = os.getenv("APP_ENV", "development").strip().lower()
IS_PRODUCTION = APP_ENV == "production"

JWT_ALGORITHM = "HS256"
ACCESS_TTL_SECONDS = int(os.getenv("JWT_ACCESS_TTL_SECONDS", "900"))         # 15 min
REFRESH_TTL_SECONDS = int(os.getenv("JWT_REFRESH_TTL_SECONDS", "1209600"))   # 14 days
ACCESS_SECRET = os.getenv("JWT_ACCESS_SECRET", "dev-access-secret-change-this")
REFRESH_SECRET = os.getenv("JWT_REFRESH_SECRET", "dev-refresh-secret-change-this")

if "change-this" in ACCESS_SECRET or "change-this" in REFRESH_SECRET:
    logger.warning("[AUTH] Using default JWT secrets. Set JWT_ACCESS_SECRET and JWT_REFRESH_SECRET in .env")

REFRESH_COOKIE_NAME = os.getenv("AUTH_REFRESH_COOKIE_NAME", "walksense_refresh_token")
COOKIE_CROSS_SITE = _bool_env("AUTH_COOKIE_CROSS_SITE", False)
COOKIE_SECURE = _bool_env("AUTH_COOKIE_SECURE", IS_PRODUCTION)
_REQUESTED_SAMESITE = os.getenv("AUTH_COOKIE_SAMESITE", "lax").strip().lower()
if COOKIE_CROSS_SITE:
    COOKIE_SAMESITE = "none"
    COOKIE_SECURE = True
else:
    if _REQUESTED_SAMESITE == "none":
        logger.warning("[AUTH] SameSite=None requires cross-site mode; falling back to SameSite=Lax")
        COOKIE_SAMESITE = "lax"
    elif _REQUESTED_SAMESITE in {"lax", "strict"}:
        COOKIE_SAMESITE = _REQUESTED_SAMESITE
    else:
        COOKIE_SAMESITE = "lax"

# Force secure cookies in production.
if IS_PRODUCTION:
    COOKIE_SECURE = True

AUTH_DB_PATH = os.getenv(
    "AUTH_DB_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "auth.db"),
)

BOOTSTRAP_USERNAME = os.getenv("AUTH_BOOTSTRAP_USERNAME", "admin")
BOOTSTRAP_PASSWORD = os.getenv("AUTH_BOOTSTRAP_PASSWORD", "ChangeMe_123!")
BOOTSTRAP_FORCE_RESET = _bool_env("AUTH_BOOTSTRAP_FORCE_RESET", False)
BOOTSTRAP_ENABLED = _bool_env("AUTH_BOOTSTRAP_ENABLED", not IS_PRODUCTION)

LOGIN_RATE_MAX_ATTEMPTS = int(os.getenv("AUTH_RATE_LIMIT_LOGIN_MAX_ATTEMPTS", "5"))
LOGIN_RATE_WINDOW_SECONDS = int(os.getenv("AUTH_RATE_LIMIT_LOGIN_WINDOW_SECONDS", "300"))
LOGIN_RATE_BLOCK_SECONDS = int(os.getenv("AUTH_RATE_LIMIT_LOGIN_BLOCK_SECONDS", "600"))

REFRESH_RATE_MAX_ATTEMPTS = int(os.getenv("AUTH_RATE_LIMIT_REFRESH_MAX_ATTEMPTS", "10"))
REFRESH_RATE_WINDOW_SECONDS = int(os.getenv("AUTH_RATE_LIMIT_REFRESH_WINDOW_SECONDS", "300"))
REFRESH_RATE_BLOCK_SECONDS = int(os.getenv("AUTH_RATE_LIMIT_REFRESH_BLOCK_SECONDS", "600"))

AUTH_AUDIT_RETENTION_SECONDS = int(os.getenv("AUTH_AUDIT_RETENTION_SECONDS", "2592000"))  # 30 days
AUTH_RATE_LIMIT_RETENTION_SECONDS = int(os.getenv("AUTH_RATE_LIMIT_RETENTION_SECONDS", "86400"))  # 1 day
AUTH_CLEANUP_INTERVAL_SECONDS = int(os.getenv("AUTH_CLEANUP_INTERVAL_SECONDS", "3600"))  # 1 hour
AUTH_HOUSEKEEPING_ENABLED = _bool_env("AUTH_HOUSEKEEPING_ENABLED", True)

AUTH_ALERT_WINDOW_SECONDS = int(os.getenv("AUTH_ALERT_WINDOW_SECONDS", "300"))  # 5 minutes
AUTH_ALERT_COMPROMISE_THRESHOLD = int(os.getenv("AUTH_ALERT_COMPROMISE_THRESHOLD", "5"))
AUTH_ALERT_COOLDOWN_SECONDS = int(os.getenv("AUTH_ALERT_COOLDOWN_SECONDS", "300"))
AUTH_ALERT_CLOUDWATCH_ENABLED = _bool_env("AUTH_ALERT_CLOUDWATCH_ENABLED", False)
AUTH_ALERT_CLOUDWATCH_NAMESPACE = os.getenv("AUTH_ALERT_CLOUDWATCH_NAMESPACE", "WalkSense/Security")

_alert_lock = threading.Lock()
_last_alert_ts = 0

class AuthError(Exception):
    def __init__(self, message: str, status_code: int = status.HTTP_401_UNAUTHORIZED):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class TokenReuseDetected(AuthError):
    pass


class RateLimitExceeded(AuthError):
    def __init__(self, message: str, retry_after: int):
        super().__init__(message, status_code=status.HTTP_429_TOO_MANY_REQUESTS)
        self.retry_after = max(1, retry_after)


def _ensure_parent_dir(path: str) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)


def _db_conn() -> sqlite3.Connection:
    _ensure_parent_dir(AUTH_DB_PATH)
    conn = sqlite3.connect(AUTH_DB_PATH, timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=15000")
    return conn


@contextmanager
def _db_session():
    conn = _db_conn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _hash_password(password: str, iterations: int = 390000) -> str:
    salt = os.urandom(16)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return (
        f"pbkdf2_sha256${iterations}$"
        f"{base64.urlsafe_b64encode(salt).decode('ascii')}$"
        f"{base64.urlsafe_b64encode(derived).decode('ascii')}"
    )


def _verify_password(password: str, stored: str) -> bool:
    try:
        algo, iter_str, salt_b64, hash_b64 = stored.split("$", 3)
        if algo != "pbkdf2_sha256":
            return False
        iterations = int(iter_str)
        salt = base64.urlsafe_b64decode(salt_b64.encode("ascii"))
        expected = base64.urlsafe_b64decode(hash_b64.encode("ascii"))
    except Exception:
        return False

    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(actual, expected)


def _audit_event_tx(
    conn: sqlite3.Connection,
    event_type: str,
    success: bool,
    *,
    username: Optional[str] = None,
    user_id: Optional[int] = None,
    family_id: Optional[str] = None,
    jti: Optional[str] = None,
    ip: Optional[str] = None,
    detail: Optional[str] = None,
) -> None:
    now = _now_ts()
    conn.execute(
        """
        INSERT INTO auth_audit_events
        (ts, event_type, success, username, user_id, family_id, jti, ip, detail)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            now,
            event_type,
            1 if success else 0,
            username,
            user_id,
            family_id,
            jti,
            ip,
            detail,
        ),
    )

    logger.bind(
        event_type=event_type,
        success=success,
        username=username,
        user_id=user_id,
        family_id=family_id,
        jti=jti,
        ip=ip,
    ).info(f"[AUTH_AUDIT] {event_type}: {detail or ''}")


def record_audit_event(
    event_type: str,
    success: bool,
    *,
    username: Optional[str] = None,
    user_id: Optional[int] = None,
    family_id: Optional[str] = None,
    jti: Optional[str] = None,
    ip: Optional[str] = None,
    detail: Optional[str] = None,
) -> None:
    with _db_session() as conn:
        _audit_event_tx(
            conn,
            event_type,
            success,
            username=username,
            user_id=user_id,
            family_id=family_id,
            jti=jti,
            ip=ip,
            detail=detail,
        )


def _rate_limit_cfg(action: str) -> Dict[str, int]:
    if action == "login":
        return {
            "max_attempts": LOGIN_RATE_MAX_ATTEMPTS,
            "window_seconds": LOGIN_RATE_WINDOW_SECONDS,
            "block_seconds": LOGIN_RATE_BLOCK_SECONDS,
        }
    if action == "refresh":
        return {
            "max_attempts": REFRESH_RATE_MAX_ATTEMPTS,
            "window_seconds": REFRESH_RATE_WINDOW_SECONDS,
            "block_seconds": REFRESH_RATE_BLOCK_SECONDS,
        }
    raise ValueError(f"Unknown rate-limit action: {action}")


def enforce_rate_limit(action: str, identifier: str) -> None:
    cfg = _rate_limit_cfg(action)
    identifier = identifier or "unknown"
    now = _now_ts()

    with _db_session() as conn:
        row = conn.execute(
            """
            SELECT action, identifier, window_started_at, fail_count, blocked_until
            FROM auth_rate_limits
            WHERE action = ? AND identifier = ?
            """,
            (action, identifier),
        ).fetchone()

        if row is None:
            conn.execute(
                """
                INSERT INTO auth_rate_limits
                (action, identifier, window_started_at, fail_count, blocked_until)
                VALUES (?, ?, ?, 0, NULL)
                """,
                (action, identifier, now),
            )
            return

        blocked_until = row["blocked_until"]
        if blocked_until is not None and int(blocked_until) > now:
            raise RateLimitExceeded(
                f"Too many {action} attempts. Try again later.",
                retry_after=int(blocked_until) - now,
            )

        window_started_at = int(row["window_started_at"])
        if now - window_started_at >= cfg["window_seconds"]:
            conn.execute(
                """
                UPDATE auth_rate_limits
                SET window_started_at = ?, fail_count = 0, blocked_until = NULL
                WHERE action = ? AND identifier = ?
                """,
                (now, action, identifier),
            )


def register_rate_limit_failure(action: str, identifier: str, *, ip: Optional[str] = None, reason: str = "") -> None:
    cfg = _rate_limit_cfg(action)
    identifier = identifier or "unknown"
    now = _now_ts()
    trigger_alert = False

    with _db_session() as conn:
        row = conn.execute(
            """
            SELECT action, identifier, window_started_at, fail_count
            FROM auth_rate_limits
            WHERE action = ? AND identifier = ?
            """,
            (action, identifier),
        ).fetchone()

        if row is None:
            window_started_at = now
            fail_count = 0
            conn.execute(
                """
                INSERT INTO auth_rate_limits
                (action, identifier, window_started_at, fail_count, blocked_until)
                VALUES (?, ?, ?, 0, NULL)
                """,
                (action, identifier, window_started_at),
            )
        else:
            window_started_at = int(row["window_started_at"])
            fail_count = int(row["fail_count"])

        if now - window_started_at >= cfg["window_seconds"]:
            window_started_at = now
            fail_count = 0

        fail_count += 1
        blocked_until = None
        if fail_count >= cfg["max_attempts"]:
            blocked_until = now + cfg["block_seconds"]

        conn.execute(
            """
            UPDATE auth_rate_limits
            SET window_started_at = ?, fail_count = ?, blocked_until = ?
            WHERE action = ? AND identifier = ?
            """,
            (window_started_at, fail_count, blocked_until, action, identifier),
        )

        if blocked_until is not None:
            trigger_alert = True
            _audit_event_tx(
                conn,
                "rate_limit_blocked",
                False,
                ip=ip,
                detail=f"action={action}; identifier={identifier}; reason={reason}",
            )

    if trigger_alert:
        maybe_emit_lockout_alert(trigger=f"rate_limit_blocked:{action}", ip=ip)


def reset_rate_limit(action: str, identifier: str) -> None:
    identifier = identifier or "unknown"
    now = _now_ts()
    with _db_session() as conn:
        conn.execute(
            """
            UPDATE auth_rate_limits
            SET window_started_at = ?, fail_count = 0, blocked_until = NULL
            WHERE action = ? AND identifier = ?
            """,
            (now, action, identifier),
        )


def cleanup_auth_tables(
    *,
    audit_retention_seconds: Optional[int] = None,
    rate_limit_retention_seconds: Optional[int] = None,
) -> Dict[str, int]:
    """Delete old auth audit and stale rate-limit rows."""
    now = _now_ts()
    audit_retention = max(60, int(audit_retention_seconds or AUTH_AUDIT_RETENTION_SECONDS))
    rate_limit_retention = max(60, int(rate_limit_retention_seconds or AUTH_RATE_LIMIT_RETENTION_SECONDS))
    audit_cutoff = now - audit_retention
    rate_limit_cutoff = now - rate_limit_retention

    with _db_session() as conn:
        deleted_audit = conn.execute(
            "DELETE FROM auth_audit_events WHERE ts < ?",
            (audit_cutoff,),
        ).rowcount
        deleted_rate_limits = conn.execute(
            """
            DELETE FROM auth_rate_limits
            WHERE window_started_at < ?
              AND (blocked_until IS NULL OR blocked_until < ?)
            """,
            (rate_limit_cutoff, now),
        ).rowcount

    return {
        "deleted_audit_events": int(deleted_audit or 0),
        "deleted_rate_limits": int(deleted_rate_limits or 0),
    }


def _count_event_since(conn: sqlite3.Connection, event_type: str, cutoff: int) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*) AS c
        FROM auth_audit_events
        WHERE event_type = ? AND ts >= ?
        """,
        (event_type, cutoff),
    ).fetchone()
    return int(row["c"]) if row else 0


def get_security_metrics(*, window_seconds: Optional[int] = None) -> Dict[str, int]:
    """Read lockout/compromise metrics for alerting and scraping."""
    now = _now_ts()
    window = max(60, int(window_seconds or AUTH_ALERT_WINDOW_SECONDS))
    cutoff = now - window

    with _db_session() as conn:
        total_audit_row = conn.execute("SELECT COUNT(*) AS c FROM auth_audit_events").fetchone()
        active_blocks_row = conn.execute(
            "SELECT COUNT(*) AS c FROM auth_rate_limits WHERE blocked_until IS NOT NULL AND blocked_until > ?",
            (now,),
        ).fetchone()

        token_family_blacklisted = _count_event_since(conn, "token_family_blacklisted", cutoff)
        rate_limit_blocked = _count_event_since(conn, "rate_limit_blocked", cutoff)
        login_rate_limited = _count_event_since(conn, "login_rate_limited", cutoff)
        refresh_rate_limited = _count_event_since(conn, "refresh_rate_limited", cutoff)
        refresh_reuse_detected = _count_event_since(conn, "refresh_reuse_detected", cutoff)

    return {
        "window_seconds": window,
        "audit_events_total": int(total_audit_row["c"]) if total_audit_row else 0,
        "token_family_blacklisted_window": token_family_blacklisted,
        "rate_limit_blocked_window": rate_limit_blocked,
        "login_rate_limited_window": login_rate_limited,
        "refresh_rate_limited_window": refresh_rate_limited,
        "refresh_reuse_detected_window": refresh_reuse_detected,
        "active_rate_limit_blocks": int(active_blocks_row["c"]) if active_blocks_row else 0,
    }


def _emit_cloudwatch_security_metric(metric_name: str, value: int) -> None:
    if not AUTH_ALERT_CLOUDWATCH_ENABLED:
        return
    try:
        import boto3  # type: ignore

        client = boto3.client("cloudwatch")
        client.put_metric_data(
            Namespace=AUTH_ALERT_CLOUDWATCH_NAMESPACE,
            MetricData=[
                {
                    "MetricName": metric_name,
                    "Value": float(value),
                    "Unit": "Count",
                }
            ],
        )
    except Exception as exc:
        logger.warning(f"[AUTH_ALERT] CloudWatch metric emit failed: {exc}")


def maybe_emit_lockout_alert(*, trigger: str, ip: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Emit an alert hook when repeated compromise events are detected."""
    global _last_alert_ts

    metrics = get_security_metrics(window_seconds=AUTH_ALERT_WINDOW_SECONDS)
    compromise_events = (
        metrics["token_family_blacklisted_window"]
        + metrics["rate_limit_blocked_window"]
        + metrics["refresh_reuse_detected_window"]
    )

    if compromise_events < AUTH_ALERT_COMPROMISE_THRESHOLD:
        return None

    now = _now_ts()
    with _alert_lock:
        if now - _last_alert_ts < AUTH_ALERT_COOLDOWN_SECONDS:
            return None
        _last_alert_ts = now

    logger.error(
        "[AUTH_ALERT] Repeated compromise/lockout events detected: "
        f"trigger={trigger}, window_seconds={metrics['window_seconds']}, "
        f"compromise_events={compromise_events}, active_blocks={metrics['active_rate_limit_blocks']}, ip={ip or 'unknown'}"
    )

    _emit_cloudwatch_security_metric("AuthCompromiseEvents", compromise_events)
    _emit_cloudwatch_security_metric("AuthActiveRateLimitBlocks", metrics["active_rate_limit_blocks"])

    return {
        "trigger": trigger,
        "window_seconds": metrics["window_seconds"],
        "compromise_events": compromise_events,
        "active_rate_limit_blocks": metrics["active_rate_limit_blocks"],
    }


def render_prometheus_metrics() -> str:
    metrics = get_security_metrics(window_seconds=AUTH_ALERT_WINDOW_SECONDS)
    lines = [
        "# HELP walksense_auth_audit_events_total Total auth audit events.",
        "# TYPE walksense_auth_audit_events_total gauge",
        f"walksense_auth_audit_events_total {metrics['audit_events_total']}",
        "# HELP walksense_auth_token_family_blacklisted_window Total token families blacklisted in alert window.",
        "# TYPE walksense_auth_token_family_blacklisted_window gauge",
        f"walksense_auth_token_family_blacklisted_window {metrics['token_family_blacklisted_window']}",
        "# HELP walksense_auth_rate_limit_blocked_window Total rate-limit blocks in alert window.",
        "# TYPE walksense_auth_rate_limit_blocked_window gauge",
        f"walksense_auth_rate_limit_blocked_window {metrics['rate_limit_blocked_window']}",
        "# HELP walksense_auth_login_rate_limited_window Total login rate-limited events in alert window.",
        "# TYPE walksense_auth_login_rate_limited_window gauge",
        f"walksense_auth_login_rate_limited_window {metrics['login_rate_limited_window']}",
        "# HELP walksense_auth_refresh_rate_limited_window Total refresh rate-limited events in alert window.",
        "# TYPE walksense_auth_refresh_rate_limited_window gauge",
        f"walksense_auth_refresh_rate_limited_window {metrics['refresh_rate_limited_window']}",
        "# HELP walksense_auth_refresh_reuse_detected_window Total refresh-token reuse detections in alert window.",
        "# TYPE walksense_auth_refresh_reuse_detected_window gauge",
        f"walksense_auth_refresh_reuse_detected_window {metrics['refresh_reuse_detected_window']}",
        "# HELP walksense_auth_rate_limit_active_blocks Current active rate-limit blocks.",
        "# TYPE walksense_auth_rate_limit_active_blocks gauge",
        f"walksense_auth_rate_limit_active_blocks {metrics['active_rate_limit_blocks']}",
    ]
    return "\n".join(lines) + "\n"


def run_auth_maintenance_cycle() -> Dict[str, int]:
    cleanup = cleanup_auth_tables()
    maybe_emit_lockout_alert(trigger="periodic_maintenance")
    return cleanup


def init_auth() -> None:
    with _db_session() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS token_families (
                family_id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                blacklist_reason TEXT,
                created_at INTEGER NOT NULL,
                blacklisted_at INTEGER
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS refresh_tokens (
                jti TEXT PRIMARY KEY,
                family_id TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                parent_jti TEXT,
                status TEXT NOT NULL,
                issued_at INTEGER NOT NULL,
                expires_at INTEGER NOT NULL,
                used_at INTEGER,
                revoked_at INTEGER,
                replaced_by_jti TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS auth_audit_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                success INTEGER NOT NULL,
                username TEXT,
                user_id INTEGER,
                family_id TEXT,
                jti TEXT,
                ip TEXT,
                detail TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS auth_rate_limits (
                action TEXT NOT NULL,
                identifier TEXT NOT NULL,
                window_started_at INTEGER NOT NULL,
                fail_count INTEGER NOT NULL,
                blocked_until INTEGER,
                PRIMARY KEY (action, identifier)
            )
            """
        )

        conn.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_refresh_family ON refresh_tokens(family_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_refresh_user ON refresh_tokens(user_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_refresh_status ON refresh_tokens(status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_ts ON auth_audit_events(ts)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_rate_limits_blocked_until ON auth_rate_limits(blocked_until)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_rate_limits_window_started ON auth_rate_limits(window_started_at)")

        if not BOOTSTRAP_ENABLED:
            logger.info("[AUTH] Bootstrap user provisioning disabled (managed provisioning mode)")
            return

        now = _now_ts()
        row = conn.execute("SELECT id FROM users WHERE username = ?", (BOOTSTRAP_USERNAME,)).fetchone()
        if row is None:
            conn.execute(
                """
                INSERT INTO users (username, password_hash, is_active, created_at)
                VALUES (?, ?, 1, ?)
                """,
                (BOOTSTRAP_USERNAME, _hash_password(BOOTSTRAP_PASSWORD), now),
            )
            _audit_event_tx(
                conn,
                "bootstrap_user_created",
                True,
                username=BOOTSTRAP_USERNAME,
                detail="bootstrap provisioning",
            )
            logger.info(f"[AUTH] Bootstrap user created: {BOOTSTRAP_USERNAME}")
        elif BOOTSTRAP_FORCE_RESET:
            conn.execute(
                "UPDATE users SET password_hash = ? WHERE username = ?",
                (_hash_password(BOOTSTRAP_PASSWORD), BOOTSTRAP_USERNAME),
            )
            _audit_event_tx(
                conn,
                "bootstrap_user_password_reset",
                True,
                username=BOOTSTRAP_USERNAME,
                detail="bootstrap force reset",
            )
            logger.warning(f"[AUTH] Bootstrap password reset for user: {BOOTSTRAP_USERNAME}")


def provision_managed_user(
    username: str,
    password: str,
    *,
    is_active: bool = True,
    force_update: bool = False,
) -> Dict[str, Any]:
    username = (username or "").strip()
    if not username:
        raise ValueError("username is required")
    if not password:
        raise ValueError("password is required")

    now = _now_ts()
    with _db_session() as conn:
        row = conn.execute(
            "SELECT id FROM users WHERE username = ?",
            (username,),
        ).fetchone()

        if row is None:
            conn.execute(
                """
                INSERT INTO users (username, password_hash, is_active, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (username, _hash_password(password), 1 if is_active else 0, now),
            )
            user_id = int(conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()["id"])
            _audit_event_tx(conn, "managed_user_created", True, username=username, user_id=user_id)
            return {"id": user_id, "username": username, "created": True}

        if not force_update:
            raise ValueError(f"user '{username}' already exists (use force_update=True)")

        user_id = int(row["id"])
        conn.execute(
            """
            UPDATE users
            SET password_hash = ?, is_active = ?
            WHERE id = ?
            """,
            (_hash_password(password), 1 if is_active else 0, user_id),
        )
        _audit_event_tx(conn, "managed_user_updated", True, username=username, user_id=user_id)
        return {"id": user_id, "username": username, "created": False}


def _to_user_dict(row: sqlite3.Row) -> Dict[str, Any]:
    return {"id": int(row["id"]), "username": row["username"]}


def authenticate_user(username: str, password: str) -> Optional[Dict[str, Any]]:
    with _db_session() as conn:
        row = conn.execute(
            "SELECT id, username, password_hash, is_active FROM users WHERE username = ?",
            (username,),
        ).fetchone()
        if row is None:
            return None
        if int(row["is_active"]) != 1:
            return None
        if not _verify_password(password, row["password_hash"]):
            return None
        return _to_user_dict(row)


def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    with _db_session() as conn:
        row = conn.execute(
            "SELECT id, username, is_active FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        if row is None or int(row["is_active"]) != 1:
            return None
        return _to_user_dict(row)


def _encode_access_token(user: Dict[str, Any], family_id: str) -> str:
    now = _now_ts()
    payload = {
        "sub": str(user["id"]),
        "username": user["username"],
        "family_id": family_id,
        "type": "access",
        "jti": str(uuid.uuid4()),
        "iat": now,
        "exp": now + ACCESS_TTL_SECONDS,
    }
    return jwt.encode(payload, ACCESS_SECRET, algorithm=JWT_ALGORITHM)


def _encode_refresh_token(user: Dict[str, Any], family_id: str, parent_jti: Optional[str] = None) -> Dict[str, Any]:
    now = _now_ts()
    jti = str(uuid.uuid4())
    expires_at = now + REFRESH_TTL_SECONDS
    payload = {
        "sub": str(user["id"]),
        "username": user["username"],
        "family_id": family_id,
        "type": "refresh",
        "jti": jti,
        "parent_jti": parent_jti,
        "iat": now,
        "exp": expires_at,
    }
    token = jwt.encode(payload, REFRESH_SECRET, algorithm=JWT_ALGORITHM)
    return {"token": token, "jti": jti, "iat": now, "exp": expires_at}


def _decode_token(token: str, token_type: str) -> Dict[str, Any]:
    secret = ACCESS_SECRET if token_type == "access" else REFRESH_SECRET
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=[JWT_ALGORITHM],
            options={"require": ["exp", "iat", "jti", "sub", "family_id", "type"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise AuthError(f"{token_type.capitalize()} token expired") from exc
    except jwt.InvalidTokenError as exc:
        raise AuthError("Invalid token") from exc

    if payload.get("type") != token_type:
        raise AuthError("Invalid token type")
    return payload


def _family_is_blacklisted(conn: sqlite3.Connection, family_id: str) -> bool:
    row = conn.execute(
        "SELECT status FROM token_families WHERE family_id = ?",
        (family_id,),
    ).fetchone()
    return row is not None and row["status"] == "blacklisted"


def _blacklist_family_tx(
    conn: sqlite3.Connection,
    family_id: str,
    reason: str,
    *,
    actor_user_id: Optional[int] = None,
    ip: Optional[str] = None,
) -> None:
    now = _now_ts()
    row = conn.execute(
        "SELECT user_id FROM token_families WHERE family_id = ?",
        (family_id,),
    ).fetchone()
    family_user_id = int(row["user_id"]) if row else None

    conn.execute(
        """
        UPDATE token_families
        SET status = 'blacklisted',
            blacklist_reason = ?,
            blacklisted_at = ?
        WHERE family_id = ?
        """,
        (reason, now, family_id),
    )
    conn.execute(
        """
        UPDATE refresh_tokens
        SET status = 'revoked',
            revoked_at = ?
        WHERE family_id = ? AND status != 'revoked'
        """,
        (now, family_id),
    )

    _audit_event_tx(
        conn,
        "token_family_blacklisted",
        False,
        user_id=actor_user_id or family_user_id,
        family_id=family_id,
        ip=ip,
        detail=reason,
    )


def issue_login_tokens(username: str, password: str, *, client_ip: Optional[str] = None) -> Dict[str, Any]:
    user = authenticate_user(username, password)
    if user is None:
        record_audit_event(
            "login_failed",
            False,
            username=username,
            ip=client_ip,
            detail="invalid_credentials",
        )
        raise AuthError("Invalid username or password")

    family_id = str(uuid.uuid4())
    refresh_data = _encode_refresh_token(user, family_id)
    access_token = _encode_access_token(user, family_id)

    with _db_session() as conn:
        now = _now_ts()
        conn.execute(
            """
            INSERT INTO token_families (family_id, user_id, status, created_at)
            VALUES (?, ?, 'active', ?)
            """,
            (family_id, user["id"], now),
        )
        conn.execute(
            """
            INSERT INTO refresh_tokens
            (jti, family_id, user_id, parent_jti, status, issued_at, expires_at)
            VALUES (?, ?, ?, ?, 'active', ?, ?)
            """,
            (
                refresh_data["jti"],
                family_id,
                user["id"],
                None,
                refresh_data["iat"],
                refresh_data["exp"],
            ),
        )
        _audit_event_tx(
            conn,
            "login_success",
            True,
            username=user["username"],
            user_id=user["id"],
            family_id=family_id,
            jti=refresh_data["jti"],
            ip=client_ip,
        )

    return {
        "user": user,
        "family_id": family_id,
        "access_token": access_token,
        "refresh_token": refresh_data["token"],
        "expires_in": ACCESS_TTL_SECONDS,
    }


def rotate_refresh_token(refresh_token: str, *, client_ip: Optional[str] = None) -> Dict[str, Any]:
    try:
        payload = _decode_token(refresh_token, "refresh")
    except AuthError as exc:
        record_audit_event("refresh_failed", False, ip=client_ip, detail=f"decode_failed:{exc.message}")
        raise

    user_id = int(payload["sub"])
    family_id = str(payload["family_id"])
    old_jti = str(payload["jti"])

    user = get_user_by_id(user_id)
    if user is None:
        record_audit_event(
            "refresh_failed",
            False,
            user_id=user_id,
            family_id=family_id,
            jti=old_jti,
            ip=client_ip,
            detail="user_inactive_or_missing",
        )
        raise AuthError("User not found or inactive")

    with _db_session() as conn:
        if _family_is_blacklisted(conn, family_id):
            _audit_event_tx(
                conn,
                "refresh_failed",
                False,
                username=user["username"],
                user_id=user_id,
                family_id=family_id,
                jti=old_jti,
                ip=client_ip,
                detail="family_blacklisted",
            )
            raise AuthError("Session family is revoked. Please log in again.")

        row = conn.execute(
            """
            SELECT jti, status, expires_at, family_id, user_id
            FROM refresh_tokens
            WHERE jti = ?
            """,
            (old_jti,),
        ).fetchone()

        if row is None:
            _audit_event_tx(
                conn,
                "refresh_failed",
                False,
                username=user["username"],
                user_id=user_id,
                family_id=family_id,
                jti=old_jti,
                ip=client_ip,
                detail="refresh_token_unknown",
            )
            raise AuthError("Refresh token is not recognized")

        if row["family_id"] != family_id or int(row["user_id"]) != user_id:
            _audit_event_tx(
                conn,
                "refresh_failed",
                False,
                username=user["username"],
                user_id=user_id,
                family_id=family_id,
                jti=old_jti,
                ip=client_ip,
                detail="refresh_metadata_mismatch",
            )
            raise AuthError("Refresh token metadata mismatch")

        now = _now_ts()
        if int(row["expires_at"]) <= now:
            conn.execute(
                "UPDATE refresh_tokens SET status = 'revoked', revoked_at = ? WHERE jti = ?",
                (now, old_jti),
            )
            _audit_event_tx(
                conn,
                "refresh_failed",
                False,
                username=user["username"],
                user_id=user_id,
                family_id=family_id,
                jti=old_jti,
                ip=client_ip,
                detail="refresh_expired",
            )
            conn.commit()
            raise AuthError("Refresh token expired")

        if row["status"] != "active":
            _audit_event_tx(
                conn,
                "refresh_reuse_detected",
                False,
                username=user["username"],
                user_id=user_id,
                family_id=family_id,
                jti=old_jti,
                ip=client_ip,
                detail="status_not_active",
            )
            _blacklist_family_tx(
                conn,
                family_id,
                f"refresh_reuse_detected:{old_jti}",
                actor_user_id=user_id,
                ip=client_ip,
            )
            conn.commit()
            raise TokenReuseDetected(
                "Refresh token reuse detected. Session family has been revoked."
            )

        new_refresh = _encode_refresh_token(user, family_id, parent_jti=old_jti)
        access_token = _encode_access_token(user, family_id)

        updated = conn.execute(
            """
            UPDATE refresh_tokens
            SET status = 'used', used_at = ?, replaced_by_jti = ?
            WHERE jti = ? AND status = 'active'
            """,
            (now, new_refresh["jti"], old_jti),
        )
        if updated.rowcount != 1:
            _audit_event_tx(
                conn,
                "refresh_reuse_detected",
                False,
                username=user["username"],
                user_id=user_id,
                family_id=family_id,
                jti=old_jti,
                ip=client_ip,
                detail="rotation_update_race",
            )
            _blacklist_family_tx(
                conn,
                family_id,
                f"refresh_race_reuse:{old_jti}",
                actor_user_id=user_id,
                ip=client_ip,
            )
            conn.commit()
            raise TokenReuseDetected(
                "Refresh token reuse detected. Session family has been revoked."
            )

        conn.execute(
            """
            INSERT INTO refresh_tokens
            (jti, family_id, user_id, parent_jti, status, issued_at, expires_at)
            VALUES (?, ?, ?, ?, 'active', ?, ?)
            """,
            (
                new_refresh["jti"],
                family_id,
                user_id,
                old_jti,
                new_refresh["iat"],
                new_refresh["exp"],
            ),
        )

        _audit_event_tx(
            conn,
            "refresh_success",
            True,
            username=user["username"],
            user_id=user_id,
            family_id=family_id,
            jti=new_refresh["jti"],
            ip=client_ip,
            detail=f"rotated_from:{old_jti}",
        )

    return {
        "user": user,
        "family_id": family_id,
        "access_token": access_token,
        "refresh_token": new_refresh["token"],
        "expires_in": ACCESS_TTL_SECONDS,
    }


def revoke_family_from_refresh(
    refresh_token: str,
    *,
    reason: str = "logout",
    client_ip: Optional[str] = None,
) -> None:
    payload = _decode_token(refresh_token, "refresh")
    family_id = str(payload["family_id"])
    user_id = int(payload["sub"])
    revoke_family(family_id, reason=reason, actor_user_id=user_id, client_ip=client_ip)


def revoke_family(
    family_id: str,
    *,
    reason: str = "manual_revoke",
    actor_user_id: Optional[int] = None,
    client_ip: Optional[str] = None,
) -> None:
    with _db_session() as conn:
        _blacklist_family_tx(
            conn,
            family_id,
            reason,
            actor_user_id=actor_user_id,
            ip=client_ip,
        )


def validate_access_token(access_token: str) -> Dict[str, Any]:
    payload = _decode_token(access_token, "access")
    user_id = int(payload["sub"])
    family_id = str(payload["family_id"])

    with _db_session() as conn:
        if _family_is_blacklisted(conn, family_id):
            raise AuthError("Session revoked. Please log in again.")

    user = get_user_by_id(user_id)
    if user is None:
        raise AuthError("User not found or inactive")

    return {
        "id": user["id"],
        "username": user["username"],
        "family_id": family_id,
        "token_jti": str(payload["jti"]),
    }


async def require_user(
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
) -> Dict[str, Any]:
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
        )
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bearer token format",
        )
    try:
        return validate_access_token(token)
    except AuthError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


def set_refresh_cookie(response: Any, refresh_token: str) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=refresh_token,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        max_age=REFRESH_TTL_SECONDS,
        path="/api/auth",
    )


def clear_refresh_cookie(response: Any) -> None:
    response.delete_cookie(
        key=REFRESH_COOKIE_NAME,
        path="/api/auth",
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
    )


# Initialize auth storage on import
init_auth()
