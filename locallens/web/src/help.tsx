import { useState, type ReactNode } from "react";
import { Icon } from "./ui";

function stored(key: string): "open" | "closed" | null {
  try { const v = localStorage.getItem(key); return v === "open" || v === "closed" ? v : null; } catch { return null; }
}

/**
 * A guide that sits above the thing it explains. It starts open (or closed, with defaultOpen=false) and then remembers
 * what the person chose in this browser, so it is there for first-timers and out of the way afterwards.
 */
export function HowTo({ id, title, defaultOpen = true, children }: { id: string; title: string; defaultOpen?: boolean; children: ReactNode }) {
  const key = `ll-help-${id}`;
  const [open, setOpen] = useState(() => (stored(key) ?? (defaultOpen ? "open" : "closed")) === "open");
  return (
    <details className="howto" open={open} onToggle={(e) => {
      const now = e.currentTarget.open;
      setOpen(now);
      try { localStorage.setItem(key, now ? "open" : "closed"); } catch { /* private mode */ }
    }}>
      <summary><span className="howto-icon">{Icon.info}</span>{title}</summary>
      <div className="howto-body">{children}</div>
    </details>
  );
}

/** A worked example: what to type and what it gives. */
export function Ex({ label = "Example", children }: { label?: string; children: ReactNode }) {
  return <div className="ex"><span className="ex-label">{label}</span><div>{children}</div></div>;
}

/** A small table that pairs "what you want" with "what to type". */
export function Recipes({ head, rows }: { head: [string, string]; rows: [ReactNode, ReactNode][] }) {
  return (
    <div className="guide-scroll"><table className="t guide">
      <thead><tr><th>{head[0]}</th><th>{head[1]}</th></tr></thead>
      <tbody>{rows.map(([a, b], i) => <tr key={i}><td>{a}</td><td>{b}</td></tr>)}</tbody>
    </table></div>
  );
}
