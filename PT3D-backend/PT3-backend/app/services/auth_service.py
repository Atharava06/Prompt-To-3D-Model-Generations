from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.config import settings
from app.core import database

USER_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")
PBKDF2_ITERATIONS = 210_000
COMMON_PASSWORDS = {
    "admin",
    "admin123",
    "password",
    "password1",
    "password123",
    "qwerty123",
    "letmein123",
    "welcome123",
    "changeme123",
    "12345678",
    "123456789",
    "1234567890",
}


@dataclass(frozen=True)
class User:
    user_id: str
    display_name: str
    created_at: str


@dataclass(frozen=True)
class SessionUser(User):
    token_hash: str


class AuthError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def validate_user_id(user_id: str) -> str:
    value = user_id.strip()
    if not USER_ID_PATTERN.fullmatch(value):
        raise AuthError(
            422,
            "User ID must be 3-32 characters using letters, numbers, dot, underscore, or hyphen.",
        )
    return value


def validate_password(password: str, user_id: str | None = None, display_name: str | None = None) -> str:
    if len(password) < settings.min_password_chars:
        raise AuthError(422, f"Password must be at least {settings.min_password_chars} characters.")
    normalized = password.lower()
    if normalized in COMMON_PASSWORDS:
        raise AuthError(422, "Password is too common.")
    if user_id and user_id.lower() in normalized:
        raise AuthError(422, "Password must not contain the user ID.")
    if display_name and display_name.strip() and display_name.lower().strip() in normalized:
        raise AuthError(422, "Password must not contain the display name.")
    if re.search(r"(.)\1{3,}", password):
        raise AuthError(422, "Password must not contain long repeated character runs.")

    checks = [
        bool(re.search(r"[a-z]", password)),
        bool(re.search(r"[A-Z]", password)),
        bool(re.search(r"\d", password)),
        bool(re.search(r"[^A-Za-z0-9]", password)),
    ]
    if sum(checks) < 3:
        raise AuthError(
            422,
            "Password must include at least three of: lowercase, uppercase, number, symbol.",
        )
    return password


def _encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii")


def _decode(data: str) -> bytes:
    return base64.urlsafe_b64decode(data.encode("ascii"))


def _password_hash(password: str, salt: bytes) -> str:
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS,
    )
    return _encode(digest)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _user_from_row(row) -> User:
    return User(
        user_id=row["user_id"],
        display_name=row["display_name"],
        created_at=row["created_at"],
    )


def create_user(user_id: str, password: str, display_name: str | None = None) -> User:
    clean_user_id = validate_user_id(user_id)
    clean_display_name = (display_name or clean_user_id).strip()[:80] or clean_user_id
    validate_password(password, clean_user_id, clean_display_name)
    salt = os.urandom(16)
    now = database.utc_now_iso()

    try:
        database.execute(
            """
            INSERT INTO users (user_id, display_name, password_salt, password_hash, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                clean_user_id,
                clean_display_name,
                _encode(salt),
                _password_hash(password, salt),
                now,
            ),
        )
    except Exception as exc:
        error_text = str(exc).lower()
        if "unique constraint" in error_text or "duplicate key" in error_text:
            raise AuthError(409, "User ID is already taken.") from exc
        raise

    return User(clean_user_id, clean_display_name, now)


def authenticate_user(user_id: str, password: str) -> User:
    clean_user_id = validate_user_id(user_id)
    row = database.fetch_one("SELECT * FROM users WHERE user_id = ?", (clean_user_id,))
    if row is None:
        raise AuthError(401, "Invalid user ID or password.")

    expected_hash = row["password_hash"]
    actual_hash = _password_hash(password, _decode(row["password_salt"]))
    if not hmac.compare_digest(expected_hash, actual_hash):
        raise AuthError(401, "Invalid user ID or password.")

    return _user_from_row(row)


def create_session(user_id: str) -> str:
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    expires = now + timedelta(hours=settings.session_ttl_hours)
    database.execute(
        """
        INSERT INTO sessions (token_hash, user_id, created_at, expires_at, revoked_at)
        VALUES (?, ?, ?, ?, NULL)
        """,
        (
            _token_hash(token),
            user_id,
            now.isoformat(),
            expires.isoformat(),
        ),
    )
    return token


def get_session_user(token: str) -> SessionUser | None:
    row = database.fetch_one(
        """
        SELECT users.user_id, users.display_name, users.created_at, sessions.token_hash, sessions.expires_at
        FROM sessions
        JOIN users ON users.user_id = sessions.user_id
        WHERE sessions.token_hash = ? AND sessions.revoked_at IS NULL
        """,
        (_token_hash(token),),
    )
    if row is None:
        return None

    expires_at = datetime.fromisoformat(row["expires_at"])
    if expires_at <= datetime.now(timezone.utc):
        revoke_session_hash(row["token_hash"])
        return None

    return SessionUser(
        user_id=row["user_id"],
        display_name=row["display_name"],
        created_at=row["created_at"],
        token_hash=row["token_hash"],
    )


def revoke_session_hash(token_hash: str) -> None:
    database.execute(
        "UPDATE sessions SET revoked_at = ? WHERE token_hash = ? AND revoked_at IS NULL",
        (database.utc_now_iso(), token_hash),
    )


def change_password(user_id: str, current_password: str, new_password: str, current_token_hash: str) -> None:
    authenticate_user(user_id, current_password)
    validate_password(new_password, user_id)
    salt = os.urandom(16)
    database.execute(
        """
        UPDATE users
        SET password_salt = ?, password_hash = ?
        WHERE user_id = ?
        """,
        (_encode(salt), _password_hash(new_password, salt), user_id),
    )
    database.execute(
        """
        UPDATE sessions
        SET revoked_at = ?
        WHERE user_id = ? AND token_hash != ? AND revoked_at IS NULL
        """,
        (database.utc_now_iso(), user_id, current_token_hash),
    )