import { describe, expect, it } from "vitest";
import { describeFilter, formatCell, formatNumber, grainTitle, prettify } from "./format";

describe("formatNumber", () => {
  it("groups thousands and keeps integers whole", () => {
    expect(formatNumber(1234567)).toBe("1,234,567");
    expect(formatNumber(1234.5678)).toBe("1,234.57");
  });
  it("formats percent from a fraction", () => expect(formatNumber(0.13048, "percent")).toBe("13.0%"));
  it("formats currency with two decimals", () => expect(formatNumber(1500, "currency")).toBe("1,500.00"));
  it("shortens big KPI numbers", () => expect(formatNumber(2_500_000, "number", true)).toBe("2.5M"));
  it("never prints NaN", () => expect(formatNumber(NaN)).toBe("–"));
});

describe("formatCell", () => {
  it("handles null, booleans and text", () => {
    expect(formatCell(null)).toBe("–");
    expect(formatCell(true)).toBe("Yes");
    expect(formatCell("Furniture")).toBe("Furniture");
  });
});

describe("labels", () => {
  it("prettifies column names", () => expect(prettify("sum_sales_amt")).toBe("Sum sales amt"));
  it("names the time grain", () => { expect(grainTitle("quarter")).toBe("Quarter"); expect(grainTitle(null)).toBe("Period"); });
  it("describes a filter in words", () => expect(describeFilter({ column: "cust_seg", op: "=", value: "Corporate" })).toBe("cust seg is Corporate"));
});
