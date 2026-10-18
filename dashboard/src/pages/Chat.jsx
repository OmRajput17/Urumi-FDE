import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { api } from "../api.js";
import { Badge, Notice } from "../ui.jsx";

const SUGGESTIONS = [
  "What orders came in today?",
  "List the products in the store",
  "Create a product called Mug for 250",
];

// The server accepts at most 4000 characters per message, so older long answers are trimmed.
const MAX_CHARS = 3900;

export default function Chat({ user }) {
  const [messages, setMessages] = useState([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [enabled, setEnabled] = useState(null);
  const [statusError, setStatusError] = useState("");
  const end = useRef(null);

  useEffect(() => {
    api
      .chatStatus()
      .then((s) => setEnabled(s.enabled))
      .catch((e) => setStatusError(e.message));
  }, []);

  useEffect(() => {
    end.current?.scrollIntoView({ block: "end" });
  }, [messages, busy]);

  async function send(content) {
    const question = content.trim();
    if (!question || busy) return;
    const next = [...messages, { role: "user", content: question }];
    setMessages(next);
    setText("");
    setBusy(true);
    try {
      const history = next
        .filter((m) => !m.error)
        .map((m) => ({ role: m.role, content: m.content.slice(0, MAX_CHARS) }));
      const res = await api.chat(history);
      setMessages([...next, { role: "assistant", content: res.reply || "(no answer)", tool_calls: res.tool_calls || [] }]);
    } catch (e) {
      setMessages([...next, { role: "assistant", content: e.message, error: true, tool_calls: [] }]);
    } finally {
      setBusy(false);
    }
  }

  function onKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send(text);
    }
  }

  return (
    <section>
      <div className="page-head">
        <div>
          <h1>Chat</h1>
          <p className="muted">
            Ask in plain language. The agent calls tools through the gateway as <strong>{user.email}</strong>, so every
            call shows up in the audit log under your name.
          </p>
        </div>
        {messages.length > 0 && (
          <button type="button" className="btn" onClick={() => setMessages([])} disabled={busy}>
            Clear chat
          </button>
        )}
      </div>

      {statusError && <Notice kind="error">{statusError}</Notice>}
      {enabled === false && (
        <Notice kind="info">
          The chat agent is switched off because no LLM key is configured. An admin sets <code>llm.apiKey</code> in the
          Helm values.
        </Notice>
      )}

      <div className="card chat">
        <div className="messages" aria-live="polite">
          {messages.length === 0 && (
            <div className="chat-empty">
              <p className="muted">Try one of these:</p>
              <div className="chips">
                {SUGGESTIONS.map((s) => (
                  <button key={s} type="button" className="chip" disabled={!enabled || busy} onClick={() => send(s)}>
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}
          {messages.map((m, i) => (
            <Message key={i} m={m} />
          ))}
          {busy && <div className="bubble assistant pending">Working on it… the agent may call several tools.</div>}
          <div ref={end} />
        </div>
        <form
          className="composer"
          onSubmit={(e) => {
            e.preventDefault();
            send(text);
          }}
        >
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={onKeyDown}
            rows={2}
            maxLength={4000}
            placeholder={enabled === false ? "Chat is switched off" : "Ask about orders, products or the time…"}
            disabled={enabled === false}
            aria-label="Message"
          />
          <button type="submit" className="btn primary" disabled={busy || !text.trim() || enabled === false}>
            Send
          </button>
        </form>
      </div>
    </section>
  );
}

function Message({ m }) {
  if (m.role === "user") return <div className="bubble user">{m.content}</div>;
  const calls = m.tool_calls || [];
  return (
    <div className={`bubble assistant${m.error ? " error" : ""}`}>
      {calls.length > 0 && (
        <div className="called">
          <span className="muted">Tools called:</span>
          {calls.map((c, i) => (
            <span key={i} className={`chip static ${c.ok ? "ok" : "bad"}`}>
              {c.name}
              {c.ok ? "" : " (failed)"}
            </span>
          ))}
        </div>
      )}
      {m.error ? (
        <p>{m.content}</p>
      ) : (
        <div className="md">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{ a: ({ node, ...props }) => <a {...props} target="_blank" rel="noopener noreferrer" /> }}
          >
            {m.content}
          </ReactMarkdown>
        </div>
      )}
      {calls.length > 0 && (
        <details className="trace">
          <summary>Show tool details</summary>
          {calls.map((c, i) => (
            <div key={i} className="trace-item">
              <div className="trace-head">
                <code>{c.name}</code>
                <Badge kind={c.ok ? "ok" : "bad"}>{c.ok ? "ok" : "failed"}</Badge>
              </div>
              <pre>{JSON.stringify(c.arguments, null, 2)}</pre>
              <pre className="result">{c.result}</pre>
            </div>
          ))}
        </details>
      )}
    </div>
  );
}