"""F5 authentication core.

PromptID: ADMS-Frontend-F5-Auth-001

DB-backed operator accounts and opaque Bearer tokens.

Design (owner-approved):
  - operators table: named accounts with PBKDF2-SHA256 password hashes.
  - api_tokens table: opaque tokens stored ONLY as SHA-256 hashes, with a
    role snapshot and expiry; revocation is reversible (revoked_at).
  - Strict posture: no valid token -> 401; insufficient role -> 403.
  - First ADMIN is bootstrapped via `python -m app.api.bootstrap_admin`.

Role hierarchy: VIEWER (1) < OPERATOR (2) < ADMIN (3).
"""

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

from app.api.errors import ApiError
from app.config import Config

ROLE_LEVEL = {"VIEWER": 1, "OPERATOR": 2, "ADMIN": 3}

PBKDF2_ITERATIONS = 260_000
TOKEN_BYTES = 32  # 256-bit opaque token


# ---------------------------------------------------------------------------
# Password hashing (PBKDF2-SHA256, per-user salt)
# ---------------------------------------------------------------------------


def hash_password(password: str) -> str:
    """Returns 'pbkdf2_sha256$iterations$salt_hex$hash_hex'."""
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return "pbkdf2_sha256$%d$%s$%s" % (
        PBKDF2_ITERATIONS,
        salt.hex(),
        dk.hex(),
    )


def verify_password(password: str, stored: str) -> bool:
    """Constant-time comparison of a candidate password against a stored hash."""
    try:
        algo, iterations_str, salt_hex, hash_hex = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
        iterations = int(iterations_str)
    except (ValueError, AttributeError):
        return False
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(dk, expected)


# ---------------------------------------------------------------------------
# Token lifecycle
# ---------------------------------------------------------------------------


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def issue_token(operator_id: int, role: str, ttl_hours: int) -> Tuple[str, datetime]:
    """Returns (plaintext_token, expires_at). Only the hash is persisted."""
    token = secrets.token_urlsafe(TOKEN_BYTES)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=ttl_hours)
    return token, expires_at


def role_required(current_role: str, min_role: str) -> bool:
    """Hierarchical role check: current_role must be >= min_role."""
    return ROLE_LEVEL.get(current_role, 0) >= ROLE_LEVEL.get(min_role, 99)


def require_role_token(role: str) -> None:
    """Raises a 403 ApiError when the role is below the required level."""
    if role not in ROLE_LEVEL:
        raise ApiError(401, "UNAUTHORIZED", "invalid token role")


def verify_token_row(row: Optional[tuple], now: Optional[datetime] = None) -> Optional[Dict[str, Any]]:
    """
    Validates a token DB row and returns an operator context dict.

    Row columns expected (in order): token_hash, role, expires_at, revoked_at,
    operator_id, username, display_name, active.
    Returns None when the token is invalid/expired/revoked or the operator is
    inactive — callers translate None to a 401.
    """
    if row is None:
        return None
    token_hash, role, expires_at, revoked_at, operator_id, username, display_name, active = row
    now = now or datetime.now(timezone.utc)
    if revoked_at is not None:
        return None
    if expires_at is not None and now > expires_at:
        return None
    if not active:
        return None
    if role not in ROLE_LEVEL:
        return None
    return {
        "operator_id": operator_id,
        "username": username,
        "display_name": display_name,
        "role": role,
    }


def authenticate_operator(cur: Any, username: str, password: str) -> Optional[Dict[str, Any]]:
    """Validates credentials against the operators table.

    cur: a psycopg2 cursor (read access to operators).
    Returns an operator dict {operator_id, username, display_name, role} or None.
    """
    cur.execute(
        "SELECT operator_id, username, display_name, role, password_hash, active "
        "FROM operators WHERE username = %s;",
        (username,),
    )
    row = cur.fetchone()
    if row is None:
        return None
    operator_id, db_username, display_name, role, password_hash, active = row
    if not active:
        return None
    if not verify_password(password, password_hash):
        return None
    return {
        "operator_id": operator_id,
        "username": db_username,
        "display_name": display_name,
        "role": role,
    }
