import { useState } from "react";
import { api } from "../api.js";
import { usePoll } from "../hooks.js";
import { Badge, Empty, Notice, timeAgo } from "../ui.jsx";

const STATUS = {
  connected: ["Connected", "ok"],
  unreachable: ["Unreachable", "bad"],
  disabled: ["Disabled", "off"],
  unknown: ["Checking…", "off"],
};
const SLUG_RE = /^[a-z0-9][a-z0-9-]{0,30}$/;

function firstLine(text, max = 150) {
  const line = (text || "").trim().split("\n")[0];
  return line.length > max ? `${line.slice(0, max - 1)}…` : line;
}

export default function Servers({ user }) {
  const isAdmin = user.role === "admin";
  const { data: servers, error, loading, refresh } = usePoll(api.servers, 5000);
  const [form, setForm] = useState(null); // null | "new" | a server being edited
  const [flash, setFlash] = useState(null);
  const [busyId, setBusyId] = useState(null);
  const [open, setOpen] = useState({});

  async function act(id, fn, okMessage) {
    setBusyId(id);
    setFlash(null);
    try {
      await fn();
      await refresh();
      if (okMessage) setFlash({ kind: "success", text: okMessage });
    } catch (e) {
      setFlash({ kind: "error", text: e.message });
    } finally {
      setBusyId(null);
    }
  }

  const list = servers || [];
  const count = (s) => list.filter((x) => x.status === s).length;

  return (
    <section>
      <div className="page-head">
        <div>
          <h1>MCP servers</h1>
          <p className="muted">
            Every tool below is available through the gateway as <code>server__tool</code>.
            {!isAdmin && " Upstream credentials are managed by admins and are never shown."}
          </p>
        </div>
        {isAdmin && (
          <button type="button" className="btn primary" onClick={() => setForm("new")}>
            Add server
          </button>
        )}
      </div>

      <div className="summary">
        <span>
          <Badge kind="ok">{count("connected")}</Badge> connected
        </span>
        <span>
          <Badge kind="bad">{count("unreachable")}</Badge> unreachable
        </span>
        <span>
          <Badge kind="off">{count("disabled")}</Badge> disabled
        </span>
        <span className="muted small-text">Updates every 5 seconds</span>
      </div>

      {error && <Notice kind="error">{error}</Notice>}
      {flash && (
        <Notice kind={flash.kind} onClose={() => setFlash(null)}>
          {flash.text}
        </Notice>
      )}

      {form && (
        <ServerForm
          server={form === "new" ? null : form}
          onCancel={() => setForm(null)}
          onSaved={(s, verb) => {
            setForm(null);
            refresh();
            setFlash({
              kind: s.status === "connected" || s.status === "disabled" ? "success" : "error",
              text:
                s.status === "unreachable"
                  ? `${verb} “${s.slug}”, but it is unreachable: ${s.status_detail || "no details"}`
                  : `${verb} “${s.slug}” (${(STATUS[s.status] || STATUS.unknown)[0].toLowerCase()}, ${s.tools.length} tools).`,
            });
          }}
        />
      )}

      {loading && !servers && <Empty>Loading servers…</Empty>}
      {servers && list.length === 0 && <Empty>No servers registered yet.</Empty>}

      <div className="server-list">
        {list.map((s) => {
          const [label, kind] = STATUS[s.status] || STATUS.unknown;
          const busy = busyId === s.id;
          return (
            <article key={s.id} className="card server">
              <div className="server-top">
                <div className="server-name">
                  <h2>{s.slug}</h2>
                  <Badge kind={kind}>{label}</Badge>
                </div>
                {isAdmin && (
                  <div className="actions">
                    <button type="button" className="btn small" disabled={busy} onClick={() => setForm(s)}>
                      Edit
                    </button>
                    <button
                      type="button"
                      className="btn small"
                      disabled={busy}
                      onClick={() =>
                        act(s.id, () => api.updateServer(s.id, { enabled: !s.enabled }), `${s.enabled ? "Disabled" : "Enabled"} “${s.slug}”.`)
                      }
                    >
                      {s.enabled ? "Disable" : "Enable"}
                    </button>
                    <button
                      type="button"
                      className="btn small"
                      disabled={busy}
                      onClick={() => act(s.id, () => api.refreshServer(s.id))}
                    >
                      Check now
                    </button>
                    <button
                      type="button"
                      className="btn small danger"
                      disabled={busy}
                      onClick={() => {
                        if (window.confirm(`Remove “${s.slug}”? Its tools disappear for everyone.`)) {
                          act(s.id, () => api.deleteServer(s.id), `Removed “${s.slug}”.`);
                        }
                      }}
                    >
                      Remove
                    </button>
                  </div>
                )}
              </div>
              <div className="server-meta">
                <code className="url">{s.url}</code>
                <span>
                  {s.auth_type === "none"
                    ? "No credential"
                    : `${s.auth_type === "bearer" ? "Bearer token" : `Header ${s.auth_header_name || "X-API-Key"}`}: ${
                        s.has_credential ? "set" : "missing"
                      }`}
                </span>
                <span>Checked {timeAgo(s.last_checked)}</span>
              </div>
              {s.status === "unreachable" && s.status_detail && (
                <div className="why">Why: {s.status_detail}</div>
              )}
              <button
                type="button"
                className="link"
                aria-expanded={Boolean(open[s.id])}
                onClick={() => setOpen({ ...open, [s.id]: !open[s.id] })}
              >
                {open[s.id] ? "Hide" : "Show"} {s.tools.length} tool{s.tools.length === 1 ? "" : "s"}
              </button>
              {open[s.id] && (
                <ul className="tools-list">
                  {s.tools.map((t) => (
                    <li key={t.name}>
                      <code>{t.name}</code>
                      <span className="muted">{firstLine(t.description)}</span>
                    </li>
                  ))}
                  {s.tools.length === 0 && <li className="muted">No tools known. The server may be disabled or unreachable.</li>}
                </ul>
              )}
            </article>
          );
        })}
      </div>
    </section>
  );
}

function ServerForm({ server, onSaved, onCancel }) {
  const editing = Boolean(server);
  const [slug, setSlug] = useState("");
  const [url, setUrl] = useState(server?.url || "");
  const [authType, setAuthType] = useState(server?.auth_type || "none");
  const [headerName, setHeaderName] = useState(server?.auth_header_name || "");
  const [credential, setCredential] = useState("");
  const [clearCredential, setClearCredential] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setError("");
    if (!editing && !SLUG_RE.test(slug)) {
      setError("Name must be lowercase letters, digits and hyphens, starting with a letter or digit (max 31).");
      return;
    }
    if (!/^https?:\/\/\S+$/.test(url)) {
      setError("URL must start with http:// or https://");
      return;
    }
    if (authType === "header" && !headerName.trim()) {
      setError("Enter the header name the server expects, for example X-API-Key.");
      return;
    }
    setBusy(true);
    try {
      let saved;
      if (editing) {
        const body = { url, auth_type: authType, auth_header_name: headerName.trim() };
        if (authType === "none" || clearCredential) body.credential = "";
        else if (credential) body.credential = credential;
        saved = await api.updateServer(server.id, body);
      } else {
        saved = await api.addServer({
          slug,
          url,
          auth_type: authType,
          auth_header_name: authType === "header" ? headerName.trim() : null,
          credential: authType === "none" ? null : credential || null,
        });
      }
      onSaved(saved, editing ? "Saved" : "Added");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="card form" onSubmit={submit}>
      <h2>{editing ? `Edit ${server.slug}` : "Add an MCP server"}</h2>
      <p className="muted">The server must speak MCP over Streamable HTTP. The gateway checks it as soon as you save.</p>
      {error && <Notice kind="error">{error}</Notice>}
      <div className="grid">
        {!editing && (
          <label>
            Name
            <input value={slug} onChange={(e) => setSlug(e.target.value.trim())} placeholder="utils" required />
            <small>Becomes the prefix of every tool, for example utils__calculate.</small>
          </label>
        )}
        <label className="wide">
          URL
          <input
            value={url}
            onChange={(e) => setUrl(e.target.value.trim())}
            placeholder="http://utils.extras.svc.cluster.local:8000/mcp"
            required
          />
        </label>
        <label>
          Credential type
          <select value={authType} onChange={(e) => setAuthType(e.target.value)}>
            <option value="none">None</option>
            <option value="bearer">Bearer token</option>
            <option value="header">Custom header</option>
          </select>
        </label>
        {authType === "header" && (
          <label>
            Header name
            <input value={headerName} onChange={(e) => setHeaderName(e.target.value)} placeholder="X-API-Key" />
          </label>
        )}
        {authType !== "none" && (
          <label>
            {authType === "bearer" ? "Token" : "Header value"}
            <input
              type="password"
              autoComplete="off"
              value={credential}
              onChange={(e) => setCredential(e.target.value)}
              placeholder={editing && server.has_credential ? "Leave empty to keep the stored value" : ""}
              disabled={clearCredential}
            />
            <small>Stored on the server. It is never shown again and never sent to a browser or MCP client.</small>
          </label>
        )}
      </div>
      {editing && server.has_credential && authType !== "none" && (
        <label className="check">
          <input type="checkbox" checked={clearCredential} onChange={(e) => setClearCredential(e.target.checked)} />
          Remove the stored credential
        </label>
      )}
      <div className="form-actions">
        <button type="submit" className="btn primary" disabled={busy}>
          {busy ? "Checking the server…" : editing ? "Save changes" : "Add server"}
        </button>
        <button type="button" className="btn" onClick={onCancel} disabled={busy}>
          Cancel
        </button>
      </div>
    </form>
  );
}