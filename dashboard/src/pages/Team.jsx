import { useCallback, useState } from "react";
import { api } from "../api.js";
import { usePoll } from "../hooks.js";
import { Badge, CopyButton, Empty, Notice, formatTime } from "../ui.jsx";

export default function Team({ user }) {
  const isAdmin = user.role === "admin";
  return (
    <section>
      <div className="page-head">
        <div>
          <h1>Team &amp; keys</h1>
          <p className="muted">
            Your API key lets an MCP client use every enabled server through one URL, with no upstream credentials.
          </p>
        </div>
      </div>
      <Connect />
      <Keys isAdmin={isAdmin} />
      {isAdmin && <Members me={user} />}
    </section>
  );
}

function Connect() {
  const url = `${window.location.origin}/mcp`;
  const claude = `claude mcp add --transport http gateway ${url} --header "Authorization: Bearer YOUR_KEY"`;
  return (
    <div className="card">
      <h2>Connect an MCP client</h2>
      <p className="muted">
        Add this URL and your key to Claude Code, Cursor or MCP Inspector (Streamable HTTP, header{" "}
        <code>Authorization: Bearer &lt;key&gt;</code>).
      </p>
      <div className="copy-row">
        <code className="block">{url}</code>
        <CopyButton text={url} label="Copy URL" />
      </div>
      <div className="copy-row">
        <code className="block">{claude}</code>
        <CopyButton text={claude} label="Copy command" />
      </div>
    </div>
  );
}

function Keys({ isAdmin }) {
  const [showAll, setShowAll] = useState(false);
  const [name, setName] = useState("");
  const [fresh, setFresh] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const load = useCallback(() => api.keys(isAdmin && showAll), [isAdmin, showAll]);
  const { data: keys, error: loadError, refresh } = usePoll(load, 10000, showAll);

  async function create(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const created = await api.createKey(name.trim() || "default");
      setFresh(created);
      setName("");
      await refresh();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function revoke(k) {
    if (!window.confirm(`Revoke the key “${k.name}” (${k.prefix}…)? Clients using it are rejected immediately.`)) return;
    setError("");
    try {
      await api.revokeKey(k.id);
      await refresh();
    } catch (err) {
      setError(err.message);
    }
  }

  const list = keys || [];
  return (
    <div className="card">
      <div className="card-head">
        <h2>{isAdmin && showAll ? "All API keys" : "My API keys"}</h2>
        {isAdmin && (
          <label className="check">
            <input type="checkbox" checked={showAll} onChange={(e) => setShowAll(e.target.checked)} />
            Show everyone’s keys
          </label>
        )}
      </div>

      {fresh && (
        <div className="fresh" role="status">
          <strong>Copy your new key now. It is shown only once.</strong>
          <div className="copy-row">
            <code className="block key">{fresh.key}</code>
            <CopyButton text={fresh.key} label="Copy key" />
          </div>
          <button type="button" className="btn ghost small" onClick={() => setFresh(null)}>
            I have saved it
          </button>
        </div>
      )}

      {(error || loadError) && <Notice kind="error">{error || loadError}</Notice>}

      <form className="inline-form" onSubmit={create}>
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Key name, for example cursor"
          maxLength={60}
          aria-label="Key name"
        />
        <button type="submit" className="btn primary" disabled={busy}>
          Generate key
        </button>
      </form>

      {list.length === 0 ? (
        <Empty>No keys yet.</Empty>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Key</th>
                {showAll && isAdmin && <th>Owner</th>}
                <th>Created</th>
                <th>Status</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {list.map((k) => (
                <tr key={k.id} className={k.revoked_at ? "dim" : ""}>
                  <td>{k.name}</td>
                  <td>
                    <code>{k.prefix}…</code>
                  </td>
                  {showAll && isAdmin && <td>{k.user_email}</td>}
                  <td>{formatTime(k.created_at)}</td>
                  <td>{k.revoked_at ? <Badge kind="off">Revoked</Badge> : <Badge kind="ok">Active</Badge>}</td>
                  <td className="right">
                    {!k.revoked_at && (
                      <button type="button" className="btn small danger" onClick={() => revoke(k)}>
                        Revoke
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="muted small-text">Only a hash of each key is stored, so a lost key cannot be shown again. Generate a new one.</p>
    </div>
  );
}

function Members({ me }) {
  const { data: users, error: loadError, refresh } = usePoll(api.users, 15000);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("member");
  const [error, setError] = useState("");
  const [ok, setOk] = useState("");
  const [busy, setBusy] = useState(false);

  async function invite(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    setOk("");
    try {
      const u = await api.inviteUser({ email, password, role });
      setOk(`Created ${u.email} as ${u.role}. Share the initial password with them directly.`);
      setEmail("");
      setPassword("");
      await refresh();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function change(u, body) {
    setError("");
    setOk("");
    try {
      await api.updateUser(u.id, body);
      await refresh();
    } catch (err) {
      setError(err.message);
    }
  }

  const list = users || [];
  return (
    <div className="card">
      <h2>Members</h2>
      {(error || loadError) && <Notice kind="error">{error || loadError}</Notice>}
      {ok && (
        <Notice kind="success" onClose={() => setOk("")}>
          {ok}
        </Notice>
      )}
      <form className="inline-form" onSubmit={invite}>
        <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="Email" aria-label="Email" />
        <input
          type="password"
          required
          minLength={8}
          autoComplete="new-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="Initial password (8+ characters)"
          aria-label="Initial password"
        />
        <select value={role} onChange={(e) => setRole(e.target.value)} aria-label="Role">
          <option value="member">Member</option>
          <option value="admin">Admin</option>
        </select>
        <button type="submit" className="btn primary" disabled={busy}>
          Invite
        </button>
      </form>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Email</th>
              <th>Role</th>
              <th>Status</th>
              <th>Created</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {list.map((u) => {
              const self = u.id === me.id;
              return (
                <tr key={u.id} className={u.disabled ? "dim" : ""}>
                  <td>
                    {u.email} {self && <span className="muted">(you)</span>}
                  </td>
                  <td>
                    <select
                      value={u.role}
                      disabled={self}
                      aria-label={`Role of ${u.email}`}
                      onChange={(e) => change(u, { role: e.target.value })}
                    >
                      <option value="member">Member</option>
                      <option value="admin">Admin</option>
                    </select>
                  </td>
                  <td>{u.disabled ? <Badge kind="off">Disabled</Badge> : <Badge kind="ok">Active</Badge>}</td>
                  <td>{formatTime(u.created_at)}</td>
                  <td className="right">
                    {!self && (
                      <button type="button" className="btn small" onClick={() => change(u, { disabled: !u.disabled })}>
                        {u.disabled ? "Enable" : "Disable"}
                      </button>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}