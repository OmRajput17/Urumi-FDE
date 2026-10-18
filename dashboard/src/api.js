// Every call goes to /api on the same origin. In the cluster the Ingress sends /api to the
// gateway; in `npm run dev` the Vite proxy does. The browser never talks to an upstream MCP
// server and never sees an upstream credential.
//
// The login token lives in sessionStorage, not localStorage: it is per tab, so two people (or
// an admin and a member in two tabs) can be signed in at once, and it disappears on close.
const KEY = "gateway_token";

export const session = {
  get() {
    try {
      return sessionStorage.getItem(KEY);
    } catch {
      return null;
    }
  },
  set(token) {
    try {
      sessionStorage.setItem(KEY, token);
    } catch {
      /* storage blocked: the user just has to sign in again after a reload */
    }
  },
  clear() {
    try {
      sessionStorage.removeItem(KEY);
    } catch {
      /* nothing to clear */
    }
  },
};

let onUnauthorized = () => {};
export function setUnauthorizedHandler(fn) {
  onUnauthorized = fn;
}

export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

function messageOf(data) {
  if (!data) return "";
  if (typeof data.detail === "string") return data.detail;
  if (Array.isArray(data.detail)) return data.detail.map((d) => d.msg).join("; ");
  return data.error || "";
}

async function request(method, path, body) {
  const headers = {};
  const token = session.get();
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";
  let res;
  try {
    res = await fetch(`/api${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, "Cannot reach the gateway. Check that it is running.");
  }
  if (res.status === 204) return null;
  let data = null;
  try {
    data = await res.json();
  } catch {
    /* empty or non-JSON body */
  }
  if (!res.ok) {
    if (res.status === 401 && path !== "/login") onUnauthorized();
    throw new ApiError(res.status, messageOf(data) || `Request failed (${res.status})`);
  }
  return data;
}

export const api = {
  login: (email, password) => request("POST", "/login", { email, password }),
  me: () => request("GET", "/me"),

  servers: () => request("GET", "/servers"),
  addServer: (body) => request("POST", "/servers", body),
  updateServer: (id, body) => request("PATCH", `/servers/${id}`, body),
  deleteServer: (id) => request("DELETE", `/servers/${id}`),
  refreshServer: (id) => request("POST", `/servers/${id}/refresh`),

  users: () => request("GET", "/users"),
  inviteUser: (body) => request("POST", "/users", body),
  updateUser: (id, body) => request("PATCH", `/users/${id}`, body),

  keys: (all) => request("GET", `/keys${all ? "?all=true" : ""}`),
  createKey: (name) => request("POST", "/keys", { name }),
  revokeKey: (id) => request("DELETE", `/keys/${id}`),

  audit: (limit = 200) => request("GET", `/audit?limit=${limit}`),

  chatStatus: () => request("GET", "/chat/status"),
  chat: (messages) => request("POST", "/chat", { messages }),
};