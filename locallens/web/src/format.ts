import type { Cell } from "./types";

export type Fmt = "number" | "currency" | "percent";

const group = new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 });
const group0 = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
const money = new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const compact = new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 2 });

export function formatNumber(v: number, fmt: Fmt = "number", short = false): string {
  if (!Number.isFinite(v)) return "–";
  if (fmt === "percent") return `${(v * 100).toLocaleString("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 })}%`;
  if (short && Math.abs(v) >= 1_000_000) return compact.format(v);
  if (fmt === "currency") return money.format(v);
  return Number.isInteger(v) ? group0.format(v) : group.format(v);
}

export function formatCell(v: Cell, fmt: Fmt = "number"): string {
  if (v === null || v === undefined) return "–";
  if (typeof v === "number") return formatNumber(v, fmt);
  if (typeof v === "boolean") return v ? "Yes" : "No";
  return v;
}

/** sum_sales_amt -> "Sum sales amt"; period -> "Period" */
export function prettify(name: string): string {
  const s = name.replace(/_/g, " ").trim();
  return s.charAt(0).toUpperCase() + s.slice(1);
}

const GRAIN_TITLE: Record<string, string> = { day: "Day", week: "Week", month: "Month", quarter: "Quarter", year: "Year" };
export const grainTitle = (g: string | null | undefined) => (g ? GRAIN_TITLE[g] ?? "Period" : "Period");

export function timeAgo(iso: string): string {
  const t = new Date(iso.replace(" ", "T") + "Z").getTime();
  const s = Math.max(0, (Date.now() - t) / 1000);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  return `${Math.floor(s / 86400)} d ago`;
}

export function describeFilter(f: { column: string; op: string; value: string }, label: (n: string) => string = prettify): string {
  const op = f.op === "=" ? "is" : f.op === "!=" ? "is not" : f.op === "in" ? "is one of" : f.op;
  return `${label(f.column).toLowerCase()} ${op} ${f.value}`;
}
