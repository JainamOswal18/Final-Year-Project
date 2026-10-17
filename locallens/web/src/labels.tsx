import { createContext, useContext, useMemo, type ReactNode } from "react";
import { prettify } from "./format";
import type { Registry } from "./types";

type Labeler = (name: string) => string;
const AGG: Record<string, string> = { sum: "Total", avg: "Average", min: "Lowest", max: "Highest", count: "Count of" };

/** Friendly names for columns and measures: the first synonym, else the cleaned-up column name. */
export function makeLabeler(reg: Registry): Labeler {
  const base = new Map<string, string>();
  for (const c of reg.columns) if (c.flat_name) base.set(c.flat_name, c.synonyms[0] ?? c.name.replace(/_/g, " "));
  for (const m of reg.measures) base.set(m.name, m.label || m.name.replace(/_/g, " "));
  const plain = (n: string) => base.get(n) ?? n.replace(/_/g, " ");
  return (name: string) => {
    if (name === "period") return "Period";
    if (name === "count") return "Orders";
    const hit = /^(sum|avg|min|max|count)_(.+)$/.exec(name);
    if (hit && base.has(hit[2])) return prettify(`${AGG[hit[1]].toLowerCase() === "total" ? "total" : AGG[hit[1]].toLowerCase()} ${plain(hit[2])}`);
    return prettify(plain(name));
  };
}

const Ctx = createContext<Labeler>((n) => prettify(n));
export const useLabel = () => useContext(Ctx);
export function LabelProvider({ registry, children }: { registry: Registry; children: ReactNode }) {
  const f = useMemo(() => makeLabeler(registry), [registry]);
  return <Ctx.Provider value={f}>{children}</Ctx.Provider>;
}
