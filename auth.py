"""
MediAssistAI - Authentication
===============================
Minimal username/password auth using only the Python standard library
(hashlib PBKDF2 + secrets) - no extra dependency needed.

Flow:
  1. POST /api/auth/register {username, password, display_name}
  2. POST /api/auth/login    {username, password} -> {token}
  3. Every subsequent request sends `Authorization: Bearer <token>`
  4. POST /api/auth/logout invalidates the token
"""
import hashlib
import os
import re
import secrets

from backend import database as db

_USERNAME_RE = re.compile(r"^[a-zA-Z0-9_.]{3,32}$")
_PBKDF2_ITERATIONS = 200_000


def _hash_password(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt),
        _PBKDF2_ITERATIONS).hex()


def validate_username(username: str) -> str:
    """Returns an error message, or '' if the username is valid."""
    if not username or not _USERNAME_RE.match(username):
        return ("Username must be 3-32 characters: letters, numbers, "
               "underscore, or dot only.")
    return ""


def validate_password(password: str) -> str:
    if not password or len(password) < 6:
        return "Password must be at least 6 characters."
    return ""


def register(username: str, password: str, display_name: str = "") -> str:
    """Creates a new user. Returns an error message, or '' on success."""
    err = validate_username(username)
    if err:
        return err
    err = validate_password(password)
    if err:
        return err
    if db.get_user(username):
        return "That username is already taken."

    salt = secrets.token_hex(16)
    password_hash = _hash_password(password, salt)
    db.create_user(username, password_hash, salt,
                   display_name.strip() or username)
    return ""


def verify_login(username: str, password: str) -> bool:
    user = db.get_user(username)
    if not user:
        return False
    expected = _hash_password(password, user["salt"])
    return secrets.compare_digest(expected, user["password_hash"])


def login(username: str, password: str):
    """Returns (token, display_name) on success, or (None, None)."""
    if not verify_login(username, password):
        return None, None
    user = db.get_user(username)
    token = db.create_token(username)
    return token, user["display_name"]


def logout(token: str):
    db.delete_token(token)


def current_username(authorization_header: str):
    """Extracts and validates the bearer token from an Authorization header.
    Returns the username, or None if missing/invalid."""
    if not authorization_header or not authorization_header.startswith("Bearer "):
        return None
    token = authorization_header[len("Bearer "):].strip()
    if not token:
        return None
    return db.get_username_from_token(token)
