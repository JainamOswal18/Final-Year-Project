import type { ReactNode } from "react";
import { Badge } from "../ui";
import type { Place } from "./place";

export interface TourStep {
  id: string;
  title: string;
  body: ReactNode;
  /** value of a data-tour attribute to light up; without it (or when it is not on screen) the card is shown in the middle */
  target?: string;
  /** page to open first when the target is not on the current page */
  route?: string;
  place?: Place;
  cta?: { label: string; run: () => Promise<void> };
}

const Q = ({ children }: { children: ReactNode }) => <span className="chip static">{children}</span>;

function Flow() {
  const items = [
    ["Add your data", "Upload a spreadsheet or database file, or open the retail demo."],
    ["Check the columns", "Say which columns are numbers to add up, labels to group by, and dates."],
    ["Teach your terms (optional)", "Define your own metrics, bands and filters, such as profit margin."],
    ["Ask", "Type a question in plain language and get a chart with an explanation."],
  ];
  return <ol className="tour-flow">{items.map(([t, d], i) => <li key={t}><span className="n">{i + 1}</span><span><strong>{t}</strong><br /><span className="muted">{d}</span></span></li>)}</ol>;
}

function MockColumns() {
  const rows: [string, string, "accent" | "warn" | "good" | undefined, string][] = [
    ["sales_amt", "Metric", "accent", "“total sales”"],
    ["region", "Category", "warn", "“sales by region”"],
    ["order_date", "Date", "good", "“monthly trend”"],
    ["customer_id", "Skip", undefined, "left out"],
  ];
  return (
    <div className="mock" aria-label="Example of tagging columns">
      {rows.map(([c, t, k, q]) => <div className="mock-row" key={c}><code>{c}</code><Badge kind={k}>{t}</Badge><span className="muted">{q}</span></div>)}
    </div>
  );
}

function MockDefs() {
  return (
    <div className="mock" aria-label="Examples of definitions">
      <div className="mock-row"><strong>Metric</strong><span className="muted">profit margin = profit ÷ sales</span></div>
      <div className="mock-row"><strong>Column</strong><span className="muted">order size = Large if sales ≥ 1,000</span></div>
      <div className="mock-row"><strong>Rule</strong><span className="muted">leave out cancelled orders</span></div>
    </div>
  );
}

export function buildSteps(o: { isAdmin: boolean; tryDemo: () => Promise<void> }): TourStep[] {
  const steps: TourStep[] = [
    { id: "welcome", title: "Welcome to LocalLens",
      body: <><p>Ask questions about your data in plain language and get a chart and a clear explanation back. No formulas or reports to build.</p>
        <p>Everything runs on this server. Your files and questions are not sent anywhere else.</p>
        <p className="muted">This tour takes about two minutes. You can leave it at any time and bring it back from the sidebar.</p></> },
    { id: "flow", title: "How it works, in four steps", body: <Flow /> },
    { id: "datasets", title: "Your datasets", target: "nav-datasets", place: "right",
      body: <p>A dataset is one set of data you can ask about, such as “Retail sales”. Everything starts here. Once you open a dataset, a menu appears to switch between them.</p> },
    { id: "upload", title: "Add your own data", target: "new-dataset", route: "/datasets", place: "bottom",
      body: <><p>Drop in CSV, Excel, Parquet or SQLite files. The first row should be the column names.</p>
        <p>Several files become several tables, for example <code>orders.csv</code> and <code>customers.csv</code>. You connect them on the Columns page.</p></> },
    { id: "demo", title: "No data to hand? Try the demo", target: "demo", route: "/datasets", place: "bottom",
      body: <p>This opens ready-made retail data with the columns already set up, so you can ask questions straight away and see how everything works.</p> },
    { id: "columns", title: "Columns: tell it what each column is", target: "nav-columns", place: "right",
      body: <><p>After an upload, you check one thing per column: what is it used for?</p><MockColumns />
        <p>You can also add <strong>other names</strong>, such as “revenue” for <code>sales_amt</code>. That page has a step-by-step guide with an example.</p></> },
    { id: "definitions", title: "Definitions: teach it your business", target: "nav-definitions", place: "right",
      body: <><p>Optional. Use this page when your team has its own terms. The assistant then uses them in every answer.</p><MockDefs />
        <p>Every section has a short guide with examples, and a button that adds a working example made from your own columns.</p></> },
    { id: "ask", title: "Ask: the heart of the app", target: "nav-ask", place: "right",
      body: <><p>Type a question the way you would say it. As you type, suggestions complete your words from your own columns; press <strong>Tab</strong> to accept.</p>
        <div className="chips"><Q>total sales by region</Q><Q>monthly profit trend for 2024</Q><Q>top 5 products by quantity</Q><Q>share of sales by category</Q></div>
        <p>Then follow up in the same chat: “now only East”. If a question could mean two things, it asks you instead of guessing.</p></> },
    { id: "answers", title: "Reading an answer",
      body: <ul className="guide-list"><li>You get a chart, a table, and a plain sentence on how the question was read. Open <strong>How I read this</strong> to see exactly what was used.</li>
        <li><strong>Thumbs up or down</strong> tells the owner whether it was right.</li>
        <li><strong>Mark as correct</strong> (if you can edit the dataset) saves the question as an example, so similar questions become more reliable.</li>
        <li><strong>Download CSV</strong> or <strong>Open in Power BI</strong> takes the result with you.</li></ul> },
    { id: "more", title: "Data, Examples and Settings",
      body: <ul className="guide-list"><li><strong>Data</strong> shows what is in the dataset and a preview of the rows.</li>
        <li><strong>Examples</strong> lists the questions you marked as correct. Remove any that are wrong.</li>
        <li><strong>Dataset settings</strong> renames the dataset, chooses who can use it (only you, or everyone on this server) and deletes it.</li></ul> },
    { id: "prefs", title: "Make it yours", target: "nav-prefs", place: "right",
      body: <p>In <strong>Preferences</strong> choose whether “sales by region” means a total or an average, which way bars are sorted, and your favourite chart types. The <strong>Theme</strong> button switches between light, dark and your system setting.</p> },
  ];
  if (o.isAdmin) steps.push({ id: "admin", title: "Administration", target: "nav-admin", place: "right",
    body: <p>As an administrator you add people, reset passwords, switch accounts off, and read the feedback users left on answers that looked wrong.</p> });
  steps.push({ id: "done", title: "You are ready", target: "tour-again", place: "top",
    body: <><p>You can replay this tour any time with <strong>Take the tour</strong> in the sidebar. Each page also has its own guide with examples.</p>
      <p>The quickest way to see it all work is to open the demo and ask your first question.</p></>,
    cta: { label: "Open the demo", run: o.tryDemo } });
  return steps;
}
