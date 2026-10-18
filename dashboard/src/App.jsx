import { useCallback, useEffect, useState } from "react";
import { api, session, setUnauthorizedHandler } from "./api.js";
import Login from "./pages/Login.jsx";
import Servers from "./pages/Servers.jsx";
import Chat from "./pages/Chat.jsx";
import Team from "./pages/Team.jsx";
import Audit from "./pages/Audit.jsx";

const TABS = [
  { id: "servers", label: "Servers" },
  { id: "chat", label: "Chat" },
  { id: "team", label: "Team & keys" },
  { id: "audit", label: "Audit log" },
];

function tabFromHash() {
  const id = window.location.hash.replace(/^#\/?/, "");
  return TABS.some((t) => t.id === id) ? id : "servers";
}

export default function App() {
  const [user, setUser] = useState(null);
  const [booting, setBooting] = useState(() => Boolean(session.get()));
  const [notice, setNotice] = useState("");
  const [tab, setTab] = useState(tabFromHash);

  const signOut = useCallback((message = "") => {
    session.clear();
    setUser(null);
    setNotice(message);
  }, []);

  useEffect(() => {
    setUnauthorizedHandler(() => signOut("Your session expired. Please sign in again."));
  }, [signOut]);

  // Restore the session after a page reload.
  useEffect(() => {
    if (!session.get()) return;
    api
      .me()
      .then(setUser)
      .catch(() => session.clear())
      .finally(() => setBooting(false));
  }, []);

  useEffect(() => {
    const onHash = () => setTab(tabFromHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  if (booting) return <div className="boot">Loading…</div>;
  if (!user) {
    return (
      <Login
        notice={notice}
        onLogin={(u) => {
          setNotice("");
          setUser(u);
        }}
      />
    );
  }

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true" />
          Team MCP Gateway
        </div>
        <nav aria-label="Main">
          {TABS.map((t) => (
            <a
              key={t.id}
              href={`#/${t.id}`}
              className={tab === t.id ? "tab active" : "tab"}
              aria-current={tab === t.id ? "page" : undefined}
            >
              {t.label}
            </a>
          ))}
        </nav>
        <div className="who">
          <span className="who-email">{user.email}</span>
          <span className={`badge role-${user.role}`}>{user.role}</span>
          <button type="button" className="btn ghost small" onClick={() => signOut()}>
            Sign out
          </button>
        </div>
      </header>
      <main>
        {tab === "servers" && <Servers user={user} />}
        {tab === "chat" && <Chat user={user} />}
        {tab === "team" && <Team user={user} />}
        {tab === "audit" && <Audit user={user} />}
      </main>
    </div>
  );
}