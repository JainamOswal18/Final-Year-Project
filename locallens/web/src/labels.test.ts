import { describe, expect, it } from "vitest";
import { makeLabeler } from "./labels";
import type { Registry } from "./types";

const reg = {
  columns: [
    { table: "orders", name: "cust_seg", flat_name: "cust_seg", synonyms: ["segment"] },
    { table: "orders", name: "sales_amt", flat_name: "sales_amt", synonyms: ["sales", "revenue"] },
    { table: "orders", name: "order_date", flat_name: "order_date", synonyms: [] },
  ],
  measures: [{ name: "profit_margin", label: "profit margin" }],
} as unknown as Registry;

describe("makeLabeler", () => {
  const label = makeLabeler(reg);
  it("prefers the first synonym", () => expect(label("cust_seg")).toBe("Segment"));
  it("falls back to the column name", () => expect(label("order_date")).toBe("Order date"));
  it("names measures by their label", () => expect(label("profit_margin")).toBe("Profit margin"));
  it("explains aggregate aliases", () => { expect(label("sum_sales_amt")).toBe("Total sales"); expect(label("avg_sales_amt")).toBe("Average sales"); });
  it("knows the generated columns", () => { expect(label("period")).toBe("Period"); expect(label("count")).toBe("Orders"); });
  it("leaves unknown names readable", () => expect(label("something_new")).toBe("Something new"));
});
