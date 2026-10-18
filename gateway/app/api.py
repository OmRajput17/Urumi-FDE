"""Admin and member REST API used by the dashboard (and later the chat agent)."""
import re

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from . import agent, core, db, security

router = APIRouter(prefix="/api")

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,30}$")  # no underscores, so "__" is a safe separator
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ---------- auth dependencies ----------

def current_user(authorization: str = Header(default="")) -> dict:
    token = authorization[7:].strip() if authorization.lower().startswith("bearer ") else ""
    user_id = security.read_session_token(token) if token else None
    user = db.one("SELECT id, email, role, disabled FROM users WHERE id = ?", (user_id,)) if user_id else None
    if not user or user["disabled"]:
        raise HTTPException(401, "Not logged in")
    return user


def admin_user(user: dict = Depends(current_user)) -> dict:
    if user["role"] != "admin":
        raise HTTPException(403, "Admins only")
    return user


# ---------- login ----------

class LoginBody(BaseModel):
    email: str
    password: str


@router.post("/login")
def login(body: LoginBody):
    user = db.one("SELECT * FROM users WHERE email = ?", (body.email.strip().lower(),))
    if not user or user["disabled"] or not security.verify_password(body.password, user["password_hash"]):
        raise HTTPException(401, "Wrong email or password")
    return {
        "token": security.make_session_token(user["id"]),
        "user": {"id": user["id"], "email": user["email"], "role": user["role"]},
    }


@router.get("/me")
def me(user: dict = Depends(current_user)):
    return {"id": user["id"], "email": user["email"], "role": user["role"]}


# ---------- upstream servers ----------

def server_view(s: dict) -> dict:
    """What the browser may see. The credential never leaves the server: only a yes/no flag."""
    enabled = bool(s["enabled"])
    return {
        "id": s["id"],
        "slug": s["slug"],
        "url": s["url"],
        "auth_type": s["auth_type"],
        "auth_header_name": s["auth_header_name"],
        "has_credential": bool(s["credential"]),
        "enabled": enabled,
        "status": s["status"] if enabled else "disabled",
        "status_detail": s["status_detail"],
        "last_checked": s["last_checked"],
        "tools": [
            {"name": core.public_name(s["slug"], t["name"]), "description": t["description"]}
            for t in core.tools_of(s)
        ],
    }


class ServerCreate(BaseModel):
    slug: str
    url: str
    auth_type: str = "none"
    auth_header_name: str | None = None
    credential: str | None = None
    enabled: bool = True


class ServerUpdate(BaseModel):
    url: str | None = None
    auth_type: str | None = None
    auth_header_name: str | None = None
    credential: str | None = None  # None = keep the stored one, "" = clear it
    enabled: bool | None = None


def _check_server_fields(url: str | None, auth_type: str | None):
    if url is not None and not re.match(r"^https?://\S+$", url):
        raise HTTPException(422, "url must start with http:// or https://")
    if auth_type is not None and auth_type not in ("none", "bearer", "header"):
        raise HTTPException(422, "auth_type must be none, bearer or header")


@router.get("/servers")
def list_servers(user: dict = Depends(current_user)):
    return [server_view(s) for s in db.query("SELECT * FROM servers ORDER BY slug")]


@router.post("/servers", status_code=201)
async def add_server(body: ServerCreate, admin: dict = Depends(admin_user)):
    if not SLUG_RE.match(body.slug):
        raise HTTPException(422, "slug must be lowercase letters, digits and hyphens (max 31 chars)")
    _check_server_fields(body.url, body.auth_type)
    if db.one("SELECT id FROM servers WHERE slug = ?", (body.slug,)):
        raise HTTPException(409, "A server with this slug already exists")
    server_id = db.execute(
        "INSERT INTO servers (slug, url, auth_type, auth_header_name, credential, enabled, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (body.slug, body.url, body.auth_type, body.auth_header_name, body.credential or None,
         int(body.enabled), db.now()),
    )
    await core.refresh_server(server_id)
    return server_view(db.one("SELECT * FROM servers WHERE id = ?", (server_id,)))


@router.patch("/servers/{server_id}")
async def update_server(server_id: int, body: ServerUpdate, admin: dict = Depends(admin_user)):
    server = db.one("SELECT * FROM servers WHERE id = ?", (server_id,))
    if not server:
        raise HTTPException(404, "No such server")
    _check_server_fields(body.url, body.auth_type)
    values = {
        "url": body.url if body.url is not None else server["url"],
        "auth_type": body.auth_type if body.auth_type is not None else server["auth_type"],
        "auth_header_name": body.auth_header_name if body.auth_header_name is not None else server["auth_header_name"],
        "credential": server["credential"] if body.credential is None else (body.credential or None),
        "enabled": int(body.enabled) if body.enabled is not None else server["enabled"],
    }
    db.execute(
        "UPDATE servers SET url=?, auth_type=?, auth_header_name=?, credential=?, enabled=? WHERE id=?",
        (values["url"], values["auth_type"], values["auth_header_name"], values["credential"],
         values["enabled"], server_id),
    )
    await core.refresh_server(server_id)
    return server_view(db.one("SELECT * FROM servers WHERE id = ?", (server_id,)))


@router.delete("/servers/{server_id}", status_code=204)
def delete_server(server_id: int, admin: dict = Depends(admin_user)):
    db.execute("DELETE FROM servers WHERE id = ?", (server_id,))


@router.post("/servers/{server_id}/refresh")
async def refresh_server(server_id: int, admin: dict = Depends(admin_user)):
    if not db.one("SELECT id FROM servers WHERE id = ?", (server_id,)):
        raise HTTPException(404, "No such server")
    await core.refresh_server(server_id)
    return server_view(db.one("SELECT * FROM servers WHERE id = ?", (server_id,)))


# ---------- users ----------

class UserCreate(BaseModel):
    email: str
    password: str
    role: str = "member"


class UserUpdate(BaseModel):
    role: str | None = None
    disabled: bool | None = None
    password: str | None = None


def user_view(u: dict) -> dict:
    return {"id": u["id"], "email": u["email"], "role": u["role"], "disabled": bool(u["disabled"]),
            "created_at": u["created_at"]}


@router.get("/users")
def list_users(admin: dict = Depends(admin_user)):
    return [user_view(u) for u in db.query("SELECT * FROM users ORDER BY id")]


@router.post("/users", status_code=201)
def invite_user(body: UserCreate, admin: dict = Depends(admin_user)):
    """'Invite' = the admin creates the account with an initial password and shares it."""
    email = body.email.strip().lower()
    if not EMAIL_RE.match(email):
        raise HTTPException(422, "Invalid email")
    if body.role not in ("admin", "member"):
        raise HTTPException(422, "role must be admin or member")
    if len(body.password) < 8:
        raise HTTPException(422, "Password must be at least 8 characters")
    if db.one("SELECT id FROM users WHERE email = ?", (email,)):
        raise HTTPException(409, "A user with this email already exists")
    user_id = db.execute(
        "INSERT INTO users (email, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
        (email, security.hash_password(body.password), body.role, db.now()),
    )
    return user_view(db.one("SELECT * FROM users WHERE id = ?", (user_id,)))


@router.patch("/users/{user_id}")
def update_user(user_id: int, body: UserUpdate, admin: dict = Depends(admin_user)):
    user = db.one("SELECT * FROM users WHERE id = ?", (user_id,))
    if not user:
        raise HTTPException(404, "No such user")
    if body.role is not None and body.role not in ("admin", "member"):
        raise HTTPException(422, "role must be admin or member")
    if body.password is not None and len(body.password) < 8:
        raise HTTPException(422, "Password must be at least 8 characters")
    if user_id == admin["id"] and (body.disabled or body.role == "member"):
        raise HTTPException(400, "You cannot disable or demote yourself")
    db.execute(
        "UPDATE users SET role=?, disabled=?, password_hash=? WHERE id=?",
        (
            body.role or user["role"],
            int(body.disabled) if body.disabled is not None else user["disabled"],
            security.hash_password(body.password) if body.password else user["password_hash"],
            user_id,
        ),
    )
    return user_view(db.one("SELECT * FROM users WHERE id = ?", (user_id,)))


# ---------- API keys ----------

class KeyCreate(BaseModel):
    name: str = "default"
    user_id: int | None = None  # admins may issue a key for someone else


def key_view(k: dict) -> dict:
    return {"id": k["id"], "user_email": k["email"], "name": k["name"], "prefix": k["prefix"],
            "created_at": k["created_at"], "revoked_at": k["revoked_at"]}


@router.get("/keys")
def list_keys(all: bool = False, user: dict = Depends(current_user)):
    sql = "SELECT k.*, u.email FROM api_keys k JOIN users u ON u.id = k.user_id"
    if all and user["role"] == "admin":
        return [key_view(k) for k in db.query(sql + " ORDER BY k.id DESC")]
    return [key_view(k) for k in db.query(sql + " WHERE k.user_id = ? ORDER BY k.id DESC", (user["id"],))]


@router.post("/keys", status_code=201)
def create_key(body: KeyCreate, user: dict = Depends(current_user)):
    owner_id = body.user_id or user["id"]
    if owner_id != user["id"] and user["role"] != "admin":
        raise HTTPException(403, "Only admins can issue keys for other users")
    if not db.one("SELECT id FROM users WHERE id = ?", (owner_id,)):
        raise HTTPException(404, "No such user")
    key, prefix, key_hash = security.new_api_key()
    key_id = db.execute(
        "INSERT INTO api_keys (user_id, name, prefix, key_hash, created_at) VALUES (?, ?, ?, ?, ?)",
        (owner_id, body.name[:60] or "default", prefix, key_hash, db.now()),
    )
    row = db.one("SELECT k.*, u.email FROM api_keys k JOIN users u ON u.id = k.user_id WHERE k.id = ?", (key_id,))
    # The plaintext key is returned exactly once. Only its hash is stored.
    return {**key_view(row), "key": key}


@router.delete("/keys/{key_id}", status_code=204)
def revoke_key(key_id: int, user: dict = Depends(current_user)):
    key = db.one("SELECT * FROM api_keys WHERE id = ?", (key_id,))
    if not key or (key["user_id"] != user["id"] and user["role"] != "admin"):
        raise HTTPException(404, "No such key")
    db.execute("UPDATE api_keys SET revoked_at = COALESCE(revoked_at, ?) WHERE id = ?", (db.now(), key_id))


# ---------- chat agent ----------

class ChatMessage(BaseModel):
    role: str
    content: str


class ChatBody(BaseModel):
    messages: list[ChatMessage]


@router.get("/chat/status")
def chat_status(user: dict = Depends(current_user)):
    return {"enabled": agent.configured()}


@router.post("/chat")
async def chat(body: ChatBody, user: dict = Depends(current_user)):
    """Run one chat turn as the logged-in user. Tool calls are audited under that user."""
    if not agent.configured():
        raise HTTPException(503, "The chat agent is not configured. Set llm.apiKey in the Helm values.")
    history = body.messages[-20:]
    if not history or history[-1].role != "user":
        raise HTTPException(422, "The last message must be from the user")
    if any(m.role not in ("user", "assistant") or len(m.content) > 4000 for m in history):
        raise HTTPException(422, "Messages must be user or assistant text under 4000 characters")
    try:
        return await agent.run(user, [{"role": m.role, "content": m.content} for m in history])
    except agent.AgentError as exc:
        raise HTTPException(502, str(exc)) from None


# ---------- audit log ----------

@router.get("/audit")
def audit(limit: int = 100, user: dict = Depends(current_user)):
    limit = max(1, min(limit, 500))
    if user["role"] == "admin":
        return db.query("SELECT * FROM audit ORDER BY id DESC LIMIT ?", (limit,))
    return db.query("SELECT * FROM audit WHERE user_id = ? ORDER BY id DESC LIMIT ?", (user["id"], limit))