import { describe, expect, it } from "vitest";
import { buildSpec } from "./Chart";
import type { Answer } from "./types";

const answer = (over: Partial<Answer> = {}): Answer => ({
  question: "q", error: "", corrections: [], timings_ms: {}, clarification: null, frame: null, sql: "", rules: [], kpi: null, metric: null, exports: [],
  columns: [{ name: "category", kind: "categorical" }, { name: "profit_margin", kind: "numeric" }],
  rows: [["A", 0.12], ["B", 0.14]], row_count: 2, truncated: false,
  chart: { type: "bar", reason: "", fallback: false, spec: { mark: "bar", encoding: { x: { field: "category", type: "nominal" }, y: { field: "profit_margin", type: "quantitative" } } } },
  ...over,
});

describe("buildSpec", () => {
  it("embeds the rows as named records", () => {
    const s = buildSpec(answer(), "percent", null) as { data: { values: Record<string, unknown>[] } };
    expect(s.data.values).toEqual([{ category: "A", profit_margin: 0.12 }, { category: "B", profit_margin: 0.14 }]);
  });
  it("formats the value axis as a percent and titles it with the friendly name", () => {
    const s = buildSpec(answer(), "percent", null, (n) => (n === "profit_margin" ? "Profit margin" : n)) as { encoding: Record<string, { title: string; axis?: { format?: string } }> };
    expect(s.encoding.y.axis?.format).toBe(".1%");
    expect(s.encoding.y.title).toBe("Profit margin");
  });
  it("keeps category labels horizontal when there are few", () => {
    const s = buildSpec(answer(), "number", null) as { encoding: Record<string, { axis?: { labelAngle?: number } }> };
    expect(s.encoding.x.axis?.labelAngle).toBe(0);
  });
  it("adds a tooltip for every field and fits the container", () => {
    const s = buildSpec(answer(), "number", null) as { width: string; encoding: { tooltip: unknown[] } };
    expect(s.width).toBe("container");
    expect(s.encoding.tooltip).toHaveLength(2);
  });
  it("does not change the server's spec", () => {
    const a = answer();
    const before = JSON.stringify(a.chart);
    buildSpec(a, "number", null);
    expect(JSON.stringify(a.chart)).toBe(before);
  });
});
