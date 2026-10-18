import { useState } from "react";
import { api, session } from "../api.js";
import { Notice } from "../ui.jsx";

export default function Login({ onLogin, notice }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const res = await api.login(email, password);
      session.set(res.token);
      onLogin(res.user);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-wrap">
      <form className="card login" onSubmit={submit}>
        <div className="brand login-brand">
          <span className="brand-mark" aria-hidden="true" />
          Team MCP Gateway
        </div>
        <p className="muted">Sign in to manage MCP servers, keys and the audit log, or to chat with the tools.</p>
        {notice && <Notice kind="info">{notice}</Notice>}
        {error && <Notice kind="error">{error}</Notice>}
        <label>
          Email
          <input type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} />
        </label>
        <label>
          Password
          <input
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>
        <button type="submit" className="btn primary" disabled={busy}>
          {busy ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </div>
  );
}