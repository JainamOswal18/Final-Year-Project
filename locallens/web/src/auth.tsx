import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, setUnauthorizedHandler } from "./api";
import type { DatasetSummary, User } from "./types";

type AuthState = { phase: "loading" } | { phase: "setup" } | { phase: "anonymous" } | { phase: "user"; user: User } | { phase: "error"; message: string };

interface AuthApi { state: AuthState; user: User | null; refresh: () => Promise<void>; signOut: () => Promise<void> }
const AuthCtx = createContext<AuthApi | null>(null);
export const useAuth = () => { const c = useContext(AuthCtx); if (!c) throw new Error("AuthProvider missing"); return c; };

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({ phase: "loading" });
  const refresh = useCallback(async () => {
    try {
      const s = await api.status();
      if (s.setup_required) { setState({ phase: "setup" }); return; }
      try { setState({ phase: "user", user: await api.me() }); } catch { setState({ phase: "anonymous" }); }
    } catch (e) { setState({ phase: "error", message: (e as Error).message }); }
  }, []);
  useEffect(() => { void refresh(); }, [refresh]);
  useEffect(() => { setUnauthorizedHandler(() => setState((s) => (s.phase === "user" ? { phase: "anonymous" } : s))); }, []);
  const signOut = useCallback(async () => { try { await api.logout(); } finally { setState({ phase: "anonymous" }); } }, []);
  const value = useMemo<AuthApi>(() => ({ state, user: state.phase === "user" ? state.user : null, refresh, signOut }), [state, refresh, signOut]);
  return <AuthCtx.Provider value={value}>{children}</AuthCtx.Provider>;
}

/** The dataset list, shared by the sidebar and the Datasets page. */
interface DatasetsApi { list: DatasetSummary[]; loading: boolean; reload: () => Promise<void> }
const DatasetsCtx = createContext<DatasetsApi | null>(null);
export const useDatasets = () => { const c = useContext(DatasetsCtx); if (!c) throw new Error("DatasetsProvider missing"); return c; };
export function DatasetsProvider({ children }: { children: ReactNode }) {
  const [list, setList] = useState<DatasetSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const reload = useCallback(async () => { try { setList(await api.datasets()); } finally { setLoading(false); } }, []);
  useEffect(() => { void reload(); }, [reload]);
  const value = useMemo(() => ({ list, loading, reload }), [list, loading, reload]);
  return <DatasetsCtx.Provider value={value}>{children}</DatasetsCtx.Provider>;
}

export type ThemePref = "system" | "light" | "dark";
export function applyTheme(t: ThemePref) {
  if (t === "system") document.documentElement.removeAttribute("data-theme");
  else document.documentElement.setAttribute("data-theme", t);
}
export function loadTheme(): ThemePref {
  try { const t = localStorage.getItem("ll-theme"); return t === "light" || t === "dark" ? t : "system"; } catch { return "system"; }
}
export function saveTheme(t: ThemePref) { try { localStorage.setItem("ll-theme", t); } catch { /* private mode */ } applyTheme(t); }
