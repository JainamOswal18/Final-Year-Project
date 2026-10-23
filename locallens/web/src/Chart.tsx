import embed from "vega-embed";
import { expressionInterpreter } from "vega-interpreter";
import { useEffect, useRef, useState } from "react";
import { grainTitle, type Fmt } from "./format";
import { useLabel } from "./labels";
import type { Answer } from "./types";

const PALETTE = ["#4263eb", "#f08c00", "#12b886", "#e64980", "#7048e8", "#15aabf", "#82c91e", "#868e96"];

function css(name: string, fallback: string): string {
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
}

export function vegaConfig() {
  const text = css("--muted", "#566077"), grid = css("--border", "#e1e4ee"), strong = css("--border-strong", "#cdd2e1");
  const font = css("--font", "system-ui, sans-serif");
  return {
    background: "transparent", font, view: { stroke: null },
    axis: { labelColor: text, titleColor: text, gridColor: grid, domainColor: strong, tickColor: strong, labelFont: font, titleFont: font, labelFontSize: 12, titleFontSize: 12, titleFontWeight: 600, titlePadding: 10 },
    legend: { labelColor: text, titleColor: text, labelFont: font, titleFont: font, labelFontSize: 12, titleFontSize: 12, symbolType: "circle" },
    range: { category: PALETTE },
    bar: { cornerRadiusEnd: 3, color: PALETTE[0] }, line: { strokeWidth: 2.5, color: PALETTE[0] }, point: { size: 50, color: PALETTE[0], filled: true },
    arc: {}, mark: { tooltip: true },
  };
}

type Enc = Record<string, { field?: string; type?: string; title?: string; axis?: Record<string, unknown>; [k: string]: unknown }>;

/** Turn the server's bare spec into a drawable one: data, titles, number formats, tooltips. */
/** Vega label expression for financial-year axes: "FY25" for years, "Q1 FY25" for quarters.
 *  A fiscal year is named after the calendar year it ends in. Returns null for calendar years and other grains. */
export function fiscalLabelExpr(grain: string | null | undefined, startMonth: number | undefined): string | null {
  if (!startMonth || startMonth === 1 || (grain !== "year" && grain !== "quarter")) return null;
  const m0 = startMonth - 1;
  const fy = `slice(toString(utcyear(datum.value) + (utcmonth(datum.value) >= ${m0} ? 1 : 0)), 2)`;
  if (grain === "year") return `'FY' + ${fy}`;
  return `'Q' + (floor(((utcmonth(datum.value) - ${m0} + 12) % 12) / 3) + 1) + ' FY' + ${fy}`;
}

export function buildSpec(answer: Answer, fmt: Fmt, grain: string | null | undefined, label: (n: string) => string = (n) => n): Record<string, unknown> {
  const spec = JSON.parse(JSON.stringify(answer.chart?.spec ?? {})) as Record<string, unknown> & { encoding?: Enc };
  const names = answer.columns.map((c) => c.name);
  const values = answer.rows.map((r) => Object.fromEntries(names.map((n, i) => [n, r[i]])));
  const numFmt = fmt === "percent" ? ".1%" : fmt === "currency" ? ",.2f" : ",.2~f";
  const kind = Object.fromEntries(answer.columns.map((c) => [c.name, c.kind]));
  const enc = (spec.encoding ?? {}) as Enc;
  const tooltip: Record<string, unknown>[] = [];
  for (const [channel, e] of Object.entries(enc)) {
    if (!e.field) continue;
    if (e.title === undefined) e.title = kind[e.field] === "temporal" && e.field === "period" ? grainTitle(grain) : label(e.field);
    if (kind[e.field] === "numeric" && ["x", "y", "theta"].includes(channel)) {
      if (channel !== "theta") e.axis = { ...(e.axis ?? {}), format: numFmt, formatType: "number" };
    }
    if (e.type === "nominal" && ["x", "y"].includes(channel)) {
      const n = new Set(values.map((v) => v[e.field!])).size;
      e.axis = { ...(e.axis ?? {}), ...(channel === "x" ? { labelAngle: n <= 5 ? 0 : -40, labelLimit: n <= 5 ? 140 : 100 } : { labelLimit: 220 }) };
    }
    if (kind[e.field] === "temporal") {
      const fy = fiscalLabelExpr(grain, answer.fiscal_start_month);
      e.axis = fy ? { ...(e.axis ?? {}), labelExpr: fy } : { ...(e.axis ?? {}), format: grain === "year" ? "%Y" : grain === "quarter" || grain === "month" ? "%b %Y" : "%d %b %Y" };
    }
    if (channel === "color" && e.field && !("legend" in e)) e.legend = { title: e.title };
    const t: Record<string, unknown> = { field: e.field, type: e.type, title: e.title };
    if (kind[e.field] === "numeric") t.format = numFmt;
    if (kind[e.field] === "temporal") t.format = "%d %b %Y";
    tooltip.push(t);
  }
  if (tooltip.length && !("tooltip" in enc)) (enc as Record<string, unknown>).tooltip = tooltip;
  spec.encoding = enc;
  return { $schema: "https://vega.github.io/schema/vega-lite/v6.json", ...spec, data: { values }, width: "container", height: 300, autosize: { type: "fit", contains: "padding" } };
}

export function Chart({ answer, fmt, grain }: { answer: Answer; fmt: Fmt; grain?: string | null }) {
  const label = useLabel();
  const host = useRef<HTMLDivElement>(null);
  const [failed, setFailed] = useState("");
  const [theme, setTheme] = useState(0);
  useEffect(() => {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const bump = () => setTheme((t) => t + 1);
    mq.addEventListener("change", bump);
    const mo = new MutationObserver(bump);
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => { mq.removeEventListener("change", bump); mo.disconnect(); };
  }, []);
  useEffect(() => {
    if (!host.current) return;
    let view: { finalize: () => void } | undefined;
    let cancelled = false;
    embed(host.current, buildSpec(answer, fmt, grain, label) as never, {
      actions: false, renderer: "svg", config: vegaConfig() as never, ast: true, expr: expressionInterpreter as never,
      tooltip: { theme: "custom" } as never,
    }).then((r) => { if (cancelled) r.finalize(); else { view = r; setFailed(""); } })
      .catch((e: Error) => !cancelled && setFailed(e.message));
    return () => { cancelled = true; view?.finalize(); };
  }, [answer, fmt, grain, theme, label]);
  if (failed) return <div className="callout warn">The chart could not be drawn ({failed}). The table below has the data.</div>;
  return <div className="chart-box" ref={host} role="img" aria-label={`${answer.chart?.type ?? ""} chart of ${answer.question}`} />;
}
