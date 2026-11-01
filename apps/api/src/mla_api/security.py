"""Passwords (Argon2id), opaque tokens, role permissions and the login rate limiter."""
from __future__ import annotations

import hashlib
import secrets
import threading
import time
from collections import defaultdict, deque

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from mla_api.models import Role

_hasher = PasswordHasher()
# Verified when the e-mail does not exist, so response time does not reveal registered accounts.
_DUMMY_HASH = _hasher.hash("mla-dummy-password-for-timing")

PASSWORD_MIN = 10
PASSWORD_MAX = 128


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerificationError, InvalidHashError):
        return False


def password_problem(password: str) -> str | None:
    if len(password) < PASSWORD_MIN:
        return f"A senha precisa ter pelo menos {PASSWORD_MIN} caracteres."
    if len(password) > PASSWORD_MAX:
        return f"A senha pode ter no máximo {PASSWORD_MAX} caracteres."
    return None


def new_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# Permissions are checked in the backend on every organization route (deps.require).
PERMISSIONS: dict[str, frozenset[str]] = {
    Role.VIEWER: frozenset({"catalog.read", "members.read"}),
    Role.EDITOR: frozenset({"catalog.read", "catalog.write", "members.read"}),
    Role.ADMIN: frozenset({"catalog.read", "catalog.write", "members.read", "members.manage", "audit.read"}),
    Role.OWNER: frozenset({"catalog.read", "catalog.write", "members.read", "members.manage", "audit.read",
                           "org.manage"}),
}


def has_permission(role: str, permission: str) -> bool:
    return permission in PERMISSIONS.get(role, frozenset())


class LoginLimiter:
    """Counts failed logins per key in a sliding window. In-process only: with several API instances this must
    move to a shared store (documented in MLA_WEB_ARCHITECTURE.md)."""

    def __init__(self, max_failures: int, window_seconds: int):
        self.max_failures = max_failures
        self.window = window_seconds
        self._fails: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _trim(self, key: str, now: float) -> deque[float]:
        q = self._fails[key]
        while q and now - q[0] > self.window:
            q.popleft()
        return q

    def blocked(self, *keys: str) -> bool:
        now = time.monotonic()
        with self._lock:
            return any(len(self._trim(k, now)) >= self.max_failures for k in keys)

    def fail(self, *keys: str) -> None:
        now = time.monotonic()
        with self._lock:
            for k in keys:
                self._trim(k, now).append(now)

    def reset(self, *keys: str) -> None:
        with self._lock:
            for k in keys:
                self._fails.pop(k, None)
