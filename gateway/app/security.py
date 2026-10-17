"""Passwords, API keys and dashboard session tokens. Standard library only.

Why two different hashes:
- Passwords are chosen by humans and guessable, so they get a slow, salted hash (scrypt).
- API keys are 256 bits of randomness, so there is nothing to guess. A plain SHA-256 is
  enough, and it lets us look a key up by its hash in one indexed query.
"""
import base64
import hashlib
import hmac
import secrets
import time

from . import config


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, salt_hex, digest_hex = stored.split("$")
        digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex), n=2**14, r=8, p=1)
    except ValueError:
        return False
    return hmac.compare_digest(digest.hex(), digest_hex)


def new_api_key() -> tuple[str, str, str]:
    """Return (plaintext key, display prefix, sha256 hash). The plaintext is shown once."""
    key = "gw_" + secrets.token_urlsafe(32)
    return key, key[:10], hash_key(key)


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def make_session_token(user_id: int) -> str:
    payload = f"{user_id}.{int(time.time()) + config.SESSION_TTL_SECONDS}"
    sig = hmac.new(config.SESSION_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(f"{payload}.{sig}".encode()).decode()


def read_session_token(token: str) -> int | None:
    """Return the user id if the token is genuine and not expired, else None."""
    try:
        raw = base64.urlsafe_b64decode(token.encode()).decode()
        user_id, expires, sig = raw.split(".")
        payload = f"{user_id}.{expires}"
    except Exception:
        return None
    expected = hmac.new(config.SESSION_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected) or int(expires) < time.time():
        return None
    return int(user_id)