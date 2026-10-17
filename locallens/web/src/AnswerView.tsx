import { useState } from "react";
import { api } from "./api";
import { Chart } from "./Chart";
import { describeFilter, formatNumber, prettify, type Fmt } from "./format";
import { useLabel } from "./labels";
import { ResultTable } from "./ResultTable";
import type { Answer, Message } from "./types";
import { Badge, Callout, Icon, useToast } from "./ui";

const INTENT: Record<string, string> = {
  trend: "Trend over time", comparison: "Comparison across groups", distribution: "Distribution of values",
  proportion: "Share of the whole", ranking: "Ranking", summary: "Single total",
};

export function titleOf(a: Answer, label: (n: string) => string = prettify): string {
  if (!a.frame || !a.metric) return a.question;
  const f = a.frame;
  const parts = [label(a.metric.name)];
  if (f.dimension) parts.push(`by ${label(f.dimension).toLowerCase()}`);
  if (f.intent === "trend") parts.push(`per ${f.time?.grain ?? "month"}`);
  if (f.intent === "ranking") parts.unshift(`${f.order === "asc" ? "Lowest" : "Top"} ${f.top_n ?? 10}:`);
  return parts.join(" ");
}

function periodOf(a: Answer): string {
  const t = a.frame?.time;
  if (t?.start && t?.end) return `${t.start} to ${t.end}`;
  return "All dates";
}

export function Explanation({ a }: { a: Answer }) {
  const label = useLabel();
  const f = a.frame!;
  return (
    <div className="explain">
      <dl>
        <dt>Question type</dt><dd>{INTENT[f.intent] ?? f.intent}{a.chart && <span className="muted"> · shown as {a.chart.type.replace("_", " ")}</span>}</dd>
        <dt>Measuring</dt><dd>{a.metric && label(a.metric.name)}{a.metric?.agg && <span className="muted"> ({a.metric.agg.toLowerCase()})</span>}{a.metric?.description && <span className="muted"> · {a.metric.description}</span>}</dd>
        {f.dimension && <><dt>Grouped by</dt><dd>{label(f.dimension).toLowerCase()}</dd></>}
        <dt>Period</dt><dd>{periodOf(a)}{f.time?.grain && <span className="muted"> · by {f.time.grain}</span>}</dd>
        {f.filters.length > 0 && <><dt>Filtered to</dt><dd>{f.filters.map((x) => describeFilter(x, label)).join(" and ")}</dd></>}
        {a.rules.length > 0 && <><dt>Business rules</dt><dd className="stack-sm">{a.rules.map((r) => <span key={r.name}><strong>{r.name.replace(/_/g, " ")}</strong>{r.description && <span className="muted"> · {r.description}</span>}{r.always && <span className="faint"> (always applied)</span>}</span>)}</dd></>}
        {(a.semantic?.length ?? 0) > 0 && <><dt>Understood as</dt><dd>{a.semantic!.map(([w, c]) => `“${w}” → ${label(c).toLowerCase()}`).join(", ")}<span className="muted"> · matched by meaning, not spelling</span></dd></>}
        {a.corrections.length > 0 && <><dt>Spelling fixed</dt><dd>{a.corrections.map(([x, y]) => `${x} → ${y}`).join(", ")}</dd></>}
      </dl>
      <details className="fold">
        <summary>Technical details</summary>
        <div className="stack-sm">
          <div className="tiny muted">Query frame the model produced (the model never writes SQL)</div>
          <pre className="code">{JSON.stringify(f, null, 2)}</pre>
          <div className="tiny muted">SQL built from a template and checked before it ran</div>
          <pre className="code">{a.sql}</pre>
          <div className="tiny faint">{Object.entries(a.timings_ms).map(([k, v]) => `${k} ${Math.round(v)} ms`).join(" · ")}</div>
        </div>
      </details>
    </div>
  );
}

export function AnswerView({ msg, canEdit, suggestions, onPick, onClarify, compact }: {
  msg: Message; canEdit: boolean; suggestions: string[]; onPick: (q: string) => void; onClarify: (q: string, field: string, option: string) => void; compact?: boolean;
}) {
  const a = msg.response;
  const label = useLabel();
  const toast = useToast();
  const [view, setView] = useState<"chart" | "table">("chart");
  const [rating, setRating] = useState<number | null>(msg.rating);
  const [saved, setSaved] = useState(false);
  const fmt: Fmt = a.metric?.format ?? "number";

  if (a.clarification) {
    const c = a.clarification;
    return (
      <div className="card answer"><div className="answer-body">
        <strong>{c.message}</strong>
        <div className="row wrap">{c.options.map((o) => <button key={o} className="chip" onClick={() => onClarify(c.question, c.field, o)}>{label(o)}</button>)}</div>
      </div></div>
    );
  }
  if (a.error || !a.chart) {
    return (
      <div className="card answer"><div className="answer-body">
        <Callout kind="warn"><span>{a.error || "I could not answer that."}</span></Callout>
        {suggestions.length > 0 && <div className="stack-sm"><span className="small muted">Try one of these:</span><div className="row wrap">{suggestions.slice(0, 4).map((s) => <button key={s} className="chip" onClick={() => onPick(s)}>{s}</button>)}</div></div>}
      </div></div>
    );
  }
  const isKpi = a.chart.type === "kpi";
  const showChart = !isKpi && (view === "chart" || a.chart.fallback);
  const rate = async (r: number) => {
    const next = rating === r ? 0 : r;
    try { await api.rate(msg.id, next); setRating(next || null); toast(next < 0 ? "Thanks. An administrator will see this answer." : "Thanks for the feedback."); }
    catch (e) { toast((e as Error).message, true); }
  };
  const save = async () => {
    try { const r = await api.saveExample(msg.id); setSaved(true); toast(r.already ? "Already saved as an example." : "Saved. The assistant will use it as an example for this dataset."); }
    catch (e) { toast((e as Error).message, true); }
  };
  return (
    <div className="card answer">
      <div className="answer-body">
        <div className="answer-title">
          <h3>{titleOf(a, label)}</h3>
          <span className="tiny muted">{periodOf(a)}{a.frame?.filters.length ? ` · ${a.frame.filters.map((x) => describeFilter(x, label)).join(", ")}` : ""}</span>
        </div>
        {isKpi && a.kpi && <div className="kpi"><div className="kpi-value">{a.kpi.value === null ? "–" : formatNumber(a.kpi.value, fmt, true)}</div><div className="kpi-label">{a.metric && label(a.metric.name)}</div></div>}
        {showChart && <Chart answer={a} fmt={fmt} grain={a.frame?.time?.grain} />}
        {a.chart.fallback && <Callout><span>I wasn't sure which chart fits this result, so here is the data with a best guess.</span></Callout>}
        {!isKpi && (view === "table" || a.chart.fallback) && <ResultTable answer={a} fmt={fmt} />}
        {a.rules.filter((r) => !r.always).length > 0 && <div className="row wrap">{a.rules.filter((r) => !r.always).map((r) => <Badge key={r.name} kind="accent" title={r.description}>{r.name.replace(/_/g, " ")}</Badge>)}</div>}
      </div>
      <div className="answer-bar">
        {!isKpi && !a.chart.fallback && (
          <div className="seg" role="group" aria-label="View">
            <button className={view === "chart" ? "on" : ""} aria-pressed={view === "chart"} onClick={() => setView("chart")}>Chart</button>
            <button className={view === "table" ? "on" : ""} aria-pressed={view === "table"} onClick={() => setView("table")}>Table</button>
          </div>
        )}
        {a.exports.includes("powerbi") && <a className="btn sm" href={api.exportUrl(msg.id, "powerbi")} title="Downloads a Power BI project. Unzip it and open the .pbip file in Power BI Desktop (Windows).">Open in Power BI</a>}
        {a.exports.includes("csv") && <a className="btn sm" href={api.exportUrl(msg.id, "csv")}>Download CSV</a>}
        <span className="sep" />
        {canEdit && <button className="btn sm ghost" onClick={() => void save()} disabled={saved} title="Use this question and answer as an example for the assistant">{Icon.check} {saved ? "Saved" : "Mark as correct"}</button>}
        <span className="grow" />
        <button className={`btn sm icon ${rating === 1 ? "" : "ghost"}`} aria-pressed={rating === 1} aria-label="Good answer" onClick={() => void rate(1)}>{Icon.up}</button>
        <button className={`btn sm icon ${rating === -1 ? "danger" : "ghost"}`} aria-pressed={rating === -1} aria-label="Wrong answer" onClick={() => void rate(-1)}>{Icon.down}</button>
      </div>
      {!compact && (
        <div style={{ padding: "12px 20px 14px", borderTop: "1px solid var(--border)" }}>
          <details className="fold"><summary>How I read this</summary><Explanation a={a} /></details>
        </div>
      )}
    </div>
  );
}
