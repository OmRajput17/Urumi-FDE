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

# Chat agent: any OpenAI-compatible chat API. Defaults point at Groq.
# The key comes from a Kubernetes Secret. Empty means the chat agent is switched off.
LLM_BASE_URL = _get("LLM_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")
LLM_MODEL = _get("LLM_MODEL", "llama-3.3-70b-versatile")
LLM_API_KEY = _get("LLM_API_KEY", "")
LLM_TIMEOUT = float(_get("LLM_TIMEOUT", "60"))
# Most tool-call rounds the agent may make for one question.
AGENT_MAX_STEPS = int(_get("AGENT_MAX_STEPS", "6"))