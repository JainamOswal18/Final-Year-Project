import { useState } from "react";
import { api } from "../api";
import { ResultTable } from "../ResultTable";
import { Callout, Spinner, useAsync } from "../ui";
import { PageHead, useDataset } from "./DatasetLoader";

export default function DataPage() {
  const { detail } = useDataset();
  const tables = Object.keys(detail.registry.tables);
  const [table, setTable] = useState("flat");
  const rows = detail.stats.tables ?? {};
  const prev = useAsync(() => api.preview(detail.id, table, 50), [detail.id, table]);
  const dates = Object.entries(detail.stats.date_ranges ?? {});
  return (
    <div className="page">
      <PageHead title="Data" subtitle="What is in this dataset. The questions you ask run on the joined view of all tables." />
      {detail.stats.error && <Callout kind="bad">{detail.stats.error}</Callout>}
      <div className="grid-cards">
        {tables.map((t) => (
          <div className="card stat" key={t}><div className="v">{(rows[t] ?? 0).toLocaleString()}</div><div className="l">rows in <strong>{t}</strong>{t === detail.registry.main_table ? " (main table)" : ""}</div></div>
        ))}
        {dates.map(([c, [lo, hi]]) => <div className="card stat" key={c}><div className="v" style={{ fontSize: 18 }}>{lo} to {hi}</div><div className="l">range of <strong>{c.replace(/_/g, " ")}</strong></div></div>)}
      </div>
      <div className="stack-sm">
        <div className="row between wrap">
          <h2>Preview</h2>
          <div className="seg" role="group" aria-label="Table">
            {["flat", ...tables].map((t) => <button key={t} className={table === t ? "on" : ""} aria-pressed={table === t} onClick={() => setTable(t)}>{t === "flat" ? "Joined view" : t}</button>)}
          </div>
        </div>
        {prev.loading ? <Spinner /> : prev.error ? <Callout kind="bad">{prev.error}</Callout> : prev.data && <ResultTable answer={prev.data} />}
      </div>
    </div>
  );
}
