"""All configuration comes from environment variables (Secrets and Helm values in the cluster)."""
import os


def _get(name: str, default: str | None = None) -> str:
    value = os.environ.get(name, default)
    if value is None:
        raise RuntimeError(f"Missing required environment variable {name}")
    return value


DB_PATH = _get("DB_PATH", "gateway.db")

# Signs dashboard session tokens. Must come from a Secret, never from source code.
SESSION_SECRET = _get("SESSION_SECRET")
SESSION_TTL_SECONDS = int(_get("SESSION_TTL_SECONDS", str(12 * 3600)))

# The first admin is created on startup if the users table is empty.
ADMIN_EMAIL = _get("ADMIN_EMAIL", "admin@example.com")
ADMIN_PASSWORD = _get("ADMIN_PASSWORD")

# Pre-registers the WooCommerce MCP server as the first upstream (empty = skip).
SEED_WOO_URL = _get("SEED_WOO_URL", "")

# Seconds to wait when asking an upstream for its tool list.
LIST_TIMEOUT = float(_get("LIST_TIMEOUT", "5"))
# Seconds to wait for one tool call before returning a clear timeout error.
CALL_TIMEOUT = float(_get("CALL_TIMEOUT", "30"))
# How often the background loop re-checks every enabled upstream.
REFRESH_INTERVAL = float(_get("REFRESH_INTERVAL", "15"))