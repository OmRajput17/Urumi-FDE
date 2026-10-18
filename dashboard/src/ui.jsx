import { useState } from "react";

export function Badge({ kind = "off", children }) {
  return <span className={`badge ${kind}`}>{children}</span>;
}

export function Notice({ kind = "info", children, onClose }) {
  return (
    <div className={`notice ${kind}`} role={kind === "error" ? "alert" : "status"}>
      <div>{children}</div>
      {onClose && (
        <button type="button" className="btn ghost small" onClick={onClose} aria-label="Dismiss">
          Dismiss
        </button>
      )}
    </div>
  );
}

export function Empty({ children }) {
  return <div className="empty">{children}</div>;
}

export function CopyButton({ text, label = "Copy" }) {
  const [state, setState] = useState("idle");
  async function copy() {
    let ok = false;
    try {
      await navigator.clipboard.writeText(text);
      ok = true;
    } catch {
      try {
        const area = document.createElement("textarea");
        area.value = text;
        area.style.position = "fixed";
        area.style.opacity = "0";
        document.body.appendChild(area);
        area.select();
        ok = document.execCommand("copy");
        document.body.removeChild(area);
      } catch {
        ok = false;
      }
    }
    setState(ok ? "done" : "failed");
    setTimeout(() => setState("idle"), 1800);
  }
  return (
    <button type="button" className="btn small" onClick={copy}>
      {state === "done" ? "Copied" : state === "failed" ? "Copy failed" : label}
    </button>
  );
}

export function timeAgo(ts) {
  if (!ts) return "never";
  const s = Math.max(0, Date.now() / 1000 - ts);
  if (s < 5) return "just now";
  if (s < 60) return `${Math.floor(s)}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  return `${Math.floor(s / 86400)} d ago`;
}

export function formatTime(ts) {
  return new Date(ts * 1000).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "medium" });
}