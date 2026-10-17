import { Link } from "react-router-dom";
import { SaveBar, useRegistryEditor } from "../useRegistryEditor";
import { PageHead } from "./DatasetLoader";

export default function ExamplesPage() {
  const { draft, update, dirty, saving, save, discard, detail } = useRegistryEditor();
  return (
    <div className="page">
      <PageHead title="Examples" subtitle="Questions you marked as answered correctly. The assistant is shown the closest ones as a guide when it reads a new question." />
      {draft.examples.length === 0 ? (
        <div className="card pad stack-sm"><strong>No examples yet</strong>
          <p className="muted small">When an answer is right, press “Mark as correct” under it on the <Link to={`/d/${detail.id}/ask`}>Ask</Link> page. Each example makes similar questions more reliable.</p></div>
      ) : (
        <div className="card" style={{ overflow: "auto" }}>
          <table className="t edit">
            <thead><tr><th>Question</th><th>Read as</th><th /></tr></thead>
            <tbody>
              {draft.examples.map((e, i) => {
                const f = e.frame as { intent?: string; metric?: { column?: string }; dimension?: string | null };
                return (
                  <tr key={i}><td><strong>{e.question}</strong></td>
                    <td className="muted small">{f.intent} · {f.metric?.column}{f.dimension ? ` by ${f.dimension}` : ""}</td>
                    <td style={{ textAlign: "right" }}><button className="btn ghost sm" onClick={() => update((d) => { d.examples.splice(i, 1); })}>Remove</button></td></tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      <SaveBar dirty={dirty} saving={saving} onSave={() => void save()} onDiscard={discard} />
    </div>
  );
}
