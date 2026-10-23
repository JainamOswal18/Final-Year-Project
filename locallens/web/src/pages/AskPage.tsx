import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import { AnswerView } from "../AnswerView";
import { LabelProvider, makeLabeler } from "../labels";
import type { Answer, Completion, Message } from "../types";
import { Callout, Icon, Spinner, useAsync } from "../ui";
import { useDataset } from "./DatasetLoader";

interface Turn { key: string; question: string; note?: string; msg?: Message; pending?: boolean; failure?: string }

export default function AskPage() {
  const { detail } = useDataset();
  const { cid } = useParams();
  const nav = useNavigate();
  const [turns, setTurns] = useState<Turn[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [hints, setHints] = useState<Completion[]>([]);
  const [pick, setPick] = useState(-1);
  const convoId = useRef<string | null>(cid ?? null);
  const loadedFor = useRef<string | null>(null);
  const scroller = useRef<HTMLDivElement>(null);
  const box = useRef<HTMLTextAreaElement>(null);
  const suggestions = useAsync(() => api.suggestions(detail.id), [detail.id]);
  const health = useAsync(() => api.health(), []);
  const [loadError, setLoadError] = useState("");

  useEffect(() => {
    convoId.current = cid ?? null;
    if (!cid) { loadedFor.current = null; setTurns([]); return; }
    if (loadedFor.current === cid) return;
    let live = true;
    setLoadError("");
    api.conversation(cid).then((c) => {
      if (!live) return;
      loadedFor.current = cid;
      setTurns(c.messages.map((m) => ({ key: m.id, question: m.response.question, msg: m })));
    }, (e: Error) => live && setLoadError(e.message));
    return () => { live = false; };
  }, [cid, detail.id]);

  useEffect(() => { scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: "smooth" }); }, [turns]);
  useEffect(() => { const el = box.current; if (el) { el.style.height = "auto"; el.style.height = `${Math.min(el.scrollHeight, 140)}px`; } }, [text]);

  const ask = useCallback(async (question: string, overrides?: Record<string, string>, note?: string) => {
    const q = question.trim();
    if (!q || busy) return;
    const key = `${Date.now()}`;
    setBusy(true); setText("");
    setTurns((t) => [...t, { key, question: q, note, pending: true }]);
    try {
      const r = await api.ask(detail.id, q, convoId.current, overrides);
      const msg: Message = { id: r.message_id, rating: null, created_at: "", response: r.response as Answer };
      setTurns((t) => t.map((x) => (x.key === key ? { key: r.message_id, question: q, note, msg } : x)));
      if (!convoId.current) {
        convoId.current = r.conversation_id; loadedFor.current = r.conversation_id;
        nav(`/d/${detail.id}/ask/${r.conversation_id}`, { replace: true });
      }
    } catch (e) {
      setTurns((t) => t.map((x) => (x.key === key ? { key, question: q, note, failure: (e as Error).message } : x)));
    } finally { setBusy(false); box.current?.focus(); }
  }, [busy, detail.id, nav]);

  // typeahead: finish the last word from the dataset's own column names and values
  useEffect(() => {
    if (!text.trim()) { setHints([]); return; }
    let live = true;
    const t = setTimeout(() => {
      api.complete(detail.id, text).then((h) => { if (live) { setHints(h); setPick(-1); } }).catch(() => { if (live) setHints([]); });
    }, 150);
    return () => { live = false; clearTimeout(t); };
  }, [text, detail.id]);
  const accept = (h: Completion) => {
    setText(text.slice(0, text.length - h.replace.length) + h.with + " ");
    setHints([]); setPick(-1); box.current?.focus();
  };

  const starters = suggestions.data ?? [];
  const modelLoading = health.data && !health.data.model_loaded && health.data.model_present;
  const noModel = health.data && !health.data.model_present;
  const empty = turns.length === 0 && !loadError;

  return (
    <LabelProvider registry={detail.registry}>
    <div className="chat">
      <div className="chat-head">
        <div><strong>{detail.name}</strong> <span className="muted small">· ask in plain language</span></div>
        <button className="btn sm" onClick={() => nav(`/d/${detail.id}/ask`)}>{Icon.plus} New chat</button>
      </div>
      <div className="chat-scroll" ref={scroller}>
        <div className="chat-inner">
          {loadError && <Callout kind="bad">{loadError}</Callout>}
          {noModel && <Callout kind="warn"><span>The language model file is missing on the server. Run <code>python scripts/download_model.py</code> once, then restart.</span></Callout>}
          {empty && (
            <div className="empty">
              <h2>What would you like to know?</h2>
              <p className="muted">Ask about {detail.registry.measures.length ? "your metrics, " : ""}totals, trends, comparisons and rankings. The answer comes with a chart and a plain explanation of how it was read.</p>
              {starters.length > 0 && <div className="chips">{starters.map((s) => <button key={s} className="chip" onClick={() => void ask(s)}>{s}</button>)}</div>}
              {detail.problems.length > 0 && detail.can_edit && <Callout kind="warn"><span>{detail.problems.length} definition{detail.problems.length > 1 ? "s are" : " is"} switched off. Check the Definitions page.</span></Callout>}
            </div>
          )}
          {turns.map((t) => (
            <div key={t.key} className="stack-sm">
              <div className="q">{t.question}{t.note && <span style={{ opacity: .75 }}> · {t.note}</span>}</div>
              {t.pending && <div className="card answer"><div className="answer-body"><div className="row muted"><Spinner /> <span>{modelLoading ? "Loading the language model, the first question takes a few seconds…" : "Reading your question…"}</span></div><div className="skeleton" style={{ height: 180 }} /></div></div>}
              {t.failure && <Callout kind="bad">{t.failure}</Callout>}
              {t.msg && <AnswerView msg={t.msg} canEdit={detail.can_edit} suggestions={starters} onPick={(s) => void ask(s)}
                onClarify={(q, field, option) => void ask(q, { [field]: option }, `using ${makeLabeler(detail.registry)(option).toLowerCase()}`)} />}
            </div>
          ))}
        </div>
      </div>
      <div className="composer">
        <div className="composer-inner">
          {hints.length > 0 && (
            <ul className="typeahead" role="listbox" aria-label="Suggestions">
              {hints.map((h, i) => (
                <li key={h.with} role="option" aria-selected={i === pick} className={i === pick ? "on" : ""}
                  onMouseDown={(e) => { e.preventDefault(); accept(h); }}>
                  <span>{h.with}</span><span className="faint tiny">{h.kind}</span>
                </li>
              ))}
            </ul>
          )}
          <form className="composer-box" onSubmit={(e) => { e.preventDefault(); void ask(text); }}>
            <textarea ref={box} rows={1} value={text} placeholder="Ask a question about your data…" aria-label="Your question" maxLength={500}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => {
                if (hints.length) {
                  if (e.key === "ArrowDown") { e.preventDefault(); setPick((p) => (p + 1) % hints.length); return; }
                  if (e.key === "ArrowUp") { e.preventDefault(); setPick((p) => (p <= 0 ? hints.length - 1 : p - 1)); return; }
                  if (e.key === "Escape") { setHints([]); return; }
                  if (e.key === "Tab" || (e.key === "Enter" && pick >= 0)) { e.preventDefault(); accept(hints[Math.max(pick, 0)]); return; }
                }
                if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); void ask(text); }
              }} />
            <button className="btn primary icon" disabled={busy || !text.trim()} aria-label="Send">{busy ? <Spinner /> : Icon.send}</button>
          </form>
          <div className="tiny faint">Runs on this server. Your data and questions are not sent anywhere else.</div>
        </div>
      </div>
    </div>
    </LabelProvider>
  );
}
