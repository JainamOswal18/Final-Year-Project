import { formatCell, type Fmt } from "./format";
import { useLabel } from "./labels";
import type { Answer } from "./types";

export function ResultTable({ answer, fmt, max = 200 }: { answer: Pick<Answer, "columns" | "rows" | "row_count" | "truncated">; fmt?: Fmt; max?: number }) {
  const label = useLabel();
  const shown = answer.rows.slice(0, max);
  return (
    <div className="stack-sm">
      <div className="table-wrap">
        <table className="t">
          <thead><tr>{answer.columns.map((c) => <th key={c.name} className={c.kind === "numeric" ? "num" : ""}>{label(c.name)}</th>)}</tr></thead>
          <tbody>
            {shown.map((r, i) => (
              <tr key={i}>{r.map((v, j) => {
                const col = answer.columns[j];
                return <td key={j} className={col.kind === "numeric" ? "num" : ""} title={typeof v === "string" ? v : undefined}>
                  {formatCell(v, col.kind === "numeric" && j === answer.columns.length - 1 ? fmt : "number")}</td>;
              })}</tr>
            ))}
          </tbody>
        </table>
      </div>
      {(answer.truncated || answer.row_count > shown.length) && <div className="tiny faint">Showing {shown.length.toLocaleString()} of {answer.row_count.toLocaleString()} rows. Export to get all of them.</div>}
    </div>
  );
}
