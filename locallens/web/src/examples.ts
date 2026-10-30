/** Starter definitions built from the dataset's own columns, so the "Start from an example" buttons always produce something that works. */
import { prettify } from "./format";
import type { Column, Measure, Rule } from "./types";

const usable = (cols: Column[]) => cols.filter((c) => c.flat_name && c.tag !== "ignore" && !c.error && c.table !== "_calc");
const metrics = (cols: Column[]) => usable(cols).filter((c) => c.tag === "metric");

/** A round number near the middle of the column's sample values, used as a cut-off ("large" orders). */
export function midpoint(c: Column | undefined): number {
  const nums = (c?.samples ?? []).map((s) => Number(String(s).replace(/,/g, ""))).filter((n) => Number.isFinite(n) && n > 0).sort((a, b) => a - b);
  if (!nums.length) return 100;
  const mid = nums[Math.floor(nums.length / 2)];
  const mag = 10 ** Math.max(0, Math.floor(Math.log10(mid)) - 1);
  return Math.max(1, Math.round(mid / mag) * mag);
}

function unusedName(base: string, taken: string[]): string {
  let n = base, i = 2;
  while (taken.includes(n)) n = `${base}_${i++}`;
  return n;
}

export function metricExample(cols: Column[], existing: Measure[]): Measure {
  const m = metrics(cols);
  const top = m.find((c) => /sales|revenue|amount|turnover|value/i.test(c.flat_name));
  const part = m.find((c) => c !== top && /profit|margin|cost|discount/i.test(c.flat_name));
  const base = { description: "", synonyms: [] as string[], additive: false, error: "" };
  const taken = existing.map((x) => x.name);
  // a share of one number in another (profit margin) is the most useful first custom metric; otherwise a plain average
  if (top && part) return { ...base, name: unusedName(`${part.flat_name}_margin`, taken), label: `${prettify(part.flat_name).toLowerCase()} margin`,
    expression: `SUM(${part.flat_name}) / NULLIF(SUM(${top.flat_name}), 0)`, format: "percent" };
  const a = m[0];
  if (a) return { ...base, name: unusedName(`average_${a.flat_name}`, taken), label: `average ${prettify(a.flat_name).toLowerCase()}`, expression: `AVG(${a.flat_name})`, format: "number" };
  return { ...base, name: unusedName("metric", taken), label: "", expression: "", format: "number" };
}

export function columnExample(cols: Column[], existing: Column[]): Column {
  const a = metrics(cols)[0];
  const taken = existing.map((x) => x.name);
  const cut = midpoint(a);
  return { table: "_calc", name: unusedName(a ? `${a.flat_name}_band` : "column", taken), flat_name: "", tag: "dimension",
    description: a ? `Large when ${a.flat_name} is ${cut} or more, otherwise Small` : "", synonyms: [], samples: [], values: [],
    expression: a ? `CASE WHEN ${a.flat_name} >= ${cut} THEN 'Large' ELSE 'Small' END` : "", error: "" };
}

export function ruleExample(cols: Column[], existing: Rule[]): Rule {
  const a = metrics(cols)[0];
  const cut = midpoint(a);
  return { name: unusedName("high_value", existing.map((x) => x.name)), condition: a ? `${a.flat_name} >= ${cut}` : "", phrases: ["high value"],
    description: a ? `Rows where ${a.flat_name} is ${cut} or more` : "", enabled: true, error: "" };
}
