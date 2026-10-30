import { useState } from "react";
import { prettify } from "../format";
import type { Join, Tag } from "../types";
import { Badge, Callout, ChipsInput, Seg } from "../ui";
import { Ex, HowTo } from "../help";
import { SaveBar, useRegistryEditor } from "../useRegistryEditor";
import { PageHead } from "./DatasetLoader";

const TAGS: { value: Tag; label: string; title: string }[] = [
  { value: "metric", label: "Metric", title: "A number to add up or average, such as sales, quantity or profit" },
  { value: "dimension", label: "Category", title: "A label to group or filter by, such as region, product or customer type" },
  { value: "date", label: "Date", title: "When something happened. Needed for trends and “last month”" },
  { value: "ignore", label: "Skip", title: "Not useful for questions, such as ids or free-text notes" },
];

export default function ColumnsPage() {
  const { draft, update, dirty, saving, save, discard, detail } = useRegistryEditor();
  const tables = Object.keys(draft.tables);
  const [table, setTable] = useState(draft.main_table);
  const reachable = new Set([draft.main_table, ...draft.joins.map((j) => j.right)]);
  const cols = draft.columns.map((c, i) => ({ c, i })).filter(({ c }) => c.table === table && c.table !== "_calc");
  const count = (t: Tag) => draft.columns.filter((c) => c.tag === t && c.flat_name !== "").length;
  const colsOf = (t: string) => draft.columns.filter((c) => c.table === t).map((c) => c.name);
  const setJoin = (i: number, patch: Partial<Join>) => update((d) => { Object.assign(d.joins[i], patch); });

  return (
    <div className="page">
      <PageHead title="Columns" subtitle="Tell the assistant how each column is used. A metric is a number to add up, a category is something to group by, a date is for trends." />
      <HowTo id="columns" title="How to fill in this page">
        <p>Every column needs one answer: <strong>what is it used for?</strong> Click one of the four buttons on its row. Nothing is saved until you press Save.</p>
        <div className="guide-scroll"><table className="t guide">
          <thead><tr><th>Choose</th><th>When the column is…</th><th>Typical columns</th><th>It lets people ask</th></tr></thead>
          <tbody>
            <tr><td><Badge kind="accent">Metric</Badge></td><td>a number you add up or average</td><td><code>sales_amt</code>, <code>quantity</code>, <code>profit</code></td><td>“total sales”, “average profit”</td></tr>
            <tr><td><Badge kind="warn">Category</Badge></td><td>a label that splits the numbers into groups</td><td><code>region</code>, <code>product</code>, <code>customer_type</code></td><td>“sales by region”, “only Technology”</td></tr>
            <tr><td><Badge kind="good">Date</Badge></td><td>when something happened</td><td><code>order_date</code></td><td>“monthly trend”, “last quarter”</td></tr>
            <tr><td><Badge>Skip</Badge></td><td>never something you would ask about</td><td><code>customer_id</code>, <code>notes</code></td><td>nothing: it is left out</td></tr>
          </tbody>
        </table></div>
        <Ex label="Worked example">
          <p>For a column called <code>sales_amt</code> you would choose <strong>Metric</strong>, type <em>revenue</em>, <em>turnover</em> and <em>sales</em> under “Other names people use”
            (press Enter or comma after each), and write <em>Order value in rupees, after discount</em> as the description.</p>
          <p>People can then ask “total <strong>revenue</strong> by region” or “<strong>turnover</strong> last quarter” and it finds <code>sales_amt</code>.</p>
        </Ex>
        <ul className="guide-list">
          <li><strong>Not sure?</strong> The grey text under a column name shows a few values from your file. A number you would add up is a Metric. Ids (<code>customer_id</code>) look like numbers but you never add them up, so choose Skip.</li>
          <li><strong>Other names</strong> are the words your team really says. Give each column its own words: if two columns share a word, the assistant has to ask which one is meant.</li>
          <li><strong>Description</strong> is one short sentence with the unit. It is shown to the assistant and in explanations.</li>
          <li><strong>Several files?</strong> Each file is a table. Connect them in “How the tables connect” below, then choose the columns of every table.</li>
        </ul>
      </HowTo>
      <div className="row wrap"><Badge kind="accent">{count("metric")} metrics</Badge><Badge kind="warn">{count("dimension")} categories</Badge><Badge kind="good">{count("date")} dates</Badge></div>

      {tables.length > 1 && (
        <section className="card pad stack" aria-labelledby="joins-h">
          <div><h2 id="joins-h">How the tables connect</h2><p className="muted small">Everything is read as one wide table: the main table plus the tables joined to it.</p>
            <p className="muted small">Pick the column that holds the <em>same value</em> in both tables. Example: <code>orders.customer_id = customers.id</code> gives every order its customer’s name and region.</p></div>
          <label className="field" style={{ maxWidth: 280 }}>Main table
            <select className="select" value={draft.main_table} onChange={(e) => update((d) => { d.main_table = e.target.value; d.joins = d.joins.filter((j) => j.right !== e.target.value); })}>
              {tables.map((t) => <option key={t}>{t}</option>)}
            </select></label>
          {draft.joins.length === 0 && <Callout kind="warn"><span>No joins yet. Columns from other tables are unavailable until you connect them.</span></Callout>}
          {draft.joins.map((j, i) => (
            <div className="row wrap" key={i}>
              <strong className="small">{j.left}</strong>
              <select className="select sm" style={{ width: 160 }} aria-label="Key in the main table" value={j.left_key} onChange={(e) => setJoin(i, { left_key: e.target.value })}>{colsOf(j.left).map((c) => <option key={c}>{c}</option>)}</select>
              <span className="muted">=</span>
              <select className="select sm" style={{ width: 150 }} aria-label="Joined table" value={j.right} onChange={(e) => setJoin(i, { right: e.target.value, right_key: colsOf(e.target.value)[0] })}>{tables.filter((t) => t !== draft.main_table).map((t) => <option key={t}>{t}</option>)}</select>
              <select className="select sm" style={{ width: 160 }} aria-label="Key in the joined table" value={j.right_key} onChange={(e) => setJoin(i, { right_key: e.target.value })}>{colsOf(j.right).map((c) => <option key={c}>{c}</option>)}</select>
              <button className="btn ghost sm" onClick={() => update((d) => { d.joins.splice(i, 1); })}>Remove</button>
            </div>
          ))}
          <div><button className="btn sm" onClick={() => update((d) => {
            const other = tables.find((t) => t !== d.main_table && !d.joins.some((j) => j.right === t)) ?? tables.find((t) => t !== d.main_table)!;
            d.joins.push({ left: d.main_table, left_key: colsOf(d.main_table)[0], right: other, right_key: colsOf(other)[0] });
          })}>Add a join</button></div>
        </section>
      )}

      <div className="stack-sm">
        {tables.length > 1 && <div className="seg" role="group" aria-label="Table">{tables.map((t) => <button key={t} className={table === t ? "on" : ""} aria-pressed={table === t} onClick={() => setTable(t)}>{t}{!reachable.has(t) ? " ⚠" : ""}</button>)}</div>}
        {!reachable.has(table) && <Callout kind="warn"><span>The table <strong>{table}</strong> is not joined to the main table, so its columns cannot be used yet.</span></Callout>}
        <div className="card" style={{ overflow: "auto" }}>
          <table className="t edit">
            <thead><tr><th title="The column name in your file. Grey text shows sample values">Column</th><th title="Metric: a number to add up. Category: a label to group by. Date: when it happened. Skip: leave it out">Used as</th><th title="Words people say for this column, e.g. revenue and turnover for sales_amt. Press Enter or comma after each">Other names people use</th><th title="One short sentence with the unit, e.g. Order value in rupees after discount">Description</th></tr></thead>
            <tbody>
              {cols.map(({ c, i }) => (
                <tr key={`${c.table}.${c.name}`}>
                  <td style={{ minWidth: 150 }}><strong>{c.name}</strong>
                    {c.samples.length > 0 && <div className="tiny faint" style={{ maxWidth: 200, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{c.samples.slice(0, 4).join(", ")}</div>}</td>
                  <td><Seg label={`How ${c.name} is used`} value={c.tag} options={TAGS} cls={(v) => v} onChange={(v) => update((d) => { d.columns[i].tag = v; })} /></td>
                  <td style={{ minWidth: 200 }}>{c.tag !== "ignore" && <ChipsInput label={`Synonyms of ${c.name}`} values={c.synonyms} placeholder={`e.g. ${prettify(c.name).toLowerCase()}, then Enter`} onChange={(v) => update((d) => { d.columns[i].synonyms = v; })} />}</td>
                  <td style={{ minWidth: 200 }}>{c.tag !== "ignore" && <input className="input sm" aria-label={`Description of ${c.name}`} value={c.description} maxLength={200} placeholder="e.g. Order value in rupees" onChange={(e) => update((d) => { d.columns[i].description = e.target.value; })} />}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <SaveBar dirty={dirty} saving={saving} onSave={() => void save()} onDiscard={discard} />
      <span className="sr">{detail.name}</span>
    </div>
  );
}
