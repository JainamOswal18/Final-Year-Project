import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation, useMatch, useNavigate } from "react-router-dom";
import { api } from "./api";
import { DatasetsProvider, loadTheme, saveTheme, useAuth, useDatasets, type ThemePref } from "./auth";
import { Icon } from "./ui";
import type { ConversationSummary } from "./types";

function Brand() {
  return (
    <div className="brand">
      <span className="brand-mark" aria-hidden="true"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2.6" strokeLinecap="round"><circle cx="10.5" cy="10.5" r="6" /><path d="M15.5 15.5L21 21" /></svg></span>
      LocalLens
    </div>
  );
}

function ThemeToggle() {
  const [t, setT] = useState<ThemePref>(loadTheme());
  const next = () => { const n: ThemePref = t === "system" ? "light" : t === "light" ? "dark" : "system"; setT(n); saveTheme(n); };
  return <button onClick={next} title="Switch between light, dark and system theme"><span aria-hidden="true">{t === "dark" ? "☾" : t === "light" ? "☀" : "◐"}</span> Theme: {t}</button>;
}

function Sidebar() {
  const { user, signOut } = useAuth();
  const { list } = useDatasets();
  const nav = useNavigate();
  const loc = useLocation();
  const m = useMatch("/d/:id/*");
  const id = m?.params.id;
  const [convos, setConvos] = useState<ConversationSummary[]>([]);
  useEffect(() => {
    if (!id) { setConvos([]); return; }
    api.conversations(id).then(setConvos, () => setConvos([]));
  }, [id, loc.pathname]);
  const current = list.find((d) => d.id === id);

  return (
    <aside className="sidebar">
      <Brand />
      <nav className="nav" aria-label="Datasets">
        <NavLink to="/datasets" end>{Icon.grid} Datasets</NavLink>
      </nav>
      {id && current && (
        <>
          <div className="stack-sm">
            <div className="nav-label">Dataset</div>
            <select className="select sm" aria-label="Switch dataset" value={id} onChange={(e) => nav(`/d/${e.target.value}/ask`)}>
              {list.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
            </select>
          </div>
          <nav className="nav" aria-label="Dataset">
            <NavLink to={`/d/${id}/ask`}>{Icon.chat} Ask</NavLink>
            <NavLink to={`/d/${id}/data`}>{Icon.table} Data</NavLink>
            {current.can_edit && <>
              <NavLink to={`/d/${id}/columns`}>{Icon.tag} Columns</NavLink>
              <NavLink to={`/d/${id}/definitions`}>{Icon.fn} Definitions</NavLink>
              <NavLink to={`/d/${id}/examples`}>{Icon.check} Examples</NavLink>
              <NavLink to={`/d/${id}/settings`}>{Icon.gear} Dataset settings</NavLink>
            </>}
          </nav>
          <div className="nav-label">Recent chats</div>
          <div className="convo-list">
            {convos.length === 0 && <span className="faint small" style={{ padding: "0 10px" }}>No chats yet</span>}
            {convos.map((c) => <NavLink key={c.id} to={`/d/${id}/ask/${c.id}`} title={c.title}>{c.title}</NavLink>)}
          </div>
        </>
      )}
      <div className="sidebar-foot">
        <nav className="nav" aria-label="Account">
          <NavLink to="/settings">{Icon.gear} Preferences</NavLink>
          {user?.role === "admin" && <NavLink to="/admin">{Icon.users} Administration</NavLink>}
          <ThemeToggle />
        </nav>
        <div className="user-pill">
          <span className="avatar" aria-hidden="true">{user?.username.slice(0, 1).toUpperCase()}</span>
          <span className="grow"><strong>{user?.username}</strong><br /><span className="tiny muted">{user?.role}</span></span>
          <button className="btn ghost sm" onClick={() => void signOut()}>Sign out</button>
        </div>
      </div>
    </aside>
  );
}

export default function Shell() {
  return (
    <DatasetsProvider>
      <div className="shell">
        <Sidebar />
        <main className="main" id="main"><Outlet /></main>
      </div>
    </DatasetsProvider>
  );
}
