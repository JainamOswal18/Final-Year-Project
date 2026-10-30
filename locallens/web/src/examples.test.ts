import { describe, expect, it } from "vitest";
import { columnExample, metricExample, midpoint, ruleExample } from "./examples";
import type { Column } from "./types";

const col = (name: string, tag: Column["tag"], samples: string[] = []): Column =>
  ({ table: "orders", name, flat_name: name, tag, description: "", expression: "", error: "", synonyms: [], samples, values: [] });

const retail = [col("sales_amt", "metric", ["120", "480", "950", "2,400", "5,000"]), col("profit", "metric"), col("region", "dimension"), col("order_id", "ignore")];

describe("starter examples", () => {
  it("builds a margin from the columns that look like one number over another", () => {
    const m = metricExample(retail, []);
    expect(m.expression).toBe("SUM(profit) / NULLIF(SUM(sales_amt), 0)");
    expect(m.format).toBe("percent");
    expect(m.name).toBe("profit_margin");
  });
  it("falls back to an average of the first metric, and an empty formula when there is none", () => {
    expect(metricExample([col("weight", "metric")], []).expression).toBe("AVG(weight)");
    expect(metricExample([col("region", "dimension")], []).expression).toBe("");
  });
  it("never reuses a name", () => {
    const first = metricExample(retail, []);
    expect(metricExample(retail, [first]).name).toBe("profit_margin_2");
  });
  it("makes a Large/Small column around the middle of the sample values", () => {
    const c = columnExample(retail, []);
    expect(c.expression).toBe("CASE WHEN sales_amt >= 950 THEN 'Large' ELSE 'Small' END");
    expect(c.table).toBe("_calc");
    expect(c.tag).toBe("dimension");
  });
  it("makes a rule that uses the same cut-off", () => {
    const r = ruleExample(retail, []);
    expect(r.condition).toBe("sales_amt >= 950");
    expect(r.phrases).toEqual(["high value"]);
  });
  it("rounds the cut-off to a tidy number and has a default", () => {
    expect(midpoint(col("x", "metric", ["1234", "1301", "1500"]))).toBe(1300);
    expect(midpoint(col("x", "metric", ["abc"]))).toBe(100);
    expect(midpoint(undefined)).toBe(100);
  });
  it("ignores skipped and calculated columns", () => {
    const calc = { ...col("band", "metric"), table: "_calc" };
    expect(metricExample([col("id", "ignore"), calc], []).expression).toBe("");
  });
});
