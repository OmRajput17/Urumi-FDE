import { useState } from "react";
import { api } from "../api.js";
import { usePoll } from "../hooks.js";
import { Badge, Empty, Notice, formatTime } from "../ui.jsx";

const OUTCOME_KIND = { success: "ok", error: "bad", timeout: "warn", rejected: "bad" };

export default function Audit({ user }) {
  const isAdmin = user.role === "admin";
  const { data: rows, error, loading } = usePoll(() => api.audit(200), 5000);
  const [outcome, setOutcome] = useState("all");
  const [text, setText] = useState("");

  const needle = text.trim().toLowerCase();
  const list = (rows || []).filter(
    (r) =>
      (outcome === "all" || r.outcome === outcome) &&
      (!needle || `${r.user_email} ${r.server} ${r.tool}`.toLowerCase().includes(needle)),
  );

  return (
    <section>
      <div className="page-head">
        <div>
          <h1>Audit log</h1>
          <p className="muted">
            {isAdmin ? "Every tool call from every user" : "Your tool calls"}: from MCP clients and from the chat agent.
            Newest first, latest 200, updates every 5 seconds.
          </p>
        </div>
      </div>
      <div className="filters">
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Filter by user, server or tool"
          aria-label="Filter"
        />
        <select value={outcome} onChange={(e) => setOutcome(e.target.value)} aria-label="Outcome">
          <option value="all">All outcomes</option>
          <option value="success">Success</option>
          <option value="error">Error</option>
          <option value="timeout">Timeout</option>
          <option value="rejected">Rejected</option>
        </select>
      </div>
      {error && <Notice kind="error">{error}</Notice>}
      {loading && !rows && <Empty>Loading…</Empty>}
      {rows && list.length === 0 && <Empty>No calls match.</Empty>}
      {list.length > 0 && (
        <div className="card flush">
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>When</th>
                  <th>User</th>
                  <th>Server</th>
                  <th>Tool</th>
                  <th className="right">Duration</th>
                  <th>Outcome</th>
                  <th>Detail</th>
                </tr>
              </thead>
              <tbody>
                {list.map((r) => (
                  <tr key={r.id}>
                    <td className="nowrap">{formatTime(r.ts)}</td>
                    <td>{r.user_email}</td>
                    <td>{r.server}</td>
                    <td>
                      <code>{r.tool}</code>
                    </td>
                    <td className="right nowrap">{r.duration_ms} ms</td>
                    <td>
                      <Badge kind={OUTCOME_KIND[r.outcome] || "off"}>{r.outcome}</Badge>
                    </td>
                    <td className="detail">{r.detail}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </section>
  );
}