import { describe, expect, it } from "vitest";
import { fiscalLabelExpr } from "./Chart";

// the same expression Vega runs in the browser, evaluated for a UTC date
const run = (expr: string, iso: string) =>
  new Function("datum", "utcyear", "utcmonth", "floor", "slice", "toString", `return ${expr};`)(
    { value: Date.parse(iso) }, (t: number) => new Date(t).getUTCFullYear(), (t: number) => new Date(t).getUTCMonth(),
    Math.floor, (s: string, a: number) => s.slice(a), String);

describe("financial-year axis labels", () => {
  it("names years after the calendar year they end in", () => {
    const e = fiscalLabelExpr("year", 4)!;
    expect(run(e, "2024-04-01")).toBe("FY25");
    expect(run(e, "2025-04-01")).toBe("FY26");
  });
  it("numbers quarters from the start month", () => {
    const e = fiscalLabelExpr("quarter", 4)!;
    expect([ "2024-04-01", "2024-07-01", "2024-10-01", "2025-01-01", "2025-04-01"].map((d) => run(e, d)))
      .toEqual(["Q1 FY25", "Q2 FY25", "Q3 FY25", "Q4 FY25", "Q1 FY26"]);
  });
  it("leaves calendar years and other grains alone", () => {
    expect(fiscalLabelExpr("year", 1)).toBeNull();
    expect(fiscalLabelExpr("month", 4)).toBeNull();
  });
});
