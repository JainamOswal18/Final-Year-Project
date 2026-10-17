import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "./api";
import type { Registry } from "./types";
import { Spinner, useToast } from "./ui";
import { useDataset } from "./pages/DatasetLoader";

export function useRegistryEditor() {
  const { detail, setRegistry } = useDataset();
  const toast = useToast();
  const [draft, setDraft] = useState<Registry>(() => structuredClone(detail.registry));
  const [saving, setSaving] = useState(false);
  const dirty = useMemo(() => JSON.stringify(draft) !== JSON.stringify(detail.registry), [draft, detail.registry]);

  useEffect(() => {
    if (!dirty) return;
    const warn = (e: BeforeUnloadEvent) => { e.preventDefault(); };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  const update = useCallback((fn: (d: Registry) => void) => {
    setDraft((prev) => { const next = structuredClone(prev); fn(next); return next; });
  }, []);
  const discard = useCallback(() => setDraft(structuredClone(detail.registry)), [detail.registry]);
  const save = useCallback(async () => {
    setSaving(true);
    try {
      const r = await api.saveRegistry(detail.id, draft);
      setRegistry(r.registry, r.problems);
      setDraft(structuredClone(r.registry));
      toast(r.problems.length ? `Saved. ${r.problems.length} definition(s) are switched off, see the list at the top.` : "Saved.");
    } catch (e) { toast((e as Error).message, true); } finally { setSaving(false); }
  }, [detail.id, draft, setRegistry, toast]);
  return { draft, update, dirty, saving, save, discard, detail };
}

export function SaveBar({ dirty, saving, onSave, onDiscard }: { dirty: boolean; saving: boolean; onSave: () => void; onDiscard: () => void }) {
  if (!dirty) return null;
  return (
    <div className="savebar" role="region" aria-label="Unsaved changes">
      <span>You have unsaved changes.</span>
      <span className="row"><button className="btn" onClick={onDiscard} disabled={saving}>Discard</button>
        <button className="btn primary" onClick={onSave} disabled={saving}>{saving ? <Spinner /> : null} Save changes</button></span>
    </div>
  );
}
