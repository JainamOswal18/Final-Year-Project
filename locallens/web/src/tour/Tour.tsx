import { createContext, useCallback, useContext, useEffect, useId, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { useLocation, useNavigate } from "react-router-dom";
import { api } from "../api";
import { useAuth, useDatasets } from "../auth";
import { Spinner, useToast } from "../ui";
import { placeCard, type Box } from "./place";
import { buildSteps, type TourStep } from "./steps";

interface TourApi { start: () => void; active: boolean }
const TourCtx = createContext<TourApi>({ start: () => {}, active: false });
export const useTour = () => useContext(TourCtx);

const selector = (name: string) => `[data-tour="${name}"]`;
const PAD = 6;

/** Finds the element a step points at (waiting briefly for a page that is still opening) and keeps its position up to date. */
function useTarget(step: TourStep | undefined): Box | null {
  const [box, setBox] = useState<Box | null>(null);
  useLayoutEffect(() => {
    setBox(null);
    if (!step?.target) return;
    const name = step.target;
    let stop = false, tries = 0, timer: ReturnType<typeof setTimeout> | undefined;
    const find = () => document.querySelector<HTMLElement>(selector(name));
    const measure = () => {
      const el = find();
      if (!el) return false;
      const r = el.getBoundingClientRect();
      if (!r.width && !r.height) return false;   // present but hidden (for example the menu on a narrow screen)
      setBox({ top: r.top, left: r.left, width: r.width, height: r.height });
      return true;
    };
    const look = () => {
      if (stop) return;
      const el = find();
      if (el) { el.scrollIntoView?.({ block: "nearest", inline: "nearest" }); measure(); return; }
      if (++tries < 15) timer = setTimeout(look, 100);
    };
    look();
    const again = () => { measure(); };
    window.addEventListener("resize", again);
    window.addEventListener("scroll", again, true);
    return () => { stop = true; if (timer) clearTimeout(timer); window.removeEventListener("resize", again); window.removeEventListener("scroll", again, true); };
  }, [step]);
  return box;
}

function TourOverlay({ steps, index, setIndex, finish }: { steps: TourStep[]; index: number; setIndex: (i: number) => void; finish: () => void }) {
  const step = steps[index];
  const nav = useNavigate();
  const loc = useLocation();
  const titleId = useId(), bodyId = useId();
  const card = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ w: 380, h: 300 });
  const [busy, setBusy] = useState(false);
  const [vp, setVp] = useState({ w: window.innerWidth, h: window.innerHeight });
  const toast = useToast();
  const box = useTarget(step);
  const last = index === steps.length - 1;

  // open the page a step belongs to when its target is not on the current page
  useEffect(() => {
    if (step.route && step.target && !document.querySelector(selector(step.target)) && loc.pathname !== step.route) nav(step.route);
  }, [step, loc.pathname, nav]);

  useEffect(() => {
    const onResize = () => setVp({ w: window.innerWidth, h: window.innerHeight });
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  useLayoutEffect(() => {
    const el = card.current;
    if (el) setSize({ w: el.offsetWidth, h: el.offsetHeight });
  }, [index, box, vp.w, vp.h]);

  useEffect(() => { card.current?.focus(); }, [index]);

  const go = useCallback((i: number) => setIndex(Math.min(Math.max(i, 0), steps.length - 1)), [setIndex, steps.length]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") { e.preventDefault(); finish(); }
      else if (e.key === "ArrowRight") { e.preventDefault(); if (last) finish(); else go(index + 1); }
      else if (e.key === "ArrowLeft") { e.preventDefault(); go(index - 1); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [finish, go, index, last]);

  const where = placeCard(box, size, vp.w, vp.h, step.place);
  const run = async () => {
    if (!step.cta) return;
    setBusy(true);
    try { await step.cta.run(); finish(); } catch (e) { toast((e as Error).message, true); } finally { setBusy(false); }
  };

  return createPortal(
    <div className="tour" data-testid="tour">
      <div className={`tour-block ${box ? "" : "dim"}`} onClick={(e) => e.stopPropagation()} />
      {box && <div className="tour-spot" style={{ top: box.top - PAD, left: box.left - PAD, width: box.width + PAD * 2, height: box.height + PAD * 2 }} />}
      <div ref={card} className={`tour-card ${where.anchored ? "" : "mid"}`} style={{ top: where.top, left: where.left }}
        role="dialog" aria-modal="true" aria-labelledby={titleId} aria-describedby={bodyId} tabIndex={-1}>
        <div className="tour-step">Step {index + 1} of {steps.length}</div>
        <h2 id={titleId}>{step.title}</h2>
        <div className="tour-body" id={bodyId}>{step.body}</div>
        <div className="tour-dots" aria-hidden="true">{steps.map((s, i) => <i key={s.id} className={i === index ? "on" : i < index ? "done" : ""} />)}</div>
        <div className="tour-foot">
          <button className="btn ghost sm" onClick={finish}>{last ? "Close" : "Skip tour"}</button>
          <span className="grow" />
          {index > 0 && <button className="btn sm" onClick={() => go(index - 1)}>Back</button>}
          {step.cta && <button className="btn sm primary" disabled={busy} onClick={() => void run()}>{busy ? <Spinner /> : null} {step.cta.label}</button>}
          {!step.cta && <button className="btn sm primary" onClick={() => (last ? finish() : go(index + 1))}>{last ? "Finish" : index === 0 ? "Start the tour" : "Next"}</button>}
        </div>
      </div>
    </div>,
    document.body,
  );
}

/** Shows the tour to someone using the app for the first time, and lets them replay it from the sidebar. */
export function TourProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const { reload } = useDatasets();
  const nav = useNavigate();
  const toast = useToast();
  const [index, setIndex] = useState<number | null>(null);
  const opener = useRef<HTMLElement | null>(null);

  useEffect(() => {
    let live = true;
    api.prefs().then((p) => { if (live && !p.tour_done) setIndex(0); }, () => { /* no preferences yet: do not nag */ });
    return () => { live = false; };
  }, []);

  const tryDemo = useCallback(async () => {
    const d = await api.demoDataset();
    await reload();
    nav(`/d/${d.id}/ask`);
  }, [reload, nav]);
  const steps = useMemo(() => buildSteps({ isAdmin: user?.role === "admin", tryDemo }), [user?.role, tryDemo]);

  // the page behind the tour cannot be clicked or tabbed into while it is open
  useEffect(() => {
    const root = document.getElementById("root");
    if (!root || index === null) return;
    root.inert = true;
    return () => { root.inert = false; };
  }, [index === null]);

  const finish = useCallback(() => {
    setIndex(null);
    api.setTour(true).catch(() => toast("Could not remember that you finished the tour, so it may show again.", true));
    setTimeout(() => opener.current?.focus(), 0);   // after the page behind the tour is clickable again
  }, [toast]);
  const start = useCallback(() => { opener.current = document.activeElement as HTMLElement | null; setIndex(0); }, []);
  const value = useMemo<TourApi>(() => ({ start, active: index !== null }), [start, index]);

  return (
    <TourCtx.Provider value={value}>
      {children}
      {index !== null && <TourOverlay steps={steps} index={Math.min(index, steps.length - 1)} setIndex={setIndex} finish={finish} />}
    </TourCtx.Provider>
  );
}
