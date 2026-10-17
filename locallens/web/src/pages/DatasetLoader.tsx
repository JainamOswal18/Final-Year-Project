import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { Outlet, useParams } from "react-router-dom";
import { api } from "../api";
import { useDatasets } from "../auth";
import type { DatasetDetail, Registry } from "../types";
import { Callout, Spinner, useToast } from "../ui";

interface Ctx { detail: DatasetDetail; reload: () => Promise<void>; setRegistry: (r: Registry, problems: string[]) => void }
const DatasetCtx = createContext<Ctx | null>(null);
export const useDataset = () => { const c = useContext(DatasetCtx); if (!c) throw new Error("no dataset"); return c; };

export default function DatasetLoader() {
  const { id = "" } = useParams();
  const [detail, setDetail] = useState<DatasetDetail | null>(null);
  const [error, setError] = useState("");
  const { reload: reloadList } = useDatasets();
  const toast = useToast();

  const load = useCallback(async () => {
    try { setDetail(await api.dataset(id)); setError(""); } catch (e) { setError((e as Error).message); }
  }, [id]);
  useEffect(() => { setDetail(null); void load(); }, [load]);

  const value = useMemo<Ctx | null>(() => detail && {
    detail,
    reload: async () => { await load(); await reloadList(); },
    setRegistry: (registry, problems) => setDetail((d) => (d ? { ...d, registry, problems } : d)),
  }, [detail, load, reloadList]);

  useEffect(() => { if (error) toast(error, true); }, [error, toast]);
  if (error && !detail) return <div className="page"><Callout kind="bad">{error}</Callout></div>;
  if (!value) return <div className="page"><Spinner /></div>;
  return <DatasetCtx.Provider value={value}><Outlet /></DatasetCtx.Provider>;
}

export function PageHead({ title, subtitle, children }: { title: string; subtitle?: string; children?: React.ReactNode }) {
  return <div className="page-head"><div><h1>{title}</h1>{subtitle && <p>{subtitle}</p>}</div>{children && <div className="row wrap">{children}</div>}</div>;
}
